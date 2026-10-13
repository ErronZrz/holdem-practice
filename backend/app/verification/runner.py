"""冻结清单与输入绑定：把运行前输入与已冻结内容机械比对，并声明运行流程。

设计目的：
- 摘要一律由内容重算，不由调用方转录：内容不同即失败，抄录一个摘要字符串不构成凭据；
- 材料必须与已审计并承诺的取值逐项配对，材料来源因此可被机械复核；
- 两侧身份的构造口径作为显式输入被直接消费：其内容摘要进入冻结清单，逐手逐臂逐座位的
  构造计划、基线身份的有效执行口径与执行身份里的实例化口径也必须与本输入逐项一致；
- 本模块**不含任何可推进牌局的代码**：不创建引擎、不注入发牌、不循环提交行动；
  执行路径属后续独立授权，本包当前不提供任何进入方式，因此也不存在可被伪造
  子类解锁的入口。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import (
    CampaignLockVersions,
    DomainRunSpec,
    campaign_configuration_digest,
    randomization_protocol_version,
    schedule_digest,
    spec_digest,
)
from .deal import deal_mapping_digest
from .digests import DIGEST_ALGORITHMS, bytes_digest, content_digest
from .errors import FreezeBindingError, IdentityMappingError, VerificationError
from .execution_identity import (
    ExecutionIdentityRecord,
    execution_identity_digest,
    reference_snapshot,
)
from .guards import injection_precheck_category_entries
from .identity import ConstructionCaliber
from .instantiation import (
    construction_caliber_digest,
    materials_digest,
    public_summary_mapping_digest,
    require_construction_calibers,
    require_instantiation_caliber,
    require_materials,
)
from .materials import (
    HandMaterials,
    MaterialManifest,
    manifest_digest,
    require_supplied_materials_order,
)
from .protocol import (
    LOCKED_ENVIRONMENT_RECORD,
    LOCKED_SOURCE_INTERFACE,
    PROTOCOL_SCHEMA_V2,
    AuditedMaterials,
    ReadRecord,
    closed_keyset_binding_digest,
    commitment_digest,
    protocol_digest,
    purpose_index_mapping_digest,
    purpose_index_mapping_v2_digest,
    read_record_digest,
    require_v2_schedule_anchors,
    verify_audit,
    verify_manifest_binding,
    verify_material_binding,
    verify_v2_closed_binding,
)
from .source_manifest import require_source_manifest, source_manifest_digest

# 材料生成器清单的唯一入口。摘要必须由显式传入的清单重算，不能只核对十六进制形状。
_GENERATOR_ENTRYPOINT: tuple[str, ...] = ("backend/tools/material_generator.py",)

NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]

# 运行流程的声明式步骤：只描述顺序与内容，不含任何可执行的推进代码。
RUN_FLOW_STEPS: tuple[str, ...] = (
    "engine-per-hand-per-arm",
    "inject-deal-after-precheck",
    "instances-per-hand-per-arm-per-seat",
    "public-summary-per-hand-per-arm",
    "advance-until-hand-over",
    "read-probed-seat-net",
    "record-pair-and-locators",
)

# 冻结清单必须覆盖的摘要项：缺任一项即失败。
FROZEN_MANIFEST_ITEMS: tuple[str, ...] = (
    "spec-digest",
    "schedule-digest",
    "protocol-digest",
    "supplied-materials-digest",
    "material-manifest-digest",
    "audit-transcript-digest",
    "audit-read-record-digest",
    "audit-commitment-digest",
    "construction-caliber-digest",
    "execution-identity-digest",
)


def flow_step_entries() -> tuple[tuple[str, str], ...]:
    """把流程步骤整理成记录条目，顺序与声明顺序一致。

    覆盖清单不再使用这些旧名称。
    """
    return tuple(
        (f"step-{index + 1}", name) for index, name in enumerate(RUN_FLOW_STEPS)
    )


def runner_flow_digest(algorithm: str) -> str:
    """对流程名称数组取摘要，不加包装对象。"""
    return content_digest(list(RUN_FLOW_STEPS), algorithm=algorithm)


def runner_category_entries(
    runner_manifest: Mapping[str, object],
    *,
    algorithm: str,
) -> tuple[tuple[str, str], ...]:
    """运行器类别的封闭条目。清单必须事先造好，本函数不读盘。"""
    manifest = require_source_manifest(runner_manifest)
    if tuple(manifest["entrypoints"]) != ("backend/app/verification/runner.py",):
        raise VerificationError("运行器清单的入口必须是运行器模块")
    return (
        ("runner-flow-version", "1"),
        ("runner-flow-digest", runner_flow_digest(algorithm)),
        (
            "runner-code-manifest-digest",
            source_manifest_digest(manifest, algorithm=algorithm),
        ),
    )


class FrozenRunManifest(BaseModel):
    """冻结清单：只记录由内容重算得到的摘要，内容本身不进入本包。

    清单不是凭据来源：校验方会用本次实际输入重算每一项摘要并与清单比对，
    因此清单与实际输入不符时必然失败，而相符时也只说明「本次输入就是清单所指的内容」。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    digest_algorithm: str
    spec_digest: str
    schedule_digest: str
    protocol_digest: str
    supplied_materials_digest: str
    material_manifest_digest: str
    audit_transcript_digest: str
    audit_read_record_digest: str
    audit_commitment_digest: str
    construction_caliber_digest: str
    execution_identity_digest: str

    @model_validator(mode="after")
    def _require_well_formed(self) -> FrozenRunManifest:
        if self.digest_algorithm not in DIGEST_ALGORITHMS:
            raise FreezeBindingError(f"摘要算法未实现：{self.digest_algorithm!r}")
        declared = (
            ("spec_digest", self.spec_digest),
            ("schedule_digest", self.schedule_digest),
            ("protocol_digest", self.protocol_digest),
            ("supplied_materials_digest", self.supplied_materials_digest),
            ("material_manifest_digest", self.material_manifest_digest),
            ("audit_transcript_digest", self.audit_transcript_digest),
            ("audit_read_record_digest", self.audit_read_record_digest),
            ("audit_commitment_digest", self.audit_commitment_digest),
            ("construction_caliber_digest", self.construction_caliber_digest),
            ("execution_identity_digest", self.execution_identity_digest),
        )
        for name, value in declared:
            if not value.strip():
                raise FreezeBindingError(f"冻结清单的摘要项不能为空：{name}")
        return self


