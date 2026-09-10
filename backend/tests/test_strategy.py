"""策略层测试：随机策略合法/可复现，启发式策略强弱牌动作倾向，双 Bot 引擎闭环。"""

from app.poker.actions import ActionType, LegalActions
from app.poker.engine import PokerEngine
from app.poker.state import GameState, PlayerState, Street
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.random_strategy import RandomStrategy

from .helpers import cards


def _hero_state(hole, board=(), street=Street.PREFLOP, pot=100, stack=0) -> GameState:
    hero = PlayerState(seat=0, name="p0", hole_cards=list(hole), stack=stack)
    return GameState(
        street=street,
        board=tuple(board),
        pot=pot,
        current_seat=0,
        button=0,
        hand_over=False,
        players=(hero,),
    )


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


# ------------------------------------------------------------------ 随机策略


def test_random_reproducible() -> None:
    state = _hero_state(cards("As Ah"))
    legal = _legal(can_call=True, call_amount=10, can_raise=True, min_raise_to=20, max_raise_to=100)
    a = RandomStrategy(seed=7)
    b = RandomStrategy(seed=7)
    assert [a.choose_action(state, legal) for _ in range(50)] == [
        b.choose_action(state, legal) for _ in range(50)
    ]


def test_random_only_legal() -> None:
    state = _hero_state(cards("As Ah"))
    legal = _legal(
        can_check=True,
        can_call=True,
        call_amount=10,
        can_bet=True,
        min_bet=10,
        max_bet=500,
        can_raise=True,
        min_raise_to=20,
        max_raise_to=1000,
    )
    bot = RandomStrategy(seed=1)
    for _ in range(500):
        action = bot.choose_action(state, legal)
        assert action.type in {
            ActionType.FOLD,
            ActionType.CHECK,
            ActionType.CALL,
            ActionType.BET,
            ActionType.RAISE,
        }
        if action.type == ActionType.BET:
            assert 10 <= action.amount <= 500
        if action.type == ActionType.RAISE:
            assert 20 <= action.amount <= 1000


# ------------------------------------------------------------------ 启发式策略：翻牌前


def test_heuristic_preflop_strong_raises() -> None:
    state = _hero_state(cards("As Ah"), street=Street.PREFLOP)
    legal = _legal(
        can_call=True, call_amount=10, can_raise=True, min_raise_to=20, max_raise_to=1000
    )
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.RAISE
    assert 20 <= action.amount <= 1000


def test_heuristic_preflop_medium_calls() -> None:
    state = _hero_state(cards("Ts 9s"), street=Street.PREFLOP)
    legal = _legal(can_call=True, call_amount=10)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CALL


def test_heuristic_preflop_weak_folds() -> None:
    state = _hero_state(cards("7d 2c"), street=Street.PREFLOP)
    legal = _legal(can_call=True, call_amount=10)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.FOLD


def test_heuristic_preflop_small_pair_set_mines() -> None:
    # 小对子在隐含赔率足够时跟注博暗三条，而非直接弃牌。
    state = _hero_state(cards("5s 5d"), street=Street.PREFLOP, pot=100, stack=1000)
    legal = _legal(can_call=True, call_amount=10)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CALL


def test_heuristic_preflop_small_pair_folds_big_raise() -> None:
    # 小对子面对过大的下注，隐含赔率不足，仍应弃牌。
    state = _hero_state(cards("5s 5d"), street=Street.PREFLOP, pot=100, stack=1000)
    legal = _legal(can_call=True, call_amount=100)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.FOLD


def test_heuristic_preflop_small_pair_checks_when_free() -> None:
    state = _hero_state(cards("5s 5d"), street=Street.PREFLOP, pot=100, stack=1000)
    legal = _legal(can_check=True)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CHECK


def test_heuristic_preflop_speculative_calls_small() -> None:
    # 同花隔张等投机边缘牌面对小注允许便宜入池。
    state = _hero_state(cards("Ts 8s"), street=Street.PREFLOP, pot=100)
    legal = _legal(can_call=True, call_amount=20)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CALL


def test_heuristic_preflop_speculative_folds_big() -> None:
    # 投机边缘牌面对超过半个底池的下注仍应弃牌。
    state = _hero_state(cards("Ts 8s"), street=Street.PREFLOP, pot=100)
    legal = _legal(can_call=True, call_amount=60)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.FOLD


def test_heuristic_preflop_medium_folds_big() -> None:
    # 中等牌面对超底池巨注不再无条件跟注。
    state = _hero_state(cards("Ts 9s"), street=Street.PREFLOP, pot=100)
    legal = _legal(can_call=True, call_amount=200)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.FOLD


def test_heuristic_preflop_ace_high_calls() -> None:
    # A 配大踢脚（ATo）不再被过早弃掉，面对常规加注可跟注。
    state = _hero_state(cards("Ah Td"), street=Street.PREFLOP, pot=100)
    legal = _legal(can_call=True, call_amount=80)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CALL


def test_heuristic_preflop_ace_high_folds_big() -> None:
    # A 高牌面对超底池巨注仍应弃牌。
    state = _hero_state(cards("Ah Td"), street=Street.PREFLOP, pot=100)
    legal = _legal(can_call=True, call_amount=200)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.FOLD


# ------------------------------------------------------------------ 启发式策略：翻牌后


