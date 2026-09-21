"""新 Bot 规则策略层的回归：阈值、候选生成、危险尺度保护、量化与抽样。

只做有界单元回归：不跑性能矩阵、不对抗对局、不访问真实库。
"""

import random

import pytest

from app.poker.actions import ActionType, LegalActions
from app.poker.state import Street
from app.strategy.mixed_features import MixedFeatures
from app.strategy.mixed_policy import (
    MIXED_DISTRIBUTION_UNITS,
    MIXED_STYLE_ORDER,
    STYLE_PARAMETERS,
    HandMode,
    MixedDistribution,
    MixedPolicyError,
    MixedStyle,
    build_distribution,
    hand_mode_for,
)


def _features(**overrides: object) -> MixedFeatures:
    payload: dict[str, object] = {
        "street": Street.FLOP,
        "base": 500,
        "draw": 0,
        "position": 0,
        "texture": 0,
        "contenders": 1,
        "live_opponents": 1,
        "recent_aggression": 0,
        "limpers": 0,
        "price": 0,
        "eligible_pot": 100,
        "actual_call": 0,
        "pot": 100,
        "effective_stack": 1000,
        "big_blind": 10,
        "stack": 1000,
        "street_bet": 0,
        "preflop_unraised": False,
        "hole_ranks": (14, 13),
    }
    payload.update(overrides)
    return MixedFeatures(**payload)  # type: ignore[arg-type]


def _legal(**overrides: object) -> LegalActions:
    payload: dict[str, object] = {
        "can_fold": False,
        "can_check": False,
        "can_call": False,
        "call_amount": 0,
        "actual_call_amount": 0,
        "is_short_all_in_call": False,
        "can_bet": False,
        "min_bet": 0,
        "max_bet": 0,
        "can_raise": False,
        "min_raise_to": 0,
        "max_raise_to": 0,
    }
    payload.update(overrides)
    return LegalActions(**payload)  # type: ignore[arg-type]


def _actions(distribution: MixedDistribution) -> list[tuple[ActionType, int]]:
    return [(item.action, item.amount) for item in distribution.candidates]


# ------------------------------------------------------------------ 参数与模式


def test_style_parameters_are_frozen() -> None:
    tight = STYLE_PARAMETERS[MixedStyle.TIGHT]
    aggressive = STYLE_PARAMETERS[MixedStyle.AGGRESSIVE]
    calling = STYLE_PARAMETERS[MixedStyle.CALLING]
    assert (tight.looseness, aggressive.looseness, calling.looseness) == (-35, 35, 10)
    assert (tight.fold_percent, aggressive.fold_percent, calling.fold_percent) == (130, 85, 70)
    assert (tight.call_percent, aggressive.call_percent, calling.call_percent) == (90, 110, 150)
    assert (
        tight.aggression_percent,
        aggressive.aggression_percent,
        calling.aggression_percent,
    ) == (90, 140, 60)
    assert tight.size_preferences == (5, 4, 1, 1)
    assert aggressive.size_preferences == (3, 5, 3, 2)
    assert calling.size_preferences == (6, 3, 1, 1)
    assert MIXED_STYLE_ORDER == (MixedStyle.TIGHT, MixedStyle.AGGRESSIVE, MixedStyle.CALLING)


@pytest.mark.parametrize(
    ("roll", "expected"),
    [
        (0, HandMode.NORMAL),
        (79, HandMode.NORMAL),
        (80, HandMode.CAUTIOUS),
        (89, HandMode.CAUTIOUS),
        (90, HandMode.PRESSED),
        (99, HandMode.PRESSED),
    ],
)
def test_hand_mode_partition(roll: int, expected: HandMode) -> None:
    assert hand_mode_for(roll) is expected


@pytest.mark.parametrize("roll", [-1, 100, 1000])
def test_hand_mode_rejects_out_of_partition(roll: int) -> None:
    with pytest.raises(MixedPolicyError):
        hand_mode_for(roll)


# ------------------------------------------------------------------ 候选生成


