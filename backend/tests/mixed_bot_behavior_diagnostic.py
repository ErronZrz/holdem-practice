"""只在开发期使用的只读行为诊断：把已落盘观测按「牌力 × 街道 × 面对状态 × 人数」桶化。

为什么需要本模块：L4 与 L3 的负差此前只能落到「净筹码」这一层，无法回答「在什么局面下、
哪个座位做了什么不同的动作」。本模块把**动作口径**与**净筹码口径**放进同一批桶，
使「某类局面暴露什么问题」可以复算，而不是靠会话内的临时统计。

纪律：
- 只读调用方给出的已落盘观测工件，绝不改写任何证据文件，也不写出任何文件；
- 不产生对局、不新增样本、不使用随机数：同一输入必得同一读数；
- 默认拒绝：只有显式传入允许开关才计算，模块被导入或被 pytest 收集都不触发计算；
- 本模块的分桶定义是**本模块自己的钉子**，先于任何读数固定；它们**不在**判定器已钉死的
  口径之内，因此**不得**与判定口径或历史轮次的任何桶化数字跨轮比较。
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from tests.mixed_bot_judgment import (
    STREET_ORDER,
    MixedJudgmentError,
    _first_facing_event,
    observation_hands,
    pair_table,
)

DIAGNOSTIC_PAYLOAD_VERSION = "mixed-behavior-diagnostic-payload.v1"

# ---------------------------------------------------------------------------
# 本模块的实现层钉子（口径的可执行定义）
# ---------------------------------------------------------------------------

# 两个臂的名称沿用配对口径，不得改名，否则与判定器的配对实现不再一致。
ARM_MIXED = "mixed-focus"
ARM_LEGACY = "legacy-focus"

# 面对状态的两种取值；「面对」指焦点座位在手内首次面对对手的下注或加注。
FACING_STATE_FACING = "facing-bet"
FACING_STATE_NO_FACING = "no-facing-bet"
FACING_STATES: tuple[str, ...] = (FACING_STATE_FACING, FACING_STATE_NO_FACING)

# 未面对下注时没有「首次面对事件」，街道改取焦点座位在手内**最后一次**行动所在的街；
# 焦点座位整手未行动时单列，不用其它街代替。
NO_ACTION_STREET = "no-action"
STREET_LABELS: tuple[str, ...] = (*STREET_ORDER, NO_ACTION_STREET)

# 牌力档直读工件字段；缺失或非字符串时单列，不用其它档代替。
NO_STRENGTH_LABEL = "None"

# 行为构成只统计**焦点座位**的动作：那才是被测策略自己的选择。
FOCUS_SEAT_RULE = "焦点座位 = 轮换号 % 人数；行为构成只计该座位的动作。"

# 大盲筹码数：把净筹码换算成每百手收益时使用；取值与夹具的翻前起始底池口径一致。
BIG_BLIND_CHIPS = 10

# 动作标签的固定顺序，避免读数依赖字典顺序。
ACTION_LABELS: tuple[str, ...] = ("fold", "check", "call", "bet", "raise")
ACTIVE_ACTION_LABELS: tuple[str, ...] = ("bet", "raise")

# 桶的最小样本量：低于该值的桶照样输出，但标记为稀疏，避免被当作结论。
SPARSE_BUCKET_MIN_PAIRS = 30

FACING_STATE_DIMENSION = "面对状态"
STRENGTH_DIMENSION = "牌力"
STREET_DIMENSION = "街道"
PLAYER_COUNT_DIMENSION = "人数"
STYLE_DIMENSION = "风格"
CELL_DIMENSIONS: tuple[str, ...] = (
    FACING_STATE_DIMENSION,
    STRENGTH_DIMENSION,
    STREET_DIMENSION,
    PLAYER_COUNT_DIMENSION,
    STYLE_DIMENSION,
)


class BehaviorDiagnosticError(MixedJudgmentError):
    """诊断前置条件失败时抛出；不产出读数、不静默继续。"""


class _FrozenModel(BaseModel):
    """诊断载荷的公共基类：冻结且禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class BucketReading(_FrozenModel):
    """一个边际桶上的净筹码差与两臂的行为构成。"""

    dimension: str
    bucket: str
    pairs: int
    sparse: bool
    diff_net_chips: int
    mean_bb_per_100_diff: float
    mixed_active_share: float
    legacy_active_share: float
    mixed_action_units: dict[str, int]
    legacy_action_units: dict[str, int]


