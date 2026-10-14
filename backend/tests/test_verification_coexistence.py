"""两种协议的来源句、构造计划与送交材料。夹具都在内存中，不是实际材料。"""

from __future__ import annotations

import pytest

from app.verification import (
    ExecutionIdentityRecord,
    IdentityMappingError,
    MaterialBindingError,
    MaterialEntry,
    SpecIncompleteError,
    bundle_payload,
    content_digest,
    instantiation_caliber_entries,
    manifest_digest,
    materials_digest,
    plan_payload,
    require_instantiation_caliber,
    require_supplied_materials_order,
    verify_manifest_binding,
)
from app.verification.execution_identity import (
    ARM_B_SCOPE_CONFLICT,
    SEED_SENTENCE_V1,
    SEED_SENTENCE_V2,
    CoverageEntry,
)
from app.verification.materials import _PROTOCOL_V2, HandMaterials
from app.verification.protocol import PROTOCOL_SCHEMA_V2, v2_record_sort_key

from .verification_helpers import (
    build_fixture,
    build_v2_frozen_fixture,
    construction_caliber,
    fixture_projection_hex,
    v2_anchor_entries,
    v2_run_spec,
)


def _kappa_rows(spec, events: tuple[str, ...]) -> list[tuple[str, tuple[str, ...]]]:
    sigma = fixture_projection_hex()
    rows: list[tuple[str, tuple[str, ...]]] = []
    for label, key in v2_anchor_entries(spec, sigma):
        if label not in ("non_probed", "arm_b"):
            rows.append((label, key))
            continue
        for event in events:
            fields = list(key)
            fields[4] = event
            rows.append((label, tuple(fields)))
    return rows


def _bundle(spec, rows: list[tuple[str, tuple[str, ...]]]):
    ordered = sorted(rows, key=lambda item: v2_record_sort_key(item[0], item[1]))
    by_hand: dict[int, list[MaterialEntry]] = {}
    for label, key in ordered:
        if label == "deal":
            value = int(key[3])
        elif label == "arm_m":
            value = 7
        else:
            value = int(key[4])
        by_hand.setdefault(int(key[2]), []).append(
            MaterialEntry(purpose_label=label, index_key=key, value=value)
        )
    return tuple(
        HandMaterials(hand_ordinal=plan.hand_ordinal, entries=tuple(by_hand[plan.hand_ordinal]))
        for plan in spec.schedule
    )


def _replace(identity: ExecutionIdentityRecord, name: str, value: str) -> ExecutionIdentityRecord:
    categories = []
    for category, entries in identity.categories:
        updated = tuple(
            entry.model_copy(update={"value": value}) if entry.name == name else entry
            for entry in entries
        )
        categories.append((category, updated))
    return identity.model_copy(update={"categories": tuple(categories)})


def test_version_one_plan_stays_a_single_material_array() -> None:
    fixture = build_fixture()
    payload = plan_payload(spec=fixture.spec, caliber=fixture.caliber, bundle=fixture.bundle)
    assert isinstance(payload, list)
    seat = payload[0]["seats"][0]
    assert "material" in seat
    assert "materials" not in seat
    wrapped = {"schema": "construction-plan-v2", "hands": payload}
    algorithm = fixture.spec.protocol.digest_algorithm
    assert content_digest(payload, algorithm=algorithm) != content_digest(
        wrapped, algorithm=algorithm
    )
    entries = dict(
        instantiation_caliber_entries(
            spec=fixture.spec,
            caliber=fixture.caliber,
            bundle=fixture.bundle,
            algorithm=algorithm,
        )
    )
    assert entries["baseline-effective-seed"] == SEED_SENTENCE_V1
    assert entries["arm-b-seed-scope-conflict"] == ARM_B_SCOPE_CONFLICT
    assert entries["baseline-effective-samples"] == "500"
    assert entries["baseline-effective-bluff-freq"] == "0.1"


