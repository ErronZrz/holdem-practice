"""运行前规格、冻结绑定、不可执行边界与输出结构的契约回归。

只做有界单元回归：不跑配对比较、不生成材料、不写任何工件，也不构成任何质量结论。
「不可执行」由结构断言自动固定：递归枚举包本身与其全部子模块、按 AST 规则检查导入白名单、
危险调用、受限成员的引用与别名、禁止符号与函数签名，并逐个检查公开可调用对象的参数与注解。
检查器本身由合成源码做反向用例：受禁依赖、执行能力、解锁入口与相对导入逃逸都必须被检出。

测试夹具在内存中拼出示例材料、材料清单与审计转录：不是域 C 材料生成，也不是任何冻结工件。
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import types
from types import ModuleType

import pytest
from pydantic import ValidationError

from app.verification import (
    EXECUTION_IDENTITY_CATEGORIES,
    FROZEN_MANIFEST_ITEMS,
    INSTANTIATION_CALIBER_CATEGORY,
    RUN_FLOW_STEPS,
    AuditedMaterials,
    DomainRunSpec,
    ExecutionIdentityRecord,
    FreezeBindingError,
    FrozenRunManifest,
    HandPlan,
    IdentityMappingError,
    MaterialBindingError,
    MaterialEntry,
    PairedHandRecord,
    PairedRunOutput,
    ProtocolAuditError,
    SeatScope,
    SpecIncompleteError,
    VerificationError,
    build_execution_identity_record,
    build_frozen_manifest,
    build_run_metadata,
    execution_identity_digest,
    flow_step_entries,
    manifest_digest,
    materials_digest,
    reference_snapshot,
    verify_frozen_inputs,
)

from .verification_helpers import (
    BASELINE_IDENTIFIER,
    Fixture,
    build_fixture,
    caliber_categories,
    conflicting_baseline_caliber,
    construction_caliber,
    entries_of,
    forged_caliber_categories,
    identity_categories,
    recommit_audit,
    replace_entries,
    replace_manifest_entry,
    run_spec,
)

FIXTURE: Fixture = build_fixture()

PACKAGE_NAME = "app.verification"

# 包与其全部子模块的声明，以及各模块允许出现的公开函数：新增模块或函数即失败。
EXPECTED_FUNCTIONS: dict[str, frozenset[str]] = {
    PACKAGE_NAME: frozenset(),
    f"{PACKAGE_NAME}.config": frozenset(
        {
            "spec_digest",
            "schedule_digest",
            "schedule_payload",
            "campaign_configuration_payload",
            "campaign_configuration_digest",
            "build_domain_run_spec",
        }
    ),
    f"{PACKAGE_NAME}.deal": frozenset(
        {
            "card_universe",
            "draw_order",
            "deal_for_hand",
            "deal_mapping_payload",
            "deal_mapping_digest",
        }
    ),
    f"{PACKAGE_NAME}.digests": frozenset(
        {"require_algorithm", "canonical_bytes", "bytes_digest", "content_digest"}
    ),
    f"{PACKAGE_NAME}.errors": frozenset(),
    f"{PACKAGE_NAME}.execution_identity": frozenset(
        {
            "reference_snapshot",
            "execution_identity_digest",
            "build_execution_identity_record",
        }
    ),
    f"{PACKAGE_NAME}.guards": frozenset(
        {
            "precheck_rule_entries",
            "injection_precheck_rules_digest",
            "injection_precheck_category_entries",
            "precheck_injection",
            "same_deal",
            "require_same_deal",
            "deal_seat_mapping",
        }
    ),
    f"{PACKAGE_NAME}.identity": frozenset(
        {
            "require_baseline_limits",
            "require_identifier_match",
            "require_material_key",
            "material_key_from_integer",
            "require_explicit_seed",
        }
    ),
    f"{PACKAGE_NAME}.instantiation": frozenset(
        {
            "require_material_format",
            "require_caliber_matches_spec",
            "require_construction_calibers",
            "require_instantiation_caliber",
            "require_registry_seed_mapping",
            "scope_seats",
            "probed_seat_style",
            "materials_digest",
            "encode_baseline_entry_payload",
            "public_summary_mapping_payload",
            "public_summary_mapping_digest",
            "require_materials",
            "plan_payload",
            "construction_caliber_payload",
            "construction_caliber_digest",
            "instantiation_caliber_entries",
            "build_arm_construction_plan",
            "plan_by_seat",
        }
    ),
    f"{PACKAGE_NAME}.materials": frozenset(
        {"bundle_payload", "manifest_digest", "require_supplied_materials_order"}
    ),
    f"{PACKAGE_NAME}.protocol": frozenset(
        {
            "required_bit_width",
            "protocol_digest",
            "protocol_payload",
            "purpose_index_mapping_payload",
            "purpose_index_mapping_digest",
            "resolve_read",
            "commitment_digest",
            "read_record_digest",
            "require_manifest_consistent",
            "verify_audit",
            "verify_manifest_binding",
            "verify_material_binding",
        }
    ),
    f"{PACKAGE_NAME}.runner": frozenset(
        {
            "flow_step_entries",
            "runner_flow_digest",
            "runner_category_entries",
            "build_frozen_manifest",
            "verify_frozen_inputs",
            "build_run_metadata",
        }
    ),
    f"{PACKAGE_NAME}.source_manifest": frozenset(
        {"require_source_manifest", "source_manifest_digest"}
    ),
}

# 包内允许出现的依赖：标准库与只读引用的应用模块。
ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "__future__",
        "collections.abc",
        "dataclasses",
        "datetime",
        "enum",
        "hashlib",
        "json",
        "math",
        "types",
        "typing",
        "pydantic",
        "app.poker.cards",
        "app.strategy.heuristic",
        "app.strategy.mixed_strategy",
        "app.analysis.reference_identity",
    }
)

# 禁止出现（无论作为名称还是属性）的逃逸内省入口：可用于替换实现、取回全局或枚举子类。
FORBIDDEN_ESCAPES: tuple[str, ...] = (
    "__getattribute__",
    "__getattr__",
    "__setattr__",
    "__delattr__",
    "__subclasses__",
    "__mro__",
    "__bases__",
    "__globals__",
    "__builtins__",
    "__dict__",
    "__class__",
    "__import__",
    "__loader__",
    "__spec__",
    "__reduce__",
    "__reduce_ex__",
    "__init_subclass__",
    "__set_name__",
    "__func__",
    "__self__",
    "__closure__",
    "__wrapped__",
)

# 禁止作为调用名出现的入口：动态求值、反射、文件与交互。
FORBIDDEN_CALL_NAMES: frozenset[str] = frozenset(
    {
        "exec",
        "eval",
        "compile",
        "open",
        "input",
        "breakpoint",
        "__import__",
        "getattr",
        "setattr",
        "delattr",
        "vars",
        "globals",
        "locals",
    }
)

# 禁止作为调用根出现的模块：动态导入、子进程、网络、随机源与并发。
FORBIDDEN_CALL_ROOTS: frozenset[str] = frozenset(
    {
        "importlib",
        "subprocess",
        "socket",
        "urllib",
        "pickle",
        "random",
        "secrets",
        "ctypes",
        "os",
        "sys",
        "shutil",
        "tempfile",
        "pathlib",
        "threading",
        "multiprocessing",
        "asyncio",
        "http",
        "ftplib",
        "smtplib",
        "inspect",
        "pty",
        "pdb",
    }
)

# 只要作为标识符出现，就说明包内重新出现了可推进牌局或可解锁执行的能力。
FORBIDDEN_SYMBOLS: tuple[str, ...] = (
    "PokerEngine",
    "start_hand_with",
    "apply_action",
    "MixedSummaryTracker",
    "mixed_state",
    "create_strategy",
    "MixedLocalStrategy",
    "FinalFreezeHandle",
    "run_paired_hands",
    "IllegalActionError",
    "project_for_actor",
)

# 基线实现的类名与其两个受限成员：构造入口不得被引用；初始化入口只允许用于读取只读元数据。
BASELINE_CLASS_NAME = "HeuristicStrategy"
BASELINE_CONSTRUCTOR_CHAIN = f"{BASELINE_CLASS_NAME}.__new__"
BASELINE_ENTRY_CHAIN = f"{BASELINE_CLASS_NAME}.__init__"
RESTRICTED_MEMBER_CHAINS: frozenset[str] = frozenset(
    {BASELINE_CONSTRUCTOR_CHAIN, BASELINE_ENTRY_CHAIN}
)

# 允许在受限初始化入口及其别名上读取的只读元数据属性：本包当前只用这四项。
ALLOWED_ENTRY_METADATA: frozenset[str] = frozenset(
    {"__code__", "__defaults__", "__module__", "__qualname__"}
)

# 禁止作为调用目标的符号：基线实现只允许读取代码元数据，不允许实例化或调用它。
FORBIDDEN_CALL_TARGETS: tuple[str, ...] = (
    *FORBIDDEN_SYMBOLS,
    BASELINE_CLASS_NAME,
    BASELINE_ENTRY_CHAIN,
)

# 禁止被改名的调用目标：只取单段名称；基线实现的点分成员由受限成员规则单独检查。
FORBIDDEN_ALIASES: frozenset[str] = frozenset(
    name for name in FORBIDDEN_CALL_TARGETS if "." not in name
)

# 基线实现模块与其唯一允许的导入形式：别名或整模块导入会绕过按名匹配的调用目标检查。
HEURISTIC_MODULE = "app.strategy.heuristic"
HEURISTIC_IMPORT_FORM: tuple[tuple[str, None], ...] = (("HeuristicStrategy", None),)

# 禁止作为参数名出现的解锁类字样；参数注解中出现句柄字样同样失败。
FORBIDDEN_PARAMETERS: frozenset[str] = frozenset(
    {"handle", "freeze", "frozen", "token", "unlock"}
)

FIELD_BY_ITEM: dict[str, str] = {
    "spec-digest": "spec_digest",
    "schedule-digest": "schedule_digest",
    "protocol-digest": "protocol_digest",
    "supplied-materials-digest": "supplied_materials_digest",
    "material-manifest-digest": "material_manifest_digest",
    "audit-transcript-digest": "audit_transcript_digest",
    "audit-read-record-digest": "audit_read_record_digest",
    "audit-commitment-digest": "audit_commitment_digest",
    "construction-caliber-digest": "construction_caliber_digest",
    "execution-identity-digest": "execution_identity_digest",
}


# ------------------------------------------------------------------ 结构检查器


def _module_tree() -> dict[str, ModuleType]:
    """递归枚举包本身与其全部子模块：包的初始化模块也在检查范围内。"""
    package = importlib.import_module(PACKAGE_NAME)
    tree = {PACKAGE_NAME: package}
    for info in pkgutil.walk_packages(package.__path__, prefix=f"{PACKAGE_NAME}."):
        tree[info.name] = importlib.import_module(info.name)
    return tree


def _declaration_gap(discovered: set[str]) -> set[str]:
    """声明表与递归枚举结果的差集：未登记的模块与缺失的已登记模块都会被指出。"""
    declared = set(EXPECTED_FUNCTIONS)
    return (discovered - declared) | (declared - discovered)


def _resolved_import(module_name: str, node: ast.ImportFrom, *, is_package: bool) -> str:
    """把（可能是相对的）导入目标解析成完整模块名。

    相对层级以所在包为基准：包的初始化模块自身的第 1 级即该包，子模块的第 1 级则为其所在包。
    """
    if node.level == 0:
        return node.module or ""
    parts = module_name.split(".")
    depth = max(0, len(parts) - node.level + (1 if is_package else 0))
    prefix = ".".join(parts[:depth])
    if node.module:
        return f"{prefix}.{node.module}" if prefix else node.module
    return prefix


def _import_violations(
    module_name: str, tree: ast.AST, *, is_package: bool
) -> list[str]:
    """按白名单校验导入：相对导入解析成完整模块名后接受同一规则。

    基线实现模块另受更严格的导入形式约束：只允许无别名的类导入，避免别名绕过调用检查。
    """
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_heuristic_module(alias.name):
                    found.append(f"禁止的基线模块导入：{alias.name!r}")
                elif alias.name not in ALLOWED_IMPORTS:
                    found.append(f"未获准的依赖：{alias.name!r}")
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        base = _resolved_import(module_name, node, is_package=is_package)
        if _is_heuristic_module(base):
            forms = tuple((alias.name, alias.asname) for alias in node.names)
            if node.module is None or forms != HEURISTIC_IMPORT_FORM:
                found.append(f"基线实现只允许无别名的类导入：{forms!r}")
            continue
        if base == PACKAGE_NAME or base.startswith(f"{PACKAGE_NAME}."):
            continue
        if base not in ALLOWED_IMPORTS:
            found.append(f"未获准的依赖：{base!r}")
    return found


def _is_heuristic_module(name: str) -> bool:
    """判断模块名是否指向基线实现所在模块（含其子模块）。"""
    return name == HEURISTIC_MODULE or name.startswith(f"{HEURISTIC_MODULE}.")


def _dotted_name(node: ast.AST) -> str | None:
    """把「纯名称起始、逐级属性」的表达式渲染成点分名；其余形态返回空。

    属性链的基座必须是纯名称：基座为调用结果、下标、lambda、生成器、条件表达式、二元运算
    或容器字面量时，返回空并由调用方默认拒绝，不做任何降级放行。
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return None if parent is None else f"{parent}.{node.attr}"
    return None


