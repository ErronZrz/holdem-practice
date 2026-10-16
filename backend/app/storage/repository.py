"""Session / Hand 与教练解读缓存的持久化读写。

函数均不自行 commit，由调用方控制事务边界。
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CoachExplanationModel, HandModel, SessionModel


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


def get_coach_explanation(db: Session, cache_key: str) -> CoachExplanationModel | None:
    """按决策缓存键读取一条教练解读。"""
    return db.get(CoachExplanationModel, cache_key)


def add_coach_explanation(
    db: Session,
    *,
    cache_key: str,
    hand_id: str,
    action_index: int,
    seat: int,
    provider: str,
    model: str,
    prompt_schema_version: int,
    explanation: str,
    reasoning_summary: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int,
    total_tokens: int,
) -> CoachExplanationModel:
    """写入一条教练解读（flush，不 commit）。"""
    row = CoachExplanationModel(
        cache_key=cache_key,
        hand_id=hand_id,
        action_index=action_index,
        seat=seat,
        provider=provider,
        model=model,
        prompt_schema_version=prompt_schema_version,
        explanation=explanation,
        reasoning_summary=reasoning_summary,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=total_tokens,
    )
    db.add(row)
    db.flush()
    return row