class CellReading(_FrozenModel):
    """一个五维格上的净筹码差与两臂的行为构成。"""

    player_count: int
    style: str
    strength: str
    street: str
    facing_state: str
    pairs: int
    sparse: bool
    diff_net_chips: int
    mean_bb_per_100_diff: float
    mixed_active_share: float
    legacy_active_share: float
    active_share_gap: float


class BehaviorDiagnosticPayload(_FrozenModel):
    """诊断载荷：边际桶 + 五维格 + 集中度与固定声明。"""

    payload_version: str
    strategy_id: str
    pairs: int
    pair_anomalies: int
    facing_pairs: int
    no_facing_pairs: int
    total_diff_net_chips: int
    facing_diff_net_chips: int
    no_facing_diff_net_chips: int
    no_facing_diff_share: float
    by_facing_state: tuple[BucketReading, ...]
    by_strength: tuple[BucketReading, ...]
    by_street: tuple[BucketReading, ...]
    by_player_count: tuple[BucketReading, ...]
    cells: tuple[CellReading, ...]
    pins: tuple[str, ...]
    limitations: tuple[str, ...]


# ---------------------------------------------------------------------------
# 只读装载
# ---------------------------------------------------------------------------


def _load_json(path: str) -> dict[str, Any]:
    """按只读方式载入一份已落盘工件。"""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def focused_arm_key(hand: dict[str, Any]) -> tuple:
    """配对键：与判定器的配对口径一致，用于把两臂配成对。"""
    return (
        hand["player_count"],
        hand["style"],
        hand["opponent"],
        hand["seed_block"],
        hand["rotation"],
    )


def focus_seat_index(hand: dict[str, Any]) -> int:
    """焦点座位：轮换号对人数取模。"""
    player_count = int(hand["player_count"])
    if player_count <= 0:
        raise BehaviorDiagnosticError("人数必须为正，无法确定焦点座位")
    return int(hand["rotation"]) % player_count


def focus_action_rows(hand: dict[str, Any]) -> list[dict[str, Any]]:
    """焦点座位在该手内的全部动作行，按原顺序。"""
    seat = focus_seat_index(hand)
    return [row for row in hand["actions"] if int(row["seat"]) == seat]


