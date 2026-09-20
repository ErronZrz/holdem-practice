"""实时 Bot 单次决策延迟的测量口径：逐人数判定、逐街明细与逐场景补充。

本模块只承载口径、冻结模型与纯汇总函数：不采集数据、不读文件、不联网、不写回工件。
预算常量、超时判据（达到或超过硬预算即记超时）与分位法全部复用既有预算模块，不另立一套。
被计时的路径与查表接入状态在报告中显式声明，避免把单条路径的数字读成端到端决策成本。
"""

from collections.abc import Mapping, Sequence
from statistics import median
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.strategy.lookup_budget import (
    DECISION_BUDGET_MS,
    MEASUREMENT_SCOPE,
    P95_GUIDANCE_MS,
    P99_GUIDANCE_MS,
    PLAYER_COUNT_RANGE,
    RECOMMENDED_DECISION_SAMPLES,
    DecisionLatencySummary,
    percentile_ms,
    summarize_decision_latencies,
)

# 被计时路径的标识：报告必须给出它，防止把单一路径的成本读成整条决策链的成本。
MEASURED_DECISION_PATH = "heuristic-action-distribution"
# 离线查表尚未接入运行时决策路径，因此「接入后的实时成本」只能标注为未建模。
LOOKUP_RUNTIME_INTEGRATION_STATUS = "not-integrated-unmodeled"
LOOKUP_RUNTIME_INTEGRATION_NOTE = (
    "离线查表未接入运行时决策路径，接入后的端到端实时成本未建模，本报告不给出该数字"
)

# 逐人数判定必须覆盖的街；元组顺序即报告顺序。
DECISION_STREETS = ("preflop", "flop", "turn", "river")
# 基础场景标识：逐人数判定只由它给出。
BASELINE_SCENARIO = "baseline"
# 补充场景为受控闭集，仅作补充证据。
SUPPLEMENTARY_SCENARIOS = ("deep-stack", "shallow-stack", "strong-draw", "long-session")
# 补充场景聚焦的人数：其余人数必须显式声明未覆盖，不得折算。
SCENARIO_FOCUS_PLAYER_COUNTS = (6, 7, 9)
# 补充场景每个（场景, 人数）的样本量。
SUPPLEMENTARY_DECISION_SAMPLES = 1_000
# 报告允许携带的环境键白名单：不含任何 seed，防止把隐藏信息带入报告。
REPORTED_ENVIRONMENT_KEYS = (
    "platform",
    "python",
    "measured_at_local_time",
    "decision_samples_per_player_count",
    "scenario_samples_per_player_count",
    "state_source",
)


class DecisionLatencyError(ValueError):
    """测量口径或汇总输入不合法时抛出。"""


