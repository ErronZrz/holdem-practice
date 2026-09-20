from fractions import Fraction
from pathlib import Path

import pytest

from multiplayer_cfr.game import infoset_by_key, infosets, structure_counts
from multiplayer_cfr.measurement import (
    MAX_RATIONAL_DIGITS,
    MEASUREMENT_RECORD_TYPE,
    MEASUREMENT_SCHEMA_VERSION,
    MeasurementRecordError,
    RationalValue,
    audit_infoset_keys,
    build_stability_payload,
    create_measurement_record,
    load_measurement,
    write_measurement,
)

_HASH = "a" * 64


def _diagnostics(player_count: int) -> dict[str, object]:
    return {
        "average_strategy_start_iteration": 1,
        "coverage": [
            {"traverser": seat, "visits": 0, "visited_infosets": 0} for seat in range(player_count)
        ],
        "importance_weights": [
            {
                "traverser": seat,
                "visits": 0,
                "maximum_milli": 0,
                "p50_milli": 0,
                "p95_milli": 0,
                "non_finite_count": 0,
            }
            for seat in range(player_count)
        ],
    }


def _valid_payload(*, completed: bool = False) -> dict[str, object]:
    player_count = 6
    strategy_ref: dict[str, object]
    profile: dict[str, object]
    execution: dict[str, object]
    if completed:
        strategy_ref = {
            "status": "present",
            "sha256": _HASH,
            "artifact_bytes": 123,
            "artifact_type": "multiplayer-cfr-average-strategy",
            "artifact_schema_version": 1,
        }
        profile = {
            "status": "completed",
            "full_chance": True,
            "ordered_deal_count": 720,
            "terminal_leaf_count": 720,
            "utilities": [{"numerator": "0", "denominator": "1"} for _ in range(player_count)],
        }
        execution = {
            "status": "completed",
            "stage": "a6-profile",
            "stop_reason": "completed",
            "controller_id": "controlled-runner-v1",
        }
    else:
        strategy_ref = {
            "status": "not-produced",
            "sha256": None,
            "artifact_bytes": None,
            "artifact_type": None,
            "artifact_schema_version": None,
        }
        profile = {
            "status": "not-run",
            "full_chance": False,
            "ordered_deal_count": 0,
            "terminal_leaf_count": 0,
            "utilities": None,
        }
        execution = {
            "status": "stopped",
            "stage": "n9-boundary",
            "stop_reason": "nine-player-boundary",
            "controller_id": "controlled-runner-v1",
        }
    return {
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
        "record_type": MEASUREMENT_RECORD_TYPE,
        "game": {"id": "m8-unique-rank-single-open", "version": "m8-a-v1", "player_count": 6},
        "strategy_ref": strategy_ref,
        "experiment_manifest": {
            "sha256": _HASH,
            "kind": "experiment-manifest",
            "schema_version": 1,
        },
        "execution": execution,
        "profile": profile,
        "probes": {
            "status": "not-run",
            "manifest_id": None,
            "manifest_sha256": None,
            "results": [],
            "gains": None,
        },
        "diagnostics": _diagnostics(player_count),
        "stability": {
            "status": "not-requested",
            "seed_set_sha256": None,
            "audit_infosets_sha256": None,
            "max_l1": None,
        },
        "resources": {
            "elapsed_milliseconds": 0,
            "wall_time_limit_milliseconds": 1000,
            "peak_rss_bytes": 0,
            "rss_warning_bytes": 100,
            "rss_hard_limit_bytes": 200,
            "rss_sampler_id": "test-rss-v1",
            "warning_triggered": False,
            "retained_artifact_bytes": 0,
            "retained_artifact_limit_bytes": 1024,
        },
    }


def test_measurement_round_trip_keeps_canonical_bytes_and_independent_identity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "measurement.json"

    written = write_measurement(path, create_measurement_record(_valid_payload(completed=True)))
    loaded = load_measurement(path)

    assert loaded == written
    assert loaded.record_bytes == len(path.read_bytes())
    assert loaded.payload["strategy_ref"]["sha256"] == _HASH


