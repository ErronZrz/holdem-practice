"""测试辅助：将字符串形式的牌转成 Card 对象。"""

from app.poker.cards import Card, Rank, Suit

_RANK = {
    "2": Rank.TWO,
    "3": Rank.THREE,
    "4": Rank.FOUR,
    "5": Rank.FIVE,
    "6": Rank.SIX,
    "7": Rank.SEVEN,
    "8": Rank.EIGHT,
    "9": Rank.NINE,
    "T": Rank.TEN,
    "J": Rank.JACK,
    "Q": Rank.QUEEN,
    "K": Rank.KING,
    "A": Rank.ACE,
}

_SUIT = {
    "c": Suit.CLUBS,
    "d": Suit.DIAMONDS,
    "h": Suit.HEARTS,
    "s": Suit.SPADES,
}


def card(text: str) -> Card:
    """把 "As"、"Th" 这类单张牌字符串转成 Card。"""
    return Card(_RANK[text[0]], _SUIT[text[1]])


def cards(text: str) -> list[Card]:
    """把 "As Kh 2c" 这类空格分隔的字符串转成 Card 列表。"""
    return [card(token) for token in text.split()]
