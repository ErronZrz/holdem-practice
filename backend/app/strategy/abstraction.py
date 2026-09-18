"""受控抽象投影、覆盖判定与回退来源声明。

本模块只交付契约与判定：把局面抽象成受控信息集键，并如实判断该键是否落在训练抽象内。
抽象键的字符串格式对齐离线训练器的既有格式，但格式由本模块的本地常量定义与校验，
既不导入训练器代码，也不把训练器包加入后端依赖。

边界：
- 「抽象外」「版本不匹配」「不完整信息集」是三个彼此独立的显式结论；任何情况下都不静默
  回退，也不用最近桶、补零或掩码近似；
- 本模块不实现回退动作，只声明回退来源；也不实现任何 lookup 或产物加载。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.poker.state import GameState
from app.strategy.projection import project_for_actor
from app.strategy.registry import known_identifiers

# 抽象键的前缀、版本与根历史：格式对齐训练器的既有键，但以后端本地常量为准。
ABSTRACTION_KEY_PREFIX = "m8"
ABSTRACTION_GAME_VERSION = "m8-a-v1"
ABSTRACTION_ROOT_HISTORY = "-"
# 训练抽象覆盖的人数；引擎支持更多人数，但只有这些人数的抽象是被训练覆盖的。
ABSTRACTION_TRAINED_PLAYER_COUNTS = frozenset({6, 7, 9})
# 抽象规则允许的公开动作 token。
ABSTRACTION_ACTIONS = frozenset({"x", "b", "c", "f"})
# 受控抽象投影的字段集：新增或删减字段都属于契约变更，必须同步更新文档与测试。
ABSTRACTION_PROJECTION_FIELDS = (
    "game_version",
    "player_count",
    "relative_actor",
    "own_rank",
    "canonical_public_history",
)

COVERAGE_IN_ABSTRACTION = "in-abstraction"
COVERAGE_OUT_OF_ABSTRACTION = "out-of-abstraction"
COVERAGE_INCOMPLETE_INFOSET = "incomplete-infoset"
COVERAGE_VERSION_MISMATCH = "version-mismatch"

CoverageStatus = Literal[
    "in-abstraction",
    "out-of-abstraction",
    "incomplete-infoset",
    "version-mismatch",
]

# 契约默认的回退来源：必须是受控注册表内的规范标识，不新增策略命名体系。
DEFAULT_FALLBACK_IDENTIFIER = "heuristic@1"
# 回退来源标注：表明回退来自契约声明，而不是某个已落地的动作实现。
FALLBACK_SOURCE_DECLARED_CONTRACT = "declared-contract"


class AbstractionContractError(ValueError):
    """抽象投影契约被违反（类型错误等结构性非法输入）。"""


class IncompleteInfosetError(AbstractionContractError):
    """构造信息集键所需的字段不完整。"""


class OutOfAbstractionError(AbstractionContractError):
    """输入齐备但落在训练抽象之外。"""


class VersionMismatchError(AbstractionContractError):
    """抽象版本与受支持版本不一致。"""


class FallbackSourceError(AbstractionContractError):
    """声明的回退来源不在受控注册表内。"""


class _FrozenModel(BaseModel):
    """本模块全部对外模型的公共基类：冻结、禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class AbstractProjection(_FrozenModel):
    """受控抽象投影：构造信息集键所需的五项输入。

    相对行动者是抽象内的相对座位（首个行动者为 0），不是引擎的绝对 seat、按钮或盲位；
    任何其他座位暗牌、未公开公共牌、真实牌面、运行中 seed 与对手内部参数都不在其中。
    """

    game_version: str
    player_count: int
    relative_actor: int
    own_rank: int
    canonical_public_history: str


class CoverageVerdict(_FrozenModel):
    """覆盖判定结果：四种取值彼此独立，抽象外不产生键。"""

    coverage: CoverageStatus
    abstraction_key: str | None = None
    projection: AbstractProjection | None = None
    reasons: tuple[str, ...] = ()

    @property
    def is_in_abstraction(self) -> bool:
        """是否落在训练抽象内。"""
        return self.coverage == COVERAGE_IN_ABSTRACTION


