"""Kuhn poker 的固定规则与信息集。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class KuhnRuleError(ValueError):
    """输入不符合 Kuhn 规则时抛出。"""


class Player(IntEnum):
    P0 = 0
    P1 = 1


class Card(StrEnum):
    JACK = "J"
    QUEEN = "Q"
    KING = "K"

    @property
    def rank(self) -> int:
        return CARD_ORDER.index(self)


class Action(StrEnum):
    CHECK = "x"
    BET = "b"
    CALL = "c"
    FOLD = "f"


CARD_ORDER = (Card.JACK, Card.QUEEN, Card.KING)
TERMINAL_HISTORIES = frozenset({"xx", "bf", "bc", "xbf", "xbc"})
LEGAL_ACTIONS: dict[str, tuple[Action, ...]] = {
    "": (Action.CHECK, Action.BET),
    "x": (Action.CHECK, Action.BET),
    "b": (Action.FOLD, Action.CALL),
    "xb": (Action.FOLD, Action.CALL),
}


@dataclass(frozen=True)
class Deal:
    p0_card: Card
    p1_card: Card

    def __post_init__(self) -> None:
        if self.p0_card is self.p1_card:
            raise KuhnRuleError("两名玩家不能持有同一张 Kuhn 暗牌")

    def card_for(self, player: Player) -> Card:
        return self.p0_card if player is Player.P0 else self.p1_card


@dataclass(frozen=True)
class InfoSetSpec:
    player: Player
    card: Card
    history: str
    actions: tuple[Action, ...]

    @property
    def key(self) -> str:
        history = self.history or "-"
        return f"p{int(self.player)}:{self.card.value}:{history}"


DEALS = tuple(
    Deal(p0_card, p1_card)
    for p0_card in CARD_ORDER
    for p1_card in CARD_ORDER
    if p0_card is not p1_card
)


def is_terminal(history: str) -> bool:
    return history in TERMINAL_HISTORIES


def acting_player(history: str) -> Player:
    if history == "":
        return Player.P0
    if history in {"x", "b"}:
        return Player.P1
    if history == "xb":
        return Player.P0
    if history in TERMINAL_HISTORIES:
        raise KuhnRuleError("终局历史不存在行动者")
    raise KuhnRuleError(f"未知 Kuhn 历史：{history!r}")


def legal_actions(history: str) -> tuple[Action, ...]:
    try:
        return LEGAL_ACTIONS[history]
    except KeyError as error:
        if history in TERMINAL_HISTORIES:
            raise KuhnRuleError("终局历史没有合法动作") from error
        raise KuhnRuleError(f"未知 Kuhn 历史：{history!r}") from error


def apply_action(history: str, action: Action) -> str:
    try:
        parsed_action = action if isinstance(action, Action) else Action(action)
    except ValueError as error:
        raise KuhnRuleError(f"未知 Kuhn 动作：{action!r}") from error
    if parsed_action not in legal_actions(history):
        raise KuhnRuleError(f"动作 {parsed_action.value!r} 不适用于历史 {history!r}")
    return history + parsed_action.value


def terminal_utility_p0(deal: Deal, history: str) -> int:
    if history not in TERMINAL_HISTORIES:
        raise KuhnRuleError(f"历史 {history!r} 不是终局")
    if history == "bf":
        return 1
    if history == "xbf":
        return -1

    winner_is_p0 = deal.p0_card.rank > deal.p1_card.rank
    stake = 1 if history == "xx" else 2
    return stake if winner_is_p0 else -stake


def information_set_key(player: Player, card: Card, history: str) -> str:
    if not isinstance(player, Player):
        raise KuhnRuleError(f"未知玩家：{player!r}")
    if not isinstance(card, Card):
        raise KuhnRuleError(f"未知 Kuhn 暗牌：{card!r}")
    if acting_player(history) is not player:
        raise KuhnRuleError("信息集行动者与公开历史不一致")
    return InfoSetSpec(player, card, history, legal_actions(history)).key


def _build_infosets() -> tuple[InfoSetSpec, ...]:
    specs: list[InfoSetSpec] = []
    for player, histories in (
        (Player.P0, ("", "xb")),
        (Player.P1, ("x", "b")),
    ):
        for card in CARD_ORDER:
            for history in histories:
                specs.append(InfoSetSpec(player, card, history, legal_actions(history)))
    return tuple(specs)


INFOSETS = _build_infosets()
INFOSET_BY_KEY = {spec.key: spec for spec in INFOSETS}
