"""按公开行动线给未弃牌对手加权，并估计候选跟注的逐层份额。

只使用英雄底牌、公共牌、底池和截至该决策之前的公开动作。公共牌只放大翻前已经可能的组合，
不能把很弱的起手牌救进很紧的行动线。采样随机源由调用方注入。
"""

import bisect
import math
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.poker.cards import Card, Rank, Suit
from app.poker.evaluator import evaluate_fast
from app.poker.hand import HandRank
from app.poker.pot_projection import CandidateCallProjection, PotLayerKind
from app.poker.state import PlayerState
from app.strategy.mixed_features import _postflop_base, _preflop_base

# 行动线从宽到紧。门槛越高、温度越低，弱起手牌的权重越接近零。
_LEVEL_PRIOR: dict[int, tuple[int, int]] = {
    0: (100, 170),
    1: (200, 130),
    2: (320, 95),
    3: (450, 75),
    4: (540, 60),
    5: (620, 48),
}
_PRIOR_GAP_MIN = -14.0
_PRIOR_GAP_MAX = 8.0
# 高于门槛的合格牌最多再加一倍；跨度用完就停在 2。
_PRIOR_SPAN = 400.0
# 翻后连接度按行动线分档。门槛越高，没打中牌面的牌越难进入紧的行动线。
_CONNECTION_PRIOR: dict[int, tuple[int, int]] = {
    0: (100, 200),
    1: (300, 160),
    2: (420, 130),
    3: (580, 95),
    4: (660, 75),
    5: (720, 60),
}
_CONNECTION_GAP_MIN = -3.0
_CONNECTION_SPAN = 400.0
_CONNECTION_CAP = 1000.0
# 抽样表相对旧翻前基础分补上的高张与国王后。只用于这张表。
_BROADWAY_ADJACENT = 220
_BROADWAY_ONE_GAP = 150
_BROADWAY_TWO_GAP = 120
_KING_QUEEN_BONUS = 50
_DRAW_BONUS_CAP = 180
# 翻前一次投入超过这么多个大盲时，再收紧一档，最高停在大额加注档。
_PREFLOP_COMMIT_BLINDS = 8
_PREFLOP_COMMIT_CAP = 4
# 冲突时有限次重抽；仍冲突就按组合表找第一手不冲突的牌。
_RESAMPLE_TRIES = 24

_DECK: tuple[Card, ...] = tuple(Card(rank, suit) for suit in Suit for rank in Rank)
_COMBOS: tuple[tuple[Card, Card], ...] = tuple(
    (_DECK[i], _DECK[j]) for i in range(len(_DECK)) for j in range(i + 1, len(_DECK))
)


def _effective_preflop_score(holes: tuple[Card, Card]) -> int:
    """抽样用的翻前分。旧基础分原样保留，只在这张表上补高张和国王后。"""
    base = _preflop_base(holes)
    high = max(card.rank.value for card in holes)
    low = min(card.rank.value for card in holes)
    if high == low:
        return base
    gap = high - low - 1
    bonus = 0
    if high == Rank.ACE.value and low >= Rank.JACK.value:
        bonus = {0: _BROADWAY_ADJACENT, 1: _BROADWAY_ONE_GAP, 2: _BROADWAY_TWO_GAP}.get(gap, 0)
    elif high == Rank.KING.value and low == Rank.QUEEN.value:
        bonus = _KING_QUEEN_BONUS
    if bonus == 0:
        return base
    return min(1000, base + bonus)


_PRE_SCORE: tuple[int, ...] = tuple(_effective_preflop_score(combo) for combo in _COMBOS)


@dataclass(frozen=True)
class DecisionValue:
    """一个决策点的份额与跟注期望。无人下注时后两项为空。"""

    equity: float
    call_ev: float | None
    pot_odds: float | None
    contested: int
    recovery: int


