"""手牌历史、复盘与教练解读接口。"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.analysis.hand_review import build_review
from app.llm.coach import explain_decisions
from app.llm.deepseek import DeepSeekProvider
from app.llm.types import CoachUnavailableError
from app.storage import repository
from app.storage.db import get_db
from app.storage.hand_history import project_hand_history
from app.storage.models import HandModel

from . import schemas

router = APIRouter(tags=["hands"])


def get_coach_provider() -> DeepSeekProvider:
    """线上教练上游。测试可替换，避免请求真实接口。"""
    return DeepSeekProvider()


def _hand_summary(hand: HandModel) -> schemas.HandSummary:
    history = project_hand_history(json.loads(hand.history_json))
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
        history=project_hand_history(json.loads(hand.history_json)),
    )


@router.get("/hands/{hand_id}/review", response_model=schemas.HandReview)
def get_review(
    hand_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> schemas.HandReview:
    hand = repository.get_hand(db, hand_id)
    if hand is None:
        raise HTTPException(status_code=404, detail="手牌记录不存在")
    review = build_review(json.loads(hand.history_json))
    return schemas.HandReview(
        hand_id=hand.id,
        hand_number=review["hand_number"],
        human_seat=review["human_seat"],
        reference_strategy=review["reference_strategy"],
        reference_version=review["reference_version"],
        evaluation_version=review["evaluation_version"],
        reference_coverage=review["reference_coverage"],
        reference_scope=review["reference_scope"],
        reference_limitations=review["reference_limitations"],
        decisions=review["decisions"],
        mistake_count=review["mistake_count"],
    )


@router.post("/hands/{hand_id}/explain", response_model=schemas.HandExplanation)
def explain_hand(
    hand_id: str,
    db: Annotated[Session, Depends(get_db)],
    provider: Annotated[Any, Depends(get_coach_provider)],
) -> schemas.HandExplanation:
    """按真人决策点生成中文解读。未缓存的点合并为一次上游请求，失败时不改动复盘。"""
    hand = repository.get_hand(db, hand_id)
    if hand is None:
        raise HTTPException(status_code=404, detail="手牌记录不存在")
    history = json.loads(hand.history_json)
    review = build_review(history)
    if not review["decisions"]:
        return schemas.HandExplanation(hand_id=hand.id, decisions=[])
    try:
        decisions = explain_decisions(
            db,
            hand_id=hand.id,
            history=history,
            review=review,
            provider=provider,
        )
    except CoachUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return schemas.HandExplanation(hand_id=hand.id, decisions=decisions)


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
