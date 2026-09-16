"""策略层测试：随机策略合法/可复现，启发式策略强弱牌动作倾向，双 Bot 引擎闭环。"""

import pytest

import app.strategy.heuristic as heuristic_module
from app.poker.actions import Action, ActionType, LegalActions
from app.poker.engine import PokerEngine
from app.poker.state import GameState, PlayerState, Street
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.random_strategy import RandomStrategy

from .helpers import cards


def _hero_state(hole, board=(), street=Street.PREFLOP, pot=100, stack=0, opponents=1) -> GameState:
    hero = PlayerState(seat=0, name="p0", hole_cards=list(hole), stack=stack)
    players = [hero]
    for i in range(opponents):
        players.append(PlayerState(seat=i + 1, name=f"p{i + 1}"))
    return GameState(
        street=street,
        board=tuple(board),
        pot=pot,
        current_seat=0,
        button=0,
        hand_over=False,
        players=tuple(players),
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


def _bot(seed: int = 0, samples: int = 2000, bluff_freq: float = 0.0) -> HeuristicStrategy:
    # 翻牌后测试默认关闭诈唬并提高采样数，以隔离并稳定地验证胜率/赔率决策本身。
    return HeuristicStrategy(seed=seed, samples=samples, bluff_freq=bluff_freq)


def test_postflop_monster_bets() -> None:
    # 三条等强成牌在无人下注时主动价值下注。
    state = _hero_state(cards("As Ah"), board=cards("Ad 7c 2s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    action = _bot().choose_action(state, legal)
    assert action.type == ActionType.BET
    assert 10 <= action.amount <= 1000


def test_postflop_top_pair_bets() -> None:
    # 顶对在无人下注时主动价值下注。
    state = _hero_state(cards("Ah 7d"), board=cards("Ad 8c 2s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    assert _bot().choose_action(state, legal).type == ActionType.BET


def test_postflop_two_pair_bets() -> None:
    # 两对主动价值下注。
    state = _hero_state(cards("Ah 8d"), board=cards("Ad 8c 2s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    assert _bot().choose_action(state, legal).type == ActionType.BET


def test_postflop_set_bets_when_unopened() -> None:
    # 底牌击中的三条（set）无人下注时主动下注。
    state = _hero_state(cards("3s 3c"), board=cards("3d Kc 2s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    assert _bot().choose_action(state, legal).type == ActionType.BET


def test_postflop_board_trips_checks_when_unopened() -> None:
    # 公共牌三条（如 AAA）时底牌只是踢脚，胜率不高，应控池过牌而非盲目下注。
    state = _hero_state(cards("Kh 8d"), board=cards("As Ah Ad"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    assert _bot().choose_action(state, legal).type == ActionType.CHECK


def test_postflop_middle_pair_checks() -> None:
    # 中/底对控池过牌，不盲目下注。
    state = _hero_state(cards("8d 7h"), board=cards("Ad Kc 8s"), street=Street.FLOP)
    legal = _legal(can_check=True)
    assert _bot().choose_action(state, legal).type == ActionType.CHECK


def test_postflop_combo_draw_semibluffs() -> None:
    # 组合听牌（同花 + 两头顺）无人下注时半诈唬下注。
    state = _hero_state(cards("Js Ts"), board=cards("Qs 9s 2d"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    assert _bot().choose_action(state, legal).type == ActionType.BET


def test_postflop_weak_checks_when_free() -> None:
    # 纯空气免费看牌时过牌（默认关闭诈唬）。
    state = _hero_state(cards("2c 7d"), board=cards("As Kc 9s"), street=Street.FLOP)
    legal = _legal(can_check=True)
    assert _bot().choose_action(state, legal).type == ActionType.CHECK


def test_postflop_multiway_decay_checks() -> None:
    # 同样的顶对在多人底池下胜率衰减，不再盲目价值下注。
    state = _hero_state(
        cards("Ah Kd"), board=cards("Ad 8c 2s"), street=Street.FLOP, opponents=4
    )
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    assert _bot().choose_action(state, legal).type == ActionType.CHECK


def test_postflop_top_pair_calls() -> None:
    # 顶对面对合理下注按赔率跟注。
    state = _hero_state(cards("As 7h"), board=cards("Ad Kc 2s"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=20)
    assert _bot().choose_action(state, legal).type == ActionType.CALL


def test_postflop_air_folds_to_bet() -> None:
    # 纯空气面对下注弃牌。
    state = _hero_state(cards("2c 7d"), board=cards("As Kc 9s"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=20)
    assert _bot().choose_action(state, legal).type == ActionType.FOLD


def test_postflop_flush_draw_calls() -> None:
    # 同花听牌面对合理下注按赔率跟注。
    state = _hero_state(cards("Ts 9s"), board=cards("As Ks 2d"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=20)
    assert _bot().choose_action(state, legal).type == ActionType.CALL


def test_postflop_straight_draw_calls() -> None:
    # 两头顺面对合理下注按赔率跟注。
    state = _hero_state(cards("7s 8d"), board=cards("9c Th 2s"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=20)
    assert _bot().choose_action(state, legal).type == ActionType.CALL


def test_postflop_draw_folds_big() -> None:
    # 听牌面对超过赔率的巨注弃牌。
    state = _hero_state(cards("Ts 9s"), board=cards("As Ks 2d"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=200)
    assert _bot().choose_action(state, legal).type == ActionType.FOLD


def test_postflop_middle_pair_folds_big() -> None:
    # 中对面对超底池巨注胜率不足，弃牌。
    state = _hero_state(cards("8d 7h"), board=cards("Ad Kc 8s"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=300)
    assert _bot().choose_action(state, legal).type == ActionType.FOLD


def test_postflop_set_calls_big() -> None:
    # 底牌击中的三条（set）面对巨注仍跟注。
    state = _hero_state(cards("3s 3c"), board=cards("3d Kc 2s"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=200)
    assert _bot().choose_action(state, legal).type == ActionType.CALL


def test_postflop_board_trips_calls_not_raises() -> None:
    # 公共牌三条面对下注只跟注（胜率不足以再加注）。
    state = _hero_state(cards("Kh 8d"), board=cards("As Ah Ad"), street=Street.FLOP, pot=100)
    legal = _legal(
        can_call=True, call_amount=20, can_raise=True, min_raise_to=40, max_raise_to=1000
    )
    assert _bot().choose_action(state, legal).type == ActionType.CALL


def test_postflop_set_raises() -> None:
    # 底牌击中的三条（set）面对下注可再加注。
    state = _hero_state(cards("3s 3c"), board=cards("3d Kc 2s"), street=Street.FLOP, pot=100)
    legal = _legal(
        can_call=True, call_amount=20, can_raise=True, min_raise_to=40, max_raise_to=1000
    )
    action = _bot().choose_action(state, legal)
    assert action.type == ActionType.RAISE
    assert 40 <= action.amount <= 1000


def test_postflop_weak_full_house_does_not_raise() -> None:
    # 公共牌三条下的低对子葫芦胜率不高，面对下注只跟注不加注。
    state = _hero_state(cards("3s 3c"), board=cards("As Ah Ad"), street=Street.FLOP, pot=100)
    legal = _legal(
        can_call=True, call_amount=20, can_raise=True, min_raise_to=40, max_raise_to=1000
    )
    assert _bot().choose_action(state, legal).type == ActionType.CALL


def test_postflop_bluffs_air_when_enabled() -> None:
    # 开启诈唬后，纯空气在无人下注时会下注诈唬。
    state = _hero_state(cards("2c 7d"), board=cards("As Kc 9s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    assert _bot(bluff_freq=1.0).choose_action(state, legal).type == ActionType.BET


def test_postflop_no_bluff_when_disabled() -> None:
    # 关闭诈唬后，纯空气只过牌。
    state = _hero_state(cards("2c 7d"), board=cards("As Kc 9s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    assert _bot(bluff_freq=0.0).choose_action(state, legal).type == ActionType.CHECK


def test_heuristic_distribution_air_bluff_mixed() -> None:
    # 纯空气无人下注：分布按下注频率配比下注与过牌，是策略里唯一的混合分支。
    state = _hero_state(cards("2c 7d"), board=cards("As Kc 9s"), street=Street.FLOP)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    bot = HeuristicStrategy(seed=0, samples=500, bluff_freq=0.25)
    dist = bot.action_distribution(state, legal)
    weights = {action.type: weight for action, weight in dist}
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights[ActionType.BET] == pytest.approx(0.25)
    assert weights[ActionType.CHECK] == pytest.approx(0.75)


def test_heuristic_distribution_deterministic_branch_single() -> None:
    # 面对下注的阈值分支是确定性的，分布只含一个动作（概率 1.0）。
    state = _hero_state(cards("As 7h"), board=cards("Ad Kc 2s"), street=Street.FLOP, pot=100)
    legal = _legal(can_call=True, call_amount=20)
    bot = HeuristicStrategy(seed=0, samples=500, bluff_freq=0.25)
    dist = bot.action_distribution(state, legal)
    assert len(dist) == 1
    assert dist[0][0].type == ActionType.CALL
    assert dist[0][1] == 1.0


# ------------------------------------------------------------------ 全下与争池人数


def _heads_up_all_in_engine() -> PokerEngine:
    """构造唯一对手全下、当前玩家仍可弃牌或跟注的翻牌局面。"""
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=110, seed=0)
    engine.players[1].stack = 100
    engine.start_hand_with(
        button=0,
        hole_cards={0: cards("Qh Jc"), 1: cards("2c 7d")},
        board=cards("As Kd 9s Th 3c"),
    )
    for action in (
        Action(ActionType.CALL),
        Action(ActionType.CHECK),
        Action(ActionType.CHECK),
        Action(ActionType.BET, 100),
    ):
        engine.apply_action(action)
    assert engine.street == Street.FLOP
    assert engine.current_seat == 1
    return engine


def _multiway_all_in_engine() -> PokerEngine:
    """构造全下对手与可行动对手同时存在的翻牌局面。"""
    engine = PokerEngine(3, small_blind=5, big_blind=10, starting_stack=110, seed=0)
    engine.players[1].stack = 1000
    engine.players[2].stack = 1000
    engine.start_hand_with(
        button=0,
        hole_cards={0: cards("6h 5c"), 1: cards("Qh Jc"), 2: cards("4c 3d")},
        board=cards("As Kd 9s Th 3c"),
    )
    for action in (
        Action(ActionType.CALL),
        Action(ActionType.CALL),
        Action(ActionType.CHECK),
        Action(ActionType.CHECK),
        Action(ActionType.CHECK),
        Action(ActionType.BET, 100),
    ):
        engine.apply_action(action)
    assert engine.street == Street.FLOP
    assert engine.current_seat == 1
    return engine


def _folded_opponent_flop_engine() -> PokerEngine:
    """构造含弃牌座位但没有全下座位的翻牌局面。"""
    engine = PokerEngine(4, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand_with(
        button=0,
        hole_cards={
            0: cards("As Ac"),
            1: cards("Kh Kd"),
            2: cards("Qh Qd"),
            3: cards("Jh Jd"),
        },
        board=cards("2c 7d 9h Ts 3c"),
    )
    for action in (
        Action(ActionType.FOLD),
        Action(ActionType.CALL),
        Action(ActionType.CALL),
        Action(ActionType.CHECK),
    ):
        engine.apply_action(action)
    assert engine.street == Street.FLOP
    assert engine.current_seat == 1
    return engine


def test_postflop_all_in_opponent_counts_as_contender(monkeypatch: pytest.MonkeyPatch) -> None:
    # 对手全下但未弃牌时，仍须作为随机范围竞争者参与胜率估值。
    engine = _heads_up_all_in_engine()
    seen: list[int] = []

    def fake_equity(_hole, _board, contenders, _rng, _samples) -> float:
        seen.append(contenders)
        return 0.0

    monkeypatch.setattr(heuristic_module, "equity", fake_equity)
    action = HeuristicStrategy(seed=0).choose_action(engine.snapshot(), engine.legal_actions())

    assert seen == [1]
    assert action.type == ActionType.FOLD


def test_postflop_all_in_opponent_folds_with_fixed_seed() -> None:
    # 固定种子下，低胜率底牌面对唯一全下对手不再被当作确定胜率而跟注。
    engine = _heads_up_all_in_engine()
    action = HeuristicStrategy(seed=17).choose_action(engine.snapshot(), engine.legal_actions())

    assert action.type == ActionType.FOLD


def test_postflop_counts_all_in_and_active_contenders(monkeypatch: pytest.MonkeyPatch) -> None:
    # 主池同时有全下和可行动对手时，两者都计入竞争人数；动作仍由引擎合法执行。
    engine = _multiway_all_in_engine()
    total = sum(player.stack for player in engine.players) + engine.pot
    seen: list[int] = []

    def fake_equity(_hole, _board, contenders, _rng, _samples) -> float:
        seen.append(contenders)
        return 0.0

    monkeypatch.setattr(heuristic_module, "equity", fake_equity)
    action = HeuristicStrategy(seed=0).choose_action(engine.snapshot(), engine.legal_actions())

    assert seen == [2]
    assert action.type == ActionType.FOLD
    engine.apply_action(action)
    engine.apply_action(Action(ActionType.CALL))
    assert engine.hand_over
    assert sum(player.stack for player in engine.players) == total
    assert sum(engine.last_net.values()) == 0


def test_postflop_contender_count_excludes_folded_seat(monkeypatch: pytest.MonkeyPatch) -> None:
    # 弃牌座位只留下死钱，不应作为翻后随机范围对手计数。
    engine = _folded_opponent_flop_engine()
    seen: list[int] = []

    def fake_equity(_hole, _board, contenders, _rng, _samples) -> float:
        seen.append(contenders)
        return 0.0

    monkeypatch.setattr(heuristic_module, "equity", fake_equity)
    HeuristicStrategy(seed=0, bluff_freq=0.0).action_distribution(
        engine.snapshot(), engine.legal_actions()
    )

    assert seen == [2]


# ------------------------------------------------------------------ 引擎闭环


def test_two_heuristic_bots_complete_hands() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    # 降低采样数以控制闭环测试耗时，这里只校验无非法动作 / 筹码守恒 / 无死锁。
    bot = HeuristicStrategy(seed=0, samples=200)
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
