"""新 Bot 安全输入的回归：摘要增量维护、一致性校验与显式失败。

本文件只做有界单元/集成回归：不跑性能矩阵、不跑对抗对局、不访问真实库。
"""

import pytest
from pydantic import ValidationError

from app.poker.actions import Action, ActionType
from app.poker.engine import PokerEngine
from app.poker.state import Street
from app.strategy.mixed_context import (
    MIXED_CONTEXT_SCHEMA_VERSION,
    MIXED_SUMMARY_STREETS,
    MixedContext,
    MixedContextError,
    MixedStreetSummary,
    MixedSummaryTracker,
    mixed_state,
    require_mixed_input,
)
from app.strategy.projection import project_for_actor

from .helpers import cards


def _zero_summary(street: Street, size: int = 3) -> MixedStreetSummary:
    return MixedStreetSummary(
        street=street,
        counts_by_seat=tuple((0, 0, 0, 0, 0) for _ in range(size)),
        paid_by_seat=tuple(0 for _ in range(size)),
    )


def _context(size: int = 3, **overrides: object) -> MixedContext:
    payload: dict[str, object] = {
        "hand_number": 1,
        "event_count": 2,
        "small_blind": 5,
        "big_blind": 10,
        "bot_seats": tuple(range(1, size)),
        "streets": tuple(_zero_summary(street, size) for street in MIXED_SUMMARY_STREETS),
    }
    payload.update(overrides)
    return MixedContext(**payload)


def _tracker_engine(
    num_players: int = 3,
    stacks: int = 1000,
) -> tuple[PokerEngine, MixedSummaryTracker]:
    engine = PokerEngine(num_players, 5, 10, stacks, seed=7)
    engine.start_hand()
    tracker = MixedSummaryTracker()
    tracker.begin_hand(
        hand_number=1,
        num_players=num_players,
        small_blind=5,
        big_blind=10,
        bot_seats=tuple(range(1, num_players)),
        history=engine.history,
    )
    return engine, tracker


# ------------------------------------------------------------------ 模型约束


def test_schema_version_is_frozen() -> None:
    assert MIXED_CONTEXT_SCHEMA_VERSION == "mixed-context.v1"
    assert _context().schema_version == "mixed-context.v1"
    assert _context().num_players == 3


def test_context_rejects_unregistered_fields() -> None:
    with pytest.raises(ValidationError):
        _context(seed=1)


def test_context_is_frozen() -> None:
    context = _context()
    with pytest.raises(ValidationError):
        context.hand_number = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "overrides",
    [
        {"hand_number": 0},
        {"event_count": 1},
        {"small_blind": 0},
        {"big_blind": 15},
        {"bot_seats": (2, 1)},
        {"bot_seats": (1, 1)},
        {"bot_seats": (1, 9)},
        {"streets": tuple(_zero_summary(street, 3) for street in MIXED_SUMMARY_STREETS[:3])},
        {
            "streets": (
                _zero_summary(Street.FLOP, 3),
                _zero_summary(Street.PREFLOP, 3),
                _zero_summary(Street.TURN, 3),
                _zero_summary(Street.RIVER, 3),
            )
        },
        {
            "streets": (
                _zero_summary(Street.PREFLOP, 3),
                _zero_summary(Street.FLOP, 4),
                _zero_summary(Street.TURN, 3),
                _zero_summary(Street.RIVER, 3),
            )
        },
    ],
)
def test_context_rejects_inconsistent_hands(overrides: dict[str, object]) -> None:
    with pytest.raises((ValidationError, MixedContextError)):
        _context(**overrides)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"counts_by_seat": ((0, 0, 0, 0),)},
        {"counts_by_seat": ((-1, 0, 0, 0, 0),)},
        {"counts_by_seat": ((9, 0, 0, 0, 0),)},
        {"paid_by_seat": (-1,)},
        {"last_aggressor": 7},
        {"preopen_callers": (1, 0)},
    ],
)
def test_street_summary_rejects_bad_arrays(kwargs: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "street": Street.PREFLOP,
        "counts_by_seat": ((0, 0, 0, 0, 0),),
        "paid_by_seat": (0,),
    }
    payload.update(kwargs)
    with pytest.raises((ValidationError, MixedContextError)):
        MixedStreetSummary(**payload)


def test_non_preflop_street_rejects_preopen_callers() -> None:
    with pytest.raises((ValidationError, MixedContextError)):
        MixedStreetSummary(
            street=Street.FLOP,
            counts_by_seat=((0, 0, 0, 0, 0),),
            paid_by_seat=(0,),
            preopen_callers=(0,),
        )