def _unit_map(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """把动作行折成「动作 → 次数」；只保留已登记的动作标签。"""
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        label = str(row["action"])
        if label in ACTION_LABELS:
            counts[label] += 1
    return {label: counts[label] for label in ACTION_LABELS if counts[label]}


def _active_share(units: dict[str, int]) -> float:
    """主动占比：bet 与 raise 次数占全部已登记动作的比例。"""
    total = sum(units.values())
    if not total:
        return 0.0
    return sum(units.get(label, 0) for label in ACTIVE_ACTION_LABELS) / total


def facing_state_and_street(hand: dict[str, Any]) -> tuple[str, str]:
    """返回（面对状态，街道）：面对时取首次面对事件的街，未面对时取焦点最后一手动作的街。"""
    event = _first_facing_event(hand)
    if event is not None:
        return FACING_STATE_FACING, str(event[0])
    rows = focus_action_rows(hand)
    if not rows:
        return FACING_STATE_NO_FACING, NO_ACTION_STREET
    return FACING_STATE_NO_FACING, str(rows[-1]["street"])


def strength_label(hand: dict[str, Any]) -> str:
    """牌力档：直读工件字段，缺失或非字符串时单列。"""
    value = hand.get("focus_strength_bucket")
    return value if isinstance(value, str) and value else NO_STRENGTH_LABEL


def _bucket_attributes(hand: dict[str, Any]) -> dict[str, str]:
    """一个配对在五个维度上的取值；维度由**被测一方**的手决定。"""
    state, street = facing_state_and_street(hand)
    return {
        FACING_STATE_DIMENSION: state,
        STRENGTH_DIMENSION: strength_label(hand),
        STREET_DIMENSION: street,
        PLAYER_COUNT_DIMENSION: str(int(hand["player_count"])),
        STYLE_DIMENSION: str(hand["style"]),
    }


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


class _PairFacts:
    """一个配对的三项事实：净筹码差、每百手差与两臂的焦点动作构成。"""

    __slots__ = ("diff_net_chips", "diff_bb_per_100", "mixed_units", "legacy_units", "attributes")

    def __init__(self, arms: dict[str, dict[str, Any]]) -> None:
        mixed = arms[ARM_MIXED]
        legacy = arms[ARM_LEGACY]
        self.diff_net_chips = int(mixed["net_chips"]) - int(legacy["net_chips"])
        self.diff_bb_per_100 = self.diff_net_chips * (100.0 / BIG_BLIND_CHIPS)
        self.mixed_units = _unit_map(focus_action_rows(mixed))
        self.legacy_units = _unit_map(focus_action_rows(legacy))
        self.attributes = _bucket_attributes(mixed)


def _facing_state_of(fact: _PairFacts) -> str:
    """取一个配对的面对状态。"""
    return fact.attributes[FACING_STATE_DIMENSION]


def _add_units(target: dict[str, int], units: dict[str, int]) -> None:
    for label, count in units.items():
        target[label] += count


def _reading(
    dimension: str,
    bucket: str,
    facts: Sequence[_PairFacts],
) -> BucketReading:
    """把一个桶里的事实折成一行读数。"""
    mixed_units: dict[str, int] = defaultdict(int)
    legacy_units: dict[str, int] = defaultdict(int)
    for fact in facts:
        _add_units(mixed_units, fact.mixed_units)
        _add_units(legacy_units, fact.legacy_units)
    mixed_final = {label: mixed_units[label] for label in ACTION_LABELS if mixed_units[label]}
    legacy_final = {label: legacy_units[label] for label in ACTION_LABELS if legacy_units[label]}
    return BucketReading(
        dimension=dimension,
        bucket=bucket,
        pairs=len(facts),
        sparse=len(facts) < SPARSE_BUCKET_MIN_PAIRS,
        diff_net_chips=sum(fact.diff_net_chips for fact in facts),
        mean_bb_per_100_diff=statistics.fmean(fact.diff_bb_per_100 for fact in facts),
        mixed_active_share=_active_share(mixed_final),
        legacy_active_share=_active_share(legacy_final),
        mixed_action_units=mixed_final,
        legacy_action_units=legacy_final,
    )


def _marginal(
    dimension: str,
    facts: Sequence[_PairFacts],
) -> tuple[BucketReading, ...]:
    """按单一维度切边际桶；桶序固定，不依赖出现顺序。"""
    grouped: dict[str, list[_PairFacts]] = defaultdict(list)
    for fact in facts:
        grouped[fact.attributes[dimension]].append(fact)
    return tuple(_reading(dimension, bucket, grouped[bucket]) for bucket in sorted(grouped))


def _cells(facts: Sequence[_PairFacts]) -> tuple[CellReading, ...]:
    """按五个维度切格；格序固定，不依赖出现顺序。"""
    grouped: dict[tuple[str, ...], list[_PairFacts]] = defaultdict(list)
    for fact in facts:
        grouped[tuple(fact.attributes[name] for name in CELL_DIMENSIONS)].append(fact)
    readings: list[CellReading] = []
    for key in sorted(grouped):
        bucket = grouped[key]
        row = _reading("格", "×".join(key), bucket)
        readings.append(
            CellReading(
                player_count=int(key[3]),
                style=key[4],
                strength=key[1],
                street=key[2],
                facing_state=key[0],
                pairs=row.pairs,
                sparse=row.sparse,
                diff_net_chips=row.diff_net_chips,
                mean_bb_per_100_diff=row.mean_bb_per_100_diff,
                mixed_active_share=row.mixed_active_share,
                legacy_active_share=row.legacy_active_share,
                active_share_gap=row.mixed_active_share - row.legacy_active_share,
            )
        )
    return tuple(readings)


PINS: tuple[str, ...] = (
    "配对键与两臂名沿用判定器口径；配对不完整即显式失败。",
    "面对状态 = 焦点座位在手内是否首次面对对手的下注或加注；面对时街道取该事件的街。",
    "未面对下注时街道取焦点座位手内最后一次动作所在的街；整手未行动单列，不用其它街代替。",
    "牌力档直读工件字段；缺失或非字符串时单列。",
    "行为构成只统计焦点座位的动作；主动占比 = bet 与 raise 占全部已登记动作的比例。",
    "净筹码换算每百手收益时使用固定的大盲筹码数；换算常量与夹具口径一致。",
    f"样本量低于 {SPARSE_BUCKET_MIN_PAIRS} 对的桶照样输出并标记稀疏。",
)

LIMITATIONS: tuple[str, ...] = (
    "本模块只做读数复算：不产生对局、不新增样本、不改写任何工件，也不写出任何文件。",
    "本模块的分桶定义不属于判定器已钉死的口径，读数不得与判定口径或任何历史轮次的桶化数字跨轮比较。",
    "净筹码差是配对口径的差值；配对单元为单手时，单个极端底池即可主导一个桶的读数。",
    "行为构成是**动作次数**口径，不是按局面加权的概率；同一手内的多次动作权重相同。",
    "稀疏桶上的差值不构成结论；本模块不给出任何强度、可剥削性或均衡判断。",
    "机械观测不包含对手暗牌；本模块只读取行动者视角的公开记录。",
)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def diagnose(
    *,
    observations_path: str,
    allow_diagnosis: bool = False,
    report_path: str | None = None,
) -> BehaviorDiagnosticPayload:
    """算出行为诊断载荷；未显式允许时不计算。"""
    if not allow_diagnosis:
        raise BehaviorDiagnosticError(
            "行为诊断默认拒绝：必须显式传入允许开关；写好的入口本身不构成运行许可"
        )
    if not os.path.exists(observations_path):
        raise BehaviorDiagnosticError(f"观测工件不存在：{observations_path}")
    observations = _load_json(observations_path)
    try:
        hands = observation_hands(observations, "观测工件")
    except MixedJudgmentError as error:
        # 逐手粒度缺失属于本模块的前置条件失败，统一成诊断层错误。
        raise BehaviorDiagnosticError(str(error)) from error
    if report_path is not None:
        _cross_check_bb_identity(report_path)
    try:
        paired, anomalies = pair_table(hands, "观测工件")
    except MixedJudgmentError as error:
        raise BehaviorDiagnosticError(str(error)) from error
    facts = [_PairFacts(arms) for arms in paired.values()]
    facing = [fact for fact in facts if _facing_state_of(fact) == FACING_STATE_FACING]
    no_facing = [fact for fact in facts if _facing_state_of(fact) == FACING_STATE_NO_FACING]
    total_diff = sum(fact.diff_net_chips for fact in facts)
    no_facing_diff = sum(fact.diff_net_chips for fact in no_facing)
    return BehaviorDiagnosticPayload(
        payload_version=DIAGNOSTIC_PAYLOAD_VERSION,
        strategy_id=str(observations.get("strategy_id", "")),
        pairs=len(facts),
        pair_anomalies=anomalies,
        facing_pairs=len(facing),
        no_facing_pairs=len(no_facing),
        total_diff_net_chips=total_diff,
        facing_diff_net_chips=total_diff - no_facing_diff,
        no_facing_diff_net_chips=no_facing_diff,
        no_facing_diff_share=(no_facing_diff / total_diff) if total_diff else 0.0,
        by_facing_state=_marginal(FACING_STATE_DIMENSION, facts),
        by_strength=_marginal(STRENGTH_DIMENSION, facts),
        by_street=_marginal(STREET_DIMENSION, facts),
        by_player_count=_marginal(PLAYER_COUNT_DIMENSION, facts),
        cells=_cells(facts),
        pins=PINS,
        limitations=LIMITATIONS,
    )


def _cross_check_bb_identity(report_path: str) -> None:
    """核对已落盘报告里的每百手换算与固定大盲一致；不一致即失败，不静默继续。"""
    if not os.path.exists(report_path):
        raise BehaviorDiagnosticError(f"报告工件不存在：{report_path}")
    matches = _load_json(report_path).get("matches")
    if not isinstance(matches, dict) or not isinstance(matches.get("rows"), list):
        raise BehaviorDiagnosticError("报告不含逐行对抗数据，无法核对换算常量")
    for row in matches["rows"]:
        measured = float(row["net_chips"]) * (100.0 / BIG_BLIND_CHIPS)
        if abs(measured - float(row["bb_per_100"])) > 1e-9:
            raise BehaviorDiagnosticError("报告的每百手换算与固定大盲不一致，停止诊断")


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：必须显式给出观测工件与允许开关。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "用法：python -m tests.mixed_bot_behavior_diagnostic <观测工件路径> "
            "--allow-diagnosis [--report=<阶段报告路径>]",
            file=sys.stderr,
        )
        return 2
    observations_path = args[0]
    allow = "--allow-diagnosis" in args[1:]
    report_path: str | None = None
    for token in args[1:]:
        if token.startswith("--report="):
            report_path = token[len("--report=") :] or None
    payload = diagnose(
        observations_path=observations_path,
        allow_diagnosis=allow,
        report_path=report_path,
    )
    print(payload.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - 手动 opt-in 入口
    raise SystemExit(main())
