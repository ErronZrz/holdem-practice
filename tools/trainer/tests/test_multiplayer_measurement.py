from fractions import Fraction
from pathlib import Path

import pytest

from multiplayer_cfr.measurement import (
    MEASUREMENT_RECORD_TYPE,
    MEASUREMENT_SCHEMA_VERSION,
    MeasurementRecordError,
    RationalValue,
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
