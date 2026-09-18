import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from multiplayer_cfr.campaign import (
    CAMPAIGN_SCHEMA_VERSION,
    CAMPAIGN_TYPE,
    acquire_campaign_lease,
    create_campaign_manifest,
)
from multiplayer_cfr.estimator_preflight import (
    PREFLIGHT_MANIFEST_TYPE,
    PREFLIGHT_SCHEMA_VERSION,
    create_preflight_spec,
    load_attestation,
    load_preflight_spec,
    run_preflight,
    write_attestation,
    write_preflight_spec,
)
from multiplayer_cfr.game import information_set_key
from multiplayer_cfr.manifest import (
    EVALUATOR_ID,
    EVALUATOR_VERSION,
    EXPERIMENT_MANIFEST_TYPE,
    MANIFEST_SCHEMA_VERSION,
    PROBE_MANIFEST_TYPE,
    create_experiment_manifest,
    create_probe_manifest,
    write_experiment_manifest,
    write_probe_manifest,
)
from multiplayer_cfr.policy import PROBABILITY_UNITS
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


def _a6_manifest(commit: str) -> dict[str, object]:
    payload = deepcopy(_n9_manifest(commit))
    payload["manifest_id"] = "a6-supervised-training"
    payload["game"]["player_count"] = 6
    payload["execution"] = {
        "kind": "a6-a7-training",
        "iterations": 1,
        "average_strategy_start_iteration": 1,
        "master_seed": 6,
    }
    payload["budget"]["cpu_limit_milliseconds"] = 120_000
    payload["budget"]["rss_warning_bytes"] = 256 * 1024 * 1024
    payload["budget"]["rss_hard_limit_bytes"] = 512 * 1024 * 1024
    payload["budget"]["retained_artifact_limit_bytes"] = 5_000_000
    payload["budget"]["stages"] = [
        {"name": name, "wall_time_milliseconds": 60_000}
        for name in ("training", "export", "profile", "probe", "measurement")
    ]
    payload["artifacts"] = {
        "strategy": {"relative_name": "strategy.json", "maximum_bytes": 3_000_000},
        "measurement": {"relative_name": "measurement.json", "maximum_bytes": 1_000_000},
    }
    return payload


def _a6_probe_manifest(player_count: int) -> dict[str, object]:
    """两组预注册阈值策略，按 probe_id 升序排列。"""

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": PROBE_MANIFEST_TYPE,
        "manifest_id": "a6-probe-tight-loose",
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
            {"probe_id": "loose-open", "open_threshold": 1, "call_threshold": 0},
            {"probe_id": "tight-open", "open_threshold": 4, "call_threshold": 3},
        ],
    }


def _a6_manifest_with_probes(commit: str, probe_identity: dict[str, object]) -> dict[str, object]:
    """引用真实 probe 的计划必须用 full-chance profile，并按实测锚点放宽质量阶段预算。"""

    payload = _a6_manifest(commit)
    payload["quality"] = {"profile_mode": "full-chance", "probe_manifest": probe_identity}
    payload["budget"]["cpu_limit_milliseconds"] = 1_140_000
    payload["budget"]["stages"] = [
        {"name": name, "wall_time_milliseconds": wall_time}
        for name, wall_time in (
            ("training", 600_000),
            ("export", 60_000),
            ("profile", 120_000),
            ("probe", 300_000),
            ("measurement", 60_000),
        )
    ]
    return payload


def _preflight_files(root: Path, commit: str) -> tuple[Path, Path]:
    """写入可复演的冻结 preflight spec 与 attestation 文件，供 campaign 引用。"""

    spec_name = "preflight-spec.json"
    attestation_name = "preflight-attestation.json"
    write_preflight_spec(
        root,
        spec_name,
        create_preflight_spec(
            {
                "schema_version": PREFLIGHT_SCHEMA_VERSION,
                "record_type": PREFLIGHT_MANIFEST_TYPE,
                "record_id": "n6-estimator-preflight",
                "code_identity": {"git_commit": commit, "trainer_version": _TRAINER_VERSION},
                "fixture_id": "three-to-one-regret-v1",
                "sample_seeds": list(range(8)),
                "target_infosets": sorted(
                    [
                        information_set_key(6, 0, 3, "-"),
                        information_set_key(6, 1, 3, "b@0"),
                        information_set_key(6, 2, 3, "b@0|c@1"),
                    ]
                ),
                "regret_tolerance_micros": 1_000_000,
                "strategy_sum_tolerance_micros": 1_000_000,
            }
        ),
    )
    write_attestation(
        root, attestation_name, run_preflight(load_preflight_spec(root / spec_name))
    )
    return root / spec_name, root / attestation_name