class ActionLineTracker:
    """记下每个座位到当前决策为止最紧的公开行动线。"""

    def __init__(self, num_players: int) -> None:
        self._levels = [0] * num_players
        self._street = "preflop"
        self._raises = 0

    def begin_street(self, street: str) -> None:
        """进入新的一条街时清零本街加注次数，已记下的档位保留。"""
        if street != self._street:
            self._street = street
            self._raises = 0

    def commit(
        self,
        *,
        seat: int,
        action: str,
        amount: int,
        pot_before: int,
        big_blind: int,
    ) -> None:
        """用刚刚发生的公开动作收紧该座位；过牌与弃牌不改变档位。"""
        incoming = _incoming_level(
            action=action,
            amount=amount,
            pot_before=pot_before,
            street=self._street,
            previous_raises=self._raises,
            big_blind=big_blind,
        )
        if incoming is not None:
            self._levels[seat] = max(self._levels[seat], incoming)
        if action in ("bet", "raise"):
            self._raises += 1

    def live_opponents(
        self, players: Sequence[PlayerState], hero_seat: int
    ) -> list[tuple[int, int]]:
        """未弃牌对手及其档位。折叠的座位不进入抽样。"""
        found: list[tuple[int, int]] = []
        for player in players:
            seat = int(player.seat)
            if seat != hero_seat and not player.folded:
                found.append((seat, self._levels[seat]))
        return found


def estimate_decision(
    *,
    hero_cards: Sequence[Card],
    board: Sequence[Card],
    opponents: Sequence[tuple[int, int]],
    projection: CandidateCallProjection | None,
    pot: int,
    hero_seat: int,
    actual_call_amount: int,
    samples: int,
    rng: random.Random,
) -> DecisionValue:
    """在同一次发牌里估计英雄份额；有候选跟注时再减去实际支付。"""
    live = [(seat, level) for seat, level in opponents]
    if not live:
        return DecisionValue(
            equity=1.0,
            call_ev=None,
            pot_odds=None,
            contested=0,
            recovery=0,
        )

    blocked = set(hero_cards) | set(board)
    strengths = _combo_strength(board, blocked)
    indices = _active_indices(blocked)
    order = _sampling_order(indices, strengths, live, board)
    contested_layers, recovery = _layers_for_hero(projection, pot, hero_seat, live)
    contested_total = sum(layer_amount for layer_amount, _eligible in contested_layers)

    need_board = 5 - len(board)
    remaining = [card for card in _DECK if card not in blocked]
    won_chips = 0.0
    used = 0
    for _ in range(samples):
        dealt = _sample_opponents(rng, order, indices, blocked)
        if dealt is None:
            continue
        used_cards = set(blocked)
        for combo in dealt.values():
            used_cards.add(combo[0])
            used_cards.add(combo[1])
        deck_left = [card for card in remaining if card not in used_cards]
        runout = rng.sample(deck_left, need_board) if need_board else []
        hero_rank = evaluate_fast([*hero_cards, *board, *runout])
        opponent_ranks = {
            seat: evaluate_fast([*combo, *board, *runout]) for seat, combo in dealt.items()
        }
        sample_chips = float(recovery)
        for amount, eligible in contested_layers:
            sample_chips += amount * _share(hero_rank, opponent_ranks, eligible, hero_seat)
        won_chips += sample_chips
        used += 1

    if used == 0:
        raise RuntimeError("行动线抽样没有产出有效样本")
    expected_return = won_chips / used
    if projection is None:
        equity = (expected_return / pot) if pot > 0 else 1.0
        return DecisionValue(
            equity=equity,
            call_ev=None,
            pot_odds=None,
            contested=pot,
            recovery=0,
        )

    equity = (expected_return - recovery) / contested_total if contested_total else 1.0
    return DecisionValue(
        equity=equity,
        call_ev=expected_return - actual_call_amount,
        pot_odds=_pot_odds(actual_call_amount, contested_total, recovery),
        contested=contested_total,
        recovery=recovery,
    )