def build_frozen_manifest(
    *,
    spec: DomainRunSpec,
    caliber: ConstructionCaliber,
    bundle: Sequence[HandMaterials],
    audit: AuditedMaterials,
    execution_identity: ExecutionIdentityRecord,
    material_manifest: MaterialManifest,
    closed_entries: Sequence[tuple[str, tuple[str, ...]]] | None = None,
) -> FrozenRunManifest:
    """由本次输入重算全部摘要，得到一份冻结清单。

    十项摘要全部取自内容：包括材料清单内容本身的摘要与显式构造口径（含构造计划）的摘要，
    而不是清单或记录里的字符串。本函数只做重算，不做任何冻结动作：它不生成材料、
    不写入清单文件，也不记录时间。
    """
    algorithm = spec.protocol.digest_algorithm
    return FrozenRunManifest(
        digest_algorithm=algorithm,
        spec_digest=spec_digest(spec),
        schedule_digest=schedule_digest(spec),
        protocol_digest=protocol_digest(spec.protocol),
        supplied_materials_digest=materials_digest(
            bundle, spec=spec, algorithm=algorithm, closed_entries=closed_entries
        ),
        material_manifest_digest=manifest_digest(material_manifest, algorithm=algorithm),
        audit_transcript_digest=bytes_digest(audit.transcript, algorithm=algorithm),
        audit_read_record_digest=read_record_digest(
            audit.reads,
            encoding=spec.protocol.read_record_encoding,
            algorithm=algorithm,
        ),
        audit_commitment_digest=commitment_digest(audit.commitment),
        construction_caliber_digest=construction_caliber_digest(
            spec=spec,
            caliber=caliber,
            bundle=bundle,
            algorithm=algorithm,
            closed_entries=closed_entries,
        ),
        execution_identity_digest=execution_identity_digest(
            execution_identity, algorithm=algorithm
        ),
    )


def _compare(item: str, recorded: str, recomputed: str) -> None:
    """比对一项摘要；不一致即失败并指出项名。"""
    if recorded != recomputed:
        raise FreezeBindingError(f"冻结清单与本次输入不一致：{item}")


def _recorded_entries(
    record: ExecutionIdentityRecord, category: str
) -> dict[str, str]:
    return {entry.name: entry.value for entry in record.entries_for(category)}


