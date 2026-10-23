"""第九版身份的反例回归：面对下注的听牌延续，以及无人下注时的成牌兑现。

旧身份的分布不得改变。这里只比较可复现局面上的动作单位，不把份额变化写成质量结论。
"""

from __future__ import annotations

from dataclasses import replace

from app.api.schemas import CreateGameRequest
from app.poker.actions import LegalActions
from app.poker.state import Street
from app.strategy.distribution_observation import supported_declaration
from app.strategy.mixed_features import MixedFeatures, extract_features
from app.strategy.mixed_policy import (
    _CHECKED_VALUE_FLOOR,
    _CHECKED_VALUE_SPAN,
    MIXED_LOCAL_V8_RULES,
    MIXED_LOCAL_V9_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    _checked_value_floor,
    _facing_draw_extra,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V8,
    MIXED_STRATEGY_IDENTIFIER_V9,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.registry import capability_declaration, create_strategy, spec_for

from .mixed_bot_states import applicable_player_counts, apply_node, build_node
from .mixed_bot_validation import DIGEST_RULE_FIELDS, config_digest

# 第九版配置摘要。字段集合变了才会变；行为常量不在摘要里，另由直接断言钉住。
_NINTH_CONFIG_DIGEST = (
    "2d3d750d1e3cdb5e9efcea89e44282013d491a1473f36f67731a615eaa862305"
)


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
        "street": Street.FLOP,
        "base": 180,
        "draw": 0,
        "position": 0,
        "texture": 0,
        "contenders": 2,
        "live_opponents": 2,
        "recent_aggression": 0,
        "limpers": 0,
        "price": 0,
        "eligible_pot": 0,
        "actual_call": 0,
        "pot": 40,
        "effective_stack": 400,
        "big_blind": 2,
        "stack": 400,
        "street_bet": 0,
        "preflop_unraised": False,
        "hole_ranks": (10, 8),
    }
    payload.update(overrides)
    return MixedFeatures(**payload)  # type: ignore[arg-type]


def _rows(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    style: MixedStyle = MixedStyle.TIGHT,
    mode: HandMode = HandMode.NORMAL,
) -> tuple[tuple[str, int, int], ...]:
    distribution = build_distribution(features, legal, style, mode, rules)
    return tuple(
        (item.action.value, item.amount, item.units) for item in distribution.candidates
    )


def _active(rows: tuple[tuple[str, int, int], ...]) -> int:
    return sum(units for action, _, units in rows if action in ("bet", "raise"))


def _same(
    left: MixedPolicyRules,
    right: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
) -> bool:
    return all(
        _rows(left, features, legal, style, mode) == _rows(right, features, legal, style, mode)
        for style in MixedStyle
        for mode in HandMode
    )


def _open_bet() -> LegalActions:
    """无人下注：可以过牌，也可以在合法区间内主动下注。"""
    return _legal(can_check=True, can_bet=True, min_bet=2, max_bet=400)


def _facing_raise() -> LegalActions:
    """面对下注：可以弃牌、跟注或加注，不能过牌。"""
    return _legal(
        can_fold=True,
        can_call=True,
        call_amount=20,
        actual_call_amount=20,
        can_raise=True,
        min_raise_to=40,
        max_raise_to=400,
    )


def test_ninth_version_values_are_recorded() -> None:
    """两个开关与两条成牌边界被钉住，关掉开关后必须回到第八版。"""
    assert _CHECKED_VALUE_FLOOR == 600
    assert _CHECKED_VALUE_SPAN == 160
    assert MIXED_LOCAL_V9_RULES.facing_draw_continuation is True
    assert MIXED_LOCAL_V9_RULES.checked_value_realization is True
    assert (
        replace(
            MIXED_LOCAL_V9_RULES,
            facing_draw_continuation=False,
            checked_value_realization=False,
        )
        == MIXED_LOCAL_V8_RULES
    )


