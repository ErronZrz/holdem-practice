"""材料生成器的夹具回归。

随机源被替换为预定字节。测试结束即丢弃返回对象，不保存材料、种子或清单。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from app.verification import ProtocolAuditError, ProtocolSpecError, SourceManifestError

from .verification_helpers import hand_source_manifest, run_spec

_FORBIDDEN_IMPORTS = {"threading", "subprocess", "asyncio", "multiprocessing"}
_FORBIDDEN_SYMBOLS = {"PokerEngine", "create_strategy", "start_hand_with", "apply_action"}


def _load_generator():
    path = Path(__file__).resolve().parents[1] / "tools" / "material_generator.py"
    spec = importlib.util.spec_from_file_location("material_generator_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _generator_manifest() -> dict[str, object]:
    return hand_source_manifest("backend/tools/material_generator.py")


def test_generator_source_calls_urandom_and_avoids_concurrency() -> None:
    path = Path(__file__).resolve().parents[1] / "tools" / "material_generator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    saw_urandom = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "urandom"
            ):
                saw_urandom = True
            if isinstance(node.func, ast.Name) and node.func.id == "HeuristicStrategy":
                raise AssertionError("生成器不得构造基线策略")
    assert saw_urandom
    assert not imports & _FORBIDDEN_IMPORTS
    source = path.read_text(encoding="utf-8")
    for symbol in _FORBIDDEN_SYMBOLS:
        assert symbol not in source
    assert "HeuristicStrategy(" not in source


def test_second_read_failure_does_not_return_materials(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    calls: list[int] = []

    def fail_on_second(size: int) -> bytes:
        calls.append(size)
        if len(calls) == 2:
            raise OSError("预定失败")
        return b"\x00" * size

    monkeypatch.setattr(module.os, "urandom", fail_on_second)
    spec = run_spec(num_players=2, hands=1)
    with pytest.raises(OSError, match="预定失败"):
        module.generate_materials(spec, _generator_manifest())
    assert len(calls) == 2


def test_short_read_stops_without_another_call(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    calls: list[int] = []

    def short(size: int) -> bytes:
        calls.append(size)
        return b"\x00" * max(size - 1, 0)

    monkeypatch.setattr(module.os, "urandom", short)
    with pytest.raises(ProtocolAuditError):
        module.generate_materials(run_spec(num_players=2, hands=1), _generator_manifest())
    assert len(calls) == 1


def test_stubbed_bytes_can_build_a_discarded_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()

    def zeros(size: int) -> bytes:
        return b"\x00" * size

    monkeypatch.setattr(module.os, "urandom", zeros)
    spec = run_spec(num_players=2, hands=1)
    generated = module.generate_materials(spec, _generator_manifest())
    assert len(generated.bundle) == 1
    assert len(generated.bundle[0].entries) == 3 * 2 + 6
    assert generated.audit.commitment.generator_code_digest
    assert generated.audit.commitment.generation_started_at.endswith("Z")
    assert (
        generated.audit.commitment.generation_started_at
        <= generated.audit.commitment.generation_finished_at
    )


def test_wrong_generator_entrypoint_fails_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_generator()
    calls: list[int] = []

    def zeros(size: int) -> bytes:
        calls.append(size)
        return b"\x00" * size

    monkeypatch.setattr(module.os, "urandom", zeros)
    manifest = hand_source_manifest("backend/app/verification/runner.py")
    with pytest.raises(ProtocolSpecError):
        module.generate_materials(run_spec(num_players=2), manifest)
    assert calls == []
    with pytest.raises(SourceManifestError):
        module.generate_materials(run_spec(), {"schema": "source-manifest-v1"})
