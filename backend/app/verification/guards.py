"""注入前硬失败校验：引擎的注入路径本身不校验，故由运行器在调用之前逐项检查。

设计目的：
- 逐项检查座位覆盖、每座底牌张数、公共牌张数、总牌数与全局唯一、牌对象类型与牌面范围、
  庄位范围，以及两侧发牌材料逐项相同；
- 任一不满足即硬失败并终止本次运行：不回退到随机开手，不修补，也不重取材料。
"""

from __future__ import annotations

from collections.abc import Mapping

from app.poker.cards import Card

from .deal import BOARD_SIZE, HOLE_CARDS_PER_SEAT, HandDeal, card_universe
from .digests import content_digest
from .errors import InjectionPrecheckError

# 校验项名：元组顺序即检查顺序，静态检查与执行身份记录都读这张表。
PRECHECK_ITEMS: tuple[str, ...] = (
    "hole_card_seats_complete",
    "hole_cards_per_seat",
    "board_size",
    "card_total_and_uniqueness",
    "card_type_and_universe",
    "button_in_range",
    "both_arms_same_deal",
)


def precheck_rule_entries() -> tuple[tuple[str, str], ...]:
    """把校验项整理成记录条目，顺序与检查顺序一致。

    覆盖清单不再使用这些旧名称，只保留给仍按项名阅读检查顺序的调用方。
    """
    return tuple((f"item-{index + 1}", name) for index, name in enumerate(PRECHECK_ITEMS))


def injection_precheck_rules_digest(algorithm: str) -> str:
    """对校验项名称数组取摘要，不加包装对象。"""
    return content_digest(list(PRECHECK_ITEMS), algorithm=algorithm)


def injection_precheck_category_entries(algorithm: str) -> tuple[tuple[str, str], ...]:
    """注入前类别的封闭条目：版本与规则摘要。"""
    return (
        ("injection-precheck-version", "1"),
        ("injection-precheck-rules-digest", injection_precheck_rules_digest(algorithm)),
    )


def _fail(item: str, detail: str) -> None:
    raise InjectionPrecheckError(item, detail)


def precheck_injection(
    deal: HandDeal,
    *,
    num_players: int,
    button: int,
    counterpart: HandDeal,
) -> None:
    """逐项执行注入前硬失败校验；任一项不满足即失败并终止本次运行。"""
    item = PRECHECK_ITEMS[0]
    if set(deal.hole_cards) != set(range(num_players)):
        _fail(item, "底牌映射的座位集合必须恰好覆盖全部座位")
    item = PRECHECK_ITEMS[1]
    for seat, cards in deal.hole_cards.items():
        if len(cards) != HOLE_CARDS_PER_SEAT:
            _fail(item, f"座位 {seat} 的底牌张数不是 {HOLE_CARDS_PER_SEAT}")
    item = PRECHECK_ITEMS[2]
    if len(deal.board) != BOARD_SIZE:
        _fail(item, f"公共牌张数不是 {BOARD_SIZE}")
    item = PRECHECK_ITEMS[3]
    cards = [card for seat_cards in deal.hole_cards.values() for card in seat_cards]
    total = len(cards) + len(deal.board)
    if total != HOLE_CARDS_PER_SEAT * num_players + BOARD_SIZE:
        _fail(item, "总牌数与人数不匹配")
    if len(set(cards) | set(deal.board)) != total:
        _fail(item, "底牌与公共牌之间出现了重复牌面")
    item = PRECHECK_ITEMS[4]
    universe = card_universe()
    for card in [*cards, *deal.board]:
        if not isinstance(card, Card):
            _fail(item, "牌对象类型不符")
        if card not in universe:
            _fail(item, f"牌面不在完整一副牌范围内：{card!r}")
    item = PRECHECK_ITEMS[5]
    if isinstance(button, bool) or not isinstance(button, int):
        _fail(item, "庄位必须是整数")
    if not 0 <= button < num_players:
        _fail(item, "庄位必须落在人数范围内")
    item = PRECHECK_ITEMS[6]
    if deal.hole_cards != counterpart.hole_cards or deal.board != counterpart.board:
        _fail(item, "两侧注入的发牌材料必须逐项相同")


def same_deal(left: HandDeal, right: HandDeal) -> bool:
    """判断两份发牌材料是否逐项相同，供调用方在注入前自检。"""
    return left.hole_cards == right.hole_cards and left.board == right.board


def require_same_deal(left: HandDeal, right: HandDeal) -> None:
    """要求两侧发牌材料逐项相同；不相同即硬失败。"""
    if not same_deal(left, right):
        _fail(PRECHECK_ITEMS[6], "两侧注入的发牌材料必须逐项相同")


def deal_seat_mapping(deal: HandDeal) -> Mapping[int, tuple[Card, ...]]:
    """按座位号升序返回底牌映射，供注入前构造引擎入参。"""
    return dict(sorted(deal.hole_cards.items()))
