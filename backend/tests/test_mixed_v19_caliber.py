"""第十九版身份的回归：短码最小加注、顶对加更低公对的有效基础分，以及旧身份隔离。

只比较可复现局面上的动作单位。不把这些读数写成质量结论。
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from app.analysis.hand_review import _history_action, _replay_action, build_review
from app.analysis.reference_identity import EVALUATION_VERSION, REFERENCE_VERSION
from app.api.schemas import CreateGameRequest
from app.llm.coach import PROMPT_SCHEMA_VERSION
from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.poker.evaluator import evaluate_fast
from app.storage.hand_history import build_hand_history
from app.strategy.mixed_context import (
    MixedSummaryTracker,
    mixed_state,
    require_mixed_input,
)
from app.strategy.mixed_features import (
    MixedFeatures,
    _postflop_base,
    _top_pair_board_pair_base,
    features_for,
)
from app.strategy.mixed_policy import (
    _CHECKED_VALUE_FLOOR,
    MIXED_LOCAL_V18_RULES,
    MIXED_LOCAL_V19_RULES,
    STYLE_PARAMETERS,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    _active_candidates,
    _checked_defense_bonus,
    _checked_value_floor,
    _close_facing_pair_raise,
    _large_commit_penalty,
    _protection_budget,
    _retains_short_stack_min_raise,
    _with_effective_base,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V18,
    MIXED_STRATEGY_IDENTIFIER_V19,
    MIXED_STRATEGY_IDENTIFIER_V20,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.projection import project_for_actor
from app.strategy.registry import create_strategy, observation_entry, spec_for
from app.verification.config import BASELINE_IDENTIFIER, UNDER_TEST_IDENTIFIERS
from tools.diagnose_bot_hand import _explain
from tools.diagnose_review import _score_features, connect_readonly

from .mixed_bot_judgment import opportunity_reading
from .mixed_bot_states import apply_node, build_frozen_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, _node_rows, config_digest, frozen_manifest

_EIGHTEENTH_CONFIG_DIGEST = (
    "07b3d17f49f3beb650e6ff1cd77a4c9e7cf16d5b0c555f3a50807b6aba3710ca"
)
_NINETEENTH_CONFIG_DIGEST = (
    "b57673c98fc0610ca89c6a3024044ff6ab4839d0dc306944cce7d2e17478f494"
)
_SHORT_HAND = "bcc103fb"
_TURN_PAIR_HAND = "83e0f6b7"
_RIVER_PAIR_HAND = "71c69750"
_UNMOVED_DOMAINS = frozenset({"unopened-open", "flop-draw"})


def _history(prefix: str) -> dict:
    connection = connect_readonly()
    try:
        rows = connection.execute(
            "SELECT id, history_json FROM hands WHERE id LIKE ?",
            (prefix + "%",),
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 1
    return json.loads(rows[0][1])


def _cards(labels: list[str]) -> list:
    return [card_from_str(label) for label in labels]


def _pair_scores(holes: list[str], board: list[str]) -> tuple[int, int]:
    hole_cards = _cards(holes)
    board_cards = _cards(board)
    rank = evaluate_fast([*hole_cards, *board_cards])
    return (
        _postflop_base(rank, hole_cards, board_cards),
        _top_pair_board_pair_base(rank, hole_cards, board_cards),
    )


def _rows(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    *,
    style: MixedStyle = MixedStyle.TIGHT,
) -> tuple[tuple[str, int, int], ...]:
    distribution = build_distribution(
        features,
        legal,
        style,
        HandMode.NORMAL,
        rules,
        trap_roll=None,
        protect_roll=None,
    )
    return tuple(
        (item.action.value, item.amount, item.units)
        for item in distribution.candidates
        if item.units
    )


def _mass(rows: tuple[tuple[str, int, int], ...], *kinds: str) -> int:
    wanted = set(kinds)
    return sum(units for name, _amount, units in rows if name in wanted)


def _at_human_decision(history: dict, index: int) -> tuple[MixedFeatures, LegalActions]:
    """重放到第 index 个真人自愿动作之前，取出当时的特征与合法动作。"""
    players = history["players"]
    human = next(player["seat"] for player in players if player.get("is_human"))
    hole_cards = {
        player["seat"]: _cards(player["hole_cards"]) for player in players
    }
    starting = {player["seat"]: player["starting_stack"] for player in players}
    board = _cards(history["board"])
    engine = PokerEngine(
        history["num_players"],
        history["small_blind"],
        history["big_blind"],
        max(starting.values()),
    )
    for seat, stack in starting.items():
        engine.players[seat].stack = stack
    engine.start_hand_with(history["button"], hole_cards, board)
    tracker = MixedSummaryTracker()
    tracker.begin_hand(
        hand_number=int(history["hand_number"]),
        num_players=history["num_players"],
        small_blind=history["small_blind"],
        big_blind=history["big_blind"],
        bot_seats=(human,),
        history=engine.history,
    )
    seen = 0
    for record in history["actions"]:
        if record["action"] in ("small_blind", "big_blind"):
            continue
        seat = int(record["seat"])
        action = _history_action(record)
        if seat == human and seen == index:
            legal = engine.legal_actions()
            projected = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
            features = features_for(require_mixed_input(projected), legal)
            return features, legal
        if seat == human:
            seen += 1
        engine.apply_action(_replay_action(engine, seat, action))
        tracker.consume_after_action(engine.history)
    raise AssertionError(f"没有第 {index} 个真人决策")


def test_nineteenth_version_only_opens_its_switches() -> None:
    """第十九版只多两个开关；关掉后必须与第十八版逐字段相同。"""
    assert MIXED_LOCAL_V19_RULES.short_stack_min_raise is True
    assert MIXED_LOCAL_V19_RULES.top_pair_board_pair_caliber is True
    assert (
        replace(
            MIXED_LOCAL_V19_RULES,
            short_stack_min_raise=False,
            top_pair_board_pair_caliber=False,
        )
        == MIXED_LOCAL_V18_RULES
    )
    for identifier in MIXED_STRATEGY_IDENTIFIERS:
        rules = rules_for_identifier(identifier)
        enabled = identifier in {
            MIXED_STRATEGY_IDENTIFIER_V19,
            MIXED_STRATEGY_IDENTIFIER_V20,
        }
        assert rules.short_stack_min_raise is enabled
        assert rules.top_pair_board_pair_caliber is enabled
        fields = DIGEST_RULE_FIELDS.get(identifier)
        if not enabled:
            assert fields is None or "short_stack_min_raise" not in fields
            assert fields is None or "top_pair_board_pair_caliber" not in fields


def test_nineteenth_is_the_create_default() -> None:
    """第十九版仍可构造；新建对局与复盘参考已经切到第二十版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    assert ordered[-1] == MIXED_STRATEGY_IDENTIFIER_V20
    assert ordered[-2] == MIXED_STRATEGY_IDENTIFIER_V19
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V19).version == 19
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V19, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V19
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V19) is MIXED_LOCAL_V19_RULES
    assert CreateGameRequest().bot_strategy == MIXED_STRATEGY_IDENTIFIER_V20
    assert "mixed-local@19" in UNDER_TEST_IDENTIFIERS
    assert "mixed-local@20" in UNDER_TEST_IDENTIFIERS
    assert BASELINE_IDENTIFIER == "heuristic@1"
    assert REFERENCE_VERSION == 9
    assert EVALUATION_VERSION == 3
    assert PROMPT_SCHEMA_VERSION == 6


