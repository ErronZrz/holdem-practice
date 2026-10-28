"""第二十版身份的回归：可见踢脚、四张同花面小同花、面对下注的强牌加分，以及旧身份隔离。

只比较可复现局面上的动作单位。不把这些读数写成质量结论。
"""

from __future__ import annotations

from dataclasses import replace

from app.analysis.hand_review import build_review
from app.analysis.reference_identity import EVALUATION_VERSION, REFERENCE_VERSION
from app.api.schemas import CreateGameRequest
from app.llm.coach import PROMPT_SCHEMA_VERSION
from app.poker.cards import card_from_str
from app.poker.evaluator import evaluate_fast
from app.strategy.mixed_features import (
    _top_pair_board_pair_base,
    _visible_top_pair_board_pair_base,
    _weak_board_flush_base,
)
from app.strategy.mixed_policy import (
    _NUT_BASE,
    _STRONG_VALUE_BONUS,
    MIXED_LOCAL_V19_RULES,
    MIXED_LOCAL_V20_RULES,
    HandMode,
    MixedStyle,
    _checked_value_floor,
    _skips_unqualified_value_bonus,
    _with_effective_base,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V19,
    MIXED_STRATEGY_IDENTIFIER_V20,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.registry import create_strategy, observation_entry, spec_for
from app.verification.config import BASELINE_IDENTIFIER, UNDER_TEST_IDENTIFIERS
from tools.diagnose_bot_hand import _explain

from .mixed_bot_judgment import opportunity_reading
from .mixed_bot_states import apply_node, build_frozen_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, _node_rows, config_digest, frozen_manifest
from .test_mixed_v19_caliber import _at_human_decision, _history, _mass, _rows

_NINETEENTH_CONFIG_DIGEST = (
    "b57673c98fc0610ca89c6a3024044ff6ab4839d0dc306944cce7d2e17478f494"
)
_TWENTIETH_CONFIG_DIGEST = (
    "ed1cf0daec2a6c52271d2065d92b983c7d4fd63bf3b3f1ef00d3d7c28d25dded"
)
_RAISE_HAND = "4a6b73f3"
_FLUSH_HAND = "49663d50"
_TURN_PAIR_HAND = "83e0f6b7"
_QUEEN_RIVER_HAND = "b9b4a56b"
_JACK_RIVER_HAND = "71c69750"


def _cards(labels: list[str]):
    return [card_from_str(label) for label in labels]


def _pair_views(holes: list[str], board: list[str]) -> tuple[int, int, int]:
    hole_cards = _cards(holes)
    board_cards = _cards(board)
    rank = evaluate_fast([*hole_cards, *board_cards])
    return (
        _top_pair_board_pair_base(rank, hole_cards, board_cards),
        _visible_top_pair_board_pair_base(rank, hole_cards, board_cards),
        _weak_board_flush_base(rank, hole_cards, board_cards),
    )


def test_twentieth_version_only_opens_its_switches() -> None:
    """第二十版只多三个开关；关掉后必须与第十九版逐字段相同。"""
    assert MIXED_LOCAL_V20_RULES.qualified_strong_value is True
    assert MIXED_LOCAL_V20_RULES.visible_pair_kicker is True
    assert MIXED_LOCAL_V20_RULES.weak_four_flush is True
    assert (
        replace(
            MIXED_LOCAL_V20_RULES,
            qualified_strong_value=False,
            visible_pair_kicker=False,
            weak_four_flush=False,
        )
        == MIXED_LOCAL_V19_RULES
    )
    for identifier in MIXED_STRATEGY_IDENTIFIERS:
        rules = rules_for_identifier(identifier)
        enabled = identifier == MIXED_STRATEGY_IDENTIFIER_V20
        assert rules.qualified_strong_value is enabled
        assert rules.visible_pair_kicker is enabled
        assert rules.weak_four_flush is enabled
        fields = DIGEST_RULE_FIELDS.get(identifier)
        if not enabled:
            assert fields is None or "qualified_strong_value" not in fields
            assert fields is None or "visible_pair_kicker" not in fields
            assert fields is None or "weak_four_flush" not in fields


def test_twentieth_is_the_create_default() -> None:
    """第二十版可构造，且未指定策略时创建对局与复盘参考都使用第二十版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    assert ordered[-1] == MIXED_STRATEGY_IDENTIFIER_V20
    assert ordered[-2] == MIXED_STRATEGY_IDENTIFIER_V19
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V20).version == 20
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V20, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V20
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V20) is MIXED_LOCAL_V20_RULES
    assert CreateGameRequest().bot_strategy == MIXED_STRATEGY_IDENTIFIER_V20
    assert "mixed-local@20" in UNDER_TEST_IDENTIFIERS
    assert BASELINE_IDENTIFIER == "heuristic@1"
    assert REFERENCE_VERSION == 9
    assert EVALUATION_VERSION == 3
    assert PROMPT_SCHEMA_VERSION == 6


def test_twentieth_digest_appends_only_its_own_fields() -> None:
    """摘要只追加第二十版自己的三个开关，第十九版摘要逐字不变。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V20][-3:] == (
        "qualified_strong_value",
        "visible_pair_kicker",
        "weak_four_flush",
    )
    assert (
        DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V20][:-3]
        == DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V19]
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V19) == _NINETEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V20) == _TWENTIETH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V20) != _NINETEENTH_CONFIG_DIGEST


