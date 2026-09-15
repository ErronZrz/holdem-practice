"""Session / Hand 的持久化读写。

函数均不自行 commit，由调用方（API 层）控制事务边界。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import HandModel, SessionModel


def _new_id() -> str:
    return uuid.uuid4().hex


def create_session(
    db: Session,
    *,
    num_players: int,
    human_seat: int,
    small_blind: int,
    big_blind: int,
    starting_stack: int,
    target_hands: int | None,
    bot_strategy: str,
) -> SessionModel:
    """新建对局记录并落库（flush，不 commit）。target_hands 为 None 时落库 0，表示不限手数。"""
    session = SessionModel(
        id=_new_id(),
        num_players=num_players,
        human_seat=human_seat,
        small_blind=small_blind,
        big_blind=big_blind,
        starting_stack=starting_stack,
        target_hands=target_hands or 0,
        bot_strategy=bot_strategy,
    )
    db.add(session)
    db.flush()
    return session


def get_session(db: Session, session_id: str) -> SessionModel | None:
    return db.get(SessionModel, session_id)


def list_sessions(db: Session) -> list[SessionModel]:
    return list(db.scalars(select(SessionModel).order_by(SessionModel.created_at.desc())))


def add_hand(
    db: Session,
    *,
    session_id: str,
    hand_number: int,
    history_json: str,
    net: int,
) -> HandModel:
    """记录一手牌，history_json 为完整 Hand History（source of truth）。"""
    hand = HandModel(
        id=_new_id(),
        session_id=session_id,
        hand_number=hand_number,
        history_json=history_json,
        net=net,
    )
    db.add(hand)
    return hand


def get_hand(db: Session, hand_id: str) -> HandModel | None:
    return db.get(HandModel, hand_id)


def list_hands(db: Session, session_id: str) -> list[HandModel]:
    return list(
        db.scalars(
            select(HandModel)
            .where(HandModel.session_id == session_id)
            .order_by(HandModel.hand_number)
        )
    )
