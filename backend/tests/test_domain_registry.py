"""节点快照、金额桶与层选择键的直接断言，并与引擎合法动作对照。"""

from __future__ import annotations

import pytest

from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.verification import CampaignLockVersions, SpecIncompleteError
from app.verification.domain_registry import (
    NODE_SNAPSHOTS,
    amount_bucket,
    legal_flags,
    require_bucket_assignments,
    require_domain_lock_versions,
    require_domain_snapshots,
    require_layer_selection_keys,
)

from .verification_helpers import fixture_lock_versions

_LEGAL_FIELDS = (
    "can_fold",
    "can_check",
    "can_call",
    "call_amount",
    "actual_call_amount",
    "is_short_all_in_call",
    "can_bet",
    "min_bet",
    "max_bet",
    "can_raise",
    "min_raise_to",
    "max_raise_to",
)


def test_registry_table_is_internally_consistent() -> None:
    require_domain_snapshots()
    require_bucket_assignments()
    require_layer_selection_keys(0)
    require_domain_lock_versions(fixture_lock_versions())
    assert amount_bucket(6) == "BKT_MID"
    assert amount_bucket(12) == "BKT_OTHER"
    with pytest.raises(SpecIncompleteError):
        require_layer_selection_keys(0, (("L-A-PF", "A-001"), ("L-A-PF", "A-001")))
    raw = fixture_lock_versions().model_dump()
    raw["domain_ab_bucket_registry"] = 2
    with pytest.raises(SpecIncompleteError):
        require_domain_lock_versions(CampaignLockVersions.model_construct(**raw))


def test_live_engine_matches_registered_legal_actions() -> None:
    holes, board = _deck()
    snapshots = {node.node_id: node for node in NODE_SNAPSHOTS}

    facing_blinds = _engine(holes, board[:0], button=0)
    facing_blinds.apply_action(Action(ActionType.FOLD))
    facing_blinds.apply_action(Action(ActionType.FOLD))
    facing_blinds.apply_action(Action(ActionType.FOLD))
    _assert_matches(facing_blinds, snapshots["A-001"])

    facing_raise = _engine(holes, board[:0], button=0)
    facing_raise.apply_action(Action(ActionType.FOLD))
    facing_raise.apply_action(Action(ActionType.FOLD))
    facing_raise.apply_action(Action(ActionType.RAISE, 4))
    _assert_matches(facing_raise, snapshots["B-001"])
    _assert_matches(facing_raise, snapshots["A-002"])

    checked = _engine(holes, board[:3], button=1)
    checked.apply_action(Action(ActionType.FOLD))
    checked.apply_action(Action(ActionType.FOLD))
    checked.apply_action(Action(ActionType.FOLD))
    checked.apply_action(Action(ActionType.CALL))
    checked.apply_action(Action(ActionType.CALL))
    checked.apply_action(Action(ActionType.CHECK))
    checked.apply_action(Action(ActionType.CHECK))
    checked.apply_action(Action(ActionType.CHECK))
    _assert_matches(checked, snapshots["A-003"])

    facing_bet = _engine(holes, board[:5], button=1)
    facing_bet.apply_action(Action(ActionType.FOLD))
    facing_bet.apply_action(Action(ActionType.FOLD))
    facing_bet.apply_action(Action(ActionType.FOLD))
    facing_bet.apply_action(Action(ActionType.CALL))
    facing_bet.apply_action(Action(ActionType.CALL))
    facing_bet.apply_action(Action(ActionType.CHECK))
    facing_bet.apply_action(Action(ActionType.BET, 6))
    facing_bet.apply_action(Action(ActionType.FOLD))
    _assert_matches(facing_bet, snapshots["B-002"])


def _deck() -> tuple[dict[int, list], list]:
    ranks = "23456789TJQKA"
    deck = [card_from_str(f"{rank}{suit}") for rank in ranks for suit in "cdhs"]
    holes = {seat: deck[seat * 2 : seat * 2 + 2] for seat in range(6)}
    return holes, deck[12:17]


def _engine(holes: dict[int, list], board: list, *, button: int) -> PokerEngine:
    engine = PokerEngine(6, small_blind=1, big_blind=2, starting_stack=200, seed=0)
    engine.start_hand_with(button=button, hole_cards=holes, board=list(board))
    return engine


def _assert_matches(engine: PokerEngine, node) -> None:
    legal = engine.legal_actions()
    assert tuple(getattr(legal, name) for name in _LEGAL_FIELDS) == legal_flags(node)
    for seat, row in enumerate(node.seats):
        player = engine.players[seat]
        assert player.folded is row.folded
        assert player.stack == row.stack_remaining
        assert player.street_bet == row.street_bet
        assert player.total_committed == row.total_committed
        assert player.has_acted_since_full_raise is row.has_acted_since_full_raise
