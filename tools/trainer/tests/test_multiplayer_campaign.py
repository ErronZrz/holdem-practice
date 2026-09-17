from pathlib import Path

import pytest

from multiplayer_cfr.campaign import (
    CAMPAIGN_LEDGER_TYPE,
    CAMPAIGN_SCHEMA_VERSION,
    CAMPAIGN_TYPE,
    CampaignError,
    CampaignLease,
    acquire_campaign_lease,
    create_campaign_manifest,
    verify_active_lease,
)
from multiplayer_cfr.estimator_preflight import PREFLIGHT_ATTESTATION_TYPE
from multiplayer_cfr.safeio import canonical_json_bytes

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


def test_campaign_rejects_uncontrolled_authorization_identifier() -> None:
    payload = _payload()
    payload["authorizations"][0]["authorization_id"] = "../escape"

    with pytest.raises(CampaignError):
        create_campaign_manifest(payload)


def test_campaign_lease_cannot_be_constructed_outside_the_mutex_entry(tmp_path: Path) -> None:
    campaign = create_campaign_manifest(_payload())

    with pytest.raises(CampaignError):
        CampaignLease(campaign, campaign.authorizations[0], tmp_path, 3)


def test_campaign_run_directories_are_created_once_inside_the_campaign_root(
    tmp_path: Path,
) -> None:
    campaign = create_campaign_manifest(_payload())

    with acquire_campaign_lease(tmp_path, campaign, "a6-seed-1") as lease:
        run_root, artifact_root, snapshot_root = lease.create_run_directories()

        assert run_root == tmp_path / "runs" / "a6-seed-1"
        assert lease.owns_path(artifact_root)
        assert lease.owns_path(snapshot_root)
        assert not lease.owns_path(tmp_path)
        assert artifact_root.is_dir() and snapshot_root.is_dir()
        with pytest.raises(CampaignError):
            lease.create_run_directories()
        lease.finalize(
            status="failed",
            supervisor_receipt_sha256=None,
            final_measurement_sha256=None,
            final_inventory=[],
        )


def test_campaign_verifies_lease_against_live_ledger_record(tmp_path: Path) -> None:
    campaign = create_campaign_manifest(_payload())

    with acquire_campaign_lease(tmp_path, campaign, "a6-seed-1") as lease:
        verify_active_lease(lease)

    with pytest.raises(CampaignError):
        verify_active_lease(lease)


def test_campaign_rejects_ledger_events_with_unexpected_fields(tmp_path: Path) -> None:
    campaign = create_campaign_manifest(_payload())

    with acquire_campaign_lease(tmp_path, campaign, "a6-seed-1") as lease:
        lease.finalize(
            status="failed",
            supervisor_receipt_sha256=None,
            final_measurement_sha256=None,
            final_inventory=[],
        )

    (tmp_path / "campaign-ledger.json").write_bytes(
        canonical_json_bytes(
            {
                "schema_version": CAMPAIGN_SCHEMA_VERSION,
                "record_type": CAMPAIGN_LEDGER_TYPE,
                "campaign": campaign.identity.as_payload(),
                "events": [
                    {"event": "leased", "authorization_id": "a6-seed-1", "status": "leased"}
                ],
            }
        )
    )

    with pytest.raises(CampaignError):
        acquire_campaign_lease(tmp_path, campaign, "a7-seed-1")
