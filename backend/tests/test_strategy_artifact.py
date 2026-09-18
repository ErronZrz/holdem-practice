"""受控策略产物加载与查表的回归测试（合成小样本，不触碰任何真实工件）。"""

import hashlib
import inspect
import json
import socket
from pathlib import Path

import pytest

from app.strategy.abstraction import (
    ABSTRACTION_GAME_VERSION,
    COVERAGE_INCOMPLETE_INFOSET,
    COVERAGE_OUT_OF_ABSTRACTION,
    COVERAGE_VERSION_MISMATCH,
    DEFAULT_FALLBACK_IDENTIFIER,
    FALLBACK_SOURCE_DECLARED_CONTRACT,
)
from app.strategy.artifact import (
    ARTIFACT_TYPE,
    LookupOutcome,
    LookupRegistry,
    LookupTable,
    StrategyArtifactError,
    StrategyInfoset,
    load_lookup_registry,
    load_lookup_table,
    load_strategy_artifact,
)
from app.strategy.registry import known_identifiers

_PROBABILITY_UNITS = 1_000_000_000_000
_HALF_UNITS = _PROBABILITY_UNITS // 2


def _game(player_count: int) -> dict:
    return {
        "action_tree_version": "single-open-v1",
        "ante": 1,
        "bet": 1,
        "deck": {"copies_per_rank": 1, "rank_count": player_count},
        "id": "m8-unique-rank-single-open",
        "player_count": player_count,
        "remainder_priority": "not-applicable",
        "seat_semantics": "relative-seat-0-is-first-actor",
        "tie_rule": "highest-unique-rank-wins-all",
        "version": ABSTRACTION_GAME_VERSION,
    }


def _infoset(
    player_count: int,
    actor: int,
    rank: int,
    history: str,
    *,
    legal_actions: list[str],
    public_state: dict,
    units: dict[str, int] | None = None,
) -> dict:
    key = (
        f"m8/{ABSTRACTION_GAME_VERSION}/n={player_count}"
        f"/actor={actor}/rank={rank}/history={history}"
    )
    distribution = units if units is not None else dict.fromkeys(legal_actions, _HALF_UNITS)
    return {
        "actions": distribution,
        "actor": actor,
        "history": history,
        "key": key,
        "legal_actions": list(legal_actions),
        "public_state": dict(public_state),
        "rank": rank,
    }


def _open_state(actor: int) -> dict:
    return {
        "actor": actor,
        "opener": None,
        "folded": [],
        "active": [0, 1, 2, 3, 4, 5],
        "contributions": [1, 1, 1, 1, 1, 1],
        "pending_responders": [],
        "terminal": False,
    }


def _default_infosets(player_count: int = 6) -> list[dict]:
    """三条最小信息集：根、一次过牌、一次开池。"""
    return [
        _infoset(
            player_count,
            0,
            0,
            "-",
            legal_actions=["x", "b"],
            public_state=_open_state(0),
        ),
        _infoset(
            player_count,
            1,
            0,
            "x@0",
            legal_actions=["x", "b"],
            public_state=_open_state(1),
        ),
        _infoset(
            player_count,
            1,
            2,
            "b@0",
            legal_actions=["c", "f"],
            public_state={
                "actor": 1,
                "opener": 0,
                "folded": [],
                "active": [0, 1, 2, 3, 4, 5],
                "contributions": [2, 1, 1, 1, 1, 1],
                "pending_responders": [1, 2, 3, 4, 5],
                "terminal": False,
            },
        ),
    ]


def _payload(player_count: int = 6, infosets: list[dict] | None = None) -> dict:
    entries = _default_infosets(player_count) if infosets is None else infosets
    return {
        "artifact_type": ARTIFACT_TYPE,
        "game": _game(player_count),
        "infosets": entries,
        "probability_units": _PROBABILITY_UNITS,
        "quality": {"coverage": {"total_infosets": len(entries), "visited_infosets": 0}},
        "resources": {"artifact_bytes": 0, "infoset_count": len(entries)},
        "schema_version": 1,
        "training": {"algorithm": "synthetic-fixed-sample", "master_seed": 0},
    }


def _write(tmp_path: Path, text: str, name: str = "strategy.json") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _write_payload(tmp_path: Path, payload: dict, name: str = "strategy.json") -> Path:
    """写出载荷，并把自述字节数收敛到真实文件长度。"""
    text = json.dumps(payload, ensure_ascii=False)
    for _ in range(10):
        payload["resources"]["artifact_bytes"] = len(text.encode("utf-8"))
        updated = json.dumps(payload, ensure_ascii=False)
        text = updated
        if len(updated) == payload["resources"]["artifact_bytes"]:
            break
    return _write(tmp_path, text, name=name)