def test_measurement_rejects_invalid_rationals_and_inconsistent_unproduced_strategy() -> None:
    assert RationalValue.from_fraction(Fraction(-2, 3)).as_payload() == {
        "numerator": "-2",
        "denominator": "3",
    }
    with pytest.raises(MeasurementRecordError):
        RationalValue("2", "4")

    payload = _valid_payload()
    payload["strategy_ref"]["sha256"] = _HASH
    with pytest.raises(MeasurementRecordError):
        create_measurement_record(payload)


def _payload_with_long_utilities(numerator: str) -> dict[str, object]:
    """构造一个仅首位效用取长分子、其相反数配平的常和 profile。"""

    payload = _valid_payload(completed=True)
    payload["profile"]["utilities"][0] = {"numerator": numerator, "denominator": "1"}
    payload["profile"]["utilities"][1] = {"numerator": f"-{numerator}", "denominator": "1"}
    return payload


def test_measurement_accepts_exact_rationals_longer_than_text_bound() -> None:
    numerator = "1" + "0" * 300
    assert len(numerator) > 256

    record = create_measurement_record(_payload_with_long_utilities(numerator))

    assert record.payload["profile"]["utilities"][0]["numerator"] == numerator
    assert record.payload["profile"]["utilities"][1]["numerator"] == f"-{numerator}"


def test_measurement_rejects_exact_rationals_beyond_the_dedicated_bound() -> None:
    numerator = "1" + "0" * MAX_RATIONAL_DIGITS
    assert len(numerator) > MAX_RATIONAL_DIGITS

    with pytest.raises(MeasurementRecordError):
        create_measurement_record(_payload_with_long_utilities(numerator))


def test_measurement_rejects_noncanonical_or_inconsistent_profile_files(tmp_path: Path) -> None:
    payload = _valid_payload(completed=True)
    payload["profile"]["utilities"][0] = {"numerator": "1", "denominator": "1"}
    payload["profile"]["utilities"][1] = {"numerator": "0", "denominator": "1"}
    with pytest.raises(MeasurementRecordError):
        create_measurement_record(payload)

    path = tmp_path / "measurement.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(MeasurementRecordError):
        load_measurement(path)

    pretty = tmp_path / "pretty.json"
    record = create_measurement_record(_valid_payload())
    pretty.write_text(str(record.payload), encoding="utf-8")
    with pytest.raises(MeasurementRecordError):
        load_measurement(pretty)


# 跨 seed 稳定性生产者的概率单位；取偶数，保证每个信息集可被两个动作均分。
_STABILITY_UNITS = 1000


def _uniform_strategy(player_count: int) -> dict[str, dict[str, int]]:
    """构造每个信息集都均匀分配概率单位的策略，用于稳定性测试。"""

    return {
        spec.key: {
            action.value: _STABILITY_UNITS // len(spec.actions) for action in spec.actions
        }
        for spec in infosets(player_count)
    }


