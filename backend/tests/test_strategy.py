"""策略层测试：随机策略合法/可复现，启发式策略强弱牌动作倾向，双 Bot 引擎闭环。"""

from app.poker.actions import ActionType, LegalActions
from app.poker.engine import PokerEngine
from app.poker.state import GameState, PlayerState, Street
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.random_strategy import RandomStrategy

from .helpers import cards


def _hero_state(hole, board=(), street=Street.PREFLOP, pot=100) -> GameState:
    hero = PlayerState(seat=0, name="p0", hole_cards=list(hole))
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