# ---------------------------------------------------------------- 加载成功


def test_loads_valid_synthetic_artifact(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, _payload())
    artifact = load_strategy_artifact(path)

    raw = path.read_bytes()
    assert artifact.identity.sha256 == hashlib.sha256(raw).hexdigest()
    assert artifact.identity.byte_length == len(raw)
    assert artifact.artifact_type == ARTIFACT_TYPE
    assert artifact.schema_version == 1
    assert artifact.probability_units == _PROBABILITY_UNITS
    assert artifact.game.player_count == 6
    assert artifact.game.game_version == ABSTRACTION_GAME_VERSION
    assert len(artifact.infosets) == 3


def test_lookup_table_indexes_every_infoset(tmp_path: Path) -> None:
    table = load_lookup_table(_write_payload(tmp_path, _payload()))
    assert table.player_count == 6
    assert table.infoset_count == 3
    for entry in table.artifact.infosets:
        assert table.entry_for(entry.key) is entry


# ---------------------------------------------------------------- 加载失败


def test_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    text = json.dumps(_payload(), ensure_ascii=False).replace(
        '"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1
    )
    with pytest.raises(StrategyArtifactError, match="重复键"):
        load_strategy_artifact(_write(tmp_path, text))


def test_rejects_non_finite_number(tmp_path: Path) -> None:
    text = json.dumps(_payload(), ensure_ascii=False).replace('"schema_version": 1', '"x": NaN')
    with pytest.raises(StrategyArtifactError, match="非有限数值"):
        load_strategy_artifact(_write(tmp_path, text))


def test_rejects_non_object_top_level(tmp_path: Path) -> None:
    with pytest.raises(StrategyArtifactError, match="顶层必须是对象"):
        load_strategy_artifact(_write(tmp_path, "[]"))


def test_rejects_non_utf8_bytes(tmp_path: Path) -> None:
    path = tmp_path / "strategy.json"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(StrategyArtifactError, match="UTF-8"):
        load_strategy_artifact(path)


def test_rejects_directory_path(tmp_path: Path) -> None:
    with pytest.raises(StrategyArtifactError, match="普通文件"):
        load_strategy_artifact(tmp_path)


def test_rejects_oversize_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_payload(tmp_path, _payload())
    monkeypatch.setattr("app.strategy.artifact.MAX_ARTIFACT_BYTES", 32)
    with pytest.raises(StrategyArtifactError, match="大小上限"):
        load_strategy_artifact(path)


@pytest.mark.parametrize("field", ["quality", "resources", "training", "insosets"])
def test_rejects_missing_or_unknown_top_level_field(tmp_path: Path, field: str) -> None:
    payload = _payload()
    if field in payload:
        del payload[field]
    else:
        payload["insosets"] = []
    with pytest.raises(StrategyArtifactError):
        load_strategy_artifact(_write(tmp_path, json.dumps(payload, ensure_ascii=False)))