def _campaign_payload(
    commit: str,
    experiment_identity: dict[str, object],
    preflight_identity: dict[str, object],
    *,
    campaign_id: str = "n9-lease-campaign",
    authorization_id: str = "n9-lease-1",
    cpu_milliseconds: int = 10_000,
    wall_milliseconds: int = 10_000,
    retained_artifact_bytes: int = 1_000_000,
    peak_rss_limit_bytes: int = 256 * 1024 * 1024,
) -> dict[str, object]:
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "record_type": CAMPAIGN_TYPE,
        "campaign_id": campaign_id,
        "code_identity": {"git_commit": commit, "trainer_version": _TRAINER_VERSION},
        "preflight_attestation": preflight_identity,
        "limits": {
            "cpu_limit_milliseconds": cpu_milliseconds,
            "wall_limit_milliseconds": wall_milliseconds,
            "peak_rss_limit_bytes": peak_rss_limit_bytes,
            "retained_artifact_limit_bytes": retained_artifact_bytes,
            "max_concurrency": 1,
        },
        "authorizations": [
            {
                "authorization_id": authorization_id,
                "experiment_manifest": experiment_identity,
                "cpu_reservation_milliseconds": cpu_milliseconds,
                "wall_reservation_milliseconds": wall_milliseconds,
                "artifact_reservation_bytes": retained_artifact_bytes,
            }
        ],
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


def test_parent_rejects_lease_bound_to_another_experiment(tmp_path: Path) -> None:
    commit = "a" * 40
    manifest_root = tmp_path / "manifests"
    campaign_root = tmp_path / "campaign"
    manifest_root.mkdir()
    campaign_root.mkdir()
    experiment_path = manifest_root / "experiment.json"
    write_experiment_manifest(
        manifest_root, experiment_path.name, create_experiment_manifest(_n9_manifest(commit))
    )
    spec_path, attestation_path = _preflight_files(manifest_root, commit)
    campaign = create_campaign_manifest(
        _campaign_payload(
            commit,
            {
                "manifest_type": "multiplayer-cfr-experiment",
                "schema_version": 1,
                "manifest_id": "other-experiment",
                "sha256": "b" * 64,
                "byte_length": 100,
            },
            load_attestation(attestation_path).identity.as_payload(),
        )
    )

    with acquire_campaign_lease(campaign_root, campaign, "n9-lease-1") as lease:
        _, artifact_root, snapshot_root = lease.create_run_directories()

        with pytest.raises(SupervisedExecutorError):
            run_supervised_manifest_executor(
                experiment_manifest_path=experiment_path,
                artifact_root=artifact_root,
                execution_snapshot_root=snapshot_root,
                working_directory=tmp_path,
                runtime_git_commit=commit,
                runtime_trainer_version=_TRAINER_VERSION,
                campaign_lease=lease,
                preflight_spec_path=spec_path,
                preflight_attestation_path=attestation_path,
            )

        assert list(artifact_root.iterdir()) == []
        assert list(snapshot_root.iterdir()) == []


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


