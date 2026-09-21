"""新 Bot 的离线验证报告与显式 opt-in 运行入口（测试侧永久能力）。

纪律：
- 只有被显式调用时才会运行；默认 pytest 不触发任何性能矩阵或对抗对局；
- 运行前必须显式给出已冻结清单与允许执行的阶段，阶段 B 还必须有阶段 A 的实测回执；
- 不访问、不修改任何封存 campaign 目录；输出目录只创建、不覆盖已有文件。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import platform
import statistics
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.engine import PokerEngine
from app.poker.state import GameState, Street
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.lookup_budget import (
    DECISION_BUDGET_MS,
    P95_GUIDANCE_MS,
    P99_GUIDANCE_MS,
    percentile_ms,
)
from app.strategy.mixed_context import (
    MixedSummaryTracker,
    mixed_state,
    require_mixed_input,
)
from app.strategy.mixed_policy import HandMode, MixedStyle
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MixedLocalStrategy,
    MixedSeatPolicy,
)
from app.strategy.projection import project_for_actor

from .mixed_bot_states import (
    MIXED_APPLICABLE_NODE_COUNT,
    MIXED_BIG_BLIND,
    MIXED_DEPTHS_BB,
    MIXED_PLANNED_SLOT_COUNT,
    MIXED_PLAYER_COUNTS,
    MIXED_SMALL_BLIND,
    MIXED_STREETS,
    MIXED_STRUCTURAL_HOLE_COUNT,
    MixedFixtureManifest,
    MixedNodeFixture,
    apply_node,
)

MIXED_VALIDATION_SCHEMA_VERSION = "mixed-validation.v1"
# 验证身份独立于候选 A 的 campaign / evaluator，不是任何既有授权的续用。
MIXED_VALIDATION_IDENTITY = "mixed-local-v1-validation"
# 复用既有主种子数值，但必须重新获得产品验证运行许可。
MIXED_MAIN_SEEDS: tuple[int, ...] = (1215, 20260918, 3311, 7926)
MIXED_HAND_MODES: tuple[HandMode, ...] = (
    HandMode.NORMAL,
    HandMode.CAUTIOUS,
    HandMode.PRESSED,
)
# 直接分布总数：125 个可行动节点 × 3 风格 × 3 模式。
MIXED_DIRECT_DISTRIBUTION_COUNT = MIXED_APPLICABLE_NODE_COUNT * len(MixedStyle) * len(
    MIXED_HAND_MODES
)

# 正式成本矩阵：逐人数 10000 次决策，36 格（街 × 风格 × 深度）按顺序分配。
COST_DECISIONS_PER_PLAYER_COUNT = 10_000
COST_CELLS_PER_PLAYER_COUNT = 36
COST_CELL_QUOTA_FIRST = 278
COST_CELL_QUOTA_REST = 277
# 补充小型测试：逐人数每类 10 次，共 240 次，与主矩阵分开报告。
SUPPLEMENTARY_CLASSES: tuple[str, ...] = ("short-stack", "long-history", "uint64-endpoints")
SUPPLEMENTARY_SAMPLES_PER_CELL = 10
SUPPLEMENTARY_TOTAL_SAMPLES = (
    len(SUPPLEMENTARY_CLASSES) * len(MIXED_PLAYER_COUNTS) * SUPPLEMENTARY_SAMPLES_PER_CELL
)
LONG_HISTORY_EVENT_CAP = 256

# 抗针对第一批：四个固定对手族、两种 arm、相对座位轮换。
ADVERSARIAL_OPPONENT_FAMILIES: tuple[str, ...] = (
    "random@1",
    "heuristic@1",
    "passive-call-probe",
    "fixed-pressure-probe",
)
ADVERSARIAL_ARMS: tuple[str, ...] = ("mixed-focus", "legacy-focus")
ADVERSARIAL_MAX_VOLUNTARY_ACTIONS = 256
ADVERSARIAL_HANDS = (
    len(MIXED_MAIN_SEEDS)
    * len(MixedStyle)
    * len(ADVERSARIAL_OPPONENT_FAMILIES)
    * len(ADVERSARIAL_ARMS)
    * sum(MIXED_PLAYER_COUNTS)
)
INTERVAL_STATUS_NOT_ESTIMATED = "not-estimated-small-fixed-seed-set"

# 阶段 A 的分层子集与阶段预算提案（待批准上限，不是已获预算）。
STAGE_A_COST_SAMPLES = 288
STAGE_A_SUPPLEMENTARY_SAMPLES = 24
STAGE_A_ADVERSARIAL_HANDS = 64
STAGE_A_WALL_SECONDS = 120.0
STAGE_AB_WALL_SECONDS = 1800.0
STAGE_RSS_BYTES = 1024 * 1024 * 1024
STAGE_OUTPUT_BYTES = 100 * 1024 * 1024

MIXED_VALIDATION_LIMITATIONS: tuple[str, ...] = (
    "规则评分是启发式分数，不是概率、EV、GTO 或均衡结论。",
    "单元测试与有界评测只证明契约与机制，不构成对手强度认证。",
    "四个固定主种子块不出具具有总体覆盖承诺的置信区间。",
    "有限样本不能证明未来不会超预算，也不向 2–9 人以外外推。",
    "本报告的记录口径与离线训练产物的记录口径不是同一回事。",
)


class MixedValidationAuthorizationError(RuntimeError):
    """缺少显式阶段许可、清单或前置回执时抛出；不做任何静默运行。"""


# ------------------------------------------------------------------ 报告模型


class _FrozenModel(BaseModel):
    """报告族的公共基类：冻结且禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class MixedLatencyPath(_FrozenModel):
    """单一计时对象的延迟分布；不同计时对象不得混读。"""

    samples: int = Field(ge=0)
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    timeout_count: int = Field(ge=0)


