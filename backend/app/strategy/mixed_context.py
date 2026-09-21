"""新 Bot 的安全输入层：冻结的公开摘要、受控状态子类与一致性校验。

职责边界：
- 只承载「公开信息摘要」：四街固定数组、实际支付、公开行动计数与位置性小计；
- 摘要在每次成功行动后增量维护，不遍历整手历史，额外空间为 O(街数 × 人数)；
- 任何缺上下文、越界、支付对不上或牌面泄漏都显式失败，不静默退回其他策略；
- 不持有引擎、不读文件与网络、不产生随机、不做任何牌力判断。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.poker.cards import Card
from app.poker.state import GameState, PlayerState, Street

# 内部输入契约版本：只对新策略自身生效，不是 HTTP / 历史 / 训练记录 schema。
MIXED_CONTEXT_SCHEMA_VERSION = "mixed-context.v1"
# 摘要覆盖的四个街，顺序即数组顺序；摊牌不属于可行动街。
MIXED_SUMMARY_STREETS: tuple[Street, ...] = (
    Street.PREFLOP,
    Street.FLOP,
    Street.TURN,
    Street.RIVER,
)
# 逐座位公开动作计数顺序。
MIXED_SUMMARY_ACTIONS: tuple[str, ...] = ("fold", "check", "call", "bet", "raise")
# 逐座位计数饱和上限：只用于粗粒度风险特征，不需要精确次数。
MIXED_COUNT_SATURATION = 3

MIXED_MIN_PLAYERS = 2
MIXED_MAX_PLAYERS = 9

# 引擎记录的盲注与非盲注公开动作词表。
BLIND_TOKENS: tuple[str, str] = ("small_blind", "big_blind")
_AGGRESSIVE_TOKENS = frozenset({"bet", "raise"})
_PASSIVE_ZERO_TOKENS = frozenset({"fold", "check"})
_EXPECTED_BOARD_LENGTH = {
    Street.PREFLOP: 0,
    Street.FLOP: 3,
    Street.TURN: 4,
    Street.RIVER: 5,
}

# 严格整数：拒绝浮点、字符串与布尔等隐式转换，保证筹码口径只能是整数。
StrictInt = Annotated[int, Field(strict=True)]

_ACTION_INDEX = {token: index for index, token in enumerate(MIXED_SUMMARY_ACTIONS)}


class MixedContextError(ValueError):
    """新 Bot 输入不完整、越界或不自洽时抛出；不表示可以回退到别的策略。"""


class MixedStreetSummary(BaseModel):
    """单个街的公开摘要：逐座位动作计数、实际累计支付与位置性小计。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    street: Street
    # N × 5，按 MIXED_SUMMARY_ACTIONS 顺序，每项非负且饱和至 MIXED_COUNT_SATURATION。
    counts_by_seat: tuple[tuple[StrictInt, ...], ...]
    # N 项，本街各座位实际投入的筹码（含盲注），整数单位。
    paid_by_seat: tuple[StrictInt, ...]
    # 本街最后一次主动投入（bet/raise）的座位，无则为 None。
    last_aggressor: StrictInt | None = None
    # 第一次自愿加注前曾跟注的唯一座位（仅翻前有意义），严格升序。
    preopen_callers: tuple[StrictInt, ...] = ()

    @model_validator(mode="after")
    def _require_consistent_shape(self) -> MixedStreetSummary:
        if self.street not in MIXED_SUMMARY_STREETS:
            raise MixedContextError(f"摘要街只能是四个可行动街，收到 {self.street!r}")
        size = len(self.paid_by_seat)
        if size < MIXED_MIN_PLAYERS or size > MIXED_MAX_PLAYERS:
            raise MixedContextError(f"摘要人数 {size} 不在 2–9 内")
        if len(self.counts_by_seat) != size:
            raise MixedContextError("动作计数与支付数组的人数不一致")
        for per_seat in self.counts_by_seat:
            if len(per_seat) != len(MIXED_SUMMARY_ACTIONS):
                raise MixedContextError("逐座位动作计数必须恰好覆盖五种动作")
            for count in per_seat:
                if count < 0 or count > MIXED_COUNT_SATURATION:
                    raise MixedContextError("动作计数必须落在 0 到饱和上限之间")
        for paid in self.paid_by_seat:
            if paid < 0:
                raise MixedContextError("实际支付不能为负")
        if self.last_aggressor is not None and not 0 <= self.last_aggressor < size:
            raise MixedContextError("最后主动者座位越界")
        if self.street is not Street.PREFLOP and self.preopen_callers:
            raise MixedContextError("只有翻前摘要允许记录加注前跟注者")
        if list(self.preopen_callers) != sorted(set(self.preopen_callers)):
            raise MixedContextError("加注前跟注者必须是升序且不重复的座位")
        for seat in self.preopen_callers:
            if not 0 <= seat < size:
                raise MixedContextError("加注前跟注者座位越界")
        return self


