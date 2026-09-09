"""随机对局仿真：大量手牌验证无非法动作、无重复发牌、无死锁且筹码守恒。"""

import random

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.engine import PokerEngine
from app.poker.state import Street


def _rand_amount(lo: int, hi: int, rng: random.Random) -> int:
    """在 [lo, hi] 内采样，并偏向边界以频繁触发全下与最小加注。"""
    roll = rng.random()
    if roll < 0.34:
        return lo
    if roll < 0.67:
        return hi
    return rng.randint(lo, hi)


def _random_action(engine: PokerEngine, legal: LegalActions, rng: random.Random) -> Action:
    options: list[tuple[float, Action]] = []
    if legal.can_fold:
        options.append((1.0, Action(ActionType.FOLD)))
    if legal.can_check:
        options.append((3.0, Action(ActionType.CHECK)))
    if legal.can_call:
        options.append((3.0, Action(ActionType.CALL)))
    if legal.can_bet:
        options.append(
            (3.0, Action(ActionType.BET, _rand_amount(legal.min_bet, legal.max_bet, rng)))
        )
    if legal.can_raise:
        amount = _rand_amount(legal.min_raise_to, legal.max_raise_to, rng)
        options.append((3.0, Action(ActionType.RAISE, amount)))
    assert options, "当前无任何合法动作"
    actions = [a for _, a in options]
    weights = [w for w, _ in options]
    return rng.choices(actions, weights=weights, k=1)[0]


def _assert_state_sane(engine: PokerEngine) -> None:
    for p in engine.players:
        assert p.stack >= 0
        assert p.street_bet >= 0
        assert p.total_committed >= 0
        if not p.all_in:
            assert p.street_bet <= engine.current_bet
    assert engine.current_bet >= 0
    assert engine.min_raise >= 1
    if engine.street == Street.FLOP:
        assert len(engine.board) == 3
    elif engine.street == Street.TURN:
        assert len(engine.board) == 4
    elif engine.street in (Street.RIVER, Street.SHOWDOWN):
        assert len(engine.board) == 5


def _simulate(num_players: int, num_hands: int, seed: int) -> tuple[int, int]:
    engine = PokerEngine(
        num_players=num_players,
        small_blind=5,
        big_blind=10,
        starting_stack=1000,
        seed=seed,
    )
    rng = random.Random(seed)
    showdowns = 0
    for _ in range(num_hands):
        engine.start_hand()
        total_start = sum(p.stack for p in engine.players) + engine.pot
        actions = 0
        while not engine.hand_over:
            assert actions < 1000, "单手动作数超限，疑似死锁"
            # 校验已发出的牌无重复。
            dealt = [c for p in engine.players for c in p.hole_cards] + engine.board
            assert len(dealt) == len(set(dealt)), "重复发牌"
            action = _random_action(engine, engine.legal_actions(), rng)
            engine.apply_action(action)
            actions += 1
            _assert_state_sane(engine)
        assert sum(p.stack for p in engine.players) == total_start, "筹码不守恒"
        assert sum(engine.last_net.values()) == 0, "盈亏未归零"
        if engine.street == Street.SHOWDOWN:
            showdowns += 1
            assert len(engine.board) == 5
    return num_hands, showdowns


def test_heads_up_10000_hands() -> None:
    total, showdowns = _simulate(num_players=2, num_hands=10000, seed=0)
    assert total == 10000
    # 随机对局应覆盖到相当数量的摊牌，保证街流转与结算被充分触发。
    assert showdowns > 0


def test_multi_player_side_pot_stress() -> None:
    # 多人对局会频繁触发边池，验证按 N 人设计正确。
    _simulate(num_players=3, num_hands=3000, seed=1)
    _simulate(num_players=5, num_hands=2000, seed=2)
