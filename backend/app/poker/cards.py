"""扑克牌基础类型：花色、点数与单张牌。"""

from dataclasses import dataclass
from enum import IntEnum


class Suit(IntEnum):
    """花色。数值仅用于稳定排序，不代表实际强弱。"""

    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3


class Rank(IntEnum):
    """点数，2~14，A 记为 14。"""

    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14


_RANK_TO_CHAR = {
    Rank.TWO: "2",
    Rank.THREE: "3",
    Rank.FOUR: "4",
    Rank.FIVE: "5",
    Rank.SIX: "6",
    Rank.SEVEN: "7",
    Rank.EIGHT: "8",
    Rank.NINE: "9",
    Rank.TEN: "T",
    Rank.JACK: "J",
    Rank.QUEEN: "Q",
    Rank.KING: "K",
    Rank.ACE: "A",
}

_SUIT_TO_CHAR = {
    Suit.CLUBS: "c",
    Suit.DIAMONDS: "d",
    Suit.HEARTS: "h",
    Suit.SPADES: "s",
}

_CHAR_TO_RANK = {ch: rank for rank, ch in _RANK_TO_CHAR.items()}
_CHAR_TO_SUIT = {ch: suit for suit, ch in _SUIT_TO_CHAR.items()}


@dataclass(frozen=True, slots=True)
class Card:
    """单张牌，不可变，可哈希，便于集合去重与比较。"""

    rank: Rank
    suit: Suit

    def __str__(self) -> str:
        return f"{_RANK_TO_CHAR[self.rank]}{_SUIT_TO_CHAR[self.suit]}"


def card_from_str(text: str) -> Card:
    """把 "As"、"Th" 这类单张牌字符串解析为 Card，与 str(Card) 互逆。"""
    if len(text) != 2:
        raise ValueError(f"非法牌面表示：{text!r}")
    return Card(_CHAR_TO_RANK[text[0]], _CHAR_TO_SUIT[text[1]])
