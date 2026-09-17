"""Kuhn 策略的精确均衡质量计算。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product
from math import fsum

from .game import (
    DEALS,
    INFOSETS,
    Action,
    Deal,
    Player,
    acting_player,
    apply_action,
    is_terminal,
    terminal_utility_p0,
)
from .policy import Strategy, uniform_strategy, validate_strategy


@dataclass(frozen=True)
class QualityMetrics:
    profile_value_p0: float
    best_response_value_p0: float
    best_response_value_p1: float
    nash_conv: float
    exploitability: float

    def as_dict(self) -> dict[str, float]:
        return {
            "profile_value_p0": self.profile_value_p0,
            "best_response_value_p0": self.best_response_value_p0,
            "best_response_value_p1": self.best_response_value_p1,
            "nash_conv": self.nash_conv,
            "exploitability": self.exploitability,
        }


def expected_utility_p0(
    strategy_p0: Mapping[str, Mapping[Action, float]],
    strategy_p1: Mapping[str, Mapping[Action, float]],
) -> float:
    """按全部六个等概率 deal 精确计算 P0 的期望净收益。"""

    validated_p0 = validate_strategy(strategy_p0)
    validated_p1 = validate_strategy(strategy_p1)
    return fsum(_deal_utility_p0(deal, "", validated_p0, validated_p1) for deal in DEALS) / len(
        DEALS
    )


def _deal_utility_p0(
    deal: Deal, history: str, strategy_p0: Strategy, strategy_p1: Strategy
) -> float:
    if is_terminal(history):
        return float(terminal_utility_p0(deal, history))
    player = acting_player(history)
    card = deal.card_for(player)
    key = f"p{int(player)}:{card.value}:{history or '-'}"
    strategy = strategy_p0 if player is Player.P0 else strategy_p1
    return fsum(
        probability
        * _deal_utility_p0(deal, apply_action(history, action), strategy_p0, strategy_p1)
        for action, probability in strategy[key].items()
    )


def _pure_strategies(player: Player) -> tuple[Strategy, ...]:
    specs = tuple(spec for spec in INFOSETS if spec.player is player)
    policies: list[Strategy] = []
    for choices in product(*(spec.actions for spec in specs)):
        strategy = uniform_strategy()
        for spec, action in zip(specs, choices, strict=True):
            strategy[spec.key] = {
                candidate: 1.0 if candidate is action else 0.0 for candidate in spec.actions
            }
        policies.append(strategy)
    return tuple(policies)


def best_response_value(
    player: Player, opponent_strategy: Mapping[str, Mapping[Action, float]]
) -> float:
    """枚举 64 个合法纯策略，避免按单个 deal 泄漏对手暗牌。"""

    validated_opponent = validate_strategy(opponent_strategy)
    if player is Player.P0:
        return max(
            expected_utility_p0(candidate, validated_opponent)
            for candidate in _pure_strategies(player)
        )
    if player is Player.P1:
        return max(
            -expected_utility_p0(validated_opponent, candidate)
            for candidate in _pure_strategies(player)
        )
    raise ValueError(f"未知玩家：{player!r}")


def evaluate_quality(strategy: Mapping[str, Mapping[Action, float]]) -> QualityMetrics:
    """计算完整平均策略的精确 NashConv 与 exploitability。"""

    validated = validate_strategy(strategy)
    profile_value_p0 = expected_utility_p0(validated, validated)
    best_response_value_p0 = best_response_value(Player.P0, validated)
    best_response_value_p1 = best_response_value(Player.P1, validated)
    nash_conv = max(0.0, best_response_value_p0 + best_response_value_p1)
    return QualityMetrics(
        profile_value_p0=profile_value_p0,
        best_response_value_p0=best_response_value_p0,
        best_response_value_p1=best_response_value_p1,
        nash_conv=nash_conv,
        exploitability=nash_conv / 2.0,
    )