def test_free_check_node_keeps_only_check_and_bets() -> None:
    distribution = build_distribution(
        _features(),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )
    assert _actions(distribution) == [
        (ActionType.CHECK, 0),
        (ActionType.BET, 34),
        (ActionType.BET, 75),
        (ActionType.BET, 125),
    ]
    assert sum(item.units for item in distribution.candidates) == MIXED_DISTRIBUTION_UNITS
    assert distribution.candidates[0].units > sum(
        item.units for item in distribution.candidates[1:]
    )


def test_size_targets_follow_share_of_pot_plus_call() -> None:
    distribution = build_distribution(
        _features(street=Street.TURN, pot=200, actual_call=50, eligible_pot=250, price=200),
        _legal(
            can_fold=True,
            can_call=True,
            call_amount=50,
            actual_call_amount=50,
            can_raise=True,
            min_raise_to=100,
            max_raise_to=1000,
        ),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )
    # 目标 = 跟注点 + ceil(P/3)、ceil(3P/4)、ceil(5P/4)，P = max(BB, 底池 + 跟注额) = 250。
    assert _actions(distribution) == [
        (ActionType.FOLD, 0),
        (ActionType.CALL, 0),
        (ActionType.RAISE, 134),
        (ActionType.RAISE, 238),
        (ActionType.RAISE, 363),
    ]


def test_preflop_open_targets_use_limpers() -> None:
    distribution = build_distribution(
        _features(
            street=Street.PREFLOP,
            limpers=2,
            preflop_unraised=True,
            street_bet=10,
            stack=500,
        ),
        _legal(
            can_fold=True,
            can_call=True,
            call_amount=10,
            actual_call_amount=10,
            can_raise=True,
            min_raise_to=20,
            max_raise_to=1000,
        ),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )
    actions = _actions(distribution)
    assert (ActionType.RAISE, 45) in actions
    assert (ActionType.RAISE, 50) in actions
    assert (ActionType.RAISE, 60) in actions


def test_sizes_clamped_to_upper_and_merged_preferences() -> None:
    clamped = build_distribution(
        _features(),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=40),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )
    # 中/大两个目标被夹到同一上限，偏好相加；小注仍在区间内不被合并。
    assert _actions(clamped) == [
        (ActionType.CHECK, 0),
        (ActionType.BET, 34),
        (ActionType.BET, 40),
    ]


def test_active_mass_does_not_grow_with_candidate_count() -> None:
    wide = build_distribution(
        _features(),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )
    narrow = build_distribution(
        _features(),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=40),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )
    wide_active = sum(item.units for item in wide.candidates[1:])
    narrow_active = sum(item.units for item in narrow.candidates[1:])
    # 归一化按精确有理数计算，量化到整数单位时允许 1 个单位的取整差。
    assert abs(wide_active - narrow_active) <= 1


def test_all_in_only_generated_when_fully_matchable() -> None:
    capped = build_distribution(
        _features(base=1000, stack=200),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=200),
        MixedStyle.AGGRESSIVE,
        HandMode.PRESSED,
    )
    assert (ActionType.BET, 200) in _actions(capped)
    capped_by_effective = build_distribution(
        _features(base=1000, stack=200, effective_stack=100),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=200),
        MixedStyle.AGGRESSIVE,
        HandMode.PRESSED,
    )
    # 无法被完整匹配的多余筹码不算有效压迫，不生成该候选。
    assert (ActionType.BET, 200) not in _actions(capped_by_effective)


def test_no_active_candidates_without_live_opponents() -> None:
    distribution = build_distribution(
        _features(live_opponents=0),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )
    assert _actions(distribution) == [(ActionType.CHECK, 0)]


# ------------------------------------------------------------------ 危险尺度保护


def _capped_bet_case(stack: int, base: int) -> MixedDistribution:
    return build_distribution(
        _features(base=base, stack=stack, effective_stack=1000, pot=100),
        _legal(can_check=True, can_bet=True, min_bet=20, max_bet=40),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )


