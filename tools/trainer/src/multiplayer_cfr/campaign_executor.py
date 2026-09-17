"""campaign 授权入口：先验证 preflight，再独占执行一个预注册 experiment。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .campaign import (
    CampaignAuthorization,
    CampaignManifest,
    acquire_campaign_lease,
    verify_campaign_preflight,
)
from .estimator_preflight import EstimatorAttestation, verify_attestation
from .manifest import (
    ExperimentManifest,
    ExperimentPlan,
    ProbeManifest,
    derive_experiment_plan,
    load_experiment_manifest_document,
    load_probe_manifest_document,
)
from .safeio import canonical_json_bytes
from .supervised_executor import SupervisedExecutionResult, run_supervised_manifest_executor


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
    preflight_attestation: EstimatorAttestation,
    authorization_id: str,
    experiment_manifest_path: str | Path,
    working_directory: str | Path,
    runtime_git_commit: str,
    runtime_trainer_version: str,
    probe_manifest_path: str | Path | None = None,
) -> CampaignExecutionResult:
    """在持有 campaign lease 的整个生命周期内执行一个预注册 authorization。"""

    verify_campaign_preflight(campaign, preflight_attestation)
    verify_attestation_identity = preflight_attestation
    verify_attestation(
        _preflight_spec_from_attestation(verify_attestation_identity),
        verify_attestation_identity,
    )
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
    _validate_authorization_budget(authorization, plan)
    root = Path(campaign_root)
    with acquire_campaign_lease(root, campaign, authorization_id) as lease:
        run_root = root / "runs" / authorization_id
        if run_root.exists():
            raise CampaignExecutorError("authorization 已有运行目录，campaign 不允许覆盖或重试")
        artifact_root = run_root / "artifacts"
        snapshot_root = run_root / "inputs"
        artifact_root.mkdir(parents=True)
        snapshot_root.mkdir()
        result = run_supervised_manifest_executor(
            experiment_manifest_path=experiment_manifest_path,
            artifact_root=artifact_root,
            execution_snapshot_root=snapshot_root,
            working_directory=working_directory,
            runtime_git_commit=runtime_git_commit,
            runtime_trainer_version=runtime_trainer_version,
            campaign_authorization_id=lease.authorization.authorization_id,
            campaign_experiment_identity=lease.authorization.experiment_manifest,
            probe_manifest_path=probe_manifest_path,
        )
        lease.finalize(
            status=result.receipt.status.value,
            supervisor_receipt_sha256=_receipt_sha256(result),
            final_measurement_sha256=result.measurement.sha256,
            final_inventory=[entry.as_payload() for entry in result.final_inventory],
        )
    return CampaignExecutionResult(authorization_id=authorization_id, result=result)


def _validate_authorization_budget(
    authorization: CampaignAuthorization, plan: ExperimentPlan
) -> None:
    requested_wall = sum(stage.wall_time_milliseconds for stage in plan.manifest.stages)
    if (
        plan.manifest.cpu_limit_milliseconds > authorization.cpu_reservation_milliseconds
        or requested_wall > authorization.wall_reservation_milliseconds
        or plan.manifest.retained_artifact_limit_bytes > authorization.artifact_reservation_bytes
    ):
        raise CampaignExecutorError("experiment 资源上限超过其 campaign authorization 预留")


def _preflight_spec_from_attestation(attestation: EstimatorAttestation):
    from .estimator_preflight import EstimatorPreflightSpec, PreflightIdentity

    payload = attestation.payload
    manifest = payload["preflight_manifest"]
    return EstimatorPreflightSpec(
        identity=PreflightIdentity(
            record_type=manifest["record_type"],
            schema_version=manifest["schema_version"],
            record_id=manifest["record_id"],
            sha256=manifest["sha256"],
            byte_length=manifest["byte_length"],
        ),
        git_commit=payload["code_identity"]["git_commit"],
        trainer_version=payload["code_identity"]["trainer_version"],
        sample_seeds=tuple(payload["sample_seeds"]),
        target_infosets=tuple(payload["target_infosets"]),
        regret_tolerance_micros=payload["regret_tolerance_micros"],
        strategy_sum_tolerance_micros=payload["strategy_sum_tolerance_micros"],
    )


def _receipt_sha256(result: SupervisedExecutionResult) -> str:
    receipt = result.measurement.payload["supervisor_receipt"]
    return sha256(canonical_json_bytes(receipt)).hexdigest()