def test_parent_runs_a6_training_under_campaign_lease(tmp_path: Path) -> None:
    worktree, commit = _clean_worktree(tmp_path)
    manifest_root = tmp_path / "manifests"
    campaign_root = tmp_path / "campaign"
    manifest_root.mkdir()
    campaign_root.mkdir()
    experiment_path = manifest_root / "experiment.json"
    experiment = write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(_a6_manifest(commit)),
    )
    spec_path, attestation_path = _preflight_files(manifest_root, commit)
    campaign = create_campaign_manifest(
        _campaign_payload(
            commit,
            experiment.identity.as_payload(),
            load_attestation(attestation_path).identity.as_payload(),
            campaign_id="a6-lease-campaign",
            authorization_id="a6-lease-1",
            cpu_milliseconds=120_000,
            wall_milliseconds=300_000,
            retained_artifact_bytes=5_000_000,
            peak_rss_limit_bytes=512 * 1024 * 1024,
        )
    )

    with acquire_campaign_lease(campaign_root, campaign, "a6-lease-1") as lease:
        _, artifact_root, snapshot_root = lease.create_run_directories()
        result = run_supervised_manifest_executor(
            experiment_manifest_path=experiment_path,
            artifact_root=artifact_root,
            execution_snapshot_root=snapshot_root,
            working_directory=worktree,
            runtime_git_commit=commit,
            runtime_trainer_version=_TRAINER_VERSION,
            campaign_lease=lease,
            preflight_spec_path=spec_path,
            preflight_attestation_path=attestation_path,
        )
        lease.finalize(
            status=result.receipt.status.value,
            supervisor_receipt_sha256="0" * 64,
            final_measurement_sha256=result.measurement.sha256,
            final_inventory=[entry.as_payload() for entry in result.final_inventory],
        )

    final = load_supervised_measurement(result.measurement_path)
    assert result.receipt.status is SupervisorStatus.COMPLETED
    assert result.strategy_path is not None and result.strategy_path.is_file()
    assert final.payload["strategy"] is not None
    assert final.payload["child_execution"] is not None
    assert [entry.relative_name for entry in result.final_inventory] == [
        "measurement.json",
        "strategy.json",
    ]


def test_parent_rejects_a6_lease_without_preflight_evidence(tmp_path: Path) -> None:
    """持有真实 lease 但省略 preflight 证据时必须在启动子进程前失败。"""

    worktree, commit = _clean_worktree(tmp_path)
    manifest_root = tmp_path / "manifests"
    campaign_root = tmp_path / "campaign"
    manifest_root.mkdir()
    campaign_root.mkdir()
    experiment_path = manifest_root / "experiment.json"
    experiment = write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(_a6_manifest(commit)),
    )
    _preflight_files(manifest_root, commit)
    campaign = create_campaign_manifest(
        _campaign_payload(
            commit,
            experiment.identity.as_payload(),
            load_attestation(manifest_root / "preflight-attestation.json").identity.as_payload(),
            campaign_id="a6-no-preflight-campaign",
            authorization_id="a6-no-preflight",
            cpu_milliseconds=120_000,
            wall_milliseconds=300_000,
            retained_artifact_bytes=5_000_000,
            peak_rss_limit_bytes=512 * 1024 * 1024,
        )
    )

    with acquire_campaign_lease(campaign_root, campaign, "a6-no-preflight") as lease:
        _, artifact_root, snapshot_root = lease.create_run_directories()

        with pytest.raises(SupervisedExecutorError):
            run_supervised_manifest_executor(
                experiment_manifest_path=experiment_path,
                artifact_root=artifact_root,
                execution_snapshot_root=snapshot_root,
                working_directory=worktree,
                runtime_git_commit=commit,
                runtime_trainer_version=_TRAINER_VERSION,
                campaign_lease=lease,
            )

        assert list(artifact_root.iterdir()) == []
        assert list(snapshot_root.iterdir()) == []


def test_parent_rejects_a6_experiment_above_authorization_reservation(tmp_path: Path) -> None:
    """绕过 campaign 授权入口时，父端仍须拒绝超出授权预留的 experiment。"""

    worktree, commit = _clean_worktree(tmp_path)
    manifest_root = tmp_path / "manifests"
    campaign_root = tmp_path / "campaign"
    manifest_root.mkdir()
    campaign_root.mkdir()
    experiment_path = manifest_root / "experiment.json"
    experiment = write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(_a6_manifest(commit)),
    )
    spec_path, attestation_path = _preflight_files(manifest_root, commit)
    campaign = create_campaign_manifest(
        _campaign_payload(
            commit,
            experiment.identity.as_payload(),
            load_attestation(attestation_path).identity.as_payload(),
            campaign_id="a6-underfunded-campaign",
            authorization_id="a6-underfunded",
            cpu_milliseconds=100_000,
            wall_milliseconds=300_000,
            retained_artifact_bytes=5_000_000,
            peak_rss_limit_bytes=512 * 1024 * 1024,
        )
    )

    with acquire_campaign_lease(campaign_root, campaign, "a6-underfunded") as lease:
        _, artifact_root, snapshot_root = lease.create_run_directories()

        with pytest.raises(SupervisedExecutorError):
            run_supervised_manifest_executor(
                experiment_manifest_path=experiment_path,
                artifact_root=artifact_root,
                execution_snapshot_root=snapshot_root,
                working_directory=worktree,
                runtime_git_commit=commit,
                runtime_trainer_version=_TRAINER_VERSION,
                campaign_lease=lease,
                preflight_spec_path=spec_path,
                preflight_attestation_path=attestation_path,
            )

        assert list(artifact_root.iterdir()) == []
        assert list(snapshot_root.iterdir()) == []