def test_version_two_plan_uses_closed_slices_and_integer_order() -> None:
    spec = v2_run_spec()
    rows = _kappa_rows(spec, ("2", "10"))
    bundle = _bundle(spec, rows)
    caliber = construction_caliber()
    require_supplied_materials_order(spec, bundle, closed_entries=rows)
    assert len(bundle[0].entries) != 3 * spec.num_players + 6
    payload = plan_payload(
        spec=spec, caliber=caliber, bundle=bundle, closed_entries=rows
    )
    assert payload["schema"] == "construction-plan-v2"
    hands = payload["hands"]
    under_test, baseline = hands
    probed = spec.schedule[0].probed_seat
    under_probed = next(item for item in under_test["seats"] if item["seat"] == probed)
    base_probed = next(item for item in baseline["seats"] if item["seat"] == probed)
    assert [item["purpose_label"] for item in under_probed["materials"]] == ["arm_m"]
    assert [item["value"] for item in base_probed["materials"]] == [2, 10]
    assert "material" not in base_probed
    assert "samples" not in base_probed["materials"][0]
    assert "bluff_freq" not in base_probed["materials"][0]
    other = next(seat for seat in range(spec.num_players) if seat != probed)
    left = next(item for item in under_test["seats"] if item["seat"] == other)
    right = next(item for item in baseline["seats"] if item["seat"] == other)
    assert left["materials"] == right["materials"]
    algorithm = spec.protocol.digest_algorithm
    assert content_digest(payload, algorithm=algorithm) != content_digest(
        hands, algorithm=algorithm
    )
    entries = dict(
        instantiation_caliber_entries(
            spec=spec,
            caliber=caliber,
            bundle=bundle,
            algorithm=algorithm,
            closed_entries=rows,
        )
    )
    assert entries["baseline-effective-seed"] == SEED_SENTENCE_V2
    assert entries["arm-b-seed-scope-conflict"] == ARM_B_SCOPE_CONFLICT


def test_version_two_identity_rejects_unwrapped_plan_digest() -> None:
    """版本 2 身份若改记未包 schema 的数组摘要，校验链必须点名该条目失败。"""
    fixture, rows = build_v2_frozen_fixture()
    algorithm = fixture.spec.protocol.digest_algorithm
    payload = plan_payload(
        spec=fixture.spec,
        caliber=fixture.caliber,
        bundle=fixture.bundle,
        closed_entries=rows,
    )
    bare = content_digest(payload["hands"], algorithm=algorithm)
    rewritten = _replace(fixture.identity, "construction-plan-digest", bare)
    with pytest.raises(IdentityMappingError, match="construction-plan-digest"):
        require_instantiation_caliber(
            rewritten,
            spec=fixture.spec,
            caliber=fixture.caliber,
            bundle=fixture.bundle,
            algorithm=algorithm,
            closed_entries=rows,
        )


def test_version_one_identity_rejects_wrapped_plan_digest() -> None:
    """版本 1 身份若改记带 schema 包装的摘要，校验链必须点名该条目失败。"""
    fixture = build_fixture()
    algorithm = fixture.spec.protocol.digest_algorithm
    payload = plan_payload(spec=fixture.spec, caliber=fixture.caliber, bundle=fixture.bundle)
    wrapped = content_digest(
        {"schema": "construction-plan-v2", "hands": payload},
        algorithm=algorithm,
    )
    rewritten = _replace(fixture.identity, "construction-plan-digest", wrapped)
    with pytest.raises(IdentityMappingError, match="construction-plan-digest"):
        require_instantiation_caliber(
            rewritten,
            spec=fixture.spec,
            caliber=fixture.caliber,
            bundle=fixture.bundle,
            algorithm=algorithm,
        )


def test_materials_schema_literal_matches_protocol_constant() -> None:
    assert _PROTOCOL_V2 == PROTOCOL_SCHEMA_V2


