"""牌型分类与牌力比较的中间结构。"""

from enum import IntEnum
from functools import total_ordering


class HandCategory(IntEnum):
    """牌型，数值越大越强。"""

    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8


@total_ordering
class HandRank:
    """评估结果：牌型 + 决胜牌点序列，支持大小比较。"""

    __slots__ = ("category", "tiebreak")

    def __init__(self, category: HandCategory, tiebreak: tuple[int, ...]) -> None:
        self.category = category
        self.tiebreak = tuple(tiebreak)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HandRank):
            return NotImplemented
        return self.category == other.category and self.tiebreak == other.tiebreak

    def __lt__(self, other: "HandRank") -> bool:
        if self.category != other.category:
            return self.category < other.category
        return self.tiebreak < other.tiebreak

    def __hash__(self) -> int:
        return hash((self.category, self.tiebreak))

    def __repr__(self) -> str:
        return f"HandRank({self.category.name}, {self.tiebreak})"
