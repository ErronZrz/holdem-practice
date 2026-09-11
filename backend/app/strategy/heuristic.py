"""基于胜率的启发式策略：翻牌前按 Chen 分档，翻牌后按蒙特卡洛胜率 + 底池赔率决策。

牌力评估分两段：
- 翻牌前：用 Chen 公式给两张底牌打分，按分数划分强/中/弱；小对子单独识别为博暗三条，
  同花/连张等投机边缘牌、A 配大踢脚的高牌在赔率合适时允许跟注，避免「见注就弃」。
- 翻牌后：用蒙特卡洛估计「赢过所有仍在场对手的随机底牌」的胜率（静态摊牌胜率），
  以胜率阈值决定价值下注 / 跟注 / 弃牌，并以底池赔率作为跟注的量化判据；
  强听牌半诈唬，纯空气按小概率诈唬以平衡下注范围。

下注/加注额度约为一个底池大小，夹在合法区间内。随机源可注入 seed 以复现（AGENTS 原则 4）。
"""

import math
import random

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import Card, Rank, Suit
from app.poker.equity import equity
from app.poker.evaluator import evaluate
from app.poker.hand import HandCategory
from app.poker.state import GameState, PlayerState, Street

from .interface import hero

# Chen 分数阈值：达到强牌 / 中牌的下限。
_STRONG_CHEN = 12
_MEDIUM_CHEN = 8
# 投机边缘牌的最低 Chen 分数：低于它视为纯垃圾牌，面对任何下注都弃。
_SPECULATIVE_CHEN = 5

# 中牌跟注上限：跟注额不超过底池的 3/2（超出则视为巨注，弃牌）。
_MEDIUM_CALL_NUM = 3
_MEDIUM_CALL_DEN = 2
# 投机边缘牌跟注上限：跟注额不超过底池的 1/2。
_SPECULATIVE_CALL_NUM = 1
_SPECULATIVE_CALL_DEN = 2
# 小对子博暗三条的隐含赔率下限：跟注额不超过剩余筹码的 1/15。
_SET_MINE_IMPLIED = 15
# A 配大踢脚（另一张不低于 T）视为中牌：Chen 公式对 ATo 打分偏低，避免其被过早弃掉。
_ACE_HIGH_KICKER = 10

# 翻牌后蒙特卡洛采样数：越大胜率越准、越慢。
_SAMPLES = 500
# 胜率阈值：无人下注时达到该值才主动价值下注。
_VALUE_BET_EQ = 0.70
# 胜率阈值：面对下注时达到该值才再加注。
_RAISE_EQ = 0.90
# 胜率阈值：低于该值视为纯空气，面对任何下注都弃牌，仅在小概率下诈唬。
_AIR_EQ = 0.25
# 纯空气诈唬频率（无人下注时）。
_BLUFF_FREQ = 0.10
# 半诈唬所需的补牌数（组合听牌）。
_DRAW_STRONG_OUTS = 12


def _chen_score(hi: int, lo: int, suited: bool) -> int:
    """按 Chen 公式给两手牌打分，返回非负整数。"""

    def high_value(rank: int) -> float:
        if rank == 14:
            return 10.0
        if rank == 13:
            return 8.0
        if rank == 12:
            return 7.0
        if rank == 11:
            return 6.0
        return rank / 2.0

    if hi == lo:
        return max(5, math.ceil(high_value(hi) * 2))

    score = high_value(hi)
    if suited:
        score += 2
    gap = hi - lo - 1
    if gap == 1:
        score -= 1
    elif gap == 2:
        score -= 2
    elif gap == 3:
        score -= 4
    elif gap >= 4:
        score -= 5
    if gap <= 1 and hi < 12:
        score += 1
    return max(0, math.ceil(score))


def _call_within(call_amount: int, pot: int, num: int, den: int) -> bool:
    """跟注额是否不超过底池的 num/den 倍（整数比较，避免浮点误差）。"""
    return call_amount * den <= pot * num


def _set_mine_within(call_amount: int, stack: int) -> bool:
    """小对子博暗三条的隐含赔率是否足够（跟注额不超过剩余筹码的 1/15）。"""
    return call_amount * _SET_MINE_IMPLIED <= stack


def _draw_outs(hole_cards: list[Card], board: tuple[Card, ...]) -> int:
    """统计「再发一张牌即可形成顺子或更高级牌型」的补牌数，用于衡量听牌强度。"""
    known = set(hole_cards) | set(board)
    outs = 0
    for suit in Suit:
        for rank in Rank:
            card = Card(rank, suit)
            if card in known:
                continue
            if evaluate([*hole_cards, *board, card]).category >= HandCategory.STRAIGHT:
                outs += 1
    return outs


def _num_opponents(state: GameState) -> int:
    """仍在场的对手数量（排除自己与已弃牌/全下的玩家）。"""
    return sum(
        1
        for p in state.players
        if p.seat != state.current_seat and not p.folded and not p.all_in
    )


