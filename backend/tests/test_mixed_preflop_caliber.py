"""翻前门槛细化（M2）的针对性回归：口径作用范围、风格排序与旧身份隔离。

只做有界单元回归与冻结节点回放：不跑性能矩阵、不对抗对局、不访问真实库。
"""

from dataclasses import replace

import pytest

from app.strategy.mixed_features import extract_features
from app.strategy.mixed_policy import (
    MIXED_DISTRIBUTION_UNITS,
    MIXED_LOCAL_V1_RULES,
    MIXED_LOCAL_V2_RULES,
    MIXED_LOCAL_V3_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    PreflopCallBonus,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.registry import create_strategy, spec_for

from .mixed_bot_states import (
    MIXED_CATEGORY_STREET,
    AppliedNode,
    applicable_player_counts,
    apply_node,
    build_node,
)

PREFLOP_CATEGORIES = tuple(
    category for category, street in MIXED_CATEGORY_STREET.items() if street.name == "PREFLOP"
)
POSTFLOP_CATEGORIES = tuple(
    category for category, street in MIXED_CATEGORY_STREET.items() if street.name != "PREFLOP"
)


def _replayed(category: str, player_count: int) -> tuple[AppliedNode, object]:
    """回放一个冻结节点并取出规则特征。"""
    node = apply_node(build_node(category, player_count))
    return node, extract_features(node.actor_state(), node.legal_actions())


def _count_for(category: str) -> int:
    """该类别的首个适用人数，避免对结构性不适用的人数取值。"""
    return applicable_player_counts(category)[0]


def _units(
    node: AppliedNode,
    features: object,
    style: MixedStyle,
    rules: MixedPolicyRules,
) -> dict[str, int]:
    """取一份分布的逐动作单位。"""
    distribution = build_distribution(
        features, node.legal_actions(), style, HandMode.NORMAL, rules
    )
    assert sum(item.units for item in distribution.candidates) == MIXED_DISTRIBUTION_UNITS
    return {item.action.value: item.units for item in distribution.candidates}


def _voluntary_units(units: dict[str, int]) -> int:
    """自愿投入的单位：跟注与主动动作之和，与弃牌、免费过牌无关。"""
    return units.get("call", 0) + units.get("bet", 0) + units.get("raise", 0)


def _entry(category: str, player_count: int, style: MixedStyle, rules: MixedPolicyRules) -> int:
    node, features = _replayed(category, player_count)
    return _voluntary_units(_units(node, features, style, rules))


# ------------------------------------------------------------------ 作用范围


@pytest.mark.parametrize("category", POSTFLOP_CATEGORIES)
@pytest.mark.parametrize("style", list(MixedStyle))
def test_preflop_caliber_does_not_leak_postflop(category: str, style: MixedStyle) -> None:
    """翻前细化只应影响翻前：翻后节点上第三版与第二版必须逐位一致。"""
    node, features = _replayed(category, _count_for(category))
    legal = node.legal_actions()
    assert build_distribution(
        features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V3_RULES
    ) == build_distribution(features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V2_RULES)


@pytest.mark.parametrize("category", PREFLOP_CATEGORIES)
@pytest.mark.parametrize("style", list(MixedStyle))
def test_second_version_preflop_is_unchanged(category: str, style: MixedStyle) -> None:
    """第二版的翻前分布必须仍与首版一致：M2 只落在第三版。"""
    node, features = _replayed(category, _count_for(category))
    legal = node.legal_actions()
    assert build_distribution(
        features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V2_RULES
    ) == build_distribution(features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V1_RULES)


@pytest.mark.parametrize("style", list(MixedStyle))
def test_preflop_bonus_moves_mass_only_to_the_passive_branch(style: MixedStyle) -> None:
    """跟注偏移只改变被动分支：主动候选与免费过牌必须逐项不变。"""
    node, features = _replayed("facing-first-raise", 4)
    without_bonus = replace(MIXED_LOCAL_V3_RULES, preflop_call_bonus=PreflopCallBonus())
    with_bonus = _units(node, features, style, MIXED_LOCAL_V3_RULES)
    plain = _units(node, features, style, without_bonus)
    for action in ("bet", "raise", "check"):
        assert with_bonus.get(action, 0) == plain.get(action, 0)
    bonus = MIXED_LOCAL_V3_RULES.preflop_call_bonus
    if getattr(bonus, style.value) == 0:
        # 偏移为零的风格必须与去掉全部偏移时逐项一致。
        assert with_bonus == plain
        return
    assert with_bonus.get("call", 0) > plain.get("call", 0)
    assert with_bonus.get("fold", 0) < plain.get("fold", 0)


# ------------------------------------------------------------------ 风格排序


@pytest.mark.parametrize("category", PREFLOP_CATEGORIES)
@pytest.mark.parametrize("style", list(MixedStyle))
def test_third_version_never_reduces_preflop_entry(category: str, style: MixedStyle) -> None:
    """第三版在任何翻前节点上都不得降低该风格的自愿投入。"""
    count = _count_for(category)
    assert _entry(category, count, style, MIXED_LOCAL_V3_RULES) >= _entry(
        category, count, style, MIXED_LOCAL_V2_RULES
    )


# 三档自愿投入互不相同的翻前节点；其余节点见下方两条边界记录。
_SEPARATING_CATEGORIES = ("unopened-open", "hu-blind-position", "facing-first-raise")


@pytest.mark.parametrize("category", _SEPARATING_CATEGORIES)
def test_third_version_separates_the_styles(category: str) -> None:
    """在没有被阈值饱和的翻前节点上，三档的自愿投入必须两两可分辨。"""
    count = _count_for(category)
    entries = sorted(
        _entry(category, count, style, MIXED_LOCAL_V3_RULES) for style in MixedStyle
    )
    assert entries[1] - entries[0] >= 10000
    assert entries[2] - entries[1] >= 10000


def test_short_stack_node_saturates_every_style() -> None:
    """记录实测边界（不是期望值）：短码跟注节点上三档的自愿投入都饱和到全量。"""
    count = _count_for("short-stack-call")
    entries = {
        _entry("short-stack-call", count, style, MIXED_LOCAL_V3_RULES) for style in MixedStyle
    }
    assert entries == {MIXED_DISTRIBUTION_UNITS}


def test_incomplete_raise_node_saturates_two_styles() -> None:
    """记录实测边界：不足额加注节点上松凶与跟注型饱和，只有紧密型仍有区分空间。"""
    count = _count_for("incomplete-raise")
    assert (
        _entry("incomplete-raise", count, MixedStyle.AGGRESSIVE, MIXED_LOCAL_V3_RULES)
        == MIXED_DISTRIBUTION_UNITS
    )
    assert (
        _entry("incomplete-raise", count, MixedStyle.CALLING, MIXED_LOCAL_V3_RULES)
        == MIXED_DISTRIBUTION_UNITS
    )
    assert (
        _entry("incomplete-raise", count, MixedStyle.TIGHT, MIXED_LOCAL_V3_RULES)
        < MIXED_DISTRIBUTION_UNITS
    )


# ------------------------------------------------------------------ 边界与身份


def test_preflop_caliber_ignores_opponent_hole_cards() -> None:
    """换掉未公开的对手底牌不得改变翻前特征。"""
    fixture = build_node("facing-first-raise", 2)
    actor_seat = apply_node(fixture).engine.current_seat
    holes = list(fixture.hole_cards)
    holes[1 - actor_seat] = ("7s", "8s")
    first = apply_node(fixture)
    second = apply_node(fixture.model_copy(update={"hole_cards": tuple(holes)}))
    assert extract_features(first.actor_state(), first.legal_actions()) == extract_features(
        second.actor_state(), second.legal_actions()
    )


def test_old_identities_keep_the_original_preflop_caliber() -> None:
    for rules in (MIXED_LOCAL_V1_RULES, MIXED_LOCAL_V2_RULES):
        assert rules.preflop_price_weight == 450
        assert rules.preflop_contender_penalty == 35
        assert rules.preflop_call_bonus == PreflopCallBonus()


def test_third_identity_is_registered_and_cumulative() -> None:
    # 后续版本会追加在末尾，因此这里只锁定前三版的顺序与并存关系。
    assert MIXED_STRATEGY_IDENTIFIERS[:3] == (
        MIXED_STRATEGY_IDENTIFIER,
        MIXED_STRATEGY_IDENTIFIER_V2,
        MIXED_STRATEGY_IDENTIFIER_V3,
    )
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V3).version == 3
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V3, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V3
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V3) is MIXED_LOCAL_V3_RULES
    # 第三版是累积版：必须继承第二版的锁定平分口径。
    assert MIXED_LOCAL_V3_RULES.shared_board_chop_caliber is True


def test_preflop_bonus_fields_match_the_style_values() -> None:
    bonus = MIXED_LOCAL_V3_RULES.preflop_call_bonus
    for style in MixedStyle:
        assert isinstance(getattr(bonus, style.value), int)
    assert (bonus.tight, bonus.aggressive, bonus.calling) == (0, 35, 110)
    assert bonus.calling > bonus.aggressive > bonus.tight
