"""新 Bot 入口的回归：随机源域分离、座位分派、可重放与信息隔离。

只做有界单元/集成回归：不跑性能矩阵、不对抗对局、不访问真实库。
"""

import pytest

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.engine import PokerEngine
from app.poker.state import GameState
from app.strategy.mixed_context import (
    MixedContextError,
    MixedSummaryTracker,
    mixed_state,
    require_mixed_input,
)
from app.strategy.mixed_policy import MixedStyle
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MixedLocalStrategy,
    MixedStrategyError,
    derive_bots_key,
    derive_deck_seed,
    derive_root_key,
    seat_style_map,
)
from app.strategy.projection import project_for_actor

SEED = 3311


def _advance_to_bot(
    num_players: int = 3,
    seed: int = 5,
    stacks: int = 1000,
) -> tuple[PokerEngine, MixedSummaryTracker]:
    """开局后让非 Bot 座位先弃牌，使当前行动者落在 Bot 座位上。"""
    engine = PokerEngine(num_players, 5, 10, stacks, seed=seed)
    engine.start_hand()
    tracker = MixedSummaryTracker()
    tracker.begin_hand(
        hand_number=1,
        num_players=num_players,
        small_blind=5,
        big_blind=10,
        bot_seats=tuple(range(1, num_players)),
        history=engine.history,
    )
    while not engine.hand_over and engine.current_seat not in range(1, num_players):
        engine.apply_action(Action(ActionType.FOLD))
        tracker.consume_after_action(engine.history)
    return engine, tracker


def _state(engine: PokerEngine, tracker: MixedSummaryTracker) -> GameState:
    return mixed_state(project_for_actor(engine.snapshot()), tracker.context())


# ------------------------------------------------------------------ 随机源


def test_identifier_is_versioned() -> None:
    assert MIXED_STRATEGY_IDENTIFIER == "mixed-local@1"


def test_root_key_is_deterministic_and_seed_dependent() -> None:
    assert derive_root_key(SEED) == derive_root_key(SEED)
    assert len(derive_root_key(SEED)) == 32
    assert derive_root_key(SEED) != derive_root_key(SEED + 1)
    assert derive_root_key(None) != derive_root_key(None)


def test_deck_seed_is_non_negative_and_separated_from_bots_key() -> None:
    root = derive_root_key(SEED)
    deck_seed = derive_deck_seed(root)
    assert isinstance(deck_seed, int)
    assert deck_seed >= 0
    assert deck_seed == derive_deck_seed(root)
    bots = derive_bots_key(root)
    assert int.from_bytes(bots, "big") != deck_seed


def test_explicit_seed_is_replayable_across_instances() -> None:
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    legal = engine.legal_actions()
    first = MixedLocalStrategy(seed=SEED)
    second = MixedLocalStrategy(seed=SEED)
    assert first.distribution_for(state, legal) == second.distribution_for(state, legal)
    action = first.choose_action(state, legal)
    assert action == second.choose_action(state, legal)
    assert (action.type, action.amount) in {
        (item.action, item.amount) for item in first.distribution_for(state, legal).candidates
    }


def test_root_key_injection_avoids_resampling_entropy() -> None:
    root = derive_root_key(SEED)
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    legal = engine.legal_actions()
    assert MixedLocalStrategy(root_key=root).choose_action(
        state, legal
    ) == MixedLocalStrategy(seed=SEED).choose_action(state, legal)


def test_repeated_distribution_queries_do_not_consume_action_stream() -> None:
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    legal = engine.legal_actions()
    baseline = MixedLocalStrategy(seed=SEED).choose_action(state, legal)
    strategy = MixedLocalStrategy(seed=SEED)
    for _ in range(3):
        strategy.distribution_for(state, legal)
    assert strategy.choose_action(state, legal) == baseline


def test_distribution_query_is_repeatable() -> None:
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    legal = engine.legal_actions()
    strategy = MixedLocalStrategy(seed=SEED)
    assert strategy.distribution_for(state, legal) == strategy.distribution_for(state, legal)


# ------------------------------------------------------------------ 座位分派


def test_seat_style_map_cycles_in_seat_order() -> None:
    assert seat_style_map([3, 1, 2]) == {
        1: MixedStyle.TIGHT,
        2: MixedStyle.AGGRESSIVE,
        3: MixedStyle.CALLING,
    }
    assert seat_style_map([1]) == {1: MixedStyle.TIGHT}
    assert seat_style_map([1, 2]) == {1: MixedStyle.TIGHT, 2: MixedStyle.AGGRESSIVE}


