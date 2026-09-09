"""手牌历史与结算/统计接口。"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.storage import repository
from app.storage.db import get_db
from app.storage.models import HandModel

from . import schemas

router = APIRouter(tags=["hands"])


def _hand_summary(hand: HandModel) -> schemas.HandSummary:
    history = json.loads(hand.history_json)
    return schemas.HandSummary(
        id=hand.id,
        session_id=hand.session_id,
        hand_number=hand.hand_number,
        created_at=hand.created_at.isoformat(),
        net=hand.net,
        winners=history.get("winners", []),
        showdown=history.get("showdown", False),
        board=history.get("board", []),
        street=history.get("street", ""),
    )


@router.get("/games/{game_id}/hands", response_model=list[schemas.HandSummary])
def list_hands(
    game_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> list[schemas.HandSummary]:
    return [_hand_summary(h) for h in repository.list_hands(db, game_id)]


@router.get("/hands/{hand_id}", response_model=schemas.HandDetail)
def get_hand(
    hand_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> schemas.HandDetail:
    hand = repository.get_hand(db, hand_id)
    if hand is None:
        raise HTTPException(status_code=404, detail="手牌记录不存在")
    return schemas.HandDetail(
        id=hand.id,
        session_id=hand.session_id,
        hand_number=hand.hand_number,
        created_at=hand.created_at.isoformat(),
        history=json.loads(hand.history_json),
    )


@router.get("/games/{game_id}/stats", response_model=schemas.SessionStats)
def get_stats(
    game_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> schemas.SessionStats:
    session = repository.get_session(db, game_id)
    if session is None:
        raise HTTPException(status_code=404, detail="对局不存在")
    hands = repository.list_hands(db, game_id)
    wins = losses = ties = 0
    for hand in hands:
        if hand.net > 0:
            wins += 1
        elif hand.net < 0:
            losses += 1
        else:
            ties += 1
    return schemas.SessionStats(
        session_id=session.id,
        status=session.status,
        num_players=session.num_players,
        big_blind=session.big_blind,
        target_hands=session.target_hands,
        hands_played=session.hands_played,
        net_chips=session.net_chips,
        wins=wins,
        losses=losses,
        ties=ties,
    )
