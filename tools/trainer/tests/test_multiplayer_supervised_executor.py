from pathlib import Path

import pytest

from multiplayer_cfr.manifest import (
    EXPERIMENT_MANIFEST_TYPE,
    MANIFEST_SCHEMA_VERSION,
    create_experiment_manifest,
    write_experiment_manifest,
)
from multiplayer_cfr.supervised_executor import (
    SupervisedExecutorError,
    run_supervised_manifest_executor,
)
from multiplayer_cfr.supervised_measurement import (
    SUPERVISED_MEASUREMENT_TYPE,
    load_supervised_measurement,
)
from multiplayer_cfr.supervisor import SupervisorStatus

_COMMIT = "4" * 40
_TRAINER_VERSION = "candidate-a-supervised-v1"


def _n9_manifest() -> dict[str, object]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": EXPERIMENT_MANIFEST_TYPE,
        "manifest_id": "n9-supervised-boundary",
        "code_identity": {
            "git_commit": _COMMIT,
            "workspace_state": "clean",
            "trainer_version": _TRAINER_VERSION,
        },
        "game": {
            "id": "m8-unique-rank-single-open",
            "version": "m8-a-v1",
            "player_count": 9,
        },
        "execution": {
            "kind": "n9-boundary-sample",
            "iteration": 1,
            "traverser": 3,
            "master_seed": 91,
        },
        "quality": {"profile_mode": "not-requested", "probe_manifest": None},
        "budget": {
            "cpu_limit_milliseconds": 10_000,
            "max_concurrency": 1,
            "rss_warning_bytes": 128 * 1024 * 1024,
            "rss_hard_limit_bytes": 256 * 1024 * 1024,
            "retained_artifact_limit_bytes": 1_000_000,
            "stages": [
                {"name": "boundary", "wall_time_milliseconds": 2_000},
                {"name": "measurement", "wall_time_milliseconds": 1_000},
            ],
        },
        "artifacts": {
            "strategy": None,
            "measurement": {"relative_name": "measurement.json", "maximum_bytes": 500_000},
        },
    }


def test_parent_supervisor_replaces_child_measurement_after_n9_boundary(tmp_path: Path) -> None:
    manifest_root = tmp_path / "manifests"
    artifact_root = tmp_path / "artifacts"
    manifest_root.mkdir()
    artifact_root.mkdir()
    experiment_path = manifest_root / "experiment.json"
    write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(_n9_manifest()),
    )

    result = run_supervised_manifest_executor(
        experiment_manifest_path=experiment_path,
        artifact_root=artifact_root,
        working_directory=Path(__file__).parents[1],
        runtime_git_commit=_COMMIT,
        runtime_trainer_version=_TRAINER_VERSION,
    )

    final = load_supervised_measurement(result.measurement_path)
    assert result.receipt.status is SupervisorStatus.COMPLETED
    assert final.payload["record_type"] == SUPERVISED_MEASUREMENT_TYPE
    assert final.payload["child_execution"] is not None
    assert final.payload["strategy"] is None
    assert sorted(path.name for path in artifact_root.iterdir()) == ["measurement.json"]


def test_parent_rejects_runtime_identity_before_starting_child(tmp_path: Path) -> None:
    manifest_root = tmp_path / "manifests"
    artifact_root = tmp_path / "artifacts"
    manifest_root.mkdir()
    artifact_root.mkdir()
    experiment_path = manifest_root / "experiment.json"
    write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(_n9_manifest()),
    )

    with pytest.raises(SupervisedExecutorError):
        run_supervised_manifest_executor(
            experiment_manifest_path=experiment_path,
            artifact_root=artifact_root,
            working_directory=Path(__file__).parents[1],
            runtime_git_commit="0" * 40,
            runtime_trainer_version=_TRAINER_VERSION,
        )

    assert list(artifact_root.iterdir()) == []