class MixedValidationTiming(_FrozenModel):
    """决策路径、执行路径与摘要更新耗时，分列不合并。"""

    decision_budget_ms: float = DECISION_BUDGET_MS
    p95_guidance_ms: float = P95_GUIDANCE_MS
    p99_guidance_ms: float = P99_GUIDANCE_MS
    decision_path: MixedLatencyPath | None = None
    engine_apply: MixedLatencyPath | None = None
    public_summary_update: MixedLatencyPath | None = None
    supplementary_decision_path: MixedLatencyPath | None = None
    bot_step: MixedLatencyPath | None = None
    timing_note: str = (
        "decision_path 是完整单次 Bot 决策计算，不含 apply；执行、摘要更新与补充场景另报；"
        "50/80ms 只是指导值，不是新门槛。"
    )


class MixedStyleBehavior(_FrozenModel):
    """单一风格在预冻结节点上的直接分布指标。"""

    style: str
    distributions: int = Field(ge=0)
    action_entropy: float | None = None
    scale_entropy: float | None = None
    effective_scale_count: int = Field(ge=0)
    structural_single_size: int = Field(ge=0)
    no_active_candidate: int = Field(ge=0)


class MixedValidationBehavior(_FrozenModel):
    """行为报告：条件动作熵与尺度熵按风格分列，分组先于结果固定。"""

    direct_distributions: int = Field(ge=0)
    styles: tuple[MixedStyleBehavior, ...]
    behavior_note: str = (
        "指标来自预冻结节点的直接分布，不靠抽样估计；手模式由内部接口显式指定。"
    )


class MixedMatchFamilyRow(_FrozenModel):
    """一组对抗对照的结果行。"""

    player_count: int
    style: str
    opponent: str
    arm: str
    hands: int = Field(ge=0)
    truncated_hands: int = Field(ge=0)
    net_chips: int
    bb_per_100: float | None = None


class MixedValidationMatches(_FrozenModel):
    """对抗对照汇总：固定种子块，明确不估计总体区间。"""

    planned_hands: int = Field(ge=0)
    completed_hands: int = Field(ge=0)
    truncated_hands: int = Field(ge=0)
    seed_blocks: tuple[int, ...]
    interval_status: str = INTERVAL_STATUS_NOT_ESTIMATED
    rows: tuple[MixedMatchFamilyRow, ...]
    matches_note: str = "机械探针不是 best response；胜过随机或旧启发式不等于强度认证。"


class MixedValidationCoverage(_FrozenModel):
    """覆盖情况：已测、未测与结构性不适用分列，不挑好看的节点。"""

    planned_nodes: int = Field(ge=0)
    executed_nodes: int = Field(ge=0)
    not_run_nodes: int = Field(ge=0)
    structurally_not_applicable: int = Field(ge=0)
    cost_cells_planned: int = Field(ge=0)
    cost_cells_executed: int = Field(ge=0)
    supplementary_samples_planned: int = Field(ge=0)
    supplementary_samples_executed: int = Field(ge=0)
    adversarial_hands_planned: int = Field(ge=0)
    adversarial_hands_executed: int = Field(ge=0)


