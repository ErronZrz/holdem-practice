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

from .config import DomainRunSpec, schedule_digest, spec_digest
from .digests import DIGEST_ALGORITHMS, bytes_digest
from .errors import FreezeBindingError, VerificationError
from .execution_identity import (
    ExecutionIdentityRecord,
    execution_identity_digest,
    reference_snapshot,
)
from .identity import ConstructionCaliber
from .instantiation import (
    construction_caliber_digest,
    materials_digest,
    require_construction_calibers,
    require_instantiation_caliber,
    require_materials,
)
from .materials import HandMaterials, MaterialManifest, manifest_digest
from .protocol import (
    AuditedMaterials,
    commitment_digest,
    protocol_digest,
    read_record_digest,
    verify_audit,
    verify_manifest_binding,
    verify_material_binding,
)

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
    """把流程步骤整理成记录条目，顺序与声明顺序一致。"""
    return tuple(
        (f"step-{index + 1}", name) for index, name in enumerate(RUN_FLOW_STEPS)
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
        supplied_materials_digest=materials_digest(bundle, algorithm=algorithm),
        material_manifest_digest=manifest_digest(material_manifest, algorithm=algorithm),
        audit_transcript_digest=bytes_digest(audit.transcript, algorithm=algorithm),
        audit_read_record_digest=read_record_digest(
            audit.reads,
            encoding=spec.protocol.read_record_encoding,
            algorithm=algorithm,
        ),
        audit_commitment_digest=commitment_digest(audit.commitment),
        construction_caliber_digest=construction_caliber_digest(
            spec=spec, caliber=caliber, bundle=bundle, algorithm=algorithm
        ),
        execution_identity_digest=execution_identity_digest(
            execution_identity, algorithm=algorithm
        ),
    )


def _compare(item: str, recorded: str, recomputed: str) -> None:
    """比对一项摘要；不一致即失败并指出项名。"""
    if recorded != recomputed:
        raise FreezeBindingError(f"冻结清单与本次输入不一致：{item}")


def verify_frozen_inputs(
    *,
    manifest: FrozenRunManifest,
    spec: DomainRunSpec,
    caliber: ConstructionCaliber,
    bundle: Sequence[HandMaterials],
    audit: AuditedMaterials,
    execution_identity: ExecutionIdentityRecord,
    material_manifest: MaterialManifest,
) -> None:
    """核验本次输入就是冻结清单所指的那一份，并核验材料来源可复核。

    校验顺序：先复核审计材料本身，再确认材料与审计逐项配对，再走清单三步链
    （清单 ↔ 审计 ↔ 送交材料 ↔ 承诺里的清单摘要），再校验材料与规格的结构一致，
    再走身份口径主链（显式构造口径与规格标识的逐字比对、基线一侧接口与公开摘要及座位范围
    三项硬限制、材料格式、逐手逐臂逐座位构造计划、执行身份里的实例化口径一致性），
    最后用本次输入重算全部十项摘要并与清单比对。任一项不符即失败，不重取材料、不修补。
    """
    protocol = spec.protocol
    if manifest.digest_algorithm != protocol.digest_algorithm:
        raise FreezeBindingError("冻结清单的摘要算法与协议不一致")
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
    )
    require_materials(spec, bundle)
    require_construction_calibers(spec, caliber, bundle)

    algorithm = protocol.digest_algorithm
    require_instantiation_caliber(
        execution_identity,
        spec=spec,
        caliber=caliber,
        bundle=bundle,
        algorithm=algorithm,
    )
    _compare("spec-digest", manifest.spec_digest, spec_digest(spec))
    _compare("schedule-digest", manifest.schedule_digest, schedule_digest(spec))
    _compare("protocol-digest", manifest.protocol_digest, protocol_digest(protocol))
    _compare(
        "supplied-materials-digest",
        manifest.supplied_materials_digest,
        materials_digest(bundle, algorithm=algorithm),
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
            spec=spec, caliber=caliber, bundle=bundle, algorithm=algorithm
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
