"""macOS 上受限子进程的外部资源监督器。"""

from __future__ import annotations

import hashlib
import os
import platform
import signal
import stat
import subprocess
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import IO, Any

SUPERVISOR_ID = "macos-process-tree-supervisor"
SUPERVISOR_VERSION = "v2"
_PS_PATH = "/bin/ps"

# 子进程输出只在内存中保留受限尾部，避免诊断能力反过来引入无界资源占用。
CHILD_OUTPUT_TAIL_BYTES = 8_192
CHILD_OUTPUT_TAIL_CHARACTERS = 2_048
_CHILD_OUTPUT_READ_BYTES = 65_536
_CHILD_OUTPUT_DRAIN_GRACE_MILLISECONDS = 200


class SupervisorError(ValueError):
    """外部监督器的命令、预算、进程快照或受限目录不符合契约时抛出。"""


class SupervisorStatus(StrEnum):
    """受控子进程的最终状态。"""

    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class SupervisorStopReason(StrEnum):
    """监督器不会自动重试的终止原因。"""

    COMPLETED = "completed"
    CHILD_EXIT_NONZERO = "child-exit-nonzero"
    WALL_TIME_LIMIT = "wall-time-limit"
    CPU_LIMIT = "cpu-limit"
    RSS_WARNING_LIMIT = "rss-warning-limit"
    RSS_HARD_LIMIT = "rss-hard-limit"
    ARTIFACT_QUOTA = "artifact-quota"
    MONITOR_FAILURE = "monitor-failure"


@dataclass(frozen=True)
class SupervisorLimits:
    """单个受控子进程的显式硬限制与采样周期。"""

    cpu_limit_milliseconds: int
    wall_time_limit_milliseconds: int
    rss_warning_bytes: int
    rss_hard_limit_bytes: int
    retained_artifact_limit_bytes: int
    max_concurrency: int = 1
    poll_interval_milliseconds: int = 50
    termination_grace_milliseconds: int = 500

    def __post_init__(self) -> None:
        _require_positive_int(self.cpu_limit_milliseconds, "CPU 上限")
        _require_positive_int(self.wall_time_limit_milliseconds, "墙钟上限")
        warning = _require_nonnegative_int(self.rss_warning_bytes, "RSS 预警阈值")
        hard = _require_positive_int(self.rss_hard_limit_bytes, "RSS 硬停阈值")
        if warning >= hard:
            raise SupervisorError("RSS 预警阈值必须小于硬停阈值")
        _require_positive_int(self.retained_artifact_limit_bytes, "工件上限")
        if self.max_concurrency != 1:
            raise SupervisorError("当前监督器仅支持单个受控子进程")
        _require_positive_int(self.poll_interval_milliseconds, "采样间隔")
        _require_positive_int(self.termination_grace_milliseconds, "终止宽限期")


@dataclass(frozen=True)
class SupervisorReceipt:
    """由父监督器生成的资源、停止原因与子进程输出摘要回执，不是子进程自述。"""

    supervisor_id: str
    supervisor_version: str
    status: SupervisorStatus
    stop_reason: SupervisorStopReason
    exit_code: int | None
    wall_time_milliseconds: int
    cpu_time_milliseconds: int
    peak_rss_bytes: int
    initial_artifact_bytes: int
    final_artifact_bytes: int
    warning_triggered: bool
    terminated_with_signal: int | None
    monitored_pids: tuple[int, ...]
    child_output_bytes: int
    child_output_sha256: str
    child_output_tail: str


@dataclass(frozen=True)
class _ProcessSample:
    pid: int
    parent_pid: int
    rss_bytes: int
    cpu_milliseconds: int


@dataclass
class _ProcessAccounting:
    root_pid: int
    maximum_cpu_by_pid: dict[int, int] = field(default_factory=dict)
    monitored_pids: set[int] = field(default_factory=set)
    peak_rss_bytes: int = 0

    def observe(self, samples: dict[int, _ProcessSample]) -> tuple[int, int]:
        selected = _select_process_tree(samples, self.root_pid)
        current_rss = 0
        for pid in selected:
            sample = samples[pid]
            self.monitored_pids.add(pid)
            self.maximum_cpu_by_pid[pid] = max(
                self.maximum_cpu_by_pid.get(pid, 0), sample.cpu_milliseconds
            )
            current_rss += sample.rss_bytes
        self.peak_rss_bytes = max(self.peak_rss_bytes, current_rss)
        return sum(self.maximum_cpu_by_pid.values()), current_rss