def prior_weight(preflop_score: float, connection: float, level: int, has_board: bool) -> float:
    """翻前行动线决定先验。过线的牌落在一到两倍，公共牌再按连接度分档放大。

    没过翻前门槛的牌，公共牌放大不超过 1，满连接度不能把它抬过自己的翻前权重。
    """
    floor, temperature = _LEVEL_PRIOR[level]
    if preflop_score < floor:
        gap = (preflop_score - floor) / temperature
        prior = math.exp(max(_PRIOR_GAP_MIN, min(_PRIOR_GAP_MAX, gap)))
    else:
        prior = 1.0 + min(preflop_score - floor, _PRIOR_SPAN) / _PRIOR_SPAN
    if not has_board:
        return prior
    connection_floor, connection_temperature = _CONNECTION_PRIOR[level]
    if connection < connection_floor:
        connection_gap = (connection - connection_floor) / connection_temperature
        lift = math.exp(max(_CONNECTION_GAP_MIN, connection_gap))
    else:
        lift = 1.0 + min(connection - connection_floor, _CONNECTION_SPAN) / _CONNECTION_SPAN
    if preflop_score < floor:
        lift = min(1.0, lift)
    return prior * lift


def _incoming_level(
    *,
    action: str,
    amount: int,
    pot_before: int,
    street: str,
    previous_raises: int,
    big_blind: int,
) -> int | None:
    if action in ("fold", "check"):
        return None
    if street == "preflop":
        if action == "call":
            return 1 if previous_raises == 0 else 2
        if action != "raise":
            return None
        if previous_raises <= 0:
            level = 2
        elif previous_raises == 1:
            level = 3
        else:
            level = 4
        if amount > _PREFLOP_COMMIT_BLINDS * big_blind:
            level = min(_PREFLOP_COMMIT_CAP, level + 1)
        return level

    fraction = amount / max(pot_before, 1)
    if action == "call":
        return 2
    if action == "bet":
        if fraction < 0.40:
            return 1
        if fraction < 0.80:
            return 3
        return 4
    if fraction < 0.50:
        return 4
    return 5


def _combo_strength(board: Sequence[Card], blocked: set[Card]) -> list[float]:
    """每个起手组合在当前公共牌下的成牌连接度。被挡住的组合不打分。"""
    if not board:
        return [float(score) for score in _PRE_SCORE]
    strengths = [0.0] * len(_COMBOS)
    board_tuple = tuple(board)
    for index, combo in enumerate(_COMBOS):
        if combo[0] in blocked or combo[1] in blocked:
            continue
        rank = evaluate_fast([*combo, *board_tuple])
        made = _postflop_base(rank, combo, board_tuple)
        strengths[index] = min(
            _CONNECTION_CAP, float(made) + _draw_bonus(combo, board_tuple)
        )
    return strengths


def _draw_bonus(holes: Sequence[Card], board: tuple[Card, ...]) -> int:
    """听牌只做常数时间的粗加分，避免对每个组合再扫一整副牌。"""
    if len(board) not in (3, 4):
        return 0
    flush_bonus = 0
    suit_counts = Counter(card.suit for card in board)
    for suit, count in suit_counts.items():
        hole_suited = sum(1 for card in holes if card.suit == suit)
        if hole_suited and count + hole_suited == 4:
            flush_bonus = max(flush_bonus, 140 if len(board) == 3 else 90)
    ranks = {card.rank.value for card in board}
    hole_ranks = {card.rank.value for card in holes}
    present = ranks | hole_ranks
    straight_bonus = 0
    for high in range(Rank.ACE.value, Rank.FIVE.value - 1, -1):
        window = (
            {Rank.ACE.value, 2, 3, 4, 5}
            if high == Rank.FIVE.value
            else set(range(high - 4, high + 1))
        )
        if not (window & (hole_ranks - ranks)):
            continue
        missing = len(window - present)
        if missing == 1:
            straight_bonus = max(straight_bonus, 110 if len(board) == 3 else 70)
        elif missing == 2 and len(board) == 3:
            straight_bonus = max(straight_bonus, 40)
    return min(_DRAW_BONUS_CAP, flush_bonus + straight_bonus)


