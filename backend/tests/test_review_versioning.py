"""复盘版本身份与决策级缓存键契约测试：可追溯、单一事实源、版本升级即失效。"""

import pytest
from fastapi.testclient import TestClient

import app.analysis.reference_identity as identity_module
from app.analysis.hand_review import build_review
from app.analysis.reference_identity import (
    CACHE_KEY_VERSION,
    EVALUATION_VERSION,
    REFERENCE_VERSION,
    decision_cache_key,
    reference_identity,
)
from app.main import app
from app.poker.actions import Action, ActionType
from app.poker.engine import PokerEngine
from app.storage.db import init_db
from app.storage.hand_history import build_hand_history

from .helpers import cards


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield


def _sample_review() -> dict:
    """打一手最短的牌并返回复盘结果（真人翻前弃牌，无决策点也无妨）。"""
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(
        button=0,
        hole_cards={0: cards("As Kd"), 1: cards("Qh Jc")},
        board=cards("2c 7d 9h Ts 3c"),
    )
    engine.apply_action(Action(ActionType.FOLD))
    assert engine.hand_over
    return build_review(build_hand_history(engine, hand_number=1, human_seat=0))


def _key(**overrides) -> str:
    params = {
        "hand_id": "hand-1",
        "action_index": 2,
        "seat": 0,
        "input_digest": "digest-abc",
        "prompt_schema_version": 1,
        "provider": "local",
        "model": "none",
    }
    params.update(overrides)
    return decision_cache_key(**params)


# ------------------------------------------------------------------ 版本身份


def test_reference_identity_is_declared() -> None:
    assert reference_identity() == {
        "reference_strategy": "heuristic-conservative",
        "reference_version": 1,
        "evaluation_version": 1,
        "reference_coverage": "vs-random",
    }


def test_review_uses_the_single_source_identity() -> None:
    review = _sample_review()
    for key, value in reference_identity().items():
        assert review[key] == value
    # 兼容字段取值保持不变。
    assert review["reference_strategy"] == "heuristic-conservative"


def test_review_endpoint_declares_versions() -> None:
    client = TestClient(app)
    created = client.post("/games", json={"num_players": 2, "target_hands": 5, "seed": 7}).json()
    finished = client.post(
        f"/games/{created['session_id']}/actions", json={"action": "fold"}
    ).json()
    body = client.get(f"/hands/{finished['last_hand_id']}/review").json()

    assert body["reference_strategy"] == "heuristic-conservative"
    assert body["reference_version"] == REFERENCE_VERSION
    assert body["evaluation_version"] == EVALUATION_VERSION
    assert body["reference_coverage"] == "vs-random"


# ------------------------------------------------------------------ 缓存键契约


def test_cache_key_is_deterministic() -> None:
    assert _key() == _key()


def test_cache_key_includes_every_required_component() -> None:
    assert _key().split("|") == [
        f"v{CACHE_KEY_VERSION}",
        "hand-1",
        "2",
        "0",
        "digest-abc",
        f"ref={REFERENCE_VERSION}",
        f"eval={EVALUATION_VERSION}",
        "prompt=1",
        "local",
        "none",
    ]


def test_cache_key_changes_with_reference_version(monkeypatch: pytest.MonkeyPatch) -> None:
    before = _key()
    monkeypatch.setattr(identity_module, "REFERENCE_VERSION", REFERENCE_VERSION + 1)
    assert _key() != before


def test_cache_key_changes_with_evaluation_version(monkeypatch: pytest.MonkeyPatch) -> None:
    before = _key()
    monkeypatch.setattr(identity_module, "EVALUATION_VERSION", EVALUATION_VERSION + 1)
    assert _key() != before


def test_cache_key_changes_with_decision_identity() -> None:
    assert _key(hand_id="hand-2") != _key()
    assert _key(action_index=3) != _key()
    assert _key(seat=1) != _key()
    assert _key(input_digest="digest-xyz") != _key()
    assert _key(provider="remote", model="m1") != _key()