def test_parent_rejects_preflight_evidence_on_n9_boundary(tmp_path: Path) -> None:
    """N9 boundary 不接受 campaign preflight 证据，避免把独立采样伪装成授权实验。"""

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
    spec_path, attestation_path = _preflight_files(manifest_root, commit)

    with pytest.raises(SupervisedExecutorError):
        run_supervised_manifest_executor(
            experiment_manifest_path=experiment_path,
            artifact_root=artifact_root,
            execution_snapshot_root=tmp_path / "snapshots",
            working_directory=worktree,
            runtime_git_commit=commit,
            runtime_trainer_version=_TRAINER_VERSION,
            preflight_spec_path=spec_path,
            preflight_attestation_path=attestation_path,
        )

    assert list(artifact_root.iterdir()) == []


def test_parent_runs_a6_with_preregistered_probes_under_campaign_lease(tmp_path: Path) -> None:
    """携带真实 probe manifest 时，父端最终 measurement 必须保留 probe 身份与两种工件。"""

    worktree, commit = _clean_worktree(tmp_path)
    manifest_root = tmp_path / "manifests"
    campaign_root = tmp_path / "campaign"
    manifest_root.mkdir()
    campaign_root.mkdir()
    probe = write_probe_manifest(
        manifest_root,
        "a6-probe.json",
        create_probe_manifest(_a6_probe_manifest(6)),
    )
    experiment_path = manifest_root / "experiment.json"
    experiment = write_experiment_manifest(
        manifest_root,
        experiment_path.name,
        create_experiment_manifest(_a6_manifest_with_probes(commit, probe.identity.as_payload())),
    )
    spec_path, attestation_path = _preflight_files(manifest_root, commit)
    campaign = create_campaign_manifest(
        _campaign_payload(
            commit,
            experiment.identity.as_payload(),
            load_attestation(attestation_path).identity.as_payload(),
            campaign_id="a6-probe-campaign",
            authorization_id="a6-probe-run",
            cpu_milliseconds=1_140_000,
            wall_milliseconds=1_140_000,
            retained_artifact_bytes=5_000_000,
            peak_rss_limit_bytes=512 * 1024 * 1024,
        )
    )

    with acquire_campaign_lease(campaign_root, campaign, "a6-probe-run") as lease:
        _, artifact_root, snapshot_root = lease.create_run_directories()
        result = run_supervised_manifest_executor(
            experiment_manifest_path=experiment_path,
            artifact_root=artifact_root,
            execution_snapshot_root=snapshot_root,
            working_directory=worktree,
            runtime_git_commit=commit,
            runtime_trainer_version=_TRAINER_VERSION,
            campaign_lease=lease,
            preflight_spec_path=spec_path,
            preflight_attestation_path=attestation_path,
            probe_manifest_path=manifest_root / "a6-probe.json",
        )
        lease.finalize(
            status=result.receipt.status.value,
            supervisor_receipt_sha256="0" * 64,
            final_measurement_sha256=result.measurement.sha256,
            final_inventory=[entry.as_payload() for entry in result.final_inventory],
        )

    final = load_supervised_measurement(result.measurement_path)
    assert result.receipt.status is SupervisorStatus.COMPLETED
    assert final.payload["execution_snapshots"]["probe"] == probe.identity.as_payload()
    assert final.payload["child_execution"] is not None
    assert final.payload["child_execution"]["payload"]["probes"] is not None
    assert [entry.relative_name for entry in result.pre_final_inventory] == [
        "measurement.json",
        "strategy.json",
    ]
    assert [entry.relative_name for entry in result.final_inventory] == [
        "measurement.json",
        "strategy.json",
    ]
