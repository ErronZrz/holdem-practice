"""随机化协议的结构规格、逐读取审计核验与材料绑定：只定结构、只做校验。

设计目的：
- 把「不放回抽取 + 无偏拒绝采样 + 可机械复核的逐读取审计」写成可校验的结构；
- 来源接口、输出域、每次读取的位宽、遍历顺序与承诺形式一律由调用方显式提供，
  本模块不设默认值，也不生成、不派生任何随机材料；
- 审计核验只检查来源标识、环境记录、调用顺序、完整性与映射规则，不能证明独立性或均匀性；
- 材料绑定把「送进运行器的材料」与「审计中被接受并承诺的取值」逐项配对，使材料来源可复核。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal, Self

if TYPE_CHECKING:
    from .config import DomainRunSpec

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .deal import DECK_SIZE
from .digests import DIGEST_ALGORITHMS, bytes_digest, content_digest
from .errors import MaterialBindingError, ProtocolAuditError, ProtocolSpecError
from .materials import (
    HandMaterials,
    MaterialManifest,
    manifest_digest,
    require_supplied_materials_order,
)

# 本模块已实现的逐读取记录编码；其余取值一律显式失败，不静默替代。
READ_RECORD_ENCODINGS: tuple[str, ...] = ("compact-json-v1",)
PROTOCOL_SCHEMA_V1 = "randomization-protocol-v1"
PROTOCOL_SCHEMA_V2 = "randomization-protocol-v2"
LOCKED_SOURCE_INTERFACE = "python-os-urandom@1"
LOCKED_ENVIRONMENT_RECORD = "local-single-process-no-parallel@1"
# 拒绝规则的规范标识：标识不变则规则内容不得变化。
REJECTION_RULE_ID = "rejection-whole-multiple-truncation-v1"
_DOMAIN_SIZE_2_256 = 1 << 256

NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]


class PurposeRole(StrEnum):
    """材料用途在运行结构中的角色。

    角色是结构性的：标签、索引字段与输出域由调用方另行显式给定，不由本模块选定。
    """

    # 两臂共享的发牌材料：不放回抽取，逐步缩小可用范围。
    DEAL = "deal"
    # 非被测座位的每手材料。
    NON_PROBED_SEED = "non-probed-seed"
    # 被测座位在候选身份一臂的材料。
    UNDER_TEST_MATERIAL = "under-test-material"
    # 被测座位在基线一臂的材料。
    BASELINE_SEED = "baseline-seed"


PURPOSE_ROLES: tuple[PurposeRole, ...] = (
    PurposeRole.DEAL,
    PurposeRole.NON_PROBED_SEED,
    PurposeRole.UNDER_TEST_MATERIAL,
    PurposeRole.BASELINE_SEED,
)


def required_bit_width(domain_size: int) -> int:
    """无偏覆盖该输出域所需的最小位宽，向上取到 8 的倍数。

    只用整数运算，避免对数带来的边界误差。
    """
    if domain_size < 1:
        raise ProtocolSpecError("输出域大小必须为正")
    span = domain_size - 1
    bits = max(1, span.bit_length())
    return ((bits + 7) // 8) * 8


class FixedDomain(BaseModel):
    """固定大小的有限输出域：每次抽取的取值集合都不变。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["fixed"] = "fixed"
    size: PositiveInt

    def domain_size(self, step_index: int) -> int:
        """第若干次抽取的域大小；固定域与抽取次序无关。"""
        if step_index < 0:
            raise ProtocolSpecError("抽取次序不能为负")
        return self.size


class ShrinkingDomain(BaseModel):
    """每次抽取后缩小一个的有限输出域：对应不放回抽取。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["shrinking"] = "shrinking"
    initial_size: PositiveInt

    def domain_size(self, step_index: int) -> int:
        """第若干次抽取的域大小；超出可用数量即失败。"""
        if step_index < 0:
            raise ProtocolSpecError("抽取次序不能为负")
        size = self.initial_size - step_index
        if size <= 0:
            raise ProtocolSpecError("抽取次数超过不放回抽取的可用数量")
        return size


DomainRule = FixedDomain | ShrinkingDomain


class PurposeSpec(BaseModel):
    """一个用途的规格：角色、标签、索引字段、输出域与每次读取的位宽。

    索引字段的语义只声明两处：发牌用途的抽取次序字段，以及非被测座位用途的座位号字段。
    两者都是结构性的定位口径，取值本身仍由调用方给出。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: PurposeRole
    label: str
    index_fields: tuple[str, ...]
    # 按整数比较的索引字段，次序与它们在索引字段中的出现次序一致。
    integer_fields: tuple[str, ...] = ()
    # 发牌用途用于标识抽取次序的索引字段；其余用途不得声明。
    draw_index_field: str | None = None
    # 非被测座位用途用于标识座位号的索引字段；其余用途不得声明。
    seat_index_field: str | None = None
    domain: DomainRule
    bit_width: PositiveInt

    @model_validator(mode="after")
    def _require_well_formed(self) -> Self:
        if not self.label.strip():
            raise ProtocolSpecError("用途标签不能为空")
        if not self.index_fields:
            raise ProtocolSpecError("索引字段不能为空")
        if len(set(self.index_fields)) != len(self.index_fields):
            raise ProtocolSpecError("索引字段必须互不重复")
        if any(not name.strip() for name in self.index_fields):
            raise ProtocolSpecError("索引字段名不能为空")
        if len(set(self.integer_fields)) != len(self.integer_fields):
            raise ProtocolSpecError("整数字段必须互不重复")
        if any(name not in self.index_fields for name in self.integer_fields):
            raise ProtocolSpecError("整数字段必须属于索引字段")
        positions = [self.index_fields.index(name) for name in self.integer_fields]
        if positions != sorted(positions):
            raise ProtocolSpecError("整数字段必须按索引字段中的次序给出")
        if self.draw_index_field is not None and self.draw_index_field not in self.integer_fields:
            raise ProtocolSpecError("抽取次序字段必须按整数比较")
        if self.seat_index_field is not None and self.seat_index_field not in self.integer_fields:
            raise ProtocolSpecError("座位号字段必须按整数比较")
        for name in (self.draw_index_field, self.seat_index_field):
            if name is not None and name not in self.index_fields:
                raise ProtocolSpecError("声明的定位字段必须属于索引字段")
        if self.role is PurposeRole.DEAL:
            if not isinstance(self.domain, ShrinkingDomain):
                raise ProtocolSpecError("发牌用途必须是不放回抽取的收缩域")
            if self.draw_index_field is None or self.seat_index_field is not None:
                raise ProtocolSpecError("发牌用途必须声明抽取次序字段且不得声明座位号字段")
        else:
            if not isinstance(self.domain, FixedDomain):
                raise ProtocolSpecError("非发牌用途必须是固定大小的有限输出域")
            if self.draw_index_field is not None:
                raise ProtocolSpecError("非发牌用途不得声明抽取次序字段")
            if self.role is PurposeRole.NON_PROBED_SEED:
                if self.seat_index_field is None:
                    raise ProtocolSpecError("非被测座位用途必须声明座位号字段")
            elif self.role is PurposeRole.BASELINE_SEED and self.index_fields == (
                "campaign",
                "block",
                "hand",
                "seat",
                "event_index",
                "sigma_public",
            ):
                if self.seat_index_field != "seat":
                    raise ProtocolSpecError("基线逐决策键必须声明座位号字段")
                if self.integer_fields != ("block", "hand", "seat", "event_index"):
                    raise ProtocolSpecError("基线逐决策键的整数字段不符")
            elif self.seat_index_field is not None:
                raise ProtocolSpecError("该用途不得声明座位号字段")
        if self.bit_width % 8 != 0:
            raise ProtocolSpecError("每次读取的位宽必须是 8 的倍数")
        if self.bit_width < required_bit_width(self.domain.domain_size(0)):
            raise ProtocolSpecError("每次读取的位宽不足以无偏覆盖该用途的输出域")
        return self

    def draw_index_of(self, index_key: tuple[str, ...]) -> int:
        """取索引键中的抽取次序值；缺失或非整数即失败。"""
        field = self.draw_index_field
        if field is None:
            raise ProtocolSpecError("该用途未声明抽取次序字段")
        return _require_integer_field(self.index_fields, index_key, field)

    def seat_index_of(self, index_key: tuple[str, ...]) -> int:
        """取索引键中的座位号；缺失或非整数即失败。"""
        field = self.seat_index_field
        if field is None:
            raise ProtocolSpecError("该用途未声明座位号字段")
        return _require_integer_field(self.index_fields, index_key, field)

    def index_order_key(self, index_key: tuple[str, ...]) -> tuple[int | str, ...]:
        """索引比较键：按声明字段顺序逐字段比较。

        整数字段按无前导零十进制解析后比较，其余字段按字符串比较。
        """
        if len(index_key) != len(self.index_fields):
            raise ProtocolSpecError("索引键的取值数与索引字段数不符")
        integers = set(self.integer_fields)
        return tuple(
            _parse_canonical_integer(name, value) if name in integers else value
            for name, value in zip(self.index_fields, index_key, strict=True)
        )

    def field_text(self, index_key: tuple[str, ...], name: str) -> str:
        """取索引键中某个具名字段的原文；字段不存在或长度不符即失败。"""
        if len(index_key) != len(self.index_fields):
            raise ProtocolSpecError("索引键的取值数与索引字段数不符")
        if name not in self.index_fields:
            raise ProtocolSpecError(f"该用途未声明字段：{name!r}")
        return index_key[self.index_fields.index(name)]

    def field_integer(self, index_key: tuple[str, ...], name: str) -> int:
        """把具名字段按无前导零十进制解析成整数。"""
        return _parse_canonical_integer(name, self.field_text(index_key, name))