def test_swapped_seed_sentence_fails_for_each_protocol() -> None:
    version_one = build_fixture()
    rewritten = _replace(version_one.identity, "baseline-effective-seed", SEED_SENTENCE_V2)
    with pytest.raises(IdentityMappingError):
        require_instantiation_caliber(
            rewritten,
            spec=version_one.spec,
            caliber=version_one.caliber,
            bundle=version_one.bundle,
            algorithm=version_one.spec.protocol.digest_algorithm,
        )
    version_two, rows = build_v2_frozen_fixture()
    rewritten = _replace(version_two.identity, "baseline-effective-seed", SEED_SENTENCE_V1)
    with pytest.raises(IdentityMappingError):
        require_instantiation_caliber(
            rewritten,
            spec=version_two.spec,
            caliber=version_two.caliber,
            bundle=version_two.bundle,
            algorithm=version_two.spec.protocol.digest_algorithm,
            closed_entries=rows,
        )


def test_pending_scope_marker_is_no_longer_legal() -> None:
    fixture = build_fixture()
    pending = "pending:per-hand-arm_b-material-vs-per-kappa-arm_b"
    categories = []
    for category, entries in fixture.identity.categories:
        categories.append(
            (
                category,
                tuple(
                    CoverageEntry(
                        name=entry.name,
                        value=pending
                        if entry.name == "arm-b-seed-scope-conflict"
                        else entry.value,
                    )
                    for entry in entries
                ),
            )
        )
    with pytest.raises(SpecIncompleteError):
        ExecutionIdentityRecord(
            categories=tuple(categories),
            reference_snapshot=fixture.identity.reference_snapshot,
        )


def test_slice_gaps_bad_order_and_illegal_values_fail() -> None:
    spec = v2_run_spec()
    rows = _kappa_rows(spec, ("2", "10"))
    bundle = _bundle(spec, rows)
    missing = [
        item
        for item in rows
        if not (len(item[1]) > 4 and item[1][4] == "10" and item[0] in ("arm_b", "non_probed"))
    ]
    with pytest.raises(SpecIncompleteError, match="不一致"):
        require_supplied_materials_order(spec, bundle, closed_entries=missing)
    sample = next(item for item in rows if item[0] == "arm_b")
    fields = list(sample[1])
    fields[4] = "11"
    extra_key = tuple(fields)
    enlarged = (
        HandMaterials(
            hand_ordinal=bundle[0].hand_ordinal,
            entries=bundle[0].entries
            + (MaterialEntry(purpose_label="arm_b", index_key=extra_key, value=3),),
        ),
    )
    with pytest.raises(SpecIncompleteError, match="不一致"):
        require_supplied_materials_order(spec, enlarged, closed_entries=rows)
    swapped = list(bundle[0].entries)
    first = next(
        index
        for index, entry in enumerate(swapped)
        if len(entry.index_key) > 4 and entry.index_key[4] == "2"
    )
    second = next(
        index
        for index, entry in enumerate(swapped)
        if len(entry.index_key) > 4 and entry.index_key[4] == "10"
    )
    swapped[first], swapped[second] = swapped[second], swapped[first]
    disordered = (
        HandMaterials(hand_ordinal=bundle[0].hand_ordinal, entries=tuple(swapped)),
    )
    with pytest.raises(SpecIncompleteError, match="升序"):
        require_supplied_materials_order(spec, disordered, closed_entries=rows)
    padded = list(sample[1])
    padded[4] = "02"
    bad_key = tuple(padded)
    bad_entries = tuple(
        MaterialEntry(purpose_label=entry.purpose_label, index_key=bad_key, value=entry.value)
        if entry.purpose_label == "arm_b" and entry.index_key == sample[1]
        else entry
        for entry in bundle[0].entries
    )
    bad_rows = [
        (label, bad_key if label == "arm_b" and key == sample[1] else key)
        for label, key in rows
    ]
    with pytest.raises(SpecIncompleteError, match="前导零"):
        require_supplied_materials_order(
            spec,
            (HandMaterials(hand_ordinal=bundle[0].hand_ordinal, entries=bad_entries),),
            closed_entries=bad_rows,
        )
    with pytest.raises(SpecIncompleteError, match="重复"):
        HandMaterials(
            hand_ordinal=1,
            entries=(bundle[0].entries[0], bundle[0].entries[0]),
        )
    with pytest.raises(SpecIncompleteError):
        MaterialEntry(purpose_label="arm_b", index_key=sample[1], value=True)  # type: ignore[arg-type]
    with pytest.raises(SpecIncompleteError):
        MaterialEntry(purpose_label="arm_b", index_key=sample[1], value=None)  # type: ignore[arg-type]
    huge = MaterialEntry(purpose_label="arm_b", index_key=sample[1], value=1 << 256)
    replaced = tuple(
        huge if entry.index_key == sample[1] and entry.purpose_label == "arm_b" else entry
        for entry in bundle[0].entries
    )
    with pytest.raises(SpecIncompleteError, match="超出范围"):
        require_supplied_materials_order(
            spec,
            (HandMaterials(hand_ordinal=bundle[0].hand_ordinal, entries=replaced),),
            closed_entries=rows,
        )