def _call_violations(tree: ast.AST) -> list[str]:
    """按 AST 检查调用：目标不是纯名称或名称起始属性链时默认拒绝，其余按三张表判定。"""
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name is None:
            found.append("调用目标不是纯名称或名称起始的属性链，默认拒绝")
            continue
        segments = name.split(".")
        if segments[0] in FORBIDDEN_CALL_NAMES:
            found.append(f"禁止的调用：{name!r}")
        elif segments[0] in FORBIDDEN_CALL_ROOTS:
            found.append(f"禁止的调用根：{name!r}")
        elif (
            segments[0] in FORBIDDEN_CALL_TARGETS
            or segments[-1] in FORBIDDEN_CALL_TARGETS
            or name in FORBIDDEN_CALL_TARGETS
        ):
            found.append(f"禁止的调用目标：{name!r}")
    return found


def _alias_violations(tree: ast.AST) -> list[str]:
    """按 AST 检查赋值：受禁调用目标不得被改名后调用，别名会绕过按名匹配的检查。"""
    found: list[str] = []
    for node in ast.walk(tree):
        values: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            values = [node.value]
        elif isinstance(node, ast.AnnAssign):
            values = [] if node.value is None else [node.value]
        elif isinstance(node, ast.AugAssign | ast.NamedExpr):
            values = [node.value]
        for value in values:
            name = _dotted_name(value)
            if name is None:
                continue
            if name.split(".")[-1] in FORBIDDEN_ALIASES:
                found.append(f"禁止的调用目标别名：{name!r}")
    return found


