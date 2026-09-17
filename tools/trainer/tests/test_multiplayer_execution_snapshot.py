from pathlib import Path

import pytest

from multiplayer_cfr.execution_snapshot import (
    ExecutionSnapshotError,
    create_execution_snapshot,
    verify_experiment_snapshot,
)
from multiplayer_cfr.manifest import (
    EXPERIMENT_MANIFEST_TYPE,
    MANIFEST_SCHEMA_VERSION,
    create_experiment_manifest,
    write_experiment_manifest,
)

_COMMIT = "7" * 40


def _experiment_payload() -> dict[str, object]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": EXPERIMENT_MANIFEST_TYPE,
        "manifest_id": "n9-snapshot",
        "code_identity": {
            "git_commit": _COMMIT,
            "workspace_state": "clean",
            "trainer_version": "candidate-a-snapshot-v1",
        },
        "game": {"id": "m8-unique-rank-single-open", "version": "m8-a-v1", "player_count": 9},
        "execution": {
            "kind": "n9-boundary-sample",
            "iteration": 1,
            "traverser": 0,
            "master_seed": 9,
        },
        "quality": {"profile_mode": "not-requested", "probe_manifest": None},
        "budget": {
            "cpu_limit_milliseconds": 100,
            "max_concurrency": 1,
            "rss_warning_bytes": 100,
            "rss_hard_limit_bytes": 200,
            "retained_artifact_limit_bytes": 1000,
            "stages": [
                {"name": "boundary", "wall_time_milliseconds": 100},
                {"name": "measurement", "wall_time_milliseconds": 100},
            ],
        },
        "artifacts": {
            "strategy": None,
            "measurement": {"relative_name": "measurement.json", "maximum_bytes": 500},
        },
    }


def test_execution_snapshot_remains_valid_after_source_manifest_is_replaced(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    snapshot_root = tmp_path / "snapshot"
    source_root.mkdir()
    snapshot_root.mkdir()
    manifest = create_experiment_manifest(_experiment_payload())
    source_path = source_root / "experiment.json"
    source = write_experiment_manifest(source_root, source_path.name, manifest)

    document = create_experiment_manifest(_experiment_payload())
    snapshot = create_execution_snapshot(snapshot_root, document, None)
    source_path.unlink()
    source_path.write_text("{}\n", encoding="utf-8")

    verified = verify_experiment_snapshot(snapshot.experiment_path, snapshot.experiment_identity)

    assert verified.identity == source.identity
    assert snapshot.experiment_path.read_bytes() != source_path.read_bytes()


def test_execution_snapshot_rejects_identity_mismatch_before_plan_derivation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    manifest = create_experiment_manifest(_experiment_payload())
    snapshot = create_execution_snapshot(root, manifest, None)
    snapshot.experiment_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ExecutionSnapshotError):
        verify_experiment_snapshot(snapshot.experiment_path, snapshot.experiment_identity)
