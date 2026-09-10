"""基于牌力的启发式策略：强牌加注、中牌跟注、弱牌弃牌，并对边缘牌做赔率修正。

牌力评估分两段：
- 翻牌前：用 Chen 公式给两张底牌打分，按分数划分强/中/弱；小对子单独识别为博暗三条，
  同花/连张等投机边缘牌、A 配大踢脚的高牌在赔率合适时允许跟注，避免「见注就弃」。
- 翻牌后：用 evaluate(底牌 + 公共牌) 得到 HandRank 分档，并区分底牌是否真正击中——公共牌三条时
  底牌只是踢脚、胜率不高；顶对/两对/底牌三条/顺子/同花主动价值下注，非葫芦的强牌面对加注只跟注；
  高牌时识别顺子/同花听牌，按补牌数决定半诈唬、赔率跟注或弃牌。

下注/加注额度约为一个底池大小，夹在合法区间内。本策略为确定性策略，暂不做位置感知。
"""

import math
from collections import Counter

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import Card, Rank, Suit
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

# 翻牌后听牌补牌数阈值：强听牌可半诈唬 / 常规听牌可跟注 / 弱听牌仅极便宜跟注。
_DRAW_STRONG_OUTS = 12
_DRAW_OUTS = 8
_DRAW_WEAK_OUTS = 4
# 翻牌后听牌跟注上限（相对底池的倍数，用分子/分母表达避免浮点）。
_DRAW_CALL_NUM = 3
_DRAW_CALL_DEN = 4
_WEAK_DRAW_CALL_NUM = 1
_WEAK_DRAW_CALL_DEN = 4


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


def _board_has_trips(board: tuple[Card, ...]) -> bool:
    """公共牌是否已有三张同点（此时所有玩家保底三条，底牌只是踢脚）。"""
    return any(count >= 3 for count in Counter(c.rank.value for c in board).values())


class HeuristicStrategy:
    """确定性启发式 Bot，依据牌力与赔率选择动作。"""

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
        rank = evaluate([*me.hole_cards, *state.board])

        if rank.category >= HandCategory.FULL_HOUSE:
            # 葫芦及以上：最强价值牌，可激进下注/加注。
            return self._aggressive(state, legal, me)

        if rank.category == HandCategory.THREE_OF_A_KIND:
            if _board_has_trips(state.board):
                # 公共牌三条（如翻牌 AAA）：底牌只是踢脚，胜率不高，保守处理。
                return self._value_action(state, legal)
            # 底牌参与的三条（set / trip）：真正强牌，主动下注、面对下注跟注。
            return self._strong_value_action(state, legal)

        if rank.category >= HandCategory.STRAIGHT:
            # 顺子/同花：主动下注，面对加注只跟注。
            return self._strong_value_action(state, legal)

        if rank.category == HandCategory.TWO_PAIR:
            # 两对：强价值牌，无人下注时主动下注。
            return self._value_action(state, legal)

        if rank.category == HandCategory.ONE_PAIR:
            pair_rank = rank.tiebreak[0]
            board_high = max(c.rank.value for c in state.board)
            if pair_rank >= board_high:
                # 顶对或超对：主动价值下注。
                return self._value_action(state, legal)
            # 中/底对：控池，免费过牌，面对合理下注跟注。
            if legal.can_check:
                return Action(ActionType.CHECK)
            if legal.can_call and _call_within(
                legal.call_amount, state.pot, _MEDIUM_CALL_NUM, _MEDIUM_CALL_DEN
            ):
                return Action(ActionType.CALL)
            return Action(ActionType.FOLD)

        # 高牌：翻牌/转牌时识别听牌；河牌已无补牌可言。
        if len(state.board) < 5:
            outs = _draw_outs(me.hole_cards, state.board)
            if outs >= _DRAW_STRONG_OUTS:
                # 强听牌（组合听）：主动半诈唬，否则跟注/过牌。
                if legal.can_bet:
                    return Action(ActionType.BET, self._bet_amount(state, legal))
                if legal.can_raise:
                    return Action(ActionType.RAISE, self._raise_amount(state, legal, me))
                if legal.can_call:
                    return Action(ActionType.CALL)
                return Action(ActionType.CHECK)
            if outs >= _DRAW_OUTS:
                # 同花/两头顺：赔率合适则跟注。
                if legal.can_check:
                    return Action(ActionType.CHECK)
                if legal.can_call and _call_within(
                    legal.call_amount, state.pot, _DRAW_CALL_NUM, _DRAW_CALL_DEN
                ):
                    return Action(ActionType.CALL)
                return Action(ActionType.FOLD)
            if outs >= _DRAW_WEAK_OUTS:
                # 卡顺等弱听牌：仅在极便宜时跟注。
                if legal.can_check:
                    return Action(ActionType.CHECK)
                if legal.can_call and _call_within(
                    legal.call_amount, state.pot, _WEAK_DRAW_CALL_NUM, _WEAK_DRAW_CALL_DEN
                ):
                    return Action(ActionType.CALL)
                return Action(ActionType.FOLD)

        # 纯空气：免费则过牌，否则弃牌。
        return Action(ActionType.CHECK) if legal.can_check else Action(ActionType.FOLD)

    # ------------------------------------------------------------------ 动作构造

    def _strong_value_action(self, state: GameState, legal: LegalActions) -> Action:
        """顺子/同花/三条：无人下注时主动下注，面对下注跟注（不主动加注）。"""
        if legal.can_bet:
            return Action(ActionType.BET, self._bet_amount(state, legal))
        if legal.can_call:
            return Action(ActionType.CALL)
        return Action(ActionType.CHECK)

    def _value_action(self, state: GameState, legal: LegalActions) -> Action:
        """中等价值牌：无人下注时主动下注，面对下注按赔率跟注（不主动加注）。"""
        if legal.can_bet:
            return Action(ActionType.BET, self._bet_amount(state, legal))
        if legal.can_check:
            return Action(ActionType.CHECK)
        if legal.can_call and _call_within(
            legal.call_amount, state.pot, _MEDIUM_CALL_NUM, _MEDIUM_CALL_DEN
        ):
            return Action(ActionType.CALL)
        return Action(ActionType.FOLD)

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
