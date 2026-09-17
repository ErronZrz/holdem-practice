"""由父 supervisor 写入的最终实验 measurement。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .experiment_record import ExperimentRecord, load_manifested_measurement_record
from .manifest import ExperimentPlan
from .policy import QuantizedStrategyArtifact
from .safeio import (
    MAX_TEXT_BYTES,
    SafeJsonError,
    canonical_json_bytes,
    load_canonical_json,
    replace_canonical_json,
    sha256_identity,
)
from .supervisor import SupervisorReceipt, SupervisorStatus

SUPERVISED_MEASUREMENT_TYPE = "multiplayer-cfr-supervised-measurement"
SUPERVISED_MEASUREMENT_SCHEMA_VERSION = 1


class SupervisedMeasurementError(ValueError):
    """父 supervisor 最终 measurement 的身份、回执或临时结果不一致时抛出。"""


@dataclass(frozen=True)
class SupervisedMeasurement:
    """父 supervisor 写入的最终 measurement 及其规范字节身份。"""

    payload: dict[str, object]
    sha256: str
    record_bytes: int


def finalize_measurement(
    *,
    plan: ExperimentPlan,
    receipt: SupervisorReceipt,
    child_measurement: ExperimentRecord | None,
    strategy: QuantizedStrategyArtifact | None,
) -> SupervisedMeasurement:
    """将父监督回执与可选子进程临时记录绑定为最终 measurement。"""

    if not isinstance(plan, ExperimentPlan) or not isinstance(receipt, SupervisorReceipt):
        raise SupervisedMeasurementError("最终 measurement 必须关联实验计划和父监督器回执")
    if child_measurement is None:
        if strategy is not None:
            raise SupervisedMeasurementError("没有子进程记录时不能关联策略")
    else:
        _validate_child_measurement(plan, child_measurement, strategy)
    payload = {
        "schema_version": SUPERVISED_MEASUREMENT_SCHEMA_VERSION,
        "record_type": SUPERVISED_MEASUREMENT_TYPE,
        "experiment_manifest": plan.manifest.identity.as_payload(),
        "supervisor_receipt": _receipt_payload(receipt),
        "child_execution": (
            None
            if child_measurement is None
            else {
                "sha256": child_measurement.sha256,
                "record_bytes": child_measurement.record_bytes,
                "payload": child_measurement.payload,
            }
        ),
        "strategy": _strategy_payload(strategy),
    }
    _validate_payload(payload)
    raw_bytes = canonical_json_bytes(payload)
    digest, byte_length = sha256_identity(raw_bytes)
    return SupervisedMeasurement(payload=payload, sha256=digest, record_bytes=byte_length)


def finalize_from_child_path(
    *,
    plan: ExperimentPlan,
    receipt: SupervisorReceipt,
    child_measurement_path: str | Path,
    strategy: QuantizedStrategyArtifact | None,
) -> SupervisedMeasurement:
    """安全回读子进程临时记录后构造父监督器最终 measurement。"""

    if receipt.status is not SupervisorStatus.COMPLETED:
        return finalize_measurement(
            plan=plan,
            receipt=receipt,
            child_measurement=None,
            strategy=None,
        )
    try:
        child = load_manifested_measurement_record(child_measurement_path)
    except Exception as error:
        raise SupervisedMeasurementError("受控子进程没有留下有效临时 measurement") from error
    return finalize_measurement(
        plan=plan,
        receipt=receipt,
        child_measurement=child,
        strategy=strategy,
    )


def replace_with_final_measurement(
    root: str | Path,
    relative_name: str,
    measurement: SupervisedMeasurement,
    *,
    maximum_bytes: int,
) -> SupervisedMeasurement:
    """由父 supervisor 原子替换子进程的临时 measurement，并严格回读。"""

    if not isinstance(measurement, SupervisedMeasurement):
        raise SupervisedMeasurementError("写入对象必须是父监督器最终 measurement")
    _validate_payload(measurement.payload)
    try:
        _, raw_bytes = replace_canonical_json(
            root,
            relative_name,
            measurement.payload,
            maximum_bytes=maximum_bytes,
        )
    except SafeJsonError as error:
        raise SupervisedMeasurementError("无法原子写入父监督器最终 measurement") from error
    loaded = load_supervised_measurement(Path(root) / relative_name)
    if loaded.sha256 != measurement.sha256 or loaded.record_bytes != len(raw_bytes):
        raise SupervisedMeasurementError("最终 measurement 回读身份不一致")
    return loaded


def load_supervised_measurement(path: str | Path) -> SupervisedMeasurement:
    """安全读取由父 supervisor 写入的最终 measurement。"""

    try:
        payload, raw_bytes = load_canonical_json(path, maximum_bytes=MAX_TEXT_BYTES)
    except SafeJsonError as error:
        raise SupervisedMeasurementError("无法安全读取父监督器最终 measurement") from error
    _validate_payload(payload)
    digest, byte_length = sha256_identity(raw_bytes)
    return SupervisedMeasurement(payload=payload, sha256=digest, record_bytes=byte_length)


def _validate_child_measurement(
    plan: ExperimentPlan,
    child: ExperimentRecord,
    strategy: QuantizedStrategyArtifact | None,
) -> None:
    expected_identity = plan.manifest.identity.as_payload()
    if child.payload["experiment_manifest"] != expected_identity:
        raise SupervisedMeasurementError("子进程 measurement 与 experiment manifest 不匹配")
    child_strategy = child.payload["strategy"]
    if child_strategy is None:
        if strategy is not None:
            raise SupervisedMeasurementError("子进程未声明策略却传入量化策略")
        return
    if strategy is None or not isinstance(child_strategy, dict):
        raise SupervisedMeasurementError("子进程策略记录与量化策略不一致")
    if (
        child_strategy.get("sha256") != strategy.identity.sha256
        or child_strategy.get("artifact_bytes") != strategy.identity.artifact_bytes
    ):
        raise SupervisedMeasurementError("子进程策略身份与父进程量化回读不一致")


def _receipt_payload(receipt: SupervisorReceipt) -> dict[str, object]:
    return {
        "supervisor_id": receipt.supervisor_id,
        "supervisor_version": receipt.supervisor_version,
        "status": receipt.status.value,
        "stop_reason": receipt.stop_reason.value,
        "exit_code": receipt.exit_code,
        "wall_time_milliseconds": receipt.wall_time_milliseconds,
        "cpu_time_milliseconds": receipt.cpu_time_milliseconds,
        "peak_rss_bytes": receipt.peak_rss_bytes,
        "initial_artifact_bytes": receipt.initial_artifact_bytes,
        "final_artifact_bytes": receipt.final_artifact_bytes,
        "warning_triggered": receipt.warning_triggered,
        "terminated_with_signal": receipt.terminated_with_signal,
        "monitored_pids": list(receipt.monitored_pids),
    }


def _strategy_payload(artifact: QuantizedStrategyArtifact | None) -> dict[str, object] | None:
    if artifact is None:
        return None
    return {
        "sha256": artifact.identity.sha256,
        "artifact_bytes": artifact.identity.artifact_bytes,
    }


def _validate_payload(value: object) -> None:
    record = _exact_mapping(
        value,
        {
            "schema_version",
            "record_type",
            "experiment_manifest",
            "supervisor_receipt",
            "child_execution",
            "strategy",
        },
        "父监督器最终 measurement",
    )
    if (
        record["schema_version"] != SUPERVISED_MEASUREMENT_SCHEMA_VERSION
        or record["record_type"] != SUPERVISED_MEASUREMENT_TYPE
    ):
        raise SupervisedMeasurementError("父监督器最终 measurement 版本不兼容")
    _validate_identity(record["experiment_manifest"])
    _validate_receipt(record["supervisor_receipt"])
    _validate_child_execution(record["child_execution"], record["strategy"])


def _validate_identity(value: object) -> None:
    identity = _exact_mapping(
        value,
        {"manifest_type", "schema_version", "manifest_id", "sha256", "byte_length"},
        "experiment manifest 身份",
    )
    if (
        identity["manifest_type"] != "multiplayer-cfr-experiment"
        or not isinstance(identity["schema_version"], int)
        or not isinstance(identity["manifest_id"], str)
        or not isinstance(identity["sha256"], str)
        or len(identity["sha256"]) != 64
        or not isinstance(identity["byte_length"], int)
    ):
        raise SupervisedMeasurementError("experiment manifest 身份不兼容")


def _validate_receipt(value: object) -> None:
    receipt = _exact_mapping(
        value,
        {
            "supervisor_id",
            "supervisor_version",
            "status",
            "stop_reason",
            "exit_code",
            "wall_time_milliseconds",
            "cpu_time_milliseconds",
            "peak_rss_bytes",
            "initial_artifact_bytes",
            "final_artifact_bytes",
            "warning_triggered",
            "terminated_with_signal",
            "monitored_pids",
        },
        "supervisor receipt",
    )
    if receipt["supervisor_id"] != "macos-process-tree-supervisor":
        raise SupervisedMeasurementError("supervisor receipt 标识不兼容")
    if receipt["status"] not in {"completed", "stopped", "failed"}:
        raise SupervisedMeasurementError("supervisor receipt 状态不兼容")
    for field in (
        "wall_time_milliseconds",
        "cpu_time_milliseconds",
        "peak_rss_bytes",
        "initial_artifact_bytes",
        "final_artifact_bytes",
    ):
        if (
            isinstance(receipt[field], bool)
            or not isinstance(receipt[field], int)
            or receipt[field] < 0
        ):
            raise SupervisedMeasurementError("supervisor receipt 资源字段不兼容")
    if not isinstance(receipt["warning_triggered"], bool):
        raise SupervisedMeasurementError("supervisor receipt 警告字段不兼容")
    if not isinstance(receipt["monitored_pids"], list) or any(
        isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0
        for pid in receipt["monitored_pids"]
    ):
        raise SupervisedMeasurementError("supervisor receipt PID 字段不兼容")


def _validate_child_execution(value: object, strategy: object) -> None:
    if value is None:
        if strategy is not None:
            raise SupervisedMeasurementError("没有子进程记录时不能关联策略")
        return
    child = _exact_mapping(value, {"sha256", "record_bytes", "payload"}, "child execution")
    if not isinstance(child["sha256"], str) or len(child["sha256"]) != 64:
        raise SupervisedMeasurementError("child execution SHA-256 不兼容")
    if isinstance(child["record_bytes"], bool) or not isinstance(child["record_bytes"], int):
        raise SupervisedMeasurementError("child execution 字节数不兼容")
    if not isinstance(child["payload"], dict):
        raise SupervisedMeasurementError("child execution payload 不兼容")
    child_strategy = child["payload"].get("strategy")
    if child_strategy != strategy:
        raise SupervisedMeasurementError("父最终 measurement 的策略与子进程记录不一致")


def _exact_mapping(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise SupervisedMeasurementError(f"{label}字段不匹配")
    return value
