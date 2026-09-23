"""独立验证判定器：把判据读数的计算口径实现为可执行、可测的只读计算。

为什么需要本模块：此前若干轮的判定读数由会话内的临时代码算出，跑完即弃，导致
部分读数**无法从已落盘工件复算**。本模块把口径的「实现层」逐项写死，使同一批工件
必得同一读数，并让「哪些历史读数复现不出来」本身也成为可断言的事实。

纪律：
- 只读调用方给出的已落盘工件，绝不改写任何证据文件，也不写出任何文件；
- 不产生对局、不新增样本、不使用随机数：同一输入必得同一读数；
- 默认拒绝：只有显式传入允许开关才计算，模块被导入或被 pytest 收集都不触发计算；
- 未在冻结文本中钉死的实现细节，一律在本模块顶部常量与各函数说明中显式声明，
  不得在读数之后临时选择更有利的读法。
"""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

JUDGMENT_PAYLOAD_VERSION = "mixed-judgment-payload.v1"

# ---------------------------------------------------------------------------
# 实现层钉子（口径的可执行定义）
# ---------------------------------------------------------------------------

# 估值单元取「清单种子序」的第一个主种子块，不取报告行序的最小值。
VALUATION_BLOCK_INDEX = 0

# 三个风格与三个配对顺序固定，避免读数依赖字典顺序。
STYLES: tuple[str, ...] = ("tight", "aggressive", "calling")
STYLE_PAIRS: tuple[tuple[str, str], ...] = (
    ("tight", "aggressive"),
    ("tight", "calling"),
    ("aggressive", "calling"),
)

# 风格可分类别的自然分区：翻前、面对下注、免费行动。
PREFLOP_CATEGORIES: frozenset[str] = frozenset(
    {
        "hu-blind-position",
        "unopened-open",
        "open-after-limp",
        "facing-first-raise",
        "facing-reraise",
        "incomplete-raise",
        "short-stack-call",
    }
)
FACING_BET_CATEGORIES: frozenset[str] = frozenset(
    {
        "flop-draw",
        "turn-combo-draw",
        "overpair-on-high-board",
        "top-pair-weak-kicker",
        "missed-draw-river",
        "one-side-all-in",
        "sizes-merged",
        "shared-board",
    }
)
FREE_ACTION_CATEGORIES: frozenset[str] = frozenset({"free-check"})

# 两个预先指定的机会域：翻前未开池节点的进池概率、翻牌面对下注节点的主动概率。
ENTRY_DOMAIN_CATEGORY = "unopened-open"
ACTIVE_DOMAIN_CATEGORY = "flop-draw"
ENTRY_ACTIONS: tuple[str, ...] = ("call", "bet", "raise")
ACTIVE_ACTIONS: tuple[str, ...] = ("bet", "raise")

# 门槛取值：只做转写，本模块不重新裁定任何门槛。
SUBSTANTIVE_MIX_MIN_SHARE = 0.10
COVERAGE_MIN_SHARE = 0.25
TYPE_ENTROPY_MIN_BITS = 0.15
SCALE_ANCHOR_MIN_SHARE = 0.15
SCALE_ANCHOR_MIN_COUNT = 2
SCALE_ENTROPY_MIN_BITS = 0.5
OPPORTUNITY_MIN_GAP_PP = 10.0
OPPORTUNITY_MIN_PAIRS = 2
STYLE_JS_MIN_DISTANCE = 0.15

# 不劣化判定的区间方法与配对骨牌：块均值双侧 t 区间，块数固定为 16。
NON_DEGRADATION_LOWER_BOUND_BB_PER_100 = -5.0
FIXED_BLOCK_COUNT = 16
T95_DF15 = 2.131

# 针对性诊断：每（对手族 × 风格）按（清单种子序、人数、轮换）排序后的前若干对为短段。
SHORT_SEGMENT_PAIRS_PER_GROUP = 20
STREET_ORDER: tuple[str, ...] = ("preflop", "flop", "turn", "river")
# 翻前街起始底池 = 小盲 + 大盲 = 1.5 个大盲。
PREFLOP_START_POT_CHIPS = 15
SCALE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("≤50%", 0.0, 0.5),
    ("50–100%", 0.5, 1.0),
    (">100%", 1.0, math.inf),
)
NO_FACING_BUCKET = "无面对加注"
# 尺度与街道分桶只对「有面对」的配对分档；牌力分档覆盖全部配对。
SCALE_BUCKET_DIMENSION = "尺度"
STREET_BUCKET_DIMENSION = "街道"
STRENGTH_BUCKET_DIMENSION = "牌力"

# 「实质动作混合」的单元 = 估值块的逐节点分布；「整体」= 该批分布上的比例。
# 「额度锚点」的单元 = 已选加注且存在额度分布的分布。
ZERO_SHARE = 0.0

# 历史对照：上一轮公布、但本实现**无法复现**的两组读数，与同样工件上的本实现读数。
# 差值一律记绝对值（公布口径也是绝对值），有符号值见载荷字段；配对计数指「有面对」的配对。
# 这两组只用于把「复现不出」本身钉成可断言事实，不参与任何判据判定。
IRREPRODUCIBLE_REFERENCE: dict[str, dict[str, Any]] = {
    "previous_opportunity_gaps_pp": {
        "published": {"entry": (20.22, 33.91, 13.69), "active": (0.35, 0.03, 0.38)},
        "this_implementation": {"entry": (30.71, 54.92, 24.22), "active": (0.62, 0.25, 0.37)},
    },
    "previous_facing_pair_counts": {
        "published": {"short": 42, "long": 1303},
        "this_implementation": {"short": 175, "long": 5191},
    },
}
IRREPRODUCIBLE_NOTE = (
    "上一轮公布的两组读数（机会域差值与针对性诊断的面对计数）无法由既有工件复现："
    "已穷举多种自然实现均不吻合，其实现细节已不可考。本模块给出的是**钉死后的实现**读数，"
    "两者只能并列呈现，不得互相替代，也不得据此改写任何已落盘回执。"
)


