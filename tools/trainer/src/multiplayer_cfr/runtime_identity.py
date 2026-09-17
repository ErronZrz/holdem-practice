"""实际工作树与解释器的父子双端身份核验。"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class RuntimeIdentityError(ValueError):
    """工作树、Git 状态或解释器身份不符合冻结 experiment 运行要求时抛出。"""


@dataclass(frozen=True)
class RuntimeIdentity:
    """从实际工作树和当前解释器读取的执行身份。"""

    worktree: Path
    git_commit: str
    python_executable: Path


def inspect_runtime_identity(worktree: str | Path) -> RuntimeIdentity:
    """只用固定 Git argv 核验实际 HEAD、干净工作树和解释器绝对路径。"""

    path = Path(worktree).resolve()
    if not path.is_dir() or path.is_symlink():
        raise RuntimeIdentityError("工作树必须是现有非链接目录")
    git_path = _git_executable()
    environment = {"PATH": os.defpath, "LC_ALL": "C", "LANG": "C"}
    commit = _git_output(git_path, path, ("rev-parse", "HEAD"), environment)
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise RuntimeIdentityError("实际 Git HEAD 不是完整小写提交")
    status = _git_output(
        git_path,
        path,
        ("status", "--porcelain=v1", "--untracked-files=all"),
        environment,
    )
    if status:
        raise RuntimeIdentityError("实际工作树必须干净")
    executable = Path(sys.executable).resolve()
    if not executable.is_file():
        raise RuntimeIdentityError("当前 Python 解释器路径不兼容")
    return RuntimeIdentity(worktree=path, git_commit=commit, python_executable=executable)


def controlled_child_environment() -> dict[str, str]:
    """为 manifest 子进程提供最小、确定性的 Python 环境，不继承调用方注入变量。"""

    return {
        "PATH": os.defpath,
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def verify_child_runtime_identity(
    *,
    worktree: str | Path,
    expected_git_commit: str,
    expected_python_executable: str | Path,
) -> RuntimeIdentity:
    """子进程在 manifest 派生前重验父端观测到的工作树与解释器身份。"""

    identity = inspect_runtime_identity(worktree)
    expected_executable = Path(expected_python_executable).resolve()
    if (
        identity.git_commit != expected_git_commit
        or identity.python_executable != expected_executable
    ):
        raise RuntimeIdentityError("子进程实际工作树或解释器身份与父端不一致")
    return identity


def _git_executable() -> str:
    path = Path("/usr/bin/git")
    if not path.is_file() or path.is_symlink():
        raise RuntimeIdentityError("macOS Git 可执行文件不可用")
    return str(path)


def _git_output(
    executable: str,
    worktree: Path,
    arguments: tuple[str, ...],
    environment: dict[str, str],
) -> str:
    try:
        result = subprocess.run(
            (executable, "-C", str(worktree), *arguments),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeIdentityError("无法读取实际 Git 工作树身份") from error
    return result.stdout.strip()
