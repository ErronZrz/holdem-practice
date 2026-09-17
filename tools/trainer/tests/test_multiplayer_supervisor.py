import sys
from pathlib import Path

import pytest

from multiplayer_cfr.supervisor import (
    SupervisorError,
    SupervisorLimits,
    SupervisorStatus,
    SupervisorStopReason,
    supervise_command,
)


def _limits(**overrides: int) -> SupervisorLimits:
    values = {
        "cpu_limit_milliseconds": 10_000,
        "wall_time_limit_milliseconds": 2_000,
        "rss_warning_bytes": 128 * 1024 * 1024,
        "rss_hard_limit_bytes": 256 * 1024 * 1024,
        "retained_artifact_limit_bytes": 1_000_000,
        "poll_interval_milliseconds": 10,
        "termination_grace_milliseconds": 50,
    }
    values.update(overrides)
    return SupervisorLimits(**values)


def test_supervisor_completes_non_shell_command_and_records_artifact_bytes(tmp_path: Path) -> None:
    receipt = supervise_command(
        (
            sys.executable,
            "-c",
            "from pathlib import Path; Path('result.txt').write_text('ok', encoding='utf-8')",
        ),
        working_directory=tmp_path,
        artifact_root=tmp_path,
        limits=_limits(),
    )

    assert receipt.status is SupervisorStatus.COMPLETED
    assert receipt.stop_reason is SupervisorStopReason.COMPLETED
    assert receipt.exit_code == 0
    assert receipt.final_artifact_bytes == 2
    assert receipt.peak_rss_bytes >= 0


def test_supervisor_stops_process_group_when_wall_time_limit_is_hit(tmp_path: Path) -> None:
    receipt = supervise_command(
        (sys.executable, "-c", "import time; time.sleep(10)"),
        working_directory=tmp_path,
        artifact_root=tmp_path,
        limits=_limits(wall_time_limit_milliseconds=50),
    )

    assert receipt.status is SupervisorStatus.STOPPED
    assert receipt.stop_reason is SupervisorStopReason.WALL_TIME_LIMIT
    assert receipt.terminated_with_signal is not None
    assert receipt.monitored_pids


def test_supervisor_stops_cpu_bound_child_at_declared_cpu_limit(tmp_path: Path) -> None:
    receipt = supervise_command(
        (sys.executable, "-c", "while True: pass"),
        working_directory=tmp_path,
        artifact_root=tmp_path,
        limits=_limits(cpu_limit_milliseconds=10),
    )

    assert receipt.status is SupervisorStatus.STOPPED
    assert receipt.stop_reason is SupervisorStopReason.CPU_LIMIT
    assert receipt.cpu_time_milliseconds >= 10


def test_supervisor_stops_when_child_exceeds_declared_artifact_quota(tmp_path: Path) -> None:
    script = (
        "from pathlib import Path; import time; "
        "Path('payload.bin').write_bytes(b'x' * 4096); time.sleep(10)"
    )
    receipt = supervise_command(
        (sys.executable, "-c", script),
        working_directory=tmp_path,
        artifact_root=tmp_path,
        limits=_limits(retained_artifact_limit_bytes=1024),
    )

    assert receipt.status is SupervisorStatus.STOPPED
    assert receipt.stop_reason is SupervisorStopReason.ARTIFACT_QUOTA
    assert receipt.final_artifact_bytes == 4096


def test_supervisor_rejects_parallel_budget_or_invalid_command(tmp_path: Path) -> None:
    with pytest.raises(SupervisorError):
        SupervisorLimits(
            cpu_limit_milliseconds=1,
            wall_time_limit_milliseconds=1,
            rss_warning_bytes=1,
            rss_hard_limit_bytes=2,
            retained_artifact_limit_bytes=1,
            max_concurrency=2,
        )
    with pytest.raises(SupervisorError):
        supervise_command(
            "not-an-argv",
            working_directory=tmp_path,
            artifact_root=tmp_path,
            limits=_limits(),
        )
