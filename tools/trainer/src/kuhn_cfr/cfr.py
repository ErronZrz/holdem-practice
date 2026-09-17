"""确定性的全 chance Kuhn CFR 训练。"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import fsum
from time import perf_counter

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
from .policy import Strategy, uniform_strategy

DEFAULT_ITERATIONS = 50_000


@dataclass(frozen=True)
class TrainingConfig:
    iterations: int = DEFAULT_ITERATIONS
    average_strategy_start_iteration: int = 1
    seed: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations <= 0
        ):
            raise ValueError("迭代次数必须是正整数")
        if (
            isinstance(self.average_strategy_start_iteration, bool)
            or not isinstance(self.average_strategy_start_iteration, int)
            or not 1 <= self.average_strategy_start_iteration <= self.iterations
        ):
            raise ValueError("平均策略起始轮次必须位于迭代范围内")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed 必须是整数")


@dataclass(frozen=True)
class TrainingResult:
    config: TrainingConfig
    average_strategy: Strategy
    infoset_count: int
    elapsed_seconds: float = field(compare=False)


@dataclass
class _InfoSetNode:
    actions: tuple[Action, ...]
    regret_sum: dict[Action, float] = field(init=False)
    strategy_sum: dict[Action, float] = field(init=False)

    def __post_init__(self) -> None:
        self.regret_sum = {action: 0.0 for action in self.actions}
        self.strategy_sum = {action: 0.0 for action in self.actions}

    def current_strategy(self) -> dict[Action, float]:
        positive_regrets = {action: max(0.0, value) for action, value in self.regret_sum.items()}
        total = fsum(positive_regrets.values())
        if total == 0.0:
            probability = 1.0 / len(self.actions)
            return {action: probability for action in self.actions}
        return {action: positive_regrets[action] / total for action in self.actions}

    def average_strategy(self) -> dict[Action, float]:
        total = fsum(self.strategy_sum.values())
        if total == 0.0:
            probability = 1.0 / len(self.actions)
            return {action: probability for action in self.actions}
        return {action: self.strategy_sum[action] / total for action in self.actions}


class CFRTrainer:
    """每次迭代完整遍历六个固定 chance deal。"""

    def __init__(self) -> None:
        self._nodes = {spec.key: _InfoSetNode(spec.actions) for spec in INFOSETS}

    def train(self, config: TrainingConfig) -> TrainingResult:
        start = perf_counter()
        for iteration in range(1, config.iterations + 1):
            accumulate_average = iteration >= config.average_strategy_start_iteration
            for deal in DEALS:
                self._cfr(deal, "", 1.0, 1.0, accumulate_average)
        return TrainingResult(
            config=config,
            average_strategy={key: node.average_strategy() for key, node in self._nodes.items()},
            infoset_count=len(self._nodes),
            elapsed_seconds=perf_counter() - start,
        )

    def _cfr(
        self,
        deal: Deal,
        history: str,
        reach_p0: float,
        reach_p1: float,
        accumulate_average: bool,
    ) -> tuple[float, float]:
        if is_terminal(history):
            utility_p0 = float(terminal_utility_p0(deal, history))
            return utility_p0, -utility_p0

        player = acting_player(history)
        card = deal.card_for(player)
        key = f"p{int(player)}:{card.value}:{history or '-'}"
        node = self._nodes[key]
        strategy = node.current_strategy()
        own_reach = reach_p0 if player is Player.P0 else reach_p1
        opponent_reach = reach_p1 if player is Player.P0 else reach_p0
        if accumulate_average:
            for action, probability in strategy.items():
                node.strategy_sum[action] += own_reach * probability

        action_utilities: dict[Action, tuple[float, float]] = {}
        node_utility = [0.0, 0.0]
        for action, probability in strategy.items():
            if player is Player.P0:
                child = self._cfr(
                    deal,
                    apply_action(history, action),
                    reach_p0 * probability,
                    reach_p1,
                    accumulate_average,
                )
            else:
                child = self._cfr(
                    deal,
                    apply_action(history, action),
                    reach_p0,
                    reach_p1 * probability,
                    accumulate_average,
                )
            action_utilities[action] = child
            node_utility[0] += probability * child[0]
            node_utility[1] += probability * child[1]

        player_index = int(player)
        node_value = node_utility[player_index]
        for action, utility in action_utilities.items():
            node.regret_sum[action] += opponent_reach * (utility[player_index] - node_value)
        return node_utility[0], node_utility[1]


def train(config: TrainingConfig | None = None) -> TrainingResult:
    """从零开始训练，避免复用跨次调用的 regret 状态。"""

    return CFRTrainer().train(TrainingConfig() if config is None else config)


def uniform_average_strategy() -> Strategy:
    """提供完整信息集上的均匀策略供独立校验使用。"""

    return uniform_strategy()
