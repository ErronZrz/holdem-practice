"""N=6 external-sampling 更新目标的独立全 chance 对照计算。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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
    infoset_by_key,
    is_terminal,
    legal_actions,
    terminal_outcome,
)
from .policy import validate_strategy


class EstimatorOracleError(ValueError):
    """独立 N=6 estimator 对照的输入不符合固定核验范围时抛出。"""


@dataclass(frozen=True)
class InfoSetEstimatorTarget:
    """一个信息集在单个 traverser pass 中的精确期望更新。"""

    infoset_key: str
    regret_deltas: dict[Action, Fraction]
    strategy_sum_deltas: dict[Action, Fraction]


@dataclass(frozen=True)
class EstimatorOracleResult:
    """选定信息集的精确 external-sampling 更新期望。"""

    player_count: int
    ordered_deal_count: int
    accumulate_average: bool
    targets: tuple[InfoSetEstimatorTarget, ...]


def exact_external_sampling_targets(
    frozen_policy: Mapping[str, Mapping[Action, float]],
    target_keys: Iterable[str],
    *,
    player_count: int = 6,
    accumulate_average: bool = True,
) -> EstimatorOracleResult:
    """全枚举 N=6 chance 与对手采样分布，计算选定信息集的更新期望。"""

    if player_count != 6:
        raise EstimatorOracleError("独立 estimator 对照只允许 N=6")
    if not isinstance(accumulate_average, bool):
        raise EstimatorOracleError("平均策略累计标记必须是布尔值")
    validated = validate_strategy(frozen_policy, player_count)
    exact_policy = {
        key: {action: Fraction(str(probability)) for action, probability in actions.items()}
        for key, actions in validated.items()
    }
    specs = infoset_by_key(player_count)
    selected_keys = tuple(target_keys)
    if not selected_keys or len(set(selected_keys)) != len(selected_keys):
        raise EstimatorOracleError("核验目标必须是非空且不重复的信息集键")
    selected = {}
    for key in selected_keys:
        spec = specs.get(key)
        if spec is None:
            raise EstimatorOracleError("核验目标不属于 N=6 候选 A 信息集")
        selected[key] = spec

    updates = {
        key: {
            "regrets": {action: Fraction(0) for action in spec.actions},
            "strategy_sums": {action: Fraction(0) for action in spec.actions},
        }
        for key, spec in selected.items()
    }
    chance_probability = Fraction(1, factorial(player_count))
    for traverser in sorted({spec.actor for spec in selected.values()}):
        for deal in iter_ordered_deals(player_count):
            _walk_expected(
                deal=deal,
                history=ROOT_HISTORY,
                traverser=traverser,
                exact_policy=exact_policy,
                selected=selected,
                updates=updates,
                chance_probability=chance_probability,
                opponent_sampling_probability=Fraction(1),
                own_reach=Fraction(1),
                accumulate_average=accumulate_average,
            )

    return EstimatorOracleResult(
        player_count=player_count,
        ordered_deal_count=factorial(player_count),
        accumulate_average=accumulate_average,
        targets=tuple(
            InfoSetEstimatorTarget(
                infoset_key=key,
                regret_deltas=dict(updates[key]["regrets"]),
                strategy_sum_deltas=dict(updates[key]["strategy_sums"]),
            )
            for key in selected_keys
        ),
    )


def _walk_expected(
    *,
    deal: Deal,
    history: str,
    traverser: int,
    exact_policy: Mapping[str, Mapping[Action, Fraction]],
    selected: Mapping[str, object],
    updates: dict[str, dict[str, dict[Action, Fraction]]],
    chance_probability: Fraction,
    opponent_sampling_probability: Fraction,
    own_reach: Fraction,
    accumulate_average: bool,
) -> tuple[Fraction, ...]:
    player_count = deal.player_count
    if is_terminal(player_count, history):
        return tuple(
            Fraction(value) for value in terminal_outcome(player_count, deal, history).utilities
        )

    actor = acting_player(player_count, history)
    key = information_set_key(player_count, actor, deal.rank_for(actor), history)
    strategy = exact_policy[key]
    actions = legal_actions(player_count, history)
    if actor != traverser:
        return _expected_opponent_node(
            deal=deal,
            history=history,
            traverser=traverser,
            exact_policy=exact_policy,
            selected=selected,
            updates=updates,
            chance_probability=chance_probability,
            opponent_sampling_probability=opponent_sampling_probability,
            own_reach=own_reach,
            accumulate_average=accumulate_average,
            strategy=strategy,
            actions=actions,
        )

    action_utilities = {
        action: _walk_expected(
            deal=deal,
            history=apply_action(player_count, history, action),
            traverser=traverser,
            exact_policy=exact_policy,
            selected=selected,
            updates=updates,
            chance_probability=chance_probability,
            opponent_sampling_probability=opponent_sampling_probability,
            own_reach=own_reach * strategy[action],
            accumulate_average=accumulate_average,
        )
        for action in actions
    }
    node_utilities = tuple(
        sum(strategy[action] * action_utilities[action][player] for action in actions)
        for player in range(player_count)
    )
    if key in selected:
        target_update = updates[key]
        if accumulate_average:
            for action in actions:
                target_update["strategy_sums"][action] += (
                    chance_probability * own_reach * strategy[action]
                )
        for action in actions:
            target_update["regrets"][action] += (
                chance_probability
                * opponent_sampling_probability
                * (action_utilities[action][traverser] - node_utilities[traverser])
            )
    return node_utilities


def _expected_opponent_node(
    *,
    deal: Deal,
    history: str,
    traverser: int,
    exact_policy: Mapping[str, Mapping[Action, Fraction]],
    selected: Mapping[str, object],
    updates: dict[str, dict[str, dict[Action, Fraction]]],
    chance_probability: Fraction,
    opponent_sampling_probability: Fraction,
    own_reach: Fraction,
    accumulate_average: bool,
    strategy: Mapping[Action, Fraction],
    actions: tuple[Action, ...],
) -> tuple[Fraction, ...]:
    total = [Fraction(0) for _ in range(deal.player_count)]
    for action in actions:
        probability = strategy[action]
        if probability == 0:
            continue
        child = _walk_expected(
            deal=deal,
            history=apply_action(deal.player_count, history, action),
            traverser=traverser,
            exact_policy=exact_policy,
            selected=selected,
            updates=updates,
            chance_probability=chance_probability,
            opponent_sampling_probability=opponent_sampling_probability * probability,
            own_reach=own_reach,
            accumulate_average=accumulate_average,
        )
        for player, utility in enumerate(child):
            total[player] += probability * utility
    return tuple(total)
