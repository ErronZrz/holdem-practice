"""对局接口：创建对局、获取对局、提交动作、下一手。

引擎实例保存在进程内（单用户本地应用），完成的手牌落库到 SQLite；进行中的对局仅
驻留内存，重启后需重新创建。human 固定坐 0 号位，其余座位由 Bot 驱动。

Bot 动作采用「惰性推进」：``GET /games/{id}`` 在轮到 Bot 且距上次动作已超过
``BOT_DELAY`` 时，仅推进一个 Bot 动作。前端通过轮询该接口逐步拉取，从而逐个
播放 Bot 的动作，而不是一次性跑到终局。
"""

import json
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.poker.actions import Action, ActionType, IllegalActionError
from app.poker.engine import PokerEngine
from app.poker.evaluator import evaluate
from app.poker.state import Street
from app.storage import repository
from app.storage.db import get_db
from app.storage.hand_history import build_hand_history
from app.storage.models import utcnow
from app.strategy import Strategy, create_strategy, project_for_actor

from . import schemas

router = APIRouter(prefix="/games", tags=["games"])

_registry: dict[str, "GameRuntime"] = {}

# Bot 相邻两次行动之间的最小间隔（秒），由前端轮询推进逐个播放。
BOT_DELAY = 1.0


@dataclass
class GameRuntime:
    """一个进行中对局的运行态。"""

    session_id: str
    engine: PokerEngine
    bot: Strategy
    human_seat: int
    bot_seats: list[int]
    hand_number: int
    last_bot_ts: float
    # 本局使用的规范策略标识，随每手历史落库以便追溯。
    bot_strategy: str
    last_hand_id: str | None = None


def _make_bot(strategy_name: str, seed: int | None) -> Strategy:
    """经受控注册表构造 Bot，未知标识在此前已由请求校验拦下。"""
    return create_strategy(strategy_name, seed)


def _blind_seats(button: int, num_players: int) -> tuple[int, int]:
    """按庄位推算出小盲/大盲座位，仅用于前端展示标记。"""
    if num_players == 2:
        return button, (button + 1) % 2
    return (button + 1) % num_players, (button + 2) % num_players


def _advance_if_bot_turn(runtime: GameRuntime) -> bool:
    """若轮到 Bot 且距上次行动已超过延迟，则推进一个 Bot 动作，返回是否推进。"""
    engine = runtime.engine
    if engine.hand_over or engine.current_seat not in runtime.bot_seats:
        return False
    if time.monotonic() - runtime.last_bot_ts < BOT_DELAY:
        return False
    # 传入受控投影，保证 Bot 视角拿不到其他座位的暗牌。
    state = project_for_actor(engine.snapshot())
    action = runtime.bot.choose_action(state, engine.legal_actions())
    engine.apply_action(action)
    runtime.last_bot_ts = time.monotonic()
    return True


def _build_action(req: schemas.SubmitActionRequest) -> Action:
    action_type = ActionType(req.action)
    if action_type in (ActionType.BET, ActionType.RAISE):
        if req.amount is None:
            raise HTTPException(status_code=400, detail="下注/加注需要提供金额")
        return Action(action_type, req.amount)
    return Action(action_type, 0)


def _finalize_hand(runtime: GameRuntime, db: Session) -> None:
    """本手结束后持久化 Hand History 并更新对局统计。"""
    engine = runtime.engine
    history = build_hand_history(
        engine,
        runtime.hand_number,
        runtime.human_seat,
        bot_strategy=runtime.bot_strategy,
    )
    human_net = engine.last_net.get(runtime.human_seat, 0)
    hand = repository.add_hand(
        db,
        session_id=runtime.session_id,
        hand_number=runtime.hand_number,
        history_json=json.dumps(history, ensure_ascii=False),
        net=human_net,
    )
    runtime.last_hand_id = hand.id
    session = repository.get_session(db, runtime.session_id)
    session.hands_played += 1
    session.net_chips += human_net
    # target_hands 为 0 表示不限手数，对局不会自动结束。
    if session.target_hands > 0 and session.hands_played >= session.target_hands:
        session.status = "finished"
        session.finished_at = utcnow()
    db.commit()


