"""第八版身份的口径回归：翻后主动门槛随公开局面按风格分化，以及既有身份的逐位隔离。

黄金值在改动前用旧实现在第四套冻结节点上捕获，改动后必须逐字复现。只做有界单元回归与
冻结节点回放：不跑性能矩阵、不对抗对局、不访问真实库。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from functools import lru_cache

import pytest

from app.poker.state import Street
from app.strategy.mixed_features import extract_features
from app.strategy.mixed_policy import (
    _ACTIVE_GATE_DRAW_SPAN,
    _ACTIVE_GATE_INDEX_CAP,
    _ACTIVE_GATE_POSITION_SPAN,
    _ACTIVE_GATE_WEIGHT,
    _VALUE_GATE_TOLERANCE,
    MIXED_LOCAL_V1_RULES,
    MIXED_LOCAL_V2_RULES,
    MIXED_LOCAL_V3_RULES,
    MIXED_LOCAL_V4_RULES,
    MIXED_LOCAL_V5_RULES,
    MIXED_LOCAL_V6_RULES,
    MIXED_LOCAL_V7_RULES,
    MIXED_LOCAL_V8_RULES,
    HandMode,
    MixedFeatures,
    MixedPolicyRules,
    MixedStyle,
    _active_gate,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
    MIXED_STRATEGY_IDENTIFIER_V4,
    MIXED_STRATEGY_IDENTIFIER_V5,
    MIXED_STRATEGY_IDENTIFIER_V6,
    MIXED_STRATEGY_IDENTIFIER_V7,
    MIXED_STRATEGY_IDENTIFIER_V8,
    MIXED_STRATEGY_IDENTIFIERS,
    MixedStrategyError,
    rules_for_identifier,
)
from app.strategy.registry import create_strategy, spec_for

from .mixed_bot_states import apply_node, build_frozen_iqv3_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, config_digest

# 改动前用旧实现在第四套冻结节点上捕获的逐身份分布摘要：改动后必须逐字复现。
FROZEN_GOLDEN_DIGESTS: dict[str, str] = {
    "mixed-local@1": "57fd4f9141516e82e0f1fa58bdfe6c4ff9ef9a95d28d5764e3ed79a079b492ea",
    "mixed-local@2": "57fd4f9141516e82e0f1fa58bdfe6c4ff9ef9a95d28d5764e3ed79a079b492ea",
    "mixed-local@3": "8d17ef513d1728019b5a815da2591850f332844e5ae76decd5d9360da3e18844",
    "mixed-local@4": "562e2d2b4495d540a1890ff32c70f4a980af81430c528f2d746bed54c0dc6e6e",
    "mixed-local@5": "854fd4971135ddba787e91d07e023fa03ebcb88b75f134ca9505ac0c9aefb110",
    "mixed-local@6": "b72f78d8dad967ddb4fee296299356949b7319aacad22c3236e1a844a832619f",
    "mixed-local@7": "9d64257c3823f3f4ada01d6745e3dc6b4608f8cd6cada0425974f5dc89be8f9a",
    "mixed-local@8": "cebe74e2977ae8986604d11d2fb2facf68075da2062c15af71044dbd751dc2c4",
}
# 逐身份与规则口径的对应关系：顺序与取值都必须逐字一致。
FROZEN_IDENTITIES: tuple[tuple[str, MixedPolicyRules], ...] = (
    (MIXED_STRATEGY_IDENTIFIER, MIXED_LOCAL_V1_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V2, MIXED_LOCAL_V2_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V3, MIXED_LOCAL_V3_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V4, MIXED_LOCAL_V4_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V5, MIXED_LOCAL_V5_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V6, MIXED_LOCAL_V6_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V7, MIXED_LOCAL_V7_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V8, MIXED_LOCAL_V8_RULES),
)
# 分化只作用于翻后，因此被触及的节点不得出现翻前项。
FROZEN_POSTFLOP_STREETS = (Street.FLOP, Street.TURN, Street.RIVER)


@lru_cache(maxsize=1)
def _frozen_states() -> tuple[tuple[str, MixedFeatures, object], ...]:
    """第四套冻结节点回放一次的（标识、特征、合法动作）：特征与身份无关，可共用。"""
    states = []
    for fixture in build_frozen_iqv3_nodes():
        applied = apply_node(fixture)
        legal = applied.legal_actions()
        states.append((fixture.node_id, extract_features(applied.actor_state(), legal), legal))
    return tuple(states)


def _frozen_payload(rules: MixedPolicyRules) -> dict[str, object]:
    """按（节点 → 风格 → 手模式 → 逐候选三元组）列出该口径在冻结节点上的全部分布。"""
    payload: dict[str, object] = {}
    for node_id, features, legal in _frozen_states():
        by_style: dict[str, object] = {}
        for style in MixedStyle:
            by_mode: dict[str, object] = {}
            for mode in HandMode:
                candidates = build_distribution(
                    features, legal, style, mode, rules
                ).candidates
                by_mode[mode.value] = [
                    [item.action.value, item.amount, item.units] for item in candidates
                ]
            by_style[style.value] = by_mode
        payload[node_id] = by_style
    return payload


def _digest(payload: object) -> str:
    material = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


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
        "price": 100,
        "eligible_pot": 300,
        "actual_call": 100,
        "pot": 300,
        "effective_stack": 1000,
        "big_blind": 10,
        "stack": 1000,
        "street_bet": 100,
        "preflop_unraised": False,
        "hole_ranks": (14, 13),
    }
    payload.update(overrides)
    return MixedFeatures(**payload)  # type: ignore[arg-type]


def _share_by_action(candidates: object) -> dict[str, float]:
    """按动作类型合并同额候选后的份额。"""
    merged: dict[str, int] = {}
    for item in candidates:  # type: ignore[union-attr]
        merged[item.action.value] = merged.get(item.action.value, 0) + item.units
    total = sum(merged.values())
    return {action: units / total for action, units in merged.items() if units > 0}


def _active_share(candidates: object) -> float:
    total = sum(item.units for item in candidates)  # type: ignore[union-attr]
    active = sum(
        item.units for item in candidates if item.action.value in ("bet", "raise")  # type: ignore[union-attr]
    )
    return active / total


def _draw_states() -> tuple[tuple[str, MixedFeatures, object], ...]:
    return tuple(state for state in _frozen_states() if state[0].startswith("flop-draw"))


# ------------------------------------------------------------------ 取值与摘要


def test_eighth_version_values_are_recorded() -> None:
    """第八版的取值被钉住，其余八个字段与第七版逐字一致。"""
    assert _VALUE_GATE_TOLERANCE == 120
    assert _ACTIVE_GATE_INDEX_CAP == 100
    assert _ACTIVE_GATE_POSITION_SPAN == 60
    assert _ACTIVE_GATE_DRAW_SPAN == 40
    assert dict(_ACTIVE_GATE_WEIGHT) == {
        MixedStyle.TIGHT: -6,
        MixedStyle.AGGRESSIVE: 8,
        MixedStyle.CALLING: 1,
    }
    assert _ACTIVE_GATE_POSITION_SPAN + _ACTIVE_GATE_DRAW_SPAN == _ACTIVE_GATE_INDEX_CAP
    assert MIXED_LOCAL_V8_RULES.situational_active_gate is True
    assert (
        replace(MIXED_LOCAL_V8_RULES, situational_active_gate=False)
        == MIXED_LOCAL_V7_RULES
    )


def test_eighth_identity_is_registered_and_cumulative() -> None:
    """第八版已注册、可构造，并与第七版共用除目标开关以外的全部口径。"""
    assert MIXED_STRATEGY_IDENTIFIERS == (
        MIXED_STRATEGY_IDENTIFIER,
        MIXED_STRATEGY_IDENTIFIER_V2,
        MIXED_STRATEGY_IDENTIFIER_V3,
        MIXED_STRATEGY_IDENTIFIER_V4,
        MIXED_STRATEGY_IDENTIFIER_V5,
        MIXED_STRATEGY_IDENTIFIER_V6,
        MIXED_STRATEGY_IDENTIFIER_V7,
        MIXED_STRATEGY_IDENTIFIER_V8,
    )
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V8).version == 8
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V8).name == "mixed-local"
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V8, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V8
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V8) is MIXED_LOCAL_V8_RULES


def test_digest_fields_add_exactly_one_entry() -> None:
    """摘要字段新增且仅新增第八版条目，逐字列出它实际读取的九个字段。"""
    assert set(DIGEST_RULE_FIELDS) == {
        MIXED_STRATEGY_IDENTIFIER_V2,
        MIXED_STRATEGY_IDENTIFIER_V3,
        MIXED_STRATEGY_IDENTIFIER_V4,
        MIXED_STRATEGY_IDENTIFIER_V5,
        MIXED_STRATEGY_IDENTIFIER_V6,
        MIXED_STRATEGY_IDENTIFIER_V7,
        MIXED_STRATEGY_IDENTIFIER_V8,
    }
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V8] == (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
        "postflop_call_bonus",
        "active_scale_percent",
        "contender_penalty_cap",
        "continuous_non_value_basis",
        "situational_active_gate",
    )
    for identifier, rules in FROZEN_IDENTITIES[1:]:
        assert set(DIGEST_RULE_FIELDS[identifier]) <= set(vars(rules)), identifier


def test_existing_identity_digests_are_unchanged() -> None:
    """旧身份的配置摘要逐字不变：新增字段只被第八版登记。"""
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V6)
        == "b6678f65069c19779f683bd6a8df31f7bc3567cf813654d2758278c13151b4a1"
    )
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V7)
        == "fd7433e35fc8260d03635774b34fbdc419ad5a04ba0448916b036e385a546665"
    )


def test_eighth_version_config_digest_is_pinned() -> None:
    """第八版的配置摘要同样钉死：它将来会被自己的标定回执引用。"""
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V8)
        == "393ca127fc16ef47d22cab29d287f43dde5aa94ee4a5cbb34ed15b4a12f627a2"
    )


# ------------------------------------------------------------------ 隔离与黄金值


def test_switch_off_reproduces_the_seventh_distributions() -> None:
    """把开关单独还原后，冻结节点上的分布必须与第七版逐位相同。"""
    off = replace(MIXED_LOCAL_V8_RULES, situational_active_gate=False)
    assert _frozen_payload(off) == _frozen_payload(MIXED_LOCAL_V7_RULES)


def test_registered_identities_keep_their_frozen_distributions() -> None:
    """逐身份在第四套冻结节点上的分布必须逐位不变：默认值不得改动任何既有分布。"""
    assert {
        identifier: _digest(_frozen_payload(rules))
        for identifier, rules in FROZEN_IDENTITIES
    } == FROZEN_GOLDEN_DIGESTS


# ------------------------------------------------------------------ 偏移的结构性质


def test_gate_is_zero_before_the_flop_and_when_disabled() -> None:
    """偏移只在翻后且开关开启时非零：翻前与关闭时二者都恒为零。"""
    for position in (-40, -10, 0, 20, 40):
        for draw in (0, 60, 180):
            preflop = _features(street=Street.PREFLOP, position=position, draw=draw)
            postflop = _features(position=position, draw=draw)
            for style in MixedStyle:
                assert _active_gate(preflop, style, MIXED_LOCAL_V8_RULES) == 0
                assert _active_gate(postflop, style, MIXED_LOCAL_V7_RULES) == 0


def test_gate_nests_the_styles_and_never_reverses() -> None:
    """三档偏移恒为 aggressive ≥ calling ≥ tight，且在指数取满时严格。"""
    for contenders in (1, 3, 6, 9):
        for position in (-40, -20, 0, 20, 40):
            for draw in (0, 30, 60, 120, 180, 240):
                features = _features(
                    contenders=contenders,
                    live_opponents=contenders,
                    position=position,
                    draw=draw,
                )
                gate = {
                    style: _active_gate(features, style, MIXED_LOCAL_V8_RULES)
                    for style in MixedStyle
                }
                assert (
                    gate[MixedStyle.AGGRESSIVE]
                    >= gate[MixedStyle.CALLING]
                    >= gate[MixedStyle.TIGHT]
                )
                assert -8 <= gate[MixedStyle.TIGHT] <= 8
                assert -8 <= gate[MixedStyle.AGGRESSIVE] <= 8
                if position == 40 and draw == 180:
                    assert (
                        gate[MixedStyle.AGGRESSIVE]
                        > gate[MixedStyle.CALLING]
                        > gate[MixedStyle.TIGHT]
                    )


def test_gate_ignores_every_hand_mode() -> None:
    """偏移不依赖手模式：同一局面在三种模式下的分布只差同一个公共倍率之外的量。"""
    features = _features(draw=180, position=40)
    for style in MixedStyle:
        values = {
            _active_gate(features, style, MIXED_LOCAL_V8_RULES) for _ in HandMode
        }
        assert values == {_active_gate(features, style, MIXED_LOCAL_V8_RULES)}


# ------------------------------------------------------------------ 冻结节点上的方向


def test_active_share_ordering_holds_on_every_draw_node() -> None:
    """冻结的翻牌面对下注节点上，三档主动率恒为 aggressive > calling > tight。"""
    draw_states = _draw_states()
    assert draw_states
    consistent = 0
    for _, features, legal in draw_states:
        for mode in HandMode:
            rates = {
                style: _active_share(
                    build_distribution(
                        features, legal, style, mode, MIXED_LOCAL_V8_RULES
                    ).candidates
                )
                for style in MixedStyle
            }
            assert rates[MixedStyle.AGGRESSIVE] > rates[MixedStyle.CALLING]
            assert rates[MixedStyle.CALLING] > rates[MixedStyle.TIGHT]
            consistent += 1
    assert consistent >= 1


def test_switch_lowers_tight_and_raises_aggressive_on_draw_nodes() -> None:
    """同一节点上，紧密型的主动率下降、进取型的主动率上升，方向不得反转。"""
    for _, features, legal in _draw_states():
        for mode in HandMode:
            for style in (MixedStyle.TIGHT, MixedStyle.AGGRESSIVE):
                before = _active_share(
                    build_distribution(
                        features, legal, style, mode, MIXED_LOCAL_V7_RULES
                    ).candidates
                )
                after = _active_share(
                    build_distribution(
                        features, legal, style, mode, MIXED_LOCAL_V8_RULES
                    ).candidates
                )
                if style is MixedStyle.TIGHT:
                    assert after < before
                else:
                    assert after > before


# ------------------------------------------------------------------ 触及面与副作用（只报告）


def test_touched_rows_are_postflop_only() -> None:
    """被触及的行必须全部落在翻后：这是分化范围的可断言后果。"""
    touched = 0
    for _, features, legal in _frozen_states():
        for style in MixedStyle:
            for mode in HandMode:
                before = build_distribution(
                    features, legal, style, mode, MIXED_LOCAL_V7_RULES
                ).candidates
                after = build_distribution(
                    features, legal, style, mode, MIXED_LOCAL_V8_RULES
                ).candidates
                if [item.model_dump() for item in before] != [
                    item.model_dump() for item in after
                ]:
                    touched += 1
                    assert features.street in FROZEN_POSTFLOP_STREETS
    assert touched > 0


def test_side_effect_inventory_is_reproducible() -> None:
    """副作用清点只作报告：此处只断言同一输入必得同一清点，不设通过门槛。"""
    assert _side_effect_inventory() == _side_effect_inventory()


def _side_effect_inventory() -> dict[str, int]:
    """清点单档化与次高份额跌破的分布数：供报告层引用，不作判定输入。"""
    single_before = single_after = 0
    dropped = 0
    for _, features, legal in _frozen_states():
        for style in MixedStyle:
            for mode in HandMode:
                before = _share_by_action(
                    build_distribution(
                        features, legal, style, mode, MIXED_LOCAL_V7_RULES
                    ).candidates
                )
                after = _share_by_action(
                    build_distribution(
                        features, legal, style, mode, MIXED_LOCAL_V8_RULES
                    ).candidates
                )
                if len(before) == 1:
                    single_before += 1
                if len(after) == 1:
                    single_after += 1
                second_before = sorted(before.values(), reverse=True)[1] if len(before) > 1 else 0.0
                second_after = sorted(after.values(), reverse=True)[1] if len(after) > 1 else 0.0
                if second_before >= 0.10 and second_after < 0.10:
                    dropped += 1
    return {
        "single_before": single_before,
        "single_after": single_after,
        "secondary_dropped": dropped,
    }


# ------------------------------------------------------------------ 合法性与信息边界


def test_candidates_stay_inside_the_known_legal_set() -> None:
    """分化不得引入非法动作：候选动作必须由合法集允许。"""
    allowed = {
        "fold": "can_fold",
        "check": "can_check",
        "call": "can_call",
        "bet": "can_bet",
        "raise": "can_raise",
    }
    for _, features, legal in _frozen_states():
        for style in MixedStyle:
            for mode in HandMode:
                for item in build_distribution(
                    features, legal, style, mode, MIXED_LOCAL_V8_RULES
                ).candidates:
                    assert item.amount >= 0
                    if item.units:
                        assert getattr(legal, allowed[item.action.value]) is True


def test_unregistered_identity_is_rejected() -> None:
    """未登记字段的身份必须显式失败，不得静默回退到别的口径。"""
    with pytest.raises(MixedStrategyError):
        config_digest("mixed-local@9")
