"""规则引擎的关键规则测试：盲注、下注、加注、全下、边池、街流转、摊牌与结算。"""

import pytest

from app.poker.actions import Action, ActionType, IllegalActionError
from app.poker.engine import PokerEngine
from app.poker.state import Street

from .helpers import cards


def _fold() -> Action:
    return Action(ActionType.FOLD)


def _check() -> Action:
    return Action(ActionType.CHECK)


def _call() -> Action:
    return Action(ActionType.CALL)


def _bet(amount: int) -> Action:
    return Action(ActionType.BET, amount)


def _raise(amount: int) -> Action:
    return Action(ActionType.RAISE, amount)


def test_blinds_heads_up() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    # 单挑时庄位是小盲。
    sb, bb = engine._blind_seats()
    assert sb == engine.button
    assert bb == (engine.button + 1) % 2
    assert engine.pot == 15
    assert engine.current_bet == 10
    assert engine.current_seat == sb
    legal = engine.legal_actions()
    assert legal.can_call and legal.can_raise and legal.can_fold
    assert not legal.can_check


def test_preflop_big_blind_option_is_raise() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    engine.apply_action(_call())  # 小盲补足到大盲
    # 大盲位已投入盲注，此时额外投入应为加注而非下注。
    assert engine.current_seat == 1
    legal = engine.legal_actions()
    assert legal.can_check
    assert legal.can_raise
    assert not legal.can_bet
    assert legal.min_raise_to == 20
    engine.apply_action(_raise(20))
    assert engine.current_bet == 20


def test_legal_action_combinations() -> None:
    # 普通玩家面对下注是「弃/跟/加」三选，无人下注时是「过牌/下注」二选；
    # 翻牌前大盲在其余人全 limp 时是「过牌/加注」特殊组合。可免费过牌时不应有弃牌。
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()

    # 翻牌前小盲面对盲注：弃 / 跟 / 加。
    la = engine.legal_actions()
    assert la.can_fold and la.can_call and la.can_raise
    assert not la.can_check and not la.can_bet

    # 翻牌前大盲面对全 limp：过牌 / 加注（无弃牌、无下注）。
    engine.apply_action(_call())
    la = engine.legal_actions()
    assert la.can_check and la.can_raise
    assert not la.can_fold and not la.can_call and not la.can_bet

    # 翻牌后无人下注：过牌 / 下注（无弃牌）。
    engine.apply_action(_check())
    la = engine.legal_actions()
    assert la.can_check and la.can_bet
    assert not la.can_fold and not la.can_call and not la.can_raise

    # 翻牌后面对下注：弃 / 跟 / 加。
    engine.apply_action(_bet(20))
    la = engine.legal_actions()
    assert la.can_fold and la.can_call and la.can_raise
    assert not la.can_check and not la.can_bet


def test_blinds_three_players_utg_first() -> None:
    engine = PokerEngine(3, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    # 庄位 0，小盲 1，大盲 2，枪口位 0 先行动。
    assert engine._blind_seats() == (1, 2)
    assert engine.current_seat == 0
    assert engine.players[1].street_bet == 5
    assert engine.players[2].street_bet == 10


def test_fold_to_big_blind_wins() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    engine.apply_action(_fold())  # 小盲弃牌
    assert engine.hand_over
    assert engine.winners == [1]  # 大盲胜
    assert engine.players[1].stack == 1000 - 10 + 15


def test_check_down_reaches_showdown() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    engine.apply_action(_call())  # 小盲补足
    engine.apply_action(_check())  # 大盲过牌
    assert engine.street == Street.FLOP
    assert len(engine.board) == 3
    engine.apply_action(_check())
    engine.apply_action(_check())
    assert engine.street == Street.TURN
    assert len(engine.board) == 4
    engine.apply_action(_check())
    engine.apply_action(_check())
    assert engine.street == Street.RIVER
    assert len(engine.board) == 5
    engine.apply_action(_check())
    engine.apply_action(_check())
    assert engine.street == Street.SHOWDOWN
    assert engine.hand_over


def test_bet_and_raise_updates_current_bet() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    engine.apply_action(_call())
    engine.apply_action(_check())
    # 翻牌圈大盲位先行动，下注 20，小盲加注到 50。
    assert engine.current_seat == 1
    engine.apply_action(_bet(20))
    assert engine.current_bet == 20
    engine.apply_action(_raise(50))
    assert engine.current_bet == 50
    engine.apply_action(_call())
    assert engine.street == Street.TURN


def test_min_raise_enforced() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    engine.apply_action(_call())
    engine.apply_action(_check())
    engine.apply_action(_bet(20))
    # 加注幅度 10 < 最小加注 20，应被拒绝。
    with pytest.raises(IllegalActionError):
        engine.apply_action(_raise(30))
    # 加注到 40 合法。
    engine.apply_action(_raise(40))
    assert engine.current_bet == 40
    assert engine.min_raise == 20


def test_all_in_runs_out_and_shows_down() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    engine.apply_action(_raise(1000))  # 小盲全下
    engine.apply_action(_call())  # 大盲跟注全下
    assert engine.hand_over
    assert engine.street == Street.SHOWDOWN
    assert len(engine.board) == 5
    assert sum(engine.players[i].stack for i in range(2)) == 2000


def test_short_call_reports_actual_payment_and_records_it() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=110, seed=0)
    engine.players[1].stack = 100
    engine.start_hand()
    engine.apply_action(_call())
    engine.apply_action(_check())
    engine.apply_action(_check())
    engine.apply_action(_bet(100))

    legal = engine.legal_actions()
    assert legal.call_amount == 100
    assert legal.actual_call_amount == 90
    assert legal.is_short_all_in_call is True
    assert legal.can_call and not legal.can_raise

    engine.apply_action(_call())

    assert engine.history[-1]["action"] == ActionType.CALL.value
    assert engine.history[-1]["amount"] == 90
    assert engine.players[1].all_in is True
    assert sum(player.stack for player in engine.players) == 210
    assert sum(engine.last_net.values()) == 0


