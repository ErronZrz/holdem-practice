"""候选 A 策略产物的严格读取与受控 lookup。"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .chance import PRNG_ID
from .game import (
    ANTE,
    BET,
    GAME_ID,
    GAME_VERSION,
    Action,
    CandidateARuleError,
    GameConfig,
    InfoSetSpec,
    information_set_key,
    infoset_by_key,
    validate_player_count,
)
from .randomness import SEED_DERIVATION_ID
from .resources import estimate_resources

if TYPE_CHECKING:
    from .mccfr import MCCFRResult

SCHEMA_VERSION = 1
ARTIFACT_TYPE = "multiplayer-cfr-average-strategy"
PROBABILITY_UNITS = 1_000_000_000_000
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
ALGORITHM = "synchronous-external-sampling-mccfr-v1"
UPDATE_MODE = "synchronous-batched"
ITERATION_DEFINITION = "one-pass-per-relative-seat"
CHANCE_MODEL = "uniform-ordered-deals"
TRAVERSER_SCHEDULE = "ascending-relative-seat"

_GAME_FIELDS = {
    "id",
    "version",
    "player_count",
    "deck",
    "ante",
    "bet",
    "action_tree_version",
    "tie_rule",
    "remainder_priority",
    "seat_semantics",
}
_TRAINING_FIELDS = {
    "algorithm",
    "update_mode",
    "iteration_definition",
    "iterations",
    "average_strategy_start_iteration",
    "chance_model",
    "traverser_schedule",
    "master_seed",
    "prng",
    "seed_derivation",
    "python_version",
    "trainer_version",
}
_QUALITY_FIELDS = {
    "profile_id",
    "full_chance",
    "sample_seed",
    "sample_count",
    "utilities",
    "probe_manifest_id",
    "probe_gains",
    "coverage",
    "stability",
}
_RESOURCE_FIELDS = {
    "elapsed_seconds",
    "peak_rss_bytes",
    "infoset_count",
    "artifact_bytes",
    "warning_triggered",
    "stop_condition_triggered",
}
_INFOSET_FIELDS = {"key", "actor", "rank", "history", "public_state", "legal_actions", "actions"}
_PUBLIC_STATE_FIELDS = {
    "actor",
    "opener",
    "folded",
    "active",
    "contributions",
    "pending_responders",
    "terminal",
}
_VERSION_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")
_ARTIFACT_SIZE_FIXPOINT_LIMIT = 16


type Strategy = dict[str, dict[Action, float]]


class StrategyArtifactError(ValueError):
    """策略产物违反受限 JSON 或抽象边界时抛出。"""


@dataclass(frozen=True)
class StrategyArtifact:
    """已验证的候选 A 策略及其声明性审计元数据。"""

    game: GameConfig
    strategy: Strategy
    training: dict[str, object]
    quality: dict[str, object]
    resources: dict[str, object]


@dataclass(frozen=True)
class StrategyArtifactIdentity:
    """与一次安全读取绑定的策略字节身份。"""

    sha256: str
    artifact_bytes: int


@dataclass(frozen=True)
class QuantizedStrategyArtifact:
    """保留导出概率单位的已验证策略，供精确离线评估使用。"""

    artifact: StrategyArtifact
    action_units: dict[str, dict[Action, int]]
    identity: StrategyArtifactIdentity


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrategyArtifactError(f"JSON 存在重复键：{key}")
        result[key] = value
    return result


def _reject_non_finite_constant(value: str) -> None:
    raise StrategyArtifactError(f"JSON 不允许非有限数值：{value}")


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except OSError as error:
        raise StrategyArtifactError("无法读取策略产物") from error

    try:
        with os.fdopen(descriptor, "rb") as source:
            details = os.fstat(source.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise StrategyArtifactError("策略产物必须是非链接的普通文件")
            raw_bytes = source.read(MAX_ARTIFACT_BYTES + 1)
    except OSError as error:
        raise StrategyArtifactError("无法读取策略产物") from error

    if len(raw_bytes) > MAX_ARTIFACT_BYTES:
        raise StrategyArtifactError("策略产物超过大小上限")
    try:
        payload = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_constant,
        )
    except UnicodeError as error:
        raise StrategyArtifactError("策略产物必须是 UTF-8 文本") from error
    except json.JSONDecodeError as error:
        raise StrategyArtifactError("策略产物不是有效 JSON") from error
    if not isinstance(payload, dict):
        raise StrategyArtifactError("策略产物顶层必须是对象")
    return payload, raw_bytes


def _expect_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise StrategyArtifactError(f"{label} 字段不匹配")
    return value


def _require_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StrategyArtifactError(f"{label} 必须是整数")
    if minimum is not None and value < minimum:
        raise StrategyArtifactError(f"{label} 不能小于 {minimum}")
    return value


def _require_finite_number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategyArtifactError(f"{label} 必须是数值")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise StrategyArtifactError(f"{label} 必须是有限数")
    if minimum is not None and numeric_value < minimum:
        raise StrategyArtifactError(f"{label} 不能小于 {minimum}")
    return numeric_value


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise StrategyArtifactError(f"{label} 必须是非空字符串")
    return value


def _require_seats(
    value: Any, player_count: int, label: str, *, preserve_order: bool = False
) -> list[int]:
    if not isinstance(value, list):
        raise StrategyArtifactError(f"{label} 必须是座位数组")
    seats = [_require_int(seat, label, minimum=0) for seat in value]
    if any(seat >= player_count for seat in seats) or len(seats) != len(set(seats)):
        raise StrategyArtifactError(f"{label} 必须是不重复的相对座位")
    if not preserve_order and seats != sorted(seats):
        raise StrategyArtifactError(f"{label} 必须按相对座位升序排列")
    return seats


def _parse_game(value: Any) -> GameConfig:
    game = _expect_exact_keys(value, _GAME_FIELDS, "game")
    try:
        player_count = validate_player_count(
            _require_int(game["player_count"], "game.player_count")
        )
    except CandidateARuleError as error:
        raise StrategyArtifactError("策略产物人数不兼容") from error
    deck = _expect_exact_keys(game["deck"], {"rank_count", "copies_per_rank"}, "game.deck")
    if (
        game["id"] != GAME_ID
        or game["version"] != GAME_VERSION
        or _require_int(deck["rank_count"], "game.deck.rank_count") != player_count
        or _require_int(deck["copies_per_rank"], "game.deck.copies_per_rank") != 1
        or _require_int(game["ante"], "game.ante") != ANTE
        or _require_int(game["bet"], "game.bet") != BET
        or game["action_tree_version"] != "single-open-v1"
        or game["tie_rule"] != "highest-unique-rank-wins-all"
        or game["remainder_priority"] != "not-applicable"
        or game["seat_semantics"] != "relative-seat-0-is-first-actor"
    ):
        raise StrategyArtifactError("策略产物游戏描述不兼容")
    return GameConfig(player_count)


def _parse_training(value: Any) -> dict[str, object]:
    training = _expect_exact_keys(value, _TRAINING_FIELDS, "training")
    if (
        training["algorithm"] != ALGORITHM
        or training["update_mode"] != UPDATE_MODE
        or training["iteration_definition"] != ITERATION_DEFINITION
        or training["chance_model"] != CHANCE_MODEL
        or training["traverser_schedule"] != TRAVERSER_SCHEDULE
        or training["prng"] != PRNG_ID
        or training["seed_derivation"] != SEED_DERIVATION_ID
    ):
        raise StrategyArtifactError("训练语义与候选 A 契约不兼容")
    iterations = _require_int(training["iterations"], "training.iterations", minimum=1)
    average_start = _require_int(
        training["average_strategy_start_iteration"],
        "training.average_strategy_start_iteration",
        minimum=1,
    )
    if average_start > iterations:
        raise StrategyArtifactError("平均策略起始轮次超出迭代范围")
    _require_int(training["master_seed"], "training.master_seed")
    for field in ("python_version", "trainer_version"):
        value = _require_nonempty_string(training[field], f"training.{field}")
        if _VERSION_TOKEN_PATTERN.fullmatch(value) is None:
            raise StrategyArtifactError(f"training.{field} 不是受控版本标识")
    return dict(training)


def _parse_public_state(value: Any, player_count: int) -> dict[str, object]:
    projection = _expect_exact_keys(value, _PUBLIC_STATE_FIELDS, "public_state")
    actor = projection["actor"]
    opener = projection["opener"]
    if actor is not None:
        actor = _require_int(actor, "public_state.actor", minimum=0)
        if actor >= player_count:
            raise StrategyArtifactError("public_state.actor 超出座位范围")
    if opener is not None:
        opener = _require_int(opener, "public_state.opener", minimum=0)
        if opener >= player_count:
            raise StrategyArtifactError("public_state.opener 超出座位范围")
    contributions = projection["contributions"]
    if not isinstance(contributions, list) or len(contributions) != player_count:
        raise StrategyArtifactError("public_state.contributions 长度不匹配")
    parsed_contributions = [
        _require_int(contribution, "public_state.contributions", minimum=ANTE)
        for contribution in contributions
    ]
    if not isinstance(projection["terminal"], bool):
        raise StrategyArtifactError("public_state.terminal 必须是布尔值")
    return {
        "actor": actor,
        "opener": opener,
        "folded": _require_seats(projection["folded"], player_count, "public_state.folded"),
        "active": _require_seats(projection["active"], player_count, "public_state.active"),
        "contributions": parsed_contributions,
        "pending_responders": _require_seats(
            projection["pending_responders"],
            player_count,
            "public_state.pending_responders",
            preserve_order=True,
        ),
        "terminal": projection["terminal"],
    }


def validate_strategy(
    strategy: Mapping[str, Mapping[Action, float]], player_count: int
) -> Strategy:
    """验证完整候选 A 策略仅覆盖可达信息集及其规则动作。"""

    player_count = validate_player_count(player_count)
    if not isinstance(strategy, Mapping):
        raise StrategyArtifactError("策略必须是信息集到动作概率的映射")
    expected_specs = infoset_by_key(player_count)
    if set(strategy) != set(expected_specs):
        raise StrategyArtifactError("策略必须完整覆盖候选 A 的可达信息集")

    validated: Strategy = {}
    for key in sorted(expected_specs):
        spec = expected_specs[key]
        probabilities = strategy[key]
        if not isinstance(probabilities, Mapping) or set(probabilities) != set(spec.actions):
            raise StrategyArtifactError(f"信息集 {key} 的动作集合不合法")
        values: dict[Action, float] = {}
        for action in spec.actions:
            value = probabilities[action]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StrategyArtifactError("策略概率必须是有限数值")
            numeric_value = float(value)
            if not math.isfinite(numeric_value) or numeric_value < 0.0:
                raise StrategyArtifactError("策略概率必须是有限非负数")
            values[action] = numeric_value
        if not math.isclose(math.fsum(values.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise StrategyArtifactError(f"信息集 {key} 的概率和必须为 1")
        validated[key] = values
    return validated


def _parse_strategy(
    entries: Any, game: GameConfig
) -> tuple[Strategy, dict[str, dict[Action, int]]]:
    expected_specs = infoset_by_key(game.player_count)
    if not isinstance(entries, list) or len(entries) != len(expected_specs):
        raise StrategyArtifactError("infosets 未完整覆盖候选 A 的可达信息集")

    strategy: Strategy = {}
    strategy_units: dict[str, dict[Action, int]] = {}
    for entry in entries:
        parsed = _expect_exact_keys(entry, _INFOSET_FIELDS, "信息集")
        key = parsed["key"]
        if not isinstance(key, str) or key in strategy:
            raise StrategyArtifactError("信息集键无效或重复")
        spec = expected_specs.get(key)
        if spec is None:
            raise StrategyArtifactError("信息集键不属于该人数的候选 A")
        _validate_infoset_entry(parsed, spec)
        action_units = _expect_exact_keys(
            parsed["actions"], {action.value for action in spec.actions}, "动作概率"
        )
        parsed_units = {
            action: _require_int(action_units[action.value], "动作概率单位", minimum=0)
            for action in spec.actions
        }
        if sum(parsed_units.values()) != PROBABILITY_UNITS:
            raise StrategyArtifactError("动作概率单位和不正确")
        strategy_units[key] = parsed_units
        strategy[key] = {
            action: parsed_units[action] / PROBABILITY_UNITS for action in spec.actions
        }
    return validate_strategy(strategy, game.player_count), strategy_units


def _validate_infoset_entry(entry: dict[str, Any], spec: InfoSetSpec) -> None:
    if (
        _require_int(entry["actor"], "信息集行动者") != spec.actor
        or _require_int(entry["rank"], "信息集 rank") != spec.rank
        or entry["history"] != spec.history
        or entry["legal_actions"] != [action.value for action in spec.actions]
    ):
        raise StrategyArtifactError("信息集元数据或动作与规范键不一致")
    if (
        _parse_public_state(entry["public_state"], spec.player_count)
        != spec.public_state.projection()
    ):
        raise StrategyArtifactError("信息集公开投影不能由历史复核")


def _parse_quality(value: Any, player_count: int, expected_infosets: int) -> dict[str, object]:
    quality = _expect_exact_keys(value, _QUALITY_FIELDS, "quality")
    _require_nonempty_string(quality["profile_id"], "quality.profile_id")
    if not isinstance(quality["full_chance"], bool):
        raise StrategyArtifactError("quality.full_chance 必须是布尔值")
    sample_seed = quality["sample_seed"]
    if sample_seed is not None:
        _require_int(sample_seed, "quality.sample_seed")
    _require_int(quality["sample_count"], "quality.sample_count", minimum=0)
    utilities = quality["utilities"]
    if not isinstance(utilities, list) or len(utilities) != player_count:
        raise StrategyArtifactError("quality.utilities 长度不匹配")
    parsed_utilities = [_require_int(utility, "quality.utilities") for utility in utilities]
    if sum(parsed_utilities) != 0:
        raise StrategyArtifactError("quality.utilities 必须保持常和")
    _require_nonempty_string(quality["probe_manifest_id"], "quality.probe_manifest_id")
    probe_gains = quality["probe_gains"]
    if not isinstance(probe_gains, list) or len(probe_gains) != player_count:
        raise StrategyArtifactError("quality.probe_gains 长度不匹配")
    parsed_probe_gains = [
        _require_finite_number(probe_gain, "quality.probe_gains", minimum=0.0)
        for probe_gain in probe_gains
    ]
    coverage = _expect_exact_keys(
        quality["coverage"], {"visited_infosets", "total_infosets"}, "quality.coverage"
    )
    visited_infosets = _require_int(
        coverage["visited_infosets"], "quality.coverage.visited_infosets", minimum=0
    )
    total_infosets = _require_int(
        coverage["total_infosets"], "quality.coverage.total_infosets", minimum=0
    )
    if total_infosets != expected_infosets or visited_infosets > total_infosets:
        raise StrategyArtifactError("quality.coverage 与信息集结构不一致")
    stability = _expect_exact_keys(quality["stability"], {"status"}, "quality.stability")
    _require_nonempty_string(stability["status"], "quality.stability.status")
    return {
        "profile_id": quality["profile_id"],
        "full_chance": quality["full_chance"],
        "sample_seed": sample_seed,
        "sample_count": quality["sample_count"],
        "utilities": parsed_utilities,
        "probe_manifest_id": quality["probe_manifest_id"],
        "probe_gains": parsed_probe_gains,
        "coverage": {"visited_infosets": visited_infosets, "total_infosets": total_infosets},
        "stability": {"status": stability["status"]},
    }


def _parse_resources(
    value: Any, expected_infosets: int, artifact_bytes: int, player_count: int
) -> dict[str, object]:
    resources = _expect_exact_keys(value, _RESOURCE_FIELDS, "resources")
    _require_finite_number(resources["elapsed_seconds"], "resources.elapsed_seconds", minimum=0.0)
    _require_int(resources["peak_rss_bytes"], "resources.peak_rss_bytes", minimum=0)
    if (
        _require_int(resources["infoset_count"], "resources.infoset_count", minimum=0)
        != expected_infosets
    ):
        raise StrategyArtifactError("resources.infoset_count 与信息集结构不一致")
    declared_artifact_bytes = _require_int(
        resources["artifact_bytes"], "resources.artifact_bytes", minimum=0
    )
    if declared_artifact_bytes != artifact_bytes:
        raise StrategyArtifactError("resources.artifact_bytes 与文件实际大小不一致")
    if artifact_bytes > estimate_resources(player_count).artifact_budget_bytes:
        raise StrategyArtifactError("策略产物超过该人数的静态产物预算")
    if not isinstance(resources["warning_triggered"], bool) or not isinstance(
        resources["stop_condition_triggered"], bool
    ):
        raise StrategyArtifactError("resources 状态字段必须是布尔值")
    return dict(resources)


def _quantize_probabilities(
    probabilities: Mapping[Action, float], actions: tuple[Action, ...]
) -> dict[str, int]:
    values = [probabilities[action] for action in actions]
    total = math.fsum(values)
    if total <= 0.0:
        raise StrategyArtifactError("概率量化前总和必须为正")
    raw_values = [value / total * PROBABILITY_UNITS for value in values]
    units = [math.floor(value) for value in raw_values]
    remainder = PROBABILITY_UNITS - sum(units)
    fractions = [value - math.floor(value) for value in raw_values]

    if remainder > 0:
        order = sorted(
            range(len(actions)), key=lambda index: (-fractions[index], actions[index].value)
        )
        for index in order[:remainder]:
            units[index] += 1
    elif remainder < 0:
        order = sorted(
            range(len(actions)), key=lambda index: (fractions[index], actions[index].value)
        )
        for index in order[:-remainder]:
            if units[index] == 0:
                raise StrategyArtifactError("概率量化失败")
            units[index] -= 1

    if any(unit < 0 for unit in units) or sum(units) != PROBABILITY_UNITS:
        raise StrategyArtifactError("概率量化后总和不正确")
    return {action.value: unit for action, unit in zip(actions, units, strict=True)}


def _game_payload(player_count: int) -> dict[str, object]:
    return {
        "id": GAME_ID,
        "version": GAME_VERSION,
        "player_count": player_count,
        "deck": {"rank_count": player_count, "copies_per_rank": 1},
        "ante": ANTE,
        "bet": BET,
        "action_tree_version": "single-open-v1",
        "tie_rule": "highest-unique-rank-wins-all",
        "remainder_priority": "not-applicable",
        "seat_semantics": "relative-seat-0-is-first-actor",
    }


def _not_measured_quality(player_count: int, infoset_count: int) -> dict[str, object]:
    return {
        "profile_id": "not-measured",
        "full_chance": False,
        "sample_seed": None,
        "sample_count": 0,
        "utilities": [0] * player_count,
        "probe_manifest_id": "not-measured",
        "probe_gains": [0.0] * player_count,
        "coverage": {"visited_infosets": 0, "total_infosets": infoset_count},
        "stability": {"status": "not-measured"},
    }


def _export_payload(
    strategy: Strategy,
    result: MCCFRResult,
    trainer_version: str,
    artifact_bytes: int,
) -> dict[str, object]:
    config = result.config
    player_count = config.player_count
    expected_specs = infoset_by_key(player_count)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "game": _game_payload(player_count),
        "training": {
            "algorithm": ALGORITHM,
            "update_mode": UPDATE_MODE,
            "iteration_definition": ITERATION_DEFINITION,
            "iterations": config.iterations,
            "average_strategy_start_iteration": config.average_strategy_start_iteration,
            "chance_model": CHANCE_MODEL,
            "traverser_schedule": TRAVERSER_SCHEDULE,
            "master_seed": config.master_seed,
            "prng": PRNG_ID,
            "seed_derivation": SEED_DERIVATION_ID,
            "python_version": ".".join(map(str, sys.version_info[:3])),
            "trainer_version": trainer_version,
        },
        "probability_units": PROBABILITY_UNITS,
        "infosets": [
            {
                "key": spec.key,
                "actor": spec.actor,
                "rank": spec.rank,
                "history": spec.history,
                "public_state": spec.public_state.projection(),
                "legal_actions": [action.value for action in spec.actions],
                "actions": _quantize_probabilities(strategy[spec.key], spec.actions),
            }
            for spec in sorted(expected_specs.values(), key=lambda spec: spec.key)
        ],
        "quality": _not_measured_quality(player_count, len(expected_specs)),
        "resources": {
            "elapsed_seconds": 0.0,
            "peak_rss_bytes": 0,
            "infoset_count": len(expected_specs),
            "artifact_bytes": artifact_bytes,
            "warning_triggered": False,
            "stop_condition_triggered": False,
        },
    }


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (serialized + "\n").encode("utf-8")


def _serialized_export(strategy: Strategy, result: MCCFRResult, trainer_version: str) -> bytes:
    artifact_bytes = 0
    for _ in range(_ARTIFACT_SIZE_FIXPOINT_LIMIT):
        serialized = _canonical_json_bytes(
            _export_payload(strategy, result, trainer_version, artifact_bytes)
        )
        actual_bytes = len(serialized)
        if actual_bytes == artifact_bytes:
            return serialized
        artifact_bytes = actual_bytes
    raise StrategyArtifactError("策略产物字节数无法在固定上限内收敛")


def _write_atomically(path: Path, serialized: bytes) -> None:
    parent = path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise StrategyArtifactError("策略产物父目录必须是现有非链接目录")
    if path.is_symlink() or path.is_dir():
        raise StrategyArtifactError("策略产物目标不能是链接或目录")

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
        raise StrategyArtifactError("无法原子写入策略产物") from error
    finally:
        if not replaced:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def export_strategy(
    path: str | Path, result: MCCFRResult, *, trainer_version: str
) -> StrategyArtifact:
    """导出完整平均策略为规范 JSON，并严格回读最终字节。"""

    from .mccfr import MCCFRResult

    if not isinstance(result, MCCFRResult):
        raise StrategyArtifactError("导出器只接受候选 A 的 MCCFR 结果")
    if result.completed_iterations != result.config.iterations:
        raise StrategyArtifactError("未完成的 MCCFR 结果不能导出")
    expected_infosets = len(infoset_by_key(result.config.player_count))
    if result.infoset_count != expected_infosets:
        raise StrategyArtifactError("MCCFR 结果的信息集计数不匹配")
    if (
        not isinstance(trainer_version, str)
        or _VERSION_TOKEN_PATTERN.fullmatch(trainer_version) is None
    ):
        raise StrategyArtifactError("trainer_version 必须是受控版本标识")

    strategy = validate_strategy(result.average_strategy, result.config.player_count)
    serialized = _serialized_export(strategy, result, trainer_version)
    artifact_budget = estimate_resources(result.config.player_count).artifact_budget_bytes
    if len(serialized) > MAX_ARTIFACT_BYTES or len(serialized) > artifact_budget:
        raise StrategyArtifactError("策略产物超过静态大小预算")

    destination = Path(path)
    _write_atomically(destination, serialized)
    _, actual_raw_bytes = _read_json(destination)
    if len(actual_raw_bytes) != len(serialized):
        raise StrategyArtifactError("策略产物回读字节数不一致")
    artifact = load_strategy(destination)
    if artifact.resources["artifact_bytes"] != len(actual_raw_bytes):
        raise StrategyArtifactError("策略产物回读资源字段不一致")
    return artifact


def _load_strategy_payload(
    payload: dict[str, Any], raw_bytes: bytes
) -> tuple[StrategyArtifact, dict[str, dict[Action, int]]]:
    if set(payload) != {
        "schema_version",
        "artifact_type",
        "game",
        "training",
        "probability_units",
        "infosets",
        "quality",
        "resources",
    }:
        raise StrategyArtifactError("策略产物顶层字段不匹配")
    if _require_int(payload["schema_version"], "schema_version") != SCHEMA_VERSION:
        raise StrategyArtifactError("策略产物 schema 版本不兼容")
    if payload["artifact_type"] != ARTIFACT_TYPE:
        raise StrategyArtifactError("策略产物类型不兼容")
    if _require_int(payload["probability_units"], "probability_units") != PROBABILITY_UNITS:
        raise StrategyArtifactError("策略产物概率精度不兼容")
    game = _parse_game(payload["game"])
    strategy, action_units = _parse_strategy(payload["infosets"], game)
    artifact = StrategyArtifact(
        game=game,
        strategy=strategy,
        training=_parse_training(payload["training"]),
        quality=_parse_quality(payload["quality"], game.player_count, len(strategy)),
        resources=_parse_resources(
            payload["resources"], len(strategy), len(raw_bytes), game.player_count
        ),
    )
    return artifact, action_units


def load_strategy(path: str | Path) -> StrategyArtifact:
    """读取并严格验证一个版本化的候选 A 策略产物。"""

    payload, raw_bytes = _read_json(Path(path))
    artifact, _ = _load_strategy_payload(payload, raw_bytes)
    return artifact


def load_quantized_strategy(path: str | Path) -> QuantizedStrategyArtifact:
    """在一次安全读取中验证策略、保留量化概率单位并计算内容摘要。"""

    payload, raw_bytes = _read_json(Path(path))
    artifact, action_units = _load_strategy_payload(payload, raw_bytes)
    return QuantizedStrategyArtifact(
        artifact=artifact,
        action_units=action_units,
        identity=StrategyArtifactIdentity(
            sha256=sha256(raw_bytes).hexdigest(),
            artifact_bytes=len(raw_bytes),
        ),
    )


def lookup(
    artifact: StrategyArtifact,
    *,
    game_version: str,
    player_count: int,
    relative_actor: int,
    own_rank: int,
    canonical_public_history: str,
) -> dict[Action, float]:
    """只接受候选 A 的受控抽象投影，拒绝跨版本、跨人数和非法信息集。"""

    if game_version != GAME_VERSION:
        raise StrategyArtifactError("lookup 的游戏版本不兼容")
    if player_count != artifact.game.player_count:
        raise StrategyArtifactError("lookup 的人数与策略产物不一致")
    try:
        key = information_set_key(
            player_count,
            relative_actor,
            own_rank,
            canonical_public_history,
        )
    except CandidateARuleError as error:
        raise StrategyArtifactError("lookup 输入不属于受控候选 A 抽象") from error
    try:
        return dict(artifact.strategy[key])
    except KeyError as error:
        raise StrategyArtifactError("策略产物缺少合法信息集") from error