def _require_identity_value(name: str, recorded: str, expected: str) -> None:
    """执行身份里的取值必须等于由当前输入重算的结果。"""
    if recorded != expected:
        raise IdentityMappingError(f"执行身份与当前输入不一致：{name}")


def _bound_value(entries: Mapping[str, str], name: str) -> str:
    """取出已经写入身份的条目。缺项按身份失败，避免变成键查找错误。"""
    if name not in entries:
        raise IdentityMappingError(f"执行身份缺少与当前输入绑定的条目：{name}")
    return entries[name]


def _require_category_values(
    recorded: Mapping[str, str], expected: Sequence[tuple[str, str]]
) -> None:
    for name, value in expected:
        _require_identity_value(name, recorded[name], value)


def _manifest_digest(
    manifest: Mapping[str, object],
    *,
    algorithm: str,
    entrypoints: tuple[str, ...] | None = None,
) -> str:
    """对显式传入的清单重算摘要。入口被限定时，不符即失败。"""
    normalized = require_source_manifest(manifest)
    if entrypoints is not None and tuple(normalized["entrypoints"]) != entrypoints:
        raise IdentityMappingError("源码清单的入口与该条目不符")
    return source_manifest_digest(normalized, algorithm=algorithm)


def _require_bound_execution_identity(
    *,
    spec: DomainRunSpec,
    bundle: Sequence[HandMaterials],
    audit: AuditedMaterials,
    execution_identity: ExecutionIdentityRecord,
    material_manifest: MaterialManifest,
    runner_manifest: Mapping[str, object],
    generator_manifest: Mapping[str, object],
    engine_manifest: Mapping[str, object],
    baseline_strategy_manifest: Mapping[str, object],
    under_test_strategy_manifest: Mapping[str, object],
    verification_manifest: Mapping[str, object],
    closed_entries: Sequence[tuple[str, tuple[str, ...]]] | None,
) -> None:
    """把其余类别中依赖本次输入的条目逐项重算并核对。

    占位十六进制不能代替当前规格、材料、审计或显式传入的源码清单。
    """
    algorithm = spec.protocol.digest_algorithm
    _require_category_values(
        _recorded_entries(execution_identity, "runner"),
        runner_category_entries(runner_manifest, algorithm=algorithm),
    )
    _require_category_values(
        _recorded_entries(execution_identity, "injection-precheck"),
        injection_precheck_category_entries(algorithm),
    )
    generator_digest = _manifest_digest(
        generator_manifest, algorithm=algorithm, entrypoints=_GENERATOR_ENTRYPOINT
    )
    protocol_entries = _recorded_entries(execution_identity, "randomization-protocol")
    _require_identity_value(
        "randomization-protocol-digest",
        protocol_entries["randomization-protocol-digest"],
        protocol_digest(spec.protocol),
    )
    schema = spec.protocol.protocol_schema
    expected_version = "2" if schema == PROTOCOL_SCHEMA_V2 else "1"
    _require_identity_value(
        "randomization-protocol-version",
        protocol_entries["randomization-protocol-version"],
        expected_version,
    )
    _require_identity_value(
        "randomization-protocol-schema",
        _bound_value(protocol_entries, "randomization-protocol-schema"),
        schema,
    )
    _require_identity_value(
        "kappa-key-rules-digest",
        _bound_value(protocol_entries, "kappa-key-rules-digest"),
        purpose_index_mapping_v2_digest(algorithm=algorithm),
    )
    bound_entries = closed_entries if schema == PROTOCOL_SCHEMA_V2 else None
    _require_identity_value(
        "closed-keyset-digest",
        _bound_value(protocol_entries, "closed-keyset-digest"),
        closed_keyset_binding_digest(bound_entries, algorithm=algorithm),
    )
    if schema == PROTOCOL_SCHEMA_V2:
        if spec.protocol.source_interface_id != LOCKED_SOURCE_INTERFACE:
            raise FreezeBindingError("v2 协议的来源与锁定值不符")
        if spec.protocol.environment_record != LOCKED_ENVIRONMENT_RECORD:
            raise FreezeBindingError("v2 协议的环境与锁定值不符")
    _require_identity_value(
        "source-interface-id",
        protocol_entries["source-interface-id"],
        spec.protocol.source_interface_id,
    )
    _require_identity_value(
        "environment-record",
        protocol_entries["environment-record"],
        spec.protocol.environment_record,
    )
    _require_identity_value(
        "supplied-materials-digest",
        protocol_entries["supplied-materials-digest"],
        materials_digest(
            bundle, spec=spec, algorithm=algorithm, closed_entries=closed_entries
        ),
    )
    _require_identity_value(
        "material-manifest-digest",
        protocol_entries["material-manifest-digest"],
        manifest_digest(material_manifest, algorithm=algorithm),
    )
    _require_identity_value(
        "audit-transcript-digest",
        protocol_entries["audit-transcript-digest"],
        bytes_digest(audit.transcript, algorithm=algorithm),
    )
    _require_identity_value(
        "audit-read-record-digest",
        protocol_entries["audit-read-record-digest"],
        read_record_digest(
            audit.reads,
            encoding=spec.protocol.read_record_encoding,
            algorithm=algorithm,
        ),
    )
    _require_identity_value(
        "audit-commitment-digest",
        protocol_entries["audit-commitment-digest"],
        commitment_digest(audit.commitment),
    )
    _require_identity_value(
        "generator-code-digest",
        protocol_entries["generator-code-digest"],
        generator_digest,
    )
    if audit.commitment.generator_code_digest != generator_digest:
        raise IdentityMappingError("生成器代码摘要与承诺不一致")
    campaign = campaign_configuration_digest(
        num_players=spec.num_players,
        starting_stack=spec.starting_stack,
        small_blind=spec.small_blind,
        big_blind=spec.big_blind,
        baseline_identifier=spec.baseline_identifier,
        under_test_identifier=spec.under_test_identifier,
        lock_versions=spec.campaign_configuration.lock_versions,
        randomization_protocol=randomization_protocol_version(spec.protocol),
    )
    if spec.campaign != campaign:
        raise IdentityMappingError("规格上的 campaign 与重算的配置摘要不一致")
    mapping_entries = _recorded_entries(execution_identity, "input-mapping")
    _require_identity_value(
        "campaign-configuration-digest",
        _bound_value(mapping_entries, "campaign-configuration-digest"),
        campaign,
    )
    _require_identity_value(
        "deal-mapping-digest",
        mapping_entries["deal-mapping-digest"],
        deal_mapping_digest(algorithm=algorithm),
    )
    _require_identity_value(
        "purpose-index-mapping-digest",
        mapping_entries["purpose-index-mapping-digest"],
        purpose_index_mapping_digest(algorithm=algorithm),
    )
    _require_identity_value(
        "schedule-digest", mapping_entries["schedule-digest"], schedule_digest(spec)
    )
    _require_identity_value(
        "public-summary-mapping-digest",
        mapping_entries["public-summary-mapping-digest"],
        public_summary_mapping_digest(algorithm=algorithm),
    )
    code_entries = _recorded_entries(execution_identity, "engine-and-strategy-code")
    code_manifests = (
        ("engine-code-manifest-digest", engine_manifest),
        ("baseline-strategy-code-manifest-digest", baseline_strategy_manifest),
        ("under-test-strategy-code-manifest-digest", under_test_strategy_manifest),
        ("verification-code-manifest-digest", verification_manifest),
    )
    for name, source_manifest in code_manifests:
        _require_identity_value(
            name,
            code_entries[name],
            _manifest_digest(source_manifest, algorithm=algorithm),
        )


