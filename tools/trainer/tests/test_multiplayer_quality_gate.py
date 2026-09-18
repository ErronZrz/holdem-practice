"""只读门槛判定层测试：多 seed 规则、人数隔离、双向报告，以及复算已冻结读数。"""

from fractions import Fraction

import pytest

from multiplayer_cfr.measurement import MeasurementRecord
from multiplayer_cfr.quality_gate import (
    DEFAULT_THRESHOLD,
    MIN_OBSERVATIONS,
    STATUS_EXCEEDS,
    STATUS_NOT_OBSERVED,
    ProbeDelta,
    QualityGateError,
    SeedObservation,
    evaluate_gains_threshold,
    observation_from_measurement,
)

# 已冻结读数：下列两组常量逐值抄自两份跨 seed 报告（N=6 与 N=7 各 4 个预注册 seed），
# 只用于复算既有读数，不构成任何新测量。每项为 (seed, gains, [loose-open, tight-open])。
_N6_FROZEN = [
    (
        1215,
        "+0.805839 0 0 +0.328938 0 0",
        [
            "+0.805839 -0.737195 -0.348910 +0.328938 -0.512568 -0.736942",
            "+0.160267 -0.233903 -0.167716 +0.023752 -0.183449 -0.238766",
        ],
    ),
    (
        20260918,
        "0 0 0 0 0 0",
        [
            "-0.707201 -0.646676 -0.226977 -0.167230 -0.703166 -0.733546",
            "-0.220863 -0.212635 -0.082016 -0.081912 -0.216290 -0.237853",
        ],
    ),
    (
        3311,
        "0 0 0 0 0 0",
        [
            "-0.675680 -0.675052 -0.673262 -0.494762 -0.567044 -0.681279",
            "-0.178736 -0.195042 -0.175046 -0.133913 -0.168196 -0.181974",
        ],
    ),
    (
        6922,
        "0 0 0 0 0 0",
        [
            "-0.084731 -0.336459 -0.479041 -0.308508 -0.532295 -0.483283",
            "-0.025205 -0.092041 -0.170782 -0.072681 -0.166034 -0.142132",
        ],
    ),
]
_N7_FROZEN = [
    (
        1215,
        "0 0 0 0 0 0 0",
        [
            "-0.448687 -0.545793 -0.337808 -0.477714 -0.494374 -0.319684 -0.650123",
            "-0.103988 -0.156304 -0.067520 -0.150181 -0.151728 -0.076899 -0.222695",
        ],
    ),
    (
        20260918,
        "0 0 0 0 0 0 0",
        [
            "-0.563032 -0.506294 -0.571205 -0.581326 -0.275772 -0.571805 -0.627554",
            "-0.149013 -0.132784 -0.159613 -0.184221 -0.038327 -0.174825 -0.199115",
        ],
    ),
    (
        3311,
        "0 0 0 0 0 0 0",
        [
            "-0.661077 -0.552045 -0.517816 -0.109012 -0.350962 -0.225884 -0.712148",
            "-0.233211 -0.199085 -0.204848 -0.000967 -0.142914 -0.066546 -0.284365",
        ],
    ),
    (
        7926,
        "0 0 0 0 0 0 0",
        [
            "-0.395701 -0.557904 -0.498953 -0.528785 -0.433570 -0.596419 -0.622409",
            "-0.103573 -0.160547 -0.139418 -0.150997 -0.123935 -0.198306 -0.196145",
        ],
    ),
]

# 两组预注册阈值 probe 的标识，顺序与报告逐行对应。
_PROBE_IDS = ("loose-open", "tight-open")


def _values(text: str) -> tuple[Fraction, ...]:
    return tuple(Fraction(token) for token in text.split())


def _frozen_observation(entry: tuple[int, str, list[str]]) -> SeedObservation:
    """把抄录的读数还原为观测对象。"""
    seed, gains, probes = entry
    gains_values = _values(gains)
    return SeedObservation(
        seed=seed,
        player_count=len(gains_values),
        gains=gains_values,
        deltas=tuple(
            ProbeDelta(player=player, probe_id=_PROBE_IDS[index], delta=delta)
            for index, per_seat in enumerate(probes)
            for player, delta in enumerate(_values(per_seat))
        ),
    )