def build_game_view(runtime: GameRuntime, db: Session) -> schemas.GameView:
    """把运行态 + 持久化对局信息组装成对外视图，遮蔽 Bot 底牌。"""
    engine = runtime.engine
    state = engine.snapshot()
    session = repository.get_session(db, runtime.session_id)
    sb, bb = _blind_seats(engine.button, engine.num_players)

    players = []
    for p in state.players:
        is_human = p.seat == runtime.human_seat
        revealed = is_human or engine.hand_over
        players.append(
            schemas.PlayerView(
                seat=p.seat,
                name=p.name,
                stack=p.stack,
                hole_cards=[str(c) for c in p.hole_cards] if revealed else [],
                cards_revealed=revealed,
                folded=p.folded,
                all_in=p.all_in,
                street_bet=p.street_bet,
                total_committed=p.total_committed,
                is_human=is_human,
                is_button=p.seat == engine.button,
                is_small_blind=p.seat == sb,
                is_big_blind=p.seat == bb,
            )
        )

    legal = None
    is_human_turn = not engine.hand_over and engine.current_seat == runtime.human_seat
    if is_human_turn:
        la = engine.legal_actions()
        legal = schemas.LegalActionsView(
            can_fold=la.can_fold,
            can_check=la.can_check,
            can_call=la.can_call,
            call_amount=la.call_amount,
            actual_call_amount=la.actual_call_amount,
            is_short_all_in_call=la.is_short_all_in_call,
            can_bet=la.can_bet,
            min_bet=la.min_bet,
            max_bet=la.max_bet,
            can_raise=la.can_raise,
            min_raise_to=la.min_raise_to,
            max_raise_to=la.max_raise_to,
        )

    hand_actions = [
        schemas.ActionRecord(
            street=str(a["street"]),
            seat=int(a["seat"]),
            action=str(a["action"]),
            amount=int(a["amount"]),
        )
        for a in engine.history
    ]

    showdown_hands: dict[str, schemas.ShowdownHand] | None = None
    pot_results: list[schemas.PotResult] | None = None
    if engine.street == Street.SHOWDOWN:
        showdown_hands = {
            str(seat): schemas.ShowdownHand(
                cards=[str(c) for c in cards],
                category=evaluate(cards).category.name,
            )
            for seat, cards in engine.showdown_hands.items()
        }
        pot_results = [
            schemas.PotResult(
                amount=int(pr["amount"]),
                winners=list(pr["winners"]),
                shares={int(k): int(v) for k, v in pr["shares"].items()},
            )
            for pr in engine.pot_results
        ]

    return schemas.GameView(
        session_id=runtime.session_id,
        hand_number=runtime.hand_number,
        hands_played=session.hands_played,
        target_hands=session.target_hands,
        small_blind=engine.small_blind,
        big_blind=engine.big_blind,
        session_finished=session.status == "finished",
        hand_over=engine.hand_over,
        street=state.street.name.lower(),
        board=[str(c) for c in state.board],
        pot=state.pot,
        button=engine.button,
        current_seat=state.current_seat if not engine.hand_over else None,
        human_seat=runtime.human_seat,
        is_human_turn=is_human_turn,
        players=players,
        legal_actions=legal,
        hand_actions=hand_actions,
        showdown_hands=showdown_hands,
        pot_results=pot_results,
        winners=list(engine.winners),
        last_net=dict(engine.last_net),
        last_hand_id=runtime.last_hand_id,
    )


