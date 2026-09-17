from collections import deque

import pytest

from multiplayer_cfr.control import (
    ControlError,
    RunLimits,
    RunStatus,
    StopReason,
    run_controlled_training,
    run_n9_boundary_sample,
)
from multiplayer_cfr.mccfr import MCCFRConfig


def _reader(values: list[int]):
    pending = deque(values)

    def read() -> int:
        return pending.popleft() if pending else values[-1]

    return read


def test_controlled_n7_short_path_collects_diagnostics_without_exporting_artifact() -> None:
    result = run_controlled_training(
        MCCFRConfig(
            player_count=7,
            iterations=1,
            master_seed=101,
            average_strategy_start_iteration=1,
        ),
        RunLimits(
            stage="n7-short-path",
            wall_time_seconds=10.0,
            rss_warning_bytes=6 * 1024**3,
            rss_hard_limit_bytes=8 * 1024**3,
            retained_artifact_limit_bytes=1024,
        ),
        monotonic_clock=_reader([0, 0, 0]),
        rss_reader=_reader([512, 1024]),
        rss_sampler_id="test-rss-v1",
    )

    assert result.status is RunStatus.COMPLETED
    assert result.stop_reason is StopReason.COMPLETED
    assert result.completed_iterations == 1
    assert result.result is not None
    assert [item.traverser for item in result.diagnostics.coverage] == list(range(7))
    assert all(item.visits > 0 for item in result.diagnostics.coverage)
    assert result.resources.peak_rss_bytes == 1024


def test_n9_requires_boundary_entry_and_returns_only_one_non_training_sample() -> None:
    limits = RunLimits(
        stage="n9-boundary",
        wall_time_seconds=10.0,
        rss_warning_bytes=6 * 1024**3,
        rss_hard_limit_bytes=8 * 1024**3,
        retained_artifact_limit_bytes=1024,
    )
    with pytest.raises(ControlError):
        run_controlled_training(
            MCCFRConfig(
                player_count=9,
                iterations=1,
                master_seed=103,
                average_strategy_start_iteration=1,
            ),
            limits,
            monotonic_clock=_reader([0, 0]),
            rss_reader=_reader([512]),
            rss_sampler_id="test-rss-v1",
        )

    boundary = run_n9_boundary_sample(
        master_seed=103,
        traverser=4,
        limits=limits,
        monotonic_clock=_reader([0, 0, 0]),
        rss_reader=_reader([512, 1024]),
        rss_sampler_id="test-rss-v1",
    )

    assert boundary.status is RunStatus.COMPLETED
    assert boundary.stop_reason is StopReason.COMPLETED
    assert boundary.sample is not None
    assert boundary.sample.traverser == 4
    assert boundary.sample.infoset_count == 20736


def test_controlled_runner_records_quota_and_rss_warning_stops() -> None:
    limits = RunLimits(
        stage="preflight",
        wall_time_seconds=10.0,
        rss_warning_bytes=100,
        rss_hard_limit_bytes=200,
        retained_artifact_limit_bytes=10,
        retained_artifact_bytes=10,
    )
    quota_result = run_controlled_training(
        MCCFRConfig(
            player_count=6,
            iterations=1,
            master_seed=107,
            average_strategy_start_iteration=1,
        ),
        limits,
        monotonic_clock=_reader([0, 0]),
        rss_reader=_reader([0]),
        rss_sampler_id="test-rss-v1",
    )

    assert quota_result.stop_reason is StopReason.ARTIFACT_QUOTA

    warning_result = run_controlled_training(
        MCCFRConfig(
            player_count=6,
            iterations=1,
            master_seed=109,
            average_strategy_start_iteration=1,
        ),
        RunLimits(
            stage="preflight",
            wall_time_seconds=10.0,
            rss_warning_bytes=100,
            rss_hard_limit_bytes=200,
            retained_artifact_limit_bytes=10,
        ),
        monotonic_clock=_reader([0, 0]),
        rss_reader=_reader([100]),
        rss_sampler_id="test-rss-v1",
    )

    assert warning_result.stop_reason is StopReason.RSS_WARNING_LIMIT
    assert warning_result.resources.warning_triggered is True