def verify_frozen_inputs(
    *,
    manifest: FrozenRunManifest,
    spec: DomainRunSpec,
    caliber: ConstructionCaliber,
    bundle: Sequence[HandMaterials],
    audit: AuditedMaterials,
    execution_identity: ExecutionIdentityRecord,
    material_manifest: MaterialManifest,
    runner_manifest: Mapping[str, object],
    generator_manifest: Mapping[str, object],
    engine_manifest: Mapping[str, object],
    baseline_strategy_manifest: Mapping[str, object],
    under_test_strategy_manifest: Mapping[str, object],
    verification_manifest: Mapping[str, object],
    closed_entries: Sequence[tuple[str, tuple[str, ...]]] | None = None,
) -> None:
    """核验本次输入就是冻结清单所指的那一份，并核验材料来源可复核。

    校验顺序：v2 协议先核对闭合集、材料清单与审计的三方相等及手序锚点；
    缺少闭合集即失败，不能绕过。规格上的 campaign 必须等于协议版本 2 的配置摘要。
    其后复核审计材料本身，再确认材料与审计逐项配对，
    再走清单三步链（清单 ↔ 审计 ↔ 送交材料 ↔ 承诺里的清单摘要），再校验材料与规格的结构一致，
    再走身份口径主链（显式构造口径与规格标识的逐字比对、基线一侧接口与公开摘要及座位范围
    三项硬限制、材料格式、逐手逐臂逐座位构造计划、执行身份里的实例化口径一致性），
    再把执行身份里依赖本次输入的条目与规格、材料、审计和显式传入的源码清单逐项重算比对，
    最后用本次输入重算全部十项摘要并与清单比对。任一项不符即失败，不重取材料、不修补。
    """
    protocol = spec.protocol
    if manifest.digest_algorithm != protocol.digest_algorithm:
        raise FreezeBindingError("冻结清单的摘要算法与协议不一致")
    if protocol.protocol_schema == PROTOCOL_SCHEMA_V2:
        if closed_entries is None:
            raise FreezeBindingError("v2 冻结输入缺少闭合集，三方相等未执行")
        probed_by_hand = {plan.hand_ordinal: plan.probed_seat for plan in spec.schedule}
        verify_v2_frozen_records(
            closed_entries,
            material_manifest,
            audit.reads,
            audit.transcript,
            probed_by_hand=probed_by_hand,
            num_players=spec.num_players,
            starting_stack=spec.starting_stack,
            small_blind=spec.small_blind,
            big_blind=spec.big_blind,
            baseline_identifier=spec.baseline_identifier,
            under_test_identifier=spec.under_test_identifier,
            lock_versions=spec.campaign_configuration.lock_versions,
        )
        campaign_v2 = campaign_configuration_digest(
            num_players=spec.num_players,
            starting_stack=spec.starting_stack,
            small_blind=spec.small_blind,
            big_blind=spec.big_blind,
            baseline_identifier=spec.baseline_identifier,
            under_test_identifier=spec.under_test_identifier,
            lock_versions=spec.campaign_configuration.lock_versions,
            randomization_protocol=2,
        )
        if spec.campaign != campaign_v2:
            raise FreezeBindingError("规格上的 campaign 必须是协议版本 2 的配置摘要")
        require_v2_schedule_anchors(
            closed_entries,
            campaign=campaign_v2,
            block=spec.block,
            draw_count=spec.deal.draw_count(spec.num_players),
            num_players=spec.num_players,
            probed_by_hand=probed_by_hand,
        )
    verify_audit(
        protocol=protocol,
        transcript=audit.transcript,
        reads=audit.reads,
        commitment=audit.commitment,
    )
    verify_material_binding(protocol=protocol, bundle=bundle, reads=audit.reads)
    verify_manifest_binding(
        protocol=protocol,
        manifest=material_manifest,
        reads=audit.reads,
        bundle=bundle,
        commitment=audit.commitment,
        spec=spec,
        closed_entries=closed_entries,
    )
    require_materials(spec, bundle, closed_entries=closed_entries)
    require_supplied_materials_order(spec, bundle, closed_entries=closed_entries)
    require_construction_calibers(spec, caliber, bundle, closed_entries=closed_entries)

    algorithm = protocol.digest_algorithm
    require_instantiation_caliber(
        execution_identity,
        spec=spec,
        caliber=caliber,
        bundle=bundle,
        algorithm=algorithm,
        closed_entries=closed_entries,
    )
    _require_bound_execution_identity(
        spec=spec,
        bundle=bundle,
        audit=audit,
        execution_identity=execution_identity,
        material_manifest=material_manifest,
        runner_manifest=runner_manifest,
        generator_manifest=generator_manifest,
        engine_manifest=engine_manifest,
        baseline_strategy_manifest=baseline_strategy_manifest,
        under_test_strategy_manifest=under_test_strategy_manifest,
        verification_manifest=verification_manifest,
        closed_entries=closed_entries,
    )
    _compare("spec-digest", manifest.spec_digest, spec_digest(spec))
    _compare("schedule-digest", manifest.schedule_digest, schedule_digest(spec))
    _compare("protocol-digest", manifest.protocol_digest, protocol_digest(protocol))
    _compare(
        "supplied-materials-digest",
        manifest.supplied_materials_digest,
        materials_digest(
            bundle, spec=spec, algorithm=algorithm, closed_entries=closed_entries
        ),
    )
    _compare(
        "material-manifest-digest",
        manifest.material_manifest_digest,
        manifest_digest(material_manifest, algorithm=algorithm),
    )
    _compare(
        "audit-transcript-digest",
        manifest.audit_transcript_digest,
        bytes_digest(audit.transcript, algorithm=algorithm),
    )
    _compare(
        "audit-read-record-digest",
        manifest.audit_read_record_digest,
        read_record_digest(
            audit.reads,
            encoding=protocol.read_record_encoding,
            algorithm=algorithm,
        ),
    )
    _compare(
        "audit-commitment-digest",
        manifest.audit_commitment_digest,
        commitment_digest(audit.commitment),
    )
    _compare(
        "construction-caliber-digest",
        manifest.construction_caliber_digest,
        construction_caliber_digest(
            spec=spec,
            caliber=caliber,
            bundle=bundle,
            algorithm=algorithm,
            closed_entries=closed_entries,
        ),
    )
    _compare(
        "execution-identity-digest",
        manifest.execution_identity_digest,
        execution_identity_digest(execution_identity, algorithm=algorithm),
    )


