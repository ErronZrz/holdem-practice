"""分布观测能力的契约回归：声明三态、三项入口、两种口径与合并取整。

只做有界单元/集成回归：不跑质量验证、不对抗对局、不访问真实库、不写任何工件。
本文件通过不代表任何质量结论。
"""

import inspect
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import pytest

from app.poker.actions import ActionType, LegalActions
from app.poker.engine import PokerEngine
from app.strategy import distribution_observation as observation
from app.strategy import registry
from app.strategy.mixed_context import mixed_state
from app.strategy.mixed_policy import MixedCandidate, MixedDistribution
from app.strategy.mixed_strategy import MIXED_STRATEGY_RULES
from app.strategy.projection import project_for_actor

from .mixed_bot_states import apply_node, build_node

CAPABILITY_IDENTIFIER = "mixed-local@8"
# 只用于验证「声明支持但能力整体不可用」路径的测试专用标识，不是受控策略身份。
UNSUPPORTED_IDENTIFIER = "observation-probe-unsupported@1"

# 测试侧独立写一遍规范次序，避免直接引用实现内部的排序索引。
_CANONICAL_ACTIONS = (
    ActionType.FOLD,
    ActionType.CHECK,
    ActionType.CALL,
    ActionType.BET,
    ActionType.RAISE,
)
_ACTION_INDEX = {action: index for index, action in enumerate(_CANONICAL_ACTIONS)}

ENTRY = registry.observation_entry(CAPABILITY_IDENTIFIER)

# 覆盖不同街与不同合法集形状的固定节点。
NODES = (
    ("unopened-open", 2),
    ("facing-first-raise", 3),
    ("short-stack-call", 3),
    ("free-check", 2),
    ("sizes-merged", 2),
    ("shared-board", 2),
)


def _order_key(key: tuple[ActionType, int]) -> tuple[int, int]:
    return (_ACTION_INDEX[key[0]], key[1])


def _units_map(distribution: MixedDistribution) -> dict[tuple[ActionType, int], int]:
    return {
        (candidate.action, candidate.amount): candidate.units
        for candidate in distribution.candidates
    }


def _distribution(*entries: tuple[ActionType, int, int]) -> MixedDistribution:
    return MixedDistribution(
        candidates=tuple(
            MixedCandidate(action=action, amount=amount, units=units)
            for action, amount, units in entries
        )
    )


def _node(category: str, player_count: int):
    applied = apply_node(build_node(category, player_count))
    return applied.actor_state(), applied.legal_actions()


# ------------------------------------------------------------------ 能力声明


def test_registered_identity_declares_fixed_capability() -> None:
    declaration = registry.capability_declaration(CAPABILITY_IDENTIFIER)
    assert declaration == observation.supported_declaration()
    assert declaration.supported is True
    assert declaration.capability_id == observation.CAPABILITY_ID
    assert declaration.probability_units == observation.PROBABILITY_UNITS
    assert declaration.modes == observation.OBSERVATION_MODES == ("normal", "cautious", "pressed")
    assert declaration.mode_weights == observation.MODE_WEIGHTS == (8, 1, 1)
    assert declaration.amount_semantics == observation.AMOUNT_SEMANTICS


def test_declaration_read_is_decoupled_from_query_inputs() -> None:
    """声明读取只接受标识：不需要对局状态，也不需要构造策略实例。"""
    parameters = inspect.signature(registry.capability_declaration).parameters
    assert list(parameters) == ["value"]
    assert list(inspect.signature(registry.observation_entry).parameters) == ["value"]
    assert list(inspect.signature(registry.capability_health).parameters) == []


@pytest.mark.parametrize("value", ["mixed-local", "mixed-local@9", "heuristic@1", "random@1"])
def test_declaration_missing_for_unknown_or_undeclared_identifier(value: str) -> None:
    with pytest.raises(observation.DeclarationMissingError):
        registry.capability_declaration(value)
    with pytest.raises(observation.DeclarationMissingError):
        registry.observation_entry(value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"capability_id": "distribution-observation@2"},
        {"probability_units": 999_999},
        {"probability_units": None},
        {"modes": ("normal", "cautious")},
        {"modes": None},
        {"mode_weights": (7, 2, 1)},
        {"mode_weights": None},
        {"amount_semantics": ("bet=anything",)},
        {"amount_semantics": None},
    ],
)
def test_supported_declaration_must_be_complete_and_fixed(overrides: dict) -> None:
    declaration = replace(observation.supported_declaration(), **overrides)
    with pytest.raises(observation.DeclarationInvalidError):
        declaration.validate()


def test_unsupported_declaration_only_commits_two_fields() -> None:
    declaration = observation.CapabilityDeclaration(capability_id="anything", supported=False)
    declaration.validate()
    noisy = replace(
        declaration,
        probability_units=1,
        modes=("somewhere",),
        mode_weights=(1,),
        amount_semantics=("unknown",),
    )
    # 不支持时其余参数一律不读取、不比对，因此噪声取值同样不构成声明失败。
    noisy.validate()