def test_side_pot_split_and_uncalled_return() -> None:
    # 直接构造结算状态，验证边池切分与未跟注退还。
    engine = PokerEngine(3, small_blind=1, big_blind=2, starting_stack=100, seed=0)
    engine.players[0].hole_cards = cards("As Ac")
    engine.players[1].hole_cards = cards("Kh Kd")
    engine.players[2].hole_cards = cards("Qh Qd")
    engine.board = cards("2c 7d 9h Js 3c")
    engine.players[0].total_committed = 100
    engine.players[1].total_committed = 60
    engine.players[2].total_committed = 30
    for p in engine.players:
        p.stack = 0
    engine._settle_showdown()
    # 主池 90 三人争夺，边池 60 两人争夺，均为 A 对胜出；60 的未跟注退还座位 0。
    assert engine.players[0].stack == 190
    assert engine.players[1].stack == 0
    assert engine.players[2].stack == 0
    assert engine.winners == [0]


def test_side_pot_with_folded_uncalled() -> None:
    # 弃牌玩家存在未跟注超额时，该部分应退还其本人。
    engine = PokerEngine(3, small_blind=1, big_blind=2, starting_stack=100, seed=0)
    engine.players[0].hole_cards = cards("As Ac")
    engine.players[1].hole_cards = cards("Kh Kd")
    engine.players[2].hole_cards = cards("Qh Qd")
    engine.players[0].folded = True  # 座位 0 已弃牌
    engine.board = cards("2c 7d 9h Js 3c")
    engine.players[0].total_committed = 50
    engine.players[1].total_committed = 30
    engine.players[2].total_committed = 30
    for p in engine.players:
        p.stack = 0
    engine._settle_showdown()
    # 座位 0 弃牌且投入 50，其余两人各 30；未跟注的 20 退还座位 0。
    assert engine.players[0].stack == 20
    # 主池 90（30*3）在座位 1、2 间争夺，K 对胜 Q 对，座位 1 全取。
    assert engine.players[1].stack == 90
    assert engine.players[2].stack == 0
    assert engine.winners == [1]


def test_position_rotation_each_hand() -> None:
    engine = PokerEngine(3, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    start_button = engine.button
    for i in range(3):
        engine.start_hand()
        assert engine.button == (start_button + 1 + i) % 3


def test_chip_conservation_full_hand() -> None:
    engine = PokerEngine(3, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    total = sum(p.stack for p in engine.players) + engine.pot
    while not engine.hand_over:
        legal = engine.legal_actions()
        if legal.can_check:
            engine.apply_action(_check())
        else:
            engine.apply_action(_call())
    assert sum(p.stack for p in engine.players) == total
    assert sum(engine.last_net.values()) == 0


def test_snapshot_is_read_only_copy() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    snap = engine.snapshot()
    assert snap.pot == 15
    assert snap.street == Street.PREFLOP
    assert len(snap.players) == 2
