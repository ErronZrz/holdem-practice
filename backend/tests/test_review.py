"""复盘分析测试：确定性重放、错误检测与参考 Bot 对比。"""

import pytest

from app.analysis.hand_review import (
    _conservative_distribution,
    _detect_mistakes,
    _dominated_pair,
    _weak_kicker_top_pair,
    build_review,
)
from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import card_from_str as card
from app.poker.engine import PokerEngine
from app.poker.state import GameState, PlayerState, Street
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
        distribution = d["bot_distribution"]
        assert distribution, "每个决策点都应给出参考动作分布"
        assert sum(item["probability"] for item in distribution) == pytest.approx(1.0)
        top = max(distribution, key=lambda item: item["probability"])
        assert d["bot_action"]["action"] == top["action"], "参考动作取分布中的众数"


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


def test_review_reference_counts_all_in_opponent() -> None:
    # 复盘参考分布复用策略口径，唯一全下对手仍应参与翻后估值。
    engine = PokerEngine(2, 5, 10, 110)
    engine.players[1].stack = 100
    engine.start_hand_with(
        button=0,
        hole_cards={
            0: [card("Qh"), card("Jc")],
            1: [card("2c"), card("7d")],
        },
        board=[card(s) for s in ("As", "Kd", "9s", "Th", "3c")],
    )
    for action_type, amount in (
        (ActionType.CALL, 0),
        (ActionType.CHECK, 0),
        (ActionType.CHECK, 0),
        (ActionType.BET, 100),
        (ActionType.FOLD, 0),
    ):
        _apply(engine, action_type, amount)
    assert engine.hand_over

    review = build_review(build_hand_history(engine, hand_number=1, human_seat=1))
    flop = next(
        decision
        for decision in review["decisions"]
        if decision["street"] == "flop" and decision["to_call"] == 100
    )

    assert flop["opponents"] == 1
    assert flop["to_call"] == 100
    assert flop["bot_action"]["action"] == ActionType.FOLD.value


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
    base = {
        "pot_odds": 0.33,
        "to_call": 20,
        "pot": 40,
        "can_raise": False,
        "hole_cards": [card("As"), card("Kd")],
        "board": [],
        "big_blind": 10,
    }
    weak = _detect_mistakes(action=Action(ActionType.FOLD), equity=0.53, **base)
    assert "bad_fold" not in {m["code"] for m in weak}
    strong = _detect_mistakes(action=Action(ActionType.FOLD), equity=0.60, **base)
    assert "bad_fold" in {m["code"] for m in strong}


def test_detect_mistakes_bad_fold_scales_with_bet_size() -> None:
    # 翻牌后跟注占底池越大，容差越高：胜率 0.50 不命中，0.60 命中。
    # 用顶对（对子等于公共牌最高点数）作样本，避免受「被压制对子」门槛干扰。
    base = {
        "pot_odds": 0.333,
        "to_call": 100,
        "pot": 200,
        "can_raise": False,
        "hole_cards": [card("Ah"), card("Kd")],
        "board": [card("Kc"), card("7d"), card("2h")],
        "big_blind": 10,
    }
    edge = _detect_mistakes(action=Action(ActionType.FOLD), equity=0.50, **base)
    assert "bad_fold" not in {m["code"] for m in edge}
    clear = _detect_mistakes(action=Action(ActionType.FOLD), equity=0.60, **base)
    assert "bad_fold" in {m["code"] for m in clear}


def test_detect_mistakes_bad_fold_requires_playable_strength() -> None:
    # 翻牌后即使胜率高于赔率容差，无真实牌力（仅公共牌成对）也不判误弃；有真实成手牌才判。
    base = {
        "pot_odds": 0.333,
        "to_call": 100,
        "pot": 200,
        "can_raise": False,
        "board": [card("5s"), card("5d"), card("7c")],
        "big_blind": 10,
    }
    weak = _detect_mistakes(
        action=Action(ActionType.FOLD), equity=0.60, hole_cards=[card("Ah"), card("9h")], **base
    )
    assert "bad_fold" not in {m["code"] for m in weak}
    made = _detect_mistakes(
        action=Action(ActionType.FOLD), equity=0.60, hole_cards=[card("7h"), card("9h")], **base
    )
    assert "bad_fold" in {m["code"] for m in made}