def _active_indices(blocked: set[Card]) -> list[int]:
    return [
        index
        for index, combo in enumerate(_COMBOS)
        if combo[0] not in blocked and combo[1] not in blocked
    ]


def _sampling_order(
    indices: list[int],
    strengths: list[float],
    opponents: Sequence[tuple[int, int]],
    board: Sequence[Card],
) -> list[tuple[int, list[float], list[int]]]:
    """从紧到宽排列对手，使紧范围先占用冲突的组合。"""
    has_board = bool(board)
    prepared: list[tuple[int, int, list[float]]] = []
    for seat, level in opponents:
        total = 0.0
        cumulative: list[float] = []
        for index in indices:
            total += prior_weight(_PRE_SCORE[index], strengths[index], level, has_board)
            cumulative.append(total)
        prepared.append((seat, level, cumulative))
    prepared.sort(key=lambda item: -item[1])
    return [(seat, cumulative, indices) for seat, _level, cumulative in prepared]


def _sample_opponents(
    rng: random.Random,
    order: Sequence[tuple[int, list[float], list[int]]],
    indices: Sequence[int],
    blocked: set[Card],
) -> dict[int, tuple[Card, Card]] | None:
    used = set(blocked)
    dealt: dict[int, tuple[Card, Card]] = {}
    for seat, cumulative, seat_indices in order:
        chosen: tuple[Card, Card] | None = None
        for _ in range(_RESAMPLE_TRIES):
            index = _pick(rng, cumulative, seat_indices)
            combo = _COMBOS[index]
            if combo[0] in used or combo[1] in used:
                continue
            chosen = combo
            break
        if chosen is None:
            for index in indices:
                combo = _COMBOS[index]
                if combo[0] in used or combo[1] in used:
                    continue
                chosen = combo
                break
        if chosen is None:
            return None
        dealt[seat] = chosen
        used.add(chosen[0])
        used.add(chosen[1])
    return dealt


def _pick(rng: random.Random, cumulative: Sequence[float], indices: Sequence[int]) -> int:
    target = rng.random() * cumulative[-1]
    found = bisect.bisect_left(cumulative, target)
    if found >= len(indices):
        found = len(indices) - 1
    return indices[found]


def _layers_for_hero(
    projection: CandidateCallProjection | None,
    pot: int,
    hero_seat: int,
    live: Sequence[tuple[int, int]],
) -> tuple[list[tuple[int, tuple[int, ...]]], int]:
    """无人下注时，整池都按当前未弃牌座位平摊到摊牌。"""
    if projection is None:
        eligible = (hero_seat, *(seat for seat, _level in live))
        return [(pot, eligible)], 0
    contested: list[tuple[int, tuple[int, ...]]] = []
    recovery = 0
    for layer in projection.layers:
        if layer.kind is PotLayerKind.CALLER_RECOVERY:
            recovery += layer.amount
        elif layer.kind is PotLayerKind.CONTESTED and hero_seat in layer.eligible_seats:
            contested.append((layer.amount, tuple(layer.eligible_seats)))
    return contested, recovery


def _share(
    hero_rank: HandRank,
    opponent_ranks: dict[int, HandRank],
    eligible: tuple[int, ...],
    hero_seat: int,
) -> float:
    """英雄在该层并列最好时份额为 1/k，否则为 0。"""
    best = hero_rank
    tied = 1
    hero_best = True
    for seat in eligible:
        if seat == hero_seat:
            continue
        rank = opponent_ranks[seat]
        if rank > best:
            best = rank
            tied = 1
            hero_best = False
        elif rank == best:
            tied += 1
    if not hero_best:
        return 0.0
    return 1.0 / tied


def _pot_odds(actual_call: int, contested: int, recovery: int) -> float | None:
    if contested <= 0:
        return 0.0 if actual_call <= recovery else None
    return max(0.0, actual_call - recovery) / contested
