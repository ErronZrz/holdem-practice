"""新 Bot 离线验证用的固定节点与清单能力（测试侧永久能力，非一次性脚本）。

职责：
- 定义 16 类评测节点、2–9 人适用性矩阵与 128 个计划槽（含 3 个结构性不适用槽）；
- 按**预先固定的构造配方**生成 125 个可行动节点：牌面、庄位、筹码、前置公开动作全部
  由规则推出，不参考任何运行结果、不做「跑完再挑好看的节点」；
- 定义「逐张牌 + 前置公开动作」的清单 schema 与确定性回放入口。

构造配方是冻结的机械明细：每类节点的决策街、翻前动作形状、牌面主题与短码角色都在本
文件的配方表中写死；生成结果由回归测试逐条核对，而不是靠人工逐张审阅 125 组牌。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.poker.state import GameState, Street
from app.strategy.mixed_context import MixedSummaryTracker, mixed_state
from app.strategy.mixed_strategy import MIXED_STRATEGY_IDENTIFIER
from app.strategy.projection import project_for_actor

# 清单与逐张牌 fixture 的版本；与运行产物、离线训练工件均无关。
MIXED_FIXTURE_SCHEMA_VERSION = "mixed-bot-fixtures.v1"
MIXED_PLAYER_COUNTS: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9)
MIXED_SMALL_BLIND = 5
MIXED_BIG_BLIND = 10
MIXED_DEPTHS_BB: tuple[int, ...] = (15, 100, 1000)
MIXED_STREETS: tuple[Street, ...] = (
    Street.PREFLOP,
    Street.FLOP,
    Street.TURN,
    Street.RIVER,
)
# 节点基准筹码（100BB）与固定庄位；成本矩阵再按深度覆写起始筹码。
MIXED_DEFAULT_STACK = 100 * MIXED_BIG_BLIND
MIXED_NODE_BUTTON = 0

# 配方用的固定投入额（全部落在合法区间内，由测试逐条复核）。
_OPEN_RAISE_TO = 30
_RERAISE_TO = 90
_SHORT_CALL_RAISE_TO = 80
_INCOMPLETE_SHORT_JAM_TO = 45
_ONE_SIDE_JAM_TO = 150
# 以下筹码是「发盲注之前」的座位筹码：盲注位全下总额等于该值本身。
_SHORT_CALLER_STACK = 60
_SHORT_JAMMER_STACK = 45
_JAMMER_STACK = 150
# 驱动到目标街的保护上限：远高于正常所需，只用于防止配方写错时死循环。
_DRIVER_GUARD = 96

_RANKS = ("A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2")
_SUITS = ("s", "h", "d", "c")
# 兜底发牌顺序：只用于给非焦点座位与无关座位填牌，保证确定性且不重复。
_ALL_CARDS: tuple[str, ...] = tuple(f"{rank}{suit}" for suit in _SUITS for rank in _RANKS)
_STREET_BY_NAME = {street.name.lower(): street for street in MIXED_STREETS}


class MixedFixtureError(ValueError):
    """配方无法生成合法节点时抛出；不允许静默换牌或换动作。"""


class MixedNodeCategory(BaseModel):
    """一类评测节点的受控定义。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    description: str
    minimum_players: int
    # 该类节点的决策街；单值即冻结的机械明细，成本矩阵按街轮换使用它。
    decision_street: Street


MIXED_NODE_CATEGORIES: tuple[MixedNodeCategory, ...] = (
    MixedNodeCategory(
        category="hu-blind-position",
        description="单挑盲位与多人桌首位行动的差异",
        minimum_players=2,
        decision_street=Street.PREFLOP,
    ),
    MixedNodeCategory(
        category="unopened-open",
        description="无人自愿加注时的开池",
        minimum_players=2,
        decision_street=Street.PREFLOP,
    ),
    MixedNodeCategory(
        category="open-after-limp",
        description="跛入之后的开池",
        minimum_players=2,
        decision_street=Street.PREFLOP,
    ),
    MixedNodeCategory(
        category="facing-first-raise",
        description="面对第一次加注",
        minimum_players=2,
        decision_street=Street.PREFLOP,
    ),
    MixedNodeCategory(
        category="facing-reraise",
        description="面对连续再加注",
        minimum_players=2,
        decision_street=Street.PREFLOP,
    ),
    MixedNodeCategory(
        category="short-stack-call",
        description="短码跟注与无资格边池",
        minimum_players=3,
        decision_street=Street.PREFLOP,
    ),
    MixedNodeCategory(
        category="incomplete-raise",
        description="不足完整加注后不重开原行动者加注权",
        minimum_players=3,
        decision_street=Street.PREFLOP,
    ),
    MixedNodeCategory(
        category="free-check",
        description="免费过牌节点",
        minimum_players=2,
        decision_street=Street.FLOP,
    ),
    MixedNodeCategory(
        category="flop-draw",
        description="翻牌同花或顺子听牌",
        minimum_players=2,
        decision_street=Street.FLOP,
    ),
    MixedNodeCategory(
        category="top-pair-weak-kicker",
        description="顶对弱踢脚",
        minimum_players=2,
        decision_street=Street.TURN,
    ),
    MixedNodeCategory(
        category="turn-combo-draw",
        description="转牌组合听牌",
        minimum_players=2,
        decision_street=Street.TURN,
    ),
    MixedNodeCategory(
        category="one-side-all-in",
        description="一方已全下、另两方仍可行动的底池",
        minimum_players=3,
        decision_street=Street.TURN,
    ),
    MixedNodeCategory(
        category="overpair-on-high-board",
        description="强口袋对子遇高公共牌",
        minimum_players=2,
        decision_street=Street.RIVER,
    ),
    MixedNodeCategory(
        category="missed-draw-river",
        description="河牌错失听牌",
        minimum_players=2,
        decision_street=Street.RIVER,
    ),
    MixedNodeCategory(
        category="shared-board",
        description="公共两对、顺子或同花的共享牌面",
        minimum_players=2,
        decision_street=Street.RIVER,
    ),
    MixedNodeCategory(
        category="sizes-merged",
        description="多个尺寸被夹紧为同一金额",
        minimum_players=2,
        decision_street=Street.RIVER,
    ),
)

