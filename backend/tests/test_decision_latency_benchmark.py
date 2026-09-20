"""修复后 2–9 人实时决策延迟的显式 opt-in 实测入口（默认整轮测试不触发）。

运行方式（不需要任何外部产物，代码不猜测任何路径）：

    HOLDEM_DECISION_LATENCY_BENCHMARK=1 \\
        uv run pytest -q -s tests/test_decision_latency_benchmark.py

可选环境变量：

- ``HOLDEM_DECISION_SAMPLES``：每个**人数**的决策样本量（默认取建议样本量）；
- ``HOLDEM_DECISION_FOCUS_SAMPLES``：每个（补充场景, 人数）的决策样本量；
- ``HOLDEM_DECISION_SCENARIOS``：补充场景名单，``none`` 表示只跑基础矩阵。

这是**只读的本机性能观测**：只打印报告，不写回、不移动任何工件，不启动训练，不消耗授权。
"""

import json
import os
import sys
import time

import pytest

from app.poker.actions import LegalActions
from app.poker.state import GameState
from app.strategy.decision_latency import (
    BASELINE_SCENARIO,
    DECISION_STREETS,
    SCENARIO_FOCUS_PLAYER_COUNTS,
    SUPPLEMENTARY_DECISION_SAMPLES,
    SUPPLEMENTARY_SCENARIOS,
    DecisionCoverageGap,
    DecisionScenarioLatency,
    PlayerCountDecisionLatency,
    build_decision_latency_report,
    summarize_player_count_latency,
)
from app.strategy.lookup_budget import PLAYER_COUNT_RANGE, RECOMMENDED_DECISION_SAMPLES

from .decision_latency_states import (
    DEEP_STARTING_STACK,
    SHALLOW_STARTING_STACK,
    STREET_BY_LABEL,
    baseline_cases,
    build_state,
    build_strong_draw_state,
    make_strategy,
    measure_decision_latencies,
)

_ENV_SWITCH = "HOLDEM_DECISION_LATENCY_BENCHMARK"
_ENV_SAMPLES = "HOLDEM_DECISION_SAMPLES"
_ENV_FOCUS_SAMPLES = "HOLDEM_DECISION_FOCUS_SAMPLES"
_ENV_SCENARIOS = "HOLDEM_DECISION_SCENARIOS"

_SCENARIO_DESCRIPTIONS = {
    "deep-stack": "深筹码（起始筹码 200 BB）下的逐街决策",
    "shallow-stack": "浅筹码（起始筹码 20 BB）下的逐街决策",
    "strong-draw": "强听牌路径下的翻牌与转牌决策",
    "long-session": "同一河牌局面上的连续决策流（长会话代理）",
}
_SCENARIO_STREETS = {
    "deep-stack": DECISION_STREETS,
    "shallow-stack": DECISION_STREETS,
    "strong-draw": ("flop", "turn"),
    "long-session": ("river",),
}
_SCENARIO_STACKS = {
    "deep-stack": DEEP_STARTING_STACK,
    "shallow-stack": SHALLOW_STARTING_STACK,
}


def _opt_in_enabled() -> bool:
    """是否已显式开启实测；默认关闭，保证整轮常规测试不受影响。"""
    return os.environ.get(_ENV_SWITCH) == "1"


pytestmark = pytest.mark.skipif(
    not _opt_in_enabled(),
    reason="实时决策延迟实测是显式 opt-in：需设置 HOLDEM_DECISION_LATENCY_BENCHMARK=1",
)


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise AssertionError(f"{name} 必须是正整数")
    return value


def _selected_scenarios() -> tuple[str, ...]:
    raw = os.environ.get(_ENV_SCENARIOS)
    if raw is None:
        return SUPPLEMENTARY_SCENARIOS
    names = tuple(item.strip() for item in raw.split(",") if item.strip())
    if names == ("none",):
        return ()
    unknown = set(names) - set(SUPPLEMENTARY_SCENARIOS)
    if unknown:
        raise AssertionError(f"未知场景：{sorted(unknown)}")
    return names


def _allocate(total: int, slots: int) -> list[int]:
    """把样本均分到各单元，余数自首个单元起逐个加一，保证总数恰为 total。"""
    base, remainder = divmod(total, slots)
    return [base + (1 if index < remainder else 0) for index in range(slots)]


def _scenario_states(
    scenario: str, player_count: int
) -> dict[str, list[tuple[GameState, LegalActions]]]:
    """按场景给出每个街的局面对集合。"""
    streets = _SCENARIO_STREETS[scenario]
    if scenario in _SCENARIO_STACKS:
        built = baseline_cases(player_count, _SCENARIO_STACKS[scenario])
        return {street: built[street] for street in streets}
    if scenario == "strong-draw":
        return {
            street: [build_strong_draw_state(player_count, STREET_BY_LABEL[street])]
            for street in streets
        }
    # 长会话：同一个河牌局面上的连续决策流
    return {
        street: [build_state(player_count, STREET_BY_LABEL[street])] for street in streets
    }


def _measure_player_count(
    player_count: int,
    states_by_street: dict[str, list[tuple[GameState, LegalActions]]],
    samples_per_street: list[int],
) -> PlayerCountDecisionLatency:
    """测量一个人数在各街上的决策耗时并汇总。"""
    strategy = make_strategy(player_count)
    samples_by_group: dict[str, list[float]] = {}
    for index, street in enumerate(states_by_street):
        samples_by_group[street] = measure_decision_latencies(
            strategy, states_by_street[street], samples_per_street[index]
        )
    return summarize_player_count_latency(player_count, samples_by_group)


