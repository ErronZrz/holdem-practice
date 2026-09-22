"""阶段回执的确定性补算：补齐按块聚合、VPIP/PFR 与类别明细，并复核可重放性。

纪律：
- 只有被显式调用时才运行；默认 pytest 不触发任何对局或矩阵；
- 只读取已冻结清单与既有阶段回执，绝不改写任何证据文件；输出目录只创建、不覆盖；
- 逐手净筹码或行为指标与既有回执不一致时立即中止上报，不写报告、不解释差异、不挑好看的读数。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.strategy.mixed_policy import MixedStyle

from .mixed_bot_states import MIXED_BIG_BLIND, MixedFixtureManifest
from .mixed_bot_validation import (
    ADVERSARIAL_ARMS,
    HandOutcome,
    MixedCategoryBehavior,
    MixedMatchFamilyRow,
    MixedStyleJsDistance,
    MixedValidationReport,
    adversarial_schedule,
    collect_behavior,
    peak_rss_bytes,
    play_adversarial_hand,
    prepare_output_dir,
    strategy_rules,
)

RECHECK_SCHEMA_VERSION = "mixed-recheck.v1"
# 已登记的种子块个数与其中文写法：块数不同时措辞必须跟着变，不能沿用别的块数。
RECHECK_BLOCK_COUNT_WORDS: dict[int, str] = {4: "四", 8: "八"}


def recheck_limitations(seed_block_count: int) -> tuple[str, ...]:
    """按回执实际的种子块个数生成块统计口径说明；未登记的块数显式失败。"""
    try:
        word = RECHECK_BLOCK_COUNT_WORDS[seed_block_count]
    except KeyError:
        raise MixedRecheckError(f"未登记的种子块个数：{seed_block_count}") from None
    return (
        "补算只把既有回执缺失的指标按确定性口径重算，不产生新对局、不产生新样本、不追加强制种子。",
        "VPIP/PFR 是焦点座位逐手的机械统计，不是范围强度、盈亏平衡频率或均衡频率。",
        f"按主种子块统计只有{word}个固定块，不出具具有总体覆盖承诺的置信区间。",
        "风格间距离只说明分布差异存在，不说明哪一档更强、更弱或更难被针对。",
    )


RECHECK_LIMITATIONS: tuple[str, ...] = recheck_limitations(4)


class MixedRecheckError(RuntimeError):
    """补算前置条件或一致性检查失败时抛出；不写报告、不静默继续。"""


class _FrozenModel(BaseModel):
    """补算报告族的公共基类：冻结且禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class MixedMatchAggregateRow(_FrozenModel):
    """一个（人数 × 风格 × 对手 × arm）格的汇总：块内先聚合，再给块间统计。"""

    player_count: int
    style: str
    opponent: str
    arm: str
    hands: int = Field(ge=0)
    net_chips: int
    bb_per_100: float
    block_means: tuple[float, ...]
    block_std: float
    block_min: float
    block_max: float
    vpip: float
    pfr: float
    aggression_rate: float
    truncated_hands: int = Field(ge=0)


class MixedWorstOpponent(_FrozenModel):
    """一种（风格 × arm）下按 bb/100 计最差的对手族。"""

    style: str
    arm: str
    opponent: str
    bb_per_100: float


class MixedRecheckConsistency(_FrozenModel):
    """补算与既有回执的一致性检查结果。"""

    source_receipt: str
    source_receipt_sha256: str
    hands_compared: int = Field(ge=0)
    net_chips_exact: bool
    behavior_exact: bool
    note: str = "逐手净筹码按排期顺序完全一致；任何差异都会中止本次补算，不写报告。"


class MixedRecheckBehavior(_FrozenModel):
    """补算出的行为指标：风格间距离与按类别明细。"""

    direct_distributions: int = Field(ge=0)
    style_js_distances: tuple[MixedStyleJsDistance, ...]
    categories: tuple[MixedCategoryBehavior, ...]


class MixedRecheckResources(_FrozenModel):
    """补算自身的资源读数。"""

    wall_seconds: float = Field(ge=0.0)
    cpu_seconds: float = Field(ge=0.0)
    peak_rss_bytes: int | None = None
    output_bytes: int = Field(ge=0)
    single_process: bool = True
    parallel: bool = False


class MixedRecheckReport(_FrozenModel):
    """补算报告：字段闭集，不夹带底牌、种子或任意元数据。"""

    schema_version: Literal["mixed-recheck.v1"] = RECHECK_SCHEMA_VERSION
    strategy_id: str
    code_identity: str
    config_digest: str
    manifest_digest: str
    source_stage: str
    status: str
    environment: str
    consistency: MixedRecheckConsistency
    aggregates: tuple[MixedMatchAggregateRow, ...]
    worst_opponents: tuple[MixedWorstOpponent, ...]
    behavior: MixedRecheckBehavior
    resources: MixedRecheckResources
    limitations: tuple[str, ...] = RECHECK_LIMITATIONS


