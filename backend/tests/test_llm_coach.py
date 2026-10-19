"""教练解读：思考模式、决策级缓存、信息边界，以及上游失败时复盘仍可用。"""

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.analysis.reference_identity as identity_module
import app.llm.deepseek as deepseek_module
from app.analysis.hand_review import build_review
from app.api.hands import get_coach_provider
from app.llm.coach import PROMPT_SCHEMA_VERSION, build_decision_payload, render_messages
from app.llm.deepseek import DEFAULT_TIMEOUT_SECONDS, DeepSeekProvider, resolve_api_key
from app.llm.types import Completion
from app.main import app
from app.poker.actions import Action, ActionType
from app.poker.engine import PokerEngine
from app.storage import repository
from app.storage.db import get_db, init_db
from app.storage.hand_history import build_hand_history
from app.storage.models import CoachExplanationModel, HandModel, SessionModel

from .helpers import cards

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SESSION_COLUMNS = {
    "id",
    "created_at",
    "num_players",
    "human_seat",
    "small_blind",
    "big_blind",
    "starting_stack",
    "target_hands",
    "hands_played",
    "net_chips",
    "bot_strategy",
    "status",
    "finished_at",
}
_HAND_COLUMNS = {"id", "session_id", "hand_number", "created_at", "net", "history_json"}


class _Response:
    """最小的上游响应替身。"""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class FakeProvider:
    """记录请求并不访问网络的教练替身。"""

    provider_name = "fake"
    model_name = "stub"

    def __init__(self, content: str = "翻前这手牌面对加注，弃牌可以少投入。") -> None:
        self.content = content
        self.calls = 0
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        self.calls += 1
        self.messages.append(messages)
        return Completion(
            content=self.content,
            reasoning="先看牌力和要跟的筹码。",
            prompt_tokens=11,
            completion_tokens=19,
            reasoning_tokens=7,
            total_tokens=30,
        )


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_provider() -> FakeProvider:
    provider = FakeProvider()
    app.dependency_overrides[get_coach_provider] = lambda: provider
    return provider


def _assert_no_solver_labels(text: str) -> None:
    lowered = text.lower()
    for token in ("gto", "nashconv", "exploitab", "最优"):
        assert token not in lowered, token
    assert re.search(r"(?<!非)均衡", text) is None


def _persist(history: dict) -> str:
    generator = get_db()
    db = next(generator)
    try:
        session = repository.create_session(
            db,
            num_players=history["num_players"],
            human_seat=0,
            small_blind=history["small_blind"],
            big_blind=history["big_blind"],
            starting_stack=1000,
            target_hands=1,
            bot_strategy="mixed-local@13",
        )
        hand = repository.add_hand(
            db,
            session_id=session.id,
            hand_number=history["hand_number"],
            history_json=json.dumps(history),
            net=0,
        )
        db.commit()
        return hand.id
    finally:
        generator.close()


def _history_json(hand_id: str) -> str:
    generator = get_db()
    db = next(generator)
    try:
        hand = repository.get_hand(db, hand_id)
        assert hand is not None
        return hand.history_json
    finally:
        generator.close()


def _coach_rows(hand_id: str) -> list[CoachExplanationModel]:
    generator = get_db()
    db = next(generator)
    try:
        return list(
            db.scalars(
                select(CoachExplanationModel).where(CoachExplanationModel.hand_id == hand_id)
            )
        )
    finally:
        generator.close()


def _human_fold_history() -> dict:
    """真人翻前弃牌。对手底牌留在历史里，但没有摊牌。"""
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(
        button=0,
        hole_cards={0: cards("As Kd"), 1: cards("Qh Jc")},
        board=cards("2c 7d 9h Ts 3c"),
    )
    assert engine.current_player.seat == 0
    engine.apply_action(Action(ActionType.FOLD))
    assert engine.hand_over
    history = build_hand_history(engine, hand_number=1, human_seat=0)
    assert "showdown_hands" not in history
    return history


def _no_human_decision_history() -> dict:
    """对手在真人行动前弃牌，真人没有决策点。"""
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(
        button=1,
        hole_cards={0: cards("As Kd"), 1: cards("Qh Jc")},
        board=cards("2c 7d 9h Ts 3c"),
    )
    assert engine.current_player.seat == 1
    engine.apply_action(Action(ActionType.FOLD))
    assert engine.hand_over
    return build_hand_history(engine, hand_number=1, human_seat=0)


