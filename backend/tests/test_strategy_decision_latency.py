"""决策延迟测量口径的回归测试（小样本合成用例，不触发任何真实测量）。"""

import inspect

import pytest
from pydantic import ValidationError

import app.strategy.decision_latency as decision_latency_module
from app.poker.cards import Card, Rank, Suit
from app.poker.state import GameState, PlayerState, Street
from app.strategy.decision_latency import (
    BASELINE_SCENARIO,
    DECISION_STREETS,
    LOOKUP_RUNTIME_INTEGRATION_STATUS,
    MEASURED_DECISION_PATH,
    REPORTED_ENVIRONMENT_KEYS,
    SCENARIO_FOCUS_PLAYER_COUNTS,
    SUPPLEMENTARY_DECISION_SAMPLES,
    SUPPLEMENTARY_SCENARIOS,
    DecisionCoverageGap,
    DecisionLatencyError,
    DecisionLatencyReport,
    DecisionScenarioLatency,
    LatencyGroupSummary,
    PlayerCountDecisionLatency,
    build_decision_latency_report,
    summarize_latency_group,
    summarize_player_count_latency,
)
from app.strategy.heuristic import HeuristicStrategy, draw_outs
from app.strategy.lookup_budget import (
    DECISION_BUDGET_MS,
    MEASUREMENT_SCOPE,
    P95_GUIDANCE_MS,
    P99_GUIDANCE_MS,
    PLAYER_COUNT_RANGE,
    RECOMMENDED_DECISION_SAMPLES,
    percentile_ms,
    summarize_decision_latencies,
)

from .decision_latency_states import (
    BASELINE_VARIANTS,
    BOARD_SIZE,
    STREET_LABELS,
    STREET_ORDER,
    baseline_cases,
    build_state,
    build_strong_draw_state,
)

_FULL_DECK = [Card(rank, suit) for suit in Suit for rank in Rank]

# 合成用例里出现的预算数值字面量白名单：用于确认新模块没有另立一套预算。
_FORBIDDEN_SOURCE_TOKENS = ("100.0", "50.0", "80.0", "10_000", "10000")
_WRITE_TOKENS = (
    "open(",
    "write_text",
    "write_bytes",
    "unlink",
    "shutil",
    "os.remove",
    "json.dump(",
)


def _samples(rounds: int, start: float = 1.0) -> list[float]:
    return [start + index for index in range(rounds)]


def _entry(
    player_count: int,
    *,
    rounds: int = 4,
    streets: tuple[str, ...] = DECISION_STREETS,
    start: float = 1.0,
) -> PlayerCountDecisionLatency:
    return summarize_player_count_latency(
        player_count,
        {street: _samples(rounds, start) for street in streets},
    )


def _player_count_gaps(counts: tuple[int, ...]) -> tuple[DecisionCoverageGap, ...]:
    return tuple(
        DecisionCoverageGap(dimension="player-count", key=str(count), reasons=("合成用例",))
        for count in PLAYER_COUNT_RANGE
        if count not in counts
    )


def _street_gaps(streets: tuple[str, ...]) -> tuple[DecisionCoverageGap, ...]:
    return tuple(
        DecisionCoverageGap(dimension="street", key=street, reasons=("合成用例",))
        for street in DECISION_STREETS
        if street not in streets
    )


def _scenario(
    scenario: str,
    counts: tuple[int, ...],
    streets: tuple[str, ...] = DECISION_STREETS,
) -> DecisionScenarioLatency:
    return DecisionScenarioLatency(
        scenario=scenario,
        description="合成用例",
        streets=streets,
        player_counts=tuple(_entry(count, streets=streets) for count in counts),
        uncovered=_player_count_gaps(counts) + _street_gaps(streets),
    )


def _report(
    *,
    baseline: DecisionScenarioLatency | None = None,
    supplements: tuple[DecisionScenarioLatency, ...] = (),
) -> DecisionLatencyReport:
    if baseline is None:
        baseline = _scenario(BASELINE_SCENARIO, PLAYER_COUNT_RANGE)
    return build_decision_latency_report(
        environment={"platform": "test", "python": "3.13"},
        baseline=baseline,
        supplements=supplements,
    )


# ---------------------------------------------------------------- 分组分位与超时


def test_group_summary_uses_the_nearest_rank() -> None:
    summary = summarize_latency_group("river", _samples(100))

    assert summary.decision_count == 100
    assert summary.median_ms == 50.5
    assert summary.p95_ms == 95.0
    assert summary.p99_ms == 99.0
    assert summary.max_ms == 100.0
    assert summary.p95_ms == percentile_ms(_samples(100), 0.95)