@dataclass
class _CellTally:
    """一个格子的逐手累计，按主种子块分桶。"""

    net: list[int] = field(default_factory=list)
    blocks: dict[int, list[int]] = field(default_factory=dict)
    vpip: int = 0
    pfr: int = 0
    aggressive: int = 0
    actions: int = 0
    truncated: int = 0


def aggregate_matches(
    schedule: Sequence[tuple[int, MixedStyle, str, str, int, int]],
    outcomes: Sequence[HandOutcome],
) -> tuple[tuple[MixedMatchAggregateRow, ...], tuple[MixedWorstOpponent, ...]]:
    """汇总对照结果：块内先按轮换聚合，再给每个种子块的均值、样本标准差与最小最大值。"""
    if len(schedule) != len(outcomes):
        raise MixedRecheckError("排期长度与结果数量不一致，无法汇总")
    # 种子块顺序取自排期自身，使换过主种子的清单也能给出正确的块统计。
    seed_blocks = tuple(dict.fromkeys(entry[0] for entry in schedule))
    cells: dict[tuple[int, str, str, str], _CellTally] = {}
    for entry, outcome in zip(schedule, outcomes, strict=True):
        seed, style, opponent, arm, player_count, _rotation = entry
        tally = cells.setdefault((player_count, style.value, opponent, arm), _CellTally())
        tally.net.append(outcome.net_chips)
        tally.blocks.setdefault(seed, []).append(outcome.net_chips)
        tally.vpip += 1 if outcome.vpip else 0
        tally.pfr += 1 if outcome.pfr else 0
        tally.aggressive += outcome.aggressive_actions
        tally.actions += outcome.total_actions
        tally.truncated += 1 if outcome.truncated else 0
    rows: list[MixedMatchAggregateRow] = []
    for (player_count, style, opponent, arm), tally in sorted(cells.items()):
        hands = len(tally.net)
        block_means = tuple(
            statistics.fmean(tally.blocks[seed])
            for seed in seed_blocks
            if seed in tally.blocks
        )
        rows.append(
            MixedMatchAggregateRow(
                player_count=player_count,
                style=style,
                opponent=opponent,
                arm=arm,
                hands=hands,
                net_chips=sum(tally.net),
                bb_per_100=statistics.fmean(tally.net) / MIXED_BIG_BLIND * 100.0,
                block_means=block_means,
                block_std=statistics.stdev(block_means) if len(block_means) > 1 else 0.0,
                block_min=min(block_means),
                block_max=max(block_means),
                vpip=tally.vpip / hands,
                pfr=tally.pfr / hands,
                aggression_rate=tally.aggressive / tally.actions if tally.actions else 0.0,
                truncated_hands=tally.truncated,
            )
        )
    worst: list[MixedWorstOpponent] = []
    for style in MixedStyle:
        for arm in ADVERSARIAL_ARMS:
            candidates = [
                row for row in rows if row.style == style.value and row.arm == arm
            ]
            if not candidates:
                continue
            picked = min(candidates, key=lambda row: row.bb_per_100)
            worst.append(
                MixedWorstOpponent(
                    style=style.value,
                    arm=arm,
                    opponent=picked.opponent,
                    bb_per_100=picked.bb_per_100,
                )
            )
    return tuple(rows), tuple(worst)


def compare_net_chips(
    rows: Sequence[MixedMatchFamilyRow],
    schedule: Sequence[tuple[int, MixedStyle, str, str, int, int]],
    outcomes: Sequence[HandOutcome],
) -> int:
    """逐手比对分组键与净筹码；任何差异立即抛错，不返回部分结论。"""
    if len(rows) != len(outcomes):
        raise MixedRecheckError(
            f"回执手数 {len(rows)} 与重算手数 {len(outcomes)} 不一致，停止补算"
        )
    for index, (row, entry, outcome) in enumerate(
        zip(rows, schedule, outcomes, strict=True)
    ):
        expected = (entry[4], entry[1].value, entry[2], entry[3])
        actual = (row.player_count, row.style, row.opponent, row.arm)
        if actual != expected:
            raise MixedRecheckError(f"第 {index} 手的分组键与排期不一致：{actual} != {expected}")
        if row.net_chips != outcome.net_chips:
            raise MixedRecheckError(
                f"第 {index} 手净筹码不一致：回执 {row.net_chips} != 重算 {outcome.net_chips}"
            )
    return len(rows)


def behavior_matches_receipt(
    receipt: MixedValidationReport,
    rebuilt: object,
) -> bool:
    """重算的行为读数必须与回执逐项完全相同，含熵与分布计数。"""
    received = {row.style: row for row in receipt.behavior.styles}
    for row in rebuilt.styles:
        expected = received.get(row.style)
        if expected is None:
            return False
        if (
            expected.distributions != row.distributions
            or expected.action_entropy != row.action_entropy
            or expected.scale_entropy != row.scale_entropy
            or expected.effective_scale_count != row.effective_scale_count
            or expected.structural_single_size != row.structural_single_size
            or expected.no_active_candidate != row.no_active_candidate
        ):
            return False
    return receipt.behavior.direct_distributions == rebuilt.direct_distributions


