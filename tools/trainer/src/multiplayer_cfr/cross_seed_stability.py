"""跨 seed 稳定性的集合级记录：只读聚合已封存的策略产物。

稳定性是「策略集合」的属性，不属于任何单条策略：本模块从一个已有策略产物的集合出发，
在固定审计信息集集合上计算概率的最大 L1 距离，并把参与比较的来源身份一并记录，
便于事后复查。本模块不写回、不改写任何既有工件，也不调用训练或评估原语。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .game import GAME_ID, GAME_VERSION, validate_player_count
from .measurement import (
    MeasurementRecordError,
    audit_infosets_sha256,
    build_stability_payload,
    seed_set_sha256,
    validate_stability,
)
from .policy import StrategyArtifactError, load_quantized_strategy
from .safeio import (
    MAX_TEXT_BYTES,
    SafeJsonError,
    canonical_json_bytes,
    load_canonical_json,
    sha256_identity,
    write_canonical_json,
)

CROSS_SEED_STABILITY_TYPE = "multiplayer-cfr-cross-seed-stability"
CROSS_SEED_STABILITY_SCHEMA_VERSION = 1
MAX_RECORD_BYTES = 4 * 1024 * 1024

_TOP_LEVEL_FIELDS = {"schema_version", "record_type", "game", "stability", "sources"}
_GAME_FIELDS = {"id", "version", "player_count"}
_SOURCE_FIELDS = {"seed", "strategy_sha256", "strategy_bytes"}
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


class CrossSeedStabilityError(ValueError):
    """跨 seed 稳定性记录的来源、指标或规范 JSON 不符合契约时抛出。"""


@dataclass(frozen=True)
class StabilitySource:
    """一条参与比较的已封存策略产物身份及其训练 seed。"""

    seed: int
    strategy_sha256: str
    strategy_bytes: int

    def as_payload(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "strategy_sha256": self.strategy_sha256,
            "strategy_bytes": self.strategy_bytes,
        }


@dataclass(frozen=True)
class SealedStrategySample:
    """从已封存策略产物读出的样本：seed、量化概率单位与来源身份。"""

    seed: int
    units: dict[str, dict[str, int]]
    source: StabilitySource


@dataclass(frozen=True)
class CrossSeedStabilityRecord:
    """已规范化的跨 seed 稳定性记录及其字节身份。"""

    payload: dict[str, object]
    sha256: str
    record_bytes: int


def read_sealed_strategy(path: str | Path) -> SealedStrategySample:
    """只读加载一个已封存策略产物，取出 seed、概率单位与来源身份。"""

    try:
        artifact = load_quantized_strategy(path)
    except (SafeJsonError, StrategyArtifactError) as error:
        raise CrossSeedStabilityError("无法安全读取已封存策略产物") from error
    seed = artifact.artifact.training["master_seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise CrossSeedStabilityError("策略产物的训练 seed 必须是整数")
    units = {
        key: {action.value: value for action, value in entry.items()}
        for key, entry in artifact.action_units.items()
    }
    return SealedStrategySample(
        seed=seed,
        units=units,
        source=StabilitySource(
            seed=seed,
            strategy_sha256=artifact.identity.sha256,
            strategy_bytes=artifact.identity.artifact_bytes,
        ),
    )


def build_cross_seed_stability_record(
    *,
    player_count: int,
    samples: Sequence[SealedStrategySample],
    probability_units: int,
) -> CrossSeedStabilityRecord:
    """聚合至少两条已封存样本，产出集合级的跨 seed 稳定性记录。"""

    player_count = validate_player_count(player_count)
    if not isinstance(samples, Sequence) or len(samples) < 2:
        raise CrossSeedStabilityError("跨 seed 稳定性记录至少需要两条策略样本")
    for sample in samples:
        if not isinstance(sample, SealedStrategySample):
            raise CrossSeedStabilityError("策略样本类型不兼容")

    sources = sorted(
        (sample.source for sample in samples), key=lambda source: source.seed
    )
    try:
        stability = validate_stability(
            build_stability_payload(
                player_count=player_count,
                strategies={sample.seed: sample.units for sample in samples},
                probability_units=probability_units,
            )
        )
    except MeasurementRecordError as error:
        raise CrossSeedStabilityError("策略样本不满足审计集或概率契约") from error
    if stability["status"] != "measured":
        raise CrossSeedStabilityError("跨 seed 稳定性记录必须携带 measured 结果")

    payload = {
        "schema_version": CROSS_SEED_STABILITY_SCHEMA_VERSION,
        "record_type": CROSS_SEED_STABILITY_TYPE,
        "game": {"id": GAME_ID, "version": GAME_VERSION, "player_count": player_count},
        "stability": stability,
        "sources": [source.as_payload() for source in sources],
    }
    _validate_payload(payload)
    return parse_cross_seed_stability_payload(payload)


def parse_cross_seed_stability_payload(
    payload: dict[str, object],
) -> CrossSeedStabilityRecord:
    """严格验证内存载荷并重算其唯一字节身份。"""

    _validate_payload(payload)
    raw_bytes = canonical_json_bytes(payload)
    digest, byte_length = sha256_identity(raw_bytes)
    return CrossSeedStabilityRecord(payload=payload, sha256=digest, record_bytes=byte_length)


def write_cross_seed_stability_record(
    root: str | Path,
    relative_name: str,
    record: CrossSeedStabilityRecord,
    *,
    maximum_bytes: int = MAX_RECORD_BYTES,
) -> CrossSeedStabilityRecord:
    """原子写入由 builder 创建的记录并回读身份。"""

    if not isinstance(record, CrossSeedStabilityRecord):
        raise CrossSeedStabilityError("写入对象必须是跨 seed 稳定性记录")
    _validate_payload(record.payload)
    _, raw_bytes = write_canonical_json(
        root, relative_name, record.payload, maximum_bytes=maximum_bytes
    )
    loaded = load_cross_seed_stability_record(Path(root) / relative_name)
    if loaded.sha256 != record.sha256 or loaded.record_bytes != len(raw_bytes):
        raise CrossSeedStabilityError("跨 seed 稳定性记录回读身份不一致")
    return loaded


def load_cross_seed_stability_record(path: str | Path) -> CrossSeedStabilityRecord:
    """安全读取并严格验证跨 seed 稳定性记录。"""

    try:
        payload, raw_bytes = load_canonical_json(path, maximum_bytes=MAX_TEXT_BYTES)
    except SafeJsonError as error:
        raise CrossSeedStabilityError("无法安全读取跨 seed 稳定性记录") from error
    record = parse_cross_seed_stability_payload(payload)
    if record.record_bytes != len(raw_bytes):
        raise CrossSeedStabilityError("跨 seed 稳定性记录字节身份不一致")
    return record


def _validate_payload(payload: object) -> None:
    if not isinstance(payload, dict):
        raise CrossSeedStabilityError("跨 seed 稳定性记录字段不匹配")
    record = _exact_mapping(payload, _TOP_LEVEL_FIELDS, "跨 seed 稳定性记录")
    if (
        record["schema_version"] != CROSS_SEED_STABILITY_SCHEMA_VERSION
        or record["record_type"] != CROSS_SEED_STABILITY_TYPE
    ):
        raise CrossSeedStabilityError("跨 seed 稳定性记录版本不兼容")

    game = _exact_mapping(record["game"], _GAME_FIELDS, "game")
    if game["id"] != GAME_ID or game["version"] != GAME_VERSION:
        raise CrossSeedStabilityError("跨 seed 稳定性记录游戏版本不兼容")
    player_count = validate_player_count(
        _require_int(game["player_count"], "game.player_count", minimum=2)
    )

    try:
        stability = validate_stability(record["stability"])
    except MeasurementRecordError as error:
        raise CrossSeedStabilityError("跨 seed 稳定性记录的 stability 段不兼容") from error
    if stability["status"] != "measured":
        raise CrossSeedStabilityError("跨 seed 稳定性记录必须携带 measured 结果")

    sources = record["sources"]
    if not isinstance(sources, list) or len(sources) < 2:
        raise CrossSeedStabilityError("跨 seed 稳定性记录至少需要两个来源")
    seeds: list[int] = []
    for entry in sources:
        source = _exact_mapping(entry, _SOURCE_FIELDS, "sources 条目")
        seeds.append(_require_int(source["seed"], "sources.seed", minimum=0))
        if not _is_hash(source["strategy_sha256"]):
            raise CrossSeedStabilityError("来源策略标识必须是小写 SHA-256")
        _require_int(source["strategy_bytes"], "sources.strategy_bytes", minimum=1)
    if len(set(seeds)) != len(seeds):
        raise CrossSeedStabilityError("参与比较的 seed 不能重复")

    # 指标身份必须与来源集合、审计集一致，避免记录被拼装出互相矛盾的声明。
    if stability["seed_set_sha256"] != seed_set_sha256(seeds):
        raise CrossSeedStabilityError("seed 集合身份与来源不一致")
    if stability["audit_infosets_sha256"] != audit_infosets_sha256(player_count):
        raise CrossSeedStabilityError("审计集身份与该人数不一致")


def _exact_mapping(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise CrossSeedStabilityError(f"{label}字段不匹配")
    return value


def _require_int(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CrossSeedStabilityError(f"{label} 必须是不小于 {minimum} 的整数")
    return value


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _HASH_PATTERN.fullmatch(value) is not None
