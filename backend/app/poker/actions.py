"""动作类型、动作对象与合法动作集合。"""

from dataclasses import dataclass
from enum import Enum


class ActionType(Enum):
    """玩家可执行的动作类型。"""

    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    BET = "bet"
    RAISE = "raise"


@dataclass(frozen=True)
class Action:
    """一次具体动作。BET/RAISE 的 amount 为下注/加注后的总额。"""

    type: ActionType
    amount: int = 0


@dataclass(frozen=True)
class LegalActions:
    """当前玩家可执行动作的完整描述，供策略采样。"""

    can_fold: bool
    can_check: bool
    can_call: bool
    call_amount: int
    can_bet: bool
    min_bet: int
    max_bet: int
    can_raise: bool
    min_raise_to: int
    max_raise_to: int


class IllegalActionError(ValueError):
    """非法动作异常。"""