def test_visible_kicker_scores_the_hole_card_and_leaves_the_old_score() -> None:
    """旧分仍按最佳五张计；可见分按手中未配对底牌计，小同花单独下调。"""
    assert _pair_views(["Kd", "4c"], ["Ks", "2c", "Tc", "6c", "6d"]) == (650, 610, 0)
    assert _pair_views(["7h", "As"], ["Jd", "Kh", "Kc", "Ad"]) == (650, 610, 0)
    assert _pair_views(["7h", "As"], ["Jd", "Kh", "Kc", "Ad", "2d"]) == (650, 610, 0)
    assert _pair_views(["As", "Qh"], ["8h", "9s", "Ah", "Ks", "9c"]) == (650, 690, 0)
    assert _pair_views(["Kd", "Jc"], ["Qd", "8s", "3h", "3d", "Kh"]) == (650, 690, 0)
    assert _pair_views(["Ah", "7d"], ["Ad", "2c", "2d"]) == (610, 610, 0)
    assert _pair_views(["2d", "2h"], ["7d", "Td", "2c", "Qd", "6d"]) == (0, 0, 640)
    queen = _pair_views(["Qd", "2h"], ["7d", "Td", "2c", "9d", "6d"])
    assert queen[2] == 0


def test_case_hands_follow_the_new_reference_modes() -> None:
    """病灶手的参考众数分别收成跟注、过牌，该留下的下注仍是下注。"""
    expected = {
        _RAISE_HAND: (6, "call"),
        _FLUSH_HAND: (3, "check"),
        _QUEEN_RIVER_HAND: (3, "check"),
    }
    turn = build_review(_history(_TURN_PAIR_HAND))
    jack = build_review(_history(_JACK_RIVER_HAND))
    assert turn["reference_version"] == 9
    assert turn["decisions"][2]["bot_action"]["action"] == "bet"
    assert turn["decisions"][3]["bot_action"]["action"] == "check"
    assert jack["decisions"][3]["bot_action"]["action"] == "bet"
    for prefix, (index, action) in expected.items():
        review = build_review(_history(prefix))
        assert review["decisions"][index]["bot_action"]["action"] == action


def test_nineteenth_rules_keep_the_old_modes_on_the_same_nodes() -> None:
    """同一局面上，第十九版规则仍是原来的下注或加注。"""
    river = _at_human_decision(_history(_TURN_PAIR_HAND), 3)
    turn = _at_human_decision(_history(_TURN_PAIR_HAND), 2)
    facing = _at_human_decision(_history(_RAISE_HAND), 6)
    jack = _at_human_decision(_history(_JACK_RIVER_HAND), 3)
    assert _mass(_rows(MIXED_LOCAL_V19_RULES, *river), "bet") > _mass(
        _rows(MIXED_LOCAL_V19_RULES, *river), "check"
    )
    assert _mass(_rows(MIXED_LOCAL_V20_RULES, *river), "check") > _mass(
        _rows(MIXED_LOCAL_V20_RULES, *river), "bet"
    )
    assert _mass(_rows(MIXED_LOCAL_V20_RULES, *turn), "bet") > _mass(
        _rows(MIXED_LOCAL_V20_RULES, *turn), "check"
    )
    assert _mass(_rows(MIXED_LOCAL_V19_RULES, *facing), "raise") > _mass(
        _rows(MIXED_LOCAL_V19_RULES, *facing), "call"
    )
    assert _mass(_rows(MIXED_LOCAL_V20_RULES, *facing), "call") > _mass(
        _rows(MIXED_LOCAL_V20_RULES, *facing), "raise"
    )
    assert _mass(_rows(MIXED_LOCAL_V20_RULES, *jack), "bet") > _mass(
        _rows(MIXED_LOCAL_V20_RULES, *jack), "check"
    )


