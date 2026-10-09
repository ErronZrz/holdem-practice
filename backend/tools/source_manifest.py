"""包外源码清单：读取原始字节、收集静态导入闭包，并核验实际加载未超出闭包。

本工具不把结果写入仓库。验证包只接收已经构造好的清单对象。
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from app.verification.errors import SourceManifestError
from app.verification.source_manifest import require_source_manifest

_DEPENDENCY_PATHS = ("backend/pyproject.toml", "backend/uv.lock")
_DYNAMIC_CALLS = {
    "__import__",
    "importlib.import_module",
    "importlib.__import__",
}
_RUNTIME_CALLS = {
    "exec",
    "eval",
    "compile",
    "importlib.util.spec_from_file_location",
    "importlib.machinery.SourceFileLoader",
}
# 这些属性本身就是加载器。点号访问即保留运行期加载能力。
_FORBIDDEN_ATTRS = frozenset(
    {
        "exec_module",
        "load_module",
        "create_module",
        "module_from_spec",
        "spec_from_file_location",
        "spec_from_loader",
        "SourceFileLoader",
    }
)
# getattr 的属性名。含可按字面调用的动态导入名，避免经反射取回。
_REFLECTED_LOADER_NAMES = _FORBIDDEN_ATTRS | {
    "import_module",
    "__import__",
    "exec",
    "eval",
    "compile",
}

_CHILD = r"""
import importlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
workspace = Path(sys.argv[1]).resolve()
entrypoints = json.loads(sys.argv[2])
sys.path.insert(0, str(workspace / "backend"))

def module_name(entry: str) -> str:
    relative = Path(entry)
    if not relative.parts or relative.parts[0] != "backend":
        raise SystemExit(2)
    body = relative.parts[1:]
    if body and body[-1] == "__init__.py":
        names = body[:-1]
    elif body and body[-1].endswith(".py"):
        names = (*body[:-1], body[-1][:-3])
    else:
        raise SystemExit(2)
    if not names or any(not part.isidentifier() for part in names):
        raise SystemExit(2)
    return ".".join(names)

for entry in entrypoints:
    importlib.import_module(module_name(entry))
loaded = []
for module in sys.modules.values():
    file_name = getattr(module, "__file__", None)
    if not isinstance(file_name, str):
        continue
    real = Path(file_name).resolve()
    try:
        relative = real.relative_to(workspace)
    except ValueError:
        continue
    if real.suffix != ".py":
        continue
    loaded.append(relative.as_posix())