class MixedValidationEnvironment(_FrozenModel):
    """运行环境：本机单机型观测，不外推生产容量。"""

    python_version: str
    platform: str
    cpu_count: int
    scope: str = "local-machine-single-host-observation"
    startup_note: str = "冷导入、建局与首手初始化不计入 decision_path，另行报告。"


class MixedValidationResources(_FrozenModel):
    """资源占用与阶段预算对照。"""

    wall_seconds: float = Field(ge=0.0)
    cpu_seconds: float = Field(ge=0.0)
    peak_rss_bytes: int | None = None
    output_bytes: int = Field(ge=0)
    single_process: bool
    parallel: bool
    budget_note: str = "预算上限为待批准提案；触发即停止并如实报告，不自行扩容。"


class MixedReportViolation(_FrozenModel):
    """一条已记录的越界或失败样本，不删除、不按结果换 seed。"""

    kind: str
    detail: str


class MixedValidationReport(_FrozenModel):
    """新 Bot 的离线验证报告；字段闭集，不夹带底牌、种子或任意元数据。"""

    schema_version: Literal["mixed-validation.v1"] = MIXED_VALIDATION_SCHEMA_VERSION
    strategy_id: str
    code_identity: str
    config_digest: str
    manifest_digest: str
    stage: Literal["A", "B"]
    status: str
    environment: MixedValidationEnvironment
    coverage: MixedValidationCoverage
    timing: MixedValidationTiming
    behavior: MixedValidationBehavior
    matches: MixedValidationMatches
    resources: MixedValidationResources
    violations: tuple[MixedReportViolation, ...] = ()
    limitations: tuple[str, ...] = MIXED_VALIDATION_LIMITATIONS

    @model_validator(mode="after")
    def _require_honest_status(self) -> MixedValidationReport:
        if self.status != "completed" and not self.status.startswith("stopped-"):
            raise ValueError("状态只能是 completed 或 stopped-*")
        return self


# ------------------------------------------------------------------ 测试侧探针


class PassiveCallProbe:
    """被动跟注探针：优先过牌，其次跟注，否则弃牌；从不主动下注。"""

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        if legal.can_check:
            return Action(ActionType.CHECK)
        if legal.can_call:
            return Action(ActionType.CALL)
        if legal.can_fold:
            return Action(ActionType.FOLD)
        raise MixedValidationAuthorizationError("被动跟注探针没有任何合法候选")


class FixedPressureProbe:
    """固定施压探针：只要可以主动就投入一个底池大小，不套人格或危险尺度过滤。"""

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        player = state.players[state.current_seat]
        target = player.street_bet + legal.call_amount + max(
            MIXED_BIG_BLIND, state.pot + legal.actual_call_amount
        )
        if legal.can_bet:
            return Action(ActionType.BET, min(max(target, legal.min_bet), legal.max_bet))
        if legal.can_raise:
            raise_to = min(max(target, legal.min_raise_to), legal.max_raise_to)
            return Action(ActionType.RAISE, raise_to)
        if legal.can_check:
            return Action(ActionType.CHECK)
        if legal.can_call:
            return Action(ActionType.CALL)
        if legal.can_fold:
            return Action(ActionType.FOLD)
        raise MixedValidationAuthorizationError("固定施压探针没有任何合法候选")


# ------------------------------------------------------------------ 派生与计时


def _derive_key(parent_key: bytes, message: Sequence[object]) -> bytes:
    payload = json.dumps(list(message), separators=(",", ":"), ensure_ascii=True)
    return hmac.new(parent_key, payload.encode("utf-8"), hashlib.sha256).digest()


def validation_root_key(seed: int) -> bytes:
    """验证分支的根键：只由验证身份与主种子派生，不进入产品运行时。"""
    material = f"{MIXED_VALIDATION_IDENTITY}:{seed}".encode()
    return hashlib.sha256(material).digest()


def adversarial_deck_seed(seed: int, player_count: int, rotation: int) -> int:
    """牌堆派生流：消息不含焦点 arm 或人格，保证两 arm 使用同一合法初态。"""
    digest = _derive_key(validation_root_key(seed), ("deck", player_count, rotation))
    return int.from_bytes(digest, "big")


def focus_seat_key(seed: int, style: str, player_count: int, rotation: int) -> bytes:
    """焦点策略的派生键：只有新焦点流区分风格，旧 arm 不使用它。"""
    return _derive_key(
        validation_root_key(seed),
        ("focus", style, player_count, rotation),
    )


