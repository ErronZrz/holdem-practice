"""候选 A 策略产物的严格读取与受控 lookup。"""

from __future__ import annotations

import json
import math
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrategyArtifactError(f"JSON 存在重复键：{key}")
        result[key] = value
    return result


def _reject_non_finite_constant(value: str) -> None:
    raise StrategyArtifactError(f"JSON 不允许非有限数值：{value}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
            raise StrategyArtifactError("策略产物必须是非链接的普通文件")
        if path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise StrategyArtifactError("策略产物超过大小上限")
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_constant,
        )
    except OSError as error:
        raise StrategyArtifactError("无法读取策略产物") from error
    except UnicodeError as error:
        raise StrategyArtifactError("策略产物必须是 UTF-8 文本") from error
    except json.JSONDecodeError as error:
        raise StrategyArtifactError("策略产物不是有效 JSON") from error
    if not isinstance(payload, dict):
        raise StrategyArtifactError("策略产物顶层必须是对象")
    return payload


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
    for field in ("prng", "seed_derivation", "python_version", "trainer_version"):
        _require_nonempty_string(training[field], f"training.{field}")
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


def _parse_strategy(entries: Any, game: GameConfig) -> Strategy:
    expected_specs = infoset_by_key(game.player_count)
    if not isinstance(entries, list) or len(entries) != len(expected_specs):
        raise StrategyArtifactError("infosets 未完整覆盖候选 A 的可达信息集")

    strategy: Strategy = {}
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
        strategy[key] = {
            action: parsed_units[action] / PROBABILITY_UNITS for action in spec.actions
        }
    if set(strategy) != set(expected_specs):
        raise StrategyArtifactError("infosets 存在缺失或跨人数条目")
    return strategy


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


def _parse_resources(value: Any, expected_infosets: int) -> dict[str, object]:
    resources = _expect_exact_keys(value, _RESOURCE_FIELDS, "resources")
    _require_finite_number(resources["elapsed_seconds"], "resources.elapsed_seconds", minimum=0.0)
    _require_int(resources["peak_rss_bytes"], "resources.peak_rss_bytes", minimum=0)
    if (
        _require_int(resources["infoset_count"], "resources.infoset_count", minimum=0)
        != expected_infosets
    ):
        raise StrategyArtifactError("resources.infoset_count 与信息集结构不一致")
    _require_int(resources["artifact_bytes"], "resources.artifact_bytes", minimum=0)
    if not isinstance(resources["warning_triggered"], bool) or not isinstance(
        resources["stop_condition_triggered"], bool
    ):
        raise StrategyArtifactError("resources 状态字段必须是布尔值")
    return dict(resources)


def load_strategy(path: str | Path) -> StrategyArtifact:
    """读取并严格验证一个版本化的候选 A 策略产物。"""

    payload = _read_json(Path(path))
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
    strategy = _parse_strategy(payload["infosets"], game)
    return StrategyArtifact(
        game=game,
        strategy=strategy,
        training=_parse_training(payload["training"]),
        quality=_parse_quality(payload["quality"], game.player_count, len(strategy)),
        resources=_parse_resources(payload["resources"], len(strategy)),
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
