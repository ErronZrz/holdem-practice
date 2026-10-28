"""第十四版身份的反例回归：强成牌设伏、空气续枪、听牌按覆盖率跟注。

旧身份的摘要与分布不得改变。这里只比较可复现局面上的动作单位，不把份额变化写成质量结论。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

import pytest

from app.api.schemas import CreateGameRequest
from app.poker.actions import LegalActions
from app.poker.state import Street
from app.strategy.distribution_observation import supported_declaration
from app.strategy.mixed_context import require_mixed_input
from app.strategy.mixed_features import MixedFeatures, extract_features, features_for
from app.strategy.mixed_policy import (
    MIXED_LOCAL_V1_RULES,
    MIXED_LOCAL_V13_RULES,
    MIXED_LOCAL_V14_RULES,
    HandMode,
    MixedPolicyError,
    MixedPolicyRules,
    MixedStyle,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V13,
    MIXED_STRATEGY_IDENTIFIER_V14,
    MIXED_STRATEGY_IDENTIFIERS,
    MIXED_STRATEGY_RULES,
    MixedSeatPolicy,
    rules_for_identifier,
    seat_style_map,
)
from app.strategy.registry import (
    capability_declaration,
    create_strategy,
    observation_entry,
    spec_for,
)
from app.verification.config import BASELINE_IDENTIFIER, UNDER_TEST_IDENTIFIERS
from tools.ninth_identity_calibration import _previous_identifier

from .mixed_bot_states import apply_node, build_frozen_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, config_digest

# 第十四版配置摘要。字段集合变了才会变；行为常量不在摘要里。
_FOURTEENTH_CONFIG_DIGEST = (
    "a5afd0c1835193ae466e7d84537b30c1b6f032eb4705cdf938ae9093166f10e6"
)
# 第一版到第十三版的摘要在本身份落地前已经钉死，这里再列一遍以免字段表被改写。
_EARLIER_CONFIG_DIGESTS = {
    "mixed-local@1": "bfe231419ecc31e54e9b73aaa16421026cc2392a21516ddb44e6a629936d1484",
    "mixed-local@2": "338a4863a68ca10eda44dcfdfdf26e510a4560cf8f7bbd1f97f048bc6ff6e794",
    "mixed-local@3": "5ed7992b36de67cc97b4035f075d2c563f989300b448c5878f31847eb001643f",
    "mixed-local@4": "52b03d5db65d92e3d0ee7a987a7f45169ff868e4273af4dd2ac8538772fb481d",
    "mixed-local@5": "8896013bbcd873cd493c6319756c353365b49cc7b4e846e927c4216d6d1f82f2",
    "mixed-local@6": "b6678f65069c19779f683bd6a8df31f7bc3567cf813654d2758278c13151b4a1",
    "mixed-local@7": "fd7433e35fc8260d03635774b34fbdc419ad5a04ba0448916b036e385a546665",
    "mixed-local@8": "393ca127fc16ef47d22cab29d287f43dde5aa94ee4a5cbb34ed15b4a12f627a2",
    "mixed-local@9": "2d3d750d1e3cdb5e9efcea89e44282013d491a1473f36f67731a615eaa862305",
    "mixed-local@10": "d54f1d467ff56cffeb818e66646c25f5279492cd27098307f5b02ed1a16d5632",
    "mixed-local@11": "86daf64b09b196d5619606180e246ccbf585d36bed231257667c538ab8c3ba69",
    "mixed-local@12": "ca5a4fe9d5ce5f8bcda98dac622fc80afa97ae9fde1fba2976cea16e94a58e24",
    "mixed-local@13": "83a94be9965925bbe4df8278bae21756a56d6559ea6d42539d1dba69b8b42279",
}
# 翻牌听牌节点按行动者风格边缘化后的弃牌、跟注、加注百分比。
_FLOP_DRAW_MARGINAL = {
    2: ((77.39, 0.0, 22.61), (10.73, 58.43, 30.84)),
    3: ((61.32, 4.76, 33.92), (0.0, 82.34, 17.66)),
    4: ((69.52, 0.09, 30.40), (5.63, 79.51, 14.86)),
    5: ((71.21, 0.0, 28.79), (15.07, 71.93, 13.01)),
    6: ((74.09, 0.0, 25.91), (27.07, 62.41, 10.52)),
    7: ((74.25, 0.0, 25.75), (42.73, 48.53, 8.74)),
    8: ((75.75, 0.0, 24.25), (44.11, 48.74, 7.15)),
    9: ((75.80, 0.0, 24.20), (44.43, 48.40, 7.17)),
}
_MODE_WEIGHT = {HandMode.NORMAL: 80, HandMode.CAUTIOUS: 10, HandMode.PRESSED: 10}


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


def _features(**overrides: object) -> MixedFeatures:
    payload: dict[str, object] = {
        "street": Street.TURN,
        "base": 60,
        "draw": 64,
        "position": -40,
        "texture": 0,
        "contenders": 2,
        "live_opponents": 2,
        "recent_aggression": 1,
        "limpers": 0,
        "price": 312,
        "eligible_pot": 110,
        "actual_call": 50,
        "pot": 160,
        "effective_stack": 2000,
        "big_blind": 20,
        "stack": 2000,
        "street_bet": 0,
        "preflop_unraised": False,
        "hole_ranks": (12, 2),
        "seat_count": 6,
        "actor_checks": 1,
    }
    payload.update(overrides)
    return MixedFeatures(**payload)  # type: ignore[arg-type]


def _facing_bet() -> LegalActions:
    return _legal(
        can_fold=True,
        can_call=True,
        call_amount=50,
        actual_call_amount=50,
        can_raise=True,
        min_raise_to=100,
        max_raise_to=2000,
    )


def _free_check() -> LegalActions:
    return _legal(can_check=True, can_bet=True, min_bet=20, max_bet=2000)


def _rows(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    style: MixedStyle = MixedStyle.CALLING,
    mode: HandMode = HandMode.NORMAL,
    trap_roll: int | None = None,
) -> tuple[tuple[str, int, int], ...]:
    distribution = build_distribution(
        features, legal, style, mode, rules, trap_roll=trap_roll
    )
    return tuple((item.action.value, item.amount, item.units) for item in distribution.candidates)


def _marginal(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    style: MixedStyle = MixedStyle.CALLING,
    trap_roll: int | None = None,
) -> dict[str, float]:
    """按 80/10/10 把三种手模式合成动作类型百分比。"""
    totals: dict[str, int] = defaultdict(int)
    for mode, weight in _MODE_WEIGHT.items():
        for action, _amount, units in _rows(rules, features, legal, style, mode, trap_roll):
            totals[action] += units * weight
    return {action: round(units / 1_000_000, 2) for action, units in totals.items()}


def _grouped(percent: dict[str, float]) -> tuple[float, float, float]:
    fold = percent.get("fold", 0.0)
    call = percent.get("call", 0.0)
    active = round(percent.get("bet", 0.0) + percent.get("raise", 0.0), 2)
    return fold, call, active


def test_fourteenth_version_only_turns_on_three_switches() -> None:
    """第十四版只打开三个开关，关掉后必须与第十三版逐字段相同。"""
    assert MIXED_LOCAL_V14_RULES.trap_allocation is True
    assert MIXED_LOCAL_V14_RULES.story_momentum is True
    assert MIXED_LOCAL_V14_RULES.effective_draw_support is True
    assert MIXED_LOCAL_V14_RULES.trap_base_percent == 24
    assert MIXED_LOCAL_V14_RULES.trap_crowd_percent == 8
    assert MIXED_LOCAL_V14_RULES.story_quality_base == 10
    assert MIXED_LOCAL_V14_RULES.draw_support_span == 360
    assert MIXED_LOCAL_V13_RULES.trap_allocation is False
    assert MIXED_LOCAL_V13_RULES.story_momentum is False
    assert MIXED_LOCAL_V13_RULES.effective_draw_support is False
    assert (
        replace(
            MIXED_LOCAL_V14_RULES,
            trap_allocation=False,
            story_momentum=False,
            effective_draw_support=False,
        )
        == MIXED_LOCAL_V13_RULES
    )


def test_fourteenth_identity_stays_registered_when_default_moves_on() -> None:
    """第十四版仍可构造；未指定策略时创建对局改用当前默认版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    assert ordered[-6] == MIXED_STRATEGY_IDENTIFIER_V14
    assert ordered[-7] == MIXED_STRATEGY_IDENTIFIER_V13
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V14).version == 14
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V14, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V14
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V14) is MIXED_LOCAL_V14_RULES
    assert CreateGameRequest().bot_strategy == "mixed-local@19"
    assert BASELINE_IDENTIFIER == "heuristic@1"
    assert "mixed-local@14" in UNDER_TEST_IDENTIFIERS
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V14) == supported_declaration()
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V14).rules is MIXED_LOCAL_V14_RULES
    assert _previous_identifier(MIXED_STRATEGY_IDENTIFIER_V14) == MIXED_STRATEGY_IDENTIFIER_V13


