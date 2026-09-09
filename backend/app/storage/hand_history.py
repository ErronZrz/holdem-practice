"""把一手结束后的引擎状态序列化为 Hand History（JSON，source of truth）。

该模块只读取引擎的公开属性（players / board / history / winners / last_net / street /
showdown_hands / pot_results），不修改引擎，属于持久化层的序列化职责。
"""

from app.poker.engine import PokerEngine
from app.poker.evaluator import evaluate
from app.poker.state import Street


def build_hand_history(engine: PokerEngine, hand_number: int, human_seat: int) -> dict:
    """构造一手牌的完整历史字典，键与值均为 JSON 可序列化类型。"""
    players = []
    for p in engine.players:
        start_stack = p.stack - engine.last_net.get(p.seat, 0)
        players.append(
            {
                "seat": p.seat,
                "name": p.name,
                "is_human": p.seat == human_seat,
                "hole_cards": [str(c) for c in p.hole_cards],
                "starting_stack": start_stack,
            }
        )
    result = {
        "hand_number": hand_number,
        "num_players": engine.num_players,
        "small_blind": engine.small_blind,
        "big_blind": engine.big_blind,
        "button": engine.button,
        "board": [str(c) for c in engine.board],
        "players": players,
        "actions": list(engine.history),
        "street": engine.street.name.lower(),
        "showdown": engine.street == Street.SHOWDOWN,
        "winners": list(engine.winners),
        "net": {str(seat): net for seat, net in engine.last_net.items()},
    }
    if engine.street == Street.SHOWDOWN:
        result["showdown_hands"] = {
            str(seat): {
                "cards": [str(c) for c in cards],
                "category": evaluate(cards).category.name,
            }
            for seat, cards in engine.showdown_hands.items()
        }
        result["pot_results"] = [
            {
                "amount": pr["amount"],
                "winners": list(pr["winners"]),
                "shares": {str(k): v for k, v in pr["shares"].items()},
            }
            for pr in engine.pot_results
        ]
    return result