def test_group_summary_counts_the_budget_boundary_as_a_timeout() -> None:
    summary = summarize_latency_group("flop", [0.1, DECISION_BUDGET_MS])

    assert summary.timeout_count == 1
    assert summary.within_hard_budget is False


def test_group_summary_matches_the_existing_timeout_rule() -> None:
    samples = [0.2, 0.3, 0.4, DECISION_BUDGET_MS, 0.5]
    group = summarize_latency_group("turn", samples)
    existing = summarize_decision_latencies(6, samples)

    assert group.timeout_count == existing.timeout_count
    assert group.within_hard_budget == existing.within_hard_budget
    assert group.max_ms == existing.max_ms
    assert group.p95_ms == existing.p95_ms


def test_group_summary_rejects_invalid_input() -> None:
    with pytest.raises(DecisionLatencyError):
        summarize_latency_group("flop", [])
    with pytest.raises(DecisionLatencyError):
        summarize_latency_group("flop", [-1.0])
    with pytest.raises(DecisionLatencyError):
        summarize_latency_group("", [1.0])


def test_group_summary_rejects_an_inconsistent_budget_flag() -> None:
    with pytest.raises(ValidationError):
        LatencyGroupSummary(
            label="river",
            decision_count=1,
            median_ms=1.0,
            p95_ms=1.0,
            p99_ms=1.0,
            max_ms=1.0,
            timeout_count=1,
            within_hard_budget=True,
        )


# ---------------------------------------------------------------- 逐人数汇总


def test_player_count_summary_merges_the_groups() -> None:
    entry = _entry(6, rounds=4)

    assert entry.player_count == 6
    assert tuple(group.label for group in entry.groups) == DECISION_STREETS
    assert entry.summary.decision_count == 16
    assert sum(group.decision_count for group in entry.groups) == 16
    assert entry.summary.median_ms == 2.5
    assert entry.summary.max_ms == 4.0
    assert entry.summary.within_hard_budget is True


@pytest.mark.parametrize("player_count", PLAYER_COUNT_RANGE)
def test_player_count_summary_supports_every_player_count(player_count: int) -> None:
    entry = _entry(player_count)

    assert entry.player_count == player_count
    assert entry.summary.player_count == player_count
    assert entry.summary.decision_count == 4 * len(DECISION_STREETS)


def test_player_count_summary_rejects_invalid_input() -> None:
    for player_count in (1, 10):
        with pytest.raises(DecisionLatencyError):
            summarize_player_count_latency(player_count, {"flop": [1.0]})
    with pytest.raises(DecisionLatencyError):
        summarize_player_count_latency(6, {})
    with pytest.raises(DecisionLatencyError):
        summarize_player_count_latency(6, {"flop": []})


def test_player_count_entry_rejects_a_group_total_mismatch() -> None:
    with pytest.raises(ValidationError):
        PlayerCountDecisionLatency(
            player_count=6,
            summary=summarize_decision_latencies(6, [1.0, 2.0, 3.0, 4.0]),
            groups=(
                LatencyGroupSummary(
                    label="preflop",
                    decision_count=3,
                    median_ms=2.0,
                    p95_ms=3.0,
                    p99_ms=3.0,
                    max_ms=3.0,
                    timeout_count=0,
                    within_hard_budget=True,
                ),
            ),
        )


# ---------------------------------------------------------------- 逐人数完整性


def test_scenario_requires_every_player_count_to_be_accounted_for() -> None:
    with pytest.raises(ValidationError):
        DecisionScenarioLatency(
            scenario=BASELINE_SCENARIO,
            description="合成用例",
            streets=DECISION_STREETS,
            player_counts=(_entry(6),),
            uncovered=(),
        )


def test_scenario_rejects_a_count_both_measured_and_uncovered() -> None:
    with pytest.raises(ValidationError, match="同时被判为已测与未覆盖"):
        DecisionScenarioLatency(
            scenario=BASELINE_SCENARIO,
            description="合成用例",
            streets=DECISION_STREETS,
            player_counts=(_entry(6),),
            uncovered=_player_count_gaps((6,))
            + (
                DecisionCoverageGap(
                    dimension="player-count", key="6", reasons=("合成用例",)
                ),
            ),
        )