def _parse_canonical_integer(field: str, raw: str) -> int:
    """整数字段只接受无前导零的 ASCII 十进制；`0` 本身合法。"""
    if not raw or any(character not in "0123456789" for character in raw):
        raise ProtocolSpecError(f"整数字段必须是无前导零的十进制：{field!r}")
    if raw.startswith("0") and raw != "0":
        raise ProtocolSpecError(f"整数字段必须是无前导零的十进制：{field!r}")
    return int(raw)


def _locator_value(field: str, raw: str) -> int:
    """把定位字段的取值解析为非负整数；非法即失败。"""
    return _parse_canonical_integer(field, raw)


def _require_integer_field(
    index_fields: tuple[str, ...], index_key: tuple[str, ...], field: str
) -> int:
    """取索引键中某个定位字段的整数值；长度不符或取值非整数即失败。"""
    if len(index_key) != len(index_fields):
        raise ProtocolSpecError("索引键的取值数与索引字段数不符")
    if field not in index_fields:
        raise ProtocolSpecError(f"该用途未声明定位字段：{field!r}")
    return _locator_value(field, index_key[index_fields.index(field)])


class RandomizationProtocolSpec(BaseModel):
    """随机化协议的结构规格：全部必填，缺一项即失败。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_interface_id: str
    environment_record: str
    rejection_rule: str
    purposes: tuple[PurposeSpec, ...]
    # 用途的生成次序；每个用途内部按索引的升序生成。
    traversal_order: tuple[str, ...]
    commitment_form: str
    audit_format_version: PositiveInt
    digest_algorithm: str
    read_record_encoding: str
    protocol_schema: Literal[PROTOCOL_SCHEMA_V1, PROTOCOL_SCHEMA_V2] = PROTOCOL_SCHEMA_V1

    @model_validator(mode="after")
    def _require_well_formed(self) -> Self:
        declared = (
            ("source_interface_id", self.source_interface_id),
            ("environment_record", self.environment_record),
            ("commitment_form", self.commitment_form),
        )
        for name, value in declared:
            if not value.strip():
                raise ProtocolSpecError(f"协议字段不能为空：{name}")
        if self.rejection_rule != REJECTION_RULE_ID:
            raise ProtocolSpecError("拒绝规则标识与锁定值不符")
        roles = [purpose.role for purpose in self.purposes]
        if len(set(roles)) != len(roles) or set(roles) != set(PURPOSE_ROLES):
            raise ProtocolSpecError("用途必须恰好覆盖四种角色各一次")
        labels = [purpose.label for purpose in self.purposes]
        if len(set(labels)) != len(labels):
            raise ProtocolSpecError("用途标签必须互不重复")
        if tuple(self.traversal_order) != tuple(labels):
            raise ProtocolSpecError("用途次序必须与遍历顺序一致")
        if self.digest_algorithm not in DIGEST_ALGORITHMS:
            raise ProtocolSpecError(f"摘要算法未实现：{self.digest_algorithm!r}")
        if self.read_record_encoding not in READ_RECORD_ENCODINGS:
            raise ProtocolSpecError(f"逐读取记录编码未实现：{self.read_record_encoding!r}")
        if self.protocol_schema == PROTOCOL_SCHEMA_V2:
            if not protocol_declares_v2_keys(self):
                raise ProtocolSpecError("v2 协议必须使用完整 κ 键形")
            if self.source_interface_id != LOCKED_SOURCE_INTERFACE:
                raise ProtocolSpecError("v2 协议的来源必须是锁定的随机源接口")
            if self.environment_record != LOCKED_ENVIRONMENT_RECORD:
                raise ProtocolSpecError("v2 协议的环境必须是锁定的单进程记录")
        elif protocol_declares_v2_keys(self):
            raise ProtocolSpecError("v1 schema 不得承载 v2 键形")
        return self

    def purpose_for_role(self, role: PurposeRole) -> PurposeSpec:
        """按角色取用途规格；角色未声明时失败。"""
        for purpose in self.purposes:
            if purpose.role is role:
                return purpose
        raise ProtocolSpecError(f"协议未声明该用途角色：{role!r}")

    def purpose_for_label(self, label: str) -> PurposeSpec:
        """按标签取用途规格；标签未声明时失败。"""
        for purpose in self.purposes:
            if purpose.label == label:
                return purpose
        raise ProtocolAuditError(f"审计记录使用了协议未声明的用途标签：{label!r}")

    def has_label(self, label: str) -> bool:
        """判断该标签是否由协议声明。"""
        return any(purpose.label == label for purpose in self.purposes)


def _purpose_protocol_payload(purpose: PurposeSpec) -> dict[str, object]:
    """协议载荷中的单个用途：字段集封闭，域大小用精确整数。"""
    domain = purpose.domain
    if isinstance(domain, ShrinkingDomain):
        domain_payload: dict[str, object] = {
            "kind": "shrinking",
            "initial_size": domain.initial_size,
        }
    else:
        domain_payload = {"kind": "fixed", "size": domain.size}
    return {
        "label": purpose.label,
        "role": purpose.role.value,
        "index_fields": list(purpose.index_fields),
        "integer_fields": list(purpose.integer_fields),
        "draw_index_field": purpose.draw_index_field,
        "seat_index_field": purpose.seat_index_field,
        "domain": domain_payload,
        "bit_width": purpose.bit_width,
    }


def protocol_payload(protocol: RandomizationProtocolSpec) -> dict[str, object]:
    """随机化协议的封闭载荷。摘要只覆盖这些字段，不覆盖模型上的其他属性。"""
    return {
        "schema": protocol.protocol_schema,
        "source_interface_id": protocol.source_interface_id,
        "environment_record": protocol.environment_record,
        "rejection_rule": protocol.rejection_rule,
        "purposes": [_purpose_protocol_payload(purpose) for purpose in protocol.purposes],
        "traversal_order": list(protocol.traversal_order),
        "commitment_form": protocol.commitment_form,
        "audit_format_version": protocol.audit_format_version,
        "digest_algorithm": protocol.digest_algorithm,
        "read_record_encoding": protocol.read_record_encoding,
    }


def protocol_digest(protocol: RandomizationProtocolSpec) -> str:
    """由封闭协议载荷重算摘要。"""
    return content_digest(protocol_payload(protocol), algorithm=protocol.digest_algorithm)


def purpose_index_mapping_payload() -> dict[str, object]:
    """用途与索引映射的封闭载荷，与某次测试协议的字段取值无关。"""
    fixed = {"kind": "fixed", "size": _DOMAIN_SIZE_2_256}
    return {
        "schema": "purpose-index-mapping-v1",
        "purposes": [
            {
                "label": "deal",
                "role": PurposeRole.DEAL.value,
                "index_fields": ["campaign", "block", "hand", "draw"],
                "integer_fields": ["block", "hand", "draw"],
                "domain": {"kind": "shrinking", "initial_size": 52},
                "bit_width": 8,
            },
            {
                "label": "non_probed",
                "role": PurposeRole.NON_PROBED_SEED.value,
                "index_fields": ["campaign", "block", "hand", "seat"],
                "integer_fields": ["block", "hand", "seat"],
                "domain": fixed,
                "bit_width": 256,
            },
            {
                "label": "arm_m",
                "role": PurposeRole.UNDER_TEST_MATERIAL.value,
                "index_fields": ["campaign", "block", "hand"],
                "integer_fields": ["block", "hand"],
                "domain": fixed,
                "bit_width": 256,
            },
            {
                "label": "arm_b",
                "role": PurposeRole.BASELINE_SEED.value,
                "index_fields": ["campaign", "block", "hand"],
                "integer_fields": ["block", "hand"],
                "domain": fixed,
                "bit_width": 256,
            },
        ],
        "traversal_order": ["deal", "non_probed", "arm_m", "arm_b"],
    }


def purpose_index_mapping_digest(*, algorithm: str) -> str:
    """按封闭载荷重算用途与索引映射摘要。"""
    return content_digest(purpose_index_mapping_payload(), algorithm=algorithm)


def resolve_read(raw_value: int, *, bit_width: int, domain_size: int) -> int | None:
    """按无偏拒绝采样判定一次读取：接受给出输出值，拒绝返回空。

    拒绝时调用方必须按同一规则继续读取下一段原始值，不得改换用途，也不得截断为有偏值。
    """
    if bit_width <= 0 or bit_width % 8 != 0:
        raise ProtocolSpecError("每次读取的位宽必须是正的 8 的倍数")
    if domain_size < 1:
        raise ProtocolSpecError("输出域大小必须为正")
    if bit_width < required_bit_width(domain_size):
        raise ProtocolSpecError("位宽不足以无偏覆盖该输出域")
    if not 0 <= raw_value < 1 << bit_width:
        raise ProtocolAuditError("原始值超出该位宽可表示的范围")
    # 可接受区间为域大小的整数倍，括号内的部分一律丢弃，保证输出在域上均匀。
    bound = domain_size * ((1 << bit_width) // domain_size)
    if raw_value < bound:
        return raw_value % domain_size
    return None


class ReadRecord(BaseModel):
    """一次读取的记录：位置、原始值与接受或拒绝判定。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    read_index: NonNegativeInt
    purpose_label: str
    index_key: tuple[str, ...]
    bit_width: PositiveInt
    raw_offset: NonNegativeInt
    raw_value: NonNegativeInt
    accepted: bool
    output: NonNegativeInt | None = None

    @model_validator(mode="after")
    def _require_consistent(self) -> Self:
        if not self.purpose_label.strip():
            raise ProtocolAuditError("读取记录的用途标签不能为空")
        if not self.index_key:
            raise ProtocolAuditError("读取记录的索引键不能为空")
        if self.accepted and self.output is None:
            raise ProtocolAuditError("被接受的读取必须给出输出值")
        if not self.accepted and self.output is not None:
            raise ProtocolAuditError("被拒绝的读取不得给出输出值")
        if self.raw_value >= 1 << self.bit_width:
            raise ProtocolAuditError("原始值超出该位宽可表示的范围")
        return self

    @property
    def byte_length(self) -> int:
        """该次读取在转录中占用的字节数。"""
        return self.bit_width // 8