def _showdown_with_folded_opponent() -> dict:
    """三人桌里一人中途弃牌，其余两人摊牌。弃牌者的底牌不得进入提示。"""
    engine = PokerEngine(3, 5, 10, 1000)
    engine.start_hand_with(
        button=0,
        hole_cards={
            0: cards("As Kd"),
            1: cards("Qh Jc"),
            2: cards("9s 8s"),
        },
        board=cards("2c 7d Th 4s 3c"),
    )
    script = [
        (0, ActionType.CALL),
        (1, ActionType.FOLD),
        (2, ActionType.CHECK),
        (2, ActionType.CHECK),
        (0, ActionType.CHECK),
        (2, ActionType.CHECK),
        (0, ActionType.CHECK),
        (2, ActionType.CHECK),
        (0, ActionType.CHECK),
    ]
    for seat, action_type in script:
        assert engine.current_player.seat == seat
        engine.apply_action(Action(action_type))
    assert engine.hand_over
    assert 1 not in engine.showdown_hands
    assert 2 in engine.showdown_hands
    return build_hand_history(engine, hand_number=1, human_seat=0)


def _completion_payload(content: str = "翻前这手牌可以弃掉。") -> bytes:
    body = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": "先比较要跟的筹码和牌力。",
                },
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 30,
            "total_tokens": 42,
            "completion_tokens_details": {"reasoning_tokens": 18},
        },
    }
    return json.dumps(body).encode()


# ------------------------------------------------------------------ 请求结构


def test_deepseek_request_keeps_thinking_enabled() -> None:
    seen: dict = {}

    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        seen["body"] = json.loads(request.data.decode())
        seen["timeout"] = timeout
        seen["authorization"] = request.get_header("Authorization")
        return _Response(_completion_payload())

    provider = DeepSeekProvider(api_key="test-key", opener=opener)
    completion = provider.complete([{"role": "user", "content": "点评这一手"}])

    body = seen["body"]
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert body["stream"] is False
    assert "temperature" not in body
    assert "frequency_penalty" not in body
    assert "presence_penalty" not in body
    assert "max_tokens" not in body
    assert seen["timeout"] == DEFAULT_TIMEOUT_SECONDS
    assert seen["timeout"] >= 60
    assert seen["authorization"] == "Bearer test-key"
    assert completion.content == "翻前这手牌可以弃掉。"
    assert completion.reasoning_tokens == 18
    assert completion.prompt_tokens == 12
    assert completion.total_tokens == 42


def test_empty_thinking_budget_is_an_upstream_error() -> None:
    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        body = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": "", "reasoning_content": "思考中"},
                }
            ]
        }
        return _Response(json.dumps(body).encode())

    provider = DeepSeekProvider(api_key="test-key", opener=opener)
    with pytest.raises(Exception, match="长度限制") as caught:
        provider.complete([{"role": "user", "content": "点评"}])
    assert "test-key" not in str(caught.value)


def test_resolve_api_key_prefers_environment_over_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    key_file = tmp_path / "env"
    key_file.write_text('export DEEPSEEK_API_KEY="file-key"\n', encoding="utf-8")
    monkeypatch.setattr(deepseek_module, "KEY_FILE", key_file)
    assert resolve_api_key() == "env-key"


