"""包外两臂推进：同一发牌、开手重置，以及终局净差可被核对。"""

from __future__ import annotations

import pytest

from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str
from tools.pairing_harness import PairingPlayError, play_paired_hand


def _holes() -> dict[int, list]:
    return {
        0: [card_from_str("As"), card_from_str("Kh")],
        1: [card_from_str("Qd"), card_from_str("Jc")],
    }


def test_same_line_has_zero_difference_and_reset_stacks() -> None:
    difference = play_paired_hand(
        num_players=2,
        starting_stack=200,
        small_blind=1,
        big_blind=2,
        button=0,
        probed_seat=0,
        hole_cards=_holes(),
        board=[],
        measured_actions=(Action(ActionType.FOLD),),
        baseline_actions=(Action(ActionType.FOLD),),
        seed=11,
    )
    assert difference == 0


def test_different_lines_stay_inside_the_derived_bound() -> None:
    difference = play_paired_hand(
        num_players=2,
        starting_stack=200,
        small_blind=1,
        big_blind=2,
        button=0,
        probed_seat=0,
        hole_cards=_holes(),
        board=[],
        measured_actions=(Action(ActionType.FOLD),),
        baseline_actions=(Action(ActionType.RAISE, 4), Action(ActionType.FOLD)),
        seed=11,
    )
    assert difference == -3
    assert abs(difference) <= 2 * 200


def test_unfinished_script_stops() -> None:
    with pytest.raises(PairingPlayError):
        play_paired_hand(
            num_players=2,
            starting_stack=200,
            small_blind=1,
            big_blind=2,
            button=0,
            probed_seat=0,
            hole_cards=_holes(),
            board=[],
            measured_actions=(),
            baseline_actions=(Action(ActionType.FOLD),),
            seed=11,
        )
