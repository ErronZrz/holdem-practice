"""新 Bot 离线验证用的固定节点与清单能力（测试侧永久能力，非一次性脚本）。

职责：
- 定义 16 类评测节点、2–9 人适用性矩阵与 128 个计划槽（含 3 个结构性不适用槽）；
- 定义「逐张牌 + 前置公开动作」的清单 schema 与确定性回放入口；
- 不在本模块内置任何具体牌面清单：逐张牌 fixture 必须在首次实跑前单独冻结并签收。
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
from app.strategy.projection import project_for_actor

# 清单与逐张牌 fixture 的版本；与运行产物、候选 A 工件均无关。
MIXED_FIXTURE_SCHEMA_VERSION = "mixed-bot-fixtures.v1"
# 产品支持的人数范围。
MIXED_PLAYER_COUNTS: tuple[int, ...] = (2, 3, 4, 5, 6, 7, 8, 9)
# 名义盲注与筹码深度的三个档位（BB 以 5/10 盲注计）。
MIXED_SMALL_BLIND = 5
MIXED_BIG_BLIND = 10
MIXED_DEPTHS_BB: tuple[int, ...] = (15, 100, 1000)
MIXED_STREETS: tuple[Street, ...] = (
    Street.PREFLOP,
    Street.FLOP,
    Street.TURN,
    Street.RIVER,
)


class MixedNodeCategory(BaseModel):
    """一类评测节点的受控定义。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str
    description: str
    minimum_players: int


MIXED_NODE_CATEGORIES: tuple[MixedNodeCategory, ...] = (
    MixedNodeCategory(
        category="hu-blind-position",
        description="单挑盲位与多人桌首位行动的差异",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="unopened-open",
        description="无人自愿加注时的开池",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="open-after-limp",
        description="跛入之后的开池",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="facing-first-raise",
        description="面对第一次加注",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="facing-reraise",
        description="面对连续再加注",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="free-check",
        description="免费过牌节点",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="top-pair-weak-kicker",
        description="顶对弱踢脚",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="overpair-on-high-board",
        description="强口袋对子遇高公共牌",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="flop-draw",
        description="翻牌同花或顺子听牌",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="turn-combo-draw",
        description="转牌组合听牌",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="missed-draw-river",
        description="河牌错失听牌",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="shared-board",
        description="公共两对、顺子或同花的共享牌面",
        minimum_players=2,
    ),
    MixedNodeCategory(
        category="one-side-all-in",
        description="一方已全下、另两方仍可行动的底池",
        minimum_players=3,
    ),
    MixedNodeCategory(
        category="short-stack-call",
        description="短码跟注与无资格边池",
        minimum_players=3,
    ),
    MixedNodeCategory(
        category="incomplete-raise",
        description="不足完整加注后不重开原行动者加注权",
        minimum_players=3,
    ),
    MixedNodeCategory(
        category="sizes-merged",
        description="多个尺寸被夹紧为同一金额",
        minimum_players=2,
    ),
)

MIXED_CATEGORY_IDS: tuple[str, ...] = tuple(
    item.category for item in MIXED_NODE_CATEGORIES
)
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
    # 逐座位两张底牌，按座位升序给出；每项是恰好两张牌的字符串元组。
    hole_cards: tuple[tuple[str, str], ...]
    # 公共牌按发牌顺序逐张给出，长度只能是 0/3/4/5。
    board: tuple[str, ...] = ()
    actions: tuple[MixedPublicAction, ...] = ()
    stacks: tuple[int, ...] = ()
    expect_distribution_slot: bool = True

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
        if len(self.board) not in (0, 3, 4, 5):
            raise ValueError("公共牌只能是 0/3/4/5 张")
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


def apply_node(fixture: MixedNodeFixture, *, hand_number: int = 1) -> AppliedNode:
    """按清单回放一个节点：注入底牌与公共牌，再按顺序执行前置公开动作。"""
    engine = PokerEngine(
        fixture.player_count,
        MIXED_SMALL_BLIND,
        MIXED_BIG_BLIND,
        fixture.starting_stack,
        seed=0,
    )
    if fixture.stacks:
        for seat, stack in enumerate(fixture.stacks):
            engine.players[seat].stack = stack
    engine.start_hand_with(
        button=fixture.button,
        hole_cards={
            seat: [card_from_str(token) for token in per_seat]
            for seat, per_seat in enumerate(fixture.hole_cards)
        },
        board=[card_from_str(token) for token in fixture.board],
    )
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
        raise ValueError(f"节点 {fixture.node_id} 的前置动作使牌局提前结束")
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