def summarize_path(samples_ms: Sequence[float]) -> MixedLatencyPath:
    """按既有最近秩口径汇总一条计时路径。"""
    if not samples_ms:
        return MixedLatencyPath(
            samples=0, p50_ms=0.0, p95_ms=0.0, p99_ms=0.0, max_ms=0.0, timeout_count=0
        )
    ordered = sorted(samples_ms)
    return MixedLatencyPath(
        samples=len(ordered),
        p50_ms=float(statistics.median(ordered)),
        p95_ms=percentile_ms(ordered, 0.95),
        p99_ms=percentile_ms(ordered, 0.99),
        max_ms=ordered[-1],
        timeout_count=sum(1 for value in ordered if value >= DECISION_BUDGET_MS),
    )


@dataclass(frozen=True)
class DecisionTiming:
    """一次决策的各段耗时，单位毫秒。"""

    decision_path_ms: float
    engine_apply_ms: float
    summary_update_ms: float


def _require_within_legal(action: Action, legal: LegalActions) -> None:
    """在提交之前复核候选是否落在合法区间，与引擎同一套口径。"""
    if action.type is ActionType.BET and not (
        legal.can_bet and legal.min_bet <= action.amount <= legal.max_bet
    ):
        raise MixedValidationAuthorizationError("候选 BET 落在合法区间之外")
    if action.type is ActionType.RAISE and not (
        legal.can_raise and legal.min_raise_to <= action.amount <= legal.max_raise_to
    ):
        raise MixedValidationAuthorizationError("候选 RAISE 落在合法区间之外")
    if action.type is ActionType.FOLD and not legal.can_fold:
        raise MixedValidationAuthorizationError("候选 FOLD 非法")
    if action.type is ActionType.CHECK and not legal.can_check:
        raise MixedValidationAuthorizationError("候选 CHECK 非法")
    if action.type is ActionType.CALL and not legal.can_call:
        raise MixedValidationAuthorizationError("候选 CALL 非法")


def measure_decision(
    engine: PokerEngine,
    tracker: MixedSummaryTracker,
    strategy: MixedLocalStrategy,
) -> DecisionTiming:
    """计时一次完整决策：脱敏/摘要/特征/分布/采样/候选校验，再单独计时执行。"""
    started = time.perf_counter()
    state = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    legal = engine.legal_actions()
    action = strategy.choose_action(state, legal)
    _require_within_legal(action, legal)
    decision_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    engine.apply_action(action)
    apply_ms = (time.perf_counter() - started) * 1000.0

    started = time.perf_counter()
    tracker.consume_after_action(engine.history)
    summary_ms = (time.perf_counter() - started) * 1000.0
    return DecisionTiming(decision_ms, apply_ms, summary_ms)


# ------------------------------------------------------------------ 分布指标


def _entropy(weights: Iterable[float]) -> float | None:
    values = [value for value in weights if value > 0]
    total = sum(values)
    if total <= 0:
        return None
    return -sum((value / total) * math.log2(value / total) for value in values)


def distribution_metrics(
    distribution: object,
) -> tuple[float | None, float | None, int, int]:
    """返回（条件动作熵、尺度熵、有效尺寸数、是否结构性单尺寸）。"""
    by_action: dict[ActionType, int] = {}
    for item in distribution.candidates:
        by_action[item.action] = by_action.get(item.action, 0) + item.units
    action_entropy = _entropy(by_action.values())
    scales: dict[int, int] = {}
    for item in distribution.candidates:
        if item.units > 0 and item.action in (ActionType.BET, ActionType.RAISE):
            scales[item.amount] = scales.get(item.amount, 0) + item.units
    if not scales:
        return action_entropy, None, 0, 0
    return action_entropy, _entropy(scales.values()), len(scales), 1 if len(scales) == 1 else 0


@dataclass
class _BehaviorBucket:
    """一种风格的累计指标桶。"""

    distributions: int = 0
    action_entropies: list[float] = field(default_factory=list)
    scale_entropies: list[float] = field(default_factory=list)
    effective_scales: int = 0
    single_size: int = 0
    no_active: int = 0