def test_rejects_wrong_artifact_type(tmp_path: Path) -> None:
    payload = _payload()
    payload["artifact_type"] = "some-other-artifact"
    with pytest.raises(StrategyArtifactError, match="类型不受支持"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_wrong_schema_version(tmp_path: Path) -> None:
    payload = _payload()
    payload["schema_version"] = 2
    with pytest.raises(StrategyArtifactError, match="结构版本不受支持"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_unsupported_game_version(tmp_path: Path) -> None:
    payload = _payload()
    payload["game"]["version"] = "m8-a-v0"
    with pytest.raises(StrategyArtifactError, match="抽象版本不受支持"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_player_count_outside_abstraction(tmp_path: Path) -> None:
    payload = _payload()
    payload["game"]["player_count"] = 8
    payload["game"]["deck"]["rank_count"] = 8
    with pytest.raises(StrategyArtifactError, match="人数"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_deck_scale_mismatch(tmp_path: Path) -> None:
    payload = _payload()
    payload["game"]["deck"]["rank_count"] = 7
    with pytest.raises(StrategyArtifactError, match="牌组规模"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_duplicated_rank_deck(tmp_path: Path) -> None:
    payload = _payload()
    payload["game"]["deck"]["copies_per_rank"] = 2
    with pytest.raises(StrategyArtifactError, match="唯一 rank"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_non_positive_probability_units(tmp_path: Path) -> None:
    payload = _payload()
    payload["probability_units"] = 0
    with pytest.raises(StrategyArtifactError, match="probability_units"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_infoset_count_mismatch_with_quality(tmp_path: Path) -> None:
    payload = _payload()
    payload["quality"]["coverage"]["total_infosets"] = 99
    with pytest.raises(StrategyArtifactError, match="互相矛盾"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_listed_infoset_count_mismatch(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"] = payload["infosets"][:2]
    with pytest.raises(StrategyArtifactError, match="条数"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_artifact_bytes_mismatch(tmp_path: Path) -> None:
    path = _write_payload(tmp_path, _payload())
    text = json.loads(path.read_text(encoding="utf-8"))
    text["resources"]["artifact_bytes"] = 123
    padded = json.dumps(text, ensure_ascii=False)
    with pytest.raises(StrategyArtifactError, match="字节数"):
        load_strategy_artifact(_write(tmp_path, padded, name="tampered.json"))


def test_rejects_infoset_key_mismatch(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"][0]["key"] = "m8/m8-a-v1/n=6/actor=0/rank=0/history=x@0"
    with pytest.raises(StrategyArtifactError, match="规范重算"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_terminal_history(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"] = [
        _infoset(
            6,
            0,
            0,
            "x@0|x@1|x@2|x@3|x@4|x@5",
            legal_actions=["x", "b"],
            public_state=_open_state(0),
        )
    ]
    payload["quality"]["coverage"]["total_infosets"] = 1
    payload["resources"]["infoset_count"] = 1
    with pytest.raises(StrategyArtifactError, match="不在该抽象内"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_unknown_action(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"][0]["actions"] = {"x": _HALF_UNITS, "r": _HALF_UNITS}
    with pytest.raises(StrategyArtifactError, match="未知动作"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_units_not_summing_to_probability_units(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"][0]["actions"] = {"x": 1, "b": 1}
    with pytest.raises(StrategyArtifactError, match="单位之和"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_negative_units(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"][0]["actions"] = {"x": -1, "b": _PROBABILITY_UNITS + 1}
    with pytest.raises(StrategyArtifactError, match="不能小于"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_duplicate_infoset_keys(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"].append(dict(payload["infosets"][0]))
    payload["quality"]["coverage"]["total_infosets"] = 4
    payload["resources"]["infoset_count"] = 4
    with pytest.raises(StrategyArtifactError, match="重复信息集键"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_legal_actions_inconsistent_with_history(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"][0]["legal_actions"] = ["c", "f"]
    payload["infosets"][0]["actions"] = {"c": _HALF_UNITS, "f": _HALF_UNITS}
    with pytest.raises(StrategyArtifactError, match="阶段不一致"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_misaligned_public_state(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"][2]["public_state"]["contributions"] = [1, 1, 1, 1, 1, 1]
    with pytest.raises(StrategyArtifactError, match="公开投影与公开历史不一致"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_public_state_with_unknown_field(tmp_path: Path) -> None:
    payload = _payload()
    payload["infosets"][0]["public_state"]["opponent_cards"] = ["As", "Kd"]
    with pytest.raises(StrategyArtifactError, match="字段集不匹配"):
        load_strategy_artifact(_write_payload(tmp_path, payload))


def test_rejects_duplicate_player_count_registration(tmp_path: Path) -> None:
    first = _write_payload(tmp_path, _payload(), "strategy-a.json")
    second = _write_payload(tmp_path, _payload(), "strategy-b.json")
    with pytest.raises(StrategyArtifactError, match="多份产物"):
        load_lookup_registry([first, second])


# ---------------------------------------------------------------- 查表语义


def _registry(tmp_path: Path) -> LookupRegistry:
    return load_lookup_registry([_write_payload(tmp_path, _payload())])


def _root_lookup(registry: LookupRegistry, **overrides) -> LookupOutcome:
    payload = {
        "game_version": ABSTRACTION_GAME_VERSION,
        "player_count": 6,
        "relative_actor": 0,
        "own_rank": 0,
        "canonical_public_history": "-",
    }
    payload.update(overrides)
    return registry.lookup(**payload)


def test_hit_returns_the_exact_distribution(tmp_path: Path) -> None:
    outcome = _root_lookup(_registry(tmp_path))
    assert outcome.is_hit
    assert outcome.status == "hit"
    assert outcome.action_units == {"x": _HALF_UNITS, "b": _HALF_UNITS}
    assert sum(outcome.action_units.values()) == _PROBABILITY_UNITS
    assert outcome.fallback is None


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"player_count": 8}, COVERAGE_OUT_OF_ABSTRACTION),
        ({"game_version": "m8-a-v0"}, COVERAGE_VERSION_MISMATCH),
        ({"canonical_public_history": None}, COVERAGE_INCOMPLETE_INFOSET),
    ],
)
def test_uncovered_statuses_are_explicit(tmp_path: Path, overrides, expected: str) -> None:
    outcome = _root_lookup(_registry(tmp_path), **overrides)
    assert outcome.status == expected
    assert outcome.action_units is None
    assert outcome.is_hit is False
    assert outcome.reasons


def test_artifact_unavailable_for_player_count_without_artifact(tmp_path: Path) -> None:
    outcome = _root_lookup(_registry(tmp_path), player_count=9)
    assert outcome.status == "artifact-unavailable"
    assert outcome.action_units is None
    assert outcome.fallback is not None
    assert outcome.fallback.triggering_coverage == "artifact-unavailable"


def test_artifact_mismatch_when_registry_keying_is_wrong(tmp_path: Path) -> None:
    # 刻意把六人产物挂到七人键下，验证产物与请求错配时明确失败。
    table = load_lookup_table(_write_payload(tmp_path, _payload()))
    registry = LookupRegistry(by_player_count={7: table})
    outcome = _root_lookup(registry, player_count=7)
    assert outcome.status == "artifact-mismatch"
    assert outcome.action_units is None
    assert outcome.fallback is not None
    assert outcome.fallback.triggering_coverage == "artifact-mismatch"


def test_key_not_in_artifact_never_returns_a_neighbour(tmp_path: Path) -> None:
    outcome = _root_lookup(
        _registry(tmp_path),
        relative_actor=2,
        canonical_public_history="x@0|x@1",
    )
    assert outcome.status == "key-not-in-artifact"
    assert outcome.action_units is None
    assert outcome.abstraction_key == "m8/m8-a-v1/n=6/actor=2/rank=0/history=x@0|x@1"
    assert outcome.fallback is not None


@pytest.mark.parametrize("player_count", [2, 3, 4, 5, 6, 7, 8, 9])
def test_lookup_is_parameterized_by_player_count(tmp_path: Path, player_count: int) -> None:
    outcome = _root_lookup(_registry(tmp_path), player_count=player_count)
    if player_count == 6:
        assert outcome.is_hit
    elif player_count in (7, 9):
        assert outcome.status == "artifact-unavailable"
    else:
        assert outcome.status == COVERAGE_OUT_OF_ABSTRACTION


def test_every_non_hit_declares_a_registered_fallback(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    outcomes = [
        registry.lookup(
            game_version=ABSTRACTION_GAME_VERSION,
            player_count=count,
            relative_actor=0,
            own_rank=0,
            canonical_public_history="-",
        )
        for count in range(2, 10)
    ]
    non_hits = [item for item in outcomes if not item.is_hit]
    assert non_hits
    for outcome in non_hits:
        assert outcome.action_units is None
        assert outcome.fallback is not None
        assert outcome.fallback.fallback_identifier == DEFAULT_FALLBACK_IDENTIFIER
        assert outcome.fallback.fallback_identifier in known_identifiers()
        assert outcome.fallback.source == FALLBACK_SOURCE_DECLARED_CONTRACT
        assert outcome.fallback.is_exact_solution is False


def test_lookup_does_not_touch_the_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*args, **kwargs):
        raise AssertionError("查表不得发起网络调用")

    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    assert _root_lookup(_registry(tmp_path)).is_hit


def test_lookup_accepts_only_the_abstraction_projection() -> None:
    parameters = list(inspect.signature(LookupRegistry.lookup).parameters)
    assert parameters == [
        "self",
        "game_version",
        "player_count",
        "relative_actor",
        "own_rank",
        "canonical_public_history",
    ]


def test_outcome_and_infoset_carry_no_hidden_or_future_fields() -> None:
    forbidden = {
        "hole_cards",
        "board",
        "seed",
        "master_seed",
        "opponent_cards",
        "rng_state",
        "blinds",
    }
    assert forbidden.isdisjoint(LookupOutcome.model_fields)
    assert forbidden.isdisjoint(StrategyInfoset.model_fields)
    assert forbidden.isdisjoint(LookupTable.model_fields)