def _sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recheck(
    *,
    manifest: MixedFixtureManifest | None,
    receipt: MixedValidationReport | None,
    receipt_path: str | None,
    allow_recheck: bool = False,
    output_dir: str | None = None,
) -> MixedRecheckReport:
    """按既有回执的同一清单与同一主种子确定性重算，并补出缺失的指标。"""
    if not allow_recheck:
        raise MixedRecheckError("补算属于评测实跑，须显式开启；默认拒绝")
    if manifest is None or receipt is None:
        raise MixedRecheckError("必须同时提供已冻结清单与阶段回执")
    if receipt.status != "completed":
        raise MixedRecheckError("补算只针对状态为 completed 的回执")
    if receipt.stage not in ("A", "B"):
        raise MixedRecheckError(f"不支持的阶段：{receipt.stage}")
    if receipt_path is None:
        raise MixedRecheckError("必须给出回执文件路径，用于记录来源与校验摘要")
    # 回执与清单必须是同一个身份，否则重算出来的不是同一套分布。
    if receipt.strategy_id != manifest.strategy_id:
        raise MixedRecheckError("回执身份与清单身份不一致，停止补算且不写报告")
    rules = strategy_rules(manifest)
    directory = prepare_output_dir(output_dir)
    started = time.perf_counter()
    cpu_started = time.process_time()

    rebuilt_behavior = collect_behavior(manifest, allow_full=True)
    if not behavior_matches_receipt(receipt, rebuilt_behavior):
        raise MixedRecheckError("重算的行为指标与既有回执不一致，停止补算且不写报告")

    schedule = adversarial_schedule(receipt.stage)
    outcomes = [
        play_adversarial_hand(
            seed=seed,
            style=style,
            opponent=opponent,
            arm=arm,
            player_count=player_count,
            rotation=rotation,
            rules=rules,
        )
        for seed, style, opponent, arm, player_count, rotation in schedule
    ]
    compared = compare_net_chips(receipt.matches.rows, schedule, outcomes)
    aggregates, worst = aggregate_matches(schedule, outcomes)

    report = MixedRecheckReport(
        strategy_id=receipt.strategy_id,
        code_identity=receipt.code_identity,
        config_digest=receipt.config_digest,
        manifest_digest=receipt.manifest_digest,
        source_stage=receipt.stage,
        status="completed",
        environment=f"{platform.platform()} / python {sys.version.split()[0]}",
        consistency=MixedRecheckConsistency(
            source_receipt=os.path.abspath(receipt_path),
            source_receipt_sha256=_sha256_of(receipt_path),
            hands_compared=compared,
            net_chips_exact=True,
            behavior_exact=True,
        ),
        aggregates=aggregates,
        worst_opponents=worst,
        behavior=MixedRecheckBehavior(
            direct_distributions=rebuilt_behavior.direct_distributions,
            style_js_distances=rebuilt_behavior.style_js_distances,
            categories=rebuilt_behavior.categories,
        ),
        resources=MixedRecheckResources(
            wall_seconds=time.perf_counter() - started,
            cpu_seconds=time.process_time() - cpu_started,
            peak_rss_bytes=peak_rss_bytes(),
            output_bytes=0,
        ),
        limitations=recheck_limitations(len(receipt.matches.seed_blocks)),
    )
    if directory is not None:
        target = os.path.join(directory, f"mixed-recheck-stage-{receipt.stage}.json")
        if os.path.exists(target):
            raise MixedRecheckError("补算报告目标文件已存在，不得覆盖")
        payload = report.model_dump_json(indent=2)
        for _ in range(3):
            report = report.model_copy(
                update={
                    "resources": report.resources.model_copy(
                        update={"output_bytes": len(payload.encode("utf-8"))}
                    )
                }
            )
            revised = report.model_dump_json(indent=2)
            if revised == payload:
                break
            payload = revised
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(payload)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：必须显式给出清单、阶段回执、输出目录与允许补算的开关。"""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 4:
        print(
            "用法：python -m tests.mixed_bot_recheck <清单路径> <阶段回执路径> <输出目录> "
            "--allow-recheck",
            file=sys.stderr,
        )
        return 2
    manifest_path, receipt_path, output_dir = args[0], args[1], args[2]
    allow = "--allow-recheck" in args[3:]
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = MixedFixtureManifest.model_validate(json.load(handle))
    with open(receipt_path, encoding="utf-8") as handle:
        receipt = MixedValidationReport.model_validate(json.load(handle))
    report = recheck(
        manifest=manifest,
        receipt=receipt,
        receipt_path=receipt_path,
        allow_recheck=allow,
        output_dir=output_dir,
    )
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - 手动 opt-in 入口
    raise SystemExit(main())