def test_unsupported_registration_refuses_query_entry() -> None:
    observation.register_observation_entry(
        UNSUPPORTED_IDENTIFIER,
        observation.CapabilityDeclaration(capability_id="whatever", supported=False),
        MIXED_STRATEGY_RULES[CAPABILITY_IDENTIFIER],
    )
    declaration = observation.declaration_for(UNSUPPORTED_IDENTIFIER)
    assert declaration.supported is False
    with pytest.raises(observation.CapabilityUnavailableError):
        observation.entry_for(UNSUPPORTED_IDENTIFIER)


# ------------------------------------------------------------------ 三项入口


def test_three_entrypoints_are_registered_and_callable() -> None:
    assert set(registry.OBSERVATION_ENTRYPOINTS) == {"declaration", "health", "query"}
    assert all(
        callable(entry) for entry in registry.OBSERVATION_ENTRYPOINTS.values()
    )


def test_health_read_is_closed_two_value_enum() -> None:
    assert {member.value for member in observation.CapabilityHealth} == {
        "available",
        "unavailable",
    }
    result = registry.capability_health()
    assert result is observation.CapabilityHealth.AVAILABLE
    assert result == "available"


def test_health_read_reports_unavailable_when_implementation_absent(monkeypatch) -> None:
    monkeypatch.setattr(observation, "_ENTRIES", {})
    result = registry.capability_health()
    # 不可用是一个返回值，不是异常，也不是不可解析结果。
    assert result is observation.CapabilityHealth.UNAVAILABLE


# ------------------------------------------------------------------ 观测输出


@pytest.mark.parametrize(("category", "player_count"), NODES)
def test_marginalized_output_is_well_formed(category: str, player_count: int) -> None:
    state, legal = _node(category, player_count)
    result = ENTRY.observe(state, legal)
    assert result.aggregation == "marginalized"
    assert result.overridden_mode is None
    assert result.probability_units == observation.PROBABILITY_UNITS
    assert result.mode_weights == observation.MODE_WEIGHTS
    assert len(result.candidates) >= 2
    _assert_candidates_well_formed(result, legal)


@pytest.mark.parametrize(("category", "player_count"), NODES)
@pytest.mark.parametrize("mode", ["normal", "cautious", "pressed"])
def test_mode_override_output_carries_the_overridden_mode(
    category: str, player_count: int, mode: str
) -> None:
    state, legal = _node(category, player_count)
    result = ENTRY.observe(state, legal, mode)
    assert result.aggregation == "mode_override"
    assert result.overridden_mode == mode
    assert result.probability_units == observation.PROBABILITY_UNITS
    assert result.mode_weights == observation.MODE_WEIGHTS
    _assert_candidates_well_formed(result, legal)


def _assert_candidates_well_formed(result, legal: LegalActions) -> None:
    keys = [(candidate.action, candidate.amount) for candidate in result.candidates]
    assert len(set(keys)) == len(keys)
    assert keys == sorted(keys, key=_order_key)
    assert sum(candidate.units for candidate in result.candidates) == result.probability_units

    allowed = {
        ActionType.FOLD: legal.can_fold,
        ActionType.CHECK: legal.can_check,
        ActionType.CALL: legal.can_call,
        ActionType.BET: legal.can_bet,
        ActionType.RAISE: legal.can_raise,
    }
    intervals = {
        ActionType.BET: (legal.min_bet, legal.max_bet),
        ActionType.RAISE: (legal.min_raise_to, legal.max_raise_to),
    }
    for candidate in result.candidates:
        assert candidate.units >= 0
        assert allowed[candidate.action]
        if candidate.action in (ActionType.FOLD, ActionType.CHECK, ActionType.CALL):
            assert candidate.amount == 0
        else:
            low, high = intervals[candidate.action]
            assert low <= candidate.amount <= high


def test_marginalized_and_override_queries_are_repeatable() -> None:
    state, legal = _node("sizes-merged", 2)
    assert ENTRY.observe(state, legal) == ENTRY.observe(state, legal)
    assert ENTRY.observe(state, legal, "pressed") == ENTRY.observe(state, legal, "pressed")


def test_observation_does_not_consume_the_action_stream() -> None:
    state, legal = _node("free-check", 2)
    strategy = registry.create_strategy(CAPABILITY_IDENTIFIER, seed=3311)
    baseline = strategy.choose_action(state, legal)
    for _ in range(3):
        ENTRY.observe(state, legal)
        ENTRY.observe(state, legal, "cautious")
    assert strategy.choose_action(state, legal) == baseline


# ------------------------------------------------------------------ 非法输入


