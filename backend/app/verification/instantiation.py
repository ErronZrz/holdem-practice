"""实例化口径与材料校验：显式构造口径、逐座位构造计划，以及材料与规格的一致性。

设计目的：
- 两侧身份的构造口径由调用方**显式给出**（不可变的构造口径对象），本模块不从进程内登记表查表；
- 每手每臂每座位的构造口径以**计划**形式描述：身份标识、构造接口、座位集合口径、所需输入口径
  与对应材料，供核验逐项阅读；本模块不构造任何策略实例；
- 基线一侧的有效执行口径（入口位置、参数布局、默认取值与代码载荷摘要）**从策略层代码只读读取**，
  不由调用方声明，也不调用受控注册表的任何函数；
- 构造口径的内容、基线执行口径与由前者唯一确定的构造计划各有规范编码与内容摘要，供冻结输入与
  执行身份绑定；
- 材料完整性、座位覆盖、取值域与协议声明在运行之前一次性校验，失败即终止；
- 单一基线身份：两臂全部非被测座位与基线臂被测座位共用同一规范标识与整数种子材料。

局限（写死）：基线入口的代码对象载荷摘要随解释器版本与加载实现变化，只是当前执行身份的
追溯绑定，**不是**代码身份冻结，也不构成来源认证；受控注册表一侧只记录位置，不计算摘要。
"""

from __future__ import annotations

import types
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.strategy.heuristic import HeuristicStrategy
from app.strategy.mixed_strategy import seat_style_map

from .config import BASELINE_IDENTIFIER, DomainRunSpec, HandPlan
from .digests import content_digest
from .errors import IdentityMappingError, SpecIncompleteError
from .execution_identity import INSTANTIATION_CALIBER_CATEGORY, ExecutionIdentityRecord
from .identity import (
    ConstructionCaliber,
    ConstructionInterface,
    ConstructionMapping,
    SeatScope,
    material_key_from_integer,
    require_baseline_limits,
    require_explicit_seed,
    require_identifier_match,
)
from .materials import HandMaterials, MaterialEntry, bundle_payload
from .protocol import PurposeRole, RandomizationProtocolSpec

# 基线身份的受控注册表构造位置：只作位置绑定与记录，本包不导入也不调用该模块。
BASELINE_REGISTRY_LOCATION = "app.strategy.registry.create_strategy"
# 基线身份实现中承载有效执行口径的入口：参数布局与默认取值的定义处。
BASELINE_ENTRY_POINT = "HeuristicStrategy.__init__"
# 基线执行口径必须携带的位置默认值：缺少任一项即失败，避免上游改动被静默记成空值。
BASELINE_REQUIRED_DEFAULTS: tuple[str, ...] = ("seed", "samples", "bluff_freq")


class Arm(StrEnum):
    """配对比较的两条臂：候选身份一臂与基线一臂。"""

    UNDER_TEST = "under-test"
    BASELINE = "baseline"


class SeatRole(StrEnum):
    """座位在本手里的角色。"""

    NON_PROBED = "non-probed"
    PROBED_UNDER_TEST = "probed-under-test"
    PROBED_BASELINE = "probed-baseline"


def require_registry_seed_mapping(mapping: ConstructionMapping) -> ConstructionMapping:
    """基线一侧必须以受控注册表的种子接口构造；其它接口即失败。"""
    if mapping.interface is not ConstructionInterface.REGISTRY_SEED:
        raise IdentityMappingError("基线一侧必须以受控注册表种子接口构造")
    return mapping


def require_caliber_matches_spec(
    spec: DomainRunSpec, caliber: ConstructionCaliber
) -> None:
    """规格里的身份标识必须与显式构造口径逐字相同，且基线一侧受三项硬限制。

    比较只做规范标识的精确相等：别名、类名与进程内登记表都不参与身份选择。
    """
    if caliber.baseline.identifier != BASELINE_IDENTIFIER:
        raise IdentityMappingError("构造口径的基线标识不是单一基线身份")
    require_identifier_match(spec.baseline_identifier, caliber.baseline)
    require_identifier_match(spec.under_test_identifier, caliber.under_test)
    require_baseline_limits(caliber.baseline)