def collect_behavior(
    manifest: MixedFixtureManifest,
    *,
    mode: HandMode | None = None,
) -> MixedValidationBehavior:
    """在预冻结节点上计算三种风格 × 三种模式的直接分布指标。"""
    buckets = {style.value: _BehaviorBucket() for style in MixedStyle}
    total = 0
    modes = MIXED_HAND_MODES if mode is None else (mode,)
    for fixture in manifest.nodes:
        applied = apply_node(fixture)
        verified = require_mixed_input(applied.actor_state())
        legal = applied.legal_actions()
        for style in MixedStyle:
            # 离线按风格逐一覆盖，生产分配仍由座位升序循环决定。
            policy = MixedSeatPolicy(
                seat=verified.actor_seat,
                style=style,
                seat_key=focus_seat_key(
                    int(manifest.seeds[0]), style.value, fixture.player_count, 0
                ),
            )
            bucket = buckets[style.value]
            for hand_mode in modes:
                distribution = policy.distribution_for(verified, legal, hand_mode)
                action_entropy, scale_entropy, scale_count, single = distribution_metrics(
                    distribution
                )
                bucket.distributions += 1
                total += 1
                if action_entropy is not None:
                    bucket.action_entropies.append(action_entropy)
                if scale_entropy is not None:
                    bucket.scale_entropies.append(scale_entropy)
                bucket.effective_scales += scale_count
                bucket.single_size += single
                bucket.no_active += 0 if scale_count else 1
    rows = tuple(
        MixedStyleBehavior(
            style=style.value,
            distributions=buckets[style.value].distributions,
            action_entropy=(
                statistics.fmean(buckets[style.value].action_entropies)
                if buckets[style.value].action_entropies
                else None
            ),
            scale_entropy=(
                statistics.fmean(buckets[style.value].scale_entropies)
                if buckets[style.value].scale_entropies
                else None
            ),
            effective_scale_count=buckets[style.value].effective_scales,
            structural_single_size=buckets[style.value].single_size,
            no_active_candidate=buckets[style.value].no_active,
        )
        for style in MixedStyle
    )
    return MixedValidationBehavior(direct_distributions=total, styles=rows)


# ------------------------------------------------------------------ 成本矩阵


def cost_cells() -> tuple[tuple[Street, str, int], ...]:
    """逐人数 36 格：街 × 风格 × 深度，按街、风格、深度顺序展开。"""
    return tuple(
        (street, style.value, depth)
        for street in MIXED_STREETS
        for style in MixedStyle
        for depth in MIXED_DEPTHS_BB
    )


def cell_quota(index: int) -> int:
    """前 28 格每格 278 次、其余 8 格每格 277 次，合计恰好 10000。"""
    return COST_CELL_QUOTA_FIRST if index < 28 else COST_CELL_QUOTA_REST


def _fixture_street(fixture: MixedNodeFixture) -> Street:
    return fixture.actions[-1].street if fixture.actions else Street.PREFLOP


def run_cost_matrix(
    manifest: MixedFixtureManifest,
    *,
    stage: Literal["A", "B"],
    player_count: int,
) -> tuple[list[float], list[float], list[float], int, int]:
    """按限额逐格计时，返回原始耗时样本与（已执行格数、计划样本数）。"""
    fixtures = manifest.nodes_for(player_count)
    by_street: dict[Street, list[MixedNodeFixture]] = {}
    for fixture in fixtures:
        by_street.setdefault(_fixture_street(fixture), []).append(fixture)

    decision: list[float] = []
    apply_ms: list[float] = []
    summary_ms: list[float] = []
    cursors: dict[Street, int] = {}
    executed_cells = 0
    planned_samples = 0
    for index, (street, style, depth) in enumerate(cost_cells()):
        quota = 1 if stage == "A" else cell_quota(index)
        planned_samples += quota
        candidates = by_street.get(street)
        if not candidates:
            continue
        cursor = cursors.get(street, 0)
        cursors[street] = cursor + 1
        fixture = candidates[cursor % len(candidates)]
        executed_cells += 1
        for _ in range(quota):
            timing = time_decision(fixture, style, depth, seed=int(manifest.seeds[0]))
            decision.append(timing.decision_path_ms)
            apply_ms.append(timing.engine_apply_ms)
            summary_ms.append(timing.summary_update_ms)
    return decision, apply_ms, summary_ms, executed_cells, planned_samples


def time_decision(
    fixture: MixedNodeFixture,
    style: str,
    depth_bb: int,
    *,
    seed: int,
) -> DecisionTiming:
    """在一个节点上计时一次完整决策；牌面与前置动作全部来自清单。"""
    stack = depth_bb * MIXED_BIG_BLIND
    adjusted = fixture.model_copy(update={"starting_stack": stack})
    applied = apply_node(adjusted)
    root = _derive_key(
        validation_root_key(seed), ("focus", style, fixture.node_id, depth_bb)
    )
    strategy = MixedLocalStrategy(
        root_key=root, bot_seats=tuple(range(adjusted.player_count))
    )
    return measure_decision(applied.engine, applied.tracker, strategy)


