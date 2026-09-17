from collections import deque

from multiplayer_cfr.control import RunLimits, RunStatus, StopReason, run_controlled_training
from multiplayer_cfr.mccfr import MCCFRConfig


def _reader(values: list[int]):
    pending = deque(values)

    def read() -> int:
        return pending.popleft() if pending else values[-1]

    return read


def test_controlled_n7_short_path_collects_diagnostics_without_exporting_artifact() -> None:
    result = run_controlled_training(
        MCCFRConfig(player_count=7, iterations=1, master_seed=101),
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


def test_controlled_n9_stops_before_any_sampling_or_exportable_result() -> None:
    result = run_controlled_training(
        MCCFRConfig(player_count=9, iterations=1, master_seed=103),
        RunLimits(
            stage="n9-boundary",
            wall_time_seconds=10.0,
            rss_warning_bytes=6 * 1024**3,
            rss_hard_limit_bytes=8 * 1024**3,
            retained_artifact_limit_bytes=1024,
        ),
        monotonic_clock=_reader([0, 0]),
        rss_reader=_reader([512]),
        rss_sampler_id="test-rss-v1",
    )

    assert result.status is RunStatus.STOPPED
    assert result.stop_reason is StopReason.NINE_PLAYER_BOUNDARY
    assert result.completed_iterations == 0
    assert result.result is None
    assert all(
        item.visits == 0 and item.visited_infosets == 0 for item in result.diagnostics.coverage
    )


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
        MCCFRConfig(player_count=6, iterations=1, master_seed=107),
        limits,
        monotonic_clock=_reader([0, 0]),
        rss_reader=_reader([0]),
        rss_sampler_id="test-rss-v1",
    )

    assert quota_result.stop_reason is StopReason.ARTIFACT_QUOTA

    warning_result = run_controlled_training(
        MCCFRConfig(player_count=6, iterations=1, master_seed=109),
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