MIXED_CATEGORY_IDS: tuple[str, ...] = tuple(item.category for item in MIXED_NODE_CATEGORIES)
MIXED_CATEGORY_STREET: dict[str, Street] = {
    item.category: item.decision_street for item in MIXED_NODE_CATEGORIES
}
# 结构性不适用槽的类别由门槛派生，避免两处口径各写一份。
MIXED_STRUCTURAL_HOLE_CATEGORIES: tuple[str, ...] = tuple(
    item.category
    for item in MIXED_NODE_CATEGORIES
    if item.minimum_players > min(MIXED_PLAYER_COUNTS)
)


def applicable_player_counts(category: str) -> tuple[int, ...]:
    """某个节点的适用人数：低于门槛的人数一律是结构性不适用，而不是伪造覆盖。"""
    for item in MIXED_NODE_CATEGORIES:
        if item.category == category:
            return tuple(count for count in MIXED_PLAYER_COUNTS if count >= item.minimum_players)
    raise KeyError(f"未知节点类别：{category}")


def structurally_not_applicable(category: str) -> tuple[int, ...]:
    """某个节点的结构性不适用人数。"""
    applicable = set(applicable_player_counts(category))
    return tuple(count for count in MIXED_PLAYER_COUNTS if count not in applicable)


MIXED_APPLICABLE_NODE_COUNT = sum(
    len(applicable_player_counts(category)) for category in MIXED_CATEGORY_IDS
)
MIXED_STRUCTURAL_HOLE_COUNT = sum(
    len(structurally_not_applicable(category)) for category in MIXED_CATEGORY_IDS
)
# 全部计划槽：可行动节点 + 结构性不适用槽。
MIXED_PLANNED_SLOT_COUNT = MIXED_APPLICABLE_NODE_COUNT + MIXED_STRUCTURAL_HOLE_COUNT

# ------------------------------------------------------------------ 构造配方

# 翻前动作形状：只描述「按行动顺序依次做什么」，与具体座位无关。
_SHAPE_OPEN = "open"
_SHAPE_LIMP = "limp"
_SHAPE_RAISE = "raise"
_SHAPE_RERAISE = "reraise"
_SHAPE_SHORT_CALL = "short-call"
_SHAPE_INCOMPLETE_RAISE = "incomplete-raise"
_SHAPE_JAM_THEN_CALL = "jam-then-call"

_SHAPE_DESCRIPTIONS = {
    _SHAPE_OPEN: "无自愿加注，首个行动者直接面对盲注",
    _SHAPE_LIMP: "先行者跛入后由下一位行动者面对盲注",
    _SHAPE_RAISE: "先行者加注到固定额度后由下一位行动者面对加注",
    _SHAPE_RERAISE: "连续两次加注后由下一位行动者面对再加注",
    _SHAPE_SHORT_CALL: "先行者加注后由短码座位面对不足额跟注",
    _SHAPE_INCOMPLETE_RAISE: "加注后全员跟注、大盲短码全下，行动权回到原加注者",
    _SHAPE_JAM_THEN_CALL: "先行者全下、其后一家跟注，行动权落在仍可行动的下一家",
}

# 短码角色：决定把哪一席的筹码改短，从而形成短码跟注、短码全下或单方全下。
_ROLE_NONE = "none"
_ROLE_ACTOR = "actor"
_ROLE_BIG_BLIND = "big-blind"
_ROLE_FIRST_ACTOR = "first-actor"


@dataclass(frozen=True)
class FixtureRecipe:
    """一类节点的确定性构造配方（冻结的机械明细）。"""

    category: str
    shape: str
    actor_holes: tuple[str, str]
    board: tuple[str, ...]
    short_role: str
    open_bet_on_street: bool


