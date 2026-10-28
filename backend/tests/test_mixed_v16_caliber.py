"""第十六版身份的回归：翻前未开池后位、翻牌强听牌支撑，以及旧身份的逐位隔离。

只比较可复现局面上的动作单位与基础分。不把这些读数写成质量结论。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import tools.diagnose_review as diagnose
from app.analysis.hand_review import _guard_reference_distribution, _mode_action, build_review
from app.api.schemas import CreateGameRequest
from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.poker.state import Street
from app.strategy.distribution_observation import supported_declaration
from app.strategy.mixed_context import MixedSummaryTracker, mixed_state, require_mixed_input
from app.strategy.mixed_features import features_for
from app.strategy.mixed_policy import (
    _STRONG_PREFLOP_BASE,
    MIXED_LOCAL_V15_RULES,
    MIXED_LOCAL_V16_RULES,
    _facing_draw_support,
    _with_broadway_base,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V15,
    MIXED_STRATEGY_IDENTIFIER_V16,
    MIXED_STRATEGY_IDENTIFIER_V17,
    MIXED_STRATEGY_IDENTIFIER_V18,
    MIXED_STRATEGY_IDENTIFIER_V19,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.projection import project_for_actor
from app.strategy.registry import (
    capability_declaration,
    create_strategy,
    observation_entry,
    spec_for,
)
from app.verification.config import BASELINE_IDENTIFIER, UNDER_TEST_IDENTIFIERS

from .mixed_bot_judgment import OPPORTUNITY_MIN_PAIRS, opportunity_reading
from .mixed_bot_states import apply_node, build_frozen_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, _node_rows, config_digest, frozen_manifest

_SIXTEENTH_CONFIG_DIGEST = (
    "941f756d1cd5e5034cf757b1d211ec9d0cd06e23486f07b92bb76970a5eab2f5"
)
_FIFTEENTH_CONFIG_DIGEST = (
    "39ae4ac9c60015df78aa9ca45340ca6a0325168e0bb1e48ea27d83ec49e4cdc9"
)
_FIXTURES = Path(__file__).parent / "fixtures"
_CO_HAND = "08985a8d951045fd8224beb2e61cc6b2"
_DRAW_HAND = "1cdb17a81ae84222841ddd8aa0979d8f"
_FILLERS = (
    ("2c", "3d"),
    ("4c", "5d"),
    ("6c", "8d"),
    ("9c", "2d"),
    ("3c", "4d"),
)


def _history(hand_id: str) -> dict:
    return json.loads((_FIXTURES / f"{hand_id}.json").read_text(encoding="utf-8"))


def _raw_mode(rows: list[dict]) -> Action:
    pairs = [
        (Action(ActionType(row["action"]), int(row["amount"])), float(row["probability"]))
        for row in rows
    ]
    return _mode_action(pairs)


def _utg_features(holes: tuple[str, str]):
    """六人桌首位行动、尚未有人加注时的特征。"""
    dealt = (holes, *_FILLERS)
    engine = PokerEngine(6, 10, 20, 2000, seed=0)
    engine.start_hand_with(
        button=3,
        hole_cards={
            seat: [card_from_str(left), card_from_str(right)]
            for seat, (left, right) in enumerate(dealt)
        },
        board=[],
    )
    tracker = MixedSummaryTracker()
    tracker.begin_hand(
        hand_number=4,
        num_players=6,
        small_blind=10,
        big_blind=20,
        bot_seats=(0,),
        history=engine.history,
    )
    projected = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    return features_for(require_mixed_input(projected), engine.legal_actions())


def _can_move(features) -> bool:
    """这一版相对上一版允许改分布的局面：国王后、未开池后位，或翻牌强听牌面对下注。"""
    if features.street is Street.PREFLOP:
        high = max(features.hole_ranks)
        low = min(features.hole_ranks)
        folded = max(0, features.seat_count - 1 - features.contenders)
        late = features.preflop_unraised and features.limpers == 0 and folded > 0
        return (high == 13 and low == 12) or late
    if features.street is not Street.FLOP:
        return False
    return features.draw // 12 >= 8 and features.actual_call > 0 and features.price > 0


def test_sixteenth_version_only_adds_its_switch() -> None:
    """第十六版只打开新开关；关掉后必须与第十五版逐字段相同。"""
    assert MIXED_LOCAL_V16_RULES.late_unopened_draw_caliber is True
    assert (
        replace(MIXED_LOCAL_V16_RULES, late_unopened_draw_caliber=False)
        == MIXED_LOCAL_V15_RULES
    )
    for identifier in MIXED_STRATEGY_IDENTIFIERS:
        enabled = identifier in (
            MIXED_STRATEGY_IDENTIFIER_V16,
            MIXED_STRATEGY_IDENTIFIER_V17,
            MIXED_STRATEGY_IDENTIFIER_V18,
            MIXED_STRATEGY_IDENTIFIER_V19,
        )
        assert rules_for_identifier(identifier).late_unopened_draw_caliber is enabled


def test_sixteenth_identity_stays_registered_when_default_moves_on() -> None:
    """第十六版仍可构造；未指定策略时创建对局改用第十九版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    assert ordered[-1] == MIXED_STRATEGY_IDENTIFIER_V19
    assert ordered[-2] == MIXED_STRATEGY_IDENTIFIER_V18
    assert ordered[-3] == MIXED_STRATEGY_IDENTIFIER_V17
    assert ordered[-4] == MIXED_STRATEGY_IDENTIFIER_V16
    assert ordered[-5] == MIXED_STRATEGY_IDENTIFIER_V15
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V16).version == 16
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V16, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V16
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V16) is MIXED_LOCAL_V16_RULES
    assert CreateGameRequest().bot_strategy == "mixed-local@19"
    assert BASELINE_IDENTIFIER == "heuristic@1"
    assert "mixed-local@16" in UNDER_TEST_IDENTIFIERS
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V16) == supported_declaration()
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V16).rules is MIXED_LOCAL_V16_RULES


