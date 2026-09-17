"""候选 A 独立测量记录的严格 schema、读取与原子写入。"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from typing import Any

from .game import GAME_ID, GAME_VERSION, structure_counts, validate_player_count

MEASUREMENT_SCHEMA_VERSION = 1
MEASUREMENT_RECORD_TYPE = "multiplayer-cfr-measurement"
MAX_MEASUREMENT_BYTES = 4 * 1024 * 1024
_MAX_JSON_DEPTH = 32
_MAX_TEXT_LENGTH = 256

_TOP_LEVEL_FIELDS = {
    "schema_version",
    "record_type",
    "game",
    "strategy_ref",
    "experiment_manifest",
    "execution",
    "profile",
    "probes",
    "diagnostics",
    "stability",
    "resources",
}
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_INTEGER_PATTERN = re.compile(r"0|-?[1-9][0-9]*")
_POSITIVE_INTEGER_PATTERN = re.compile(r"[1-9][0-9]*")


class MeasurementRecordError(ValueError):
    """独立测量记录违反 schema 或文件安全契约时抛出。"""


@dataclass(frozen=True)
class RationalValue:
    """规范十进制字符串表示的精确有理数。"""

    numerator: str
    denominator: str

    def __post_init__(self) -> None:
        numerator = _parse_integer_text(self.numerator, "有理数分子")
        denominator = _parse_positive_integer_text(self.denominator, "有理数分母")
        fraction = Fraction(numerator, denominator)
        if (
            str(fraction.numerator) != self.numerator
            or str(fraction.denominator) != self.denominator
        ):
            raise MeasurementRecordError("有理数必须使用既约的规范十进制形式")

    @classmethod
    def from_fraction(cls, value: Fraction) -> RationalValue:
        if not isinstance(value, Fraction):
            raise MeasurementRecordError("只能从 Fraction 创建有理数")
        return cls(numerator=str(value.numerator), denominator=str(value.denominator))

    def as_fraction(self) -> Fraction:
        return Fraction(int(self.numerator), int(self.denominator))

    def as_payload(self) -> dict[str, str]:
        return {"numerator": self.numerator, "denominator": self.denominator}


@dataclass(frozen=True)
class MeasurementRecord:
    """已严格验证的独立测量记录，不改变策略 artifact v1。"""

    payload: dict[str, object]
    sha256: str
    record_bytes: int


def create_measurement_record(payload: dict[str, object]) -> MeasurementRecord:
    """验证内存 payload 并生成规范化、可原子写入的测量记录。"""

    validated = _validate_payload(payload)
    serialized = _canonical_json_bytes(validated)
    return MeasurementRecord(
        payload=validated,
        sha256=sha256(serialized).hexdigest(),
        record_bytes=len(serialized),
    )


def write_measurement(path: str | Path, record: MeasurementRecord) -> MeasurementRecord:
    """以规范 JSON 原子写入已验证记录，并回读确认最终字节。"""

    if not isinstance(record, MeasurementRecord):
        raise MeasurementRecordError("写入对象必须是已验证的测量记录")
    validated = _validate_payload(record.payload)
    serialized = _canonical_json_bytes(validated)
    if len(serialized) > MAX_MEASUREMENT_BYTES:
        raise MeasurementRecordError("测量记录超过大小上限")
    _write_atomically(Path(path), serialized)
    loaded = load_measurement(path)
    if loaded.sha256 != sha256(serialized).hexdigest() or loaded.record_bytes != len(serialized):
        raise MeasurementRecordError("测量记录回读身份不一致")
    return loaded


def load_measurement(path: str | Path) -> MeasurementRecord:
    """安全读取、严格校验并返回独立测量记录。"""

    payload, raw_bytes = _read_json(Path(path))
    validated = _validate_payload(payload)
    canonical = _canonical_json_bytes(validated)
    if raw_bytes != canonical:
        raise MeasurementRecordError("测量记录必须使用规范 JSON 编码")
    return MeasurementRecord(
        payload=validated,
        sha256=sha256(raw_bytes).hexdigest(),
        record_bytes=len(raw_bytes),
    )


def _validate_payload(value: object) -> dict[str, object]:
    payload = _expect_exact_keys(value, _TOP_LEVEL_FIELDS, "测量记录")
    if (
        _require_int(payload["schema_version"], "schema_version", minimum=1)
        != MEASUREMENT_SCHEMA_VERSION
    ):
        raise MeasurementRecordError("测量记录 schema 版本不兼容")
    if payload["record_type"] != MEASUREMENT_RECORD_TYPE:
        raise MeasurementRecordError("测量记录类型不兼容")
    game = _validate_game(payload["game"])
    strategy_ref = _validate_strategy_ref(payload["strategy_ref"], game)
    manifest = _validate_manifest(payload["experiment_manifest"])
    execution = _validate_execution(payload["execution"])
    profile = _validate_profile(payload["profile"], game, strategy_ref)
    probes = _validate_probes(payload["probes"], game, profile, strategy_ref)
    diagnostics = _validate_diagnostics(payload["diagnostics"], game)
    stability = _validate_stability(payload["stability"])
    resources = _validate_resources(payload["resources"])
    if execution["status"] == "completed" and strategy_ref["status"] != "present":
        raise MeasurementRecordError("完成的训练记录必须关联策略产物")
    if strategy_ref["status"] == "not-produced" and (
        profile["status"] != "not-run"
        or probes["status"] != "not-run"
        or stability["status"] == "measured"
    ):
        raise MeasurementRecordError("未生成策略不能携带质量或稳定性结果")
    return {
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
        "record_type": MEASUREMENT_RECORD_TYPE,
        "game": game,
        "strategy_ref": strategy_ref,
        "experiment_manifest": manifest,
        "execution": execution,
        "profile": profile,
        "probes": probes,
        "diagnostics": diagnostics,
        "stability": stability,
        "resources": resources,
    }


def _validate_game(value: object) -> dict[str, object]:
    game = _expect_exact_keys(value, {"id", "version", "player_count"}, "game")
    player_count = validate_player_count(
        _require_int(game["player_count"], "game.player_count", minimum=0)
    )
    if game["id"] != GAME_ID or game["version"] != GAME_VERSION:
        raise MeasurementRecordError("测量记录游戏版本不兼容")
    return {"id": GAME_ID, "version": GAME_VERSION, "player_count": player_count}


def _validate_strategy_ref(value: object, game: dict[str, object]) -> dict[str, object]:
    reference = _expect_exact_keys(
        value,
        {"status", "sha256", "artifact_bytes", "artifact_type", "artifact_schema_version"},
        "strategy_ref",
    )
    status = reference["status"]
    if status == "not-produced":
        if any(reference[field] is not None for field in reference if field != "status"):
            raise MeasurementRecordError("未生成策略时不能伪造策略身份")
        return {
            "status": "not-produced",
            "sha256": None,
            "artifact_bytes": None,
            "artifact_type": None,
            "artifact_schema_version": None,
        }
    if status != "present":
        raise MeasurementRecordError("strategy_ref.status 不兼容")
    artifact_bytes = _require_int(
        reference["artifact_bytes"], "strategy_ref.artifact_bytes", minimum=1
    )
    schema_version = _require_int(
        reference["artifact_schema_version"], "strategy_ref.artifact_schema_version", minimum=1
    )
    artifact_type = _require_string(reference["artifact_type"], "strategy_ref.artifact_type")
    return {
        "status": "present",
        "sha256": _require_hash(reference["sha256"], "strategy_ref.sha256"),
        "artifact_bytes": artifact_bytes,
        "artifact_type": artifact_type,
        "artifact_schema_version": schema_version,
    }


def _validate_manifest(value: object) -> dict[str, object]:
    manifest = _expect_exact_keys(
        value, {"sha256", "kind", "schema_version"}, "experiment_manifest"
    )
    return {
        "sha256": _require_hash(manifest["sha256"], "experiment_manifest.sha256"),
        "kind": _require_string(manifest["kind"], "experiment_manifest.kind"),
        "schema_version": _require_int(
            manifest["schema_version"], "experiment_manifest.schema_version", minimum=1
        ),
    }


def _validate_execution(value: object) -> dict[str, object]:
    execution = _expect_exact_keys(
        value, {"status", "stage", "stop_reason", "controller_id"}, "execution"
    )
    status = execution["status"]
    stop_reason = execution["stop_reason"]
    if status not in {"completed", "stopped", "failed"}:
        raise MeasurementRecordError("execution.status 不兼容")
    if not isinstance(stop_reason, str) or not stop_reason:
        raise MeasurementRecordError("execution.stop_reason 必须是非空字符串")
    if (status == "completed") != (stop_reason == "completed"):
        raise MeasurementRecordError("execution 状态与停止原因不一致")
    return {
        "status": status,
        "stage": _require_string(execution["stage"], "execution.stage"),
        "stop_reason": stop_reason,
        "controller_id": _require_string(execution["controller_id"], "execution.controller_id"),
    }


def _validate_profile(
    value: object, game: dict[str, object], strategy_ref: dict[str, object]
) -> dict[str, object]:
    profile = _expect_exact_keys(
        value,
        {"status", "full_chance", "ordered_deal_count", "terminal_leaf_count", "utilities"},
        "profile",
    )
    status = profile["status"]
    player_count = game["player_count"]
    if status in {"not-run", "stopped"}:
        if (
            profile["full_chance"] is not False
            or profile["ordered_deal_count"] != 0
            or profile["terminal_leaf_count"] != 0
            or profile["utilities"] is not None
        ):
            raise MeasurementRecordError("未完成 profile 的字段必须为未测量值")
        return {
            "status": status,
            "full_chance": False,
            "ordered_deal_count": 0,
            "terminal_leaf_count": 0,
            "utilities": None,
        }
    if status != "completed" or strategy_ref["status"] != "present":
        raise MeasurementRecordError("profile 状态或策略引用不兼容")
    if player_count not in {6, 7} or profile["full_chance"] is not True:
        raise MeasurementRecordError("完整 profile 只允许关联 A6/A7 策略")
    ordered_deal_count = _require_int(
        profile["ordered_deal_count"], "profile.ordered_deal_count", minimum=1
    )
    if ordered_deal_count != structure_counts(player_count).ordered_deals:
        raise MeasurementRecordError("profile chance 数量与游戏不一致")
    terminal_leaf_count = _require_int(
        profile["terminal_leaf_count"], "profile.terminal_leaf_count", minimum=1
    )
    utilities = _validate_rational_array(profile["utilities"], player_count, "profile.utilities")
    if sum((value.as_fraction() for value in utilities), Fraction(0)) != 0:
        raise MeasurementRecordError("profile.utilities 必须保持常和")
    return {
        "status": "completed",
        "full_chance": True,
        "ordered_deal_count": ordered_deal_count,
        "terminal_leaf_count": terminal_leaf_count,
        "utilities": [value.as_payload() for value in utilities],
    }


def _validate_probes(
    value: object,
    game: dict[str, object],
    profile: dict[str, object],
    strategy_ref: dict[str, object],
) -> dict[str, object]:
    probes = _expect_exact_keys(
        value,
        {"status", "manifest_id", "manifest_sha256", "results", "gains"},
        "probes",
    )
    status = probes["status"]
    if status in {"not-run", "stopped"}:
        if (
            probes["manifest_id"] is not None
            or probes["manifest_sha256"] is not None
            or probes["results"] != []
            or probes["gains"] is not None
        ):
            raise MeasurementRecordError("未完成 probe 的字段必须为未测量值")
        return {
            "status": status,
            "manifest_id": None,
            "manifest_sha256": None,
            "results": [],
            "gains": None,
        }
    if (
        status != "completed"
        or profile["status"] != "completed"
        or strategy_ref["status"] != "present"
    ):
        raise MeasurementRecordError("probe 状态、profile 或策略引用不兼容")
    results = probes["results"]
    if not isinstance(results, list) or not results:
        raise MeasurementRecordError("完成的 probe 必须包含结果")
    parsed_results = []
    for result in results:
        entry = _expect_exact_keys(result, {"player", "probe_id", "utility", "delta"}, "probe 结果")
        player = _require_int(entry["player"], "probe.player", minimum=0)
        if player >= game["player_count"]:
            raise MeasurementRecordError("probe.player 超出座位范围")
        parsed_results.append(
            {
                "player": player,
                "probe_id": _require_string(entry["probe_id"], "probe.probe_id"),
                "utility": _parse_rational(entry["utility"], "probe.utility").as_payload(),
                "delta": _parse_rational(entry["delta"], "probe.delta").as_payload(),
            }
        )
    gains = _validate_rational_array(probes["gains"], game["player_count"], "probes.gains")
    if any(value.as_fraction() < 0 for value in gains):
        raise MeasurementRecordError("probes.gains 不能为负")
    return {
        "status": "completed",
        "manifest_id": _require_string(probes["manifest_id"], "probes.manifest_id"),
        "manifest_sha256": _require_hash(probes["manifest_sha256"], "probes.manifest_sha256"),
        "results": parsed_results,
        "gains": [value.as_payload() for value in gains],
    }


def _validate_diagnostics(value: object, game: dict[str, object]) -> dict[str, object]:
    diagnostics = _expect_exact_keys(
        value,
        {"average_strategy_start_iteration", "coverage", "importance_weights"},
        "diagnostics",
    )
    player_count = game["player_count"]
    total_infosets = structure_counts(player_count).infosets
    coverage = _validate_coverage(diagnostics["coverage"], player_count, total_infosets)
    weights = _validate_importance_weights(diagnostics["importance_weights"], player_count)
    return {
        "average_strategy_start_iteration": _require_int(
            diagnostics["average_strategy_start_iteration"],
            "diagnostics.average_strategy_start_iteration",
            minimum=1,
        ),
        "coverage": coverage,
        "importance_weights": weights,
    }


def _validate_coverage(
    value: object, player_count: int, total_infosets: int
) -> list[dict[str, int]]:
    if not isinstance(value, list) or len(value) != player_count:
        raise MeasurementRecordError("diagnostics.coverage 长度不匹配")
    parsed = []
    for entry in value:
        item = _expect_exact_keys(entry, {"traverser", "visits", "visited_infosets"}, "coverage")
        traverser = _require_int(item["traverser"], "diagnostics.coverage.traverser", minimum=0)
        visits = _require_int(item["visits"], "diagnostics.coverage.visits", minimum=0)
        visited = _require_int(
            item["visited_infosets"], "diagnostics.coverage.visited_infosets", minimum=0
        )
        if traverser >= player_count or visited > total_infosets:
            raise MeasurementRecordError("diagnostics.coverage 座位或信息集计数不兼容")
        parsed.append({"traverser": traverser, "visits": visits, "visited_infosets": visited})
    if [item["traverser"] for item in parsed] != list(range(player_count)):
        raise MeasurementRecordError("diagnostics.coverage 必须按相对座位升序完整覆盖")
    return parsed


def _validate_importance_weights(value: object, player_count: int) -> list[dict[str, int]]:
    if not isinstance(value, list) or len(value) != player_count:
        raise MeasurementRecordError("diagnostics.importance_weights 长度不匹配")
    parsed = []
    fields = {"traverser", "visits", "maximum_milli", "p50_milli", "p95_milli", "non_finite_count"}
    for entry in value:
        item = _expect_exact_keys(entry, fields, "importance_weights")
        traverser = _require_int(
            item["traverser"], "diagnostics.importance_weights.traverser", minimum=0
        )
        visits = _require_int(item["visits"], "diagnostics.importance_weights.visits", minimum=0)
        maximum = _require_int(
            item["maximum_milli"], "diagnostics.importance_weights.maximum_milli", minimum=0
        )
        p50 = _require_int(item["p50_milli"], "diagnostics.importance_weights.p50_milli", minimum=0)
        p95 = _require_int(item["p95_milli"], "diagnostics.importance_weights.p95_milli", minimum=0)
        non_finite = _require_int(
            item["non_finite_count"], "diagnostics.importance_weights.non_finite_count", minimum=0
        )
        if traverser >= player_count or not p50 <= p95 <= maximum:
            raise MeasurementRecordError("diagnostics.importance_weights 座位或分位数不兼容")
        parsed.append(
            {
                "traverser": traverser,
                "visits": visits,
                "maximum_milli": maximum,
                "p50_milli": p50,
                "p95_milli": p95,
                "non_finite_count": non_finite,
            }
        )
    if [item["traverser"] for item in parsed] != list(range(player_count)):
        raise MeasurementRecordError("diagnostics.importance_weights 必须按相对座位升序完整覆盖")
    return parsed


def _validate_stability(value: object) -> dict[str, object]:
    stability = _expect_exact_keys(
        value,
        {"status", "seed_set_sha256", "audit_infosets_sha256", "max_l1"},
        "stability",
    )
    status = stability["status"]
    if status in {"not-requested", "not-measured"}:
        if any(stability[field] is not None for field in stability if field != "status"):
            raise MeasurementRecordError("未测量稳定性不能携带结果")
        return {
            "status": status,
            "seed_set_sha256": None,
            "audit_infosets_sha256": None,
            "max_l1": None,
        }
    if status != "measured":
        raise MeasurementRecordError("stability.status 不兼容")
    max_l1 = _parse_rational(stability["max_l1"], "stability.max_l1")
    if max_l1.as_fraction() < 0:
        raise MeasurementRecordError("stability.max_l1 不能为负")
    return {
        "status": "measured",
        "seed_set_sha256": _require_hash(stability["seed_set_sha256"], "stability.seed_set_sha256"),
        "audit_infosets_sha256": _require_hash(
            stability["audit_infosets_sha256"], "stability.audit_infosets_sha256"
        ),
        "max_l1": max_l1.as_payload(),
    }


def _validate_resources(value: object) -> dict[str, object]:
    resources = _expect_exact_keys(
        value,
        {
            "elapsed_milliseconds",
            "wall_time_limit_milliseconds",
            "peak_rss_bytes",
            "rss_warning_bytes",
            "rss_hard_limit_bytes",
            "rss_sampler_id",
            "warning_triggered",
            "retained_artifact_bytes",
            "retained_artifact_limit_bytes",
        },
        "resources",
    )
    retained = _require_int(
        resources["retained_artifact_bytes"], "resources.retained_artifact_bytes", minimum=0
    )
    limit = _require_int(
        resources["retained_artifact_limit_bytes"],
        "resources.retained_artifact_limit_bytes",
        minimum=1,
    )
    if retained > limit:
        raise MeasurementRecordError("resources 保留产物超出上限")
    if not isinstance(resources["warning_triggered"], bool):
        raise MeasurementRecordError("resources.warning_triggered 必须是布尔值")
    rss_warning_bytes = _require_int(
        resources["rss_warning_bytes"], "resources.rss_warning_bytes", minimum=0
    )
    rss_hard_limit_bytes = _require_int(
        resources["rss_hard_limit_bytes"], "resources.rss_hard_limit_bytes", minimum=1
    )
    if rss_warning_bytes >= rss_hard_limit_bytes:
        raise MeasurementRecordError("resources RSS 预警阈值必须小于硬停阈值")
    return {
        "elapsed_milliseconds": _require_int(
            resources["elapsed_milliseconds"], "resources.elapsed_milliseconds", minimum=0
        ),
        "wall_time_limit_milliseconds": _require_int(
            resources["wall_time_limit_milliseconds"],
            "resources.wall_time_limit_milliseconds",
            minimum=1,
        ),
        "peak_rss_bytes": _require_int(
            resources["peak_rss_bytes"], "resources.peak_rss_bytes", minimum=0
        ),
        "rss_warning_bytes": rss_warning_bytes,
        "rss_hard_limit_bytes": rss_hard_limit_bytes,
        "rss_sampler_id": _require_string(resources["rss_sampler_id"], "resources.rss_sampler_id"),
        "warning_triggered": resources["warning_triggered"],
        "retained_artifact_bytes": retained,
        "retained_artifact_limit_bytes": limit,
    }


def _validate_rational_array(value: object, length: int, label: str) -> tuple[RationalValue, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise MeasurementRecordError(f"{label} 长度不匹配")
    return tuple(_parse_rational(item, label) for item in value)


def _parse_rational(value: object, label: str) -> RationalValue:
    rational = _expect_exact_keys(value, {"numerator", "denominator"}, label)
    try:
        return RationalValue(
            numerator=_require_string(rational["numerator"], f"{label}.numerator"),
            denominator=_require_string(rational["denominator"], f"{label}.denominator"),
        )
    except MeasurementRecordError:
        raise


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise MeasurementRecordError("无法读取测量记录") from error
    try:
        with os.fdopen(descriptor, "rb") as source:
            details = os.fstat(source.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise MeasurementRecordError("测量记录必须是非链接的普通文件")
            raw_bytes = source.read(MAX_MEASUREMENT_BYTES + 1)
    except OSError as error:
        raise MeasurementRecordError("无法读取测量记录") from error
    if len(raw_bytes) > MAX_MEASUREMENT_BYTES:
        raise MeasurementRecordError("测量记录超过大小上限")
    try:
        payload = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_constant,
        )
    except UnicodeError as error:
        raise MeasurementRecordError("测量记录必须是 UTF-8 文本") from error
    except (json.JSONDecodeError, RecursionError) as error:
        raise MeasurementRecordError("测量记录不是有效 JSON") from error
    if not isinstance(payload, dict):
        raise MeasurementRecordError("测量记录顶层必须是对象")
    _ensure_max_depth(payload)
    return payload, raw_bytes


def _write_atomically(path: Path, serialized: bytes) -> None:
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink() or path.is_symlink() or path.is_dir():
        raise MeasurementRecordError("测量记录目标必须位于现有非链接目录")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary_path = Path(temporary_name)
    replaced = False
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            os.fchmod(temporary_file.fileno(), 0o600)
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        replaced = True
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        raise MeasurementRecordError("无法原子写入测量记录") from error
    finally:
        if not replaced:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _expect_exact_keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise MeasurementRecordError(f"{label} 字段不匹配")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise MeasurementRecordError(f"测量记录存在重复键：{key}")
        payload[key] = value
    return payload


def _reject_non_finite_constant(value: str) -> None:
    raise MeasurementRecordError(f"测量记录不允许非有限数值：{value}")


def _ensure_max_depth(value: object, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise MeasurementRecordError("测量记录嵌套层级超过上限")
    if isinstance(value, dict):
        for nested in value.values():
            _ensure_max_depth(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _ensure_max_depth(nested, depth + 1)


def _require_int(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise MeasurementRecordError(f"{label} 必须是不小于 {minimum} 的整数")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT_LENGTH:
        raise MeasurementRecordError(f"{label} 必须是长度受限的非空字符串")
    return value


def _require_hash(value: object, label: str) -> str:
    value = _require_string(value, label)
    if _HASH_PATTERN.fullmatch(value) is None:
        raise MeasurementRecordError(f"{label} 必须是小写 SHA-256")
    return value


def _parse_integer_text(value: str, label: str) -> int:
    if _INTEGER_PATTERN.fullmatch(value) is None:
        raise MeasurementRecordError(f"{label} 必须是规范十进制整数")
    return int(value)


def _parse_positive_integer_text(value: str, label: str) -> int:
    if _POSITIVE_INTEGER_PATTERN.fullmatch(value) is None:
        raise MeasurementRecordError(f"{label} 必须是规范正整数")
    return int(value)
