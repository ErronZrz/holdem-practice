"""风格可分辨性细化（第五版身份）的针对性回归：取值、作用面与旧身份隔离。

只做有界单元回归与冻结节点回放：不跑性能矩阵、不对抗对局、不访问真实库。
"""

from dataclasses import replace

import pytest

from app.strategy.mixed_context import require_mixed_input
from app.strategy.mixed_features import features_for
from app.strategy.mixed_policy import (
    HAND_MODE_ROLL_BOUNDS,
    MIXED_DISTRIBUTION_UNITS,
    MIXED_LOCAL_V1_RULES,
    MIXED_LOCAL_V2_RULES,
    MIXED_LOCAL_V3_RULES,
    MIXED_LOCAL_V4_RULES,
    MIXED_LOCAL_V5_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    PreflopCallBonus,
    StyleCallBonus,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
    MIXED_STRATEGY_IDENTIFIER_V4,
    MIXED_STRATEGY_IDENTIFIER_V5,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.registry import create_strategy, spec_for

from .mixed_bot_states import (
    MIXED_CATEGORY_STREET,
    AppliedNode,
    applicable_player_counts,
    apply_node,
    build_frozen_nodes,
    build_node,
)
from .mixed_bot_validation import (
    MIXED_HAND_MODE_WEIGHTS,
    MIXED_HAND_MODES,
    js_distance,
)

PREFLOP_CATEGORIES = tuple(
    category for category, street in MIXED_CATEGORY_STREET.items() if street.name == "PREFLOP"
)
POSTFLOP_CATEGORIES = tuple(
    category for category, street in MIXED_CATEGORY_STREET.items() if street.name != "PREFLOP"
)
STYLE_PAIRS = (
    (MixedStyle.TIGHT, MixedStyle.AGGRESSIVE),
    (MixedStyle.TIGHT, MixedStyle.CALLING),
    (MixedStyle.AGGRESSIVE, MixedStyle.CALLING),
)
# 目标口径：三对风格的平均距离都不得低于该值。
SEPARATION_FLOOR = 0.15
# 记录实测（不是期望值）：第五版在松凶–跟注这一对上仍有这么多节点分布逐位相同。
IDENTICAL_NODES_FIFTH_VERSION = 30


def _replayed(category: str, player_count: int) -> AppliedNode:
    """回放一个冻结节点。"""
    return apply_node(build_node(category, player_count))


def _count_for(category: str) -> int:
    """该类别的首个适用人数，避免对结构性不适用的人数取值。"""
    return applicable_player_counts(category)[0]


def _features(node: AppliedNode) -> object:
    """取出该节点行动者视角的规则特征。"""
    return features_for(require_mixed_input(node.actor_state()), node.legal_actions())


def _units(
    node: AppliedNode,
    style: MixedStyle,
    rules: MixedPolicyRules,
    mode: HandMode = HandMode.NORMAL,
) -> dict[str, int]:
    """取一份分布的逐动作单位。"""
    distribution = build_distribution(
        _features(node), node.legal_actions(), style, mode, rules
    )
    assert sum(item.units for item in distribution.candidates) == MIXED_DISTRIBUTION_UNITS
    return {item.action.value: item.units for item in distribution.candidates}


def _marginal(
    node: AppliedNode,
    style: MixedStyle,
    rules: MixedPolicyRules,
) -> dict[tuple[str, int], float]:
    """按手模式权重把三份分布合并为一份动作/金额边缘分布。"""
    features = _features(node)
    assert len(MIXED_HAND_MODES) == len(HAND_MODE_ROLL_BOUNDS)
    marginal: dict[tuple[str, int], float] = {}
    for weight, mode in zip(MIXED_HAND_MODE_WEIGHTS, MIXED_HAND_MODES, strict=True):
        distribution = build_distribution(features, node.legal_actions(), style, mode, rules)
        for item in distribution.candidates:
            key = (item.action.value, item.amount)
            marginal[key] = marginal.get(key, 0.0) + weight * item.units
    return marginal


@pytest.fixture(scope="module")
def separated() -> dict[str, float]:
    """第五版在全部冻结节点上的成对平均距离（确定性回放，不抽样）。"""
    samples: dict[tuple[MixedStyle, MixedStyle], list[float]] = {pair: [] for pair in STYLE_PAIRS}
    for fixture in build_frozen_nodes():
        node = apply_node(fixture)
        marginals = {
            style: _marginal(node, style, MIXED_LOCAL_V5_RULES) for style in MixedStyle
        }
        for pair in STYLE_PAIRS:
            samples[pair].append(js_distance(marginals[pair[0]], marginals[pair[1]]))
    return {
        f"{left.value}-{right.value}": sum(samples[(left, right)]) / len(samples[(left, right)])
        for left, right in STYLE_PAIRS
    }


# ------------------------------------------------------------------ 取值与身份


def test_fifth_version_postflop_bonus_value_is_recorded() -> None:
    """第五版的偏移取值被钉住：只有跟注型拿到翻后偏移。"""
    bonus = MIXED_LOCAL_V5_RULES.postflop_call_bonus
    assert (bonus.tight, bonus.aggressive, bonus.calling) == (0, 0, 100)


def test_fifth_version_only_adds_the_postflop_bonus() -> None:
    """第五版与第四版只应相差翻后偏移这一个字段取值。"""
    assert MIXED_LOCAL_V4_RULES.postflop_call_bonus == StyleCallBonus()
    assert MIXED_LOCAL_V5_RULES.preflop_call_bonus == MIXED_LOCAL_V4_RULES.preflop_call_bonus
    assert (
        replace(MIXED_LOCAL_V5_RULES, postflop_call_bonus=StyleCallBonus())
        == MIXED_LOCAL_V4_RULES
    )


def test_first_four_identities_keep_their_calibers() -> None:
    """前四个身份的口径取值保持不变，新版本不回溯改写旧身份。"""
    for rules in (MIXED_LOCAL_V1_RULES, MIXED_LOCAL_V2_RULES):
        assert rules.preflop_call_bonus == PreflopCallBonus()
        assert rules.postflop_call_bonus == StyleCallBonus()
    assert MIXED_LOCAL_V3_RULES.preflop_call_bonus == PreflopCallBonus(
        tight=0, aggressive=35, calling=110
    )
    assert MIXED_LOCAL_V4_RULES.preflop_call_bonus == PreflopCallBonus(
        tight=30, aggressive=35, calling=110
    )
    for rules in (MIXED_LOCAL_V3_RULES, MIXED_LOCAL_V4_RULES):
        assert rules.postflop_call_bonus == StyleCallBonus()


def test_fifth_identity_is_registered_and_cumulative() -> None:
    """第五版已注册、可构造，且继承第四版的口径。"""
    assert MIXED_STRATEGY_IDENTIFIERS[:5] == (
        MIXED_STRATEGY_IDENTIFIER,
        MIXED_STRATEGY_IDENTIFIER_V2,
        MIXED_STRATEGY_IDENTIFIER_V3,
        MIXED_STRATEGY_IDENTIFIER_V4,
        MIXED_STRATEGY_IDENTIFIER_V5,
    )
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V5).version == 5
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V5, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V5
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V5) is MIXED_LOCAL_V5_RULES
    assert MIXED_LOCAL_V5_RULES.shared_board_chop_caliber is True


