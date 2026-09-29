"""分布观测契约的一致性核验：同源两级、取整唯一性、无副作用、边界与无关性。

核验对象是已实现的契约本身，不是质量验证：本文件不产生质量结论，不使用任何清单、
seed、节点冻结或运行读数，只执行确定性的逐项对照与独立复算。

节点集合取自仓库既有的确定性构造配方，仅覆盖实际执行的有限集合，不构成任何清单冻结。
"""

import hashlib
import hmac
import json
import random
from collections import Counter
from dataclasses import replace
from fractions import Fraction
from typing import Mapping, Sequence

import pytest

from app.poker.actions import ActionType
from app.poker.engine import PokerEngine
from app.strategy import distribution_observation as observation
from app.strategy import registry
from app.strategy.mixed_context import mixed_state, require_mixed_input
from app.strategy.mixed_features import features_for
from app.strategy.mixed_policy import (
    HAND_MODE_ROLL_BOUNDS,
    HandMode,
    MIXED_DISTRIBUTION_UNITS,
    MixedCandidate,
    MixedDistribution,
    build_distribution,
    hand_mode_for,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V8,
    MIXED_STRATEGY_RULES,
    MixedLocalStrategy,
    derive_bots_key,
    derive_root_key,
)

from .mixed_bot_states import (
    MIXED_CATEGORY_IDS,
    applicable_player_counts,
    apply_node,
    build_node,
)

CAPABILITY_IDENTIFIER = MIXED_STRATEGY_IDENTIFIER_V8
SEED = 3311
ROOT_KEY = derive_root_key(SEED)

# 核验覆盖的节点：每类配方的适用人数两端（同一人则只取一个），覆盖 2–9 人。
NODE_PARAMS: tuple[tuple[str, int], ...] = tuple(
    (category, count)
    for category in MIXED_CATEGORY_IDS
    for count in sorted(
        {min(applicable_player_counts(category)), max(applicable_player_counts(category))}
    )
)

_CANONICAL_ACTIONS = (
    ActionType.FOLD,
    ActionType.CHECK,
    ActionType.CALL,
    ActionType.BET,
    ActionType.RAISE,
)
_ACTION_INDEX = {action: index for index, action in enumerate(_CANONICAL_ACTIONS)}

# 独立复算用的固定权重，按契约冻结的整数比书写，不引用实现常量。
_REFERENCE_MODES = ("normal", "cautious", "pressed")
_REFERENCE_WEIGHTS = (8, 1, 1)

_CACHE: dict[tuple[str, int, int], tuple] = {}


def _order_key(key: tuple[ActionType, int]) -> tuple[int, int]:
    return (_ACTION_INDEX[key[0]], key[1])


def _node(category: str, player_count: int, hand_number: int = 1) -> tuple:
    cache_key = (category, player_count, hand_number)
    if cache_key not in _CACHE:
        applied = apply_node(build_node(category, player_count), hand_number=hand_number)
        _CACHE[cache_key] = (
            applied.actor_state(),
            applied.legal_actions(),
            applied.engine,
        )
    return _CACHE[cache_key]


def _runtime_strategy(state) -> MixedLocalStrategy:
    """按运行态口径构造同身份实例：座位集合与风格分派与观测入口完全一致。"""
    return MixedLocalStrategy(
        seed=SEED,
        bot_seats=state.context.bot_seats,
        identifier=CAPABILITY_IDENTIFIER,
    )


def _triples(distribution) -> list[tuple[ActionType, int, int]]:
    return [(c.action, c.amount, c.units) for c in distribution.candidates]


def _units_map(candidates) -> dict[tuple[ActionType, int], int]:
    return {(c.action, c.amount): c.units for c in candidates}


def _derive_key(parent: bytes, message: tuple) -> bytes:
    """独立复写派生的消息格式与摘要：只用于复算，不引用实现的私有函数。"""
    payload = json.dumps(list(message), separators=(",", ":"), ensure_ascii=True)
    return hmac.new(parent, payload.encode("utf-8"), hashlib.sha256).digest()


def _reference_roll(seat: int, hand_number: int) -> int:
    """独立复算手模式的随机源取值：输入只有座位键与手号。"""
    seat_key = _derive_key(derive_bots_key(ROOT_KEY, CAPABILITY_IDENTIFIER), ("seat", seat))
    digest = _derive_key(seat_key, ("hand", hand_number, "mode"))
    return random.Random(int.from_bytes(digest, "big")).randrange(100)


