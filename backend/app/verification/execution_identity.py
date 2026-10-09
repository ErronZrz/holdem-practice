"""验证执行身份的覆盖清单：六类结构必填，参考与评估版本只读记录。

设计目的：
- 覆盖清单按固定类别组织：缺任一类别或类别内条目为空即失败，不靠默认值补齐；
- 实例化口径类别的取值不是自由文本：其规范条目由当前显式构造口径、基线身份的有效执行口径
  与重算的构造计划得出，绑定校验时须与之逐项一致（比较在实例化口径模块内实现，由冻结输入
  主链调用）；该类别承载的是当前执行身份的追溯字段，不是身份创建或冻结；
- 参考与评估版本只在运行时只读取快照，作为追溯关联字段，不反向约束复盘参考契约。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, model_validator

from app.analysis.reference_identity import reference_identity

from .digests import DIGEST_ALGORITHMS, content_digest
from .errors import SpecIncompleteError
from .identity import ConstructionInterface, SeatScope

_DIGEST_ALGORITHM = "sha256"
_RUNNER_ENTRIES: tuple[str, ...] = (
    "runner-flow-version",
    "runner-flow-digest",
    "runner-code-manifest-digest",
)
_PROTOCOL_ENTRIES: tuple[str, ...] = (
    "randomization-protocol-version",
    "randomization-protocol-digest",
    "source-interface-id",
    "environment-record",
    "supplied-materials-digest",
    "material-manifest-digest",
    "audit-transcript-digest",
    "audit-read-record-digest",
    "audit-commitment-digest",
    "generator-code-digest",
)
_CALIBER_ENTRIES: tuple[str, ...] = (
    "baseline-identifier",
    "under-test-identifier",
    "baseline-interface",
    "under-test-interface",
    "baseline-requires-public-summary",
    "under-test-requires-public-summary",
    "baseline-seat-scope",
    "under-test-seat-scope",
    "baseline-registry-location",
    "baseline-entry-point",
    "baseline-parameter-layout",
    "baseline-effective-seed",
    "baseline-effective-samples",
    "baseline-effective-bluff-freq",
    "baseline-entry-code-digest",
    "construction-plan-digest",
)
_PRECHECK_ENTRIES: tuple[str, ...] = (
    "injection-precheck-version",
    "injection-precheck-rules-digest",
)
_MAPPING_ENTRIES: tuple[str, ...] = (
    "input-mapping-version",
    "campaign-configuration-digest",
    "deal-mapping-digest",
    "purpose-index-mapping-digest",
    "schedule-digest",
    "public-summary-mapping-digest",
)
_ENGINE_ENTRIES: tuple[str, ...] = (
    "engine-code-manifest-digest",
    "baseline-strategy-code-manifest-digest",
    "under-test-strategy-code-manifest-digest",
    "verification-code-manifest-digest",
)
_CLOSED_ENTRIES: dict[str, tuple[str, ...]] = {
    "runner": _RUNNER_ENTRIES,
    "randomization-protocol": _PROTOCOL_ENTRIES,
    "instantiation-caliber": _CALIBER_ENTRIES,
    "injection-precheck": _PRECHECK_ENTRIES,
    "input-mapping": _MAPPING_ENTRIES,
    "engine-and-strategy-code": _ENGINE_ENTRIES,
}
_FIXED_TEXT: dict[str, str] = {
    "baseline-identifier": "heuristic@1",
    "under-test-identifier": "mixed-local@9",
    "baseline-registry-location": "app.strategy.registry.create_strategy",
    "baseline-entry-point": "app.strategy.heuristic.HeuristicStrategy.__init__",
    "source-interface-id": "python-os-urandom@1",
    "environment-record": "local-single-process-no-parallel@1",
    "baseline-effective-seed": "per-hand-arm_b-material",
}
_VERSION_ENTRIES: frozenset[str] = frozenset(
    {
        "runner-flow-version",
        "randomization-protocol-version",
        "injection-precheck-version",
        "input-mapping-version",
    }
)
_INTERFACE_ENTRIES: frozenset[str] = frozenset(
    {"baseline-interface", "under-test-interface"}
)
_BOOL_ENTRIES: frozenset[str] = frozenset(
    {"baseline-requires-public-summary", "under-test-requires-public-summary"}
)
_SCOPE_ENTRIES: frozenset[str] = frozenset({"baseline-seat-scope", "under-test-seat-scope"})
_HEX_ENTRIES: frozenset[str] = frozenset(
    {
        "runner-code-manifest-digest",
        "randomization-protocol-digest",
        "supplied-materials-digest",
        "material-manifest-digest",
        "audit-transcript-digest",
        "audit-read-record-digest",
        "audit-commitment-digest",
        "generator-code-digest",
        "campaign-configuration-digest",
        "schedule-digest",
        "baseline-entry-code-digest",
        "construction-plan-digest",
        *_ENGINE_ENTRIES,
    }
)

# 实例化口径类别：其条目须与显式构造口径及重算的构造计划逐项一致。
INSTANTIATION_CALIBER_CATEGORY = "instantiation-caliber"

# 覆盖类别：顺序即清单顺序，静态检查、记录与测试都读这张表。
EXECUTION_IDENTITY_CATEGORIES: tuple[str, ...] = (
    "runner",
    "randomization-protocol",
    INSTANTIATION_CALIBER_CATEGORY,
    "injection-precheck",
    "input-mapping",
    "engine-and-strategy-code",
)


class CoverageEntry(BaseModel):
    """覆盖清单中的一个条目：条目名与其取值的表示。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: str

    @model_validator(mode="after")
    def _require_well_formed(self) -> CoverageEntry:
        if not self.name.strip():
            raise SpecIncompleteError("覆盖条目的名称不能为空")
        if not self.value.strip():
            raise SpecIncompleteError("覆盖条目的取值不能为空")
        return self


