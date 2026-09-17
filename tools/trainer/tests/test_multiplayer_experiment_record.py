from collections import deque
from pathlib import Path

import pytest

from multiplayer_cfr.control import RunLimits, run_controlled_training, run_n9_boundary_sample
from multiplayer_cfr.experiment_record import (
    ExperimentRecordError,
    SupervisorIdentity,
    build_manifested_measurement_record,
    load_manifested_measurement_record,
    write_manifested_measurement_record,
)
from multiplayer_cfr.manifest import (
    EXPERIMENT_MANIFEST_TYPE,
    MANIFEST_SCHEMA_VERSION,
    create_experiment_manifest,
    derive_experiment_plan,
)
from multiplayer_cfr.policy import export_strategy, load_quantized_strategy

_COMMIT = "2" * 40


def _reader(values: list[int]):
    pending = deque(values)

    def read() -> int:
        return pending.popleft() if pending else values[-1]

    return read


def _plan(*, player_count: int) -> object:
    is_n9 = player_count == 9
    manifest = create_experiment_manifest(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "manifest_type": EXPERIMENT_MANIFEST_TYPE,
            "manifest_id": f"a{player_count}-record",
            "code_identity": {
                "git_commit": _COMMIT,
                "workspace_state": "clean",
                "trainer_version": "candidate-a-record-v1",
            },
            "game": {
                "id": "m8-unique-rank-single-open",
                "version": "m8-a-v1",
                "player_count": player_count,
            },
            "execution": (
                {"kind": "n9-boundary-sample", "iteration": 1, "traverser": 0, "master_seed": 9}
                if is_n9
                else {
                    "kind": "a6-a7-training",
                    "iterations": 1,
                    "average_strategy_start_iteration": 1,
                    "master_seed": 6,
                }
            ),
            "quality": {"profile_mode": "not-requested", "probe_manifest": None},
            "budget": {
                "cpu_limit_milliseconds": 1000,
                "max_concurrency": 1,
                "rss_warning_bytes": 100,
                "rss_hard_limit_bytes": 200,
                "retained_artifact_limit_bytes": 4_000_000,
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
                "strategy": (
                    None
                    if is_n9
                    else {"relative_name": "strategy.json", "maximum_bytes": 3_000_000}
                ),
                "measurement": {"relative_name": "measurement.json", "maximum_bytes": 1_000_000},
            },
        }
    ).value
    return derive_experiment_plan(manifest, None)


def _limits() -> RunLimits:
    return RunLimits(
        stage="training",
        wall_time_seconds=10.0,
        rss_warning_bytes=100,
        rss_hard_limit_bytes=200,
        retained_artifact_limit_bytes=4096,
    )


def _supervisor() -> SupervisorIdentity:
    return SupervisorIdentity(
        supervisor_id="local-supervisor",
        supervisor_version="v1",
        rss_scope="process-tree",
        enforcement_mode="external-hard-limit",
    )


def test_builder_mechanically_binds_manifest_training_receipt_and_quantized_strategy(
    tmp_path: Path,
) -> None:
    plan = _plan(player_count=6)
    assert plan.training_config is not None
    training = run_controlled_training(
        plan.training_config,
        _limits(),
        monotonic_clock=_reader([0, 0, 0]),
        rss_reader=_reader([0, 0]),
        rss_sampler_id="test-rss-v1",
    )
    assert training.result is not None
    strategy_path = tmp_path / "strategy.json"
    export_strategy(strategy_path, training.result, trainer_version=plan.manifest.trainer_version)
    artifact = load_quantized_strategy(strategy_path)

    record = build_manifested_measurement_record(
        plan=plan,
        supervisor=_supervisor(),
        training=training,
        artifact=artifact,
    )
    written = write_manifested_measurement_record(
        tmp_path,
        "measurement.json",
        record,
        maximum_bytes=1_000_000,
    )

    assert load_manifested_measurement_record(tmp_path / "measurement.json") == written
    assert written.payload["strategy"]["sha256"] == artifact.identity.sha256
    assert written.payload["experiment_manifest"] == plan.manifest.identity.as_payload()


def test_builder_allows_completed_n9_boundary_only_without_strategy_or_quality() -> None:
    plan = _plan(player_count=9)
    boundary = run_n9_boundary_sample(
        master_seed=plan.manifest.master_seed,
        traverser=plan.manifest.n9_traverser or 0,
        limits=RunLimits(
            stage="boundary",
            wall_time_seconds=10.0,
            rss_warning_bytes=100,
            rss_hard_limit_bytes=200,
            retained_artifact_limit_bytes=4096,
        ),
        monotonic_clock=_reader([0, 0, 0]),
        rss_reader=_reader([0, 0]),
        rss_sampler_id="test-rss-v1",
    )

    record = build_manifested_measurement_record(
        plan=plan, supervisor=_supervisor(), boundary=boundary
    )

    assert record.payload["execution"]["plan_kind"] == "n9-boundary-sample"
    assert record.payload["strategy"] is None
    assert record.payload["profile"] is None
    assert record.payload["probes"] is None


def test_builder_rejects_manual_cross_plan_strategy_binding(tmp_path: Path) -> None:
    plan = _plan(player_count=6)
    assert plan.training_config is not None
    training = run_controlled_training(
        plan.training_config,
        _limits(),
        monotonic_clock=_reader([0, 0, 0]),
        rss_reader=_reader([0, 0]),
        rss_sampler_id="test-rss-v1",
    )
    assert training.result is not None
    path = tmp_path / "strategy.json"
    export_strategy(path, training.result, trainer_version=plan.manifest.trainer_version)
    artifact = load_quantized_strategy(path)

    with pytest.raises(ExperimentRecordError):
        build_manifested_measurement_record(
            plan=_plan(player_count=7),
            supervisor=_supervisor(),
            training=training,
            artifact=artifact,
        )
