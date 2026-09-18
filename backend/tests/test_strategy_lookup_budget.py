"""实时 lookup 预算口径与测量汇总的回归测试。"""

import pytest
from pydantic import ValidationError

from app.strategy.abstraction import DEFAULT_FALLBACK_IDENTIFIER, FallbackDeclaration
from app.strategy.artifact import ArtifactIdentity
from app.strategy.lookup_budget import (
    DECISION_BUDGET_MS,
    P95_GUIDANCE_MS,
    P99_GUIDANCE_MS,
    PLAYER_COUNT_RANGE,
    RECOMMENDED_DECISION_SAMPLES,
    ArtifactLoadSummary,
    DecisionLatencySummary,
    LookupBudgetError,
    PlayerCountCoverage,
    artifact_load_summary,
    build_report,
    percentile_ms,
    summarize_decision_latencies,
)

_IDENTITY = ArtifactIdentity(sha256="a" * 64, byte_length=1234)


def _load_summary(player_count: int, cold_load_ms: float = 10.0) -> ArtifactLoadSummary:
    return artifact_load_summary(
        identity=_IDENTITY,
        player_count=player_count,
        infoset_count=1152,
        cold_load_ms=cold_load_ms,
        peak_rss_bytes=64 * 1024 * 1024,
    )


def _coverage(player_count: int, status: str) -> PlayerCountCoverage:
    return PlayerCountCoverage(
        player_count=player_count,
        status=status,
        reasons=("合成用例",),
        fallback=FallbackDeclaration(
            fallback_identifier=DEFAULT_FALLBACK_IDENTIFIER,
            triggering_coverage=status,
            reasons=("合成用例",),
        ),
    )


def _default_uncovered() -> list[PlayerCountCoverage]:
    return [
        _coverage(2, "out-of-abstraction"),
        _coverage(3, "out-of-abstraction"),
        _coverage(4, "out-of-abstraction"),
        _coverage(5, "out-of-abstraction"),
        _coverage(8, "out-of-abstraction"),
        _coverage(9, "artifact-unavailable"),
    ]


# ---------------------------------------------------------------- 分位点


def test_percentile_uses_the_nearest_rank() -> None:
    samples = [float(value) for value in range(1, 101)]
    assert percentile_ms(samples, 0.95) == 95.0
    assert percentile_ms(samples, 0.99) == 99.0
    assert percentile_ms(samples, 1.0) == 100.0
    assert percentile_ms([7.0], 0.95) == 7.0


def test_percentile_rejects_invalid_input() -> None:
    with pytest.raises(LookupBudgetError):
        percentile_ms([], 0.95)
    with pytest.raises(LookupBudgetError):
        percentile_ms([1.0], 0.0)
    with pytest.raises(LookupBudgetError):
        percentile_ms([1.0], 1.5)


# ---------------------------------------------------------------- 延迟汇总


def test_summarize_reports_the_full_distribution() -> None:
    samples = [float(value) for value in range(1, 1001)]
    summary = summarize_decision_latencies(6, samples)

    assert summary.player_count == 6
    assert summary.decision_count == 1000
    assert summary.median_ms == 500.5
    assert summary.p95_ms == 950.0
    assert summary.p99_ms == 990.0
    assert summary.max_ms == 1000.0
    assert summary.timeout_count == 901
    assert summary.within_hard_budget is False


def test_summarize_flags_a_quiet_path_as_within_budget() -> None:
    samples = [0.05, 0.06, 0.07, 0.08, 0.09]
    summary = summarize_decision_latencies(7, samples)

    assert summary.within_hard_budget is True
    assert summary.timeout_count == 0
    assert summary.meets_p95_guidance is True
    assert summary.meets_p99_guidance is True
    assert summary.max_ms < DECISION_BUDGET_MS


def test_summarize_counts_the_budget_boundary_as_a_timeout() -> None:
    summary = summarize_decision_latencies(6, [0.1, DECISION_BUDGET_MS])
    assert summary.timeout_count == 1
    assert summary.within_hard_budget is False


def test_summarize_rejects_invalid_input() -> None:
    with pytest.raises(LookupBudgetError):
        summarize_decision_latencies(1, [1.0])
    with pytest.raises(LookupBudgetError):
        summarize_decision_latencies(6, [])
    with pytest.raises(LookupBudgetError):
        summarize_decision_latencies(6, [-1.0])


# ---------------------------------------------------------------- 冷加载汇总


