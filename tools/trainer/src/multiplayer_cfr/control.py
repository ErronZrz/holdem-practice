"""候选 A 离线训练的合作式停止控制与采样诊断。"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from math import ceil

from .mccfr import (
    IterationTrace,
    MCCFRConfig,
    MCCFRResult,
    N9BoundarySample,
    SynchronousExternalSamplingMCCFR,
    sample_n9_boundary,
)


class ControlError(ValueError):
    """受控运行的预算、采样或状态不符合明确契约时抛出。"""


class RunStatus(StrEnum):
    """合作式运行结束状态。"""

    COMPLETED = "completed"
    STOPPED = "stopped"


class StopReason(StrEnum):
    """不触发隐式重试的受控停止原因。"""

    COMPLETED = "completed"
    WALL_TIME_LIMIT = "wall-time-limit"
    RSS_WARNING_LIMIT = "rss-warning-limit"
    RSS_HARD_LIMIT = "rss-hard-limit"
    ARTIFACT_QUOTA = "artifact-quota"
    EXTERNAL_CANCELLATION = "external-cancellation"
    NINE_PLAYER_BOUNDARY = "nine-player-boundary"


@dataclass(frozen=True)
class RunLimits:
    """由调用方显式提供的单阶段资源上限，不启动或管理进程。"""

    stage: str
    wall_time_seconds: float
    rss_warning_bytes: int
    rss_hard_limit_bytes: int
    retained_artifact_limit_bytes: int
    retained_artifact_bytes: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.stage, str) or not self.stage:
            raise ControlError("阶段标识必须是非空字符串")
        _require_positive_finite(self.wall_time_seconds, "墙钟上限")
        warning = _require_nonnegative_int(self.rss_warning_bytes, "RSS 预警阈值")
        hard = _require_positive_int(self.rss_hard_limit_bytes, "RSS 硬停阈值")
        if warning >= hard:
            raise ControlError("RSS 预警阈值必须小于硬停阈值")
        limit = _require_positive_int(self.retained_artifact_limit_bytes, "保留产物上限")
        retained = _require_nonnegative_int(self.retained_artifact_bytes, "已保留产物字节数")
        if retained > limit:
            raise ControlError("已保留产物不能超过上限")


@dataclass(frozen=True)
class CoverageSummary:
    """单个相对座位的访问覆盖计数，不代表有效样本量。"""

    traverser: int
    visits: int
    visited_infosets: int
    total_infosets: int


@dataclass(frozen=True)
class ImportanceWeightSummary:
    """单个相对座位的平均策略重要性权重摘要。"""

    traverser: int
    visits: int
    maximum: float
    p50: float
    p95: float
    non_finite_count: int


@dataclass(frozen=True)
class TrainingDiagnostics:
    """由 iteration trace 汇总的覆盖和权重诊断。"""

    coverage: tuple[CoverageSummary, ...]
    importance_weights: tuple[ImportanceWeightSummary, ...]


@dataclass(frozen=True)
class RunResources:
    """合作式运行观察到的资源与预算状态。"""

    elapsed_seconds: float
    wall_time_limit_seconds: float
    peak_rss_bytes: int
    rss_warning_bytes: int
    rss_hard_limit_bytes: int
    rss_sampler_id: str
    warning_triggered: bool
    retained_artifact_bytes: int
    retained_artifact_limit_bytes: int


@dataclass(frozen=True)
class ControlledTrainingResult:
    """受控运行结果；停止时不生成可导出的 MCCFR 结果。"""

    status: RunStatus
    stop_reason: StopReason
    completed_iterations: int
    diagnostics: TrainingDiagnostics
    resources: RunResources
    result: MCCFRResult | None


@dataclass(frozen=True)
class N9BoundaryResult:
    """N9 单次边界采样的受控回执，绝不包含长期策略结果。"""

    status: RunStatus
    stop_reason: StopReason
    sample: N9BoundarySample | None
    resources: RunResources


@dataclass
class _DiagnosticsCollector:
    player_count: int
    total_infosets: int
    _visited: dict[int, set[str]] = field(init=False)
    _weights: dict[int, list[float]] = field(init=False)
    _visit_counts: dict[int, int] = field(init=False)
    _non_finite_counts: dict[int, int] = field(init=False)

    def __post_init__(self) -> None:
        self._visited = {traverser: set() for traverser in range(self.player_count)}
        self._weights = {traverser: [] for traverser in range(self.player_count)}
        self._visit_counts = {traverser: 0 for traverser in range(self.player_count)}
        self._non_finite_counts = {traverser: 0 for traverser in range(self.player_count)}

    def add_trace(self, trace: IterationTrace) -> None:
        for passed in trace.passes:
            traverser = passed.traverser
            for visit in passed.traverser_visits:
                self._visit_counts[traverser] += 1
                self._visited[traverser].add(visit.infoset_key)
                if math.isfinite(visit.average_importance_weight):
                    self._weights[traverser].append(visit.average_importance_weight)
                else:
                    self._non_finite_counts[traverser] += 1

    def build(self) -> TrainingDiagnostics:
        coverage = tuple(
            CoverageSummary(
                traverser=traverser,
                visits=self._visit_counts[traverser],
                visited_infosets=len(self._visited[traverser]),
                total_infosets=self.total_infosets,
            )
            for traverser in range(self.player_count)
        )
        weights = tuple(
            ImportanceWeightSummary(
                traverser=traverser,
                visits=self._visit_counts[traverser],
                maximum=max(self._weights[traverser], default=0.0),
                p50=_quantile(self._weights[traverser], 0.5),
                p95=_quantile(self._weights[traverser], 0.95),
                non_finite_count=self._non_finite_counts[traverser],
            )
            for traverser in range(self.player_count)
        )
        return TrainingDiagnostics(coverage=coverage, importance_weights=weights)


def run_controlled_training(
    config: MCCFRConfig,
    limits: RunLimits,
    *,
    monotonic_clock: Callable[[], float],
    rss_reader: Callable[[], int],
    rss_sampler_id: str,
    cancellation_requested: Callable[[], bool] | None = None,
) -> ControlledTrainingResult:
    """在 iteration 边界采样外部资源并合作式停止，不启动子进程。"""

    if not callable(monotonic_clock) or not callable(rss_reader):
        raise ControlError("时钟和 RSS 读取器必须可调用")
    if not isinstance(rss_sampler_id, str) or not rss_sampler_id:
        raise ControlError("RSS 采样器标识必须是非空字符串")
    if cancellation_requested is not None and not callable(cancellation_requested):
        raise ControlError("取消检查器必须可调用")

    trainer = SynchronousExternalSamplingMCCFR(config)
    collector = _DiagnosticsCollector(config.player_count, trainer.infoset_count)
    started_at = _read_clock(monotonic_clock, "起始时间")
    peak_rss = 0
    warning_triggered = False

    def stop_result(reason: StopReason, elapsed_seconds: float) -> ControlledTrainingResult:
        return ControlledTrainingResult(
            status=RunStatus.STOPPED,
            stop_reason=reason,
            completed_iterations=trainer.completed_iterations,
            diagnostics=collector.build(),
            resources=RunResources(
                elapsed_seconds=elapsed_seconds,
                wall_time_limit_seconds=limits.wall_time_seconds,
                peak_rss_bytes=peak_rss,
                rss_warning_bytes=limits.rss_warning_bytes,
                rss_hard_limit_bytes=limits.rss_hard_limit_bytes,
                rss_sampler_id=rss_sampler_id,
                warning_triggered=warning_triggered,
                retained_artifact_bytes=limits.retained_artifact_bytes,
                retained_artifact_limit_bytes=limits.retained_artifact_limit_bytes,
            ),
            result=None,
        )

    def preflight_stop_reason() -> tuple[StopReason | None, float]:
        nonlocal peak_rss, warning_triggered
        elapsed_seconds = _read_elapsed(monotonic_clock, started_at)
        if limits.retained_artifact_bytes >= limits.retained_artifact_limit_bytes:
            return StopReason.ARTIFACT_QUOTA, elapsed_seconds
        if cancellation_requested is not None and cancellation_requested():
            return StopReason.EXTERNAL_CANCELLATION, elapsed_seconds
        rss_bytes = _read_rss(rss_reader)
        peak_rss = max(peak_rss, rss_bytes)
        if rss_bytes >= limits.rss_hard_limit_bytes:
            return StopReason.RSS_HARD_LIMIT, elapsed_seconds
        if rss_bytes >= limits.rss_warning_bytes:
            warning_triggered = True
            return StopReason.RSS_WARNING_LIMIT, elapsed_seconds
        if elapsed_seconds >= limits.wall_time_seconds:
            return StopReason.WALL_TIME_LIMIT, elapsed_seconds
        return None, elapsed_seconds

    reason, elapsed = preflight_stop_reason()
    if reason is not None:
        return stop_result(reason, elapsed)

    while trainer.completed_iterations < config.iterations:
        trainer_trace = trainer.run_iteration(trainer.completed_iterations + 1)
        collector.add_trace(trainer_trace)
        reason, elapsed = preflight_stop_reason()
        if reason is not None:
            return stop_result(reason, elapsed)

    completed_at = _read_elapsed(monotonic_clock, started_at)
    return ControlledTrainingResult(
        status=RunStatus.COMPLETED,
        stop_reason=StopReason.COMPLETED,
        completed_iterations=trainer.completed_iterations,
        diagnostics=collector.build(),
        resources=RunResources(
            elapsed_seconds=completed_at,
            wall_time_limit_seconds=limits.wall_time_seconds,
            peak_rss_bytes=peak_rss,
            rss_warning_bytes=limits.rss_warning_bytes,
            rss_hard_limit_bytes=limits.rss_hard_limit_bytes,
            rss_sampler_id=rss_sampler_id,
            warning_triggered=warning_triggered,
            retained_artifact_bytes=limits.retained_artifact_bytes,
            retained_artifact_limit_bytes=limits.retained_artifact_limit_bytes,
        ),
        result=trainer.completed_result(),
    )


def run_n9_boundary_sample(
    *,
    master_seed: int,
    traverser: int,
    limits: RunLimits,
    monotonic_clock: Callable[[], float],
    rss_reader: Callable[[], int],
    rss_sampler_id: str,
    cancellation_requested: Callable[[], bool] | None = None,
) -> N9BoundaryResult:
    """在显式资源检查下执行 N9 的一条 sampled pass，不创建训练结果。"""

    if not callable(monotonic_clock) or not callable(rss_reader):
        raise ControlError("时钟和 RSS 读取器必须可调用")
    if not isinstance(rss_sampler_id, str) or not rss_sampler_id:
        raise ControlError("RSS 采样器标识必须是非空字符串")
    if cancellation_requested is not None and not callable(cancellation_requested):
        raise ControlError("取消检查器必须可调用")
    started_at = _read_clock(monotonic_clock, "起始时间")
    peak_rss = 0
    warning_triggered = False

    def receipt(reason: StopReason, sample: N9BoundarySample | None) -> N9BoundaryResult:
        elapsed_seconds = _read_elapsed(monotonic_clock, started_at)
        return N9BoundaryResult(
            status=RunStatus.COMPLETED if reason is StopReason.COMPLETED else RunStatus.STOPPED,
            stop_reason=reason,
            sample=sample,
            resources=RunResources(
                elapsed_seconds=elapsed_seconds,
                wall_time_limit_seconds=limits.wall_time_seconds,
                peak_rss_bytes=peak_rss,
                rss_warning_bytes=limits.rss_warning_bytes,
                rss_hard_limit_bytes=limits.rss_hard_limit_bytes,
                rss_sampler_id=rss_sampler_id,
                warning_triggered=warning_triggered,
                retained_artifact_bytes=limits.retained_artifact_bytes,
                retained_artifact_limit_bytes=limits.retained_artifact_limit_bytes,
            ),
        )

    if limits.retained_artifact_bytes >= limits.retained_artifact_limit_bytes:
        return receipt(StopReason.ARTIFACT_QUOTA, None)
    if cancellation_requested is not None and cancellation_requested():
        return receipt(StopReason.EXTERNAL_CANCELLATION, None)
    peak_rss = _read_rss(rss_reader)
    if peak_rss >= limits.rss_hard_limit_bytes:
        return receipt(StopReason.RSS_HARD_LIMIT, None)
    if peak_rss >= limits.rss_warning_bytes:
        warning_triggered = True
        return receipt(StopReason.RSS_WARNING_LIMIT, None)
    if _read_elapsed(monotonic_clock, started_at) >= limits.wall_time_seconds:
        return receipt(StopReason.WALL_TIME_LIMIT, None)

    sample = sample_n9_boundary(master_seed=master_seed, traverser=traverser)
    peak_rss = max(peak_rss, _read_rss(rss_reader))
    if peak_rss >= limits.rss_hard_limit_bytes:
        return receipt(StopReason.RSS_HARD_LIMIT, None)
    if peak_rss >= limits.rss_warning_bytes:
        warning_triggered = True
        return receipt(StopReason.RSS_WARNING_LIMIT, None)
    if _read_elapsed(monotonic_clock, started_at) >= limits.wall_time_seconds:
        return receipt(StopReason.WALL_TIME_LIMIT, None)
    return receipt(StopReason.COMPLETED, sample)


def _quantile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _read_clock(clock: Callable[[], float], label: str) -> float:
    value = clock()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ControlError(f"{label}必须是有限数")
    return float(value)


def _read_elapsed(clock: Callable[[], float], started_at: float) -> float:
    elapsed_seconds = _read_clock(clock, "当前时间") - started_at
    if elapsed_seconds < 0.0:
        raise ControlError("时钟不能倒退")
    return elapsed_seconds


def _read_rss(rss_reader: Callable[[], int]) -> int:
    value = rss_reader()
    return _require_nonnegative_int(value, "RSS 读数")


def _require_positive_finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ControlError(f"{label}必须是有限数")
    if value <= 0.0:
        raise ControlError(f"{label}必须为正数")
    return float(value)


def _require_nonnegative_int(value: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ControlError(f"{label}必须是非负整数")
    return value


def _require_positive_int(value: int, label: str) -> int:
    value = _require_nonnegative_int(value, label)
    if value == 0:
        raise ControlError(f"{label}必须为正整数")
    return value
