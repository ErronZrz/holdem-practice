"""将冻结 manifest 子进程置于 macOS supervisor 下，并由父进程终结 measurement。"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from .artifact_inventory import (
    ArtifactInventoryError,
    InventoryEntry,
    InventorySlot,
    inventory_declared_artifacts,
    remove_declared_artifacts,
    require_empty_artifact_root,
)
from .campaign import CampaignError, CampaignLease, verify_active_lease
from .execution_snapshot import ExecutionSnapshot, create_execution_snapshot
from .experiment_record import load_manifested_measurement_record
from .manifest import (
    ExperimentManifest,
    ExperimentPlan,
    ProbeManifest,
    derive_experiment_plan,
    load_experiment_manifest_document,
    load_probe_manifest_document,
)
from .policy import QuantizedStrategyArtifact, load_quantized_strategy
from .runtime_identity import (
    RuntimeIdentityError,
    controlled_child_environment,
    inspect_runtime_identity,
)
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
    """父 supervisor 终结后的最终 measurement、快照与封存清单。"""

    plan: ExperimentPlan
    receipt: SupervisorReceipt
    snapshot: ExecutionSnapshot
    measurement: SupervisedMeasurement
    measurement_path: Path
    strategy_path: Path | None
    pre_final_inventory: tuple[InventoryEntry, ...]
    final_inventory: tuple[InventoryEntry, ...]


def run_supervised_manifest_executor(
    *,
    experiment_manifest_path: str | Path,
    artifact_root: str | Path,
    execution_snapshot_root: str | Path,
    working_directory: str | Path,
    runtime_git_commit: str,
    runtime_trainer_version: str,
    campaign_lease: CampaignLease | None = None,
    probe_manifest_path: str | Path | None = None,
    python_executable: str | Path = sys.executable,
) -> SupervisedExecutionResult:
    """监督一个固定的 manifest executor 子进程，并由父进程替换最终 measurement。"""

    experiment_document = load_experiment_manifest_document(experiment_manifest_path)
    probe_document = (
        load_probe_manifest_document(probe_manifest_path)
        if probe_manifest_path is not None
        else None
    )
    experiment = experiment_document.value
    probe = None if probe_document is None else probe_document.value
    if not isinstance(experiment, ExperimentManifest) or (
        probe is not None and not isinstance(probe, ProbeManifest)
    ):
        raise SupervisedExecutorError("父端 manifest document 类型不兼容")
    plan = derive_experiment_plan(experiment, probe)
    _require_campaign_authorization(plan, campaign_lease)
    cwd = _require_directory(working_directory, "工作目录")
    try:
        runtime = inspect_runtime_identity(cwd)
    except RuntimeIdentityError as error:
        raise SupervisedExecutorError("无法核验父端实际工作树和解释器身份") from error
    _validate_runtime_identity(
        plan,
        runtime_git_commit,
        runtime_trainer_version,
        actual_git_commit=runtime.git_commit,
    )
    root = require_empty_artifact_root(artifact_root)
    snapshot_root = _require_directory(execution_snapshot_root, "执行快照根目录")
    if campaign_lease is not None:
        _require_lease_paths(campaign_lease, root, snapshot_root)
    snapshot = create_execution_snapshot(snapshot_root, experiment_document, probe_document)
    executable = _require_python_executable(python_executable)
    if executable.resolve() != runtime.python_executable:
        raise SupervisedExecutorError("受控子进程解释器与父端实际解释器不一致")
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
        "--experiment-snapshot",
        str(snapshot.experiment_path),
        "--experiment-manifest-id",
        snapshot.experiment_identity.manifest_id,
        "--experiment-manifest-sha256",
        snapshot.experiment_identity.sha256,
        "--experiment-manifest-bytes",
        str(snapshot.experiment_identity.byte_length),
        "--artifact-root",
        str(root.resolve()),
        "--git-commit",
        runtime_git_commit,
        "--trainer-version",
        runtime_trainer_version,
        "--workspace-state",
        "clean",
        "--worktree",
        str(runtime.worktree),
        "--python-executable",
        str(runtime.python_executable),
    ]
    if snapshot.probe_path is not None and snapshot.probe_identity is not None:
        command.extend(
            (
                "--probe-snapshot",
                str(snapshot.probe_path),
                "--probe-manifest-id",
                snapshot.probe_identity.manifest_id,
                "--probe-manifest-sha256",
                snapshot.probe_identity.sha256,
                "--probe-manifest-bytes",
                str(snapshot.probe_identity.byte_length),
            )
        )
    receipt = supervise_command(
        command,
        working_directory=cwd,
        artifact_root=root,
        limits=_supervisor_limits(plan),
        environment=controlled_child_environment(),
    )
    artifact = _load_child_strategy(receipt, child_measurement_path, strategy_path)
    slots = inventory_slots_for_plan(plan)
    required_pre_final = {plan.manifest.measurement_slot.relative_name}
    if artifact is not None and plan.manifest.strategy_slot is not None:
        required_pre_final.add(plan.manifest.strategy_slot.relative_name)
    try:
        if receipt.status is SupervisorStatus.COMPLETED:
            pre_final_inventory = inventory_declared_artifacts(
                root,
                slots,
                required_names=frozenset(required_pre_final),
            )
        else:
            remove_declared_artifacts(root, slots)
            pre_final_inventory = ()
            required_pre_final = {plan.manifest.measurement_slot.relative_name}
    except ArtifactInventoryError as error:
        raise SupervisedExecutorError("子进程退出后的工件清单不符合计划") from error
    measurement = finalize_from_child_path(
        plan=plan,
        receipt=receipt,
        child_measurement_path=child_measurement_path,
        strategy=artifact,
        execution_snapshot=snapshot,
        pre_final_inventory=pre_final_inventory,
    )
    final = replace_with_final_measurement(
        root,
        plan.manifest.measurement_slot.relative_name,
        measurement,
        maximum_bytes=plan.manifest.measurement_slot.maximum_bytes,
    )
    try:
        final_inventory = inventory_declared_artifacts(
            root,
            slots,
            required_names=frozenset(required_pre_final),
        )
    except ArtifactInventoryError as error:
        raise SupervisedExecutorError("最终 measurement 替换后的工件清单不符合计划") from error
    return SupervisedExecutionResult(
        plan=plan,
        receipt=receipt,
        snapshot=snapshot,
        measurement=final,
        measurement_path=child_measurement_path,
        strategy_path=strategy_path if artifact is not None else None,
        pre_final_inventory=pre_final_inventory,
        final_inventory=final_inventory,
    )


def _require_campaign_authorization(
    plan: ExperimentPlan, campaign_lease: CampaignLease | None
) -> None:
    """A6/A7 必须携带由 campaign 签发的有效 lease；N9 允许独立执行。"""

    if campaign_lease is None:
        if plan.manifest.execution_kind == "n9-boundary-sample":
            return
        raise SupervisedExecutorError("A6/A7 必须通过冻结 campaign authorization 执行")
    try:
        verify_active_lease(campaign_lease)
    except CampaignError as error:
        raise SupervisedExecutorError("campaign authorization lease 无效") from error
    if (
        campaign_lease.authorization.experiment_manifest != plan.manifest.identity
        or campaign_lease.campaign.git_commit != plan.manifest.code_commit
        or campaign_lease.campaign.trainer_version != plan.manifest.trainer_version
    ):
        raise SupervisedExecutorError("campaign authorization 与冻结 experiment 不一致")


def _require_lease_paths(
    lease: CampaignLease, artifact_root: Path, snapshot_root: Path
) -> None:
    """工件与快照目录必须落在这条 authorization 独占的 run 目录之内。"""

    if not lease.owns_path(artifact_root) or not lease.owns_path(snapshot_root):
        raise SupervisedExecutorError("工件或快照目录越出 authorization run 目录")


def inventory_slots_for_plan(plan: ExperimentPlan) -> tuple[InventorySlot, ...]:
    slots = [
        InventorySlot(
            relative_name=plan.manifest.measurement_slot.relative_name,
            maximum_bytes=plan.manifest.measurement_slot.maximum_bytes,
        )
    ]
    if plan.manifest.strategy_slot is not None:
        slots.append(
            InventorySlot(
                relative_name=plan.manifest.strategy_slot.relative_name,
                maximum_bytes=plan.manifest.strategy_slot.maximum_bytes,
            )
        )
    return tuple(slots)


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
    plan: ExperimentPlan,
    runtime_git_commit: str,
    runtime_trainer_version: str,
    *,
    actual_git_commit: str,
) -> None:
    if (
        runtime_git_commit != actual_git_commit
        or actual_git_commit != plan.manifest.code_commit
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
