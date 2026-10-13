"""一手材料的结构与规范编码：材料只由外部提供，本模块不生成也不派生。

设计目的：
- 每条材料都带用途标签与索引键，因此材料能与审计记录里的接受项逐一配对；
- 规范编码固定字段与顺序，使材料束的摘要可重算、可比对；
- 取值一律为非负整数：字节型材料以 32 字节大端的整数表示。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .digests import content_digest
from .errors import ProtocolAuditError, ProtocolSpecError, SpecIncompleteError

if TYPE_CHECKING:
    from .config import DomainRunSpec


@dataclass(frozen=True)
class MaterialEntry:
    """一条材料：用途标签、索引键与取值。"""

    purpose_label: str
    index_key: tuple[str, ...]
    value: int

    def __post_init__(self) -> None:
        if not self.purpose_label.strip():
            raise SpecIncompleteError("材料的用途标签不能为空")
        if not self.index_key or any(not field.strip() for field in self.index_key):
            raise SpecIncompleteError("材料的索引键必须非空且每项非空")
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise SpecIncompleteError("材料取值必须是非负整数")
        if self.value < 0:
            raise SpecIncompleteError("材料取值必须是非负整数")

    def canonical_payload(self) -> dict[str, object]:
        """规范编码：字段与顺序固定，供摘要重算。"""
        return {
            "purpose_label": self.purpose_label,
            "index_key": list(self.index_key),
            "value": self.value,
        }


@dataclass(frozen=True)
class HandMaterials:
    """一手牌的全部材料：块内手序加逐条材料。"""

    hand_ordinal: int
    entries: tuple[MaterialEntry, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.hand_ordinal, bool)
            or not isinstance(self.hand_ordinal, int)
            or self.hand_ordinal < 1
        ):
            raise SpecIncompleteError("块内手序必须是正整数")
        if not self.entries:
            raise SpecIncompleteError("一手材料不能为空")
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for entry in self.entries:
            key = (entry.purpose_label, entry.index_key)
            if key in seen:
                raise SpecIncompleteError("同一用途的同一索引不得重复给材料")
            seen.add(key)

    def entries_for(self, purpose_label: str) -> tuple[MaterialEntry, ...]:
        """取该用途的全部材料，保持给定顺序。"""
        return tuple(entry for entry in self.entries if entry.purpose_label == purpose_label)

    def canonical_payload(self) -> dict[str, object]:
        """规范编码：字段与顺序固定，供摘要重算。"""
        return {
            "hand_ordinal": self.hand_ordinal,
            "entries": [entry.canonical_payload() for entry in self.entries],
        }


def bundle_payload(bundle: Sequence[HandMaterials]) -> list[dict[str, object]]:
    """材料束的规范编码：按给定次序逐手展开。"""
    return [hand.canonical_payload() for hand in bundle]


_VALUE_UPPER_BOUND = 1 << 256
_PROTOCOL_V2 = "randomization-protocol-v2"


def _hand_locations(
    spec: DomainRunSpec, hand: HandMaterials, *, hand_ordinal: int
) -> list[tuple[int, tuple[int | str, ...]]]:
    """读出一手材料的排序键，并核对索引里的战役、块和手序。"""
    protocol = spec.protocol
    purpose_order = {label: index for index, label in enumerate(protocol.traversal_order)}
    positions: list[tuple[int, tuple[int | str, ...]]] = []
    for entry in hand.entries:
        try:
            purpose = protocol.purpose_for_label(entry.purpose_label)
            if purpose.field_text(entry.index_key, "campaign") != spec.campaign:
                raise SpecIncompleteError("索引中的 campaign 与规格不一致")
            if purpose.field_integer(entry.index_key, "block") != spec.block:
                raise SpecIncompleteError("索引中的 block 与规格不一致")
            hand_number = purpose.field_integer(entry.index_key, "hand")
            if hand_number != hand_ordinal or hand_number != hand.hand_ordinal:
                raise SpecIncompleteError("索引中的 hand 必须与两处手序一致")
            positions.append(
                (purpose_order[entry.purpose_label], purpose.index_order_key(entry.index_key))
            )
        except (ProtocolSpecError, ProtocolAuditError) as error:
            raise SpecIncompleteError(f"材料索引不合规：{error}") from error
    return positions


def _require_sorted_positions(positions: Sequence[tuple[int, tuple[int | str, ...]]]) -> None:
    if len(positions) != len(set(positions)) or list(positions) != sorted(positions):
        raise SpecIncompleteError("手内材料必须按用途遍历顺序与索引升序排列")


def _require_v2_supplied_order(
    spec: DomainRunSpec,
    bundle: Sequence[HandMaterials],
    closed_entries: Sequence[tuple[str, tuple[str, ...]]] | None,
) -> None:
    """另一版送交材料按闭合集切片计条数，手内先用途、再按整数字段比较完整键。"""
    if closed_entries is None:
        raise SpecIncompleteError("这一版送交材料必须对照闭合集")
    if isinstance(closed_entries, (str, bytes)) or not isinstance(closed_entries, Sequence):
        raise SpecIncompleteError("闭合集必须是有限序列")
    protocol = spec.protocol
    if len(bundle) != len(spec.schedule):
        raise SpecIncompleteError("材料束必须与手序计划一一对应")
    closed_by_hand: dict[int, set[tuple[str, tuple[str, ...]]]] = {}
    seen_closed: set[tuple[str, tuple[str, ...]]] = set()
    for label, index_key in closed_entries:
        if not isinstance(index_key, tuple):
            raise SpecIncompleteError("闭合集的索引键必须是元组")
        try:
            purpose = protocol.purpose_for_label(label)
            hand_number = purpose.field_integer(index_key, "hand")
        except (ProtocolSpecError, ProtocolAuditError) as error:
            raise SpecIncompleteError(f"闭合集索引不合规：{error}") from error
        location = (label, index_key)
        if location in seen_closed:
            raise SpecIncompleteError("闭合集出现重复的完整键")
        seen_closed.add(location)
        bucket = closed_by_hand.get(hand_number)
        if bucket is None:
            bucket = set()
            closed_by_hand[hand_number] = bucket
        bucket.add(location)
    scheduled = {plan.hand_ordinal for plan in spec.schedule}
    if set(closed_by_hand) - scheduled:
        raise SpecIncompleteError("闭合集含有手序计划以外的手")
    draw_count = spec.deal.draw_count(spec.num_players)
    for plan, hand in zip(spec.schedule, bundle, strict=True):
        if hand.hand_ordinal != plan.hand_ordinal:
            raise SpecIncompleteError("材料束的块内手序必须与手序计划一致")
        _require_sorted_positions(_hand_locations(spec, hand, hand_ordinal=plan.hand_ordinal))
        actual = {(entry.purpose_label, entry.index_key) for entry in hand.entries}
        if actual != closed_by_hand.get(plan.hand_ordinal, set()):
            raise SpecIncompleteError("送交材料与闭合集在该手上不一致")
        grouped: dict[str, list[MaterialEntry]] = {}
        slots: dict[tuple[str, int, int], str] = {}
        for entry in hand.entries:
            items = grouped.get(entry.purpose_label)
            if items is None:
                items = []
                grouped[entry.purpose_label] = items
            items.append(entry)
            if entry.purpose_label == "deal":
                continue
            if isinstance(entry.value, bool) or not isinstance(entry.value, int):
                raise SpecIncompleteError("材料取值必须是整数")
            if not 0 <= entry.value < _VALUE_UPPER_BOUND:
                raise SpecIncompleteError("材料取值超出范围")
            if entry.purpose_label not in ("non_probed", "arm_b"):
                continue
            purpose = protocol.purpose_for_label(entry.purpose_label)
            seat = purpose.field_integer(entry.index_key, "seat")
            event_index = purpose.field_integer(entry.index_key, "event_index")
            sigma = purpose.field_text(entry.index_key, "sigma_public")
            slot = (entry.purpose_label, seat, event_index)
            previous = slots.get(slot)
            if previous is not None and previous != sigma:
                raise SpecIncompleteError("同一决策序号不得对应两条公开投影")
            slots[slot] = sigma
        if len(grouped.get("deal", ())) != draw_count:
            raise SpecIncompleteError("每手发牌材料条数与抽取次数不符")
        if len(grouped.get("arm_m", ())) != 1:
            raise SpecIncompleteError("每手被测材料必须恰好一条")
        non_probed = grouped.get("non_probed", ())
        if not non_probed:
            raise SpecIncompleteError("非被测材料不能为空")
        non_probed_purpose = protocol.purpose_for_label("non_probed")
        seats = {
            non_probed_purpose.field_integer(entry.index_key, "seat")
            for entry in non_probed
        }
        expected_seats = {seat for seat in range(spec.num_players) if seat != plan.probed_seat}
        if seats != expected_seats:
            raise SpecIncompleteError("非被测材料必须覆盖该手全部非被测座位")
        arm_b = grouped.get("arm_b", ())
        if not arm_b:
            raise SpecIncompleteError("基线材料不能为空")
        arm_b_purpose = protocol.purpose_for_label("arm_b")
        if any(
            arm_b_purpose.field_integer(entry.index_key, "seat") != plan.probed_seat
            for entry in arm_b
        ):
            raise SpecIncompleteError("基线材料的座位必须是该手被测座位")
        deal_purpose = protocol.purpose_for_label("deal")
        deal_entries = sorted(
            grouped["deal"], key=lambda item: deal_purpose.index_order_key(item.index_key)
        )
        draws = [deal_purpose.draw_index_of(entry.index_key) for entry in deal_entries]
        if draws != list(range(draw_count)):
            raise SpecIncompleteError("发牌材料的抽取次序必须从零起连续")
        for index, entry in enumerate(deal_entries):
            if not 0 <= entry.value < deal_purpose.domain.domain_size(index):
                raise SpecIncompleteError("发牌材料的取值超出该次抽取的输出域")


def require_supplied_materials_order(
    spec: DomainRunSpec,
    bundle: Sequence[HandMaterials],
    *,
    closed_entries: Sequence[tuple[str, tuple[str, ...]]] | None = None,
) -> None:
    """送交材料必须逐手对应计划。旧版按人数固定条数；另一版按闭合集切片。"""
    if spec.protocol.protocol_schema == _PROTOCOL_V2:
        _require_v2_supplied_order(spec, bundle, closed_entries)
        return
    if len(bundle) != len(spec.schedule):
        raise SpecIncompleteError("材料束必须与手序计划一一对应")
    expected_count = 3 * spec.num_players + 6
    for plan, hand in zip(spec.schedule, bundle, strict=True):
        if hand.hand_ordinal != plan.hand_ordinal:
            raise SpecIncompleteError("材料束的块内手序必须与手序计划一致")
        if len(hand.entries) != expected_count:
            raise SpecIncompleteError("每手材料条数与人数不符")
        _require_sorted_positions(_hand_locations(spec, hand, hand_ordinal=plan.hand_ordinal))


@dataclass(frozen=True)
class MaterialManifest:
    """生成阶段的材料清单内容：逐用途逐索引的取值，按生成次序给出。

    清单是本包内被摘要的对象本身，因此「清单摘要」由内容重算，而不是转录一个字符串。
    """

    entries: tuple[MaterialEntry, ...]

    def __post_init__(self) -> None:
        if not self.entries:
            raise SpecIncompleteError("材料清单不能为空")
        seen: set[tuple[str, tuple[str, ...]]] = set()
        for entry in self.entries:
            key = (entry.purpose_label, entry.index_key)
            if key in seen:
                raise SpecIncompleteError("材料清单不得出现重复定位")
            seen.add(key)

    def entry_map(self) -> dict[tuple[str, tuple[str, ...]], int]:
        """把清单展开为「用途标签 + 索引键 → 取值」的映射。"""
        return {(entry.purpose_label, entry.index_key): entry.value for entry in self.entries}

    def canonical_payload(self) -> list[dict[str, object]]:
        """规范编码：逐条按固定字段展开，条目顺序即生成顺序。"""
        return [entry.canonical_payload() for entry in self.entries]


def manifest_digest(manifest: MaterialManifest, *, algorithm: str) -> str:
    """由材料清单内容重算摘要：清单内容不同即摘要不同。"""
    return content_digest(manifest.canonical_payload(), algorithm=algorithm)
