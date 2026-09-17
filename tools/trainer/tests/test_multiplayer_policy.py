import json
from copy import deepcopy
from math import fsum
from pathlib import Path
from typing import Any

import pytest

from multiplayer_cfr.game import GAME_ID, GAME_VERSION, infosets
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
    load_strategy,
    lookup,
)


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
            "prng": "python-random-mt19937",
            "seed_derivation": "not-applicable-without-training",
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


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


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


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.__setitem__("unexpected", True),
        lambda payload: payload["game"].__setitem__("version", "other-version"),
        lambda payload: payload["game"].update(
            {"player_count": 7, "deck": {"rank_count": 7, "copies_per_rank": 1}}
        ),
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