class _FrozenModel(BaseModel):
    """本模块全部模型的公共基类：冻结、禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class LatencyGroupSummary(_FrozenModel):
    """一个分组（某一街或某一段连续决策）的延迟分布。"""

    label: str
    decision_count: int
    median_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    timeout_count: int
    within_hard_budget: bool

    def model_post_init(self, _context: object) -> None:
        if not self.label:
            raise ValueError("分组标签不能为空")
        if self.decision_count <= 0:
            raise ValueError("分组样本数必须为正")
        if min(self.median_ms, self.p95_ms, self.p99_ms, self.max_ms) < 0.0:
            raise ValueError("延迟分位不能为负")
        if not 0 <= self.timeout_count <= self.decision_count:
            raise ValueError("超时数必须落在样本数范围之内")
        if self.within_hard_budget != (self.timeout_count == 0):
            raise ValueError("硬预算判定必须与超时数一致")


class PlayerCountDecisionLatency(_FrozenModel):
    """一个人数的决策延迟：跨分组合并的判定单元，外加逐分组明细。"""

    player_count: int
    summary: DecisionLatencySummary
    groups: tuple[LatencyGroupSummary, ...]

    def model_post_init(self, _context: object) -> None:
        if self.player_count not in PLAYER_COUNT_RANGE:
            raise ValueError(f"人数 {self.player_count} 不在产品范围内")
        if self.summary.player_count != self.player_count:
            raise ValueError("逐人数汇总与条目人数不一致")
        if not self.groups:
            raise ValueError("逐人数明细至少需要一个分组")
        labels = [group.label for group in self.groups]
        if len(set(labels)) != len(labels):
            raise ValueError("分组标签不能重复")
        if sum(group.decision_count for group in self.groups) != self.summary.decision_count:
            raise ValueError("分组合计样本数必须等于逐人数样本数")


class DecisionCoverageGap(_FrozenModel):
    """未覆盖的测量单元：只带维度与真实原因，不带任何延迟值。"""

    dimension: Literal["player-count", "street"]
    key: str
    reasons: tuple[str, ...]

    def model_post_init(self, _context: object) -> None:
        if not self.key:
            raise ValueError("未覆盖单元的键不能为空")
        if not self.reasons:
            raise ValueError("未覆盖单元必须声明原因")


class DecisionScenarioLatency(_FrozenModel):
    """一个测量场景：逐人数结果 + 街范围 + 未覆盖声明。

    硬要求：已测人数与未覆盖人数的并集必须恰为产品声称支持的人数范围，
    不得缺项、不得重复、不得同时判为已测与未覆盖。
    """

    scenario: str
    description: str
    streets: tuple[str, ...]
    player_counts: tuple[PlayerCountDecisionLatency, ...]
    uncovered: tuple[DecisionCoverageGap, ...] = ()

    def model_post_init(self, _context: object) -> None:
        if self.scenario not in (BASELINE_SCENARIO, *SUPPLEMENTARY_SCENARIOS):
            raise ValueError(f"未知场景标识：{self.scenario}")
        if not self.description:
            raise ValueError("场景必须给出说明")
        if not self.streets:
            raise ValueError("场景必须声明街范围")
        if len(set(self.streets)) != len(self.streets):
            raise ValueError("场景街范围不能重复")
        if not set(self.streets) <= set(DECISION_STREETS):
            raise ValueError("场景街范围必须是已知街的子集")
        if tuple(sorted(self.streets, key=DECISION_STREETS.index)) != self.streets:
            raise ValueError("场景街范围必须按固定顺序给出")

        measured = [entry.player_count for entry in self.player_counts]
        if len(set(measured)) != len(measured):
            raise ValueError("已测人数不能重复")
        for entry in self.player_counts:
            if tuple(group.label for group in entry.groups) != self.streets:
                raise ValueError("分组标签必须恰等于场景声明的街范围")

        for gap in self.uncovered:
            if gap.dimension == "player-count":
                if not gap.key.isdigit() or int(gap.key) not in PLAYER_COUNT_RANGE:
                    raise ValueError(f"未覆盖人数键不合法：{gap.key}")
            elif gap.key not in DECISION_STREETS:
                raise ValueError(f"未覆盖街键不合法：{gap.key}")

        count_keys = [gap.key for gap in self.uncovered if gap.dimension == "player-count"]
        street_keys = [gap.key for gap in self.uncovered if gap.dimension == "street"]
        if len(set(count_keys)) != len(count_keys):
            raise ValueError("未覆盖人数不能重复")
        if len(set(street_keys)) != len(street_keys):
            raise ValueError("未覆盖街不能重复")
        overlap = {int(key) for key in count_keys} & set(measured)
        if overlap:
            raise ValueError(f"人数同时被判为已测与未覆盖：{sorted(overlap)}")
        accounted = {int(key) for key in count_keys} | set(measured)
        if accounted != set(PLAYER_COUNT_RANGE):
            raise ValueError(f"逐人数覆盖必须完整给出：{sorted(accounted)}")
        if set(street_keys) != set(DECISION_STREETS) - set(self.streets):
            raise ValueError("街缺口必须恰为场景未覆盖的街")

    @property
    def measured_player_counts(self) -> tuple[int, ...]:
        """有实测延迟的人数。"""
        return tuple(sorted(entry.player_count for entry in self.player_counts))

    @property
    def uncovered_player_counts(self) -> tuple[int, ...]:
        """无实测延迟的人数。"""
        return tuple(
            sorted(int(gap.key) for gap in self.uncovered if gap.dimension == "player-count")
        )


class DecisionLatencyReport(_FrozenModel):
    """逐人数延迟报告：基础场景给出判定，补充场景作补充证据。

    报告不含任何均值、合计或加权字段，因此「用一个人数的汇总冒充全人数通过」不可表达。
    """

    scope: str = MEASUREMENT_SCOPE
    measured_path: str = MEASURED_DECISION_PATH
    lookup_runtime_integration: str = LOOKUP_RUNTIME_INTEGRATION_STATUS
    lookup_runtime_integration_note: str = LOOKUP_RUNTIME_INTEGRATION_NOTE
    decision_budget_ms: float = DECISION_BUDGET_MS
    p95_guidance_ms: float = P95_GUIDANCE_MS
    p99_guidance_ms: float = P99_GUIDANCE_MS
    recommended_decision_samples: int = RECOMMENDED_DECISION_SAMPLES
    environment: dict[str, str] = Field(default_factory=dict)
    baseline: DecisionScenarioLatency
    supplements: tuple[DecisionScenarioLatency, ...] = ()

    def model_post_init(self, _context: object) -> None:
        if self.baseline.scenario != BASELINE_SCENARIO:
            raise ValueError(f"基础场景标识必须是 {BASELINE_SCENARIO}")
        names = [item.scenario for item in self.supplements]
        if len(set(names)) != len(names):
            raise ValueError("补充场景标识不能重复")
        if BASELINE_SCENARIO in names:
            raise ValueError("补充场景不得复用基础场景标识")
        unknown = set(self.environment) - set(REPORTED_ENVIRONMENT_KEYS)
        if unknown:
            raise ValueError(f"报告环境字段不在白名单内：{sorted(unknown)}")

    @property
    def all_within_hard_budget(self) -> bool:
        """全部已测人数是否都未观察到超预算决策。"""
        return all(entry.summary.within_hard_budget for entry in self.baseline.player_counts)

    @property
    def timeout_player_counts(self) -> tuple[int, ...]:
        """观察到超预算决策的人数。"""
        return tuple(
            sorted(
                entry.player_count
                for entry in self.baseline.player_counts
                if entry.summary.timeout_count > 0
            )
        )


def summarize_latency_group(label: str, samples_ms: Sequence[float]) -> LatencyGroupSummary:
    """汇总一个分组的延迟分布；分位法与超时判据沿用既有预算口径。"""
    if not label:
        raise DecisionLatencyError("分组标签不能为空")
    if not samples_ms:
        raise DecisionLatencyError("分组汇总需要非空样本")
    ordered = sorted(float(sample) for sample in samples_ms)
    if ordered[0] < 0.0:
        raise DecisionLatencyError("延迟样本不能为负")
    timeout_count = sum(1 for sample in ordered if sample >= DECISION_BUDGET_MS)
    return LatencyGroupSummary(
        label=label,
        decision_count=len(ordered),
        median_ms=float(median(ordered)),
        p95_ms=percentile_ms(ordered, 0.95),
        p99_ms=percentile_ms(ordered, 0.99),
        max_ms=ordered[-1],
        timeout_count=timeout_count,
        within_hard_budget=timeout_count == 0,
    )


def summarize_player_count_latency(
    player_count: int,
    samples_by_group: Mapping[str, Sequence[float]],
) -> PlayerCountDecisionLatency:
    """汇总一个人数：逐分组明细，外加跨分组合并后的逐人数判定单元。"""
    if player_count not in PLAYER_COUNT_RANGE:
        raise DecisionLatencyError(f"人数 {player_count} 不在产品范围内")
    if not samples_by_group:
        raise DecisionLatencyError("逐人数汇总至少需要一个分组")
    labels = list(samples_by_group)
    if len(set(labels)) != len(labels):
        raise DecisionLatencyError("分组标签不能重复")
    groups = tuple(summarize_latency_group(label, samples_by_group[label]) for label in labels)
    combined: list[float] = []
    for label in labels:
        combined.extend(float(sample) for sample in samples_by_group[label])
    if not combined:
        raise DecisionLatencyError("逐人数汇总需要非空样本")
    return PlayerCountDecisionLatency(
        player_count=player_count,
        summary=summarize_decision_latencies(player_count, combined),
        groups=groups,
    )


def build_decision_latency_report(
    *,
    environment: Mapping[str, str],
    baseline: DecisionScenarioLatency,
    supplements: Sequence[DecisionScenarioLatency] = (),
) -> DecisionLatencyReport:
    """装配报告：入口级显式失败，场景内部一致性由模型自身保证。"""
    if not environment:
        raise DecisionLatencyError("报告必须给出环境快照")
    for key, value in environment.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise DecisionLatencyError("环境字段必须是字符串键值")
    unknown = set(environment) - set(REPORTED_ENVIRONMENT_KEYS)
    if unknown:
        raise DecisionLatencyError(f"环境字段不在白名单内：{sorted(unknown)}")
    if baseline.scenario != BASELINE_SCENARIO:
        raise DecisionLatencyError(f"基础场景标识必须是 {BASELINE_SCENARIO}")
    names = [item.scenario for item in supplements]
    if len(set(names)) != len(names):
        raise DecisionLatencyError("补充场景标识不能重复")
    if BASELINE_SCENARIO in names:
        raise DecisionLatencyError("补充场景不得复用基础场景标识")
    return DecisionLatencyReport(
        environment=dict(environment),
        baseline=baseline,
        supplements=tuple(supplements),
    )