def test_version_two_supplied_digest_matches_plan_slices_and_manifest() -> None:
    """核验第二版送交材料摘要重算、与构造计划同座切片一致、以及与材料清单逐项一致。"""
    fixture, rows = build_v2_frozen_fixture()
    spec = fixture.spec
    bundle = fixture.bundle
    manifest = fixture.material_manifest
    algorithm = spec.protocol.digest_algorithm

    raw_bundle = bundle_payload(bundle)
    assert isinstance(raw_bundle, list)
    recomputed = materials_digest(
        bundle, spec=spec, algorithm=algorithm, closed_entries=rows
    )
    assert recomputed == content_digest(raw_bundle, algorithm=algorithm)
    assert recomputed != manifest_digest(manifest, algorithm=algorithm)

    manifest_items = [
        (entry.purpose_label, entry.index_key, entry.value)
        for entry in manifest.entries
    ]
    bundle_items = [
        (entry.purpose_label, entry.index_key, entry.value)
        for hand in bundle
        for entry in hand.entries
    ]
    assert set(manifest_items) == set(bundle_items)
    assert len(manifest_items) == len(bundle_items)

    plan = plan_payload(
        spec=spec,
        caliber=fixture.caliber,
        bundle=bundle,
        closed_entries=rows,
    )
    by_hand = {hand.hand_ordinal: hand for hand in bundle}
    for hand_plan in plan["hands"]:
        hand_materials = by_hand[hand_plan["hand_ordinal"]]
        probed_seat = hand_plan["probed_seat"]
        arm = hand_plan["arm"]
        for seat_entry in hand_plan["seats"]:
            seat = seat_entry["seat"]
            if seat == probed_seat and arm == "under-test":
                expected = [
                    item.canonical_payload()
                    for item in hand_materials.entries_for("arm_m")
                ]
            elif seat == probed_seat:
                expected = [
                    item.canonical_payload()
                    for item in hand_materials.entries_for("arm_b")
                    if int(item.index_key[3]) == seat
                ]
            else:
                expected = [
                    item.canonical_payload()
                    for item in hand_materials.entries_for("non_probed")
                    if int(item.index_key[3]) == seat
                ]
            assert seat_entry["materials"] == expected

    verify_manifest_binding(
        protocol=spec.protocol,
        manifest=manifest,
        reads=fixture.audit.reads,
        bundle=bundle,
        commitment=fixture.audit.commitment,
        spec=spec,
        closed_entries=rows,
    )
    tampered_entries = (
        MaterialEntry(
            purpose_label=bundle[0].entries[0].purpose_label,
            index_key=bundle[0].entries[0].index_key,
            value=bundle[0].entries[0].value + 1,
        ),
        *bundle[0].entries[1:],
    )
    tampered_bundle = (
        HandMaterials(hand_ordinal=bundle[0].hand_ordinal, entries=tampered_entries),
        *bundle[1:],
    )
    with pytest.raises(MaterialBindingError, match="不一致"):
        verify_manifest_binding(
            protocol=spec.protocol,
            manifest=manifest,
            reads=fixture.audit.reads,
            bundle=tampered_bundle,
            commitment=fixture.audit.commitment,
            spec=spec,
            closed_entries=rows,
        )
