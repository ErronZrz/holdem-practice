"""策略注册表测试：旧值兼容、版本化标识、未知标识与任意类名/模块路径被拒。"""

import pytest
from fastapi.testclient import TestClient

from app.api import games
from app.main import app
from app.storage import repository
from app.storage.db import get_db, init_db
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.mixed_strategy import MixedLocalStrategy
from app.strategy.random_strategy import RandomStrategy
from app.strategy.registry import (
    StrategySpec,
    UnknownStrategyError,
    create_strategy,
    known_identifiers,
    register_strategy,
    resolve_identifier,
    spec_for,
)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield


# ------------------------------------------------------------------ 标识解析


def test_legacy_values_normalize_to_frozen_versions() -> None:
    assert resolve_identifier("heuristic") == "heuristic@1"
    assert resolve_identifier("random") == "random@1"


def test_canonical_identifiers_resolve_unchanged() -> None:
    assert resolve_identifier("heuristic@1") == "heuristic@1"
    assert resolve_identifier("random@1") == "random@1"
    assert {"heuristic@1", "random@1", "mixed-local@1"} <= set(known_identifiers())


def test_mixed_identity_has_no_unversioned_alias() -> None:
    assert resolve_identifier("mixed-local@1") == "mixed-local@1"
    assert spec_for("mixed-local@1").name == "mixed-local"
    assert spec_for("mixed-local@1").version == 1
    with pytest.raises(UnknownStrategyError):
        resolve_identifier("mixed-local")
    # 已注册的版本号逐版上移，因此这里改用尚未注册的版本号；「未知版本必须被拒」的性质不变。
    with pytest.raises(UnknownStrategyError):
        resolve_identifier("mixed-local@8")


def test_mixed_strategy_factory_is_registered() -> None:
    assert isinstance(create_strategy("mixed-local@1", 3), MixedLocalStrategy)


def test_spec_exposes_version() -> None:
    assert spec_for("heuristic").name == "heuristic"
    assert spec_for("heuristic").version == 1
    assert spec_for("random").version == 1


@pytest.mark.parametrize(
    "value",
    [
        "cfr",
        "heuristic@2",
        "HeuristicStrategy",
        "app.strategy.HeuristicStrategy",
        "app.strategy.heuristic",
        "os.system",
        "",
        "heuristic@1 ",
    ],
)
def test_unknown_identifiers_fail(value: str) -> None:
    with pytest.raises(UnknownStrategyError):
        resolve_identifier(value)


def test_create_strategy_returns_registered_type() -> None:
    assert isinstance(create_strategy("heuristic", 3), HeuristicStrategy)
    assert isinstance(create_strategy("random@1", 3), RandomStrategy)


# ------------------------------------------------------------------ 注册表约束


def test_duplicate_identifier_rejected() -> None:
    duplicate = StrategySpec(
        identifier="random@1",
        name="random",
        version=1,
        factory=lambda seed: RandomStrategy(seed=seed),
        description="重复注册应被拒绝",
    )
    with pytest.raises(ValueError):
        register_strategy(duplicate)


def test_legacy_alias_cannot_be_reclaimed_by_new_version() -> None:
    # 新版本不得占用旧名称，否则旧客户端会被静默切到新行为。
    intruder = StrategySpec(
        identifier="heuristic@2",
        name="heuristic",
        version=2,
        factory=lambda seed: HeuristicStrategy(seed=seed),
        description="故意复用旧别名，必须失败",
    )
    with pytest.raises(ValueError):
        register_strategy(intruder, aliases=("heuristic",))
    # 失败的注册不得留下任何痕迹。
    assert "heuristic@2" not in known_identifiers()
    assert resolve_identifier("heuristic") == "heuristic@1"


# ------------------------------------------------------------------ 接口层


def _stored_strategy(session_id: str) -> str:
    db = next(get_db())
    try:
        session = repository.get_session(db, session_id)
        assert session is not None
        return session.bot_strategy
    finally:
        db.close()


def test_create_game_normalizes_legacy_value() -> None:
    client = TestClient(app)
    resp = client.post("/games", json={"num_players": 2, "bot_strategy": "heuristic"})
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    assert _stored_strategy(session_id) == "heuristic@1"
    assert isinstance(games._registry[session_id].bot, HeuristicStrategy)


def test_create_game_defaults_to_canonical_identifier() -> None:
    client = TestClient(app)
    resp = client.post("/games", json={"num_players": 2})
    assert resp.status_code == 201
    assert _stored_strategy(resp.json()["session_id"]) == "heuristic@1"


def test_create_game_accepts_versioned_identifier() -> None:
    client = TestClient(app)
    resp = client.post("/games", json={"num_players": 2, "bot_strategy": "random@1"})
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    assert _stored_strategy(session_id) == "random@1"
    assert isinstance(games._registry[session_id].bot, RandomStrategy)


@pytest.mark.parametrize(
    "value",
    [
        "cfr",
        "heuristic@2",
        "mixed-local",
        "mixed-local@8",
        "app.strategy.HeuristicStrategy",
        "os.system",
    ],
)
def test_create_game_rejects_unknown_identifier(value: str) -> None:
    client = TestClient(app)
    resp = client.post("/games", json={"num_players": 2, "bot_strategy": value})
    assert resp.status_code == 422


def test_create_game_accepts_mixed_identifier() -> None:
    client = TestClient(app)
    resp = client.post(
        "/games", json={"num_players": 3, "seed": 5, "bot_strategy": "mixed-local@1"}
    )
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    assert _stored_strategy(session_id) == "mixed-local@1"
    assert isinstance(games._registry[session_id].bot, MixedLocalStrategy)
