"""5 人桌接口测试：多人位置轮转 / side pot 守恒 / 多 Bot 逐帧推进。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.db import init_db

from .test_games_api import _play_session


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield


def test_five_player_positions() -> None:
    """首手庄位 = 0（真人），小盲 1、大盲 2，preflop 首个行动者 = 大盲左侧。"""
    client = TestClient(app)
    data = client.post(
        "/games", json={"num_players": 5, "target_hands": 5, "seed": 1}
    ).json()
    assert len(data["players"]) == 5
    assert data["button"] == 0
    by_seat = {p["seat"]: p for p in data["players"]}
    assert by_seat[0]["is_button"] is True
    assert by_seat[1]["is_small_blind"] is True
    assert by_seat[2]["is_big_blind"] is True
    # N>=3 时 preflop 首个行动者 = 大盲左侧（seat 3），开局即由 Bot 先行动。
    assert data["current_seat"] == 3
    assert data["is_human_turn"] is False


def test_five_player_session_completes() -> None:
    """5 人桌连续打满 3 手，无非法动作、无死锁，对局正常结束。"""
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 5, "target_hands": 3, "seed": 5, "bot_strategy": "heuristic"},
    ).json()
    final = _play_session(client, data["session_id"])
    assert final["session_finished"] is True

    stats = client.get(f"/games/{data['session_id']}/stats").json()
    assert stats["hands_played"] == 3
    assert stats["num_players"] == 5


def test_five_player_side_pot_conservation() -> None:
    """多人桌每手结算后净盈亏归零（覆盖 side pot 与未跟注退还）。"""
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 5, "target_hands": 2, "seed": 9, "bot_strategy": "random"},
    ).json()
    final = _play_session(client, data["session_id"])
    assert final["session_finished"] is True

    hands = client.get(f"/games/{data['session_id']}/hands").json()
    assert len(hands) == 2
    for h in hands:
        detail = client.get(f"/hands/{h['id']}").json()
        net = detail["history"]["net"]
        assert sum(int(v) for v in net.values()) == 0, "单手净盈亏未归零（含边池）"