def _name_bindings(tree: ast.AST) -> list[tuple[str, ast.AST]]:
    """本模块内「目标为纯名称」的绑定：赋值、注解赋值、增量赋值与海象表达式。"""
    found: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [item for item in node.targets if isinstance(item, ast.Name)]
            found.extend((item.id, node.value) for item in targets)
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None and isinstance(node.target, ast.Name):
                found.append((node.target.id, node.value))
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                found.append((node.target.id, node.value))
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            found.append((node.target.id, node.value))
    return found


def _restricted_names(tree: ast.AST, chains: frozenset[str]) -> set[str]:
    """受限成员别名的（本模块内）不动点：只沿简单名称绑定传播，不外推容器与跨模块。"""
    bindings = _name_bindings(tree)
    names: set[str] = set()
    growing = True
    while growing:
        growing = False
        for target, value in bindings:
            if target in names:
                continue
            propagated = isinstance(value, ast.Name) and value.id in names
            if propagated or _dotted_name(value) in chains:
                names.add(target)
                growing = True
    return names


def _metadata_bases(tree: ast.AST, entry_aliases: set[str]) -> set[int]:
    """被读取的只读元数据属性的基座：只认受限初始化入口本身或它的简单名称别名。

    其它受限成员（例如受限构造入口）即使被取用这些属性名，也不进入豁免集合。
    """
    bases: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr not in ALLOWED_ENTRY_METADATA:
            continue
        value = node.value
        is_entry = _dotted_name(value) == BASELINE_ENTRY_CHAIN
        is_alias = isinstance(value, ast.Name) and value.id in entry_aliases
        if is_entry or is_alias:
            bases.add(id(value))
    return bases


def _module_functions(tree: ast.Module) -> dict[str, ast.AST]:
    """模块顶层的函数定义：参数传递规则只在同一模块的顶层函数之间成立。"""
    definitions = (ast.FunctionDef, ast.AsyncFunctionDef)
    return {node.name: node for node in tree.body if isinstance(node, definitions)}


def _parameter_reads_metadata_only(function: ast.AST, parameter: str) -> bool:
    """该参数在函数体内是否只被用作只读元数据属性的基座。

    参数在函数体内按受限初始化入口的别名对待；出现任何其它取值用法（调用、再绑定、
    置入容器、作为返回值等）即判否，规则保持保守。
    """
    bases = _metadata_bases(function, {parameter})
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == parameter
            and id(node) not in bases
        ):
            return False
    return True


def _metadata_argument_ids(tree: ast.Module, names: set[str]) -> set[int]:
    """受限别名传给本模块顶层函数、且该参数只读元数据时，该实参被放行。

    受限构造入口的引用本身即违例，因此本规则不为它留下例外。
    """
    functions = _module_functions(tree)
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        function = functions.get(node.func.id)
        if function is None:
            continue
        parameters = [item.arg for item in (*function.args.posonlyargs, *function.args.args)]
        for position, argument in enumerate(node.args):
            if position >= len(parameters):
                break
            if not isinstance(argument, ast.Name) or argument.id not in names:
                continue
            if _parameter_reads_metadata_only(function, parameters[position]):
                allowed.add(id(argument))
    return allowed


def _restricted_violations(tree: ast.Module) -> list[str]:
    """按 AST 检查受限成员的引用、别名与调用：只覆盖本模块内的简单名称传播。

    受限初始化入口可以绑定到名称，并用于读取预置的只读元数据或把**该别名**传给本模块内
    只读该元数据的顶层函数；调用、再次传播、置入容器、作为返回值等其它用法一律拒绝。受限
    构造入口的任何引用都拒绝，且不因取用元数据属性名而获得豁免。跨模块数据流、运行期注入
    与包外执行不在本规则范围内。
    """
    entry_aliases = _restricted_names(tree, frozenset({BASELINE_ENTRY_CHAIN}))
    names = _restricted_names(tree, RESTRICTED_MEMBER_CHAINS)
    permitted = _metadata_bases(tree, entry_aliases)
    for _, value in _name_bindings(tree):
        if _dotted_name(value) == BASELINE_ENTRY_CHAIN:
            permitted.add(id(value))
    permitted |= _metadata_argument_ids(tree, entry_aliases)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            name = _dotted_name(node)
            if name not in RESTRICTED_MEMBER_CHAINS or id(node) in permitted:
                continue
            if name == BASELINE_CONSTRUCTOR_CHAIN:
                found.append(f"禁止引用受限成员：{name!r}")
            else:
                found.append(f"禁止在元数据读取之外使用受限成员：{name!r}")
        elif (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in names
            and id(node) not in permitted
        ):
            found.append(f"禁止使用受限成员别名：{node.id!r}")
    return found


def _escape_violations(tree: ast.AST) -> list[str]:
    """按 AST 检查逃逸内省入口：以名称或属性形式出现都拒绝。"""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_ESCAPES:
            found.append(f"禁止的逃逸入口：{node.id!r}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ESCAPES:
            found.append(f"禁止的逃逸入口：{node.attr!r}")
    return found


def _identifier_violations(tree: ast.AST) -> list[str]:
    """按 AST 检查标识符：禁止符号不得作为名称、属性、定义名或参数名出现。"""
    found: list[str] = []
    checked: tuple[type[ast.AST], ...] = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
    )
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, checked):
            names = [node.name]
        elif isinstance(node, ast.arg):
            names = [node.arg]
        for name in names:
            if name in FORBIDDEN_SYMBOLS or "Handle" in name:
                found.append(f"禁止的符号：{name!r}")
    return found


def _parameter_violations(tree: ast.AST) -> list[str]:
    """按 AST 检查函数签名：不得出现解锁类参数名或句柄类型注解。"""
    found: list[str] = []
    definitions: tuple[type[ast.AST], ...] = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, definitions):
            continue
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        for argument in arguments:
            if argument.arg in FORBIDDEN_PARAMETERS:
                found.append(f"禁止的参数名：{argument.arg!r}")
            annotation = "" if argument.annotation is None else ast.unparse(argument.annotation)
            if "Handle" in annotation:
                found.append(f"禁止的参数类型：{annotation!r}")
    return found


def _source_violations(
    module_name: str, source: str, *, is_package: bool = False
) -> list[str]:
    """对一段源码做全部 AST 级检查；返回空列表表示没有违例。"""
    tree = ast.parse(source)
    return (
        _import_violations(module_name, tree, is_package=is_package)
        + _call_violations(tree)
        + _alias_violations(tree)
        + _restricted_violations(tree)
        + _escape_violations(tree)
        + _identifier_violations(tree)
        + _parameter_violations(tree)
    )


def _own_classes(module: ModuleType) -> dict[str, type]:
    """该模块自有的类（不含导入进来的类）。"""
    return {
        name: value
        for name, value in vars(module).items()
        if inspect.isclass(value)
        and value.__module__ == module.__name__
        and not name.startswith("_")
    }


