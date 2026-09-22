"""共享牌面细化（M1）的针对性回归：锁定判定、分池口径与新身份隔离。

只做有界单元回归与冻结节点回放：不跑性能矩阵、不对抗对局、不访问真实库。
"""

import pytest

from app.poker.cards import card_from_str
from app.poker.evaluator import evaluate_fast
from app.strategy import mixed_features
from app.strategy.mixed_features import _board_hand_is_untouchable, extract_features
from app.strategy.mixed_policy import (
    MIXED_DISTRIBUTION_UNITS,
    MIXED_LOCAL_V1_RULES,
    MIXED_LOCAL_V2_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIERS,
    MixedLocalStrategy,
    MixedStrategyError,
    derive_bots_key,
    derive_deck_seed,
    derive_root_key,
    rules_for_identifier,
)
from app.strategy.registry import (
    UnknownStrategyError,
    create_strategy,
    known_identifiers,
    resolve_identifier,
    spec_for,
)

from .mixed_bot_states import MIXED_PLAYER_COUNTS, AppliedNode, apply_node, build_node

# ------------------------------------------------------------------ 锁定判定


def _untouchable(tokens: str) -> bool:
    """按牌面字符串判断公共五张是否已不可能被任意两张底牌超越。"""
    board = [card_from_str(token) for token in tokens.split()]
    return _board_hand_is_untouchable(board, evaluate_fast(board))


@pytest.mark.parametrize(
    ("board", "expected"),
    [
        # 百老汇顺子：没有对子、同花不可能、已是最高的顺子。
        ("Ah Kd Qc Js Th", True),
        # 中段顺子可被更高的顺子超越。
        ("9h 8d 7c 6s 5h", False),
        # 公共至少三张同花：两张同花底牌即可成同花。
        ("Ah Kh Qh Js Td", False),
        # 公共三条：任一底牌配上即成四条。
        ("Ah Ad Ac Kd Qc", False),
        # 公共两对：底牌可凑出葫芦。
        ("Ah Ad Kc Kd 2s", False),
        # 公共四条：排除同花顺后无人能超越。
        ("Ah Ad Ac As Kd", True),
        # 皇家同花顺本身就是最高牌型。
        ("Ah Kh Qh Jh Th", True),
        # 九高同花顺：同花色的 J T 即可抬高。
        ("9h 8h 7h 6h 5h", False),
        # 公共五张同花（非同花顺）：同花底牌可抬高。
        ("Ah Kh 9h 7h 4h", False),
    ],
)
def test_untouchable_board_detection(board: str, expected: bool) -> None:
    assert _untouchable(board) is expected


def _replayed(category: str, player_count: int) -> tuple[AppliedNode, mixed_features.MixedFeatures]:
    """回放一个冻结节点并取出规则特征。"""
    node = apply_node(build_node(category, player_count))
    return node, extract_features(node.actor_state(), node.legal_actions())


@pytest.mark.parametrize("player_count", MIXED_PLAYER_COUNTS)
def test_shared_board_nodes_are_locked(player_count: int) -> None:
    """冻结的共享牌面节点在全部适用人数上都应被判为锁定平分。"""
    _, features = _replayed("shared-board", player_count)
    assert features.shared_board_locked is True
    # 既有保守封顶保持不变：细化只改跟注价格口径。
    assert features.base == 450


def test_plain_river_shape_is_not_locked() -> None:
    """普通一对牌面不属于锁定平分，不得被误判。"""
    _, features = _replayed("sizes-merged", 2)
    assert features.shared_board_locked is False


# ------------------------------------------------------------------ 分池口径


def _units(
    node: AppliedNode,
    features: mixed_features.MixedFeatures,
    style: MixedStyle,
    rules: MixedPolicyRules,
) -> dict[str, int]:
    """取一份分布的逐动作单位，便于比较两版口径。"""
    distribution = build_distribution(
        features, node.legal_actions(), style, HandMode.NORMAL, rules
    )
    return {item.action.value: item.units for item in distribution.candidates}


