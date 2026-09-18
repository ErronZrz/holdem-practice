"""实时 lookup 的预算口径与测量汇总。

本模块只承载预算常量、汇总模型与纯汇总函数：不读文件、不联网、不采集数据。
真实测量在显式 opt-in 入口中进行，默认测试路径不触发任何真实产物加载。
报告只描述本机单机型观测，不外推云环境或生产容量。
"""

import math
from collections.abc import Sequence
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from app.strategy.abstraction import FallbackDeclaration
from app.strategy.artifact import ArtifactIdentity, LookupStatus

# 单次决策硬预算：达到或超过即判失败，不放宽。
DECISION_BUDGET_MS = 100.0
# 建议余量：用于判断是否留有余量，不是门槛。
P95_GUIDANCE_MS = 50.0
P99_GUIDANCE_MS = 80.0
# 建议的逐人数决策样本量。
RECOMMENDED_DECISION_SAMPLES = 10_000
# 平台已有的 idle 内存对照上界（数百 MB 量级）：仅作对照，本轮不新设门槛。
PLATFORM_IDLE_MEMORY_REFERENCE_BYTES = 512 * 1024 * 1024
# 测量范围声明：本机单机型观测。
MEASUREMENT_SCOPE = "local-machine-single-host-observation"

# 产品声称统一支持的人数范围：逐人数报告必须完整覆盖它。
PLAYER_COUNT_RANGE = (2, 3, 4, 5, 6, 7, 8, 9)


class LookupBudgetError(ValueError):
    """预算或汇总输入不合法时抛出。"""