def _copy_strategy(strategy: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {key: dict(values) for key, values in strategy.items()}


@pytest.mark.parametrize("player_count", [6, 7, 9])
def test_audit_infosets_cover_every_infoset_of_supported_player_counts(
    player_count: int,
) -> None:
    keys = audit_infoset_keys(player_count)

    assert len(keys) == structure_counts(player_count).infosets
    assert len(set(keys)) == len(keys)
    assert set(keys) == {spec.key for spec in infosets(player_count)}


def test_stability_producer_reports_zero_distance_for_identical_strategies() -> None:
    strategy = _uniform_strategy(6)

    payload = build_stability_payload(
        player_count=6,
        strategies={1215: strategy, 3311: strategy},
        probability_units=_STABILITY_UNITS,
    )

    assert payload["status"] == "measured"
    assert payload["max_l1"] == {"numerator": "0", "denominator": "1"}
    assert len(payload["seed_set_sha256"]) == 64
    assert len(payload["audit_infosets_sha256"]) == 64


def test_stability_producer_measures_exact_distance_on_a_single_infoset() -> None:
    baseline = _uniform_strategy(6)
    shifted = _copy_strategy(baseline)
    key = sorted(baseline)[0]
    first, second = infoset_by_key(6)[key].actions
    shifted[key] = {first.value: 400, second.value: 600}

    payload = build_stability_payload(
        player_count=6,
        strategies={1215: baseline, 3311: shifted},
        probability_units=_STABILITY_UNITS,
    )

    assert payload["max_l1"] == {"numerator": "1", "denominator": "5"}


def test_stability_producer_is_independent_of_seed_insertion_order() -> None:
    left = _uniform_strategy(6)
    right = _copy_strategy(left)
    key = sorted(left)[-1]
    first, second = infoset_by_key(6)[key].actions
    right[key] = {first.value: 250, second.value: 750}

    forward = build_stability_payload(
        player_count=6,
        strategies={1215: left, 3311: right},
        probability_units=_STABILITY_UNITS,
    )
    backward = build_stability_payload(
        player_count=6,
        strategies={3311: right, 1215: left},
        probability_units=_STABILITY_UNITS,
    )

    assert forward == backward
    assert forward["max_l1"] == {"numerator": "1", "denominator": "2"}


def test_stability_producer_rejects_a_single_seed_and_non_integer_seeds() -> None:
    strategy = _uniform_strategy(6)

    with pytest.raises(MeasurementRecordError):
        build_stability_payload(
            player_count=6,
            strategies={1215: strategy},
            probability_units=_STABILITY_UNITS,
        )
    with pytest.raises(MeasurementRecordError):
        build_stability_payload(
            player_count=6,
            strategies={True: strategy, 1215: strategy},
            probability_units=_STABILITY_UNITS,
        )


def test_stability_producer_requires_the_full_audit_set_and_legal_actions() -> None:
    baseline = _uniform_strategy(6)

    missing = _copy_strategy(baseline)
    missing.pop(sorted(missing)[0])
    with pytest.raises(MeasurementRecordError):
        build_stability_payload(
            player_count=6,
            strategies={1215: baseline, 3311: missing},
            probability_units=_STABILITY_UNITS,
        )

    key = sorted(baseline)[0]
    renamed = _copy_strategy(baseline)
    renamed[key] = {"open": _STABILITY_UNITS}
    with pytest.raises(MeasurementRecordError):
        build_stability_payload(
            player_count=6,
            strategies={1215: baseline, 3311: renamed},
            probability_units=_STABILITY_UNITS,
        )

    actions = infoset_by_key(6)[key].actions
    unbalanced = _copy_strategy(baseline)
    unbalanced[key] = {actions[0].value: 400, actions[1].value: 400}
    with pytest.raises(MeasurementRecordError):
        build_stability_payload(
            player_count=6,
            strategies={1215: baseline, 3311: unbalanced},
            probability_units=_STABILITY_UNITS,
        )

    negative = _copy_strategy(baseline)
    negative[key] = {actions[0].value: -100, actions[1].value: 1100}
    with pytest.raises(MeasurementRecordError):
        build_stability_payload(
            player_count=6,
            strategies={1215: baseline, 3311: negative},
            probability_units=_STABILITY_UNITS,
        )


def test_stability_producer_rejects_a_non_positive_probability_unit() -> None:
    strategy = _uniform_strategy(6)

    with pytest.raises(MeasurementRecordError):
        build_stability_payload(
            player_count=6,
            strategies={1215: strategy, 3311: strategy},
            probability_units=0,
        )


def test_produced_stability_payload_is_accepted_by_the_measurement_record() -> None:
    strategy = _uniform_strategy(6)
    payload = _valid_payload(completed=True)
    payload["stability"] = build_stability_payload(
        player_count=6,
        strategies={1215: strategy, 3311: strategy},
        probability_units=_STABILITY_UNITS,
    )

    record = create_measurement_record(payload)

    assert record.payload["stability"]["status"] == "measured"
    assert record.payload["stability"]["max_l1"] == {"numerator": "0", "denominator": "1"}
