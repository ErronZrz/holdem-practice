import pytest

from kuhn_cfr.game import (
    CARD_ORDER,
    DEALS,
    INFOSETS,
    Action,
    Card,
    Deal,
    KuhnRuleError,
    Player,
    acting_player,
    apply_action,
    information_set_key,
    legal_actions,
    terminal_utility_p0,
)


def test_three_cards_and_six_ordered_deals() -> None:
    assert CARD_ORDER == (Card.JACK, Card.QUEEN, Card.KING)
    assert len(DEALS) == 6
    assert {(deal.p0_card, deal.p1_card) for deal in DEALS} == {
        (first, second) for first in CARD_ORDER for second in CARD_ORDER if first is not second
    }
    assert all(deal.p0_card is not deal.p1_card for deal in DEALS)


@pytest.mark.parametrize(
    ("history", "player", "actions"),
    [
        ("", Player.P0, (Action.CHECK, Action.BET)),
        ("x", Player.P1, (Action.CHECK, Action.BET)),
        ("b", Player.P1, (Action.FOLD, Action.CALL)),
        ("xb", Player.P0, (Action.FOLD, Action.CALL)),
    ],
)
def test_non_terminal_action_contract(
    history: str, player: Player, actions: tuple[Action, ...]
) -> None:
    assert acting_player(history) is player
    assert legal_actions(history) == actions
    assert apply_action(history, actions[0]) == history + actions[0].value


@pytest.mark.parametrize("history", ["xx", "bf", "bc", "xbf", "xbc"])
def test_terminal_histories_reject_further_actions(history: str) -> None:
    with pytest.raises(KuhnRuleError):
        legal_actions(history)


@pytest.mark.parametrize(
    ("history", "action"),
    [("", Action.CALL), ("x", Action.FOLD), ("b", Action.BET), ("xb", Action.CHECK)],
)
def test_illegal_actions_are_rejected(history: str, action: Action) -> None:
    with pytest.raises(KuhnRuleError):
        apply_action(history, action)


@pytest.mark.parametrize(
    ("deal", "history", "expected"),
    [
        (Deal(Card.KING, Card.JACK), "bf", 1),
        (Deal(Card.KING, Card.JACK), "xbf", -1),
        (Deal(Card.KING, Card.JACK), "xx", 1),
        (Deal(Card.JACK, Card.KING), "xx", -1),
        (Deal(Card.KING, Card.JACK), "bc", 2),
        (Deal(Card.JACK, Card.KING), "xbc", -2),
    ],
)
def test_terminal_payoffs_are_zero_sum(deal: Deal, history: str, expected: int) -> None:
    utility_p0 = terminal_utility_p0(deal, history)

    assert utility_p0 == expected
    assert utility_p0 + -utility_p0 == 0


def test_information_set_does_not_include_opponent_private_card() -> None:
    root_key = information_set_key(Player.P0, Card.QUEEN, "")
    facing_check_key = information_set_key(Player.P1, Card.JACK, "x")

    assert root_key == "p0:Q:-"
    assert facing_check_key == "p1:J:x"
    assert root_key in {spec.key for spec in INFOSETS}
    assert facing_check_key in {spec.key for spec in INFOSETS}
    assert Deal(Card.QUEEN, Card.JACK).card_for(Player.P0) is Card.QUEEN
    assert Deal(Card.QUEEN, Card.KING).card_for(Player.P0) is Card.QUEEN


def test_information_set_rejects_wrong_actor_or_terminal_history() -> None:
    with pytest.raises(KuhnRuleError):
        information_set_key(Player.P1, Card.JACK, "")
    with pytest.raises(KuhnRuleError):
        information_set_key(Player.P0, Card.JACK, "xx")
