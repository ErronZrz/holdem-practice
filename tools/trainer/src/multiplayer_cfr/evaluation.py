"""候选 A 的量化策略全 chance profile 与受限阈值 probe 评估。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from fractions import Fraction
from math import factorial

from .chance import iter_ordered_deals
from .game import (
    ROOT_HISTORY,
    Action,
    Deal,
    acting_player,
    apply_action,
    information_set_key,
    is_terminal,
    legal_actions,
    terminal_outcome,
)
from .policy import PROBABILITY_UNITS, QuantizedStrategyArtifact


class EvaluationError(ValueError):
    """全 chance 评估、阈值 probe 或停止检查不符合候选 A 契约时抛出。"""


class EvaluationStopped(EvaluationError):
    """外层检查器要求在 deal 边界停止评估时抛出。"""


@dataclass(frozen=True)
class ProfileEvaluation:
    """对量化策略计算的精确 profile 净收益，不包含均衡解释。"""

    player_count: int
    ordered_deal_count: int
    terminal_leaf_count: int
    utilities: tuple[Fraction, ...]


@dataclass(frozen=True)
class ThresholdProbe:
    """只依赖自身 rank 和公开阶段的预声明阈值偏离。"""

    probe_id: str
    open_threshold: int
    call_threshold: int

    def action_for(self, own_rank: int, history: str, player_count: int) -> Action:
        _validate_threshold(self.open_threshold, player_count, "开池阈值")
        _validate_threshold(self.call_threshold, player_count, "跟注阈值")
        actions = legal_actions(player_count, history)
        if actions == (Action.CHECK, Action.BET):
            return Action.BET if own_rank >= self.open_threshold else Action.CHECK
        if actions == (Action.CALL, Action.FOLD):
            return Action.CALL if own_rank >= self.call_threshold else Action.FOLD
        raise EvaluationError("候选 A 规则返回了未知动作阶段")


@dataclass(frozen=True)
class ProbeResult:
    """一个座位替换为一个预声明阈值策略后的精确收益差。"""

    player: int
    probe_id: str
    utility: Fraction
    delta: Fraction


@dataclass(frozen=True)
class ProbeEvaluation:
    """有限阈值集合的全部结果与每座位最大非负增益。"""

    baseline: ProfileEvaluation
    results: tuple[ProbeResult, ...]
    gains: tuple[Fraction, ...]


@dataclass(frozen=True)
class _Replacement:
    player: int
    probe: ThresholdProbe


def evaluate_profile(
    artifact: QuantizedStrategyArtifact,
    *,
    checkpoint: Callable[[int], bool] | None = None,
) -> ProfileEvaluation:
    """仅对 N=6/7 的量化策略完整枚举 chance 和行为树。"""

    return _evaluate_profile(artifact, replacement=None, checkpoint=checkpoint)


def evaluate_threshold_probes(
    artifact: QuantizedStrategyArtifact,
    probes: Iterable[ThresholdProbe],
    *,
    baseline: ProfileEvaluation | None = None,
    checkpoint: Callable[[int], bool] | None = None,
) -> ProbeEvaluation:
    """逐座位评估预注册阈值偏离，不搜索 best response。"""

    probes = tuple(probes)
    if not probes or len(probes) > 2:
        raise EvaluationError("阈值 probe 必须包含一至两组预声明策略")
    if len({probe.probe_id for probe in probes}) != len(probes):
        raise EvaluationError("阈值 probe 标识不能重复")
    player_count = artifact.artifact.game.player_count
    for probe in probes:
        if not isinstance(probe.probe_id, str) or not probe.probe_id:
            raise EvaluationError("阈值 probe 标识必须是非空字符串")
        _validate_threshold(probe.open_threshold, player_count, "开池阈值")
        _validate_threshold(probe.call_threshold, player_count, "跟注阈值")
    if baseline is None:
        baseline = evaluate_profile(artifact, checkpoint=checkpoint)
    if baseline.player_count != player_count:
        raise EvaluationError("baseline 人数与量化策略不一致")

    results: list[ProbeResult] = []
    gains = [Fraction(0) for _ in range(player_count)]
    for player in range(player_count):
        for probe in probes:
            evaluated = _evaluate_profile(
                artifact,
                replacement=_Replacement(player, probe),
                checkpoint=checkpoint,
            )
            utility = evaluated.utilities[player]
            delta = utility - baseline.utilities[player]
            results.append(
                ProbeResult(player=player, probe_id=probe.probe_id, utility=utility, delta=delta)
            )
            gains[player] = max(gains[player], delta, Fraction(0))
    return ProbeEvaluation(baseline=baseline, results=tuple(results), gains=tuple(gains))


def _evaluate_profile(
    artifact: QuantizedStrategyArtifact,
    *,
    replacement: _Replacement | None,
    checkpoint: Callable[[int], bool] | None,
) -> ProfileEvaluation:
    player_count = artifact.artifact.game.player_count
    if player_count not in {6, 7}:
        raise EvaluationError("完整 chance profile 只允许 N=6 或 N=7")
    if checkpoint is not None and not callable(checkpoint):
        raise EvaluationError("评估检查器必须可调用")

    total = [Fraction(0) for _ in range(player_count)]
    terminal_leaf_count = 0
    for completed_deals, deal in enumerate(iter_ordered_deals(player_count), start=1):
        utilities, leaves = _evaluate_deal(
            artifact,
            deal,
            ROOT_HISTORY,
            replacement=replacement,
        )
        for player, utility in enumerate(utilities):
            total[player] += utility
        terminal_leaf_count += leaves
        if checkpoint is not None and not checkpoint(completed_deals):
            raise EvaluationStopped("外层检查器要求停止完整 chance 评估")

    ordered_deal_count = factorial(player_count)
    utilities = tuple(utility / ordered_deal_count for utility in total)
    if sum(utilities, Fraction(0)) != 0:
        raise EvaluationError("完整 chance profile 未保持候选 A 常和效用")
    return ProfileEvaluation(
        player_count=player_count,
        ordered_deal_count=ordered_deal_count,
        terminal_leaf_count=terminal_leaf_count,
        utilities=utilities,
    )


def _evaluate_deal(
    artifact: QuantizedStrategyArtifact,
    deal: Deal,
    history: str,
    *,
    replacement: _Replacement | None,
) -> tuple[tuple[Fraction, ...], int]:
    player_count = artifact.artifact.game.player_count
    if is_terminal(player_count, history):
        outcome = terminal_outcome(player_count, deal, history)
        return tuple(Fraction(utility) for utility in outcome.utilities), 1

    actor = acting_player(player_count, history)
    key = information_set_key(player_count, actor, deal.rank_for(actor), history)
    action_units = _action_units_for(artifact, key, actor, deal, history, replacement)
    total = [Fraction(0) for _ in range(player_count)]
    terminal_leaf_count = 0
    for action in legal_actions(player_count, history):
        units = action_units[action]
        if units == 0:
            continue
        child_utilities, child_leaves = _evaluate_deal(
            artifact,
            deal,
            apply_action(player_count, history, action),
            replacement=replacement,
        )
        probability = Fraction(units, PROBABILITY_UNITS)
        for player, utility in enumerate(child_utilities):
            total[player] += probability * utility
        terminal_leaf_count += child_leaves
    return tuple(total), terminal_leaf_count


def _action_units_for(
    artifact: QuantizedStrategyArtifact,
    key: str,
    actor: int,
    deal: Deal,
    history: str,
    replacement: _Replacement | None,
) -> dict[Action, int]:
    if replacement is not None and actor == replacement.player:
        chosen = replacement.probe.action_for(
            own_rank=deal.rank_for(actor),
            history=history,
            player_count=artifact.artifact.game.player_count,
        )
        return {
            action: PROBABILITY_UNITS if action is chosen else 0
            for action in legal_actions(artifact.artifact.game.player_count, history)
        }
    try:
        return artifact.action_units[key]
    except KeyError as error:
        raise EvaluationError("量化策略缺少规则信息集") from error


def _validate_threshold(value: int, player_count: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < player_count:
        raise EvaluationError(f"{label}必须位于私有 rank 范围内")
    return value