def _build_scenario(scenario: str, focus_samples: int) -> DecisionScenarioLatency:
    """测量一个补充场景：只在聚焦人数上给实测值，其余人数显式声明未覆盖。"""
    streets = _SCENARIO_STREETS[scenario]
    samples_per_street = _allocate(focus_samples, len(streets))
    entries = tuple(
        _measure_player_count(
            player_count,
            _scenario_states(scenario, player_count),
            samples_per_street,
        )
        for player_count in SCENARIO_FOCUS_PLAYER_COUNTS
    )
    uncovered = tuple(
        DecisionCoverageGap(
            dimension="player-count",
            key=str(count),
            reasons=("场景层按验收口径聚焦重点人数，未覆盖该人数",),
        )
        for count in PLAYER_COUNT_RANGE
        if count not in SCENARIO_FOCUS_PLAYER_COUNTS
    ) + tuple(
        DecisionCoverageGap(dimension="street", key=street, reasons=("该场景不覆盖此街",))
        for street in DECISION_STREETS
        if street not in streets
    )
    return DecisionScenarioLatency(
        scenario=scenario,
        description=_SCENARIO_DESCRIPTIONS[scenario],
        streets=streets,
        player_counts=entries,
        uncovered=uncovered,
    )


def _print_table(title: str, entries: tuple[PlayerCountDecisionLatency, ...]) -> None:
    print(f"=== {title} ===")
    print("| 人数 | 样本 | 中位数 ms | p95 ms | p99 ms | max ms | 超时数 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for entry in entries:
        summary = entry.summary
        print(
            f"| {summary.player_count} | {summary.decision_count} "
            f"| {summary.median_ms:.4f} | {summary.p95_ms:.4f} "
            f"| {summary.p99_ms:.4f} | {summary.max_ms:.4f} | {summary.timeout_count} |"
        )
    print("| 街 | 样本 | 中位数 ms | p95 ms | p99 ms | max ms | 超时数 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for entry in entries:
        for group in entry.groups:
            print(
                f"| {entry.player_count}-{group.label} | {group.decision_count} "
                f"| {group.median_ms:.4f} | {group.p95_ms:.4f} "
                f"| {group.p99_ms:.4f} | {group.max_ms:.4f} | {group.timeout_count} |"
            )


def test_measure_decision_latency_on_this_machine() -> None:
    started_at = time.perf_counter()
    samples = _positive_int_env(_ENV_SAMPLES, RECOMMENDED_DECISION_SAMPLES)
    focus_samples = _positive_int_env(_ENV_FOCUS_SAMPLES, SUPPLEMENTARY_DECISION_SAMPLES)
    scenarios = _selected_scenarios()

    samples_per_street = _allocate(samples, len(DECISION_STREETS))
    baseline = DecisionScenarioLatency(
        scenario=BASELINE_SCENARIO,
        description="2–9 人 × 各街的修复后启发式单次决策",
        streets=DECISION_STREETS,
        player_counts=tuple(
            _measure_player_count(player_count, baseline_cases(player_count), samples_per_street)
            for player_count in PLAYER_COUNT_RANGE
        ),
        uncovered=(),
    )
    supplements = tuple(_build_scenario(scenario, focus_samples) for scenario in scenarios)

    report = build_decision_latency_report(
        environment={
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "measured_at_local_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "decision_samples_per_player_count": str(samples),
            "scenario_samples_per_player_count": str(focus_samples),
            "state_source": "deterministic-construction",
        },
        baseline=baseline,
        supplements=supplements,
    )
    elapsed_seconds = time.perf_counter() - started_at

    print(
        f"被计时路径：{report.measured_path}；"
        f"查表接入状态：{report.lookup_runtime_integration}（{report.lookup_runtime_integration_note}）"
    )
    print(
        f"硬预算 {report.decision_budget_ms} ms（达到即失败）；"
        f"建议余量 p95<{report.p95_guidance_ms} ms、p99<{report.p99_guidance_ms} ms（仅提示）"
    )
    _print_table("逐人数判定（基础矩阵）", report.baseline.player_counts)
    for scenario in report.supplements:
        print(f"补充场景 {scenario.scenario}：{scenario.description}")
        print(f"未覆盖人数：{scenario.uncovered_player_counts}（只声明状态，不给延迟值）")
        _print_table(f"补充场景 {scenario.scenario}", scenario.player_counts)
    print("=== 报告 JSON ===")
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True))
    print(f"本轮实测本机耗时：{elapsed_seconds:.1f} s")

    assert report.baseline.measured_player_counts == PLAYER_COUNT_RANGE
    assert report.baseline.uncovered == ()
    for entry in report.baseline.player_counts:
        assert entry.summary.decision_count == samples
        assert tuple(group.label for group in entry.groups) == DECISION_STREETS
        assert sum(group.decision_count for group in entry.groups) == samples
    for entry in report.baseline.player_counts:
        assert entry.summary.within_hard_budget is True, (
            f"人数 {entry.player_count} 观察到超预算决策："
            f"max={entry.summary.max_ms}ms、超时数={entry.summary.timeout_count}"
        )
    assert report.all_within_hard_budget is True
    assert report.timeout_player_counts == ()
