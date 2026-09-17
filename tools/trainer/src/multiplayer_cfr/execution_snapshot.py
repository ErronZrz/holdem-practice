"""父端将已验证 manifest 固化为子进程专用执行快照。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .manifest import (
    ExperimentManifest,
    LoadedManifest,
    ManifestError,
    ManifestIdentity,
    ProbeManifest,
    load_experiment_manifest_document,
    load_probe_manifest_document,
)
from .safeio import MAX_TEXT_BYTES, SafeJsonError, write_canonical_json


class ExecutionSnapshotError(ValueError):
    """执行快照目录、manifest 身份或子进程重验证不符合冻结契约时抛出。"""


@dataclass(frozen=True)
class ExecutionSnapshot:
    """父端固定的 experiment/probe 输入文件与其内容身份。"""

    root: Path
    experiment_path: Path
    experiment_identity: ManifestIdentity
    probe_path: Path | None
    probe_identity: ManifestIdentity | None


def create_execution_snapshot(
    root: str | Path,
    experiment: LoadedManifest,
    probe: LoadedManifest | None,
) -> ExecutionSnapshot:
    """仅从父端已验证的规范字节创建新且独占的子进程输入快照。"""

    if not isinstance(experiment.value, ExperimentManifest):
        raise ExecutionSnapshotError("experiment 快照必须来自已验证 experiment manifest")
    if probe is not None and not isinstance(probe.value, ProbeManifest):
        raise ExecutionSnapshotError("probe 快照必须来自已验证 probe manifest")
    snapshot_root = Path(root)
    if not snapshot_root.is_dir() or snapshot_root.is_symlink() or any(snapshot_root.iterdir()):
        raise ExecutionSnapshotError("执行快照根目录必须是新建且为空的非链接目录")

    try:
        experiment_path, _ = write_canonical_json(
            snapshot_root,
            "experiment.json",
            experiment.payload,
            maximum_bytes=MAX_TEXT_BYTES,
        )
        reloaded_experiment = load_experiment_manifest_document(experiment_path)
        _require_document_identity(reloaded_experiment, experiment.value.identity, "experiment")
        if probe is None:
            return ExecutionSnapshot(
                root=snapshot_root,
                experiment_path=experiment_path,
                experiment_identity=experiment.value.identity,
                probe_path=None,
                probe_identity=None,
            )
        probe_path, _ = write_canonical_json(
            snapshot_root,
            "probe.json",
            probe.payload,
            maximum_bytes=MAX_TEXT_BYTES,
        )
        reloaded_probe = load_probe_manifest_document(probe_path)
        _require_document_identity(reloaded_probe, probe.value.identity, "probe")
    except (ManifestError, SafeJsonError) as error:
        raise ExecutionSnapshotError("无法创建并验证执行快照") from error
    return ExecutionSnapshot(
        root=snapshot_root,
        experiment_path=experiment_path,
        experiment_identity=experiment.value.identity,
        probe_path=probe_path,
        probe_identity=probe.value.identity,
    )


def verify_experiment_snapshot(path: str | Path, expected: ManifestIdentity) -> ExperimentManifest:
    """子进程在构造计划前重新读取 experiment snapshot 并严格比对父端身份。"""

    try:
        document = load_experiment_manifest_document(path)
    except ManifestError as error:
        raise ExecutionSnapshotError("无法读取 experiment 执行快照") from error
    _require_document_identity(document, expected, "experiment")
    assert isinstance(document.value, ExperimentManifest)
    return document.value


def verify_probe_snapshot(path: str | Path, expected: ManifestIdentity) -> ProbeManifest:
    """子进程在构造计划前重新读取 probe snapshot 并严格比对父端身份。"""

    try:
        document = load_probe_manifest_document(path)
    except ManifestError as error:
        raise ExecutionSnapshotError("无法读取 probe 执行快照") from error
    _require_document_identity(document, expected, "probe")
    assert isinstance(document.value, ProbeManifest)
    return document.value


def _require_document_identity(
    document: LoadedManifest, expected: ManifestIdentity, label: str
) -> None:
    value = document.value
    if not isinstance(value, (ExperimentManifest, ProbeManifest)) or value.identity != expected:
        raise ExecutionSnapshotError(f"{label} 执行快照身份与父端冻结输入不一致")