@dataclass
class _ChildOutput:
    """合并子进程输出收集器：累计字节与全量摘要，只在内存中保留受限尾部。"""

    maximum_tail_bytes: int
    total_bytes: int = 0
    _tail: bytearray = field(default_factory=bytearray)
    _digest: Any = None

    def __post_init__(self) -> None:
        if isinstance(self.maximum_tail_bytes, bool) or self.maximum_tail_bytes <= 0:
            raise SupervisorError("子进程输出尾部上限必须是正整数")
        self._digest = hashlib.sha256()

    def observe(self, stream: IO[bytes] | None) -> bool:
        """非阻塞读取当前可用输出；返回是否已读到流结束。"""

        if stream is None:
            return True
        descriptor = stream.fileno()
        try:
            os.set_blocking(descriptor, False)
        except OSError:
            return True
        while True:
            try:
                chunk = os.read(descriptor, _CHILD_OUTPUT_READ_BYTES)
            except BlockingIOError:
                return False
            except OSError:
                return True
            if not chunk:
                return True
            self.total_bytes += len(chunk)
            self._digest.update(chunk)
            self._tail.extend(chunk)
            overflow = len(self._tail) - self.maximum_tail_bytes
            if overflow > 0:
                del self._tail[:overflow]

    def drain_until_closed(self, stream: IO[bytes] | None, grace_milliseconds: int) -> None:
        """在有限宽限期内读完剩余输出，避免子进程退出后管道中的诊断信息丢失。"""

        deadline = time.monotonic() + grace_milliseconds / 1000
        while time.monotonic() < deadline:
            if self.observe(stream):
                return
            time.sleep(0.01)

    def digest(self) -> str:
        return self._digest.hexdigest()

    def tail_text(self) -> str:
        return self._tail.decode("utf-8", errors="replace")[-CHILD_OUTPUT_TAIL_CHARACTERS:]


def supervise_command(
    argv: Sequence[str],
    *,
    working_directory: str | Path,
    artifact_root: str | Path,
    limits: SupervisorLimits,
    environment: Mapping[str, str] | None = None,
) -> SupervisorReceipt:
    """在新的进程组启动无 shell 子进程，并监督其进程树、工件目录与合并输出。

    子进程的 stdout 与 stderr 合并到同一管道，由父端边采样边排空；父端只保留受限
    尾部用于定位失败原因，因此该诊断能力不会引入无界磁盘或内存占用。若子进程持续
    高速输出，它会因管道背压而变慢，但不会被丢弃或死锁。
    """

    _require_macos()
    command = _validate_argv(argv)
    child_environment = _validate_child_environment(environment)
    cwd = _require_directory(working_directory, "工作目录")
    artifact_directory = _require_directory(artifact_root, "工件根目录")
    initial_artifact_bytes = _artifact_bytes(artifact_directory)
    if initial_artifact_bytes > limits.retained_artifact_limit_bytes:
        raise SupervisorError("工件根目录已超过保留上限")

    started_at = time.monotonic()
    warning_triggered = False
    terminated_with_signal: int | None = None
    accounting: _ProcessAccounting | None = None
    child: subprocess.Popen[bytes] | None = None
    output = _ChildOutput(maximum_tail_bytes=CHILD_OUTPUT_TAIL_BYTES)
    try:
        child = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=child_environment,
        )
        accounting = _ProcessAccounting(root_pid=child.pid)
        while True:
            output.observe(child.stdout)
            samples = _snapshot_processes()
            cpu_milliseconds, current_rss = accounting.observe(samples)
            elapsed_milliseconds = _elapsed_milliseconds(started_at)
            artifact_bytes = _artifact_bytes(artifact_directory)
            reason = _limit_reason(
                elapsed_milliseconds=elapsed_milliseconds,
                cpu_milliseconds=cpu_milliseconds,
                current_rss_bytes=current_rss,
                artifact_bytes=artifact_bytes,
                limits=limits,
            )
            if reason is not None:
                warning_triggered = (
                    warning_triggered or reason is SupervisorStopReason.RSS_WARNING_LIMIT
                )
                terminated_with_signal = _terminate_process_tree(
                    child,
                    accounting.monitored_pids,
                    limits.termination_grace_milliseconds,
                )
                output.drain_until_closed(
                    child.stdout, _CHILD_OUTPUT_DRAIN_GRACE_MILLISECONDS
                )
                return _receipt(
                    status=SupervisorStatus.STOPPED,
                    stop_reason=reason,
                    child=child,
                    started_at=started_at,
                    accounting=accounting,
                    initial_artifact_bytes=initial_artifact_bytes,
                    final_artifact_bytes=_artifact_bytes(artifact_directory),
                    warning_triggered=warning_triggered,
                    terminated_with_signal=terminated_with_signal,
                    child_output=output,
                )
            exit_code = child.poll()
            if exit_code is not None:
                output.drain_until_closed(
                    child.stdout, _CHILD_OUTPUT_DRAIN_GRACE_MILLISECONDS
                )
                return _receipt(
                    status=(
                        SupervisorStatus.COMPLETED if exit_code == 0 else SupervisorStatus.FAILED
                    ),
                    stop_reason=(
                        SupervisorStopReason.COMPLETED
                        if exit_code == 0
                        else SupervisorStopReason.CHILD_EXIT_NONZERO
                    ),
                    child=child,
                    started_at=started_at,
                    accounting=accounting,
                    initial_artifact_bytes=initial_artifact_bytes,
                    final_artifact_bytes=_artifact_bytes(artifact_directory),
                    warning_triggered=warning_triggered,
                    terminated_with_signal=None,
                    child_output=output,
                )
            time.sleep(limits.poll_interval_milliseconds / 1000)
    except (OSError, SupervisorError):
        if child is not None and accounting is not None and child.poll() is None:
            terminated_with_signal = _terminate_process_tree(
                child,
                accounting.monitored_pids,
                limits.termination_grace_milliseconds,
            )
        if child is None or accounting is None:
            raise
        output.drain_until_closed(child.stdout, _CHILD_OUTPUT_DRAIN_GRACE_MILLISECONDS)
        return _receipt(
            status=SupervisorStatus.FAILED,
            stop_reason=SupervisorStopReason.MONITOR_FAILURE,
            child=child,
            started_at=started_at,
            accounting=accounting,
            initial_artifact_bytes=initial_artifact_bytes,
            final_artifact_bytes=_artifact_bytes(artifact_directory),
            warning_triggered=warning_triggered,
            terminated_with_signal=terminated_with_signal,
            child_output=output,
        )


