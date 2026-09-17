"""独占实验工件根目录的封存清单与最终字节核验。"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


class ArtifactInventoryError(ValueError):
    """工件根目录包含未声明条目、链接或不符合槽位限制的文件时抛出。"""


@dataclass(frozen=True)
class InventorySlot:
    """由父端计划派生的工件文件名与最大字节数。"""

    relative_name: str
    maximum_bytes: int


@dataclass(frozen=True)
class InventoryEntry:
    """一次安全读取到的最终普通文件身份。"""

    relative_name: str
    sha256: str
    byte_length: int

    def as_payload(self) -> dict[str, object]:
        return {
            "relative_name": self.relative_name,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
        }


def require_empty_artifact_root(root: str | Path) -> Path:
    """要求本次 authorization 使用一个新建、空且非链接的独占工件根目录。"""

    path = _require_root(root)
    if any(path.iterdir()):
        raise ArtifactInventoryError("工件根目录必须在执行前为空")
    return path


def inventory_declared_artifacts(
    root: str | Path,
    slots: tuple[InventorySlot, ...],
    *,
    required_names: frozenset[str],
) -> tuple[InventoryEntry, ...]:
    """严格扫描根目录，只接受声明槽位中的非链接普通文件。"""

    path = _require_root(root)
    slot_by_name = {slot.relative_name: slot for slot in slots}
    if len(slot_by_name) != len(slots):
        raise ArtifactInventoryError("工件槽位名称不能重复")
    if not required_names <= set(slot_by_name):
        raise ArtifactInventoryError("必需工件不属于已声明槽位")
    names = set()
    for entry in path.iterdir():
        if entry.is_symlink() or entry.is_dir():
            raise ArtifactInventoryError("工件根目录不能包含链接或子目录")
        if entry.name not in slot_by_name:
            raise ArtifactInventoryError("工件根目录包含未声明文件")
        names.add(entry.name)
    if names != required_names:
        raise ArtifactInventoryError("工件根目录的最终文件集合与计划不一致")

    entries = []
    for name in sorted(required_names):
        slot = slot_by_name[name]
        raw_bytes = _read_single_regular_file(path / name, slot.maximum_bytes)
        entries.append(
            InventoryEntry(
                relative_name=name,
                sha256=sha256(raw_bytes).hexdigest(),
                byte_length=len(raw_bytes),
            )
        )
    return tuple(entries)


def remove_declared_artifacts(
    root: str | Path, slots: tuple[InventorySlot, ...]
) -> tuple[str, ...]:
    """停止/失败时仅清理已声明普通文件，未知或链接条目一律 fail-closed。"""

    path = _require_root(root)
    slot_names = {slot.relative_name for slot in slots}
    removed = []
    for entry in path.iterdir():
        if entry.name not in slot_names or entry.is_symlink() or entry.is_dir():
            raise ArtifactInventoryError("停止路径存在未知、链接或目录工件，不能安全清理")
        raw_bytes = _read_single_regular_file(
            entry, next(slot.maximum_bytes for slot in slots if slot.relative_name == entry.name)
        )
        del raw_bytes
        entry.unlink()
        removed.append(entry.name)
    return tuple(sorted(removed))


def _require_root(root: str | Path) -> Path:
    path = Path(root)
    if not path.is_dir() or path.is_symlink():
        raise ArtifactInventoryError("工件根目录必须是现有非链接目录")
    return path


def _read_single_regular_file(path: Path, maximum_bytes: int) -> bytes:
    if maximum_bytes <= 0:
        raise ArtifactInventoryError("工件槽位大小必须为正整数")
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise ArtifactInventoryError("无法读取声明工件") from error
    try:
        with os.fdopen(descriptor, "rb") as source:
            details = os.fstat(source.fileno())
            if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
                raise ArtifactInventoryError("工件必须是单链接普通文件")
            raw_bytes = source.read(maximum_bytes + 1)
    except OSError as error:
        raise ArtifactInventoryError("无法读取声明工件") from error
    if len(raw_bytes) > maximum_bytes:
        raise ArtifactInventoryError("工件超过声明槽位大小")
    return raw_bytes