def test_ninth_identity_stays_selectable_when_default_is_fourteenth() -> None:
    """第九版可构造；未指定策略时创建对局使用第十六版。"""
    ninth_at = MIXED_STRATEGY_IDENTIFIERS.index(MIXED_STRATEGY_IDENTIFIER_V9)
    assert MIXED_STRATEGY_IDENTIFIERS[ninth_at - 1] == MIXED_STRATEGY_IDENTIFIER_V8
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V9).version == 9
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V9, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V9
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V9) is MIXED_LOCAL_V9_RULES
    assert CreateGameRequest().bot_strategy == "mixed-local@17"
    selected = CreateGameRequest(bot_strategy=MIXED_STRATEGY_IDENTIFIER_V9)
    assert selected.bot_strategy == MIXED_STRATEGY_IDENTIFIER_V9


def test_ninth_identity_declares_distribution_observation() -> None:
    """第九版显式登记与第八版相同的能力声明，规则对象仍是第九版自己的。"""
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V9) == supported_declaration()
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V9) == capability_declaration(
        MIXED_STRATEGY_IDENTIFIER_V8
    )


def test_ninth_digest_lists_both_new_switches() -> None:
    """摘要只追加第九版自己的两个开关，不改写第八版摘要。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V9][-2:] == (
        "facing_draw_continuation",
        "checked_value_realization",
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V9) == _NINTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V9) != config_digest(
        MIXED_STRATEGY_IDENTIFIER_V8
    )
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V8)
        == "393ca127fc16ef47d22cab29d287f43dde5aa94ee4a5cbb34ed15b4a12f627a2"
    )


def test_switches_off_match_the_eighth_version() -> None:
    """两个开关单独关掉时，各自不该碰的局面与第八版逐位相同。"""
    count = applicable_player_counts("flop-draw")[0]
    faced = apply_node(build_node("flop-draw", count))
    faced_legal = faced.legal_actions()
    faced_features = extract_features(faced.actor_state(), faced_legal)
    checked = _features(base=650, position=-40, texture=40, contenders=4, live_opponents=4)
    checked_legal = _open_bet()
    continuation_only = replace(MIXED_LOCAL_V9_RULES, checked_value_realization=False)
    realization_only = replace(MIXED_LOCAL_V9_RULES, facing_draw_continuation=False)
    assert _same(continuation_only, MIXED_LOCAL_V8_RULES, checked, checked_legal)
    assert _same(realization_only, MIXED_LOCAL_V8_RULES, faced_features, faced_legal)


def test_draw_facing_a_bet_raises_more_without_collapsing_styles() -> None:
    """听牌面对下注时三档主动单位都上升，且彼此仍然可区分。"""
    count = applicable_player_counts("flop-draw")[0]
    applied = apply_node(build_node("flop-draw", count))
    legal = applied.legal_actions()
    features = extract_features(applied.actor_state(), legal)
    assert features.street is Street.FLOP
    assert features.draw > 0
    assert features.actual_call > 0
    assert _facing_draw_extra(features, MIXED_LOCAL_V9_RULES) == (
        features.draw // MIXED_LOCAL_V9_RULES.active_scale_percent
    )
    shares = {}
    for style in MixedStyle:
        before = _active(_rows(MIXED_LOCAL_V8_RULES, features, legal, style))
        after = _active(_rows(MIXED_LOCAL_V9_RULES, features, legal, style))
        assert after > before
        shares[style] = after
    assert len(set(shares.values())) == 3
    assert shares[MixedStyle.AGGRESSIVE] > shares[MixedStyle.CALLING]
    assert shares[MixedStyle.CALLING] > shares[MixedStyle.TIGHT]


def test_continuation_stays_off_without_a_live_draw_or_under_heavy_action() -> None:
    """没有听牌，或本街已经连续进攻时，面对下注的分布与第八版相同。"""
    legal = _facing_raise()
    no_draw = _features(
        draw=0,
        actual_call=20,
        price=250,
        recent_aggression=1,
        hole_ranks=(14, 10),
    )
    heavy = _features(draw=108, actual_call=20, price=250, recent_aggression=2)
    assert _facing_draw_extra(no_draw, MIXED_LOCAL_V9_RULES) == 0
    assert _same(MIXED_LOCAL_V9_RULES, MIXED_LOCAL_V8_RULES, no_draw, legal)
    assert _same(MIXED_LOCAL_V9_RULES, MIXED_LOCAL_V8_RULES, heavy, legal)


def test_checked_made_hand_bets_more_and_weaker_hands_do_not() -> None:
    """无人下注时，顶对从完全不过牌变成会下注；低于下沿的牌力保持原分布。"""
    legal = _open_bet()
    made = _features(base=610, position=-40, texture=40, contenders=4, live_opponents=4)
    weak = _features(base=520, position=-40, texture=40, contenders=4, live_opponents=4)
    assert made.actual_call == 0
    assert _checked_value_floor(made, MIXED_LOCAL_V9_RULES) == 10
    assert _checked_value_floor(weak, MIXED_LOCAL_V9_RULES) == 0
    assert _same(MIXED_LOCAL_V9_RULES, MIXED_LOCAL_V8_RULES, weak, legal)
    before = {
        style: _active(_rows(MIXED_LOCAL_V8_RULES, made, legal, style)) for style in MixedStyle
    }
    after = {
        style: _active(_rows(MIXED_LOCAL_V9_RULES, made, legal, style)) for style in MixedStyle
    }
    assert before == {style: 0 for style in MixedStyle}
    assert after[MixedStyle.AGGRESSIVE] > after[MixedStyle.TIGHT] > after[MixedStyle.CALLING]
    assert all(after[style] > before[style] for style in MixedStyle)


def test_checked_air_on_a_real_node_is_unchanged() -> None:
    """没有成牌、也没有待跟注的冻结节点，第九版与第八版逐位相同。"""
    count = applicable_player_counts("free-check")[0]
    applied = apply_node(build_node("free-check", count))
    legal = applied.legal_actions()
    features = extract_features(applied.actor_state(), legal)
    assert features.base < _CHECKED_VALUE_FLOOR
    assert features.actual_call == 0
    assert _same(MIXED_LOCAL_V9_RULES, MIXED_LOCAL_V8_RULES, features, legal)


def test_realization_does_not_apply_when_facing_a_bet() -> None:
    """面对下注时，成牌基础分不得另开一条加注下限。"""
    legal = _facing_raise()
    made = _features(base=760, draw=0, actual_call=20, price=250, recent_aggression=1)
    assert _checked_value_floor(made, MIXED_LOCAL_V9_RULES) == 0
    assert _same(MIXED_LOCAL_V9_RULES, MIXED_LOCAL_V8_RULES, made, legal)


def test_preflop_matches_the_eighth_version() -> None:
    """两条翻后路径都不作用于翻前。"""
    features = _features(street=Street.PREFLOP, base=700, draw=0, preflop_unraised=True)
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=2,
        actual_call_amount=2,
        can_raise=True,
        min_raise_to=6,
        max_raise_to=400,
    )
    assert _facing_draw_extra(features, MIXED_LOCAL_V9_RULES) == 0
    assert _checked_value_floor(features, MIXED_LOCAL_V9_RULES) == 0
    assert _same(MIXED_LOCAL_V9_RULES, MIXED_LOCAL_V8_RULES, features, legal)


def test_draw_continuation_does_not_fund_an_all_in() -> None:
    """听牌延续只进入未达危险尺度的加注，全下仍被原有保护挡下。"""
    features = _features(
        draw=108,
        position=40,
        actual_call=20,
        price=250,
        pot=60,
        recent_aggression=1,
        contenders=1,
        live_opponents=1,
        effective_stack=80,
        stack=80,
        hole_ranks=(14, 13),
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=20,
        actual_call_amount=20,
        can_raise=True,
        min_raise_to=40,
        max_raise_to=80,
    )
    rows = _rows(MIXED_LOCAL_V9_RULES, features, legal, MixedStyle.AGGRESSIVE)
    raised = [amount for action, amount, units in rows if action == "raise" and units]
    assert raised
    assert features.street_bet + features.stack not in raised
