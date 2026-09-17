import subprocess
from pathlib import Path

import pytest

from multiplayer_cfr import campaign_executor
from multiplayer_cfr.campaign import (
    CAMPAIGN_SCHEMA_VERSION,
    CAMPAIGN_TYPE,
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
                "code_identity": {"git_commit": commit, "trainer_version": _VERSION},
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
    attestation_identity: dict[str, object],
    experiment_identity: dict[str, object],
    *,
    peak_rss_limit_bytes: int = 256 * 1024 * 1024,
) -> dict[str, object]:
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "record_type": CAMPAIGN_TYPE,
        "campaign_id": "n9-campaign",
        "code_identity": {"git_commit": commit, "trainer_version": _VERSION},
        "preflight_attestation": attestation_identity,
        "limits": {
            "cpu_limit_milliseconds": 10_000,
            "wall_limit_milliseconds": 10_000,
            "peak_rss_limit_bytes": peak_rss_limit_bytes,
            "retained_artifact_limit_bytes": 1_000_000,
            "max_concurrency": 1,
        },
        "authorizations": [
            {
                "authorization_id": "n9-boundary-1",
                "experiment_manifest": experiment_identity,
                "cpu_reservation_milliseconds": 10_000,
                "wall_reservation_milliseconds": 10_000,
                "artifact_reservation_bytes": 1_000_000,
            }
        ],
    }


def test_campaign_executor_uses_single_lease_and_parent_final_measurement(
    tmp_path: Path,
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
    spec_path, attestation_path = _preflight_files(source_root, commit)
    campaign = create_campaign_manifest(
        _campaign_payload(
            commit,
            load_attestation(attestation_path).identity.as_payload(),
            experiment.identity.as_payload(),
        )
    )

    result = campaign_executor.run_campaign_authorization(
        campaign_root=campaign_root,
        campaign=campaign,
        authorization_id="n9-boundary-1",
        experiment_manifest_path=source_root / "experiment.json",
        preflight_spec_path=spec_path,
        preflight_attestation_path=attestation_path,
        working_directory=worktree,
        runtime_git_commit=commit,
        runtime_trainer_version=_VERSION,
    )

    assert result.result.measurement_path.is_file()
    assert (campaign_root / "campaign-ledger.json").is_file()
    assert (campaign_root / "runs" / "n9-boundary-1" / "inputs" / "experiment.json").is_file()


def test_campaign_executor_rejects_experiment_rss_above_campaign_envelope(
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    source_root = tmp_path / "source"
    campaign_root = tmp_path / "campaign"
    source_root.mkdir()
    campaign_root.mkdir()
    experiment = write_experiment_manifest(
        source_root, "experiment.json", create_experiment_manifest(_experiment_payload(commit))
    )
    spec_path, attestation_path = _preflight_files(source_root, commit)
    campaign = create_campaign_manifest(
        _campaign_payload(
            commit,
            load_attestation(attestation_path).identity.as_payload(),
            experiment.identity.as_payload(),
            peak_rss_limit_bytes=1024,
        )
    )

    with pytest.raises(campaign_executor.CampaignExecutorError):
        campaign_executor.run_campaign_authorization(
            campaign_root=campaign_root,
            campaign=campaign,
            authorization_id="n9-boundary-1",
            experiment_manifest_path=source_root / "experiment.json",
            preflight_spec_path=spec_path,
            preflight_attestation_path=attestation_path,
            working_directory=tmp_path,
            runtime_git_commit=commit,
            runtime_trainer_version=_VERSION,
        )

    assert not (campaign_root / "runs").exists()