def test_nineteenth_digest_appends_only_its_own_fields() -> None:
    """摘要只追加第十九版自己的两个开关，第十八版摘要逐字不变。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V19][-2:] == (
        "short_stack_min_raise",
        "top_pair_board_pair_caliber",
    )
    assert (
        DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V19][:-2]
        == DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V18]
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V18) == _EIGHTEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V19) == _NINETEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V19) != _EIGHTEENTH_CONFIG_DIGEST


def test_shared_two_pair_base_stays_520_for_the_board_pair_branch() -> None:
    """共用基础分仍返回 520；顶对加更低公对只写在派生特征上。"""
    assert _pair_scores(["Ah", "7d"], ["Ad", "2c", "2d"]) == (520, 610)
    assert _pair_scores(["Ah", "9d"], ["Ad", "2c", "2d"]) == (520, 650)
    assert _pair_scores(["Ah", "Jd"], ["Ad", "2c", "2d"]) == (520, 690)
    assert _pair_scores(["7h", "As"], ["Jd", "Kh", "Kc", "Ad"]) == (520, 650)
    assert _pair_scores(["Kd", "Jc"], ["Qd", "8s", "3h", "3d", "Kh"]) == (520, 650)
    assert _pair_scores(["7c", "2d"], ["As", "Ad", "7h"]) == (520, 0)
    assert _pair_scores(["Qc", "2d"], ["As", "Kd", "Kc", "Qh"]) == (520, 0)
    assert _pair_scores(["Ah", "Kd"], ["As", "Kc", "2d"]) == (760, 0)


def test_top_pair_board_pair_lifts_the_effective_base_before_the_gates() -> None:
    """开关打开时先把有效基础分抬到顶对分，评分、托底和诊断展示都读这一分。"""
    features, legal = _at_human_decision(_history(_TURN_PAIR_HAND), 2)
    assert features.base == 520
    assert features.top_pair_board_pair_base == 650
    assert legal.can_bet is True
    assert _with_effective_base(features, MIXED_LOCAL_V18_RULES).base == 520
    adjusted = _with_effective_base(features, MIXED_LOCAL_V19_RULES)
    assert adjusted.base == 650
    assert adjusted.base == features.top_pair_board_pair_base
    assert _checked_value_floor(features, MIXED_LOCAL_V19_RULES) == 0
    assert _checked_value_floor(adjusted, MIXED_LOCAL_V19_RULES) > 0
    assert _checked_value_floor(adjusted, MIXED_LOCAL_V19_RULES) == min(
        adjusted.base - _CHECKED_VALUE_FLOOR, 160
    )
    low_pair = replace(features, base=520, top_pair_board_pair_base=0)
    assert _with_effective_base(low_pair, MIXED_LOCAL_V19_RULES).base == 520
    scored = _score_features(features, MixedStyle.TIGHT, MIXED_LOCAL_V19_RULES)
    earlier = _score_features(features, MixedStyle.TIGHT, MIXED_LOCAL_V18_RULES)
    assert scored["base"] == 650
    assert scored["top_pair_board_pair_base"] == 650
    assert earlier["base"] == 520
    assert earlier["top_pair_board_pair_base"] == 650
    assert scored["score"] == earlier["score"] + 130
    previous = _rows(MIXED_LOCAL_V18_RULES, features, legal)
    current = _rows(MIXED_LOCAL_V19_RULES, features, legal)
    assert _mass(previous, "check") > _mass(previous, "bet")
    assert _mass(current, "bet") > _mass(current, "check")
    assert _large_commit_penalty(adjusted, MIXED_LOCAL_V19_RULES) == _large_commit_penalty(
        replace(features, base=650), MIXED_LOCAL_V19_RULES
    )
    assert _protection_budget(adjusted, MIXED_LOCAL_V19_RULES) == _protection_budget(
        replace(features, base=650), MIXED_LOCAL_V19_RULES
    )
    defended = replace(adjusted, actor_checks=1, actual_call=40, price=40)
    assert _checked_defense_bonus(defended, MIXED_LOCAL_V19_RULES) == _checked_defense_bonus(
        replace(features, base=650, actor_checks=1, actual_call=40, price=40),
        MIXED_LOCAL_V19_RULES,
    )
    assert _close_facing_pair_raise(
        adjusted, MIXED_LOCAL_V19_RULES, MixedStyle.AGGRESSIVE, 10, 4
    ) == _close_facing_pair_raise(
        replace(features, base=650),
        MIXED_LOCAL_V19_RULES,
        MixedStyle.AGGRESSIVE,
        10,
        4,
    )


def test_case_hands_bet_the_top_pair_and_keep_the_lower_pair() -> None:
    """两处顶对加更低公对的参考众数变成下注；低对加高公对仍是 520。"""
    turn = build_review(_history(_TURN_PAIR_HAND))
    river = build_review(_history(_RIVER_PAIR_HAND))
    assert turn["reference_version"] == 9
    turn_point = turn["decisions"][2]
    river_point = river["decisions"][3]
    assert turn_point["street"] == "turn"
    assert river_point["street"] == "river"
    assert turn_point["bot_action"]["action"] == "bet"
    assert river_point["bot_action"]["action"] == "bet"
    features, legal = _at_human_decision(_history(_RIVER_PAIR_HAND), 3)
    assert features.base == 520
    assert features.top_pair_board_pair_base == 650
    previous = _rows(MIXED_LOCAL_V18_RULES, features, legal)
    current = _rows(MIXED_LOCAL_V19_RULES, features, legal)
    assert _mass(previous, "check") == 649350
    assert _mass(current, "bet") > _mass(current, "check")
    assert _pair_scores(["7c", "2d"], ["As", "Ad", "7h", "9c"]) == (520, 0)


def test_short_stack_keeps_only_the_legal_minimum_raise() -> None:
    """天顺面对短码不再是百分之百跟注；对手已全下或没有价值质量时仍不加注。"""
    features, legal = _at_human_decision(_history(_SHORT_HAND), 5)
    assert features.base == 860
    assert features.live_opponents > 0
    assert features.effective_stack > legal.call_amount
    covered = features.street_bet + features.effective_stack
    assert covered < legal.min_raise_to <= legal.max_raise_to
    previous = _rows(MIXED_LOCAL_V18_RULES, features, legal)
    current = _rows(MIXED_LOCAL_V19_RULES, features, legal)
    assert previous == (("call", 0, 1_000_000),)
    assert _mass(current, "raise") > _mass(current, "call")
    assert {amount for name, amount, _units in current if name == "raise"} == {
        legal.min_raise_to
    }
    preferences = STYLE_PARAMETERS[MixedStyle.TIGHT].size_preferences
    assert _active_candidates(
        features, legal, 785, 0, 40, preferences, MIXED_LOCAL_V19_RULES
    ) == []
    covered_call = replace(features, effective_stack=legal.call_amount)
    assert _retains_short_stack_min_raise(
        covered_call, legal, 330, MIXED_LOCAL_V19_RULES
    ) is False
    assert _active_candidates(
        covered_call, legal, 785, 330, 0, preferences, MIXED_LOCAL_V19_RULES
    ) == []
    assert _retains_short_stack_min_raise(
        features, legal, 330, MIXED_LOCAL_V18_RULES
    ) is False
    explained = _explain(features, legal, "tight", HandMode.NORMAL, MIXED_LOCAL_V19_RULES)
    closed = _explain(features, legal, "tight", HandMode.NORMAL, MIXED_LOCAL_V18_RULES)
    assert explained["short_stack_min_raise"] is True
    assert any(item["action"] == "raise" for item in explained["active_after_dangerous_filter"])
    assert closed["short_stack_min_raise"] is False
    assert closed["active_after_dangerous_filter"] == []
    review = build_review(_history(_SHORT_HAND))
    point = review["decisions"][5]
    assert point["street"] == "turn"
    assert point["bot_action"]["action"] == "raise"
    call_only = sum(
        item["probability"] for item in point["bot_distribution"] if item["action"] == "call"
    )
    assert call_only < 1


def test_frozen_nodes_keep_the_opportunity_gaps() -> None:
    """一百二十五个冻结节点与第十八版逐位相同，机会域差值仍达标。"""
    nodes = build_frozen_nodes()
    assert len(nodes) == 125
    current = observation_entry(MIXED_STRATEGY_IDENTIFIER_V19)
    previous = observation_entry(MIXED_STRATEGY_IDENTIFIER_V18)
    for node in nodes:
        applied = apply_node(node)
        state = applied.actor_state()
        legal = applied.legal_actions()
        assert current.observe(state, legal).candidates == previous.observe(
            state, legal
        ).candidates

    def matrix(identifier: str) -> list[dict]:
        manifest = frozen_manifest(
            code_identity="v19-regression",
            output_dir="not-written",
            strategy_id=identifier,
        )
        return [row.model_dump() for row in _node_rows(manifest)]

    latest = matrix(MIXED_STRATEGY_IDENTIFIER_V19)
    prior = matrix(MIXED_STRATEGY_IDENTIFIER_V18)
    for left, right in zip(latest, prior, strict=True):
        assert left["node_id"] == right["node_id"]
        assert left["action_units"] == right["action_units"]
        if left["category"] in _UNMOVED_DOMAINS:
            assert left["action_units"] == right["action_units"]
    reading, _domains = opportunity_reading(latest)
    assert reading.entry_probabilities["tight"] == pytest.approx(0.5136, abs=0.0001)
    assert reading.entry_probabilities["aggressive"] == pytest.approx(0.8581, abs=0.0001)
    assert reading.entry_probabilities["calling"] == pytest.approx(0.9776, abs=0.0001)
    assert reading.active_probabilities["tight"] == pytest.approx(0.1717, abs=0.0001)
    assert reading.active_probabilities["aggressive"] == pytest.approx(0.3429, abs=0.0001)
    assert reading.active_probabilities["calling"] == pytest.approx(0.1186, abs=0.0001)
    assert reading.active_gaps_pp["tight-calling"] == pytest.approx(5.31, abs=0.02)
    assert reading.entry_pairs_above >= 2
    assert reading.active_pairs_above >= 2
    assert reading.satisfied


def test_review_reference_ignores_the_hand_number() -> None:
    """复盘参考关闭设伏和过牌保护，只改手号时动作和分布不变。"""
    hole = {
        0: [card_from_str("Ah"), card_from_str("Kh")],
        1: [card_from_str("2c"), card_from_str("3d")],
    }
    board = [card_from_str(label) for label in ("As", "Kd", "7c", "2h", "9s")]
    moves = [(ActionType.CALL, 0), *([(ActionType.CHECK, 0)] * 7)]
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(button=1, hole_cards=hole, board=board)
    for action_type, amount in moves:
        engine.apply_action(Action(action_type, amount))
    assert engine.hand_over
    reviews = [
        build_review(build_hand_history(engine, hand_number=number, human_seat=0))
        for number in (1, 88)
    ]
    assert reviews[0]["reference_version"] == 9
    first = reviews[0]["decisions"]
    for review in reviews[1:]:
        assert review["hand_number"] != reviews[0]["hand_number"]
        for left, right in zip(first, review["decisions"], strict=True):
            assert left["bot_action"] == right["bot_action"]
            assert left["bot_distribution"] == right["bot_distribution"]


def test_older_rules_do_not_move_on_the_new_morphologies() -> None:
    """关掉第十九版开关后，短码与顶对加公对的分布回到第十八版。"""
    closed = replace(
        MIXED_LOCAL_V19_RULES,
        short_stack_min_raise=False,
        top_pair_board_pair_caliber=False,
    )
    for prefix, index in ((_SHORT_HAND, 5), (_TURN_PAIR_HAND, 2), (_RIVER_PAIR_HAND, 3)):
        features, legal = _at_human_decision(_history(prefix), index)
        assert _rows(closed, features, legal) == _rows(MIXED_LOCAL_V18_RULES, features, legal)