def test_dominated_pair_detection() -> None:
    board = [card(s) for s in ("9d", "Kd", "2h")]
    # 一对且该对低于公共牌最高点数：JJ 在 K 高面判压制。
    assert _dominated_pair([card("Jc"), card("Js")], board) is True
    # 顶对（对子等于公共牌最高点数）与超对不受影响。
    assert _dominated_pair([card("Kc"), card("Jd")], board) is False
    assert _dominated_pair([card("Ac"), card("Ad")], board) is False
    # 三条、两对与翻牌前均不适用。
    assert _dominated_pair([card("9c"), card("9h")], board) is False
    assert _dominated_pair([card("9c"), card("2c")], board) is False
    assert _dominated_pair([card("Jc"), card("Js")], []) is False
    # 仅靠公共牌成对不算真实成手牌。
    assert (
        _dominated_pair(
            [card("Ah"), card("5h")], [card("Jd"), card("Jc"), card("2s")]
        )
        is False
    )


def test_detect_mistakes_bad_fold_skips_dominated_pair() -> None:
    # 被公共牌高张压制的对子不算可继续牌力：胜率高于赔率容差也不判误弃，超对仍判。
    base = {
        "pot_odds": 0.333,
        "to_call": 120,
        "pot": 240,
        "can_raise": False,
        "board": [card(s) for s in ("9d", "Kd", "2h")],
        "big_blind": 10,
    }
    dominated = _detect_mistakes(
        action=Action(ActionType.FOLD),
        equity=0.60,
        hole_cards=[card("Jc"), card("Js")],
        **base,
    )
    assert "bad_fold" not in {m["code"] for m in dominated}
    overpair = _detect_mistakes(
        action=Action(ActionType.FOLD),
        equity=0.60,
        hole_cards=[card("Ac"), card("Ad")],
        **base,
    )
    assert "bad_fold" in {m["code"] for m in overpair}


def test_detect_mistakes_value_missed_threshold() -> None:
    # 无人下注过牌：胜率 0.75 不再判价值丢失，0.85 命中。
    base = {
        "pot_odds": None,
        "to_call": 0,
        "pot": 100,
        "can_raise": True,
        "hole_cards": [card("As"), card("Ad")],
        "board": [card("2c"), card("7d"), card("9h")],
        "big_blind": 10,
    }
    thin = _detect_mistakes(action=Action(ActionType.CHECK), equity=0.75, **base)
    assert "value_missed" not in {m["code"] for m in thin}
    strong = _detect_mistakes(action=Action(ActionType.CHECK), equity=0.85, **base)
    assert "value_missed" in {m["code"] for m in strong}


def test_detect_mistakes_bad_call_margin() -> None:
    # 跟注仅略低于赔率（EV 约 0）不判 error，明显不足才判。
    base = {
        "pot_odds": 0.40,
        "to_call": 20,
        "pot": 30,
        "can_raise": True,
        "hole_cards": [card("8c"), card("3d")],
        "board": [card("2c"), card("7d"), card("9h")],
        "big_blind": 10,
    }
    edge = _detect_mistakes(action=Action(ActionType.CALL), equity=0.38, **base)
    assert "bad_call" not in {m["code"] for m in edge}
    clear = _detect_mistakes(action=Action(ActionType.CALL), equity=0.30, **base)
    assert "bad_call" in {m["code"] for m in clear}