class FallbackDeclaration(_FrozenModel):
    """回退来源声明：只标注回退来源与触发依据，不承载任何动作实现。"""

    fallback_identifier: str
    triggering_coverage: CoverageStatus
    abstraction_key: str | None = None
    reasons: tuple[str, ...] = ()
    source: str = FALLBACK_SOURCE_DECLARED_CONTRACT
    is_exact_solution: bool = False

    @field_validator("fallback_identifier")
    @classmethod
    def _source_must_be_registered(cls, value: str) -> str:
        """回退来源必须是受控注册表内的规范标识，避免出现未受控的兜底策略。"""
        if value not in known_identifiers():
            raise ValueError(f"回退来源不在受控注册表内：{value!r}")
        return value

    @field_validator("triggering_coverage")
    @classmethod
    def _reject_in_abstraction(cls, value: str) -> str:
        """抽象内不需要回退，为它声明来源属于自相矛盾。"""
        if value == COVERAGE_IN_ABSTRACTION:
            raise ValueError("抽象内不产生回退声明")
        return value

    @field_validator("is_exact_solution")
    @classmethod
    def _never_exact(cls, value: bool) -> bool:
        """回退不是精确解，从结构上禁止把它标注成精确。"""
        if value:
            raise ValueError("回退不是精确解，不得标记为精确")
        return value