def _receipt(
    *,
    status: SupervisorStatus,
    stop_reason: SupervisorStopReason,
    child: subprocess.Popen[bytes],
    started_at: float,
    accounting: _ProcessAccounting,
    initial_artifact_bytes: int,
    final_artifact_bytes: int,
    warning_triggered: bool,
    terminated_with_signal: int | None,
    child_output: _ChildOutput,
) -> SupervisorReceipt:
    return SupervisorReceipt(
        supervisor_id=SUPERVISOR_ID,
        supervisor_version=SUPERVISOR_VERSION,
        status=status,
        stop_reason=stop_reason,
        exit_code=child.poll(),
        wall_time_milliseconds=_elapsed_milliseconds(started_at),
        cpu_time_milliseconds=sum(accounting.maximum_cpu_by_pid.values()),
        peak_rss_bytes=accounting.peak_rss_bytes,
        initial_artifact_bytes=initial_artifact_bytes,
        final_artifact_bytes=final_artifact_bytes,
        warning_triggered=warning_triggered,
        terminated_with_signal=terminated_with_signal,
        monitored_pids=tuple(sorted(accounting.monitored_pids)),
        child_output_bytes=child_output.total_bytes,
        child_output_sha256=child_output.digest(),
        child_output_tail=child_output.tail_text(),
    )


def _limit_reason(
    *,
    elapsed_milliseconds: int,
    cpu_milliseconds: int,
    current_rss_bytes: int,
    artifact_bytes: int,
    limits: SupervisorLimits,
) -> SupervisorStopReason | None:
    if artifact_bytes > limits.retained_artifact_limit_bytes:
        return SupervisorStopReason.ARTIFACT_QUOTA
    if current_rss_bytes >= limits.rss_hard_limit_bytes:
        return SupervisorStopReason.RSS_HARD_LIMIT
    if current_rss_bytes >= limits.rss_warning_bytes:
        return SupervisorStopReason.RSS_WARNING_LIMIT
    if cpu_milliseconds >= limits.cpu_limit_milliseconds:
        return SupervisorStopReason.CPU_LIMIT
    if elapsed_milliseconds >= limits.wall_time_limit_milliseconds:
        return SupervisorStopReason.WALL_TIME_LIMIT
    return None


