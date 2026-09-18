"""受控局面投影：把完整快照裁剪为「公开信息 + 行动者自己的底牌」。

引擎快照出于回放/复盘目的保留了所有玩家底牌，但策略视角只能看到公开信息。
本模块提供唯一入口，保证其他座位暗牌、未发出的公共牌与随机源不会进入策略。
"""

from app.poker.state import GameState, PlayerState


def project_for_actor(state: GameState) -> GameState:
    """返回当前行动者视角的投影：其他座位底牌置空，其余公开字段原样保留。"""
    actor = state.current_seat
    players = tuple(
        PlayerState(
            seat=p.seat,
            name=p.name,
            stack=p.stack,
            hole_cards=list(p.hole_cards) if p.seat == actor else [],
            folded=p.folded,
            all_in=p.all_in,
            street_bet=p.street_bet,
            total_committed=p.total_committed,
            has_acted_since_full_raise=p.has_acted_since_full_raise,
        )
        for p in state.players
    )
    return GameState(
        street=state.street,
        board=tuple(state.board),
        pot=state.pot,
        current_seat=state.current_seat,
        button=state.button,
        hand_over=state.hand_over,
        players=players,
    )
