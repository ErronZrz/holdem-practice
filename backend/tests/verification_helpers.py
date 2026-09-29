"""验证运行器测试用的构造辅助：只把规格与已有材料拼起来。

这里的牌规范序、用途标签、索引键与输出域都是测试自建口径，用于覆盖结构校验的分支，
不是任何冻结取值。审计示例与材料清单由本文件在内存中拼出：既不是域 C 材料生成，
也不是任何冻结工件。

读取排布遵循结构规则：用途按遍历顺序、用途内部按索引升序；每手第 0 次发牌先给出一条
与之同索引的被拒绝读取，随后一条同索引的接受读取。手号零填充，以便非定位字段按字符串
比较时仍与数值顺序一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.verification import (
    BASELINE_IDENTIFIER,
    DIGEST_ALGORITHMS,
    EXECUTION_IDENTITY_CATEGORIES,
    INSTANTIATION_CALIBER_CATEGORY,
    READ_RECORD_ENCODINGS,
    AuditedMaterials,
    ConstructionCaliber,
    ConstructionInterface,
    ConstructionMapping,
    DealMappingSpec,
    DomainRunSpec,
    ExecutionIdentityRecord,
    FixedDomain,
    FrozenRunManifest,
    HandMaterials,
    HandPlan,
    MaterialEntry,
    MaterialManifest,
    PurposeRole,
    PurposeSpec,
    RandomizationProtocolSpec,
    ReadRecord,
    SeatScope,
    ShrinkingDomain,
    TranscriptCommitment,
    build_execution_identity_record,
    build_frozen_manifest,
    bytes_digest,
    instantiation_caliber_entries,
    manifest_digest,
    read_record_digest,
)

# 测试自建的牌规范序：先点数后花色，共一副牌。
DECK_ORDER: tuple[str, ...] = tuple(
    f"{rank}{suit}" for rank in "23456789TJQKA" for suit in "cdhs"
)

# 测试自建的用途标签、索引字段与定位字段。
DEAL_LABEL = "deal"
NON_PROBED_LABEL = "non-probed-seed"
UNDER_TEST_LABEL = "under-test-material"
BASELINE_LABEL = "baseline-seed"
DRAW_FIELD = "draw"
SEAT_FIELD = "seat"

TRAVERSAL_ORDER: tuple[str, ...] = (
    DEAL_LABEL,
    NON_PROBED_LABEL,
    UNDER_TEST_LABEL,
    BASELINE_LABEL,
)

# 候选侧标识在构造计划阶段不需要真的存在；基线标识固定为单一基线身份。
UNDER_TEST_IDENTIFIER = "mixed-local@8"

# 测试自建的索引前缀、材料基数与被拒绝的原始值。
CONFIGURATION = "cfg"
BLOCK = "b1"
INDEX_PREFIX: tuple[str, ...] = (CONFIGURATION, BLOCK)
NON_PROBED_BASE = 1000
UNDER_TEST_BASE = 1 << 250
BASELINE_BASE = 5000
REJECTED_RAW = 255

_ReadPlan = tuple[tuple[str, tuple[str, ...], int, int | None], ...]
_Values = dict[tuple[str, tuple[str, ...]], int]


def hand_field(hand: int) -> str:
    """手号的渲染：零填充，保证按字符串比较时与数值顺序一致。"""
    return f"{hand:02d}"


def purpose_specs(under_test_bits: int = 256) -> tuple[PurposeSpec, ...]:
    """测试自建的用途规格：四种角色各一份，索引字段含定位字段。"""
    return (
        PurposeSpec(
            role=PurposeRole.DEAL,
            label=DEAL_LABEL,
            index_fields=("configuration", "block", "hand", DRAW_FIELD),
            draw_index_field=DRAW_FIELD,
            domain=ShrinkingDomain(initial_size=52),
            bit_width=8,
        ),
        PurposeSpec(
            role=PurposeRole.NON_PROBED_SEED,
            label=NON_PROBED_LABEL,
            index_fields=("configuration", "block", "hand", SEAT_FIELD),
            seat_index_field=SEAT_FIELD,
            domain=FixedDomain(size=1 << 64),
            bit_width=64,
        ),
        PurposeSpec(
            role=PurposeRole.UNDER_TEST_MATERIAL,
            label=UNDER_TEST_LABEL,
            index_fields=("configuration", "block", "hand"),
            domain=FixedDomain(size=1 << under_test_bits),
            bit_width=under_test_bits,
        ),
        PurposeSpec(
            role=PurposeRole.BASELINE_SEED,
            label=BASELINE_LABEL,
            index_fields=("configuration", "block", "hand"),
            domain=FixedDomain(size=1 << 64),
            bit_width=64,
        ),
    )


def protocol_spec(
    under_test_bits: int = 256, **overrides: object
) -> RandomizationProtocolSpec:
    """测试自建的协议规格；需要覆盖某一字段时按关键字替换。"""
    fields: dict[str, object] = {
        "source_interface_id": "test-source-interface",
        "environment_record": "测试环境记录",
        "purposes": purpose_specs(under_test_bits),
        "traversal_order": TRAVERSAL_ORDER,
        "commitment_form": "single-digest-seal",
        "audit_format_version": 1,
        "digest_algorithm": DIGEST_ALGORITHMS[0],
        "read_record_encoding": READ_RECORD_ENCODINGS[0],
    }
    fields.update(overrides)
    return RandomizationProtocolSpec.model_validate(fields)


def deal_spec(**overrides: object) -> DealMappingSpec:
    """测试自建的发牌映射规格。"""
    fields: dict[str, object] = {"deck_order": DECK_ORDER}
    fields.update(overrides)
    return DealMappingSpec.model_validate(fields)


def run_spec(
    *,
    num_players: int = 3,
    probed_seat: int = 1,
    hands: int = 1,
    baseline_identifier: str = BASELINE_IDENTIFIER,
    under_test_identifier: str = UNDER_TEST_IDENTIFIER,
    under_test_bits: int = 256,
) -> DomainRunSpec:
    """测试自建的运行前规格：手序计划按手号逐手显式给出。"""
    schedule = tuple(
        HandPlan(hand_ordinal=hand, button=hand % num_players, probed_seat=probed_seat)
        for hand in range(1, hands + 1)
    )
    return DomainRunSpec(
        num_players=num_players,
        starting_stack=200,
        small_blind=1,
        big_blind=2,
        engine_seed=17,
        baseline_identifier=baseline_identifier,
        under_test_identifier=under_test_identifier,
        deal=deal_spec(),
        protocol=protocol_spec(under_test_bits),
        schedule=schedule,
    )


def under_test_mapping(
    seat_scope: SeatScope = SeatScope.PROBED_SEAT_ONLY,
    identifier: str = UNDER_TEST_IDENTIFIER,
) -> ConstructionMapping:
    """候选侧身份的构造映射：经主键接口构造并依赖公开摘要输入。"""
    return ConstructionMapping(
        identifier=identifier,
        interface=ConstructionInterface.MATERIAL_KEY,
        requires_public_summary=True,
        seat_scope=seat_scope,
    )


def baseline_mapping() -> ConstructionMapping:
    """基线侧身份的构造映射：经受控注册表以整数种子构造。"""
    return ConstructionMapping(
        identifier=BASELINE_IDENTIFIER,
        interface=ConstructionInterface.REGISTRY_SEED,
        requires_public_summary=False,
    )


def construction_caliber(
    seat_scope: SeatScope = SeatScope.PROBED_SEAT_ONLY,
    identifier: str = UNDER_TEST_IDENTIFIER,
) -> ConstructionCaliber:
    """测试自建的构造口径：两侧映射都由本函数显式给出，不经过任何登记表。"""
    return ConstructionCaliber(
        baseline=baseline_mapping(),
        under_test=under_test_mapping(seat_scope, identifier=identifier),
    )


def identity_categories() -> dict[str, list[tuple[str, str]]]:
    """覆盖清单的六类占位条目：只用于结构类校验，不代表任何真实构造口径。"""
    return {
        name: [(f"{name}-entry", f"{name}-value")] for name in EXECUTION_IDENTITY_CATEGORIES
    }


def caliber_categories(
    caliber: ConstructionCaliber,
    spec: DomainRunSpec,
    bundle: tuple[HandMaterials, ...],
) -> dict[str, list[tuple[str, str]]]:
    """覆盖清单的六类条目：实例化口径一类取当前构造口径与重算计划的规范条目。"""
    categories = identity_categories()
    categories[INSTANTIATION_CALIBER_CATEGORY] = [
        (name, value)
        for name, value in instantiation_caliber_entries(
            spec=spec,
            caliber=caliber,
            bundle=bundle,
            algorithm=spec.protocol.digest_algorithm,
        )
    ]
    return categories


def forged_caliber_categories(
    caliber: ConstructionCaliber,
    spec: DomainRunSpec,
    bundle: tuple[HandMaterials, ...],
    *,
    name: str,
    value: str,
) -> dict[str, list[tuple[str, str]]]:
    """把实例化口径类别中某一条取值换成别的值，供构造「记录与当前口径不一致」的反例。"""
    categories = caliber_categories(caliber, spec, bundle)
    categories[INSTANTIATION_CALIBER_CATEGORY] = [
        (entry_name, value if entry_name == name else entry_value)
        for entry_name, entry_value in categories[INSTANTIATION_CALIBER_CATEGORY]
    ]
    return categories


def conflicting_baseline_caliber(
    seat_scope: SeatScope = SeatScope.ALL_SEATS,
) -> ConstructionCaliber:
    """拼出与基线约束冲突的构造口径：绕过模型级校验，仅供反例使用。

    该写法只允许出现在测试里，生产实现不得用它绕过任何校验。
    """
    baseline = ConstructionMapping(
        identifier=BASELINE_IDENTIFIER,
        interface=ConstructionInterface.REGISTRY_SEED,
        requires_public_summary=True,
        seat_scope=seat_scope,
    )
    return ConstructionCaliber.model_construct(
        baseline=baseline, under_test=under_test_mapping()
    )


def hand_values(
    num_players: int,
    hand: int,
    probed_seat: int,
    under_test_value: int | None = None,
) -> _Values:
    """一手牌的逐条取值：材料侧、清单侧与审计侧共用同一份定义。"""
    values: _Values = {}
    hand_token = hand_field(hand)
    for draw in range(2 * num_players + 5):
        values[(DEAL_LABEL, (CONFIGURATION, BLOCK, hand_token, str(draw)))] = draw
    for seat in range(num_players):
        if seat == probed_seat:
            continue
        values[(NON_PROBED_LABEL, (CONFIGURATION, BLOCK, hand_token, str(seat)))] = (
            NON_PROBED_BASE + seat
        )
    values[(UNDER_TEST_LABEL, (CONFIGURATION, BLOCK, hand_token))] = (
        UNDER_TEST_BASE + hand if under_test_value is None else under_test_value
    )
    values[(BASELINE_LABEL, (CONFIGURATION, BLOCK, hand_token))] = BASELINE_BASE + hand
    return values


def _hand_scheme(scheme: tuple[tuple[int, int], ...], num_players: int, under_test_value):
    """逐手取值的内部构造：手号、被测座位与该手取值。"""
    return [
        (hand, hand_values(num_players, hand, probed, under_test_value))
        for hand, probed in scheme
    ]


def _ordered_keys(
    protocol: RandomizationProtocolSpec, values: _Values, label: str
) -> tuple[tuple[str, ...], ...]:
    """该用途在本手的索引键，按用途的索引比较键升序。"""
    purpose = protocol.purpose_for_label(label)
    return tuple(
        sorted(
            (key for entry_label, key in values if entry_label == label),
            key=purpose.index_order_key,
        )
    )


def materials_for_hand(values: _Values, hand: int) -> HandMaterials:
    """把一手取值整理成材料结构。"""
    return HandMaterials(
        hand_ordinal=hand,
        entries=tuple(
            MaterialEntry(purpose_label=label, index_key=key, value=value)
            for (label, key), value in values.items()
        ),
    )


def materials_bundle(
    scheme: tuple[tuple[int, int], ...],
    num_players: int,
    under_test_value: int | None = None,
) -> tuple[HandMaterials, ...]:
    """逐手材料束：与清单、审计使用同一份取值定义。"""
    return tuple(
        materials_for_hand(values, hand)
        for hand, values in _hand_scheme(scheme, num_players, under_test_value)
    )


def manifest_for(
    protocol: RandomizationProtocolSpec,
    scheme: tuple[tuple[int, int], ...],
    num_players: int,
    under_test_value: int | None = None,
) -> MaterialManifest:
    """材料清单：用途按遍历顺序、用途内部按索引升序。"""
    entries: list[MaterialEntry] = []
    per_hand = _hand_scheme(scheme, num_players, under_test_value)
    for label in protocol.traversal_order:
        for _hand, values in per_hand:
            for key in _ordered_keys(protocol, values, label):
                entries.append(
                    MaterialEntry(
                        purpose_label=label, index_key=key, value=values[(label, key)]
                    )
                )
    return MaterialManifest(entries=tuple(entries))


def read_plan(
    protocol: RandomizationProtocolSpec,
    scheme: tuple[tuple[int, int], ...],
    num_players: int,
    under_test_value: int | None = None,
) -> _ReadPlan:
    """逐条读取计划：用途优先、用途内索引升序、第 0 次发牌先拒绝后接受。"""
    plan: list[tuple[str, tuple[str, ...], int, int | None]] = []
    per_hand = _hand_scheme(scheme, num_players, under_test_value)
    for label in protocol.traversal_order:
        purpose = protocol.purpose_for_label(label)
        for _hand, values in per_hand:
            for key in _ordered_keys(protocol, values, label):
                if purpose.role is PurposeRole.DEAL and purpose.draw_index_of(key) == 0:
                    plan.append((label, key, REJECTED_RAW, None))
                plan.append((label, key, values[(label, key)], None))
    return tuple(plan)


def audit_from_plan(
    protocol: RandomizationProtocolSpec,
    plan: _ReadPlan,
    *,
    manifest_digest_value: str = "generated-manifest-digest",
) -> AuditedMaterials:
    """按读取计划拼出一份自洽的审计凭据。"""
    transcript = bytearray()
    reads: list[ReadRecord] = []
    accepted = dict.fromkeys((purpose.label for purpose in protocol.purposes), 0)
    rejected = dict.fromkeys((purpose.label for purpose in protocol.purposes), 0)
    for index, (label, key, raw, override) in enumerate(plan):
        purpose = protocol.purpose_for_label(label)
        width = purpose.bit_width if override is None else override
        step_index = (
            purpose.draw_index_of(key) if purpose.role is PurposeRole.DEAL else 0
        )
        domain_size = purpose.domain.domain_size(step_index)
        output = resolve(output_raw=raw, width=width, domain_size=domain_size)
        offset = len(transcript)
        transcript.extend(raw.to_bytes(width // 8, "big"))
        reads.append(
            ReadRecord(
                read_index=index,
                purpose_label=label,
                index_key=key,
                bit_width=width,
                raw_offset=offset,
                raw_value=raw,
                accepted=output is not None,
                output=output,
            )
        )
        if output is None:
            rejected[label] += 1
        else:
            accepted[label] += 1
    commitment = TranscriptCommitment(
        source_interface_id=protocol.source_interface_id,
        environment_record=protocol.environment_record,
        generation_started_at="2026-09-29T00:00:00Z",
        generation_finished_at="2026-09-29T00:00:01Z",
        traversal_order=protocol.traversal_order,
        entry_counts=tuple(
            (purpose.label, accepted[purpose.label]) for purpose in protocol.purposes
        ),
        rejection_counts=tuple(
            (purpose.label, rejected[purpose.label]) for purpose in protocol.purposes
        ),
        transcript_digest=bytes_digest(bytes(transcript), algorithm=protocol.digest_algorithm),
        read_record_digest=read_record_digest(
            reads, encoding=protocol.read_record_encoding, algorithm=protocol.digest_algorithm
        ),
        manifest_digest=manifest_digest_value,
        generator_code_digest="generator-code-digest",
        digest_algorithm=protocol.digest_algorithm,
        read_record_encoding=protocol.read_record_encoding,
        audit_format_version=protocol.audit_format_version,
    )
    return AuditedMaterials(
        transcript=bytes(transcript), reads=tuple(reads), commitment=commitment
    )


@dataclass(frozen=True)
class Fixture:
    """一份自洽的测试输入：规格、构造口径、材料、审计凭据、执行身份与冻结清单。"""

    spec: DomainRunSpec
    caliber: ConstructionCaliber
    bundle: tuple[HandMaterials, ...]
    audit: AuditedMaterials
    identity: ExecutionIdentityRecord
    material_manifest: MaterialManifest
    manifest: FrozenRunManifest


def build_fixture(
    num_players: int = 3,
    hands: int = 1,
    probed_seat: int = 1,
    under_test_bits: int = 256,
    under_test_value: int | None = None,
    under_test_scope: SeatScope = SeatScope.PROBED_SEAT_ONLY,
) -> Fixture:
    """拼出一份自洽的测试输入，供绑定与核验用例使用。"""
    caliber = construction_caliber(under_test_scope)
    spec = run_spec(
        num_players=num_players,
        probed_seat=probed_seat,
        hands=hands,
        under_test_bits=under_test_bits,
    )
    scheme = tuple((plan.hand_ordinal, plan.probed_seat) for plan in spec.schedule)
    material_manifest = manifest_for(
        spec.protocol, scheme, num_players, under_test_value
    )
    algorithm = spec.protocol.digest_algorithm
    audit = audit_from_plan(
        spec.protocol,
        read_plan(spec.protocol, scheme, num_players, under_test_value),
        manifest_digest_value=manifest_digest(material_manifest, algorithm=algorithm),
    )
    bundle = materials_bundle(scheme, num_players, under_test_value)
    identity = build_execution_identity_record(caliber_categories(caliber, spec, bundle))
    return Fixture(
        spec=spec,
        caliber=caliber,
        bundle=bundle,
        audit=audit,
        identity=identity,
        material_manifest=material_manifest,
        manifest=build_frozen_manifest(
            spec=spec,
            caliber=caliber,
            bundle=bundle,
            audit=audit,
            execution_identity=identity,
            material_manifest=material_manifest,
        ),
    )


def resolve(*, output_raw: int, width: int, domain_size: int) -> int | None:
    """测试侧的拒绝判定：与实现相互独立地写一遍同一规则。"""
    bound = domain_size * ((1 << width) // domain_size)
    if output_raw < bound:
        return output_raw % domain_size
    return None


def recommit_audit(
    audit: AuditedMaterials,
    *,
    reads: tuple[ReadRecord, ...] | None = None,
    transcript: bytes | None = None,
    entry_counts: tuple[tuple[str, int], ...] | None = None,
    rejection_counts: tuple[tuple[str, int], ...] | None = None,
    environment_record: str | None = None,
    manifest_digest_value: str | None = None,
) -> AuditedMaterials:
    """按给定内容重算摘要，使其余校验项可以单独被触发。"""
    current_reads = audit.reads if reads is None else reads
    current_transcript = audit.transcript if transcript is None else transcript
    updates: dict[str, Any] = {
        "transcript_digest": bytes_digest(
            current_transcript, algorithm=audit.commitment.digest_algorithm
        ),
        "read_record_digest": read_record_digest(
            current_reads,
            encoding=audit.commitment.read_record_encoding,
            algorithm=audit.commitment.digest_algorithm,
        ),
        "entry_counts": audit.commitment.entry_counts
        if entry_counts is None
        else entry_counts,
        "rejection_counts": audit.commitment.rejection_counts
        if rejection_counts is None
        else rejection_counts,
    }
    if environment_record is not None:
        updates["environment_record"] = environment_record
    if manifest_digest_value is not None:
        updates["manifest_digest"] = manifest_digest_value
    return AuditedMaterials(
        transcript=current_transcript,
        reads=current_reads,
        commitment=audit.commitment.model_copy(update=updates),
    )


def replace_reads(
    audit: AuditedMaterials, index: int, **updates: object
) -> tuple[ReadRecord, ...]:
    """替换第若干条读取记录，供构造各类不自洽情形。"""
    reads = list(audit.reads)
    reads[index] = reads[index].model_copy(update=updates)
    return tuple(reads)


def replace_team_reads(
    audit: AuditedMaterials, start: int, count: int, **updates: object
) -> tuple[ReadRecord, ...]:
    """替换连续若干条读取记录，供构造索引顺序类情形。"""
    reads = list(audit.reads)
    for offset in range(count):
        position = start + offset
        reads[position] = reads[position].model_copy(update=updates)
    return tuple(reads)


def entries_of(bundle: tuple[HandMaterials, ...], hand_index: int) -> list[MaterialEntry]:
    """取某一手的材料列表副本，便于逐条替换。"""
    return list(bundle[hand_index].entries)


def replace_entries(
    bundle: tuple[HandMaterials, ...], hand_index: int, entries: list[MaterialEntry]
) -> tuple[HandMaterials, ...]:
    """替换某一手的材料，供构造材料与审计不匹配的情形。"""
    hands = list(bundle)
    hands[hand_index] = HandMaterials(
        hand_ordinal=hands[hand_index].hand_ordinal, entries=tuple(entries)
    )
    return tuple(hands)


def replace_manifest_entry(
    manifest: MaterialManifest, position: int, value: int
) -> MaterialManifest:
    """替换清单中的一条取值，供构造清单与内容不一致的情形。"""
    entries = list(manifest.entries)
    entry = entries[position]
    entries[position] = MaterialEntry(
        purpose_label=entry.purpose_label, index_key=entry.index_key, value=value
    )
    return MaterialManifest(entries=tuple(entries))
