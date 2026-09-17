import pytest

from multiplayer_cfr.game import (
    ROOT_HISTORY,
    Action,
    CandidateARuleError,
    Deal,
    acting_player,
    apply_action,
    decision_histories,
    derive_public_state,
    information_set_key,
    infosets,
    is_terminal,
    legal_actions,
    structure_counts,
    terminal_outcome,
)
from multiplayer_cfr.resources import estimate_resources


@pytest.mark.parametrize(
    ("player_count", "expected_decisions", "expected_infosets", "expected_terminals"),
    [(6, 192, 1152, 193), (7, 448, 3136, 449), (9, 2304, 20736, 2305)],
)
def test_structure_and_infoset_contract(
    player_count: int,
    expected_decisions: int,
    expected_infosets: int,
    expected_terminals: int,
) -> None:
    counts = structure_counts(player_count)

    assert counts.ordered_deals > 0
    assert counts.public_decision_histories == expected_decisions
    assert counts.infosets == expected_infosets
    assert counts.terminal_histories == expected_terminals
    assert len(decision_histories(player_count)) == expected_decisions
    assert len(infosets(player_count)) == expected_infosets
    assert all(
        spec.actions == legal_actions(player_count, spec.history) for spec in infosets(player_count)
    )


def _all_terminal_histories(player_count: int) -> tuple[str, ...]:
    pending = [ROOT_HISTORY]
    terminals: list[str] = []
    while pending:
        history = pending.pop()
        if is_terminal(player_count, history):
            terminals.append(history)
            continue
        pending.extend(
            apply_action(player_count, history, action)
            for action in legal_actions(player_count, history)
        )
    return tuple(terminals)


@pytest.mark.parametrize("player_count", [6, 7, 9])
def test_all_terminal_histories_preserve_integer_chips(player_count: int) -> None:
    deal = Deal(tuple(range(player_count)))
    terminals = _all_terminal_histories(player_count)

    assert len(terminals) == structure_counts(player_count).terminal_histories
    for history in terminals:
        outcome = terminal_outcome(player_count, deal, history)
        assert sum(outcome.payouts) == outcome.pot
        assert sum(outcome.utilities) == 0
        assert all(isinstance(value, int) for value in outcome.utilities)


@pytest.mark.parametrize("player_count", [6, 7, 9])
def test_opening_response_wraps_and_derived_state_is_consistent(player_count: int) -> None:
    history = ROOT_HISTORY
    for _ in range(2):
        history = apply_action(player_count, history, Action.CHECK)
    history = apply_action(player_count, history, Action.BET)

    state = derive_public_state(player_count, history)
    expected_order = tuple(range(3, player_count)) + (0, 1)
    assert state.opener == 2
    assert state.actor == expected_order[0]
    assert state.pending_responders == expected_order
    assert state.contributions == tuple(2 if seat == 2 else 1 for seat in range(player_count))
    assert legal_actions(player_count, history) == (Action.CALL, Action.FOLD)

    for index, expected_actor in enumerate(expected_order):
        assert acting_player(player_count, history) == expected_actor
        history = apply_action(
            player_count,
            history,
            Action.CALL if index % 2 == 0 else Action.FOLD,
        )

    terminal_state = derive_public_state(player_count, history)
    assert terminal_state.terminal
    assert terminal_state.pending_responders == ()
    assert terminal_state.folded == frozenset(expected_order[1::2])


@pytest.mark.parametrize("player_count", [6, 7, 9])
def test_all_checks_and_all_folds_handle_dead_money(player_count: int) -> None:
    all_checks = ROOT_HISTORY
    for _ in range(player_count):
        all_checks = apply_action(player_count, all_checks, Action.CHECK)
    checked = terminal_outcome(player_count, Deal(tuple(range(player_count))), all_checks)
    assert checked.winner == player_count - 1
    assert checked.pot == player_count
    assert checked.payouts[-1] == player_count
    assert checked.utilities[-1] == player_count - 1

    all_folds = apply_action(player_count, ROOT_HISTORY, Action.BET)
    for _ in range(player_count - 1):
        all_folds = apply_action(player_count, all_folds, Action.FOLD)
    folded = terminal_outcome(player_count, Deal(tuple(range(player_count))), all_folds)
    assert folded.winner == 0
    assert folded.pot == player_count + 1
    assert folded.contributions == tuple(2 if seat == 0 else 1 for seat in range(player_count))
    assert folded.utilities == tuple(
        player_count - 1 if seat == 0 else -1 for seat in range(player_count)
    )


@pytest.mark.parametrize(
    "history",
    [
        "",
        "x@1",
        "x@0|c@1",
        "b@0|b@1",
        "x@0|x@1|x@2|x@3|x@4|x@5|x@0",
    ],
)
def test_invalid_histories_are_rejected(history: str) -> None:
    with pytest.raises(CandidateARuleError):
        derive_public_state(6, history)


def test_illegal_action_and_terminal_actor_are_rejected() -> None:
    with pytest.raises(CandidateARuleError):
        apply_action(6, ROOT_HISTORY, Action.CALL)

    history = ROOT_HISTORY
    for _ in range(6):
        history = apply_action(6, history, Action.CHECK)
    with pytest.raises(CandidateARuleError):
        acting_player(6, history)
    with pytest.raises(CandidateARuleError):
        apply_action(6, history, Action.CHECK)


def test_information_key_excludes_other_private_cards_and_future_result() -> None:
    history = "x@0|x@1"
    first_deal = Deal((0, 1, 4, 2, 3, 5))
    second_deal = Deal((5, 3, 4, 2, 1, 0))
    key = information_set_key(6, 2, first_deal.rank_for(2), history)

    assert key == information_set_key(6, 2, second_deal.rank_for(2), history)
    future = "x@0|x@1|x@2|x@3|x@4|x@5"
    first_future = terminal_outcome(6, first_deal, future)
    second_future = terminal_outcome(6, second_deal, future)
    assert first_future.winner != second_future.winner
    assert key != information_set_key(6, 2, 3, history)
    assert key != information_set_key(6, 1, 4, "x@0")
    assert key != information_set_key(6, 2, 4, "b@0|c@1")


@pytest.mark.parametrize(
    ("player_count", "state_budget", "artifact_budget"),
    [
        (6, 32 * 1024 * 1024, 4 * 1024 * 1024),
        (7, 96 * 1024 * 1024, 12 * 1024 * 1024),
        (9, 512 * 1024 * 1024, 64 * 1024 * 1024),
    ],
)
def test_resource_estimates_are_static_contracts(
    player_count: int, state_budget: int, artifact_budget: int
) -> None:
    estimate = estimate_resources(player_count)

    assert estimate.structure == structure_counts(player_count)
    assert estimate.state_budget_bytes == state_budget
    assert estimate.artifact_budget_bytes == artifact_budget
