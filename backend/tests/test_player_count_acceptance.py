"""2–9 人产品范围与旧 10 人对局只读兼容的回归测试。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import repository
from app.storage.db import get_db, init_db

from .test_games_api import _play_session

_SUPPORTED_COUNTS = [2, 3, 4, 5, 6, 7, 8, 9]


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    # 关闭 Bot 思考延迟，避免测试被 sleep 拖慢。
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield


def _blind_seats(button: int, num_players: int) -> tuple[int, int]:
    """按与接口/引擎相同的口径推算出小盲与大盲座位。"""
    if num_players == 2:
        return button, (button + 1) % 2
    return (button + 1) % num_players, (button + 2) % num_players


def _insert_session(num_players: int) -> str:
    """直接落库一条对局记录，用于模拟收紧上限之前产生（或由窗口外客户端写入）的旧数据。"""
    generator = get_db()
    db = next(generator)
    try:
        session = repository.create_session(
            db,
            num_players=num_players,
            human_seat=0,
            small_blind=5,
            big_blind=10,
            starting_stack=1000,
            target_hands=None,
            bot_strategy="heuristic@1",
        )
        db.commit()
        return session.id
    finally:
        generator.close()


@pytest.mark.parametrize("num_players", _SUPPORTED_COUNTS)
def test_create_game_accepts_every_supported_player_count(num_players: int) -> None:
    """2–9 每个人数都能建桌，座位、盲注标记与首个行动者口径一致。"""
    client = TestClient(app)
    resp = client.post("/games", json={"num_players": num_players, "seed": 1})

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert len(data["players"]) == num_players
    assert [p["seat"] for p in data["players"]] == list(range(num_players))

    by_seat = {p["seat"]: p for p in data["players"]}
    small_blind, big_blind = _blind_seats(data["button"], num_players)
    assert by_seat[small_blind]["is_small_blind"] is True
    assert by_seat[big_blind]["is_big_blind"] is True
    assert sum(p["is_button"] for p in data["players"]) == 1
    assert sum(p["is_small_blind"] for p in data["players"]) == 1
    assert sum(p["is_big_blind"] for p in data["players"]) == 1

    # 首手庄位落在真人（0 号位）；单挑由庄位先行动，其余人数由大盲左侧先行动。
    first_actor = 0 if num_players == 2 else 3 % num_players
    assert data["current_seat"] == first_actor
    assert data["is_human_turn"] is (first_actor == data["human_seat"])


@pytest.mark.parametrize("num_players", [0, 1, 10, 11, -1])
def test_create_game_rejects_player_counts_outside_the_product_range(num_players: int) -> None:
    """越界人数直接失败，且不留下任何对局记录（不截断、不回落默认值）。"""
    client = TestClient(app)

    resp = client.post("/games", json={"num_players": num_players, "seed": 1})

    assert resp.status_code == 422, resp.text
    assert client.get("/games").json() == []


def test_default_player_count_stays_two() -> None:
    """省略人数时仍默认 2 人桌。"""
    client = TestClient(app)

    data = client.post("/games", json={"seed": 1}).json()

    assert len(data["players"]) == 2


@pytest.mark.parametrize("num_players", [6, 7, 9])
def test_large_table_can_play_a_hand(num_players: int) -> None:
    """重点人数各完整打一手：无非法动作、无死锁，单手净额归零。"""
    client = TestClient(app)
    data = client.post(
        "/games",
        json={
            "num_players": num_players,
            "target_hands": 1,
            "seed": 7,
            "bot_strategy": "heuristic",
        },
    ).json()

    final = _play_session(client, data["session_id"])

    assert final["session_finished"] is True
    hands = client.get(f"/games/{data['session_id']}/hands").json()
    assert len(hands) == 1
    detail = client.get(f"/hands/{hands[0]['id']}").json()
    net = detail["history"]["net"]
    assert sum(int(value) for value in net.values()) == 0


def test_legacy_ten_player_session_stays_readable() -> None:
    """旧 10 人对局仍按库中原值只读展示：不过滤、不改写、不迁移。"""
    client = TestClient(app)
    legacy_id = _insert_session(10)

    listed = {item["id"]: item for item in client.get("/games").json()}
    assert listed[legacy_id]["num_players"] == 10

    stats = client.get(f"/games/{legacy_id}/stats").json()
    assert stats["num_players"] == 10
    assert stats["hands_played"] == 0


def test_new_game_creation_rejects_ten_players_but_keeps_legacy_rows() -> None:
    """收紧只作用于新建：10 人建桌失败，既有 10 人记录仍在列表中。"""
    client = TestClient(app)
    legacy_id = _insert_session(10)

    resp = client.post("/games", json={"num_players": 10, "seed": 1})

    assert resp.status_code == 422, resp.text
    assert {item["id"] for item in client.get("/games").json()} == {legacy_id}
