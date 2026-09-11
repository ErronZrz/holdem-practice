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


def evaluate_fast(cards: Sequence[Card]) -> HandRank:
    """一次性评估 5~7 张牌的牌力，结果与 :func:`evaluate` 等价。

    与 ``evaluate`` 的差异在于实现：这里直接按点数频次、花色分布与顺子判定推导牌型，
    避免 ``combinations`` 枚举 5 张子集的 21 次开销，专供蒙特卡洛胜率等需要海量评估的热路径。
    """

    ranks = sorted((card.rank.value for card in cards), reverse=True)

    # 按花色分组，用于同花与同花顺判定。
    suit_buckets: dict[int, list[int]] = {}
    for card in cards:
        suit_buckets.setdefault(card.suit.value, []).append(card.rank.value)
    flush_ranks: list[int] | None = None
    for bucket in suit_buckets.values():
        if len(bucket) >= 5:
            flush_ranks = sorted(bucket, reverse=True)
            break

    # 点数频次，按 (次数, 点数) 降序，便于区分四条/葫芦/三条/两对/一对。
    counter = Counter(ranks)
    groups = sorted(counter.items(), key=lambda item: (item[1], item[0]), reverse=True)
    distinct = sorted(counter.keys(), reverse=True)

    def _straight_high(seq: list[int]) -> int:
        """在降序去重点数序列中找顺子顶点，无则返回 0（A-2-3-4-5 记 5）。"""
        if len(seq) < 5:
            return 0
        for i in range(len(seq) - 4):
            if seq[i] - seq[i + 4] == 4:
                return seq[i]
        if 14 in seq and {5, 4, 3, 2}.issubset(seq):
            return 5
        return 0

    straight_high = _straight_high(distinct)

    if flush_ranks is not None:
        flush_straight = _straight_high(sorted(set(flush_ranks), reverse=True))
        if flush_straight:
            return HandRank(HandCategory.STRAIGHT_FLUSH, (flush_straight,))

    if groups[0][1] == 4:
        quad = groups[0][0]
        kicker = max(rank for rank in ranks if rank != quad)
        return HandRank(HandCategory.FOUR_OF_A_KIND, (quad, kicker))

    if groups[0][1] == 3 and len(groups) >= 2 and groups[1][1] >= 2:
        # 三条 + 对子（或两组三条）均构成葫芦，取高三条为「三」、次高为「对」。
        return HandRank(HandCategory.FULL_HOUSE, (groups[0][0], groups[1][0]))

    if flush_ranks is not None:
        return HandRank(HandCategory.FLUSH, tuple(flush_ranks[:5]))

    if straight_high:
        return HandRank(HandCategory.STRAIGHT, (straight_high,))

    if groups[0][1] == 3:
        kickers = tuple(rank for rank, _ in groups[1:3])
        return HandRank(HandCategory.THREE_OF_A_KIND, (groups[0][0], *kickers))

    if groups[0][1] == 2 and groups[1][1] == 2:
        # 踢脚取两对之外的最高点数（7 张牌可能出现三对，此时第三对不参与，取单张作踢脚）。
        hi, lo = groups[0][0], groups[1][0]
        kicker = max(rank for rank in ranks if rank != hi and rank != lo)
        return HandRank(HandCategory.TWO_PAIR, (hi, lo, kicker))

    if groups[0][1] == 2:
        kickers = tuple(rank for rank, _ in groups[1:4])
        return HandRank(HandCategory.ONE_PAIR, (groups[0][0], *kickers))

    return HandRank(HandCategory.HIGH_CARD, tuple(ranks[:5]))


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
