"""引擎确定性回放入口测试：注入底牌/公共牌与发牌顺序。"""

from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine


def _checkdown(engine: PokerEngine) -> None:
    """让所有在场玩家免费过牌、面对下注则跟注，直至摊牌。"""
    while not engine.hand_over:
        legal = engine.legal_actions()
        engine.apply_action(
            Action(ActionType.CHECK) if legal.can_check else Action(ActionType.CALL)
        )


def test_start_hand_with_injects_hole_cards() -> None:
    engine = PokerEngine(2, 5, 10, 1000)
    hole = {
        0: [card_from_str("As"), card_from_str("Kh")],
        1: [card_from_str("2c"), card_from_str("7d")],
    }
    engine.start_hand_with(button=0, hole_cards=hole, board=[])
    assert engine.players[0].hole_cards == hole[0]
    assert engine.players[1].hole_cards == hole[1]
    assert engine.button == 0


def test_replay_deals_board_in_order() -> None:
    engine = PokerEngine(2, 5, 10, 1000)
    hole = {
        0: [card_from_str("As"), card_from_str("Kh")],
        1: [card_from_str("2c"), card_from_str("7d")],
    }
    board = [card_from_str(s) for s in ("3h", "4s", "5c", "9d", "Jh")]
    engine.start_hand_with(button=0, hole_cards=hole, board=board)
    _checkdown(engine)
    # 公共牌应严格按注入顺序发（翻牌 3 张 + 转牌 1 张 + 河牌 1 张）。
    assert engine.board == board


def test_card_from_str_roundtrip() -> None:
    for text in ("As", "Th", "2c", "Qd", "Kd"):
        assert str(card_from_str(text)) == text