def test_detect_mistakes_preflop_limp_exempt() -> None:
    # 翻牌前跟注额不超过一个大盲（补齐盲注 / limp）属廉价看牌，不判赔率不足。
    base = {
        "pot_odds": 0.40,
        "to_call": 20,
        "pot": 30,
        "can_raise": True,
        "hole_cards": [card("6h"), card("As")],
        "board": [],
    }
    limp = _detect_mistakes(
        action=Action(ActionType.CALL), equity=0.275, big_blind=20, **base
    )
    assert "bad_call" not in {m["code"] for m in limp}
    # 超过一个大盲的翻前跟注仍按赔率判定。
    raised = _detect_mistakes(
        action=Action(ActionType.CALL), equity=0.275, big_blind=10, **base
    )
    assert "bad_call" in {m["code"] for m in raised}


def test_detect_mistakes_limp_exempt_is_preflop_only() -> None:
    # 翻牌后即使跟注额不超过一个大盲，也不适用 limp 豁免。
    base = {
        "pot_odds": 0.40,
        "to_call": 20,
        "pot": 30,
        "can_raise": True,
        "hole_cards": [card("8c"), card("3d")],
        "board": [card("2c"), card("7d"), card("9h")],
    }
    mistakes = _detect_mistakes(
        action=Action(ActionType.CALL), equity=0.275, big_blind=20, **base
    )
    assert "bad_call" in {m["code"] for m in mistakes}


def test_weak_kicker_top_pair_detection() -> None:
    board = [card(s) for s in ("Qs", "Tc", "Ad", "2h", "8s")]
    # 顶对但踢脚 6 低于公共牌第二高的 Q，判弱；踢脚 K 高于 Q 不判弱。
    assert _weak_kicker_top_pair([card("6h"), card("As")], board) is True
    assert _weak_kicker_top_pair([card("Kh"), card("As")], board) is False
    # 两对、三条、超对与「仅靠公共牌成对」均不属弱踢脚顶对。
    assert _weak_kicker_top_pair([card("Qh"), card("As")], board) is False
    assert _weak_kicker_top_pair([card("Ah"), card("Ad")], board) is False
    assert _weak_kicker_top_pair([card("Kh"), card("Kd")], board) is False
    assert (
        _weak_kicker_top_pair(
            [card("Kh"), card("Jd")], [card("Qs"), card("Qd"), card("2c")]
        )
        is False
    )
    # 翻牌同样适用：A6 在 A 8 2 上踢脚 6 低于 8，判弱。
    flop = [card("Ad"), card("8c"), card("2s")]
    assert _weak_kicker_top_pair([card("6h"), card("As")], flop) is True


def test_detect_mistakes_value_missed_skips_weak_kicker() -> None:
    # 弱踢脚顶对属薄价值，过牌不判价值丢失；强踢脚顶对仍判。
    base = {
        "pot_odds": None,
        "to_call": 0,
        "pot": 630,
        "can_raise": True,
        "board": [card(s) for s in ("Qs", "Tc", "Ad", "2h", "8s")],
        "big_blind": 10,
    }
    weak = _detect_mistakes(
        action=Action(ActionType.CHECK), equity=0.85, hole_cards=[card("6h"), card("As")], **base
    )
    assert "value_missed" not in {m["code"] for m in weak}
    strong = _detect_mistakes(
        action=Action(ActionType.CHECK), equity=0.85, hole_cards=[card("Kh"), card("As")], **base
    )
    assert "value_missed" in {m["code"] for m in strong}


# ------------------------------------------------------------------ 保守参考动作


def _legal(**kw) -> LegalActions:
    defaults = dict(
        can_fold=True,
        can_check=False,
        can_call=False,
        call_amount=0,
        can_bet=False,
        min_bet=0,
        max_bet=0,
        can_raise=False,
        min_raise_to=0,
        max_raise_to=0,
    )
    defaults.update(kw)
    return LegalActions(**defaults)


