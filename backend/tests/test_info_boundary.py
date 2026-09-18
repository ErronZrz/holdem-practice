"""信息边界测试：受控局面投影、历史 JSON 版本化与白名单投影、seed 不外发。"""

import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.poker.actions import LegalActions
from app.poker.cards import Card
from app.poker.state import GameState, PlayerState, Street
from app.storage import repository
from app.storage.db import get_db, init_db
from app.storage.hand_history import project_hand_history
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.projection import project_for_actor

from .helpers import cards


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield


def _all_keys(obj: object) -> set[str]:
    """递归收集 JSON 结构中的全部键名，用于检查敏感字段是否外泄。"""
    if isinstance(obj, dict):
        keys = set(obj)
        for value in obj.values():
            keys |= _all_keys(value)
        return keys
    if isinstance(obj, list):
        keys: set[str] = set()
        for value in obj:
            keys |= _all_keys(value)
        return keys
    return set()


def _hero_state(opponent_holes: list[list[Card]]) -> GameState:
    """构造行动者为座位 0、仅对手底牌不同的翻牌局面。"""
    players = [PlayerState(seat=0, name="p0", hole_cards=cards("As Kd"), stack=1000)]
    for seat, hole in enumerate(opponent_holes, start=1):
        players.append(PlayerState(seat=seat, name=f"p{seat}", hole_cards=list(hole), stack=1000))
    return GameState(
        street=Street.FLOP,
        board=tuple(cards("2c 7d 9h")),
        pot=100,
        current_seat=0,
        button=0,
        hand_over=False,
        players=tuple(players),
    )


def _legal(**kwargs) -> LegalActions:
    defaults = dict(
        can_fold=True,
        can_check=False,
        can_call=False,
        call_amount=0,
        actual_call_amount=0,
        is_short_all_in_call=False,
        can_bet=False,
        min_bet=0,
        max_bet=0,
        can_raise=False,
        min_raise_to=0,
        max_raise_to=0,
    )
    defaults.update(kwargs)
    return LegalActions(**defaults)


# ------------------------------------------------------------------ 局面投影


def test_projection_keeps_only_actor_hole_cards() -> None:
    state = _hero_state([cards("Qh Jc"), cards("Ts 9s")])
    projected = project_for_actor(state)

    assert projected.players[0].hole_cards == cards("As Kd")
    assert projected.players[1].hole_cards == []
    assert projected.players[2].hole_cards == []
    # 公开字段与局面元数据原样保留。
    assert projected.board == state.board
    assert projected.pot == state.pot
    assert projected.current_seat == state.current_seat
    assert projected.players[1].folded == state.players[1].folded
    assert projected.players[1].stack == state.players[1].stack


def test_projection_has_no_seed_field() -> None:
    projected = project_for_actor(_hero_state([cards("Qh Jc")]))
    assert "seed" not in _all_keys(dataclasses.asdict(projected))


def test_hidden_cards_do_not_change_projection_or_distribution() -> None:
    state_a = _hero_state([cards("Qh Jc"), cards("Ts 9s")])
    state_b = _hero_state([cards("7c 2d"), cards("Ah Ad")])
    assert state_a != state_b

    projected_a = project_for_actor(state_a)
    projected_b = project_for_actor(state_b)
    assert projected_a == projected_b

    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=1000)
    dist_a = HeuristicStrategy(seed=0, samples=200).action_distribution(projected_a, legal)
    dist_b = HeuristicStrategy(seed=0, samples=200).action_distribution(projected_b, legal)
    assert dist_a == dist_b


# ------------------------------------------------------------------ 历史投影


def test_projection_drops_unregistered_keys() -> None:
    raw = {
        "schema_version": "hand-history.v1",
        "hand_number": 1,
        "winners": [0],
        "master_seed": 12345,
        "rng_state": "leak",
    }
    projected = project_hand_history(raw)

    assert "master_seed" not in projected
    assert "rng_state" not in projected
    assert projected["hand_number"] == 1
    assert projected["winners"] == [0]
    assert projected["schema_version"] == "hand-history.v1"
    assert projected["bot_strategy"] == "unknown"


def test_legacy_history_is_read_as_unknown() -> None:
    db = next(get_db())
    try:
        session = repository.create_session(
            db,
            num_players=2,
            human_seat=0,
            small_blind=5,
            big_blind=10,
            starting_stack=1000,
            target_hands=5,
            bot_strategy="heuristic",
        )
        db.commit()
        legacy = {
            "hand_number": 1,
            "board": [],
            "winners": [0],
            "showdown": False,
            "net": {"0": 5, "1": -5},
            "actions": [],
            "players": [],
        }
        hand = repository.add_hand(
            db,
            session_id=session.id,
            hand_number=1,
            history_json=json.dumps(legacy, ensure_ascii=False),
            net=5,
        )
        db.commit()
        hand_id = hand.id
    finally:
        db.close()

    body = TestClient(app).get(f"/hands/{hand_id}").json()
    history = body["history"]
    assert history["schema_version"] == "unknown"
    assert history["bot_strategy"] == "unknown"
    # 已知的旧字段仍按白名单透出，历史视图不因缺版本而不可用。
    assert history["winners"] == [0]
    assert history["net"] == {"0": 5, "1": -5}


def test_legacy_history_summary_still_works() -> None:
    db = next(get_db())
    try:
        session = repository.create_session(
            db,
            num_players=2,
            human_seat=0,
            small_blind=5,
            big_blind=10,
            starting_stack=1000,
            target_hands=5,
            bot_strategy="heuristic",
        )
        db.commit()
        session_id = session.id
        repository.add_hand(
            db,
            session_id=session_id,
            hand_number=1,
            history_json=json.dumps({"board": ["As"], "winners": [1], "street": "river"}),
            net=-5,
        )
        db.commit()
    finally:
        db.close()

    summaries = TestClient(app).get(f"/games/{session_id}/hands").json()
    assert len(summaries) == 1
    assert summaries[0]["winners"] == [1]
    assert summaries[0]["board"] == ["As"]


# ------------------------------------------------------------------ seed 外发


def test_new_hand_detail_is_versioned_and_seed_free() -> None:
    client = TestClient(app)
    created = client.post(
        "/games", json={"num_players": 2, "target_hands": 5, "seed": 123456789}
    ).json()
    assert "seed" not in _all_keys(created)

    # 真人开局是第一个行动者，直接弃牌即可结束本手并落库。
    finished = client.post(f"/games/{created['session_id']}/actions", json={"action": "fold"})
    assert finished.status_code == 200
    body = finished.json()
    assert "seed" not in _all_keys(body)

    detail = client.get(f"/hands/{body['last_hand_id']}").json()
    assert "seed" not in _all_keys(detail)
    assert detail["history"]["schema_version"] == "hand-history.v1"
    assert detail["history"]["bot_strategy"] == "heuristic@1"

    review = client.get(f"/hands/{body['last_hand_id']}/review").json()
    assert "seed" not in _all_keys(review)
