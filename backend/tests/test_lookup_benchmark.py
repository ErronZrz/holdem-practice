"""实时 lookup 的真实产物实测（显式 opt-in，默认整轮测试不会触发）。

运行方式（需要自行提供产物根目录，代码不猜测任何路径）：

    HOLDEM_LOOKUP_BENCHMARK=1 HOLDEM_ARTIFACT_ROOT=<产物根目录> \\
        uv run pytest -q -s tests/test_lookup_benchmark.py

这是**只读的本机性能观测**：不写回、不移动任何工件，不启动训练，不消耗任何授权。
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.strategy.abstraction import ABSTRACTION_GAME_VERSION
from app.strategy.artifact import ArtifactIdentity, LookupRegistry, load_lookup_registry
from app.strategy.lookup_budget import (
    DECISION_BUDGET_MS,
    PLAYER_COUNT_RANGE,
    RECOMMENDED_DECISION_SAMPLES,
    PlayerCountCoverage,
    artifact_load_summary,
    build_report,
    summarize_decision_latencies,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    os.environ.get("HOLDEM_LOOKUP_BENCHMARK") != "1",
    reason="真实产物测量是显式 opt-in：需设置 HOLDEM_LOOKUP_BENCHMARK=1 与 HOLDEM_ARTIFACT_ROOT",
)

# 在全新解释器中加载产物，读取该进程的峰值常驻内存；macOS 返回字节、Linux 返回 KB。
_CHILD_SCRIPT = """\
import json, resource, sys, time
from app.strategy.artifact import load_strategy_artifact

started = time.perf_counter()
artifact = load_strategy_artifact(sys.argv[1])
elapsed_ms = (time.perf_counter() - started) * 1000.0
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({
    "cold_load_ms": elapsed_ms,
    "peak_rss_bytes": peak if sys.platform == "darwin" else peak * 1024,
    "player_count": artifact.game.player_count,
    "infoset_count": len(artifact.infosets),
    "sha256": artifact.identity.sha256,
    "byte_length": artifact.identity.byte_length,
}))
"""


def _artifact_root() -> Path:
    raw = os.environ.get("HOLDEM_ARTIFACT_ROOT")
    if not raw:
        pytest.skip("未提供 HOLDEM_ARTIFACT_ROOT：不猜测路径，跳过实测")
    root = Path(raw)
    if not root.is_dir():
        pytest.skip(f"产物根目录不存在：{root}")
    return root


def _measure_cold_load(path: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD_SCRIPT, str(path)],
        capture_output=True,
        text=True,
        cwd=str(_BACKEND_ROOT),
    )
    if completed.returncode != 0:
        raise AssertionError(f"子进程加载失败：{path}\n{completed.stderr}")
    return json.loads(completed.stdout.strip().splitlines()[-1])


def _measure_latencies(
    registry: LookupRegistry,
    table,
    player_count: int,
    samples: int,
) -> list[float]:
    inputs = [(item.actor, item.rank, item.history) for item in table.artifact.infosets]
    durations: list[float] = []
    for index in range(samples):
        actor, rank, history = inputs[index % len(inputs)]
        started = time.perf_counter()
        outcome = registry.lookup(
            game_version=ABSTRACTION_GAME_VERSION,
            player_count=player_count,
            relative_actor=actor,
            own_rank=rank,
            canonical_public_history=history,
        )
        durations.append((time.perf_counter() - started) * 1000.0)
        if not outcome.is_hit:
            raise AssertionError(f"查表未命中：{outcome.status} / {outcome.reasons}")
    return durations


def test_measure_lookup_budget_on_real_artifacts() -> None:
    root = _artifact_root()
    paths = sorted(root.rglob("strategy.json"))
    assert paths, f"目录下没有任何策略产物：{root}"

    measured_loads: dict[Path, dict] = {}
    for path in paths:
        measured_loads[path] = _measure_cold_load(path)

    # 每个有产物的人数只取路径字典序第一份装载，避免同人数重复注册。
    representative: dict[int, Path] = {}
    for path in paths:
        count = measured_loads[path]["player_count"]
        representative.setdefault(count, path)

    registry = load_lookup_registry([representative[count] for count in sorted(representative)])
    samples = int(os.environ.get("HOLDEM_LOOKUP_SAMPLES", RECOMMENDED_DECISION_SAMPLES))

    latencies = []
    for count in sorted(representative):
        table = registry.by_player_count[count]
        latencies.append(
            summarize_decision_latencies(
                count, _measure_latencies(registry, table, count, samples)
            )
        )

    uncovered: list[PlayerCountCoverage] = []
    for count in PLAYER_COUNT_RANGE:
        if count in representative:
            continue
        outcome = registry.lookup(
            game_version=ABSTRACTION_GAME_VERSION,
            player_count=count,
            relative_actor=0,
            own_rank=0,
            canonical_public_history="-",
        )
        assert not outcome.is_hit
        assert outcome.action_units is None
        assert outcome.fallback is not None
        uncovered.append(
            PlayerCountCoverage(
                player_count=count,
                status=outcome.status,
                abstraction_key=outcome.abstraction_key,
                reasons=outcome.reasons,
                fallback=outcome.fallback,
            )
        )

    report = build_report(
        environment={
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "artifact_root": str(root),
            "decision_samples_per_player_count": str(samples),
            "measured_at_local_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        loads=[
            artifact_load_summary(
                identity=ArtifactIdentity(
                    sha256=measured_loads[representative[count]]["sha256"],
                    byte_length=measured_loads[representative[count]]["byte_length"],
                ),
                player_count=count,
                infoset_count=measured_loads[representative[count]]["infoset_count"],
                cold_load_ms=measured_loads[representative[count]]["cold_load_ms"],
                peak_rss_bytes=measured_loads[representative[count]]["peak_rss_bytes"],
            )
            for count in sorted(representative)
        ],
        latencies=latencies,
        uncovered=uncovered,
    )

    supplementary = {
        str(path.relative_to(root)): measured_loads[path] for path in paths
    }
    print("=== 全部产物的冷加载观测（补充证据，不进入逐人数报告） ===")
    print(json.dumps(supplementary, ensure_ascii=False, indent=2, sort_keys=True))
    print("=== 逐人数报告 ===")
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))

    # 报告口径：逐人数完整覆盖 2–9，已测人数必须与"确实存在产物"的人数一致。
    assert set(report.measured_player_counts) == set(representative)
    for summary in report.latencies:
        assert summary.decision_count == samples
        assert summary.max_ms < DECISION_BUDGET_MS
        assert summary.timeout_count == 0
    assert report.all_within_hard_budget is True
    assert sorted(report.measured_player_counts + report.uncovered_player_counts) == list(
        PLAYER_COUNT_RANGE
    )