def _callables(module: ModuleType) -> dict[str, object]:
    """该模块自有的可调用对象。

    范围包括模块级函数、类、类成员、属性访问器，以及类定义在本模块内的模块级 callable
    实例；自有类的 `__call__` 同样纳入，避免以实例形态隐藏入口。
    """
    found: dict[str, object] = {}
    for name, value in vars(module).items():
        if inspect.isfunction(value) and value.__module__ == module.__name__:
            found[name] = value
        elif not inspect.isclass(value) and callable(value):
            owner = type(value)
            if owner.__module__ != module.__name__:
                continue
            found[name] = value
            hook = vars(owner).get("__call__")
            if hook is not None:
                found[f"{name}.__call__"] = hook
    for class_name, klass in _own_classes(module).items():
        if callable(klass):
            found[class_name] = klass
        for member_name, member in vars(klass).items():
            if member_name.startswith("__") and member_name != "__call__":
                continue
            target = member.fget if isinstance(member, property) else member
            if not callable(target):
                continue
            owner = getattr(target, "__module__", None)
            if owner is not None and owner != module.__name__:
                continue
            found[f"{class_name}.{member_name}"] = target
    return found


def _signature_violations(module: ModuleType) -> list[str]:
    """逐个检查可调用对象的签名：不得接受解锁类参数或句柄类型。

    签名取不到时默认拒绝；唯一的例外是自身没有定义构造或调用入口的类（其构造能力来自
    基类），此类没有可检查的本模块入口。
    """
    found: list[str] = []
    hooks = {"__init__", "__call__", "__new__"}
    for item, value in _callables(module).items():
        try:
            parameters = inspect.signature(value).parameters
        except (TypeError, ValueError):
            if inspect.isclass(value) and not set(vars(value)) & hooks:
                continue
            found.append(f"{item} 的签名无法静态取得，默认拒绝")
            continue
        overlap = set(parameters) & FORBIDDEN_PARAMETERS
        if overlap:
            found.append(f"{item} 接受了禁用参数：{sorted(overlap)}")
        for parameter in parameters.values():
            if "Handle" in str(parameter.annotation):
                found.append(f"{item} 接受了句柄类型注解")
    return found


def _source_manifest_kwargs(fixture: Fixture) -> dict[str, object]:
    """把夹具里的手造清单传给冻结输入主链。"""
    manifests = fixture.source_manifests
    return {
        "runner_manifest": manifests.runner,
        "generator_manifest": manifests.generator,
        "engine_manifest": manifests.engine,
        "baseline_strategy_manifest": manifests.baseline_strategy,
        "under_test_strategy_manifest": manifests.under_test_strategy,
        "verification_manifest": manifests.verification,
    }


def _verify_fixture(
    fixture: Fixture = FIXTURE,
    *,
    manifest: FrozenRunManifest | None = None,
    spec: DomainRunSpec | None = None,
) -> None:
    """按夹具走一遍冻结输入校验，允许替换清单或规格。"""
    verify_frozen_inputs(
        manifest=fixture.manifest if manifest is None else manifest,
        spec=fixture.spec if spec is None else spec,
        caliber=fixture.caliber,
        bundle=fixture.bundle,
        audit=fixture.audit,
        execution_identity=fixture.identity,
        material_manifest=fixture.material_manifest,
        **_source_manifest_kwargs(fixture),
    )


# ------------------------------------------------------------------ 不可执行边界


def test_package_module_declaration_is_exhaustive() -> None:
    """递归枚举出的模块集合必须与声明表完全一致，含包自身的初始化模块。"""
    discovered = set(_module_tree())
    assert PACKAGE_NAME in discovered
    assert _declaration_gap(discovered) == set()


def test_new_or_missing_module_is_detected() -> None:
    """声明表之外的新模块（含递归子模块）必须被检出。"""
    injected = f"{PACKAGE_NAME}.subpackage.injected"
    assert _declaration_gap({*_module_tree(), injected}) == {injected}
    assert _declaration_gap({PACKAGE_NAME}) == set(EXPECTED_FUNCTIONS) - {PACKAGE_NAME}


def test_package_public_function_surface_is_allowlisted() -> None:
    for name, module in _module_tree().items():
        functions = {
            item
            for item, value in vars(module).items()
            if inspect.isfunction(value)
            and value.__module__ == module.__name__
            and not item.startswith("_")
        }
        assert functions == set(EXPECTED_FUNCTIONS[name]), f"{name} 的公开函数与白名单不符"


def test_package_source_has_no_forbidden_structure() -> None:
    """包与全部子模块的源码都不得出现受禁依赖、危险调用、禁止符号或解锁参数。"""
    for name, module in _module_tree().items():
        is_package = hasattr(module, "__path__")
        violations = _source_violations(
            name, inspect.getsource(module), is_package=is_package
        )
        assert violations == [], f"{name}: {violations}"


def test_package_callables_accept_no_unlock_parameter() -> None:
    for name, module in _module_tree().items():
        assert _signature_violations(module) == [], name


def test_package_defines_no_handle_or_strategy_or_engine_type() -> None:
    package = importlib.import_module(PACKAGE_NAME)
    for name, module in _module_tree().items():
        for class_name in _own_classes(module):
            assert class_name not in {
                "MixedLocalStrategy",
                "HeuristicStrategy",
                "PokerEngine",
            }, f"{name} 不应定义可推进牌局的类型"
        assert not [
            item for item in dir(module) if item in {"MixedLocalStrategy", "PokerEngine"}
        ]
    assert not hasattr(package, "FinalFreezeHandle")


def test_checker_detects_forbidden_dependency() -> None:
    """包初始化模块出现受禁依赖，或子模块借相对导入逃出包外，都必须被检出。"""
    package_sources = (
        "import importlib\n",
        "from app.poker import engine\n",
        "from .. import strategy\n",
        "from ... import poker\n",
    )
    for source in package_sources:
        assert _source_violations(PACKAGE_NAME, source, is_package=True), source
    module_sources = (
        "from ...poker.cards import Card\n",
        "from .... import poker\n",
    )
    for source in module_sources:
        assert _source_violations(f"{PACKAGE_NAME}.sample", source), source


def test_checker_detects_execution_capability() -> None:
    """包初始化模块出现执行能力或解锁入口时都必须被检出。"""
    sources = (
        "def run():\n    return PokerEngine()\n",
        "def run(engine):\n    return engine.start_hand_with(0)\n",
        "def run(table):\n    return table.apply_action(1)\n",
        "def run(engine):\n    return engine.run_paired_hands()\n",
        "from app.strategy.heuristic import HeuristicStrategy\n"
        "\ndef run():\n    return HeuristicStrategy()\n",
        "from app.strategy.heuristic import HeuristicStrategy\n"
        "\ndef run():\n    return HeuristicStrategy.__new__(HeuristicStrategy)\n",
        "def unlock(handle):\n    return handle\n",
    )
    for source in sources:
        assert _source_violations(PACKAGE_NAME, source), source


def test_checker_detects_dynamic_import_and_reflection() -> None:
    sources = (
        "import importlib\n\ndef load():\n    return importlib.import_module('x')\n",
        "def load():\n    return __import__('os')\n",
        "def read(name):\n    return getattr(name, 'x')\n",
        "def read():\n    return open('x')\n",
    )
    for source in sources:
        assert _source_violations(PACKAGE_NAME, source), source


