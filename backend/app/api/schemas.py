"""对外 API 的 Pydantic 请求/响应模型。"""

from typing import Literal

from pydantic import BaseModel, Field


class CreateGameRequest(BaseModel):
    """创建对局的请求。num_players 可大于 2（引擎按 N 人设计，MVP 界面默认 2）。"""

    num_players: int = Field(default=2, ge=2, le=10)
    target_hands: int = Field(default=50, ge=1, le=10000)
    small_blind: int = Field(default=5, ge=1)
    big_blind: int = Field(default=10, ge=1)
    starting_stack: int = Field(default=1000, ge=1)
    bot_strategy: Literal["heuristic", "random"] = "heuristic"
    seed: int | None = None


class SubmitActionRequest(BaseModel):
    """提交动作的请求；bet/raise 需要金额，其余忽略。"""

    action: Literal["fold", "check", "call", "bet", "raise"]
    amount: int | None = Field(default=None, ge=0)


class LegalActionsView(BaseModel):
    can_fold: bool
    can_check: bool
    can_call: bool
    call_amount: int
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
    target_hands: int
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