def _observation(*, seed: int, gains: str, deltas: str) -> SeedObservation:
    """构造只含一组 probe 的观测，用于边界用例。"""
    gains_values = _values(gains)
    return SeedObservation(
        seed=seed,
        player_count=len(gains_values),
        gains=gains_values,
        deltas=tuple(
            ProbeDelta(player=player, probe_id="p1", delta=delta)
            for player, delta in enumerate(_values(deltas))
        ),
    )


def _rational(text: str) -> dict[str, str]:
    """按既有规范有理数形式序列化，避免测试自造另一种格式。"""
    value = Fraction(text)
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _record(*, player_count: int, status: str, raw: dict[str, object]) -> MeasurementRecord:
    """直接构造测量记录对象，用于提取逻辑的单元测试（真实调用方传入的是已校验记录）。"""
    payload = {"game": {"player_count": player_count}, "probes": raw}
    return MeasurementRecord(payload=payload, sha256="0" * 64, record_bytes=0)


def _n6_observations() -> list[SeedObservation]:
    return [_frozen_observation(entry) for entry in _N6_FROZEN]


def _n7_observations() -> list[SeedObservation]:
    return [_frozen_observation(entry) for entry in _N7_FROZEN]


# ------------------------------------------------------------------ 多 seed 规则


def test_single_seed_is_not_judged() -> None:
    # 单 seed 不判定：观测数不足时明确失败，而不是给出一个「未观察到」的默认结论。
    assert MIN_OBSERVATIONS == 2
    with pytest.raises(QualityGateError):
        evaluate_gains_threshold([_frozen_observation(_N6_FROZEN[0])])


def test_duplicate_seeds_are_rejected() -> None:
    first = _frozen_observation(_N6_FROZEN[0])
    with pytest.raises(QualityGateError):
        evaluate_gains_threshold([first, first])


def test_mixed_player_counts_are_rejected() -> None:
    with pytest.raises(QualityGateError):
        evaluate_gains_threshold(
            [_frozen_observation(_N6_FROZEN[0]), _frozen_observation(_N7_FROZEN[0])]
        )


def test_threshold_must_be_positive() -> None:
    with pytest.raises(QualityGateError):
        evaluate_gains_threshold(_n6_observations(), threshold=Fraction(0))
    with pytest.raises(QualityGateError):
        evaluate_gains_threshold(_n6_observations(), threshold=0.05)  # type: ignore[arg-type]


# ------------------------------------------------------------------ 观测对象校验


def test_observation_rejects_gains_that_are_not_clamped_deltas() -> None:
    # 判定对象必须是同座位 delta 的钳位最大值，否则双向报告与判定自相矛盾。
    with pytest.raises(QualityGateError):
        _observation(seed=1, gains="0.9 0", deltas="0.1 -0.2")


def test_observation_rejects_negative_gains() -> None:
    with pytest.raises(QualityGateError):
        _observation(seed=1, gains="-0.1 0", deltas="-0.1 -0.2")


def test_observation_requires_deltas_for_every_seat() -> None:
    with pytest.raises(QualityGateError):
        SeedObservation(
            seed=1,
            player_count=2,
            gains=(Fraction("0.5"), Fraction(0)),
            deltas=(ProbeDelta(player=0, probe_id="p1", delta=Fraction("0.5")),),
        )


def test_observation_rejects_float_deltas() -> None:
    with pytest.raises(QualityGateError):
        ProbeDelta(player=0, probe_id="p1", delta=0.5)  # type: ignore[arg-type]


# ------------------------------------------------------------------ 复算已冻结读数


def test_recomputes_frozen_n6_reading() -> None:
    verdict = evaluate_gains_threshold(_n6_observations())

    assert verdict.player_count == 6
    assert verdict.threshold == DEFAULT_THRESHOLD
    assert verdict.seeds == (1215, 20260918, 3311, 6922)
    assert verdict.exceeded_seeds == (1215,)
    assert verdict.status == STATUS_EXCEEDS
    assert verdict.max_gain == Fraction("+0.805839")
    assert verdict.max_gain_seed == 1215
    assert verdict.max_gain_player == 0
    # 双向报告：最负偏离不是 0，必须被如实呈现。
    assert verdict.max_positive_delta == Fraction("+0.805839")
    assert verdict.min_negative_delta == Fraction("-0.737195")