def require_material_format(mapping: ConstructionMapping, value: int) -> None:
    """按构造接口校验材料格式：主键接口走 32 字节还原，种子接口走非空整数校验。"""
    if mapping.interface is ConstructionInterface.MATERIAL_KEY:
        material_key_from_integer(value)
        return
    require_explicit_seed(value)


def require_construction_calibers(
    spec: DomainRunSpec, caliber: ConstructionCaliber, bundle: Sequence[HandMaterials]
) -> None:
    """身份相关硬校验，全部纳入冻结输入主链。

    内容：核对规格标识与显式构造口径逐字一致并限定基线接口、按接口校验逐条材料格式，
    并为每个臂、每一手构造座位计划（计划同时校验材料与座位的对应关系）。
    """
    require_caliber_matches_spec(spec, caliber)
    protocol = spec.protocol
    baseline = require_registry_seed_mapping(caliber.baseline)
    under_test = caliber.under_test
    for plan, materials in zip(spec.schedule, bundle, strict=True):
        require_material_format(
            under_test,
            _single_material(materials, protocol, PurposeRole.UNDER_TEST_MATERIAL).value,
        )
        require_material_format(
            baseline,
            _single_material(materials, protocol, PurposeRole.BASELINE_SEED).value,
        )
        for seat in range(spec.num_players):
            if seat == plan.probed_seat:
                continue
            require_material_format(
                baseline, _material_for_seat(materials, protocol, seat).value
            )
        for arm in (Arm.UNDER_TEST, Arm.BASELINE):
            build_arm_construction_plan(spec, caliber, arm, plan, materials)


def scope_seats(scope: SeatScope, *, num_players: int, probed_seat: int) -> tuple[int, ...]:
    """按座位集合口径给出实际座位集合。"""
    if scope is SeatScope.PROBED_SEAT_ONLY:
        return (probed_seat,)
    return tuple(range(num_players))


def probed_seat_style(scope: SeatScope, *, num_players: int, probed_seat: int) -> str:
    """给出该口径下被测座位实际得到的风格名，供记录实例化口径。"""
    seats = scope_seats(scope, num_players=num_players, probed_seat=probed_seat)
    return seat_style_map(seats)[probed_seat].value


def materials_digest(bundle: Sequence[HandMaterials], *, algorithm: str) -> str:
    """由材料束内容重算摘要：材料内容不同即摘要不同。"""
    return content_digest(bundle_payload(bundle), algorithm=algorithm)


def _single_material(
    materials: HandMaterials, protocol: RandomizationProtocolSpec, role: PurposeRole
) -> MaterialEntry:
    """取该用途角色在本手的唯一一条材料；数量不符即失败。"""
    purpose = protocol.purpose_for_role(role)
    entries = materials.entries_for(purpose.label)
    if len(entries) != 1:
        raise SpecIncompleteError(f"该用途每手必须恰好一条材料：{role.value}")
    return entries[0]


def _material_for_seat(
    materials: HandMaterials, protocol: RandomizationProtocolSpec, seat: int
) -> MaterialEntry:
    """取某个非被测座位的材料；缺该座位即失败。"""
    purpose = protocol.purpose_for_role(PurposeRole.NON_PROBED_SEED)
    for entry in materials.entries_for(purpose.label):
        if purpose.seat_index_of(entry.index_key) == seat:
            return entry
    raise SpecIncompleteError(f"座位 {seat} 缺少非被测材料")


