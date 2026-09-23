"""第七版身份的口径回归：非价值进攻依据改为连续量，以及既有身份的逐位隔离。

黄金值在改动前用旧实现捕获，改动后必须逐字复现。口径核验沿用「单开关隔离」：把
第七版规则对象里的目标开关单独还原，比较其余部分完全相同的两份分布，避免别的改动
混入结论。只做有界单元回归与冻结节点回放：不跑性能矩阵、不对抗对局、不访问真实库。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from functools import lru_cache

import pytest

from app.poker.actions import LegalActions
from app.poker.state import Street
from app.strategy.mixed_features import MixedFeatures, extract_features
from app.strategy.mixed_policy import (
    _NON_VALUE_BASE,
    _NON_VALUE_DRAW_CAP,
    _NON_VALUE_DRAW_WEIGHT,
    _NON_VALUE_POSITION_WEIGHT,
    MIXED_LOCAL_V1_RULES,
    MIXED_LOCAL_V2_RULES,
    MIXED_LOCAL_V3_RULES,
    MIXED_LOCAL_V4_RULES,
    MIXED_LOCAL_V5_RULES,
    MIXED_LOCAL_V6_RULES,
    MIXED_LOCAL_V7_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    _continuous_non_value_parts,
    _continuous_non_value_quality,
    _non_value_quality,
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
}
# 改动前捕获时所用的身份与规则对应关系：顺序与取值都必须逐字一致。
FROZEN_IDENTITIES: tuple[tuple[str, MixedPolicyRules], ...] = (
    (MIXED_STRATEGY_IDENTIFIER, MIXED_LOCAL_V1_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V2, MIXED_LOCAL_V2_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V3, MIXED_LOCAL_V3_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V4, MIXED_LOCAL_V4_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V5, MIXED_LOCAL_V5_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V6, MIXED_LOCAL_V6_RULES),
)


@lru_cache(maxsize=1)
def _frozen_states() -> tuple[tuple[str, MixedFeatures, LegalActions], ...]:
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


def _with_contenders(count: int) -> MixedFeatures:
    """把同一翻后局面改成人数的函数：对手数与有筹码对手数同步变化。"""
    return _features(contenders=count, live_opponents=count)


def _active_share(
    normalized_features: MixedFeatures,
    legal: LegalActions,
    style: MixedStyle,
    rules: MixedPolicyRules,
) -> float:
    """主动份额：下注与加注单位之和除以总单位。"""
    candidates = build_distribution(
        normalized_features, legal, style, HandMode.NORMAL, rules
    ).candidates
    total = sum(item.units for item in candidates)
    active = sum(
        item.units for item in candidates if item.action.value in ("bet", "raise")
    )
    return active / total


# ------------------------------------------------------------------ 取值与摘要


def test_seventh_version_values_are_recorded() -> None:
    """第七版的四个取值被钉住，其余七个字段与第六版逐字一致。"""
    assert _NON_VALUE_BASE == 12
    assert _NON_VALUE_POSITION_WEIGHT == 4
    assert _NON_VALUE_DRAW_WEIGHT == 4
    assert _NON_VALUE_DRAW_CAP == 180
    assert MIXED_LOCAL_V7_RULES.continuous_non_value_basis is True
    assert (
        replace(MIXED_LOCAL_V7_RULES, continuous_non_value_basis=False)
        == MIXED_LOCAL_V6_RULES
    )


def test_seventh_identity_is_registered_and_cumulative() -> None:
    """第七版已注册、可构造，并与第六版共用除目标开关以外的全部口径。"""
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
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V7).version == 7
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V7).name == "mixed-local"
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V7, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V7
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V7) is MIXED_LOCAL_V7_RULES
    assert MIXED_LOCAL_V7_RULES.shared_board_chop_caliber is True


def test_digest_fields_cover_exactly_the_registered_identities() -> None:
    """摘要字段按身份登记：既有身份的登记条目未被增删，第七版登记全部八个字段。"""
    assert set(DIGEST_RULE_FIELDS) == {
        MIXED_STRATEGY_IDENTIFIER_V2,
        MIXED_STRATEGY_IDENTIFIER_V3,
        MIXED_STRATEGY_IDENTIFIER_V4,
        MIXED_STRATEGY_IDENTIFIER_V5,
        MIXED_STRATEGY_IDENTIFIER_V6,
        MIXED_STRATEGY_IDENTIFIER_V7,
        MIXED_STRATEGY_IDENTIFIER_V8,
    }
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V7] == (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
        "postflop_call_bonus",
        "active_scale_percent",
        "contender_penalty_cap",
        "continuous_non_value_basis",
    )
    for identifier, rules in FROZEN_IDENTITIES[1:]:
        assert set(DIGEST_RULE_FIELDS[identifier]) <= set(vars(rules)), identifier


def test_earlier_identity_digests_are_unchanged() -> None:
    """旧身份的配置摘要逐字不变：新增字段只被第七版登记。"""
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V6)
        == "b6678f65069c19779f683bd6a8df31f7bc3567cf813654d2758278c13151b4a1"
    )


def test_seventh_version_config_digest_is_pinned() -> None:
    """第七版的配置摘要同样钉死：它将来会被自己的标定回执引用。"""
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V7)
        == "fd7433e35fc8260d03635774b34fbdc419ad5a04ba0448916b036e385a546665"
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V7) != config_digest(
        MIXED_STRATEGY_IDENTIFIER_V6
    )


# ------------------------------------------------------------------ 连续式依据


def test_continuous_basis_is_monotone_and_positive() -> None:
    """准入成立时，对手数增加只会让连续式依据单调不增，且始终为正。"""
    qualities = [
        _non_value_quality(_with_contenders(count), MIXED_LOCAL_V7_RULES)
        for count in range(1, 10)
    ]
    assert all(quality >= 1 for quality in qualities)
    assert qualities == sorted(qualities, reverse=True)


def test_continuous_basis_parts_stay_within_their_declared_bounds() -> None:
    """三个分量各自落在声明上限内，质量等于分量和再按基数封顶。"""
    for contenders in (1, 2, 3, 5, 9):
        for position in (-40, -20, 0, 20, 40):
            for draw in (0, 60, 180, 240):
                features = _features(
                    contenders=contenders,
                    live_opponents=contenders,
                    position=position,
                    draw=draw,
                )
                seats, place, potential = _continuous_non_value_parts(features)
                assert seats == max(1, _NON_VALUE_BASE // contenders)
                assert 0 <= place <= _NON_VALUE_POSITION_WEIGHT
                assert 0 <= potential <= _NON_VALUE_DRAW_WEIGHT
                assert _continuous_non_value_quality(features) == min(
                    _NON_VALUE_BASE, seats + place + potential
                )
                assert 0 <= _continuous_non_value_quality(features) <= _NON_VALUE_BASE


def test_continuous_basis_zeroes_the_absent_components() -> None:
    """最差位置上位置分量为零；无补牌时听牌分量为零；无补牌且无阻断牌时依据为零。"""
    worst_position = _features(position=-40, draw=180)
    assert _continuous_non_value_parts(worst_position)[1] == 0
    no_draw = _features(draw=0)
    assert _continuous_non_value_parts(no_draw)[2] == 0
    assert (
        _non_value_quality(_features(draw=0, hole_ranks=(9, 8)), MIXED_LOCAL_V7_RULES)
        == 0
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_admission_gates_are_unchanged_under_the_switch(enabled: bool) -> None:
    """四条准入与目标开关无关：开关只决定准入成立之后给出多少依据。"""
    rules = replace(MIXED_LOCAL_V7_RULES, continuous_non_value_basis=enabled)
    assert _non_value_quality(_features(recent_aggression=2), rules) == 0
    assert _non_value_quality(_features(live_opponents=0), rules) == 0
    assert (
        _non_value_quality(_features(street=Street.PREFLOP, position=-1, base=400), rules)
        == 0
    )
    assert (
        _non_value_quality(_features(street=Street.PREFLOP, position=10, base=279), rules)
        == 0
    )
    assert _non_value_quality(_features(draw=0, hole_ranks=(9, 8)), rules) == 0
    assert (
        _non_value_quality(
            _features(street=Street.PREFLOP, position=10, base=400), rules
        )
        > 0
    )
    assert _non_value_quality(_features(), rules) > 0


def test_switch_off_reproduces_the_sixth_distributions() -> None:
    """把开关单独还原后，冻结节点上的分布必须与第六版逐位相同。"""
    off = replace(MIXED_LOCAL_V7_RULES, continuous_non_value_basis=False)
    assert _frozen_payload(off) == _frozen_payload(MIXED_LOCAL_V6_RULES)


def test_existing_identities_keep_their_frozen_distributions() -> None:
    """旧身份在第四套冻结节点上的分布必须逐位不变：默认值不得改动任何既有分布。"""
    assert {
        identifier: _digest(_frozen_payload(rules))
        for identifier, rules in FROZEN_IDENTITIES
    } == FROZEN_GOLDEN_DIGESTS


# ------------------------------------------------------------------ 冻结节点上的方向


def test_seventh_version_raises_active_share_on_frozen_draw_nodes() -> None:
    """冻结的翻牌面对下注节点上，第七版的三档主动份额不低于第六版；只断言方向。"""
    draw_nodes = [
        state for state in _frozen_states() if _is_draw_node(state[0])
    ]
    assert draw_nodes
    raised = 0
    for _, features, legal in draw_nodes:
        for style in MixedStyle:
            sixth = _active_share(features, legal, style, MIXED_LOCAL_V6_RULES)
            seventh = _active_share(features, legal, style, MIXED_LOCAL_V7_RULES)
            assert seventh >= sixth
            if seventh > sixth:
                raised += 1
    assert raised > 0


def _is_draw_node(node_id: str) -> bool:
    """第四套配方里翻牌面对下注的节点标识前缀。"""
    return node_id.startswith("flop-draw")