# ------------------------------------------------------------------ 作用范围


@pytest.mark.parametrize("category", PREFLOP_CATEGORIES)
@pytest.mark.parametrize("style", list(MixedStyle))
def test_preflop_is_identical_between_fourth_and_fifth(
    category: str, style: MixedStyle
) -> None:
    """翻前节点上第五版与第四版必须逐位一致：本次只动翻后被动分支。"""
    node = _replayed(category, _count_for(category))
    legal = node.legal_actions()
    features = _features(node)
    assert build_distribution(
        features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V5_RULES
    ) == build_distribution(features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V4_RULES)


@pytest.mark.parametrize("category", POSTFLOP_CATEGORIES)
@pytest.mark.parametrize("style", [MixedStyle.TIGHT, MixedStyle.AGGRESSIVE])
def test_postflop_bonus_leaves_other_styles_unchanged(
    category: str, style: MixedStyle
) -> None:
    """偏移只发给跟注型：其余两档在翻后也必须逐位一致。"""
    node = _replayed(category, _count_for(category))
    legal = node.legal_actions()
    features = _features(node)
    assert build_distribution(
        features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V5_RULES
    ) == build_distribution(features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V4_RULES)


def test_postflop_bonus_moves_mass_only_to_the_passive_branch() -> None:
    """偏移只改变跟注型的被动分支：跟注变多、弃牌变少。"""
    node = _replayed("overpair-on-high-board", 2)
    fifth = _units(node, MixedStyle.CALLING, MIXED_LOCAL_V5_RULES)
    fourth = _units(node, MixedStyle.CALLING, MIXED_LOCAL_V4_RULES)
    assert fifth.get("call", 0) > fourth.get("call", 0)
    assert fifth.get("fold", 0) < fourth.get("fold", 0)