def _require_str(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise AbstractionContractError(f"{name} 必须是字符串，收到 {type(value).__name__}")


def _require_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AbstractionContractError(f"{name} 必须是整数，收到 {type(value).__name__}")


def build_abstract_projection(
    game_version: str,
    player_count: int,
    relative_actor: int,
    own_rank: int,
    canonical_public_history: str,
) -> AbstractProjection:
    """按契约构造抽象投影；结构性非法输入明确失败，不做任何类型转换。"""
    _require_str("game_version", game_version)
    _require_int("player_count", player_count)
    _require_int("relative_actor", relative_actor)
    _require_int("own_rank", own_rank)
    _require_str("canonical_public_history", canonical_public_history)
    return AbstractProjection(
        game_version=game_version,
        player_count=player_count,
        relative_actor=relative_actor,
        own_rank=own_rank,
        canonical_public_history=canonical_public_history,
    )


def _parse_history_token(token: str, expected_actor: int) -> str | None:
    """解析单个公开动作 token；形式或行动者不符时返回 None。"""
    action, separator, seat_text = token.partition("@")
    if separator != "@" or "@" in seat_text or action not in ABSTRACTION_ACTIONS:
        return None
    if seat_text != str(expected_actor):
        return None
    return action


def _derive_decision_history(player_count: int, history: str) -> tuple[str | None, int | None]:
    """派生规范公开决策历史，返回 (拒绝原因, 行动者)。

    拒绝原因非空表示该历史不是抽象规则下的公开决策历史（可能是终局、形式不规范或
    行动顺序不可能）；此时不返回行动者。本函数只做校验与派生，不改写、不修补历史。
    """
    if player_count < 1:
        return "人数不足以拥有首个行动者", None
    if history == ABSTRACTION_ROOT_HISTORY:
        return None, 0

    if not history or history.startswith("|") or history.endswith("|") or "||" in history:
        return "公开历史不是规范形式", None

    opening_index = 0
    opener: int | None = None
    response_order: tuple[int, ...] = ()
    response_index = 0

    for token in history.split("|"):
        if opener is None:
            if opening_index >= player_count:
                return "全员行动结束后仍有多余 token", None
            action = _parse_history_token(token, opening_index)
            if action is None:
                return "token 形式或行动者与行动顺序不一致", None
            if action == "x":
                opening_index += 1
            elif action == "b":
                opener = opening_index
                response_order = tuple(
                    (opener + offset) % player_count for offset in range(1, player_count)
                )
            else:
                return "无下注阶段只允许 check 或固定开池", None
        else:
            if response_index >= len(response_order):
                return "所有回应完成后仍有多余 token", None
            action = _parse_history_token(token, response_order[response_index])
            if action is None:
                return "token 形式或行动者与回应顺序不一致", None
            if action not in ("c", "f"):
                return "固定开池后只允许 call 或 fold", None
            response_index += 1

    if opener is None:
        if opening_index >= player_count:
            return "全员 check 属于终局历史", None
        return None, opening_index
    if response_index >= len(response_order):
        return "开池回应完毕属于终局历史", None
    return None, response_order[response_index]


def _format_key(projection: AbstractProjection) -> str:
    """按冻结格式拼接抽象键。"""
    return (
        f"{ABSTRACTION_KEY_PREFIX}/{projection.game_version}"
        f"/n={projection.player_count}/actor={projection.relative_actor}"
        f"/rank={projection.own_rank}"
        f"/history={projection.canonical_public_history}"
    )


def judge_coverage(
    *,
    game_version: str | None = None,
    player_count: int | None = None,
    relative_actor: int | None = None,
    own_rank: int | None = None,
    canonical_public_history: str | None = None,
) -> CoverageVerdict:
    """判断给定输入是否落在训练抽象内。

    字段缺失记「不完整信息集」；版本不一致记「版本不匹配」；字段齐备但不在抽象范围内记
    「抽象外」。三种结论互不合并，且都不产生键，更不回退到最近的历史或最近的桶。
    """
    optional_fields = (
        ("game_version", game_version),
        ("player_count", player_count),
        ("relative_actor", relative_actor),
        ("own_rank", own_rank),
        ("canonical_public_history", canonical_public_history),
    )
    missing: list[str] = []
    for name, value in optional_fields:
        if value is None:
            missing.append(name)
            continue
        if name in ("game_version", "canonical_public_history"):
            _require_str(name, value)
        else:
            _require_int(name, value)
    if missing:
        return CoverageVerdict(
            coverage=COVERAGE_INCOMPLETE_INFOSET,
            reasons=tuple(f"缺少必需字段：{name}" for name in missing),
        )

    if game_version != ABSTRACTION_GAME_VERSION:
        return CoverageVerdict(
            coverage=COVERAGE_VERSION_MISMATCH,
            reasons=(f"抽象版本不匹配：期望 {ABSTRACTION_GAME_VERSION}，收到 {game_version!r}",),
        )

    if player_count not in ABSTRACTION_TRAINED_PLAYER_COUNTS:
        trained = ", ".join(str(count) for count in sorted(ABSTRACTION_TRAINED_PLAYER_COUNTS))
        return CoverageVerdict(
            coverage=COVERAGE_OUT_OF_ABSTRACTION,
            reasons=(f"人数 {player_count} 未被训练抽象覆盖（仅 {trained}）",),
        )

    reasons: list[str] = []
    if not 0 <= relative_actor < player_count:
        reasons.append(f"相对行动者 {relative_actor} 越界（应为 0..{player_count - 1}）")
    if not 0 <= own_rank < player_count:
        reasons.append(f"私有 rank {own_rank} 越界（应为 0..{player_count - 1}）")
    if reasons:
        return CoverageVerdict(coverage=COVERAGE_OUT_OF_ABSTRACTION, reasons=tuple(reasons))

    rejection, history_actor = _derive_decision_history(player_count, canonical_public_history)
    if rejection is not None:
        return CoverageVerdict(
            coverage=COVERAGE_OUT_OF_ABSTRACTION,
            reasons=(f"公开历史不属于该抽象：{rejection}",),
        )
    if history_actor != relative_actor:
        return CoverageVerdict(
            coverage=COVERAGE_OUT_OF_ABSTRACTION,
            reasons=(
                f"历史派生的行动者 {history_actor} 与给定相对行动者 {relative_actor} 不一致",
            ),
        )

    projection = build_abstract_projection(
        game_version=game_version,
        player_count=player_count,
        relative_actor=relative_actor,
        own_rank=own_rank,
        canonical_public_history=canonical_public_history,
    )
    return CoverageVerdict(
        coverage=COVERAGE_IN_ABSTRACTION,
        abstraction_key=_format_key(projection),
        projection=projection,
        reasons=(),
    )


def build_abstraction_key(projection: AbstractProjection) -> str:
    """按冻结格式生成抽象键；不在抽象内时明确失败，不返回近似键。"""
    verdict = judge_coverage(
        game_version=projection.game_version,
        player_count=projection.player_count,
        relative_actor=projection.relative_actor,
        own_rank=projection.own_rank,
        canonical_public_history=projection.canonical_public_history,
    )
    if not verdict.is_in_abstraction or verdict.abstraction_key is None:
        raise _error_for(verdict)
    return verdict.abstraction_key


def _error_for(verdict: CoverageVerdict) -> AbstractionContractError:
    """把判定结果转换为分类型明确异常，便于调用方区分处置。"""
    detail = "；".join(verdict.reasons) if verdict.reasons else "无附加原因"
    message = f"局面不在训练抽象内（{verdict.coverage}）：{detail}"
    if verdict.coverage == COVERAGE_INCOMPLETE_INFOSET:
        return IncompleteInfosetError(message)
    if verdict.coverage == COVERAGE_VERSION_MISMATCH:
        return VersionMismatchError(message)
    if verdict.coverage == COVERAGE_OUT_OF_ABSTRACTION:
        return OutOfAbstractionError(message)
    return AbstractionContractError(message)


def require_in_abstraction(verdict: CoverageVerdict) -> AbstractProjection:
    """要求判定为抽象内并返回投影；其余三种结论各自抛出明确异常。"""
    if verdict.is_in_abstraction and verdict.projection is not None:
        return verdict.projection
    raise _error_for(verdict)


def judge_game_state_coverage(state: GameState) -> CoverageVerdict:
    """从生产快照判断覆盖：只读行动者视角，能判的判、判不了的不假装。

    快照可可靠给出人数，因此人数不在训练抽象内时直接判为抽象外；但快照不含公开行动
    历史、相对行动者与抽象 rank，即便人数匹配也只如实记为不完整信息集。把真实局面映射
    成抽象投影属于位置与行动顺序投影、抽象映射等后续独立授权的工作，本函数不代劳，
    也不给出任何近似结论。本函数只读取行动者自己的牌与公开字段。
    """
    projected = project_for_actor(state)
    player_count = len(projected.players)
    if player_count not in ABSTRACTION_TRAINED_PLAYER_COUNTS:
        trained = ", ".join(str(count) for count in sorted(ABSTRACTION_TRAINED_PLAYER_COUNTS))
        return CoverageVerdict(
            coverage=COVERAGE_OUT_OF_ABSTRACTION,
            reasons=(f"人数 {player_count} 未被训练抽象覆盖（仅 {trained}）",),
        )
    return CoverageVerdict(
        coverage=COVERAGE_INCOMPLETE_INFOSET,
        reasons=(
            "快照不含公开行动历史，无法构造规范公开历史",
            "快照不含相对行动者，需由位置与行动顺序投影提供",
            "快照含真实牌面而非抽象 rank，需由抽象映射提供",
        ),
    )


def declared_fallback(
    verdict: CoverageVerdict,
    *,
    fallback_identifier: str = DEFAULT_FALLBACK_IDENTIFIER,
) -> FallbackDeclaration | None:
    """声明未覆盖场景的回退来源；抽象内返回 None。

    本函数只产出声明，不执行任何动作，也不改变策略分派：回退来源必须是受控注册表内的
    规范标识，声明本身恒为「非精确解」。
    """
    if verdict.is_in_abstraction:
        return None
    if fallback_identifier not in known_identifiers():
        raise FallbackSourceError(f"回退来源不在受控注册表内：{fallback_identifier!r}")
    return FallbackDeclaration(
        fallback_identifier=fallback_identifier,
        triggering_coverage=verdict.coverage,
        abstraction_key=verdict.abstraction_key,
        reasons=verdict.reasons,
    )
