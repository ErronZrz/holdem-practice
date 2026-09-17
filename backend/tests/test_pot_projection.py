"""候选 CALL 后逐池资格投影测试。"""

import pytest

from app.poker.actions import Action, ActionType
from app.poker.engine import PokerEngine
from app.poker.pot_projection import (
    PotLayerKind,
    PotParticipant,
    project_candidate_call,
)

from .helpers import cards


def _participants(*items: tuple[int, int, bool]) -> tuple[PotParticipant, ...]:
    return tuple(
        PotParticipant(seat=seat, total_committed=total_committed, folded=folded)
        for seat, total_committed, folded in items
    )


def _layer_shape(projection):
    return [
        (
            layer.lower_commitment,
            layer.upper_commitment,
            layer.amount,
            layer.contributor_seats,
            layer.eligible_seats,
            layer.caller_is_eligible,
            layer.kind,
            tuple((refund.seat, refund.amount) for refund in layer.refunds),
        )
        for layer in projection.layers
    ]


def test_projection_keeps_side_pot_layers_and_caller_recovery() -> None:
    participants = _participants((0, 80, False), (1, 60, False), (2, 30, False))

    projection = project_candidate_call(participants, caller_seat=0, actual_call_amount=20)

    assert tuple(participant.total_committed for participant in projection.participants) == (
        100,
        60,
        30,
    )
    assert _layer_shape(projection) == [
        (0, 30, 90, (0, 1, 2), (0, 1, 2), True, PotLayerKind.CONTESTED, ()),
        (30, 60, 60, (0, 1), (0, 1), True, PotLayerKind.CONTESTED, ()),
        (60, 100, 40, (0,), (0,), True, PotLayerKind.CALLER_RECOVERY, ()),
    ]
    assert sum(layer.amount for layer in projection.layers) == 190
    assert participants == _participants((0, 80, False), (1, 60, False), (2, 30, False))


def test_projection_returns_layer_without_eligible_players() -> None:
    projection = project_candidate_call(
        _participants((0, 50, True), (1, 10, False), (2, 30, False)),
        caller_seat=1,
        actual_call_amount=20,
    )

    assert _layer_shape(projection) == [
        (0, 30, 90, (0, 1, 2), (1, 2), True, PotLayerKind.CONTESTED, ()),
        (30, 50, 20, (0,), (), False, PotLayerKind.NO_ELIGIBLE_RETURN, ((0, 20),)),
    ]
    assert sum(refund.amount for refund in projection.layers[-1].refunds) == 20


def test_projection_handles_nine_players_dead_money_and_other_uncontested_layer() -> None:
    projection = project_candidate_call(
        _participants(
            (0, 5, False),
            (1, 30, False),
            (2, 20, True),
            (3, 15, False),
            (4, 10, False),
            (5, 30, True),
            (6, 5, False),
            (7, 20, False),
            (8, 0, False),
        ),
        caller_seat=0,
        actual_call_amount=10,
    )

    assert len(projection.participants) == 9
    assert projection.layers[0].contributor_seats == (0, 1, 2, 3, 4, 5, 6, 7)
    assert projection.layers[0].eligible_seats == (0, 1, 3, 4, 6, 7)
    assert projection.layers[-1].contributor_seats == (1, 5)
    assert projection.layers[-1].eligible_seats == (1,)
    assert projection.layers[-1].caller_is_eligible is False
    assert projection.layers[-1].kind is PotLayerKind.OTHER_UNCONTESTED
    assert sum(layer.amount for layer in projection.layers) == sum(
        participant.total_committed for participant in projection.participants
    )


def _short_call_with_active_opponent() -> PokerEngine:
    engine = PokerEngine(3, small_blind=5, big_blind=10, starting_stack=110, seed=0)
    engine.players[1].stack = 70
    engine.players[2].stack = 1000
    engine.start_hand_with(
        button=0,
        hole_cards={
            0: cards("As Kd"),
            1: cards("Qh Jc"),
            2: cards("9c 8d"),
        },
        board=cards("2c 7d 9h Ts 3c"),
    )
    for action in (
        Action(ActionType.CALL),
        Action(ActionType.CALL),
        Action(ActionType.CHECK),
        Action(ActionType.CHECK),
        Action(ActionType.CHECK),
        Action(ActionType.BET, 100),
    ):
        engine.apply_action(action)
    assert engine.current_seat == 1
    return engine


def _engine_signature(engine: PokerEngine) -> tuple[object, ...]:
    return (
        engine.pot,
        engine.current_seat,
        engine.current_bet,
        engine.min_raise,
        engine.street,
        engine.hand_over,
        tuple(engine.winners),
        tuple(sorted(engine.last_net.items())),
        tuple(engine.pot_results),
        tuple(sorted(engine.showdown_hands.items())),
        tuple(
            (
                player.stack,
                player.folded,
                player.all_in,
                player.street_bet,
                player.total_committed,
                player.has_acted_since_full_raise,
            )
            for player in engine.players
        ),
        tuple(tuple(sorted(record.items())) for record in engine.history),
    )


def test_engine_projection_uses_actual_short_call_without_mutation() -> None:
    engine = _short_call_with_active_opponent()
    before = _engine_signature(engine)

    projection = engine.candidate_call_pot_projection()

    assert projection is not None
    assert projection.actual_call_amount == 60
    assert tuple(participant.total_committed for participant in projection.participants) == (
        110,
        70,
        10,
    )
    assert _layer_shape(projection) == [
        (0, 10, 30, (0, 1, 2), (0, 1, 2), True, PotLayerKind.CONTESTED, ()),
        (10, 70, 120, (0, 1), (0, 1), True, PotLayerKind.CONTESTED, ()),
        (70, 110, 40, (0,), (0,), False, PotLayerKind.OTHER_UNCONTESTED, ()),
    ]
    assert _engine_signature(engine) == before

    engine.apply_action(Action(ActionType.CALL))
    assert tuple(player.total_committed for player in engine.players) == (110, 70, 10)
    assert engine.players[1].all_in is True
    assert engine.current_seat == 2


def test_engine_projection_is_none_without_legal_call() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=100, seed=0)
    engine.start_hand()
    engine.apply_action(Action(ActionType.CALL))

    assert engine.legal_actions().can_check is True
    assert engine.candidate_call_pot_projection() is None


@pytest.mark.parametrize(
    ("participants", "caller_seat", "actual_call_amount"),
    [
        (_participants((0, 10, False)), 0, 0),
        (_participants((0, 10, False), (0, 20, False)), 0, 10),
        (_participants((0, -1, False)), 0, 10),
        (_participants((0, 10, False)), 1, 10),
        (_participants((0, 10, True)), 0, 10),
    ],
)
def test_projection_rejects_invalid_public_state(
    participants: tuple[PotParticipant, ...],
    caller_seat: int,
    actual_call_amount: int,
) -> None:
    with pytest.raises(ValueError):
        project_candidate_call(participants, caller_seat, actual_call_amount)