class TranscriptCommitment(BaseModel):
    """汇总层的审计材料：来源、环境、生成时段、遍历顺序、计数与各项摘要。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_interface_id: str
    environment_record: str
    generation_started_at: str
    generation_finished_at: str
    traversal_order: tuple[str, ...]
    # 每用途的条目数与拒绝次数；标签必须来自协议声明。
    entry_counts: tuple[tuple[str, NonNegativeInt], ...]
    rejection_counts: tuple[tuple[str, NonNegativeInt], ...]
    transcript_digest: str
    read_record_digest: str
    manifest_digest: str
    generator_code_digest: str
    digest_algorithm: str
    read_record_encoding: str
    audit_format_version: PositiveInt

    @model_validator(mode="after")
    def _require_well_formed(self) -> Self:
        declared = (
            ("source_interface_id", self.source_interface_id),
            ("environment_record", self.environment_record),
        )
        for name, value in declared:
            if not value.strip():
                raise ProtocolAuditError(f"承诺字段不能为空：{name}")
        started = _parse_generation_timestamp(
            "generation_started_at", self.generation_started_at
        )
        finished = _parse_generation_timestamp(
            "generation_finished_at", self.generation_finished_at
        )
        if started > finished:
            raise ProtocolAuditError("生成开始时刻不得晚于结束时刻")
        declared = (
            ("transcript_digest", self.transcript_digest),
            ("read_record_digest", self.read_record_digest),
            ("manifest_digest", self.manifest_digest),
            ("generator_code_digest", self.generator_code_digest),
        )
        for name, value in declared:
            if not value.strip():
                raise ProtocolAuditError(f"摘要字段不能为空：{name}")
        if self.digest_algorithm not in DIGEST_ALGORITHMS:
            raise ProtocolAuditError(f"摘要算法未实现：{self.digest_algorithm!r}")
        if self.read_record_encoding not in READ_RECORD_ENCODINGS:
            raise ProtocolAuditError(f"逐读取记录编码未实现：{self.read_record_encoding!r}")
        for name, counts in self.count_groups():
            labels = [label for label, _ in counts]
            if len(set(labels)) != len(labels):
                raise ProtocolAuditError(f"计数条目的用途标签必须互不重复：{name}")
        return self

    def count_groups(self) -> tuple[tuple[str, tuple[tuple[str, int], ...]], ...]:
        """两类计数条目：条目名与其内容，供结构校验与比对使用。"""
        return (
            ("entry_counts", self.entry_counts),
            ("rejection_counts", self.rejection_counts),
        )

    def count_for(self, name: str, label: str) -> int | None:
        """读取指定计数条目；标签缺失时返回空。"""
        groups = dict(self.count_groups())
        counts = groups.get(name)
        if counts is None:
            raise ProtocolAuditError(f"承诺不含该计数条目：{name!r}")
        for entry_label, count in counts:
            if entry_label == label:
                return count
        return None


def commitment_digest(commitment: TranscriptCommitment) -> str:
    """由承诺内容重算摘要：承诺的任何字段被改动都会使摘要不符。"""
    return content_digest(
        commitment.model_dump(mode="json"), algorithm=commitment.digest_algorithm
    )


@dataclass(frozen=True)
class AuditedMaterials:
    """已审计材料的凭据：原始字节转录、逐读取记录与汇总承诺。"""

    transcript: bytes
    reads: tuple[ReadRecord, ...]
    commitment: TranscriptCommitment

    def __post_init__(self) -> None:
        if not isinstance(self.transcript, bytes):
            raise ProtocolAuditError("原始字节转录必须是字节串")


def _parse_generation_timestamp(name: str, value: str) -> datetime:
    """生成时刻只接受六位微秒、后缀为 Z 的有效公历时间。"""
    fraction = value[20:26]
    if (
        len(value) != 27
        or value[4] != "-"
        or value[7] != "-"
        or value[10] != "T"
        or value[13] != ":"
        or value[16] != ":"
        or value[19] != "."
        or value[26] != "Z"
        or not fraction.isdigit()
    ):
        raise ProtocolAuditError(f"生成时刻格式不合法：{name}")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ProtocolAuditError(f"生成时刻不是有效公历时间：{name}") from error


def read_record_digest(
    reads: Sequence[ReadRecord], *, encoding: str, algorithm: str
) -> str:
    """按调用时的物理序号编码逐读取记录。序号不连续则拒绝，不先排序再取摘要。"""
    if encoding != "compact-json-v1":
        raise ProtocolSpecError(f"逐读取记录编码未实现：{encoding!r}")
    if [record.read_index for record in reads] != list(range(len(reads))):
        raise ProtocolAuditError("逐读取记录必须按物理序号从零起连续排列")
    text = json.dumps(
        [record.model_dump(mode="json") for record in reads],
        separators=(",", ":"),
        ensure_ascii=True,
        sort_keys=True,
    )
    payload = text.encode("utf-8")
    return bytes_digest(payload, algorithm=algorithm)


def _require_commitment_matches_protocol(
    protocol: RandomizationProtocolSpec, commitment: TranscriptCommitment
) -> None:
    """确认承诺与协议逐项一致：来源、环境、遍历顺序、算法与记录编码。"""
    if commitment.source_interface_id != protocol.source_interface_id:
        raise ProtocolAuditError("承诺的来源接口标识与协议不一致")
    if commitment.environment_record != protocol.environment_record:
        raise ProtocolAuditError("承诺的环境记录与协议不一致")
    if commitment.traversal_order != protocol.traversal_order:
        raise ProtocolAuditError("承诺的遍历顺序与协议不一致")
    if commitment.digest_algorithm != protocol.digest_algorithm:
        raise ProtocolAuditError("承诺的摘要算法与协议不一致")
    if commitment.read_record_encoding != protocol.read_record_encoding:
        raise ProtocolAuditError("承诺的逐读取记录编码与协议不一致")
    if commitment.audit_format_version != protocol.audit_format_version:
        raise ProtocolAuditError("承诺的审计材料格式版本与协议不一致")


def _require_counts_match(
    protocol: RandomizationProtocolSpec,
    commitment: TranscriptCommitment,
    accepted: dict[str, int],
    rejected: dict[str, int],
) -> None:
    """确认承诺中的每用途计数与逐读取记录的重算结果一致。"""
    declared = {purpose.label for purpose in protocol.purposes}
    reported = (
        ("entry_counts", commitment.entry_counts, accepted),
        ("rejection_counts", commitment.rejection_counts, rejected),
    )
    for name, counts, observed in reported:
        labels = [label for label, _ in counts]
        if labels != list(protocol.traversal_order):
            raise ProtocolAuditError(f"计数条目必须按遍历顺序排列：{name}")
        if set(labels) != declared:
            raise ProtocolAuditError(f"承诺的计数条目未覆盖全部用途：{name}")
        for label in declared:
            if commitment.count_for(name, label) != observed[label]:
                raise ProtocolAuditError(f"承诺的计数与逐读取记录不符：{name}/{label}")


def verify_audit(
    *,
    protocol: RandomizationProtocolSpec,
    transcript: bytes,
    reads: Sequence[ReadRecord],
    commitment: TranscriptCommitment,
) -> None:
    """机械复核逐读取审计材料；任一项不符即失败。

    可复核的范围包括：来源与环境、用途与索引的完整顺序、转录的完整性与无重叠、
    每次读取的输出与拒绝判定、同一用途索引读取组的完整不变量（零或多条拒绝之后必须有
    恰一条同键接受，已接受后不得再读，索引切换或审计结束时仍未接受的组不成立）、
    逐用途计数与各项摘要。它不能证明来源的实际独立性或均匀性。
    """
    if not isinstance(transcript, bytes):
        raise ProtocolAuditError("原始字节转录必须是字节串")
    _require_commitment_matches_protocol(protocol, commitment)
    if commitment.transcript_digest != bytes_digest(
        transcript, algorithm=commitment.digest_algorithm
    ):
        raise ProtocolAuditError("转录摘要与转录内容不符")
    if commitment.read_record_digest != read_record_digest(
        reads, encoding=commitment.read_record_encoding, algorithm=commitment.digest_algorithm
    ):
        raise ProtocolAuditError("逐读取记录摘要与记录内容不符")

    ordered = sorted(reads, key=lambda record: record.read_index)
    if [record.read_index for record in ordered] != list(range(len(ordered))):
        raise ProtocolAuditError("逐读取序号必须从零起连续，不得重复或跳号")

    order_index = {label: index for index, label in enumerate(protocol.traversal_order)}
    accepted_counts = {purpose.label: 0 for purpose in protocol.purposes}
    rejection_counts = {purpose.label: 0 for purpose in protocol.purposes}
    accepted_keys: dict[str, set[tuple[str, ...]]] = {
        purpose.label: set() for purpose in protocol.purposes
    }
    last_index_key: dict[str, tuple[str, ...] | None] = {
        purpose.label: None for purpose in protocol.purposes
    }
    last_order_key: dict[str, tuple[int | str, ...] | None] = {
        purpose.label: None for purpose in protocol.purposes
    }
    # 每个用途当前正在读取的索引组：组内可有零或多条拒绝，但必须以恰一条接受收尾。
    open_index_key: dict[str, tuple[str, ...] | None] = {
        purpose.label: None for purpose in protocol.purposes
    }
    open_group_accepted: dict[str, bool] = {
        purpose.label: False for purpose in protocol.purposes
    }
    offset = 0
    previous_purpose_order = 0
    for position, record in enumerate(ordered):
        purpose = protocol.purpose_for_label(record.purpose_label)
        label = purpose.label
        if record.bit_width != purpose.bit_width:
            raise ProtocolAuditError(f"读取 #{position} 的位宽与协议不一致")
        if len(record.index_key) != len(purpose.index_fields):
            raise ProtocolAuditError(f"读取 #{position} 的索引取值数与索引字段不符")
        current_purpose_order = order_index[label]
        if current_purpose_order < previous_purpose_order:
            raise ProtocolAuditError("读取顺序不符合协议声明的遍历顺序")
        previous_purpose_order = current_purpose_order

        # 同一用途内必须按索引升序给出；同一索引的多次读取（拒绝与接受）必须同键相邻。
        settled_order = last_order_key[label]
        settled_key = last_index_key[label]
        try:
            order_key = purpose.index_order_key(record.index_key)
            step_index = (
                purpose.draw_index_of(record.index_key)
                if purpose.role is PurposeRole.DEAL
                else 0
            )
        except ProtocolSpecError as error:
            raise ProtocolAuditError(f"读取 #{position} 的索引不合规：{error}") from error
        if settled_order is not None:
            if order_key < settled_order:
                raise ProtocolAuditError("同一用途内的索引顺序必须递增")
            if order_key == settled_order and record.index_key != settled_key:
                raise ProtocolAuditError("同一索引的取值表示必须一致")
        last_index_key[label] = record.index_key
        last_order_key[label] = order_key

        # 索引切换即一个读取组结束：该组必须以一条同键的接受读取收尾，只有拒绝的组不成立。
        open_key = open_index_key[label]
        if open_key is not None and record.index_key != open_key:
            _require_group_settled(label, open_key, open_group_accepted[label])
            open_group_accepted[label] = False
        open_index_key[label] = record.index_key

        if record.index_key in accepted_keys[label]:
            raise ProtocolAuditError("同一用途的同一索引在被接受之后不得再次读取")

        if record.raw_offset != offset:
            raise ProtocolAuditError(f"读取 #{position} 的偏移出现缺口或重叠")
        end = offset + record.byte_length
        if end > len(transcript):
            raise ProtocolAuditError("转录长度不足以覆盖该次读取")
        if int.from_bytes(transcript[offset:end], "big") != record.raw_value:
            raise ProtocolAuditError(f"读取 #{position} 的原始值与转录不符")
        offset = end

        try:
            domain_size = purpose.domain.domain_size(step_index)
        except ProtocolSpecError as error:
            raise ProtocolAuditError(f"该用途的抽取次序超出可用数量：{error}") from error
        expected = resolve_read(
            record.raw_value, bit_width=record.bit_width, domain_size=domain_size
        )
        if expected is None:
            if record.accepted or record.output is not None:
                raise ProtocolAuditError("按拒绝规则应丢弃的读取被记为接受")
            rejection_counts[label] += 1
            continue
        if not record.accepted or record.output != expected:
            raise ProtocolAuditError("读取的输出值与拒绝规则的重算结果不符")
        group_keys = accepted_keys[label]
        group_keys.add(record.index_key)
        accepted_counts[label] += 1
        open_group_accepted[label] = True

    # 审计结束时不得留下只有拒绝读取、从未被接受的索引组。
    for label, open_key in open_index_key.items():
        if open_key is None:
            continue
        _require_group_settled(label, open_key, open_group_accepted[label])
    if offset != len(transcript):
        raise ProtocolAuditError("转录尾部存在未被任何读取消耗的多余字节")
    _require_deal_draw_coverage(protocol, ordered)
    _require_counts_match(protocol, commitment, accepted_counts, rejection_counts)


def _require_group_settled(
    label: str, index_key: tuple[str, ...], accepted: bool
) -> None:
    """一个索引读取组必须以同键的接受读取收尾；只有拒绝读取的组不成立。"""
    if accepted:
        return
    raise ProtocolAuditError(
        f"用途 {label!r} 在索引 {index_key!r} 上缺少同键的接受读取："
        "只含拒绝读取的索引组不成立"
    )


def _require_deal_draw_coverage(
    protocol: RandomizationProtocolSpec, reads: Sequence[ReadRecord]
) -> None:
    """确认发牌用途在各自分组内的已接受抽取次序从零起连续。"""
    purpose = protocol.purpose_for_role(PurposeRole.DEAL)
    draw_field = purpose.draw_index_field
    if draw_field is None:
        raise ProtocolAuditError("发牌用途未声明抽取次序字段")
    position = purpose.index_fields.index(draw_field)
    groups: dict[tuple[str, ...], list[int]] = {}
    for record in reads:
        if not record.accepted or record.purpose_label != purpose.label:
            continue
        draw = purpose.draw_index_of(record.index_key)
        group = record.index_key[:position] + record.index_key[position + 1 :]
        bucket = groups.setdefault(group, [])
        bucket.append(draw)
    for draws in groups.values():
        if sorted(draws) != list(range(len(draws))):
            raise ProtocolAuditError("发牌用途在各分组内的抽取次序必须从零起连续")


def _accepted_map(
    protocol: RandomizationProtocolSpec, reads: Sequence[ReadRecord]
) -> dict[tuple[str, tuple[str, ...]], int]:
    """审计侧映射：把已接受的读取展成「用途标签 + 索引键 → 输出值」。"""
    audited: dict[tuple[str, tuple[str, ...]], int] = {}
    for record in reads:
        if not record.accepted:
            continue
        protocol.purpose_for_label(record.purpose_label)
        key = (record.purpose_label, record.index_key)
        if key in audited:
            raise MaterialBindingError("审计中出现重复的已接受索引")
        if record.output is None:
            raise MaterialBindingError("已接受的读取缺少输出值")
        audited[key] = record.output
    return audited


def _supplied_map(
    protocol: RandomizationProtocolSpec, bundle: Sequence[HandMaterials]
) -> dict[tuple[str, tuple[str, ...]], int]:
    """材料侧映射：把送交材料展成「用途标签 + 索引键 → 取值」。"""
    supplied: dict[tuple[str, tuple[str, ...]], int] = {}
    for hand in bundle:
        for entry in hand.entries:
            if not protocol.has_label(entry.purpose_label):
                raise MaterialBindingError("材料使用了协议未声明的用途标签")
            key = (entry.purpose_label, entry.index_key)
            if key in supplied:
                raise MaterialBindingError("材料束中出现重复的索引")
            supplied[key] = entry.value
    return supplied


def _require_same_locations(
    left_name: str,
    right_name: str,
    left: dict[tuple[str, tuple[str, ...]], int],
    right: dict[tuple[str, tuple[str, ...]], int],
) -> None:
    """逐项比对两份定位映射：定位集合与同一位置的取值都必须相同。"""
    missing = set(right) - set(left)
    extra = set(left) - set(right)
    if missing or extra:
        raise MaterialBindingError(
            f"{left_name}与{right_name}的定位不一致：缺少 {len(missing)} 项，多出 {len(extra)} 项"
        )
    for key, value in left.items():
        if right[key] != value:
            raise MaterialBindingError(f"{left_name}与{right_name}的取值不一致")


def verify_material_binding(
    *,
    protocol: RandomizationProtocolSpec,
    bundle: Sequence[HandMaterials],
    reads: Sequence[ReadRecord],
) -> None:
    """逐项确认材料就是审计中被接受并承诺的取值。

    配对依据是「用途标签 + 索引键」构成的定位：材料侧与审计侧的定位集合必须相同，
    同一位置的取值必须相同。因此「材料来自被审计的那次生成」是可机械复核的结论，
    而不只是抄录一个摘要字符串。
    """
    supplied = _supplied_map(protocol, bundle)
    audited = _accepted_map(protocol, reads)
    _require_same_locations("材料", "审计", supplied, audited)
    _require_draw_order_matches(protocol, bundle)


def require_manifest_consistent(
    protocol: RandomizationProtocolSpec, manifest: MaterialManifest
) -> None:
    """校验材料清单的结构：标签已声明、定位合法，并按遍历顺序与索引升序给出。"""
    order = {label: index for index, label in enumerate(protocol.traversal_order)}
    positions: list[tuple[int, tuple[int | str, ...]]] = []
    for entry in manifest.entries:
        if not protocol.has_label(entry.purpose_label):
            raise MaterialBindingError("材料清单使用了协议未声明的用途标签")
        try:
            purpose = protocol.purpose_for_label(entry.purpose_label)
            order_key = purpose.index_order_key(entry.index_key)
        except ProtocolSpecError as error:
            raise MaterialBindingError(f"材料清单的索引不合规：{error}") from error
        positions.append((order[entry.purpose_label], order_key))
    if positions != sorted(positions):
        raise MaterialBindingError("材料清单必须按遍历顺序与索引升序给出")


def verify_manifest_binding(
    *,
    protocol: RandomizationProtocolSpec,
    manifest: MaterialManifest,
    reads: Sequence[ReadRecord],
    bundle: Sequence[HandMaterials],
    commitment: TranscriptCommitment,
    spec: DomainRunSpec,
) -> None:
    """三步链：材料清单 ↔ 审计中被接受的取值 ↔ 送交材料，并与承诺里的清单摘要比对。

    清单摘要由清单内容重算，因此「抄录一个与内容不符的摘要」必然失败；同时清单条目必须
    与审计的被接受取值、送交材料逐项一致，材料来源由此形成完整可复核链条。
    送交材料的次序在定位比对之前核对，且协议对象必须就是规格上的那一份。
    """
    if protocol is not spec.protocol:
        raise MaterialBindingError("绑定的协议必须就是规格上的协议")
    require_supplied_materials_order(spec, bundle)
    require_manifest_consistent(protocol, manifest)
    declared = manifest.entry_map()
    if commitment.manifest_digest != manifest_digest(
        manifest, algorithm=commitment.digest_algorithm
    ):
        raise MaterialBindingError("承诺里的清单摘要与清单内容不符")
    _require_same_locations("清单", "审计", declared, _accepted_map(protocol, reads))
    _require_same_locations("清单", "送交材料", declared, _supplied_map(protocol, bundle))


V2_TRAVERSAL: tuple[str, ...] = ("deal", "non_probed", "arm_m", "arm_b")
_V2_FIELDS: dict[str, tuple[str, ...]] = {
    "deal": ("campaign", "block", "hand", "draw"),
    "non_probed": ("campaign", "block", "hand", "seat", "event_index", "sigma_public"),
    "arm_m": ("campaign", "block", "hand"),
    "arm_b": ("campaign", "block", "hand", "seat", "event_index", "sigma_public"),
}
_V2_INTEGER_FIELDS = frozenset({"block", "hand", "seat", "event_index", "draw"})
_KAPPA_LABELS = frozenset({"non_probed", "arm_b"})
_COMMITMENT_FIELD_NAMES: tuple[str, ...] = (
    "source_interface_id",
    "environment_record",
    "generation_started_at",
    "generation_finished_at",
    "traversal_order",
    "entry_counts",
    "rejection_counts",
    "transcript_digest",
    "read_record_digest",
    "manifest_digest",
    "generator_code_digest",
    "digest_algorithm",
    "read_record_encoding",
    "audit_format_version",
)


def purpose_index_mapping_v2_payload() -> dict[str, object]:
    """v2 用途与索引的封闭载荷。不替换仍供既有身份使用的 v1 载荷。"""
    fixed = {"kind": "fixed", "size": _DOMAIN_SIZE_2_256}
    shrinking = {"kind": "shrinking", "initial_size": DECK_SIZE}

    def row(label: str, role: PurposeRole, domain: dict[str, object], bit_width: int) -> dict:
        fields = _V2_FIELDS[label]
        integers = [name for name in fields if name in _V2_INTEGER_FIELDS]
        return {
            "label": label,
            "role": role.value,
            "index_fields": list(fields),
            "integer_fields": integers,
            "domain": domain,
            "bit_width": bit_width,
        }

    return {
        "schema": "purpose-index-mapping-v2",
        "purposes": [
            row("deal", PurposeRole.DEAL, shrinking, 8),
            row("non_probed", PurposeRole.NON_PROBED_SEED, fixed, 256),
            row("arm_m", PurposeRole.UNDER_TEST_MATERIAL, fixed, 256),
            row("arm_b", PurposeRole.BASELINE_SEED, fixed, 256),
        ],
        "traversal_order": list(V2_TRAVERSAL),
    }


def randomization_protocol_v2_payload() -> dict[str, object]:
    """v2 协议载荷的字段表。拒绝标识与承诺字段名保持原样。"""
    mapping = purpose_index_mapping_v2_payload()
    return {
        "schema": "randomization-protocol-v2",
        "rejection_rule": REJECTION_RULE_ID,
        "purposes": mapping["purposes"],
        "traversal_order": list(V2_TRAVERSAL),
        "digest_algorithm": "sha256",
        "read_record_encoding": "compact-json-v1",
        "audit_format_version": 1,
        "commitment_fields": list(_COMMITMENT_FIELD_NAMES),
    }


def purpose_index_mapping_v2_digest(*, algorithm: str) -> str:
    """重算 v2 完整 κ 键规则的摘要。这是执行身份的输入，不是某次战役摘要。"""
    return content_digest(purpose_index_mapping_v2_payload(), algorithm=algorithm)


def closed_keyset_binding_digest(
    entries: Sequence[tuple[str, tuple[str, ...]]] | None,
    *,
    algorithm: str,
) -> str:
    """闭合集绑定摘要。v1 没有 κ 闭合集时使用固定缺席标记。"""
    if entries is None:
        payload: object = {"closed_keyset": "v1-absent"}
    else:
        payload = [
            {"purpose_label": label, "index_key": list(key)} for label, key in entries
        ]
    return content_digest(payload, algorithm=algorithm)


def validate_explicit_v2_keyset(
    entries: Sequence[tuple[str, tuple[str, ...]]],
    *,
    probed_by_hand: Mapping[int, int],
    num_players: int,
) -> None:
    """检查逐条预注册的完整键。不读取随机字节，也不补键。"""
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise ProtocolSpecError("条目必须是有限序列")
    if (
        isinstance(num_players, bool)
        or not isinstance(num_players, int)
        or not 2 <= num_players <= 23
    ):
        raise ProtocolSpecError("人数必须是 2 到 23 的整数")
    seen: set[tuple[str, tuple[str, ...]]] = set()
    sigma_slots: dict[tuple[str, str, int, int, int, int], str] = {}
    campaigns: set[str] = set()
    for label, index_key in entries:
        fields = _V2_FIELDS.get(label)
        if fields is None or len(index_key) != len(fields):
            raise ProtocolSpecError("完整键的用途或字段数不符")
        parsed = _parsed_v2_fields(fields, index_key)
        campaign = index_key[0]
        _require_campaign_text(campaign)
        campaigns.add(campaign)
        if label in _KAPPA_LABELS:
            _require_sigma_public_text(index_key[fields.index("sigma_public")])
            slot = (
                label,
                campaign,
                parsed["block"],
                parsed["hand"],
                parsed["seat"],
                parsed["event_index"],
            )
            sigma = index_key[fields.index("sigma_public")]
            previous = sigma_slots.get(slot)
            if previous is not None and previous != sigma:
                raise ProtocolSpecError("同一决策序号不得对应两条公开投影")
            sigma_slots[slot] = sigma
        _require_v2_ranges(label, parsed, probed_by_hand=probed_by_hand, num_players=num_players)
        location = (label, index_key)
        if location in seen:
            raise ProtocolSpecError("闭合集出现重复的完整键")
        seen.add(location)
    if len(campaigns) > 1:
        raise ProtocolSpecError("同一闭合集的 campaign 必须相同")


def verify_v2_closed_binding(
    entries: Sequence[tuple[str, tuple[str, ...]]],
    manifest: MaterialManifest,
    reads: Sequence[ReadRecord],
    transcript: bytes,
    *,
    probed_by_hand: Mapping[int, int],
    num_players: int,
    campaign_v1: str,
    campaign_v2: str,
) -> None:
    """核对已提交的闭合集、清单与审计。不创建引擎，也不补读。"""
    validate_explicit_v2_keyset(entries, probed_by_hand=probed_by_hand, num_players=num_players)
    ordered = sorted(entries, key=lambda item: v2_record_sort_key(item[0], item[1]))
    for _label, index_key in ordered:
        campaign = index_key[0]
        if campaign == campaign_v1 or campaign != campaign_v2:
            raise ProtocolSpecError("v2 材料键的 campaign 必须等于协议版本 2 的配置摘要")
    accepted = _require_v2_read_sequence(reads, ordered, transcript)
    locations = [(entry.purpose_label, entry.index_key) for entry in manifest.entries]
    if locations != ordered:
        raise MaterialBindingError("材料清单的键或次序与闭合集不符")
    for entry in manifest.entries:
        location = (entry.purpose_label, entry.index_key)
        if accepted[location] != entry.value:
            raise MaterialBindingError("材料清单的取值与审计接受值不符")
        if entry.purpose_label != "deal":
            _require_seed_octets(entry.value)


def v2_record_sort_key(label: str, index_key: tuple[str, ...]) -> tuple[int | str, ...]:
    """用途次序之后，按完整键的整数或字符串升序。"""
    fields = _V2_FIELDS[label]
    parsed: list[int | str] = [V2_TRAVERSAL.index(label)]
    for name, raw in zip(fields, index_key, strict=True):
        if name in _V2_INTEGER_FIELDS:
            parsed.append(_parse_canonical_integer(name, raw))
        else:
            parsed.append(raw)
    return tuple(parsed)


def _parsed_v2_fields(fields: tuple[str, ...], index_key: tuple[str, ...]) -> dict[str, int]:
    parsed: dict[str, int] = {}
    for name, raw in zip(fields, index_key, strict=True):
        if name in _V2_INTEGER_FIELDS:
            parsed[name] = _parse_canonical_integer(name, raw)
    return parsed


def _require_campaign_text(text: str) -> None:
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ProtocolSpecError("campaign 必须是小写 64 位十六进制")


_V2_INTEGERS: dict[str, tuple[str, ...]] = {
    "deal": ("block", "hand", "draw"),
    "non_probed": ("block", "hand", "seat", "event_index"),
    "arm_m": ("block", "hand"),
    "arm_b": ("block", "hand", "seat", "event_index"),
}
_PROJECTION_SCHEMA = "k2-public-projection-v1"
_PROJECTION_FLAGS = frozenset(
    {
        "hand_over",
        "legal.can_fold",
        "legal.can_check",
        "legal.can_call",
        "legal.is_short_all_in_call",
        "legal.can_bet",
        "legal.can_raise",
    }
)
_PROJECTION_LEGAL = (
    "legal.can_fold",
    "legal.can_check",
    "legal.can_call",
    "legal.call_amount",
    "legal.actual_call_amount",
    "legal.is_short_all_in_call",
    "legal.can_bet",
    "legal.min_bet",
    "legal.max_bet",
    "legal.can_raise",
    "legal.min_raise_to",
    "legal.max_raise_to",
)


def protocol_declares_v2_keys(protocol: RandomizationProtocolSpec) -> bool:
    """协议的用途键形是否已经是 v2。v1 四字段键不会被当成 v2。"""
    roles = {
        "deal": PurposeRole.DEAL,
        "non_probed": PurposeRole.NON_PROBED_SEED,
        "arm_m": PurposeRole.UNDER_TEST_MATERIAL,
        "arm_b": PurposeRole.BASELINE_SEED,
    }
    if tuple(purpose.label for purpose in protocol.purposes) != V2_TRAVERSAL:
        return False
    if tuple(protocol.traversal_order) != V2_TRAVERSAL:
        return False
    for purpose in protocol.purposes:
        if purpose.role is not roles[purpose.label]:
            return False
        if purpose.index_fields != _V2_FIELDS[purpose.label]:
            return False
        if purpose.integer_fields != _V2_INTEGERS[purpose.label]:
            return False
        if purpose.label == "deal":
            if (
                not isinstance(purpose.domain, ShrinkingDomain)
                or purpose.domain.initial_size != DECK_SIZE
                or purpose.bit_width != 8
                or purpose.draw_index_field != "draw"
            ):
                return False
            continue
        if (
            not isinstance(purpose.domain, FixedDomain)
            or purpose.domain.size != _DOMAIN_SIZE_2_256
            or purpose.bit_width != 256
        ):
            return False
        if purpose.label in _KAPPA_LABELS and purpose.seat_index_field != "seat":
            return False
    return True


def require_v2_schedule_anchors(
    entries: Sequence[tuple[str, tuple[str, ...]]],
    *,
    campaign: str,
    block: int,
    draw_count: int,
    num_players: int,
    probed_by_hand: Mapping[int, int],
) -> None:
    """闭合集必须盖住每个手序上的四种用途锚点。缺任一条即失败，不补键。"""
    block_text = str(block)
    deal: set[tuple[int, int]] = set()
    arm_m: set[int] = set()
    non_probed: dict[int, set[int]] = {hand: set() for hand in probed_by_hand}
    arm_b: dict[int, set[int]] = {hand: set() for hand in probed_by_hand}
    for label, index_key in entries:
        if index_key[0] != campaign or index_key[1] != block_text:
            raise ProtocolSpecError("闭合集的 campaign 或 block 与规格不符")
        hand = _parse_canonical_integer("hand", index_key[2])
        if hand not in probed_by_hand:
            raise ProtocolSpecError("闭合集含有手序计划之外的手")
        if label == "deal":
            deal.add((hand, _parse_canonical_integer("draw", index_key[3])))
        elif label == "arm_m":
            arm_m.add(hand)
        elif label == "non_probed":
            seats = non_probed[hand]
            seats.add(_parse_canonical_integer("seat", index_key[3]))
        elif label == "arm_b":
            seats = arm_b[hand]
            seats.add(_parse_canonical_integer("seat", index_key[3]))
        else:
            raise ProtocolSpecError("闭合集含有未声明的用途")
    required_deal = {
        (hand, draw)
        for hand in probed_by_hand
        for draw in range(draw_count)
    }
    if deal != required_deal:
        raise ProtocolSpecError("闭合集的发牌键与手序所需抽取不符")
    for hand, probed in probed_by_hand.items():
        if hand not in arm_m:
            raise ProtocolSpecError("闭合集缺少 arm_m")
        expected = {seat for seat in range(num_players) if seat != probed}
        if not expected <= non_probed[hand]:
            raise ProtocolSpecError("闭合集缺少 non_probed")
        if probed not in arm_b[hand]:
            raise ProtocolSpecError("闭合集缺少 arm_b")


def _require_sigma_public_text(text: str) -> None:
    if (
        len(text) < 2
        or len(text) % 2 != 0
        or any(character not in "0123456789abcdef" for character in text)
    ):
        raise ProtocolSpecError("sigma_public 必须是规范投影的 UTF-8 字节")
    raw = bytes.fromhex(text)
    if raw.hex() != text:
        raise ProtocolSpecError("sigma_public 必须是规范投影的 UTF-8 字节")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProtocolSpecError("sigma_public 必须是规范投影的 UTF-8 字节") from error
    encoded = decoded.encode("utf-8")
    if encoded.hex() != text:
        raise ProtocolSpecError("sigma_public 必须是规范投影的 UTF-8 字节")
    _require_projection_text(decoded)


def _projection_names(num_players: int, board_len: int) -> list[str]:
    names = [
        "schema",
        "street",
        "hand_over",
        "button",
        "current_seat",
        "pot",
        "n_players",
        "board_len",
    ]
    names.extend(f"board.{index}" for index in range(board_len))
    for seat in range(num_players):
        prefix = f"player.{seat}"
        names.extend(
            (
                f"{prefix}.stack",
                f"{prefix}.folded",
                f"{prefix}.all_in",
                f"{prefix}.street_bet",
                f"{prefix}.total_committed",
                f"{prefix}.has_acted_since_full_raise",
            )
        )
    names.extend(_PROJECTION_LEGAL)
    return names


def _require_projection_text(text: str) -> None:
    if not text or text.endswith("\n"):
        raise ProtocolSpecError("公开投影行格式不符")
    rows: list[tuple[str, str]] = []
    for line in text.split("\n"):
        if line.count("=") != 1:
            raise ProtocolSpecError("公开投影行格式不符")
        name, value = line.split("=", 1)
        rows.append((name, value))
    names = [name for name, _value in rows]
    if len(set(names)) != len(names):
        raise ProtocolSpecError("公开投影字段重复")
    values = dict(rows)
    if values.get("schema") != _PROJECTION_SCHEMA:
        raise ProtocolSpecError("公开投影的模式标识不符")
    if "n_players" not in values or "board_len" not in values or "street" not in values:
        raise ProtocolSpecError("公开投影字段与规范串不符")
    _require_projection_flag("street", values["street"], low=0, high=4)
    num_players = _require_projection_integer("n_players", values["n_players"], low=2, high=23)
    board_len = _require_projection_integer("board_len", values["board_len"], low=0, high=52)
    if names != _projection_names(num_players, board_len):
        raise ProtocolSpecError("公开投影字段与规范串不符")
    for name, value in rows:
        if name == "schema":
            continue
        if name == "street":
            continue
        if name.startswith("board."):
            _require_projection_card(value)
        elif name in _PROJECTION_FLAGS or name.endswith(
            (".folded", ".all_in", ".has_acted_since_full_raise")
        ):
            _require_projection_flag(name, value)
        else:
            _require_projection_integer(name, value, low=0)


def _require_projection_integer(
    name: str, raw: str, *, low: int, high: int | None = None
) -> int:
    if not raw.isdigit() or (len(raw) > 1 and raw.startswith("0")):
        raise ProtocolSpecError(f"公开投影的整数格式不符：{name}")
    value = int(raw)
    if value < low or (high is not None and value > high):
        raise ProtocolSpecError(f"公开投影的整数超出范围：{name}")
    return value


def _require_projection_flag(
    name: str, raw: str, *, low: int = 0, high: int = 1
) -> None:
    if raw not in {str(item) for item in range(low, high + 1)}:
        raise ProtocolSpecError(f"公开投影的标志不符：{name}")


def _require_projection_card(raw: str) -> None:
    if len(raw) != 2 or raw[0] not in "23456789TJQKA" or raw[1] not in "cdhs":
        raise ProtocolSpecError("公开投影的牌面不符")


def _require_v2_ranges(
    label: str,
    parsed: Mapping[str, int],
    *,
    probed_by_hand: Mapping[int, int],
    num_players: int,
) -> None:
    hand = parsed["hand"]
    if hand < 1:
        raise ProtocolSpecError("hand 必须是正整数")
    if hand not in probed_by_hand:
        raise ProtocolSpecError("键上的 hand 不在已登记的手序中")
    probed = probed_by_hand[hand]
    if isinstance(probed, bool) or not isinstance(probed, int) or not 0 <= probed < num_players:
        raise ProtocolSpecError("被测座位超出人数范围")
    if label == "deal":
        draw = parsed["draw"]
        if draw >= DECK_SIZE:
            raise ProtocolSpecError("发牌抽取次序超出牌堆")
        return
    if label not in _KAPPA_LABELS:
        return
    seat = parsed["seat"]
    if label == "non_probed" and (seat == probed or not 0 <= seat < num_players):
        raise ProtocolSpecError("non_probed 的座位必须是该手的非被测座位")
    if label == "arm_b" and seat != probed:
        raise ProtocolSpecError("arm_b 的座位必须是该手的被测座位")


def _require_seed_octets(seed: int) -> bytes:
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < _DOMAIN_SIZE_2_256:
        raise ProtocolSpecError("seed 必须落在 [0, 2^256)")
    octets = seed.to_bytes(32, "big")
    if int.from_bytes(octets, "big") != seed:
        raise ProtocolSpecError("seed 的 32 字节大端与整数不一致")
    return octets


def _require_v2_read_sequence(
    reads: Sequence[ReadRecord],
    ordered: Sequence[tuple[str, tuple[str, ...]]],
    transcript: bytes,
) -> dict[tuple[str, tuple[str, ...]], int]:
    if [record.read_index for record in reads] != list(range(len(reads))):
        raise ProtocolAuditError("逐读取记录的序号必须从零起连续")
    accepted: dict[tuple[str, tuple[str, ...]], int] = {}
    cursor = 0
    accepted_current = False
    offset = 0
    for record in reads:
        location = (record.purpose_label, record.index_key)
        if cursor < len(ordered) and location == ordered[cursor]:
            pass
        elif (
            accepted_current
            and cursor + 1 < len(ordered)
            and location == ordered[cursor + 1]
        ):
            cursor += 1
            accepted_current = False
        else:
            raise ProtocolAuditError("逐读取记录偏离已闭合键集的规范次序，或出现集外键")
        width = 8 if record.purpose_label == "deal" else 256
        if record.bit_width != width:
            raise ProtocolAuditError("读取位宽与用途不符")
        nbytes = width // 8
        if record.raw_offset != offset or offset + nbytes > len(transcript):
            raise ProtocolAuditError("读取偏移与转录不符")
        chunk = transcript[offset : offset + nbytes]
        if int.from_bytes(chunk, "big") != record.raw_value:
            raise ProtocolAuditError("转录字节与原始值不符")
        offset += nbytes
        if record.purpose_label == "deal":
            draw = _parse_canonical_integer("draw", record.index_key[3])
            domain = DECK_SIZE - draw
        else:
            domain = _DOMAIN_SIZE_2_256
        expected = resolve_read(record.raw_value, bit_width=width, domain_size=domain)
        if record.accepted:
            if expected is None or record.output != expected or accepted_current:
                raise ProtocolAuditError("接受判定与拒绝规则不符")
            accepted_current = True
            accepted[location] = record.output
        elif expected is not None or record.output is not None or accepted_current:
            raise ProtocolAuditError("拒绝判定与拒绝规则不符")
    if offset != len(transcript):
        raise ProtocolAuditError("转录尚有未入账的字节")
    if not ordered:
        if reads:
            raise ProtocolAuditError("空键集不得有读取记录")
        return accepted
    if cursor != len(ordered) - 1 or not accepted_current:
        raise ProtocolAuditError("闭合集中仍有键未被接受")
    if set(accepted) != set(ordered):
        raise ProtocolAuditError("审计接受键与闭合集不相等")
    return accepted


def _require_draw_order_matches(
    protocol: RandomizationProtocolSpec, bundle: Sequence[HandMaterials]
) -> None:
    """确认每手发牌材料按其抽取次序字段严格递增给出。"""
    purpose = protocol.purpose_for_role(PurposeRole.DEAL)
    for hand in bundle:
        draws = [
            purpose.draw_index_of(entry.index_key)
            for entry in hand.entries_for(purpose.label)
        ]
        if draws != sorted(draws) or len(set(draws)) != len(draws):
            raise MaterialBindingError("每手发牌材料必须按抽取次序严格递增给出")
