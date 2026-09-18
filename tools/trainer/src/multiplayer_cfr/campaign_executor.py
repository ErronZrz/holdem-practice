"""campaign 授权入口：先验证 preflight，再独占执行一个预注册 experiment。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .artifact_inventory import ArtifactInventoryError, remove_declared_artifacts
from .campaign import (
    CampaignAuthorization,
    CampaignError,
    CampaignManifest,
    acquire_campaign_lease,
    require_authorization_within_reservation,
    require_campaign_preflight_files,
)
from .estimator_preflight import EstimatorPreflightError
from .manifest import (
    ExperimentManifest,
    ExperimentPlan,
    ProbeManifest,
    derive_experiment_plan,
    load_experiment_manifest_document,
    load_probe_manifest_document,
)
from .safeio import canonical_json_bytes
from .supervised_executor import (
    SupervisedExecutionResult,
    inventory_slots_for_plan,
    run_supervised_manifest_executor,
)


class CampaignExecutorError(ValueError):
    """campaign authorization、preflight 或受监督 experiment 不符合冻结执行契约时抛出。"""


@dataclass(frozen=True)
class CampaignExecutionResult:
    """单个不可重试 authorization 的最终父监督结果。"""

    authorization_id: str
    result: SupervisedExecutionResult


def run_campaign_authorization(
    *,
    campaign_root: str | Path,
    campaign: CampaignManifest,
    authorization_id: str,
    experiment_manifest_path: str | Path,
    preflight_spec_path: str | Path,
    preflight_attestation_path: str | Path,
    working_directory: str | Path,
    runtime_git_commit: str,
    runtime_trainer_version: str,
    probe_manifest_path: str | Path | None = None,
) -> CampaignExecutionResult:
    """在持有 campaign lease 的整个生命周期内执行一个预注册 authorization。"""

    document = load_experiment_manifest_document(experiment_manifest_path)
    experiment = document.value
    probe_document = (
        load_probe_manifest_document(probe_manifest_path)
        if probe_manifest_path is not None
        else None
    )
    probe = None if probe_document is None else probe_document.value
    if not isinstance(experiment, ExperimentManifest) or (
        probe is not None and not isinstance(probe, ProbeManifest)
    ):
        raise CampaignExecutorError("campaign authorization manifest 类型不兼容")
    plan = derive_experiment_plan(experiment, probe)
    authorization = next(
        (item for item in campaign.authorizations if item.authorization_id == authorization_id),
        None,
    )
    if authorization is None or experiment.identity != authorization.experiment_manifest:
        raise CampaignExecutorError("authorization 与 experiment manifest 身份不匹配")
    _require_authorization_gate(
        campaign, authorization, plan, preflight_spec_path, preflight_attestation_path
    )
    root = Path(campaign_root)
    with acquire_campaign_lease(root, campaign, authorization_id) as lease:
        artifact_root: Path | None = None
        try:
            _, artifact_root, snapshot_root = lease.create_run_directories()
            result = run_supervised_manifest_executor(
                experiment_manifest_path=experiment_manifest_path,
                artifact_root=artifact_root,
                execution_snapshot_root=snapshot_root,
                working_directory=working_directory,
                runtime_git_commit=runtime_git_commit,
                runtime_trainer_version=runtime_trainer_version,
                campaign_lease=lease,
                preflight_spec_path=preflight_spec_path,
                preflight_attestation_path=preflight_attestation_path,
                probe_manifest_path=probe_manifest_path,
            )
        except BaseException:
            lease.finalize(
                status=_failure_status(artifact_root, plan),
                supervisor_receipt_sha256=None,
                final_measurement_sha256=None,
                final_inventory=[],
            )
            raise
        lease.finalize(
            status=result.receipt.status.value,
            supervisor_receipt_sha256=_receipt_sha256(result),
            final_measurement_sha256=result.measurement.sha256,
            final_inventory=[entry.as_payload() for entry in result.final_inventory],
        )
    return CampaignExecutionResult(authorization_id=authorization_id, result=result)


def _failure_status(artifact_root: Path | None, plan: ExperimentPlan) -> str:
    """异常退出时按声明槽位清理残留工件；无法安全清理则记为清单失败。"""

    if artifact_root is None or not artifact_root.is_dir():
        return "failed"
    try:
        remove_declared_artifacts(artifact_root, inventory_slots_for_plan(plan))
    except ArtifactInventoryError:
        return "inventory-failed"
    return "failed"


def _require_authorization_gate(
    campaign: CampaignManifest,
    authorization: CampaignAuthorization,
    plan: ExperimentPlan,
    preflight_spec_path: str | Path,
    preflight_attestation_path: str | Path,
) -> None:
    """在获取 lease 之前完成资源预留与 preflight 校验，门禁失败不消耗一次性授权。"""

    try:
        require_authorization_within_reservation(authorization, plan, campaign)
        require_campaign_preflight_files(campaign, preflight_spec_path, preflight_attestation_path)
    except (CampaignError, EstimatorPreflightError) as error:
        raise CampaignExecutorError("campaign authorization 门禁未通过") from error


def _receipt_sha256(result: SupervisedExecutionResult) -> str:
    receipt = result.measurement.payload["supervisor_receipt"]
    return sha256(canonical_json_bytes(receipt)).hexdigest()
