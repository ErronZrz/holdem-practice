"""蒙特卡洛胜率估算测试。"""

import random

import pytest

from app.poker.equity import equity, estimate_static_showdown_share

from .helpers import cards


class _FixedSampleRandom(random.Random):
    """为单样本用例固定抽牌结果。"""

    def __init__(self, drawn) -> None:
        super().__init__(0)
        self._drawn = list(drawn)

    def sample(self, population, k):
        assert k == len(self._drawn)
        assert set(self._drawn).issubset(population)
        return list(self._drawn)


def _eq(hole: str, board: str, n: int, seed: int = 0, samples: int = 5000) -> float:
    rng = random.Random(seed)
    return equity(
        cards(hole),
        tuple(cards(board)) if board else (),
        n,
        rng,
        samples,
    )


def _share(hole: str, board: str, n: int, seed: int = 0, samples: int = 5000):
    return estimate_static_showdown_share(
        cards(hole),
        tuple(cards(board)) if board else (),
        n,
        random.Random(seed),
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


def test_legacy_equity_keeps_half_score_for_three_way_board_tie() -> None:
    value = _eq("2c 3d", "As Ks Qs Js Ts", 2, samples=20)

    assert value == 0.5


@pytest.mark.parametrize(
    ("opponents", "expected_share"),
    [(1, 1 / 2), (2, 1 / 3), (3, 1 / 4), (8, 1 / 9)],
)
def test_static_share_splits_forced_board_ties(
    opponents: int, expected_share: float
) -> None:
    estimate = _share("2c 3d", "As Ks Qs Js Ts", opponents, samples=20)

    assert estimate.strict_win_rate == 0.0
    assert estimate.tie_for_best_rate == 1.0
    assert estimate.expected_share == pytest.approx(expected_share)


def test_static_share_distinguishes_strict_win_and_loss() -> None:
    strict_win = _share("As Ad", "Ac Ah 2c 7d 9h", 1, samples=20)
    forced_loss = estimate_static_showdown_share(
        cards("2c 3d"),
        tuple(cards("As Kd Qh Jc 9s")),
        1,
        _FixedSampleRandom(cards("Ts 8d")),
        samples=1,
    )

    assert strict_win.strict_win_rate == 1.0
    assert strict_win.tie_for_best_rate == 0.0
    assert strict_win.expected_share == 1.0
    assert forced_loss.strict_win_rate == 0.0
    assert forced_loss.tie_for_best_rate == 0.0
    assert forced_loss.expected_share == 0.0


def test_static_share_is_reproducible_and_bounded() -> None:
    first = _share("Ah Kd", "Ad 8c 2s", 3, seed=7, samples=1000)
    second = _share("Ah Kd", "Ad 8c 2s", 3, seed=7, samples=1000)

    assert first == second
    assert 0.0 <= first.strict_win_rate <= 1.0
    assert 0.0 <= first.tie_for_best_rate <= 1.0
    assert 0.0 <= first.expected_share <= 1.0
    assert first.strict_win_rate + first.tie_for_best_rate <= 1.0
    assert first.expected_share <= first.strict_win_rate + first.tie_for_best_rate


def test_static_share_without_opponents_and_invalid_inputs() -> None:
    no_opponents = _share("As Ah", "Ad 7c 2s", 0)

    assert no_opponents.strict_win_rate == 1.0
    assert no_opponents.tie_for_best_rate == 0.0
    assert no_opponents.expected_share == 1.0
    with pytest.raises(ValueError, match="对手数量"):
        _share("As Ah", "Ad 7c 2s", -1)
    with pytest.raises(ValueError, match="采样次数"):
        _share("As Ah", "Ad 7c 2s", 1, samples=0)