def test_checker_denies_unresolvable_call_target() -> None:
    """调用目标不是纯名称或名称起始属性链时默认拒绝，不做降级放行。"""
    sources = (
        "def load(factory):\n    return factory()(1)\n",
        "def load(factory):\n    return factory().method()\n",
        "def load(items):\n    return items[0](1)\n",
        "def load(items):\n    return items[0].method()\n",
        "def load():\n    return (lambda value: value)(1)\n",
        "def load(values):\n    return (value for value in values).send(None)\n",
        "def load(flag, left, right):\n    return (left if flag else right)()\n",
        "def load(left, right):\n    return (left + right)()\n",
        "def load():\n    return {'run': 1}['run']()\n",
        "def load(obj):\n    return object.__getattribute__(obj, 'run')(1)\n",
    )
    for source in sources:
        assert _source_violations(PACKAGE_NAME, source), source


def test_checker_denies_baseline_import_aliases() -> None:
    """基线实现模块只允许无别名的类导入，别名与整模块导入会绕过调用目标检查。"""
    sources = (
        "from app.strategy.heuristic import HeuristicStrategy as H\n"
        "\ndef build():\n    return H()\n",
        "from app.strategy.heuristic import *\n\ndef build():\n    return HeuristicStrategy()\n",
        "from app.strategy.heuristic import HeuristicStrategy, _SAMPLES\n",
        "import app.strategy.heuristic as heuristic\n"
        "\ndef build():\n    return heuristic.HeuristicStrategy()\n",
        "import app.strategy.heuristic\n"
        "\ndef build():\n    return app.strategy.heuristic.HeuristicStrategy()\n",
    )
    for source in sources:
        assert _source_violations(PACKAGE_NAME, source), source


def test_checker_denies_baseline_target_aliases_and_construction() -> None:
    """受禁构造目标、其别名与其 `__new__`／构造调用一律拒绝。"""
    import_line = "from app.strategy.heuristic import HeuristicStrategy\n"
    sources = (
        import_line + "\ndef build():\n    return HeuristicStrategy()\n",
        import_line + "\nH = HeuristicStrategy\n\ndef build():\n    return H()\n",
        import_line + "\nH: object = HeuristicStrategy\n\ndef build():\n    return H()\n",
        import_line
        + "\ndef build(registry):\n    alias = registry.HeuristicStrategy\n    return alias()\n",
        import_line
        + "\ndef build():\n    return HeuristicStrategy.__new__(HeuristicStrategy)\n",
        import_line + "\ndef build():\n    return HeuristicStrategy.__init__(None)\n",
    )
    for source in sources:
        assert _source_violations(PACKAGE_NAME, source), source


def test_checker_denies_restricted_member_aliases_and_calls() -> None:
    """受限成员的别名、容器传播与调用一律拒绝，构造入口的任何引用都拒绝。"""
    import_line = "from app.strategy.heuristic import HeuristicStrategy\n"
    sources = (
        import_line
        + "\ndef build():\n    entry = HeuristicStrategy.__init__\n    return entry(object())\n",
        import_line
        + "\ndef build():\n"
        "    factory = HeuristicStrategy.__new__\n"
        "    return factory(HeuristicStrategy)\n",
        import_line
        + "\ndef build():\n    return (HeuristicStrategy.__new__,)[0](HeuristicStrategy)\n",
        import_line
        + "\ndef build():\n"
        "    holder = (HeuristicStrategy.__new__,)\n"
        "    factory = holder[0]\n"
        "    return factory(HeuristicStrategy)\n",
        import_line
        + "\ndef build():\n"
        "    factory = HeuristicStrategy.__new__\n"
        "    other = factory\n"
        "    return other(HeuristicStrategy)\n",
        import_line
        + "\ndef build():\n"
        "    entry = HeuristicStrategy.__init__\n"
        "    other = entry\n"
        "    return other(object())\n",
        import_line
        + "\ndef build():\n    entry = HeuristicStrategy.__init__\n    return (entry,)\n",
        import_line + "\ndef build():\n    entry = HeuristicStrategy.__init__\n    return entry\n",
        import_line
        + "\ndef build():\n"
        "    entry = HeuristicStrategy.__init__\n"
        "    return entry.__call__(object())\n",
        import_line
        + "\ndef invoke(target):\n    return target(object())\n"
        "\ndef build():\n    entry = HeuristicStrategy.__init__\n    return invoke(entry)\n",
        import_line + "\ndef build():\n    return HeuristicStrategy.__init__\n",
        import_line + "\nentry = HeuristicStrategy.__new__\n",
    )
    for source in sources:
        violations = _source_violations(PACKAGE_NAME, source)
        assert violations, source
        assert any("受限成员" in item for item in violations), (source, violations)


def test_checker_denies_constructor_member_metadata_reads() -> None:
    """构造入口不得因取用元数据属性名而获得豁免，任何直接引用都必须被检出。"""
    import_line = "from app.strategy.heuristic import HeuristicStrategy\n"
    sources = (
        import_line + "\ndef build():\n    return HeuristicStrategy.__new__.__code__\n",
        import_line + "\ndef build():\n    return HeuristicStrategy.__new__.__defaults__\n",
        import_line + "\ndef build():\n    return HeuristicStrategy.__new__.__module__\n",
        import_line + "\ndef build():\n    return HeuristicStrategy.__new__.__qualname__\n",
        import_line
        + "\ndef build():\n"
        "    holder = HeuristicStrategy.__new__\n"
        "    return holder.__code__\n",
    )
    for source in sources:
        violations = _source_violations(PACKAGE_NAME, source)
        assert violations, source
        assert any("受限成员" in item for item in violations), (source, violations)


def test_checker_denies_escape_entries() -> None:
    """逃逸内省入口（取全局、枚举子类、替换实现、取回类对象等）一律拒绝。"""
    sources = (
        "def load(obj):\n    return obj.__class__\n",
        "def load(obj):\n    return obj.__dict__\n",
        "def load(obj):\n    return obj.__getattribute__('run')\n",
        "def load():\n    return __builtins__\n",
        "def load(func):\n    return func.__globals__\n",
        "def load(klass):\n    return klass.__subclasses__()\n",
    )
    for source in sources:
        assert _source_violations(PACKAGE_NAME, source), source


def test_callable_collection_covers_instances_and_dunder_call() -> None:
    """模块级 callable 实例与自有类的 `__call__` 都在可调用对象的检查范围内。"""
    synthetic = types.ModuleType("synthetic.module")

    class CallableEntry:
        def __call__(self, handle: int) -> int:
            return handle

    CallableEntry.__module__ = synthetic.__name__
    module_entry = CallableEntry()
    synthetic.entry = module_entry
    found = _callables(synthetic)
    assert "entry" in found
    assert "entry.__call__" in found
    assert _signature_violations(synthetic) != []


def test_checker_accepts_plain_declaration() -> None:
    """检查器不误报：纯声明与只读计算的源码没有违例。"""
    source = (
        "from .errors import VerificationError\n"
        "\n"
        "def check(value: int) -> int:\n"
        "    return value + 1\n"
    )
    assert _source_violations(f"{PACKAGE_NAME}.sample", source) == []