class MixedContext(BaseModel):
    """行动者可用的公开上下文：四街摘要、名义盲注与 Bot 座位集合。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["mixed-context.v1"] = MIXED_CONTEXT_SCHEMA_VERSION
    # 正整数手号，来自运行态；不用 UUID、时钟或随机值充当牌理特征。
    hand_number: StrictInt
    # 本手已成功记录的公开事件数，含两条盲注；用作行动标识，不参与牌力分数。
    event_count: StrictInt
    small_blind: StrictInt
    big_blind: StrictInt
    # 严格升序、无重复的 Bot 座位元组。
    bot_seats: tuple[StrictInt, ...]
    # 恰好四个街摘要，按翻前/翻牌/转牌/河牌排列；未来街为零值。
    streets: tuple[MixedStreetSummary, ...]

    @model_validator(mode="after")
    def _require_consistent_hand(self) -> MixedContext:
        if self.hand_number < 1:
            raise MixedContextError("手号必须是正整数")
        if self.event_count < len(BLIND_TOKENS):
            raise MixedContextError("事件数至少包含两条盲注")
        if self.small_blind < 1:
            raise MixedContextError("小盲必须是正整数")
        if self.big_blind != 2 * self.small_blind:
            raise MixedContextError("大盲必须恰好是小盲的两倍")
        if len(self.streets) != len(MIXED_SUMMARY_STREETS):
            raise MixedContextError("摘要必须恰好包含四个街")
        for expected, summary in zip(MIXED_SUMMARY_STREETS, self.streets, strict=True):
            if summary.street is not expected:
                raise MixedContextError("摘要街顺序必须为翻前/翻牌/转牌/河牌")
        sizes = {len(summary.paid_by_seat) for summary in self.streets}
        if len(sizes) != 1:
            raise MixedContextError("四个街摘要的人数必须一致")
        size = sizes.pop()
        if list(self.bot_seats) != sorted(set(self.bot_seats)):
            raise MixedContextError("Bot 座位必须严格升序且不重复")
        for seat in self.bot_seats:
            if not 0 <= seat < size:
                raise MixedContextError("Bot 座位越界")
        return self

    @property
    def num_players(self) -> int:
        """本手人数，由摘要数组长度派生，不单独存储避免两处口径。"""
        return len(self.streets[0].paid_by_seat)


@dataclass(frozen=True)
class MixedGameState(GameState):
    """附加公开摘要的只读快照：唯一新增属性是 ``context``。

    只由本模块把已脱敏的投影与摘要组合而成；不得先附加再走旧投影，
    因为旧投影会重建基类并丢掉上下文。
    """

    context: MixedContext


@dataclass(frozen=True)
class VerifiedMixedInput:
    """通过全部一致性检查后的行动者输入。"""

    context: MixedContext
    actor: PlayerState
    actor_seat: int
    num_players: int
    board: tuple[Card, ...]
    street: Street
    button: int
    pot: int
    players: tuple[PlayerState, ...]

    @property
    def known_cards(self) -> tuple[Card, ...]:
        """行动者已知的牌（自己两张 + 公共牌），供特征层复用同一份校验结果。"""
        return (*self.actor.hole_cards, *self.board)


def mixed_state(state: GameState, context: MixedContext) -> MixedGameState:
    """把已脱敏的投影与公开摘要组合成新策略的输入状态。"""
    return MixedGameState(
        street=state.street,
        board=tuple(state.board),
        pot=state.pot,
        current_seat=state.current_seat,
        button=state.button,
        hand_over=state.hand_over,
        players=state.players,
        context=context,
    )


def require_mixed_input(state: GameState) -> VerifiedMixedInput:
    """校验新策略的全部输入前置条件；任一项不满足都显式失败。"""
    if not isinstance(state, MixedGameState):
        raise MixedContextError("运行态未附加公开摘要，拒绝以不完整信息决策")
    context = state.context

    if state.hand_over or state.street is Street.SHOWDOWN:
        raise MixedContextError("终局状态不应构造 Bot 决策")

    players = state.players
    size = len(players)
    if size != context.num_players:
        raise MixedContextError("快照人数与摘要人数不一致")
    if not MIXED_MIN_PLAYERS <= size <= MIXED_MAX_PLAYERS:
        raise MixedContextError(f"人数 {size} 超出受支持范围")
    if [p.seat for p in players] != list(range(size)):
        raise MixedContextError("座位必须唯一且连续")

    if not 0 <= state.current_seat < size:
        raise MixedContextError("当前行动者座位越界")
    actor = players[state.current_seat]
    if actor.folded or actor.all_in:
        raise MixedContextError("当前行动者已弃牌或已全下")

    expected_board = _EXPECTED_BOARD_LENGTH.get(state.street)
    if expected_board is None or len(state.board) != expected_board:
        raise MixedContextError("街与公共牌数量不匹配")

    if len(actor.hole_cards) != 2:
        raise MixedContextError("行动者必须恰好持有两张底牌")
    for player in players:
        if player.seat != actor.seat and player.hole_cards:
            raise MixedContextError("快照泄漏了其他座位的底牌")
        if player.total_committed < 0 or player.street_bet < 0 or player.stack < 0:
            raise MixedContextError("筹码与投入不能为负")

    known = [*actor.hole_cards, *state.board]
    if len(set(known)) != len(known):
        raise MixedContextError("已知牌出现重复")

    if sum(p.total_committed for p in players) != state.pot:
        raise MixedContextError("逐座位累计投入与底池不一致")
    for seat, player in enumerate(players):
        paid = sum(summary.paid_by_seat[seat] for summary in context.streets)
        if paid < 0:
            raise MixedContextError("摘要支付不能为负")
        if paid != player.total_committed:
            raise MixedContextError("摘要逐座位支付与快照累计投入不一致")

    return VerifiedMixedInput(
        context=context,
        actor=actor,
        actor_seat=actor.seat,
        num_players=size,
        board=tuple(state.board),
        street=state.street,
        button=state.button,
        pot=state.pot,
        players=players,
    )


class MixedSummaryTracker:
    """按手维护四街公开摘要：只增量消费新事件，不重放整手历史。"""

    def __init__(self) -> None:
        self._active = False
        self._hand_number = 0
        self._num_players = 0
        self._small_blind = 0
        self._big_blind = 0
        self._bot_seats: tuple[int, ...] = ()
        self._counts: list[list[list[int]]] = []
        self._paid: list[list[int]] = []
        self._last_aggressor: list[int | None] = []
        self._preopen_callers: list[set[int]] = []
        self._raise_seen: list[bool] = []
        self._consumed = 0

    @property
    def active(self) -> bool:
        """本手摘要是否已初始化。"""
        return self._active

    @property
    def hand_number(self) -> int:
        """当前摘要对应的手号；未初始化时为 0。"""
        return self._hand_number

    @property
    def consumed_events(self) -> int:
        """已消费的公开事件条数。"""
        return self._consumed

    def reset(self) -> None:
        """丢弃当前摘要；用于本手已结束或运行态被替换。"""
        self.__init__()

    def begin_hand(
        self,
        *,
        hand_number: int,
        num_players: int,
        small_blind: int,
        big_blind: int,
        bot_seats: Sequence[int],
        history: Sequence[dict[str, object]],
    ) -> None:
        """初始化本手摘要并消费恰好两条盲注记录。"""
        if not MIXED_MIN_PLAYERS <= num_players <= MIXED_MAX_PLAYERS:
            raise MixedContextError(f"人数 {num_players} 超出受支持范围")
        if small_blind < 1 or big_blind != 2 * small_blind:
            raise MixedContextError("名义盲注配置不满足大盲为小盲两倍")
        seats = tuple(bot_seats)
        if list(seats) != sorted(set(seats)) or any(not 0 <= s < num_players for s in seats):
            raise MixedContextError("Bot 座位必须升序、不重复且落在人数范围内")
        if len(history) != len(BLIND_TOKENS):
            raise MixedContextError("本手开头必须恰好是两条盲注记录")

        self._active = True
        self._hand_number = hand_number
        self._num_players = num_players
        self._small_blind = small_blind
        self._big_blind = big_blind
        self._bot_seats = seats
        width = len(MIXED_SUMMARY_ACTIONS)
        self._counts = [[[0] * width for _ in range(num_players)] for _ in MIXED_SUMMARY_STREETS]
        self._paid = [[0] * num_players for _ in MIXED_SUMMARY_STREETS]
        self._last_aggressor = [None] * len(MIXED_SUMMARY_STREETS)
        self._preopen_callers = [set() for _ in MIXED_SUMMARY_STREETS]
        self._raise_seen = [False] * len(MIXED_SUMMARY_STREETS)
        self._consumed = 0

        for expected_token, record in zip(BLIND_TOKENS, history, strict=True):
            if record.get("action") != expected_token:
                raise MixedContextError("本手开头两条记录必须依次是小盲与大盲")
            self._consume_amount_only(record)
            self._consumed += 1

    def consume_after_action(self, history: Sequence[dict[str, object]]) -> None:
        """在 ``apply_action`` 成功后消费恰好一条新公开事件。"""
        if not self._active:
            raise MixedContextError("摘要未初始化即收到新动作")
        appended = len(history) - self._consumed
        if appended != 1:
            raise MixedContextError(f"一次成功行动应追加一条公开事件，实际 {appended}")
        self._consume_voluntary(history[-1])
        self._consumed += 1

    def context(self) -> MixedContext:
        """把增量数组导出为冻结上下文；未初始化时失败。"""
        if not self._active:
            raise MixedContextError("摘要尚未初始化，无法导出上下文")
        summaries = tuple(
            MixedStreetSummary(
                street=street,
                counts_by_seat=tuple(
                    tuple(self._counts[index][seat]) for seat in range(self._num_players)
                ),
                paid_by_seat=tuple(self._paid[index]),
                last_aggressor=self._last_aggressor[index],
                preopen_callers=(
                    tuple(sorted(self._preopen_callers[index]))
                    if street is Street.PREFLOP
                    else ()
                ),
            )
            for index, street in enumerate(MIXED_SUMMARY_STREETS)
        )
        return MixedContext(
            hand_number=self._hand_number,
            event_count=self._consumed,
            small_blind=self._small_blind,
            big_blind=self._big_blind,
            bot_seats=self._bot_seats,
            streets=summaries,
        )

    # ------------------------------------------------------------------ 内部

    def _consume_amount_only(self, record: dict[str, object]) -> None:
        """盲注只计入实际支付，不计为自愿动作。"""
        street_index = self._street_index(record)
        seat = self._seat_index(record)
        self._paid[street_index][seat] += self._amount(record)

    def _consume_voluntary(self, record: dict[str, object]) -> None:
        """普通行动同时更新计数、支付与位置性小计。"""
        street_index = self._street_index(record)
        seat = self._seat_index(record)
        token = record.get("action")
        if not isinstance(token, str) or token not in _ACTION_INDEX:
            raise MixedContextError(f"公开行动词表外的动作：{token!r}")
        amount = self._amount(record)
        if token in _PASSIVE_ZERO_TOKENS and amount != 0:
            raise MixedContextError(f"{token} 的记录金额必须为 0")

        counts = self._counts[street_index][seat]
        counts[_ACTION_INDEX[token]] = min(MIXED_COUNT_SATURATION, counts[_ACTION_INDEX[token]] + 1)
        self._paid[street_index][seat] += amount

        if token in _AGGRESSIVE_TOKENS:
            self._last_aggressor[street_index] = seat
            self._raise_seen[street_index] = True
        elif token == "call" and not self._raise_seen[street_index]:
            self._preopen_callers[street_index].add(seat)

    def _street_index(self, record: dict[str, object]) -> int:
        token = record.get("street")
        if not isinstance(token, str):
            raise MixedContextError("公开事件的街标识缺失或非法")
        for index, street in enumerate(MIXED_SUMMARY_STREETS):
            if street.name.lower() == token:
                return index
        raise MixedContextError(f"公开事件落在非可行动街：{token}")

    def _seat_index(self, record: dict[str, object]) -> int:
        seat = record.get("seat")
        if not isinstance(seat, int) or isinstance(seat, bool):
            raise MixedContextError("公开事件的座位标识必须为整数")
        if not 0 <= seat < self._num_players:
            raise MixedContextError("公开事件的座位越界")
        return seat

    def _amount(self, record: dict[str, object]) -> int:
        amount = record.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise MixedContextError("公开事件的金额必须为整数")
        if amount < 0:
            raise MixedContextError("公开事件的金额不能为负")
        return amount
