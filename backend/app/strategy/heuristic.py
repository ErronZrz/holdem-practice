"""基于牌力的启发式策略：强牌加注、中牌跟注、弱牌弃牌。

牌力评估分两段：
- 翻牌前：用 Chen 公式给两张底牌打分，映射到强/中/弱三档。
- 翻牌后：用 evaluate(底牌 + 公共牌) 得到 HandRank，按牌型映射到三档。

动作倾向：
- 强牌：能下注/加注就下注/加注，否则过牌/跟注。
- 中牌：能过牌就过牌，否则跟注。
- 弱牌：能过牌就过牌，否则弃牌。

本策略为确定性策略，初期不做位置感知；下注/加注额度约为一个底池大小。
"""

import math
from enum import IntEnum

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import Card
from app.poker.evaluator import evaluate
from app.poker.hand import HandCategory
from app.poker.state import GameState, PlayerState, Street

from .interface import hero


class Strength(IntEnum):
    """牌力档位，数值越大越强。"""

    WEAK = 0
    MEDIUM = 1
    STRONG = 2


# Chen 分数阈值：达到强牌 / 中牌的下限。
_STRONG_CHEN = 12
_MEDIUM_CHEN = 8


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


def _preflop_strength(hole_cards: list[Card]) -> Strength:
    ranks = sorted((c.rank.value for c in hole_cards), reverse=True)
    suited = hole_cards[0].suit == hole_cards[1].suit
    score = _chen_score(ranks[0], ranks[1], suited)
    if score >= _STRONG_CHEN:
        return Strength.STRONG
    if score >= _MEDIUM_CHEN:
        return Strength.MEDIUM
    return Strength.WEAK


def _postflop_strength(hole_cards: list[Card], board: tuple[Card, ...]) -> Strength:
    rank = evaluate([*hole_cards, *board])
    if rank.category >= HandCategory.THREE_OF_A_KIND:
        return Strength.STRONG
    if rank.category >= HandCategory.ONE_PAIR:
        return Strength.MEDIUM
    return Strength.WEAK


class HeuristicStrategy:
    """确定性启发式 Bot，依据牌力档位选择动作。"""

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        me = hero(state)
        if state.street == Street.PREFLOP:
            strength = _preflop_strength(me.hole_cards)
        else:
            strength = _postflop_strength(me.hole_cards, state.board)
        return self._select(strength, state, legal, me)

    def _select(
        self,
        strength: Strength,
        state: GameState,
        legal: LegalActions,
        me: PlayerState,
    ) -> Action:
        if strength == Strength.WEAK:
            return Action(ActionType.CHECK) if legal.can_check else Action(ActionType.FOLD)
        if strength == Strength.MEDIUM:
            return Action(ActionType.CHECK) if legal.can_check else Action(ActionType.CALL)
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
