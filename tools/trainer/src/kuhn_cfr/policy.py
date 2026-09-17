"""Kuhn 平均策略的安全导出、读取与 lookup。"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .game import INFOSET_BY_KEY, INFOSETS, Action, Card, Player, information_set_key

SCHEMA_VERSION = 1
ARTIFACT_TYPE = "kuhn-average-strategy"
GAME_ID = "kuhn-poker"
GAME_VERSION = "kuhn-v1"
CHANCE_MODEL = "all-six-ordered-deals"
RANDOMNESS_MODE = "none"
PROBABILITY_UNITS = 1_000_000_000_000
MAX_ARTIFACT_BYTES = 1_000_000
QUALITY_FIELDS = (
    "profile_value_p0",
    "best_response_value_p0",
    "best_response_value_p1",
    "nash_conv",
    "exploitability",
)

type Strategy = dict[str, dict[Action, float]]


class StrategyArtifactError(ValueError):
    """策略产物不符合受限格式时抛出。"""


@dataclass(frozen=True)
class TrainingMetadata:
    algorithm: str
    iterations: int
    average_strategy_start_iteration: int
    chance_model: str = CHANCE_MODEL
    seed: int = 0
    randomness: str = RANDOMNESS_MODE


@dataclass(frozen=True)
class StrategyArtifact:
    strategy: Strategy
    metadata: TrainingMetadata
    quality: dict[str, float]


def uniform_strategy() -> Strategy:
    strategy: Strategy = {}
    for spec in INFOSETS:
        probability = 1.0 / len(spec.actions)
        strategy[spec.key] = {action: probability for action in spec.actions}
    return strategy


def validate_strategy(strategy: Mapping[str, Mapping[Action, float]]) -> Strategy:
    if set(strategy) != set(INFOSET_BY_KEY):
        raise StrategyArtifactError("策略必须恰好覆盖 12 个合法信息集")

    validated: Strategy = {}
    for spec in INFOSETS:
        probabilities = strategy[spec.key]
        if set(probabilities) != set(spec.actions):
            raise StrategyArtifactError(f"信息集 {spec.key} 的动作集合不合法")
        values: dict[Action, float] = {}
        for action in spec.actions:
            value = probabilities[action]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StrategyArtifactError("策略概率必须是有限数值")
            numeric_value = float(value)
            if not math.isfinite(numeric_value) or numeric_value < 0.0:
                raise StrategyArtifactError("策略概率必须是有限非负数")
            values[action] = numeric_value
        if not math.isclose(math.fsum(values.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise StrategyArtifactError(f"信息集 {spec.key} 的概率和必须为 1")
        validated[spec.key] = values
    return validated


def _metadata_to_dict(metadata: TrainingMetadata) -> dict[str, Any]:
    _validate_metadata(metadata)
    return {
        "algorithm": metadata.algorithm,
        "iterations": metadata.iterations,
        "average_strategy_start_iteration": metadata.average_strategy_start_iteration,
        "chance_model": metadata.chance_model,
        "seed": metadata.seed,
        "randomness": metadata.randomness,
    }


def _validate_metadata(metadata: TrainingMetadata) -> None:
    if not metadata.algorithm:
        raise StrategyArtifactError("训练算法不能为空")
    if isinstance(metadata.iterations, bool) or metadata.iterations <= 0:
        raise StrategyArtifactError("迭代次数必须是正整数")
    if isinstance(metadata.average_strategy_start_iteration, bool) or not (
        1 <= metadata.average_strategy_start_iteration <= metadata.iterations
    ):
        raise StrategyArtifactError("平均策略起始轮次必须位于迭代范围内")
    if metadata.chance_model != CHANCE_MODEL or metadata.randomness != RANDOMNESS_MODE:
        raise StrategyArtifactError("策略产物的 chance 或随机性模式不兼容")
    if isinstance(metadata.seed, bool) or not isinstance(metadata.seed, int):
        raise StrategyArtifactError("seed 必须是整数")


def _quantize_probabilities(
    probabilities: Mapping[Action, float], actions: tuple[Action, ...]
) -> dict[str, int]:
    values = [probabilities[action] for action in actions]
    total = math.fsum(values)
    normalized = [value / total for value in values]
    raw_values = [value * PROBABILITY_UNITS for value in normalized]
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

    if sum(units) != PROBABILITY_UNITS:
        raise StrategyArtifactError("概率量化后总和不正确")
    return {action.value: unit for action, unit in zip(actions, units, strict=True)}


def _payload(
    strategy: Strategy, metadata: TrainingMetadata, quality: Mapping[str, float]
) -> dict[str, Any]:
    if set(quality) != set(QUALITY_FIELDS):
        raise StrategyArtifactError("质量指标字段不完整")
    serialized_quality: dict[str, float] = {}
    for field in QUALITY_FIELDS:
        value = quality[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise StrategyArtifactError("质量指标必须是有限数值")
        serialized_quality[field] = float(value)

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "game": {"id": GAME_ID, "version": GAME_VERSION},
        "training": _metadata_to_dict(metadata),
        "probability_units": PROBABILITY_UNITS,
        "infosets": [
            {
                "key": spec.key,
                "player": int(spec.player),
                "card": spec.card.value,
                "history": spec.history,
                "actions": _quantize_probabilities(strategy[spec.key], spec.actions),
            }
            for spec in INFOSETS
        ],
        "quality": serialized_quality,
    }


def _write_payload(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    )
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(serialized, encoding="utf-8")
    os.replace(temporary_path, path)


def export_strategy(
    path: str | Path, strategy: Mapping[str, Mapping[Action, float]], metadata: TrainingMetadata
) -> StrategyArtifact:
    """量化并重读策略后计算质量指标，返回已校验的最终产物。"""

    destination = Path(path)
    validated_strategy = validate_strategy(strategy)
    placeholder_quality = {field: 0.0 for field in QUALITY_FIELDS}
    _write_payload(destination, _payload(validated_strategy, metadata, placeholder_quality))
    quantized_artifact = load_strategy(destination)

    from .quality import evaluate_quality

    metrics = evaluate_quality(quantized_artifact.strategy)
    _write_payload(destination, _payload(validated_strategy, metadata, metrics.as_dict()))
    return load_strategy(destination)


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
        if not path.is_file():
            raise StrategyArtifactError("策略产物不存在或不是普通文件")
        if path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise StrategyArtifactError("策略产物超过大小上限")
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_constant,
        )
    except OSError as error:
        raise StrategyArtifactError("无法读取策略产物") from error
    except json.JSONDecodeError as error:
        raise StrategyArtifactError("策略产物不是有效 JSON") from error
    if not isinstance(payload, dict):
        raise StrategyArtifactError("策略产物顶层必须是对象")
    return payload


def _expect_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise StrategyArtifactError(f"{label} 字段不匹配")
    return value


def _require_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StrategyArtifactError(f"{label} 必须是整数")
    return value


def _require_finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategyArtifactError(f"{label} 必须是数值")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise StrategyArtifactError(f"{label} 必须是有限数")
    return numeric_value


def _parse_metadata(value: Any) -> TrainingMetadata:
    training = _expect_exact_keys(
        value,
        {
            "algorithm",
            "iterations",
            "average_strategy_start_iteration",
            "chance_model",
            "seed",
            "randomness",
        },
        "training",
    )
    if not isinstance(training["algorithm"], str):
        raise StrategyArtifactError("算法必须是字符串")
    if not isinstance(training["chance_model"], str) or not isinstance(training["randomness"], str):
        raise StrategyArtifactError("训练模式必须是字符串")
    metadata = TrainingMetadata(
        algorithm=training["algorithm"],
        iterations=_require_int(training["iterations"], "迭代次数"),
        average_strategy_start_iteration=_require_int(
            training["average_strategy_start_iteration"], "平均策略起始轮次"
        ),
        chance_model=training["chance_model"],
        seed=_require_int(training["seed"], "seed"),
        randomness=training["randomness"],
    )
    _validate_metadata(metadata)
    return metadata


def _parse_strategy(entries: Any) -> Strategy:
    if not isinstance(entries, list) or len(entries) != len(INFOSETS):
        raise StrategyArtifactError("infosets 必须恰好包含 12 个条目")

    strategy: Strategy = {}
    for entry in entries:
        parsed = _expect_exact_keys(
            entry, {"key", "player", "card", "history", "actions"}, "信息集"
        )
        key = parsed["key"]
        if not isinstance(key, str) or key in strategy:
            raise StrategyArtifactError("信息集键无效或重复")
        spec = INFOSET_BY_KEY.get(key)
        if spec is None:
            raise StrategyArtifactError("信息集键不在 Kuhn 游戏中")
        if (
            _require_int(parsed["player"], "信息集玩家") != int(spec.player)
            or parsed["card"] != spec.card.value
            or parsed["history"] != spec.history
        ):
            raise StrategyArtifactError("信息集元数据与键不一致")
        action_units = _expect_exact_keys(
            parsed["actions"], {action.value for action in spec.actions}, "动作"
        )
        parsed_units = {
            Action(action): _require_int(units, "动作概率单位")
            for action, units in action_units.items()
        }
        if (
            any(units < 0 for units in parsed_units.values())
            or sum(parsed_units.values()) != PROBABILITY_UNITS
        ):
            raise StrategyArtifactError("动作概率单位不合法")
        strategy[key] = {
            action: parsed_units[action] / PROBABILITY_UNITS for action in spec.actions
        }
    return validate_strategy(strategy)


def _parse_quality(value: Any) -> dict[str, float]:
    quality = _expect_exact_keys(value, set(QUALITY_FIELDS), "quality")
    return {
        field: _require_finite_number(quality[field], f"quality.{field}")
        for field in QUALITY_FIELDS
    }


def load_strategy(path: str | Path) -> StrategyArtifact:
    """读取并严格校验一个版本化 Kuhn 策略产物。"""

    payload = _read_json(Path(path))
    if set(payload) != {
        "schema_version",
        "artifact_type",
        "game",
        "training",
        "probability_units",
        "infosets",
        "quality",
    }:
        raise StrategyArtifactError("策略产物顶层字段不匹配")
    if _require_int(payload["schema_version"], "schema_version") != SCHEMA_VERSION:
        raise StrategyArtifactError("策略产物 schema 版本不兼容")
    if payload["artifact_type"] != ARTIFACT_TYPE:
        raise StrategyArtifactError("策略产物类型不兼容")
    game = _expect_exact_keys(payload["game"], {"id", "version"}, "game")
    if game != {"id": GAME_ID, "version": GAME_VERSION}:
        raise StrategyArtifactError("策略产物游戏版本不兼容")
    if _require_int(payload["probability_units"], "probability_units") != PROBABILITY_UNITS:
        raise StrategyArtifactError("策略产物概率精度不兼容")
    return StrategyArtifact(
        strategy=_parse_strategy(payload["infosets"]),
        metadata=_parse_metadata(payload["training"]),
        quality=_parse_quality(payload["quality"]),
    )


def lookup(
    artifact: StrategyArtifact, player: Player, card: Card, history: str
) -> dict[Action, float]:
    """返回已校验产物中一个合法信息集的独立概率副本。"""

    key = information_set_key(player, card, history)
    try:
        return dict(artifact.strategy[key])
    except KeyError as error:
        raise StrategyArtifactError("策略产物缺少合法信息集") from error