class HeuristicStrategy:
    """基于胜率的启发式 Bot：翻牌前按 Chen 分档，翻牌后按胜率 + 赔率决策。"""

    def __init__(
        self,
        seed: int | None = None,
        samples: int = _SAMPLES,
        bluff_freq: float = _BLUFF_FREQ,
    ) -> None:
        self._rng = random.Random(seed)
        self._samples = samples
        self._bluff_freq = bluff_freq

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        me = hero(state)
        if state.street == Street.PREFLOP:
            return self._preflop_action(state, legal, me)
        return self._postflop_action(state, legal, me)

    # ------------------------------------------------------------------ 翻牌前

    def _preflop_action(
        self,
        state: GameState,
        legal: LegalActions,
        me: PlayerState,
    ) -> Action:
        ranks = sorted((c.rank.value for c in me.hole_cards), reverse=True)
        suited = me.hole_cards[0].suit == me.hole_cards[1].suit
        score = _chen_score(ranks[0], ranks[1], suited)
        is_pair = ranks[0] == ranks[1]
        ace_high = ranks[0] == 14 and ranks[1] >= _ACE_HIGH_KICKER

        if score >= _STRONG_CHEN:
            return self._aggressive(state, legal, me)

        if score >= _MEDIUM_CHEN or ace_high:
            # 中等牌或 A 大踢脚高牌：免费过牌；面对合理下注跟注，面对巨注弃牌。
            if legal.can_check:
                return Action(ActionType.CHECK)
            if legal.can_call and _call_within(
                legal.call_amount, state.pot, _MEDIUM_CALL_NUM, _MEDIUM_CALL_DEN
            ):
                return Action(ActionType.CALL)
            return Action(ActionType.FOLD)

        if is_pair:
            # 小对子：博暗三条，只有隐含赔率足够时才跟注。
            if legal.can_check:
                return Action(ActionType.CHECK)
            if legal.can_call and _set_mine_within(legal.call_amount, me.stack):
                return Action(ActionType.CALL)
            return Action(ActionType.FOLD)

        if score >= _SPECULATIVE_CHEN:
            # 同花/连张等投机边缘牌：面对小注可便宜看牌，面对大注弃牌。
            if legal.can_check:
                return Action(ActionType.CHECK)
            if legal.can_call and _call_within(
                legal.call_amount, state.pot, _SPECULATIVE_CALL_NUM, _SPECULATIVE_CALL_DEN
            ):
                return Action(ActionType.CALL)
            return Action(ActionType.FOLD)

        # 纯垃圾牌：免费则过牌，否则弃牌。
        return Action(ActionType.CHECK) if legal.can_check else Action(ActionType.FOLD)

    # ------------------------------------------------------------------ 翻牌后

    def _postflop_action(
        self,
        state: GameState,
        legal: LegalActions,
        me: PlayerState,
    ) -> Action:
        opps = _num_opponents(state)
        eq = equity(me.hole_cards, state.board, opps, self._rng, self._samples)

        if legal.call_amount > 0:
            # 面对下注：按胜率与底池赔率决定跟注/加注/弃牌。
            pot_odds = legal.call_amount / (state.pot + legal.call_amount)
            if eq >= _RAISE_EQ and legal.can_raise:
                return Action(ActionType.RAISE, self._raise_amount(state, legal, me))
            if eq >= _AIR_EQ and eq >= pot_odds:
                return Action(ActionType.CALL)
            return Action(ActionType.FOLD)

        # 无人下注：按胜率决定价值下注、半诈唬、诈唬或过牌。
        if legal.can_bet:
            if eq >= _VALUE_BET_EQ:
                return Action(ActionType.BET, self._bet_amount(state, legal))
            outs = _draw_outs(me.hole_cards, state.board) if len(state.board) < 5 else 0
            if outs >= _DRAW_STRONG_OUTS:
                return Action(ActionType.BET, self._bet_amount(state, legal))
            if eq < _AIR_EQ and self._rng.random() < self._bluff_freq:
                return Action(ActionType.BET, self._bet_amount(state, legal))
        return Action(ActionType.CHECK)

    # ------------------------------------------------------------------ 动作构造

    def _aggressive(
        self,
        state: GameState,
        legal: LegalActions,
        me: PlayerState,
    ) -> Action:
        """强牌：能下注就下注、能加注就加注，否则过牌/跟注。"""
        if legal.can_bet:
            return Action(ActionType.BET, self._bet_amount(state, legal))
        if legal.can_raise:
            return Action(ActionType.RAISE, self._raise_amount(state, legal, me))
        return Action(ActionType.CHECK) if legal.can_check else Action(ActionType.CALL)

    def _bet_amount(self, state: GameState, legal: LegalActions) -> int:
        # 下注约一个底池，夹在合法区间内。
        return min(legal.max_bet, max(legal.min_bet, state.pot))

    def _raise_amount(self, state: GameState, legal: LegalActions, me: PlayerState) -> int:
        # 加注后总额约为「当前跟注额 + 一个底池」，夹在合法区间内。
        current_bet = me.street_bet + legal.call_amount
        target = current_bet + state.pot
        return min(legal.max_raise_to, max(legal.min_raise_to, target))