def run_supplementary_matrix(
    manifest: MixedFixtureManifest,
    *,
    samples_per_cell: int,
) -> tuple[list[float], int]:
    """补充小型测试：逐人数每类固定样本，与主矩阵分开统计。"""
    samples: list[float] = []
    executed = 0
    for player_count in MIXED_PLAYER_COUNTS:
        fixtures = manifest.nodes_for(player_count)
        if not fixtures:
            continue
        for _ in SUPPLEMENTARY_CLASSES:
            fixture = fixtures[executed % len(fixtures)]
            executed += 1
            for _ in range(samples_per_cell):
                timing = time_decision(fixture, MixedStyle.TIGHT.value, 100, seed=manifest.seeds[0])
                samples.append(timing.decision_path_ms)
    return samples, executed


# ------------------------------------------------------------------ 对抗对照


def adversarial_schedule(
    stage: Literal["A", "B"],
) -> list[tuple[int, MixedStyle, str, str, int, int]]:
    """对照排期：阶段 A 只取首轮换的一个子集，阶段 B 为完整轮换。"""
    schedule: list[tuple[int, MixedStyle, str, str, int, int]] = []
    if stage == "A":
        seed = MIXED_MAIN_SEEDS[0]
        style = MixedStyle.TIGHT
        for opponent in ADVERSARIAL_OPPONENT_FAMILIES:
            for arm in ADVERSARIAL_ARMS:
                for player_count in MIXED_PLAYER_COUNTS:
                    schedule.append((seed, style, opponent, arm, player_count, 0))
        return schedule
    for seed in MIXED_MAIN_SEEDS:
        for style in MixedStyle:
            for opponent in ADVERSARIAL_OPPONENT_FAMILIES:
                for arm in ADVERSARIAL_ARMS:
                    for player_count in MIXED_PLAYER_COUNTS:
                        for rotation in range(player_count):
                            schedule.append(
                                (seed, style, opponent, arm, player_count, rotation)
                            )
    return schedule


@dataclass(frozen=True)
class HandOutcome:
    """一手对照的净筹码与是否被截断。"""

    net_chips: int
    truncated: bool


def _focus_mover(
    *,
    style: MixedStyle,
    arm: str,
    seed: int,
    player_count: int,
    rotation: int,
    seat: int,
) -> object:
    if arm == "legacy-focus":
        return HeuristicStrategy(seed=seed)
    policy = MixedSeatPolicy(
        seat=seat,
        style=style,
        seat_key=focus_seat_key(seed, style.value, player_count, rotation),
    )
    return _PolicyMover(policy)


class _PolicyMover:
    """把单座位子策略适配成可调用的行动方；只用于离线对照。"""

    def __init__(self, policy: MixedSeatPolicy) -> None:
        self._policy = policy

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        return self._policy.choose_action(require_mixed_input(state), legal)


def _opponent_mover(family: str, seed: int) -> object:
    if family == "passive-call-probe":
        return PassiveCallProbe()
    if family == "fixed-pressure-probe":
        return FixedPressureProbe()
    if family == "heuristic@1":
        return HeuristicStrategy(seed=seed)
    from app.strategy.random_strategy import RandomStrategy

    return RandomStrategy(seed=seed)


def play_adversarial_hand(
    *,
    seed: int,
    style: MixedStyle,
    opponent: str,
    arm: str,
    player_count: int,
    rotation: int,
) -> HandOutcome:
    """一手有界对照：每手重置到 100BB、盲注 5/10、不设抽水。"""
    engine = PokerEngine(
        player_count,
        MIXED_SMALL_BLIND,
        MIXED_BIG_BLIND,
        100 * MIXED_BIG_BLIND,
        seed=adversarial_deck_seed(seed, player_count, rotation),
    )
    engine.start_hand()
    focus_seat = rotation % player_count
    tracker = MixedSummaryTracker()
    if not engine.hand_over:
        tracker.begin_hand(
            hand_number=1,
            num_players=player_count,
            small_blind=MIXED_SMALL_BLIND,
            big_blind=MIXED_BIG_BLIND,
            bot_seats=(focus_seat,),
            history=engine.history,
        )
    focus = _focus_mover(
        style=style,
        arm=arm,
        seed=seed,
        player_count=player_count,
        rotation=rotation,
        seat=focus_seat,
    )
    others = _opponent_mover(opponent, seed)

    voluntary = 0
    while not engine.hand_over:
        legal = engine.legal_actions()
        seat = engine.current_seat
        if seat == focus_seat:
            if not tracker.active:
                raise MixedValidationAuthorizationError("焦点座位缺少公开摘要")
            state = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
            mover = focus
        else:
            # 非焦点座位只看公开投影；两个 arm 的初态与牌堆流完全一致。
            state = project_for_actor(engine.snapshot())
            mover = others
        action = mover.choose_action(state, legal)
        if action.type in (ActionType.BET, ActionType.RAISE, ActionType.CALL):
            voluntary += 1
        engine.apply_action(action)
        if tracker.active:
            # 摘要覆盖全桌公开事件，与谁行动无关。
            tracker.consume_after_action(engine.history)
        if voluntary >= ADVERSARIAL_MAX_VOLUNTARY_ACTIONS:
            return HandOutcome(net_chips=0, truncated=True)
    return HandOutcome(net_chips=engine.last_net.get(focus_seat, 0), truncated=False)


