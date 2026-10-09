"""发牌映射：把不放回抽取的均匀整数序列还原成各座位底牌与公共牌。

设计目的：
- 牌的规范序由调用方显式给定，本模块只校验收到的顺序确实是完整一副牌的排列；
- 抽取与分配都是确定函数：同一组整数必得同一手牌，不引入随机，也不读取任何外部状态；
- 映射不改变牌局规则，注入路径仍由引擎既有接口承担。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, model_validator

from app.poker.cards import Card, Rank, Suit, card_from_str

from .digests import content_digest
from .errors import DealMaterialError

# 一副牌的张数、每座位底牌张数与公共牌张数；三者共同决定一手牌所需的抽取次数。
DECK_SIZE = 52
HOLE_CARDS_PER_SEAT = 2
BOARD_SIZE = 5


def card_universe() -> frozenset[Card]:
    """完整一副牌的规范牌集合，用于校验牌对象是否落在牌面范围内。"""
    return frozenset(Card(rank, suit) for suit in Suit for rank in Rank)


class DealMappingSpec(BaseModel):
    """发牌映射规格：牌规范序由调用方显式给定。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    deck_order: tuple[str, ...]

    @model_validator(mode="after")
    def _require_full_deck(self) -> DealMappingSpec:
        if len(self.deck_order) != DECK_SIZE:
            raise DealMaterialError("牌规范序必须恰好包含一副牌的张数")
        cards = self.parsed_cards()
        if len(set(cards)) != DECK_SIZE:
            raise DealMaterialError("牌规范序不得出现重复牌面")
        return self

    def parsed_cards(self) -> tuple[Card, ...]:
        """把牌面表示解析成牌对象；表示非法即失败。"""
        cards: list[Card] = []
        for token in self.deck_order:
            try:
                cards.append(card_from_str(token))
            except (KeyError, ValueError) as error:
                raise DealMaterialError(f"牌面表示非法：{token!r}") from error
        return tuple(cards)

    def draw_count(self, num_players: int) -> int:
        """一手牌所需的抽取次数：各座位底牌与公共牌之和。"""
        _require_player_count(num_players)
        return HOLE_CARDS_PER_SEAT * num_players + BOARD_SIZE


@dataclass(frozen=True)
class HandDeal:
    """一手牌的发牌材料：逐座位底牌与按发牌顺序排列的公共牌。"""

    hole_cards: Mapping[int, tuple[Card, ...]]
    board: tuple[Card, ...]


def _require_player_count(num_players: int) -> None:
    if (
        isinstance(num_players, bool)
        or not isinstance(num_players, int)
        or not 2 <= num_players <= 23
    ):
        raise DealMaterialError("人数必须是 2 到 23 的整数")


def draw_order(spec: DealMappingSpec, steps: Sequence[int]) -> tuple[Card, ...]:
    """按不放回抽取的整数序列取出牌面，得到确定顺序的牌序列。

    第 k 次抽取从剩余范围中取一个下标：把第 k 张与第 k + 取值 张互换，输出互换后的第 k 张。
    因此第 k 次的取值必须严格小于剩余张数，越界即失败。
    """
    cards = list(spec.parsed_cards())
    drawn: list[Card] = []
    for index, step in enumerate(steps):
        remaining = len(cards) - index
        if isinstance(step, bool) or not isinstance(step, int):
            raise DealMaterialError("抽取取值必须是整数")
        if not 0 <= step < remaining:
            raise DealMaterialError(f"第 {index} 次抽取的取值超出剩余范围")
        target = index + step
        cards[index], cards[target] = cards[target], cards[index]
        drawn.append(cards[index])
    return tuple(drawn)


def deal_for_hand(
    spec: DealMappingSpec, *, num_players: int, steps: Sequence[int]
) -> HandDeal:
    """把抽取序列分配到各座位底牌与公共牌。

    分配规则为固定函数：按座位号升序，每个座位取连续两张；其后五张依次为翻牌三张、
    转牌与河牌，顺序与引擎注入路径要求的发牌顺序一致。
    """
    required = spec.draw_count(num_players)
    if len(steps) != required:
        raise DealMaterialError(f"一手牌需要的抽取次数为 {required}，实际为 {len(steps)}")
    drawn = draw_order(spec, steps)
    hole_cards = {
        seat: (drawn[HOLE_CARDS_PER_SEAT * seat], drawn[HOLE_CARDS_PER_SEAT * seat + 1])
        for seat in range(num_players)
    }
    return HandDeal(
        hole_cards=hole_cards,
        board=drawn[HOLE_CARDS_PER_SEAT * num_players :],
    )


# 发牌映射摘要的封闭牌序：规范位置 0…51，与映射载荷一起重算，不读取调用方牌序。
_LOCKED_DECK_ORDER: tuple[str, ...] = (
    "2c", "3c", "4c", "5c", "6c", "7c", "8c", "9c", "Tc", "Jc", "Qc", "Kc", "Ac",
    "2d", "3d", "4d", "5d", "6d", "7d", "8d", "9d", "Td", "Jd", "Qd", "Kd", "Ad",
    "2h", "3h", "4h", "5h", "6h", "7h", "8h", "9h", "Th", "Jh", "Qh", "Kh", "Ah",
    "2s", "3s", "4s", "5s", "6s", "7s", "8s", "9s", "Ts", "Js", "Qs", "Ks", "As",
)


def deal_mapping_payload() -> dict[str, object]:
    """发牌映射的封闭载荷：牌序、人数边界与分配规则，不含某次运行的实际人数。"""
    return {
        "schema": "deal-mapping-v1",
        "deck_order": list(_LOCKED_DECK_ORDER),
        "player_count_min": 2,
        "player_count_max": 23,
        "deck_size": DECK_SIZE,
        "hole_cards_per_seat": HOLE_CARDS_PER_SEAT,
        "board_size": BOARD_SIZE,
        "draw_rule": "swap-without-replacement-v1",
        "hole_card_allocation": "seat-ascending-consecutive-v1",
        "board_order": ["flop", "flop", "flop", "turn", "river"],
    }


def deal_mapping_digest(*, algorithm: str) -> str:
    """按封闭载荷重算发牌映射摘要。"""
    return content_digest(deal_mapping_payload(), algorithm=algorithm)
