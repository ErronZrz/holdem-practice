import json
from copy import deepcopy
from math import fsum
from pathlib import Path
from typing import Any

import pytest

from multiplayer_cfr import policy
from multiplayer_cfr.chance import PRNG_ID
from multiplayer_cfr.game import GAME_ID, GAME_VERSION, Action, infosets
from multiplayer_cfr.mccfr import MCCFRConfig, MCCFRResult
from multiplayer_cfr.policy import (
    ALGORITHM,
    ARTIFACT_TYPE,
    CHANCE_MODEL,
    ITERATION_DEFINITION,
    PROBABILITY_UNITS,
    SCHEMA_VERSION,
    TRAVERSER_SCHEDULE,
    UPDATE_MODE,
    StrategyArtifactError,
    _quantize_probabilities,
    export_strategy,
    load_strategy,
    lookup,
)
from multiplayer_cfr.randomness import SEED_DERIVATION_ID
from multiplayer_cfr.resources import estimate_resources


def _valid_payload(player_count: int = 6) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for spec in infosets(player_count):
        first_action, second_action = spec.actions
        entries.append(
            {
                "key": spec.key,
                "actor": spec.actor,
                "rank": spec.rank,
                "history": spec.history,
                "public_state": spec.public_state.projection(),
                "legal_actions": [first_action.value, second_action.value],
                "actions": {
                    first_action.value: PROBABILITY_UNITS // 2,
                    second_action.value: PROBABILITY_UNITS // 2,
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "game": {
            "id": GAME_ID,
            "version": GAME_VERSION,
            "player_count": player_count,
            "deck": {"rank_count": player_count, "copies_per_rank": 1},
            "ante": 1,
            "bet": 1,
            "action_tree_version": "single-open-v1",
            "tie_rule": "highest-unique-rank-wins-all",
            "remainder_priority": "not-applicable",
            "seat_semantics": "relative-seat-0-is-first-actor",
        },
        "training": {
            "algorithm": ALGORITHM,
            "update_mode": UPDATE_MODE,
            "iteration_definition": ITERATION_DEFINITION,
            "iterations": 1,
            "average_strategy_start_iteration": 1,
            "chance_model": CHANCE_MODEL,
            "traverser_schedule": TRAVERSER_SCHEDULE,
            "master_seed": 20260917,
            "prng": PRNG_ID,
            "seed_derivation": SEED_DERIVATION_ID,
            "python_version": "3.12",
            "trainer_version": "candidate-a-contract-only",
        },
        "probability_units": PROBABILITY_UNITS,
        "infosets": entries,
        "quality": {
            "profile_id": "not-measured",
            "full_chance": False,
            "sample_seed": None,
            "sample_count": 0,
            "utilities": [0] * player_count,
            "probe_manifest_id": "not-measured",
            "probe_gains": [0.0] * player_count,
            "coverage": {"visited_infosets": 0, "total_infosets": len(entries)},
            "stability": {"status": "not-measured"},
        },
        "resources": {
            "elapsed_seconds": 0.0,
            "peak_rss_bytes": 0,
            "infoset_count": len(entries),
            "artifact_bytes": 0,
            "warning_triggered": False,
            "stop_condition_triggered": False,
        },
    }


def _serialized_payload(payload: dict[str, Any]) -> str:
    artifact_bytes = 0
    for _ in range(16):
        payload["resources"]["artifact_bytes"] = artifact_bytes
        serialized = (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        actual_bytes = len(serialized.encode("utf-8"))
        if actual_bytes == artifact_bytes:
            return serialized
        artifact_bytes = actual_bytes
    raise AssertionError("测试 payload 的 artifact_bytes 未收敛")


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(_serialized_payload(payload), encoding="utf-8")


def _completed_result(*, reverse_insertion_order: bool = False) -> MCCFRResult:
    config = MCCFRConfig(
        player_count=6,
        iterations=1,
        master_seed=20260917,
        average_strategy_start_iteration=1,
    )
    specs = tuple(reversed(infosets(6))) if reverse_insertion_order else infosets(6)
    strategy = {
        spec.key: {
            action: 1.0 / len(spec.actions)
            for action in (reversed(spec.actions) if reverse_insertion_order else spec.actions)
        }
        for spec in specs
    }
    return MCCFRResult(
        config=config,
        average_strategy=strategy,
        infoset_count=len(strategy),
        completed_iterations=1,
    )


def test_loader_and_controlled_lookup_accept_a_complete_abstract_artifact(tmp_path: Path) -> None:
    path = tmp_path / "strategy.json"
    _write_payload(path, _valid_payload())

    artifact = load_strategy(path)
    probabilities = lookup(
        artifact,
        game_version=GAME_VERSION,
        player_count=6,
        relative_actor=0,
        own_rank=3,
        canonical_public_history="-",
    )

    assert artifact.game.player_count == 6
    assert set(probabilities) == {"x", "b"}
    assert fsum(probabilities.values()) == pytest.approx(1.0)
    assert artifact.resources["artifact_bytes"] == len(path.read_bytes())


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.__setitem__("unexpected", True),
        lambda payload: payload["game"].__setitem__("version", "other-version"),
        lambda payload: payload["game"].update(
            {"player_count": 7, "deck": {"rank_count": 7, "copies_per_rank": 1}}
        ),
        lambda payload: payload["training"].__setitem__("prng", "other-prng"),
        lambda payload: payload["training"].__setitem__("seed_derivation", "other-derivation"),
        lambda payload: payload["infosets"][0].__setitem__("key", "m8/not-a-real-key"),
        lambda payload: payload["infosets"][0].__setitem__("legal_actions", ["b", "x"]),
        lambda payload: payload["infosets"][0]["actions"].update(
            {"x": -1, "b": PROBABILITY_UNITS + 1}
        ),
        lambda payload: payload["infosets"][0]["actions"].update(
            {"x": PROBABILITY_UNITS - 1, "b": 0}
        ),
        lambda payload: payload["infosets"][0]["public_state"]["contributions"].__setitem__(0, 2),
    ],
)
def test_loader_rejects_unknown_or_inconsistent_contract_data(tmp_path: Path, mutator: Any) -> None:
    path = tmp_path / "strategy.json"
    payload = deepcopy(_valid_payload())
    mutator(payload)
    _write_payload(path, payload)

    with pytest.raises(StrategyArtifactError):
        load_strategy(path)


@pytest.mark.parametrize(
    "raw_json",
    [
        '{"schema_version":1,"schema_version":1}',
        '{"schema_version":NaN}',
        '{"schema_version":Infinity}',
    ],
)
def test_loader_rejects_duplicate_keys_and_non_finite_json(tmp_path: Path, raw_json: str) -> None:
    path = tmp_path / "strategy.json"
    path.write_text(raw_json, encoding="utf-8")

    with pytest.raises(StrategyArtifactError):
        load_strategy(path)


def test_loader_rejects_an_incorrect_declared_artifact_size(tmp_path: Path) -> None:
    path = tmp_path / "strategy.json"
    payload = _valid_payload()
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")

    with pytest.raises(StrategyArtifactError):
        load_strategy(path)


def test_lookup_rejects_cross_game_cross_player_count_and_abstract_external_input(
    tmp_path: Path,
) -> None:
    path = tmp_path / "strategy.json"
    _write_payload(path, _valid_payload())
    artifact = load_strategy(path)

    with pytest.raises(StrategyArtifactError):
        lookup(
            artifact,
            game_version="m8-a-v0",
            player_count=6,
            relative_actor=0,
            own_rank=3,
            canonical_public_history="-",
        )
    with pytest.raises(StrategyArtifactError):
        lookup(
            artifact,
            game_version=GAME_VERSION,
            player_count=7,
            relative_actor=0,
            own_rank=3,
            canonical_public_history="-",
        )
    with pytest.raises(StrategyArtifactError):
        lookup(
            artifact,
            game_version=GAME_VERSION,
            player_count=6,
            relative_actor=0,
            own_rank=3,
            canonical_public_history="x@1",
        )


def test_export_quantizes_reloads_and_keeps_not_measured_evidence(tmp_path: Path) -> None:
    path = tmp_path / "strategy.json"

    artifact = export_strategy(path, _completed_result(), trainer_version="candidate-a-export-v1")

    assert path.read_bytes().endswith(b"\n")
    assert artifact.resources["artifact_bytes"] == len(path.read_bytes())
    assert artifact.resources["artifact_bytes"] <= estimate_resources(6).artifact_budget_bytes
    assert artifact.training["prng"] == PRNG_ID
    assert artifact.training["seed_derivation"] == SEED_DERIVATION_ID
    assert artifact.quality["profile_id"] == "not-measured"
    assert artifact.quality["stability"] == {"status": "not-measured"}
    assert artifact.resources["elapsed_seconds"] == 0.0
    assert artifact.resources["peak_rss_bytes"] == 0
    assert load_strategy(path) == artifact
    assert list(tmp_path.iterdir()) == [path]


def test_export_is_byte_deterministic_across_mapping_insertion_orders(tmp_path: Path) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    export_strategy(first_path, _completed_result(), trainer_version="candidate-a-export-v1")
    export_strategy(
        second_path,
        _completed_result(reverse_insertion_order=True),
        trainer_version="candidate-a-export-v1",
    )

    assert first_path.read_bytes() == second_path.read_bytes()


def test_quantization_uses_action_value_as_a_stable_tie_breaker(monkeypatch) -> None:
    monkeypatch.setattr(policy, "PROBABILITY_UNITS", 3)

    units = _quantize_probabilities(
        {Action.CHECK: 0.5, Action.BET: 0.5},
        (Action.CHECK, Action.BET),
    )

    assert units == {"x": 1, "b": 2}


def test_export_rejects_incomplete_result_without_overwriting_existing_target(
    tmp_path: Path,
) -> None:
    path = tmp_path / "strategy.json"
    path.write_bytes(b"existing artifact")
    result = _completed_result()
    incomplete = MCCFRResult(
        config=result.config,
        average_strategy=result.average_strategy,
        infoset_count=result.infoset_count,
        completed_iterations=0,
    )

    with pytest.raises(StrategyArtifactError):
        export_strategy(path, incomplete, trainer_version="candidate-a-export-v1")

    assert path.read_bytes() == b"existing artifact"


def test_export_rejects_invalid_strategy_before_writing(tmp_path: Path) -> None:
    path = tmp_path / "strategy.json"
    path.write_bytes(b"existing artifact")
    result = _completed_result()
    invalid_strategy = dict(result.average_strategy)
    invalid_strategy.pop(next(iter(invalid_strategy)))
    invalid = MCCFRResult(
        config=result.config,
        average_strategy=invalid_strategy,
        infoset_count=result.infoset_count,
        completed_iterations=result.completed_iterations,
    )

    with pytest.raises(StrategyArtifactError):
        export_strategy(path, invalid, trainer_version="candidate-a-export-v1")

    assert path.read_bytes() == b"existing artifact"
