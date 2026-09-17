from collections import deque
from copy import deepcopy
from pathlib import Path

import pytest

from multiplayer_cfr.experiment_record import (
    ExperimentRecordError,
    SupervisorIdentity,
    load_manifested_measurement_record,
)
from multiplayer_cfr.manifest import (
    EXPERIMENT_MANIFEST_TYPE,
    MANIFEST_SCHEMA_VERSION,
    create_experiment_manifest,
    derive_experiment_plan,
)
from multiplayer_cfr.orchestration import (
    OrchestrationError,
    SupervisorSession,
    run_manifested_experiment,
)
from multiplayer_cfr.safeio import canonical_json_bytes

_COMMIT = "3" * 40


def _reader(values: list[int]):
    pending = deque(values)

    def read() -> int:
        return pending.popleft() if pending else values[-1]

    return read


def _plan(player_count: int, *, profile_mode: str = "not-requested"):
    is_n9 = player_count == 9
    manifest = create_experiment_manifest(
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "manifest_type": EXPERIMENT_MANIFEST_TYPE,
            "manifest_id": f"a{player_count}-orchestration",
            "code_identity": {
                "git_commit": _COMMIT,
                "workspace_state": "clean",
                "trainer_version": "candidate-a-orchestration-v1",
            },
            "game": {
                "id": "m8-unique-rank-single-open",
                "version": "m8-a-v1",
                "player_count": player_count,
            },
            "execution": (
                {"kind": "n9-boundary-sample", "iteration": 1, "traverser": 2, "master_seed": 9}
                if is_n9
                else {
                    "kind": "a6-a7-training",
                    "iterations": 1,
                    "average_strategy_start_iteration": 1,
                    "master_seed": 6,
                }
            ),
            "quality": {
                "profile_mode": "not-requested" if is_n9 else profile_mode,
                "probe_manifest": None,
            },
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


def _session() -> SupervisorSession:
    return SupervisorSession(
        identity=SupervisorIdentity(
            supervisor_id="local-supervisor",
            supervisor_version="v1",
            rss_scope="process-tree",
            enforcement_mode="external-hard-limit",
        ),
        monotonic_clock=_reader([0, 0, 0, 0, 0]),
        rss_reader=_reader([0, 0, 0]),
        rss_sampler_id="test-rss-v1",
        git_commit=_COMMIT,
        workspace_state="clean",
        trainer_version="candidate-a-orchestration-v1",
    )


def test_orchestration_runs_only_manifested_a6_stages_and_declared_artifacts(
    tmp_path: Path,
) -> None:
    result = run_manifested_experiment(_plan(6), tmp_path, _session())

    assert result.strategy_path == tmp_path / "strategy.json"
    assert result.measurement_path == tmp_path / "measurement.json"
    assert result.strategy_path.is_file()
    assert result.measurement_path.is_file()
    assert result.record.payload["strategy"] is not None
    assert sorted(path.name for path in tmp_path.iterdir()) == ["measurement.json", "strategy.json"]


def test_orchestration_rejects_runtime_code_identity_not_equal_to_manifest(tmp_path: Path) -> None:
    session = _session()
    mismatched = SupervisorSession(
        identity=session.identity,
        monotonic_clock=session.monotonic_clock,
        rss_reader=session.rss_reader,
        rss_sampler_id=session.rss_sampler_id,
        git_commit="0" * 40,
        workspace_state="clean",
        trainer_version="candidate-a-orchestration-v1",
    )

    with pytest.raises(OrchestrationError):
        run_manifested_experiment(_plan(6), tmp_path, mismatched)

    assert list(tmp_path.iterdir()) == []


def test_orchestration_binds_profile_to_the_exported_quantized_strategy(tmp_path: Path) -> None:
    result = run_manifested_experiment(_plan(6, profile_mode="full-chance"), tmp_path, _session())

    profile = result.record.payload["profile"]
    strategy = result.record.payload["strategy"]
    assert profile is not None
    assert strategy is not None
    assert profile["strategy_sha256"] == strategy["sha256"]
    assert profile["evaluator_id"] == "candidate-a-full-chance-evaluator"

    tampered = deepcopy(result.record.payload)
    tampered["profile"]["strategy_sha256"] = "0" * 64
    tampered_path = tmp_path / "tampered.json"
    tampered_path.write_bytes(canonical_json_bytes(tampered))
    with pytest.raises(ExperimentRecordError):
        load_manifested_measurement_record(tampered_path)


def test_orchestration_allows_n9_boundary_without_strategy_and_rejects_existing_slots(
    tmp_path: Path,
) -> None:
    n9 = run_manifested_experiment(_plan(9), tmp_path, _session())

    assert n9.strategy_path is None
    assert n9.measurement_path.is_file()
    assert n9.record.payload["strategy"] is None

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "measurement.json").write_text("reserved", encoding="utf-8")
    with pytest.raises(OrchestrationError):
        run_manifested_experiment(_plan(9), occupied, _session())