@pytest.mark.parametrize("style", list(MixedStyle))
@pytest.mark.parametrize("player_count", MIXED_PLAYER_COUNTS)
def test_chop_caliber_only_moves_mass_from_fold_to_call(
    style: MixedStyle, player_count: int
) -> None:
    """分池口径只把质量从弃牌移向跟注，任何人数与风格上都不得反向。"""
    node, features = _replayed("shared-board", player_count)
    old = _units(node, features, style, MIXED_LOCAL_V1_RULES)
    new = _units(node, features, style, MIXED_LOCAL_V2_RULES)
    assert new.get("fold", 0) <= old.get("fold", 0)
    assert new.get("call", 0) >= old.get("call", 0)
    assert sum(new.values()) == MIXED_DISTRIBUTION_UNITS


@pytest.mark.parametrize("style", list(MixedStyle))
def test_heads_up_locked_board_recovers_call_mass(style: MixedStyle) -> None:
    """两人桌的锁定平分局面必须给出高于首版的跟注质量。"""
    node, features = _replayed("shared-board", 2)
    old = _units(node, features, style, MIXED_LOCAL_V1_RULES)
    new = _units(node, features, style, MIXED_LOCAL_V2_RULES)
    assert new.get("call", 0) > old.get("call", 0)


@pytest.mark.parametrize("style", list(MixedStyle))
def test_non_locked_nodes_are_unchanged(style: MixedStyle) -> None:
    """非锁定节点上两版分布必须完全一致，细化不得外溢。"""
    node, features = _replayed("sizes-merged", 2)
    legal = node.legal_actions()
    assert build_distribution(
        features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V1_RULES
    ) == build_distribution(features, legal, style, HandMode.NORMAL, MIXED_LOCAL_V2_RULES)


@pytest.mark.parametrize("style", list(MixedStyle))
def test_lock_covers_every_player_count(style: MixedStyle) -> None:
    """人数惩罚在锁定局面被免除后，全部适用人数都应给出非零跟注质量。"""
    for player_count in MIXED_PLAYER_COUNTS:
        node, features = _replayed("shared-board", player_count)
        new = _units(node, features, style, MIXED_LOCAL_V2_RULES)
        assert new.get("call", 0) > 0


@pytest.mark.parametrize("style", list(MixedStyle))
@pytest.mark.parametrize("player_count", MIXED_PLAYER_COUNTS)
def test_locked_board_keeps_no_active_aggression(
    style: MixedStyle, player_count: int
) -> None:
    """锁定平分局面只在弃牌与跟注之间分摊：不得凭空产生下注或加注质量。"""
    node, features = _replayed("shared-board", player_count)
    new = _units(node, features, style, MIXED_LOCAL_V2_RULES)
    passive = new.get("fold", 0) + new.get("call", 0) + new.get("check", 0)
    assert passive == MIXED_DISTRIBUTION_UNITS


# ------------------------------------------------------------------ 边界与预算


def test_locked_decision_ignores_opponent_hole_cards() -> None:
    """换掉未公开的对手底牌不得改变锁定判定与特征。"""
    fixture = build_node("shared-board", 2)
    actor_seat = apply_node(fixture).engine.current_seat
    other = 1 - actor_seat
    holes = list(fixture.hole_cards)
    holes[other] = ("7s", "8s")
    first = apply_node(fixture)
    second = apply_node(fixture.model_copy(update={"hole_cards": tuple(holes)}))
    assert extract_features(first.actor_state(), first.legal_actions()) == extract_features(
        second.actor_state(), second.legal_actions()
    )


def test_river_decision_still_uses_at_most_two_evaluations(monkeypatch) -> None:
    """锁定判定不得增加牌型评估次数：河牌单次决策仍然至多两次。"""
    calls = {"count": 0}
    original = mixed_features.evaluate_fast

    def _counting(cards):
        calls["count"] += 1
        return original(cards)

    monkeypatch.setattr(mixed_features, "evaluate_fast", _counting)
    node = apply_node(build_node("shared-board", 2))
    features = extract_features(node.actor_state(), node.legal_actions())
    assert features.shared_board_locked is True
    assert calls["count"] <= 2


