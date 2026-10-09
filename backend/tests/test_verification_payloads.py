"""封闭载荷与次序的夹具回归。

摘要只在进程内重算，用来核对载荷形状。不把这些值写成冻结结果。
"""

from __future__ import annotations

import pytest

from app.verification import (
    HandMaterials,
    MaterialBindingError,
    ProtocolAuditError,
    ProtocolSpecError,
    PurposeRole,
    SpecIncompleteError,
    deal_mapping_payload,
    protocol_digest,
    protocol_payload,
    public_summary_mapping_payload,
    purpose_index_mapping_payload,
    read_record_digest,
    schedule_payload,
    verify_manifest_binding,
)
from app.verification.materials import require_supplied_materials_order

from .verification_helpers import build_fixture, protocol_spec


def test_payloads_keep_closed_fields() -> None:
    spec = build_fixture().spec
    schedule = schedule_payload(spec)
    assert schedule["schema"] == "schedule-v1"
    assert "campaign" not in schedule
    assert schedule["block"] == spec.block
    assert [hand["hand_ordinal"] for hand in schedule["hands"]] == [
        plan.hand_ordinal for plan in spec.schedule
    ]
    deal = deal_mapping_payload()
    assert deal["schema"] == "deal-mapping-v1"
    assert len(deal["deck_order"]) == 52
    assert deal["player_count_max"] == 23
    purpose = purpose_index_mapping_payload()
    assert [item["label"] for item in purpose["purposes"]] == [
        "deal",
        "non_probed",
        "arm_m",
        "arm_b",
    ]
    assert purpose["purposes"][1]["domain"]["size"] == 1 << 256
    summary = public_summary_mapping_payload()
    assert summary["probed_seat_style"] == "tight"
    assert summary["style_cycle"] == ["tight", "aggressive", "calling"]
    protocol = protocol_payload(spec.protocol)
    assert set(protocol) == {
        "schema",
        "source_interface_id",
        "environment_record",
        "rejection_rule",
        "purposes",
        "traversal_order",
        "commitment_form",
        "audit_format_version",
        "digest_algorithm",
        "read_record_encoding",
    }
    assert protocol["rejection_rule"] == "rejection-whole-multiple-truncation-v1"
    assert len(protocol_digest(spec.protocol)) == 64


def test_read_records_must_stay_in_physical_order() -> None:
    reads = build_fixture().audit.reads
    read_record_digest(reads, encoding="compact-json-v1", algorithm="sha256")
    swapped = (reads[1], reads[0], *reads[2:])
    with pytest.raises(ProtocolAuditError, match="物理序号"):
        read_record_digest(swapped, encoding="compact-json-v1", algorithm="sha256")


def test_supplied_materials_reject_bad_order_and_foreign_protocol() -> None:
    fixture = build_fixture()
    require_supplied_materials_order(fixture.spec, fixture.bundle)
    shuffled = list(fixture.bundle[0].entries)
    shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
    bundle = (
        HandMaterials(
            hand_ordinal=fixture.bundle[0].hand_ordinal, entries=tuple(shuffled)
        ),
    )
    with pytest.raises(SpecIncompleteError):
        require_supplied_materials_order(fixture.spec, bundle)
    with pytest.raises(MaterialBindingError, match="规格上的协议"):
        verify_manifest_binding(
            protocol=protocol_spec(),
            manifest=fixture.material_manifest,
            reads=fixture.audit.reads,
            bundle=fixture.bundle,
            commitment=fixture.audit.commitment,
            spec=fixture.spec,
        )


def test_integer_rendering_rejects_leading_zeros() -> None:
    purpose = protocol_spec().purpose_for_role(PurposeRole.DEAL)
    assert purpose.field_integer(("aa" * 32, "0", "10", "0"), "hand") == 10
    assert purpose.field_integer(("aa" * 32, "0", "0", "0"), "block") == 0
    with pytest.raises(ProtocolSpecError):
        purpose.field_integer(("aa" * 32, "00", "1", "0"), "block")
    with pytest.raises(ProtocolSpecError):
        purpose.field_integer(("aa" * 32, "0", "+1", "0"), "hand")
    with pytest.raises(ProtocolSpecError):
        purpose.field_integer(("aa" * 32, "0", "1", " 1"), "draw")
    for raw in ("１", "١", "²"):
        with pytest.raises(ProtocolSpecError):
            purpose.field_integer(("aa" * 32, "0", raw, "0"), "hand")