print(json.dumps(sorted(set(loaded))))
"""


def _fail(message: str) -> NoReturn:
    raise SourceManifestError(message)


def _relative(workspace: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        _fail("路径逃出了工作区")


def _reject_relative_text(entry: str) -> None:
    if not entry or "\\" in entry or entry.startswith("/") or Path(entry).is_absolute():
        _fail("入口必须是工作区相对 POSIX 路径")
    if any(part in {"", ".", ".."} for part in entry.split("/")):
        _fail("入口不得包含空段、当前目录或上级目录")


def _resolve_entry(workspace: Path, entry: str) -> Path:
    _reject_relative_text(entry)
    candidate = workspace.joinpath(*entry.split("/"))
    if not candidate.exists():
        _fail(f"入口不存在：{entry}")
    real = candidate.resolve()
    _relative(workspace, real)
    if not real.is_file():
        _fail(f"入口不是文件：{entry}")
    return real


def _lookup_module(source_root: Path, module: str) -> Path | None:
    if not module:
        return None
    base = source_root.joinpath(*module.split("."))
    module_file = base.with_suffix(".py")
    package_init = base / "__init__.py"
    if module_file.is_file():
        return module_file.resolve()
    if package_init.is_file():
        return package_init.resolve()
    return None


def _is_first_party(source_root: Path, module: str) -> bool:
    top = module.split(".", 1)[0]
    return _lookup_module(source_root, top) is not None


def _package_name(source_root: Path, file_path: Path) -> str:
    relative = file_path.resolve().relative_to(source_root.resolve())
    parts = list(relative.parts)
    return ".".join(parts[:-1])


def _absolute_module(package: str, level: int, module: str | None) -> str:
    parts = package.split(".") if package else []
    if level:
        if level > len(parts) + (0 if package else 0):
            _fail("相对导入超出了包的层级")
        prefix = parts[: len(parts) - (level - 1)]
    else:
        prefix = []
    if module:
        prefix.extend(module.split("."))
    if not prefix:
        _fail("无法解析的导入")
    return ".".join(prefix)


def _normalize_callable(name: str) -> str:
    """把内建模块前缀还原成调用名，避免别名绕过运行期加载检查。"""
    prefix = "builtins."
    if name.startswith(prefix):
        return name[len(prefix) :]
    return name


def _literal_module_name(node: ast.Call) -> str | None:
    if not node.args:
        return None
    argument = node.args[0]
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    return None


def _is_loader_reference(name: str) -> bool:
    """名称是否指向导入系统或已知的动态/运行期加载器。"""
    normalized = _normalize_callable(name)
    if normalized in _DYNAMIC_CALLS or normalized in _RUNTIME_CALLS:
        return True
    return name in {"importlib", "builtins"} or name.startswith(("importlib.", "builtins."))


def _is_getattr(name: str) -> bool:
    normalized = _normalize_callable(name)
    return normalized == "getattr" or normalized.endswith(".getattr")


def _include_module(source_root: Path, module: str, found: set[Path]) -> None:
    if not _is_first_party(source_root, module):
        return
    prefixes: list[str] = []
    parts = module.split(".")
    for index in range(len(parts)):
        prefixes.append(".".join(parts[: index + 1]))
    for name in prefixes:
        path = _lookup_module(source_root, name)
        if path is None:
            _fail(f"无法解析的第一方导入：{name}")
        found.add(path)


class _ImportCollector(ast.NodeVisitor):
    def __init__(self, source_root: Path, package: str) -> None:
        self._source_root = source_root
        self._package = package
        self.found: set[Path] = set()
        self._bound: dict[str, str] = {}

    def _bind(self, local: str, canonical: str) -> None:
        previous = self._bound.get(local)
        if previous is not None and previous != canonical and _normalize_callable(previous) in {
            *_DYNAMIC_CALLS,
            *_RUNTIME_CALLS,
        }:
            _fail("非字面动态导入不能进入清单")
        self._bound[local] = canonical

    def _canonical(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self._bound.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            parent = self._canonical(node.value)
            if parent is None:
                return None
            return f"{parent}.{node.attr}"
        return None

    def _enter_scope(self, node: ast.AST) -> None:
        saved = dict(self._bound)
        arguments = getattr(node, "args", None)
        if arguments is not None:
            names = [
                arg.arg
                for arg in arguments.posonlyargs + arguments.args + arguments.kwonlyargs
            ]
            if arguments.vararg is not None:
                names.append(arguments.vararg.arg)
            if arguments.kwarg is not None:
                names.append(arguments.kwarg.arg)
            for name in names:
                previous = self._bound.get(name)
                if previous is not None and _normalize_callable(previous) in {
                    *_DYNAMIC_CALLS,
                    *_RUNTIME_CALLS,
                }:
                    _fail("非字面动态导入不能进入清单")
        self.generic_visit(node)
        self._bound = saved

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter_scope(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._enter_scope(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter_scope(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            _include_module(self._source_root, alias.name, self.found)
            if alias.asname:
                self._bind(alias.asname, alias.name)
            else:
                root = alias.name.split(".", 1)[0]
                self._bind(root, root)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            base = _absolute_module(self._package, node.level, node.module)
        else:
            base = node.module or ""
        if base:
            _include_module(self._source_root, base, self.found)
        for alias in node.names:
            if alias.name == "*":
                if base == "importlib" or base.startswith("importlib."):
                    _fail("非字面动态导入不能进入清单")
                continue
            local = alias.asname or alias.name
            if base:
                self._bind(local, f"{base}.{alias.name}")
            candidate = f"{base}.{alias.name}" if base else alias.name
            if _lookup_module(self._source_root, candidate) is not None:
                _include_module(self._source_root, candidate, self.found)

    def _keeps_loader(self, node: ast.AST) -> bool:
        if isinstance(node, ast.Starred):
            return self._keeps_loader(node.value)
        canonical = self._canonical(node)
        return canonical is not None and _is_loader_reference(canonical)

    def _reject_loader_elements(self, elements: Sequence[ast.AST]) -> None:
        if any(self._keeps_loader(element) for element in elements):
            _fail("运行期代码加载不能进入清单")

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            canonical = self._canonical(node.value)
            if canonical is not None:
                self._bind(node.targets[0].id, canonical)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.value is not None:
            canonical = self._canonical(node.value)
            if canonical is not None:
                self._bind(node.target.id, canonical)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _FORBIDDEN_ATTRS:
            _fail("运行期代码加载不能进入清单")
        canonical = self._canonical(node.value)
        if node.attr in {"__dict__", "__globals__", "__builtins__"} and (
            canonical is not None and _is_loader_reference(canonical)
        ):
            _fail("运行期代码加载不能进入清单")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        canonical = self._canonical(node.value)
        if canonical is not None and _is_loader_reference(canonical):
            _fail("运行期代码加载不能进入清单")
        slice_node = node.slice
        if (
            isinstance(slice_node, ast.Constant)
            and isinstance(slice_node.value, str)
            and slice_node.value in _REFLECTED_LOADER_NAMES
        ):
            _fail("运行期代码加载不能进入清单")
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        self._reject_loader_elements(node.elts)
        self.generic_visit(node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self._reject_loader_elements(node.elts)
        self.generic_visit(node)

    def visit_Set(self, node: ast.Set) -> None:
        self._reject_loader_elements(node.elts)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        self._reject_loader_elements([key for key in node.keys if key is not None])
        self._reject_loader_elements(node.values)
        self.generic_visit(node)

    def _reject_getattr(self, node: ast.Call) -> None:
        """反射取出加载器，或基座无法证明与加载器无关时，直接失败。"""
        if not node.args:
            _fail("运行期代码加载不能进入清单")
        base = self._canonical(node.args[0])
        if base is None or _is_loader_reference(base):
            _fail("运行期代码加载不能进入清单")
        if len(node.args) < 2:
            return
        attr = node.args[1]
        if (
            isinstance(attr, ast.Constant)
            and isinstance(attr.value, str)
            and attr.value in _REFLECTED_LOADER_NAMES
        ):
            _fail("运行期代码加载不能进入清单")

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, (ast.Subscript, ast.Call)):
            _fail("运行期代码加载不能进入清单")
        name = self._canonical(node.func)
        normalized = _normalize_callable(name) if name is not None else None
        if normalized is not None and _is_getattr(normalized):
            self._reject_getattr(node)
        if normalized in _RUNTIME_CALLS or (
            normalized is not None and normalized.rsplit(".", 1)[-1] in _FORBIDDEN_ATTRS
        ):
            _fail("运行期代码加载不能进入清单")
        if normalized in _DYNAMIC_CALLS:
            literal = _literal_module_name(node)
            if literal is None:
                _fail("非字面动态导入不能进入清单")
            _include_module(self._source_root, literal, self.found)
        self.generic_visit(node)


def _closure(workspace: Path, entry_files: Sequence[Path]) -> list[str]:
    source_root = workspace / "backend"
    pending = list(entry_files)
    seen: set[Path] = set()
    while pending:
        current = pending.pop()
        real = current.resolve()
        if real in seen:
            continue
        _relative(workspace, real)
        seen.add(real)
        try:
            tree = ast.parse(real.read_bytes().decode("utf-8"))
        except (UnicodeError, SyntaxError) as error:
            _fail(f"无法静态解析源码：{error}")
        package = _package_name(source_root, real)
        collector = _ImportCollector(source_root, package)
        collector.visit(tree)
        for path in collector.found:
            if path.resolve() not in seen:
                pending.append(path)
    return sorted(_relative(workspace, path) for path in seen)


def _imported_first_party_files(
    entrypoints: Sequence[str], workspace_root: Path
) -> set[str]:
    """启动只做导入的子进程，避免调用方已经导入的模块污染模块表。"""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-B", "-c", _CHILD, str(workspace_root), json.dumps(list(entrypoints))],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        _fail("实际加载入口失败")
    try:
        loaded = json.loads(completed.stdout)
    except json.JSONDecodeError:
        _fail("实际加载结果无法读取")
    if not isinstance(loaded, list) or any(not isinstance(item, str) for item in loaded):
        _fail("实际加载结果无法读取")
    return set(loaded)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_source_manifest(
    entrypoints: Sequence[str],
    *,
    workspace_root: Path,
) -> dict[str, object]:
    """在同一次调用内完成路径检查、静态闭包、实际加载核验与摘要。失败则不返回清单。"""
    if not isinstance(workspace_root, Path) or not workspace_root.is_absolute():
        _fail("工作区根必须是绝对路径")
    workspace = workspace_root.resolve()
    for dependency in _DEPENDENCY_PATHS:
        if not (workspace / dependency).is_file():
            _fail("工作区缺少固定的依赖文件")
    if not entrypoints:
        _fail("入口不得为空")
    resolved: list[Path] = []
    seen_real: set[Path] = set()
    for entry in entrypoints:
        if not isinstance(entry, str):
            _fail("入口必须是字符串")
        real = _resolve_entry(workspace, entry)
        if real in seen_real:
            _fail("入口的真实路径不得重复")
        seen_real.add(real)
        resolved.append(real)
    files = _closure(workspace, resolved)
    loaded = _imported_first_party_files(entrypoints, workspace)
    missing = set(entrypoints) - loaded
    if missing:
        _fail("入口未被实际加载")
    outside = loaded - set(files)
    if outside:
        _fail("实际加载的第一方源码超出了清单")
    version = sys.version_info
    manifest: dict[str, object] = {
        "schema": "source-manifest-v1",
        "entrypoints": sorted(entrypoints),
        "python_version": f"{version.major}.{version.minor}.{version.micro}",
        "files": [
            {"path": relative, "sha256": _sha256(workspace / relative)}
            for relative in files
        ],
        "dependency_files": [
            {"path": relative, "sha256": _sha256(workspace / relative)}
            for relative in _DEPENDENCY_PATHS
        ],
    }
    require_source_manifest(manifest)
    return manifest
