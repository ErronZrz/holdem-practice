"""冻结 manifest 驱动的离线实验编排，不创建进程或扩大预算。"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .control import RunLimits, run_controlled_training, run_n9_boundary_sample
from .evaluation import EvaluationStopped, ManifestedEvaluation, evaluate_manifested_plan
from .experiment_record import (
    ExperimentRecord,
    SupervisorIdentity,
    build_manifested_measurement_record,
    write_manifested_measurement_record,
)
from .manifest import ArtifactSlot, ExperimentPlan
from .policy import export_strategy, load_quantized_strategy


class OrchestrationError(ValueError):
    """manifest 驱动实验的阶段顺序、工件额度或监督器输入不符合契约时抛出。"""


_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")


@dataclass(frozen=True)
class SupervisorSession:
    """外部监督器向编排器提供的合作式观察口。"""

    identity: SupervisorIdentity
    monotonic_clock: Callable[[], float]
    rss_reader: Callable[[], int]
    rss_sampler_id: str
    git_commit: str
    workspace_state: str
    trainer_version: str
    cancellation_requested: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        if not callable(self.monotonic_clock) or not callable(self.rss_reader):
            raise OrchestrationError("监督器会话必须提供时钟和 RSS 读取器")
        if not isinstance(self.rss_sampler_id, str) or not self.rss_sampler_id:
            raise OrchestrationError("监督器会话必须提供 RSS 采样器标识")
        if (
            not isinstance(self.git_commit, str)
            or _COMMIT_PATTERN.fullmatch(self.git_commit) is None
        ):
            raise OrchestrationError("监督器会话必须提供完整 Git 提交")
        if self.workspace_state != "clean":
            raise OrchestrationError("实际实验监督器会话必须处于干净工作区")
        if (
            not isinstance(self.trainer_version, str)
            or _VERSION_PATTERN.fullmatch(self.trainer_version) is None
        ):
            raise OrchestrationError("监督器会话必须提供受控训练器版本")
        if self.cancellation_requested is not None and not callable(self.cancellation_requested):
            raise OrchestrationError("监督器取消检查器必须可调用")


@dataclass(frozen=True)
class ManifestedExperimentResult:
    """一次 manifest 驱动运行的策略、测量记录和阶段结果。"""

    record: ExperimentRecord
    strategy_path: Path | None
    measurement_path: Path


class _ArtifactLedger:
    """仅允许计划中预声明的策略与 measurement 槽位。"""

    def __init__(self, root: str | Path, plan: ExperimentPlan) -> None:
        self.root = Path(root)
        if not self.root.is_dir() or self.root.is_symlink():
            raise OrchestrationError("实验工件根目录必须是现有非链接目录")
        self.plan = plan
        self._slots = {
            "measurement": plan.manifest.measurement_slot,
        }
        if plan.manifest.strategy_slot is not None:
            self._slots["strategy"] = plan.manifest.strategy_slot
        reserved = sum(slot.maximum_bytes for slot in self._slots.values())
        if reserved > plan.manifest.retained_artifact_limit_bytes:
            raise OrchestrationError("预留工件槽位超过 manifest 总额度")
        for slot in self._slots.values():
            target = self.root / slot.relative_name
            if target.exists() or target.is_symlink():
                raise OrchestrationError("预声明工件目标已存在")
        self._committed: dict[str, int] = {}

    def slot(self, name: str) -> ArtifactSlot:
        try:
            return self._slots[name]
        except KeyError as error:
            raise OrchestrationError("实验计划未声明该工件槽位") from error

    def path(self, name: str) -> Path:
        return self.root / self.slot(name).relative_name

    def commit(self, name: str, actual_bytes: int) -> None:
        slot = self.slot(name)
        if name in self._committed or actual_bytes < 0 or actual_bytes > slot.maximum_bytes:
            raise OrchestrationError("工件提交不符合预留槽位")
        self._committed[name] = actual_bytes


def run_manifested_experiment(
    plan: ExperimentPlan,
    artifact_root: str | Path,
    supervisor: SupervisorSession,
) -> ManifestedExperimentResult:
    """按冻结计划顺序运行 A6/A7 或 N9 boundary，并仅写预声明工件。"""

    if not isinstance(plan, ExperimentPlan) or not isinstance(supervisor, SupervisorSession):
        raise OrchestrationError("实验只能接受已验证计划和外部监督器会话")
    _validate_runtime_code_identity(plan, supervisor)
    ledger = _ArtifactLedger(artifact_root, plan)
    manifest = plan.manifest
    if manifest.execution_kind == "n9-boundary-sample":
        return _run_n9(plan, ledger, supervisor)
    return _run_a6_a7(plan, ledger, supervisor)


def _validate_runtime_code_identity(plan: ExperimentPlan, supervisor: SupervisorSession) -> None:
    manifest = plan.manifest
    if (
        supervisor.git_commit != manifest.code_commit
        or supervisor.workspace_state != "clean"
        or supervisor.trainer_version != manifest.trainer_version
    ):
        raise OrchestrationError("运行时代码身份与冻结 experiment manifest 不匹配")


def _run_a6_a7(
    plan: ExperimentPlan,
    ledger: _ArtifactLedger,
    supervisor: SupervisorSession,
) -> ManifestedExperimentResult:
    config = plan.training_config
    if config is None:
        raise OrchestrationError("A6/A7 计划缺少训练配置")
    training = run_controlled_training(
        config,
        _run_limits(plan, "training"),
        monotonic_clock=supervisor.monotonic_clock,
        rss_reader=supervisor.rss_reader,
        rss_sampler_id=supervisor.rss_sampler_id,
        cancellation_requested=supervisor.cancellation_requested,
    )
    if training.result is None:
        return _write_record(plan, ledger, supervisor, training=training)

    strategy_slot = ledger.slot("strategy")
    strategy_path = ledger.path("strategy")
    export_can_continue = _stage_deadline(plan, supervisor, "export")
    export_strategy(strategy_path, training.result, trainer_version=plan.manifest.trainer_version)
    if not export_can_continue():
        raise OrchestrationError("导出阶段超过 manifest 墙钟预算，未生成测量记录")
    artifact = load_quantized_strategy(strategy_path)
    if artifact.identity.artifact_bytes > strategy_slot.maximum_bytes:
        raise OrchestrationError("导出策略超过 manifest 预留槽位")
    ledger.commit("strategy", artifact.identity.artifact_bytes)

    evaluation: ManifestedEvaluation | None = None
    if plan.manifest.profile_mode == "full-chance":
        try:
            evaluation = evaluate_manifested_plan(
                artifact,
                plan,
                profile_checkpoint=_evaluation_checkpoint(plan, supervisor, "profile"),
                probe_checkpoint=_evaluation_checkpoint(plan, supervisor, "probe"),
            )
        except EvaluationStopped as error:
            raise OrchestrationError("质量阶段被外部合作式检查停止，未生成测量记录") from error
    return _write_record(
        plan,
        ledger,
        supervisor,
        training=training,
        artifact=artifact,
        evaluation=evaluation,
        strategy_path=strategy_path,
    )


def _run_n9(
    plan: ExperimentPlan,
    ledger: _ArtifactLedger,
    supervisor: SupervisorSession,
) -> ManifestedExperimentResult:
    traverser = plan.manifest.n9_traverser
    if traverser is None:
        raise OrchestrationError("N9 boundary 计划缺少 traverser")
    boundary = run_n9_boundary_sample(
        master_seed=plan.manifest.master_seed,
        traverser=traverser,
        limits=_run_limits(plan, "boundary"),
        monotonic_clock=supervisor.monotonic_clock,
        rss_reader=supervisor.rss_reader,
        rss_sampler_id=supervisor.rss_sampler_id,
        cancellation_requested=supervisor.cancellation_requested,
    )
    return _write_record(plan, ledger, supervisor, boundary=boundary)


def _write_record(
    plan: ExperimentPlan,
    ledger: _ArtifactLedger,
    supervisor: SupervisorSession,
    *,
    training=None,
    boundary=None,
    artifact=None,
    evaluation=None,
    strategy_path: Path | None = None,
) -> ManifestedExperimentResult:
    measurement_can_continue = _stage_deadline(plan, supervisor, "measurement")
    record = build_manifested_measurement_record(
        plan=plan,
        supervisor=supervisor.identity,
        training=training,
        boundary=boundary,
        artifact=artifact,
        evaluation=evaluation,
    )
    if not measurement_can_continue():
        raise OrchestrationError("measurement 阶段超过 manifest 墙钟预算")
    measurement_slot = ledger.slot("measurement")
    written = write_manifested_measurement_record(
        ledger.root,
        measurement_slot.relative_name,
        record,
        maximum_bytes=measurement_slot.maximum_bytes,
    )
    if not measurement_can_continue():
        raise OrchestrationError("measurement 阶段超过 manifest 墙钟预算")
    ledger.commit("measurement", written.record_bytes)
    return ManifestedExperimentResult(
        record=written,
        strategy_path=strategy_path,
        measurement_path=ledger.path("measurement"),
    )


def _run_limits(plan: ExperimentPlan, stage: str) -> RunLimits:
    try:
        stage_budget = plan.stage_budgets[stage]
    except KeyError as error:
        raise OrchestrationError("manifest 缺少所需阶段预算") from error
    return RunLimits(
        stage=stage,
        wall_time_seconds=stage_budget.wall_time_milliseconds / 1000,
        rss_warning_bytes=plan.manifest.rss_warning_bytes,
        rss_hard_limit_bytes=plan.manifest.rss_hard_limit_bytes,
        retained_artifact_limit_bytes=plan.manifest.retained_artifact_limit_bytes,
    )


def _stage_deadline(
    plan: ExperimentPlan, supervisor: SupervisorSession, stage: str
) -> Callable[[], bool]:
    """按阶段墙钟预算返回"仍可继续"的合作式检查，同时响应外部取消与 RSS 预警。"""

    try:
        stage_budget = plan.stage_budgets[stage]
    except KeyError as error:
        raise OrchestrationError("manifest 缺少所需阶段预算") from error
    started_at = supervisor.monotonic_clock()

    def can_continue() -> bool:
        if supervisor.cancellation_requested is not None and supervisor.cancellation_requested():
            return False
        if supervisor.rss_reader() >= plan.manifest.rss_warning_bytes:
            return False
        return (
            supervisor.monotonic_clock() - started_at < stage_budget.wall_time_milliseconds / 1000
        )

    return can_continue


def _evaluation_checkpoint(
    plan: ExperimentPlan, supervisor: SupervisorSession, stage: str
) -> Callable[[int], bool]:
    can_continue = _stage_deadline(plan, supervisor, stage)

    def check(_: int) -> bool:
        return can_continue()

    return check
