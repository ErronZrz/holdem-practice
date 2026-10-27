"""第十八版身份的回归：单对加注收口、公共牌两对上的口袋对折价，以及旧身份隔离。

只比较可复现局面上的动作单位。不把这些读数写成质量结论。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

import pytest

from app.analysis.hand_review import build_review
from app.analysis.reference_identity import EVALUATION_VERSION, REFERENCE_VERSION
from app.api.schemas import CreateGameRequest
from app.llm.coach import PROMPT_SCHEMA_VERSION
from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.poker.evaluator import evaluate_fast
from app.poker.state import Street
from app.storage.hand_history import build_hand_history
from app.strategy.mixed_features import (
    MixedFeatures,
    _capped_board_two_pair,
    _postflop_base,
)
from app.strategy.mixed_policy import (
    _CAPPED_BOARD_PAIR_BASE,
    _CHECKED_VALUE_FLOOR,
    _LARGE_COMMIT_PENALTY,
    _THIN_VALUE_BASE,
    MIXED_LOCAL_V17_RULES,
    MIXED_LOCAL_V18_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    _checked_defense_bonus,
    _checked_value_floor,
    _close_facing_pair_raise,
    _large_commit_penalty,
    _protection_budget,
    _with_effective_base,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V17,
    MIXED_STRATEGY_IDENTIFIER_V18,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.registry import create_strategy, observation_entry, spec_for
from app.verification.config import BASELINE_IDENTIFIER, UNDER_TEST_IDENTIFIERS
from tools.diagnose_bot_hand import diagnose_history
from tools.diagnose_review import _score_features, connect_readonly, load_history

from .mixed_bot_judgment import opportunity_reading
from .mixed_bot_states import apply_node, build_frozen_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, _node_rows, config_digest, frozen_manifest

_SEVENTEENTH_CONFIG_DIGEST = (
    "d2516f80702f8b951b6b118fd3905b87518a1fae25084d1cddc60f0c558dc07c"
)
_EIGHTEENTH_CONFIG_DIGEST = (
    "07b3d17f49f3beb650e6ff1cd77a4c9e7cf16d5b0c555f3a50807b6aba3710ca"
)
_FACING_RAISE_HAND = "9bd5aa4b84aa4b54bc8b69745531f5dd"
_DOUBLE_BOARD_HAND = "0e2b3825283c4c938b967582ea32d2fe"
_SINGLE_BOARD_HAND = "b08831e06de443159b779779e99d32b5"
_MODE_WEIGHT = {HandMode.NORMAL: 80, HandMode.CAUTIOUS: 10, HandMode.PRESSED: 10}
_UNMOVED_DOMAINS = frozenset({"unopened-open", "flop-draw"})


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
        "base": 690,
        "draw": 0,
        "position": 20,
        "texture": 0,
        "contenders": 1,
        "live_opponents": 1,
        "recent_aggression": 1,
        "limpers": 0,
        "price": 400,
        "eligible_pot": 400,
        "actual_call": 200,
        "pot": 400,
        "effective_stack": 1800,
        "big_blind": 20,
        "stack": 1800,
        "street_bet": 0,
        "preflop_unraised": False,
        "hole_ranks": (12, 7),
        "seat_count": 2,
    }
    payload.update(overrides)
    return MixedFeatures(**payload)  # type: ignore[arg-type]


def _facing() -> LegalActions:
    return _legal(
        can_fold=True,
        can_call=True,
        call_amount=200,
        actual_call_amount=200,
        can_raise=True,
        min_raise_to=400,
        max_raise_to=1800,
    )


def _open() -> LegalActions:
    return _legal(can_check=True, can_bet=True, min_bet=20, max_bet=1800)


def _rows(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    *,
    style: MixedStyle = MixedStyle.AGGRESSIVE,
    mode: HandMode = HandMode.NORMAL,
) -> tuple[tuple[str, int, int], ...]:
    distribution = build_distribution(features, legal, style, mode, rules)
    return tuple((item.action.value, item.amount, item.units) for item in distribution.candidates)


def _active_units(rows: tuple[tuple[str, int, int], ...]) -> int:
    return sum(units for name, _amount, units in rows if name in {"bet", "raise"})


def _marginal(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    *,
    style: MixedStyle,
) -> dict[str, float]:
    totals: dict[str, int] = defaultdict(int)
    for mode, weight in _MODE_WEIGHT.items():
        for action, _amount, units in _rows(rules, features, legal, style=style, mode=mode):
            totals[action] += units * weight
    return {action: round(units / 1_000_000, 2) for action, units in totals.items()}


def _decision_percent(decision: dict) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in decision["marginal_80_10_10"]:
        totals[row["action"]] += float(row["pct"])
    return {action: round(value, 2) for action, value in totals.items()}


def _history(hand_id: str) -> dict:
    connection = connect_readonly()
    try:
        history = load_history(connection, hand_id)
    finally:
        connection.close()
    assert history is not None
    return history


def test_eighteenth_version_only_opens_its_switch() -> None:
    """第十八版只多一个开关；关掉后必须与第十七版逐字段相同。"""
    assert MIXED_LOCAL_V18_RULES.postflop_pair_caliber is True
    assert replace(MIXED_LOCAL_V18_RULES, postflop_pair_caliber=False) == MIXED_LOCAL_V17_RULES
    for identifier in MIXED_STRATEGY_IDENTIFIERS:
        enabled = identifier == MIXED_STRATEGY_IDENTIFIER_V18
        assert rules_for_identifier(identifier).postflop_pair_caliber is enabled
        fields = DIGEST_RULE_FIELDS.get(identifier)
        if identifier != MIXED_STRATEGY_IDENTIFIER_V18:
            assert fields is None or "postflop_pair_caliber" not in fields


def test_eighteenth_is_the_create_default() -> None:
    """第十八版可构造，且未指定策略时创建对局使用第十八版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    assert ordered[-1] == MIXED_STRATEGY_IDENTIFIER_V18
    assert ordered[-2] == MIXED_STRATEGY_IDENTIFIER_V17
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V18).version == 18
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V18, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V18
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V18) is MIXED_LOCAL_V18_RULES
    assert CreateGameRequest().bot_strategy == MIXED_STRATEGY_IDENTIFIER_V18
    assert "mixed-local@18" in UNDER_TEST_IDENTIFIERS
    assert BASELINE_IDENTIFIER == "heuristic@1"
    assert REFERENCE_VERSION == 7
    assert EVALUATION_VERSION == 3
    assert PROMPT_SCHEMA_VERSION == 5