def run_adversarial_batch(*, stage: Literal["A", "B"]) -> MixedValidationMatches:
    """执行第一批有界对照；达到动作上限的手截断、不补终局、不估算输赢。"""
    schedule = adversarial_schedule(stage)
    rows: list[MixedMatchFamilyRow] = []
    completed = 0
    truncated = 0
    for seed, style, opponent, arm, player_count, rotation in schedule:
        outcome = play_adversarial_hand(
            seed=seed,
            style=style,
            opponent=opponent,
            arm=arm,
            player_count=player_count,
            rotation=rotation,
        )
        completed += 1
        truncated += 1 if outcome.truncated else 0
        rows.append(
            MixedMatchFamilyRow(
                player_count=player_count,
                style=style.value,
                opponent=opponent,
                arm=arm,
                hands=1,
                truncated_hands=1 if outcome.truncated else 0,
                net_chips=outcome.net_chips,
                bb_per_100=outcome.net_chips / MIXED_BIG_BLIND * 100.0,
            )
        )
    return MixedValidationMatches(
        planned_hands=ADVERSARIAL_HANDS,
        completed_hands=completed,
        truncated_hands=truncated,
        seed_blocks=MIXED_MAIN_SEEDS,
        rows=tuple(rows),
    )


# ------------------------------------------------------------------ 阶段门禁与运行


def require_stage_permission(
    *,
    stage: Literal["A", "B"],
    allow_stage: str | None,
    manifest: MixedFixtureManifest | None,
    stage_a_receipt: MixedValidationReport | None = None,
) -> MixedFixtureManifest:
    """运行前的显式授权检查；默认禁止，缺失任一必要条件都不启动。"""
    if allow_stage != stage:
        raise MixedValidationAuthorizationError(
            "必须显式传入与目标一致的允许阶段；写好的入口本身不构成运行许可"
        )
    if manifest is None:
        raise MixedValidationAuthorizationError("必须提供已冻结的逐张牌清单")
    if not manifest.digest():
        raise MixedValidationAuthorizationError("清单摘要必须非空")
    if stage == "B":
        if stage_a_receipt is None:
            raise MixedValidationAuthorizationError("阶段 B 需要阶段 A 的实测回执")
        if stage_a_receipt.stage != "A" or stage_a_receipt.status != "completed":
            raise MixedValidationAuthorizationError("阶段 B 的前置回执不是已完成的阶段 A")
    return manifest


