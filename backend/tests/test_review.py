"""复盘分析测试：确定性重放、错误检测与参考 Bot 对比。"""

import pytest

import app.analysis.hand_review as hand_review_module
from app.analysis.hand_review import (
    _detect_mistakes,
    _dominated_pair,
    _fair_share,
    _folding_gives_up_value,
    _guard_low_equity_lead,
    _guard_negative_call,
    _guard_reference_distribution,
    _mode_action,
    _publish_reference,
    _reference_chips,
    _weak_kicker_top_pair,
    build_review,
)
from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str as card
from app.poker.engine import PokerEngine
from app.storage.hand_history import build_hand_history
from tools.diagnose_review import connect_readonly, diagnose_history, load_history


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
    # 真人 AA 无人下注却过牌。翻牌份额刚好低于单挑价值线，转牌和河牌越过这条线后记价值丢失。
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

    by_street = {d["street"]: d for d in review["decisions"]}
    flop_codes = {m["code"] for m in by_street["flop"]["mistakes"]}
    assert by_street["flop"]["equity"] < 0.8
    assert "value_missed" not in flop_codes
    for street in ("turn", "river"):
        codes = {m["code"] for m in by_street[street]["mistakes"]}
        assert by_street[street]["equity"] >= 0.8
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
        assert d["actual_call_amount"] == d["to_call"]
        assert d["is_short_all_in_call"] is False
        assert d["bot_action"]["action"] in ("fold", "check", "call", "bet", "raise")
        distribution = d["bot_distribution"]
        assert distribution, "每个决策点都应给出参考动作分布"
        assert sum(item["probability"] for item in distribution) == pytest.approx(1.0)
        totals: dict[str, float] = {}
        order: list[str] = []
        for item in distribution:
            action_name = item["action"]
            if action_name not in totals:
                order.append(action_name)
                totals[action_name] = 0.0
            totals[action_name] += item["probability"]
        leading = max(order, key=lambda name: totals[name])
        assert d["bot_action"]["action"] == leading, "参考动作取动作类型汇总后的众数"


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


