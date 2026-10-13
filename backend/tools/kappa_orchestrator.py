"""包外编排：决策前编码公开投影，再查已经生成的材料。

对局推进只发生在本模块。查表未命中即停止。本模块没有补料或回呼生成器的参数。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.poker.actions import Action, LegalActions
from app.poker.engine import PokerEngine
from app.poker.k2_public_projection import sigma_public_hex
from app.poker.state import GameState
from app.strategy.registry import create_strategy

_BASELINE = "heuristic@1"


class KappaMaterialMiss(Exception):
    """已生成材料中没有这次决策需要的键。"""


@dataclass(frozen=True)
class MaterialTable:
    """生成结束后的材料表。只供查表，不能再追加键。"""

    rows: tuple[tuple[str, tuple[str, ...], int], ...]

    def __post_init__(self) -> None:
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for label, key, value in self.rows:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise KappaMaterialMiss("材料取值必须是非负整数")
            if label != "deal" and value >= 1 << 256:
                raise KappaMaterialMiss("种子必须落在 [0, 2^256)")
            location = (label, key)
            if location in seen:
                raise KappaMaterialMiss("材料表出现重复键")
            seen.add(location)

    def require(self, label: str, key: tuple[str, ...]) -> int:
        """命中则返回整数。未命中即失败，不触发任何读取。"""
        found = [
            value
            for item_label, item_key, value in self.rows
            if item_label == label and item_key == key
        ]
        if len(found) != 1:
            raise KappaMaterialMiss("已生成材料中没有该键")
        return found[0]


def material_table_from_rows(
    rows: Sequence[tuple[str, tuple[str, ...], int]],
) -> MaterialTable:
    """收成不可变查表。调用方必须已经持有生成结果。"""
    return MaterialTable(rows=tuple(rows))


def play_hand(
    engine: PokerEngine,
    table: MaterialTable,
    *,
    campaign: str,
    block: int,
    hand_ordinal: int,
    probed_seat: int,
    arm: str,
    under_test_choose: Callable[[GameState, LegalActions, int], Action] | None = None,
) -> None:
    """推进一手牌。每次决策新建基线实例；缺键时不提交动作。"""
    if arm not in ("baseline", "under-test"):
        raise KappaMaterialMiss("臂必须是基线或被测")
    next_index: dict[int, int] = {}
    while not engine.hand_over:
        state = engine.snapshot()
        legal = engine.legal_actions()
        seat = state.current_seat
        event_index = next_index.get(seat, 0)
        action = _action_for_decision(
            table,
            state,
            legal,
            campaign=campaign,
            block=block,
            hand_ordinal=hand_ordinal,
            probed_seat=probed_seat,
            arm=arm,
            event_index=event_index,
            under_test_choose=under_test_choose,
        )
        engine.apply_action(action)
        next_index[seat] = event_index + 1


def _action_for_decision(
    table: MaterialTable,
    state: GameState,
    legal: LegalActions,
    *,
    campaign: str,
    block: int,
    hand_ordinal: int,
    probed_seat: int,
    arm: str,
    event_index: int,
    under_test_choose: Callable[[GameState, LegalActions, int], Action] | None,
) -> Action:
    if arm == "under-test" and state.current_seat == probed_seat:
        seed = table.require("arm_m", (campaign, str(block), str(hand_ordinal)))
        if under_test_choose is None:
            raise KappaMaterialMiss("被测臂的被测座位必须由调用方给出动作")
        return under_test_choose(state, legal, seed)
    purpose = "arm_b" if state.current_seat == probed_seat else "non_probed"
    sigma = sigma_public_hex(state, legal)
    seed = table.require(
        purpose,
        (
            campaign,
            str(block),
            str(hand_ordinal),
            str(state.current_seat),
            str(event_index),
            sigma,
        ),
    )
    strategy = create_strategy(_BASELINE, seed=seed)
    return strategy.choose_action(state, legal)
