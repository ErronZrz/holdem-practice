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
            if len(set(entry_names)) != len(entry_names):
                raise SpecIncompleteError(f"同一类别内的条目名不得重复：{name}")
        if self.reference_snapshot != reference_snapshot():
            raise SpecIncompleteError("参考与评估版本快照必须取运行时的只读值")
        return self

    def entries_for(self, category: str) -> tuple[CoverageEntry, ...]:
        """按类别取覆盖条目；类别未声明即失败。"""
        for name, entries in self.categories:
            if name == category:
                return entries
        raise SpecIncompleteError(f"覆盖清单不含该类别：{category!r}")


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
