"""由外部 supervisor 启动的 manifest 子进程执行器。"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from .experiment_record import SupervisorIdentity
from .manifest import derive_experiment_plan, load_experiment_manifest, load_probe_manifest
from .orchestration import SupervisorSession, run_manifested_experiment
from .supervisor import SUPERVISOR_ID, SUPERVISOR_VERSION


class ManifestExecutorError(ValueError):
    """受控子进程的 manifest、参数或工件根目录不符合执行契约时抛出。"""


def main(arguments: list[str] | None = None) -> int:
    """执行一个已冻结 manifest；最终 measurement 仍由父 supervisor 替换写入。"""

    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--experiment-manifest", required=True)
    parser.add_argument("--probe-manifest")
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument("--trainer-version", required=True)
    parser.add_argument("--workspace-state", required=True, choices=("clean",))
    options = parser.parse_args(arguments)

    experiment = load_experiment_manifest(options.experiment_manifest)
    probe = load_probe_manifest(options.probe_manifest) if options.probe_manifest else None
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