def test_eighteenth_digest_appends_only_its_own_field() -> None:
    """摘要只追加第十八版自己的开关，第十七版摘要逐字不变。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V18][-1] == "postflop_pair_caliber"
    assert (
        DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V18][:-1]
        == DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V17]
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V17) == _SEVENTEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V18) == _EIGHTEENTH_CONFIG_DIGEST


def test_facing_pair_raise_closes_only_the_aggressive_band() -> None:
    """面对下注的单对收口只打在激进型、翻后、基础分低于两对高档的区间。"""
    pair = _features()
    legal = _facing()
    previous = _rows(MIXED_LOCAL_V17_RULES, pair, legal)
    current = _rows(MIXED_LOCAL_V18_RULES, pair, legal)
    assert _active_units(previous) > 0
    assert _active_units(current) == 0
    assert _close_facing_pair_raise(pair, MIXED_LOCAL_V18_RULES, MixedStyle.AGGRESSIVE, 10, 4) == (
        0,
        0,
    )
    kept = _close_facing_pair_raise(
        replace(pair, draw=48), MIXED_LOCAL_V18_RULES, MixedStyle.AGGRESSIVE, 10, 4
    )
    assert kept == (0, 4)
    below = _close_facing_pair_raise(
        replace(pair, base=_CHECKED_VALUE_FLOOR - 1),
        MIXED_LOCAL_V18_RULES,
        MixedStyle.AGGRESSIVE,
        10,
        4,
    )
    assert below == (0, 4)
    assert _close_facing_pair_raise(
        replace(pair, base=_THIN_VALUE_BASE),
        MIXED_LOCAL_V18_RULES,
        MixedStyle.AGGRESSIVE,
        10,
        4,
    ) == (10, 4)

    drawn = replace(pair, draw=48, hole_ranks=(14, 13))
    assert _active_units(_rows(MIXED_LOCAL_V18_RULES, drawn, legal)) > 0
    assert _rows(MIXED_LOCAL_V18_RULES, replace(pair, actual_call=0), _open()) == _rows(
        MIXED_LOCAL_V17_RULES, replace(pair, actual_call=0), _open()
    )
    strong = replace(pair, base=800, hole_ranks=(14, 14))
    assert _rows(MIXED_LOCAL_V18_RULES, strong, legal) == _rows(
        MIXED_LOCAL_V17_RULES, strong, legal
    )
    preflop = replace(pair, street=Street.PREFLOP, preflop_unraised=False)
    assert _rows(MIXED_LOCAL_V18_RULES, preflop, legal) == _rows(
        MIXED_LOCAL_V17_RULES, preflop, legal
    )
    for style in (MixedStyle.TIGHT, MixedStyle.CALLING):
        assert _marginal(MIXED_LOCAL_V18_RULES, pair, legal, style=style) == _marginal(
            MIXED_LOCAL_V17_RULES, pair, legal, style=style
        )
    aggressive = _marginal(MIXED_LOCAL_V18_RULES, pair, legal, style=MixedStyle.AGGRESSIVE)
    assert aggressive.get("raise", 0.0) == 0.0
    assert aggressive.get("bet", 0.0) == 0.0
    assert aggressive["call"] == 100.0


def test_case_hand_stops_raising_the_pair_but_keeps_the_open_bet() -> None:
    """实战翻牌面对加注不再加注；同一手无人下注时的主动下注保持原分布。"""
    history = _history(_FACING_RAISE_HAND)
    current = diagnose_history(history, hand_id=_FACING_RAISE_HAND, identity="mixed-local@18")
    previous = diagnose_history(history, hand_id=_FACING_RAISE_HAND, identity="mixed-local@17")

    def facing(report: dict) -> dict:
        return next(
            item
            for item in report["decisions"]
            if item["seat"] == 5
            and item["street"] == "flop"
            and item["features"]["actual_call"] == 290
        )

    def opening(report: dict) -> dict:
        return next(
            item
            for item in report["decisions"]
            if item["seat"] == 5
            and item["street"] == "flop"
            and item["features"]["actual_call"] == 0
        )

    after = facing(current)
    before = facing(previous)
    assert after["style"] == "aggressive"
    assert after["features"]["base"] == 690
    assert _decision_percent(before)["raise"] == pytest.approx(81.22, abs=0.05)
    assert _decision_percent(after) == {"call": 100.0}
    assert all(mode["value_quality_after_guards"] == 0 for mode in after["modes"])
    assert all(mode["pair_raise_applies"] for mode in after["modes"])
    assert _decision_percent(opening(current)) == _decision_percent(opening(previous))
    assert opening(current)["marginal_80_10_10"]
    assert not opening(current)["modes"][0]["pair_raise_applies"]


def test_shared_base_stays_put_when_the_marker_is_only_a_flag() -> None:
    """公共牌两对只附加标记；共用基础分函数的返回值不变，单公对不标记。"""
    tens = [card_from_str(label) for label in ("Td", "Tc")]
    double_board = [card_from_str(label) for label in ("As", "9c", "Qs", "Ah", "9d")]
    double_rank = evaluate_fast([*tens, *double_board])
    assert _postflop_base(double_rank, tens, double_board) == 600
    assert _capped_board_two_pair(double_rank, tens, double_board) is True

    jacks = [card_from_str(label) for label in ("Js", "Jh")]
    single_board = [card_from_str(label) for label in ("As", "Ad", "6c")]
    single_rank = evaluate_fast([*jacks, *single_board])
    assert _postflop_base(single_rank, jacks, single_board) == 600
    assert _capped_board_two_pair(single_rank, jacks, single_board) is False

    aces = [card_from_str(label) for label in ("As", "Ad")]
    lower_board = [card_from_str(label) for label in ("9s", "9c", "7h", "7d", "Qh")]
    higher_rank = evaluate_fast([*aces, *lower_board])
    assert _capped_board_two_pair(higher_rank, aces, lower_board) is False

    deuces = [card_from_str(label) for label in ("2s", "2d")]
    played_by_board = evaluate_fast([*deuces, *double_board])
    assert _capped_board_two_pair(played_by_board, deuces, double_board) is False


def test_capped_board_pair_rewrites_base_before_the_gates() -> None:
    """开关打开时基础分先记成 400，再进入评分、托底、承诺、保护和过牌后跟注。"""
    raw = _features(
        street=Street.RIVER,
        base=600,
        capped_board_two_pair=True,
        actual_call=400,
        price=600,
        contenders=3,
        live_opponents=3,
        stack=700,
        effective_stack=700,
        pot=800,
        hole_ranks=(10, 10),
        recent_aggression=1,
    )
    assert _with_effective_base(raw, MIXED_LOCAL_V17_RULES).base == 600
    adjusted = _with_effective_base(raw, MIXED_LOCAL_V18_RULES)
    assert adjusted.base == _CAPPED_BOARD_PAIR_BASE
    assert _large_commit_penalty(raw, MIXED_LOCAL_V18_RULES) == 0
    assert _large_commit_penalty(adjusted, MIXED_LOCAL_V18_RULES) == _LARGE_COMMIT_PENALTY
    assert _checked_value_floor(replace(adjusted, actual_call=0), MIXED_LOCAL_V18_RULES) == 0
    assert _protection_budget(adjusted, MIXED_LOCAL_V18_RULES) == 0
    defended = replace(adjusted, actor_checks=1, price=200, contenders=1, recent_aggression=1)
    assert _checked_defense_bonus(defended, MIXED_LOCAL_V18_RULES) > 0
    plain = replace(raw, base=_CAPPED_BOARD_PAIR_BASE, capped_board_two_pair=False)
    assert _rows(MIXED_LOCAL_V18_RULES, raw, _facing()) == _rows(
        MIXED_LOCAL_V18_RULES, plain, _facing()
    )
    scored = _score_features(raw, MixedStyle.AGGRESSIVE, MIXED_LOCAL_V18_RULES)
    earlier = _score_features(raw, MixedStyle.AGGRESSIVE, MIXED_LOCAL_V17_RULES)
    assert scored["base"] == 400
    assert scored["capped_board_two_pair"] is True
    assert scored["pair_raise_applies"] is True
    assert earlier["base"] == 600
    assert earlier["pair_raise_applies"] is False
    assert scored["score"] == earlier["score"] - 200


def test_double_board_pair_case_folds_more_and_single_board_pair_stays() -> None:
    """双公对口袋对在河牌把基础分记到 400；同一手单公对，以及另一手单公对，分布不变。"""
    double = _history(_DOUBLE_BOARD_HAND)
    current = diagnose_history(double, hand_id=_DOUBLE_BOARD_HAND, identity="mixed-local@18")
    previous = diagnose_history(double, hand_id=_DOUBLE_BOARD_HAND, identity="mixed-local@17")

    def river(report: dict) -> dict:
        return next(
            item
            for item in report["decisions"]
            if item["street"] == "river" and item["hole_cards"] == ["Td", "Tc"]
        )

    def turn(report: dict) -> dict:
        return next(
            item
            for item in report["decisions"]
            if item["street"] == "turn"
            and item["seat"] == 5
            and item["hole_cards"] == ["Td", "Tc"]
        )

    after = river(current)
    before = river(previous)
    assert after["features"]["capped_board_two_pair"] is True
    assert before["features"]["capped_board_two_pair"] is True
    assert after["features"]["base"] == 400
    assert before["features"]["base"] == 600
    assert _decision_percent(before)["call"] == pytest.approx(80.86, abs=0.05)
    assert _decision_percent(after)["call"] == pytest.approx(17.46, abs=0.05)
    assert _decision_percent(after)["fold"] == pytest.approx(82.54, abs=0.05)
    assert _decision_percent(turn(current)) == _decision_percent(turn(previous))
    assert turn(current)["features"]["base"] == 600
    assert turn(current)["features"]["capped_board_two_pair"] is False

    single = _history(_SINGLE_BOARD_HAND)
    now = diagnose_history(single, hand_id=_SINGLE_BOARD_HAND, identity="mixed-local@18")
    then = diagnose_history(single, hand_id=_SINGLE_BOARD_HAND, identity="mixed-local@17")
    assert [item["marginal_80_10_10"] for item in now["decisions"]] == [
        item["marginal_80_10_10"] for item in then["decisions"]
    ]
    jacks = next(
        item
        for item in now["decisions"]
        if item["street"] == "flop" and item["hole_cards"] == ["Jh", "Jd"]
    )
    queens = next(
        item
        for item in now["decisions"]
        if item["hole_cards"] == ["Qc", "Qh"] and item["features"]["actual_call"] == 330
    )
    assert jacks["features"]["base"] == 600
    assert jacks["features"]["capped_board_two_pair"] is False
    assert _decision_percent(jacks)["bet"] == pytest.approx(82.82, abs=0.05)
    assert queens["features"]["actual_call"] == 330
    assert _decision_percent(queens)["call"] == pytest.approx(99.78, abs=0.05)


def test_frozen_nodes_keep_the_two_opportunity_domains() -> None:
    """一百二十五个冻结节点的两个机会域与第十七版逐位相同，风格差值仍达标。"""
    nodes = build_frozen_nodes()
    assert len(nodes) == 125
    current = observation_entry(MIXED_STRATEGY_IDENTIFIER_V18)
    previous = observation_entry(MIXED_STRATEGY_IDENTIFIER_V17)
    for node in nodes:
        applied = apply_node(node)
        state = applied.actor_state()
        legal = applied.legal_actions()
        assert current.observe(state, legal).candidates == previous.observe(state, legal).candidates

    def matrix(identifier: str) -> list[dict]:
        manifest = frozen_manifest(
            code_identity="v18-regression",
            output_dir="not-written",
            strategy_id=identifier,
        )
        return [row.model_dump() for row in _node_rows(manifest)]

    latest = matrix(MIXED_STRATEGY_IDENTIFIER_V18)
    prior = matrix(MIXED_STRATEGY_IDENTIFIER_V17)
    moved: set[tuple[str, str]] = set()
    for left, right in zip(latest, prior, strict=True):
        assert left["node_id"] == right["node_id"]
        assert left["style"] == right["style"]
        if left["category"] in _UNMOVED_DOMAINS:
            assert left["action_units"] == right["action_units"]
        elif left["action_units"] != right["action_units"]:
            moved.add((left["node_id"], left["style"]))
            assert left["style"] == MixedStyle.AGGRESSIVE.value
    assert len(moved) == 17
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
    assert reviews[0]["reference_version"] == 7
    first = reviews[0]["decisions"]
    for review in reviews[1:]:
        assert review["hand_number"] != reviews[0]["hand_number"]
        for left, right in zip(first, review["decisions"], strict=True):
            assert left["bot_action"] == right["bot_action"]
            assert left["bot_distribution"] == right["bot_distribution"]
