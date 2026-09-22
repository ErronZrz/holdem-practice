"""紧密型翻前跟注偏移修订（第四版身份）的针对性回归：取值、作用范围与旧身份隔离。

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
    MIXED_LOCAL_V4_RULES,
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
    MIXED_STRATEGY_IDENTIFIER_V4,
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
# 该节点唯一自愿动作是主动投入，没有跟注分支，偏移在此处无从生效。
PASSIVE_FREE_CATEGORY = "open-after-limp"
# 该节点上三档自愿投入都已饱和，偏移不可能再提高紧密型的投入。
SATURATED_CATEGORY = "short-stack-call"


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


RAISED_CATEGORIES = tuple(
    category
    for category in PREFLOP_CATEGORIES
    if category not in (PASSIVE_FREE_CATEGORY, SATURATED_CATEGORY)
)


# ------------------------------------------------------------------ 取值与身份


def test_fourth_version_bonus_value_is_recorded() -> None:
    """第四版的偏移取值被钉住：紧密型 30，松凶与跟注型沿用第三版。"""
    bonus = MIXED_LOCAL_V4_RULES.preflop_call_bonus
    assert (bonus.tight, bonus.aggressive, bonus.calling) == (30, 35, 110)


def test_fourth_version_only_changes_the_tight_bonus() -> None:
    """第四版与第三版只应相差紧密型这一个偏移取值。"""
    third = MIXED_LOCAL_V3_RULES.preflop_call_bonus
    fourth = MIXED_LOCAL_V4_RULES.preflop_call_bonus
    assert third.tight == 0 and fourth.tight == 30
    assert (third.aggressive, third.calling) == (fourth.aggressive, fourth.calling)
    assert replace(MIXED_LOCAL_V4_RULES, preflop_call_bonus=third) == MIXED_LOCAL_V3_RULES


def test_first_three_identities_keep_their_preflop_values() -> None:
    """前三个身份的口径对象取值保持不变，新版本不回溯改写旧身份。"""
    for rules in (MIXED_LOCAL_V1_RULES, MIXED_LOCAL_V2_RULES):
        assert rules.preflop_price_weight == 450
        assert rules.preflop_contender_penalty == 35
        assert rules.preflop_call_bonus == PreflopCallBonus()
    assert MIXED_LOCAL_V3_RULES.preflop_price_weight == 150
    assert MIXED_LOCAL_V3_RULES.preflop_contender_penalty == 30
    assert MIXED_LOCAL_V3_RULES.preflop_call_bonus == PreflopCallBonus(
        tight=0, aggressive=35, calling=110
    )


def test_fourth_identity_is_registered_and_cumulative() -> None:
    """第四版已注册、可构造，且继承第三版的分池口径。"""
    assert MIXED_STRATEGY_IDENTIFIERS[:4] == (
        MIXED_STRATEGY_IDENTIFIER,
        MIXED_STRATEGY_IDENTIFIER_V2,
        MIXED_STRATEGY_IDENTIFIER_V3,
        MIXED_STRATEGY_IDENTIFIER_V4,
    )
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V4).version == 4
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V4, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V4
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V4) is MIXED_LOCAL_V4_RULES
    assert MIXED_LOCAL_V4_RULES.shared_board_chop_caliber is True


# ------------------------------------------------------------------ 作用范围


@pytest.mark.parametrize("category", POSTFLOP_CATEGORIES)
@pytest.mark.parametrize("style", list(MixedStyle))
def test_postflop_is_identical_between_third_and_fourth(category: str, style: MixedStyle) -> None:
    """翻后节点上第四版与第三版必须逐位一致：本次只动翻前偏移。"""
    node, features = _replayed(category, _count_for(category))
    legal = node.legal_actions()
    assert build_distribution(
        features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V4_RULES
    ) == build_distribution(features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V3_RULES)


@pytest.mark.parametrize("style", list(MixedStyle))
def test_tight_bonus_moves_mass_only_to_the_passive_branch(style: MixedStyle) -> None:
    """偏移只改变被动分支：主动候选与免费过牌必须逐项不变。"""
    node, features = _replayed("facing-first-raise", 4)
    fourth = _units(node, features, style, MIXED_LOCAL_V4_RULES)
    third = _units(node, features, style, MIXED_LOCAL_V3_RULES)
    for action in ("bet", "raise", "check"):
        assert fourth.get(action, 0) == third.get(action, 0)
    if style is not MixedStyle.TIGHT:
        # 松凶与跟注型的偏移未变，因此整份分布必须逐项一致。
        assert fourth == third
        return
    assert fourth.get("call", 0) > third.get("call", 0)
    assert fourth.get("fold", 0) < third.get("fold", 0)


# ------------------------------------------------------------------ 翻前效果


@pytest.mark.parametrize("category", PREFLOP_CATEGORIES)
@pytest.mark.parametrize("style", list(MixedStyle))
def test_fourth_version_never_reduces_preflop_entry(category: str, style: MixedStyle) -> None:
    """第四版在任何翻前节点上都不得降低该风格的自愿投入。"""
    count = _count_for(category)
    assert _entry(category, count, style, MIXED_LOCAL_V4_RULES) >= _entry(
        category, count, style, MIXED_LOCAL_V3_RULES
    )


@pytest.mark.parametrize("category", RAISED_CATEGORIES)
def test_fourth_version_raises_tight_entry(category: str) -> None:
    """有跟注分支且未饱和的节点上，紧密型的自愿投入必须真的提高。"""
    count = _count_for(category)
    assert _entry(category, count, MixedStyle.TIGHT, MIXED_LOCAL_V4_RULES) > _entry(
        category, count, MixedStyle.TIGHT, MIXED_LOCAL_V3_RULES
    )


def test_passive_free_node_is_unaffected_by_the_tight_bonus() -> None:
    """记录实测边界（不是期望值）：两人可过牌节点没有跟注分支，偏移不生效。"""
    count = _count_for(PASSIVE_FREE_CATEGORY)
    node, features = _replayed(PASSIVE_FREE_CATEGORY, count)
    legal = node.legal_actions()
    assert build_distribution(
        features, legal, MixedStyle.TIGHT, HandMode.NORMAL, MIXED_LOCAL_V4_RULES
    ) == build_distribution(
        features, legal, MixedStyle.TIGHT, HandMode.NORMAL, MIXED_LOCAL_V3_RULES
    )


def test_tight_bonus_ignores_opponent_hole_cards() -> None:
    """换掉未公开的对手底牌不得改变紧密型的翻前分布。"""
    fixture = build_node("facing-first-raise", 2)
    actor_seat = apply_node(fixture).engine.current_seat
    holes = list(fixture.hole_cards)
    holes[1 - actor_seat] = ("7s", "8s")
    first = apply_node(fixture)
    second = apply_node(fixture.model_copy(update={"hole_cards": tuple(holes)}))
    assert build_distribution(
        extract_features(first.actor_state(), first.legal_actions()),
        first.legal_actions(),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
        MIXED_LOCAL_V4_RULES,
    ) == build_distribution(
        extract_features(second.actor_state(), second.legal_actions()),
        second.legal_actions(),
        MixedStyle.TIGHT,
        HandMode.NORMAL,
        MIXED_LOCAL_V4_RULES,
    )
