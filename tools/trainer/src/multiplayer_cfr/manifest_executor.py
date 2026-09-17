"""由外部 supervisor 启动的 manifest 子进程执行器。"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from .execution_snapshot import (
    ExecutionSnapshotError,
    verify_experiment_snapshot,
    verify_probe_snapshot,
)
from .experiment_record import SupervisorIdentity
from .manifest import ManifestIdentity, derive_experiment_plan
from .orchestration import SupervisorSession, run_manifested_experiment
from .runtime_identity import RuntimeIdentityError, verify_child_runtime_identity
from .supervisor import SUPERVISOR_ID, SUPERVISOR_VERSION


class ManifestExecutorError(ValueError):
    """受控子进程的 manifest、参数或工件根目录不符合执行契约时抛出。"""


def main(arguments: list[str] | None = None) -> int:
    """执行一个已冻结 manifest；最终 measurement 仍由父 supervisor 替换写入。"""

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--experiment-snapshot", required=True)
    parser.add_argument("--experiment-manifest-id", required=True)
    parser.add_argument("--experiment-manifest-sha256", required=True)
    parser.add_argument("--experiment-manifest-bytes", required=True, type=int)
    parser.add_argument("--probe-snapshot")
    parser.add_argument("--probe-manifest-id")
    parser.add_argument("--probe-manifest-sha256")
    parser.add_argument("--probe-manifest-bytes", type=int)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--trainer-version", required=True)
    parser.add_argument("--workspace-state", required=True, choices=("clean",))
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--python-executable", required=True)
    options = parser.parse_args(arguments)

    experiment_identity = ManifestIdentity(
        manifest_type="multiplayer-cfr-experiment",
        schema_version=1,
        manifest_id=options.experiment_manifest_id,
        sha256=options.experiment_manifest_sha256,
        byte_length=options.experiment_manifest_bytes,
    )
    probe_values = (
        options.probe_snapshot,
        options.probe_manifest_id,
        options.probe_manifest_sha256,
        options.probe_manifest_bytes,
    )
    if any(value is None for value in probe_values) and any(
        value is not None for value in probe_values
    ):
        raise ManifestExecutorError("probe 执行快照与全部身份参数必须同时提供或同时省略")
    try:
        experiment = verify_experiment_snapshot(options.experiment_snapshot, experiment_identity)
        probe = (
            None
            if options.probe_snapshot is None
            else verify_probe_snapshot(
                options.probe_snapshot,
                ManifestIdentity(
                    manifest_type="multiplayer-cfr-threshold-probes",
                    schema_version=1,
                    manifest_id=options.probe_manifest_id,
                    sha256=options.probe_manifest_sha256,
                    byte_length=options.probe_manifest_bytes,
                ),
            )
        )
    except (ExecutionSnapshotError, TypeError, ValueError) as error:
        raise ManifestExecutorError("执行快照身份不兼容") from error
    try:
        child_runtime = verify_child_runtime_identity(
            worktree=options.worktree,
            expected_git_commit=options.git_commit,
            expected_python_executable=options.python_executable,
        )
    except RuntimeIdentityError as error:
        raise ManifestExecutorError("子进程实际运行时代码身份不兼容") from error
    if child_runtime.git_commit != experiment.code_commit:
        raise ManifestExecutorError("子进程实际 Git HEAD 与冻结 experiment manifest 不一致")
    plan = derive_experiment_plan(experiment, probe)
    artifact_root = Path(options.artifact_root)
    if not artifact_root.is_dir() or artifact_root.is_symlink():
        raise ManifestExecutorError("工件根目录必须是现有非链接目录")
    session = SupervisorSession(
        identity=SupervisorIdentity(
            supervisor_id=SUPERVISOR_ID,
            supervisor_version=SUPERVISOR_VERSION,
            rss_scope="process-tree",
            enforcement_mode="external-hard-limit",
        ),
        monotonic_clock=time.monotonic,
        rss_reader=lambda: 0,
        rss_sampler_id="parent-supervisor-receipt-v1",
        git_commit=options.git_commit,
        workspace_state=options.workspace_state,
        trainer_version=options.trainer_version,
    )
    run_manifested_experiment(plan, artifact_root, session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
