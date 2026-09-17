"""将冻结 manifest 子进程置于 macOS supervisor 下，并由父进程终结 measurement。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .experiment_record import load_manifested_measurement_record
from .manifest import (
    ExperimentPlan,
    derive_experiment_plan,
    load_experiment_manifest,
    load_probe_manifest,
)
from .policy import QuantizedStrategyArtifact, load_quantized_strategy
from .supervised_measurement import (
    SupervisedMeasurement,
    finalize_from_child_path,
    replace_with_final_measurement,
)
from .supervisor import SupervisorLimits, SupervisorReceipt, SupervisorStatus, supervise_command


class SupervisedExecutorError(ValueError):
    """父监督器、冻结 manifest、子进程临时记录或最终 measurement 不一致时抛出。"""


@dataclass(frozen=True)
class SupervisedExecutionResult:
    """父 supervisor 终结后的最终 measurement 与真实父进程回执。"""

    plan: ExperimentPlan
    receipt: SupervisorReceipt
    measurement: SupervisedMeasurement
    measurement_path: Path
    strategy_path: Path | None


def run_supervised_manifest_executor(
    *,
    experiment_manifest_path: str | Path,
    artifact_root: str | Path,
    working_directory: str | Path,
    runtime_git_commit: str,
    runtime_trainer_version: str,
    probe_manifest_path: str | Path | None = None,
    python_executable: str | Path = sys.executable,
) -> SupervisedExecutionResult:
    """监督一个固定的 manifest executor 子进程，并由父进程替换最终 measurement。"""

    experiment = load_experiment_manifest(experiment_manifest_path)
    probe = load_probe_manifest(probe_manifest_path) if probe_manifest_path is not None else None
    plan = derive_experiment_plan(experiment, probe)
    _validate_runtime_identity(plan, runtime_git_commit, runtime_trainer_version)
    root = _require_directory(artifact_root, "工件根目录")
    cwd = _require_directory(working_directory, "工作目录")
    executable = _require_python_executable(python_executable)
    child_measurement_path = root / plan.manifest.measurement_slot.relative_name
    strategy_path = (
        None
        if plan.manifest.strategy_slot is None
        else root / plan.manifest.strategy_slot.relative_name
    )
    command = [
        str(executable),
        "-m",
        "multiplayer_cfr.manifest_executor",
        "--experiment-manifest",
        str(Path(experiment_manifest_path).resolve()),
        "--artifact-root",
        str(root.resolve()),
        "--git-commit",
        runtime_git_commit,
        "--trainer-version",
        runtime_trainer_version,
        "--workspace-state",
        "clean",
    ]
    if probe_manifest_path is not None:
        command.extend(("--probe-manifest", str(Path(probe_manifest_path).resolve())))
    receipt = supervise_command(
        command,
        working_directory=cwd,
        artifact_root=root,
        limits=_supervisor_limits(plan),
    )
    artifact = _load_child_strategy(receipt, child_measurement_path, strategy_path)
    measurement = finalize_from_child_path(
        plan=plan,
        receipt=receipt,
        child_measurement_path=child_measurement_path,
        strategy=artifact,
    )
    final = replace_with_final_measurement(
        root,
        plan.manifest.measurement_slot.relative_name,
        measurement,
        maximum_bytes=plan.manifest.measurement_slot.maximum_bytes,
    )
    return SupervisedExecutionResult(
        plan=plan,
        receipt=receipt,
        measurement=final,
        measurement_path=child_measurement_path,
        strategy_path=strategy_path if artifact is not None else None,
    )


def _load_child_strategy(
    receipt: SupervisorReceipt,
    child_measurement_path: Path,
    strategy_path: Path | None,
) -> QuantizedStrategyArtifact | None:
    if receipt.status is not SupervisorStatus.COMPLETED:
        return None
    if not child_measurement_path.is_file():
        raise SupervisedExecutorError("受控子进程完成后未生成临时 measurement")
    child_measurement = load_manifested_measurement_record(child_measurement_path)
    if child_measurement.payload["strategy"] is None:
        return None
    if strategy_path is None or not strategy_path.is_file():
        raise SupervisedExecutorError("子进程记录声明策略但未生成量化策略工件")
    return load_quantized_strategy(strategy_path)


def _supervisor_limits(plan: ExperimentPlan) -> SupervisorLimits:
    return SupervisorLimits(
        cpu_limit_milliseconds=plan.manifest.cpu_limit_milliseconds,
        wall_time_limit_milliseconds=sum(
            stage.wall_time_milliseconds for stage in plan.manifest.stages
        ),
        rss_warning_bytes=plan.manifest.rss_warning_bytes,
        rss_hard_limit_bytes=plan.manifest.rss_hard_limit_bytes,
        retained_artifact_limit_bytes=plan.manifest.retained_artifact_limit_bytes,
    )


def _validate_runtime_identity(
    plan: ExperimentPlan, runtime_git_commit: str, runtime_trainer_version: str
) -> None:
    if (
        runtime_git_commit != plan.manifest.code_commit
        or runtime_trainer_version != plan.manifest.trainer_version
    ):
        raise SupervisedExecutorError("运行时代码身份与冻结 experiment manifest 不匹配")


def _require_directory(value: str | Path, label: str) -> Path:
    path = Path(value)
    if not path.is_dir() or path.is_symlink():
        raise SupervisedExecutorError(f"{label}必须是现有非链接目录")
    return path


def _require_python_executable(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise SupervisedExecutorError("Python 可执行文件必须是绝对常规可执行路径")
    return path