def _snapshot_processes() -> dict[int, _ProcessSample]:
    result = subprocess.run(
        [_PS_PATH, "-axo", "pid=,ppid=,rss=,time="],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={"LC_ALL": "C", "LANG": "C", "PATH": os.defpath},
    )
    samples: dict[int, _ProcessSample] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise SupervisorError("ps 快照格式不兼容")
        pid = _require_positive_int_text(fields[0], "ps pid")
        parent_pid = _require_nonnegative_int_text(fields[1], "ps ppid")
        rss_kibibytes = _require_nonnegative_int_text(fields[2], "ps rss")
        samples[pid] = _ProcessSample(
            pid=pid,
            parent_pid=parent_pid,
            rss_bytes=rss_kibibytes * 1024,
            cpu_milliseconds=_parse_cpu_milliseconds(fields[3]),
        )
    return samples


def _select_process_tree(samples: dict[int, _ProcessSample], root_pid: int) -> set[int]:
    selected = {root_pid} if root_pid in samples else set()
    changed = True
    while changed:
        changed = False
        for pid, sample in samples.items():
            if sample.parent_pid in selected and pid not in selected:
                selected.add(pid)
                changed = True
    return selected


def _terminate_process_tree(
    child: subprocess.Popen[bytes], known_pids: set[int], grace_milliseconds: int
) -> int | None:
    try:
        os.killpg(child.pid, signal.SIGTERM)
        signal_sent = signal.SIGTERM
    except ProcessLookupError:
        return None
    deadline = time.monotonic() + grace_milliseconds / 1000
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return signal_sent
        time.sleep(0.01)
    try:
        os.killpg(child.pid, signal.SIGKILL)
        signal_sent = signal.SIGKILL
    except ProcessLookupError:
        return signal_sent
    for pid in known_pids:
        if pid != child.pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue
    with suppress(subprocess.TimeoutExpired):
        child.wait(timeout=1)
    return signal_sent


def _artifact_bytes(root: Path) -> int:
    total = 0
    for directory, subdirectories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in subdirectories:
            details = (directory_path / name).lstat()
            if stat.S_ISLNK(details.st_mode):
                raise SupervisorError("工件根目录不能包含链接目录")
        for name in filenames:
            details = (directory_path / name).lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
                raise SupervisorError("工件根目录只能包含普通文件")
            total += details.st_size
    return total


def _validate_child_environment(environment: Mapping[str, str] | None) -> dict[str, str] | None:
    if environment is None:
        return None
    validated = {}
    for key, value in environment.items():
        if (
            not isinstance(key, str)
            or not key
            or "=" in key
            or "\x00" in key
            or not isinstance(value, str)
            or "\x00" in value
        ):
            raise SupervisorError("受控子进程环境变量不合法")
        validated[key] = value
    return validated


def _validate_argv(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not value or len(value) > 64:
        raise SupervisorError("监督命令必须是长度受限的参数序列")
    command = tuple(value)
    for argument in command:
        if (
            not isinstance(argument, str)
            or not argument
            or len(argument) > 4096
            or "\x00" in argument
        ):
            raise SupervisorError("监督命令参数不合法")
    return command


def _require_directory(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_dir() or path.is_symlink():
        raise SupervisorError(f"{label}必须是现有非链接目录")
    return path


def _parse_cpu_milliseconds(value: str) -> int:
    days = 0
    if "-" in value:
        day_text, value = value.split("-", maxsplit=1)
        days = _require_nonnegative_int_text(day_text, "ps CPU 天数")
    parts = value.split(":")
    if not 2 <= len(parts) <= 3:
        raise SupervisorError("ps CPU 时间格式不兼容")
    seconds = float(parts[-1])
    if seconds < 0:
        raise SupervisorError("ps CPU 秒数不能为负")
    minutes = _require_nonnegative_int_text(parts[-2], "ps CPU 分钟")
    hours = _require_nonnegative_int_text(parts[-3], "ps CPU 小时") if len(parts) == 3 else 0
    return round((((days * 24 + hours) * 60 + minutes) * 60 + seconds) * 1000)


def _elapsed_milliseconds(started_at: float) -> int:
    elapsed = time.monotonic() - started_at
    if elapsed < 0:
        raise SupervisorError("单调时钟不能倒退")
    return round(elapsed * 1000)


def _require_positive_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SupervisorError(f"{label}必须是正整数")
    return value


def _require_nonnegative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SupervisorError(f"{label}必须是非负整数")
    return value


def _require_positive_int_text(value: str, label: str) -> int:
    if not value.isdigit() or int(value) <= 0:
        raise SupervisorError(f"{label}必须是正整数")
    return int(value)


def _require_nonnegative_int_text(value: str, label: str) -> int:
    if not value.isdigit():
        raise SupervisorError(f"{label}必须是非负整数")
    return int(value)


def _require_macos() -> None:
    if platform.system() != "Darwin":
        raise SupervisorError("当前外部监督器仅支持 macOS")
