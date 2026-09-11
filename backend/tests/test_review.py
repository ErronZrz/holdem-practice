"""复盘分析测试：确定性重放、错误检测与参考 Bot 对比。"""

from app.analysis.hand_review import _detect_mistakes, build_review
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


def _play_and_capture(
    stacks: dict[int, int],
    hole: dict[int, list],
    board: list,
    moves: list[tuple[int, ActionType, int]],
    human_seat: int,
    button: int,
) -> tuple[dict, list[tuple[int, int]]]:
    """按脚本打完一手牌，返回历史与真人各决策点的（底池, 跟注额）。"""
    engine = PokerEngine(len(stacks), 5, 10, max(stacks.values()))
    for seat, stack in stacks.items():
        engine.players[seat].stack = stack
    engine.start_hand_with(button=button, hole_cards=hole, board=board)
    captured: list[tuple[int, int]] = []
    for seat, action_type, amount in moves:
        assert engine.current_seat == seat
        if seat == human_seat:
            captured.append((engine.pot, engine.legal_actions().call_amount))
        engine.apply_action(Action(action_type, amount))
    assert engine.hand_over
    history = build_hand_history(engine, hand_number=1, human_seat=human_seat)
    return history, captured


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


def test_review_replays_per_player_stacks() -> None:
    # 各玩家起始筹码不同且有人全下时，重放应逐人还原筹码，底池/跟注额与实际一致。
    stacks = {0: 2000, 1: 2000, 2: 100}
    hole = {
        0: [card("As"), card("Ad")],
        1: [card("7c"), card("2d")],
        2: [card("Qh"), card("Qs")],
    }
    board = [card(s) for s in ("2c", "7d", "9h", "3s", "Kd")]
    moves = [
        (0, ActionType.RAISE, 200),
        (1, ActionType.CALL, 0),
        (2, ActionType.CALL, 0),  # 短码全下
        (1, ActionType.CHECK, 0),
        (0, ActionType.CHECK, 0),
        (1, ActionType.CHECK, 0),
        (0, ActionType.CHECK, 0),
        (1, ActionType.CHECK, 0),
        (0, ActionType.CHECK, 0),
    ]
    history, captured = _play_and_capture(stacks, hole, board, moves, human_seat=0, button=0)
    review = build_review(history)

    assert [(d["pot"], d["to_call"]) for d in review["decisions"]] == captured
    assert captured[0] == (15, 10)
    assert captured[1] == (500, 0)


def test_review_replays_raise_increment() -> None:
    # 历史记录的是加注增量，重放需换算为加注后总额，否则底池与跟注额会漂移。
    stacks = {0: 1000, 1: 1000, 2: 1000}
    hole = {
        0: [card("As"), card("Ad")],
        1: [card("Kh"), card("Qs")],
        2: [card("7c"), card("2d")],
    }
    board = [card(s) for s in ("2c", "7d", "9h", "3s", "Kd")]
    moves = [
        (0, ActionType.RAISE, 30),
        (1, ActionType.CALL, 0),
        (2, ActionType.RAISE, 90),  # 大盲再加注
        (0, ActionType.CALL, 0),
        (1, ActionType.CALL, 0),
        (1, ActionType.CHECK, 0),
        (2, ActionType.CHECK, 0),
        (0, ActionType.CHECK, 0),
        (1, ActionType.CHECK, 0),
        (2, ActionType.CHECK, 0),
        (0, ActionType.CHECK, 0),
        (1, ActionType.CHECK, 0),
        (2, ActionType.CHECK, 0),
        (0, ActionType.CHECK, 0),
    ]
    history, captured = _play_and_capture(stacks, hole, board, moves, human_seat=1, button=0)
    review = build_review(history)

    assert [(d["pot"], d["to_call"]) for d in review["decisions"]] == captured
    assert captured[1] == (210, 60)


def test_detect_mistakes_bad_fold_preflop_floor() -> None:
    # 翻牌前 vs 随机胜率不足以支撑「误弃」判定：胜率 0.53 不命中，0.60 命中。
    base = {"pot_odds": 0.33, "to_call": 20, "board_len": 0, "pot": 40, "can_raise": False}
    weak = _detect_mistakes(action=Action(ActionType.FOLD), equity=0.53, **base)
    assert "bad_fold" not in {m["code"] for m in weak}
    strong = _detect_mistakes(action=Action(ActionType.FOLD), equity=0.60, **base)
    assert "bad_fold" in {m["code"] for m in strong}


def test_detect_mistakes_bad_fold_scales_with_bet_size() -> None:
    # 翻牌后跟注占底池越大，容差越高：胜率 0.50 不命中，0.60 命中。
    base = {"pot_odds": 0.333, "to_call": 100, "board_len": 3, "pot": 200, "can_raise": False}
    edge = _detect_mistakes(action=Action(ActionType.FOLD), equity=0.50, **base)
    assert "bad_fold" not in {m["code"] for m in edge}
    clear = _detect_mistakes(action=Action(ActionType.FOLD), equity=0.60, **base)
    assert "bad_fold" in {m["code"] for m in clear}


def test_detect_mistakes_value_missed_threshold() -> None:
    # 无人下注过牌：胜率 0.75 不再判价值丢失，0.85 命中。
    base = {"pot_odds": None, "to_call": 0, "board_len": 3, "pot": 100, "can_raise": True}
    thin = _detect_mistakes(action=Action(ActionType.CHECK), equity=0.75, **base)
    assert "value_missed" not in {m["code"] for m in thin}
    strong = _detect_mistakes(action=Action(ActionType.CHECK), equity=0.85, **base)
    assert "value_missed" in {m["code"] for m in strong}


def test_detect_mistakes_bad_call_margin() -> None:
    # 跟注仅略低于赔率（EV 约 0）不判 error，明显不足才判。
    base = {"pot_odds": 0.40, "to_call": 20, "board_len": 3, "pot": 30, "can_raise": True}
    edge = _detect_mistakes(action=Action(ActionType.CALL), equity=0.38, **base)
    assert "bad_call" not in {m["code"] for m in edge}
    clear = _detect_mistakes(action=Action(ActionType.CALL), equity=0.30, **base)
    assert "bad_call" in {m["code"] for m in clear}