MIXED_RECIPES: tuple[FixtureRecipe, ...] = (
    FixtureRecipe("hu-blind-position", _SHAPE_OPEN, ("Ah", "Qh"), (), _ROLE_NONE, False),
    FixtureRecipe("unopened-open", _SHAPE_OPEN, ("Kd", "Qd"), (), _ROLE_NONE, False),
    FixtureRecipe("open-after-limp", _SHAPE_LIMP, ("Jh", "Th"), (), _ROLE_NONE, False),
    FixtureRecipe("facing-first-raise", _SHAPE_RAISE, ("Ah", "Jc"), (), _ROLE_NONE, False),
    FixtureRecipe("facing-reraise", _SHAPE_RERAISE, ("Qc", "Qs"), (), _ROLE_NONE, False),
    FixtureRecipe(
        "short-stack-call", _SHAPE_SHORT_CALL, ("9c", "9d"), (), _ROLE_ACTOR, False
    ),
    FixtureRecipe(
        "incomplete-raise", _SHAPE_INCOMPLETE_RAISE, ("Ac", "Kc"), (), _ROLE_BIG_BLIND, False
    ),
    FixtureRecipe("free-check", _SHAPE_OPEN, ("Ad", "Td"), ("Qs", "7h", "2c"), _ROLE_NONE, False),
    FixtureRecipe("flop-draw", _SHAPE_RAISE, ("As", "Js"), ("Qs", "7s", "2h"), _ROLE_NONE, True),
    FixtureRecipe(
        "top-pair-weak-kicker",
        _SHAPE_RAISE,
        ("8d", "5s"),
        ("8h", "3c", "2d", "4s"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "turn-combo-draw",
        _SHAPE_RAISE,
        ("Jh", "Th"),
        ("9h", "8h", "2c", "Ts"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "one-side-all-in",
        _SHAPE_JAM_THEN_CALL,
        ("Ah", "Qd"),
        ("Jc", "8d", "4h", "2s"),
        _ROLE_FIRST_ACTOR,
        True,
    ),
    FixtureRecipe(
        "overpair-on-high-board",
        _SHAPE_RAISE,
        ("Qc", "Qd"),
        ("Ah", "Kd", "7c", "2s", "3h"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "missed-draw-river",
        _SHAPE_RAISE,
        ("As", "Js"),
        ("Qs", "7s", "2h", "3d", "4c"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "shared-board",
        _SHAPE_RAISE,
        ("2c", "3d"),
        ("Ah", "Kd", "Qc", "Js", "Th"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "sizes-merged", _SHAPE_RAISE, ("Ts", "9c"), ("Th", "7c", "3s", "2d", "5h"), _ROLE_NONE, True
    ),
)

MIXED_RECIPE_BY_CATEGORY: dict[str, FixtureRecipe] = {
    recipe.category: recipe for recipe in MIXED_RECIPES
}
_RECIPE_CATEGORY_ORDER: tuple[str, ...] = tuple(recipe.category for recipe in MIXED_RECIPES)

# ------------------------------------------------------------------ 第二套构造配方
#
# 独立质量验证使用的第二套配方：类别与形状语义沿用既有定义，但逐项换成不同构造，
# 使新节点与既有 125 个可行动节点在内容上正交。既有配方常量不得改动，
# 否则已落盘清单的可复现性会被破坏。

MIXED_IQV_NODE_ID_SUFFIX = "-iqv1"

MIXED_IQV_RECIPES: tuple[FixtureRecipe, ...] = (
    FixtureRecipe("hu-blind-position", _SHAPE_OPEN, ("Kc", "Jc"), (), _ROLE_NONE, False),
    FixtureRecipe("unopened-open", _SHAPE_OPEN, ("As", "Ts"), (), _ROLE_NONE, False),
    FixtureRecipe("open-after-limp", _SHAPE_LIMP, ("Qh", "Jh"), (), _ROLE_NONE, False),
    FixtureRecipe("facing-first-raise", _SHAPE_RAISE, ("Ks", "Qc"), (), _ROLE_NONE, False),
    FixtureRecipe("facing-reraise", _SHAPE_RERAISE, ("Jd", "Jc"), (), _ROLE_NONE, False),
    FixtureRecipe(
        "short-stack-call", _SHAPE_SHORT_CALL, ("7h", "7s"), (), _ROLE_ACTOR, False
    ),
    FixtureRecipe(
        "incomplete-raise", _SHAPE_INCOMPLETE_RAISE, ("Ad", "Kd"), (), _ROLE_BIG_BLIND, False
    ),
    FixtureRecipe("free-check", _SHAPE_OPEN, ("Qh", "Th"), ("Jd", "6s", "2c"), _ROLE_NONE, False),
    FixtureRecipe("flop-draw", _SHAPE_RAISE, ("Th", "9h"), ("8h", "7h", "2c"), _ROLE_NONE, True),
    FixtureRecipe(
        "top-pair-weak-kicker",
        _SHAPE_RAISE,
        ("9c", "4h"),
        ("9d", "7s", "3h", "2c"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "turn-combo-draw",
        _SHAPE_RAISE,
        ("Qc", "Jc"),
        ("Tc", "9c", "4h", "2d"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "one-side-all-in",
        _SHAPE_JAM_THEN_CALL,
        ("Kc", "Js"),
        ("Td", "7h", "3c", "2d"),
        _ROLE_FIRST_ACTOR,
        True,
    ),
    FixtureRecipe(
        "overpair-on-high-board",
        _SHAPE_RAISE,
        ("Jc", "Jd"),
        ("Ah", "Qd", "8c", "3s", "2h"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "missed-draw-river",
        _SHAPE_RAISE,
        ("Kh", "Th"),
        ("Jh", "6h", "2c", "8d", "3s"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "shared-board",
        _SHAPE_RAISE,
        ("2h", "2s"),
        ("9c", "8d", "7h", "6s", "5c"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "sizes-merged",
        _SHAPE_RAISE,
        ("8c", "3h"),
        ("8d", "5c", "2s", "9h", "Kd"),
        _ROLE_NONE,
        True,
    ),
)

MIXED_IQV_RECIPE_BY_CATEGORY: dict[str, FixtureRecipe] = {
    recipe.category: recipe for recipe in MIXED_IQV_RECIPES
}
MIXED_IQV_RECIPE_CATEGORY_ORDER: tuple[str, ...] = tuple(
    recipe.category for recipe in MIXED_IQV_RECIPES
)

# ------------------------------------------------------------------ 第三套构造配方
#
# 又一套配方：类别与形状语义沿用既有定义，逐项换成与前两套都不同的构造，
# 使节点在内容上与既有清单正交。前两套配方常量不得改动，
# 否则已落盘清单的可复现性会被破坏。

MIXED_IQV2_NODE_ID_SUFFIX = "-iqv2"

MIXED_IQV2_RECIPES: tuple[FixtureRecipe, ...] = (
    FixtureRecipe("hu-blind-position", _SHAPE_OPEN, ("Ad", "9d"), (), _ROLE_NONE, False),
    FixtureRecipe("unopened-open", _SHAPE_OPEN, ("Qs", "Js"), (), _ROLE_NONE, False),
    FixtureRecipe("open-after-limp", _SHAPE_LIMP, ("Td", "9d"), (), _ROLE_NONE, False),
    FixtureRecipe("facing-first-raise", _SHAPE_RAISE, ("Kh", "Tc"), (), _ROLE_NONE, False),
    FixtureRecipe("facing-reraise", _SHAPE_RERAISE, ("Ts", "Tc"), (), _ROLE_NONE, False),
    FixtureRecipe(
        "short-stack-call", _SHAPE_SHORT_CALL, ("8h", "8c"), (), _ROLE_ACTOR, False
    ),
    FixtureRecipe(
        "incomplete-raise", _SHAPE_INCOMPLETE_RAISE, ("As", "Ks"), (), _ROLE_BIG_BLIND, False
    ),
    FixtureRecipe("free-check", _SHAPE_OPEN, ("Kc", "9c"), ("Td", "5h", "2s"), _ROLE_NONE, False),
    FixtureRecipe("flop-draw", _SHAPE_RAISE, ("Qd", "Jd"), ("Td", "8d", "3h"), _ROLE_NONE, True),
    FixtureRecipe(
        "top-pair-weak-kicker",
        _SHAPE_RAISE,
        ("6h", "3d"),
        ("6s", "5c", "2h", "Kd"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "turn-combo-draw",
        _SHAPE_RAISE,
        ("Ah", "5h"),
        ("3h", "4h", "Kc", "Td"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "one-side-all-in",
        _SHAPE_JAM_THEN_CALL,
        ("Qd", "Td"),
        ("9s", "6c", "3h", "2c"),
        _ROLE_FIRST_ACTOR,
        True,
    ),
    FixtureRecipe(
        "overpair-on-high-board",
        _SHAPE_RAISE,
        ("Tc", "Ts"),
        ("Kh", "Qd", "9c", "4s", "2d"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "missed-draw-river",
        _SHAPE_RAISE,
        ("9d", "8d"),
        ("Kd", "Jd", "2h", "5c", "3s"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "shared-board",
        _SHAPE_RAISE,
        ("5c", "4d"),
        ("Ks", "Qd", "Jc", "Th", "9s"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "sizes-merged",
        _SHAPE_RAISE,
        ("Kc", "7h"),
        ("Kd", "5s", "2c", "9h", "4d"),
        _ROLE_NONE,
        True,
    ),
)

MIXED_IQV2_RECIPE_BY_CATEGORY: dict[str, FixtureRecipe] = {
    recipe.category: recipe for recipe in MIXED_IQV2_RECIPES
}
MIXED_IQV2_RECIPE_CATEGORY_ORDER: tuple[str, ...] = tuple(
    recipe.category for recipe in MIXED_IQV2_RECIPES
)

# ------------------------------------------------------------------ 第四次构造配方
#
# 第四套配方：类别与形状语义沿用既有定义，逐项换成与前几套都不同的构造，
# 使节点在牌面与行动线上与既有清单正交。既有配方常量不得改动，
# 否则已落盘清单的可复现性会被破坏。

MIXED_IQV3_NODE_ID_SUFFIX = "-iqv3"

MIXED_IQV3_RECIPES: tuple[FixtureRecipe, ...] = (
    FixtureRecipe("hu-blind-position", _SHAPE_OPEN, ("Jh", "9h"), (), _ROLE_NONE, False),
    FixtureRecipe("unopened-open", _SHAPE_OPEN, ("Ac", "Qc"), (), _ROLE_NONE, False),
    FixtureRecipe("open-after-limp", _SHAPE_LIMP, ("Qh", "Ts"), (), _ROLE_NONE, False),
    FixtureRecipe("facing-first-raise", _SHAPE_RAISE, ("Ad", "Jh"), (), _ROLE_NONE, False),
    FixtureRecipe("facing-reraise", _SHAPE_RERAISE, ("8d", "8h"), (), _ROLE_NONE, False),
    FixtureRecipe(
        "short-stack-call", _SHAPE_SHORT_CALL, ("5h", "5s"), (), _ROLE_ACTOR, False
    ),
    FixtureRecipe(
        "incomplete-raise", _SHAPE_INCOMPLETE_RAISE, ("Ah", "Kc"), (), _ROLE_BIG_BLIND, False
    ),
    FixtureRecipe("free-check", _SHAPE_OPEN, ("Js", "8s"), ("9s", "4h", "2d"), _ROLE_NONE, False),
    FixtureRecipe("flop-draw", _SHAPE_RAISE, ("Kd", "Td"), ("9d", "7d", "3c"), _ROLE_NONE, True),
    FixtureRecipe(
        "top-pair-weak-kicker",
        _SHAPE_RAISE,
        ("Jc", "6h"),
        ("Jd", "8s", "3c", "2h"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "turn-combo-draw",
        _SHAPE_RAISE,
        ("9c", "8c"),
        ("7c", "6c", "Kd", "2s"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "one-side-all-in",
        _SHAPE_JAM_THEN_CALL,
        ("Ac", "9h"),
        ("8s", "5d", "2h", "3c"),
        _ROLE_FIRST_ACTOR,
        True,
    ),
    FixtureRecipe(
        "overpair-on-high-board",
        _SHAPE_RAISE,
        ("9h", "9s"),
        ("Ah", "Kc", "Qd", "5s", "3h"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "missed-draw-river",
        _SHAPE_RAISE,
        ("Ah", "4h"),
        ("Kh", "8h", "2c", "5d", "9s"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "shared-board",
        _SHAPE_RAISE,
        ("4c", "3s"),
        ("Th", "9d", "8c", "7s", "6h"),
        _ROLE_NONE,
        True,
    ),
    FixtureRecipe(
        "sizes-merged",
        _SHAPE_RAISE,
        ("Qh", "5c"),
        ("Qd", "9s", "4h", "2c", "7d"),
        _ROLE_NONE,
        True,
    ),
)

MIXED_IQV3_RECIPE_BY_CATEGORY: dict[str, FixtureRecipe] = {
    recipe.category: recipe for recipe in MIXED_IQV3_RECIPES
}
MIXED_IQV3_RECIPE_CATEGORY_ORDER: tuple[str, ...] = tuple(
    recipe.category for recipe in MIXED_IQV3_RECIPES
)

# ------------------------------------------------------------------ 清单模型


class MixedPublicAction(BaseModel):
    """清单中的一条前置公开动作；BET/RAISE 的金额是本街总额（raise-to）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    street: Street
    seat: int = Field(ge=0)
    action: Literal["fold", "check", "call", "bet", "raise"]
    amount: int = Field(default=0, ge=0)


class MixedNodeFixture(BaseModel):
    """一个确定性的可行动节点：逐张牌、筹码、庄位与前置公开动作全部写死。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str
    category: str
    player_count: int = Field(ge=2, le=9)
    button: int = Field(ge=0)
    starting_stack: int = Field(gt=0)
    # 逐座位两张底牌，按座位升序给出。
    hole_cards: tuple[tuple[str, str], ...]
    # 公共牌按发牌顺序逐张给出，长度只能是 0/3/4/5。
    board: tuple[str, ...] = ()
    # 前置公开动作（不含两条盲注），按顺序执行。
    actions: tuple[MixedPublicAction, ...] = ()
    stacks: tuple[int, ...] = ()
    # 该节点的决策街；必须与回放后的引擎街一致。
    decision_street: Street
    # 该节点是否本来就发生在同一条街的主动投入之后（用于分类统计口径）。
    price_context: str = "unopened"
    # 逐座位筹码是否可按深度等比缩放；固定短码节点只在自身筹码深度上使用。
    depth_scalable: bool = True

    @model_validator(mode="after")
    def _require_consistent_node(self) -> MixedNodeFixture:
        if self.category not in MIXED_CATEGORY_IDS:
            raise ValueError(f"未知节点类别：{self.category}")
        if self.player_count not in applicable_player_counts(self.category):
            raise ValueError(f"{self.category} 在 {self.player_count} 人桌是结构性不适用槽")
        if len(self.hole_cards) != self.player_count:
            raise ValueError("底牌数量必须与人数一致")
        for per_seat in self.hole_cards:
            if len(per_seat) != 2:
                raise ValueError("每个座位必须恰好给出两张底牌")
        for token in (*self.board, *(card for pair in self.hole_cards for card in pair)):
            card_from_str(token)
        expected_board = {Street.PREFLOP: 0, Street.FLOP: 3, Street.TURN: 4, Street.RIVER: 5}
        if len(self.board) != expected_board[self.decision_street]:
            raise ValueError("公共牌数量必须与决策街一致")
        if len(set(self.board)) != len(self.board):
            raise ValueError("公共牌不能重复")
        all_cards = [*self.board, *(card for pair in self.hole_cards for card in pair)]
        if len(set(all_cards)) != len(all_cards):
            raise ValueError("底牌与公共牌之间不能重复")
        if not 0 <= self.button < self.player_count:
            raise ValueError("庄位越界")
        if self.stacks and len(self.stacks) != self.player_count:
            raise ValueError("逐座位筹码数量必须与人数一致")
        seats = {action.seat for action in self.actions}
        if any(not 0 <= seat < self.player_count for seat in seats):
            raise ValueError("前置公开动作的座位越界")
        return self


class MixedFixtureManifest(BaseModel):
    """逐张牌清单：首次实跑前必须冻结并签收的机械明细。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["mixed-bot-fixtures.v1"] = MIXED_FIXTURE_SCHEMA_VERSION
    strategy_id: str
    code_identity: str
    config_digest: str
    seeds: tuple[int, ...]
    nodes: tuple[MixedNodeFixture, ...]
    scenario_order: str = ""
    seed_derivation: str = ""
    stage_plan: tuple[str, ...] = ()
    resource_envelope: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    output_dir: str = ""
    report_format: str = ""

    @model_validator(mode="after")
    def _require_frozen(self) -> MixedFixtureManifest:
        if not self.strategy_id or not self.code_identity or not self.config_digest:
            raise ValueError("清单必须写明策略身份、代码身份与配置摘要")
        if not self.seeds:
            raise ValueError("清单必须写明预留的主种子块")
        ids = [node.node_id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("节点标识不能重复")
        return self

    def digest(self) -> str:
        """清单摘要：只由规范化的清单内容决定，用于报告可追溯。"""
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def nodes_for(self, player_count: int) -> tuple[MixedNodeFixture, ...]:
        return tuple(node for node in self.nodes if node.player_count == player_count)

    def nodes_for_street(self, player_count: int, street: Street) -> tuple[MixedNodeFixture, ...]:
        return tuple(
            node
            for node in self.nodes
            if node.player_count == player_count and node.decision_street is street
        )


@dataclass(frozen=True)
class AppliedNode:
    """回放一个节点后的确定局面。"""

    engine: PokerEngine
    tracker: MixedSummaryTracker
    fixture: MixedNodeFixture

    def actor_state(self) -> GameState:
        """当前行动者视角的安全状态（先脱敏投影，再附加公开摘要）。"""
        return mixed_state(project_for_actor(self.engine.snapshot()), self.tracker.context())

    def legal_actions(self) -> LegalActions:
        return self.engine.legal_actions()


# ------------------------------------------------------------------ 配方执行


@dataclass
class _ScriptedRun:
    """一次配方执行的中间结果。"""

    engine: PokerEngine
    actions: list[MixedPublicAction]
    first_actor: int
    actor_seat: int

    @property
    def blind_seats(self) -> tuple[int, int]:
        """从引擎历史读出的两条盲注座位，不自行重算盲注规则。"""
        return int(self.engine.history[0]["seat"]), int(self.engine.history[1]["seat"])


def _step(engine: PokerEngine, action: Action, actions: list[MixedPublicAction]) -> None:
    """执行一步并记录公开动作（金额取 raise-to 总额，与引擎历史口径分开）。"""
    engine.apply_action(action)
    record = engine.history[-1]
    street = _STREET_BY_NAME[str(record["street"])]
    amount = action.amount if action.type in (ActionType.BET, ActionType.RAISE) else 0
    actions.append(
        MixedPublicAction(
            street=street,
            seat=int(record["seat"]),
            action=action.type.value,
            amount=amount,
        )
    )


def _call_or_check(engine: PokerEngine, actions: list[MixedPublicAction]) -> None:
    legal = engine.legal_actions()
    if legal.can_check:
        _step(engine, Action(ActionType.CHECK), actions)
    elif legal.can_call:
        _step(engine, Action(ActionType.CALL), actions)
    else:
        raise MixedFixtureError("驱动到目标街时遇到无法跟注也无法过牌的局面")


def _run_shape(
    engine: PokerEngine,
    run: _ScriptedRun,
    shape: str,
    player_count: int,
) -> None:
    """按冻结形状执行翻前前缀。"""
    actions = run.actions
    if shape == _SHAPE_OPEN:
        return
    if shape == _SHAPE_LIMP:
        _call_or_check(engine, actions)
        return
    if shape == _SHAPE_RAISE:
        _step(engine, Action(ActionType.RAISE, _OPEN_RAISE_TO), actions)
        return
    if shape == _SHAPE_RERAISE:
        _step(engine, Action(ActionType.RAISE, _OPEN_RAISE_TO), actions)
        _step(engine, Action(ActionType.RAISE, _RERAISE_TO), actions)
        return
    if shape == _SHAPE_SHORT_CALL:
        _step(engine, Action(ActionType.RAISE, _SHORT_CALL_RAISE_TO), actions)
        return
    if shape == _SHAPE_INCOMPLETE_RAISE:
        # 先行者加注，其余人依次跟注，大盲短码全下；行动权回到先行者且不再重开。
        _step(engine, Action(ActionType.RAISE, _OPEN_RAISE_TO), actions)
        for _ in range(player_count - 2):
            _step(engine, Action(ActionType.CALL), actions)
        _step(engine, Action(ActionType.RAISE, _INCOMPLETE_SHORT_JAM_TO), actions)
        return
    if shape == _SHAPE_JAM_THEN_CALL:
        _step(engine, Action(ActionType.RAISE, _ONE_SIDE_JAM_TO), actions)
        _step(engine, Action(ActionType.CALL), actions)
        return
    raise MixedFixtureError(f"未知翻前动作形状：{shape}")


def _advance_to(
    engine: PokerEngine,
    target: Street,
    actions: list[MixedPublicAction],
) -> None:
    """用跟注/过牌把牌局推进到目标街，不越过目标街行动。"""
    guard = 0
    while engine.street < target and not engine.hand_over:
        guard += 1
        if guard > _DRIVER_GUARD:
            raise MixedFixtureError("推进到目标街时超出保护上限")
        street_before = engine.street
        while engine.street == street_before and not engine.hand_over:
            guard += 1
            if guard > _DRIVER_GUARD:
                raise MixedFixtureError("完成本街时超出保护上限")
            _call_or_check(engine, actions)


def _open_bet(engine: PokerEngine, actions: list[MixedPublicAction]) -> None:
    """到达决策街后先让首位玩家做一个尺度合理的下注，制造价格与资格场景。"""
    legal = engine.legal_actions()
    if not legal.can_bet:
        raise MixedFixtureError("配方要求本街先下注，但当前无法下注")
    target = max(legal.min_bet, min(legal.max_bet, engine.pot // 2))
    _step(engine, Action(ActionType.BET, target), actions)


def _filler_cards(excluded: set[str], count: int) -> list[str]:
    """按固定顺序给非焦点座位填牌，保证确定性且与已用牌不重复。"""
    picked = [token for token in _ALL_CARDS if token not in excluded][:count]
    if len(picked) != count:
        raise MixedFixtureError("可用的兜底牌不足")
    return picked


def _start_engine(
    player_count: int,
    stacks: Sequence[int],
    hole_cards: Sequence[Sequence[str]],
    board: Sequence[str],
) -> PokerEngine:
    engine = PokerEngine(
        player_count,
        MIXED_SMALL_BLIND,
        MIXED_BIG_BLIND,
        MIXED_DEFAULT_STACK,
        seed=0,
    )
    for seat, stack in enumerate(stacks):
        engine.players[seat].stack = stack
    engine.start_hand_with(
        button=MIXED_NODE_BUTTON,
        hole_cards={
            seat: [card_from_str(token) for token in per_seat]
            for seat, per_seat in enumerate(hole_cards)
        },
        board=[card_from_str(token) for token in board],
    )
    return engine


def _open_engine(
    recipe: FixtureRecipe,
    player_count: int,
    stacks: Sequence[int],
    hole_cards: Sequence[Sequence[str]],
) -> _ScriptedRun:
    """开局但不执行任何前缀：盲位与首位行动者在发牌后即可读取。"""
    engine = _start_engine(player_count, stacks, hole_cards, recipe.board)
    first_actor = engine.current_seat
    return _ScriptedRun(engine=engine, actions=[], first_actor=first_actor, actor_seat=first_actor)


def _execute_recipe(
    recipe: FixtureRecipe,
    player_count: int,
    stacks: Sequence[int],
    hole_cards: Sequence[Sequence[str]],
) -> _ScriptedRun:
    run = _open_engine(recipe, player_count, stacks, hole_cards)
    engine = run.engine
    _run_shape(engine, run, recipe.shape, player_count)
    _advance_to(engine, MIXED_CATEGORY_STREET[recipe.category], run.actions)
    if engine.hand_over:
        raise MixedFixtureError(f"{recipe.category} 的前置动作使牌局提前结束")
    if recipe.open_bet_on_street:
        _open_bet(engine, run.actions)
    run.actor_seat = engine.current_seat
    return run


def _placeholder_holes(player_count: int, board: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """第一遍用的占位底牌：动作合法性只取决于筹码与街，与具体牌面无关。"""
    tokens = _filler_cards(set(board), 2 * player_count)
    return tuple(
        (tokens[2 * seat], tokens[2 * seat + 1]) for seat in range(player_count)
    )


def _stacks_for(
    recipe: FixtureRecipe,
    player_count: int,
    run: _ScriptedRun,
    starting_stack: int,
) -> list[int]:
    """按短码角色写出逐座位筹码；其余座位保持该深度的常量筹码。"""
    stacks = [starting_stack] * player_count
    _, big_blind = run.blind_seats
    if recipe.short_role == _ROLE_ACTOR:
        stacks[run.actor_seat] = _SHORT_CALLER_STACK
    elif recipe.short_role == _ROLE_BIG_BLIND:
        stacks[big_blind] = _SHORT_JAMMER_STACK
    elif recipe.short_role == _ROLE_FIRST_ACTOR:
        stacks[run.first_actor] = _JAMMER_STACK
    return stacks


def _settle_stacks(
    recipe: FixtureRecipe,
    player_count: int,
    placeholder: Sequence[Sequence[str]],
    starting_stack: int,
) -> _ScriptedRun:
    """先把短码角色落位再执行前缀。

    盲位与首位行动者开局即可读出，因此大盲短码与先行者全下都能在第一遍就正确设置；
    只有「决策者本人是短码」需要先跑一遍前缀才知道是谁，第二遍再落位。
    """
    uniform = [starting_stack] * player_count
    opened = _open_engine(recipe, player_count, uniform, placeholder)
    _, big_blind = opened.blind_seats
    stacks = list(uniform)
    if recipe.short_role == _ROLE_BIG_BLIND:
        stacks[big_blind] = _SHORT_JAMMER_STACK
    elif recipe.short_role == _ROLE_FIRST_ACTOR:
        stacks[opened.first_actor] = _JAMMER_STACK
    run = _execute_recipe(recipe, player_count, stacks, placeholder)
    if recipe.short_role == _ROLE_ACTOR:
        candidate = _stacks_for(recipe, player_count, run, starting_stack)
        if candidate != stacks:
            stacks = candidate
            run = _execute_recipe(recipe, player_count, stacks, placeholder)
    _require_short_role_landed(recipe, run, stacks)
    return run


def _require_short_role_landed(
    recipe: FixtureRecipe,
    run: _ScriptedRun,
    stacks: Sequence[int],
) -> None:
    """复核短码确实落在配方指定的角色上，避免配方与筹码错位后仍继续。"""
    _, big_blind = run.blind_seats
    if recipe.short_role == _ROLE_BIG_BLIND:
        if stacks[big_blind] != _SHORT_JAMMER_STACK or run.actions[-1].seat != big_blind:
            raise MixedFixtureError("大盲短码全下的角色未落在配方指定的大盲上")
    elif recipe.short_role == _ROLE_FIRST_ACTOR:
        if stacks[run.first_actor] != _JAMMER_STACK or run.actions[0].seat != run.first_actor:
            raise MixedFixtureError("先行者全下的角色未落在配方指定的先行者上")
    elif (
        recipe.short_role == _ROLE_ACTOR
        and stacks[run.actor_seat] != _SHORT_CALLER_STACK
    ):
        raise MixedFixtureError("短码跟注的角色未落在决策者身上")


def _build_node_from(
    recipe: FixtureRecipe,
    player_count: int,
    *,
    starting_stack: int,
    node_id_suffix: str,
) -> MixedNodeFixture:
    """按给定配方生成一个可行动节点。

    先用占位底牌把短码角色迭代稳定并确定决策座位，再把主题牌面放到该座位重跑一次；
    两次的决策座位与决策街必须完全一致，否则显式失败，不做静默修补。

    ``starting_stack`` 用于把同一配方放到别的筹码深度上重跑：牌面与形状不变，翻后开注额
    由该深度下当时的合法区间决定。带短码角色的配方筹码额与深度无关，因此只在默认深度使用。
    """
    category = recipe.category
    if player_count not in applicable_player_counts(category):
        raise MixedFixtureError(f"{category} 在 {player_count} 人桌是结构性不适用槽")

    placeholder = _placeholder_holes(player_count, recipe.board)
    settled = _settle_stacks(recipe, player_count, placeholder, starting_stack)
    stacks = _stacks_for(recipe, player_count, settled, starting_stack)
    focus = settled.actor_seat

    # 焦点座位拿主题牌面，其余座位按固定顺序填牌，保证与已用牌不重复。
    used = set(recipe.board) | set(recipe.actor_holes)
    others = _filler_cards(used, 2 * (player_count - 1))
    holes: list[tuple[str, str]] = []
    filler_index = 0
    for seat in range(player_count):
        if seat == focus:
            holes.append(recipe.actor_holes)
        else:
            holes.append((others[2 * filler_index], others[2 * filler_index + 1]))
            filler_index += 1

    target = MIXED_CATEGORY_STREET[category]
    final = _execute_recipe(recipe, player_count, stacks, holes)
    if final.actor_seat != focus or final.engine.street is not target:
        raise MixedFixtureError(f"{category} 在 {player_count} 人桌的两次执行结果不一致")
    if tuple(final.actions) != tuple(settled.actions):
        raise MixedFixtureError(f"{category} 在 {player_count} 人桌的动作线与占位执行不一致")

    return MixedNodeFixture(
        node_id=f"{category}-n{player_count}{node_id_suffix}",
        category=category,
        player_count=player_count,
        button=MIXED_NODE_BUTTON,
        starting_stack=starting_stack,
        hole_cards=tuple(holes),
        board=recipe.board,
        actions=tuple(final.actions),
        stacks=tuple(stacks),
        decision_street=target,
        price_context="facing-bet" if recipe.open_bet_on_street else "unopened",
        depth_scalable=recipe.short_role == _ROLE_NONE,
    )


def build_node(
    category: str,
    player_count: int,
    *,
    starting_stack: int = MIXED_DEFAULT_STACK,
) -> MixedNodeFixture:
    """按首套冻结配方生成一个可行动节点；标识不带后缀，与既有清单逐字一致。"""
    return _build_node_from(
        MIXED_RECIPE_BY_CATEGORY[category],
        player_count,
        starting_stack=starting_stack,
        node_id_suffix="",
    )


def build_iqv_node(
    category: str,
    player_count: int,
    *,
    starting_stack: int = MIXED_DEFAULT_STACK,
) -> MixedNodeFixture:
    """按第二套配方生成一个可行动节点；标识带后缀，与首套节点不重名。"""
    return _build_node_from(
        MIXED_IQV_RECIPE_BY_CATEGORY[category],
        player_count,
        starting_stack=starting_stack,
        node_id_suffix=MIXED_IQV_NODE_ID_SUFFIX,
    )


def build_frozen_nodes() -> tuple[MixedNodeFixture, ...]:
    """按冻结配方的固定顺序生成全部可行动节点。"""
    return tuple(
        build_node(category, player_count)
        for category in _RECIPE_CATEGORY_ORDER
        for player_count in applicable_player_counts(category)
    )


def build_frozen_iqv_nodes() -> tuple[MixedNodeFixture, ...]:
    """按第二套配方的固定顺序生成全部可行动节点；数量与计划槽口径保持一致。"""
    return tuple(
        build_iqv_node(category, player_count)
        for category in MIXED_IQV_RECIPE_CATEGORY_ORDER
        for player_count in applicable_player_counts(category)
    )


def build_iqv2_node(
    category: str,
    player_count: int,
    *,
    starting_stack: int = MIXED_DEFAULT_STACK,
) -> MixedNodeFixture:
    """按第三套配方生成一个可行动节点；标识带独立后缀，与前两套节点都不重名。"""
    return _build_node_from(
        MIXED_IQV2_RECIPE_BY_CATEGORY[category],
        player_count,
        starting_stack=starting_stack,
        node_id_suffix=MIXED_IQV2_NODE_ID_SUFFIX,
    )


def build_frozen_iqv2_nodes() -> tuple[MixedNodeFixture, ...]:
    """按第三套配方的固定顺序生成全部可行动节点。"""
    return tuple(
        build_iqv2_node(category, player_count)
        for category in MIXED_IQV2_RECIPE_CATEGORY_ORDER
        for player_count in applicable_player_counts(category)
    )


def build_iqv3_node(
    category: str,
    player_count: int,
    *,
    starting_stack: int = MIXED_DEFAULT_STACK,
) -> MixedNodeFixture:
    """按第四套配方生成一个可行动节点；标识带独立后缀，与前三套节点都不重名。"""
    return _build_node_from(
        MIXED_IQV3_RECIPE_BY_CATEGORY[category],
        player_count,
        starting_stack=starting_stack,
        node_id_suffix=MIXED_IQV3_NODE_ID_SUFFIX,
    )


def build_frozen_iqv3_nodes() -> tuple[MixedNodeFixture, ...]:
    """按第四套配方的固定顺序生成全部可行动节点。"""
    return tuple(
        build_iqv3_node(category, player_count)
        for category in MIXED_IQV3_RECIPE_CATEGORY_ORDER
        for player_count in applicable_player_counts(category)
    )


def build_frozen_manifest(
    *,
    code_identity: str,
    config_digest: str,
    seeds: Sequence[int],
    output_dir: str,
    scenario_order: str,
    seed_derivation: str,
    stage_plan: Sequence[str],
    resource_envelope: Sequence[str],
    stop_conditions: Sequence[str],
    report_format: str,
    strategy_id: str = MIXED_STRATEGY_IDENTIFIER,
    nodes: Sequence[MixedNodeFixture] | None = None,
) -> MixedFixtureManifest:
    """装配冻结清单：节点由配方生成，其余机械明细由调用方按规格注入。

    ``nodes`` 省略时按首套配方生成，使既有调用逐字不变；显式传入时不做任何改写。
    """
    return MixedFixtureManifest(
        strategy_id=strategy_id,
        code_identity=code_identity,
        config_digest=config_digest,
        seeds=tuple(seeds),
        nodes=build_frozen_nodes() if nodes is None else tuple(nodes),
        scenario_order=scenario_order,
        seed_derivation=seed_derivation,
        stage_plan=tuple(stage_plan),
        resource_envelope=tuple(resource_envelope),
        stop_conditions=tuple(stop_conditions),
        output_dir=output_dir,
        report_format=report_format,
    )


def manifest_json(manifest: MixedFixtureManifest) -> str:
    """把清单序列化为可直接落盘的文本（键序稳定，便于核对摘要）。"""
    return json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


# ------------------------------------------------------------------ 回放


def apply_node(fixture: MixedNodeFixture, *, hand_number: int = 1) -> AppliedNode:
    """按清单回放一个节点：注入底牌与公共牌，再按顺序执行前置公开动作。"""
    stacks = fixture.stacks or (fixture.starting_stack,) * fixture.player_count
    engine = _start_engine(
        fixture.player_count,
        stacks,
        fixture.hole_cards,
        fixture.board,
    )
    if engine.street is not Street.PREFLOP:
        raise MixedFixtureError("节点必须从翻前开始回放")
    tracker = MixedSummaryTracker()
    if not engine.hand_over:
        tracker.begin_hand(
            hand_number=hand_number,
            num_players=fixture.player_count,
            small_blind=MIXED_SMALL_BLIND,
            big_blind=MIXED_BIG_BLIND,
            # 离线清单可以覆盖全部座位，不制造生产桌面上不存在的风格差异。
            bot_seats=tuple(range(fixture.player_count)),
            history=engine.history,
        )
    for action in fixture.actions:
        engine.apply_action(Action(ActionType(action.action), action.amount))
        tracker.consume_after_action(engine.history)
    if engine.hand_over:
        raise MixedFixtureError(f"节点 {fixture.node_id} 的前置动作使牌局提前结束")
    if engine.street is not fixture.decision_street:
        raise MixedFixtureError(
            f"节点 {fixture.node_id} 回放后的街与声明的决策街不一致"
        )
    return AppliedNode(engine=engine, tracker=tracker, fixture=fixture)


def iter_planned_slots() -> Iterator[tuple[str, int, bool]]:
    """遍历全部计划槽：``(类别, 人数, 是否可行动)``。"""
    for category in MIXED_CATEGORY_IDS:
        applicable = set(applicable_player_counts(category))
        for count in MIXED_PLAYER_COUNTS:
            yield category, count, count in applicable


def planned_slots_by_category(category: str) -> Sequence[tuple[int, bool]]:
    """某一类别的全部计划槽。"""
    applicable = set(applicable_player_counts(category))
    return tuple((count, count in applicable) for count in MIXED_PLAYER_COUNTS)