def test_overbet_scale_is_removed_without_value() -> None:
    distribution = build_distribution(
        _features(base=400),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
    )
    # 全下既超过可匹配上限的常规尺度、又无价值依据，必须被删除。
    assert all(amount < 1000 for _, amount in _actions(distribution))


def test_dangerous_scale_disables_non_value_quality() -> None:
    safe = _capped_bet_case(stack=1000, base=1000)
    dangerous = _capped_bet_case(stack=40, base=1000)
    assert (ActionType.BET, 40) in _actions(dangerous)
    # 危险候选禁用非价值质量 U，其主动概率必须低于同类非危险候选。
    assert sum(item.units for item in dangerous.candidates[1:]) < sum(
        item.units for item in safe.candidates[1:]
    )


def test_short_stack_jam_removed_when_score_too_low() -> None:
    distribution = _capped_bet_case(stack=40, base=400)
    assert (ActionType.BET, 40) not in _actions(distribution)
    assert (ActionType.BET, 34) in _actions(distribution)


# ------------------------------------------------------------------ 失败与抽样


def test_contradictory_legal_actions_fail() -> None:
    with pytest.raises(MixedPolicyError):
        build_distribution(
            _features(),
            _legal(can_check=True, can_call=True, call_amount=10),
            MixedStyle.TIGHT,
            HandMode.NORMAL,
        )
    with pytest.raises(MixedPolicyError):
        build_distribution(
            _features(),
            _legal(
                can_bet=True,
                min_bet=10,
                max_bet=100,
                can_raise=True,
                min_raise_to=20,
                max_raise_to=100,
            ),
            MixedStyle.TIGHT,
            HandMode.NORMAL,
        )


def test_degenerate_zero_mass_fails_explicitly() -> None:
    with pytest.raises(MixedPolicyError):
        build_distribution(
            _features(base=1000, price=1000, actual_call=1000, live_opponents=0),
            _legal(can_fold=True, call_amount=1000, actual_call_amount=1000),
            MixedStyle.AGGRESSIVE,
            HandMode.NORMAL,
        )


def test_sampling_is_seeded_and_never_picks_zero_units() -> None:
    distribution = build_distribution(
        _features(),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000),
        MixedStyle.AGGRESSIVE,
        HandMode.PRESSED,
    )
    first = [distribution.sample(random.Random(7)) for _ in range(20)]
    second = [distribution.sample(random.Random(7)) for _ in range(20)]
    assert first == second
    positive = {(item.action, item.amount) for item in distribution.candidates if item.units > 0}
    assert all((action.type, action.amount) in positive for action in first)


def test_distribution_is_reproducible_across_calls() -> None:
    features = _features()
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    first = build_distribution(features, legal, MixedStyle.CALLING, HandMode.CAUTIOUS)
    second = build_distribution(features, legal, MixedStyle.CALLING, HandMode.CAUTIOUS)
    assert first == second
    assert first.candidates[0].action is ActionType.CHECK


def test_styles_differ_on_the_same_node() -> None:
    features = _features(street=Street.PREFLOP, base=300, pot=45, price=222, actual_call=20)
    legal = _legal(can_fold=True, can_call=True, call_amount=20, actual_call_amount=20)
    tight = build_distribution(features, legal, MixedStyle.TIGHT, HandMode.NORMAL)
    calling = build_distribution(features, legal, MixedStyle.CALLING, HandMode.NORMAL)
    assert tight.candidates[0].units > calling.candidates[0].units
    assert tight.candidates[1].units < calling.candidates[1].units


def test_candidate_order_and_amounts_are_canonical() -> None:
    distribution = build_distribution(
        _features(),
        _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000),
        MixedStyle.AGGRESSIVE,
        HandMode.NORMAL,
    )
    amounts = [amount for action, amount in _actions(distribution) if action is ActionType.BET]
    assert amounts == sorted(amounts)
    assert all(amount >= 0 for _, amount in _actions(distribution))
    assert [item.schema_version for item in [distribution]] == ["mixed-distribution.v1"]