def test_checker_accepts_split_expressions_and_metadata_reads() -> None:
    """语句拆分后的纯计算写法与入口元数据读取不得误报。"""
    source = (
        "import hashlib\n"
        "import json\n"
        "\n"
        "def canonical(payload: object) -> bytes:\n"
        "    text = json.dumps(payload, separators=(',', ':'))\n"
        "    return text.encode('utf-8')\n"
        "\n"
        "def digest(payload: bytes) -> str:\n"
        "    hasher = hashlib.sha256(payload)\n"
        "    return hasher.hexdigest()\n"
        "\n"
        "def entry_metadata():\n"
        "    entry = HeuristicStrategy.__init__\n"
        "    return entry.__qualname__\n"
        "\n"
        "def initialise(parent_value: str) -> None:\n"
        "    parent = super()\n"
        "    parent.__init__(parent_value)\n"
        "\n"
        "def read(holder):\n"
        "    return holder.inner.describe()\n"
    )
    assert _source_violations(f"{PACKAGE_NAME}.sample", source) == []


def test_checker_accepts_entry_metadata_only_reads() -> None:
    """只读访问入口元数据不得误报：直接读取、经别名读取与经本模块只读辅助读取。"""
    source = (
        "from app.strategy.heuristic import HeuristicStrategy\n"
        "\n"
        "def defaults_of(function: object) -> object:\n"
        "    return function.__defaults__\n"
        "\n"
        "def entry_metadata() -> object:\n"
        "    entry = HeuristicStrategy.__init__\n"
        "    payload = {\n"
        "        'code': HeuristicStrategy.__init__.__code__,\n"
        "        'module': HeuristicStrategy.__init__.__module__,\n"
        "        'qualname': HeuristicStrategy.__init__.__qualname__,\n"
        "        'defaults': entry.__defaults__,\n"
        "        'helper': defaults_of(entry),\n"
        "    }\n"
        "    return payload\n"
    )
    assert _source_violations(f"{PACKAGE_NAME}.sample", source) == []


def test_runner_declares_flow_without_executing_it() -> None:
    assert len(RUN_FLOW_STEPS) == 7
    assert [name for _, name in flow_step_entries()] == list(RUN_FLOW_STEPS)
    runner = importlib.import_module("app.verification.runner")
    assert not hasattr(runner, "FinalFreezeHandle")
    assert not hasattr(runner, "run_paired_hands")


# ------------------------------------------------------------------ 运行前规格


def test_run_spec_requires_explicit_values() -> None:
    with pytest.raises(ValidationError):
        DomainRunSpec.model_validate({"num_players": 3})


@pytest.mark.parametrize(
    "overrides",
    [
        {"num_players": 1},
        {"small_blind": 3, "big_blind": 2},
        {"baseline_identifier": "   "},
        {"baseline_identifier": "random@1"},
        {"under_test_identifier": BASELINE_IDENTIFIER},
        {"schedule": ()},
        {
            "schedule": (
                HandPlan(hand_ordinal=2, button=1, probed_seat=1),
                HandPlan(hand_ordinal=1, button=2, probed_seat=1),
            )
        },
        {"schedule": (HandPlan(hand_ordinal=1, button=3, probed_seat=1),)},
        {"schedule": (HandPlan(hand_ordinal=1, button=1, probed_seat=3),)},
    ],
)
def test_run_spec_rejects_inconsistent_values(overrides: dict[str, object]) -> None:
    fields = run_spec().model_dump()
    fields.update(overrides)
    with pytest.raises(SpecIncompleteError):
        DomainRunSpec.model_validate(fields)


@pytest.mark.parametrize("field", ["num_players", "starting_stack", "engine_seed"])
def test_run_spec_requires_strict_integers(field: str) -> None:
    fields = run_spec().model_dump()
    fields[field] = "1"
    with pytest.raises(ValidationError):
        DomainRunSpec.model_validate(fields)


def test_run_spec_plan_lookup_by_hand_ordinal() -> None:
    spec = run_spec()
    assert spec.plan_for(1).probed_seat == 1
    with pytest.raises(SpecIncompleteError):
        spec.plan_for(2)


# ------------------------------------------------------------------ 冻结绑定


def test_frozen_manifest_covers_declared_items() -> None:
    assert set(FIELD_BY_ITEM) == set(FROZEN_MANIFEST_ITEMS)
    assert len(FROZEN_MANIFEST_ITEMS) == 10


def test_well_formed_inputs_pass_freeze_binding() -> None:
    _verify_fixture()


def test_multi_hand_inputs_pass_end_to_end() -> None:
    _verify_fixture(build_fixture(hands=2))


def test_frozen_manifest_requires_every_digest() -> None:
    with pytest.raises(ValidationError):
        FrozenRunManifest.model_validate({"digest_algorithm": "sha256"})
    fields = FIXTURE.manifest.model_dump()
    fields["spec_digest"] = ""
    with pytest.raises(FreezeBindingError):
        FrozenRunManifest.model_validate(fields)
    fields = FIXTURE.manifest.model_dump()
    fields["digest_algorithm"] = "sha512"
    with pytest.raises(FreezeBindingError):
        FrozenRunManifest.model_validate(fields)


@pytest.mark.parametrize("item", FROZEN_MANIFEST_ITEMS)
def test_manifest_item_mismatch_fails(item: str) -> None:
    manifest = FIXTURE.manifest.model_copy(update={FIELD_BY_ITEM[item]: "0" * 64})
    with pytest.raises(FreezeBindingError, match=item):
        _verify_fixture(manifest=manifest)


def test_manifest_algorithm_must_match_protocol() -> None:
    manifest = FIXTURE.manifest.model_copy(update={"digest_algorithm": "sha512"})
    with pytest.raises(FreezeBindingError, match="摘要算法"):
        _verify_fixture(manifest=manifest)