def test_load_summary_uses_the_identity_byte_length() -> None:
    summary = _load_summary(6, cold_load_ms=12.5)
    assert summary.artifact_bytes == _IDENTITY.byte_length
    assert summary.cold_load_ms == 12.5
    assert summary.peak_rss_bytes == 64 * 1024 * 1024


def test_load_summary_rejects_invalid_input() -> None:
    with pytest.raises(LookupBudgetError):
        artifact_load_summary(
            identity=_IDENTITY, player_count=1, infoset_count=1, cold_load_ms=1.0
        )
    with pytest.raises(LookupBudgetError):
        artifact_load_summary(
            identity=_IDENTITY, player_count=6, infoset_count=1, cold_load_ms=-1.0
        )
    with pytest.raises(LookupBudgetError):
        artifact_load_summary(
            identity=_IDENTITY, player_count=6, infoset_count=0, cold_load_ms=1.0
        )


# ---------------------------------------------------------------- 报告装配


def _report():
    return build_report(
        environment={"platform": "test", "python": "3.12"},
        loads=[_load_summary(6), _load_summary(7, cold_load_ms=20.0)],
        latencies=[
            summarize_decision_latencies(6, [0.02, 0.03, 0.04]),
            summarize_decision_latencies(7, [0.02, 0.03, 0.05]),
        ],
        uncovered=_default_uncovered(),
    )


def test_report_covers_every_player_count() -> None:
    report = _report()
    assert report.measured_player_counts == (6, 7)
    assert report.uncovered_player_counts == (2, 3, 4, 5, 8, 9)
    assert set(report.measured_player_counts) | set(report.uncovered_player_counts) == set(
        PLAYER_COUNT_RANGE
    )
    assert report.all_within_hard_budget is True
    assert report.decision_budget_ms == DECISION_BUDGET_MS
    assert report.p95_guidance_ms == P95_GUIDANCE_MS
    assert report.p99_guidance_ms == P99_GUIDANCE_MS
    assert report.recommended_decision_samples == RECOMMENDED_DECISION_SAMPLES
    assert report.scope == "local-machine-single-host-observation"


def test_report_requires_the_complete_player_count_range() -> None:
    with pytest.raises(LookupBudgetError, match="完整覆盖"):
        build_report(
            environment={},
            loads=[_load_summary(6), _load_summary(7)],
            latencies=[summarize_decision_latencies(6, [0.02])],
            uncovered=[],
        )


def test_report_rejects_overlapping_or_duplicated_counts() -> None:
    with pytest.raises(LookupBudgetError, match="同时被判为已测与未覆盖"):
        build_report(
            environment={},
            loads=[_load_summary(6)],
            latencies=[summarize_decision_latencies(6, [0.02])],
            uncovered=[
                _coverage(6, "artifact-unavailable"),
                *(_coverage(count, "out-of-abstraction") for count in (2, 3, 4, 5, 7, 8, 9)),
            ],
        )
    with pytest.raises(LookupBudgetError, match="重复"):
        build_report(
            environment={},
            loads=[_load_summary(6)],
            latencies=[
                summarize_decision_latencies(6, [0.02]),
                summarize_decision_latencies(6, [0.03]),
            ],
            uncovered=[_coverage(count, "out-of-abstraction") for count in (2, 3, 4, 5, 7, 8, 9)],
        )


def test_report_rejects_a_measurement_without_a_load_observation() -> None:
    with pytest.raises(LookupBudgetError, match="没有冷加载观测"):
        build_report(
            environment={},
            loads=[_load_summary(6)],
            latencies=[
                summarize_decision_latencies(6, [0.02]),
                summarize_decision_latencies(7, [0.03]),
            ],
            uncovered=[_coverage(count, "out-of-abstraction") for count in (2, 3, 4, 5, 8, 9)],
        )


def test_uncovered_counts_never_carry_interpolated_latency() -> None:
    report = _report()
    measured = {item.player_count for item in report.latencies}
    for item in report.uncovered:
        assert item.player_count not in measured
        assert item.status in ("out-of-abstraction", "artifact-unavailable")
        assert item.fallback.is_exact_solution is False
        assert item.fallback.fallback_identifier == DEFAULT_FALLBACK_IDENTIFIER


def test_report_is_frozen() -> None:
    report = _report()
    with pytest.raises(ValidationError):
        report.scope = "other"  # type: ignore[misc]
    assert isinstance(report.latencies[0], DecisionLatencySummary)
