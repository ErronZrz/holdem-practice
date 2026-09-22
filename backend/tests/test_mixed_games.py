"""新 Bot 与对局接口的回归：默认不变、显式可选、逐人数可完成、身份可追溯。

只做有界集成回归：不跑性能矩阵、不跑对抗对局、不访问真实库。
"""

import pytest
from fastapi.testclient import TestClient

from app.api import games, schemas
from app.main import app
from app.storage import repository
from app.storage.db import get_db, init_db
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MixedLocalStrategy,
    derive_deck_seed,
    derive_root_key,
)
from app.strategy.random_strategy import RandomStrategy


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield


def _stored_strategy(session_id: str) -> str:
    db = next(get_db())
    try:
        session = repository.get_session(db, session_id)
        assert session is not None
        return session.bot_strategy
    finally:
        db.close()


def _legal_move(legal: dict) -> dict:
    if legal["can_check"]:
        return {"action": "check"}
    if legal["can_call"]:
        return {"action": "call"}
    return {"action": "fold"}


def _play_session(client: TestClient, game_id: str, max_steps: int = 20000) -> dict:
    data = client.get(f"/games/{game_id}").json()
    steps = 0
    while not data["session_finished"] and steps < max_steps:
        if data["hand_over"]:
            data = client.post(f"/games/{game_id}/next-hand").json()
        elif data["is_human_turn"]:
            resp = client.post(
                f"/games/{game_id}/actions", json=_legal_move(data["legal_actions"])
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
        else:
            data = client.get(f"/games/{game_id}").json()
        steps += 1
    assert steps < max_steps, "对局步数超限，疑似死锁"
    return data


def _play_one_hand(client: TestClient, game_id: str, data: dict, max_steps: int = 5000) -> dict:
    steps = 0
    while not data["hand_over"] and steps < max_steps:
        if data["is_human_turn"]:
            resp = client.post(
                f"/games/{game_id}/actions", json=_legal_move(data["legal_actions"])
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
        else:
            data = client.get(f"/games/{game_id}").json()
        steps += 1
    assert data["hand_over"], "单手步数超限，疑似死锁"
    return data


# ------------------------------------------------------------------ 默认与可选


def test_schema_default_stays_on_the_old_strategy() -> None:
    assert schemas.CreateGameRequest(num_players=2).bot_strategy == "heuristic@1"


def test_omitting_strategy_still_creates_the_old_bot() -> None:
    client = TestClient(app)
    data = client.post("/games", json={"num_players": 3, "seed": 11}).json()
    assert _stored_strategy(data["session_id"]) == "heuristic@1"
    runtime = games._registry[data["session_id"]]
    assert isinstance(runtime.bot, HeuristicStrategy)
    assert runtime.summary is None


def test_explicit_mixed_strategy_is_selectable() -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 4, "seed": 11, "bot_strategy": MIXED_STRATEGY_IDENTIFIER},
    ).json()
    assert _stored_strategy(data["session_id"]) == MIXED_STRATEGY_IDENTIFIER
    runtime = games._registry[data["session_id"]]
    assert isinstance(runtime.bot, MixedLocalStrategy)
    assert runtime.summary is not None
    assert runtime.summary.active is True
    # 主键与派生种子不外发、不落库。
    assert "seed" not in data
    assert data["players"][1]["hole_cards"] == []


def test_second_mixed_version_is_selectable_and_plays_a_hand() -> None:
    """第二版身份可显式选择、能打完一手，且与首版使用不同的牌堆派生流。"""
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 3, "seed": 11, "bot_strategy": MIXED_STRATEGY_IDENTIFIER_V2},
    ).json()
    session_id = data["session_id"]
    assert _stored_strategy(session_id) == MIXED_STRATEGY_IDENTIFIER_V2
    runtime = games._registry[session_id]
    assert isinstance(runtime.bot, MixedLocalStrategy)
    assert runtime.bot.identifier == MIXED_STRATEGY_IDENTIFIER_V2
    assert runtime.summary is not None
    root = derive_root_key(11)
    assert derive_deck_seed(root, MIXED_STRATEGY_IDENTIFIER_V2) != derive_deck_seed(
        root, MIXED_STRATEGY_IDENTIFIER
    )
    assert _play_one_hand(client, session_id, data)["hand_over"] is True


def test_unversioned_mixed_alias_is_rejected() -> None:
    client = TestClient(app)
    resp = client.post("/games", json={"num_players": 2, "bot_strategy": "mixed-local"})
    assert resp.status_code == 422