def require_materials(spec: DomainRunSpec, bundle: Sequence[HandMaterials]) -> None:
    """校验材料束与规格一致：手数、逐手完整性、座位覆盖、取值域与协议声明。"""
    if len(bundle) != len(spec.schedule):
        raise SpecIncompleteError("材料束必须与手序计划一一对应")
    protocol = spec.protocol
    declared = {purpose.label for purpose in protocol.purposes}
    required_draws = spec.deal.draw_count(spec.num_players)
    for plan, materials in zip(spec.schedule, bundle, strict=True):
        if materials.hand_ordinal != plan.hand_ordinal:
            raise SpecIncompleteError("材料束的块内手序必须与手序计划一致")
        for entry in materials.entries:
            if entry.purpose_label not in declared:
                raise SpecIncompleteError("材料使用了协议未声明的用途标签")
        expected_seats = [
            seat for seat in range(spec.num_players) if seat != plan.probed_seat
        ]
        for purpose in protocol.purposes:
            entries = materials.entries_for(purpose.label)
            for entry in entries:
                if len(entry.index_key) != len(purpose.index_fields):
                    raise SpecIncompleteError("材料的索引取值数与索引字段不符")
            if purpose.role is PurposeRole.DEAL:
                if len(entries) != required_draws:
                    raise SpecIncompleteError(f"每手发牌材料的条数必须为 {required_draws}")
                draws = []
                for index, entry in enumerate(entries):
                    draws.append(purpose.draw_index_of(entry.index_key))
                    if not 0 <= entry.value < purpose.domain.domain_size(index):
                        raise SpecIncompleteError("发牌材料的取值超出该次抽取的输出域")
                if draws != list(range(required_draws)):
                    raise SpecIncompleteError("发牌材料的抽取次序必须从零起连续")
                continue
            if purpose.role is PurposeRole.NON_PROBED_SEED:
                if len(entries) != len(expected_seats):
                    raise SpecIncompleteError("非被测材料必须逐一覆盖非被测座位")
                seats = sorted(
                    purpose.seat_index_of(entry.index_key) for entry in entries
                )
                if seats != expected_seats:
                    raise SpecIncompleteError("非被测材料必须恰好覆盖除被测座位外的全部座位")
                for entry in entries:
                    if not 0 <= entry.value < purpose.domain.domain_size(0):
                        raise SpecIncompleteError("材料取值超出该用途的输出域")
                continue
            if len(entries) != 1:
                raise SpecIncompleteError(f"该用途每手必须恰好一条材料：{purpose.role.value}")
            if not 0 <= entries[0].value < purpose.domain.domain_size(0):
                raise SpecIncompleteError(f"材料取值超出该用途的输出域：{purpose.role.value}")


@dataclass(frozen=True)
class SeatConstructionEntry:
    """一个座位在本手本臂的构造口径：身份、接口、输入口径与该座位的材料。"""

    seat: int
    role: SeatRole
    identifier: str
    interface: ConstructionInterface
    requires_public_summary: bool
    seat_scope: SeatScope | None
    material: MaterialEntry


@dataclass(frozen=True)
class ArmConstructionPlan:
    """一个臂在本手的构造计划：逐座位口径与摘要输入口径。"""

    arm: Arm
    entries: tuple[SeatConstructionEntry, ...]
    # 需要公开摘要输入的座位，按升序给出。
    summary_seats: tuple[int, ...] = ()
    # 摘要中的座位集合；不需要摘要时为空元组。
    summary_scope: tuple[int, ...] = ()
    # 依赖公开摘要时被测座位实际得到的风格名。
    probed_seat_style: str | None = None

    def entry_for(self, seat: int) -> SeatConstructionEntry:
        """按座位取构造口径；不存在即失败。"""
        for entry in self.entries:
            if entry.seat == seat:
                return entry
        raise SpecIncompleteError(f"构造计划不含该座位：{seat}")


