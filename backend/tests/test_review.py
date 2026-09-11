"""复盘分析测试：确定性重放、错误检测与参考 Bot 对比。"""

from app.analysis.hand_review import build_review
from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str as card
from app.poker.engine import PokerEngine
from app.storage.hand_history import build_hand_history


def _apply(engine: PokerEngine, action_type: ActionType, amount: int = 0) -> None:
    engine.apply_action(Action(action_type, amount))


def _review_for(hole: dict[int, list], board: list, moves: list) -> dict:
    """按给定动作脚本打完一手牌并返回复盘结果（HU，button=1，真人 seat0 为大盲）。"""
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(button=1, hole_cards=hole, board=board)
    for action_type, amount in moves:
        _apply(engine, action_type, amount)
    assert engine.hand_over
    history = build_hand_history(engine, hand_number=1, human_seat=0)
    return build_review(history)


def test_review_flags_value_missed() -> None:
    # 真人 AA 翻牌后无人下注却过牌，应命中「价值丢失」。
    hole = {0: [card("As"), card("Ad")], 1: [card("7c"), card("2d")]}
    board = [card(s) for s in ("2c", "7d", "9h", "3s", "Kd")]
    moves = [
        (ActionType.CALL, 0),  # SB 跟注
        (ActionType.CHECK, 0),  # BB 过牌（真人）
        (ActionType.CHECK, 0),  # 翻牌真人过牌
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
    ]
    review = _review_for(hole, board, moves)

    flop = [d for d in review["decisions"] if d["street"] == "flop"]
    assert flop, "翻牌后真人应有决策点"
    codes = {m["code"] for d in flop for m in d["mistakes"]}
    assert "value_missed" in codes


def test_review_flags_bad_call() -> None:
    # 真人 8 高牌面对大额下注仍跟注，应命中「跟注赔率不足」。
    hole = {0: [card("8c"), card("3d")], 1: [card("As"), card("Ad")]}
    board = [card(s) for s in ("2c", "7d", "9h", "3s", "Kd")]
    moves = [
        (ActionType.CALL, 0),  # SB 跟注
        (ActionType.CHECK, 0),  # BB 过牌（真人）
        (ActionType.CHECK, 0),  # 翻牌真人过牌
        (ActionType.BET, 300),  # 对手大额下注
        (ActionType.CALL, 0),  # 真人跟注
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
    ]
    review = _review_for(hole, board, moves)

    flop = [d for d in review["decisions"] if d["street"] == "flop"]
    codes = {m["code"] for d in flop for m in d["mistakes"]}
    assert "bad_call" in codes


def test_review_reports_reference_bot_action() -> None:
    # 每个真人决策点都应给出参考 Bot 的动作，且结构完整。
    hole = {0: [card("As"), card("Ad")], 1: [card("7c"), card("2d")]}
    board = [card(s) for s in ("2c", "7d", "9h", "3s", "Kd")]
    moves = [
        (ActionType.CALL, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
    ]
    review = _review_for(hole, board, moves)

    assert review["hand_number"] == 1
    assert review["human_seat"] == 0
    assert review["decisions"], "应至少存在一个真人决策点"
    for d in review["decisions"]:
        assert 0.0 <= d["equity"] <= 1.0
        assert d["bot_action"]["action"] in ("fold", "check", "call", "bet", "raise")