def _reference_marginal_units(per_mode_units: Sequence[Mapping[tuple[ActionType, int], int]]):
    """独立复算合并口径：精确有理值、向下取整、余数降序补一、规范次序破平。"""
    keys = sorted(set().union(*per_mode_units), key=_order_key)
    total_weight = sum(_REFERENCE_WEIGHTS)
    exact = {
        key: Fraction(
            sum(
                weight * table.get(key, 0)
                for weight, table in zip(_REFERENCE_WEIGHTS, per_mode_units, strict=True)
            ),
            total_weight,
        )
        for key in keys
    }
    units = {key: value.numerator // value.denominator for key, value in exact.items()}
    leftovers = {key: exact[key] - units[key] for key in keys}
    ranked = sorted(
        (key for key in keys if leftovers[key] > 0),
        key=lambda key: (-leftovers[key], _order_key(key)),
    )
    remaining = MIXED_DISTRIBUTION_UNITS - sum(units.values())
    for key in ranked[:remaining]:
        units[key] += 1
    assert sum(units.values()) == MIXED_DISTRIBUTION_UNITS
    for key, value in units.items():
        assert abs(Fraction(value) - exact[key]) < 1
    return units, exact


def _engine_signature(engine) -> tuple:
    return (
        engine.street,
        tuple(engine.board),
        engine.pot,
        engine.current_seat,
        engine.hand_over,
        len(engine.history),
        tuple(
            (p.seat, p.stack, p.street_bet, p.total_committed, p.folded, p.all_in)
            for p in engine.players
        ),
    )


# ------------------------------------------------------- 要求 A：条件分布逐模式同源


@pytest.mark.parametrize(("category", "player_count"), NODE_PARAMS)
@pytest.mark.parametrize("mode_name", _REFERENCE_MODES)
def test_requirement_a_conditional_distribution_matches_sampling_path(
    category: str, player_count: int, mode_name: str
) -> None:
    state, legal, _ = _node(category, player_count)
    strategy = _runtime_strategy(state)
    observed = registry.observation_entry(CAPABILITY_IDENTIFIER).observe(
        state, legal, mode_name
    )
    assert observed.aggregation == "mode_override"
    assert observed.overridden_mode == mode_name

    # 运行态侧的两种取法：既有的显式模式查询，以及采样前直接构造的条件分布。
    via_query = strategy.distribution_for(state, legal, HandMode(mode_name))
    via_builder = build_distribution(
        features_for(require_mixed_input(state), legal),
        legal,
        strategy.style_for(state.current_seat),
        HandMode(mode_name),
        MIXED_STRATEGY_RULES[CAPABILITY_IDENTIFIER],
    )
    assert _triples(observed) == _triples(via_query)
    assert _triples(observed) == _triples(via_builder)


# ------------------------------------------------------- 要求 B：边缘化唯一构造


@pytest.mark.parametrize(("category", "player_count"), NODE_PARAMS)
def test_requirement_b_marginalized_output_is_the_unique_construction(
    category: str, player_count: int
) -> None:
    state, legal, _ = _node(category, player_count)
    entry = registry.observation_entry(CAPABILITY_IDENTIFIER)
    marginalized = entry.observe(state, legal)
    per_mode_units = [
        _units_map(entry.observe(state, legal, mode_name).candidates)
        for mode_name in _REFERENCE_MODES
    ]
    expected, exact = _reference_marginal_units(per_mode_units)

    assert marginalized.aggregation == "marginalized"
    assert marginalized.overridden_mode is None
    assert _units_map(marginalized.candidates) == expected
    # 候选集合是三个模式候选集合的并集，且按规范次序排列。
    keys = [(c.action, c.amount) for c in marginalized.candidates]
    assert keys == sorted(set().union(*per_mode_units), key=_order_key)
    for key, value in _units_map(marginalized.candidates).items():
        assert abs(Fraction(value) - exact[key]) < 1


def test_marginalization_tie_break_matches_the_frozen_rule() -> None:
    """余数相同的候选，剩余单位归规范次序在前者：合成用例给出固定黄金值。"""

    def mode(units: tuple[tuple[ActionType, int, int], ...]) -> MixedDistribution:
        return MixedDistribution(
            candidates=tuple(
                MixedCandidate(action=action, amount=amount, units=value)
                for action, amount, value in units
            )
        )

    per_mode = {
        "normal": mode(((ActionType.CALL, 0, 500_000), (ActionType.BET, 100, 500_000))),
        "cautious": mode(((ActionType.CALL, 0, 300_000), (ActionType.BET, 100, 700_000))),
        "pressed": mode(((ActionType.CALL, 0, 300_005), (ActionType.BET, 100, 699_995))),
    }
    units = _units_map(observation.marginalize(per_mode))
    assert units == {(ActionType.CALL, 0): 460_001, (ActionType.BET, 100): 539_999}


# ------------------------------------------------------- 观测无副作用


@pytest.mark.parametrize(("category", "player_count"), NODE_PARAMS)
def test_observation_changes_neither_sampling_nor_game_state(
    category: str, player_count: int
) -> None:
    state, legal, engine = _node(category, player_count)
    strategy = _runtime_strategy(state)
    before_state = _engine_signature(engine)
    baseline = strategy.choose_action(state, legal)

    for _ in range(2):
        first = registry.observation_entry(CAPABILITY_IDENTIFIER).observe(state, legal)
        second = registry.observation_entry(CAPABILITY_IDENTIFIER).observe(state, legal, "normal")
        assert first == registry.observation_entry(CAPABILITY_IDENTIFIER).observe(state, legal)
        assert second == registry.observation_entry(CAPABILITY_IDENTIFIER).observe(
            state, legal, "normal"
        )

    assert strategy.choose_action(state, legal) == baseline
    assert _runtime_strategy(state).choose_action(state, legal) == baseline
    assert _engine_signature(engine) == before_state
    assert legal == engine.legal_actions()


# ------------------------------------------------------- 单位、金额与输出结构


@pytest.mark.parametrize(("category", "player_count"), NODE_PARAMS)
@pytest.mark.parametrize("mode_name", (None, *_REFERENCE_MODES))
def test_units_amounts_and_output_structure(
    category: str, player_count: int, mode_name
) -> None:
    state, legal, _ = _node(category, player_count)
    entry = registry.observation_entry(CAPABILITY_IDENTIFIER)
    declaration = registry.capability_declaration(CAPABILITY_IDENTIFIER)
    result = entry.observe(state, legal, mode_name)

    # 元数据与已通过的声明逐项一致。
    assert result.probability_units == declaration.probability_units
    assert result.mode_weights == declaration.mode_weights

    keys = [(c.action, c.amount) for c in result.candidates]
    assert len(set(keys)) == len(keys)
    assert keys == sorted(keys, key=_order_key)
    assert all(isinstance(c.units, int) and not isinstance(c.units, bool) for c in result.candidates)
    assert all(isinstance(c.amount, int) and not isinstance(c.amount, bool) for c in result.candidates)
    assert sum(c.units for c in result.candidates) == result.probability_units
    assert result.probability_units == MIXED_DISTRIBUTION_UNITS

    if mode_name is None:
        assert result.aggregation == "marginalized"
        assert result.overridden_mode is None
    else:
        assert result.aggregation == "mode_override"
        assert result.overridden_mode == mode_name
        assert result.overridden_mode in declaration.modes

    intervals = {
        ActionType.BET: (legal.min_bet, legal.max_bet),
        ActionType.RAISE: (legal.min_raise_to, legal.max_raise_to),
    }
    for candidate in result.candidates:
        if candidate.action in (ActionType.FOLD, ActionType.CHECK, ActionType.CALL):
            assert candidate.amount == 0
        else:
            low, high = intervals[candidate.action]
            # 闭区间：两端都必须允许。
            assert low <= candidate.amount <= high


# ------------------------------------------------------- 信息边界


@pytest.mark.parametrize(("category", "player_count"), NODE_PARAMS)
def test_leaked_private_information_is_refused(category: str, player_count: int) -> None:
    state, legal, engine = _node(category, player_count)
    leaked = mixed_state(engine.snapshot(), state.context)
    with pytest.raises(observation.IllegalObservationInputError):
        registry.observation_entry(CAPABILITY_IDENTIFIER).observe(leaked, legal)


def test_state_without_summary_is_refused() -> None:
    engine = PokerEngine(3, 5, 10, 1000, seed=5)
    engine.start_hand()
    with pytest.raises(observation.IllegalObservationInputError):
        registry.observation_entry(CAPABILITY_IDENTIFIER).observe(
            engine.snapshot(), engine.legal_actions()
        )


def test_incoherent_legal_actions_are_refused() -> None:
    state, legal, _ = _node(*NODE_PARAMS[0])
    contradictory = replace(legal, can_check=True, can_call=True)
    with pytest.raises(observation.IllegalObservationInputError):
        registry.observation_entry(CAPABILITY_IDENTIFIER).observe(state, contradictory)


def test_unsupported_mode_override_is_refused() -> None:
    state, legal, _ = _node(*NODE_PARAMS[0])
    for mode in ("careful", "Normal", ""):
        with pytest.raises(observation.IllegalObservationInputError):
            registry.observation_entry(CAPABILITY_IDENTIFIER).observe(state, legal, mode)


# ------------------------------------------------------- 声明、入口与探测


def test_declaration_is_bound_to_the_canonical_identifier() -> None:
    declaration = registry.capability_declaration(CAPABILITY_IDENTIFIER)
    assert declaration.capability_id == observation.CAPABILITY_ID
    assert declaration.supported is True
    assert declaration.probability_units == MIXED_DISTRIBUTION_UNITS
    assert declaration.modes == _REFERENCE_MODES
    assert declaration.mode_weights == _REFERENCE_WEIGHTS
    for value in ("mixed-local", "mixed-local@9", "heuristic@1", "random@1"):
        with pytest.raises(observation.DeclarationMissingError):
            registry.capability_declaration(value)


def test_failure_categories_are_distinct_types() -> None:
    categories = (
        observation.DeclarationMissingError,
        observation.DeclarationInvalidError,
        observation.CapabilityUnavailableError,
        observation.DeclarationBehaviourMismatchError,
        observation.IllegalObservationInputError,
        observation.ObservationTechnicalError,
        observation.ObservationSemanticError,
    )
    assert len(set(categories)) == len(categories)
    for kind in categories:
        assert issubclass(kind, observation.DistributionObservationError)
    for left in categories:
        for right in categories:
            if left is not right:
                assert not issubclass(left, right)


def test_static_entry_check_and_health_read() -> None:
    entries = registry.OBSERVATION_ENTRYPOINTS
    assert set(entries) == {"declaration", "health", "query"}
    assert all(callable(entry) for entry in entries.values())
    assert registry.capability_health() is observation.CapabilityHealth.AVAILABLE
    assert {member.value for member in observation.CapabilityHealth} == {
        "available",
        "unavailable",
    }


def test_weights_used_by_the_capability_equal_the_weights_it_declares() -> None:
    declaration = registry.capability_declaration(CAPABILITY_IDENTIFIER)
    assert observation.MODE_WEIGHTS == declaration.mode_weights == _REFERENCE_WEIGHTS
    assert observation.OBSERVATION_MODES == declaration.modes == _REFERENCE_MODES


# ------------------------------------------------------- 模式分布：P1 与 P2 的可复现判据


def test_mode_partition_maps_hundred_rolls_to_declared_weights() -> None:
    counts = Counter(hand_mode_for(roll) for roll in range(100))
    assert counts == {
        HandMode.NORMAL: 80,
        HandMode.CAUTIOUS: 10,
        HandMode.PRESSED: 10,
    }
    assert HAND_MODE_ROLL_BOUNDS == (80, 90, 100)


@pytest.mark.parametrize("hand_number", (1, 2, 3, 7, 23, 97, 1000))
def test_mode_derivation_reads_only_the_seat_key_and_the_hand_number(hand_number: int) -> None:
    state, legal, _ = _node("free-check", 2, hand_number)
    verified = require_mixed_input(state)
    strategy = _runtime_strategy(state)
    observed_modes = set()
    for seat in verified.context.bot_seats:
        expected = hand_mode_for(_reference_roll(seat, hand_number))
        actual = strategy._policies[seat].hand_mode(verified)  # 只读复算用的私有子策略
        assert actual is expected
        observed_modes.add(actual)
    # 单次取值可以随座位不同（这不违反边际分布无关性）。
    assert observed_modes