def test_tampered_audit_transcript_fails_before_binding() -> None:
    audit = recommit_audit(FIXTURE.audit, transcript=FIXTURE.audit.transcript + b"\x00")
    with pytest.raises(ProtocolAuditError):
        verify_frozen_inputs(
            manifest=FIXTURE.manifest,
            spec=FIXTURE.spec,
            caliber=FIXTURE.caliber,
            bundle=FIXTURE.bundle,
            audit=audit,
            execution_identity=FIXTURE.identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


def test_forged_manifest_cannot_unlock_unaligned_materials() -> None:
    """即便伪造方把材料摘要改成与改动后材料自洽的值，材料与审计的对齐仍会失败。"""
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    entries = entries_of(FIXTURE.bundle, 0)
    first = entries[0]
    entries[0] = MaterialEntry(
        purpose_label=first.purpose_label, index_key=first.index_key, value=first.value + 1
    )
    forged_bundle = replace_entries(FIXTURE.bundle, 0, entries)
    forged_manifest = FIXTURE.manifest.model_copy(
        update={
            "supplied_materials_digest": materials_digest(
                forged_bundle, spec=FIXTURE.spec, algorithm=algorithm
            )
        }
    )
    with pytest.raises(MaterialBindingError):
        verify_frozen_inputs(
            manifest=forged_manifest,
            spec=FIXTURE.spec,
            caliber=FIXTURE.caliber,
            bundle=forged_bundle,
            audit=FIXTURE.audit,
            execution_identity=FIXTURE.identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


def test_forged_commitment_and_manifest_cannot_pass() -> None:
    """同步伪造承诺里的清单摘要与清单内容，仍会因清单与审计不一致而失败。"""
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    forged_manifest_content = replace_manifest_entry(
        FIXTURE.material_manifest, 0, FIXTURE.material_manifest.entries[0].value + 1
    )
    forged_digest = manifest_digest(forged_manifest_content, algorithm=algorithm)
    audit = recommit_audit(FIXTURE.audit, manifest_digest_value=forged_digest)
    frozen = FIXTURE.manifest.model_copy(update={"material_manifest_digest": forged_digest})
    with pytest.raises(MaterialBindingError, match="审计"):
        verify_frozen_inputs(
            manifest=frozen,
            spec=FIXTURE.spec,
            caliber=FIXTURE.caliber,
            bundle=FIXTURE.bundle,
            audit=audit,
            execution_identity=FIXTURE.identity,
            material_manifest=forged_manifest_content,
            **_source_manifest_kwargs(FIXTURE),
        )


def test_manifest_digest_is_content_derived() -> None:
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    changed = replace_manifest_entry(
        FIXTURE.material_manifest, 0, FIXTURE.material_manifest.entries[0].value + 1
    )
    assert manifest_digest(changed, algorithm=algorithm) != manifest_digest(
        FIXTURE.material_manifest, algorithm=algorithm
    )


def test_material_digest_is_content_derived() -> None:
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    entries = entries_of(FIXTURE.bundle, 0)
    first = entries[0]
    entries[0] = MaterialEntry(
        purpose_label=first.purpose_label, index_key=first.index_key, value=first.value + 1
    )
    changed = replace_entries(FIXTURE.bundle, 0, entries)
    assert materials_digest(changed, spec=FIXTURE.spec, algorithm=algorithm) != materials_digest(
        FIXTURE.bundle, spec=FIXTURE.spec, algorithm=algorithm
    )


def test_build_frozen_manifest_recomputes_from_content() -> None:
    rebuilt = build_frozen_manifest(
        spec=FIXTURE.spec,
        caliber=FIXTURE.caliber,
        bundle=FIXTURE.bundle,
        audit=FIXTURE.audit,
        execution_identity=FIXTURE.identity,
        material_manifest=FIXTURE.material_manifest,
    )
    assert rebuilt == FIXTURE.manifest


# ------------------------------------------------------------------ 身份口径主链


def test_chain_requires_identifier_agreement() -> None:
    """规格里的身份标识与显式构造口径不一致时，冻结输入校验即失败。"""
    with pytest.raises(SpecIncompleteError):
        run_spec(under_test_identifier="absent@1")
    mismatched_caliber = construction_caliber(identifier="absent@1")
    with pytest.raises(IdentityMappingError):
        verify_frozen_inputs(
            manifest=FIXTURE.manifest,
            spec=FIXTURE.spec,
            caliber=mismatched_caliber,
            bundle=FIXTURE.bundle,
            audit=FIXTURE.audit,
            execution_identity=FIXTURE.identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


def test_chain_rejects_out_of_range_material_key() -> None:
    """协议域放宽到超过 32 字节时，身份相关的主键约束仍须拦下越界材料。"""
    with pytest.raises(IdentityMappingError):
        build_fixture(under_test_bits=264, under_test_value=1 << 256)


def test_caliber_content_is_bound_by_its_own_digest() -> None:
    """构造口径被替换、执行身份摘要照着重算时，仍会因口径摘要不符而失败。"""
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    forged = construction_caliber(SeatScope.ALL_SEATS)
    identity = build_execution_identity_record(
        caliber_categories(
            forged,
            FIXTURE.spec,
            FIXTURE.bundle,
            FIXTURE.audit,
            FIXTURE.material_manifest,
            FIXTURE.source_manifests,
        )
    )
    manifest = FIXTURE.manifest.model_copy(
        update={
            "execution_identity_digest": execution_identity_digest(
                identity, algorithm=algorithm
            )
        }
    )
    with pytest.raises(FreezeBindingError, match="construction-caliber-digest"):
        verify_frozen_inputs(
            manifest=manifest,
            spec=FIXTURE.spec,
            caliber=forged,
            bundle=FIXTURE.bundle,
            audit=FIXTURE.audit,
            execution_identity=identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


def test_execution_identity_caliber_must_match_current_caliber() -> None:
    """执行身份里的实例化口径与当前构造口径逐项不一致时必须失败。"""
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    categories = caliber_categories(
        FIXTURE.caliber,
        FIXTURE.spec,
        FIXTURE.bundle,
        FIXTURE.audit,
        FIXTURE.material_manifest,
        FIXTURE.source_manifests,
    )
    entries = categories[INSTANTIATION_CALIBER_CATEGORY]
    forged_values = [
        (name, "0" * 64) if name == "construction-plan-digest" else (name, value)
        for name, value in entries
    ]
    identity = build_execution_identity_record(
        {**categories, INSTANTIATION_CALIBER_CATEGORY: forged_values}
    )
    manifest = FIXTURE.manifest.model_copy(
        update={
            "execution_identity_digest": execution_identity_digest(
                identity, algorithm=algorithm
            )
        }
    )
    with pytest.raises(IdentityMappingError, match="实例化口径"):
        verify_frozen_inputs(
                manifest=manifest,
                spec=FIXTURE.spec,
                caliber=FIXTURE.caliber,
                bundle=FIXTURE.bundle,
                audit=FIXTURE.audit,
                execution_identity=identity,
                material_manifest=FIXTURE.material_manifest,
                **_source_manifest_kwargs(FIXTURE),
            )


def test_conflicting_baseline_caliber_fails_end_to_end() -> None:
    """基线口径声明公开摘要与座位范围时，冻结输入校验必须在身份口径主链入口硬失败。"""
    with pytest.raises(IdentityMappingError):
        verify_frozen_inputs(
            manifest=FIXTURE.manifest,
            spec=FIXTURE.spec,
            caliber=conflicting_baseline_caliber(),
            bundle=FIXTURE.bundle,
            audit=FIXTURE.audit,
            execution_identity=FIXTURE.identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("baseline-effective-samples", "1"),
        ("baseline-entry-code-digest", "0" * 64),
    ],
)
def test_forged_baseline_execution_entry_fails(name: str, value: str) -> None:
    """基线执行口径的任一项被改写、其余摘要照着重算时，仍必须失败。"""
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    identity = build_execution_identity_record(
        forged_caliber_categories(
            FIXTURE.caliber,
            FIXTURE.spec,
            FIXTURE.bundle,
            FIXTURE.audit,
            FIXTURE.material_manifest,
            FIXTURE.source_manifests,
            name=name,
            value=value,
        )
    )
    manifest = FIXTURE.manifest.model_copy(
        update={
            "execution_identity_digest": execution_identity_digest(
                identity, algorithm=algorithm
            )
        }
    )
    with pytest.raises(IdentityMappingError, match="实例化口径"):
        verify_frozen_inputs(
            manifest=manifest,
            spec=FIXTURE.spec,
            caliber=FIXTURE.caliber,
            bundle=FIXTURE.bundle,
            audit=FIXTURE.audit,
            execution_identity=identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


def test_placeholder_identity_categories_are_not_enough() -> None:
    """只满足类别的结构要求不再足够：实例化口径必须与当前口径一致。"""
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    identity = build_execution_identity_record(identity_categories())
    manifest = FIXTURE.manifest.model_copy(
        update={
            "execution_identity_digest": execution_identity_digest(
                identity, algorithm=algorithm
            )
        }
    )
    with pytest.raises(IdentityMappingError, match="实例化口径"):
        verify_frozen_inputs(
            manifest=manifest,
            spec=FIXTURE.spec,
            caliber=FIXTURE.caliber,
            bundle=FIXTURE.bundle,
            audit=FIXTURE.audit,
            execution_identity=identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


@pytest.mark.parametrize(
    ("category", "name"),
    [
        ("randomization-protocol", "randomization-protocol-digest"),
        ("randomization-protocol", "supplied-materials-digest"),
        ("randomization-protocol", "material-manifest-digest"),
        ("randomization-protocol", "audit-transcript-digest"),
        ("randomization-protocol", "audit-read-record-digest"),
        ("randomization-protocol", "audit-commitment-digest"),
        ("randomization-protocol", "generator-code-digest"),
        ("input-mapping", "campaign-configuration-digest"),
        ("input-mapping", "schedule-digest"),
        ("runner", "runner-code-manifest-digest"),
        ("engine-and-strategy-code", "engine-code-manifest-digest"),
        ("engine-and-strategy-code", "baseline-strategy-code-manifest-digest"),
        ("engine-and-strategy-code", "under-test-strategy-code-manifest-digest"),
        ("engine-and-strategy-code", "verification-code-manifest-digest"),
    ],
)
def test_placeholder_execution_identity_digest_cannot_pass_main_chain(
    category: str, name: str
) -> None:
    """占位摘要即使其余条目与当前输入一致，也不能通过冻结输入主链。"""
    categories = caliber_categories(
        FIXTURE.caliber,
        FIXTURE.spec,
        FIXTURE.bundle,
        FIXTURE.audit,
        FIXTURE.material_manifest,
        FIXTURE.source_manifests,
    )
    placeholder = "ab" * 32
    assert dict(categories[category])[name] != placeholder
    categories[category] = [
        (entry_name, placeholder if entry_name == name else entry_value)
        for entry_name, entry_value in categories[category]
    ]
    identity = build_execution_identity_record(categories)
    with pytest.raises(IdentityMappingError, match="当前输入"):
        verify_frozen_inputs(
            manifest=FIXTURE.manifest,
            spec=FIXTURE.spec,
            caliber=FIXTURE.caliber,
            bundle=FIXTURE.bundle,
            audit=FIXTURE.audit,
            execution_identity=identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_interface_id", "test-source-interface"),
        ("environment_record", "test-environment"),
    ],
)
def test_identity_source_and_environment_must_match_current_protocol(
    field: str, value: str
) -> None:
    """来源接口与环境记录必须等于当前协议；只改一侧时主链失败。"""
    protocol = FIXTURE.spec.protocol.model_copy(update={field: value})
    spec = FIXTURE.spec.model_copy(update={"protocol": protocol})
    audit = AuditedMaterials(
        transcript=FIXTURE.audit.transcript,
        reads=FIXTURE.audit.reads,
        commitment=FIXTURE.audit.commitment.model_copy(update={field: value}),
    )
    with pytest.raises(IdentityMappingError, match="当前输入"):
        verify_frozen_inputs(
            manifest=FIXTURE.manifest,
            spec=spec,
            caliber=FIXTURE.caliber,
            bundle=FIXTURE.bundle,
            audit=audit,
            execution_identity=FIXTURE.identity,
            material_manifest=FIXTURE.material_manifest,
            **_source_manifest_kwargs(FIXTURE),
        )


def test_execution_identity_digest_is_content_derived() -> None:
    algorithm = FIXTURE.spec.protocol.digest_algorithm
    categories = identity_categories()
    runner_entries = categories[EXECUTION_IDENTITY_CATEGORIES[0]]
    categories[EXECUTION_IDENTITY_CATEGORIES[0]] = [
        (name, "c" * 64 if name == "runner-code-manifest-digest" else value)
        for name, value in runner_entries
    ]
    other = build_execution_identity_record(categories)
    assert execution_identity_digest(other, algorithm=algorithm) != execution_identity_digest(
        FIXTURE.identity, algorithm=algorithm
    )


# ------------------------------------------------------------------ 执行身份记录


def test_execution_identity_record_requires_all_categories() -> None:
    record = build_execution_identity_record(identity_categories())
    assert [name for name, _ in record.categories] == list(EXECUTION_IDENTITY_CATEGORIES)
    assert record.reference_snapshot == reference_snapshot()
    assert len(record.entries_for(EXECUTION_IDENTITY_CATEGORIES[0])) == 3


def test_execution_identity_record_rejects_incomplete_input() -> None:
    categories = identity_categories()
    missing = dict(categories)
    del missing[EXECUTION_IDENTITY_CATEGORIES[0]]
    with pytest.raises(SpecIncompleteError):
        build_execution_identity_record(missing)

    extra = {**categories, "extra-category": [("entry", "value")]}
    with pytest.raises(SpecIncompleteError):
        build_execution_identity_record(extra)

    empty = {**categories, EXECUTION_IDENTITY_CATEGORIES[1]: []}
    with pytest.raises(SpecIncompleteError):
        build_execution_identity_record(empty)


def test_execution_identity_record_rejects_foreign_snapshot() -> None:
    fields = build_execution_identity_record(identity_categories()).model_dump()
    fields["reference_snapshot"] = {"reference_version": 99}
    with pytest.raises(SpecIncompleteError):
        ExecutionIdentityRecord.model_validate(fields)


def test_execution_identity_record_rejects_unknown_category_lookup() -> None:
    record = build_execution_identity_record(identity_categories())
    with pytest.raises(SpecIncompleteError):
        record.entries_for("unknown-category")


# ------------------------------------------------------------------ 输出结构


def test_paired_output_carries_only_nets_and_locators() -> None:
    record = PairedHandRecord(
        hand_ordinal=1, button=2, probed_seat=1, under_test_net=10, baseline_net=-10
    )
    metadata = build_run_metadata(
        spec=FIXTURE.spec,
        manifest=FIXTURE.manifest,
        execution_identity=FIXTURE.identity,
        records=(record,),
    )
    output = PairedRunOutput(hands=(record,), metadata=metadata)
    assert set(record.model_dump()) == {
        "hand_ordinal",
        "button",
        "probed_seat",
        "under_test_net",
        "baseline_net",
    }
    assert output.metadata.spec_digest == FIXTURE.manifest.spec_digest
    assert output.metadata.material_manifest_digest == (
        FIXTURE.manifest.material_manifest_digest
    )


def test_paired_output_requires_consistent_hand_count() -> None:
    record = PairedHandRecord(
        hand_ordinal=1, button=2, probed_seat=1, under_test_net=10, baseline_net=-10
    )
    metadata = build_run_metadata(
        spec=FIXTURE.spec,
        manifest=FIXTURE.manifest,
        execution_identity=FIXTURE.identity,
        records=(record,),
    )
    with pytest.raises(VerificationError):
        PairedRunOutput(
            hands=(record,), metadata=metadata.model_copy(update={"hand_count": 2})
        )
    with pytest.raises(VerificationError):
        PairedRunOutput(hands=(), metadata=metadata)


def test_paired_output_requires_distinct_hand_ordinals() -> None:
    record = PairedHandRecord(
        hand_ordinal=1, button=2, probed_seat=1, under_test_net=10, baseline_net=-10
    )
    duplicate = PairedHandRecord(
        hand_ordinal=1, button=0, probed_seat=0, under_test_net=0, baseline_net=0
    )
    metadata = build_run_metadata(
        spec=FIXTURE.spec,
        manifest=FIXTURE.manifest,
        execution_identity=FIXTURE.identity,
        records=(record, duplicate),
    )
    with pytest.raises(VerificationError):
        PairedRunOutput(hands=(record, duplicate), metadata=metadata)
