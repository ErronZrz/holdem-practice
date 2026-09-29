"""随机化协议结构、逐读取审计核验与材料绑定的契约回归。

只做有界单元回归：不跑对局、不生成材料、不写任何工件，也不构成任何质量结论。
审计示例由测试辅助在内存中拼出，只用于覆盖校验分支，不是任何材料清单或冻结工件。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.verification import (
    FixedDomain,
    MaterialBindingError,
    MaterialEntry,
    MaterialManifest,
    ProtocolAuditError,
    ProtocolSpecError,
    PurposeRole,
    PurposeSpec,
    RandomizationProtocolSpec,
    ReadRecord,
    ShrinkingDomain,
    TranscriptCommitment,
    bytes_digest,
    manifest_digest,
    read_record_digest,
    require_manifest_consistent,
    required_bit_width,
    resolve_read,
    verify_audit,
    verify_manifest_binding,
    verify_material_binding,
)

from .verification_helpers import (
    BASELINE_LABEL,
    BLOCK,
    CONFIGURATION,
    DEAL_LABEL,
    NON_PROBED_LABEL,
    REJECTED_RAW,
    SEAT_FIELD,
    TRAVERSAL_ORDER,
    UNDER_TEST_LABEL,
    audit_from_plan,
    build_fixture,
    entries_of,
    hand_field,
    protocol_spec,
    read_plan,
    recommit_audit,
    replace_entries,
    replace_manifest_entry,
    replace_reads,
)

FIXTURE = build_fixture()


def _draw_purpose() -> PurposeSpec:
    for purpose in protocol_spec().purposes:
        if purpose.role is PurposeRole.DEAL:
            return purpose
    raise AssertionError("测试协议必须声明发牌用途")


def _deal_index(hand: int, draw: int) -> tuple[str, ...]:
    """测试自建的发牌索引键：手号零填充，抽取次序为整数定位字段。"""
    return (CONFIGURATION, BLOCK, hand_field(hand), str(draw))


def _verify(protocol: RandomizationProtocolSpec, audit) -> None:
    """按给定协议复核一份审计凭据。"""
    verify_audit(
        protocol=protocol,
        transcript=audit.transcript,
        reads=audit.reads,
        commitment=audit.commitment,
    )


# ------------------------------------------------------------------ 位宽与拒绝规则


@pytest.mark.parametrize(
    ("domain_size", "expected"),
    [(1, 8), (2, 8), (52, 8), (256, 8), (257, 16), (1 << 64, 64), (1 << 256, 256)],
)
def test_required_bit_width_covers_domain(domain_size: int, expected: int) -> None:
    assert required_bit_width(domain_size) == expected


def test_required_bit_width_rejects_empty_domain() -> None:
    with pytest.raises(ProtocolSpecError):
        required_bit_width(0)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, 0), (10, 10), (207, 51), (208, None), (255, None)],
)
def test_resolve_read_follows_rejection_rule(raw: int, expected: int | None) -> None:
    assert resolve_read(raw, bit_width=8, domain_size=52) == expected


def test_resolve_read_accepts_whole_range_when_domain_divides_it() -> None:
    assert resolve_read((1 << 64) - 1, bit_width=64, domain_size=1 << 64) == (1 << 64) - 1


@pytest.mark.parametrize("bit_width", [0, -8, 7])
def test_resolve_read_requires_byte_aligned_positive_width(bit_width: int) -> None:
    with pytest.raises(ProtocolSpecError):
        resolve_read(0, bit_width=bit_width, domain_size=2)


def test_resolve_read_requires_sufficient_width() -> None:
    with pytest.raises(ProtocolSpecError):
        resolve_read(0, bit_width=8, domain_size=1 << 16)


def test_resolve_read_rejects_out_of_range_raw_value() -> None:
    with pytest.raises(ProtocolAuditError):
        resolve_read(300, bit_width=8, domain_size=52)


# ------------------------------------------------------------------ 协议结构校验


def test_protocol_spec_accepts_four_roles_in_order() -> None:
    protocol = protocol_spec()
    assert protocol.traversal_order == TRAVERSAL_ORDER
    assert protocol.purpose_for_role(PurposeRole.DEAL).label == DEAL_LABEL
    assert protocol.purpose_for_role(PurposeRole.BASELINE_SEED).label == BASELINE_LABEL
    assert protocol.has_label(DEAL_LABEL) is True
    assert protocol.has_label("unknown-purpose") is False


def test_protocol_spec_requires_all_roles_once() -> None:
    purposes = protocol_spec().purposes
    with pytest.raises(ProtocolSpecError):
        protocol_spec(purposes=purposes[:-1])
    duplicated = (*purposes[:-1], purposes[-2])
    with pytest.raises(ProtocolSpecError):
        protocol_spec(purposes=duplicated)


def test_protocol_spec_requires_matching_traversal_order() -> None:
    with pytest.raises(ProtocolSpecError):
        protocol_spec(traversal_order=(DEAL_LABEL, NON_PROBED_LABEL))


def test_protocol_spec_rejects_unimplemented_algorithm_and_encoding() -> None:
    with pytest.raises(ProtocolSpecError):
        protocol_spec(digest_algorithm="sha512")
    with pytest.raises(ProtocolSpecError):
        protocol_spec(read_record_encoding="json-lines")


def test_protocol_spec_requires_non_empty_source_and_environment() -> None:
    with pytest.raises(ProtocolSpecError):
        protocol_spec(source_interface_id="   ")
    with pytest.raises(ProtocolSpecError):
        protocol_spec(environment_record="   ")


def test_protocol_spec_rejects_duplicate_labels() -> None:
    purposes = protocol_spec().purposes
    with pytest.raises(ProtocolSpecError):
        protocol_spec(
            purposes=(
                purposes[0],
                purposes[1].model_copy(update={"label": DEAL_LABEL}),
                purposes[2],
                purposes[3],
            )
        )


def test_deal_purpose_requires_shrinking_domain() -> None:
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=PurposeRole.DEAL,
            label=DEAL_LABEL,
            index_fields=("draw",),
            draw_index_field="draw",
            domain=FixedDomain(size=52),
            bit_width=8,
        )


def test_deal_purpose_requires_draw_index_field() -> None:
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=PurposeRole.DEAL,
            label=DEAL_LABEL,
            index_fields=("draw",),
            domain=ShrinkingDomain(initial_size=52),
            bit_width=8,
        )
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=PurposeRole.DEAL,
            label=DEAL_LABEL,
            index_fields=("draw", "seat"),
            draw_index_field="draw",
            seat_index_field="seat",
            domain=ShrinkingDomain(initial_size=52),
            bit_width=8,
        )


def test_non_probed_purpose_requires_seat_index_field() -> None:
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=PurposeRole.NON_PROBED_SEED,
            label=NON_PROBED_LABEL,
            index_fields=("seat",),
            domain=FixedDomain(size=1 << 64),
            bit_width=64,
        )


@pytest.mark.parametrize("role", [PurposeRole.UNDER_TEST_MATERIAL, PurposeRole.BASELINE_SEED])
def test_other_purposes_declare_no_locator_field(role: PurposeRole) -> None:
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=role,
            label=BASELINE_LABEL,
            index_fields=("draw", SEAT_FIELD),
            draw_index_field="draw",
            domain=FixedDomain(size=1 << 64),
            bit_width=64,
        )
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=role,
            label=BASELINE_LABEL,
            index_fields=(SEAT_FIELD,),
            seat_index_field=SEAT_FIELD,
            domain=FixedDomain(size=1 << 64),
            bit_width=64,
        )


def test_non_deal_purpose_requires_fixed_domain() -> None:
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=PurposeRole.BASELINE_SEED,
            label=BASELINE_LABEL,
            index_fields=("hand",),
            domain=ShrinkingDomain(initial_size=1 << 64),
            bit_width=64,
        )


@pytest.mark.parametrize("bit_width", [4, 9])
def test_purpose_spec_requires_byte_aligned_width(bit_width: int) -> None:
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=PurposeRole.BASELINE_SEED,
            label=BASELINE_LABEL,
            index_fields=("hand",),
            domain=ShrinkingDomain(initial_size=52),
            bit_width=bit_width,
        )


def test_purpose_spec_requires_sufficient_width() -> None:
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=PurposeRole.BASELINE_SEED,
            label=BASELINE_LABEL,
            index_fields=("hand",),
            domain=FixedDomain(size=1 << 64),
            bit_width=8,
        )


def test_purpose_spec_rejects_duplicate_index_fields() -> None:
    with pytest.raises(ProtocolSpecError):
        PurposeSpec(
            role=PurposeRole.BASELINE_SEED,
            label=BASELINE_LABEL,
            index_fields=("hand", "hand"),
            domain=ShrinkingDomain(initial_size=52),
            bit_width=8,
        )


def test_draw_index_lookup_reports_locator_failures() -> None:
    purpose = _draw_purpose()
    assert purpose.draw_index_of(("cfg", "b1", "1", "3")) == 3
    with pytest.raises(ProtocolSpecError):
        purpose.draw_index_of(("cfg", "1", "3"))
    with pytest.raises(ProtocolSpecError):
        purpose.draw_index_of(("cfg", "b1", "1", "x"))
    with pytest.raises(ProtocolSpecError):
        purpose.draw_index_of(("cfg", "b1", "1", "-1"))


def test_seat_index_lookup_requires_declared_field() -> None:
    purpose = protocol_spec().purpose_for_role(PurposeRole.BASELINE_SEED)
    with pytest.raises(ProtocolSpecError):
        purpose.seat_index_of(("cfg", "b1", "1"))


# ------------------------------------------------------------------ 读取记录校验


def test_read_record_requires_output_only_when_accepted() -> None:
    with pytest.raises(ProtocolAuditError):
        ReadRecord(
            read_index=0,
            purpose_label=DEAL_LABEL,
            index_key=("a",),
            bit_width=8,
            raw_offset=0,
            raw_value=1,
            accepted=True,
        )
    with pytest.raises(ProtocolAuditError):
        ReadRecord(
            read_index=0,
            purpose_label=DEAL_LABEL,
            index_key=("a",),
            bit_width=8,
            raw_offset=0,
            raw_value=1,
            accepted=False,
            output=1,
        )


def test_read_record_rejects_raw_value_beyond_width() -> None:
    with pytest.raises(ProtocolAuditError):
        ReadRecord(
            read_index=0,
            purpose_label=DEAL_LABEL,
            index_key=("a",),
            bit_width=8,
            raw_offset=0,
            raw_value=256,
            accepted=False,
        )


def test_read_record_requires_non_empty_index_key() -> None:
    with pytest.raises(ProtocolAuditError):
        ReadRecord(
            read_index=0,
            purpose_label=DEAL_LABEL,
            index_key=(),
            bit_width=8,
            raw_offset=0,
            raw_value=1,
            accepted=False,
        )


def test_read_record_reports_byte_length() -> None:
    record = ReadRecord(
        read_index=0,
        purpose_label=DEAL_LABEL,
        index_key=("a",),
        bit_width=64,
        raw_offset=0,
        raw_value=1,
        accepted=False,
    )
    assert record.byte_length == 8


# ------------------------------------------------------------------ 审计核验


def test_well_formed_audit_passes() -> None:
    audit = FIXTURE.audit
    verify_audit(
        protocol=FIXTURE.spec.protocol,
        transcript=audit.transcript,
        reads=audit.reads,
        commitment=audit.commitment,
    )


def test_audit_contains_a_rejected_read() -> None:
    assert any(not record.accepted for record in FIXTURE.audit.reads)


def test_transcript_must_be_bytes() -> None:
    audit = FIXTURE.audit
    with pytest.raises(ProtocolAuditError):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=bytearray(audit.transcript),
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_commitment_must_match_protocol() -> None:
    audit = FIXTURE.audit
    commitment = audit.commitment.model_copy(update={"traversal_order": (DEAL_LABEL,)})
    with pytest.raises(ProtocolAuditError, match="遍历顺序"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=commitment,
        )


def test_commitment_environment_record_must_match_protocol() -> None:
    audit = recommit_audit(FIXTURE.audit, environment_record="另一台机器的环境记录")
    with pytest.raises(ProtocolAuditError, match="环境记录"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_transcript_digest_mismatch_fails() -> None:
    audit = FIXTURE.audit
    commitment = audit.commitment.model_copy(update={"transcript_digest": "0" * 64})
    with pytest.raises(ProtocolAuditError, match="转录摘要"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=commitment,
        )


def test_read_digest_mismatch_fails() -> None:
    audit = FIXTURE.audit
    reads = replace_reads(audit, 0, output=11)
    with pytest.raises(ProtocolAuditError, match="逐读取记录摘要"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=reads,
            commitment=audit.commitment,
        )


def test_offset_gap_fails() -> None:
    audit = recommit_audit(FIXTURE.audit, reads=replace_reads(FIXTURE.audit, 2, raw_offset=99))
    with pytest.raises(ProtocolAuditError, match="偏移"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_read_index_must_be_contiguous() -> None:
    reads = tuple(
        record.model_copy(update={"read_index": index + 1})
        for index, record in enumerate(FIXTURE.audit.reads)
    )
    audit = recommit_audit(FIXTURE.audit, reads=reads)
    with pytest.raises(ProtocolAuditError, match="序号"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_raw_value_must_match_transcript() -> None:
    audit = recommit_audit(FIXTURE.audit, reads=replace_reads(FIXTURE.audit, 0, raw_value=11))
    with pytest.raises(ProtocolAuditError, match="原始值"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_bit_width_must_match_protocol() -> None:
    audit = recommit_audit(FIXTURE.audit, reads=replace_reads(FIXTURE.audit, 0, bit_width=16))
    with pytest.raises(ProtocolAuditError, match="位宽"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_index_key_length_must_match_index_fields() -> None:
    audit = recommit_audit(
        FIXTURE.audit, reads=replace_reads(FIXTURE.audit, 0, index_key=("cfg",))
    )
    with pytest.raises(ProtocolAuditError, match="索引取值数"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_undeclared_purpose_label_fails() -> None:
    audit = recommit_audit(
        FIXTURE.audit, reads=replace_reads(FIXTURE.audit, 0, purpose_label="unknown-purpose")
    )
    with pytest.raises(ProtocolAuditError, match="未声明的用途标签"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_traversal_order_violation_fails() -> None:
    plan = read_plan(FIXTURE.spec.protocol, ((1, 1),), 3)
    moved = next(index for index, item in enumerate(plan) if item[0] == NON_PROBED_LABEL)
    reordered = (plan[moved], *plan[:moved], *plan[moved + 1 :])
    audit = audit_from_plan(FIXTURE.spec.protocol, reordered)
    with pytest.raises(ProtocolAuditError, match="遍历顺序"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_rejected_read_marked_accepted_fails() -> None:
    rejected = [
        index for index, record in enumerate(FIXTURE.audit.reads) if not record.accepted
    ]
    audit = recommit_audit(
        FIXTURE.audit,
        reads=replace_reads(FIXTURE.audit, rejected[0], accepted=True, output=5),
    )
    with pytest.raises(ProtocolAuditError, match="应丢弃"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_flipped_output_fails() -> None:
    accepted = next(
        index for index, record in enumerate(FIXTURE.audit.reads) if record.accepted
    )
    original = FIXTURE.audit.reads[accepted].output
    assert original is not None
    audit = recommit_audit(
        FIXTURE.audit, reads=replace_reads(FIXTURE.audit, accepted, output=original + 1)
    )
    with pytest.raises(ProtocolAuditError, match="重算结果"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_read_after_acceptance_of_same_index_fails() -> None:
    plan = read_plan(FIXTURE.spec.protocol, ((1, 1),), 3)
    accepted = next(item for item in plan if item[0] == DEAL_LABEL and item[2] == 0)
    insertion = plan.index(accepted) + 1
    audit = audit_from_plan(
        FIXTURE.spec.protocol, (*plan[:insertion], accepted, *plan[insertion:])
    )
    with pytest.raises(ProtocolAuditError, match="不得再次读取"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_rejection_must_follow_index_order() -> None:
    """被拒绝的读取也带索引：把第 0 次发牌的拒绝移到第 1 次之后即乱序。"""
    plan = list(read_plan(FIXTURE.spec.protocol, ((1, 1),), 3))
    rejection = next(
        index
        for index, item in enumerate(plan)
        if item[0] == DEAL_LABEL and item[2] == REJECTED_RAW
    )
    moved = plan.pop(rejection)
    plan.insert(rejection + 2, moved)
    audit = audit_from_plan(FIXTURE.spec.protocol, tuple(plan))
    with pytest.raises(ProtocolAuditError, match="索引顺序"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_index_order_within_purpose_is_enforced() -> None:
    plan = list(read_plan(FIXTURE.spec.protocol, ((1, 1),), 3))
    seats = [
        index
        for index, item in enumerate(plan)
        if item[0] == NON_PROBED_LABEL
    ]
    plan[seats[0]], plan[seats[1]] = plan[seats[1]], plan[seats[0]]
    audit = audit_from_plan(FIXTURE.spec.protocol, tuple(plan))
    with pytest.raises(ProtocolAuditError, match="索引顺序"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_deal_draw_coverage_must_be_contiguous() -> None:
    """整组删掉第 0 次发牌读取后，抽取次序不再从零起连续，必须失败。"""
    plan = tuple(
        item
        for item in read_plan(FIXTURE.spec.protocol, ((1, 1),), 3)
        if not (item[0] == DEAL_LABEL and item[1][-1] == "0")
    )
    audit = audit_from_plan(FIXTURE.spec.protocol, plan)
    with pytest.raises(ProtocolAuditError, match="从零起连续"):
        _verify(FIXTURE.spec.protocol, audit)


def test_rejection_group_must_close_before_the_next_index() -> None:
    """同一索引的拒绝读取之后必须出现同键接受读取，否则索引切换即失败。"""
    plan = list(read_plan(FIXTURE.spec.protocol, ((1, 1),), 3))
    rejected = next(
        index
        for index, item in enumerate(plan)
        if item[0] == DEAL_LABEL and item[2] == REJECTED_RAW
    )
    # 只删掉该索引的接受读取：留下的拒绝读取随即被下一个索引的读取收尾。
    del plan[rejected + 1]
    audit = audit_from_plan(FIXTURE.spec.protocol, tuple(plan))
    with pytest.raises(ProtocolAuditError, match="接受"):
        _verify(FIXTURE.spec.protocol, audit)


def test_isolated_rejection_at_purpose_end_fails() -> None:
    """用途末尾多出一条孤立拒绝读取：该索引永不接受，不得通过核验。"""
    plan = list(read_plan(FIXTURE.spec.protocol, ((1, 1),), 3))
    last_deal = max(index for index, item in enumerate(plan) if item[0] == DEAL_LABEL)
    plan.insert(
        last_deal + 1, (DEAL_LABEL, _deal_index(1, 11), REJECTED_RAW, None)
    )
    audit = audit_from_plan(FIXTURE.spec.protocol, tuple(plan))
    with pytest.raises(ProtocolAuditError, match="接受"):
        _verify(FIXTURE.spec.protocol, audit)


def test_isolated_rejection_at_audit_end_fails() -> None:
    """发牌用途排在遍历顺序末尾时，审计末尾的孤立拒绝读取同样失败。"""
    protocol = protocol_spec(
        traversal_order=(
            NON_PROBED_LABEL,
            UNDER_TEST_LABEL,
            BASELINE_LABEL,
            DEAL_LABEL,
        )
    )
    plan = list(read_plan(protocol, ((1, 1),), 3))
    plan.append((DEAL_LABEL, _deal_index(1, 11), REJECTED_RAW, None))
    audit = audit_from_plan(protocol, tuple(plan))
    with pytest.raises(ProtocolAuditError, match="接受"):
        _verify(protocol, audit)


def test_multiple_rejections_then_one_acceptance_passes() -> None:
    """同一索引连续多次拒绝、随后一次同键接受，是允许且必须通过的结构。"""
    plan = list(read_plan(FIXTURE.spec.protocol, ((1, 1),), 3))
    rejected = next(
        index
        for index, item in enumerate(plan)
        if item[0] == DEAL_LABEL and item[2] == REJECTED_RAW
    )
    plan.insert(rejected + 1, plan[rejected])
    audit = audit_from_plan(FIXTURE.spec.protocol, tuple(plan))
    key = plan[rejected][1]
    assert (
        sum(
            1
            for record in audit.reads
            if not record.accepted and record.index_key == key
        )
        == 2
    )
    assert audit.commitment.count_for("rejection_counts", DEAL_LABEL) == 2
    _verify(FIXTURE.spec.protocol, audit)


def test_multi_hand_audit_passes_end_to_end() -> None:
    fixture = build_fixture(hands=2)
    verify_audit(
        protocol=fixture.spec.protocol,
        transcript=fixture.audit.transcript,
        reads=fixture.audit.reads,
        commitment=fixture.audit.commitment,
    )
    verify_material_binding(
        protocol=fixture.spec.protocol,
        bundle=fixture.bundle,
        reads=fixture.audit.reads,
    )
    verify_manifest_binding(
        protocol=fixture.spec.protocol,
        manifest=fixture.material_manifest,
        reads=fixture.audit.reads,
        bundle=fixture.bundle,
        commitment=fixture.audit.commitment,
    )


def test_deal_domain_step_comes_from_draw_index() -> None:
    """收缩域的步数由抽取次序字段决定：第 1 次抽取可用域为 51。"""
    purpose = _draw_purpose()
    assert purpose.domain.domain_size(purpose.draw_index_of(("cfg", "b1", "01", "1"))) == 51


# ------------------------------------------------------------------ 材料清单绑定


def test_manifest_binding_passes_for_fixture() -> None:
    verify_manifest_binding(
        protocol=FIXTURE.spec.protocol,
        manifest=FIXTURE.material_manifest,
        reads=FIXTURE.audit.reads,
        bundle=FIXTURE.bundle,
        commitment=FIXTURE.audit.commitment,
    )


def test_manifest_requires_declared_labels() -> None:
    entries = list(FIXTURE.material_manifest.entries)
    first = entries[0]
    entries[0] = MaterialEntry(
        purpose_label="unknown-purpose", index_key=first.index_key, value=first.value
    )
    manifest = MaterialManifest(entries=tuple(entries))
    with pytest.raises(MaterialBindingError, match="未声明"):
        require_manifest_consistent(FIXTURE.spec.protocol, manifest)


def test_manifest_requires_canonical_order() -> None:
    entries = list(FIXTURE.material_manifest.entries)
    entries[0], entries[1] = entries[1], entries[0]
    manifest = MaterialManifest(entries=tuple(entries))
    with pytest.raises(MaterialBindingError, match="升序"):
        require_manifest_consistent(FIXTURE.spec.protocol, manifest)


def test_manifest_content_digest_is_recomputed() -> None:
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    original = FIXTURE.material_manifest.entries[0]
    changed = replace_manifest_entry(FIXTURE.material_manifest, 0, original.value + 1)
    assert manifest_digest(changed, algorithm=algorithm) != manifest_digest(
        FIXTURE.material_manifest, algorithm=algorithm
    )
    # 清单内容被改动后，即使承诺照着改，清单与审计的取值也不再一致。
    audit = recommit_audit(
        FIXTURE.audit,
        manifest_digest_value=manifest_digest(changed, algorithm=algorithm),
    )
    with pytest.raises(MaterialBindingError, match="审计"):
        verify_manifest_binding(
            protocol=FIXTURE.spec.protocol,
            manifest=changed,
            reads=audit.reads,
            bundle=FIXTURE.bundle,
            commitment=audit.commitment,
        )


def test_commitment_manifest_digest_must_match_manifest_content() -> None:
    audit = recommit_audit(FIXTURE.audit, manifest_digest_value="0" * 64)
    with pytest.raises(MaterialBindingError, match="清单摘要"):
        verify_manifest_binding(
            protocol=FIXTURE.spec.protocol,
            manifest=FIXTURE.material_manifest,
            reads=audit.reads,
            bundle=FIXTURE.bundle,
            commitment=audit.commitment,
        )


def test_manifest_must_match_supplied_materials() -> None:
    entries = entries_of(FIXTURE.bundle, 0)
    first = entries[0]
    entries[0] = MaterialEntry(
        purpose_label=first.purpose_label, index_key=first.index_key, value=first.value + 1
    )
    with pytest.raises(MaterialBindingError, match="送交材料"):
        verify_manifest_binding(
            protocol=FIXTURE.spec.protocol,
            manifest=FIXTURE.material_manifest,
            reads=FIXTURE.audit.reads,
            bundle=replace_entries(FIXTURE.bundle, 0, entries),
            commitment=FIXTURE.audit.commitment,
        )


def test_trailing_bytes_fail() -> None:
    transcript = FIXTURE.audit.transcript + b"\x00"
    audit = recommit_audit(FIXTURE.audit, transcript=transcript)
    with pytest.raises(ProtocolAuditError, match="多余字节"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_counts_must_match_reads() -> None:
    counts = tuple(
        (label, 0 if label == DEAL_LABEL else count)
        for label, count in FIXTURE.audit.commitment.entry_counts
    )
    audit = recommit_audit(FIXTURE.audit, entry_counts=counts)
    with pytest.raises(ProtocolAuditError, match="计数"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_counts_must_cover_declared_purposes() -> None:
    counts = tuple(
        (label, count)
        for label, count in FIXTURE.audit.commitment.entry_counts
        if label != DEAL_LABEL
    )
    audit = recommit_audit(FIXTURE.audit, entry_counts=counts)
    with pytest.raises(ProtocolAuditError, match="未覆盖"):
        verify_audit(
            protocol=FIXTURE.spec.protocol,
            transcript=audit.transcript,
            reads=audit.reads,
            commitment=audit.commitment,
        )


def test_commitment_rejects_unimplemented_algorithm() -> None:
    fields = FIXTURE.audit.commitment.model_dump()
    fields["digest_algorithm"] = "sha512"
    with pytest.raises(ProtocolAuditError, match="摘要算法"):
        TranscriptCommitment.model_validate(fields)


def test_commitment_requires_non_empty_digests() -> None:
    fields = FIXTURE.audit.commitment.model_dump()
    fields["manifest_digest"] = ""
    with pytest.raises(ProtocolAuditError, match="摘要字段"):
        TranscriptCommitment.model_validate(fields)


def test_commitment_requires_distinct_count_labels() -> None:
    fields = FIXTURE.audit.commitment.model_dump()
    fields["entry_counts"] = ((DEAL_LABEL, 1), (DEAL_LABEL, 2))
    with pytest.raises(ProtocolAuditError, match="互不重复"):
        TranscriptCommitment.model_validate(fields)


# ------------------------------------------------------------------ 材料绑定


def test_material_binding_passes_for_audited_materials() -> None:
    verify_material_binding(
        protocol=FIXTURE.spec.protocol,
        bundle=FIXTURE.bundle,
        reads=FIXTURE.audit.reads,
    )


def test_material_binding_rejects_value_mismatch() -> None:
    entries = entries_of(FIXTURE.bundle, 0)
    entries[0] = MaterialEntry(
        purpose_label=entries[0].purpose_label,
        index_key=entries[0].index_key,
        value=entries[0].value + 1,
    )
    with pytest.raises(MaterialBindingError, match="取值"):
        verify_material_binding(
            protocol=FIXTURE.spec.protocol,
            bundle=replace_entries(FIXTURE.bundle, 0, entries),
            reads=FIXTURE.audit.reads,
        )


def test_material_binding_rejects_missing_material() -> None:
    entries = entries_of(FIXTURE.bundle, 0)
    with pytest.raises(MaterialBindingError, match="定位不一致"):
        verify_material_binding(
            protocol=FIXTURE.spec.protocol,
            bundle=replace_entries(FIXTURE.bundle, 0, entries[1:]),
            reads=FIXTURE.audit.reads,
        )


def test_material_binding_rejects_extra_material() -> None:
    entries = entries_of(FIXTURE.bundle, 0)
    entries.append(
        MaterialEntry(
            purpose_label=BASELINE_LABEL, index_key=("cfg", "b1", "extra"), value=1
        )
    )
    with pytest.raises(MaterialBindingError, match="定位不一致"):
        verify_material_binding(
            protocol=FIXTURE.spec.protocol,
            bundle=replace_entries(FIXTURE.bundle, 0, entries),
            reads=FIXTURE.audit.reads,
        )


def test_material_binding_rejects_undeclared_label() -> None:
    entries = entries_of(FIXTURE.bundle, 0)
    entries[0] = MaterialEntry(
        purpose_label="unknown-purpose",
        index_key=entries[0].index_key,
        value=entries[0].value,
    )
    with pytest.raises(MaterialBindingError, match="未声明"):
        verify_material_binding(
            protocol=FIXTURE.spec.protocol,
            bundle=replace_entries(FIXTURE.bundle, 0, entries),
            reads=FIXTURE.audit.reads,
        )


def test_material_binding_requires_ascending_draw_order() -> None:
    entries = entries_of(FIXTURE.bundle, 0)
    entries[0], entries[1] = entries[1], entries[0]
    with pytest.raises(MaterialBindingError, match="抽取次序"):
        verify_material_binding(
            protocol=FIXTURE.spec.protocol,
            bundle=replace_entries(FIXTURE.bundle, 0, entries),
            reads=FIXTURE.audit.reads,
        )


def test_material_binding_rejects_duplicate_index_in_audit() -> None:
    source = next(record for record in FIXTURE.audit.reads if record.accepted)
    reads = (*FIXTURE.audit.reads, source.model_copy(update={"read_index": 999}))
    with pytest.raises(MaterialBindingError, match="重复"):
        verify_material_binding(
            protocol=FIXTURE.spec.protocol,
            bundle=FIXTURE.bundle,
            reads=reads,
        )


def test_protocol_spec_is_frozen() -> None:
    protocol = protocol_spec()
    with pytest.raises(ValidationError):
        protocol.source_interface_id = "other"


def test_bytes_and_record_digests_are_content_derived() -> None:
    assert bytes_digest(b"a", algorithm="sha256") != bytes_digest(b"b", algorithm="sha256")
    assert read_record_digest(
        FIXTURE.audit.reads,
        encoding=FIXTURE.spec.protocol.read_record_encoding,
        algorithm="sha256",
    ) == FIXTURE.audit.commitment.read_record_digest


def test_randomization_protocol_spec_dump_is_stable() -> None:
    protocol = protocol_spec()
    assert RandomizationProtocolSpec.model_validate(protocol.model_dump()) == protocol