class _FrozenModel(BaseModel):
    """本模块全部模型的公共基类：冻结、禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ArtifactLoadSummary(_FrozenModel):
    """一次冷加载观测：加载耗时与进程峰值常驻内存。"""

    player_count: int
    identity: ArtifactIdentity
    artifact_bytes: int
    infoset_count: int
    cold_load_ms: float
    # 进程峰值常驻内存的采集口径为「子进程峰值」，不是产物独占增量；未采集到则为空。
    peak_rss_bytes: int | None = None


class DecisionLatencySummary(_FrozenModel):
    """一个查询路径的逐人数延迟分布。"""

    player_count: int
    decision_count: int
    median_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    timeout_count: int
    within_hard_budget: bool
    meets_p95_guidance: bool
    meets_p99_guidance: bool


class PlayerCountCoverage(_FrozenModel):
    """一个未被覆盖的人数：给出真实状态、原因与回退来源声明。"""

    player_count: int
    status: LookupStatus
    abstraction_key: str | None = None
    reasons: tuple[str, ...] = ()
    fallback: FallbackDeclaration


class LookupBudgetReport(_FrozenModel):
    """逐人数报告：有产物的给实测值，无产物的给显式状态与回退声明。"""

    scope: str = MEASUREMENT_SCOPE
    decision_budget_ms: float = DECISION_BUDGET_MS
    p95_guidance_ms: float = P95_GUIDANCE_MS
    p99_guidance_ms: float = P99_GUIDANCE_MS
    recommended_decision_samples: int = RECOMMENDED_DECISION_SAMPLES
    idle_memory_reference_bytes: int = PLATFORM_IDLE_MEMORY_REFERENCE_BYTES
    environment: dict[str, str] = Field(default_factory=dict)
    loads: tuple[ArtifactLoadSummary, ...] = ()
    latencies: tuple[DecisionLatencySummary, ...] = ()
    uncovered: tuple[PlayerCountCoverage, ...] = ()

    @property
    def measured_player_counts(self) -> tuple[int, ...]:
        """有实测延迟的人数。"""
        return tuple(sorted(item.player_count for item in self.latencies))

    @property
    def uncovered_player_counts(self) -> tuple[int, ...]:
        """无实测延迟的人数。"""
        return tuple(sorted(item.player_count for item in self.uncovered))

    @property
    def all_within_hard_budget(self) -> bool:
        """全部实测人数是否都未观察到超预算查询。"""
        return all(item.within_hard_budget for item in self.latencies)


def percentile_ms(samples_ms: Sequence[float], quantile: float) -> float:
    """按最近秩法计算分位点：返回不小于 ``quantile * 样本数`` 的最小秩对应样本。"""
    if not samples_ms:
        raise LookupBudgetError("分位点计算需要非空样本")
    if not 0.0 < quantile <= 1.0:
        raise LookupBudgetError("分位点必须位于 (0, 1]")
    ordered = sorted(float(sample) for sample in samples_ms)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def summarize_decision_latencies(
    player_count: int,
    samples_ms: Sequence[float],
) -> DecisionLatencySummary:
    """汇总一次逐人数延迟观测：中位数取真实中位数，分位点取最近秩。"""
    if player_count not in PLAYER_COUNT_RANGE:
        raise LookupBudgetError(f"人数 {player_count} 不在产品范围内")
    if not samples_ms:
        raise LookupBudgetError("延迟汇总需要非空样本")
    ordered = sorted(float(sample) for sample in samples_ms)
    if ordered[0] < 0.0:
        raise LookupBudgetError("延迟样本不能为负")
    p95_ms = percentile_ms(ordered, 0.95)
    p99_ms = percentile_ms(ordered, 0.99)
    timeout_count = sum(1 for sample in ordered if sample >= DECISION_BUDGET_MS)
    return DecisionLatencySummary(
        player_count=player_count,
        decision_count=len(ordered),
        median_ms=float(median(ordered)),
        p95_ms=p95_ms,
        p99_ms=p99_ms,
        max_ms=ordered[-1],
        timeout_count=timeout_count,
        within_hard_budget=timeout_count == 0,
        meets_p95_guidance=p95_ms < P95_GUIDANCE_MS,
        meets_p99_guidance=p99_ms < P99_GUIDANCE_MS,
    )


def artifact_load_summary(
    *,
    identity: ArtifactIdentity,
    player_count: int,
    infoset_count: int,
    cold_load_ms: float,
    peak_rss_bytes: int | None = None,
) -> ArtifactLoadSummary:
    """汇总一次冷加载观测。"""
    if player_count not in PLAYER_COUNT_RANGE:
        raise LookupBudgetError(f"人数 {player_count} 不在产品范围内")
    if cold_load_ms < 0.0:
        raise LookupBudgetError("冷加载耗时不能为负")
    if infoset_count <= 0:
        raise LookupBudgetError("信息集条数必须为正")
    return ArtifactLoadSummary(
        player_count=player_count,
        identity=identity,
        artifact_bytes=identity.byte_length,
        infoset_count=infoset_count,
        cold_load_ms=cold_load_ms,
        peak_rss_bytes=peak_rss_bytes,
    )


def build_report(
    *,
    environment: dict[str, str],
    loads: Sequence[ArtifactLoadSummary],
    latencies: Sequence[DecisionLatencySummary],
    uncovered: Sequence[PlayerCountCoverage],
) -> LookupBudgetReport:
    """装配逐人数报告；人数必须无重复且完整覆盖产品范围。"""
    load_counts = [item.player_count for item in loads]
    measured_counts = [item.player_count for item in latencies]
    uncovered_counts = [item.player_count for item in uncovered]
    for label, counts in (
        ("冷加载", load_counts),
        ("延迟", measured_counts),
        ("未覆盖", uncovered_counts),
    ):
        if len(set(counts)) != len(counts):
            raise LookupBudgetError(f"{label}人数出现重复")
    overlap = set(measured_counts) & set(uncovered_counts)
    if overlap:
        raise LookupBudgetError(f"人数同时被判为已测与未覆盖：{sorted(overlap)}")
    covered = set(measured_counts) | set(uncovered_counts)
    if covered != set(PLAYER_COUNT_RANGE):
        raise LookupBudgetError(f"逐人数报告必须完整覆盖 {PLAYER_COUNT_RANGE}")
    if not set(measured_counts) <= set(load_counts):
        raise LookupBudgetError("存在有延迟实测但没有冷加载观测的人数")
    return LookupBudgetReport(
        environment=dict(environment),
        loads=tuple(loads),
        latencies=tuple(latencies),
        uncovered=tuple(uncovered),
    )