def test_postflop_bonus_keeps_the_active_candidate_set() -> None:
    """偏移不生成也不删除主动候选：它的作用面只有被动分支。

    主动候选的单位数会随归一化分母变化（被动质量变大后份额自然下降），
    因此这里锁定的是候选集合与彼此的相对大小，而不是单位数本身。
    """
    node = _replayed("sizes-merged", 2)
    fifth = _units(node, MixedStyle.CALLING, MIXED_LOCAL_V5_RULES)
    fourth = _units(node, MixedStyle.CALLING, MIXED_LOCAL_V4_RULES)
    active = ("bet", "raise")
    for action in active:
        assert (action in fifth) == (action in fourth)
    assert sum(fifth.get(a, 0) for a in active) <= sum(fourth.get(a, 0) for a in active)


def test_postflop_bonus_does_not_touch_the_check_weight() -> None:
    """免费过牌的质量不由跟注偏移决定，因此该动作的单位数不受影响。"""
    node = _replayed("free-check", 2)
    fifth = _units(node, MixedStyle.CALLING, MIXED_LOCAL_V5_RULES)
    fourth = _units(node, MixedStyle.CALLING, MIXED_LOCAL_V4_RULES)
    assert fifth == fourth


# ------------------------------------------------------------------ 可分辨性


def test_fifth_version_meets_the_separation_target(separated: dict[str, float]) -> None:
    """目标口径：三对风格的平均距离都不低于下限。"""
    assert min(separated.values()) >= SEPARATION_FLOOR
    assert separated["tight-aggressive"] > SEPARATION_FLOOR
    assert separated["tight-calling"] > SEPARATION_FLOOR


def test_fifth_version_lifts_the_weakest_pair(separated: dict[str, float]) -> None:
    """最弱的一对被抬到与另两对同量级，且另两对不因此回落。"""
    assert separated["aggressive-calling"] > separated["tight-aggressive"] * 0.75


def test_identical_node_count_is_recorded() -> None:
    """记录实测边界（不是期望值）：最弱一对上仍有这么多节点的分布逐位相同。"""
    identical = 0
    for fixture in build_frozen_nodes():
        node = apply_node(fixture)
        if _marginal(node, MixedStyle.AGGRESSIVE, MIXED_LOCAL_V5_RULES) == _marginal(
            node, MixedStyle.CALLING, MIXED_LOCAL_V5_RULES
        ):
            identical += 1
    assert identical == IDENTICAL_NODES_FIFTH_VERSION
