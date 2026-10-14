"""域节点、金额桶与层选择的静态核对。

设计目的：
- 把已生效的节点快照、桶归属和层选择收成可机械复算的表；
- 合法动作由快照字段按规则推出，不创建引擎，也不提交行动；
- 域侧版本号必须保持为 1，避免未升版的表混入配置摘要。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .config import CampaignLockVersions
from .errors import SpecIncompleteError

TABLE_SIZE = 6
STARTING_STACK = 200
BIG_BLIND = 2

# 层权重按节点个数写成既约分数。顺序与层名一致。
LAYER_WEIGHTS: tuple[tuple[str, int, int], ...] = (
    ("L-A-PF", 2, 5),
    ("L-A-FL", 1, 5),
    ("L-B", 2, 5),
)

# 每个域 B 节点的主动金额与主判桶。
BUCKET_STARS: tuple[tuple[str, tuple[int, ...], str], ...] = (
    ("B-001", (6, 8, 10), "BKT_MID"),
    ("B-002", (12, 14, 16), "BKT_OTHER"),
)

LOCKED_LAYER_PAIRS: tuple[tuple[str, str], ...] = (
    ("L-A-PF", "A-001"),
    ("L-A-PF", "A-002"),
    ("L-A-FL", "A-003"),
    ("L-B", "B-001"),
    ("L-B", "B-002"),
)


@dataclass(frozen=True)
class SeatRow:
    """一个座位的公开快照。不含任何座位的私牌。"""

    folded: bool
    all_in: bool
    street_bet: int
    total_committed: int
    stack_remaining: int
    has_acted_this_street: bool
    has_acted_since_full_raise: bool


@dataclass(frozen=True)
class NodeSnapshot:
    """一个已登记节点的静态快照与候选动作。"""

    node_id: str
    domain: str
    street: str
    hand_ordinal: int
    actor_hole: tuple[str, str]
    board: tuple[str, ...]
    current_bet: int
    min_raise: int
    pot_main: int
    seats: tuple[SeatRow, ...]
    candidates: tuple[tuple[str, int], ...]


def _seat(
    folded: bool,
    street_bet: int,
    total_committed: int,
    *,
    acted: bool,
    since_raise: bool,
) -> SeatRow:
    return SeatRow(
        folded=folded,
        all_in=False,
        street_bet=street_bet,
        total_committed=total_committed,
        stack_remaining=STARTING_STACK - total_committed,
        has_acted_this_street=acted,
        has_acted_since_full_raise=since_raise,
    )


_OPEN_BLINDS: tuple[SeatRow, ...] = (
    _seat(False, 0, 0, acted=False, since_raise=False),
    _seat(False, 1, 1, acted=False, since_raise=False),
    _seat(False, 2, 2, acted=False, since_raise=False),
    _seat(True, 0, 0, acted=True, since_raise=False),
    _seat(True, 0, 0, acted=True, since_raise=False),
    _seat(True, 0, 0, acted=True, since_raise=False),
)
_FACING_RAISE: tuple[SeatRow, ...] = (
    _seat(False, 0, 0, acted=False, since_raise=False),
    _seat(False, 1, 1, acted=False, since_raise=False),
    _seat(False, 2, 2, acted=False, since_raise=False),
    _seat(True, 0, 0, acted=True, since_raise=False),
    _seat(True, 0, 0, acted=True, since_raise=False),
    _seat(False, 4, 4, acted=True, since_raise=True),
)
_FLOP_CHECKED: tuple[SeatRow, ...] = (
    _seat(True, 0, 0, acted=True, since_raise=False),
    _seat(False, 0, 2, acted=False, since_raise=False),
    _seat(False, 0, 2, acted=True, since_raise=True),
    _seat(False, 0, 2, acted=True, since_raise=True),
    _seat(True, 0, 0, acted=True, since_raise=False),
    _seat(True, 0, 0, acted=True, since_raise=False),
)
_FLOP_FACING_BET: tuple[SeatRow, ...] = (
    _seat(True, 0, 0, acted=True, since_raise=False),
    _seat(False, 0, 2, acted=False, since_raise=False),
    _seat(False, 6, 8, acted=True, since_raise=True),
    _seat(True, 0, 2, acted=True, since_raise=False),
    _seat(True, 0, 0, acted=True, since_raise=False),
    _seat(True, 0, 0, acted=True, since_raise=False),
)

NODE_SNAPSHOTS: tuple[NodeSnapshot, ...] = (
    NodeSnapshot(
        node_id="A-001",
        domain="A",
        street="preflop",
        hand_ordinal=1,
        actor_hole=("As", "Kh"),
        board=(),
        current_bet=2,
        min_raise=2,
        pot_main=3,
        seats=_OPEN_BLINDS,
        candidates=(("fold", 0), ("call", 0)),
    ),
    NodeSnapshot(
        node_id="A-002",
        domain="A",
        street="preflop",
        hand_ordinal=1,
        actor_hole=("As", "Kh"),
        board=(),
        current_bet=4,
        min_raise=2,
        pot_main=7,
        seats=_FACING_RAISE,
        candidates=(("fold", 0), ("call", 0)),
    ),
    NodeSnapshot(
        node_id="A-003",
        domain="A",
        street="flop",
        hand_ordinal=2,
        actor_hole=("Qs", "Jd"),
        board=("Ah", "7d", "3c"),
        current_bet=0,
        min_raise=2,
        pot_main=6,
        seats=_FLOP_CHECKED,
        candidates=(("check", 0), ("bet", 4)),
    ),
    NodeSnapshot(
        node_id="B-001",
        domain="B",
        street="preflop",
        hand_ordinal=1,
        actor_hole=("As", "Kh"),
        board=(),
        current_bet=4,
        min_raise=2,
        pot_main=7,
        seats=_FACING_RAISE,
        candidates=(("raise", 6), ("raise", 8), ("raise", 10)),
    ),
    NodeSnapshot(
        node_id="B-002",
        domain="B",
        street="flop",
        hand_ordinal=2,
        actor_hole=("Qs", "Jd"),
        board=("Ah", "7d", "3c"),
        current_bet=6,
        min_raise=6,
        pot_main=12,
        seats=_FLOP_FACING_BET,
        candidates=(("raise", 12), ("raise", 14), ("raise", 16)),
    ),
)


def amount_bucket(amount: int) -> str:
    """按金额把主动投入分到开池、小、中、大或其余。"""
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise SpecIncompleteError("金额必须是整数")
    if amount == 2:
        return "BKT_OPEN"
    if 3 <= amount <= 4:
        return "BKT_SMALL"
    if 5 <= amount <= 7:
        return "BKT_MID"
    if 8 <= amount <= 10:
        return "BKT_LARGE"
    return "BKT_OTHER"


def require_domain_lock_versions(versions: CampaignLockVersions) -> None:
    """域侧六项版本必须为 1。构造校验被绕开时这里仍然拒绝。"""
    pairs = (
        ("domain_ab_node_registry", versions.domain_ab_node_registry),
        ("domain_ab_bucket_registry", versions.domain_ab_bucket_registry),
        ("domain_ab_layer_partition", versions.domain_ab_layer_partition),
        ("domain_ab_layer_weights", versions.domain_ab_layer_weights),
        ("domain_ab_block_template", versions.domain_ab_block_template),
        ("domain_ab_support_bounds", versions.domain_ab_support_bounds),
    )
    for name, value in pairs:
        if isinstance(value, bool) or value != 1:
            raise SpecIncompleteError(f"域锁定版本必须为 1：{name}")


def require_domain_snapshots(nodes: Sequence[NodeSnapshot] = NODE_SNAPSHOTS) -> None:
    """核对快照守恒、私牌边界、候选动作与层谓词。"""
    if len(nodes) != 5:
        raise SpecIncompleteError("节点表必须恰好包含五个已登记节点")
    seen: set[str] = set()
    for node in nodes:
        if node.node_id in seen:
            raise SpecIncompleteError("节点标识不能重复")
        seen.add(node.node_id)
        _require_snapshot(node)
    if seen != {"A-001", "A-002", "A-003", "B-001", "B-002"}:
        raise SpecIncompleteError("节点表与已登记标识不一致")
    _require_shared_snapshot(nodes)
    _require_layer_predicates(nodes)
    _require_layer_weights()


def require_bucket_assignments(
    stars: Sequence[tuple[str, tuple[int, ...], str]] = BUCKET_STARS,
) -> None:
    """核对每个域 B 节点的金额归属与主判桶。"""
    expected = {node_id: (amounts, bucket) for node_id, amounts, bucket in BUCKET_STARS}
    if len(stars) != len(expected):
        raise SpecIncompleteError("桶表行数与已登记域 B 节点不一致")
    for node_id, amounts, bucket in stars:
        if expected.get(node_id) != (amounts, bucket):
            raise SpecIncompleteError(f"桶表与已登记主判桶不一致：{node_id}")
        found = {amount_bucket(amount) for amount in amounts}
        if bucket not in found:
            raise SpecIncompleteError(f"主判桶在该节点的金额上为空：{node_id}")
        if node_id == "B-001" and "BKT_OTHER" in found:
            raise SpecIncompleteError("前一节点的主动金额不应落入其余桶")
        if node_id == "B-002" and found != {"BKT_OTHER"}:
            raise SpecIncompleteError("后一节点的主动金额应全部落入其余桶")


def require_layer_selection_keys(
    block_index: int,
    pairs: Sequence[tuple[str, str]] = LOCKED_LAYER_PAIRS,
) -> None:
    """同一块内，层与节点组成的选择键必须唯一，且每个节点只进一层。"""
    if isinstance(block_index, bool) or not isinstance(block_index, int) or block_index < 0:
        raise SpecIncompleteError("块索引必须是非负整数")
    seen: set[tuple[int, str, str]] = set()
    nodes: list[str] = []
    for layer, node_id in pairs:
        key = (block_index, layer, node_id)
        if key in seen:
            raise SpecIncompleteError("同一块内的层选择键不能重复")
        seen.add(key)
        nodes.append(node_id)
    if len(nodes) != len(set(nodes)):
        raise SpecIncompleteError("同一节点不能进入多个层")
    if set(nodes) != {node.node_id for node in NODE_SNAPSHOTS}:
        raise SpecIncompleteError("层选择必须覆盖全部已登记节点")


def legal_flags(node: NodeSnapshot) -> tuple[object, ...]:
    """由快照字段推出行动者的合法动作标志，供外部与引擎对照。"""
    actor = _actor_index(node)
    return _legal_from_row(node.street, node.current_bet, node.min_raise, node.seats[actor])


def bucket_mass_in_range(units_by_amount: Mapping[int, int], bucket: str) -> int:
    """把已合并的整数单位按桶相加。调用方负责保证单位来自合并口径。"""
    total = 0
    for amount, units in units_by_amount.items():
        if isinstance(units, bool) or not isinstance(units, int) or units < 0:
            raise SpecIncompleteError("桶内单位必须是非负整数")
        if amount_bucket(amount) == bucket:
            total += units
    return total


def _actor_index(node: NodeSnapshot) -> int:
    return (node.hand_ordinal - 1) % TABLE_SIZE


def _require_snapshot(node: NodeSnapshot) -> None:
    if len(node.seats) != TABLE_SIZE:
        raise SpecIncompleteError("座位表长度必须等于人数")
    if len(node.actor_hole) != 2:
        raise SpecIncompleteError("行动者私牌必须恰好两张")
    if node.street == "preflop" and node.board:
        raise SpecIncompleteError("翻牌前不能带有公共牌")
    if node.street == "flop" and len(node.board) != 3:
        raise SpecIncompleteError("翻牌圈公共牌必须是三张")
    committed = sum(seat.total_committed for seat in node.seats)
    remaining = sum(seat.stack_remaining for seat in node.seats)
    if committed + remaining != TABLE_SIZE * STARTING_STACK:
        raise SpecIncompleteError("快照筹码必须守恒")
    if committed != node.pot_main:
        raise SpecIncompleteError("主池必须等于各座已投入之和")
    for seat in node.seats:
        if seat.stack_remaining != STARTING_STACK - seat.total_committed:
            raise SpecIncompleteError("后手筹码必须等于起始筹码减去已投入")
        if seat.all_in:
            raise SpecIncompleteError("本版快照不包含全下座位")
    flags = legal_flags(node)
    for action, amount in node.candidates:
        if not _candidate_fits(action, amount, flags):
            raise SpecIncompleteError(f"候选动作不在合法范围内：{node.node_id}")


def _require_shared_snapshot(nodes: Sequence[NodeSnapshot]) -> None:
    by_id = {node.node_id: node for node in nodes}
    left = by_id["A-002"]
    right = by_id["B-001"]
    if (left.seats, left.current_bet, left.min_raise, left.pot_main, left.actor_hole) != (
        right.seats,
        right.current_bet,
        right.min_raise,
        right.pot_main,
        right.actor_hole,
    ):
        raise SpecIncompleteError("共用快照的两个节点必须逐字段相同")
    if legal_flags(left) != legal_flags(right):
        raise SpecIncompleteError("共用快照必须推出相同的合法动作")


def _require_layer_predicates(nodes: Sequence[NodeSnapshot]) -> None:
    expected = {
        "A-001": "L-A-PF",
        "A-002": "L-A-PF",
        "A-003": "L-A-FL",
        "B-001": "L-B",
        "B-002": "L-B",
    }
    for node in nodes:
        if node.domain == "A" and node.street == "preflop":
            layer = "L-A-PF"
        elif node.domain == "A" and node.street == "flop":
            layer = "L-A-FL"
        elif node.domain == "B":
            layer = "L-B"
        else:
            raise SpecIncompleteError(f"节点无法归入唯一层：{node.node_id}")
        if expected[node.node_id] != layer:
            raise SpecIncompleteError(f"层谓词与登记不一致：{node.node_id}")


def _require_layer_weights() -> None:
    total_num = 0
    for _name, numerator, denominator in LAYER_WEIGHTS:
        if denominator != 5 or numerator < 0:
            raise SpecIncompleteError("层权重分母必须与节点总数一致")
        total_num += numerator
    if total_num != 5:
        raise SpecIncompleteError("层权重必须合计为 1")


def _legal_from_row(
    street: str, current_bet: int, min_raise: int, row: SeatRow
) -> tuple[object, ...]:
    to_call = current_bet - row.street_bet
    all_in_total = row.street_bet + row.stack_remaining
    can_fold = to_call > 0
    can_check = to_call == 0
    can_call = to_call > 0
    call_amount = to_call if can_call else 0
    actual_call = min(to_call, row.stack_remaining) if can_call else 0
    short_call = can_call and to_call > row.stack_remaining
    can_bet = False
    can_raise = False
    min_bet = 0
    max_bet = 0
    min_raise_to = 0
    max_raise_to = 0
    if row.stack_remaining > 0:
        if to_call == 0 and street == "flop":
            can_bet = True
            min_bet = min(BIG_BLIND, all_in_total)
            max_bet = all_in_total
        elif all_in_total > current_bet and (to_call == 0 or not row.has_acted_since_full_raise):
            can_raise = True
            full_min = current_bet + min_raise
            min_raise_to = full_min if all_in_total >= full_min else all_in_total
            max_raise_to = all_in_total
    return (
        can_fold,
        can_check,
        can_call,
        call_amount,
        actual_call,
        short_call,
        can_bet,
        min_bet,
        max_bet,
        can_raise,
        min_raise_to,
        max_raise_to,
    )


def _candidate_fits(action: str, amount: int, flags: tuple[object, ...]) -> bool:
    (
        can_fold,
        can_check,
        can_call,
        _call_amount,
        _actual_call,
        _short_call,
        can_bet,
        min_bet,
        max_bet,
        can_raise,
        min_raise_to,
        max_raise_to,
    ) = flags
    if action == "fold":
        return bool(can_fold) and amount == 0
    if action == "check":
        return bool(can_check) and amount == 0
    if action == "call":
        return bool(can_call) and amount == 0
    if action == "bet":
        return bool(can_bet) and int(min_bet) <= amount <= int(max_bet)
    if action == "raise":
        return bool(can_raise) and int(min_raise_to) <= amount <= int(max_raise_to)
    return False