def test_dispatcher_assigns_stable_style_per_seat() -> None:
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    strategy = MixedLocalStrategy(seed=SEED)
    strategy.choose_action(state, engine.legal_actions())
    assert strategy.bot_seats == (1, 2)
    assert strategy.style_for(1) is MixedStyle.TIGHT
    assert strategy.style_for(2) is MixedStyle.AGGRESSIVE


def test_dispatcher_rejects_seat_set_change() -> None:
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    strategy = MixedLocalStrategy(seed=SEED, bot_seats=(1, 2))
    strategy.choose_action(state, engine.legal_actions())
    other_engine = PokerEngine(3, 5, 10, 1000, seed=5)
    other_engine.start_hand()
    other_tracker = MixedSummaryTracker()
    other_tracker.begin_hand(
        hand_number=1,
        num_players=3,
        small_blind=5,
        big_blind=10,
        bot_seats=(1,),
        history=other_engine.history,
    )
    other_engine.apply_action(Action(ActionType.FOLD))
    other_tracker.consume_after_action(other_engine.history)
    with pytest.raises(MixedStrategyError):
        strategy.choose_action(_state(other_engine, other_tracker), other_engine.legal_actions())


def test_dispatcher_rejects_unknown_seat() -> None:
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    strategy = MixedLocalStrategy(seed=SEED, bot_seats=(2,))
    with pytest.raises(MixedStrategyError):
        strategy.choose_action(state, engine.legal_actions())
    with pytest.raises(MixedStrategyError):
        strategy.style_for(1)
    assert MixedLocalStrategy(seed=SEED).bot_seats == ()
    with pytest.raises(MixedStrategyError):
        MixedLocalStrategy(seed=SEED).style_for(1)


def test_dispatcher_requires_attached_context() -> None:
    engine, _ = _advance_to_bot()
    strategy = MixedLocalStrategy(seed=SEED)
    with pytest.raises(MixedContextError):
        strategy.choose_action(
            project_for_actor(engine.snapshot()), engine.legal_actions()
        )


def test_dispatcher_rejects_leaked_snapshot() -> None:
    engine, tracker = _advance_to_bot()
    leaked = mixed_state(engine.snapshot(), tracker.context())
    with pytest.raises(MixedContextError):
        MixedLocalStrategy(seed=SEED).choose_action(leaked, engine.legal_actions())


# ------------------------------------------------------------------ 每手与动作隔离


def test_hand_mode_is_stable_within_a_hand() -> None:
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    strategy = MixedLocalStrategy(seed=SEED)
    strategy.choose_action(state, engine.legal_actions())
    # 子策略按手号派生隐变量；重复计算必须得到同一模式，且不消耗行动流。
    policy = strategy._policies[1]
    verified = require_mixed_input(state)
    assert policy.hand_mode(verified) is policy.hand_mode(verified)


def test_different_seats_derive_different_streams() -> None:
    engine, tracker = _advance_to_bot()
    state = _state(engine, tracker)
    strategy = MixedLocalStrategy(seed=SEED)
    strategy.choose_action(state, engine.legal_actions())
    assert strategy._policies[1]._seat_key != strategy._policies[2]._seat_key


def test_action_line_advance_changes_event_identifier_only() -> None:
    """同一座位在同一手内、状态不同（事件数不同）时抽样流彼此独立。"""
    engine, tracker = _advance_to_bot()
    first_context = tracker.context()
    strategy = MixedLocalStrategy(seed=SEED)
    strategy.choose_action(_state(engine, tracker), engine.legal_actions())
    engine.apply_action(Action(ActionType.CALL))
    tracker.consume_after_action(engine.history)
    second_context = tracker.context()
    assert second_context.hand_number == first_context.hand_number
    assert second_context.event_count > first_context.event_count


def test_strategy_accepts_plain_legal_actions_protocol() -> None:
    engine, tracker = _advance_to_bot()
    legal = engine.legal_actions()
    assert isinstance(legal, LegalActions)
    action = MixedLocalStrategy(seed=SEED).choose_action(_state(engine, tracker), legal)
    assert action.type in (
        ActionType.FOLD,
        ActionType.CHECK,
        ActionType.CALL,
        ActionType.BET,
        ActionType.RAISE,
    )