def test_heuristic_postflop_strong_bets() -> None:
    state = _hero_state(cards("As Ah"), board=cards("Ad 7c 2s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.BET
    assert 10 <= action.amount <= 1000


def test_heuristic_postflop_medium_calls() -> None:
    state = _hero_state(cards("As 7h"), board=cards("Ad Kc 2s"), street=Street.FLOP)
    legal = _legal(can_call=True, call_amount=20)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CALL


def test_heuristic_postflop_weak_folds() -> None:
    state = _hero_state(cards("2c 7d"), board=cards("As Kc 9s"), street=Street.FLOP)
    legal = _legal(can_call=True, call_amount=20)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.FOLD


def test_heuristic_weak_checks_when_free() -> None:
    state = _hero_state(cards("2c 7d"), board=cards("As Kc 9s"), street=Street.FLOP)
    legal = _legal(can_check=True)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CHECK


def test_heuristic_postflop_flush_draw_calls() -> None:
    # 同花听牌不再被当作纯空气弃牌，面对合理下注可跟注。
    state = _hero_state(cards("Ts 9s"), board=cards("As Ks 2d"), street=Street.FLOP)
    legal = _legal(can_call=True, call_amount=20)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CALL


def test_heuristic_postflop_straight_draw_calls() -> None:
    # 两头顺面对合理下注可跟注。
    state = _hero_state(cards("7s 8d"), board=cards("9c Th 2s"), street=Street.FLOP)
    legal = _legal(can_call=True, call_amount=20)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CALL


def test_heuristic_postflop_combo_draw_semibluffs() -> None:
    # 组合听牌（同花 + 两头顺）主动半诈唬下注。
    state = _hero_state(cards("Js Ts"), board=cards("Qs 9s 2d"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.BET
    assert 10 <= action.amount <= 1000


def test_heuristic_postflop_draw_folds_big() -> None:
    # 听牌面对超过赔率上限的巨注仍应弃牌。
    state = _hero_state(cards("Ts 9s"), board=cards("As Ks 2d"), street=Street.FLOP)
    legal = _legal(can_call=True, call_amount=150)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.FOLD


def test_heuristic_postflop_medium_folds_big() -> None:
    # 一对面对超底池巨注不再无条件跟注。
    state = _hero_state(cards("As 7h"), board=cards("Ad Kc 2s"), street=Street.FLOP)
    legal = _legal(can_call=True, call_amount=200)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.FOLD


def test_heuristic_postflop_top_pair_bets() -> None:
    # 顶对在无人下注时主动价值下注，而非过牌。
    state = _hero_state(cards("Ah 7d"), board=cards("Ad 8c 2s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.BET
    assert 10 <= action.amount <= 1000


def test_heuristic_postflop_two_pair_bets() -> None:
    # 两对主动价值下注。
    state = _hero_state(cards("Ah 8d"), board=cards("Ad 8c 2s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.BET
    assert 10 <= action.amount <= 1000


def test_heuristic_postflop_middle_pair_checks() -> None:
    # 中/底对控池过牌，不盲目下注。
    state = _hero_state(cards("8d 7h"), board=cards("Ad Kc 8s"), street=Street.FLOP)
    legal = _legal(can_check=True)
    assert HeuristicStrategy().choose_action(state, legal).type == ActionType.CHECK


def test_heuristic_postflop_board_trips_calls_not_raises() -> None:
    # 公共牌三条（翻牌 AAA）时底牌只是踢脚，面对加注只跟注，不再无限加注。
    state = _hero_state(cards("Kh 8d"), board=cards("As Ah Ad"), street=Street.FLOP)
    legal = _legal(
        can_call=True, call_amount=20, can_raise=True, min_raise_to=40, max_raise_to=1000
    )
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.CALL


def test_heuristic_postflop_full_house_raises() -> None:
    # 葫芦面对加注仍可激进加注。
    state = _hero_state(cards("3s 3c"), board=cards("As Ah Ad"), street=Street.FLOP)
    legal = _legal(
        can_call=True, call_amount=20, can_raise=True, min_raise_to=40, max_raise_to=1000
    )
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.RAISE
    assert 40 <= action.amount <= 1000


def test_heuristic_postflop_trips_bets_when_unopened() -> None:
    # 三条在无人下注时仍主动价值下注。
    state = _hero_state(cards("Kh 8d"), board=cards("As Ah Ad"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.BET
    assert 10 <= action.amount <= 1000


def test_heuristic_postflop_board_trips_folds_big() -> None:
    # 公共牌三条（翻牌 AAA）：底牌只是踢脚，面对巨注弃牌（对手很可能成葫芦）。
    state = _hero_state(cards("Kh 8d"), board=cards("As Ah Ad"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=200)
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.FOLD


def test_heuristic_postflop_set_calls_big() -> None:
    # 底牌击中的三条（set）才是真强牌，面对巨注仍跟注。
    state = _hero_state(cards("3s 3c"), board=cards("3d Kc 2s"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=200)
    action = HeuristicStrategy().choose_action(state, legal)
    assert action.type == ActionType.CALL


# ------------------------------------------------------------------ 引擎闭环


def test_two_heuristic_bots_complete_hands() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    bot = HeuristicStrategy()
    for _ in range(200):
        engine.start_hand()
        total = sum(p.stack for p in engine.players) + engine.pot
        actions = 0
        while not engine.hand_over:
            assert actions < 1000, "单手动作数超限，疑似死锁"
            action = bot.choose_action(engine.snapshot(), engine.legal_actions())
            engine.apply_action(action)  # 非法动作会抛异常
            actions += 1
        assert sum(p.stack for p in engine.players) == total
        assert sum(engine.last_net.values()) == 0