class ExecutionIdentityRecord(BaseModel):
    """验证执行身份的覆盖清单与只读版本快照。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    categories: tuple[tuple[str, tuple[CoverageEntry, ...]], ...]
    reference_snapshot: Mapping[str, object]

    @model_validator(mode="after")
    def _require_complete(self) -> ExecutionIdentityRecord:
        names = [name for name, _ in self.categories]
        if names != list(EXECUTION_IDENTITY_CATEGORIES):
            raise SpecIncompleteError("覆盖清单必须按固定类别齐备，且次序一致")
        for name, entries in self.categories:
            if not entries:
                raise SpecIncompleteError(f"覆盖类别不得为空：{name}")
            entry_names = [entry.name for entry in entries]
            if entry_names != list(_CLOSED_ENTRIES[name]):
                raise SpecIncompleteError(f"覆盖类别的条目名或次序不正确：{name}")
            for entry in entries:
                _require_entry_value(entry.name, entry.value)
        if self.reference_snapshot != reference_snapshot():
            raise SpecIncompleteError("参考与评估版本快照必须取运行时的只读值")
        return self

    def entries_for(self, category: str) -> tuple[CoverageEntry, ...]:
        """按类别取覆盖条目；类别未声明即失败。"""
        for name, entries in self.categories:
            if name == category:
                return entries
        raise SpecIncompleteError(f"覆盖清单不含该类别：{category!r}")


def _is_lower_hex64(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _is_canonical_integer(value: str) -> bool:
    return value.isdigit() and not (value.startswith("0") and value != "0")


def _require_visible_ascii(value: str) -> None:
    if not value or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
        raise SpecIncompleteError("普通文本必须是非空的可见 ASCII")


def _determined_digest(name: str) -> str:
    """参数已完全确定的摘要。延迟导入，避免覆盖清单模块与运行器互相加载。"""
    if name == "runner-flow-digest":
        from .runner import runner_flow_digest

        return runner_flow_digest(_DIGEST_ALGORITHM)
    if name == "injection-precheck-rules-digest":
        from .guards import injection_precheck_rules_digest

        return injection_precheck_rules_digest(_DIGEST_ALGORITHM)
    if name == "deal-mapping-digest":
        from .deal import deal_mapping_digest

        return deal_mapping_digest(algorithm=_DIGEST_ALGORITHM)
    if name == "purpose-index-mapping-digest":
        from .protocol import purpose_index_mapping_digest

        return purpose_index_mapping_digest(algorithm=_DIGEST_ALGORITHM)
    if name == "public-summary-mapping-digest":
        from .instantiation import public_summary_mapping_digest

        return public_summary_mapping_digest(algorithm=_DIGEST_ALGORITHM)
    raise SpecIncompleteError(f"没有可重算的摘要：{name}")


def _require_entry_value(name: str, value: str) -> None:
    """按条目种类核对渲染：固定文本、版本、布尔、枚举、整数、摘要与两个可重算摘要。"""
    if name in _FIXED_TEXT:
        _require_visible_ascii(value)
        if value != _FIXED_TEXT[name]:
            raise SpecIncompleteError(f"固定文本与锁定值不符：{name}")
        return
    if name in _VERSION_ENTRIES:
        if value != "1":
            raise SpecIncompleteError(f"版本条目的取值必须是 1：{name}")
        return
    if name == "baseline-parameter-layout":
        if value != '["self","seed","samples","bluff_freq"]':
            raise SpecIncompleteError("参数布局必须是锁定的紧凑 JSON 数组")
        return
    if name == "baseline-effective-bluff-freq":
        if value != "0.1":
            raise SpecIncompleteError("诈唬频率文本必须是 0.1")
        return
    if name == "baseline-effective-samples":
        if not _is_canonical_integer(value):
            raise SpecIncompleteError("采样数必须是无前导零的十进制")
        return
    if name in _BOOL_ENTRIES:
        if value not in {"true", "false"}:
            raise SpecIncompleteError(f"布尔条目只能是 true 或 false：{name}")
        return
    if name in _INTERFACE_ENTRIES:
        if value not in {item.value for item in ConstructionInterface}:
            raise SpecIncompleteError(f"接口条目必须是规范枚举值：{name}")
        return
    if name in _SCOPE_ENTRIES:
        allowed = {"none", *(item.value for item in SeatScope)}
        if value not in allowed:
            raise SpecIncompleteError(f"座位口径必须是 none 或规范枚举值：{name}")
        return
    if name in {"runner-flow-digest", "injection-precheck-rules-digest"} or name in {
        "deal-mapping-digest",
        "purpose-index-mapping-digest",
        "public-summary-mapping-digest",
    }:
        if value != _determined_digest(name):
            raise SpecIncompleteError(f"摘要与封闭载荷的重算结果不符：{name}")
        return
    if name in _HEX_ENTRIES:
        # 构造记录时只核对字符形式。与当前规格、材料、审计和显式清单的逐项绑定在冻结输入主链完成。
        if not _is_lower_hex64(value):
            raise SpecIncompleteError(f"摘要必须是小写 64 位十六进制：{name}")
        return
    raise SpecIncompleteError(f"未声明的覆盖条目：{name}")


def reference_snapshot() -> Mapping[str, object]:
    """只读记录运行时的参考与评估版本，仅用于追溯关联。"""
    return dict(reference_identity())


def execution_identity_digest(record: ExecutionIdentityRecord, *, algorithm: str) -> str:
    """由覆盖清单内容重算摘要：清单内容不同即摘要不同。"""
    if algorithm not in DIGEST_ALGORITHMS:
        raise SpecIncompleteError(f"摘要算法未实现：{algorithm!r}")
    return content_digest(record.model_dump(mode="json"), algorithm=algorithm)


def build_execution_identity_record(
    categories: Mapping[str, Sequence[tuple[str, str]]],
) -> ExecutionIdentityRecord:
    """按调用方给出的条目构造覆盖清单；类别缺项或出现未声明类别即失败。"""
    separator = ", "
    missing = [name for name in EXECUTION_IDENTITY_CATEGORIES if name not in categories]
    if missing:
        joined = separator.join(missing)
        raise SpecIncompleteError(f"覆盖清单缺少类别：{joined}")
    extra = [name for name in categories if name not in EXECUTION_IDENTITY_CATEGORIES]
    if extra:
        joined = separator.join(extra)
        raise SpecIncompleteError(f"覆盖清单出现未声明的类别：{joined}")
    ordered = tuple(
        (
            name,
            tuple(
                CoverageEntry(name=entry_name, value=value)
                for entry_name, value in categories[name]
            ),
        )
        for name in EXECUTION_IDENTITY_CATEGORIES
    )
    return ExecutionIdentityRecord(categories=ordered, reference_snapshot=reference_snapshot())
