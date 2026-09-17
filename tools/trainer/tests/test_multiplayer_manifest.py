from copy import deepcopy
from pathlib import Path

import pytest

from multiplayer_cfr.manifest import (
    EVALUATOR_ID,
    EVALUATOR_VERSION,
    EXPERIMENT_MANIFEST_TYPE,
    MANIFEST_SCHEMA_VERSION,
    PROBE_MANIFEST_TYPE,
    ManifestError,
    create_experiment_manifest,
    create_probe_manifest,
    derive_experiment_plan,
    load_experiment_manifest,
    load_probe_manifest,
    write_experiment_manifest,
    write_probe_manifest,
)
from multiplayer_cfr.policy import PROBABILITY_UNITS

_COMMIT = "1" * 40


def _probe_payload(player_count: int = 6) -> dict[str, object]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": PROBE_MANIFEST_TYPE,
        "manifest_id": f"a{player_count}-probes",
        "game": {
            "id": "m8-unique-rank-single-open",
            "version": "m8-a-v1",
            "player_count": player_count,
        },
        "evaluator": {
            "evaluator_id": EVALUATOR_ID,
            "evaluator_version": EVALUATOR_VERSION,
            "probability_units": PROBABILITY_UNITS,
        },
        "probes": [
            {"probe_id": "high-open", "open_threshold": player_count - 1, "call_threshold": 3},
            {"probe_id": "median", "open_threshold": player_count // 2, "call_threshold": 3},
        ],
    }


def _experiment_payload(
    *,
    player_count: int = 6,
    probe_reference: dict[str, object] | None = None,
) -> dict[str, object]:
    is_n9 = player_count == 9
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": EXPERIMENT_MANIFEST_TYPE,
        "manifest_id": f"a{player_count}-preflight",
        "code_identity": {
            "git_commit": _COMMIT,
            "workspace_state": "clean",
            "trainer_version": "candidate-a-preflight-v1",
        },
        "game": {
            "id": "m8-unique-rank-single-open",
            "version": "m8-a-v1",
            "player_count": player_count,
        },
        "execution": (
            {"kind": "n9-boundary-sample", "iteration": 1, "traverser": 4, "master_seed": 9}
            if is_n9
            else {
                "kind": "a6-a7-training",
                "iterations": 1,
                "average_strategy_start_iteration": 1,
                "master_seed": 6,
            }
        ),
        "quality": (
            {"profile_mode": "not-requested", "probe_manifest": None}
            if is_n9
            else {"profile_mode": "full-chance", "probe_manifest": probe_reference}
        ),
        "budget": {
            "cpu_limit_milliseconds": 1000,
            "max_concurrency": 1,
            "rss_warning_bytes": 100,
            "rss_hard_limit_bytes": 200,
            "retained_artifact_limit_bytes": 4096,
            "stages": (
                [
                    {"name": "boundary", "wall_time_milliseconds": 100},
                    {"name": "measurement", "wall_time_milliseconds": 100},
                ]
                if is_n9
                else [
                    {"name": "training", "wall_time_milliseconds": 100},
                    {"name": "export", "wall_time_milliseconds": 100},
                    {"name": "profile", "wall_time_milliseconds": 100},
                    {"name": "probe", "wall_time_milliseconds": 100},
                    {"name": "measurement", "wall_time_milliseconds": 100},
                ]
            ),
        },
        "artifacts": {
            "strategy": None
            if is_n9
            else {"relative_name": "strategy.json", "maximum_bytes": 1024},
            "measurement": {"relative_name": "measurement.json", "maximum_bytes": 1024},
        },
    }


def test_canonical_manifests_round_trip_and_uniquely_derive_a6_plan(tmp_path: Path) -> None:
    probe = create_probe_manifest(_probe_payload())
    loaded_probe = write_probe_manifest(tmp_path, "probes.json", probe)
    experiment = create_experiment_manifest(
        _experiment_payload(probe_reference=loaded_probe.identity.as_payload())
    )
    loaded_experiment = write_experiment_manifest(tmp_path, "experiment.json", experiment)

    plan = derive_experiment_plan(loaded_experiment, load_probe_manifest(tmp_path / "probes.json"))

    assert load_experiment_manifest(tmp_path / "experiment.json") == loaded_experiment
    assert plan.training_config is not None
    assert plan.training_config.average_strategy_start_iteration == 1
    assert plan.probe_manifest is not None
    assert plan.probe_manifest.identity == loaded_probe.identity


def test_manifest_rejects_unfrozen_or_inconsistent_n9_and_probe_configurations() -> None:
    dirty = _experiment_payload()
    dirty["code_identity"]["workspace_state"] = "dirty"
    with pytest.raises(ManifestError):
        create_experiment_manifest(dirty)

    n9 = _experiment_payload(player_count=9)
    n9["artifacts"]["strategy"] = {"relative_name": "strategy.json", "maximum_bytes": 1}
    with pytest.raises(ManifestError):
        create_experiment_manifest(n9)

    unordered = _probe_payload()
    unordered["probes"] = list(reversed(unordered["probes"]))
    with pytest.raises(ManifestError):
        create_probe_manifest(unordered)


def test_manifest_rejects_noncanonical_files_and_mismatched_probe_reference(tmp_path: Path) -> None:
    probe = create_probe_manifest(_probe_payload())
    actual_probe = write_probe_manifest(tmp_path, "probes.json", probe)
    experiment_payload = _experiment_payload(probe_reference=actual_probe.identity.as_payload())
    experiment_payload["quality"]["probe_manifest"]["sha256"] = "0" * 64
    experiment = create_experiment_manifest(experiment_payload)
    loaded_experiment = write_experiment_manifest(tmp_path, "experiment.json", experiment)

    with pytest.raises(ManifestError):
        derive_experiment_plan(loaded_experiment, actual_probe)

    pretty = tmp_path / "pretty.json"
    pretty.write_text(str(deepcopy(experiment_payload)), encoding="utf-8")
    with pytest.raises(ManifestError):
        load_experiment_manifest(pretty)
