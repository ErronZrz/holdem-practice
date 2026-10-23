"""行动线分档、乘法权重与逐层份额的口径测试。"""

import random

import pytest

from app.analysis.action_line_equity import (
    ActionLineTracker,
    _effective_preflop_score,
    estimate_decision,
    prior_weight,
)
from app.poker.cards import Card, Rank, Suit, card_from_str
from app.poker.pot_projection import (
    CandidateCallProjection,
    PotLayerKind,
    ProjectedPotLayer,
)
from app.strategy.mixed_features import _preflop_base


def _card(text: str) -> Card:
    return card_from_str(text)


def _layer(kind: PotLayerKind, amount: int, eligible: tuple[int, ...]) -> ProjectedPotLayer:
    return ProjectedPotLayer(
        lower_commitment=0,
        upper_commitment=amount,
        amount=amount,
        contributor_seats=eligible,
        eligible_seats=eligible,
        caller_is_eligible=0 in eligible,
        kind=kind,
        refunds=(),
    )


def test_prior_separates_premiums_from_trash_without_a_board() -> None:
    # 没有公共牌时，过线的牌只比刚过线的牌重一到两倍，比值仍随行动线收紧。
    aa = _preflop_base([Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS)])
    trash = _preflop_base([Card(Rank.SEVEN, Suit.CLUBS), Card(Rank.TWO, Suit.DIAMONDS)])
    expected = {0: 1.79, 1: 3.03, 2: 12.49, 3: 115.18, 4: 1386.44, 5: 34017.00}
    ratios = []
    for level, ratio in expected.items():
        left = prior_weight(aa, 0.0, level, False)
        right = prior_weight(trash, 0.0, level, False)
        found = left / right
        ratios.append(found)
        assert found == pytest.approx(ratio, rel=0.02)
    assert ratios[0] < 2
    assert ratios == sorted(ratios)
    assert ratios[3] > 100


def test_board_connection_cannot_rescue_trash_into_a_tight_line() -> None:
    # 档位 3 上，满连接度的 72o 仍轻于没有连接度的 AA，但不再是数千倍。
    aa = _preflop_base([Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS)])
    trash = _preflop_base([Card(Rank.SEVEN, Suit.CLUBS), Card(Rank.TWO, Suit.DIAMONDS)])
    premium = prior_weight(aa, 0.0, 3, True)
    rescued = prior_weight(trash, 1000.0, 3, True)
    assert premium / rescued == pytest.approx(5.73, rel=0.02)
    assert premium / rescued > 5


def test_sampling_table_uses_effective_broadway_scores() -> None:
    # 抽样表补上高张和国王后，旧基础分函数的返回值保持原样。
    samples = {
        ("As", "Kh"): (542, 762),
        ("As", "Ks"): (587, 807),
        ("Ad", "Qh"): (567, 717),
        ("Ac", "Qc"): (612, 762),
        ("Ah", "Jd"): (542, 662),
        ("Ah", "Jh"): (587, 707),
        ("Kd", "Qh"): (429, 479),
        ("Kd", "Qd"): (474, 524),
        ("7c", "2d"): (146, 146),
        ("Ac", "Ad"): (920, 920),
    }
    for (left, right), (raw, effective) in samples.items():
        holes = (card_from_str(left), card_from_str(right))
        assert _preflop_base(holes) == raw
        assert _effective_preflop_score(holes) == effective


def test_action_line_keeps_the_tightest_public_action() -> None:
    tracker = ActionLineTracker(3)
    tracker.begin_street("preflop")
    tracker.commit(seat=1, action="call", amount=10, pot_before=15, big_blind=10)
    tracker.commit(seat=1, action="raise", amount=30, pot_before=25, big_blind=10)
    tracker.begin_street("flop")
    tracker.commit(seat=1, action="bet", amount=10, pot_before=100, big_blind=10)
    tracker.commit(seat=2, action="raise", amount=80, pot_before=110, big_blind=10)
    tracker.commit(seat=2, action="check", amount=0, pot_before=190, big_blind=10)
    levels = dict(tracker.live_opponents(_players(), hero_seat=0))
    # 翻前加注已经到开池档，翻后小注不再放宽；翻后半池以上的加注进到最紧档。
    assert levels[1] == 2
    assert levels[2] == 5


def test_preflop_large_commit_tightens_one_more_level() -> None:
    tracker = ActionLineTracker(2)
    tracker.begin_street("preflop")
    tracker.commit(seat=1, action="raise", amount=90, pot_before=15, big_blind=10)
    levels = dict(tracker.live_opponents(_players(2), hero_seat=0))
    assert levels[1] == 3


def test_checked_down_chop_uses_equal_shares() -> None:
    # 公共牌已经是坚果时人人平分，三人底池的份额是 1/3，而不是平局记 0.5。
    board = [_card(text) for text in ("Ah", "Kh", "Qh", "Jh", "Th")]
    valued = estimate_decision(
        hero_cards=[_card("2c"), _card("3d")],
        board=board,
        opponents=[(1, 0), (2, 0)],
        projection=None,
        pot=30,
        hero_seat=0,
        actual_call_amount=0,
        samples=8,
        rng=random.Random(0),
    )
    assert valued.equity == pytest.approx(1 / 3)
    assert valued.call_ev is None
    assert valued.pot_odds is None


def test_nuts_call_returns_the_whole_contested_layer() -> None:
    # 河牌坚果面对跟注时，每一手样本都拿走竞争层，期望等于层金额减去实付。
    board = [_card(text) for text in ("2h", "2s", "3c", "3d", "3h")]
    projection = CandidateCallProjection(
        caller_seat=0,
        actual_call_amount=20,
        participants=(),
        layers=(
            _layer(PotLayerKind.CALLER_RECOVERY, 10, (0,)),
            _layer(PotLayerKind.CONTESTED, 50, (0, 1)),
        ),
    )
    valued = estimate_decision(
        hero_cards=[_card("2c"), _card("2d")],
        board=board,
        opponents=[(1, 4)],
        projection=projection,
        pot=40,
        hero_seat=0,
        actual_call_amount=20,
        samples=6,
        rng=random.Random(0),
    )
    assert valued.equity == pytest.approx(1.0)
    assert valued.call_ev == pytest.approx(40.0)
    assert valued.pot_odds == pytest.approx(0.2)
    assert valued.contested == 50
    assert valued.recovery == 10


class _Seat:
    def __init__(self, seat: int, folded: bool = False) -> None:
        self.seat = seat
        self.folded = folded


def _players(count: int = 3) -> list[_Seat]:
    return [_Seat(seat) for seat in range(count)]
