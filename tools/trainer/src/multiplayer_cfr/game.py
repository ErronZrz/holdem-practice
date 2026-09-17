"""候选 A 的多人唯一 rank 单次开池规则与公开信息契约。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from math import factorial
from types import MappingProxyType

ALLOWED_PLAYER_COUNTS = frozenset({6, 7, 9})
ROOT_HISTORY = "-"
GAME_ID = "m8-unique-rank-single-open"
GAME_VERSION = "m8-a-v1"
ANTE = 1
BET = 1


class CandidateARuleError(ValueError):
    """候选 A 的输入不符合受限规则时抛出。"""


class Action(StrEnum):
    CHECK = "x"
    BET = "b"
    CALL = "c"
    FOLD = "f"


@dataclass(frozen=True)
class GameConfig:
    """固定人数和筹码单位，禁止混入生产牌局状态。"""

    player_count: int

    def __post_init__(self) -> None:
        validate_player_count(self.player_count)

    @property
    def ranks(self) -> tuple[int, ...]:
        return tuple(range(self.player_count))

    @property
    def ordered_deal_count(self) -> int:
        return factorial(self.player_count)


def validate_player_count(player_count: int) -> int:
    if (
        isinstance(player_count, bool)
        or not isinstance(player_count, int)
        or player_count not in ALLOWED_PLAYER_COUNTS
    ):
        raise CandidateARuleError("候选 A 仅支持 6、7 或 9 名相对座位")
    return player_count


def _require_rank(player_count: int, rank: int) -> int:
    if isinstance(rank, bool) or not isinstance(rank, int) or not 0 <= rank < player_count:
        raise CandidateARuleError("私有 rank 必须位于该人数的唯一牌组中")
    return rank


def _require_actor(player_count: int, actor: int) -> int:
    if isinstance(actor, bool) or not isinstance(actor, int) or not 0 <= actor < player_count:
        raise CandidateARuleError("相对行动者不在候选 A 的座位范围内")
    return actor


def _parse_action(value: Action | str) -> Action:
    try:
        if not isinstance(value, (Action, str)):
            raise ValueError
        return Action(value)
    except ValueError as error:
        raise CandidateARuleError(f"未知候选 A 动作：{value!r}") from error


@dataclass(frozen=True)
class PublicState:
    """由规范历史唯一派生的公开状态，不能由调用方分别注入。"""

    player_count: int
    history: str
    actor: int | None
    opener: int | None
    folded: frozenset[int]
    active: frozenset[int]
    contributions: tuple[int, ...]
    pending_responders: tuple[int, ...]
    terminal: bool

    def projection(self) -> dict[str, object]:
        """返回 JSON 可表示的、可由历史复核的公开投影。"""

        return {
            "actor": self.actor,
            "opener": self.opener,
            "folded": sorted(self.folded),
            "active": sorted(self.active),
            "contributions": list(self.contributions),
            "pending_responders": list(self.pending_responders),
            "terminal": self.terminal,
        }


def _parse_token(token: str, expected_actor: int) -> Action:
    if not isinstance(token, str):
        raise CandidateARuleError("公开历史 token 必须是字符串")
    action_text, separator, seat_text = token.partition("@")
    if separator != "@" or "@" in seat_text:
        raise CandidateARuleError("公开历史必须使用 action@relative-seat 形式")
    action = _parse_action(action_text)
    if token != f"{action.value}@{expected_actor}" or seat_text != str(expected_actor):
        raise CandidateARuleError("公开历史的行动者或 token 形式不规范")
    return action


def derive_public_state(player_count: int, history: str) -> PublicState:
    """只从规范公开历史派生行动、投入、弃牌和待回应顺序。"""

    player_count = validate_player_count(player_count)
    if not isinstance(history, str):
        raise CandidateARuleError("公开历史必须是字符串")
    if history == ROOT_HISTORY:
        tokens: tuple[str, ...] = ()
    elif not history or history.startswith("|") or history.endswith("|") or "||" in history:
        raise CandidateARuleError("公开历史不是规范形式")
    else:
        tokens = tuple(history.split("|"))

    opening_index = 0
    opener: int | None = None
    response_order: tuple[int, ...] = ()
    response_index = 0
    folded: set[int] = set()
    contributions = [ANTE for _ in range(player_count)]

    for token in tokens:
        if opener is None:
            if opening_index == player_count:
                raise CandidateARuleError("全员 check 的终局后不能继续行动")
            actor = opening_index
            action = _parse_token(token, actor)
            if action not in (Action.CHECK, Action.BET):
                raise CandidateARuleError("无下注阶段只允许 check 或固定开池")
            if action is Action.CHECK:
                opening_index += 1
            else:
                opener = actor
                contributions[actor] += BET
                response_order = tuple(
                    (opener + offset) % player_count for offset in range(1, player_count)
                )
        else:
            if response_index == len(response_order):
                raise CandidateARuleError("所有回应完成后不能继续行动")
            actor = response_order[response_index]
            action = _parse_token(token, actor)
            if action not in (Action.CALL, Action.FOLD):
                raise CandidateARuleError("固定开池后只允许 call 或 fold")
            if action is Action.CALL:
                contributions[actor] += BET
            else:
                folded.add(actor)
            response_index += 1

    if opener is None:
        terminal = opening_index == player_count
        actor = None if terminal else opening_index
        pending_responders: tuple[int, ...] = ()
    else:
        terminal = response_index == len(response_order)
        actor = None if terminal else response_order[response_index]
        pending_responders = () if terminal else response_order[response_index:]

    return PublicState(
        player_count=player_count,
        history=ROOT_HISTORY if not tokens else "|".join(tokens),
        actor=actor,
        opener=opener,
        folded=frozenset(folded),
        active=frozenset(set(range(player_count)) - folded),
        contributions=tuple(contributions),
        pending_responders=pending_responders,
        terminal=terminal,
    )


def canonical_history(player_count: int, history: str) -> str:
    """校验并返回唯一的规范公开历史表示。"""

    return derive_public_state(player_count, history).history


def is_terminal(player_count: int, history: str) -> bool:
    return derive_public_state(player_count, history).terminal


def acting_player(player_count: int, history: str) -> int:
    actor = derive_public_state(player_count, history).actor
    if actor is None:
        raise CandidateARuleError("终局历史不存在行动者")
    return actor


def legal_actions(player_count: int, history: str) -> tuple[Action, ...]:
    state = derive_public_state(player_count, history)
    if state.terminal:
        raise CandidateARuleError("终局历史没有合法动作")
    if state.opener is None:
        return (Action.CHECK, Action.BET)
    return (Action.CALL, Action.FOLD)


def apply_action(player_count: int, history: str, action: Action | str) -> str:
    """在当前规范历史上应用一个合法动作并返回下一个规范历史。"""

    state = derive_public_state(player_count, history)
    parsed_action = _parse_action(action)
    if parsed_action not in legal_actions(player_count, state.history):
        raise CandidateARuleError(f"动作 {parsed_action.value!r} 不适用于当前公开历史")
    if state.actor is None:
        raise CandidateARuleError("终局历史不能继续行动")
    token = f"{parsed_action.value}@{state.actor}"
    return token if state.history == ROOT_HISTORY else f"{state.history}|{token}"


@dataclass(frozen=True)
class Deal:
    """完整 chance 结果仅供终局结算，不能传入信息集或 lookup。"""

    ranks: tuple[int, ...]

    def __post_init__(self) -> None:
        player_count = validate_player_count(len(self.ranks))
        if any(isinstance(rank, bool) or not isinstance(rank, int) for rank in self.ranks):
            raise CandidateARuleError("chance deal 的 rank 必须是整数")
        if set(self.ranks) != set(range(player_count)):
            raise CandidateARuleError("chance deal 必须恰好发出每个唯一 rank 一次")

    @property
    def player_count(self) -> int:
        return len(self.ranks)

    def rank_for(self, actor: int) -> int:
        return self.ranks[_require_actor(self.player_count, actor)]


@dataclass(frozen=True)
class TerminalOutcome:
    """候选 A 终局的整数投入、派彩和净收益。"""

    winner: int
    pot: int
    contributions: tuple[int, ...]
    payouts: tuple[int, ...]
    utilities: tuple[int, ...]


def terminal_outcome(player_count: int, deal: Deal, history: str) -> TerminalOutcome:
    """按唯一最高 rank 或唯一存活开池者结算一个已完成的公开历史。"""

    player_count = validate_player_count(player_count)
    if deal.player_count != player_count:
        raise CandidateARuleError("deal 的人数与公开历史人数不一致")
    state = derive_public_state(player_count, history)
    if not state.terminal:
        raise CandidateARuleError("仅终局历史可以结算")

    active = tuple(sorted(state.active))
    if state.opener is not None and active == (state.opener,):
        winner = state.opener
    else:
        winner = max(active, key=deal.rank_for)

    pot = sum(state.contributions)
    payouts = tuple(pot if seat == winner else 0 for seat in range(player_count))
    utilities = tuple(
        payout - contribution
        for payout, contribution in zip(payouts, state.contributions, strict=True)
    )
    if sum(payouts) != pot or sum(utilities) != 0:
        raise CandidateARuleError("候选 A 的整数筹码守恒被破坏")
    return TerminalOutcome(
        winner=winner,
        pot=pot,
        contributions=state.contributions,
        payouts=payouts,
        utilities=utilities,
    )


@dataclass(frozen=True)
class InfoSetSpec:
    """只包含行动者可见私有 rank 与规范公开历史的信息集。"""

    player_count: int
    actor: int
    rank: int
    history: str
    actions: tuple[Action, ...]
    public_state: PublicState

    @property
    def key(self) -> str:
        return information_set_key(self.player_count, self.actor, self.rank, self.history)


def information_set_key(player_count: int, actor: int, own_rank: int, history: str) -> str:
    """建立不携带其他私牌、未来结果或训练随机状态的规范信息集键。"""

    player_count = validate_player_count(player_count)
    actor = _require_actor(player_count, actor)
    own_rank = _require_rank(player_count, own_rank)
    state = derive_public_state(player_count, history)
    if state.actor != actor:
        raise CandidateARuleError("信息集行动者与规范公开历史不一致")
    return (
        f"m8/{GAME_VERSION}/n={player_count}/actor={actor}/rank={own_rank}/history={state.history}"
    )


@cache
def _decision_histories(player_count: int) -> tuple[str, ...]:
    validate_player_count(player_count)
    pending = [ROOT_HISTORY]
    histories: list[str] = []
    while pending:
        history = pending.pop(0)
        if is_terminal(player_count, history):
            continue
        histories.append(history)
        pending.extend(
            apply_action(player_count, history, action)
            for action in legal_actions(player_count, history)
        )
    return tuple(histories)


def decision_histories(player_count: int) -> tuple[str, ...]:
    """返回按固定顺序枚举的全部公开决策历史。"""

    return _decision_histories(validate_player_count(player_count))


@cache
def _infosets(player_count: int) -> tuple[InfoSetSpec, ...]:
    player_count = validate_player_count(player_count)
    specs: list[InfoSetSpec] = []
    for history in decision_histories(player_count):
        state = derive_public_state(player_count, history)
        if state.actor is None:
            raise CandidateARuleError("决策历史不能是终局")
        actions = legal_actions(player_count, history)
        for rank in range(player_count):
            specs.append(
                InfoSetSpec(
                    player_count=player_count,
                    actor=state.actor,
                    rank=rank,
                    history=history,
                    actions=actions,
                    public_state=state,
                )
            )
    return tuple(specs)


def infosets(player_count: int) -> tuple[InfoSetSpec, ...]:
    """返回该人数下完整、可达且不含私牌泄漏的信息集。"""

    return _infosets(validate_player_count(player_count))


@cache
def _infoset_by_key(player_count: int) -> Mapping[str, InfoSetSpec]:
    return MappingProxyType({spec.key: spec for spec in infosets(player_count)})


def infoset_by_key(player_count: int) -> Mapping[str, InfoSetSpec]:
    return _infoset_by_key(validate_player_count(player_count))


@dataclass(frozen=True)
class StructureCounts:
    """规则树与 chance 的静态结构计数，不代表训练或资源测量。"""

    player_count: int
    ordered_deals: int
    public_decision_histories: int
    infosets: int
    terminal_histories: int


def structure_counts(player_count: int) -> StructureCounts:
    """按候选 A 的闭式规则返回结构计数。"""

    player_count = validate_player_count(player_count)
    public_decision_histories = player_count * (2 ** (player_count - 1))
    return StructureCounts(
        player_count=player_count,
        ordered_deals=factorial(player_count),
        public_decision_histories=public_decision_histories,
        infosets=player_count * public_decision_histories,
        terminal_histories=1 + public_decision_histories,
    )
