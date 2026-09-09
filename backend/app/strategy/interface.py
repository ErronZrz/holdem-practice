"""策略统一接口与信息边界约定。

策略只能通过 GameState 与引擎交互（AGENTS 原则 2），不得直接改动引擎内部状态。

信息边界：引擎的 GameState 快照出于测试/复盘目的保留了所有玩家的 hole_cards。
策略在真实对局中不得读取对手底牌，只允许读取以下公开信息：

- 当前行动玩家（``state.players[state.current_seat]``）自己的 hole_cards；
- 公共牌 ``state.board``、底池 ``state.pot``、阶段 ``state.street``、庄位 ``state.button``；
- 各玩家的公开状态：stack / folded / all_in / street_bet / total_committed。

严禁访问 ``state.players[i].hole_cards``（其中 ``i != state.current_seat``）。
"""

from typing import Protocol

from app.poker.actions import Action, LegalActions
from app.poker.state import GameState, PlayerState


class Strategy(Protocol):
    """插件式 Bot 策略的统一接口，与位置、具体牌型解耦。"""

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        """根据当前局面返回一个合法动作。"""
        ...


def hero(state: GameState) -> PlayerState:
    """返回当前行动玩家，即策略视角下的「自己」。"""
    return state.players[state.current_seat]