def test_scenario_rejects_duplicate_measured_counts() -> None:
    with pytest.raises(ValidationError, match="不能重复"):
        DecisionScenarioLatency(
            scenario=BASELINE_SCENARIO,
            description="合成用例",
            streets=DECISION_STREETS,
            player_counts=(_entry(6), _entry(6)),
            uncovered=_player_count_gaps((6,)),
        )


def test_scenario_rejects_unknown_scenario_or_bad_streets() -> None:
    with pytest.raises(ValidationError, match="未知场景标识"):
        _scenario("mystery", PLAYER_COUNT_RANGE)
    with pytest.raises(ValidationError, match="固定顺序"):
        _scenario(BASELINE_SCENARIO, PLAYER_COUNT_RANGE, ("flop", "preflop"))
    with pytest.raises(ValidationError, match="已知街"):
        _scenario(BASELINE_SCENARIO, PLAYER_COUNT_RANGE, ("flop", "showdown"))


def test_scenario_requires_street_gaps_to_match() -> None:
    with pytest.raises(ValidationError, match="街缺口"):
        DecisionScenarioLatency(
            scenario="strong-draw",
            description="合成用例",
            streets=("flop", "turn"),
            player_counts=tuple(
                _entry(count, streets=("flop", "turn")) for count in SCENARIO_FOCUS_PLAYER_COUNTS
            ),
            uncovered=_player_count_gaps(SCENARIO_FOCUS_PLAYER_COUNTS),
        )


def test_scenario_rejects_groups_outside_the_declared_streets() -> None:
    with pytest.raises(ValidationError, match="分组标签"):
        DecisionScenarioLatency(
            scenario="strong-draw",
            description="合成用例",
            streets=("flop", "turn"),
            player_counts=tuple(_entry(count) for count in SCENARIO_FOCUS_PLAYER_COUNTS),
            uncovered=_player_count_gaps(SCENARIO_FOCUS_PLAYER_COUNTS)
            + _street_gaps(("flop", "turn")),
        )


def test_scenario_exposes_measured_and_uncovered_counts() -> None:
    scenario = _scenario("strong-draw", SCENARIO_FOCUS_PLAYER_COUNTS, ("flop", "turn"))

    assert scenario.measured_player_counts == SCENARIO_FOCUS_PLAYER_COUNTS
    assert scenario.uncovered_player_counts == (2, 3, 4, 5, 8)
    assert set(scenario.measured_player_counts) | set(scenario.uncovered_player_counts) == set(
        PLAYER_COUNT_RANGE
    )


def test_uncovered_gap_carries_no_latency_value() -> None:
    assert set(DecisionCoverageGap.model_fields) == {"dimension", "key", "reasons"}
    with pytest.raises(ValidationError):
        DecisionCoverageGap(
            dimension="player-count", key="6", reasons=("合成用例",), median_ms=1.0
        )
    with pytest.raises(ValidationError):
        DecisionCoverageGap(dimension="player-count", key="6", reasons=())


# ---------------------------------------------------------------- 报告装配


def test_report_exposes_the_path_and_the_lookup_status() -> None:
    report = _report()

    assert report.scope == MEASUREMENT_SCOPE
    assert report.measured_path == MEASURED_DECISION_PATH
    assert report.lookup_runtime_integration == LOOKUP_RUNTIME_INTEGRATION_STATUS
    assert "未建模" in report.lookup_runtime_integration_note
    assert report.decision_budget_ms == DECISION_BUDGET_MS
    assert report.p95_guidance_ms == P95_GUIDANCE_MS
    assert report.p99_guidance_ms == P99_GUIDANCE_MS
    assert report.recommended_decision_samples == RECOMMENDED_DECISION_SAMPLES
    assert report.all_within_hard_budget is True
    assert report.timeout_player_counts == ()


def test_report_has_no_aggregate_field() -> None:
    assert set(DecisionLatencyReport.model_fields) == {
        "scope",
        "measured_path",
        "lookup_runtime_integration",
        "lookup_runtime_integration_note",
        "decision_budget_ms",
        "p95_guidance_ms",
        "p99_guidance_ms",
        "recommended_decision_samples",
        "environment",
        "baseline",
        "supplements",
    }
    for name in DecisionLatencyReport.model_fields:
        assert not any(token in name for token in ("mean", "average", "weighted", "aggregate"))


def test_report_requires_a_whitelisted_environment() -> None:
    baseline = _scenario(BASELINE_SCENARIO, PLAYER_COUNT_RANGE)
    with pytest.raises(DecisionLatencyError):
        build_decision_latency_report(environment={}, baseline=baseline)
    with pytest.raises(DecisionLatencyError, match="白名单"):
        build_decision_latency_report(
            environment={"master_seed": "1"},
            baseline=_scenario(BASELINE_SCENARIO, PLAYER_COUNT_RANGE),
        )
    assert all("seed" not in key for key in REPORTED_ENVIRONMENT_KEYS)


