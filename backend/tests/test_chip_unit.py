"""最小筹码单位：摊牌余数、启发式尺度，以及新混合身份的候选金额。"""

from __future__ import annotations

from dataclasses import replace

from app.api.schemas import CreateGameRequest
from app.poker.actions import LegalActions
from app.poker.engine import PokerEngine
from app.poker.state import GameState, PlayerState, Street
from app.strategy.abstraction import DEFAULT_FALLBACK_IDENTIFIER
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.mixed_features import MixedFeatures
from app.strategy.mixed_policy import (
    MIXED_LOCAL_V12_RULES,
    MIXED_LOCAL_V13_RULES,
    _active_candidates,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V12,
    MIXED_STRATEGY_IDENTIFIER_V13,
    MIXED_STRATEGY_IDENTIFIER_V14,
    MIXED_STRATEGY_IDENTIFIER_V15,
    MIXED_STRATEGY_IDENTIFIER_V16,
    MIXED_STRATEGY_IDENTIFIER_V17,
    MIXED_STRATEGY_IDENTIFIER_V18,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.projection import project_for_actor
from app.strategy.registry import create_strategy, observation_entry, spec_for
from app.verification.config import BASELINE_IDENTIFIER

from .helpers import cards
from .mixed_bot_validation import DIGEST_RULE_FIELDS, config_digest

_THIRTEENTH_CONFIG_DIGEST = (
    "83a94be9965925bbe4df8278bae21756a56d6559ea6d42539d1dba69b8b42279"
)
_TWELFTH_CONFIG_DIGEST = (
    "ca5a4fe9d5ce5f8bcda98dac622fc80afa97ae9fde1fba2976cea16e94a58e24"
)
_ROYAL_BOARD = "As Ks Qs Js Ts"
_TIE_HOLES = (
    "2c 3d",
    "4c 5d",
    "6c 7d",
    "8c 9d",
    "Tc Jd",
    "Qc Kd",
    "Ac 2d",
    "3c 4d",
    "5c 6d",
)


def _settle_tie(
    commitments: list[int],
    *,
    small_blind: int,
    big_blind: int,
    button: int,
    folded_seats: tuple[int, ...] = (),
) -> PokerEngine:
    engine = PokerEngine(
        len(commitments),
        small_blind=small_blind,
        big_blind=big_blind,
        starting_stack=max(commitments),
        seed=0,
    )
    engine.button = button
    engine.board = cards(_ROYAL_BOARD)
    for seat, player in enumerate(engine.players):
        player.hole_cards = cards(_TIE_HOLES[seat])
        player.total_committed = commitments[seat]
        player.folded = seat in folded_seats
        player.stack = 0
    engine._settle_showdown()
    return engine


def test_heads_up_split_remainder_goes_to_big_blind() -> None:
    """两人局庄家即小盲，平分后多出的一枚小盲归大盲。"""
    engine = _settle_tie([3, 3], small_blind=2, big_blind=4, button=0)

    assert engine.pot_results == [
        {"amount": 6, "winners": [0, 1], "shares": {0: 2, 1: 4}}
    ]
    assert [player.stack for player in engine.players] == [2, 4]


def test_multiway_split_remainder_starts_at_small_blind() -> None:
    """多人平分时，余下的小盲按小盲、大盲、枪口的顺序发放，庄家最后。"""
    engine = _settle_tie(
        [7, 7, 7, 7, 7],
        small_blind=5,
        big_blind=10,
        button=0,
        folded_seats=(4,),
    )

    assert engine.pot_results == [
        {"amount": 35, "winners": [0, 1, 2, 3], "shares": {0: 5, 1: 10, 2: 10, 3: 10}}
    ]
    assert sum(player.stack for player in engine.players) == 35


def test_non_multiple_pot_still_splits_by_single_chips() -> None:
    """池层不是小盲整数倍时退回逐筹码切分，发放顺序仍从小盲开始。"""
    engine = _settle_tie([4, 4, 4], small_blind=5, big_blind=10, button=0)

    assert engine.pot_results == [
        {"amount": 12, "winners": [0, 1, 2], "shares": {0: 4, 1: 4, 2: 4}}
    ]


def test_odd_single_chips_follow_the_seat_after_the_button() -> None:
    """不能按小盲切分时，零头从庄家下家起顺时针分配，而不是从最小座位号开始。"""
    engine = _settle_tie(
        [3, 3, 3, 2],
        small_blind=5,
        big_blind=10,
        button=0,
        folded_seats=(3,),
    )

    assert engine.pot_results[0] == {
        "amount": 8,
        "winners": [0, 1, 2],
        "shares": {0: 2, 1: 3, 2: 3},
    }


def test_snapshot_keeps_big_blind_for_the_actor_view() -> None:
    engine = PokerEngine(2, small_blind=5, big_blind=10, starting_stack=1000, seed=0)
    engine.start_hand()
    snapshot = engine.snapshot()
    assert snapshot.big_blind == 10
    assert project_for_actor(snapshot).big_blind == 10


def test_heuristic_sizes_align_to_small_blind_when_the_blind_is_known() -> None:
    bot = HeuristicStrategy()
    state = GameState(
        street=Street.FLOP,
        board=tuple(cards("2c 7d 9h")),
        pot=67,
        current_seat=0,
        button=1,
        hand_over=False,
        players=(
            PlayerState(seat=0, name="p0", stack=500, hole_cards=cards("As Kd")),
            PlayerState(seat=1, name="p1", stack=500),
        ),
        big_blind=10,
    )
    bet = LegalActions(
        can_fold=False,
        can_check=True,
        can_call=False,
        call_amount=0,
        actual_call_amount=0,
        is_short_all_in_call=False,
        can_bet=True,
        min_bet=10,
        max_bet=500,
        can_raise=False,
        min_raise_to=0,
        max_raise_to=0,
    )
    assert bot._bet_amount(state, bet) == 65
    assert bot._bet_amount(replace(state, big_blind=0), bet) == 67
    raised = LegalActions(
        can_fold=True,
        can_check=False,
        can_call=True,
        call_amount=10,
        actual_call_amount=10,
        is_short_all_in_call=False,
        can_bet=False,
        min_bet=0,
        max_bet=0,
        can_raise=True,
        min_raise_to=20,
        max_raise_to=500,
    )
    assert bot._raise_amount(state, raised, state.players[0]) == 75


def _postflop_bet_features() -> MixedFeatures:
    return MixedFeatures(
        street=Street.FLOP,
        base=900,
        draw=0,
        position=20,
        texture=0,
        contenders=1,
        live_opponents=1,
        recent_aggression=0,
        limpers=0,
        price=0,
        eligible_pot=200,
        actual_call=0,
        pot=200,
        effective_stack=2000,
        big_blind=10,
        stack=2000,
        street_bet=0,
        preflop_unraised=False,
        hole_ranks=(14, 14),
    )


def _bet_legal() -> LegalActions:
    return LegalActions(
        can_fold=False,
        can_check=True,
        can_call=False,
        call_amount=0,
        actual_call_amount=0,
        is_short_all_in_call=False,
        can_bet=True,
        min_bet=10,
        max_bet=2000,
        can_raise=False,
        min_raise_to=0,
        max_raise_to=0,
    )


def _candidate_amounts(rules) -> tuple[int, ...]:
    active = _active_candidates(
        _postflop_bet_features(),
        _bet_legal(),
        900,
        100,
        0,
        (6, 3, 1, 1),
        rules,
    )
    return tuple(amount for (action, amount, _quality), _preference in active)


def test_thirteenth_identity_aligns_candidates_without_moving_the_twelfth() -> None:
    """新身份的主动候选都是小盲整数倍；上一身份在同一局面仍保留未对齐金额。"""
    assert MIXED_LOCAL_V12_RULES.align_bet_to_small_blind is False
    assert MIXED_LOCAL_V13_RULES.align_bet_to_small_blind is True
    assert replace(MIXED_LOCAL_V13_RULES, align_bet_to_small_blind=False) == MIXED_LOCAL_V12_RULES
    previous = _candidate_amounts(MIXED_LOCAL_V12_RULES)
    current = _candidate_amounts(MIXED_LOCAL_V13_RULES)
    assert 67 in previous
    assert current
    assert all(amount % 5 == 0 for amount in current)


def test_thirteenth_identity_stays_constructable_when_default_is_eighteenth() -> None:
    ordered = MIXED_STRATEGY_IDENTIFIERS
    assert ordered[-1] == MIXED_STRATEGY_IDENTIFIER_V18
    assert ordered[-2] == MIXED_STRATEGY_IDENTIFIER_V17
    assert ordered[-3] == MIXED_STRATEGY_IDENTIFIER_V16
    assert ordered[-4] == MIXED_STRATEGY_IDENTIFIER_V15
    assert ordered[-5] == MIXED_STRATEGY_IDENTIFIER_V14
    assert ordered[-6] == MIXED_STRATEGY_IDENTIFIER_V13
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V13).version == 13
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V13, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V13
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V13) is MIXED_LOCAL_V13_RULES
    assert CreateGameRequest().bot_strategy == MIXED_STRATEGY_IDENTIFIER_V18
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V13).rules is MIXED_LOCAL_V13_RULES
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V13][-1] == "align_bet_to_small_blind"
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V13) == _THIRTEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V12) == _TWELFTH_CONFIG_DIGEST
    assert BASELINE_IDENTIFIER == "heuristic@1"
    assert DEFAULT_FALLBACK_IDENTIFIER == "heuristic@1"