def test_resolve_api_key_reads_export_file(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    key_file = tmp_path / "env"
    key_file.write_text('# local\nexport DEEPSEEK_API_KEY="file-key"\n', encoding="utf-8")
    monkeypatch.setattr(deepseek_module, "KEY_FILE", key_file)
    assert resolve_api_key() == "file-key"


def test_source_does_not_embed_a_key() -> None:
    text = Path(deepseek_module.__file__).read_text(encoding="utf-8")
    assert "sk-" not in text


# ------------------------------------------------------------------ 缓存与信息边界


def test_cache_hit_does_not_call_upstream_again(fake_provider: FakeProvider) -> None:
    hand_id = _persist(_human_fold_history())
    client = TestClient(app)

    first = client.post(f"/hands/{hand_id}/explain")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["decisions"][0]["cached"] is False
    assert body["decisions"][0]["model"] == "stub"
    assert fake_provider.calls == 1

    second = client.post(f"/hands/{hand_id}/explain")
    assert second.status_code == 200
    assert second.json()["decisions"][0]["cached"] is True
    assert second.json()["decisions"][0]["explanation"] == body["decisions"][0]["explanation"]
    assert fake_provider.calls == 1

    rows = _coach_rows(hand_id)
    assert len(rows) == 1
    assert rows[0].prompt_tokens == 11
    assert rows[0].completion_tokens == 19
    assert rows[0].reasoning_tokens == 7
    assert rows[0].total_tokens == 30
    assert rows[0].prompt_schema_version == PROMPT_SCHEMA_VERSION
    assert rows[0].reasoning_summary


@pytest.mark.parametrize("field", ["REFERENCE_VERSION", "EVALUATION_VERSION"])
def test_version_change_busts_the_decision_cache(
    fake_provider: FakeProvider, field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    hand_id = _persist(_human_fold_history())
    client = TestClient(app)
    assert client.post(f"/hands/{hand_id}/explain").status_code == 200
    assert fake_provider.calls == 1
    again = client.post(f"/hands/{hand_id}/explain")
    assert again.json()["decisions"][0]["cached"] is True
    assert fake_provider.calls == 1

    monkeypatch.setattr(identity_module, field, getattr(identity_module, field) + 1)
    refreshed = client.post(f"/hands/{hand_id}/explain")
    assert refreshed.status_code == 200
    assert refreshed.json()["decisions"][0]["cached"] is False
    assert fake_provider.calls == 2


def test_unrevealed_opponent_cards_never_enter_the_request(fake_provider: FakeProvider) -> None:
    history = _showdown_with_folded_opponent()
    assert "Qh" in json.dumps(history)
    assert "Jc" in json.dumps(history)
    hand_id = _persist(history)
    client = TestClient(app)

    response = client.post(f"/hands/{hand_id}/explain")
    assert response.status_code == 200, response.text
    decisions = response.json()["decisions"]
    assert len(decisions) == fake_provider.calls
    assert fake_provider.calls > 1

    request_text = json.dumps(fake_provider.messages, ensure_ascii=False)
    assert "Qh" not in request_text
    assert "Jc" not in request_text
    assert "As" in request_text
    assert "9s" in request_text
    for messages in fake_provider.messages:
        payload = json.loads(messages[1]["content"].split("\n", 1)[1])
        assert "players" not in payload
        assert all(item["seat"] != 1 for item in payload["revealed_hands"])
        assert any(item["seat"] == 2 for item in payload["revealed_hands"])
        _assert_no_solver_labels(messages[0]["content"] + messages[1]["content"])

    cached = client.post(f"/hands/{hand_id}/explain")
    assert cached.status_code == 200
    assert all(item["cached"] for item in cached.json()["decisions"])
    assert fake_provider.calls == len(decisions)


def test_prompt_forbids_solver_wording_without_hiding_the_reference() -> None:
    history = _human_fold_history()
    review = build_review(history)
    messages = render_messages(build_decision_payload(history, review, 0))
    text = messages[0]["content"] + messages[1]["content"]
    _assert_no_solver_labels(text)
    assert "非均衡" in text
    assert "紧手标准" in messages[0]["content"]
    assert PROMPT_SCHEMA_VERSION == 2


def test_solver_claims_are_removed_before_storage(fake_provider: FakeProvider) -> None:
    fake_provider.content = (
        "按 GTO 这是最优均衡，nashconv 与 exploitability 都不是本手的依据。参考仍是非均衡近似。"
    )
    hand_id = _persist(_human_fold_history())
    response = TestClient(app).post(f"/hands/{hand_id}/explain")
    assert response.status_code == 200, response.text
    explanation = response.json()["decisions"][0]["explanation"]
    _assert_no_solver_labels(explanation)
    assert "非均衡" in explanation
    assert _coach_rows(hand_id)[0].explanation == explanation


def test_no_human_decision_skips_upstream_even_without_a_key(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(deepseek_module, "KEY_FILE", tmp_path / "missing.env")

    def boom(*args, **kwargs):
        raise AssertionError("没有决策点时不应访问上游")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    hand_id = _persist(_no_human_decision_history())
    response = TestClient(app).post(f"/hands/{hand_id}/explain")
    assert response.status_code == 200, response.text
    assert response.json() == {"hand_id": hand_id, "decisions": []}
    assert _coach_rows(hand_id) == []


def test_missing_api_key_returns_503_and_review_still_works(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(deepseek_module, "KEY_FILE", tmp_path / "missing.env")

    def boom(*args, **kwargs):
        raise AssertionError("缺少密钥时不应访问上游")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    hand_id = _persist(_human_fold_history())
    stored = _history_json(hand_id)
    client = TestClient(app)
    before = client.get(f"/hands/{hand_id}/review")
    assert before.status_code == 200

    response = client.post(f"/hands/{hand_id}/explain")
    assert response.status_code == 503
    assert "密钥" in response.json()["detail"]
    assert "sk-" not in response.json()["detail"]

    after = client.get(f"/hands/{hand_id}/review")
    assert after.status_code == 200
    assert after.json() == before.json()
    assert _history_json(hand_id) == stored


def test_upstream_failure_returns_503_and_leaves_review_untouched() -> None:
    def opener(request: urllib.request.Request, timeout: float):
        raise urllib.error.URLError("offline")

    app.dependency_overrides[get_coach_provider] = lambda: DeepSeekProvider(
        api_key="test-key",
        opener=opener,
    )
    hand_id = _persist(_human_fold_history())
    stored = _history_json(hand_id)
    client = TestClient(app)
    before = client.get(f"/hands/{hand_id}/review")
    assert before.status_code == 200

    response = client.post(f"/hands/{hand_id}/explain")
    assert response.status_code == 503
    assert "暂时不可用" in response.json()["detail"]
    assert "test-key" not in response.json()["detail"]
    assert client.get(f"/hands/{hand_id}/review").json() == before.json()
    assert _history_json(hand_id) == stored
    assert _coach_rows(hand_id) == []


def test_missing_hand_does_not_call_upstream(fake_provider: FakeProvider) -> None:
    response = TestClient(app).post("/hands/missing-hand/explain")
    assert response.status_code == 404
    assert fake_provider.calls == 0


def test_existing_hand_and_session_columns_stay_put() -> None:
    assert {column.name for column in SessionModel.__table__.columns} == _SESSION_COLUMNS
    assert {column.name for column in HandModel.__table__.columns} == _HAND_COLUMNS
    assert CoachExplanationModel.__tablename__ == "coach_explanations"
    assert "cache_key" in {column.name for column in CoachExplanationModel.__table__.primary_key}


def test_decision_modules_do_not_import_the_coach() -> None:
    root = _REPO_ROOT / "backend" / "app"
    for folder in ("poker", "strategy", "verification"):
        for path in (root / folder).rglob("*.py"):
            assert "app.llm" not in path.read_text(encoding="utf-8")


def test_review_views_request_the_coach_only_from_a_button() -> None:
    api_source = (_REPO_ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "explainHand" in api_source
    assert "/explain" in api_source
    for name in ("GameTable.vue", "HistoryView.vue"):
        source = (_REPO_ROOT / "frontend" / "src" / "components" / name).read_text(
            encoding="utf-8"
        )
        assert "AI 教练解读" in source
        assert "explainHand" in source
        assert "loadCoach" in source
        _assert_no_solver_labels(source)


# ------------------------------------------------------------------ 真实上游冒烟


@pytest.mark.skipif(os.environ.get("HOLDEM_LLM_SMOKE") != "1", reason="需要显式开启真实上游冒烟")
def test_live_deepseek_smoke() -> None:
    captured: dict = {"calls": 0}

    def opener(request: urllib.request.Request, timeout: float):
        captured["calls"] += 1
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        captured["authorization"] = request.get_header("Authorization") or ""
        return urllib.request.urlopen(request, timeout=timeout)

    app.dependency_overrides[get_coach_provider] = lambda: DeepSeekProvider(opener=opener)
    history = _human_fold_history()
    hand_id = _persist(history)
    client = TestClient(app)

    first = client.post(f"/hands/{hand_id}/explain")
    assert first.status_code == 200, first.text
    decision = first.json()["decisions"][0]
    assert decision["cached"] is False
    assert decision["model"] == "deepseek-flash"
    assert decision["provider"] == "deepseek"
    assert decision["explanation"].strip()
    _assert_no_solver_labels(decision["explanation"])

    sent = captured["body"]
    assert sent["model"] == "deepseek-flash"
    assert sent["thinking"] == {"type": "enabled"}
    assert sent["reasoning_effort"] == "high"
    assert sent["stream"] is False
    assert "temperature" not in sent
    assert "frequency_penalty" not in sent
    assert "presence_penalty" not in sent
    assert "max_tokens" not in sent
    assert captured["timeout"] >= 60
    assert captured["authorization"].startswith("Bearer ")
    assert len(captured["authorization"]) > len("Bearer ")
    request_text = json.dumps(sent["messages"], ensure_ascii=False)
    assert "Qh" not in request_text
    assert "Jc" not in request_text
    assert "As" in request_text

    row = _coach_rows(hand_id)[0]
    assert row.reasoning_tokens > 0 or row.reasoning_summary
    print(
        "smoke explanation:",
        decision["explanation"][:300],
        "tokens:",
        row.prompt_tokens,
        row.completion_tokens,
        row.reasoning_tokens,
    )

    second = client.post(f"/hands/{hand_id}/explain")
    assert second.status_code == 200, second.text
    assert second.json()["decisions"][0]["cached"] is True
    assert captured["calls"] == 1
    assert client.get(f"/hands/{hand_id}/review").status_code == 200
