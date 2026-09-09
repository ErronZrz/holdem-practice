"""牌力评估：从 5~7 张牌中选出最强 5 张并给出可比较的牌力。"""

from collections import Counter
from collections.abc import Sequence
from itertools import combinations

from .cards import Card, Rank
from .hand import HandCategory, HandRank


def evaluate(cards: Sequence[Card]) -> HandRank:
    """评估一组牌（5~7 张）的最强牌力。"""
    if len(cards) < 5:
        raise ValueError("评估至少需要 5 张牌")
    if len(cards) == 5:
        return _evaluate_five(list(cards))
    return max(_evaluate_five(list(combo)) for combo in combinations(cards, 5))


def best_five(cards: Sequence[Card]) -> list[Card]:
    """从 5~7 张牌中返回构成最强牌力、且按牌型语义排序的 5 张牌（用于摊牌展示）。"""
    if len(cards) < 5:
        raise ValueError("评估至少需要 5 张牌")
    five = (
        list(cards)
        if len(cards) == 5
        else list(max(combinations(cards, 5), key=_evaluate_five))
    )
    return sort_five(five)


def sort_five(cards: Sequence[Card]) -> list[Card]:
    """把 5 张牌按牌型语义排序：相同点数优先、踢脚从大到小；顺子从小到大（轮子 A 记低）。"""
    c = list(cards)
    category = _evaluate_five(c).category
    counter = Counter(card.rank for card in c)
    is_straight = category in (HandCategory.STRAIGHT, HandCategory.STRAIGHT_FLUSH)
    if is_straight:
        ranks = {r.value for r in counter}
        if ranks == {14, 5, 4, 3, 2}:
            # 轮子顺子：A 记低，从小到大 A 2 3 4 5。
            return sorted(c, key=lambda card: (1 if card.rank == Rank.ACE else card.rank.value))
        return sorted(c, key=lambda card: card.rank.value)
    return sorted(c, key=lambda card: (counter[card.rank], card.rank.value), reverse=True)


def _evaluate_five(cards: list[Card]) -> HandRank:
    """评估恰好 5 张牌的牌力。"""
    ranks = sorted((card.rank.value for card in cards), reverse=True)
    is_flush = len({card.suit for card in cards}) == 1

    distinct = sorted(set(ranks), reverse=True)
    is_straight = False
    straight_high = 0
    if len(distinct) == 5:
        if distinct[0] - distinct[4] == 4:
            is_straight = True
            straight_high = distinct[0]
        elif distinct == [14, 5, 4, 3, 2]:
            # A-2-3-4-5 轮子顺子，A 记为低点。
            is_straight = True
            straight_high = 5

    # 按 (出现次数, 点数) 降序排列，便于区分四条/葫芦/三条/两对/一对。
    groups = sorted(Counter(ranks).items(), key=lambda item: (item[1], item[0]), reverse=True)

    if is_flush and is_straight:
        return HandRank(HandCategory.STRAIGHT_FLUSH, (straight_high,))
    if groups[0][1] == 4:
        return HandRank(HandCategory.FOUR_OF_A_KIND, (groups[0][0], groups[1][0]))
    if groups[0][1] == 3 and groups[1][1] == 2:
        return HandRank(HandCategory.FULL_HOUSE, (groups[0][0], groups[1][0]))
    if is_flush:
        return HandRank(HandCategory.FLUSH, tuple(ranks))
    if is_straight:
        return HandRank(HandCategory.STRAIGHT, (straight_high,))
    if groups[0][1] == 3:
        kickers = tuple(rank for rank, _ in groups[1:])
        return HandRank(HandCategory.THREE_OF_A_KIND, (groups[0][0], *kickers))
    if groups[0][1] == 2 and groups[1][1] == 2:
        return HandRank(HandCategory.TWO_PAIR, (groups[0][0], groups[1][0], groups[2][0]))
    if groups[0][1] == 2:
        kickers = tuple(rank for rank, _ in groups[1:])
        return HandRank(HandCategory.ONE_PAIR, (groups[0][0], *kickers))
    return HandRank(HandCategory.HIGH_CARD, tuple(ranks))