def test_saturation_is_respected() -> None:
    summary = MixedStreetSummary(
        street=Street.FLOP,
        counts_by_seat=((3, 0, 0, 0, 0), (0, 0, 0, 0, 0)),
        paid_by_seat=(30, 0),
    )
    assert summary.counts_by_seat[0][0] == 3


# ------------------------------------------------------------------ 摘要增量维护


def test_begin_hand_consumes_two_blinds_without_voluntary_counts() -> None:
    engine, tracker = _tracker_engine()
    context = tracker.context()
    assert tracker.consumed_events == 2
    assert context.event_count == 2
    preflop = context.streets[0]
    # 盲注计入支付，不计为自愿 call / raise。
    for seat, player in enumerate(engine.players):
        assert preflop.paid_by_seat[seat] == player.total_committed
    assert all(counts == (0, 0, 0, 0, 0) for counts in preflop.counts_by_seat)
    assert preflop.last_aggressor is None
    assert preflop.preopen_callers == ()
    assert engine.history[0]["action"] == "small_blind"
    assert engine.history[1]["action"] == "big_blind"


def test_begin_hand_requires_exactly_two_blind_records() -> None:
    tracker = MixedSummaryTracker()
    with pytest.raises(MixedContextError):
        tracker.begin_hand(
            hand_number=1,
            num_players=3,
            small_blind=5,
            big_blind=10,
            bot_seats=(1, 2),
            history=[],
        )


def test_consume_requires_exactly_one_new_event() -> None:
    engine, tracker = _tracker_engine()
    with pytest.raises(MixedContextError):
        tracker.consume_after_action(engine.history)
    engine.apply_action(Action(ActionType.FOLD))
    tracker.consume_after_action(engine.history)
    assert tracker.consumed_events == 3
    with pytest.raises(MixedContextError):
        tracker.consume_after_action(engine.history)


def test_voluntary_actions_update_counts_paid_and_aggressor() -> None:
    engine, tracker = _tracker_engine()
    raiser = engine.current_seat
    engine.apply_action(Action(ActionType.RAISE, 30))
    tracker.consume_after_action(engine.history)
    caller = engine.current_seat
    engine.apply_action(Action(ActionType.CALL))
    tracker.consume_after_action(engine.history)
    preflop = tracker.context().streets[0]
    assert preflop.counts_by_seat[raiser][4] == 1
    assert preflop.last_aggressor == raiser
    assert preflop.paid_by_seat[raiser] == 30
    assert preflop.counts_by_seat[caller][2] == 1
    # 加注之后的跟注者不进入「加注前跟注」集合。
    assert preflop.preopen_callers == ()


def test_preopen_callers_capture_limpers_only() -> None:
    engine, tracker = _tracker_engine()
    first = engine.current_seat
    engine.apply_action(Action(ActionType.CALL))
    tracker.consume_after_action(engine.history)
    assert tracker.context().streets[0].preopen_callers == (first,)
    second = engine.current_seat
    engine.apply_action(Action(ActionType.CALL))
    tracker.consume_after_action(engine.history)
    assert tracker.context().streets[0].preopen_callers == tuple(sorted((first, second)))


def test_counts_saturate_but_payment_keeps_accumulating() -> None:
    tracker = MixedSummaryTracker()
    history: list[dict[str, object]] = [
        {"street": "preflop", "seat": 0, "action": "small_blind", "amount": 5},
        {"street": "preflop", "seat": 1, "action": "big_blind", "amount": 10},
    ]
    tracker.begin_hand(
        hand_number=1,
        num_players=2,
        small_blind=5,
        big_blind=10,
        bot_seats=(1,),
        history=history,
    )
    for _ in range(5):
        history.append({"street": "preflop", "seat": 0, "action": "call", "amount": 10})
        tracker.consume_after_action(history)
    preflop = tracker.context().streets[0]
    assert preflop.counts_by_seat[0][2] == 3
    assert preflop.paid_by_seat[0] == 5 + 50


def test_unknown_public_action_and_negative_amount_fail() -> None:
    tracker = MixedSummaryTracker()
    history = [
        {"street": "preflop", "seat": 0, "action": "small_blind", "amount": 5},
        {"street": "preflop", "seat": 1, "action": "big_blind", "amount": 10},
    ]
    tracker.begin_hand(
        hand_number=1,
        num_players=2,
        small_blind=5,
        big_blind=10,
        bot_seats=(1,),
        history=history,
    )
    history.append({"street": "preflop", "seat": 0, "action": "post_ante", "amount": 0})
    with pytest.raises(MixedContextError):
        tracker.consume_after_action(history)
    history[-1] = {"street": "preflop", "seat": 0, "action": "call", "amount": -1}
    with pytest.raises(MixedContextError):
        tracker.consume_after_action(history)
    history[-1] = {"street": "showdown", "seat": 0, "action": "call", "amount": 1}
    with pytest.raises(MixedContextError):
        tracker.consume_after_action(history)


