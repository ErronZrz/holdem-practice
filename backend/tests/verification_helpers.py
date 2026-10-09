"""验证运行器测试用的构造辅助：只把规格与已有材料拼起来。

这里的牌规范序、用途标签、索引键与输出域都是测试自建口径，用于覆盖结构校验的分支，
不是任何冻结取值。审计示例与材料清单由本文件在内存中拼出：既不是域 C 材料生成，
也不是任何冻结工件。

读取排布遵循结构规则：用途按遍历顺序、用途内部按索引升序；每手第 0 次发牌先给出一条
与之同索引的被拒绝读取，随后一条同索引的接受读取。整数字段按无前导零十进制渲染。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.verification import (
    BASELINE_IDENTIFIER,
    DIGEST_ALGORITHMS,
    INSTANTIATION_CALIBER_CATEGORY,
    READ_RECORD_ENCODINGS,
    UNDER_TEST_IDENTIFIER,
    AuditedMaterials,
    CampaignConfiguration,
    CampaignLockVersions,
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
    build_domain_run_spec,
    build_execution_identity_record,
    build_frozen_manifest,
    bytes_digest,
    campaign_configuration_digest,
    commitment_digest,
    deal_mapping_digest,
    injection_precheck_category_entries,
    instantiation_caliber_entries,
    manifest_digest,
    materials_digest,
    protocol_digest,
    public_summary_mapping_digest,
    purpose_index_mapping_digest,
    read_record_digest,
    require_source_manifest,
    runner_category_entries,
    schedule_digest,
    source_manifest_digest,
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

# 测试自建的索引前缀、材料基数与被拒绝的原始值。
# campaign 由夹具组成字段现算，只存在于本次进程，不作为实际配置摘要保存。
BLOCK = "0"


def fixture_lock_versions() -> CampaignLockVersions:
    """夹具用的五个版本号。它们不是五个对象锁定之后的实际版本。"""
    return CampaignLockVersions(
        pairing_and_reset=1,
        per_hand_bound=1,
        fragment_template=1,
        weight_class=1,
        seat_rotation=1,
    )


def fixture_campaign(*, num_players: int = 3) -> str:
    """夹具配置摘要。只供本进程内的索引键使用。"""
    return campaign_configuration_digest(
        num_players=num_players,
        starting_stack=200,
        small_blind=1,
        big_blind=2,
        baseline_identifier=BASELINE_IDENTIFIER,
        under_test_identifier=UNDER_TEST_IDENTIFIER,
        lock_versions=fixture_lock_versions(),
    )


CONFIGURATION = fixture_campaign()
INDEX_PREFIX: tuple[str, ...] = (CONFIGURATION, BLOCK)
NON_PROBED_BASE = 1000
UNDER_TEST_BASE = 1 << 250
BASELINE_BASE = 5000
REJECTED_RAW = 255

_ReadPlan = tuple[tuple[str, tuple[str, ...], int, int | None], ...]
_Values = dict[tuple[str, tuple[str, ...]], int]


def hand_field(hand: int) -> str:
    """手号的十进制渲染：不补零。"""
    return str(hand)


def purpose_specs(under_test_bits: int = 256) -> tuple[PurposeSpec, ...]:
    """测试自建的用途规格：四种角色各一份，索引字段含定位字段。"""
    return (
        PurposeSpec(
            role=PurposeRole.DEAL,
            label=DEAL_LABEL,
            index_fields=("campaign", "block", "hand", DRAW_FIELD),
            integer_fields=("block", "hand", DRAW_FIELD),
            draw_index_field=DRAW_FIELD,
            domain=ShrinkingDomain(initial_size=52),
            bit_width=8,
        ),
        PurposeSpec(
            role=PurposeRole.NON_PROBED_SEED,
            label=NON_PROBED_LABEL,
            index_fields=("campaign", "block", "hand", SEAT_FIELD),
            integer_fields=("block", "hand", SEAT_FIELD),
            seat_index_field=SEAT_FIELD,
            domain=FixedDomain(size=1 << 64),
            bit_width=64,
        ),
        PurposeSpec(
            role=PurposeRole.UNDER_TEST_MATERIAL,
            label=UNDER_TEST_LABEL,
            index_fields=("campaign", "block", "hand"),
            integer_fields=("block", "hand"),
            domain=FixedDomain(size=1 << under_test_bits),
            bit_width=under_test_bits,
        ),
        PurposeSpec(
            role=PurposeRole.BASELINE_SEED,
            label=BASELINE_LABEL,
            index_fields=("campaign", "block", "hand"),
            integer_fields=("block", "hand"),
            domain=FixedDomain(size=1 << 64),
            bit_width=64,
        ),
    )


def protocol_spec(
    under_test_bits: int = 256, **overrides: object
) -> RandomizationProtocolSpec:
    """测试自建的协议规格；需要覆盖某一字段时按关键字替换。"""
    fields: dict[str, object] = {
        "source_interface_id": "python-os-urandom@1",
        "environment_record": "local-single-process-no-parallel@1",
        "rejection_rule": "rejection-whole-multiple-truncation-v1",
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
    return build_domain_run_spec(
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
        block=0,
        campaign_configuration=CampaignConfiguration(lock_versions=fixture_lock_versions()),
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


def _manifest_row(path: str, digest: str) -> dict[str, str]:
    return {"path": path, "sha256": digest}


@dataclass(frozen=True)
class SourceManifestSet:
    """六份手造源码清单。文件摘要是占位十六进制，不是仓库源码的真实摘要。"""

    runner: dict[str, object]
    generator: dict[str, object]
    engine: dict[str, object]
    baseline_strategy: dict[str, object]
    under_test_strategy: dict[str, object]
    verification: dict[str, object]


def fixture_source_manifests() -> SourceManifestSet:
    """主链夹具使用的非实际清单。不读取这些路径上的文件。"""
    return SourceManifestSet(
        runner=hand_source_manifest("backend/app/verification/runner.py"),
        generator=hand_source_manifest("backend/tools/material_generator.py"),
        engine=hand_source_manifest("backend/fixtures/engine.py"),
        baseline_strategy=hand_source_manifest("backend/fixtures/baseline.py"),
        under_test_strategy=hand_source_manifest("backend/fixtures/under_test.py"),
        verification=hand_source_manifest("backend/fixtures/verification.py"),
    )


def hand_source_manifest(entrypoint: str) -> dict[str, object]:
    """手造源码清单。摘要是占位十六进制，不对应仓库里的真实文件。"""
    digest = "11" * 32
    require_source_manifest(
        {
            "schema": "source-manifest-v1",
            "entrypoints": [entrypoint],
            "python_version": "3.12.0",
            "files": [_manifest_row(entrypoint, digest)],
            "dependency_files": [
                _manifest_row("backend/pyproject.toml", "22" * 32),
                _manifest_row("backend/uv.lock", "33" * 32),
            ],
        }
    )
    return {
        "schema": "source-manifest-v1",
        "entrypoints": [entrypoint],
        "python_version": "3.12.0",
        "files": [_manifest_row(entrypoint, digest)],
        "dependency_files": [
            _manifest_row("backend/pyproject.toml", "22" * 32),
            _manifest_row("backend/uv.lock", "33" * 32),
        ],
    }


def identity_categories() -> dict[str, list[tuple[str, str]]]:
    """六类封闭条目。实例化口径里的两份摘要是占位值，因此不能当作当前口径。"""
    algorithm = DIGEST_ALGORITHMS[0]
    placeholder = "ab" * 32
    return {
        "runner": list(
            runner_category_entries(
                hand_source_manifest("backend/app/verification/runner.py"),
                algorithm=algorithm,
            )
        ),
        "randomization-protocol": [
            ("randomization-protocol-version", "1"),
            ("randomization-protocol-digest", placeholder),
            ("source-interface-id", "python-os-urandom@1"),
            ("environment-record", "local-single-process-no-parallel@1"),
            ("supplied-materials-digest", placeholder),
            ("material-manifest-digest", placeholder),
            ("audit-transcript-digest", placeholder),
            ("audit-read-record-digest", placeholder),
            ("audit-commitment-digest", placeholder),
            ("generator-code-digest", placeholder),
        ],
        INSTANTIATION_CALIBER_CATEGORY: [
            ("baseline-identifier", BASELINE_IDENTIFIER),
            ("under-test-identifier", UNDER_TEST_IDENTIFIER),
            ("baseline-interface", "registry-seed"),
            ("under-test-interface", "material-key"),
            ("baseline-requires-public-summary", "false"),
            ("under-test-requires-public-summary", "true"),
            ("baseline-seat-scope", "none"),
            ("under-test-seat-scope", "probed-seat-only"),
            ("baseline-registry-location", "app.strategy.registry.create_strategy"),
            ("baseline-entry-point", "app.strategy.heuristic.HeuristicStrategy.__init__"),
            ("baseline-parameter-layout", '["self","seed","samples","bluff_freq"]'),
            ("baseline-effective-seed", "per-hand-arm_b-material"),
            ("baseline-effective-samples", "500"),
            ("baseline-effective-bluff-freq", "0.1"),
            ("baseline-entry-code-digest", "cd" * 32),
            ("construction-plan-digest", "ef" * 32),
        ],
        "injection-precheck": list(injection_precheck_category_entries(algorithm)),
        "input-mapping": [
            ("input-mapping-version", "1"),
            ("campaign-configuration-digest", CONFIGURATION),
            ("deal-mapping-digest", deal_mapping_digest(algorithm=algorithm)),
            ("purpose-index-mapping-digest", purpose_index_mapping_digest(algorithm=algorithm)),
            ("schedule-digest", placeholder),
            (
                "public-summary-mapping-digest",
                public_summary_mapping_digest(algorithm=algorithm),
            ),
        ],
        "engine-and-strategy-code": [
            ("engine-code-manifest-digest", placeholder),
            ("baseline-strategy-code-manifest-digest", placeholder),
            ("under-test-strategy-code-manifest-digest", placeholder),
            ("verification-code-manifest-digest", placeholder),
        ],
    }


def caliber_categories(
    caliber: ConstructionCaliber,
    spec: DomainRunSpec,
    bundle: tuple[HandMaterials, ...],
    audit: AuditedMaterials,
    material_manifest: MaterialManifest,
    manifests: SourceManifestSet,
) -> dict[str, list[tuple[str, str]]]:
    """六类条目都按当前规格、材料、审计和手造清单重算，不保留占位摘要。"""
    algorithm = spec.protocol.digest_algorithm
    generator_digest = source_manifest_digest(manifests.generator, algorithm=algorithm)
    campaign = campaign_configuration_digest(
        num_players=spec.num_players,
        starting_stack=spec.starting_stack,
        small_blind=spec.small_blind,
        big_blind=spec.big_blind,
        baseline_identifier=spec.baseline_identifier,
        under_test_identifier=spec.under_test_identifier,
        lock_versions=spec.campaign_configuration.lock_versions,
    )
    return {
        "runner": list(runner_category_entries(manifests.runner, algorithm=algorithm)),
        "randomization-protocol": [
            ("randomization-protocol-version", "1"),
            ("randomization-protocol-digest", protocol_digest(spec.protocol)),
            ("source-interface-id", spec.protocol.source_interface_id),
            ("environment-record", spec.protocol.environment_record),
            ("supplied-materials-digest", materials_digest(bundle, spec=spec, algorithm=algorithm)),
            (
                "material-manifest-digest",
                manifest_digest(material_manifest, algorithm=algorithm),
            ),
            (
                "audit-transcript-digest",
                bytes_digest(audit.transcript, algorithm=algorithm),
            ),
            (
                "audit-read-record-digest",
                read_record_digest(
                    audit.reads,
                    encoding=spec.protocol.read_record_encoding,
                    algorithm=algorithm,
                ),
            ),
            ("audit-commitment-digest", commitment_digest(audit.commitment)),
            ("generator-code-digest", generator_digest),
        ],
        INSTANTIATION_CALIBER_CATEGORY: [
            (name, value)
            for name, value in instantiation_caliber_entries(
                spec=spec, caliber=caliber, bundle=bundle, algorithm=algorithm
            )
        ],
        "injection-precheck": list(injection_precheck_category_entries(algorithm)),
        "input-mapping": [
            ("input-mapping-version", "1"),
            ("campaign-configuration-digest", campaign),
            ("deal-mapping-digest", deal_mapping_digest(algorithm=algorithm)),
            (
                "purpose-index-mapping-digest",
                purpose_index_mapping_digest(algorithm=algorithm),
            ),
            ("schedule-digest", schedule_digest(spec)),
            (
                "public-summary-mapping-digest",
                public_summary_mapping_digest(algorithm=algorithm),
            ),
        ],
        "engine-and-strategy-code": [
            (
                "engine-code-manifest-digest",
                source_manifest_digest(manifests.engine, algorithm=algorithm),
            ),
            (
                "baseline-strategy-code-manifest-digest",
                source_manifest_digest(manifests.baseline_strategy, algorithm=algorithm),
            ),
            (
                "under-test-strategy-code-manifest-digest",
                source_manifest_digest(manifests.under_test_strategy, algorithm=algorithm),
            ),
            (
                "verification-code-manifest-digest",
                source_manifest_digest(manifests.verification, algorithm=algorithm),
            ),
        ],
    }


def forged_caliber_categories(
    caliber: ConstructionCaliber,
    spec: DomainRunSpec,
    bundle: tuple[HandMaterials, ...],
    audit: AuditedMaterials,
    material_manifest: MaterialManifest,
    manifests: SourceManifestSet,
    *,
    name: str,
    value: str,
) -> dict[str, list[tuple[str, str]]]:
    """把实例化口径类别中某一条取值换成别的值，供构造「记录与当前口径不一致」的反例。"""
    categories = caliber_categories(
        caliber, spec, bundle, audit, material_manifest, manifests
    )
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
    generator_code_digest: str = "ab" * 32,
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
        generation_started_at="2026-09-29T00:00:00.000000Z",
        generation_finished_at="2026-09-29T00:00:01.000000Z",
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
        generator_code_digest=generator_code_digest,
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
    source_manifests: SourceManifestSet
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
    manifests = fixture_source_manifests()
    audit = audit_from_plan(
        spec.protocol,
        read_plan(spec.protocol, scheme, num_players, under_test_value),
        manifest_digest_value=manifest_digest(material_manifest, algorithm=algorithm),
        generator_code_digest=source_manifest_digest(
            manifests.generator, algorithm=algorithm
        ),
    )
    bundle = materials_bundle(scheme, num_players, under_test_value)
    identity = build_execution_identity_record(
        caliber_categories(
            caliber, spec, bundle, audit, material_manifest, manifests
        )
    )
    return Fixture(
        spec=spec,
        caliber=caliber,
        bundle=bundle,
        audit=audit,
        identity=identity,
        material_manifest=material_manifest,
        source_manifests=manifests,
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
