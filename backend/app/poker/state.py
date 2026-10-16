"""引擎状态与玩家状态的数据结构。"""

from dataclasses import dataclass, field
from enum import IntEnum

from .cards import Card


class Street(IntEnum):
    """牌局所处阶段。"""

    PREFLOP = 0
    FLOP = 1
    TURN = 2
    RIVER = 3
    SHOWDOWN = 4


@dataclass
class PlayerState:
    """单个玩家的状态。筹码统一使用整数单位，避免浮点误差。"""

    seat: int
    name: str
    stack: int = 0
    hole_cards: list[Card] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    street_bet: int = 0
    total_committed: int = 0
    has_acted_since_full_raise: bool = False


@dataclass(frozen=True)
class GameState:
    """引擎对外暴露的只读快照，供策略等外部模块消费。"""

    street: Street
    board: tuple[Card, ...]
    pot: int
    current_seat: int
    button: int
    hand_over: bool
    players: tuple[PlayerState, ...]
    # 大盲。为 0 表示这份快照没有带盲注，调用方不能据此推断最小筹码单位。
    # 仅关键字传入，避免带默认值的字段挡在子类必填字段之前。
    big_blind: int = field(default=0, kw_only=True)
