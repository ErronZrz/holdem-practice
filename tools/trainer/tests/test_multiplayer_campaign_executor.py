import subprocess
from pathlib import Path

from multiplayer_cfr import campaign_executor
from multiplayer_cfr.campaign import (
    CAMPAIGN_SCHEMA_VERSION,
    CAMPAIGN_TYPE,
    create_campaign_manifest,
)
from multiplayer_cfr.estimator_preflight import (
    PREFLIGHT_ATTESTATION_TYPE,
    EstimatorAttestation,
    PreflightIdentity,
)
from multiplayer_cfr.manifest import (
    EXPERIMENT_MANIFEST_TYPE,
    MANIFEST_SCHEMA_VERSION,
    create_experiment_manifest,
    write_experiment_manifest,
)

_VERSION = "candidate-a-campaign-executor-v1"


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


def _experiment_payload(commit: str, *, cpu_limit_milliseconds: int = 10_000) -> dict[str, object]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": EXPERIMENT_MANIFEST_TYPE,
        "manifest_id": "n9-campaign-boundary",
        "code_identity": {
            "git_commit": commit,
            "workspace_state": "clean",
            "trainer_version": _VERSION,
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
            "cpu_limit_milliseconds": cpu_limit_milliseconds,
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


def _attestation(commit: str) -> EstimatorAttestation:
    identity = PreflightIdentity(
        record_type=PREFLIGHT_ATTESTATION_TYPE,
        schema_version=1,
        record_id="n6-preflight",
        sha256="c" * 64,
        byte_length=300,
    )
    return EstimatorAttestation(
        payload={
            "passed": True,
            "code_identity": {"git_commit": commit, "trainer_version": _VERSION},
            "preflight_manifest": {
                "record_type": "multiplayer-cfr-estimator-preflight",
                "schema_version": 1,
                "record_id": "n6-preflight-spec",
                "sha256": "d" * 64,
                "byte_length": 200,
            },
            "sample_seeds": list(range(8)),
            "target_infosets": [],
            "regret_tolerance_micros": 1,
            "strategy_sum_tolerance_micros": 1,
        },
        identity=identity,
    )


def test_campaign_executor_uses_single_lease_and_parent_final_measurement(
    tmp_path: Path, monkeypatch
) -> None:
    worktree, commit = _clean_worktree(tmp_path)
    source_root = tmp_path / "source"
    campaign_root = tmp_path / "campaign"
    source_root.mkdir()
    campaign_root.mkdir()
    experiment = write_experiment_manifest(
        source_root,
        "experiment.json",
        create_experiment_manifest(_experiment_payload(commit)),
    )
    attestation = _attestation(commit)
    campaign = create_campaign_manifest(
        {
            "schema_version": CAMPAIGN_SCHEMA_VERSION,
            "record_type": CAMPAIGN_TYPE,
            "campaign_id": "n9-campaign",
            "code_identity": {"git_commit": commit, "trainer_version": _VERSION},
            "preflight_attestation": attestation.identity.as_payload(),
            "limits": {
                "cpu_limit_milliseconds": 10_000,
                "wall_limit_milliseconds": 10_000,
                "peak_rss_limit_bytes": 256 * 1024 * 1024,
                "retained_artifact_limit_bytes": 1_000_000,
                "max_concurrency": 1,
            },
            "authorizations": [
                {
                    "authorization_id": "n9-boundary-1",
                    "experiment_manifest": experiment.identity.as_payload(),
                    "cpu_reservation_milliseconds": 10_000,
                    "wall_reservation_milliseconds": 10_000,
                    "artifact_reservation_bytes": 1_000_000,
                }
            ],
        }
    )
    monkeypatch.setattr(campaign_executor, "verify_attestation", lambda *_: None)

    result = campaign_executor.run_campaign_authorization(
        campaign_root=campaign_root,
        campaign=campaign,
        preflight_attestation=attestation,
        authorization_id="n9-boundary-1",
        experiment_manifest_path=source_root / "experiment.json",
        working_directory=worktree,
        runtime_git_commit=commit,
        runtime_trainer_version=_VERSION,
    )

    assert result.result.measurement_path.is_file()
    assert (campaign_root / "campaign-ledger.json").is_file()
    assert (campaign_root / "runs" / "n9-boundary-1" / "inputs" / "experiment.json").is_file()
