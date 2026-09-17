import subprocess
from copy import deepcopy
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

_TRAINER_VERSION = "candidate-a-supervised-v1"


def _clean_worktree(tmp_path: Path) -> tuple[Path, str]:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    environment = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_AUTHOR_NAME": "CodeBuddy Test",
        "GIT_AUTHOR_EMAIL": "codebuddy@example.invalid",
        "GIT_COMMITTER_NAME": "CodeBuddy Test",
        "GIT_COMMITTER_EMAIL": "codebuddy@example.invalid",
    }
    for arguments in (
        ("/usr/bin/git", "-C", str(worktree), "init"),
        ("/usr/bin/git", "-C", str(worktree), "commit", "--allow-empty", "-m", "fixture"),
    ):
        subprocess.run(arguments, check=True, capture_output=True, env=environment)
    result = subprocess.run(
        ("/usr/bin/git", "-C", str(worktree), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
    )
    return worktree, result.stdout.strip()


def _n9_manifest(commit: str) -> dict[str, object]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": EXPERIMENT_MANIFEST_TYPE,
        "manifest_id": "n9-supervised-boundary",
        "code_identity": {
            "git_commit": commit,
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
    worktree, commit = _clean_worktree(tmp_path)
    manifest_root = tmp_path / "manifests"
    artifact_root = tmp_path / "artifacts"
    manifest_root.mkdir()
    artifact_root.mkdir()
    (tmp_path / "snapshots").mkdir()
    experiment_path = manifest_root / "experiment.json"
    write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(_n9_manifest(commit)),
    )

    result = run_supervised_manifest_executor(
        experiment_manifest_path=experiment_path,
        artifact_root=artifact_root,
        execution_snapshot_root=tmp_path / "snapshots",
        working_directory=worktree,
        runtime_git_commit=commit,
        runtime_trainer_version=_TRAINER_VERSION,
    )

    final = load_supervised_measurement(result.measurement_path)
    assert result.receipt.status is SupervisorStatus.COMPLETED
    assert final.payload["record_type"] == SUPERVISED_MEASUREMENT_TYPE
    assert final.payload["child_execution"] is not None
    assert final.payload["strategy"] is None
    assert (
        final.payload["execution_snapshots"]["experiment"]
        == result.snapshot.experiment_identity.as_payload()
    )
    assert final.payload["pre_final_inventory"][0]["relative_name"] == "measurement.json"
    assert [entry.relative_name for entry in result.final_inventory] == ["measurement.json"]
    assert sorted(path.name for path in artifact_root.iterdir()) == ["measurement.json"]


def test_parent_rejects_a6_execution_without_campaign_authorization(tmp_path: Path) -> None:
    worktree, commit = _clean_worktree(tmp_path)
    manifest_root = tmp_path / "manifests"
    artifact_root = tmp_path / "artifacts"
    manifest_root.mkdir()
    artifact_root.mkdir()
    (tmp_path / "snapshots").mkdir()
    payload = deepcopy(_n9_manifest(commit))
    payload["manifest_id"] = "a6-supervised-training"
    payload["game"]["player_count"] = 6
    payload["execution"] = {
        "kind": "a6-a7-training",
        "iterations": 1,
        "average_strategy_start_iteration": 1,
        "master_seed": 6,
    }
    payload["budget"]["retained_artifact_limit_bytes"] = 3_000
    payload["budget"]["stages"] = [
        {"name": "training", "wall_time_milliseconds": 100},
        {"name": "export", "wall_time_milliseconds": 100},
        {"name": "profile", "wall_time_milliseconds": 100},
        {"name": "probe", "wall_time_milliseconds": 100},
        {"name": "measurement", "wall_time_milliseconds": 100},
    ]
    payload["artifacts"] = {
        "strategy": {"relative_name": "strategy.json", "maximum_bytes": 1_000},
        "measurement": {"relative_name": "measurement.json", "maximum_bytes": 1_000},
    }
    experiment_path = manifest_root / "experiment.json"
    write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(payload),
    )

    with pytest.raises(SupervisedExecutorError):
        run_supervised_manifest_executor(
            experiment_manifest_path=experiment_path,
            artifact_root=artifact_root,
            execution_snapshot_root=tmp_path / "snapshots",
            working_directory=worktree,
            runtime_git_commit=commit,
            runtime_trainer_version=_TRAINER_VERSION,
        )

    assert list(artifact_root.iterdir()) == []


def test_parent_rejects_runtime_identity_before_starting_child(tmp_path: Path) -> None:
    worktree, commit = _clean_worktree(tmp_path)
    manifest_root = tmp_path / "manifests"
    artifact_root = tmp_path / "artifacts"
    manifest_root.mkdir()
    artifact_root.mkdir()
    (tmp_path / "snapshots").mkdir()
    experiment_path = manifest_root / "experiment.json"
    write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(_n9_manifest(commit)),
    )

    with pytest.raises(SupervisedExecutorError):
        run_supervised_manifest_executor(
            experiment_manifest_path=experiment_path,
            artifact_root=artifact_root,
            execution_snapshot_root=tmp_path / "snapshots",
            working_directory=worktree,
            runtime_git_commit="0" * 40,
            runtime_trainer_version=_TRAINER_VERSION,
        )

    assert list(artifact_root.iterdir()) == []