class PairedHandRecord(BaseModel):
    """一手牌的配对结果：定位字段与被测座位在两侧的净筹码。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hand_ordinal: PositiveInt
    button: NonNegativeInt
    probed_seat: NonNegativeInt
    under_test_net: int
    baseline_net: int


class PairedRunMetadata(BaseModel):
    """运行元数据：规格定位、手数与环境口径，不含策略内部量。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    num_players: PositiveInt
    starting_stack: PositiveInt
    small_blind: PositiveInt
    big_blind: PositiveInt
    hand_count: PositiveInt
    spec_digest: str
    schedule_digest: str
    material_manifest_digest: str
    execution_identity: ExecutionIdentityRecord
    reference_snapshot: Mapping[str, object]


class PairedRunOutput(BaseModel):
    """配对比较的输出结构：逐手记录与运行元数据。

    本结构只描述输出应含哪些字段；产出它的执行路径尚未实现，也不在本轮范围内。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    hands: tuple[PairedHandRecord, ...]
    metadata: PairedRunMetadata

    @model_validator(mode="after")
    def _require_well_formed(self) -> PairedRunOutput:
        if not self.hands:
            raise VerificationError("输出必须至少包含一手牌")
        ordinals = [record.hand_ordinal for record in self.hands]
        if ordinals != sorted(set(ordinals)):
            raise VerificationError("逐手记录的块内手序必须严格递增且互不重复")
        if len(self.hands) != self.metadata.hand_count:
            raise VerificationError("逐手记录条数与运行元数据的手数不一致")
        return self


def build_run_metadata(
    *,
    spec: DomainRunSpec,
    manifest: FrozenRunManifest,
    execution_identity: ExecutionIdentityRecord,
    records: Sequence[PairedHandRecord],
) -> PairedRunMetadata:
    """按下发规格与冻结清单组装运行元数据；不执行任何牌局推进。"""
    return PairedRunMetadata(
        num_players=spec.num_players,
        starting_stack=spec.starting_stack,
        small_blind=spec.small_blind,
        big_blind=spec.big_blind,
        hand_count=len(records),
        spec_digest=manifest.spec_digest,
        schedule_digest=manifest.schedule_digest,
        material_manifest_digest=manifest.material_manifest_digest,
        execution_identity=execution_identity,
        reference_snapshot=reference_snapshot(),
    )


def verify_v2_frozen_records(
    entries: Sequence[tuple[str, tuple[str, ...]]],
    manifest: MaterialManifest,
    reads: Sequence[ReadRecord],
    transcript: bytes,
    *,
    probed_by_hand: Mapping[int, int],
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    baseline_identifier: str,
    under_test_identifier: str,
    lock_versions: CampaignLockVersions,
) -> None:
    """重算两个协议版本的配置摘要，并核对已提交的 v2 记录。不推进牌局。"""
    common = {
        "num_players": num_players,
        "starting_stack": starting_stack,
        "small_blind": small_blind,
        "big_blind": big_blind,
        "baseline_identifier": baseline_identifier,
        "under_test_identifier": under_test_identifier,
        "lock_versions": lock_versions,
    }
    campaign_v1 = campaign_configuration_digest(**common, randomization_protocol=1)
    campaign_v2 = campaign_configuration_digest(**common, randomization_protocol=2)
    verify_v2_closed_binding(
        entries,
        manifest,
        reads,
        transcript,
        probed_by_hand=probed_by_hand,
        num_players=num_players,
        campaign_v1=campaign_v1,
        campaign_v2=campaign_v2,
    )