def test_nonzero_amount_on_passive_action_fails() -> None:
    engine, tracker = _tracker_engine(num_players=2)
    engine.apply_action(Action(ActionType.CALL))
    tracker.consume_after_action(engine.history)
    engine.apply_action(Action(ActionType.CHECK))
    engine.history[-1]["amount"] = 3
    with pytest.raises(MixedContextError):
        tracker.consume_after_action(engine.history)


def test_tracker_reset_clears_state() -> None:
    _, tracker = _tracker_engine()
    tracker.reset()
    assert tracker.active is False
    with pytest.raises(MixedContextError):
        tracker.context()


def test_begin_hand_rejects_invalid_bot_seats() -> None:
    tracker = MixedSummaryTracker()
    history = [
        {"street": "preflop", "seat": 0, "action": "small_blind", "amount": 5},
        {"street": "preflop", "seat": 1, "action": "big_blind", "amount": 10},
    ]
    with pytest.raises(MixedContextError):
        tracker.begin_hand(
            hand_number=1,
            num_players=2,
            small_blind=5,
            big_blind=10,
            bot_seats=(1, 1),
            history=history,
        )


# ------------------------------------------------------------------ 输入校验


def test_plain_projection_is_rejected() -> None:
    engine, _ = _tracker_engine()
    with pytest.raises(MixedContextError):
        require_mixed_input(project_for_actor(engine.snapshot()))


def test_valid_state_passes_and_exposes_known_cards() -> None:
    engine, tracker = _tracker_engine()
    state = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    verified = require_mixed_input(state)
    assert verified.actor_seat == engine.current_seat
    assert verified.num_players == 3
    assert len(verified.known_cards) == 2


def test_other_seats_hole_cards_are_rejected() -> None:
    engine, tracker = _tracker_engine()
    # 直接使用未脱敏快照：其他座位底牌仍在，必须显式失败。
    state = mixed_state(engine.snapshot(), tracker.context())
    with pytest.raises(MixedContextError):
        require_mixed_input(state)


def test_mismatched_paid_is_rejected() -> None:
    engine, tracker = _tracker_engine()
    context = tracker.context()
    tampered_streets = list(context.streets)
    tampered_streets[1] = MixedStreetSummary(
        street=Street.FLOP,
        counts_by_seat=((0, 0, 0, 0, 0),) * 3,
        paid_by_seat=(1, 0, 0),
    )
    tampered = MixedContext(
        hand_number=context.hand_number,
        event_count=context.event_count,
        small_blind=context.small_blind,
        big_blind=context.big_blind,
        bot_seats=context.bot_seats,
        streets=tuple(tampered_streets),
    )
    state = mixed_state(project_for_actor(engine.snapshot()), tampered)
    with pytest.raises(MixedContextError):
        require_mixed_input(state)


def test_finished_hand_is_rejected() -> None:
    engine, tracker = _tracker_engine()
    engine.hand_over = True
    state = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    with pytest.raises(MixedContextError):
        require_mixed_input(state)


def test_folded_actor_is_rejected() -> None:
    engine, tracker = _tracker_engine()
    engine.players[engine.current_seat].folded = True
    state = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    with pytest.raises(MixedContextError):
        require_mixed_input(state)


def test_street_and_board_length_must_match() -> None:
    engine, tracker = _tracker_engine()
    engine.board = cards("2c 3d 4h")
    state = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    with pytest.raises(MixedContextError):
        require_mixed_input(state)


def test_tracker_matches_engine_commitments_over_a_real_hand() -> None:
    engine, tracker = _tracker_engine(num_players=4)
    guards = 0
    while not engine.hand_over and guards < 60:
        guards += 1
        legal = engine.legal_actions()
        action = Action(ActionType.CHECK) if legal.can_check else Action(ActionType.CALL)
        engine.apply_action(action)
        tracker.consume_after_action(engine.history)
    assert engine.hand_over
    context = tracker.context()
    for seat in range(engine.num_players):
        paid = sum(summary.paid_by_seat[seat] for summary in context.streets)
        assert paid == engine.players[seat].total_committed