@router.post("", response_model=schemas.GameView, status_code=201)
def create_game(
    req: schemas.CreateGameRequest,
    db: Annotated[Session, Depends(get_db)],
) -> schemas.GameView:
    if req.big_blind % 2 != 0:
        raise HTTPException(status_code=400, detail="大盲必须是偶数")
    # 小盲固定为大盲的一半；显式传入时校验一致，避免与旧客户端口径漂移。
    small_blind = req.big_blind // 2
    if req.small_blind is not None and req.small_blind != small_blind:
        raise HTTPException(status_code=400, detail="小盲必须等于大盲的一半")
    session = repository.create_session(
        db,
        num_players=req.num_players,
        human_seat=0,
        small_blind=small_blind,
        big_blind=req.big_blind,
        starting_stack=req.starting_stack,
        target_hands=req.target_hands,
        bot_strategy=req.bot_strategy,
    )
    db.commit()

    engine = PokerEngine(
        req.num_players,
        small_blind,
        req.big_blind,
        req.starting_stack,
        seed=req.seed,
    )
    runtime = GameRuntime(
        session_id=session.id,
        engine=engine,
        bot=_make_bot(req.bot_strategy, req.seed),
        human_seat=0,
        bot_seats=[seat for seat in range(req.num_players) if seat != 0],
        hand_number=1,
        last_bot_ts=time.monotonic(),
        bot_strategy=req.bot_strategy,
    )
    engine.start_hand()
    if engine.hand_over:
        _finalize_hand(runtime, db)
    _registry[runtime.session_id] = runtime
    return build_game_view(runtime, db)


@router.get("", response_model=list[schemas.SessionSummary])
def list_games(db: Annotated[Session, Depends(get_db)]) -> list[schemas.SessionSummary]:
    return [
        schemas.SessionSummary(
            id=s.id,
            created_at=s.created_at.isoformat(),
            num_players=s.num_players,
            big_blind=s.big_blind,
            target_hands=s.target_hands,
            hands_played=s.hands_played,
            status=s.status,
            net_chips=s.net_chips,
        )
        for s in repository.list_sessions(db)
    ]


@router.get("/{game_id}", response_model=schemas.GameView)
def get_game(
    game_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> schemas.GameView:
    runtime = _registry.get(game_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="对局不存在或已不在内存中")
    if _advance_if_bot_turn(runtime) and runtime.engine.hand_over:
        _finalize_hand(runtime, db)
    return build_game_view(runtime, db)


@router.post("/{game_id}/actions", response_model=schemas.GameView)
def submit_action(
    game_id: str,
    req: schemas.SubmitActionRequest,
    db: Annotated[Session, Depends(get_db)],
) -> schemas.GameView:
    runtime = _registry.get(game_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="对局不存在或已不在内存中")
    engine = runtime.engine
    if engine.hand_over:
        raise HTTPException(status_code=400, detail="本手已结束，请进入下一手")
    if engine.current_seat != runtime.human_seat:
        raise HTTPException(status_code=400, detail="当前不是你的行动回合")

    action = _build_action(req)
    try:
        engine.apply_action(action)
    except IllegalActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 真人刚行动完，重置 Bot 计时，让下一个 Bot 动作间隔一个 BOT_DELAY 再播放。
    runtime.last_bot_ts = time.monotonic()
    if engine.hand_over:
        _finalize_hand(runtime, db)
    return build_game_view(runtime, db)


@router.post("/{game_id}/next-hand", response_model=schemas.GameView)
def next_hand(
    game_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> schemas.GameView:
    runtime = _registry.get(game_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="对局不存在或已不在内存中")
    engine = runtime.engine
    if not engine.hand_over:
        raise HTTPException(status_code=400, detail="当前手尚未结束")
    session = repository.get_session(db, game_id)
    if session.status == "finished":
        raise HTTPException(status_code=400, detail="本局已结束")

    runtime.hand_number += 1
    engine.start_hand()
    runtime.last_bot_ts = time.monotonic()
    if engine.hand_over:
        _finalize_hand(runtime, db)
    return build_game_view(runtime, db)