@pytest.mark.parametrize("value", ["heuristic", "heuristic@1", "random@1"])
def test_old_strategies_are_unaffected(value: str) -> None:
    client = TestClient(app)
    data = client.post("/games", json={"num_players": 2, "seed": 3, "bot_strategy": value}).json()
    expected = "heuristic@1" if value.startswith("heuristic") else value
    assert _stored_strategy(data["session_id"]) == expected
    runtime = games._registry[data["session_id"]]
    assert runtime.summary is None
    if value.startswith("heuristic"):
        assert isinstance(runtime.bot, HeuristicStrategy)
    else:
        assert isinstance(runtime.bot, RandomStrategy)


# ------------------------------------------------------------------ 完整对局


@pytest.mark.parametrize("players", [2, 3, 4, 5, 6, 7, 8, 9])
def test_mixed_session_completes_at_every_player_count(players: int) -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={
            "num_players": players,
            "target_hands": 2,
            "seed": 1215,
            "bot_strategy": MIXED_STRATEGY_IDENTIFIER,
        },
    ).json()
    final = _play_session(client, data["session_id"])
    assert final["session_finished"] is True
    stats = client.get(f"/games/{data['session_id']}/stats").json()
    assert stats["hands_played"] == 2


def test_mixed_hand_history_records_the_strategy_identity() -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={
            "num_players": 5,
            "target_hands": 1,
            "seed": 20260918,
            "bot_strategy": MIXED_STRATEGY_IDENTIFIER,
        },
    ).json()
    game_id = data["session_id"]
    ended = _play_one_hand(client, game_id, data)
    assert ended["last_hand_id"]
    detail = client.get(f"/hands/{ended['last_hand_id']}").json()
    assert detail["history"]["bot_strategy"] == MIXED_STRATEGY_IDENTIFIER
    assert detail["history"]["schema_version"] == "hand-history.v1"
    review = client.get(f"/hands/{ended['last_hand_id']}/review")
    assert review.status_code == 200
    # 复盘仍使用独立的保守参考，不随新对手切换。
    assert review.json()["reference_strategy"] == "heuristic-conservative"


def test_summary_resets_between_hands() -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 6, "seed": 7, "bot_strategy": MIXED_STRATEGY_IDENTIFIER},
    ).json()
    game_id = data["session_id"]
    runtime = games._registry[game_id]
    ended = _play_one_hand(client, game_id, data)
    assert ended["hand_over"]
    assert runtime.summary is not None
    assert runtime.summary.hand_number == 1
    client.post(f"/games/{game_id}/next-hand")
    assert runtime.summary.hand_number == 2
    assert runtime.summary.consumed_events == 2


def test_illegal_human_action_does_not_touch_the_summary() -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 4, "seed": 7, "bot_strategy": MIXED_STRATEGY_IDENTIFIER},
    ).json()
    game_id = data["session_id"]
    runtime = games._registry[game_id]
    assert runtime.summary is not None
    before = runtime.summary.consumed_events
    resp = client.post(f"/games/{game_id}/actions", json={"action": "check"})
    assert resp.status_code in (200, 400)
    if resp.status_code == 400:
        assert runtime.summary.consumed_events == before


def test_same_seed_replays_the_same_action_line() -> None:
    client = TestClient(app)
    payload = {
        "num_players": 6,
        "seed": 3311,
        "bot_strategy": MIXED_STRATEGY_IDENTIFIER,
    }
    lines = []
    for _ in range(2):
        data = client.post("/games", json=payload).json()
        ended = _play_one_hand(client, data["session_id"], data)
        lines.append(ended["hand_actions"])
    assert lines[0]
    assert lines[0] == lines[1]
    # 显式 seed 只是非保密的重放模式：换 seed 会换出不同的牌堆派生流。
    assert derive_deck_seed(derive_root_key(3311)) != derive_deck_seed(derive_root_key(7926))


def test_mixed_bot_never_leaks_opponent_hole_cards_before_showdown() -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 4, "seed": 5, "bot_strategy": MIXED_STRATEGY_IDENTIFIER},
    ).json()
    game_id = data["session_id"]
    for _ in range(6):
        if data["hand_over"]:
            break
        for player in data["players"]:
            if not player["is_human"] and not data["hand_over"]:
                assert player["cards_revealed"] is False
                assert player["hole_cards"] == []
        if data["is_human_turn"]:
            data = client.post(
                f"/games/{game_id}/actions", json=_legal_move(data["legal_actions"])
            ).json()
        else:
            data = client.get(f"/games/{game_id}").json()
    assert True
