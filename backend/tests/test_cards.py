"""牌与牌堆的基础测试。"""

import random

import pytest

from app.poker.cards import Rank, Suit
from app.poker.deck import Deck


def test_deck_has_52_unique_cards() -> None:
    deck = Deck()
    deck.shuffle()
    drawn = []
    while deck.remaining > 0:
        drawn.extend(deck.draw(1))
    assert len(drawn) == 52
    assert len(set(drawn)) == 52


def test_shuffle_reproducible_with_seed() -> None:
    a = Deck(random.Random(123))
    b = Deck(random.Random(123))
    a.shuffle()
    b.shuffle()
    seq_a = a.draw(52)
    seq_b = b.draw(52)
    assert seq_a == seq_b


def test_shuffle_differs_across_seeds() -> None:
    a = Deck(random.Random(1))
    b = Deck(random.Random(2))
    a.shuffle()
    b.shuffle()
    assert a.draw(52) != b.draw(52)


def test_draw_many() -> None:
    deck = Deck(random.Random(0))
    deck.shuffle()
    cards = deck.draw(5)
    assert len(cards) == 5
    assert deck.remaining == 47


def test_draw_exhaustion_raises() -> None:
    deck = Deck(random.Random(0))
    deck.shuffle()
    deck.draw(52)
    with pytest.raises(IndexError):
        deck.draw(1)


def test_rank_and_suit_values() -> None:
    assert Rank.ACE.value == 14
    assert Rank.TWO.value == 2
    assert len(Suit) == 4
