"""蒙特卡洛胜率估算：估计自己的底牌面对若干随机底牌的摊牌胜率。

用于把策略层的离散牌力分档替换为连续胜率阈值。这里只做「静态摊牌胜率 vs 随机范围」，
不建模对手的真实下注范围与位置（那是后续范围建模 / CFR 的范畴）。

纯 Python、无 Web 依赖，随机源由调用方注入，满足可复现要求（AGENTS 原则 4）。
"""

import random
from dataclasses import dataclass

from .cards import Card, Rank, Suit
from .evaluator import evaluate_fast

# 一整副牌，作为采样池的构造基准。
_FULL_DECK = [Card(rank, suit) for suit in Suit for rank in Rank]


@dataclass(frozen=True)
class StaticShowdownShareEstimate:
    """固定竞争集合下的静态名义摊牌份额估计。"""

    strict_win_rate: float
    tie_for_best_rate: float
    expected_share: float


def equity(
    hole_cards: list[Card],
    board: tuple[Card, ...],
    num_opponents: int,
    rng: random.Random,
    samples: int = 1000,
) -> float:
    """估计「自己赢过所有对手」的摊牌胜率，范围 [0, 1]，平局按半个胜场计入。

    对每个样本：给每个对手从剩余牌中各随机发两张底牌，再补完剩余公共牌，
    用快速评估器比较自己的牌力与最强对手的牌力，累计胜/平。
    """

    if num_opponents <= 0:
        return 1.0

    known = set(hole_cards) | set(board)
    deck = [card for card in _FULL_DECK if card not in known]
    need_board = 5 - len(board)
    need_opp = 2 * num_opponents

    wins = 0
    ties = 0
    for _ in range(samples):
        drawn = rng.sample(deck, need_opp + need_board)
        runout = drawn[need_opp : need_opp + need_board]
        my_rank = evaluate_fast([*hole_cards, *board, *runout])
        best_opp = None
        for i in range(num_opponents):
            opp_rank = evaluate_fast([*drawn[2 * i : 2 * i + 2], *board, *runout])
            if best_opp is None or opp_rank > best_opp:
                best_opp = opp_rank
        if my_rank > best_opp:
            wins += 1
        elif my_rank == best_opp:
            ties += 1

    return (wins + ties / 2) / samples


def estimate_static_showdown_share(
    hole_cards: list[Card],
    board: tuple[Card, ...],
    num_opponents: int,
    rng: random.Random,
    samples: int = 1000,
) -> StaticShowdownShareEstimate:
    """估计固定随机竞争集合中的静态名义摊牌份额。"""

    if num_opponents < 0:
        raise ValueError("对手数量不能为负数")
    if samples <= 0:
        raise ValueError("采样次数必须为正数")
    if num_opponents == 0:
        return StaticShowdownShareEstimate(
            strict_win_rate=1.0,
            tie_for_best_rate=0.0,
            expected_share=1.0,
        )

    known = set(hole_cards) | set(board)
    deck = [card for card in _FULL_DECK if card not in known]
    need_board = 5 - len(board)
    need_opp = 2 * num_opponents

    strict_wins = 0
    ties_for_best = 0
    expected_share = 0.0
    for _ in range(samples):
        drawn = rng.sample(deck, need_opp + need_board)
        runout = drawn[need_opp : need_opp + need_board]
        my_rank = evaluate_fast([*hole_cards, *board, *runout])
        opponent_ranks = [
            evaluate_fast([*drawn[2 * i : 2 * i + 2], *board, *runout])
            for i in range(num_opponents)
        ]
        if all(my_rank > opponent_rank for opponent_rank in opponent_ranks):
            strict_wins += 1
            expected_share += 1.0
            continue
        if any(opponent_rank > my_rank for opponent_rank in opponent_ranks):
            continue

        tied_opponents = sum(opponent_rank == my_rank for opponent_rank in opponent_ranks)
        ties_for_best += 1
        expected_share += 1 / (tied_opponents + 1)

    return StaticShowdownShareEstimate(
        strict_win_rate=strict_wins / samples,
        tie_for_best_rate=ties_for_best / samples,
        expected_share=expected_share / samples,
    )
