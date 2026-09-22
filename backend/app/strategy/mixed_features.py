"""新 Bot 的状态特征：确定性牌力、听牌潜力、位置、公开风险与筹码关系。

设计要点：
- 全部特征只从已校验的安全输入与公开摘要派生，不读对手底牌、不枚举 runout；
- 复用的既有能力只有只读的 ``evaluate_fast`` 与候选 CALL 资格投影；
- 分数是 0–1000 的规则评分，不是概率、不是 EV；补牌不是「干净 outs」。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from app.poker.actions import LegalActions
from app.poker.cards import Card, Rank, Suit
from app.poker.evaluator import evaluate_fast
from app.poker.hand import HandCategory, HandRank
from app.poker.pot_projection import (
    PotLayerKind,
    PotParticipant,
    project_candidate_call,
)
from app.poker.state import GameState, PlayerState, Street

from .mixed_context import (
    MIXED_SUMMARY_STREETS,
    MixedContextError,
    VerifiedMixedInput,
    require_mixed_input,
)

# 评分上限与四街的听牌上限。
SCORE_MIN = 0
SCORE_MAX = 1000
_FLOP_DRAW_CAP = 180
_TURN_DRAW_CAP = 120
_FLOP_OUTS_WEIGHT = 12
_TURN_OUTS_WEIGHT = 8
# 河牌共享牌面（自身最佳牌型与公共五张完全相同）的安全上限。
_SHARED_BOARD_CAP = 450
# 同花至少需要公共牌提供的同花张数；不足则该花色不可能成同花。
_BOARD_FLUSH_SUIT_FLOOR = 3
# 任意两张底牌最多能补上的点数缺口。
_HOLE_CARD_BUDGET = 2

# 摘要中 bet / raise 的列索引：用于统计本街对手主动动作。
_BET_INDEX = 3
_RAISE_INDEX = 4


class MixedFeaturesError(ValueError):
    """特征层遇到无法有定义地打分的局面时抛出。"""


def clip(value: int, low: int, high: int) -> int:
    """把整数夹到闭区间，规则层统一用它避免各处重复写边界。"""
    return min(max(value, low), high)


@dataclass(frozen=True)
class MixedFeatures:
    """一次决策所需的全部规则特征；全部为整数，可直接比较。"""

    street: Street
    base: int
    draw: int
    position: int
    texture: int
    contenders: int
    live_opponents: int
    recent_aggression: int
    limpers: int
    price: int
    eligible_pot: int
    actual_call: int
    pot: int
    effective_stack: int
    big_blind: int
    stack: int
    street_bet: int
    preflop_unraised: bool
    hole_ranks: tuple[int, int]
    # 河牌时自身最佳牌型等同于公共五张，且该牌型已不可能被任何两张底牌超越。
    shared_board_locked: bool = False

    @property
    def spr_denominator(self) -> int:
        """SPR 的分母：底池与大盲中的较大者，至少为正。"""
        return max(self.pot, self.big_blind)

    @property
    def has_broadway_blocker(self) -> bool:
        """底牌是否含 A 或 K；仅作粗粒度阻断提示，不是范围阻断模型。"""
        return any(rank >= 13 for rank in self.hole_ranks)

    def spr_at_most(self, numerator: int, denominator: int = 1) -> bool:
        """以交叉相乘比较有效投入比，避免把浮点写进筹码口径。"""
        return self.effective_stack * denominator <= self.spr_denominator * numerator

    def spr_at_least(self, numerator: int, denominator: int = 1) -> bool:
        """以交叉相乘比较有效投入比的下界。"""
        return self.effective_stack * denominator >= self.spr_denominator * numerator


def extract_features(state: GameState, legal: LegalActions) -> MixedFeatures:
    """从安全状态与合法动作派生规则特征（自带一致性校验）。"""
    return features_for(require_mixed_input(state), legal)


def features_for(verified: VerifiedMixedInput, legal: LegalActions) -> MixedFeatures:
    """在已完成校验的输入上派生规则特征，避免同一次决策重复校验。"""
    actor = verified.actor
    context = verified.context
    board = verified.board
    holes = list(actor.hole_cards)
    players = verified.players
    street = verified.street
    street_index = list(MIXED_SUMMARY_STREETS).index(street)

    contenders = sum(1 for p in players if p.seat != actor.seat and not p.folded)
    if contenders <= 0:
        raise MixedFeaturesError("没有仍在争夺底池的对手，不应构造主动决策")
    live = sum(1 for p in players if p.seat != actor.seat and not p.folded and p.stack > 0)

    counts = context.streets[street_index].counts_by_seat
    aggression = sum(
        counts[p.seat][_BET_INDEX] + counts[p.seat][_RAISE_INDEX]
        for p in players
        if p.seat != actor.seat
    )
    limpers = len(context.streets[0].preopen_callers)

    price, eligible_pot, actual_call = _call_price(verified, players, legal)

    if street is Street.PREFLOP:
        base = _preflop_base(holes)
        draw = 0
        texture = 0
        shared_locked = False
    else:
        hero_rank = evaluate_fast([*holes, *board])
        base = _postflop_base(hero_rank, holes, board)
        board_rank = evaluate_fast(board) if len(board) == 5 else None
        if board_rank is not None and hero_rank == board_rank:
            # 与公共五张完全同型：保守封顶，不据此判定可弃或该跟。
            base = min(base, _SHARED_BOARD_CAP)
        shared_locked = (
            board_rank is not None
            and hero_rank == board_rank
            and _board_hand_is_untouchable(board, board_rank)
        )
        draw = _draw_score(holes, board, hero_rank.category)
        texture = _texture(hero_rank.category, board)

    position = _position(verified, street is Street.PREFLOP)
    effective = _effective_stack(players, actor.seat)

    ranks = sorted((card.rank.value for card in holes), reverse=True)
    return MixedFeatures(
        street=street,
        base=base,
        draw=draw,
        position=position,
        texture=texture,
        contenders=contenders,
        live_opponents=live,
        recent_aggression=min(3, aggression),
        limpers=limpers,
        price=price,
        eligible_pot=eligible_pot,
        actual_call=actual_call,
        pot=verified.pot,
        effective_stack=effective,
        big_blind=context.big_blind,
        stack=actor.stack,
        street_bet=actor.street_bet,
        # 翻前尚无自愿加注时，开池尺寸按人头的名义目标给出。
        preflop_unraised=(street is Street.PREFLOP and context.streets[0].last_aggressor is None),
        hole_ranks=(ranks[0], ranks[1]),
        shared_board_locked=shared_locked,
    )


# ------------------------------------------------------------------ 牌力基础分


def _preflop_base(holes: Sequence[Card]) -> int:
    """翻前两牌强弱初值：口袋对子按点数线性，非对子按高张/踢脚/同花/点差。"""
    high = max(card.rank.value for card in holes)
    low = min(card.rank.value for card in holes)
    if high == low:
        return clip(500 + 35 * (high - 2), SCORE_MIN, SCORE_MAX)
    gap = high - low - 1
    gap_bonus = {1: 35, 2: 20, 3: 5}.get(gap, 0)
    suited = holes[0].suit == holes[1].suit
    score = (
        18 * high
        + 10 * low
        + (85 if high == (Rank.ACE.value) else 0)
        + (75 if low >= (Rank.TEN.value) else 0)
        + (45 if suited else 0)
        + gap_bonus
    )
    return clip(score, SCORE_MIN, SCORE_MAX)


def _postflop_base(rank: HandRank, holes: Sequence[Card], board: Sequence[Card]) -> int:
    """翻后基础分：先按最佳牌型分类，再按实际采用的配对面关系细分。"""
    fixed = {
        HandCategory.STRAIGHT_FLUSH: 1000,
        HandCategory.FOUR_OF_A_KIND: 985,
        HandCategory.FULL_HOUSE: 960,
        HandCategory.FLUSH: 900,
        HandCategory.STRAIGHT: 860,
    }
    if rank.category in fixed:
        return fixed[rank.category]

    hole_counts = Counter(card.rank.value for card in holes)
    board_counts = Counter(card.rank.value for card in board)
    board_ranks = set(board_counts)

    if rank.category is HandCategory.THREE_OF_A_KIND:
        trips = rank.tiebreak[0]
        if hole_counts.get(trips, 0) == 2:
            return 840
        if hole_counts.get(trips, 0) == 1:
            return 780
        return 180

    if rank.category is HandCategory.TWO_PAIR:
        high, low = rank.tiebreak[0], rank.tiebreak[1]
        used = (high, low)
        if all(board_counts.get(rank_value, 0) >= 2 for rank_value in used):
            return 200
        if any(hole_counts.get(rank_value, 0) == 2 for rank_value in used):
            return 600
        if all(
            hole_counts.get(rank_value, 0) == 1 and board_counts.get(rank_value, 0) == 1
            for rank_value in used
        ):
            return 760
        return 520

    if rank.category is HandCategory.ONE_PAIR:
        pair = rank.tiebreak[0]
        if hole_counts.get(pair, 0) == 2:
            if pair > max(board_ranks):
                return 720
            if pair < min(board_ranks):
                return 400
            return 520
        if hole_counts.get(pair, 0) == 1:
            if pair == max(board_ranks):
                base = 650
            elif pair == min(board_ranks):
                base = 360
            else:
                base = 500
            return base + _kicker_increment(rank.tiebreak[1:], holes, board_ranks)
        return 180

    top = rank.tiebreak[0]
    if top == Rank.ACE.value:
        return 180
    if top == Rank.KING.value:
        return 130
    return 60


def _kicker_increment(
    kickers: tuple[int, ...],
    holes: Sequence[Card],
    board_ranks: set[int],
) -> int:
    """未配对底牌进入最佳五张踢脚时的加/减分；未进入则不计。"""
    hole_counts = Counter(card.rank.value for card in holes)
    for card in holes:
        rank_value = card.rank.value
        if hole_counts[rank_value] != 1 or rank_value in board_ranks:
            continue
        if rank_value not in kickers:
            return 0
        if rank_value >= Rank.JACK.value:
            return 40
        if rank_value >= Rank.EIGHT.value:
            return 0
        return -40
    return 0


# ------------------------------------------------------------------ 共享牌面锁定


def _highest_straight_window(ranks: set[int], hole_budget: int) -> int:
    """点数集合能用至多 ``hole_budget`` 张外部牌补齐的最高五连窗口高度。

    轮子顺子按 5 计（与评估器的顺子决胜牌口径一致）；一个也补不出时返回 0。
    """
    best = 0
    for high in range(Rank.ACE.value, Rank.FIVE.value - 1, -1):
        window = (
            {Rank.ACE.value, 2, 3, 4, 5}
            if high == Rank.FIVE.value
            else set(range(high - 4, high + 1))
        )
        if len(window - ranks) <= hole_budget:
            best = max(best, high)
    return best


def _board_hand_is_untouchable(board: Sequence[Card], board_rank: HandRank) -> bool:
    """公共五张自身的牌型是否已不可能被任何两张底牌超越。

    只在能够证明时返回真：此时用公共牌打到底至少不输，与「公共牌本身很弱、只是恰好同型」
    是两回事。判定只读公共五张，不枚举对手底牌，也不改变既有的保守封顶。
    """
    rank_counts = Counter(card.rank.value for card in board)
    suit_counts = Counter(card.suit for card in board)
    if board_rank.category is HandCategory.STRAIGHT_FLUSH:
        # 同花顺面上所有公共牌同花色，只有更高的同花顺能超越。
        suited = {card.rank.value for card in board}
        return _highest_straight_window(suited, _HOLE_CARD_BUDGET) <= board_rank.tiebreak[0]
    if max(suit_counts.values()) >= _BOARD_FLUSH_SUIT_FLOOR:
        # 公共至少三张同花：两张同花底牌即可成同花或抬高已有同花。
        return False
    if board_rank.category is HandCategory.FOUR_OF_A_KIND:
        # 公共四条已用掉四张同点数牌，底牌既凑不出更高四条，也凑不出葫芦。
        return True
    if max(rank_counts.values()) >= 3:
        # 公共三条：任一底牌配上即成四条。
        return False
    if board_rank.category is not HandCategory.STRAIGHT:
        return False
    if max(rank_counts.values()) >= 2:
        # 顺子面理论上不可能有对子；保留判定以免依赖「恰好五张」的隐含前提。
        return False
    return _highest_straight_window(set(rank_counts), _HOLE_CARD_BUDGET) <= board_rank.tiebreak[0]


# ------------------------------------------------------------------ 听牌潜力


def _draw_score(holes: Sequence[Card], board: Sequence[Card], category: HandCategory) -> int:
    """只统计「再发一张即成形、且依赖自身底牌」的补牌，作为潜力信号。"""
    if len(board) not in (3, 4) or category >= HandCategory.STRAIGHT:
        return 0
    known = set(holes) | set(board)
    outs: set[Card] = set()
    for suit in Suit:
        for rank in Rank:
            candidate = Card(rank, suit)
            if candidate in known:
                continue
            if _is_private_flush_out(holes, board, candidate) or _is_private_straight_out(
                holes, board, candidate
            ):
                outs.add(candidate)
    if len(board) == 3:
        return min(_FLOP_DRAW_CAP, _FLOP_OUTS_WEIGHT * len(outs))
    return min(_TURN_DRAW_CAP, _TURN_OUTS_WEIGHT * len(outs))


def _is_private_flush_out(holes: Sequence[Card], board: Sequence[Card], candidate: Card) -> bool:
    """补牌是否形成同花，且原有四张同花中至少一张来自自身底牌。"""
    suited = [card for card in (*holes, *board) if card.suit == candidate.suit]
    if len(suited) != 4:
        return False
    return any(card.suit == candidate.suit for card in holes)


def _is_private_straight_out(holes: Sequence[Card], board: Sequence[Card], candidate: Card) -> bool:
    """补牌是否形成顺子，且该顺子至少有一个点数只能由自身底牌提供。"""
    hole_ranks = {card.rank.value for card in holes}
    board_ranks = {card.rank.value for card in board}
    available = hole_ranks | board_ranks | {candidate.rank.value}
    for high in range(Rank.ACE.value, Rank.FIVE.value - 1, -1):
        window = (
            {Rank.ACE.value, 2, 3, 4, 5}
            if high == Rank.FIVE.value
            else set(range(high - 4, high + 1))
        )
        if not window <= available:
            continue
        if any(
            rank_value in hole_ranks
            and rank_value not in board_ranks
            and rank_value != candidate.rank.value
            for rank_value in window
        ):
            return True
    return False


# ------------------------------------------------------------------ 风险与位置


def _texture(category: HandCategory, board: Sequence[Card]) -> int:
    """公共牌面风险：同花成张与顺子窗口缺口的公开提示，不读取未发牌。"""
    if not board:
        return 0
    texture = 0
    suit_counts = Counter(card.suit for card in board)
    max_suit = max(suit_counts.values())
    if category < HandCategory.FLUSH:
        if max_suit >= 4:
            texture += 80
        elif max_suit == 3:
            texture += 40
    if category < HandCategory.STRAIGHT and _board_straight_risk({c.rank.value for c in board}):
        texture += 40
    return texture


def _board_straight_risk(board_ranks: set[int]) -> bool:
    """公共点数是否存在「五连窗口只缺不超过一个点」的排列。"""
    for high in range(Rank.FIVE.value, Rank.ACE.value + 1):
        window = (
            {Rank.ACE.value, 2, 3, 4, 5}
            if high == Rank.FIVE.value
            else set(range(high - 4, high + 1))
        )
        if len(window - board_ranks) <= 1:
            return True
    return False


def _position(verified: VerifiedMixedInput, is_preflop: bool) -> int:
    """按未弃牌且有筹码者的行动顺序给出 -40..40 的相对位置。"""
    players = verified.players
    size = verified.num_players
    button = verified.button
    preflop_start = button if size == 2 else (button + 3) % size
    start = preflop_start if is_preflop else (button + 1) % size
    order = [
        (start + step) % size
        for step in range(size)
        if not players[(start + step) % size].folded and players[(start + step) % size].stack > 0
    ]
    index = order.index(verified.actor_seat)
    if len(order) == 1:
        return 0
    return (80 * index) // (len(order) - 1) - 40


def _effective_stack(players: Sequence[PlayerState], actor_seat: int) -> int:
    """规则用有效投入：自己剩余筹码与对手最大可投入之差，不冒充统一的边池 SPR。"""
    actor = players[actor_seat]
    opponent_max = 0
    for player in players:
        if player.seat == actor_seat or player.folded:
            continue
        opponent_max = max(opponent_max, player.total_committed + player.stack)
    return min(actor.stack, max(0, opponent_max - actor.total_committed))


# ------------------------------------------------------------------ 价格


def _call_price(
    verified: VerifiedMixedInput,
    players: Sequence[PlayerState],
    legal: LegalActions,
) -> tuple[int, int, int]:
    """用候选 CALL 资格投影算价格特征；无实际跟注时为 (0, 0, 0)。"""
    problems: list[str] = []
    if legal.can_check and legal.can_call:
        problems.append("可过牌与可跟注同时为真")
    if legal.can_bet and legal.can_raise:
        problems.append("可下注与可加注同时为真")
    if problems:
        raise MixedContextError("；".join(problems))

    actual = legal.actual_call_amount
    if not legal.can_call or actual <= 0:
        return 0, 0, 0
    participants = tuple(
        PotParticipant(
            seat=player.seat,
            total_committed=player.total_committed,
            folded=player.folded,
        )
        for player in players
    )
    projection = project_candidate_call(
        participants=participants,
        caller_seat=verified.actor_seat,
        actual_call_amount=actual,
    )
    eligible = sum(
        layer.amount
        for layer in projection.layers
        if layer.kind in (PotLayerKind.CONTESTED, PotLayerKind.CALLER_RECOVERY)
    )
    denominator = max(actual, eligible)
    return (1000 * actual) // denominator, eligible, actual
