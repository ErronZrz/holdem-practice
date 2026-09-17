from pathlib import Path

import pytest

from multiplayer_cfr.estimator_preflight import (
    PREFLIGHT_MANIFEST_TYPE,
    PREFLIGHT_SCHEMA_VERSION,
    EstimatorPreflightError,
    create_preflight_spec,
    load_attestation,
    run_preflight,
    verify_attestation,
    write_attestation,
)
from multiplayer_cfr.game import information_set_key

_COMMIT = "5" * 40


def _payload() -> dict[str, object]:
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "record_type": PREFLIGHT_MANIFEST_TYPE,
        "record_id": "n6-estimator-preflight",
        "code_identity": {"git_commit": _COMMIT, "trainer_version": "candidate-a-preflight-v1"},
        "fixture_id": "three-to-one-regret-v1",
        "sample_seeds": list(range(8)),
        "target_infosets": sorted(
            [
                information_set_key(6, 0, 3, "-"),
                information_set_key(6, 1, 3, "b@0"),
                information_set_key(6, 2, 3, "b@0|c@1"),
            ]
        ),
        "regret_tolerance_micros": 1_000_000,
        "strategy_sum_tolerance_micros": 1_000_000,
    }


def test_preflight_attestation_is_canonical_replayable_and_covers_both_average_modes(
    tmp_path: Path,
) -> None:
    spec = create_preflight_spec(_payload())

    attestation = run_preflight(spec)
    written = write_attestation(tmp_path, "attestation.json", attestation)
    verify_attestation(spec, load_attestation(tmp_path / "attestation.json"))

    assert written.payload["passed"] is True
    assert [case["accumulate_average"] for case in written.payload["cases"]] == [False, True]


def test_preflight_rejects_implicit_or_unsorted_seed_and_target_inputs() -> None:
    payload = _payload()
    payload["sample_seeds"] = [1, 0, 2, 3, 4, 5, 6, 7]
    with pytest.raises(EstimatorPreflightError):
        create_preflight_spec(payload)

    payload = _payload()
    payload["target_infosets"] = [information_set_key(6, 0, 0, "-")]
    with pytest.raises(EstimatorPreflightError):
        create_preflight_spec(payload)
