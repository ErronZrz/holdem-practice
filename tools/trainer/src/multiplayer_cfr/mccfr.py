"""候选 A 的同步 external-sampling MCCFR 训练核心。"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import fsum

from .chance import CandidateAChance
from .game import (
    ROOT_HISTORY,
    Action,
    Deal,
    acting_player,
    apply_action,
    information_set_key,
    infosets,
    is_terminal,
    terminal_outcome,
    validate_player_count,
)
from .policy import Strategy
from .randomness import (
    CHANCE_PURPOSE,
    OPPONENT_ACTION_PURPOSE,
    derive_seed,
)


class MCCFRError(ValueError):
    """同步 MCCFR 的配置、概率或训练状态违反固定契约时抛出。"""


@dataclass(frozen=True)
class MCCFRConfig:
    """显式描述一次候选 A 离线训练请求，不提供隐式训练默认值。"""

    player_count: int
    iterations: int
    master_seed: int
    average_strategy_start_iteration: int

    def __post_init__(self) -> None:
        validate_player_count(self.player_count)
        _require_positive_int(self.iterations, "迭代次数")
        _require_int(self.master_seed, "master seed")
        average_start = _require_positive_int(
            self.average_strategy_start_iteration, "平均策略起始轮次"
        )
        if average_start > self.iterations:
            raise MCCFRError("平均策略起始轮次必须位于迭代范围内")


@dataclass(frozen=True)
class MCCFRResult:
    """训练核心的内存结果，不代表收敛、质量或可导出的长期策略。"""

    config: MCCFRConfig
    average_strategy: Strategy
    infoset_count: int
    completed_iterations: int


@dataclass(frozen=True)
class TraverserVisit:
    """单个 traverser 信息集访问的公开可审计采样权重。"""

    infoset_key: str
    own_reach: float
    opponent_sampling_probability: float
    average_importance_weight: float


@dataclass(frozen=True)
class TraverserPassTrace:
    """单个相对座位 pass 的种子和抽样摘要，不保留完整私牌发放。"""

    traverser: int
    chance_seed: int
    opponent_action_seed: int
    sampled_opponent_actions: tuple[tuple[str, Action], ...]
    traverser_visits: tuple[TraverserVisit, ...]


@dataclass(frozen=True)
class IterationUpdate:
    """本轮批量提交前收集的稀疏更新快照，仅用于离线核验。"""

    regret_deltas: tuple[tuple[str, tuple[tuple[Action, float], ...]], ...]
    strategy_sum_deltas: tuple[tuple[str, tuple[tuple[Action, float], ...]], ...]


@dataclass(frozen=True)
class IterationTrace:
    """同步 iteration 的固定 traverser 顺序、访问和更新摘要。"""

    iteration: int
    passes: tuple[TraverserPassTrace, ...]
    update: IterationUpdate


@dataclass
class _InfoSetNode:
    actions: tuple[Action, ...]
    regret_sum: dict[Action, float] = field(init=False)
    strategy_sum: dict[Action, float] = field(init=False)

    def __post_init__(self) -> None:
        if not self.actions or len(set(self.actions)) != len(self.actions):
            raise MCCFRError("信息集必须包含不重复的合法动作")
        self.regret_sum = {action: 0.0 for action in self.actions}
        self.strategy_sum = {action: 0.0 for action in self.actions}

    def current_strategy(self) -> dict[Action, float]:
        positive_regrets = {
            action: _require_finite(max(0.0, regret), "累计 regret")
            for action, regret in self.regret_sum.items()
        }
        total = fsum(positive_regrets.values())
        if total == 0.0:
            probability = 1.0 / len(self.actions)
            return {action: probability for action in self.actions}
        return {action: positive_regrets[action] / total for action in self.actions}

    def average_strategy(self) -> dict[Action, float]:
        values = {
            action: _require_finite(value, "平均策略累计量")
            for action, value in self.strategy_sum.items()
        }
        total = fsum(values.values())
        if total == 0.0:
            probability = 1.0 / len(self.actions)
            return {action: probability for action in self.actions}
        if total < 0.0:
            raise MCCFRError("平均策略累计量不能为负")
        return {action: values[action] / total for action in self.actions}


@dataclass
class _IterationDeltas:
    regrets: dict[str, dict[Action, float]] = field(default_factory=dict)
    strategy_sums: dict[str, dict[Action, float]] = field(default_factory=dict)

    def add_regret(self, key: str, action: Action, value: float) -> None:
        self._add(self.regrets, key, action, value)

    def add_strategy_sum(self, key: str, action: Action, value: float) -> None:
        self._add(self.strategy_sums, key, action, value)

    def snapshot(self) -> IterationUpdate:
        """返回按信息集键和动作顺序固定的更新副本。"""

        return IterationUpdate(
            regret_deltas=self._snapshot(self.regrets),
            strategy_sum_deltas=self._snapshot(self.strategy_sums),
        )

    @staticmethod
    def _snapshot(
        values: Mapping[str, Mapping[Action, float]],
    ) -> tuple[tuple[str, tuple[tuple[Action, float], ...]], ...]:
        return tuple(
            (
                key,
                tuple(sorted(action_values.items(), key=lambda item: item[0].value)),
            )
            for key, action_values in sorted(values.items())
        )

    @staticmethod
    def _add(
        target: dict[str, dict[Action, float]], key: str, action: Action, value: float
    ) -> None:
        value = _require_finite(value, "iteration delta")
        action_values = target.setdefault(key, {})
        action_values[action] = fsum((action_values.get(action, 0.0), value))


@dataclass
class _PassTraceBuilder:
    traverser: int
    chance_seed: int
    opponent_action_seed: int
    sampled_opponent_actions: list[tuple[str, Action]] = field(default_factory=list)
    traverser_visits: list[TraverserVisit] = field(default_factory=list)

    def build(self) -> TraverserPassTrace:
        return TraverserPassTrace(
            traverser=self.traverser,
            chance_seed=self.chance_seed,
            opponent_action_seed=self.opponent_action_seed,
            sampled_opponent_actions=tuple(self.sampled_opponent_actions),
            traverser_visits=tuple(self.traverser_visits),
        )


@dataclass(frozen=True)
class N9BoundarySample:
    """N9 单次采样边界结果，不包含更新、平均策略或可导出训练状态。"""

    traverser: int
    infoset_count: int
    trace: TraverserPassTrace


class SynchronousExternalSamplingMCCFR:
    """每轮冻结策略后按相对座位顺序完成全部 external-sampling pass。"""

    def __init__(self, config: MCCFRConfig) -> None:
        self.config = config
        self._nodes = {
            spec.key: _InfoSetNode(spec.actions) for spec in infosets(config.player_count)
        }
        self._completed_iterations = 0

    @property
    def infoset_count(self) -> int:
        """返回由固定规则树预先建立的信息集数量。"""

        return len(self._nodes)

    def average_strategy(self) -> Strategy:
        """返回完整信息集覆盖的当前平均策略副本。"""

        return {key: node.average_strategy() for key, node in self._nodes.items()}

    def run_iteration(self, iteration: int) -> IterationTrace:
        """执行一个同步批次，所有 pass 结束后才写入 regret 和平均策略累计量。"""

        if self.config.player_count == 9:
            raise MCCFRError("N9 仅允许专用单次边界采样，不能执行训练 iteration")
        iteration = _require_positive_int(iteration, "iteration")
        if iteration != self._completed_iterations + 1:
            raise MCCFRError("iteration 必须按顺序从一开始执行")
        if iteration > self.config.iterations:
            raise MCCFRError("iteration 超出配置范围")

        frozen_policy = self._freeze_policy()
        deltas = _IterationDeltas()
        accumulate_average = iteration >= self.config.average_strategy_start_iteration
        traces = tuple(
            self._collect_pass(
                iteration,
                traverser,
                frozen_policy,
                deltas,
                accumulate_average,
            )
            for traverser in range(self.config.player_count)
        )
        update = deltas.snapshot()
        self._apply_deltas(deltas)
        self._completed_iterations = iteration
        return IterationTrace(iteration=iteration, passes=traces, update=update)

    @property
    def completed_iterations(self) -> int:
        """返回已完成的同步 iteration 数，供外层受控运行器审计。"""

        return self._completed_iterations

    def completed_result(self) -> MCCFRResult:
        """仅在全部显式 iteration 完成后返回可导出的内存结果。"""

        if self.config.player_count == 9:
            raise MCCFRError("N9 边界采样不产生可导出的训练结果")
        if self._completed_iterations != self.config.iterations:
            raise MCCFRError("尚未完成全部 iteration，不能生成训练结果")
        return MCCFRResult(
            config=self.config,
            average_strategy=self.average_strategy(),
            infoset_count=self.infoset_count,
            completed_iterations=self._completed_iterations,
        )

    def train(self) -> MCCFRResult:
        """按配置完成有限 iteration；调用方必须显式提供次数和 master seed。"""

        while self._completed_iterations < self.config.iterations:
            self.run_iteration(self._completed_iterations + 1)
        return self.completed_result()

    def _freeze_policy(self) -> dict[str, dict[Action, float]]:
        return {key: node.current_strategy() for key, node in self._nodes.items()}

    def _collect_pass(
        self,
        iteration: int,
        traverser: int,
        frozen_policy: Mapping[str, Mapping[Action, float]],
        deltas: _IterationDeltas,
        accumulate_average: bool,
    ) -> TraverserPassTrace:
        chance_seed = derive_seed(
            self.config.master_seed,
            player_count=self.config.player_count,
            iteration=iteration,
            traverser=traverser,
            purpose=CHANCE_PURPOSE,
        )
        opponent_action_seed = derive_seed(
            self.config.master_seed,
            player_count=self.config.player_count,
            iteration=iteration,
            traverser=traverser,
            purpose=OPPONENT_ACTION_PURPOSE,
        )
        deal = CandidateAChance(self.config.player_count, chance_seed).sample_ordered_deal()
        trace = _PassTraceBuilder(traverser, chance_seed, opponent_action_seed)
        self._traverse(
            deal=deal,
            history=ROOT_HISTORY,
            traverser=traverser,
            frozen_policy=frozen_policy,
            action_random=random.Random(opponent_action_seed),
            own_reach=1.0,
            opponent_sampling_probability=1.0,
            deltas=deltas,
            trace=trace,
            accumulate_average=accumulate_average,
        )
        return trace.build()

    def _traverse(
        self,
        *,
        deal: Deal,
        history: str,
        traverser: int,
        frozen_policy: Mapping[str, Mapping[Action, float]],
        action_random: random.Random,
        own_reach: float,
        opponent_sampling_probability: float,
        deltas: _IterationDeltas,
        trace: _PassTraceBuilder,
        accumulate_average: bool,
    ) -> float:
        if is_terminal(self.config.player_count, history):
            outcome = terminal_outcome(self.config.player_count, deal, history)
            return float(outcome.utilities[traverser])

        actor = acting_player(self.config.player_count, history)
        key = information_set_key(
            self.config.player_count,
            actor,
            deal.rank_for(actor),
            history,
        )
        node = self._nodes[key]
        strategy = frozen_policy[key]
        _validate_distribution(node.actions, strategy)

        if actor != traverser:
            action = _sample_action(node.actions, strategy, action_random)
            probability = strategy[action]
            next_sampling_probability = _require_finite(
                opponent_sampling_probability * probability,
                "对手抽样概率",
            )
            if next_sampling_probability <= 0.0:
                raise MCCFRError("被采样的对手动作必须具有正概率")
            trace.sampled_opponent_actions.append((history, action))
            return self._traverse(
                deal=deal,
                history=apply_action(self.config.player_count, history, action),
                traverser=traverser,
                frozen_policy=frozen_policy,
                action_random=action_random,
                own_reach=own_reach,
                opponent_sampling_probability=next_sampling_probability,
                deltas=deltas,
                trace=trace,
                accumulate_average=accumulate_average,
            )

        importance_weight = _inverse_sampling_probability(opponent_sampling_probability)
        trace.traverser_visits.append(
            TraverserVisit(
                infoset_key=key,
                own_reach=own_reach,
                opponent_sampling_probability=opponent_sampling_probability,
                average_importance_weight=importance_weight,
            )
        )
        if accumulate_average:
            for action in node.actions:
                weighted_probability = own_reach * importance_weight * strategy[action]
                deltas.add_strategy_sum(key, action, weighted_probability)

        action_utilities = {
            action: self._traverse(
                deal=deal,
                history=apply_action(self.config.player_count, history, action),
                traverser=traverser,
                frozen_policy=frozen_policy,
                action_random=action_random,
                own_reach=own_reach * strategy[action],
                opponent_sampling_probability=opponent_sampling_probability,
                deltas=deltas,
                trace=trace,
                accumulate_average=accumulate_average,
            )
            for action in node.actions
        }
        node_utility = fsum(strategy[action] * action_utilities[action] for action in node.actions)
        for action in node.actions:
            deltas.add_regret(key, action, action_utilities[action] - node_utility)
        return node_utility

    def _apply_deltas(self, deltas: _IterationDeltas) -> None:
        for key, node in self._nodes.items():
            for action in node.actions:
                regret = deltas.regrets.get(key, {}).get(action, 0.0)
                strategy_sum = deltas.strategy_sums.get(key, {}).get(action, 0.0)
                if regret:
                    node.regret_sum[action] = fsum((node.regret_sum[action], regret))
                if strategy_sum:
                    node.strategy_sum[action] = fsum((node.strategy_sum[action], strategy_sum))


def run_audit_iteration(
    config: MCCFRConfig,
    initial_regrets: Mapping[str, Mapping[Action, float]],
) -> IterationTrace:
    """以完整显式 regret fixture 执行一次审计采样，不生成训练结果或工件。"""

    if config.player_count == 9:
        raise MCCFRError("N9 不允许 audit iteration")
    trainer = SynchronousExternalSamplingMCCFR(config)
    if set(initial_regrets) != set(trainer._nodes):
        raise MCCFRError("审计 regret fixture 必须完整覆盖候选 A 信息集")
    for key, node in trainer._nodes.items():
        values = initial_regrets[key]
        if set(values) != set(node.actions):
            raise MCCFRError("审计 regret fixture 的动作集合不合法")
        node.regret_sum = {
            action: _require_finite(float(values[action]), "审计 regret fixture")
            for action in node.actions
        }
    return trainer.run_iteration(1)


def sample_n9_boundary(*, master_seed: int, traverser: int) -> N9BoundarySample:
    """执行 N9 的一条不提交更新的 sampled pass，仅供边界测量。"""

    traverser = _require_int(traverser, "traverser")
    if not 0 <= traverser < 9:
        raise MCCFRError("N9 traverser 必须位于相对座位范围内")
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(
            player_count=9,
            iterations=1,
            master_seed=master_seed,
            average_strategy_start_iteration=1,
        )
    )
    frozen_policy = trainer._freeze_policy()
    trace = trainer._collect_pass(
        iteration=1,
        traverser=traverser,
        frozen_policy=frozen_policy,
        deltas=_IterationDeltas(),
        accumulate_average=False,
    )
    return N9BoundarySample(
        traverser=traverser,
        infoset_count=trainer.infoset_count,
        trace=trace,
    )


def train(config: MCCFRConfig) -> MCCFRResult:
    """从零开始执行显式配置的同步 MCCFR，避免复用跨调用状态。"""

    if config.player_count == 9:
        raise MCCFRError("N9 仅允许 sample_n9_boundary，不能执行长期训练")
    return SynchronousExternalSamplingMCCFR(config).train()


def _require_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MCCFRError(f"{label} 必须是整数")
    return value


def _require_positive_int(value: int, label: str) -> int:
    value = _require_int(value, label)
    if value <= 0:
        raise MCCFRError(f"{label} 必须是正整数")
    return value


def _require_finite(value: float, label: str) -> float:
    if not math.isfinite(value):
        raise MCCFRError(f"{label} 必须是有限数")
    return value


def _validate_distribution(actions: tuple[Action, ...], strategy: Mapping[Action, float]) -> None:
    if set(strategy) != set(actions):
        raise MCCFRError("冻结策略动作集与规则信息集不一致")
    probabilities = []
    for action in actions:
        probability = strategy[action]
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise MCCFRError("冻结策略概率必须是数值")
        probability = float(probability)
        if not math.isfinite(probability) or probability < 0.0:
            raise MCCFRError("冻结策略概率必须是非负有限数")
        probabilities.append(probability)
    if not math.isclose(fsum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise MCCFRError("冻结策略概率和必须为一")


def _sample_action(
    actions: tuple[Action, ...], strategy: Mapping[Action, float], action_random: random.Random
) -> Action:
    """只从正概率动作采样，避免浮点边界回退到零概率动作。"""

    draw = action_random.random()
    cumulative = 0.0
    last_positive: Action | None = None
    for action in actions:
        probability = float(strategy[action])
        if probability <= 0.0:
            continue
        cumulative += probability
        last_positive = action
        if draw < cumulative:
            return action
    if last_positive is None:
        raise MCCFRError("冻结策略不存在正概率动作")
    return last_positive


def _inverse_sampling_probability(probability: float) -> float:
    probability = _require_finite(probability, "对手抽样概率")
    if probability <= 0.0:
        raise MCCFRError("对手抽样概率必须为正")
    return _require_finite(1.0 / probability, "平均策略重要性权重")