def _facing_bet_state(hole, board, pot, street=Street.FLOP) -> GameState:
    me = PlayerState(seat=0, name="p0", hole_cards=list(hole))
    villain = PlayerState(seat=1, name="p1")
    return GameState(
        street=street,
        board=tuple(board),
        pot=pot,
        current_seat=0,
        button=0,
        hand_over=False,
        players=(me, villain),
    )


def _prob(distribution: list[tuple[Action, float]], action_type: ActionType) -> float:
    """取分布中某类动作的总概率，便于断言。"""
    return sum(weight for action, weight in distribution if action.type == action_type)


def _single(action_type: ActionType, amount: int = 0) -> list[tuple[Action, float]]:
    """构造只含一个动作（概率 1.0）的基线分布。"""
    return [(Action(action_type, amount), 1.0)]


def test_conservative_reference_folds_high_card_to_bet() -> None:
    # 高张无听牌面对下注：胜率虽高于赔率，但无成手牌，跟注质量应转移到弃牌。
    state = _facing_bet_state(
        [card("Ah"), card("Qs")], [card("8h"), card("Th"), card("4d")], pot=30
    )
    legal = _legal(can_call=True, call_amount=15)
    dist = _conservative_distribution(
        state, legal, state.players[0], eq=0.55, baseline=_single(ActionType.CALL)
    )
    assert _prob(dist, ActionType.FOLD) == 1.0
    assert _prob(dist, ActionType.CALL) == 0.0


def test_conservative_reference_calls_top_pair() -> None:
    # 顶对（底牌与公共牌配对）是真实成手牌，参考动作仍跟注。
    state = _facing_bet_state(
        [card("Ah"), card("7d")], [card("Ad"), card("Kc"), card("2s")], pot=30
    )
    legal = _legal(can_call=True, call_amount=15)
    dist = _conservative_distribution(
        state, legal, state.players[0], eq=0.55, baseline=_single(ActionType.CALL)
    )
    assert _prob(dist, ActionType.CALL) == 1.0


def test_conservative_reference_calls_strong_draw() -> None:
    # 同花听牌（补牌数 ≥ 8）即使暂无成手牌，参考动作仍跟注。
    state = _facing_bet_state(
        [card("Ts"), card("9s")], [card("As"), card("Ks"), card("2d")], pot=30
    )
    legal = _legal(can_call=True, call_amount=15)
    dist = _conservative_distribution(
        state, legal, state.players[0], eq=0.55, baseline=_single(ActionType.CALL)
    )
    assert _prob(dist, ActionType.CALL) == 1.0


def test_conservative_reference_folds_dominated_pair() -> None:
    # 被公共牌高张压制的口袋对（JJ 在 K 高面）面对大注：跟注质量转移到弃牌。
    state = _facing_bet_state(
        [card("Jc"), card("Js")], [card(s) for s in ("9d", "Kd", "2h")], pot=240
    )
    legal = _legal(can_call=True, call_amount=120)
    dist = _conservative_distribution(
        state, legal, state.players[0], eq=0.60, baseline=_single(ActionType.CALL)
    )
    assert _prob(dist, ActionType.FOLD) == 1.0
    assert _prob(dist, ActionType.CALL) == 0.0


def test_conservative_reference_calls_overpair() -> None:
    # 超对不被公共牌压制，赔率有余量时参考动作仍跟注。
    state = _facing_bet_state(
        [card("Ac"), card("Ad")], [card(s) for s in ("9d", "Kd", "2h")], pot=240
    )
    legal = _legal(can_call=True, call_amount=120)
    dist = _conservative_distribution(
        state, legal, state.players[0], eq=0.60, baseline=_single(ActionType.CALL)
    )
    assert _prob(dist, ActionType.CALL) == 1.0


