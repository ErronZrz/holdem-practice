from collections import deque
from pathlib import Path

import pytest

from multiplayer_cfr.control import RunLimits, run_controlled_training, run_n9_boundary_sample
from multiplayer_cfr.experiment_record import (
    EXPERIMENT_RECORD_SCHEMA_VERSION,
    EXPERIMENT_RECORD_TYPE,
    LEGACY_EXPERIMENT_RECORD_SCHEMA_VERSION,
    MAX_RATIONAL_DIGITS,
    ExperimentRecordError,
    SupervisorIdentity,
    build_manifested_measurement_record,
    load_manifested_measurement_record,
    parse_manifested_measurement_payload,
    write_manifested_measurement_record,
)
from multiplayer_cfr.manifest import (
    EVALUATOR_ID,
    EVALUATOR_VERSION,
    EXPERIMENT_MANIFEST_TYPE,
    MANIFEST_SCHEMA_VERSION,
    create_experiment_manifest,
    derive_experiment_plan,
)
from multiplayer_cfr.policy import (
    ARTIFACT_TYPE,
    PROBABILITY_UNITS,
    export_strategy,
    load_quantized_strategy,
)
from multiplayer_cfr.policy import SCHEMA_VERSION as STRATEGY_SCHEMA_VERSION

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
                "retained_artifact_limit_bytes": 5_000_000,
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


def _synthetic_child_payload(*, numerator: str) -> dict[str, object]:
    """构造结构完整、只把 profile 首位效用换成指定分子的候选 A 子进程记录。"""

    player_count = 6
    strategy_sha256 = "b" * 64
    strategy_bytes = 1234
    utilities = [
        {"numerator": numerator, "denominator": "1"},
        {"numerator": f"-{numerator}", "denominator": "1"},
    ]
    utilities.extend(
        {"numerator": "0", "denominator": "1"} for _ in range(player_count - len(utilities))
    )
    supervisor = {
        "supervisor_id": "local-supervisor",
        "supervisor_version": "v1",
        "rss_scope": "process-tree",
        "enforcement_mode": "external-hard-limit",
    }
    return {
        "schema_version": EXPERIMENT_RECORD_SCHEMA_VERSION,
        "record_type": EXPERIMENT_RECORD_TYPE,
        "experiment_manifest": {
            "manifest_type": EXPERIMENT_MANIFEST_TYPE,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "manifest_id": "a6-length-probe",
            "sha256": "c" * 64,
            "byte_length": 1300,
        },
        "game": {
            "id": "m8-unique-rank-single-open",
            "version": "m8-a-v1",
            "player_count": player_count,
        },
        "execution": {
            "plan_kind": "a6-a7-training",
            "status": "completed",
            "stage": "training",
            "stop_reason": "completed",
            "completed_iterations": 1,
            "player_count": player_count,
            "iterations": 1,
            "average_strategy_start_iteration": 1,
            "master_seed": 6,
            "traverser": None,
        },
        "supervisor": dict(supervisor),
        "strategy": {
            "sha256": strategy_sha256,
            "artifact_bytes": strategy_bytes,
            "artifact_type": ARTIFACT_TYPE,
            "artifact_schema_version": STRATEGY_SCHEMA_VERSION,
        },
        "profile": {
            "ordered_deal_count": 720,
            "terminal_leaf_count": 720,
            "utilities": utilities,
            "strategy_sha256": strategy_sha256,
            "strategy_bytes": strategy_bytes,
            "evaluator_id": EVALUATOR_ID,
            "evaluator_version": EVALUATOR_VERSION,
            "probability_units": PROBABILITY_UNITS,
        },
        "probes": None,
        "stability": {
            "status": "not-requested",
            "seed_set_sha256": None,
            "audit_infosets_sha256": None,
            "max_l1": None,
        },
        "diagnostics": {
            "average_strategy_start_iteration": 1,
            "coverage": [],
            "importance_weights": [],
        },
        "resources": {
            "elapsed_milliseconds": 0,
            "wall_time_limit_milliseconds": 1000,
            "peak_rss_bytes": 0,
            "rss_warning_bytes": 100,
            "rss_hard_limit_bytes": 200,
            "warning_triggered": False,
            "retained_artifact_bytes": 0,
            "retained_artifact_limit_bytes": 1024,
            **supervisor,
        },
    }


def test_record_accepts_exact_rationals_longer_than_identifier_bound() -> None:
    numerator = "1" + "0" * 200
    assert len(numerator) > 128

    record = parse_manifested_measurement_payload(_synthetic_child_payload(numerator=numerator))

    assert record.payload["profile"]["utilities"][0]["numerator"] == numerator
    assert record.payload["profile"]["utilities"][1]["numerator"] == f"-{numerator}"


def test_record_rejects_exact_rationals_beyond_the_dedicated_bound() -> None:
    numerator = "1" + "0" * MAX_RATIONAL_DIGITS
    assert len(numerator) > MAX_RATIONAL_DIGITS

    with pytest.raises(ExperimentRecordError):
        parse_manifested_measurement_payload(_synthetic_child_payload(numerator=numerator))


def test_current_version_declares_unrequested_stability() -> None:
    payload = _synthetic_child_payload(numerator="1")

    assert payload["schema_version"] == EXPERIMENT_RECORD_SCHEMA_VERSION
    assert payload["stability"] == {
        "status": "not-requested",
        "seed_set_sha256": None,
        "audit_infosets_sha256": None,
        "max_l1": None,
    }


def test_legacy_payload_without_stability_section_is_still_accepted() -> None:
    current = _synthetic_child_payload(numerator="1")
    legacy = {key: value for key, value in current.items() if key != "stability"}
    legacy["schema_version"] = LEGACY_EXPERIMENT_RECORD_SCHEMA_VERSION

    record = parse_manifested_measurement_payload(legacy)

    assert "stability" not in record.payload


def test_record_rejects_an_incompatible_stability_section() -> None:
    payload = _synthetic_child_payload(numerator="1")
    payload["stability"] = {"status": "measured"}

    with pytest.raises(ExperimentRecordError):
        parse_manifested_measurement_payload(payload)


def test_record_rejects_a_stability_section_on_the_legacy_version() -> None:
    payload = _synthetic_child_payload(numerator="1")
    payload["schema_version"] = LEGACY_EXPERIMENT_RECORD_SCHEMA_VERSION

    with pytest.raises(ExperimentRecordError):
        parse_manifested_measurement_payload(payload)
