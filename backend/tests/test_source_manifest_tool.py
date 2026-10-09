"""包外源码清单工具的夹具回归。

工作区是临时目录。不对真实仓库调用该工具，也不把返回的清单写入仓库。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.verification import SourceManifestError, require_source_manifest, source_manifest_digest


def _load_tool():
    path = Path(__file__).resolve().parents[1] / "tools" / "source_manifest.py"
    spec = importlib.util.spec_from_file_location("source_manifest_tool", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _workspace(root: Path) -> None:
    _write(root / "backend" / "pyproject.toml", "[project]\nname='fixture'\n")
    _write(root / "backend" / "uv.lock", "version = 1\n")


def test_temp_workspace_manifest_covers_the_import_closure(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _write(tmp_path / "backend" / "pkg" / "__init__.py", "")
    _write(
        tmp_path / "backend" / "pkg" / "helper.py",
        "VALUE = 1\n",
    )
    _write(
        tmp_path / "backend" / "pkg" / "entry.py",
        "import pkg.helper\n",
    )
    tool = _load_tool()

    def listed(root: Path) -> set[str]:
        return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}

    before = listed(tmp_path)
    manifest = tool.build_source_manifest(
        ["backend/pkg/entry.py"], workspace_root=tmp_path
    )
    after = listed(tmp_path)
    assert after == before
    normalized = require_source_manifest(manifest)
    assert normalized["entrypoints"] == ["backend/pkg/entry.py"]
    assert [row["path"] for row in normalized["dependency_files"]] == [
        "backend/pyproject.toml",
        "backend/uv.lock",
    ]
    paths = {row["path"] for row in normalized["files"]}
    assert paths == {
        "backend/pkg/__init__.py",
        "backend/pkg/entry.py",
        "backend/pkg/helper.py",
    }
    assert len(source_manifest_digest(normalized, algorithm="sha256")) == 64


def test_relative_import_entrypoint_loads_without_bytecode(tmp_path: Path) -> None:
    """包内相对导入必须能完成实际加载，并且工作区不出现字节码文件。"""
    _workspace(tmp_path)
    _write(tmp_path / "backend" / "fixturepkg" / "__init__.py", "")
    _write(tmp_path / "backend" / "fixturepkg" / "verification" / "__init__.py", "")
    _write(
        tmp_path / "backend" / "fixturepkg" / "verification" / "config.py",
        "VALUE = 1\n",
    )
    _write(
        tmp_path / "backend" / "fixturepkg" / "verification" / "runner.py",
        "from .config import VALUE\n",
    )
    tool = _load_tool()
    before = {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    manifest = tool.build_source_manifest(
        ["backend/fixturepkg/verification/runner.py"], workspace_root=tmp_path
    )
    after = {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert list(tmp_path.rglob("*.pyc")) == []
    assert [path for path in tmp_path.rglob("*") if path.name == "__pycache__"] == []
    assert {row["path"] for row in manifest["files"]} == {
        "backend/fixturepkg/__init__.py",
        "backend/fixturepkg/verification/__init__.py",
        "backend/fixturepkg/verification/config.py",
        "backend/fixturepkg/verification/runner.py",
    }


def test_aliased_non_literal_import_fails(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _write(tmp_path / "backend" / "pkg" / "__init__.py", "")
    _write(tmp_path / "backend" / "pkg" / "helper.py", "VALUE = 1\n")
    tool = _load_tool()
    sources = (
        "from importlib import import_module\nname = 'pkg.helper'\nimport_module(name)\n",
        "import importlib as il\nname = 'pkg.helper'\nil.import_module(name)\n",
        "from importlib import import_module as load\n"
        "target = load\n"
        "name = 'pkg.helper'\n"
        "target(name)\n",
    )
    for source in sources:
        _write(tmp_path / "backend" / "pkg" / "entry.py", source)
        with pytest.raises(SourceManifestError, match="非字面动态导入"):
            tool.build_source_manifest(["backend/pkg/entry.py"], workspace_root=tmp_path)
    _write(
        tmp_path / "backend" / "pkg" / "entry.py",
        "from importlib import import_module\nimport_module('pkg.helper')\n",
    )
    manifest = tool.build_source_manifest(
        ["backend/pkg/entry.py"], workspace_root=tmp_path
    )
    assert "backend/pkg/helper.py" in {row["path"] for row in manifest["files"]}
    assert list(tmp_path.rglob("*.pyc")) == []


def test_indirect_loader_paths_fail_without_being_called(tmp_path: Path) -> None:
    """函数里保留的反射、容器或 exec_module 路径，即使导入时不执行也要失败。"""
    _workspace(tmp_path)
    _write(tmp_path / "backend" / "pkg" / "__init__.py", "")
    tool = _load_tool()
    sources = (
        "import importlib\n"
        "def hidden():\n"
        "    return getattr(importlib, 'import_module')\n",
        "import importlib\n"
        "def hidden():\n"
        "    tools = [importlib.import_module]\n"
        "    return tools[0]\n",
        "def hidden(loader, module):\n"
        "    loader.exec_module(module)\n",
        "import importlib\n"
        "def hidden():\n"
        "    return importlib.__dict__['import_module']\n",
    )
    for source in sources:
        _write(tmp_path / "backend" / "pkg" / "entry.py", source)
        with pytest.raises(SourceManifestError, match="运行期代码加载"):
            tool.build_source_manifest(["backend/pkg/entry.py"], workspace_root=tmp_path)


def test_shadowed_entrypoint_is_not_treated_as_loaded(tmp_path: Path) -> None:
    """模块名被预先占用时，入口文件没有实际加载，不得返回清单。"""
    _workspace(tmp_path)
    _write(
        tmp_path / "backend" / "pkg" / "__init__.py",
        "import sys\n"
        "import types\n"
        "sys.modules['pkg.entry'] = types.ModuleType('pkg.entry')\n",
    )
    _write(tmp_path / "backend" / "pkg" / "entry.py", "VALUE = 1\n")
    tool = _load_tool()
    with pytest.raises(SourceManifestError, match="未被实际加载"):
        tool.build_source_manifest(["backend/pkg/entry.py"], workspace_root=tmp_path)


def test_loaded_module_outside_the_closure_returns_nothing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _write(tmp_path / "backend" / "pkg" / "__init__.py", "")
    _write(
        tmp_path / "backend" / "pkg" / "vendor" / "sneak.py",
        "VALUE = 1\n",
    )
    _write(
        tmp_path / "backend" / "pkg" / "helper.py",
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))\n"
        "import sneak\n",
    )
    _write(tmp_path / "backend" / "pkg" / "entry.py", "import pkg.helper\n")
    tool = _load_tool()
    with pytest.raises(SourceManifestError, match="超出"):
        tool.build_source_manifest(["backend/pkg/entry.py"], workspace_root=tmp_path)


def test_non_literal_import_and_path_escape_fail(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _write(tmp_path / "backend" / "pkg" / "__init__.py", "")
    _write(
        tmp_path / "backend" / "pkg" / "entry.py",
        "name = 'pkg.helper'\n__import__(name)\n",
    )
    tool = _load_tool()
    with pytest.raises(SourceManifestError):
        tool.build_source_manifest(["backend/pkg/entry.py"], workspace_root=tmp_path)
    with pytest.raises(SourceManifestError):
        tool.build_source_manifest(["../outside.py"], workspace_root=tmp_path)
    with pytest.raises(SourceManifestError):
        tool.build_source_manifest(
            ["backend/pkg/entry.py", "backend/pkg/entry.py"], workspace_root=tmp_path
        )


def test_package_rejects_a_hand_built_manifest_with_wrong_dependencies() -> None:
    manifest = {
        "schema": "source-manifest-v1",
        "entrypoints": ["backend/app/verification/runner.py"],
        "python_version": "3.12.0",
        "files": [
            {"path": "backend/app/verification/runner.py", "sha256": "ab" * 32},
        ],
        "dependency_files": [
            {"path": "backend/uv.lock", "sha256": "cd" * 32},
            {"path": "backend/pyproject.toml", "sha256": "ef" * 32},
        ],
    }
    with pytest.raises(SourceManifestError, match="依赖文件"):
        require_source_manifest(manifest)
