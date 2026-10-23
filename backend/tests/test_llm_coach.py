"""教练解读：思考模式、决策级缓存、信息边界，以及上游失败时复盘仍可用。"""

import json
import os
import re
import sqlite3
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
from app.llm.coach import (
    PROMPT_SCHEMA_VERSION,
    _one_card_outs,
    build_decision_payload,
    input_digest,
    render_followup_messages,
    render_messages,
)
from app.llm.deepseek import DEFAULT_TIMEOUT_SECONDS, DeepSeekProvider, resolve_api_key
from app.llm.types import CoachUnavailableError, Completion
from app.main import app
from app.poker.actions import Action, ActionType
from app.poker.engine import PokerEngine
from app.storage import repository
from app.storage.db import get_db, init_db
from app.storage.hand_history import build_hand_history
from app.storage.models import (
    CoachExplanationModel,
    CoachMessageModel,
    HandModel,
    SessionModel,
)

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

    def __init__(self, content: str | None = None) -> None:
        self.content = content
        self.calls = 0
        self.messages: list[list[dict[str, str]]] = []
        self.json_modes: list[bool] = []
        self.plain_error: Exception | None = None

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
    ) -> Completion:
        self.calls += 1
        self.messages.append(messages)
        self.json_modes.append(json_mode)
        if not json_mode and self.plain_error is not None:
            raise self.plain_error
        if self.content is not None:
            content = self.content
        elif json_mode:
            content = _batch_reply(messages)
        else:
            content = "结合公开行动线和已有解读，这里不必再追加投入。"
        return Completion(
            content=content,
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


def _message_rows(hand_id: str) -> list[CoachMessageModel]:
    generator = get_db()
    db = next(generator)
    try:
        return list(
            db.scalars(
                select(CoachMessageModel)
                .where(CoachMessageModel.hand_id == hand_id)
                .order_by(CoachMessageModel.id)
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


def _request_body(messages: list[dict[str, str]]) -> dict:
    return json.loads(messages[1]["content"].split("\n", 1)[1])


def _batch_reply(messages: list[dict[str, str]]) -> str:
    """按请求里的决策序号回一份结构化点评，便于断言只打了一次上游。"""
    body = _request_body(messages)
    return json.dumps(
        {
            "explanations": [
                {
                    "action_index": item["action_index"],
                    "recommended_action": "fold",
                    "explanation": (
                        f"决策{item['action_index']}结合公开行动线看，这一手不必追加被动投入。"
                    ),
                }
                for item in body["decisions"]
            ]
        },
        ensure_ascii=False,
    )


def _seed_explanation(hand_id: str, history: dict, index: int, explanation: str) -> None:
    review = build_review(history)
    payload = build_decision_payload(history, review, index)
    cache_key = identity_module.decision_cache_key(
        hand_id=hand_id,
        action_index=index,
        seat=int(review["human_seat"]),
        input_digest=input_digest(payload),
        prompt_schema_version=PROMPT_SCHEMA_VERSION,
        provider=FakeProvider.provider_name,
        model=FakeProvider.model_name,
    )
    generator = get_db()
    db = next(generator)
    try:
        repository.add_coach_explanation(
            db,
            cache_key=cache_key,
            hand_id=hand_id,
            action_index=index,
            seat=int(review["human_seat"]),
            provider=FakeProvider.provider_name,
            model=FakeProvider.model_name,
            prompt_schema_version=PROMPT_SCHEMA_VERSION,
            explanation=explanation,
            recommended_action=None,
            reasoning_summary=None,
            prompt_tokens=0,
            completion_tokens=0,
            reasoning_tokens=0,
            total_tokens=0,
        )
        db.commit()
    finally:
        generator.close()


def _heads_up_checked_down() -> dict:
    """两人打到摊牌，真人有翻前到河牌的多个决策点。"""
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(
        button=0,
        hole_cards={0: cards("As Kd"), 1: cards("Qh Jc")},
        board=cards("2c 7d 9h Ts 3c"),
    )
    script = [
        (0, ActionType.CALL),
        (1, ActionType.CHECK),
        (1, ActionType.CHECK),
        (0, ActionType.CHECK),
        (1, ActionType.CHECK),
        (0, ActionType.CHECK),
        (1, ActionType.CHECK),
        (0, ActionType.CHECK),
    ]
    for seat, action_type in script:
        assert engine.current_player.seat == seat
        engine.apply_action(Action(action_type))
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
    assert body["response_format"] == {"type": "json_object"}
    assert "temperature" not in body
    assert "frequency_penalty" not in body
    assert "presence_penalty" not in body
    assert "max_tokens" not in body
    assert seen["timeout"] == DEFAULT_TIMEOUT_SECONDS
    assert seen["timeout"] >= 60
    assert seen["authorization"] == "Bearer test-key"
    assert completion.content == "翻前这手牌可以弃掉。"


def test_followup_request_keeps_thinking_without_json_mode() -> None:
    seen: dict = {}

    def opener(request: urllib.request.Request, timeout: float) -> _Response:
        seen["body"] = json.loads(request.data.decode())
        return _Response(_completion_payload("这里不必再跟。"))

    provider = DeepSeekProvider(api_key="test-key", opener=opener)
    completion = provider.complete(
        [{"role": "user", "content": "为什么弃牌？"}],
        json_mode=False,
    )

    body = seen["body"]
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "enabled"}
    assert body["reasoning_effort"] == "high"
    assert body["stream"] is False
    assert "response_format" not in body
    assert completion.content == "这里不必再跟。"
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
    assert len(decisions) > 1
    assert fake_provider.calls == 1

    request_text = json.dumps(fake_provider.messages, ensure_ascii=False)
    assert "Qh" not in request_text
    assert "Jc" not in request_text
    assert "As" in request_text
    assert "9s" in request_text
    messages = fake_provider.messages[0]
    payload = _request_body(messages)
    assert "players" not in payload
    assert "players" not in payload["hand"]
    revealed = payload["hand"]["revealed_hands"]
    assert all(item["seat"] != 1 for item in revealed)
    assert any(item["seat"] == 2 for item in revealed)
    assert [item["action_index"] for item in payload["decisions"]] == [
        item["action_index"] for item in decisions
    ]
    assert all("revealed_hands" not in item for item in payload["decisions"])
    _assert_no_solver_labels(messages[0]["content"] + messages[1]["content"])

    cached = client.post(f"/hands/{hand_id}/explain")
    assert cached.status_code == 200
    assert all(item["cached"] for item in cached.json()["decisions"])
    assert fake_provider.calls == 1


def test_prompt_forbids_solver_wording_without_hiding_the_reference() -> None:
    history = _human_fold_history()
    review = build_review(history)
    messages = render_messages([build_decision_payload(history, review, 0)])
    text = messages[0]["content"] + messages[1]["content"]
    _assert_no_solver_labels(text)
    assert "非均衡" in text
    system = messages[0]["content"]
    assert "紧手标准" in system
    assert "mixed-tight-normal" in system
    assert "公开行动线加权" in system
    assert "逐层摊牌份额" in system
    assert "随机两张牌" in system
    assert "求解器范围" in system
    assert "call_ev" in system
    assert "不含加注的弃牌权益" in system
    assert "call_ev < 0" in system
    assert "one_card_outs" in system
    assert "不要把这手写成听牌" in system
    assert "recommended_action" in system
    assert "本身不构成错误" in system
    assert PROMPT_SCHEMA_VERSION == 5
    body = _request_body(messages)
    assert "As" in body["hand"]["hero_hole_cards"]
    assert body["hand"]["revealed_hands"] == []
    decision = body["decisions"][0]
    assert decision["action_index"] == 0
    assert "hero_hole_cards" not in decision
    assert "revealed_hands" not in decision
    for field in ("equity", "pot_odds", "call_ev", "one_card_outs"):
        assert field in decision
    assert decision["one_card_outs"] == 0


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


def test_multiple_decisions_share_one_upstream_call(fake_provider: FakeProvider) -> None:
    history = _heads_up_checked_down()
    hand_id = _persist(history)
    client = TestClient(app)

    first = client.post(f"/hands/{hand_id}/explain")
    assert first.status_code == 200, first.text
    decisions = first.json()["decisions"]
    assert len(decisions) > 1
    assert {item["street"] for item in decisions} >= {"preflop", "flop", "turn", "river"}
    assert fake_provider.calls == 1
    assert all(item["cached"] is False for item in decisions)
    for item in decisions:
        assert item["explanation"] == (
            f"决策{item['action_index']}结合公开行动线看，这一手不必追加被动投入。"
        )
        _assert_no_solver_labels(item["explanation"])

    sent = _request_body(fake_provider.messages[0])
    assert [item["action_index"] for item in sent["decisions"]] == [
        item["action_index"] for item in decisions
    ]
    assert sent["hand"]["public_actions"]
    assert "As" in sent["hand"]["hero_hole_cards"]

    rows = _coach_rows(hand_id)
    assert len(rows) == len(decisions)
    assert len({row.cache_key for row in rows}) == len(rows)
    assert {row.action_index for row in rows} == {item["action_index"] for item in decisions}
    assert all(row.hand_id == hand_id and row.cache_key != hand_id for row in rows)
    assert all(row.cache_key.split("|")[2] == str(row.action_index) for row in rows)
    assert all(row.prompt_schema_version == PROMPT_SCHEMA_VERSION for row in rows)
    assert all(row.recommended_action == "fold" for row in rows)
    assert all(item["recommended_action"] == "fold" for item in decisions)
    assert all(row.prompt_tokens == 11 and row.total_tokens == 30 for row in rows)

    second = client.post(f"/hands/{hand_id}/explain")
    assert second.status_code == 200, second.text
    again = second.json()["decisions"]
    assert [item["explanation"] for item in again] == [item["explanation"] for item in decisions]
    assert all(item["cached"] is True for item in again)
    assert fake_provider.calls == 1


def test_partial_cache_requests_only_the_misses(fake_provider: FakeProvider) -> None:
    history = _heads_up_checked_down()
    hand_id = _persist(history)
    seeded = "翻前这一手已有解读，不必再问。"
    _seed_explanation(hand_id, history, 0, seeded)
    client = TestClient(app)

    first = client.post(f"/hands/{hand_id}/explain")
    assert first.status_code == 200, first.text
    decisions = first.json()["decisions"]
    assert len(decisions) > 1
    assert fake_provider.calls == 1
    assert decisions[0]["cached"] is True
    assert decisions[0]["explanation"] == seeded
    assert all(item["cached"] is False for item in decisions[1:])
    sent = _request_body(fake_provider.messages[0])
    sent_indexes = [item["action_index"] for item in sent["decisions"]]
    assert sent_indexes == [item["action_index"] for item in decisions[1:]]
    assert 0 not in sent_indexes

    second = client.post(f"/hands/{hand_id}/explain")
    assert second.status_code == 200, second.text
    assert all(item["cached"] is True for item in second.json()["decisions"])
    assert second.json()["decisions"][0]["explanation"] == seeded
    assert fake_provider.calls == 1


def test_fenced_json_is_split_and_sanitized_per_decision(fake_provider: FakeProvider) -> None:
    history = _heads_up_checked_down()
    review = build_review(history)
    indexes = list(range(len(review["decisions"])))
    rows = []
    for index in indexes:
        text = "按 GTO 这是最优均衡。" if index == 0 else f"决策{index}可以少投入。"
        rows.append(
            {"action_index": index, "recommended_action": "check", "explanation": text}
        )
    fake_provider.content = "```json\n" + json.dumps(
        {"explanations": rows}, ensure_ascii=False
    ) + "\n```"
    hand_id = _persist(history)

    response = TestClient(app).post(f"/hands/{hand_id}/explain")
    assert response.status_code == 200, response.text
    decisions = response.json()["decisions"]
    assert fake_provider.calls == 1
    assert len(decisions) == len(indexes)
    _assert_no_solver_labels(decisions[0]["explanation"])
    assert "参考" in decisions[0]["explanation"]
    assert "非均衡" not in decisions[0]["explanation"]
    for item in decisions[1:]:
        assert item["explanation"] == f"决策{item['action_index']}可以少投入。"
    stored = _coach_rows(hand_id)
    assert len(stored) == len(indexes)
    by_index = {row.action_index: row.explanation for row in stored}
    assert by_index[0] == decisions[0]["explanation"]
    assert "gto" not in by_index[0].lower()
    assert all(row.recommended_action == "check" for row in stored)


def test_blank_or_unstructured_batch_returns_503_and_keeps_review(
    fake_provider: FakeProvider,
) -> None:
    history = _heads_up_checked_down()
    hand_id = _persist(history)
    seeded = "翻前这一手已有解读，不必再问。"
    _seed_explanation(hand_id, history, 0, seeded)
    fake_provider.content = "先随便说两句，没有按决策序号分开。"
    client = TestClient(app)
    before = client.get(f"/hands/{hand_id}/review")
    assert before.status_code == 200

    response = client.post(f"/hands/{hand_id}/explain")
    assert response.status_code == 503
    assert "暂时不可用" in response.json()["detail"]
    assert fake_provider.calls == 1
    assert client.get(f"/hands/{hand_id}/review").json() == before.json()
    rows = _coach_rows(hand_id)
    assert len(rows) == 1
    assert rows[0].action_index == 0
    assert rows[0].explanation == seeded

    pending = list(range(1, len(before.json()["decisions"])))
    fake_provider.content = json.dumps(
        {
            "explanations": [
                {
                    "action_index": index,
                    "recommended_action": "fold",
                    "explanation": "   " if index == pending[-1] else f"决策{index}可以少投入。",
                }
                for index in pending
            ]
        },
        ensure_ascii=False,
    )
    blank = client.post(f"/hands/{hand_id}/explain")
    assert blank.status_code == 503
    assert fake_provider.calls == 2
    assert [row.action_index for row in _coach_rows(hand_id)] == [0]
    assert client.get(f"/hands/{hand_id}/review").json() == before.json()


def test_single_decision_accepts_plain_text_and_bare_json(fake_provider: FakeProvider) -> None:
    fake_provider.content = "翻前面对加注，弃牌可以少投入。"
    client = TestClient(app)
    plain_id = _persist(_human_fold_history())
    plain = client.post(f"/hands/{plain_id}/explain")
    assert plain.status_code == 200, plain.text
    assert plain.json()["decisions"][0]["explanation"] == "翻前面对加注，弃牌可以少投入。"
    assert plain.json()["decisions"][0]["recommended_action"] is None
    assert _coach_rows(plain_id)[0].recommended_action is None

    fake_provider.content = json.dumps(
        {"action_index": 0, "explanation": "这手翻前弃牌更稳妥。"},
        ensure_ascii=False,
    )
    bare_id = _persist(_human_fold_history())
    bare = client.post(f"/hands/{bare_id}/explain")
    assert bare.status_code == 200, bare.text
    assert bare.json()["decisions"][0]["explanation"] == "这手翻前弃牌更稳妥。"
    assert bare.json()["decisions"][0]["recommended_action"] is None
    assert _coach_rows(bare_id)[0].recommended_action is None
    assert fake_provider.calls == 2


def test_batch_rejects_missing_illegal_or_mismatched_actions(fake_provider: FakeProvider) -> None:
    history = _heads_up_checked_down()
    hand_id = _persist(history)
    review = build_review(history)
    indexes = list(range(len(review["decisions"])))
    client = TestClient(app)

    fake_provider.content = json.dumps(
        {
            "explanations": [
                {"action_index": index, "explanation": f"决策{index}可以少投入。"}
                for index in indexes
            ]
        },
        ensure_ascii=False,
    )
    missing = client.post(f"/hands/{hand_id}/explain")
    assert missing.status_code == 503
    assert _coach_rows(hand_id) == []

    fake_provider.content = json.dumps(
        {
            "explanations": [
                {
                    "action_index": index,
                    "recommended_action": "all-in",
                    "explanation": f"决策{index}可以少投入。",
                }
                for index in indexes
            ]
        },
        ensure_ascii=False,
    )
    illegal = client.post(f"/hands/{hand_id}/explain")
    assert illegal.status_code == 503
    assert _coach_rows(hand_id) == []

    fake_provider.content = json.dumps(
        {
            "explanations": [
                {
                    "action_index": index + 1,
                    "recommended_action": "fold",
                    "explanation": f"决策{index}可以少投入。",
                }
                for index in indexes
            ]
        },
        ensure_ascii=False,
    )
    mismatched = client.post(f"/hands/{hand_id}/explain")
    assert mismatched.status_code == 503
    assert _coach_rows(hand_id) == []
    assert client.get(f"/hands/{hand_id}/review").status_code == 200


def test_chinese_actions_are_stored_as_enums(fake_provider: FakeProvider) -> None:
    history = _heads_up_checked_down()
    review = build_review(history)
    indexes = list(range(len(review["decisions"])))
    words = ["弃牌", "过牌", "跟注", "下注", "加注", "再加注"]
    expected = ["fold", "check", "call", "bet", "raise", "raise"]
    fake_provider.content = json.dumps(
        {
            "explanations": [
                {
                    "action_index": index,
                    "recommended_action": words[index % len(words)],
                    "explanation": f"决策{index}可以少投入。",
                }
                for index in indexes
            ]
        },
        ensure_ascii=False,
    )
    hand_id = _persist(history)
    response = TestClient(app).post(f"/hands/{hand_id}/explain")
    assert response.status_code == 200, response.text
    stored = {row.action_index: row.recommended_action for row in _coach_rows(hand_id)}
    assert stored == {index: expected[index % len(expected)] for index in indexes}


def test_one_card_outs_count_only_straight_and_flush_completions() -> None:
    # 翻前和河牌固定为 0，避免牌张不够或已经发完时去评估。
    assert _one_card_outs(["As", "Kd"], []) == 0
    assert _one_card_outs(["As", "Kd"], ["2c", "7d", "9h", "Ts", "3c"]) == 0
    # 后门花完不成，听牌补牌是 0。
    assert _one_card_outs(["Kc", "Jh"], ["Kh", "Qh", "5c"]) == 0
    # 四张红桃再加顺子补牌。红桃十已算在同花里，另外三张十只补顺子。
    assert _one_card_outs(["Ah", "Kh"], ["Qh", "Jh", "2c"]) == 12
    # 两对升葫芦、三条升葫芦都不算听牌补牌。
    assert _one_card_outs(["Ah", "Kd"], ["As", "Kc", "2d"]) == 0
    assert _one_card_outs(["Ah", "Ad"], ["Ac", "7d", "2c"]) == 0
    # 已经成顺时不再把更高的牌记成补牌。
    assert _one_card_outs(["9h", "8c"], ["7d", "6s", "5c"]) == 0
    # 开放式顺子听牌是八张。
    assert _one_card_outs(["9h", "8d"], ["7c", "6s", "2d"]) == 8


def test_old_coach_table_gains_recommended_action(tmp_path) -> None:
    fresh = tmp_path / "test.db"
    with sqlite3.connect(fresh) as raw:
        columns = [row[1] for row in raw.execute("PRAGMA table_info(coach_explanations)")]
    assert "recommended_action" in columns

    legacy = tmp_path / "legacy.db"
    with sqlite3.connect(legacy) as raw:
        raw.execute(
            """
            CREATE TABLE coach_explanations (
                cache_key VARCHAR(512) PRIMARY KEY,
                hand_id VARCHAR(32) NOT NULL,
                action_index INTEGER NOT NULL,
                seat INTEGER NOT NULL,
                provider VARCHAR(32) NOT NULL,
                model VARCHAR(64) NOT NULL,
                prompt_schema_version INTEGER NOT NULL,
                explanation TEXT NOT NULL,
                reasoning_summary TEXT,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                reasoning_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME
            )
            """
        )
        raw.execute(
            "INSERT INTO coach_explanations "
            "(cache_key, hand_id, action_index, seat, provider, model, "
            "prompt_schema_version, explanation) "
            "VALUES ('k', 'h', 0, 0, 'fake', 'stub', 3, '旧解读')"
        )
    init_db(str(legacy))
    init_db(str(legacy))
    with sqlite3.connect(legacy) as raw:
        columns = [row[1] for row in raw.execute("PRAGMA table_info(coach_explanations)")]
        saved = raw.execute(
            "SELECT recommended_action, explanation FROM coach_explanations"
        ).fetchone()
    assert columns.count("recommended_action") == 1
    assert saved == (None, "旧解读")
    with sqlite3.connect(legacy) as raw:
        tables = {
            row[0]
            for row in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "coach_messages" in tables


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
    assert CoachMessageModel.__tablename__ == "coach_messages"
    message_columns = {column.name for column in CoachMessageModel.__table__.columns}
    assert {
        "cache_key",
        "hand_id",
        "action_index",
        "role",
        "content",
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "total_tokens",
        "created_at",
    } <= message_columns


def test_decision_modules_do_not_import_the_coach() -> None:
    root = _REPO_ROOT / "backend" / "app"
    for folder in ("poker", "strategy", "verification"):
        for path in (root / folder).rglob("*.py"):
            assert "app.llm" not in path.read_text(encoding="utf-8")


def test_review_views_request_the_coach_only_from_a_button() -> None:
    api_source = (_REPO_ROOT / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "explainHand" in api_source
    assert "getExplanation" in api_source
    assert "askCoach" in api_source
    assert "/explain" in api_source
    for name in ("GameTable.vue", "HistoryView.vue"):
        source = (_REPO_ROOT / "frontend" / "src" / "components" / name).read_text(
            encoding="utf-8"
        )
        assert "AI 教练解读" in source
        assert source.count("explainHand") == 1
        assert "loadCoach" in source
        assert "loadCachedCoach" in source
        assert "getExplanation" in source
        _assert_no_solver_labels(source)
    card = (_REPO_ROOT / "frontend" / "src" / "components" / "ReviewDecisionCard.vue").read_text(
        encoding="utf-8"
    )
    assert 'type="text"' in card
    assert "contenteditable" not in card.lower()
    assert "aria-label" in card
    assert "追问教练" in card
    assert "<svg" in card
    table = (_REPO_ROOT / "frontend" / "src" / "components" / "GameTable.vue").read_text(
        encoding="utf-8"
    )
    assert "tagName === 'INPUT'" in table
    assert "tagName === 'TEXTAREA'" in table


# ------------------------------------------------------------------ 追问


def _followup_facts(messages: list[dict[str, str]]) -> dict:
    return json.loads(messages[1]["content"].split("\n", 1)[1])


def test_followup_context_keeps_public_facts_and_drops_reasoning() -> None:
    history = _showdown_with_folded_opponent()
    review = build_review(history)
    payload = build_decision_payload(history, review, 0)
    messages = render_followup_messages(
        payload,
        explanation="翻前面对加注，弃牌可以少投入。",
        recommended_action="fold",
        history=[
            {
                "role": "user",
                "content": "为什么不是跟注？",
                "reasoning_content": "这段思维链不能回传。",
            },
            {"role": "assistant", "content": "因为跟注期望为负。"},
        ],
        question="那转牌过牌呢？",
    )
    assert [item["role"] for item in messages] == [
        "system",
        "user",
        "user",
        "assistant",
        "user",
    ]
    assert all(set(item) == {"role", "content"} for item in messages)
    assert "reasoning_content" not in json.dumps(messages, ensure_ascii=False)
    assert "这段思维链不能回传" not in json.dumps(messages, ensure_ascii=False)
    text = messages[0]["content"] + messages[1]["content"]
    _assert_no_solver_labels(text)
    assert "不要改写" in messages[0]["content"]
    assert "revealed_hands" in messages[0]["content"]
    facts = _followup_facts(messages)
    assert facts["decision"]["one_card_outs"] == payload["one_card_outs"]
    assert facts["decision"]["equity"] == payload["equity"]
    assert facts["decision"]["pot_odds"] == payload["pot_odds"]
    assert facts["decision"]["call_ev"] == payload["call_ev"]
    assert facts["decision"]["bot_action"] == payload["bot_action"]
    assert facts["decision"]["mistakes"] == payload["mistakes"]
    assert facts["hand"]["hero_hole_cards"] == payload["hero_hole_cards"]
    assert facts["hand"]["revealed_hands"] == payload["revealed_hands"]
    assert facts["coach"] == {
        "explanation": "翻前面对加注，弃牌可以少投入。",
        "recommended_action": "fold",
    }
    request_text = json.dumps(messages, ensure_ascii=False)
    assert "Qh" not in request_text
    assert "Jc" not in request_text
    assert "As" in request_text
    assert "9s" in request_text
    assert messages[-1]["content"] == "那转牌过牌呢？"


def test_cached_explain_read_does_not_call_upstream(fake_provider: FakeProvider) -> None:
    history = _human_fold_history()
    hand_id = _persist(history)
    client = TestClient(app)
    assert client.get(f"/hands/{hand_id}/explain").json()["decisions"] == []
    assert fake_provider.calls == 0

    created = client.post(f"/hands/{hand_id}/explain")
    assert created.status_code == 200, created.text
    assert fake_provider.calls == 1

    cached = client.get(f"/hands/{hand_id}/explain")
    assert cached.status_code == 200
    body = cached.json()["decisions"][0]
    assert body["cached"] is True
    assert body["explanation"] == created.json()["decisions"][0]["explanation"]
    assert body["messages"] == []
    assert fake_provider.calls == 1

    import app.llm.coach as coach_module

    original = coach_module.PROMPT_SCHEMA_VERSION
    coach_module.PROMPT_SCHEMA_VERSION = original + 1
    try:
        stale = client.get(f"/hands/{hand_id}/explain")
    finally:
        coach_module.PROMPT_SCHEMA_VERSION = original
    assert stale.status_code == 200
    assert stale.json()["decisions"] == []
    assert fake_provider.calls == 1


def test_ask_persists_turns_and_replays_history_without_reasoning(
    fake_provider: FakeProvider,
) -> None:
    history = _showdown_with_folded_opponent()
    hand_id = _persist(history)
    client = TestClient(app)
    created = client.post(f"/hands/{hand_id}/explain")
    assert created.status_code == 200, created.text
    assert fake_provider.calls == 1

    first = client.post(
        f"/hands/{hand_id}/decisions/0/ask",
        json={"question": "  为什么不是跟注？  "},
    )
    assert first.status_code == 200, first.text
    assert fake_provider.json_modes[-1] is False
    payload = first.json()
    assert [item["role"] for item in payload["messages"]] == ["user", "assistant"]
    assert payload["messages"][0]["content"] == "为什么不是跟注？"
    assert payload["messages"][1]["content"] == "结合公开行动线和已有解读，这里不必再追加投入。"
    assert payload["explanation"] == created.json()["decisions"][0]["explanation"]
    sent = fake_provider.messages[-1]
    assert all("reasoning_content" not in item for item in sent)
    assert "先看牌力和要跟的筹码" not in json.dumps(sent, ensure_ascii=False)
    request_text = json.dumps(sent, ensure_ascii=False)
    assert "Qh" not in request_text
    assert "Jc" not in request_text
    facts = _followup_facts(sent)
    review = build_review(history)
    expected = build_decision_payload(history, review, 0)
    assert facts["decision"]["equity"] == expected["equity"]
    assert facts["decision"]["pot_odds"] == expected["pot_odds"]
    assert facts["decision"]["call_ev"] == expected["call_ev"]
    assert facts["decision"]["one_card_outs"] == expected["one_card_outs"]
    assert facts["decision"]["bot_action"] == expected["bot_action"]
    assert facts["decision"]["mistakes"] == expected["mistakes"]
    assert facts["coach"]["explanation"] == payload["explanation"]

    second = client.post(
        f"/hands/{hand_id}/decisions/0/ask",
        json={"question": "那转牌过牌呢？"},
    )
    assert second.status_code == 200, second.text
    roles = [item["role"] for item in second.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]
    replay = [item["content"] for item in fake_provider.messages[-1]]
    assert "为什么不是跟注？" in replay
    assert "结合公开行动线和已有解读，这里不必再追加投入。" in replay
    assert replay[-1] == "那转牌过牌呢？"
    assert [item["role"] for item in fake_provider.messages[-1]] == [
        "system",
        "user",
        "user",
        "assistant",
        "user",
    ]

    rows = _message_rows(hand_id)
    assert [row.role for row in rows] == ["user", "assistant", "user", "assistant"]
    assert rows[1].prompt_tokens == 11
    assert rows[1].completion_tokens == 19
    assert rows[0].total_tokens == 0
    cached = client.get(f"/hands/{hand_id}/explain")
    assert fake_provider.calls == 3
    assert len(cached.json()["decisions"][0]["messages"]) == 4


def test_ask_sanitizes_plain_and_json_replies(fake_provider: FakeProvider) -> None:
    hand_id = _persist(_human_fold_history())
    client = TestClient(app)
    assert client.post(f"/hands/{hand_id}/explain").status_code == 200
    fake_provider.content = (
        '{"reply":"按 GTO 这是最优均衡，nashconv 与 exploitability 都不是依据。'
        '参考仍是非均衡近似。"}'
    )
    response = client.post(
        f"/hands/{hand_id}/decisions/0/ask",
        json={"question": "这样弃牌合理吗？"},
    )
    assert response.status_code == 200, response.text
    reply = response.json()["messages"][-1]["content"]
    _assert_no_solver_labels(reply)
    assert "非均衡" in reply
    assert _message_rows(hand_id)[-1].content == reply


def test_ask_rejects_missing_explanation_and_bad_questions(fake_provider: FakeProvider) -> None:
    hand_id = _persist(_human_fold_history())
    client = TestClient(app)
    missing = client.post(f"/hands/{hand_id}/decisions/0/ask", json={"question": "为什么？"})
    assert missing.status_code == 409
    assert "教练解读" in missing.json()["detail"]
    assert fake_provider.calls == 0
    assert _message_rows(hand_id) == []

    absent = client.post("/hands/missing-hand/decisions/0/ask", json={"question": "为什么？"})
    assert absent.status_code == 404
    blank = client.post(f"/hands/{hand_id}/decisions/0/ask", json={"question": "   "})
    assert blank.status_code == 422
    assert blank.json()["detail"] == "问题需为 1 到 500 个字符"
    too_long = client.post(
        f"/hands/{hand_id}/decisions/0/ask",
        json={"question": "问" * 501},
    )
    assert too_long.status_code == 422
    assert client.post(
        f"/hands/{hand_id}/decisions/9/ask",
        json={"question": "为什么？"},
    ).status_code == 422
    empty_hand = _persist(_no_human_decision_history())
    assert (
        client.post(
            f"/hands/{empty_hand}/decisions/0/ask",
            json={"question": "为什么？"},
        ).status_code
        == 422
    )
    assert fake_provider.calls == 0


def test_ask_upstream_failure_does_not_store_the_question(fake_provider: FakeProvider) -> None:
    hand_id = _persist(_human_fold_history())
    client = TestClient(app)
    before = client.get(f"/hands/{hand_id}/review").json()
    assert client.post(f"/hands/{hand_id}/explain").status_code == 200
    fake_provider.plain_error = CoachUnavailableError("教练解读暂时不可用，请稍后再试")
    failed = client.post(f"/hands/{hand_id}/decisions/0/ask", json={"question": "为什么弃牌？"})
    assert failed.status_code == 503
    assert _message_rows(hand_id) == []
    assert client.get(f"/hands/{hand_id}/review").json() == before
    fake_provider.plain_error = None
    fake_provider.content = "   "
    blank = client.post(f"/hands/{hand_id}/decisions/0/ask", json={"question": "为什么弃牌？"})
    assert blank.status_code == 503
    assert _message_rows(hand_id) == []


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
    history = _heads_up_checked_down()
    hand_id = _persist(history)
    client = TestClient(app)

    first = client.post(f"/hands/{hand_id}/explain")
    assert first.status_code == 200, first.text
    decisions = first.json()["decisions"]
    assert len(decisions) > 1
    assert captured["calls"] == 1
    assert all(item["cached"] is False for item in decisions)
    assert all(item["model"] == "deepseek-flash" for item in decisions)
    assert all(item["provider"] == "deepseek" for item in decisions)
    for item in decisions:
        assert item["explanation"].strip()
        _assert_no_solver_labels(item["explanation"])

    sent = captured["body"]
    assert sent["model"] == "deepseek-flash"
    assert sent["thinking"] == {"type": "enabled"}
    assert sent["reasoning_effort"] == "high"
    assert sent["stream"] is False
    assert sent["response_format"] == {"type": "json_object"}
    assert "temperature" not in sent
    assert "frequency_penalty" not in sent
    assert "presence_penalty" not in sent
    assert "max_tokens" not in sent
    assert captured["timeout"] >= 60
    assert captured["authorization"].startswith("Bearer ")
    assert len(captured["authorization"]) > len("Bearer ")
    request_text = json.dumps(sent["messages"], ensure_ascii=False)
    payload = _request_body(sent["messages"])
    assert [item["action_index"] for item in payload["decisions"]] == [
        item["action_index"] for item in decisions
    ]
    assert "As" in request_text
    assert "公开行动线" in sent["messages"][0]["content"]

    rows = _coach_rows(hand_id)
    assert len(rows) == len(decisions)
    assert len({row.cache_key for row in rows}) == len(rows)
    assert any(row.reasoning_tokens > 0 or row.reasoning_summary for row in rows)
    print(
        "smoke explanations:",
        [(item["action_index"], item["explanation"][:180]) for item in decisions],
        "tokens:",
        rows[0].prompt_tokens,
        rows[0].completion_tokens,
        rows[0].reasoning_tokens,
    )

    second = client.post(f"/hands/{hand_id}/explain")
    assert second.status_code == 200, second.text
    assert all(item["cached"] is True for item in second.json()["decisions"])
    assert captured["calls"] == 1
    assert client.get(f"/hands/{hand_id}/review").status_code == 200