@pytest.mark.parametrize("mode", ["careful", "Normal", "NORMAL", "", 1])
def test_unsupported_mode_override_is_illegal_input(mode) -> None:
    state, legal = _node("free-check", 2)
    with pytest.raises(observation.IllegalObservationInputError):
        ENTRY.observe(state, legal, mode)


def test_state_without_public_summary_is_illegal_input() -> None:
    engine = PokerEngine(3, 5, 10, 1000, seed=5)
    engine.start_hand()
    with pytest.raises(observation.IllegalObservationInputError):
        ENTRY.observe(project_for_actor(engine.snapshot()), engine.legal_actions())


def test_incoherent_legal_actions_are_illegal_input() -> None:
    state, legal = _node("free-check", 2)
    contradictory = replace(legal, can_check=True, can_call=True)
    with pytest.raises(observation.IllegalObservationInputError):
        ENTRY.observe(state, contradictory)


def test_actor_outside_declared_seats_is_illegal_input() -> None:
    state, legal = _node("unopened-open", 3)
    actor = state.current_seat
    other_seat = 0 if actor != 0 else 1
    context = state.context.model_copy(update={"bot_seats": (other_seat,)})
    alt_state = mixed_state(state, context)
    with pytest.raises(observation.IllegalObservationInputError):
        ENTRY.observe(alt_state, legal)


# ------------------------------------------------------------------ 合并取整


def test_marginalize_uses_fixed_integer_weights_and_exact_totals() -> None:
    per_mode = {
        "normal": _distribution(
            (ActionType.CALL, 0, 500_000), (ActionType.BET, 100, 500_000)
        ),
        "cautious": _distribution(
            (ActionType.CALL, 0, 300_000), (ActionType.BET, 100, 700_000)
        ),
        "pressed": _distribution(
            (ActionType.CALL, 0, 300_005), (ActionType.BET, 100, 699_995)
        ),
    }
    units = _units_map_from(observation.marginalize(per_mode))
    assert set(units) == {(ActionType.CALL, 0), (ActionType.BET, 100)}
    assert sum(units.values()) == observation.PROBABILITY_UNITS

    tables = [_units_map(per_mode[mode]) for mode in observation.OBSERVATION_MODES]
    total_weight = sum(observation.MODE_WEIGHTS)
    for key, value in units.items():
        numerator = sum(
            weight * table.get(key, 0)
            for weight, table in zip(observation.MODE_WEIGHTS, tables, strict=True)
        )
        exact = Fraction(numerator, total_weight)
        # 偏差必须小于一个定点单位；总和已由上一行断言锁定。
        assert abs(Fraction(value) - exact) < 1


def test_marginalize_breaks_ties_in_canonical_order() -> None:
    per_mode = {
        "normal": _distribution(
            (ActionType.CALL, 0, 500_000), (ActionType.BET, 100, 500_000)
        ),
        "cautious": _distribution(
            (ActionType.CALL, 0, 300_000), (ActionType.BET, 100, 700_000)
        ),
        "pressed": _distribution(
            (ActionType.CALL, 0, 300_005), (ActionType.BET, 100, 699_995)
        ),
    }
    units = _units_map_from(observation.marginalize(per_mode))
    # 两个候选的大数余数相同，剩余的一个单位归规范次序在前的跟注候选。
    assert units == {(ActionType.CALL, 0): 460_001, (ActionType.BET, 100): 539_999}


def test_marginalize_unions_candidates_across_modes() -> None:
    per_mode = {
        "normal": _distribution(
            (ActionType.FOLD, 0, 400_000), (ActionType.BET, 100, 600_000)
        ),
        "cautious": _distribution((ActionType.FOLD, 0, 1_000_000)),
        "pressed": _distribution(
            (ActionType.CHECK, 0, 250_000), (ActionType.BET, 100, 750_000)
        ),
    }
    units = _units_map_from(observation.marginalize(per_mode))
    assert units == {
        (ActionType.FOLD, 0): 420_000,
        (ActionType.CHECK, 0): 25_000,
        (ActionType.BET, 100): 555_000,
    }


def test_marginalize_rejects_missing_or_uncovered_mode() -> None:
    partial = {
        "normal": _distribution((ActionType.FOLD, 0, 1_000_000)),
        "cautious": _distribution((ActionType.FOLD, 0, 1_000_000)),
    }
    with pytest.raises(observation.ObservationSemanticError):
        observation.marginalize(partial)
    uncovered = {
        mode: SimpleNamespace(candidates=()) for mode in observation.OBSERVATION_MODES
    }
    with pytest.raises(observation.ObservationSemanticError):
        observation.marginalize(uncovered)


def _units_map_from(candidates) -> dict[tuple[ActionType, int], int]:
    return {(candidate.action, candidate.amount): candidate.units for candidate in candidates}
