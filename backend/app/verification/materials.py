"""一手材料的结构与规范编码：材料只由外部提供，本模块不生成也不派生。

设计目的：
- 每条材料都带用途标签与索引键，因此材料能与审计记录里的接受项逐一配对；
- 规范编码固定字段与顺序，使材料束的摘要可重算、可比对；
- 取值一律为非负整数：字节型材料以 32 字节大端的整数表示。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .digests import content_digest
from .errors import SpecIncompleteError


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
