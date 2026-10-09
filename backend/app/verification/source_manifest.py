"""显式传入的源码清单：只校验封闭结构并重算内容摘要。

本模块不打开文件，也不收集导入闭包。文件读取与闭包核验由包外工具完成。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .digests import content_digest
from .errors import SourceManifestError

_SCHEMA = "source-manifest-v1"
_DEPENDENCY_PATHS: tuple[str, ...] = ("backend/pyproject.toml", "backend/uv.lock")
_FIELDS: frozenset[str] = frozenset(
    {"schema", "entrypoints", "python_version", "files", "dependency_files"}
)
_FILE_FIELDS: frozenset[str] = frozenset({"path", "sha256"})


def _require_lower_hex64(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise SourceManifestError(f"摘要格式不合法：{label}")
    if any(character not in "0123456789abcdef" for character in value):
        raise SourceManifestError(f"摘要格式不合法：{label}")
    return value


def _require_relative_posix(path: object) -> str:
    """工作区相对 POSIX 路径：拒绝绝对路径、空段、`.` 与 `..`。"""
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("/"):
        raise SourceManifestError("路径必须是工作区相对 POSIX 路径")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise SourceManifestError("路径不得包含空段、当前目录或上级目录")
    return path


def _require_version(value: object) -> str:
    if not isinstance(value, str):
        raise SourceManifestError("解释器版本格式不合法")
    parts = value.split(".")
    if len(parts) != 3:
        raise SourceManifestError("解释器版本必须是主版本、次版本与补丁号")
    for part in parts:
        if not part.isdigit() or (part.startswith("0") and part != "0"):
            raise SourceManifestError("解释器版本的每一段必须是无前导零的十进制")
    return value


def _require_file_rows(rows: object, *, label: str) -> list[dict[str, str]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise SourceManifestError(f"{label}必须是列表")
    normalized: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != _FILE_FIELDS:
            raise SourceManifestError(f"{label}的每项只能包含路径与摘要")
        normalized.append(
            {
                "path": _require_relative_posix(row["path"]),
                "sha256": _require_lower_hex64(row["sha256"], label),
            }
        )
    return normalized


def _require_increasing(paths: Sequence[str], label: str) -> None:
    if not paths:
        raise SourceManifestError(f"{label}不得为空")
    if list(paths) != sorted(paths) or len(set(paths)) != len(paths):
        raise SourceManifestError(f"{label}必须按路径严格递增且不重复")


def require_source_manifest(manifest: Mapping[str, object]) -> dict[str, object]:
    """校验封闭结构、路径、次序、入口包含与依赖文件。返回规范化后的清单。"""
    if not isinstance(manifest, Mapping) or set(manifest) != _FIELDS:
        raise SourceManifestError("清单字段集不封闭")
    if manifest["schema"] != _SCHEMA:
        raise SourceManifestError("清单模式不符")
    entrypoints = manifest["entrypoints"]
    if not isinstance(entrypoints, Sequence) or isinstance(entrypoints, (str, bytes)):
        raise SourceManifestError("入口必须是列表")
    entry_paths = [_require_relative_posix(path) for path in entrypoints]
    _require_increasing(entry_paths, "入口")
    files = _require_file_rows(manifest["files"], label="文件")
    file_paths = [row["path"] for row in files]
    _require_increasing(file_paths, "文件")
    missing = [path for path in entry_paths if path not in file_paths]
    if missing:
        raise SourceManifestError("每个入口都必须出现在文件列表中")
    dependencies = _require_file_rows(manifest["dependency_files"], label="依赖文件")
    dependency_paths = [row["path"] for row in dependencies]
    if tuple(dependency_paths) != _DEPENDENCY_PATHS:
        raise SourceManifestError("依赖文件必须按固定的两项次序出现")
    return {
        "schema": _SCHEMA,
        "entrypoints": entry_paths,
        "python_version": _require_version(manifest["python_version"]),
        "files": files,
        "dependency_files": dependencies,
    }


def source_manifest_digest(manifest: Mapping[str, object], *, algorithm: str) -> str:
    """按规范编码重算清单内容摘要。"""
    return content_digest(require_source_manifest(manifest), algorithm=algorithm)