def test_report_rejects_a_foreign_baseline_or_duplicate_scenarios() -> None:
    with pytest.raises(DecisionLatencyError, match="基础场景标识"):
        _report(baseline=_scenario("deep-stack", PLAYER_COUNT_RANGE))
    with pytest.raises(DecisionLatencyError, match="不能重复"):
        _report(
            supplements=(
                _scenario("strong-draw", SCENARIO_FOCUS_PLAYER_COUNTS, ("flop", "turn")),
                _scenario("strong-draw", SCENARIO_FOCUS_PLAYER_COUNTS, ("flop", "turn")),
            )
        )
    with pytest.raises(DecisionLatencyError, match="不得复用"):
        _report(supplements=(_scenario(BASELINE_SCENARIO, PLAYER_COUNT_RANGE),))


def test_report_is_frozen() -> None:
    report = _report()

    with pytest.raises(ValidationError):
        report.scope = "other"  # type: ignore[misc]


def test_report_requires_every_player_count_via_the_scenario() -> None:
    scenario = _scenario(BASELINE_SCENARIO, (6, 7, 9))
    report = build_decision_latency_report(
        environment={"platform": "test"},
        baseline=scenario,
    )

    assert report.baseline.measured_player_counts == (6, 7, 9)
    assert report.baseline.uncovered_player_counts == (2, 3, 4, 5, 8)
    assert report.all_within_hard_budget is True


# ---------------------------------------------------------------- 失败与建议余量


def test_timeout_is_reported_per_player_count_and_never_hidden() -> None:
    entry = summarize_player_count_latency(
        6, {street: [1.0, 1.0, 1.0, DECISION_BUDGET_MS] for street in DECISION_STREETS}
    )
    report = build_decision_latency_report(
        environment={"platform": "test"},
        baseline=DecisionScenarioLatency(
            scenario=BASELINE_SCENARIO,
            description="合成用例",
            streets=DECISION_STREETS,
            player_counts=(
                entry,
                *(_entry(count) for count in PLAYER_COUNT_RANGE if count != 6),
            ),
        ),
    )

    assert entry.summary.timeout_count == 4
    assert report.all_within_hard_budget is False
    assert report.timeout_player_counts == (6,)


def test_guidance_flags_are_reported_but_not_enforced() -> None:
    entry = summarize_player_count_latency(9, {street: [90.0] * 10 for street in DECISION_STREETS})

    assert entry.summary.within_hard_budget is True
    assert entry.summary.timeout_count == 0
    assert entry.summary.meets_p95_guidance is False
    assert entry.summary.meets_p99_guidance is False


def test_recommended_scale_stays_self_consistent() -> None:
    per_street = RECOMMENDED_DECISION_SAMPLES // len(DECISION_STREETS)
    entry = _entry(9, rounds=per_street)

    assert entry.summary.decision_count == RECOMMENDED_DECISION_SAMPLES
    assert sum(group.decision_count for group in entry.groups) == RECOMMENDED_DECISION_SAMPLES
    assert all(group.decision_count == per_street for group in entry.groups)


# ---------------------------------------------------------------- 口径复用与纪律


def test_module_reuses_the_existing_budget_constants() -> None:
    assert decision_latency_module.DECISION_BUDGET_MS == DECISION_BUDGET_MS
    assert decision_latency_module.P95_GUIDANCE_MS == P95_GUIDANCE_MS
    assert decision_latency_module.P99_GUIDANCE_MS == P99_GUIDANCE_MS
    assert decision_latency_module.RECOMMENDED_DECISION_SAMPLES == RECOMMENDED_DECISION_SAMPLES
    assert decision_latency_module.PLAYER_COUNT_RANGE == PLAYER_COUNT_RANGE
    assert decision_latency_module.MEASUREMENT_SCOPE == MEASUREMENT_SCOPE
    assert decision_latency_module.percentile_ms is percentile_ms
    assert (
        decision_latency_module.summarize_decision_latencies is summarize_decision_latencies
    )


def test_module_does_not_restate_any_budget_number() -> None:
    source = inspect.getsource(decision_latency_module)

    for token in _FORBIDDEN_SOURCE_TOKENS:
        assert token not in source, f"新模块不应出现预算数值字面量：{token}"


