"""新 Bot 的离线验证报告与显式 opt-in 运行入口（测试侧永久能力）。

纪律：
- 只有被显式调用时才会运行；默认 pytest 不触发任何性能矩阵或对抗对局；
- 运行前必须显式给出已冻结清单与允许执行的阶段，阶段 B 还必须有阶段 A 的实测回执；
- 不访问、不修改任何封存 campaign 目录；输出目录只创建、不覆盖已有文件；
- 出现合法性、信息边界或摘要一致性错误时，按冻结的停止条件落 stopped-* 报告并保留
  已完成计数，不抛穿、不丢样本、不自动重试。
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
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.poker.actions import Action, ActionType, IllegalActionError, LegalActions
from app.poker.cards import Card
from app.poker.engine import PokerEngine
from app.poker.evaluator import evaluate_fast
from app.poker.hand import HandCategory
from app.poker.state import GameState, Street
from app.strategy.heuristic import HeuristicStrategy
from app.strategy.lookup_budget import (
    DECISION_BUDGET_MS,
    P95_GUIDANCE_MS,
    P99_GUIDANCE_MS,
    percentile_ms,
)
from app.strategy.mixed_context import (
    MixedContextError,
    MixedSummaryTracker,
    mixed_state,
    require_mixed_input,
)
from app.strategy.mixed_policy import (
    HAND_MODE_ROLL_BOUNDS,
    MIXED_DISTRIBUTION_SCHEMA_VERSION,
    MIXED_DISTRIBUTION_UNITS,
    STYLE_PARAMETERS,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
    MIXED_STRATEGY_IDENTIFIER_V4,
    MIXED_STRATEGY_IDENTIFIER_V5,
    MIXED_STRATEGY_IDENTIFIER_V6,
    MIXED_STRATEGY_IDENTIFIER_V7,
    MixedDistribution,
    MixedLocalStrategy,
    MixedSeatPolicy,
    MixedStrategyError,
    rules_for_identifier,
)
from app.strategy.projection import project_for_actor

from .mixed_bot_states import (
    MIXED_APPLICABLE_NODE_COUNT,
    MIXED_BIG_BLIND,
    MIXED_DEPTHS_BB,
    MIXED_IQV2_NODE_ID_SUFFIX,
    MIXED_IQV3_NODE_ID_SUFFIX,
    MIXED_IQV4_NODE_ID_SUFFIX,
    MIXED_IQV_NODE_ID_SUFFIX,
    MIXED_PLANNED_SLOT_COUNT,
    MIXED_PLAYER_COUNTS,
    MIXED_SMALL_BLIND,
    MIXED_STREETS,
    MIXED_STRUCTURAL_HOLE_COUNT,
    MixedFixtureError,
    MixedFixtureManifest,
    MixedNodeFixture,
    apply_node,
    build_frozen_iqv2_nodes,
    build_frozen_iqv3_nodes,
    build_frozen_iqv4_nodes,
    build_frozen_iqv_nodes,
    build_frozen_manifest,
    build_iqv2_node,
    build_iqv3_node,
    build_iqv4_node,
    build_iqv_node,
    build_node,
    manifest_json,
)

MIXED_VALIDATION_SCHEMA_VERSION = "mixed-validation.v1"
# 逐节点明细引入后的报告版本；上一版的字段与语义保持不变，历史回执继续可读。
MIXED_VALIDATION_SCHEMA_VERSION_V2 = "mixed-validation.v2"
# 逐手观测工件的版本：单独落盘，不并入主报告，避免主报告体积与职责膨胀。
MIXED_OBSERVATIONS_SCHEMA_VERSION = "mixed-observations.v1"
# 验证身份独立于任何既有评测身份，不是任何既有运行许可的续用。
MIXED_VALIDATION_IDENTITY = "mixed-local-v1-validation"
# 复用既有主种子数值，但必须重新获得产品验证运行许可。
MIXED_MAIN_SEEDS: tuple[int, ...] = (1215, 20260918, 3311, 7926)

# 第二套主种子：与既有四个主种子全部不同，取值由固定派生规则生成，不按任何读数挑选。
MIXED_IQV_SEED_PREFIX = "mixed-local-iqv-v1:seed:"
MIXED_IQV_MAIN_SEED_COUNT = 8


def derive_iqv_main_seeds(count: int = MIXED_IQV_MAIN_SEED_COUNT) -> tuple[int, ...]:
    """按冻结规则复算第二套主种子：派生串的 SHA-256 前 4 字节按大端解释为无符号整数。"""
    if count < 1:
        raise MixedValidationAuthorizationError("主种子个数必须为正")
    return tuple(
        int.from_bytes(
            hashlib.sha256(f"{MIXED_IQV_SEED_PREFIX}{index}".encode()).digest()[:4],
            "big",
        )
        for index in range(1, count + 1)
    )


MIXED_IQV_MAIN_SEEDS: tuple[int, ...] = (
    184808075,
    3360391539,
    2335308857,
    1406656097,
    318027253,
    1141464625,
    2667074870,
    4248100349,
)

# 第三套主种子：换独立派生前缀以区别于第二套；数目加倍只为增加块数，不改任何门槛。
MIXED_IQV2_SEED_PREFIX = "mixed-local-iqv-v2:seed:"
MIXED_IQV2_MAIN_SEED_COUNT = 16


def derive_iqv2_main_seeds(count: int = MIXED_IQV2_MAIN_SEED_COUNT) -> tuple[int, ...]:
    """按冻结规则复算第三套主种子：派生串的 SHA-256 前 4 字节按大端解释为无符号整数。"""
    if count < 1:
        raise MixedValidationAuthorizationError("主种子个数必须为正")
    return tuple(
        int.from_bytes(
            hashlib.sha256(f"{MIXED_IQV2_SEED_PREFIX}{index}".encode()).digest()[:4],
            "big",
        )
        for index in range(1, count + 1)
    )


MIXED_IQV2_MAIN_SEEDS: tuple[int, ...] = (
    2518403890,
    3304231143,
    279877713,
    626104627,
    299830952,
    2327033474,
    2624733157,
    849177851,
    1676376096,
    3564845513,
    2849348124,
    542008929,
    2910136284,
    2975201120,
    3882415196,
    4160511683,
)

# 第四套主种子：再换独立派生前缀；块数与前一套相同，只为换取新样本。
MIXED_IQV3_SEED_PREFIX = "mixed-local-iqv-v3:seed:"
MIXED_IQV3_MAIN_SEED_COUNT = 16


def derive_iqv3_main_seeds(count: int = MIXED_IQV3_MAIN_SEED_COUNT) -> tuple[int, ...]:
    """按冻结规则复算第四套主种子：派生串的 SHA-256 前 4 字节按大端解释为无符号整数。"""
    if count < 1:
        raise MixedValidationAuthorizationError("主种子个数必须为正")
    return tuple(
        int.from_bytes(
            hashlib.sha256(f"{MIXED_IQV3_SEED_PREFIX}{index}".encode()).digest()[:4],
            "big",
        )
        for index in range(1, count + 1)
    )


MIXED_IQV3_MAIN_SEEDS: tuple[int, ...] = (
    2992123152,
    861226357,
    3069791970,
    398151747,
    4174639366,
    3668686169,
    1723187620,
    1755981957,
    2802107378,
    559001126,
    2601949847,
    2974243246,
    490723481,
    2182117330,
    1255170312,
    1138830182,
)

# 第五套主种子：再换独立派生前缀；块数与前一套相同，只为换取新样本。
MIXED_IQV4_SEED_PREFIX = "mixed-local-iqv-v4:seed:"
MIXED_IQV4_MAIN_SEED_COUNT = 16


def derive_iqv4_main_seeds(count: int = MIXED_IQV4_MAIN_SEED_COUNT) -> tuple[int, ...]:
    """按冻结规则复算第五套主种子：派生串的 SHA-256 前 4 字节按大端解释为无符号整数。"""
    if count < 1:
        raise MixedValidationAuthorizationError("主种子个数必须为正")
    return tuple(
        int.from_bytes(
            hashlib.sha256(f"{MIXED_IQV4_SEED_PREFIX}{index}".encode()).digest()[:4],
            "big",
        )
        for index in range(1, count + 1)
    )


MIXED_IQV4_MAIN_SEEDS: tuple[int, ...] = (
    1780719137,
    1236765905,
    2134507197,
    2265833065,
    1298901453,
    4293932627,
    4195004242,
    23362354,
    2615148125,
    3861800455,
    2973349364,
    1973802598,
    2776075815,
    848535546,
    1162498705,
    467384311,
)
MIXED_HAND_MODES: tuple[HandMode, ...] = (
    HandMode.NORMAL,
    HandMode.CAUTIOUS,
    HandMode.PRESSED,
)
# 手模式的固定边缘化权重：与 [0,80)/[80,90)/[90,100) 的分区一致，先于读数写死。
MIXED_HAND_MODE_WEIGHTS: tuple[int, ...] = (80, 10, 10)
# 直接分布总数：125 个可行动节点 × 3 风格 × 3 模式。
MIXED_DIRECT_DISTRIBUTION_COUNT = MIXED_APPLICABLE_NODE_COUNT * len(MixedStyle) * len(
    MIXED_HAND_MODES
)
# 分布指标的有界冒烟上限：默认只允许少量节点，完整矩阵须经阶段许可开启。
BEHAVIOR_SMOKE_NODE_LIMIT = 8

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

# 第二套对手族：只增不改，既有四族的名称与实现保持原样。
ADVERSARIAL_OPPONENT_FAMILIES_IQV: tuple[str, ...] = (
    *ADVERSARIAL_OPPONENT_FAMILIES,
    "size-signal-probe",
    "position-pressure-probe",
    "marginal-call-pressure-probe",
    "aggression-rate-probe",
)
# 族集注册表：运行入口按名称取族，未注册名称显式失败，不退回默认集合。
ADVERSARIAL_FAMILY_SETS: dict[str, tuple[str, ...]] = {
    "first-batch": ADVERSARIAL_OPPONENT_FAMILIES,
    "iqv": ADVERSARIAL_OPPONENT_FAMILIES_IQV,
}
DEFAULT_ADVERSARIAL_FAMILY_SET = "first-batch"
# 第二套排期的机械手数：只作算式，不构成任何耗时承诺。
STAGE_A_ADVERSARIAL_HANDS_IQV = (
    len(ADVERSARIAL_OPPONENT_FAMILIES_IQV)
    * len(ADVERSARIAL_ARMS)
    * len(MIXED_PLAYER_COUNTS)
)
ADVERSARIAL_HANDS_IQV = (
    len(MIXED_IQV_MAIN_SEEDS)
    * len(MixedStyle)
    * len(ADVERSARIAL_OPPONENT_FAMILIES_IQV)
    * len(ADVERSARIAL_ARMS)
    * sum(MIXED_PLAYER_COUNTS)
)
# 第三套排期的机械手数：只作算式，不构成任何耗时承诺。
STAGE_A_ADVERSARIAL_HANDS_IQV2 = (
    len(ADVERSARIAL_OPPONENT_FAMILIES_IQV)
    * len(ADVERSARIAL_ARMS)
    * len(MIXED_PLAYER_COUNTS)
)
ADVERSARIAL_HANDS_IQV2 = (
    len(MIXED_IQV2_MAIN_SEEDS)
    * len(MixedStyle)
    * len(ADVERSARIAL_OPPONENT_FAMILIES_IQV)
    * len(ADVERSARIAL_ARMS)
    * sum(MIXED_PLAYER_COUNTS)
)


def adversarial_families(family_set: str = DEFAULT_ADVERSARIAL_FAMILY_SET) -> tuple[str, ...]:
    """按名称取对手族集；未注册名称显式失败。"""
    try:
        return ADVERSARIAL_FAMILY_SETS[family_set]
    except KeyError:
        raise MixedValidationAuthorizationError(f"未注册的对手族集：{family_set}") from None
INTERVAL_STATUS_NOT_ESTIMATED = "not-estimated-small-fixed-seed-set"

# 阶段 A 的分层子集与阶段预算提案（待批准上限，不是已获预算）。
STAGE_A_COST_SAMPLES = 288
STAGE_A_SUPPLEMENTARY_SAMPLES = 24
STAGE_A_ADVERSARIAL_HANDS = 64
STAGE_A_WALL_SECONDS = 120.0
STAGE_AB_WALL_SECONDS = 1800.0
STAGE_RSS_BYTES = 1024 * 1024 * 1024
STAGE_OUTPUT_BYTES = 100 * 1024 * 1024

# A0 前哨：阶段 A 的受限子集，只取单人数、单风格、单深度、四街各一次。
STAGE_A0_PLAYER_COUNT = 6
STAGE_A0_STYLE = MixedStyle.TIGHT
STAGE_A0_DEPTH_BB = 100
STAGE_A0_COST_SAMPLES = len(MIXED_STREETS)
STAGE_A0_LIMITATION = (
    "A0 只是阶段 A 的受限前哨，用于确认运行入口端到端可用，不产生质量或预算证据。"
)

MIXED_VALIDATION_LIMITATIONS: tuple[str, ...] = (
    "规则评分是启发式分数，不是概率、EV、GTO 或均衡结论。",
    "单元测试与有界评测只证明契约与机制，不构成对手强度认证。",
    "四个固定主种子块不出具具有总体覆盖承诺的置信区间。",
    "有限样本不能证明未来不会超预算，也不向 2–9 人以外外推。",
    "本报告的记录口径与离线训练产物的记录口径不是同一回事。",
)

# 第二套验证的局限说明：种子块个数不同，措辞必须与之一致，不沿用首套的四块口径。
MIXED_IQV_VALIDATION_LIMITATIONS: tuple[str, ...] = (
    "规则评分是启发式分数，不是概率、EV、GTO 或均衡结论。",
    "单元测试与有界评测只证明契约与机制，不构成对手强度认证。",
    "八个固定主种子块只能给出块间离散与粗区间，不构成总体覆盖承诺。",
    "有限样本不能证明未来不会超预算，也不向 2–9 人以外外推。",
    "本报告的记录口径与离线训练产物的记录口径不是同一回事。",
)
# 第三套验证的局限说明：块数再次变化，措辞必须同步，不沿用四块或八块口径。
MIXED_IQV2_VALIDATION_LIMITATIONS: tuple[str, ...] = (
    "规则评分是启发式分数，不是概率、EV、GTO 或均衡结论。",
    "单元测试与有界评测只证明契约与机制，不构成对手强度认证。",
    "十六个固定主种子块只能给出块间离散与粗区间，不构成总体覆盖承诺。",
    "有限样本不能证明未来不会超预算，也不向 2–9 人以外外推。",
    "本报告的记录口径与离线训练产物的记录口径不是同一回事。",
)
# 种子块个数与局限说明的对应关系：块数未登记时显式失败，避免套用别的块数措辞。
VALIDATION_LIMITATIONS_BY_BLOCK_COUNT: dict[int, tuple[str, ...]] = {
    4: MIXED_VALIDATION_LIMITATIONS,
    8: MIXED_IQV_VALIDATION_LIMITATIONS,
    16: MIXED_IQV2_VALIDATION_LIMITATIONS,
}


def validation_limitations(seed_block_count: int) -> tuple[str, ...]:
    """按清单实际的种子块个数取局限说明；未登记的块数显式失败。"""
    try:
        return VALIDATION_LIMITATIONS_BY_BLOCK_COUNT[seed_block_count]
    except KeyError:
        raise MixedValidationAuthorizationError(
            f"未登记的种子块个数：{seed_block_count}"
        ) from None


class MixedValidationAuthorizationError(RuntimeError):
    """缺少显式阶段许可、清单或前置回执时抛出；不做任何静默运行。"""


# ------------------------------------------------------------------ 清单机械明细

MIXED_SCENARIO_ORDER = (
    "按配方类别顺序 × 适用人数升序；成本矩阵每格在该街的可用节点间顺序轮换"
)
MIXED_SEED_DERIVATION = (
    "牌堆流消息为 (deck, 人数, 轮换号)，不含焦点 arm 或人格；"
    "焦点流消息为 (focus, 风格, 人数, 轮换号)，旧 arm 不使用该流"
)
MIXED_STAGE_PLAN: tuple[str, ...] = (
    "阶段 A：成本矩阵逐人数 36 格各取首个样本，"
    f"合计 {STAGE_A_COST_SAMPLES} 次；补充场景首样本 {STAGE_A_SUPPLEMENTARY_SAMPLES} 次；"
    f"对抗对照 {STAGE_A_ADVERSARIAL_HANDS} 手（单一主种子、单一风格、单一轮换）",
    f"阶段 B：成本矩阵补足逐人数 {COST_DECISIONS_PER_PLAYER_COUNT} 次、"
    f"补充场景 {SUPPLEMENTARY_TOTAL_SAMPLES} 次、对抗对照 {ADVERSARIAL_HANDS} 手；"
    "A 样本不重跑、不替换",
)
MIXED_RESOURCE_ENVELOPE: tuple[str, ...] = (
    f"阶段 A：wall/CPU 各不超过 {STAGE_A_WALL_SECONDS:.0f} 秒，单进程 RSS ≤ {STAGE_RSS_BYTES} 字节",
    f"阶段 A+B：累计 wall/CPU 各不超过 {STAGE_AB_WALL_SECONDS:.0f} 秒，"
    f"RSS ≤ {STAGE_RSS_BYTES} 字节，保留文件 ≤ {STAGE_OUTPUT_BYTES} 字节，单 CPU 进程、不并行",
)
MIXED_STOP_CONDITIONS: tuple[str, ...] = (
    "任何合法性、信息边界或摘要一致性错误：立即停止该轮，保留已完成计数与错误，其余记为 not-run",
    "新 Bot 的 decision_path ≥ 100ms：立即标为性能失败并暂停后续阶段，不删样本、不自动复测",
    "预算、动作上限、输出大小或 RSS 任一触发：报告 stopped-*，不声称完成、不自行扩容",
    "达到对手动作上限 256 的手：截断、不补终局、不估算输赢，并按人数/对手/arm 报告",
)
MIXED_REPORT_FORMAT = (
    "mixed-validation.v1：字段闭集，输出目录只创建不覆盖，存在同名文件即拒绝运行"
)
# 含逐节点明细的报告版本声明：清单声明哪一版，报告就产出哪一版。
MIXED_REPORT_FORMAT_V2 = (
    "mixed-validation.v2：字段闭集，输出目录只创建不覆盖，存在同名文件即拒绝运行"
)


def _nodes_are_reported(manifest: MixedFixtureManifest) -> bool:
    """清单声明逐节点明细时才产出该字段，避免旧清单的报告多出字段。"""
    return manifest.report_format.startswith(MIXED_VALIDATION_SCHEMA_VERSION_V2)

# 第二套清单的机械明细文本：节点与种子都换过，因此场景顺序与手数说明必须重写。
MIXED_IQV_SCENARIO_ORDER = (
    "按第二套配方类别顺序 × 适用人数升序；成本矩阵每格在该街的可用节点间顺序轮换"
)
MIXED_IQV_STAGE_PLAN: tuple[str, ...] = (
    "阶段 A：成本矩阵逐人数 36 格各取首个样本，"
    f"合计 {STAGE_A_COST_SAMPLES} 次；补充场景首样本 {STAGE_A_SUPPLEMENTARY_SAMPLES} 次；"
    f"对抗对照 {STAGE_A_ADVERSARIAL_HANDS_IQV} 手（单一主种子、单一风格、单一轮换）",
    f"阶段 B：成本矩阵补足逐人数 {COST_DECISIONS_PER_PLAYER_COUNT} 次、"
    f"补充场景 {SUPPLEMENTARY_TOTAL_SAMPLES} 次、对抗对照 {ADVERSARIAL_HANDS_IQV} 手；"
    "A 样本不重跑、不替换",
)

# 第三套清单的机械明细文本：节点与种子再次更换，因此场景顺序与手数说明同步重写。
MIXED_IQV2_SCENARIO_ORDER = (
    "按第三套配方类别顺序 × 适用人数升序；成本矩阵每格在该街的可用节点间顺序轮换"
)
MIXED_IQV2_STAGE_PLAN: tuple[str, ...] = (
    "阶段 A：成本矩阵逐人数 36 格各取首个样本，"
    f"合计 {STAGE_A_COST_SAMPLES} 次；补充场景首样本 {STAGE_A_SUPPLEMENTARY_SAMPLES} 次；"
    f"对抗对照 {STAGE_A_ADVERSARIAL_HANDS_IQV2} 手（单一主种子、单一风格、单一轮换）",
    f"阶段 B：成本矩阵补足逐人数 {COST_DECISIONS_PER_PLAYER_COUNT} 次、"
    f"补充场景 {SUPPLEMENTARY_TOTAL_SAMPLES} 次、对抗对照 {ADVERSARIAL_HANDS_IQV2} 手；"
    "A 样本不重跑、不替换",
)

# 第四套清单的机械明细文本：节点与种子再次更换，因此场景顺序与手数说明同步重写。
MIXED_IQV3_SCENARIO_ORDER = (
    "按第四套配方类别顺序 × 适用人数升序；成本矩阵每格在该街的可用节点间顺序轮换"
)
MIXED_IQV3_STAGE_PLAN: tuple[str, ...] = (
    "阶段 A：成本矩阵逐人数 36 格各取首个样本，"
    f"合计 {STAGE_A_COST_SAMPLES} 次；补充场景首样本 {STAGE_A_SUPPLEMENTARY_SAMPLES} 次；"
    f"对抗对照 {STAGE_A_ADVERSARIAL_HANDS_IQV2} 手（单一主种子、单一风格、单一轮换）",
    f"阶段 B：成本矩阵补足逐人数 {COST_DECISIONS_PER_PLAYER_COUNT} 次、"
    f"补充场景 {SUPPLEMENTARY_TOTAL_SAMPLES} 次、对抗对照 {ADVERSARIAL_HANDS_IQV2} 手；"
    "A 样本不重跑、不替换",
)

# 第五套清单的机械明细文本：节点与种子再次更换，因此场景顺序与手数说明同步重写。
MIXED_IQV4_SCENARIO_ORDER = (
    "按第五套配方类别顺序 × 适用人数升序；成本矩阵每格在该街的可用节点间顺序轮换"
)
MIXED_IQV4_STAGE_PLAN: tuple[str, ...] = (
    "阶段 A：成本矩阵逐人数 36 格各取首个样本，"
    f"合计 {STAGE_A_COST_SAMPLES} 次；补充场景首样本 {STAGE_A_SUPPLEMENTARY_SAMPLES} 次；"
    f"对抗对照 {STAGE_A_ADVERSARIAL_HANDS_IQV2} 手（单一主种子、单一风格、单一轮换）",
    f"阶段 B：成本矩阵补足逐人数 {COST_DECISIONS_PER_PLAYER_COUNT} 次、"
    f"补充场景 {SUPPLEMENTARY_TOTAL_SAMPLES} 次、对抗对照 {ADVERSARIAL_HANDS_IQV2} 手；"
    "A 样本不重跑、不替换",
)


# 每个身份参与配置摘要的规则字段：只登记该身份自身引入的口径，
# 使后续身份新增规则字段时，旧身份的摘要仍可逐字复算。
DIGEST_RULE_FIELDS: dict[str, tuple[str, ...]] = {
    MIXED_STRATEGY_IDENTIFIER_V2: ("shared_board_chop_caliber",),
    MIXED_STRATEGY_IDENTIFIER_V3: (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
    ),
    MIXED_STRATEGY_IDENTIFIER_V4: (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
    ),
    MIXED_STRATEGY_IDENTIFIER_V5: (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
        "postflop_call_bonus",
    ),
    MIXED_STRATEGY_IDENTIFIER_V6: (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
        "postflop_call_bonus",
        "active_scale_percent",
        "contender_penalty_cap",
    ),
    # 第七版在第六版的七个字段之上多出非价值进攻依据的口径开关。
    MIXED_STRATEGY_IDENTIFIER_V7: (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
        "postflop_call_bonus",
        "active_scale_percent",
        "contender_penalty_cap",
        "continuous_non_value_basis",
    ),
}


def config_digest(identifier: str = MIXED_STRATEGY_IDENTIFIER) -> str:
    """策略配置摘要：只覆盖固定的规则参数表与量化口径，不含任何运行时状态。

    首版身份的载荷已被外部冻结清单逐字引用，因此不追加任何字段；其余身份额外写入
    自身的规则口径，避免两套不同的分布共用同一个配置摘要。写入的字段取自该身份
    登记的清单，而不是整份规则对象，这样别的身份新增字段不会改动这里的取值。
    未注册身份、以及已注册但未登记字段的身份，都在此显式失败，不静默回退。
    """
    payload: dict[str, object] = {
        "distribution_schema": MIXED_DISTRIBUTION_SCHEMA_VERSION,
        "distribution_units": MIXED_DISTRIBUTION_UNITS,
        "hand_mode_bounds": list(HAND_MODE_ROLL_BOUNDS),
        "styles": {
            style.value: {
                "looseness": STYLE_PARAMETERS[style].looseness,
                "fold_percent": STYLE_PARAMETERS[style].fold_percent,
                "call_percent": STYLE_PARAMETERS[style].call_percent,
                "aggression_percent": STYLE_PARAMETERS[style].aggression_percent,
                "size_preferences": list(STYLE_PARAMETERS[style].size_preferences),
            }
            for style in MixedStyle
        },
    }
    if identifier != MIXED_STRATEGY_IDENTIFIER:
        rules = asdict(rules_for_identifier(identifier))
        fields = DIGEST_RULE_FIELDS.get(identifier)
        if fields is None:
            raise MixedStrategyError(f"身份 {identifier} 未登记配置摘要字段，拒绝出具摘要")
        payload["rules"] = {name: rules[name] for name in fields}
    material = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def strategy_rules(manifest: MixedFixtureManifest) -> MixedPolicyRules:
    """清单声明的策略身份对应的规则口径；未注册身份在此显式失败。"""
    return rules_for_identifier(manifest.strategy_id)


def frozen_manifest(
    *,
    code_identity: str,
    output_dir: str,
    strategy_id: str = MIXED_STRATEGY_IDENTIFIER,
) -> MixedFixtureManifest:
    """按规格常量装配冻结清单；节点由配方生成，机械明细由本模块注入。"""
    return build_frozen_manifest(
        strategy_id=strategy_id,
        code_identity=code_identity,
        config_digest=config_digest(strategy_id),
        seeds=MIXED_MAIN_SEEDS,
        output_dir=output_dir,
        scenario_order=MIXED_SCENARIO_ORDER,
        seed_derivation=MIXED_SEED_DERIVATION,
        stage_plan=MIXED_STAGE_PLAN,
        resource_envelope=MIXED_RESOURCE_ENVELOPE,
        stop_conditions=MIXED_STOP_CONDITIONS,
        report_format=MIXED_REPORT_FORMAT,
    )


def frozen_iqv_manifest(
    *,
    code_identity: str,
    output_dir: str,
    strategy_id: str,
) -> MixedFixtureManifest:
    """装配第二套冻结清单：新节点集 + 新主种子。

    只返回清单对象，不写任何文件、不创建目录；落盘属于单独授权的动作。
    """
    return build_frozen_manifest(
        strategy_id=strategy_id,
        code_identity=code_identity,
        config_digest=config_digest(strategy_id),
        seeds=MIXED_IQV_MAIN_SEEDS,
        nodes=build_frozen_iqv_nodes(),
        output_dir=output_dir,
        scenario_order=MIXED_IQV_SCENARIO_ORDER,
        seed_derivation=MIXED_SEED_DERIVATION,
        stage_plan=MIXED_IQV_STAGE_PLAN,
        resource_envelope=MIXED_RESOURCE_ENVELOPE,
        stop_conditions=MIXED_STOP_CONDITIONS,
        report_format=MIXED_REPORT_FORMAT,
    )


def frozen_iqv2_manifest(
    *,
    code_identity: str,
    output_dir: str,
    strategy_id: str,
) -> MixedFixtureManifest:
    """装配第三套冻结清单：新节点集 + 新主种子 + 逐节点明细的报告版本。

    只返回清单对象，不写任何文件、不创建目录；落盘属于单独授权的动作。
    """
    return build_frozen_manifest(
        strategy_id=strategy_id,
        code_identity=code_identity,
        config_digest=config_digest(strategy_id),
        seeds=MIXED_IQV2_MAIN_SEEDS,
        nodes=build_frozen_iqv2_nodes(),
        output_dir=output_dir,
        scenario_order=MIXED_IQV2_SCENARIO_ORDER,
        seed_derivation=MIXED_SEED_DERIVATION,
        stage_plan=MIXED_IQV2_STAGE_PLAN,
        resource_envelope=MIXED_RESOURCE_ENVELOPE,
        stop_conditions=MIXED_STOP_CONDITIONS,
        report_format=MIXED_REPORT_FORMAT_V2,
    )


def frozen_iqv3_manifest(
    *,
    code_identity: str,
    output_dir: str,
    strategy_id: str,
) -> MixedFixtureManifest:
    """装配第四套冻结清单：又一套节点集与主种子，报告版本与前一套相同。

    只返回清单对象，不写任何文件、不创建目录；落盘属于单独授权的动作。
    """
    return build_frozen_manifest(
        strategy_id=strategy_id,
        code_identity=code_identity,
        config_digest=config_digest(strategy_id),
        seeds=MIXED_IQV3_MAIN_SEEDS,
        nodes=build_frozen_iqv3_nodes(),
        output_dir=output_dir,
        scenario_order=MIXED_IQV3_SCENARIO_ORDER,
        seed_derivation=MIXED_SEED_DERIVATION,
        stage_plan=MIXED_IQV3_STAGE_PLAN,
        resource_envelope=MIXED_RESOURCE_ENVELOPE,
        stop_conditions=MIXED_STOP_CONDITIONS,
        report_format=MIXED_REPORT_FORMAT_V2,
    )


def frozen_iqv4_manifest(
    *,
    code_identity: str,
    output_dir: str,
    strategy_id: str,
) -> MixedFixtureManifest:
    """装配第五套冻结清单：又一套节点集与主种子，报告版本与前一版相同。

    只返回清单对象，不写任何文件、不创建目录；落盘属于单独授权的动作。
    """
    return build_frozen_manifest(
        strategy_id=strategy_id,
        code_identity=code_identity,
        config_digest=config_digest(strategy_id),
        seeds=MIXED_IQV4_MAIN_SEEDS,
        nodes=build_frozen_iqv4_nodes(),
        output_dir=output_dir,
        scenario_order=MIXED_IQV4_SCENARIO_ORDER,
        seed_derivation=MIXED_SEED_DERIVATION,
        stage_plan=MIXED_IQV4_STAGE_PLAN,
        resource_envelope=MIXED_RESOURCE_ENVELOPE,
        stop_conditions=MIXED_STOP_CONDITIONS,
        report_format=MIXED_REPORT_FORMAT_V2,
    )


def required_envelope_fields(manifest: MixedFixtureManifest) -> tuple[str, ...]:
    """清单中缺失的运行机械明细；非空即表示清单尚未冻结完备。"""
    return tuple(
        name
        for name, value in (
            ("scenario_order", manifest.scenario_order),
            ("seed_derivation", manifest.seed_derivation),
            ("stage_plan", manifest.stage_plan),
            ("resource_envelope", manifest.resource_envelope),
            ("stop_conditions", manifest.stop_conditions),
            ("output_dir", manifest.output_dir),
            ("report_format", manifest.report_format),
        )
        if not value
    )


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


class MixedLatencyGroup(_FrozenModel):
    """按单一维度分组的决策路径延迟；维度与分组先于读数固定，不按结果挑选。"""

    dimension: Literal["player_count", "street", "style", "depth"]
    group: str
    path: MixedLatencyPath


class MixedValidationTiming(_FrozenModel):
    """决策路径、执行路径与摘要更新耗时，分列不合并。"""

    decision_budget_ms: float = DECISION_BUDGET_MS
    p95_guidance_ms: float = P95_GUIDANCE_MS
    p99_guidance_ms: float = P99_GUIDANCE_MS
    decision_path: MixedLatencyPath | None = None
    # 分组读数与全局读数不能互相替代：全局分布可能掩盖某一档的慢样本。
    decision_path_groups: tuple[MixedLatencyGroup, ...] = ()
    engine_apply: MixedLatencyPath | None = None
    public_summary_update: MixedLatencyPath | None = None
    supplementary_decision_path: MixedLatencyPath | None = None
    bot_step: MixedLatencyPath | None = None
    timing_note: str = (
        "decision_path 是完整单次 Bot 决策计算，不含 apply；执行、摘要更新、完整单步 bot_step "
        "与补充场景均另报；分组读数按人数/街/风格/深度分列；50/80ms 只是指导值，不是新门槛。"
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


class MixedStyleJsDistance(_FrozenModel):
    """两种风格在预冻结节点上的 JS 距离；按节点比较后再汇总，不抽样估计。"""

    style_a: str
    style_b: str
    nodes: int = Field(ge=0)
    mean_js_distance: float
    max_js_distance: float


class MixedCategoryBehavior(_FrozenModel):
    """单一节点类别的分布明细；共享公共大牌一类必须能单独读出读数。"""

    category: str
    style: str
    distributions: int = Field(ge=0)
    action_entropy: float | None = None
    scale_entropy: float | None = None
    effective_scale_count: int = Field(ge=0)
    structural_single_size: int = Field(ge=0)
    no_active_candidate: int = Field(ge=0)
    # 各动作类型的平均质量（百万单位口径），可直接读出该类别的动作倾向。
    mean_fold_units: int = Field(ge=0)
    mean_check_units: int = Field(ge=0)
    mean_call_units: int = Field(ge=0)
    mean_bet_units: int = Field(ge=0)
    mean_raise_units: int = Field(ge=0)


class MixedNodeBehavior(_FrozenModel):
    """单个预冻结节点在单一手模式与单一主种子块上的直接分布摘要。

    只记录分布本身的机械读数：不含任何底牌、公共牌或牌堆内容，
    也不含派生种子细节，避免把私有信息带出记录层。
    """

    node_id: str
    category: str
    player_count: int
    style: str
    hand_mode: str
    seed_block: int
    # 动作类型到份额的映射；键为动作类型名，值为该动作在分布内的份额。
    action_units: dict[str, int] = Field(default_factory=dict)
    # 同额度合并后的额度到份额映射；键为额度字符串，便于逐字复算与比较。
    scale_units: dict[str, int] = Field(default_factory=dict)
    action_entropy: float | None = None
    scale_entropy: float | None = None
    effective_scale_count: int = Field(ge=0)
    structural_single_size: int = Field(ge=0)
    has_active_candidate: bool


class MixedObservationAction(_FrozenModel):
    """一次落子的机械记录：只记公开动作与额度，不记任何牌面。"""

    street: str
    seat: int
    action: str
    amount: int


class MixedObservationHand(_FrozenModel):
    """一手对照的落子序列与派生标签；牌力档是算出来的标签，不是牌面本身。"""

    hand_index: int
    player_count: int
    style: str
    opponent: str
    arm: str
    seed_block: int | None = None
    rotation: int | None = None
    actions: tuple[MixedObservationAction, ...] = ()
    # 各街结束时的底池；只出现在本手实际发生过落子的街上。
    pot_after_street: dict[str, int] = Field(default_factory=dict)
    net_chips: int = 0
    focus_strength_bucket: str | None = None


class MixedObservations(_FrozenModel):
    """逐手观测工件：仅供离线归因，不进入任何决策路径。"""

    schema_version: Literal["mixed-observations.v1"] = MIXED_OBSERVATIONS_SCHEMA_VERSION
    strategy_id: str
    manifest_digest: str
    hands: tuple[MixedObservationHand, ...] = ()
    output_bytes: int = Field(default=0, ge=0)
    observations_note: str = (
        "落子序列与底池来自对局记录层；牌力档是焦点座位自身牌力的派生标签。"
        "工件不含底牌、公共牌或牌堆内容，也不参与任何决策。"
    )


class MixedValidationBehavior(_FrozenModel):
    """行为报告：条件动作熵与尺度熵按风格分列，分组先于结果固定。"""

    direct_distributions: int = Field(ge=0)
    styles: tuple[MixedStyleBehavior, ...]
    style_js_distances: tuple[MixedStyleJsDistance, ...] = ()
    categories: tuple[MixedCategoryBehavior, ...] = ()
    # 逐节点明细：按种子块分列，用于按节点判定与按块比较倾向。
    nodes: tuple[MixedNodeBehavior, ...] = ()
    behavior_note: str = (
        "指标来自预冻结节点的直接分布，不靠抽样估计；手模式由内部接口显式指定；"
        "风格间比较先按固定的模式权重边缘化。"
    )


class MixedMatchFamilyRow(_FrozenModel):
    """一组对抗对照的结果行。"""

    player_count: int
    style: str
    opponent: str
    arm: str
    # 主种子块与轮换号随行保存：按块聚合需要它们，缺了就无法事后回补。
    # 本版起产出时一律写入；更早落盘的回执没有这两项，读回时给 None 而不伪造数值。
    seed_block: int | None = None
    rotation: int | None = Field(default=None, ge=0)
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
    # 格口径与样本口径分列：每格 1 样本时两者相等，配额大于 1 时相差三个数量级。
    cost_samples_planned: int = Field(default=0, ge=0)
    cost_samples_executed: int = Field(default=0, ge=0)
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

    schema_version: Literal["mixed-validation.v1", "mixed-validation.v2"] = (
        MIXED_VALIDATION_SCHEMA_VERSION
    )
    strategy_id: str
    code_identity: str
    config_digest: str
    manifest_digest: str
    stage: Literal["A0", "A", "B"]
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


# 第二套探针：只读公开信息与自己底牌，同 seed 下确定性；不读对手暗牌或人格参数。
_SIZE_SIGNAL_LOW_RATIO = 1 / 3
_SIZE_SIGNAL_HIGH_RATIO = 2 / 3
_POSITION_PRESSURE_TABLE_LIMIT = 4
_MARGINAL_HOLDING_SUIT_LIMIT = 4


def _probe_fallback(legal: LegalActions) -> Action:
    """探针兜底：先过牌、再跟注、再弃牌，最后才用最小主动额度。"""
    if legal.can_check:
        return Action(ActionType.CHECK)
    if legal.can_call:
        return Action(ActionType.CALL)
    if legal.can_fold:
        return Action(ActionType.FOLD)
    if legal.can_raise:
        return Action(ActionType.RAISE, legal.min_raise_to)
    if legal.can_bet:
        return Action(ActionType.BET, legal.min_bet)
    raise MixedValidationAuthorizationError("探针没有任何合法候选")


def _clamp_target(value: int, minimum: int, maximum: int) -> int:
    """把目标额度夹紧到合法区间内，保证产出的动作一定合法。"""
    return min(max(value, minimum), maximum)


class SizeSignalProbe:
    """尺度针对探针：按对手公开下注额相对底池的比例分档做固定响应。"""

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        if legal.can_check or legal.call_amount <= 0:
            return _probe_fallback(legal)
        ratio = legal.call_amount / max(1, state.pot)
        if ratio < _SIZE_SIGNAL_LOW_RATIO:
            # 最小档固定弃牌，用于暴露「小尺度必被弃」这类固定反应。
            if legal.can_fold:
                return Action(ActionType.FOLD)
            return _probe_fallback(legal)
        if ratio <= _SIZE_SIGNAL_HIGH_RATIO:
            if legal.can_call:
                return Action(ActionType.CALL)
            return _probe_fallback(legal)
        # 最大档固定加价，用于暴露「大尺度必被反加」这类固定反应。
        if legal.can_raise:
            target = _clamp_target(
                3 * legal.call_amount, legal.min_raise_to, legal.max_raise_to
            )
            return Action(ActionType.RAISE, target)
        return _probe_fallback(legal)


class PositionPressureProbe:
    """位置人数针对探针：按人数与相对庄位分档固定施压，只读公开局面。"""

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        seats = len(state.players)
        live = sum(1 for player in state.players if not player.folded)
        distance = (state.current_seat - state.button) % seats
        late = distance * 2 >= seats
        if late and live <= _POSITION_PRESSURE_TABLE_LIMIT:
            if legal.can_bet:
                return Action(
                    ActionType.BET,
                    _clamp_target(2 * MIXED_BIG_BLIND, legal.min_bet, legal.max_bet),
                )
            if legal.can_raise:
                return Action(
                    ActionType.RAISE,
                    _clamp_target(2 * MIXED_BIG_BLIND, legal.min_raise_to, legal.max_raise_to),
                )
        return _probe_fallback(legal)


def _is_marginal_holding(state: GameState) -> bool:
    """只用公共牌与自己的底牌判断是否属于翻后边缘牌力（未成牌且无同花听牌）。"""
    if state.street is Street.PREFLOP or len(state.board) < 3:
        return False
    mine = state.players[state.current_seat].hole_cards
    if len(mine) != 2:
        return False
    board_ranks = {card.rank for card in state.board}
    if any(card.rank in board_ranks for card in mine):
        return False
    cards = (*state.board, *mine)
    longest_suit = max(
        sum(1 for card in cards if card.suit == suit) for suit in {card.suit for card in cards}
    )
    return longest_suit < _MARGINAL_HOLDING_SUIT_LIMIT


class MarginalCallPressureProbe:
    """边缘跟弃压力探针：在翻后边缘牌力上固定施加小额下注。"""

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        if not _is_marginal_holding(state):
            return _probe_fallback(legal)
        small = max(1, state.pot // 3)
        if legal.can_bet:
            return Action(
                ActionType.BET, _clamp_target(small, legal.min_bet, legal.max_bet)
            )
        if legal.can_raise:
            return Action(
                ActionType.RAISE,
                _clamp_target(
                    legal.call_amount + small, legal.min_raise_to, legal.max_raise_to
                ),
            )
        if legal.can_call and legal.call_amount <= 2 * MIXED_BIG_BLIND:
            return Action(ActionType.CALL)
        if legal.can_fold:
            return Action(ActionType.FOLD)
        return _probe_fallback(legal)


def _opponents_still_passive(state: GameState) -> bool:
    """公开判断：是否存在本手投入未超过一个大盲的未弃牌对手。"""
    return any(
        not player.folded and player.total_committed <= MIXED_BIG_BLIND
        for player in state.players
        if player.seat != state.current_seat
    )


class AggressionRateProbe:
    """主动率针对探针：对手本手尚未主动时固定提高下注频率。"""

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        if _opponents_still_passive(state) and legal.can_bet:
            return Action(
                ActionType.BET,
                _clamp_target(state.pot // 2, legal.min_bet, legal.max_bet),
            )
        return _probe_fallback(legal)


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


def peak_rss_bytes() -> int | None:
    """进程峰值常驻内存（字节）；平台不提供读数时返回 None，不填 0 冒充已测。"""
    try:
        import resource
    except ImportError:  # pragma: no cover - 仅非 Unix 平台会走到这里
        return None
    try:
        usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ValueError, OSError):  # pragma: no cover - 平台读数异常
        return None
    if usage <= 0:
        return None
    # macOS 的读数单位是字节，其余 Unix 是 KiB。
    return usage if sys.platform == "darwin" else usage * 1024


@dataclass(frozen=True)
class DecisionTiming:
    """一次决策的各段耗时，单位毫秒；各段与完整单步分列，不互相替代。"""

    decision_path_ms: float
    engine_apply_ms: float
    summary_update_ms: float
    # 完整单步：从决策开始到摘要更新结束。摘要维护卡顿在这里也会显形。
    bot_step_ms: float


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
    """计时一次完整决策：脱敏/摘要/特征/分布/采样/候选校验，再单独计时执行与摘要更新。"""
    step_started = time.perf_counter()
    started = step_started
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
    bot_step_ms = (time.perf_counter() - step_started) * 1000.0
    return DecisionTiming(decision_ms, apply_ms, summary_ms, bot_step_ms)


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
    """一种分组（风格或类别 × 风格）的累计指标桶。"""

    distributions: int = 0
    action_entropies: list[float] = field(default_factory=list)
    scale_entropies: list[float] = field(default_factory=list)
    effective_scales: int = 0
    single_size: int = 0
    no_active: int = 0
    # 各动作类型累计质量，用于读出分类别的动作倾向。
    action_units: dict[ActionType, int] = field(default_factory=dict)


# 风格比较的固定配对与顺序，先于读数固定。
_STYLE_PAIRS: tuple[tuple[str, str], ...] = tuple(
    (left.value, right.value)
    for index, left in enumerate(MixedStyle)
    for right in list(MixedStyle)[index + 1 :]
)


def js_distance(
    left: dict[tuple[ActionType, int], float],
    right: dict[tuple[ActionType, int], float],
) -> float:
    """两个分布的 JS 距离：共同支撑集上求散度再开方，零概率按极限取 0。"""
    left_total = sum(left.values())
    right_total = sum(right.values())
    if left_total <= 0 or right_total <= 0:
        raise MixedValidationAuthorizationError("参与比较的分布质量为零，无法给出距离")
    divergence = 0.0
    for key in set(left) | set(right):
        p = left.get(key, 0.0) / left_total
        q = right.get(key, 0.0) / right_total
        middle = (p + q) / 2.0
        for value in (p, q):
            if value > 0:
                divergence += 0.5 * value * math.log2(value / middle)
    return math.sqrt(divergence)


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _node_row(
    fixture: MixedNodeFixture,
    style: str,
    hand_mode: str,
    seed_block: int,
    distribution: MixedDistribution,
) -> MixedNodeBehavior:
    """把单个分布写成一行逐节点明细；额度按同额度合并后记录。"""
    action_entropy, scale_entropy, scale_count, single = distribution_metrics(distribution)
    action_units: dict[str, int] = {}
    scale_units: dict[str, int] = {}
    for item in distribution.candidates:
        action_units[item.action.value] = action_units.get(item.action.value, 0) + item.units
        if item.units > 0 and item.action in (ActionType.BET, ActionType.RAISE):
            scale_units[str(item.amount)] = scale_units.get(str(item.amount), 0) + item.units
    return MixedNodeBehavior(
        node_id=fixture.node_id,
        category=fixture.category,
        player_count=fixture.player_count,
        style=style,
        hand_mode=hand_mode,
        seed_block=seed_block,
        # 键排序后再落盘，使同一清单的序列化字节可逐字比较。
        action_units={key: action_units[key] for key in sorted(action_units)},
        scale_units={key: scale_units[key] for key in sorted(scale_units, key=int)},
        action_entropy=action_entropy,
        scale_entropy=scale_entropy,
        effective_scale_count=scale_count,
        structural_single_size=single,
        has_active_candidate=scale_count > 0,
    )


def _node_rows(manifest: MixedFixtureManifest) -> tuple[MixedNodeBehavior, ...]:
    """按节点 × 风格 × 手模式 × 主种子块重算逐节点明细。

    每个种子块各算一次：只算首个种子块时，倾向随种子是否稳定这件事无从比较。
    """
    rows: list[MixedNodeBehavior] = []
    for fixture in manifest.nodes:
        applied = apply_node(fixture)
        verified = require_mixed_input(applied.actor_state())
        legal = applied.legal_actions()
        for seed_block in manifest.seeds:
            for style in MixedStyle:
                policy = MixedSeatPolicy(
                    seat=verified.actor_seat,
                    style=style,
                    seat_key=focus_seat_key(
                        int(seed_block), style.value, fixture.player_count, 0
                    ),
                    rules=strategy_rules(manifest),
                )
                for hand_mode in MIXED_HAND_MODES:
                    rows.append(
                        _node_row(
                            fixture,
                            style.value,
                            hand_mode.value,
                            int(seed_block),
                            policy.distribution_for(verified, legal, hand_mode),
                        )
                    )
    return tuple(rows)


def _style_row(style: str, bucket: _BehaviorBucket) -> MixedStyleBehavior:
    return MixedStyleBehavior(
        style=style,
        distributions=bucket.distributions,
        action_entropy=_mean(bucket.action_entropies),
        scale_entropy=_mean(bucket.scale_entropies),
        effective_scale_count=bucket.effective_scales,
        structural_single_size=bucket.single_size,
        no_active_candidate=bucket.no_active,
    )


def _category_row(category: str, style: str, bucket: _BehaviorBucket) -> MixedCategoryBehavior:
    """把类别桶写成一行；平均质量按该桶的分布数取整，不代表任何单一局面。"""
    count = bucket.distributions

    def units_of(action: ActionType) -> int:
        return round(bucket.action_units.get(action, 0) / count) if count else 0

    return MixedCategoryBehavior(
        category=category,
        style=style,
        distributions=count,
        action_entropy=_mean(bucket.action_entropies),
        scale_entropy=_mean(bucket.scale_entropies),
        effective_scale_count=bucket.effective_scales,
        structural_single_size=bucket.single_size,
        no_active_candidate=bucket.no_active,
        mean_fold_units=units_of(ActionType.FOLD),
        mean_check_units=units_of(ActionType.CHECK),
        mean_call_units=units_of(ActionType.CALL),
        mean_bet_units=units_of(ActionType.BET),
        mean_raise_units=units_of(ActionType.RAISE),
    )


def collect_behavior(
    manifest: MixedFixtureManifest,
    *,
    mode: HandMode | None = None,
    allow_full: bool = False,
) -> MixedValidationBehavior:
    """在预冻结节点上计算三种风格 × 三种模式的直接分布指标。

    节点数超过有界冒烟上限时属评测实跑，必须由阶段许可显式开启；默认拒绝。
    """
    if not allow_full and len(manifest.nodes) > BEHAVIOR_SMOKE_NODE_LIMIT:
        raise MixedValidationAuthorizationError(
            "完整分布矩阵属于评测实跑，须经阶段许可后显式开启"
        )
    style_buckets = {style.value: _BehaviorBucket() for style in MixedStyle}
    category_buckets: dict[tuple[str, str], _BehaviorBucket] = {}
    js_samples: dict[tuple[str, str], list[float]] = {pair: [] for pair in _STYLE_PAIRS}
    total = 0
    modes = MIXED_HAND_MODES if mode is None else (mode,)
    weights = (
        MIXED_HAND_MODE_WEIGHTS
        if mode is None
        else (MIXED_HAND_MODE_WEIGHTS[MIXED_HAND_MODES.index(mode)],)
    )
    for fixture in manifest.nodes:
        applied = apply_node(fixture)
        verified = require_mixed_input(applied.actor_state())
        legal = applied.legal_actions()
        marginals: dict[str, dict[tuple[ActionType, int], float]] = {}
        for style in MixedStyle:
            # 离线按风格逐一覆盖，生产分配仍由座位升序循环决定。
            policy = MixedSeatPolicy(
                seat=verified.actor_seat,
                style=style,
                seat_key=focus_seat_key(
                    int(manifest.seeds[0]), style.value, fixture.player_count, 0
                ),
                rules=strategy_rules(manifest),
            )
            bucket = style_buckets[style.value]
            category_bucket = category_buckets.setdefault(
                (fixture.category, style.value), _BehaviorBucket()
            )
            marginal: dict[tuple[ActionType, int], float] = {}
            for weight, hand_mode in zip(weights, modes, strict=True):
                distribution = policy.distribution_for(verified, legal, hand_mode)
                action_entropy, scale_entropy, scale_count, single = distribution_metrics(
                    distribution
                )
                for target in (bucket, category_bucket):
                    target.distributions += 1
                    if action_entropy is not None:
                        target.action_entropies.append(action_entropy)
                    if scale_entropy is not None:
                        target.scale_entropies.append(scale_entropy)
                    target.effective_scales += scale_count
                    target.single_size += single
                    target.no_active += 0 if scale_count else 1
                    for item in distribution.candidates:
                        target.action_units[item.action] = (
                            target.action_units.get(item.action, 0) + item.units
                        )
                total += 1
                for item in distribution.candidates:
                    key = (item.action, item.amount)
                    marginal[key] = marginal.get(key, 0.0) + weight * item.units
            marginals[style.value] = marginal
        for left, right in _STYLE_PAIRS:
            js_samples[(left, right)].append(js_distance(marginals[left], marginals[right]))
    styles = tuple(_style_row(style.value, style_buckets[style.value]) for style in MixedStyle)
    categories = tuple(
        _category_row(category, style, bucket)
        for (category, style), bucket in sorted(category_buckets.items())
        if bucket.distributions
    )
    distances = tuple(
        MixedStyleJsDistance(
            style_a=left,
            style_b=right,
            nodes=len(js_samples[(left, right)]),
            mean_js_distance=statistics.fmean(js_samples[(left, right)]),
            max_js_distance=max(js_samples[(left, right)]),
        )
        for left, right in _STYLE_PAIRS
    )
    return MixedValidationBehavior(
        direct_distributions=total,
        styles=styles,
        style_js_distances=distances,
        categories=categories,
        nodes=_node_rows(manifest) if _nodes_are_reported(manifest) else (),
    )


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


def usable_at_depth(fixture: MixedNodeFixture, depth_bb: int) -> bool:
    """固定短码节点只在自身筹码深度上使用；其余节点可按深度等比缩放。"""
    return fixture.depth_scalable or depth_bb == MIXED_DEPTHS_BB[1]


def _rebuild_fixture(
    fixture: MixedNodeFixture,
    *,
    starting_stack: int | None = None,
) -> MixedNodeFixture:
    """按节点标识回到它所属的那一套配方重建节点。

    标识形状是节点归属配方的唯一标记：两种已知形状之外一律显式失败，
    避免拿错配方的牌面继续跑。
    """
    base = f"{fixture.category}-n{fixture.player_count}"
    if fixture.node_id == base:
        builder = build_node
    elif fixture.node_id == base + MIXED_IQV_NODE_ID_SUFFIX:
        builder = build_iqv_node
    elif fixture.node_id == base + MIXED_IQV2_NODE_ID_SUFFIX:
        builder = build_iqv2_node
    elif fixture.node_id == base + MIXED_IQV3_NODE_ID_SUFFIX:
        builder = build_iqv3_node
    elif fixture.node_id == base + MIXED_IQV4_NODE_ID_SUFFIX:
        builder = build_iqv4_node
    else:
        raise MixedValidationAuthorizationError(
            f"节点标识 {fixture.node_id} 不属于任何已注册的配方集"
        )
    if starting_stack is None:
        return builder(fixture.category, fixture.player_count)
    return builder(fixture.category, fixture.player_count, starting_stack=starting_stack)


def fixture_at_depth(fixture: MixedNodeFixture, depth_bb: int) -> MixedNodeFixture:
    """把节点按它自己的配方在目标深度上重建；固定短码节点原样返回。

    只接受「由配方在其自身筹码深度上生成」的节点：重建不出与清单一致的基线时显式失败，
    避免静默换掉牌面、筹码或前置动作线。翻后开注额由目标深度下当时的合法区间决定，
    因此浅深两档的派生节点可能只在该金额上与清单不同。
    """
    if not fixture.depth_scalable:
        return fixture
    target = depth_bb * MIXED_BIG_BLIND
    if target == fixture.starting_stack:
        return fixture
    baseline = _rebuild_fixture(fixture)
    if baseline.model_dump() != fixture.model_dump():
        raise MixedValidationAuthorizationError(
            f"节点 {fixture.node_id} 与配方基线不一致，不能按深度派生"
        )
    return _rebuild_fixture(fixture, starting_stack=target)


@dataclass
class _CostTally:
    """成本矩阵累计器：样本与格计数边跑边写，中途失败也保留已完成的部分。"""

    decision: list[float] = field(default_factory=list)
    apply_ms: list[float] = field(default_factory=list)
    summary_ms: list[float] = field(default_factory=list)
    bot_step: list[float] = field(default_factory=list)
    # 与 decision 一一对应的分组键：(人数, 街, 风格, 深度)。
    keys: list[tuple[int, str, str, int]] = field(default_factory=list)
    # 格数按格计数，样本数按配额累计；两者不混用。
    cells_executed: int = 0
    cells_planned: int = 0
    samples_planned: int = 0


def run_cost_matrix(
    manifest: MixedFixtureManifest,
    *,
    stage: Literal["A0", "A", "B"],
    player_count: int,
    styles: Sequence[str] | None = None,
    depths: Sequence[int] | None = None,
    tally: _CostTally | None = None,
) -> _CostTally:
    """按限额逐格计时，结果写进累计器并返回。

    ``styles`` / ``depths`` 是受限子集用的筛选：只跳过不匹配的格，不改变格的定义、
    顺序与配额口径，因此不会产生与完整矩阵不同的格。
    """
    if tally is None:
        tally = _CostTally()
    fixtures = manifest.nodes_for(player_count)
    cursors: dict[Street, int] = {}
    for index, (street, style, depth) in enumerate(cost_cells()):
        if styles is not None and style not in styles:
            continue
        if depths is not None and depth not in depths:
            continue
        quota = cell_quota(index) if stage == "B" else 1
        tally.cells_planned += 1
        tally.samples_planned += quota
        candidates = [
            node
            for node in fixtures
            if node.decision_street is street and usable_at_depth(node, depth)
        ]
        if not candidates:
            continue
        cursor = cursors.get(street, 0)
        cursors[street] = cursor + 1
        fixture = candidates[cursor % len(candidates)]
        # 一个格只有在真正产出样本后才算已执行，避免首个样本就失败的格被记为已完成。
        produced = False
        for _ in range(quota):
            timing = time_decision(
                fixture,
                style,
                depth,
                seed=int(manifest.seeds[0]),
                identifier=manifest.strategy_id,
            )
            tally.decision.append(timing.decision_path_ms)
            tally.apply_ms.append(timing.engine_apply_ms)
            tally.summary_ms.append(timing.summary_update_ms)
            tally.bot_step.append(timing.bot_step_ms)
            tally.keys.append((player_count, street.name.lower(), style, depth))
            if not produced:
                tally.cells_executed += 1
                produced = True
    return tally


# 分组维度的固定顺序，避免报告顺序随字典遍历或读数变化。
_LATENCY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("player_count", tuple(str(count) for count in MIXED_PLAYER_COUNTS)),
    ("street", tuple(street.name.lower() for street in MIXED_STREETS)),
    ("style", tuple(style.value for style in MixedStyle)),
    ("depth", tuple(str(depth) for depth in MIXED_DEPTHS_BB)),
)


def latency_groups(cost: _CostTally) -> tuple[MixedLatencyGroup, ...]:
    """把成本矩阵样本按人数、街、风格、深度分别汇总；空分组不伪造读数。"""
    buckets: dict[tuple[str, str], list[float]] = {}
    for (player_count, street, style, depth), value in zip(
        cost.keys, cost.decision, strict=True
    ):
        for dimension, group in (
            ("player_count", str(player_count)),
            ("street", street),
            ("style", style),
            ("depth", str(depth)),
        ):
            buckets.setdefault((dimension, group), []).append(value)
    groups: list[MixedLatencyGroup] = []
    for dimension, values in _LATENCY_GROUPS:
        for group in values:
            samples = buckets.get((dimension, group))
            if not samples:
                continue
            groups.append(
                MixedLatencyGroup(
                    dimension=dimension,  # type: ignore[arg-type]
                    group=group,
                    path=summarize_path(samples),
                )
            )
    return tuple(groups)


def time_decision(
    fixture: MixedNodeFixture,
    style: str,
    depth_bb: int,
    *,
    seed: int,
    identifier: str = MIXED_STRATEGY_IDENTIFIER,
) -> DecisionTiming:
    """在一个节点上计时一次完整决策；牌面与前置动作全部来自清单。"""
    adjusted = fixture_at_depth(fixture, depth_bb)
    applied = apply_node(adjusted)
    root = _derive_key(
        validation_root_key(seed), ("focus", style, fixture.node_id, depth_bb)
    )
    strategy = MixedLocalStrategy(
        root_key=root,
        bot_seats=tuple(range(adjusted.player_count)),
        identifier=identifier,
    )
    return measure_decision(applied.engine, applied.tracker, strategy)


def run_supplementary_matrix(
    manifest: MixedFixtureManifest,
    *,
    samples_per_cell: int,
    samples: list[float] | None = None,
) -> tuple[list[float], int]:
    """补充小型测试：逐人数每类固定样本，与主矩阵分开统计。

    样本边跑边写进调用方给定的列表，中途失败也保留已完成的部分。
    """
    if samples is None:
        samples = []
    executed = 0
    for player_count in MIXED_PLAYER_COUNTS:
        fixtures = manifest.nodes_for(player_count)
        if not fixtures:
            continue
        for _ in SUPPLEMENTARY_CLASSES:
            fixture = fixtures[executed % len(fixtures)]
            executed += 1
            for _ in range(samples_per_cell):
                timing = time_decision(
                    fixture,
                    MixedStyle.TIGHT.value,
                    100,
                    seed=manifest.seeds[0],
                    identifier=manifest.strategy_id,
                )
                samples.append(timing.decision_path_ms)
    return samples, executed


# ------------------------------------------------------------------ 对抗对照


def adversarial_schedule(
    stage: Literal["A", "B"],
    *,
    seeds: Sequence[int] | None = None,
    families: Sequence[str] | None = None,
    family_set: str = DEFAULT_ADVERSARIAL_FAMILY_SET,
) -> list[tuple[int, MixedStyle, str, str, int, int]]:
    """对照排期：阶段 A 只取首轮换的一个子集，阶段 B 为完整轮换。

    主种子、对手族序列与族集名称都可显式给出：显式族序列优先于族集名称；
    全部省略时沿用既有常量，使既有调用逐字不变。
    """
    seed_blocks = MIXED_MAIN_SEEDS if seeds is None else tuple(seeds)
    if not seed_blocks:
        raise MixedValidationAuthorizationError("对照排期至少需要一个主种子块")
    opponents = tuple(families) if families is not None else adversarial_families(family_set)
    if not opponents:
        raise MixedValidationAuthorizationError("对照排期至少需要一个对手族")
    schedule: list[tuple[int, MixedStyle, str, str, int, int]] = []
    if stage == "A":
        seed = seed_blocks[0]
        style = MixedStyle.TIGHT
        for opponent in opponents:
            for arm in ADVERSARIAL_ARMS:
                for player_count in MIXED_PLAYER_COUNTS:
                    schedule.append((seed, style, opponent, arm, player_count, 0))
        return schedule
    for seed in seed_blocks:
        for style in MixedStyle:
            for opponent in opponents:
                for arm in ADVERSARIAL_ARMS:
                    for player_count in MIXED_PLAYER_COUNTS:
                        for rotation in range(player_count):
                            schedule.append(
                                (seed, style, opponent, arm, player_count, rotation)
                            )
    return schedule


@dataclass(frozen=True)
class HandOutcome:
    """一手对照的净筹码、是否被截断，以及焦点座位的行动统计。"""

    net_chips: int
    truncated: bool
    # 焦点座位：翻前是否自愿进池、是否加注，以及全手主动动作与总动作数。
    vpip: bool = False
    pfr: bool = False
    aggressive_actions: int = 0
    total_actions: int = 0
    # 观测开启时另存落子序列、各街底池与派生的牌力档；默认关闭时保持为空。
    actions: tuple[MixedObservationAction, ...] = ()
    pot_after_street: dict[str, int] = field(default_factory=dict)
    strength_bucket: str | None = None


def _focus_mover(
    *,
    style: MixedStyle,
    arm: str,
    seed: int,
    player_count: int,
    rotation: int,
    seat: int,
    rules: MixedPolicyRules,
) -> object:
    if arm == "legacy-focus":
        return HeuristicStrategy(seed=seed)
    policy = MixedSeatPolicy(
        seat=seat,
        style=style,
        seat_key=focus_seat_key(seed, style.value, player_count, rotation),
        rules=rules,
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
    if family == "size-signal-probe":
        return SizeSignalProbe()
    if family == "position-pressure-probe":
        return PositionPressureProbe()
    if family == "marginal-call-pressure-probe":
        return MarginalCallPressureProbe()
    if family == "aggression-rate-probe":
        return AggressionRateProbe()
    if family == "heuristic@1":
        return HeuristicStrategy(seed=seed)
    from app.strategy.random_strategy import RandomStrategy

    return RandomStrategy(seed=seed)


def _sorted_pots(by_street: dict[str, int]) -> dict[str, int]:
    """按街名排序后返回，使同一手在不同运行下的序列化结果一致。"""
    return {key: by_street[key] for key in sorted(by_street)}


def _strength_bucket(hole: Sequence[Card], board: Sequence[Card]) -> str | None:
    """按焦点座位自身的成手牌力给一个粗档；公共牌不足三张时不给档。

    只使用焦点座位自己的底牌与公开公共牌，因此不引入任何对手私有信息。
    """
    if not hole or len(board) < 3:
        return None
    category = evaluate_fast([*hole, *board]).category
    if category <= HandCategory.ONE_PAIR:
        return "weak"
    if category <= HandCategory.STRAIGHT:
        return "medium"
    return "strong"


def play_adversarial_hand(
    *,
    seed: int,
    style: MixedStyle,
    opponent: str,
    arm: str,
    player_count: int,
    rotation: int,
    rules: MixedPolicyRules,
    observe: bool = False,
) -> HandOutcome:
    """一手有界对照：每手重置到 100BB、盲注 5/10、不设抽水。

    观测默认关闭；开启时另存落子序列、各街底池与派生的牌力档。
    """
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
        rules=rules,
    )
    others = _opponent_mover(opponent, seed)

    voluntary = 0
    focus_vpip = False
    focus_pfr = False
    focus_aggressive = 0
    focus_actions = 0
    observed_actions: list[MixedObservationAction] = []
    pot_by_street: dict[str, int] = {}
    while not engine.hand_over:
        legal = engine.legal_actions()
        seat = engine.current_seat
        # 落子所属的街必须在应用动作之前取，动作应用后可能已进入下一条街。
        street_before = engine.street
        preflop = engine.street is Street.PREFLOP
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
        if seat == focus_seat:
            focus_actions += 1
            if action.type in (ActionType.BET, ActionType.RAISE):
                focus_aggressive += 1
            # 盲注不算自愿进池，因此只看焦点座位自己的自愿动作。
            if preflop and action.type in (ActionType.CALL, ActionType.BET, ActionType.RAISE):
                focus_vpip = True
            if preflop and action.type is ActionType.RAISE:
                focus_pfr = True
        engine.apply_action(action)
        if observe:
            observed_actions.append(
                MixedObservationAction(
                    street=street_before.name.lower(),
                    seat=seat,
                    action=action.type.value,
                    amount=action.amount,
                )
            )
            # 底池按整手累计投入计算，覆盖本街读数即得该街结束时的底池。
            pot_by_street[street_before.name.lower()] = engine.pot
        if tracker.active:
            # 摘要覆盖全桌公开事件，与谁行动无关。
            tracker.consume_after_action(engine.history)
        if voluntary >= ADVERSARIAL_MAX_VOLUNTARY_ACTIONS:
            return HandOutcome(
                net_chips=0,
                truncated=True,
                vpip=focus_vpip,
                pfr=focus_pfr,
                aggressive_actions=focus_aggressive,
                total_actions=focus_actions,
                actions=tuple(observed_actions),
                pot_after_street=_sorted_pots(pot_by_street),
                strength_bucket=_strength_bucket(
                    engine.players[focus_seat].hole_cards, engine.board
                ),
            )
    return HandOutcome(
        net_chips=engine.last_net.get(focus_seat, 0),
        truncated=False,
        vpip=focus_vpip,
        pfr=focus_pfr,
        aggressive_actions=focus_aggressive,
        total_actions=focus_actions,
        actions=tuple(observed_actions),
        pot_after_street=_sorted_pots(pot_by_street),
        strength_bucket=_strength_bucket(
            engine.players[focus_seat].hole_cards, engine.board
        ),
    )


@dataclass
class _MatchTally:
    """对抗对照累计器：逐手写入，中途失败也保留已经跑完的手。"""

    rows: list[MixedMatchFamilyRow] = field(default_factory=list)
    truncated: int = 0
    # 观测开启时逐手另存归因用的落子序列；关闭时保持为空，不影响既有路径。
    observations: list[MixedObservationHand] = field(default_factory=list)


def matches_from_tally(
    tally: _MatchTally,
    *,
    planned_hands: int,
    note: str | None = None,
    seed_blocks: Sequence[int] | None = None,
) -> MixedValidationMatches:
    """把累计器内容汇总成报告用的对照结果；完成手数按实际写入的内容计数。"""
    payload: dict[str, object] = {
        "planned_hands": planned_hands,
        "completed_hands": len(tally.rows),
        "truncated_hands": tally.truncated,
        "seed_blocks": MIXED_MAIN_SEEDS if seed_blocks is None else tuple(seed_blocks),
        "rows": tuple(tally.rows),
    }
    if note is not None:
        payload["matches_note"] = note
    return MixedValidationMatches(**payload)  # type: ignore[arg-type]


def run_adversarial_batch(
    *,
    stage: Literal["A", "B"],
    allow_matches: bool = False,
    tally: _MatchTally | None = None,
    identifier: str = MIXED_STRATEGY_IDENTIFIER,
    seeds: Sequence[int] | None = None,
    family_set: str = DEFAULT_ADVERSARIAL_FAMILY_SET,
    observe: bool = False,
) -> _MatchTally:
    """执行第一批有界对照；达到动作上限的手截断、不补终局、不估算输赢。

    对抗对照属于评测实跑，必须由阶段许可显式开启；默认拒绝。结果写进累计器并返回。
    主种子与对手族集可显式给出；省略时沿用既有常量，使既有调用逐字不变。
    """
    if not allow_matches:
        raise MixedValidationAuthorizationError("对抗对照属于评测实跑，须经阶段许可后显式开启")
    if tally is None:
        tally = _MatchTally()
    rules = rules_for_identifier(identifier)
    schedule = adversarial_schedule(stage, seeds=seeds, family_set=family_set)
    for seed, style, opponent, arm, player_count, rotation in schedule:
        outcome = play_adversarial_hand(
            seed=seed,
            style=style,
            opponent=opponent,
            arm=arm,
            player_count=player_count,
            rotation=rotation,
            rules=rules,
            observe=observe,
        )
        tally.truncated += 1 if outcome.truncated else 0
        if observe:
            tally.observations.append(
                MixedObservationHand(
                    hand_index=len(tally.rows),
                    player_count=player_count,
                    style=style.value,
                    opponent=opponent,
                    arm=arm,
                    seed_block=seed,
                    rotation=rotation,
                    actions=outcome.actions,
                    pot_after_street=outcome.pot_after_street,
                    net_chips=outcome.net_chips,
                    focus_strength_bucket=outcome.strength_bucket,
                )
            )
        tally.rows.append(
            MixedMatchFamilyRow(
                player_count=player_count,
                style=style.value,
                opponent=opponent,
                arm=arm,
                seed_block=seed,
                rotation=rotation,
                hands=1,
                truncated_hands=1 if outcome.truncated else 0,
                net_chips=outcome.net_chips,
                bb_per_100=outcome.net_chips / MIXED_BIG_BLIND * 100.0,
            )
        )
    return tally


# ------------------------------------------------------------------ 阶段门禁与运行


def require_stage_permission(
    *,
    stage: Literal["A0", "A", "B"],
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
    missing = required_envelope_fields(manifest)
    if missing:
        raise MixedValidationAuthorizationError(
            f"清单缺少运行机械明细，尚未冻结完备：{'、'.join(missing)}"
        )
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


def write_observations(
    observations: MixedObservations,
    directory: str,
    stage: str,
) -> str:
    """把逐手观测工件写入目录；已存在同名文件时拒绝覆盖。

    与主报告一致，写进文件的字节数就是这份文件自身的大小。
    """
    target = os.path.join(directory, f"mixed-observations-stage-{stage}.json")
    if os.path.exists(target):
        raise MixedValidationAuthorizationError("观测工件已存在，不得覆盖")
    # 工件只供离线机器读取，紧凑落盘以控制体积；主报告仍保持逐字可读的缩进格式。
    payload = observations.model_dump_json()
    for _ in range(3):
        revised = observations.model_copy(
            update={"output_bytes": len(payload.encode("utf-8"))}
        ).model_dump_json()
        if revised == payload:
            break
        payload = revised
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(payload)
    return target


def write_frozen_manifest(manifest: MixedFixtureManifest, directory: str) -> str:
    """把冻结清单写入指定目录；已存在同名文件时拒绝覆盖。"""
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "frozen-fixture-manifest.json")
    if os.path.exists(target):
        raise MixedValidationAuthorizationError("清单文件已存在，不得覆盖")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(manifest_json(manifest))
    return target


def supplementary_plan(stage: Literal["A0", "A", "B"]) -> int:
    """该阶段的补充样本计划数：前哨不跑，阶段 A 取首样本，阶段 B 取完整矩阵。"""
    if stage == "A0":
        return 0
    return STAGE_A_SUPPLEMENTARY_SAMPLES if stage == "A" else SUPPLEMENTARY_TOTAL_SAMPLES


def run_validation(
    *,
    manifest: MixedFixtureManifest | None,
    stage: Literal["A0", "A", "B"],
    allow_stage: str | None,
    output_dir: str | None = None,
    stage_a_receipt: MixedValidationReport | None = None,
    family_set: str = DEFAULT_ADVERSARIAL_FAMILY_SET,
    emit_observations: bool = False,
) -> MixedValidationReport:
    """执行一个显式授权的验证阶段；不访问、不修改任何封存工件。

    主种子块取自清单本身，对手族集可显式给出；省略时沿用既有口径，使既有调用逐字不变。
    """
    frozen = require_stage_permission(
        stage=stage,
        allow_stage=allow_stage,
        manifest=manifest,
        stage_a_receipt=stage_a_receipt,
    )
    # 局限说明按清单实际的种子块个数选取；块数未登记时在做任何计算之前失败。
    resolved_limitations = validation_limitations(len(frozen.seeds))
    # 未注册身份在任何计算之前显式失败，避免报告身份与实际驱动口径不一致。
    strategy_rules(frozen)
    directory = prepare_output_dir(output_dir)
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    violations: list[MixedReportViolation] = []
    # A0 是阶段 A 的受限子集：沿用同一套格定义，只取单人数、单风格、单深度各一次。
    sentinel = stage == "A0"
    player_counts = (STAGE_A0_PLAYER_COUNT,) if sentinel else MIXED_PLAYER_COUNTS
    styles = (STAGE_A0_STYLE.value,) if sentinel else None
    depths = (STAGE_A0_DEPTH_BB,) if sentinel else None

    cost = _CostTally()
    supplementary: list[float] = []
    match_tally = _MatchTally()
    supplementary_path: MixedLatencyPath | None = None
    supplementary_planned = 0
    matches = MixedValidationMatches(
        planned_hands=0,
        completed_hands=0,
        truncated_hands=0,
        seed_blocks=frozen.seeds,
        rows=(),
        matches_note="本轮未执行到对抗对照，因此没有对照读数。",
    )
    behavior = MixedValidationBehavior(
        direct_distributions=0,
        styles=(),
        behavior_note="本轮未执行到分布矩阵，因此没有行为读数。",
    )
    full_stage: Literal["A", "B"] = "B" if stage == "B" else "A"
    failure: str | None = None
    try:
        for player_count in player_counts:
            run_cost_matrix(
                frozen,
                stage=stage,
                player_count=player_count,
                styles=styles,
                depths=depths,
                tally=cost,
            )

        if sentinel:
            # 前哨不做补充场景、不收集分布矩阵、不跑对抗对照，三项在报告里记为未运行。
            matches = MixedValidationMatches(
                planned_hands=0,
                completed_hands=0,
                truncated_hands=0,
                seed_blocks=frozen.seeds,
                rows=(),
                matches_note="A0 前哨不执行对抗对照，因此没有对照读数。",
            )
            behavior = MixedValidationBehavior(
                direct_distributions=0,
                styles=(),
                behavior_note="A0 前哨不收集完整分布矩阵，因此没有行为读数。",
            )
        else:
            supplementary_target = supplementary_plan(stage)
            samples_per_cell = 1 if stage == "A" else SUPPLEMENTARY_SAMPLES_PER_CELL
            run_supplementary_matrix(
                frozen, samples_per_cell=samples_per_cell, samples=supplementary
            )
            # 补充场景与主矩阵分开报告，不并入主路径的分布。
            supplementary_path = summarize_path(supplementary[:supplementary_target])
            supplementary_planned = supplementary_target
            run_adversarial_batch(
                stage=full_stage,
                allow_matches=True,
                tally=match_tally,
                identifier=frozen.strategy_id,
                seeds=frozen.seeds,
                family_set=family_set,
                observe=emit_observations,
            )
            matches = matches_from_tally(
                match_tally,
                planned_hands=len(
                    adversarial_schedule(full_stage, seeds=frozen.seeds, family_set=family_set)
                ),
                seed_blocks=frozen.seeds,
            )
            behavior = collect_behavior(frozen, allow_full=True)
    except (
        MixedFixtureError,
        MixedContextError,
        MixedValidationAuthorizationError,
        IllegalActionError,
    ) as error:
        # 冻结的停止条件：出现合法性、信息边界或摘要一致性错误立即停止该轮，
        # 保留已完成计数与错误，其余记为未运行；不自动重试、不删样本。
        failure = f"{type(error).__name__}: {error}"
        if not sentinel:
            matches = matches_from_tally(
                match_tally,
                planned_hands=len(
                    adversarial_schedule(full_stage, seeds=frozen.seeds, family_set=family_set)
                ),
                note="本轮在跑完对抗对照前停止，计数只覆盖已经完成的手。",
                seed_blocks=frozen.seeds,
            )

    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    # A0 沿用阶段 A 的包络：它只是 A 的受限子集。
    limit = STAGE_AB_WALL_SECONDS if stage == "B" else STAGE_A_WALL_SECONDS
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
    decision_path = summarize_path(cost.decision)
    if decision_path.timeout_count:
        # 出现超预算样本立即标为性能失败，不删除、不自动复测。
        status = "stopped-decision-over-budget"
        violations.append(
            MixedReportViolation(
                kind="decision-over-budget",
                detail=f"出现 {decision_path.timeout_count} 次 >=100ms 的单次决策",
            )
        )
    if failure is not None:
        # 一致性类失败优先于预算类状态：它解释了本轮为何提前结束。
        status = "stopped-consistency-error"
        violations.append(MixedReportViolation(kind="replay-error", detail=failure))

    report = MixedValidationReport(
        schema_version=(
            MIXED_VALIDATION_SCHEMA_VERSION_V2
            if _nodes_are_reported(frozen)
            else MIXED_VALIDATION_SCHEMA_VERSION
        ),
        strategy_id=frozen.strategy_id,
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
            cost_cells_planned=cost.cells_planned,
            cost_cells_executed=cost.cells_executed,
            cost_samples_planned=cost.samples_planned,
            cost_samples_executed=len(cost.decision),
            supplementary_samples_planned=supplementary_planned,
            supplementary_samples_executed=(
                0 if supplementary_path is None else supplementary_path.samples
            ),
            adversarial_hands_planned=matches.planned_hands,
            adversarial_hands_executed=matches.completed_hands,
        ),
        timing=MixedValidationTiming(
            decision_path=decision_path,
            decision_path_groups=latency_groups(cost),
            engine_apply=summarize_path(cost.apply_ms),
            public_summary_update=summarize_path(cost.summary_ms),
            bot_step=summarize_path(cost.bot_step),
            supplementary_decision_path=supplementary_path,
        ),
        behavior=behavior,
        matches=matches,
        resources=MixedValidationResources(
            wall_seconds=wall_seconds,
            cpu_seconds=cpu_seconds,
            peak_rss_bytes=peak_rss_bytes(),
            output_bytes=0,
            single_process=True,
            parallel=False,
        ),
        violations=tuple(violations),
        limitations=(
            (resolved_limitations + (STAGE_A0_LIMITATION,))
            if sentinel
            else resolved_limitations
        ),
    )
    if directory is not None:
        target = os.path.join(directory, f"mixed-validation-stage-{stage}.json")
        if os.path.exists(target):
            raise MixedValidationAuthorizationError("报告目标文件已存在，不得覆盖")
        # 让落盘字节数与文件自洽：写进文件的数就是这份文件自身的大小。
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
        if emit_observations:
            write_observations(
                MixedObservations(
                    strategy_id=report.strategy_id,
                    manifest_digest=report.manifest_digest,
                    hands=tuple(match_tally.observations),
                ),
                directory,
                stage,
            )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：必须显式给出清单路径、阶段、输出目录与允许阶段。

    阶段 B 还必须给出阶段 A 的实测回执文件；缺失或不合格一律由门禁拒绝，入口不兜底放行。
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 4:
        print(
            "用法：python -m tests.mixed_bot_validation <清单路径> <A0|A|B> <输出目录> "
            "--allow-stage=<A0|A|B> [--stage-a-receipt=<阶段 A 回执路径>] "
            "[--family-set=<已注册族集名>] [--emit-observations]",
            file=sys.stderr,
        )
        return 2
    manifest_path, stage, output_dir = args[0], args[1], args[2]
    allow_stage = None
    receipt_path = None
    family_set = DEFAULT_ADVERSARIAL_FAMILY_SET
    emit_observations = False
    for token in args[3:]:
        if token.startswith("--allow-stage="):
            allow_stage = token.split("=", 1)[1]
        elif token.startswith("--stage-a-receipt="):
            receipt_path = token.split("=", 1)[1]
        elif token.startswith("--family-set="):
            family_set = token.split("=", 1)[1]
        elif token == "--emit-observations":
            emit_observations = True
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = MixedFixtureManifest.model_validate(json.load(handle))
    receipt = None
    if receipt_path is not None:
        with open(receipt_path, encoding="utf-8") as handle:
            receipt = MixedValidationReport.model_validate(json.load(handle))
    report = run_validation(
        manifest=manifest,
        stage=stage,  # type: ignore[arg-type]
        allow_stage=allow_stage,
        output_dir=output_dir,
        stage_a_receipt=receipt,
        family_set=family_set,
        emit_observations=emit_observations,
    )
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - 手动 opt-in 入口
    raise SystemExit(main())
