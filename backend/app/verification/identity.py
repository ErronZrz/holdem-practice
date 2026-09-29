"""身份构造口径：两侧映射由调用方显式给出，不做全局登记，也不做隐式选择。

设计目的：
- 两侧构造映射以**显式、不可变、可规范编码的输入**形式传递：规格里的规范标识必须与之逐字
  相同，别名、类名、模块路径与未冻结的默认值都不构成身份选择依据，进程内也不存在可供隐式
  选择的登记表；
- 构造路径与被测身份的创建解耦：本模块只描述口径与校验材料，何时创建身份不在此处；
- 单一基线身份的构造口径受限：接口、公开摘要与座位范围三项都必须是最小形态，口径因此不
  可能声明出与构造计划相矛盾的语义；
- 主键材料必须恰好是 32 字节的字节串，类型或长度不符即硬失败；
- 本模块只描述口径与校验材料，不构造任何策略实例。
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from .errors import IdentityMappingError, MaterialKeyError, SpecIncompleteError

# 主键材料的固定字节长度：与构造器的直接注入分支一致。
MATERIAL_KEY_BYTES = 32
# 主键材料的取值上界：32 字节可表示的非负整数范围。
MATERIAL_KEY_UPPER_BOUND = 1 << (8 * MATERIAL_KEY_BYTES)


class ConstructionInterface(StrEnum):
    """构造接口：本包只支持这两种显式接口。"""

    # 以恰好 32 字节的主键经构造器的直接注入分支构造。
    MATERIAL_KEY = "material-key"
    # 经受控注册表以非空整数种子构造。
    REGISTRY_SEED = "registry-seed"


class SeatScope(StrEnum):
    """座位集合口径：决定策略实例绑定哪些座位，从而决定这些座位的风格分配。"""

    PROBED_SEAT_ONLY = "probed-seat-only"
    ALL_SEATS = "all-seats"


class ConstructionMapping(BaseModel):
    """一份显式身份构造映射：声明规范标识、接口与输入口径。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    interface: ConstructionInterface
    # 是否依赖公开摘要输入；为真时座位集合口径必须显式给出。
    requires_public_summary: bool
    seat_scope: SeatScope | None = None

    @model_validator(mode="after")
    def _require_well_formed(self) -> ConstructionMapping:
        if not self.identifier.strip():
            raise SpecIncompleteError("身份规范标识不能为空")
        if self.requires_public_summary and self.seat_scope is None:
            raise SpecIncompleteError("依赖公开摘要的身份必须显式给出座位集合口径")
        if not self.requires_public_summary and self.seat_scope is not None:
            raise SpecIncompleteError("不依赖公开摘要的身份不应声明座位集合口径")
        return self

    def canonical_payload(self) -> dict[str, object]:
        """规范编码：字段固定，供构造口径的内容摘要重算。"""
        return {
            "identifier": self.identifier,
            "interface": self.interface.value,
            "requires_public_summary": self.requires_public_summary,
            "seat_scope": None if self.seat_scope is None else self.seat_scope.value,
        }


def require_baseline_limits(mapping: ConstructionMapping) -> ConstructionMapping:
    """单一基线身份的构造口径限制：接口、公开摘要与座位范围三项都必须是最小形态。

    三项同时成立才允许继续：以受控注册表种子接口构造、不依赖公开摘要输入、不声明座位集合
    口径。因此基线侧的构造计划可以由该口径无损导出，不会出现「口径声明的语义」与
    「计划写死的语义」互相矛盾的情形。
    """
    if mapping.interface is not ConstructionInterface.REGISTRY_SEED:
        raise IdentityMappingError("基线一侧必须以受控注册表种子接口构造")
    if mapping.requires_public_summary:
        raise IdentityMappingError("基线一侧不得依赖公开摘要输入")
    if mapping.seat_scope is not None:
        raise IdentityMappingError("基线一侧不得声明座位集合口径")
    return mapping


class ConstructionCaliber(BaseModel):
    """两侧身份的构造口径：基线侧与候选侧的映射都由调用方显式给出。

    该对象是身份相关校验的唯一事实源：它被冻结输入主链直接消费，其内容进入冻结清单的一项
    内容摘要，并由它决定逐手逐臂逐座位的构造计划。本类型不登记、不创建也不冻结任何身份。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline: ConstructionMapping
    under_test: ConstructionMapping

    @model_validator(mode="after")
    def _require_well_formed(self) -> ConstructionCaliber:
        if self.baseline.identifier == self.under_test.identifier:
            raise IdentityMappingError("两侧构造口径的规范标识必须不同")
        require_baseline_limits(self.baseline)
        return self

    def canonical_payload(self) -> dict[str, object]:
        """规范编码：两侧映射按固定字段展开，供内容摘要重算。"""
        return {
            "baseline": self.baseline.canonical_payload(),
            "under_test": self.under_test.canonical_payload(),
        }


def require_identifier_match(identifier: str, mapping: ConstructionMapping) -> None:
    """规范标识必须与显式构造口径给出的标识完全相同；不一致即失败，无回退路径。"""
    if mapping.identifier != identifier:
        raise IdentityMappingError(
            f"构造口径的规范标识与规格不一致：{mapping.identifier!r} 与 {identifier!r}"
        )


def require_material_key(value: object) -> bytes:
    """校验主键材料：必须恰好是 32 字节的字节串。"""
    if not isinstance(value, bytes):
        raise MaterialKeyError("主键材料必须是字节串")
    if len(value) != MATERIAL_KEY_BYTES:
        raise MaterialKeyError(f"主键材料必须恰好 {MATERIAL_KEY_BYTES} 字节，实际 {len(value)}")
    return value


def material_key_from_integer(value: int) -> bytes:
    """把协议给出的非负整数还原为 32 字节主键；超出范围即失败。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise MaterialKeyError("主键材料的整数表示必须是整数")
    if not 0 <= value < MATERIAL_KEY_UPPER_BOUND:
        raise MaterialKeyError("主键材料的整数表示超出 32 字节可表示范围")
    return require_material_key(value.to_bytes(MATERIAL_KEY_BYTES, "big"))


def require_explicit_seed(value: object) -> int:
    """校验种子材料：必须是非空整数，不接受空值或布尔值。"""
    if value is None:
        raise IdentityMappingError("种子材料不得为空")
    if isinstance(value, bool) or not isinstance(value, int):
        raise IdentityMappingError("种子材料必须是整数")
    return value
