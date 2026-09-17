"""受限 manifest 与实验工件的规范 JSON 读写。"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from typing import Any

MAX_JSON_DEPTH = 32
MAX_TEXT_BYTES = 4 * 1024 * 1024


class SafeJsonError(ValueError):
    """规范 JSON 或受限文件路径不符合离线实验安全契约时抛出。"""


def canonical_json_bytes(payload: dict[str, object]) -> bytes:
    """以固定键序、紧凑 UTF-8 和末尾换行编码受限 JSON。"""

    return (
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def load_canonical_json(
    path: str | Path, *, maximum_bytes: int = MAX_TEXT_BYTES
) -> tuple[dict[str, Any], bytes]:
    """安全读取普通文件，并要求原始字节已经是规范 JSON。"""

    raw_bytes = read_regular_file(path, maximum_bytes=maximum_bytes)
    try:
        payload = json.loads(
            raw_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_constant,
        )
    except UnicodeError as error:
        raise SafeJsonError("JSON 文件必须是 UTF-8 文本") from error
    except (json.JSONDecodeError, RecursionError) as error:
        raise SafeJsonError("JSON 文件不是有效 JSON") from error
    if not isinstance(payload, dict):
        raise SafeJsonError("JSON 顶层必须是对象")
    _ensure_max_depth(payload)
    canonical = canonical_json_bytes(payload)
    if raw_bytes != canonical:
        raise SafeJsonError("JSON 文件必须使用规范编码")
    return payload, raw_bytes


def read_regular_file(path: str | Path, *, maximum_bytes: int) -> bytes:
    """通过非链接描述符读取受限大小的普通文件。"""

    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) or maximum_bytes <= 0:
        raise SafeJsonError("文件大小上限必须是正整数")
    try:
        descriptor = os.open(Path(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise SafeJsonError("无法读取受限文件") from error
    try:
        with os.fdopen(descriptor, "rb") as source:
            details = os.fstat(source.fileno())
            if not stat.S_ISREG(details.st_mode):
                raise SafeJsonError("受限文件必须是非链接的普通文件")
            raw_bytes = source.read(maximum_bytes + 1)
    except OSError as error:
        raise SafeJsonError("无法读取受限文件") from error
    if len(raw_bytes) > maximum_bytes:
        raise SafeJsonError("受限文件超过大小上限")
    return raw_bytes


def write_canonical_json(
    root: str | Path,
    relative_name: str,
    payload: dict[str, object],
    *,
    maximum_bytes: int,
) -> tuple[Path, bytes]:
    """在受信任根目录内原子写入一个预声明的相对文件名。"""

    serialized = canonical_json_bytes(payload)
    if len(serialized) > maximum_bytes:
        raise SafeJsonError("JSON 工件超过声明大小上限")
    root_path = _validate_root(root)
    name = _validate_relative_name(relative_name)
    destination = root_path / name
    if destination.exists() or destination.is_symlink():
        raise SafeJsonError("实验工件目标已存在或不是受限普通路径")
    _write_atomically(destination, serialized)
    _, read_back = load_canonical_json(destination, maximum_bytes=maximum_bytes)
    if read_back != serialized:
        raise SafeJsonError("实验工件回读字节不一致")
    return destination, serialized


def sha256_identity(raw_bytes: bytes) -> tuple[str, int]:
    """返回同一份已验证字节的 SHA-256 与长度。"""

    return sha256(raw_bytes).hexdigest(), len(raw_bytes)


def _validate_root(root: str | Path) -> Path:
    root_path = Path(root)
    if not root_path.is_dir() or root_path.is_symlink():
        raise SafeJsonError("工件根目录必须是现有非链接目录")
    return root_path


def _validate_relative_name(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise SafeJsonError("工件文件名必须是长度受限的非空字符串")
    candidate = Path(value)
    if candidate.is_absolute() or len(candidate.parts) != 1 or candidate.name != value:
        raise SafeJsonError("工件文件名不能包含目录或绝对路径")
    if value in {".", ".."} or "\x00" in value:
        raise SafeJsonError("工件文件名不合法")
    return value


def _write_atomically(path: Path, serialized: bytes) -> None:
    parent = path.parent
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary_path = Path(temporary_name)
    replaced = False
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            os.fchmod(temporary_file.fileno(), 0o600)
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        replaced = True
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError as error:
        raise SafeJsonError("无法原子写入实验工件") from error
    finally:
        if not replaced:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise SafeJsonError(f"JSON 存在重复键：{key}")
        payload[key] = value
    return payload


def _reject_non_finite_constant(value: str) -> None:
    raise SafeJsonError(f"JSON 不允许非有限数值：{value}")


def _ensure_max_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise SafeJsonError("JSON 嵌套层级超过上限")
    if isinstance(value, dict):
        for nested in value.values():
            _ensure_max_depth(nested, depth + 1)
    elif isinstance(value, list):
        for nested in value:
            _ensure_max_depth(nested, depth + 1)
