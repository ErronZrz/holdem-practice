"""候选 A 的可复现 ordered-deal chance 抽样。"""

from __future__ import annotations

import random
from collections.abc import Iterator
from itertools import permutations
from math import factorial

from .game import CandidateARuleError, Deal, validate_player_count

PRNG_ID = "python-random-mt19937"


class CandidateAChance:
    """仅使用显式整数 seed 的均匀有序发牌器。"""

    def __init__(self, player_count: int, seed: int) -> None:
        self.player_count = validate_player_count(player_count)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise CandidateARuleError("chance seed 必须是显式整数")
        self.seed = seed
        self._random = random.Random(seed)

    def sample_ordered_deal(self) -> Deal:
        """抽取一组无重复 rank 的完整有序发牌。"""

        return Deal(tuple(self._random.sample(range(self.player_count), self.player_count)))


def ordered_deal_count(player_count: int) -> int:
    """返回均匀 chance 空间中 ordered deal 的精确数量。"""

    return factorial(validate_player_count(player_count))


def iter_ordered_deals(player_count: int) -> Iterator[Deal]:
    """按词典序完整枚举 chance 空间，仅用于规则核验。"""

    player_count = validate_player_count(player_count)
    for ranks in permutations(range(player_count)):
        yield Deal(ranks)