def test_new_code_never_writes_files() -> None:
    from . import decision_latency_states, test_decision_latency_benchmark

    modules = (decision_latency_module, decision_latency_states, test_decision_latency_benchmark)
    for module in modules:
        source = inspect.getsource(module)
        for token in _WRITE_TOKENS:
            assert token not in source, f"{module.__name__} 不应写回工件：{token}"


def test_declared_coverage_matches_the_public_streets() -> None:
    assert DECISION_STREETS == ("preflop", "flop", "turn", "river")
    assert tuple(STREET_LABELS[street] for street in STREET_ORDER) == DECISION_STREETS
    assert tuple(BOARD_SIZE[street] for street in STREET_ORDER) == (0, 3, 4, 5)


def test_supplementary_scenarios_are_focused_and_bounded() -> None:
    assert SCENARIO_FOCUS_PLAYER_COUNTS == (6, 7, 9)
    assert set(SCENARIO_FOCUS_PLAYER_COUNTS) <= set(PLAYER_COUNT_RANGE)
    assert SUPPLEMENTARY_DECISION_SAMPLES < RECOMMENDED_DECISION_SAMPLES
    assert len(set(SUPPLEMENTARY_SCENARIOS)) == len(SUPPLEMENTARY_SCENARIOS)
    assert BASELINE_SCENARIO not in SUPPLEMENTARY_SCENARIOS


def test_benchmark_entry_is_opt_in_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from . import test_decision_latency_benchmark as benchmark

    monkeypatch.delenv(benchmark._ENV_SWITCH, raising=False)
    assert benchmark._opt_in_enabled() is False
    monkeypatch.setenv(benchmark._ENV_SWITCH, "1")
    assert benchmark._opt_in_enabled() is True
    assert benchmark.pytestmark is not None


# ---------------------------------------------------------------- 局面构造与信息边界


@pytest.mark.parametrize("player_count", PLAYER_COUNT_RANGE)
def test_state_builder_produces_a_legal_decision_point(player_count: int) -> None:
    for street in STREET_ORDER:
        state, legal = build_state(player_count, street)

        assert state.street == street
        assert not state.hand_over
        assert len(state.players) == player_count
        assert len(state.board) == BOARD_SIZE[street]
        assert any((legal.can_check, legal.can_call, legal.can_bet, legal.can_raise))
    assert BASELINE_VARIANTS > 0
    assert set(baseline_cases(player_count)) == set(DECISION_STREETS)


def test_strong_draw_state_reaches_the_draw_branch() -> None:
    for street in (Street.FLOP, Street.TURN):
        state, legal = build_strong_draw_state(6, street)
        hero = state.players[state.current_seat]

        assert legal.can_bet
        assert draw_outs(hero.hole_cards, state.board) >= 12
        distribution = HeuristicStrategy(seed=11).action_distribution(state, legal)
        assert distribution
        assert abs(sum(weight for _, weight in distribution) - 1.0) < 1e-9


def test_measured_path_ignores_hidden_cards() -> None:
    state, legal = build_state(6, Street.RIVER)
    hero = state.current_seat
    baseline = HeuristicStrategy(seed=7).action_distribution(state, legal)

    used = set(state.board) | set(state.players[hero].hole_cards)
    replacement = [card for card in _FULL_DECK if card not in used]
    players = []
    cursor = 0
    for player in state.players:
        if player.seat == hero:
            players.append(player)
            continue
        players.append(
            PlayerState(
                seat=player.seat,
                name=player.name,
                stack=player.stack,
                hole_cards=replacement[cursor : cursor + 2],
                folded=player.folded,
                all_in=player.all_in,
                street_bet=player.street_bet,
                total_committed=player.total_committed,
                has_acted_since_full_raise=player.has_acted_since_full_raise,
            )
        )
        cursor += 2
    swapped = GameState(
        street=state.street,
        board=state.board,
        pot=state.pot,
        current_seat=state.current_seat,
        button=state.button,
        hand_over=state.hand_over,
        players=tuple(players),
    )

    assert HeuristicStrategy(seed=7).action_distribution(swapped, legal) == baseline


def test_measurement_helper_rejects_invalid_arguments() -> None:
    from .decision_latency_states import measure_decision_latencies

    cases = [build_state(2, Street.FLOP)]
    with pytest.raises(AssertionError):
        measure_decision_latencies(HeuristicStrategy(seed=1), cases, 0)
    with pytest.raises(AssertionError):
        measure_decision_latencies(HeuristicStrategy(seed=1), [], 1)
