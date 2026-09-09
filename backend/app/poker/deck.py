"""牌堆：生成完整 52 张牌，洗牌随机源可注入以便复现。"""

import random

from .cards import Card, Rank, Suit


class Deck:
    """一副扑克牌。洗牌后按顺序发牌，天然避免同一手内重复发牌。"""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng if rng is not None else random.Random()
        self._cards = [Card(rank, suit) for suit in Suit for rank in Rank]
        self._cursor = 0

    def shuffle(self) -> None:
        """洗牌并重置发牌游标。"""
        self._rng.shuffle(self._cards)
        self._cursor = 0

    def draw(self, count: int = 1) -> list[Card]:
        """从牌堆顶取指定数量的牌。"""
        if count < 0:
            raise ValueError("发牌数量不能为负")
        if self._cursor + count > len(self._cards):
            raise IndexError("牌堆剩余牌不足")
        cards = self._cards[self._cursor : self._cursor + count]
        self._cursor += count
        return cards

    @property
    def remaining(self) -> int:
        """牌堆剩余牌数。"""
        return len(self._cards) - self._cursor