def build_arm_construction_plan(
    spec: DomainRunSpec,
    caliber: ConstructionCaliber,
    arm: Arm,
    plan: HandPlan,
    materials: HandMaterials,
) -> ArmConstructionPlan:
    """按显式构造口径给出一个臂在本手的逐座位构造计划。

    两侧的全部非被测座位共用基线标识与非被测材料；被测座位在基线一臂用基线标识与基线材料，
    在候选一臂用候选侧的构造映射与其材料。本函数不构造任何实例。
    """
    require_caliber_matches_spec(spec, caliber)
    protocol = spec.protocol
    baseline = require_registry_seed_mapping(caliber.baseline)
    under_test = caliber.under_test
    entries: list[SeatConstructionEntry] = []
    summary_seats: list[int] = []
    summary_scope: tuple[int, ...] = ()
    style: str | None = None
    for seat in range(spec.num_players):
        if seat != plan.probed_seat:
            entries.append(
                SeatConstructionEntry(
                    seat=seat,
                    role=SeatRole.NON_PROBED,
                    identifier=baseline.identifier,
                    interface=baseline.interface,
                    requires_public_summary=baseline.requires_public_summary,
                    seat_scope=baseline.seat_scope,
                    material=_material_for_seat(materials, protocol, seat),
                )
            )
            continue
        if arm is Arm.BASELINE:
            entries.append(
                SeatConstructionEntry(
                    seat=seat,
                    role=SeatRole.PROBED_BASELINE,
                    identifier=baseline.identifier,
                    interface=baseline.interface,
                    requires_public_summary=baseline.requires_public_summary,
                    seat_scope=baseline.seat_scope,
                    material=_single_material(materials, protocol, PurposeRole.BASELINE_SEED),
                )
            )
            continue
        scope: SeatScope | None = None
        if under_test.requires_public_summary:
            if under_test.seat_scope is None:
                raise IdentityMappingError("依赖公开摘要的身份必须给出座位集合口径")
            scope = under_test.seat_scope
            summary_seats.append(seat)
            summary_scope = scope_seats(scope, num_players=spec.num_players, probed_seat=seat)
            style = probed_seat_style(
                scope, num_players=spec.num_players, probed_seat=seat
            )
        entries.append(
            SeatConstructionEntry(
                seat=seat,
                role=SeatRole.PROBED_UNDER_TEST,
                identifier=under_test.identifier,
                interface=under_test.interface,
                requires_public_summary=under_test.requires_public_summary,
                seat_scope=scope,
                material=_single_material(materials, protocol, PurposeRole.UNDER_TEST_MATERIAL),
            )
        )
    return ArmConstructionPlan(
        arm=arm,
        entries=tuple(entries),
        summary_seats=tuple(summary_seats),
        summary_scope=summary_scope,
        probed_seat_style=style,
    )


def plan_by_seat(plan: ArmConstructionPlan) -> Mapping[int, SeatConstructionEntry]:
    """按座位号升序返回构造口径映射，供核验逐项阅读。"""
    return {entry.seat: entry for entry in sorted(plan.entries, key=lambda item: item.seat)}


def _value_token(value: object) -> str:
    """把默认取值渲染成稳定的字符串表示：空值、布尔、整数与其余取值分开处理。"""
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return repr(value)


def _constant_payload(value: object) -> object:
    """把代码对象常量转成可规范序列化的表示；嵌套代码对象递归展开。"""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, tuple):
        return [_constant_payload(item) for item in value]
    if isinstance(value, types.CodeType):
        return _code_payload(value)
    return {"type": type(value).__name__}


def _code_payload(code: types.CodeType) -> dict[str, object]:
    """一个已加载代码对象的规范载荷：标识、参数布局与编译产物。"""
    return {
        "name": code.co_name,
        "qualname": code.co_qualname,
        "first_line": code.co_firstlineno,
        "parameter_layout": {
            "positional_only": code.co_posonlyargcount,
            "positional_or_keyword": code.co_argcount - code.co_posonlyargcount,
            "keyword_only": code.co_kwonlyargcount,
        },
        "variable_names": list(code.co_varnames),
        "names": list(code.co_names),
        "free_variables": list(code.co_freevars),
        "cell_variables": list(code.co_cellvars),
        "code": code.co_code.hex(),
        "constants": [_constant_payload(item) for item in code.co_consts],
    }


def _positional_defaults(function: types.FunctionType) -> tuple[tuple[str, object], ...]:
    """位置参数的默认值：名称与取值配对（默认值对应参数表末尾的若干项）。"""
    code = function.__code__
    names = code.co_varnames[: code.co_argcount]
    defaults = function.__defaults__ or ()
    paired = names[len(names) - len(defaults) :]
    return tuple(zip(paired, defaults, strict=True))