def test_earlier_digests_and_field_lists_stay_put() -> None:
    """摘要只追加第十四版自己的字段，第一版到第十三版的摘要逐字不变。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V13][-1] == "align_bet_to_small_blind"
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V14][-7:] == (
        "trap_allocation",
        "trap_base_percent",
        "trap_crowd_percent",
        "story_momentum",
        "story_quality_base",
        "effective_draw_support",
        "draw_support_span",
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V14) == _FOURTEENTH_CONFIG_DIGEST
    for identifier, digest in _EARLIER_CONFIG_DIGESTS.items():
        assert config_digest(identifier) == digest


def test_new_feature_fields_do_not_move_older_rules() -> None:
    """旧口径不读取新派生字段：填上之后分布仍与缺省构造逐位相同。"""
    legal = _facing_bet()
    plain = _features()
    touched = replace(
        plain,
        actor_checks=3,
        prior_street_aggressor=True,
        prior_street_aggression=3,
    )
    for rules in MIXED_STRATEGY_RULES.values():
        if rules.trap_allocation:
            continue
        assert _rows(rules, plain, legal) == _rows(rules, touched, legal)
    assert _rows(MIXED_LOCAL_V1_RULES, plain, legal) == _rows(
        MIXED_LOCAL_V1_RULES, touched, legal
    )


def test_frozen_nodes_only_move_flop_draws() -> None:
    """125 个冻结节点里，只有翻牌听牌面对下注相对第十三版移动。"""
    nodes = build_frozen_nodes()
    assert len(nodes) == 125
    draw_nodes = 0
    for node in nodes:
        applied = apply_node(node)
        legal = applied.legal_actions()
        state = applied.actor_state()
        features = extract_features(state, legal)
        verified = require_mixed_input(state)
        actor_style = seat_style_map(verified.context.bot_seats)[verified.actor_seat]
        for style in MixedStyle:
            for mode in HandMode:
                current = _rows(MIXED_LOCAL_V14_RULES, features, legal, style, mode)
                previous = _rows(MIXED_LOCAL_V13_RULES, features, legal, style, mode)
                if node.category == "flop-draw":
                    draw_nodes += 1
                else:
                    assert current == previous
        if node.category != "flop-draw":
            assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V14).observe(
                state, legal
            ).candidates == observation_entry(MIXED_STRATEGY_IDENTIFIER_V13).observe(
                state, legal
            ).candidates
            continue
        expected_previous, expected_current = _FLOP_DRAW_MARGINAL[node.player_count]
        assert _grouped(
            _marginal(MIXED_LOCAL_V13_RULES, features, legal, actor_style)
        ) == expected_previous
        assert _grouped(
            _marginal(MIXED_LOCAL_V14_RULES, features, legal, actor_style)
        ) == expected_current
    assert draw_nodes == 8 * len(MixedStyle) * len(HandMode)


def test_draw_support_raises_calls_and_closes_raises() -> None:
    """听牌面对下注时跟注升高、加注下降；无人下注、成牌和已清零的节点不动。"""
    facing = _features()
    legal = _facing_bet()
    assert _grouped(_marginal(MIXED_LOCAL_V13_RULES, facing, legal)) == (82.92, 0.0, 17.08)
    assert _grouped(_marginal(MIXED_LOCAL_V14_RULES, facing, legal)) == (71.16, 22.27, 6.57)
    quiet = _features(
        price=0,
        actual_call=0,
        recent_aggression=0,
        actor_checks=0,
        pot=100,
        eligible_pot=0,
    )
    assert _marginal(MIXED_LOCAL_V14_RULES, quiet, _free_check()) == _marginal(
        MIXED_LOCAL_V13_RULES, quiet, _free_check()
    )
    assert _grouped(_marginal(MIXED_LOCAL_V13_RULES, quiet, _free_check())) == (
        0.0,
        0.0,
        17.34,
    )
    made = replace(facing, base=400)
    assert _rows(MIXED_LOCAL_V14_RULES, made, legal) == _rows(
        MIXED_LOCAL_V13_RULES, made, legal
    )
    river = replace(facing, street=Street.RIVER, draw=0)
    assert _rows(MIXED_LOCAL_V14_RULES, river, legal) == _rows(
        MIXED_LOCAL_V13_RULES, river, legal
    )
    valued = _features(
        street=Street.FLOP,
        base=399,
        draw=180,
        position=40,
        contenders=1,
        live_opponents=1,
        price=200,
        actual_call=40,
        pot=200,
        hole_ranks=(14, 13),
        seat_count=2,
        actor_checks=0,
    )
    assert _rows(
        MIXED_LOCAL_V14_RULES, valued, legal, MixedStyle.AGGRESSIVE, HandMode.PRESSED
    ) == _rows(
        replace(MIXED_LOCAL_V14_RULES, effective_draw_support=False),
        valued,
        legal,
        MixedStyle.AGGRESSIVE,
        HandMode.PRESSED,
    )
    committed = _features(
        base=60,
        draw=96,
        contenders=4,
        live_opponents=4,
        price=600,
        actual_call=400,
        pot=400,
        stack=500,
        effective_stack=500,
        position=-40,
        hole_ranks=(12, 11),
    )
    assert _rows(MIXED_LOCAL_V14_RULES, committed, legal) == _rows(
        MIXED_LOCAL_V13_RULES, committed, legal
    )


def test_story_adds_a_small_bet_only_for_heads_up_air() -> None:
    """单挑、上一街自己收尾的空气可以小额续枪；面对下注时与第十三版逐位相同。"""
    air = _features(
        street=Street.RIVER,
        base=180,
        draw=0,
        texture=40,
        position=0,
        contenders=1,
        live_opponents=1,
        recent_aggression=0,
        price=0,
        actual_call=0,
        pot=200,
        eligible_pot=0,
        effective_stack=1800,
        stack=1800,
        actor_checks=0,
        prior_street_aggressor=True,
        prior_street_aggression=1,
    )
    legal = _free_check()
    assert _grouped(_marginal(MIXED_LOCAL_V13_RULES, air, legal)) == (0.0, 0.0, 0.0)
    assert _grouped(_marginal(MIXED_LOCAL_V14_RULES, air, legal)) == (0.0, 0.0, 17.34)
    assert _grouped(
        _marginal(MIXED_LOCAL_V14_RULES, air, legal, MixedStyle.AGGRESSIVE)
    ) == (0.0, 0.0, 32.85)
    blocked = (
        replace(air, street=Street.FLOP),
        replace(air, hole_ranks=(14, 2)),
        replace(air, draw=8),
        replace(air, base=600),
        replace(air, contenders=2, live_opponents=2),
        replace(air, recent_aggression=2),
        replace(air, effective_stack=400),
        replace(air, prior_street_aggressor=False),
        replace(air, actual_call=40, price=250, recent_aggression=1),
    )
    facing = _facing_bet()
    for features in blocked:
        chosen = facing if features.actual_call > 0 else legal
        assert _rows(MIXED_LOCAL_V14_RULES, features, chosen) == _rows(
            MIXED_LOCAL_V13_RULES, features, chosen
        )


def test_trap_checks_strong_hands_and_releases_a_call_after_checking() -> None:
    """设伏命中时强成牌整段过牌；本街已过牌再面对下注时跟注略增，价值加注仍在。"""
    trips = _features(
        street=Street.FLOP,
        base=840,
        draw=0,
        contenders=2,
        live_opponents=2,
        recent_aggression=0,
        price=0,
        actual_call=0,
        pot=150,
        eligible_pot=0,
        effective_stack=1900,
        actor_checks=0,
        hole_ranks=(12, 12),
    )
    legal = _free_check()
    assert _grouped(_marginal(MIXED_LOCAL_V13_RULES, trips, legal)) == (0.0, 0.0, 91.89)
    assert _grouped(_marginal(MIXED_LOCAL_V14_RULES, trips, legal)) == (0.0, 0.0, 91.89)
    assert _grouped(_marginal(MIXED_LOCAL_V14_RULES, trips, legal, trap_roll=0)) == (
        0.0,
        0.0,
        0.0,
    )
    assert _rows(MIXED_LOCAL_V14_RULES, trips, legal, trap_roll=99) == _rows(
        MIXED_LOCAL_V13_RULES, trips, legal
    )
    release = replace(
        trips,
        street=Street.TURN,
        price=312,
        actual_call=50,
        recent_aggression=1,
        actor_checks=1,
        pot=250,
    )
    facing = _facing_bet()
    assert _grouped(_marginal(MIXED_LOCAL_V13_RULES, release, facing)) == (0.0, 28.94, 71.06)
    assert _grouped(_marginal(MIXED_LOCAL_V14_RULES, release, facing, trap_roll=0)) == (
        0.0,
        32.11,
        67.89,
    )
    assert _rows(MIXED_LOCAL_V14_RULES, release, facing, trap_roll=99) == _rows(
        MIXED_LOCAL_V13_RULES, release, facing
    )
    untouched = (
        replace(trips, base=759),
        replace(trips, street=Street.RIVER, base=900),
        replace(trips, effective_stack=100, stack=100, pot=150),
        replace(trips, contenders=4, live_opponents=4),
    )
    for features in untouched:
        assert _rows(MIXED_LOCAL_V14_RULES, features, legal, trap_roll=0) == _rows(
            MIXED_LOCAL_V13_RULES, features, legal
        )
    with pytest.raises(MixedPolicyError):
        build_distribution(
            trips, legal, MixedStyle.CALLING, HandMode.NORMAL, MIXED_LOCAL_V14_RULES, 100
        )


def test_seat_policy_shares_one_trap_roll_and_observation_omits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """持有座位键的两条路径传入同一个设伏数；分布观测不传，设伏保持关闭。"""
    node = next(item for item in build_frozen_nodes() if item.category == "free-check")
    applied = apply_node(node)
    legal = applied.legal_actions()
    state = applied.actor_state()
    verified = require_mixed_input(state)
    policy = MixedSeatPolicy(
        seat=verified.actor_seat,
        style=MixedStyle.CALLING,
        seat_key=b"seat-key",
        rules=MIXED_LOCAL_V14_RULES,
    )
    roll = policy.trap_roll(verified)
    assert 0 <= roll < 100
    assert policy.trap_roll(verified) == roll
    assert policy.hand_mode(verified) == policy.hand_mode(verified)
    seen: list[int | None] = []
    real = build_distribution

    def spy(*args: object, **kwargs: object):
        seen.append(kwargs.get("trap_roll"))  # type: ignore[arg-type]
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("app.strategy.mixed_strategy.build_distribution", spy)
    first = policy.distribution_for(verified, legal)
    policy.choose_action(verified, legal)
    assert seen == [roll, roll]
    assert first == build_distribution(
        features_for(verified, legal),
        legal,
        policy.style,
        policy.hand_mode(verified),
        MIXED_LOCAL_V14_RULES,
        trap_roll=roll,
    )
    observed: list[object] = []

    def observe_spy(*args: object, **kwargs: object):
        observed.append(kwargs.get("trap_roll"))
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "app.strategy.distribution_observation.build_distribution", observe_spy
    )
    observation_entry(MIXED_STRATEGY_IDENTIFIER_V14).observe(state, legal)
    assert observed
    assert all(item is None for item in observed)