def test_conservative_reference_halves_margin_for_strong_draw() -> None:
    # 强听牌（同花听牌 9 补牌）余量折半：胜率 0.4570 可跟半池，0.4200 仍弃牌。
    board = [card(s) for s in ("Jh", "8h", "Kh", "7c")]
    state = _facing_bet_state(
        [card("2h"), card("2d")], board, pot=360, street=Street.TURN
    )
    legal = _legal(can_call=True, call_amount=180)
    calls = _conservative_distribution(
        state, legal, state.players[0], eq=0.4570, baseline=_single(ActionType.CALL)
    )
    assert _prob(calls, ActionType.CALL) == 1.0
    folds = _conservative_distribution(
        state, legal, state.players[0], eq=0.4200, baseline=_single(ActionType.CALL)
    )
    assert _prob(folds, ActionType.FOLD) == 1.0


def test_conservative_reference_allows_cheap_call_with_high_card() -> None:
    # 跟注额不超过底池 1/3 时放宽牌力要求，高张可便宜看牌。
    state = _facing_bet_state(
        [card("Ah"), card("Qs")], [card("8h"), card("Th"), card("4d")], pot=60
    )
    legal = _legal(can_call=True, call_amount=20)
    dist = _conservative_distribution(
        state, legal, state.players[0], eq=0.55, baseline=_single(ActionType.CALL)
    )
    assert _prob(dist, ActionType.CALL) == 1.0


def test_conservative_reference_shifts_only_call_mass() -> None:
    # 收窄只转移跟注质量，不改变弃牌等其它动作的权重。
    state = _facing_bet_state(
        [card("Ah"), card("Qs")], [card("8h"), card("Th"), card("4d")], pot=30
    )
    legal = _legal(can_call=True, call_amount=15)
    baseline = [(Action(ActionType.CALL), 0.6), (Action(ActionType.FOLD), 0.4)]
    dist = _conservative_distribution(state, legal, state.players[0], eq=0.55, baseline=baseline)
    assert _prob(dist, ActionType.FOLD) == pytest.approx(1.0)
    assert _prob(dist, ActionType.CALL) == 0.0


def test_conservative_reference_checks_weak_kicker_top_pair() -> None:
    # 弱踢脚顶对无人下注：把价值下注质量转移到过牌。
    state = _facing_bet_state(
        [card("6h"), card("As")],
        [card(s) for s in ("Qs", "Tc", "Ad", "2h", "8s")],
        pot=630,
        street=Street.RIVER,
    )
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=630)
    dist = _conservative_distribution(
        state, legal, state.players[0], eq=0.85, baseline=_single(ActionType.BET, 630)
    )
    assert _prob(dist, ActionType.CHECK) == 1.0
    assert _prob(dist, ActionType.BET) == 0.0


def test_conservative_reference_keeps_strong_kicker_value_bet() -> None:
    # 强踢脚顶对（K 高于公共牌第二高的 Q）不属弱踢脚，价值下注保留。
    state = _facing_bet_state(
        [card("Kh"), card("As")], [card("Qs"), card("Tc"), card("Ad")], pot=100
    )
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=100)
    dist = _conservative_distribution(
        state, legal, state.players[0], eq=0.85, baseline=_single(ActionType.BET, 100)
    )
    assert _prob(dist, ActionType.BET) == 1.0


def test_conservative_reference_keeps_raise_and_fold() -> None:
    # 加注与弃牌不属于「宽松跟注」，参考分布原样沿用基线。
    state = _facing_bet_state(
        [card("3s"), card("3c")], [card("3d"), card("Kc"), card("2s")], pot=30
    )
    legal = _legal(
        can_call=True, call_amount=15, can_raise=True, min_raise_to=30, max_raise_to=1000
    )
    raise_dist = _single(ActionType.RAISE, 60)
    assert (
        _conservative_distribution(state, legal, state.players[0], eq=0.95, baseline=raise_dist)
        == raise_dist
    )
    fold_dist = _single(ActionType.FOLD)
    assert (
        _conservative_distribution(state, legal, state.players[0], eq=0.10, baseline=fold_dist)
        == fold_dist
    )
