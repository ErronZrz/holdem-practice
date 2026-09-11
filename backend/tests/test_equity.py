"""蒙特卡洛胜率估算测试。"""

import random

from app.poker.equity import equity

from .helpers import cards


def _eq(hole: str, board: str, n: int, seed: int = 0, samples: int = 5000) -> float:
    rng = random.Random(seed)
    return equity(
        cards(hole),
        tuple(cards(board)) if board else (),
        n,
        rng,
        samples,
    )


def test_no_opponents_returns_certainty() -> None:
    assert _eq("As Ah", "Ad 7c 2s", 0) == 1.0


def test_reproducible_with_same_seed() -> None:
    rng1 = random.Random(7)
    rng2 = random.Random(7)
    a = equity(cards("As Ah"), tuple(cards("Ad 7c 2s")), 1, rng1, 1000)
    b = equity(cards("As Ah"), tuple(cards("Ad 7c 2s")), 1, rng2, 1000)
    assert a == b


def test_bounds() -> None:
    value = _eq("As Ah", "Ad 7c 2s", 3)
    assert 0.0 <= value <= 1.0


def test_monster_beats_air() -> None:
    monster = _eq("As Ah", "Ad 7c 2s", 1)
    air = _eq("2c 7d", "As Kc 9s", 1)
    assert monster > air


def test_equity_decays_with_more_opponents() -> None:
    single = _eq("Ah Kd", "Ad 8c 2s", 1)
    multi = _eq("Ah Kd", "Ad 8c 2s", 4)
    assert multi < single


def test_nut_hand_equity_near_one() -> None:
    # 已成皇家同花顺，面对随机手几乎必胜（至多与公共牌成同花顺时平局）。
    value = _eq("As Ks", "Qs Js Ts 2c 2d", 1)
    assert value > 0.95