def test_review_short_call_reports_layered_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 短码全下对外给出按实际支付计算的赔率，判据看到的跟注额仍是完整欠注。
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

    captured: list[tuple[int, float | None]] = []
    original = hand_review_module._detect_mistakes

    def capture_mistakes(*args, **kwargs):
        if kwargs["to_call"] == 100:
            captured.append((kwargs["to_call"], kwargs["pot_odds"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(hand_review_module, "_detect_mistakes", capture_mistakes)
    review = build_review(build_hand_history(engine, hand_number=1, human_seat=1))
    flop = next(
        decision
        for decision in review["decisions"]
        if decision["street"] == "flop" and decision["to_call"] == 100
    )

    assert flop["actual_call_amount"] == 90
    assert flop["pot_odds"] is not None
    assert flop["call_ev"] is not None
    # 弃牌探针和正式判据各看一次，两次都按完整欠注，不按短码实付。
    assert captured == [
        (100, pytest.approx(flop["pot_odds"])),
        (100, pytest.approx(flop["pot_odds"])),
    ]


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
    assert flop["actual_call_amount"] == 90
    assert flop["is_short_all_in_call"] is True
    assert flop["pot_odds"] is not None
    assert flop["call_ev"] is not None
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


def _codes(action: Action, **overrides: object) -> set[str]:
    """用单挑、跟注期望足够高的默认局面调用判据，再按用例覆盖字段。"""
    params: dict[str, object] = {
        "equity": 0.60,
        "call_ev": 500.0,
        "pot_odds": 0.33,
        "to_call": 20,
        "actual_call": 20,
        "pot": 40,
        "contested": 60,
        "can_raise": False,
        "opponents": 1,
        "hole_cards": [card("As"), card("Kd")],
        "board": [],
        "big_blind": 10,
        "reference": Action(ActionType.CALL),
    }
    params.update(overrides)
    return {item["code"] for item in _detect_mistakes(action=action, **params)}


def test_detect_mistakes_bad_fold_preflop_floor() -> None:
    # 翻牌前份额低于公平份额时不判误弃；达到公平份额且跟注期望超过门槛才判。
    base = {
        "call_ev": 500.0,
        "to_call": 20,
        "actual_call": 20,
        "pot": 40,
        "contested": 60,
        "hole_cards": [card("As"), card("Kd")],
        "board": [],
    }
    assert "bad_fold" not in _codes(Action(ActionType.FOLD), equity=0.49, **base)
    assert "bad_fold" in _codes(Action(ActionType.FOLD), equity=0.50, **base)


def test_detect_mistakes_bad_fold_scales_with_bet_size() -> None:
    # 实付占底池一半时门槛更高：跟注期望等于门槛不命中，超过才命中。
    base = {
        "to_call": 100,
        "actual_call": 100,
        "pot": 200,
        "contested": 300,
        "hole_cards": [card("Ah"), card("Kd")],
        "board": [card("Kc"), card("7d"), card("2h")],
    }
    assert "bad_fold" not in _codes(Action(ActionType.FOLD), call_ev=60.0, **base)
    assert "bad_fold" in _codes(Action(ActionType.FOLD), call_ev=60.1, **base)


def test_detect_mistakes_bad_fold_requires_playable_strength() -> None:
    # 翻牌后即使跟注期望很高，无真实牌力也不判误弃；有真实成手牌才判。
    base = {
        "call_ev": 500.0,
        "to_call": 100,
        "actual_call": 100,
        "pot": 200,
        "contested": 300,
        "board": [card("5s"), card("5d"), card("7c")],
    }
    assert "bad_fold" not in _codes(
        Action(ActionType.FOLD), hole_cards=[card("Ah"), card("9h")], **base
    )
    assert "bad_fold" in _codes(
        Action(ActionType.FOLD), hole_cards=[card("7h"), card("9h")], **base
    )


def test_detect_mistakes_bad_fold_requires_positive_call_ev() -> None:
    # 跟注期望为负时，弃牌不再被标成放弃正期望。
    assert "bad_fold" not in _codes(
        Action(ActionType.FOLD),
        call_ev=-1.0,
        equity=0.80,
        board=[card("Kc"), card("7d"), card("2h")],
        hole_cards=[card("Ah"), card("Kd")],
    )


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
    # 被公共牌高张压制的对子不算可继续牌力：跟注期望很高也不判误弃，超对仍判。
    base = {
        "call_ev": 500.0,
        "to_call": 120,
        "actual_call": 120,
        "pot": 240,
        "contested": 360,
        "board": [card(s) for s in ("9d", "Kd", "2h")],
    }
    assert "bad_fold" not in _codes(
        Action(ActionType.FOLD), hole_cards=[card("Jc"), card("Js")], **base
    )
    assert "bad_fold" in _codes(
        Action(ActionType.FOLD), hole_cards=[card("Ac"), card("Ad")], **base
    )


def test_detect_mistakes_value_missed_threshold() -> None:
    # 单挑公平份额 1/2，价值线是 0.8。参考自己下注时才标过牌丢失价值。
    base = {
        "call_ev": None,
        "pot_odds": None,
        "to_call": 0,
        "actual_call": 0,
        "pot": 100,
        "contested": 0,
        "can_raise": True,
        "hole_cards": [card("As"), card("Ad")],
        "board": [card("2c"), card("7d"), card("9h")],
        "reference": Action(ActionType.BET, 60),
    }
    assert "value_missed" not in _codes(Action(ActionType.CHECK), equity=0.79, **base)
    assert "value_missed" in _codes(Action(ActionType.CHECK), equity=0.80, **base)
    assert "value_missed" not in _codes(
        Action(ActionType.CHECK),
        equity=0.90,
        reference=Action(ActionType.CHECK),
        **{key: value for key, value in base.items() if key != "reference"},
    )


def test_detect_mistakes_bad_call_margin() -> None:
    # 亏损不超过一个大盲或竞争层的 3% 时不判，明显超出才判。
    base = {
        "pot_odds": 0.40,
        "to_call": 40,
        "actual_call": 40,
        "pot": 60,
        "contested": 100,
        "can_raise": True,
        "hole_cards": [card("8c"), card("3d")],
        "board": [card("2c"), card("7d"), card("9h")],
    }
    assert "bad_call" not in _codes(Action(ActionType.CALL), call_ev=-9.0, **base)
    assert "bad_call" in _codes(Action(ActionType.CALL), call_ev=-10.1, **base)


def test_detect_mistakes_preflop_limp_exempt() -> None:
    # 翻牌前跟注额不超过一个大盲属廉价看牌，不判赔率不足。
    base = {
        "call_ev": -50.0,
        "pot_odds": 0.40,
        "to_call": 20,
        "actual_call": 20,
        "pot": 30,
        "contested": 50,
        "can_raise": True,
        "hole_cards": [card("6h"), card("As")],
        "board": [],
    }
    assert "bad_call" not in _codes(Action(ActionType.CALL), big_blind=20, **base)
    assert "bad_call" in _codes(Action(ActionType.CALL), big_blind=10, **base)


def test_detect_mistakes_limp_exempt_is_preflop_only() -> None:
    # 翻牌后即使跟注额不超过一个大盲，也不适用补盲豁免。
    assert "bad_call" in _codes(
        Action(ActionType.CALL),
        call_ev=-50.0,
        pot_odds=0.40,
        to_call=20,
        actual_call=20,
        pot=30,
        contested=50,
        can_raise=True,
        hole_cards=[card("8c"), card("3d")],
        board=[card("2c"), card("7d"), card("9h")],
        big_blind=20,
    )


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
    # 弱踢脚顶对属薄价值，过牌不判价值丢失；强踢脚顶对在参考下注时仍判。
    base = {
        "call_ev": None,
        "pot_odds": None,
        "to_call": 0,
        "actual_call": 0,
        "pot": 630,
        "contested": 0,
        "can_raise": True,
        "board": [card(s) for s in ("Qs", "Tc", "Ad", "2h", "8s")],
        "reference": Action(ActionType.BET, 400),
    }
    assert "value_missed" not in _codes(
        Action(ActionType.CHECK), equity=0.85, hole_cards=[card("6h"), card("As")], **base
    )
    assert "value_missed" in _codes(
        Action(ActionType.CHECK), equity=0.85, hole_cards=[card("Kh"), card("As")], **base
    )


def test_detect_mistakes_scales_fair_share_with_opponents() -> None:
    # 五人底池的公平份额是 1/5，价值线降到 0.32；单挑同一份额不够。
    board = [card("2c"), card("7d"), card("9h")]
    shared = {
        "call_ev": None,
        "pot_odds": None,
        "to_call": 0,
        "actual_call": 0,
        "contested": 0,
        "can_raise": True,
        "hole_cards": [card("As"), card("Ad")],
        "board": board,
        "reference": Action(ActionType.BET, 40),
    }
    assert "value_missed" in _codes(
        Action(ActionType.CHECK), equity=0.40, opponents=4, **shared
    )
    assert "value_missed" not in _codes(
        Action(ActionType.CHECK), equity=0.40, opponents=1, **shared
    )


def test_detect_mistakes_reference_direction_vetoes_aggression_labels() -> None:
    # 参考自己在加注时，不把真人的加注标成过度激进；参考在过牌时才标。
    board = [card("2c"), card("7d"), card("9h")]
    shared = {
        "equity": 0.20,
        "call_ev": -30.0,
        "pot_odds": 0.40,
        "to_call": 40,
        "actual_call": 40,
        "pot": 60,
        "contested": 100,
        "can_raise": True,
        "hole_cards": [card("8c"), card("3d")],
        "board": board,
    }
    assert "over_aggressive" not in _codes(
        Action(ActionType.RAISE, 80), reference=Action(ActionType.RAISE, 120), **shared
    )
    assert "over_aggressive" in _codes(
        Action(ActionType.RAISE, 80), reference=Action(ActionType.FOLD), **shared
    )
    # 慢玩只在参考自己会加注时出现。
    strong = {**shared, "equity": 0.95, "call_ev": 80.0}
    assert "slowplay" in _codes(
        Action(ActionType.CALL), reference=Action(ActionType.RAISE, 120), **strong
    )
    assert "slowplay" not in _codes(
        Action(ActionType.CALL), reference=Action(ActionType.CALL), **strong
    )


# ------------------------------------------------------------------ 负期望跟注保护


def _prob(distribution: list[tuple[Action, float]], action_type: ActionType) -> float:
    return sum(weight for action, weight in distribution if action.type == action_type)


def _guard_call(
    distribution,
    call_ev,
    *,
    to_call=40,
    equity=0.8,
    opponents=1,
    postflop=True,
    big_blind=0,
    contested=0,
):
    return _guard_negative_call(
        distribution,
        call_ev,
        to_call=to_call,
        equity=equity,
        opponents=opponents,
        postflop=postflop,
        big_blind=big_blind,
        contested=contested,
    )


def test_negative_call_ev_moves_call_mass_onto_the_leading_raise() -> None:
    # 份额不低于平均且已有加注时，跟注并入概率最高的加注，弃牌保持原样。
    baseline = [
        (Action(ActionType.FOLD), 0.1),
        (Action(ActionType.CALL), 0.6),
        (Action(ActionType.RAISE, 40), 0.2),
        (Action(ActionType.RAISE, 80), 0.1),
    ]
    guarded = _guard_call(baseline, -1.0, equity=0.8)
    raises = [item for item in guarded if item[0].type == ActionType.RAISE]
    assert len(raises) == 2
    assert raises[0][1] == pytest.approx(0.8)
    assert raises[1][1] == pytest.approx(0.1)
    assert _prob(guarded, ActionType.FOLD) == pytest.approx(0.1)
    assert _prob(guarded, ActionType.CALL) == 0.0
    assert _mode_action(guarded).type == ActionType.RAISE
    assert _mode_action(guarded).amount == 40


def test_negative_call_ev_does_not_invent_a_fold_when_a_raise_exists() -> None:
    baseline = [
        (Action(ActionType.CALL), 0.7),
        (Action(ActionType.RAISE, 40), 0.3),
    ]
    guarded = _guard_call(baseline, -1.0, equity=0.8)
    assert _prob(guarded, ActionType.FOLD) == 0.0
    assert _prob(guarded, ActionType.CALL) == 0.0
    assert _prob(guarded, ActionType.RAISE) == pytest.approx(1.0)


def test_non_negative_call_ev_keeps_the_call() -> None:
    baseline = [(Action(ActionType.CALL), 1.0)]
    assert _guard_call(baseline, 0.0) == baseline
    assert _guard_call(baseline, None) == baseline
    assert _guard_call(baseline, -1.0, to_call=0) == baseline


def test_negative_raise_stays_when_equity_is_not_below_fair_share() -> None:
    # 份额不低于平均时，负期望跟注并入已有加注，加注成为唯一质量。
    baseline = [
        (Action(ActionType.RAISE, 40), 0.6),
        (Action(ActionType.CALL), 0.4),
    ]
    fair = _fair_share(1)
    guarded = _guard_call(baseline, -5.0, equity=fair)
    assert _prob(guarded, ActionType.RAISE) == pytest.approx(1.0)
    assert _prob(guarded, ActionType.CALL) == 0.0
    assert _prob(guarded, ActionType.FOLD) == 0.0
    assert _mode_action(guarded).type == ActionType.RAISE


def test_negative_raise_moves_to_fold_when_equity_is_below_fair_share() -> None:
    # 份额低于平均时，跟注和加注都归并到同一条弃牌，归并完再取众数。
    baseline = [
        (Action(ActionType.RAISE, 40), 0.34),
        (Action(ActionType.RAISE, 80), 0.33),
        (Action(ActionType.CALL), 0.33),
    ]
    guarded = _guard_call(baseline, -5.0, equity=_fair_share(1) - 0.01)
    assert len(guarded) == 1
    assert guarded[0][0].type == ActionType.FOLD
    assert guarded[0][1] == pytest.approx(1.0)
    assert _mode_action(guarded).type == ActionType.FOLD


def test_mode_action_groups_split_raise_sizes() -> None:
    # 单个跟注桶高于任一加注尺度，但加注合计更高时，众数仍是加注里最大的那一档。
    baseline = [
        (Action(ActionType.CALL), 0.375),
        (Action(ActionType.RAISE, 50), 0.312),
        (Action(ActionType.RAISE, 60), 0.250),
        (Action(ActionType.RAISE, 80), 0.063),
    ]
    chosen = _mode_action(baseline)
    assert chosen.type == ActionType.RAISE
    assert chosen.amount == 50


def test_cheap_preflop_keeps_a_small_negative_call_without_aggression() -> None:
    # 翻前只补盲、负期望还没到错误容差、又没有加注质量时，跟注留下来。
    baseline = [
        (Action(ActionType.FOLD), 0.4),
        (Action(ActionType.CALL), 0.6),
    ]
    guarded = _guard_call(
        baseline,
        -1.0,
        to_call=20,
        equity=0.4,
        opponents=5,
        postflop=False,
        big_blind=20,
        contested=30,
    )
    assert guarded == baseline
    # 负期望已经超过容差时，仍把跟注并入弃牌。
    folded = _guard_call(
        baseline,
        -21.0,
        to_call=20,
        equity=0.4,
        opponents=5,
        postflop=False,
        big_blind=20,
        contested=30,
    )
    assert _prob(folded, ActionType.CALL) == 0.0
    assert _prob(folded, ActionType.FOLD) == pytest.approx(1.0)


def test_low_equity_lead_moves_aggression_onto_check() -> None:
    baseline = [
        (Action(ActionType.BET, 180), 0.41),
        (Action(ActionType.CHECK), 0.24),
        (Action(ActionType.RAISE, 400), 0.35),
    ]
    # 单挑空气线是 0.25。低于这条线时，主动质量收进已有的过牌。
    below_air = _guard_low_equity_lead(
        baseline,
        to_call=0,
        postflop=True,
        equity=0.18,
        opponents=1,
        max_line=0,
    )
    checks = [item for item in below_air if item[0].type == ActionType.CHECK]
    assert len(checks) == 1
    assert checks[0][1] == pytest.approx(1.0)
    assert _mode_action(below_air).type == ActionType.CHECK
    # 份额高于空气线、但行动线已经偏高且低于平均时，同样收成过牌。
    high_line = _guard_low_equity_lead(
        baseline,
        to_call=0,
        postflop=True,
        equity=0.33,
        opponents=1,
        max_line=3,
    )
    assert _prob(high_line, ActionType.CHECK) == pytest.approx(1.0)
    assert len([item for item in high_line if item[0].type == ActionType.CHECK]) == 1


def test_thin_value_and_preflop_leads_stay() -> None:
    baseline = [
        (Action(ActionType.BET, 40), 0.6),
        (Action(ActionType.CHECK), 0.4),
    ]
    # 单挑份额约三分之一、行动线只有溜入档，主动下注保留。
    thin = _guard_low_equity_lead(
        baseline,
        to_call=0,
        postflop=True,
        equity=0.33,
        opponents=1,
        max_line=1,
    )
    assert thin == baseline
    preflop = _guard_low_equity_lead(
        [(Action(ActionType.RAISE, 60), 1.0)],
        to_call=0,
        postflop=False,
        equity=0.2,
        opponents=3,
        max_line=0,
    )
    assert preflop == [(Action(ActionType.RAISE, 60), 1.0)]
    facing = _guard_low_equity_lead(
        baseline,
        to_call=20,
        postflop=True,
        equity=0.1,
        opponents=1,
        max_line=5,
    )
    assert facing == baseline


def test_bad_fold_probe_moves_fold_mass_onto_call() -> None:
    hole = [card("2c"), card("3d")]
    board = [card("7c"), card("Ah"), card("8h"), card("9c"), card("8s")]
    shared = {
        "equity": 0.64,
        "call_ev": 200.0,
        "pot_odds": 0.2,
        "to_call": 100,
        "actual_call": 100,
        "pot": 400,
        "contested": 500,
        "can_raise": True,
        "opponents": 1,
        "hole_cards": hole,
        "board": board,
        "big_blind": 20,
    }
    assert _folding_gives_up_value(**shared) is True
    baseline = [
        (Action(ActionType.FOLD), 0.7),
        (Action(ActionType.CALL), 0.3),
    ]
    guarded = _guard_reference_distribution(
        baseline,
        to_call=100,
        call_ev=200.0,
        equity=0.64,
        opponents=1,
        postflop=True,
        max_line=0,
        bad_fold=True,
    )
    calls = [item for item in guarded if item[0].type == ActionType.CALL]
    assert len(calls) == 1
    assert calls[0][1] == pytest.approx(1.0)
    assert _mode_action(guarded).type == ActionType.CALL
    # 翻前补盲这种廉价正期望，探针不触发，弃牌保留。
    assert (
        _folding_gives_up_value(
            equity=0.30,
            call_ev=4.0,
            pot_odds=0.25,
            to_call=10,
            actual_call=10,
            pot=30,
            contested=40,
            can_raise=True,
            opponents=1,
            hole_cards=[card("7c"), card("2d")],
            board=[],
            big_blind=20,
        )
        is False
    )


def test_review_equity_ignores_opponent_hole_cards() -> None:
    # 换掉对手底牌后，同一条公开行动线上的份额与跟注期望不变。
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
    original = _review_for(hole, board, moves)
    swapped = _review_for(
        {0: [card("As"), card("Ad")], 1: [card("Ks"), card("Qh")]},
        board,
        moves,
    )
    assert [item["equity"] for item in original["decisions"]] == [
        item["equity"] for item in swapped["decisions"]
    ]
    assert [item["call_ev"] for item in original["decisions"]] == [
        item["call_ev"] for item in swapped["decisions"]
    ]


def _player(seat: int, hole: str, stack: int, *, human: bool = False) -> dict:
    return {
        "seat": seat,
        "name": f"玩家{seat}",
        "is_human": human,
        "hole_cards": hole.split(),
        "starting_stack": stack,
    }


def test_reference_raise_is_published_as_chips_added() -> None:
    # 策略内部的加注额是本街总额；对外要换成这一下投入的筹码，且不能超过剩余筹码。
    assert _reference_chips(Action(ActionType.RAISE, 1320), 200, 1280, 160) == 1120
    assert _reference_chips(Action(ActionType.RAISE, 2000), 200, 1280, 160) == 1280
    assert _reference_chips(Action(ActionType.BET, 1480), 0, 1480, 160) == 1480


def test_reference_call_uses_the_actual_payment() -> None:
    # 候选里的跟注额是 0。对外改成当时实际要付的筹码，短码不能超过剩余筹码。
    assert _reference_chips(Action(ActionType.CALL, 0), 40, 500, 160) == 160
    assert _reference_chips(Action(ActionType.CALL, 0), 40, 100, 160) == 100
    assert _reference_chips(Action(ActionType.FOLD), 40, 500, 160) == 0
    mode = Action(ActionType.CALL, 0)
    published, rows = _publish_reference(
        [(mode, 0.55), (Action(ActionType.FOLD), 0.45)],
        mode,
        40,
        500,
        160,
    )
    assert published == {"action": "call", "amount": 160}
    assert rows[0]["action"] == "call"
    assert rows[0]["amount"] == 160


def test_all_in_reraise_reference_does_not_spend_more_than_the_stack() -> None:
    # 真人翻牌加注到全下后，参考加注若仍用本街总额，会比剩余筹码多出一截。
    history = {
        "hand_number": 36,
        "num_players": 6,
        "small_blind": 10,
        "big_blind": 20,
        "button": 5,
        "board": ["Kh", "8h", "9h", "7s", "4h"],
        "players": [
            _player(0, "Th Ah", 1500, human=True),
            _player(1, "7c 2d", 1960),
            _player(2, "Qs Kd", 1970),
            _player(3, "8c 4c", 2180),
            _player(4, "Js Ac", 3000),
            _player(5, "Ks Tc", 1390),
        ],
        "actions": [
            {"street": "preflop", "seat": 0, "action": "small_blind", "amount": 10},
            {"street": "preflop", "seat": 1, "action": "big_blind", "amount": 20},
            {"street": "preflop", "seat": 2, "action": "call", "amount": 20},
            {"street": "preflop", "seat": 3, "action": "fold", "amount": 0},
            {"street": "preflop", "seat": 4, "action": "call", "amount": 20},
            {"street": "preflop", "seat": 5, "action": "call", "amount": 20},
            {"street": "preflop", "seat": 0, "action": "call", "amount": 10},
            {"street": "preflop", "seat": 1, "action": "check", "amount": 0},
            {"street": "flop", "seat": 0, "action": "bet", "amount": 200},
            {"street": "flop", "seat": 1, "action": "fold", "amount": 0},
            {"street": "flop", "seat": 2, "action": "call", "amount": 200},
            {"street": "flop", "seat": 4, "action": "fold", "amount": 0},
            {"street": "flop", "seat": 5, "action": "raise", "amount": 730},
            {"street": "flop", "seat": 0, "action": "raise", "amount": 1280},
            {"street": "flop", "seat": 2, "action": "call", "amount": 1280},
            {"street": "flop", "seat": 5, "action": "call", "amount": 640},
        ],
    }
    review = build_review(history)
    all_in = review["decisions"][2]
    assert all_in["action"] == {"action": "raise", "amount": 1280}
    assert all_in["stack_after"] == 0
    assert all_in["bot_action"]["action"] == "raise"
    assert all_in["bot_action"]["amount"] == 1120
    stack_before = all_in["stack_after"] + all_in["action"]["amount"]
    for item in all_in["bot_distribution"]:
        if item["action"] in ("bet", "raise", "call"):
            assert item["amount"] <= stack_before


def test_review_reference_is_unchanged_when_only_the_hand_number_changes() -> None:
    # 同一局面只改手号时，参考动作和分布必须完全一样，不能随设伏抽签变动。
    hole = {0: [card("Ah"), card("Kh")], 1: [card("2c"), card("3d")]}
    board = [card(s) for s in ("As", "Kd", "7c", "2h", "9s")]
    moves = [(ActionType.CALL, 0), *([(ActionType.CHECK, 0)] * 7)]
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(button=1, hole_cards=hole, board=board)
    for action_type, amount in moves:
        _apply(engine, action_type, amount)
    assert engine.hand_over
    reviews = [
        build_review(build_hand_history(engine, hand_number=number, human_seat=0))
        for number in (1, 2, 7, 24, 88)
    ]
    first = reviews[0]["decisions"]
    for review in reviews[1:]:
        assert review["hand_number"] != reviews[0]["hand_number"]
        for left, right in zip(first, review["decisions"], strict=True):
            assert left["bot_action"] == right["bot_action"]
            assert left["bot_distribution"] == right["bot_distribution"]


# 新先验下六手标杆的份额与参考众数。翻前与有效分对齐；翻后高行动线不再被未击中的口袋对抬高。
_CASE_READINGS = {
    "555285f9dc2242649a2cf90134435823": (
        (0, "preflop", "raise", 0.6300, None),
        (1, "flop", "check", 0.4875, None),
        (2, "turn", "check", 0.3435, None),
        (3, "river", "check", 0.2700, None),
    ),
    "9b32cc7c8f804678a9e00de183a3b231": (
        (0, "preflop", "raise", 0.4007, 8.05),
        (1, "preflop", "raise", 0.3231, 58.31),
    ),
    "76a53e0e04dd4325b26db042c7eb2666": (
        (0, "preflop", "fold", 0.4712, 3.56),
        (1, "flop", "bet", 0.6460, None),
        (2, "flop", "fold", 0.2365, -34.66),
    ),
    "08985a8d951045fd8224beb2e61cc6b2": (
        (0, "preflop", "raise", 0.5232, 6.16),
        (2, "turn", "fold", 0.1245, -18.88),
    ),
    "1cdb17a81ae84222841ddd8aa0979d8f": (
        (0, "preflop", "call", 0.5182, 5.91),
    ),
    "af81bfa4db0d44589f5e42ab3dcc7feb": (
        (0, "preflop", "raise", 0.5331, 6.66),
    ),
}


def test_case_hands_keep_the_calibrated_action_line_shares() -> None:
    """六手标杆的份额与参考众数落在新先验上，翻后面对下注不再被误抬成加注或跟注。"""
    connection = connect_readonly()
    try:
        for hand_id, expected in _CASE_READINGS.items():
            history = load_history(connection, hand_id)
            assert history is not None
            report = diagnose_history(history, hand_id=hand_id)
            assert report.get("error") is None
            points = {point["action_index"]: point for point in report["decisions"]}
            for index, street, mode, equity, call_ev in expected:
                point = points[index]
                assert point["street"] == street
                assert point["mode"] == mode
                assert round(point["equity"], 4) == equity
                if call_ev is None:
                    assert point["call_ev"] is None
                else:
                    assert point["call_ev"] == pytest.approx(call_ev, abs=0.01)
            codes = {code for point in report["decisions"] for code in point["contradictions"]}
            assert "c_preflop_free_raise" not in codes
            assert "b_postflop" not in codes
    finally:
        connection.close()