def test_second_version_replays_deterministically() -> None:
    """第二版仍是无状态函数式实现：重复查询与采样得到同一结果。"""
    node = apply_node(build_node("shared-board", 2))
    state = node.actor_state()
    legal = node.legal_actions()
    strategy = MixedLocalStrategy(seed=7, identifier=MIXED_STRATEGY_IDENTIFIER_V2)
    assert strategy.bot_seats == ()
    distribution = strategy.distribution_for(state, legal)
    assert distribution == strategy.distribution_for(state, legal)
    assert strategy.choose_action(state, legal) == strategy.choose_action(state, legal)
    first_version = MixedLocalStrategy(seed=7, identifier=MIXED_STRATEGY_IDENTIFIER)
    assert first_version.distribution_for(state, legal) != distribution


# ------------------------------------------------------------------ 身份隔离


def test_second_identity_is_registered_alongside_the_first() -> None:
    assert resolve_identifier(MIXED_STRATEGY_IDENTIFIER_V2) == MIXED_STRATEGY_IDENTIFIER_V2
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V2).version == 2
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V2).name == "mixed-local"
    assert {
        MIXED_STRATEGY_IDENTIFIER,
        MIXED_STRATEGY_IDENTIFIER_V2,
    } <= set(known_identifiers())
    # 后续版本会追加在末尾，因此这里只锁定前两版的顺序与并存关系。
    assert MIXED_STRATEGY_IDENTIFIERS[:2] == (
        MIXED_STRATEGY_IDENTIFIER,
        MIXED_STRATEGY_IDENTIFIER_V2,
    )


@pytest.mark.parametrize("value", ["mixed-local", "mixed-local@4", "mixed-local@1 "])
def test_unregistered_mixed_identifiers_still_fail(value: str) -> None:
    with pytest.raises(UnknownStrategyError):
        resolve_identifier(value)


def test_factory_keeps_each_version_on_its_own_caliber() -> None:
    second = create_strategy(MIXED_STRATEGY_IDENTIFIER_V2, 5)
    first = create_strategy(MIXED_STRATEGY_IDENTIFIER, 5)
    assert isinstance(second, MixedLocalStrategy)
    assert second.identifier == MIXED_STRATEGY_IDENTIFIER_V2
    assert first.identifier == MIXED_STRATEGY_IDENTIFIER
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER) is MIXED_LOCAL_V1_RULES
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V2) is MIXED_LOCAL_V2_RULES


def test_unregistered_identity_never_falls_back_to_the_first_version() -> None:
    """未注册身份必须显式失败，不得静默沿用首版口径或随机流。"""
    with pytest.raises(MixedStrategyError):
        rules_for_identifier("mixed-local@4")
    with pytest.raises(MixedStrategyError):
        MixedLocalStrategy(seed=1, identifier="mixed-local@4")
    root = derive_root_key(11)
    with pytest.raises(MixedStrategyError):
        derive_deck_seed(root, "mixed-local@4")
    with pytest.raises(MixedStrategyError):
        derive_bots_key(root, "mixed-local@4")


def test_omitted_identifier_stays_on_the_first_version() -> None:
    """省略身份时必须等价于首版，避免旧调用被静默换版。"""
    root = derive_root_key(11)
    assert derive_deck_seed(root) == derive_deck_seed(root, MIXED_STRATEGY_IDENTIFIER)
    assert derive_bots_key(root) == derive_bots_key(root, MIXED_STRATEGY_IDENTIFIER)


def test_versions_do_not_share_random_streams() -> None:
    """两个身份的牌堆派生与 Bot 派生流必须互不相同。"""
    root = derive_root_key(11)
    assert derive_deck_seed(root, MIXED_STRATEGY_IDENTIFIER_V2) != derive_deck_seed(root)
    assert derive_bots_key(root, MIXED_STRATEGY_IDENTIFIER_V2) != derive_bots_key(root)
