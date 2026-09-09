"""随机策略：从合法动作中均匀随机选择，金额在合法区间内随机。"""

import random

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.state import GameState


class RandomStrategy:
    """从合法动作中随机采样，seed 可注入以保证可复现。"""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        options: list[Action] = []
        if legal.can_fold:
            options.append(Action(ActionType.FOLD))
        if legal.can_check:
            options.append(Action(ActionType.CHECK))
        if legal.can_call:
            options.append(Action(ActionType.CALL))
        if legal.can_bet:
            options.append(
                Action(ActionType.BET, self._rng.randint(legal.min_bet, legal.max_bet))
            )
        if legal.can_raise:
            options.append(
                Action(ActionType.RAISE, self._rng.randint(legal.min_raise_to, legal.max_raise_to))
            )
        return self._rng.choice(options)