def test_sixteenth_digest_appends_only_its_own_field() -> None:
    """摘要只追加第十六版自己的开关，第一版到第十五版的摘要逐字不变。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V16][-1] == (
        "late_unopened_draw_caliber"
    )
    assert (
        DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V16][:-1]
        == DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V15]
    )
    assert "late_unopened_draw_caliber" not in DIGEST_RULE_FIELDS[
        MIXED_STRATEGY_IDENTIFIER_V15
    ]
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V15) == _FIFTEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V16) == _SIXTEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V16) != config_digest(
        MIXED_STRATEGY_IDENTIFIER_V15
    )


def test_king_queen_and_unopened_late_position_use_the_new_base() -> None:
    """国王后补上连张分；未开池且前位已有弃牌时恢复位置，弱牌不加分，强牌不越线。"""
    kqs = _utg_features(("Kd", "Qd"))
    assert kqs.base == 474
    assert kqs.position == -40
    assert _with_broadway_base(kqs, MIXED_LOCAL_V15_RULES).base == 474
    assert _with_broadway_base(kqs, MIXED_LOCAL_V16_RULES).base == 524
    kqo = replace(kqs, base=429)
    kjs = replace(kqs, hole_ranks=(13, 11), base=499)
    kjo = replace(kqs, hole_ranks=(13, 11), base=454)
    assert _with_broadway_base(kqo, MIXED_LOCAL_V16_RULES).base == 479
    assert _with_broadway_base(kjs, MIXED_LOCAL_V16_RULES).base == 499
    assert _with_broadway_base(kjo, MIXED_LOCAL_V16_RULES).base == 454
    assert 524 > 499
    assert 479 > 454

    # 前位两人已弃，行动者仍被旧位置分记成最前档。
    cutoff = replace(kqs, contenders=3)
    adjusted = _with_broadway_base(cutoff, MIXED_LOCAL_V16_RULES)
    assert adjusted.position == -8
    assert adjusted.base == 654
    assert _with_broadway_base(cutoff, MIXED_LOCAL_V15_RULES) is cutoff

    capped = replace(kqs, contenders=3, hole_ranks=(10, 10), base=700)
    assert _with_broadway_base(capped, MIXED_LOCAL_V16_RULES).base == _STRONG_PREFLOP_BASE - 1
    premium = replace(kqs, contenders=3, hole_ranks=(14, 14), base=820)
    assert _with_broadway_base(premium, MIXED_LOCAL_V16_RULES).base == 950
    weak = replace(kqs, contenders=3, hole_ranks=(7, 2), base=200)
    weak_adjusted = _with_broadway_base(weak, MIXED_LOCAL_V16_RULES)
    assert weak_adjusted.base == 200
    assert weak_adjusted.position == -8
    facing_raise = replace(cutoff, preflop_unraised=False)
    raised = _with_broadway_base(facing_raise, MIXED_LOCAL_V16_RULES)
    assert raised.base == 524
    assert raised.position == -40
    limped = replace(cutoff, limpers=1)
    assert _with_broadway_base(limped, MIXED_LOCAL_V16_RULES).base == 524
    assert _with_broadway_base(limped, MIXED_LOCAL_V16_RULES).position == -40


def test_flop_strong_draw_uses_two_street_support_only() -> None:
    """翻牌八张及以上补牌改支撑；四张补牌和转牌保持原公式。"""
    flop = next(
        node
        for node in build_frozen_nodes()
        if node.category == "flop-draw" and node.player_count == 2
    )
    applied = apply_node(flop)
    features = features_for(require_mixed_input(applied.actor_state()), applied.legal_actions())
    assert features.street is Street.FLOP
    assert features.draw // 12 >= 8
    assert _facing_draw_support(features, MIXED_LOCAL_V16_RULES) != _facing_draw_support(
        features, MIXED_LOCAL_V15_RULES
    )
    gutshot = replace(features, draw=48)
    assert _facing_draw_support(gutshot, MIXED_LOCAL_V16_RULES) == _facing_draw_support(
        gutshot, MIXED_LOCAL_V15_RULES
    )
    turn = replace(features, street=Street.TURN, draw=72)
    assert _facing_draw_support(turn, MIXED_LOCAL_V16_RULES) == _facing_draw_support(
        turn, MIXED_LOCAL_V15_RULES
    )


def test_earlier_frozen_nodes_stay_with_the_fifteenth_identity() -> None:
    """一百二十五个冻结节点里，只有新口径覆盖的局面相对第十五版有位移。"""
    nodes = build_frozen_nodes()
    assert len(nodes) == 125
    current = observation_entry(MIXED_STRATEGY_IDENTIFIER_V16)
    previous = observation_entry(MIXED_STRATEGY_IDENTIFIER_V15)
    moved: set[str] = set()
    for node in nodes:
        applied = apply_node(node)
        state = applied.actor_state()
        legal = applied.legal_actions()
        features = features_for(require_mixed_input(state), legal)
        left = current.observe(state, legal).candidates
        right = previous.observe(state, legal).candidates
        if left != right:
            moved.add(node.category)
            assert _can_move(features), node.node_id
    assert "unopened-open" in moved
    assert "flop-draw" in moved


def test_case_hands_publish_the_expected_modes() -> None:
    """两手案例的原始众数与复盘发布众数落到开池和跟注。"""
    cutoff = _history(_CO_HAND)
    cutoff_report = diagnose.diagnose_history(cutoff, hand_id=_CO_HAND)
    cutoff_review = build_review(cutoff)
    raw = _raw_mode(cutoff_report["decisions"][0]["raw_distribution"])
    assert (raw.type, raw.amount) == (ActionType.RAISE, 50)
    assert cutoff_report["decisions"][0]["mode"] == "raise"
    assert cutoff_report["decisions"][0]["mode_amount"] == 50
    assert cutoff_review["decisions"][0]["bot_action"] == {"action": "raise", "amount": 50}

    draw = _history(_DRAW_HAND)
    draw_report = diagnose.diagnose_history(draw, hand_id=_DRAW_HAND)
    draw_review = build_review(draw)
    assert _raw_mode(draw_report["decisions"][0]["raw_distribution"]).type is ActionType.CALL
    assert draw_review["decisions"][0]["bot_action"] == {"action": "call", "amount": 20}
    for index, amount in ((1, 110), (2, 1060)):
        assert _raw_mode(draw_report["decisions"][index]["raw_distribution"]).type is (
            ActionType.CALL
        )
        assert draw_report["decisions"][index]["mode"] == "call"
        assert draw_report["decisions"][index]["mode_amount"] == amount
        assert draw_review["decisions"][index]["bot_action"] == {
            "action": "call",
            "amount": amount,
        }
    # 诊断展示的被动分含听牌支撑，与实际分布同一条口径。
    assert [draw_report["decisions"][index]["passive_score"] for index in (1, 2)] == [
        589,
        638,
    ]


def test_positive_postflop_call_moves_fold_mass_when_the_hand_can_continue() -> None:
    """翻后跟注期望为正且具备可继续牌力时，即使探针未触发，弃牌质量也并入跟注。"""
    hole = [card_from_str("Ts"), card_from_str("As")]
    board = [card_from_str(label) for label in ("4c", "5s", "Js")]
    baseline = [
        (Action(ActionType.FOLD), 0.62),
        (Action(ActionType.CALL), 0.38),
    ]
    guarded = _guard_reference_distribution(
        baseline,
        to_call=1060,
        call_ev=12.0,
        equity=0.34,
        opponents=1,
        postflop=True,
        max_line=1,
        bad_fold=False,
        hole_cards=hole,
        board=board,
        pot=900,
    )
    assert _mode_action(guarded).type is ActionType.CALL
    assert sum(weight for action, weight in guarded if action.type is ActionType.FOLD) == 0
    air = [card_from_str("2c"), card_from_str("7d")]
    dry = [card_from_str(label) for label in ("Ah", "Kd", "9c")]
    kept = _guard_reference_distribution(
        baseline,
        to_call=400,
        call_ev=12.0,
        equity=0.2,
        opponents=1,
        postflop=True,
        max_line=1,
        bad_fold=False,
        hole_cards=air,
        board=dry,
        pot=200,
    )
    assert kept == baseline
    preflop = _guard_reference_distribution(
        baseline,
        to_call=20,
        call_ev=4.0,
        equity=0.4,
        opponents=1,
        postflop=False,
        max_line=0,
        bad_fold=False,
        hole_cards=hole,
        board=(),
        pot=30,
    )
    assert preflop == baseline


def test_unopened_and_flop_draw_style_gaps_stay_above_the_reference() -> None:
    """未开池进池与翻牌面对下注的风格差值仍达到既有配对门槛。"""
    manifest = frozen_manifest(
        code_identity="v16-regression",
        output_dir="not-written",
        strategy_id=MIXED_STRATEGY_IDENTIFIER_V16,
    )
    rows = [row.model_dump() for row in _node_rows(manifest)]
    reading, _domains = opportunity_reading(rows)
    assert reading.entry_pairs_above >= OPPORTUNITY_MIN_PAIRS
    assert reading.active_pairs_above >= OPPORTUNITY_MIN_PAIRS
    assert reading.satisfied
