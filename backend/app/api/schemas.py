"""对外 API 的 Pydantic 请求/响应模型。"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.strategy.registry import UnknownStrategyError, resolve_identifier


class CreateGameRequest(BaseModel):
    """创建对局的请求。产品支持 2–9 人（引擎自身按 N 人设计且不设上限，默认 2）。

    人数上限只在这里落实：越界请求直接失败，不静默截断、不回退到默认值。
    大盲必须是偶数，小盲由大盲推导（= 大盲 / 2）；``target_hands`` 省略表示不限手数。
    ``small_blind`` / ``target_hands`` / ``bot_strategy`` 保留以兼容旧客户端，界面已不再提供这三项。
    ``bot_strategy`` 只接受受控注册表内的标识，旧值会被规范化到对应历史版本。
    """

    num_players: int = Field(default=2, ge=2, le=9)
    big_blind: int = Field(default=10, ge=2)
    starting_stack: int = Field(default=1000, ge=1)
    seed: int | None = None
    small_blind: int | None = Field(default=None, ge=1)
    target_hands: int | None = Field(default=None, ge=1, le=10000)
    # 默认取规范标识，并让校验器同样作用于默认值，避免绕过受控注册表。
    bot_strategy: str = Field(default="heuristic@1", validate_default=True)

    @field_validator("bot_strategy")
    @classmethod
    def _normalize_bot_strategy(cls, value: str) -> str:
        """规范化受控策略标识；未知标识校验失败，不静默回退到默认策略。"""
        try:
            return resolve_identifier(value)
        except UnknownStrategyError as exc:
            raise ValueError(str(exc)) from exc


class SubmitActionRequest(BaseModel):
    """提交动作的请求；bet/raise 需要金额，其余忽略。"""

    action: Literal["fold", "check", "call", "bet", "raise"]
    amount: int | None = Field(default=None, ge=0)


class LegalActionsView(BaseModel):
    can_fold: bool
    can_check: bool
    can_call: bool
    call_amount: int
    actual_call_amount: int
    is_short_all_in_call: bool
    can_bet: bool
    min_bet: int
    max_bet: int
    can_raise: bool
    min_raise_to: int
    max_raise_to: int


class ActionRecord(BaseModel):
    """一手牌中单次动作（含盲注），用于牌桌内实时展示当前手历史。"""

    street: str
    seat: int
    action: str
    amount: int


class ShowdownHand(BaseModel):
    """摊牌时单个玩家的最佳 5 张牌与牌型。"""

    cards: list[str]
    category: str


class PotResult(BaseModel):
    """单个边池的归属结果。"""

    amount: int
    winners: list[int]
    shares: dict[int, int]


class PlayerView(BaseModel):
    seat: int
    name: str
    stack: int
    hole_cards: list[str]
    cards_revealed: bool
    folded: bool
    all_in: bool
    street_bet: int
    total_committed: int
    is_human: bool
    is_button: bool
    is_small_blind: bool
    is_big_blind: bool


class GameView(BaseModel):
    session_id: str
    hand_number: int
    hands_played: int
    target_hands: int  # 0 表示不限手数
    small_blind: int
    big_blind: int
    session_finished: bool
    hand_over: bool
    street: str
    board: list[str]
    pot: int
    button: int
    current_seat: int | None
    human_seat: int
    is_human_turn: bool
    players: list[PlayerView]
    legal_actions: LegalActionsView | None
    hand_actions: list[ActionRecord]
    showdown_hands: dict[str, ShowdownHand] | None = None
    pot_results: list[PotResult] | None = None
    winners: list[int]
    last_net: dict[int, int]
    last_hand_id: str | None = None


class SessionSummary(BaseModel):
    id: str
    created_at: str
    num_players: int
    big_blind: int
    target_hands: int
    hands_played: int
    status: str
    net_chips: int


class SessionStats(BaseModel):
    session_id: str
    status: str
    num_players: int
    big_blind: int
    target_hands: int
    hands_played: int
    net_chips: int
    wins: int
    losses: int
    ties: int


class HandSummary(BaseModel):
    id: str
    session_id: str
    hand_number: int
    created_at: str
    net: int
    winners: list[int]
    showdown: bool
    board: list[str]
    street: str


class HandDetail(BaseModel):
    id: str
    session_id: str
    hand_number: int
    created_at: str
    history: dict


class Mistake(BaseModel):
    """复盘中的单条错误标记。"""

    code: str
    severity: Literal["error", "warning", "info"]
    message: str


class ActionChoice(BaseModel):
    """复盘中的一次动作选择（真人实际动作或参考 Bot 动作）。"""

    action: Literal["fold", "check", "call", "bet", "raise"]
    amount: int


class ActionProbability(BaseModel):
    """复盘参考动作分布中的一项：动作、额度与概率。"""

    action: Literal["fold", "check", "call", "bet", "raise"]
    amount: int
    probability: float


class DecisionReview(BaseModel):
    """真人单个决策点的复盘结果。"""

    street: str
    board: list[str]
    pot: int
    to_call: int
    actual_call_amount: int
    is_short_all_in_call: bool
    opponents: int
    equity: float
    pot_odds: float | None
    call_ev: int | None
    action: ActionChoice
    bot_action: ActionChoice
    bot_distribution: list[ActionProbability] = Field(default_factory=list)
    mistakes: list[Mistake]


class HandReview(BaseModel):
    """单手复盘总览。

    参考契约由来源（``reference_strategy``）、版本（``reference_version`` /
    ``evaluation_version``）、覆盖范围（``reference_coverage``）与适用域/局限
    （``reference_scope`` / ``reference_limitations``）共同声明，既保证可追溯，
    也避免把参考当作求解器结论。
    """

    hand_id: str
    hand_number: int
    human_seat: int
    reference_strategy: str
    reference_version: int
    evaluation_version: int
    reference_coverage: str
    reference_scope: str
    reference_limitations: list[str]
    decisions: list[DecisionReview]
    mistake_count: int