def _entry_point_payload() -> dict[str, object]:
    """基线实现入口的规范载荷：模块、限定名、参数布局、默认值与代码对象载荷。"""
    function = HeuristicStrategy.__init__
    defaults = {name: _constant_payload(value) for name, value in _positional_defaults(function)}
    return {
        "module": function.__module__,
        "qualname": function.__qualname__,
        "positional_defaults": defaults,
        "code": _code_payload(function.__code__),
    }


def _require_expected_defaults(defaults: dict[str, object]) -> None:
    """基线入口必须带有预期的位置默认值：上游改动导致参数缺失即失败，不静默记成空值。"""
    for name in BASELINE_REQUIRED_DEFAULTS:
        if name not in defaults:
            raise IdentityMappingError(f"基线入口的位置默认值缺少参数：{name!r}")


def _baseline_execution_payload(algorithm: str) -> dict[str, object]:
    """基线身份的有效执行口径：位置绑定与从策略代码只读读取的执行参数。

    取值在本包内从已加载的策略代码读取，不由调用方声明；本函数不构造任何策略实例，
    也不导入或调用受控注册表的任何函数。绑定的强度与环境相关性见本模块说明。
    """
    entry = _entry_point_payload()
    return {
        "identifier": BASELINE_IDENTIFIER,
        "registry_location": BASELINE_REGISTRY_LOCATION,
        "entry_point": entry,
        "entry_digest": content_digest(entry, algorithm=algorithm),
    }


def _baseline_execution_entries(algorithm: str) -> tuple[tuple[str, str], ...]:
    """基线执行口径的规范条目：位置、参数布局、有效取值与代码对象载荷摘要。"""
    function = HeuristicStrategy.__init__
    code = function.__code__
    defaults = {name: value for name, value in _positional_defaults(function)}
    _require_expected_defaults(defaults)
    location = f"{function.__module__}.{function.__qualname__}"
    if not location.endswith(BASELINE_ENTRY_POINT):
        raise IdentityMappingError(f"基线入口的位置与预期不符：{location!r}")
    layout = code.co_varnames[: code.co_argcount + code.co_kwonlyargcount]
    separator = ","
    layout_text = separator.join(layout)
    return (
        ("baseline-registry-location", BASELINE_REGISTRY_LOCATION),
        ("baseline-entry-point", location),
        ("baseline-parameter-layout", layout_text),
        ("baseline-effective-seed", _value_token(defaults["seed"])),
        ("baseline-effective-samples", _value_token(defaults["samples"])),
        ("baseline-effective-bluff-freq", _value_token(defaults["bluff_freq"])),
        (
            "baseline-entry-code-digest",
            content_digest(_entry_point_payload(), algorithm=algorithm),
        ),
    )


def _seat_payload(entry: SeatConstructionEntry) -> dict[str, object]:
    """一个座位的构造口径规范编码。"""
    return {
        "seat": entry.seat,
        "role": entry.role.value,
        "identifier": entry.identifier,
        "interface": entry.interface.value,
        "requires_public_summary": entry.requires_public_summary,
        "seat_scope": None if entry.seat_scope is None else entry.seat_scope.value,
        "material": {
            "purpose_label": entry.material.purpose_label,
            "index_key": list(entry.material.index_key),
            "value": entry.material.value,
        },
    }


def plan_payload(
    *, spec: DomainRunSpec, caliber: ConstructionCaliber, bundle: Sequence[HandMaterials]
) -> list[dict[str, object]]:
    """逐手逐臂逐座位的构造计划规范编码：由显式构造口径唯一确定。"""
    if len(bundle) != len(spec.schedule):
        raise SpecIncompleteError("材料束必须与手序计划一一对应")
    payload: list[dict[str, object]] = []
    for plan, materials in zip(spec.schedule, bundle, strict=True):
        for arm in (Arm.UNDER_TEST, Arm.BASELINE):
            arm_plan = build_arm_construction_plan(spec, caliber, arm, plan, materials)
            payload.append(
                {
                    "hand_ordinal": plan.hand_ordinal,
                    "button": plan.button,
                    "probed_seat": plan.probed_seat,
                    "arm": arm.value,
                    "summary_seats": list(arm_plan.summary_seats),
                    "summary_scope": list(arm_plan.summary_scope),
                    "probed_seat_style": arm_plan.probed_seat_style,
                    "seats": [_seat_payload(entry) for entry in arm_plan.entries],
                }
            )
    return payload