class MixedJudgmentError(RuntimeError):
    """判定前置条件失败时抛出；不产出读数、不静默继续。"""


class _FrozenModel(BaseModel):
    """判定载荷的公共基类：冻结且禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class CoverageReading(_FrozenModel):
    """实质动作混合覆盖率：整体、分域与按节点聚合的并列读数。"""

    unit_total: int
    unit_mixed: int
    share: float
    preflop_total: int
    preflop_mixed: int
    preflop_share: float
    facing_bet_total: int
    facing_bet_mixed: int
    facing_bet_share: float
    free_action_total: int
    free_action_mixed: int
    free_action_share: float
    node_total: int
    node_mixed: int
    node_share: float
    above_threshold: bool


class EntropyReading(_FrozenModel):
    """平均类型熵：逐风格读数与是否达到门槛。"""

    per_style: dict[str, float]
    counts: dict[str, int]
    minimum: float
    above_threshold: bool


class ScaleAnchorReading(_FrozenModel):
    """额度多样性：两档锚点满足率与金额条件熵。"""

    unit_total: int
    anchor_satisfied: int
    anchor_share: float
    structurally_single: int
    anchor_min_count: int
    mean_scale_entropy: float
    scale_entropy_per_style: dict[str, float]
    scale_entropy_counts: dict[str, int]
    anchors_above_threshold: bool
    scale_entropy_above_threshold: bool


class OpportunityReading(_FrozenModel):
    """两个机会域上的风格条件概率差（百分点）与达到阈值的配对数。"""

    entry_probabilities: dict[str, float]
    entry_gaps_pp: dict[str, float]
    entry_pairs_above: int
    active_probabilities: dict[str, float]
    active_gaps_pp: dict[str, float]
    active_pairs_above: int
    satisfied: bool


class JsReading(_FrozenModel):
    """风格间 JS 距离（由工件字段直读）与最薄余量。"""

    distances: dict[str, float]
    thinnest_pair: str
    thinnest_value: float
    above_threshold: bool


class StabilityReading(_FrozenModel):
    """风格稳定性：逐（配对 × 域）在全部种子块上的符号是否一致。"""

    entry_sign_consistent: dict[str, bool]
    active_sign_consistent: dict[str, bool]
    blocks: int
    consistent_combinations: int
    total_combinations: int
    direction_stable: bool
    blocks_vary: bool


class UnpredictabilityReading(_FrozenModel):
    """不可预测性六项的读数与是否满足。"""

    coverage: CoverageReading
    entropy: EntropyReading
    scale_anchor: ScaleAnchorReading
    opportunity: OpportunityReading
    style_js: JsReading
    stability: StabilityReading
    unsatisfied_items: tuple[str, ...]


class PlayerNonDegradation(_FrozenModel):
    """单一人数下的不劣化判定：最差族与正偏离族并列。"""

    player_count: int
    worst_family: str
    worst_mean_bb_per_100: float
    worst_lower_bound_bb_per_100: float
    worst_block_min_bb_per_100: float
    worst_block_max_bb_per_100: float
    interval_satisfied: bool
    block_extreme_satisfied: bool
    satisfied: bool
    best_family: str
    best_mean_bb_per_100: float


class NonDegradationReading(_FrozenModel):
    """不劣化：逐人数独立判定，禁止跨人数归因。"""

    pairs: int
    pair_anomalies: int
    players: tuple[PlayerNonDegradation, ...]
    players_satisfied: int
    players_satisfied_block_extreme: int
    satisfied: bool
    total_net_chips_mixed: int
    total_net_chips_legacy: int
    blocks_mixed_higher: int


class FamilyReading(_FrozenModel):
    """逐对手族收益读数（仅被测一方，跨人数汇总只作报告）。"""

    opponent: str
    net_chips: int
    mean_bb_per_100: float
    block_min_bb_per_100: float
    block_max_bb_per_100: float
    hands: int


class FamilySegment(_FrozenModel):
    """逐族短段 / 长段对比。"""

    opponent: str
    short_mean_bb_per_100: float
    long_mean_bb_per_100: float
    gain_bb_per_100: float
    short_pairs: int
    long_pairs: int


class BucketReading(_FrozenModel):
    """一个分桶的短段 / 长段读数。"""

    dimension: str
    bucket: str
    short_pairs: int
    long_pairs: int
    short_mean_bb_per_100: float | None
    long_mean_bb_per_100: float | None
    gain_bb_per_100: float | None


class TargetingReading(_FrozenModel):
    """抗针对诊断：逐族短长段与分桶读数，并附稀疏度。"""

    pairs: int
    pairs_with_facing: int
    facing_share: float
    families: tuple[FamilySegment, ...]
    buckets: tuple[BucketReading, ...]


class TargetingReadingFull(_FrozenModel):
    """抗针对：逐族收益与针对性诊断并列。"""

    families: tuple[FamilyReading, ...]
    diagnostic: TargetingReading


class MechanicsReading(_FrozenModel):
    """机制与正确性：违规、截断、摘要一致与（可选的）重放一致性。"""

    violations: tuple[str, ...]
    truncated_hands: int
    digests_consistent: bool
    digest_sources: dict[str, str]
    replay_hands_compared: int
    replay_net_chips_exact: bool | None
    replay_behavior_exact: bool | None
    replay_sources: tuple[str, ...]
    observations_checked: bool


class CostReading(_FrozenModel):
    """成本：硬预算、指导值与逐人数超时计数。"""

    decision_budget_ms: float
    samples: int
    timeout_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    per_player_samples: dict[int, int]
    per_player_timeouts: dict[int, int]
    per_player_p95_range: tuple[float, float]
    hard_budget_satisfied: bool
    guidance_satisfied: bool


class JudgmentPayload(_FrozenModel):
    """判定载荷：只打印、不落盘，由调用方决定如何呈现。"""

    payload_version: str
    strategy_id: str
    config_digest: str
    manifest_digest: str
    valuation_seed_block: int
    mechanics: MechanicsReading
    cost: CostReading
    unpredictability: UnpredictabilityReading
    non_degradation: NonDegradationReading
    targeting: TargetingReadingFull
    pins: tuple[str, ...]
    limitations: tuple[str, ...]


# ---------------------------------------------------------------------------
# 只读装载
# ---------------------------------------------------------------------------


def _load_json(path: str) -> dict[str, Any]:
    """按只读方式载入一份已落盘工件。"""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    """取必需字段；缺失即失败，不用默认值掩盖工件粒度不足。"""
    if key not in mapping:
        raise MixedJudgmentError(f"{where} 缺少必需字段：{key}")
    return mapping[key]


def _share(part: float, whole: float) -> float:
    """占比计算：分母为 0 时显式归零，不产生 NaN。"""
    return part / whole if whole else ZERO_SHARE


def _mean_or_zero(values: Sequence[float]) -> float:
    """取均值；样本为空时归零，避免部分工件触发崩溃。"""
    return statistics.fmean(values) if values else ZERO_SHARE


def valuation_block(manifest: dict[str, Any]) -> int:
    """取估值单元所用的种子块：清单种子序中的第一个。"""
    seeds = _require(manifest, "seeds", "清单")
    if not seeds:
        raise MixedJudgmentError("清单未登记任何主种子块，无法确定估值单元")
    return int(seeds[VALUATION_BLOCK_INDEX])


def block_order(manifest: dict[str, Any]) -> dict[int, int]:
    """种子块的清单序映射：短段排序依赖清单序，不能用数值大小代替。"""
    return {int(seed): index for index, seed in enumerate(_require(manifest, "seeds", "清单"))}


def node_rows(report: dict[str, Any], where: str) -> list[dict[str, Any]]:
    """取逐节点分布行；工件不含该粒度时显式失败，不回退到类别均值。"""
    behavior = _require(report, "behavior", where)
    if not isinstance(behavior, dict) or not isinstance(behavior.get("nodes"), list):
        raise MixedJudgmentError(
            f"{where} 的 behavior 不含逐节点分布行，无法按覆盖分母计算；"
            "该粒度缺失时不得用类别或风格均值代替"
        )
    return list(behavior["nodes"])


def match_rows(report: dict[str, Any], where: str) -> list[dict[str, Any]]:
    """取对抗对照逐行数据。"""
    matches = _require(report, "matches", where)
    rows = _require(matches, "rows", f"{where} 的 matches")
    if not isinstance(rows, list) or not rows:
        raise MixedJudgmentError(f"{where} 的 matches.rows 为空，无法做配对判定")
    return list(rows)


def observation_hands(observations: dict[str, Any], where: str) -> list[dict[str, Any]]:
    """取观测工件的逐手行。"""
    hands = _require(observations, "hands", where)
    if not isinstance(hands, list) or not hands:
        raise MixedJudgmentError(f"{where} 的 hands 为空，无法做针对性诊断")
    return list(hands)


# ---------------------------------------------------------------------------
# 不可预测性
# ---------------------------------------------------------------------------


def _is_substantively_mixed(units: dict[str, float]) -> bool:
    """分布是否在两个动作上各留有实质份额：次高份额需达到门槛。"""
    ordered = sorted((float(v) for v in units.values()), reverse=True)
    total = sum(ordered)
    if len(ordered) < 2 or not total:
        return False
    return _share(ordered[1], total) >= SUBSTANTIVE_MIX_MIN_SHARE


def _rate(rows: Iterable[dict[str, Any]], categories: frozenset[str] | None) -> tuple[int, int]:
    """按类别过滤后统计（混合数、总数）。"""
    selected = [r for r in rows if categories is None or r["category"] in categories]
    mixed = sum(1 for r in selected if _is_substantively_mixed(r["action_units"]))
    return mixed, len(selected)


def coverage_reading(rows: Sequence[dict[str, Any]]) -> CoverageReading:
    """实质动作混合覆盖率：整体、三分域，以及把同一节点各分布 units 相加后的节点读数。"""
    mixed, total = _rate(rows, None)
    preflop = _rate(rows, PREFLOP_CATEGORIES)
    facing = _rate(rows, FACING_BET_CATEGORIES)
    free = _rate(rows, FREE_ACTION_CATEGORIES)
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        for action, units in row["action_units"].items():
            grouped[row["node_id"]][action] += float(units)
    node_mixed = sum(1 for units in grouped.values() if _is_substantively_mixed(units))
    share = _share(mixed, total)
    return CoverageReading(
        unit_total=total,
        unit_mixed=mixed,
        share=share,
        preflop_total=preflop[1],
        preflop_mixed=preflop[0],
        preflop_share=_share(preflop[0], preflop[1]),
        facing_bet_total=facing[1],
        facing_bet_mixed=facing[0],
        facing_bet_share=_share(facing[0], facing[1]),
        free_action_total=free[1],
        free_action_mixed=free[0],
        free_action_share=_share(free[0], free[1]),
        node_total=len(grouped),
        node_mixed=node_mixed,
        node_share=_share(node_mixed, len(grouped)),
        above_threshold=share >= COVERAGE_MIN_SHARE,
    )


def entropy_reading(rows: Sequence[dict[str, Any]]) -> EntropyReading:
    """平均类型熵：逐风格对分布熵取算术均值。"""
    per_style: dict[str, float] = {}
    counts: dict[str, int] = {}
    for style in STYLES:
        values = [float(r["action_entropy"]) for r in rows if r["style"] == style]
        counts[style] = len(values)
        per_style[style] = statistics.fmean(values) if values else ZERO_SHARE
    minimum = min(per_style.values())
    return EntropyReading(
        per_style=per_style,
        counts=counts,
        minimum=minimum,
        above_threshold=minimum >= TYPE_ENTROPY_MIN_BITS,
    )


def scale_anchor_reading(rows: Sequence[dict[str, Any]]) -> ScaleAnchorReading:
    """额度多样性：条件于已选加注的额度分布，统计达到门槛的锚点档数与金额条件熵。"""
    units = [r for r in rows if r.get("scale_entropy") is not None]
    satisfied = 0
    for row in units:
        scale = row.get("scale_units") or {}
        total = sum(float(v) for v in scale.values())
        anchors = sum(
            1 for v in scale.values() if _share(float(v), total) >= SCALE_ANCHOR_MIN_SHARE
        )
        if anchors >= SCALE_ANCHOR_MIN_COUNT:
            satisfied += 1
    entropies = [float(r["scale_entropy"]) for r in units]
    per_style = {
        style: _mean_or_zero(
            [e for e, r in zip(entropies, units, strict=True) if r["style"] == style]
        )
        for style in STYLES
    }
    counts = {style: sum(1 for r in units if r["style"] == style) for style in STYLES}
    mean_entropy = statistics.fmean(entropies) if entropies else ZERO_SHARE
    structurally_single = sum(int(r.get("structural_single_size", 0)) for r in rows)
    return ScaleAnchorReading(
        unit_total=len(units),
        anchor_satisfied=satisfied,
        anchor_share=_share(satisfied, len(units)),
        structurally_single=structurally_single,
        anchor_min_count=SCALE_ANCHOR_MIN_COUNT,
        mean_scale_entropy=mean_entropy,
        scale_entropy_per_style=per_style,
        scale_entropy_counts=counts,
        anchors_above_threshold=satisfied == len(units),
        scale_entropy_above_threshold=mean_entropy >= SCALE_ENTROPY_MIN_BITS,
    )


def _style_action_units() -> dict[str, dict[str, float]]:
    """构造「风格 → 动作 → 累计 units」的空容器，供机会域聚合使用。"""
    return defaultdict(lambda: defaultdict(float))


def _domain_probabilities(
    rows: Sequence[dict[str, Any]], category: str, actions: tuple[str, ...]
) -> dict[str, float]:
    """机会域概率：先把同一节点的各手模式 units 相加，再按节点等权平均。"""
    grouped: dict[str, dict[str, dict[str, float]]] = defaultdict(_style_action_units)
    for row in rows:
        if row["category"] != category:
            continue
        for action, units in row["action_units"].items():
            grouped[row["node_id"]][row["style"]][action] += float(units)
    per_node: dict[str, dict[str, float]] = {}
    for node, styles in grouped.items():
        per_node[node] = {}
        for style in STYLES:
            units = styles.get(style) or {}
            total = sum(units.values())
            per_node[node][style] = _share(
                sum(units.get(action, 0.0) for action in actions), total
            )
    return {
        style: _mean_or_zero([per_node[node][style] for node in per_node]) for style in STYLES
    }


def opportunity_reading(
    rows: Sequence[dict[str, Any]],
) -> tuple[OpportunityReading, dict[str, dict[str, float]]]:
    """两个机会域的风格条件概率与差值；第二返回值供稳定性检查按块复用。"""
    entry = _domain_probabilities(rows, ENTRY_DOMAIN_CATEGORY, ENTRY_ACTIONS)
    active = _domain_probabilities(rows, ACTIVE_DOMAIN_CATEGORY, ACTIVE_ACTIONS)
    entry_gaps = {f"{a}-{b}": 100.0 * (entry[a] - entry[b]) for a, b in STYLE_PAIRS}
    active_gaps = {f"{a}-{b}": 100.0 * (active[a] - active[b]) for a, b in STYLE_PAIRS}
    entry_pairs = sum(1 for gap in entry_gaps.values() if abs(gap) >= OPPORTUNITY_MIN_GAP_PP)
    active_pairs = sum(1 for gap in active_gaps.values() if abs(gap) >= OPPORTUNITY_MIN_GAP_PP)
    reading = OpportunityReading(
        entry_probabilities=entry,
        entry_gaps_pp=entry_gaps,
        entry_pairs_above=entry_pairs,
        active_probabilities=active,
        active_gaps_pp=active_gaps,
        active_pairs_above=active_pairs,
        satisfied=(
            entry_pairs >= OPPORTUNITY_MIN_PAIRS and active_pairs >= OPPORTUNITY_MIN_PAIRS
        ),
    )
    return reading, {"entry": entry, "active": active}


def js_reading(report: dict[str, Any]) -> JsReading:
    """风格间 JS 距离：直接读工件字段，不在本模块重算距离。"""
    behavior = _require(report, "behavior", "阶段回执")
    entries = _require(behavior, "style_js_distances", "阶段回执的 behavior")
    distances: dict[str, float] = {}
    for entry in entries:
        distances[f"{entry['style_a']}-{entry['style_b']}"] = float(entry["mean_js_distance"])
    if not distances:
        raise MixedJudgmentError("工件未给出风格间距离，无法判定该项")
    thinnest = min(distances, key=lambda key: distances[key])
    return JsReading(
        distances=distances,
        thinnest_pair=thinnest,
        thinnest_value=distances[thinnest],
        above_threshold=min(distances.values()) >= STYLE_JS_MIN_DISTANCE,
    )


def _gap_sign(value: float) -> int:
    """把差值映射为符号，用于跨块方向一致性检查。"""
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def stability_reading(
    rows: Sequence[dict[str, Any]], blocks: Sequence[int]
) -> StabilityReading:
    """风格稳定性：同一配对同一域在全部种子块上的差值符号是否一致。"""
    per_block: dict[int, Sequence[dict[str, Any]]] = {
        block: [r for r in rows if r["seed_block"] == block] for block in blocks
    }
    entry_signs: dict[str, set[int]] = {f"{a}-{b}": set() for a, b in STYLE_PAIRS}
    active_signs: dict[str, set[int]] = {f"{a}-{b}": set() for a, b in STYLE_PAIRS}
    for block in blocks:
        _, domains = opportunity_reading(per_block[block])
        for a, b in STYLE_PAIRS:
            key = f"{a}-{b}"
            entry_signs[key].add(_gap_sign(100.0 * (domains["entry"][a] - domains["entry"][b])))
            active_signs[key].add(_gap_sign(100.0 * (domains["active"][a] - domains["active"][b])))
    entry_ok = {key: len(signs) == 1 for key, signs in entry_signs.items()}
    active_ok = {key: len(signs) == 1 for key, signs in active_signs.items()}
    consistent = sum(1 for value in (*entry_ok.values(), *active_ok.values()) if value)
    total = len(entry_ok) + len(active_ok)
    # 分布是否随块变化：按（节点 × 风格 × 手模式）看跨块取值是否只有一种。
    keyed: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        key = (row["node_id"], row["style"], row["hand_mode"])
        keyed[key].add(json.dumps(row["action_units"], sort_keys=True))
    blocks_vary = any(len(values) > 1 for values in keyed.values())
    return StabilityReading(
        entry_sign_consistent=entry_ok,
        active_sign_consistent=active_ok,
        blocks=len(blocks),
        consistent_combinations=consistent,
        total_combinations=total,
        direction_stable=consistent == total,
        blocks_vary=blocks_vary,
    )


def unpredictability_reading(
    report: dict[str, Any], manifest: dict[str, Any], where: str
) -> UnpredictabilityReading:
    """不可预测性六项：统一在估值块的逐节点分布上计算。"""
    rows = node_rows(report, where)
    block = valuation_block(manifest)
    unit = [r for r in rows if r["seed_block"] == block]
    if not unit:
        raise MixedJudgmentError(f"{where} 的逐节点分布不含估值种子块 {block}")
    blocks = sorted({int(r["seed_block"]) for r in rows})
    coverage = coverage_reading(unit)
    entropy = entropy_reading(unit)
    scale = scale_anchor_reading(unit)
    opportunity, _ = opportunity_reading(unit)
    js = js_reading(report)
    stability = stability_reading(rows, blocks)
    unsatisfied: list[str] = []
    if not coverage.above_threshold:
        unsatisfied.append("实质动作混合覆盖率")
    if not entropy.above_threshold:
        unsatisfied.append("平均类型熵")
    if not scale.anchors_above_threshold:
        unsatisfied.append("额度锚点档数")
    if not scale.scale_entropy_above_threshold:
        unsatisfied.append("金额条件熵")
    if not opportunity.satisfied:
        unsatisfied.append("两个机会域的风格可分度")
    if not js.above_threshold:
        unsatisfied.append("风格间距离")
    if not stability.direction_stable:
        unsatisfied.append("风格稳定性")
    return UnpredictabilityReading(
        coverage=coverage,
        entropy=entropy,
        scale_anchor=scale,
        opportunity=opportunity,
        style_js=js,
        stability=stability,
        unsatisfied_items=tuple(unsatisfied),
    )


# ---------------------------------------------------------------------------
# 不劣化与抗针对
# ---------------------------------------------------------------------------


def pair_table(rows: Sequence[dict[str, Any]], where: str) -> tuple[dict[tuple, dict], int]:
    """把两个 arm 的逐行数据配成对；返回配对表与不完整配对计数。"""
    pairs: dict[tuple, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        key = (
            row["player_count"],
            row["style"],
            row["opponent"],
            row["seed_block"],
            row["rotation"],
        )
        pairs[key][row["arm"]] = row
    anomalies = sum(1 for arms in pairs.values() if set(arms) != {"mixed-focus", "legacy-focus"})
    if anomalies:
        raise MixedJudgmentError(f"{where} 存在 {anomalies} 个不完整配对，停止判定")
    return dict(pairs), anomalies


def non_degradation_reading(report: dict[str, Any], where: str) -> NonDegradationReading:
    """不劣化：逐人数各自取最差族，按块均值 t 区间与块极值两口径判定。"""
    rows = match_rows(report, where)
    pairs, anomalies = pair_table(rows, where)
    blocks = sorted({key[3] for key in pairs})
    grouped: dict[tuple[int, str, int], list[float]] = defaultdict(list)
    for (player_count, _style, opponent, block, _rotation), arms in pairs.items():
        diff = float(arms["mixed-focus"]["bb_per_100"]) - float(arms["legacy-focus"]["bb_per_100"])
        grouped[(player_count, opponent, block)].append(diff)
    players = sorted({key[0] for key in pairs})
    families = sorted({key[2] for key in pairs})
    readings: list[PlayerNonDegradation] = []
    for player_count in players:
        stats: list[tuple[float, str, float, float, float]] = []
        for family in families:
            means = [statistics.fmean(grouped[(player_count, family, block)]) for block in blocks]
            mean = statistics.fmean(means)
            deviation = statistics.stdev(means) / math.sqrt(len(means))
            stats.append((mean, family, mean - T95_DF15 * deviation, min(means), max(means)))
        stats.sort(key=lambda item: (item[0], item[1]))
        worst = stats[0]
        best = stats[-1]
        interval_ok = worst[2] >= NON_DEGRADATION_LOWER_BOUND_BB_PER_100
        extreme_ok = worst[3] >= NON_DEGRADATION_LOWER_BOUND_BB_PER_100
        readings.append(
            PlayerNonDegradation(
                player_count=player_count,
                worst_family=worst[1],
                worst_mean_bb_per_100=worst[0],
                worst_lower_bound_bb_per_100=worst[2],
                worst_block_min_bb_per_100=worst[3],
                worst_block_max_bb_per_100=worst[4],
                interval_satisfied=interval_ok,
                block_extreme_satisfied=extreme_ok,
                satisfied=interval_ok and extreme_ok,
                best_family=best[1],
                best_mean_bb_per_100=best[0],
            )
        )
    totals: dict[str, int] = defaultdict(int)
    for arms in pairs.values():
        for arm, row in arms.items():
            totals[arm] += int(row["net_chips"])
    block_sums: dict[int, int] = defaultdict(int)
    for (_, _, _, block, _), arms in pairs.items():
        block_sums[block] += int(arms["mixed-focus"]["net_chips"]) - int(
            arms["legacy-focus"]["net_chips"]
        )
    return NonDegradationReading(
        pairs=len(pairs),
        pair_anomalies=anomalies,
        players=tuple(readings),
        players_satisfied=sum(1 for r in readings if r.satisfied),
        players_satisfied_block_extreme=sum(1 for r in readings if r.block_extreme_satisfied),
        satisfied=all(r.satisfied for r in readings),
        total_net_chips_mixed=totals.get("mixed-focus", 0),
        total_net_chips_legacy=totals.get("legacy-focus", 0),
        blocks_mixed_higher=sum(1 for value in block_sums.values() if value > 0),
    )


def family_reading(report: dict[str, Any], where: str) -> tuple[FamilyReading, ...]:
    """逐对手族收益：净筹码与块间均值/极值，跨人数汇总只作报告。"""
    rows = match_rows(report, where)
    grouped: dict[tuple[str, int], list[float]] = defaultdict(list)
    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row["arm"] != "mixed-focus":
            continue
        grouped[(row["opponent"], row["seed_block"])].append(float(row["bb_per_100"]))
        totals[row["opponent"]] += int(row["net_chips"])
        counts[row["opponent"]] += 1
    readings: list[FamilyReading] = []
    for family in sorted(totals):
        means = [
            statistics.fmean(values)
            for (opponent, _block), values in sorted(grouped.items())
            if opponent == family
        ]
        readings.append(
            FamilyReading(
                opponent=family,
                net_chips=totals[family],
                mean_bb_per_100=statistics.fmean(means),
                block_min_bb_per_100=min(means),
                block_max_bb_per_100=max(means),
                hands=counts[family],
            )
        )
    return tuple(readings)


def _first_facing_event(hand: dict[str, Any]) -> tuple[str, int, int] | None:
    """焦点座位首次面对下注/加注的事件：返回（街、面对额度、该街起始底池）。

    面对的额度取同一街上最后一次对手下注/加注的额度；焦点座位自己的下注或加注不构成
    「面对」，只把局面推向对手。街起始底池取上一街结束底池，翻前按 1.5 个大盲。
    """
    player_count = hand["player_count"]
    focus = hand["rotation"] % player_count
    pending: tuple[str, int] | None = None
    for action in hand["actions"]:
        street = action["street"]
        if action["seat"] == focus:
            if action["action"] in ACTIVE_ACTIONS:
                pending = (street, int(action["amount"]))
            elif pending and pending[0] == street:
                if street == STREET_ORDER[0]:
                    start_pot = PREFLOP_START_POT_CHIPS
                else:
                    previous = STREET_ORDER[STREET_ORDER.index(street) - 1]
                    start_pot = int(hand["pot_after_street"].get(previous, 0))
                return street, pending[1], start_pot
        elif action["action"] in ACTIVE_ACTIONS:
            pending = (street, int(action["amount"]))
    return None


def _scale_bucket(amount: int, start_pot: int) -> str:
    """按「面对额度 ÷ 街起始底池」分档；起始底池缺失时单列。"""
    if start_pot <= 0:
        return "起始底池缺失"
    ratio = amount / start_pot
    for label, low, high in SCALE_BUCKETS:
        if low < ratio <= high or (low == 0.0 and ratio <= high):
            return label
    return SCALE_BUCKETS[-1][0]


def _empty_segments() -> dict[str, list[float]]:
    """构造短段 / 长段两个空列表，供分桶聚合使用。"""
    return {"short": [], "long": []}


def targeting_diagnostic(
    observations: dict[str, Any], manifest: dict[str, Any], where: str
) -> TargetingReading:
    """抗针对诊断：逐族短长段对比与尺度/街道/牌力分桶，并给出稀疏度。"""
    hands = observation_hands(observations, where)
    order = block_order(manifest)
    paired: dict[tuple, dict[str, dict[str, Any]]] = defaultdict(dict)
    for hand in hands:
        key = (
            hand["player_count"],
            hand["style"],
            hand["opponent"],
            hand["seed_block"],
            hand["rotation"],
        )
        paired[key][hand["arm"]] = hand
    anomalies = sum(1 for arms in paired.values() if set(arms) != {"mixed-focus", "legacy-focus"})
    if anomalies:
        raise MixedJudgmentError(f"{where} 存在 {anomalies} 个不完整配对，停止诊断")
    groups: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    for key in paired:
        groups[(key[2], key[1])].append(key)
    short_keys: set[tuple] = set()
    for keys in groups.values():
        ordered = sorted(keys, key=lambda k: (order.get(k[3], len(order)), k[0], k[4]))
        short_keys.update(ordered[:SHORT_SEGMENT_PAIRS_PER_GROUP])

    def gain(key: tuple) -> float:
        arms = paired[key]
        return float(arms["mixed-focus"]["net_chips"]) * 10.0 - float(
            arms["legacy-focus"]["net_chips"]
        ) * 10.0

    family_values: dict[str, dict[str, list[float]]] = defaultdict(_empty_segments)
    for key in paired:
        segment = "short" if key in short_keys else "long"
        family_values[key[2]][segment].append(gain(key))
    families = tuple(
        FamilySegment(
            opponent=family,
            short_mean_bb_per_100=statistics.fmean(values["short"]),
            long_mean_bb_per_100=statistics.fmean(values["long"]),
            gain_bb_per_100=statistics.fmean(values["short"]) - statistics.fmean(values["long"]),
            short_pairs=len(values["short"]),
            long_pairs=len(values["long"]),
        )
        for family, values in sorted(family_values.items())
    )

    buckets: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(_empty_segments)
    facing = 0
    for key, arms in paired.items():
        segment = "short" if key in short_keys else "long"
        mixed_hand = arms["mixed-focus"]
        event = _first_facing_event(mixed_hand)
        strength = mixed_hand.get("focus_strength_bucket")
        strength_label = strength if isinstance(strength, str) else "None"
        buckets[(STRENGTH_BUCKET_DIMENSION, strength_label)][segment].append(gain(key))
        if event is None:
            buckets[(SCALE_BUCKET_DIMENSION, NO_FACING_BUCKET)][segment].append(gain(key))
            continue
        facing += 1
        street, amount, start_pot = event
        scale_label = _scale_bucket(amount, start_pot)
        buckets[(SCALE_BUCKET_DIMENSION, scale_label)][segment].append(gain(key))
        buckets[(STREET_BUCKET_DIMENSION, street)][segment].append(gain(key))

    def mean_or_none(values: list[float]) -> float | None:
        return statistics.fmean(values) if values else None

    readings: list[BucketReading] = []
    for (dimension, bucket), values in sorted(buckets.items()):
        short_mean = mean_or_none(values["short"])
        long_mean = mean_or_none(values["long"])
        readings.append(
            BucketReading(
                dimension=dimension,
                bucket=bucket,
                short_pairs=len(values["short"]),
                long_pairs=len(values["long"]),
                short_mean_bb_per_100=short_mean,
                long_mean_bb_per_100=long_mean,
                gain_bb_per_100=(
                    short_mean - long_mean
                    if short_mean is not None and long_mean is not None
                    else None
                ),
            )
        )
    return TargetingReading(
        pairs=len(paired),
        pairs_with_facing=facing,
        facing_share=_share(facing, len(paired)),
        families=families,
        buckets=tuple(readings),
    )


# ---------------------------------------------------------------------------
# 机制与成本
# ---------------------------------------------------------------------------


def mechanics_reading(
    reports: Sequence[tuple[str, dict[str, Any]]],
    rechecks: Sequence[tuple[str, dict[str, Any]]],
) -> MechanicsReading:
    """机制与正确性：违规、截断、摘要一致与（可选）重放一致性。

    重放一致性只在调用方给出补算工件时填写；未给出时保持 `None`，不用推测值填充。
    """
    violations: list[str] = []
    truncated = 0
    digests: dict[str, str] = {}
    for label, report in reports:
        violations.extend(str(v) for v in report.get("violations", []))
        matches = report.get("matches") or {}
        truncated += int(matches.get("truncated_hands", 0))
        digests[label] = f"{report.get('config_digest', '')}::{report.get('manifest_digest', '')}"
    consistent = len(set(digests.values())) <= 1
    hands_compared = 0
    net_exact: bool | None = None
    behavior_exact: bool | None = None
    sources: list[str] = []
    for label, recheck in rechecks:
        entry = _require(recheck, "consistency", f"{label} 的一致性字段")
        hands_compared += int(entry["hands_compared"])
        net_exact = bool(entry["net_chips_exact"]) if net_exact is None else (
            net_exact and bool(entry["net_chips_exact"])
        )
        behavior_exact = (
            bool(entry["behavior_exact"]) if behavior_exact is None else (
                behavior_exact and bool(entry["behavior_exact"])
            )
        )
        truncated += sum(int(a.get("truncated_hands", 0)) for a in recheck.get("aggregates", []))
        sources.append(label)
    return MechanicsReading(
        violations=tuple(violations),
        truncated_hands=truncated,
        digests_consistent=consistent,
        digest_sources=digests,
        replay_hands_compared=hands_compared,
        replay_net_chips_exact=net_exact,
        replay_behavior_exact=behavior_exact,
        replay_sources=tuple(sources),
        observations_checked=bool(rechecks),
    )


def cost_reading(report: dict[str, Any]) -> CostReading:
    """成本：硬预算与指导值读数，逐人数各自汇报，不以合并均值代替。"""
    timing = _require(report, "timing", "阶段回执")
    path = _require(timing, "decision_path", "阶段回执的 timing")
    groups = [
        entry
        for entry in timing.get("decision_path_groups", [])
        if entry.get("dimension") == "player_count"
    ]
    per_samples = {int(entry["group"]): int(entry["path"]["samples"]) for entry in groups}
    per_timeouts = {int(entry["group"]): int(entry["path"]["timeout_count"]) for entry in groups}
    p95_values = [float(entry["path"]["p95_ms"]) for entry in groups]
    return CostReading(
        decision_budget_ms=float(timing["decision_budget_ms"]),
        samples=int(path["samples"]),
        timeout_count=int(path["timeout_count"]),
        p50_ms=float(path["p50_ms"]),
        p95_ms=float(path["p95_ms"]),
        p99_ms=float(path["p99_ms"]),
        max_ms=float(path["max_ms"]),
        per_player_samples=per_samples,
        per_player_timeouts=per_timeouts,
        per_player_p95_range=(min(p95_values), max(p95_values)),
        hard_budget_satisfied=int(path["timeout_count"]) == 0 and not any(per_timeouts.values()),
        guidance_satisfied=(
            float(path["p95_ms"]) < float(timing["p95_guidance_ms"])
            and float(path["p99_ms"]) < float(timing["p99_guidance_ms"])
        ),
    )


PINS: tuple[str, ...] = (
    "估值单元取清单种子序的第一个主种子块；短段排序同样使用清单序，不使用数值大小。",
    "实质动作混合 = 次高份额 ≥10%；分域按类别自然分区；节点读数先合并 units 再套同一规则。",
    "类型熵 = 逐风格分布熵的算术均值；金额条件熵 = 存在额度分布的行的均值。",
    "额度锚点 = 同额合并后份额 ≥15% 的档数；达到两档记为满足。",
    (
        "机会域概率 = 先按节点合并手模式 units，再按节点等权平均；"
        "进池取 call/bet/raise，主动取 bet/raise。"
    ),
    "风格可分度 = 三个配对中至少两对在两域上各 ≥10 个百分点。",
    "风格间距离直读工件字段，不在本模块重算。",
    "稳定性 = 同一配对同一域的差值在全部种子块上符号一致（含恒为零）。",
    (
        "不劣化 = 逐人数各自取最差族；块均值双侧 t 区间（S=16，t=2.131），"
        "块极值口径并列，二者不一致判未满足。"
    ),
    "针对性诊断的短段 = 每（对手族 × 风格）按清单种子序/人数/轮换排序的前 20 对。",
    (
        "针对性诊断的面对事件 = 被测一方首次面对对手下注或加注；"
        "额度 ÷ 街起始底池（翻前 1.5 个大盲）分三档。"
    ),
)

LIMITATIONS: tuple[str, ...] = (
    "本模块只做读数复算：不产生对局、不新增样本、不改写任何工件，也不写出任何文件。",
    "读数不等于结论：判据是否满足、是否签收由冻结口径与用户决定，本模块不代作裁定。",
    "上一轮公布的机会域差值与针对性诊断面对计数无法由既有工件复现，本模块只并列呈现两类读数。",
    "固定种子块是小样本集，块间区间只是粗区间，不构成总体覆盖承诺。",
    "机械探针不是最优反应；本模块的任何读数都不构成强度、可剥削性或均衡结论。",
)


def judge(
    *,
    manifest_path: str,
    reports: Sequence[tuple[str, str]],
    observations_path: str | None = None,
    recheck_paths: Sequence[tuple[str, str]] = (),
    allow_judgment: bool = False,
) -> JudgmentPayload:
    """算出判定载荷；未显式允许时不计算。"""
    if not allow_judgment:
        raise MixedJudgmentError(
            "判定器默认拒绝：必须显式传入允许开关；写好的入口本身不构成运行许可"
        )
    manifest = _load_json(manifest_path)
    loaded: list[tuple[str, dict[str, Any]]] = []
    for label, path in reports:
        if not os.path.exists(path):
            raise MixedJudgmentError(f"{label} 工件不存在：{path}")
        loaded.append((label, _load_json(path)))
    primary_label, primary = loaded[0]
    mechanics = mechanics_reading(
        loaded,
        [(label, _load_json(path)) for label, path in recheck_paths],
    )
    cost = cost_reading(primary)
    unpredictability = unpredictability_reading(primary, manifest, primary_label)
    non_degradation = non_degradation_reading(primary, primary_label)
    families = family_reading(primary, primary_label)
    if observations_path is None:
        raise MixedJudgmentError("针对性诊断需要观测工件路径")
    diagnostic = targeting_diagnostic(_load_json(observations_path), manifest, "观测工件")
    return JudgmentPayload(
        payload_version=JUDGMENT_PAYLOAD_VERSION,
        strategy_id=str(primary.get("strategy_id", "")),
        config_digest=str(primary.get("config_digest", "")),
        manifest_digest=str(primary.get("manifest_digest", "")),
        valuation_seed_block=valuation_block(manifest),
        mechanics=mechanics,
        cost=cost,
        unpredictability=unpredictability,
        non_degradation=non_degradation,
        targeting=TargetingReadingFull(families=families, diagnostic=diagnostic),
        pins=PINS,
        limitations=LIMITATIONS,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：必须显式给出清单、阶段回执、观测工件与允许开关。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3:
        print(
            "用法：python -m tests.mixed_bot_judgment <清单路径> <阶段回执路径> <观测工件路径> "
            "--allow-judgment [--recheck=<标签>=<路径> ...]",
            file=sys.stderr,
        )
        return 2
    manifest_path, report_path, observations_path = args[0], args[1], args[2]
    allow = "--allow-judgment" in args[3:]
    rechecks: list[tuple[str, str]] = []
    for token in args[3:]:
        if token.startswith("--recheck="):
            label, _, path = token[len("--recheck=") :].partition("=")
            rechecks.append((label or path, path))
    payload = judge(
        manifest_path=manifest_path,
        reports=[("阶段回执", report_path)],
        observations_path=observations_path,
        recheck_paths=rechecks,
        allow_judgment=allow,
    )
    print(payload.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - 手动 opt-in 入口
    raise SystemExit(main())
