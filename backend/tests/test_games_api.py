"""对局接口测试：创建/获取/动作/下一手/历史/统计，覆盖 HU 连续打牌。"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage.db import init_db


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    # 关闭 Bot 思考延迟，避免测试被 sleep 拖慢。
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield


def _pick_legal(legal: dict) -> dict:
    """在合法集合内选择一个确定性动作，保证始终合法。"""
    if legal["can_check"]:
        return {"action": "check"}
    if legal["can_call"]:
        return {"action": "call"}
    return {"action": "fold"}


def _play_session(client: TestClient, game_id: str, max_steps: int = 20000) -> dict:
    """从当前状态一直打到对局结束，返回最终 GameView。"""
    data = client.get(f"/games/{game_id}").json()
    steps = 0
    while not data["session_finished"] and steps < max_steps:
        if data["hand_over"]:
            data = client.post(f"/games/{game_id}/next-hand").json()
        elif data["is_human_turn"]:
            resp = client.post(
                f"/games/{game_id}/actions", json=_pick_legal(data["legal_actions"])
            )
            assert resp.status_code == 200, resp.text
            data = resp.json()
        else:
            # 轮到 Bot：轮询 GET 逐个推进（测试里 BOT_DELAY 已置 0）。
            data = client.get(f"/games/{game_id}").json()
        steps += 1
    assert steps < max_steps, "对局步数超限，疑似死锁"
    return data


def test_create_and_get_game() -> None:
    client = TestClient(app)
    resp = client.post(
        "/games",
        json={"num_players": 2, "target_hands": 10, "seed": 42, "bot_strategy": "heuristic"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["hand_number"] == 1
    assert data["hand_over"] is False
    assert data["human_seat"] == 0
    assert len(data["players"]) == 2
    # 第一手首局庄位为 0（真人 = 小盲），必为真人先行动。
    assert data["is_human_turn"] is True
    assert data["legal_actions"]["can_raise"] is True
    assert data["legal_actions"]["min_raise_to"] == 20

    got = client.get(f"/games/{data['session_id']}")
    assert got.status_code == 200
    assert got.json()["session_id"] == data["session_id"]


def test_bot_hole_cards_masked_until_showdown() -> None:
    client = TestClient(app)
    data = client.post("/games", json={"num_players": 2, "target_hands": 5, "seed": 1}).json()
    human = next(p for p in data["players"] if p["is_human"])
    bot = next(p for p in data["players"] if not p["is_human"])
    assert human["cards_revealed"] is True and human["hole_cards"]
    assert bot["cards_revealed"] is False and bot["hole_cards"] == []


def test_action_amount_validation() -> None:
    client = TestClient(app)
    game_id = client.post(
        "/games", json={"num_players": 2, "target_hands": 10, "seed": 42}
    ).json()["session_id"]

    # bet 未提供金额 -> 400
    assert client.post(f"/games/{game_id}/actions", json={"action": "bet"}).status_code == 400
    # raise 金额低于最小加注 -> 400
    assert (
        client.post(f"/games/{game_id}/actions", json={"action": "raise", "amount": 5}).status_code
        == 400
    )
    # 合法加注 -> 200
    assert (
        client.post(f"/games/{game_id}/actions", json={"action": "raise", "amount": 20}).status_code
        == 200
    )


def test_fold_ends_hand_immediately() -> None:
    client = TestClient(app)
    game_id = client.post(
        "/games", json={"num_players": 2, "target_hands": 10, "seed": 42}
    ).json()["session_id"]
    resp = client.post(f"/games/{game_id}/actions", json={"action": "fold"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["hand_over"] is True
    assert data["hands_played"] == 1
    assert data["winners"] == [1]  # 真人弃牌，Bot 获胜
    assert data["last_hand_id"]
    assert client.get(f"/hands/{data['last_hand_id']}/review").status_code == 200


def test_full_hu_session_and_persistence() -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 2, "target_hands": 5, "seed": 7, "bot_strategy": "heuristic"},
    ).json()
    game_id = data["session_id"]

    final = _play_session(client, game_id)
    assert final["session_finished"] is True
    assert final["hand_over"] is True

    stats = client.get(f"/games/{game_id}/stats").json()
    assert stats["hands_played"] == 5
    assert stats["status"] == "finished"
    assert stats["wins"] + stats["losses"] + stats["ties"] == 5

    hands = client.get(f"/games/{game_id}/hands").json()
    assert len(hands) == 5
    # 手牌历史详情可读，且包含动作序列与摊牌信息。
    detail = client.get(f"/hands/{hands[0]['id']}").json()
    assert detail["history"]["hand_number"] == 1
    assert "actions" in detail["history"]
    assert "net" in detail["history"]


def test_random_bot_session_completes() -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 2, "target_hands": 3, "seed": 11, "bot_strategy": "random"},
    ).json()
    final = _play_session(client, data["session_id"])
    assert final["session_finished"] is True


def test_errors() -> None:
    client = TestClient(app)
    assert client.get("/games/unknown").status_code == 404
    assert client.post("/games/unknown/actions", json={"action": "call"}).status_code == 404
    resp = client.post("/games", json={"num_players": 2, "small_blind": 20, "big_blind": 10})
    assert resp.status_code == 400


def test_showdown_reveals_hands_and_pots() -> None:
    """摊牌时返回各玩家最佳 5 张牌与边池归属，且边池分配守恒。"""
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 2, "target_hands": 30, "seed": 123, "bot_strategy": "random"},
    ).json()
    game_id = data["session_id"]
    found = False
    steps = 0
    while not data["session_finished"] and steps < 20000:
        if data["hand_over"]:
            if data["street"] == "showdown":
                found = True
                assert data["showdown_hands"] is not None
                assert data["pot_results"] is not None
                for p in data["players"]:
                    if not p["folded"]:
                        sh = data["showdown_hands"][str(p["seat"])]
                        assert len(sh["cards"]) == 5
                        assert sh["category"]
                for pr in data["pot_results"]:
                    assert sum(pr["shares"].values()) == pr["amount"]
                break
            data = client.post(f"/games/{game_id}/next-hand").json()
        elif data["is_human_turn"]:
            la = data["legal_actions"]
            act = {"action": "check"} if la["can_check"] else {"action": "call"}
            data = client.post(f"/games/{game_id}/actions", json=act).json()
        else:
            data = client.get(f"/games/{game_id}").json()
        steps += 1
    assert found, "未出现摊牌"


def test_hand_review_endpoint() -> None:
    client = TestClient(app)
    data = client.post(
        "/games",
        json={"num_players": 2, "target_hands": 3, "seed": 7, "bot_strategy": "heuristic"},
    ).json()
    _play_session(client, data["session_id"])

    hands = client.get(f"/games/{data['session_id']}/hands").json()
    assert hands
    review = client.get(f"/hands/{hands[0]['id']}/review")
    assert review.status_code == 200
    body = review.json()
    assert body["hand_id"] == hands[0]["id"]
    assert body["human_seat"] == 0
    assert body["reference_strategy"] == "heuristic-conservative"
    assert body["decisions"], "HU 对局中真人应至少有一个决策点"
    for d in body["decisions"]:
        assert d["action"]["action"] in ("fold", "check", "call", "bet", "raise")
        assert d["bot_action"]["action"] in ("fold", "check", "call", "bet", "raise")
    assert client.get("/hands/unknown/review").status_code == 404
