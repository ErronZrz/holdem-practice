"""包外配对推进：两臂各用独立引擎打完一手，再交给校验器核对终局。

本模块可以创建引擎并提交行动。校验器本身不推进牌局，只消费这里交出的终局记录。
"""

from __future__ import annotations

from collections.abc import Sequence

from app.poker.actions import Action
from app.poker.cards import Card
from app.poker.engine import PokerEngine
from app.verification.structure_checks import (
    ArmTerminal,
    PairingTranscript,
    require_pairing_transcript,
)


class PairingPlayError(Exception):
    """脚本没有把这一手打到终局，或终局之后仍有多余行动。"""


def play_paired_hand(
    *,
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    button: int,
    probed_seat: int,
    hole_cards: dict[int, list[Card]],
    board: list[Card],
    measured_actions: Sequence[Action],
    baseline_actions: Sequence[Action],
    seed: int,
) -> int:
    """用同一份发牌分别打完两臂，返回被测座位的两臂净差。"""
    measured = _play_arm(
        num_players=num_players,
        starting_stack=starting_stack,
        small_blind=small_blind,
        big_blind=big_blind,
        button=button,
        hole_cards=hole_cards,
        board=board,
        actions=measured_actions,
        seed=seed,
    )
    baseline = _play_arm(
        num_players=num_players,
        starting_stack=starting_stack,
        small_blind=small_blind,
        big_blind=big_blind,
        button=button,
        hole_cards=hole_cards,
        board=board,
        actions=baseline_actions,
        seed=seed,
    )
    transcript = PairingTranscript(
        num_players=num_players,
        starting_stack=starting_stack,
        probed_seat=probed_seat,
        measured=measured,
        baseline=baseline,
    )
    return require_pairing_transcript(transcript)


def _play_arm(
    *,
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    button: int,
    hole_cards: dict[int, list[Card]],
    board: list[Card],
    actions: Sequence[Action],
    seed: int,
) -> ArmTerminal:
    engine = PokerEngine(
        num_players,
        small_blind=small_blind,
        big_blind=big_blind,
        starting_stack=starting_stack,
        seed=seed,
    )
    opening = tuple(player.stack for player in engine.players)
    engine.start_hand_with(button=button, hole_cards=hole_cards, board=list(board))
    for action in actions:
        if engine.hand_over:
            raise PairingPlayError("终局之后不能再提交行动")
        engine.apply_action(action)
    if not engine.hand_over:
        raise PairingPlayError("行动脚本结束时这一手尚未终局")
    terminal = tuple(player.stack for player in engine.players)
    return ArmTerminal(
        opening_stacks=opening,
        terminal_stacks=terminal,
        deal_cards=_deal_cards(hole_cards, board, num_players),
    )


def _deal_cards(
    hole_cards: dict[int, list[Card]], board: Sequence[Card], num_players: int
) -> tuple[str, ...]:
    cards: list[str] = []
    for seat in range(num_players):
        cards.extend(str(card) for card in hole_cards[seat])
    cards.extend(str(card) for card in board)
    return tuple(cards)