def construction_caliber_payload(
    *,
    spec: DomainRunSpec,
    caliber: ConstructionCaliber,
    bundle: Sequence[HandMaterials],
    algorithm: str,
) -> dict[str, object]:
    """构造口径的完整规范载荷：两侧口径、基线约束与执行口径、规格标识、构造计划。"""
    return {
        "caliber": caliber.canonical_payload(),
        "baseline_constraint": {
            "identifier": BASELINE_IDENTIFIER,
            "interface": ConstructionInterface.REGISTRY_SEED.value,
            "requires_public_summary": False,
            "seat_scope": None,
        },
        "baseline_execution": _baseline_execution_payload(algorithm),
        "spec_identifiers": {
            "num_players": spec.num_players,
            "baseline": spec.baseline_identifier,
            "under_test": spec.under_test_identifier,
        },
        "plan": plan_payload(spec=spec, caliber=caliber, bundle=bundle),
    }


def construction_caliber_digest(
    *,
    spec: DomainRunSpec,
    caliber: ConstructionCaliber,
    bundle: Sequence[HandMaterials],
    algorithm: str,
) -> str:
    """由构造口径内容、基线执行口径与由它唯一确定的构造计划重算摘要。"""
    return content_digest(
        construction_caliber_payload(
            spec=spec, caliber=caliber, bundle=bundle, algorithm=algorithm
        ),
        algorithm=algorithm,
    )


def _bool_token(value: bool) -> str:
    """把布尔口径渲染成稳定的字符串表示。"""
    return "true" if value else "false"


def instantiation_caliber_entries(
    *,
    spec: DomainRunSpec,
    caliber: ConstructionCaliber,
    bundle: Sequence[HandMaterials],
    algorithm: str,
) -> tuple[tuple[str, str], ...]:
    """实例化口径类别的规范条目：逐项由当前显式构造口径、基线执行口径与重算的构造计划得出。"""
    require_caliber_matches_spec(spec, caliber)
    plan = plan_payload(spec=spec, caliber=caliber, bundle=bundle)
    scope = caliber.under_test.seat_scope
    baseline_scope = caliber.baseline.seat_scope
    return (
        ("baseline-identifier", caliber.baseline.identifier),
        ("under-test-identifier", caliber.under_test.identifier),
        ("baseline-interface", caliber.baseline.interface.value),
        ("under-test-interface", caliber.under_test.interface.value),
        (
            "baseline-requires-public-summary",
            _bool_token(caliber.baseline.requires_public_summary),
        ),
        (
            "under-test-requires-public-summary",
            _bool_token(caliber.under_test.requires_public_summary),
        ),
        ("baseline-seat-scope", "none" if baseline_scope is None else baseline_scope.value),
        ("under-test-seat-scope", "none" if scope is None else scope.value),
        *_baseline_execution_entries(algorithm),
        ("construction-plan-digest", content_digest(plan, algorithm=algorithm)),
    )


def require_instantiation_caliber(
    record: ExecutionIdentityRecord,
    *,
    spec: DomainRunSpec,
    caliber: ConstructionCaliber,
    bundle: Sequence[HandMaterials],
    algorithm: str,
) -> None:
    """执行身份里的实例化口径必须与当前显式构造口径及重算的构造计划逐项一致。"""
    expected = dict(
        instantiation_caliber_entries(
            spec=spec, caliber=caliber, bundle=bundle, algorithm=algorithm
        )
    )
    reported = {entry.name: entry.value for entry in record.entries_for(
        INSTANTIATION_CALIBER_CATEGORY
    )}
    missing = set(expected) - set(reported)
    extra = set(reported) - set(expected)
    if missing or extra:
        raise IdentityMappingError(
            "执行身份的实例化口径条目与当前构造口径不一致："
            f"缺少 {len(missing)} 项，多出 {len(extra)} 项"
        )
    for name, value in expected.items():
        if reported[name] != value:
            raise IdentityMappingError(
                f"执行身份的实例化口径与当前构造口径不一致：{name}"
            )