def prepare_output_dir(output_dir: str | None) -> str | None:
    """输出目录只创建、不覆盖：已存在非空内容时拒绝运行。"""
    if output_dir is None:
        return None
    if os.path.exists(output_dir) and os.listdir(output_dir):
        raise MixedValidationAuthorizationError("输出目录必须为空，不得覆盖已有文件")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def run_validation(
    *,
    manifest: MixedFixtureManifest | None,
    stage: Literal["A", "B"],
    allow_stage: str | None,
    output_dir: str | None = None,
    stage_a_receipt: MixedValidationReport | None = None,
) -> MixedValidationReport:
    """执行一个显式授权的验证阶段；不访问、不修改任何封存工件。"""
    frozen = require_stage_permission(
        stage=stage,
        allow_stage=allow_stage,
        manifest=manifest,
        stage_a_receipt=stage_a_receipt,
    )
    directory = prepare_output_dir(output_dir)
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    violations: list[MixedReportViolation] = []

    decision: list[float] = []
    apply_ms: list[float] = []
    summary_ms: list[float] = []
    cells_executed = 0
    cells_planned = 0
    for player_count in MIXED_PLAYER_COUNTS:
        part_decision, part_apply, part_summary, executed, planned = run_cost_matrix(
            frozen, stage=stage, player_count=player_count
        )
        decision.extend(part_decision)
        apply_ms.extend(part_apply)
        summary_ms.extend(part_summary)
        cells_executed += executed
        cells_planned += planned

    supplementary_target = (
        STAGE_A_SUPPLEMENTARY_SAMPLES if stage == "A" else SUPPLEMENTARY_TOTAL_SAMPLES
    )
    samples_per_cell = 1 if stage == "A" else SUPPLEMENTARY_SAMPLES_PER_CELL
    supplementary, _supplementary_cells = run_supplementary_matrix(
        frozen, samples_per_cell=samples_per_cell
    )
    # 补充场景与主矩阵分开报告，不并入主路径的分布。
    supplementary_path = summarize_path(supplementary[:supplementary_target])

    matches = run_adversarial_batch(stage=stage)
    behavior = collect_behavior(frozen)

    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    limit = STAGE_A_WALL_SECONDS if stage == "A" else STAGE_AB_WALL_SECONDS
    status = "completed"
    if wall_seconds > limit:
        status = "stopped-wall-budget"
    if matches.truncated_hands:
        violations.append(
            MixedReportViolation(
                kind="truncated-hands",
                detail=f"对抗对照有 {matches.truncated_hands} 手达到动作上限被截断",
            )
        )
    decision_path = summarize_path(decision)
    if decision_path.timeout_count:
        # 出现超预算样本立即标为性能失败，不删除、不自动复测。
        status = "stopped-decision-over-budget"
        violations.append(
            MixedReportViolation(
                kind="decision-over-budget",
                detail=f"出现 {decision_path.timeout_count} 次 >=100ms 的单次决策",
            )
        )

    report = MixedValidationReport(
        strategy_id=MIXED_STRATEGY_IDENTIFIER,
        code_identity=frozen.code_identity,
        config_digest=frozen.config_digest,
        manifest_digest=frozen.digest(),
        stage=stage,
        status=status,
        environment=MixedValidationEnvironment(
            python_version=sys.version.split()[0],
            platform=platform.platform(),
            cpu_count=os.cpu_count() or 1,
        ),
        coverage=MixedValidationCoverage(
            planned_nodes=MIXED_PLANNED_SLOT_COUNT,
            executed_nodes=len(frozen.nodes),
            not_run_nodes=max(
                0,
                MIXED_APPLICABLE_NODE_COUNT - len(frozen.nodes),
            ),
            structurally_not_applicable=MIXED_STRUCTURAL_HOLE_COUNT,
            cost_cells_planned=cells_planned,
            cost_cells_executed=cells_executed,
            supplementary_samples_planned=SUPPLEMENTARY_TOTAL_SAMPLES,
            supplementary_samples_executed=supplementary_path.samples,
            adversarial_hands_planned=matches.planned_hands,
            adversarial_hands_executed=matches.completed_hands,
        ),
        timing=MixedValidationTiming(
            decision_path=decision_path,
            engine_apply=summarize_path(apply_ms),
            public_summary_update=summarize_path(summary_ms),
            supplementary_decision_path=supplementary_path,
        ),
        behavior=behavior,
        matches=matches,
        resources=MixedValidationResources(
            wall_seconds=wall_seconds,
            cpu_seconds=cpu_seconds,
            peak_rss_bytes=None,
            output_bytes=0,
            single_process=True,
            parallel=False,
        ),
        violations=tuple(violations),
    )
    if directory is not None:
        target = os.path.join(directory, f"mixed-validation-stage-{stage}.json")
        if os.path.exists(target):
            raise MixedValidationAuthorizationError("报告目标文件已存在，不得覆盖")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(report.model_dump_json(indent=2))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：必须显式给出清单路径、阶段、输出目录与允许阶段。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 4:
        print(
            "用法：python -m tests.mixed_bot_validation <清单路径> <A|B> <输出目录> "
            "--allow-stage=<A|B>",
            file=sys.stderr,
        )
        return 2
    manifest_path, stage, output_dir = args[0], args[1], args[2]
    allow_stage = None
    for token in args[3:]:
        if token.startswith("--allow-stage="):
            allow_stage = token.split("=", 1)[1]
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = MixedFixtureManifest.model_validate(json.load(handle))
    report = run_validation(
        manifest=manifest,
        stage=stage,  # type: ignore[arg-type]
        allow_stage=allow_stage,
        output_dir=output_dir,
    )
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - 手动 opt-in 入口
    raise SystemExit(main())
