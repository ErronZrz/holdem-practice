from pathlib import Path

import pytest

from multiplayer_cfr.campaign import (
    CAMPAIGN_SCHEMA_VERSION,
    CAMPAIGN_TYPE,
    CampaignError,
    acquire_campaign_lease,
    create_campaign_manifest,
)
from multiplayer_cfr.estimator_preflight import PREFLIGHT_ATTESTATION_TYPE

_COMMIT = "6" * 40


def _experiment_identity(identifier: str) -> dict[str, object]:
    return {
        "manifest_type": "multiplayer-cfr-experiment",
        "schema_version": 1,
        "manifest_id": identifier,
        "sha256": "a" * 64,
        "byte_length": 100,
    }


def _payload() -> dict[str, object]:
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "record_type": CAMPAIGN_TYPE,
        "campaign_id": "a6-a7-campaign",
        "code_identity": {"git_commit": _COMMIT, "trainer_version": "candidate-a-campaign-v1"},
        "preflight_attestation": {
            "record_type": PREFLIGHT_ATTESTATION_TYPE,
            "schema_version": 1,
            "record_id": "n6-preflight",
            "sha256": "b" * 64,
            "byte_length": 200,
        },
        "limits": {
            "cpu_limit_milliseconds": 100,
            "wall_limit_milliseconds": 100,
            "peak_rss_limit_bytes": 1000,
            "retained_artifact_limit_bytes": 1000,
            "max_concurrency": 1,
        },
        "authorizations": [
            {
                "authorization_id": "a6-seed-1",
                "experiment_manifest": _experiment_identity("a6-experiment"),
                "cpu_reservation_milliseconds": 50,
                "wall_reservation_milliseconds": 50,
                "artifact_reservation_bytes": 500,
            },
            {
                "authorization_id": "a7-seed-1",
                "experiment_manifest": _experiment_identity("a7-experiment"),
                "cpu_reservation_milliseconds": 50,
                "wall_reservation_milliseconds": 50,
                "artifact_reservation_bytes": 500,
            },
        ],
    }


def test_campaign_lease_is_exclusive_and_authorization_cannot_be_retried(tmp_path: Path) -> None:
    campaign = create_campaign_manifest(_payload())

    with acquire_campaign_lease(tmp_path, campaign, "a6-seed-1") as lease:
        with pytest.raises(CampaignError):
            acquire_campaign_lease(tmp_path, campaign, "a7-seed-1")
        lease.finalize(
            status="stopped",
            supervisor_receipt_sha256=None,
            final_measurement_sha256=None,
            final_inventory=[],
        )

    with pytest.raises(CampaignError):
        acquire_campaign_lease(tmp_path, campaign, "a6-seed-1")


def test_campaign_rejects_reservations_that_exceed_shared_envelope() -> None:
    payload = _payload()
    payload["authorizations"][1]["cpu_reservation_milliseconds"] = 51

    with pytest.raises(CampaignError):
        create_campaign_manifest(payload)


def test_campaign_lease_rejects_unknown_authorization(tmp_path: Path) -> None:
    campaign = create_campaign_manifest(_payload())

    with pytest.raises(CampaignError):
        acquire_campaign_lease(tmp_path, campaign, "unlisted")