def test_weak_flush_and_unqualified_bonus_stay_behind_the_switch() -> None:
    """小同花下调分和没过门槛的强牌加分只在第二十版生效。"""
    features, flush_legal = _at_human_decision(_history(_FLUSH_HAND), 3)
    assert features.base == 900
    assert features.weak_board_flush_base == 640
    assert _with_effective_base(features, MIXED_LOCAL_V19_RULES).base == 900
    lowered = _with_effective_base(features, MIXED_LOCAL_V20_RULES)
    assert lowered.base == 640
    assert lowered.base < _NUT_BASE
    facing, facing_legal = _at_human_decision(_history(_RAISE_HAND), 6)
    adjusted = _with_effective_base(facing, MIXED_LOCAL_V19_RULES)
    assert adjusted.base == 760
    assert _skips_unqualified_value_bonus(adjusted, MIXED_LOCAL_V19_RULES, 0) is False
    assert _skips_unqualified_value_bonus(adjusted, MIXED_LOCAL_V20_RULES, 0) is True
    assert _skips_unqualified_value_bonus(adjusted, MIXED_LOCAL_V20_RULES, 40) is False
    nut = replace(adjusted, base=_NUT_BASE)
    assert _skips_unqualified_value_bonus(nut, MIXED_LOCAL_V20_RULES, 0) is False
    assert _STRONG_VALUE_BONUS == 160
    shown = _explain(facing, facing_legal, "tight", HandMode.NORMAL, MIXED_LOCAL_V20_RULES)
    assert shown["strong_value_hand"] is True
    assert shown["threshold_quality"] == 0
    assert shown["value_quality_after_guards"] == shown["checked_value_floor"]
    assert shown["top_pair_board_pair_visible_base"] == facing.top_pair_board_pair_visible_base
    flush_shown = _explain(features, flush_legal, "tight", HandMode.NORMAL, MIXED_LOCAL_V20_RULES)
    assert flush_shown["weak_board_flush_base"] == 640
    earlier = _explain(facing, facing_legal, "tight", HandMode.NORMAL, MIXED_LOCAL_V19_RULES)
    assert earlier["value_quality_after_guards"] == (
        earlier["checked_value_floor"] + _STRONG_VALUE_BONUS
    )
    turn_features, _legal = _at_human_decision(_history(_TURN_PAIR_HAND), 2)
    visible = _with_effective_base(turn_features, MIXED_LOCAL_V20_RULES)
    assert visible.base == 610
    assert _checked_value_floor(visible, MIXED_LOCAL_V20_RULES) == 20
    river_features, _legal = _at_human_decision(_history(_TURN_PAIR_HAND), 3)
    river = _with_effective_base(river_features, MIXED_LOCAL_V20_RULES)
    assert _checked_value_floor(river, MIXED_LOCAL_V20_RULES) == 0


def test_older_rules_do_not_move_when_the_new_switches_close() -> None:
    """关掉第二十版开关后，分布回到第十九版。"""
    closed = replace(
        MIXED_LOCAL_V20_RULES,
        qualified_strong_value=False,
        visible_pair_kicker=False,
        weak_four_flush=False,
    )
    for prefix, index in (
        (_RAISE_HAND, 6),
        (_FLUSH_HAND, 3),
        (_TURN_PAIR_HAND, 2),
        (_TURN_PAIR_HAND, 3),
        (_JACK_RIVER_HAND, 3),
    ):
        features, legal = _at_human_decision(_history(prefix), index)
        assert build_distribution(
            features, legal, MixedStyle.TIGHT, HandMode.NORMAL, closed
        ).candidates == build_distribution(
            features, legal, MixedStyle.TIGHT, HandMode.NORMAL, MIXED_LOCAL_V19_RULES
        ).candidates


def test_frozen_nodes_keep_the_opportunity_gaps() -> None:
    """机会域差值仍达标。冻结节点相对第十九版可以不同，但风格差不能塌掉。"""
    nodes = build_frozen_nodes()
    assert len(nodes) == 125
    current = observation_entry(MIXED_STRATEGY_IDENTIFIER_V20)
    previous = observation_entry(MIXED_STRATEGY_IDENTIFIER_V19)

    def matrix(identifier: str) -> list[dict]:
        manifest = frozen_manifest(
            code_identity="v20-regression",
            output_dir="not-written",
            strategy_id=identifier,
        )
        return [row.model_dump() for row in _node_rows(manifest)]

    latest = matrix(MIXED_STRATEGY_IDENTIFIER_V20)
    prior = matrix(MIXED_STRATEGY_IDENTIFIER_V19)
    for left, right in zip(latest, prior, strict=True):
        assert left["node_id"] == right["node_id"]
    reading, _domains = opportunity_reading(latest)
    assert reading.entry_pairs_above >= 2
    assert reading.active_pairs_above >= 2
    assert reading.satisfied
    # 观察入口能构造，避免新身份漏登记。
    sample = apply_node(nodes[0])
    assert current.observe(sample.actor_state(), sample.legal_actions())
    assert previous.observe(sample.actor_state(), sample.legal_actions())