def test_recomputes_frozen_n7_reading() -> None:
    verdict = evaluate_gains_threshold(_n7_observations())

    assert verdict.player_count == 7
    assert verdict.seeds == (1215, 20260918, 3311, 7926)
    assert verdict.exceeded_seeds == ()
    assert verdict.status == STATUS_NOT_OBSERVED
    assert verdict.max_gain == Fraction(0)
    assert verdict.max_positive_delta == Fraction(0)
    assert verdict.min_negative_delta == Fraction("-0.712148")


def test_verdicts_are_isolated_per_player_count() -> None:
    six = evaluate_gains_threshold(_n6_observations())
    seven = evaluate_gains_threshold(_n7_observations())

    assert six.status != seven.status
    assert six.player_count != seven.player_count
    assert six.threshold == seven.threshold == DEFAULT_THRESHOLD


def test_verdict_does_not_mutate_observations() -> None:
    observations = _n6_observations()
    before = tuple(observations)
    evaluate_gains_threshold(observations)
    assert tuple(observations) == before


# ------------------------------------------------------------------ 措辞与报告


def test_status_wording_contains_no_acceptance_terms() -> None:
    banned = ("合格", "不合格", "通过", "达标")
    for status in (STATUS_EXCEEDS, STATUS_NOT_OBSERVED):
        assert isinstance(status, str) and status
        assert not any(term in status for term in banned)


def test_summary_reports_both_directions() -> None:
    summary = evaluate_gains_threshold(_n7_observations()).summary()

    assert summary["player_count"] == 7
    assert summary["seeds"] == [1215, 20260918, 3311, 7926]
    assert summary["exceeded_seeds"] == []
    assert summary["status"] == STATUS_NOT_OBSERVED
    assert Fraction(summary["max_positive_delta"]) == Fraction(0)
    assert Fraction(summary["min_negative_delta"]) == Fraction("-0.712148")


# ------------------------------------------------------------------ 从记录提取观测


def test_observation_from_measurement_reads_completed_probes() -> None:
    seed, gains, probes = _N6_FROZEN[0]
    raw = {
        "status": "completed",
        "manifest_id": "probe-manifest",
        "manifest_sha256": "b" * 64,
        "results": [
            {"player": player, "probe_id": _PROBE_IDS[index], "delta": _rational(token)}
            for index, per_seat in enumerate(probes)
            for player, token in enumerate(per_seat.split())
        ],
        "gains": [_rational(token) for token in gains.split()],
    }

    observation = observation_from_measurement(
        _record(player_count=6, status="completed", raw=raw), seed=seed
    )

    assert observation.seed == seed
    assert observation.player_count == 6
    assert observation.gains == _values(gains)
    assert len(observation.deltas) == 12
    assert max(entry.delta for entry in observation.deltas) == Fraction("+0.805839")


def test_observation_from_measurement_rejects_unfinished_probes() -> None:
    raw = {
        "status": "not-run",
        "manifest_id": None,
        "manifest_sha256": None,
        "results": [],
        "gains": None,
    }
    with pytest.raises(QualityGateError):
        observation_from_measurement(
            _record(player_count=6, status="not-run", raw=raw), seed=1
        )


def test_observation_from_measurement_rejects_non_rational_values() -> None:
    raw = {
        "status": "completed",
        "manifest_id": "probe-manifest",
        "manifest_sha256": "b" * 64,
        "results": [
            {"player": 0, "probe_id": "p1", "delta": "+0.1"},
            {"player": 1, "probe_id": "p1", "delta": _rational("-0.1")},
        ],
        "gains": [_rational("0"), _rational("0")],
    }
    with pytest.raises(QualityGateError):
        observation_from_measurement(
            _record(player_count=2, status="completed", raw=raw), seed=1
        )
