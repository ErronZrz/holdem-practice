"""分布观测能力的实现：声明校验、无状态健康读取、按权重合并与定点输出。

设计目的：
- 把「直接读取动作概率质量」做成独立能力，不改动统一策略接口；
- 声明与实例化解耦：只凭规范标识即可读到能力参数，无需构造策略对象；
- 观测只读行动者可见的安全状态与合法动作集，不消耗也不推进任何随机流；
- 概率质量用定点整数表示，靠确定性取整保证总和恒定，全程不引入浮点。

失败按发生阶段分成互不合并的若干类，调用方据此分别处理，不做笼统归并。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.poker.actions import ActionType, LegalActions
from app.poker.state import GameState

from .mixed_context import MixedContextError, VerifiedMixedInput, require_mixed_input
from .mixed_features import MixedFeaturesError, features_for
from .mixed_policy import (
    MIXED_DISTRIBUTION_UNITS,
    HandMode,
    MixedCandidate,
    MixedDistribution,
    MixedPolicyError,
    MixedPolicyRules,
    build_distribution,
)
from .mixed_strategy import seat_style_map

# 能力标识与固定取值：与具体身份、对局和清单无关。
CAPABILITY_ID = "distribution-observation@1"
# 定点单位总和沿用既有混合策略的常量，避免另立一个任意数值。
PROBABILITY_UNITS = MIXED_DISTRIBUTION_UNITS
OBSERVATION_MODES: tuple[str, ...] = ("normal", "cautious", "pressed")
MODE_WEIGHTS: tuple[int, ...] = (8, 1, 1)
AMOUNT_SEMANTICS: tuple[str, ...] = (
    "bet=closed_interval_street_total",
    "raise=closed_interval_total_after_raise",
    "fold=0",
    "check=0",
    "call=0",
)

# 候选的统一排列次序：先动作类型，再金额升序。
_CANONICAL_ACTION_ORDER: tuple[ActionType, ...] = (
    ActionType.FOLD,
    ActionType.CHECK,
    ActionType.CALL,
    ActionType.BET,
    ActionType.RAISE,
)
_ACTION_ORDER_INDEX = {
    action: index for index, action in enumerate(_CANONICAL_ACTION_ORDER)
}
# 输出金额恒为零的动作类型。
_ZERO_AMOUNT_ACTIONS = frozenset({ActionType.FOLD, ActionType.CHECK, ActionType.CALL})


# ------------------------------------------------------------------ 失败类别


class DistributionObservationError(Exception):
    """分布观测相关失败的基类；子类各自对应一个可区分的类别。"""


class DeclarationMissingError(DistributionObservationError):
    """读取不到该标识的能力声明：声明缺失。"""


class DeclarationInvalidError(DistributionObservationError):
    """声明声明了支持，但字段缺失或固定取值不符。"""


class CapabilityUnavailableError(DistributionObservationError):
    """声明表明该能力不受支持；调用方据此判定，而不是解析查询结果。"""

    def __init__(self, identifier: str) -> None:
        super().__init__(f"该身份未声明支持分布观测能力：{identifier}")
        self.identifier = identifier


class IllegalObservationInputError(DistributionObservationError):
    """安全状态、合法动作集或模式覆盖不构成一次合法观测。"""


class ObservationTechnicalError(DistributionObservationError):
    """查询过程中出现内部技术故障，结果不可用于任何校验。"""


class ObservationSemanticError(DistributionObservationError):
    """构造出的观测结果不满足结构或取值约束。"""


class DeclarationBehaviourMismatchError(DistributionObservationError):
    """已通过的声明与后续可观察行为直接矛盾。"""


class CapabilityHealth(StrEnum):
    """能力整体的可用状态：只有这两个取值，不设第三类。"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


# ------------------------------------------------------------------ 能力声明


@dataclass(frozen=True)
class CapabilityDeclaration:
    """一份能力声明：参数固定，与身份、座位、节点和随机源无关。

    ``supported`` 为假时只认前两个字段，其余参数一律不读取、不比对、不据以调用；
    为真时必须齐备全部字段且每个字段取固定值，任何偏离都在读取阶段失败。
    """

    capability_id: str
    supported: bool
    probability_units: int | None = None
    modes: tuple[str, ...] | None = None
    mode_weights: tuple[int, ...] | None = None
    amount_semantics: tuple[str, ...] | None = None

    def validate(self) -> None:
        """按上述两种情形校验；不合规一律在声明读取阶段失败。"""
        if not self.supported:
            # 不支持时不得把其余参数当成可用配置，因此也不做任何比对。
            return
        if self.capability_id != CAPABILITY_ID:
            raise DeclarationInvalidError(f"能力标识不符：{self.capability_id!r}")
        if self.probability_units != PROBABILITY_UNITS:
            raise DeclarationInvalidError(f"定点单位总和不符：{self.probability_units!r}")
        if self.modes != OBSERVATION_MODES:
            raise DeclarationInvalidError(f"模式集合不符：{self.modes!r}")
        if self.mode_weights != MODE_WEIGHTS:
            raise DeclarationInvalidError(f"模式权重不符：{self.mode_weights!r}")
        if self.amount_semantics != AMOUNT_SEMANTICS:
            raise DeclarationInvalidError(f"金额语义标记不符：{self.amount_semantics!r}")


def supported_declaration() -> CapabilityDeclaration:
    """返回本能力完整合规的声明：固定取值集中在此处，避免多处抄写。"""
    return CapabilityDeclaration(
        capability_id=CAPABILITY_ID,
        supported=True,
        probability_units=PROBABILITY_UNITS,
        modes=OBSERVATION_MODES,
        mode_weights=MODE_WEIGHTS,
        amount_semantics=AMOUNT_SEMANTICS,
    )


# ------------------------------------------------------------------ 观测输出


class DistributionObservation(BaseModel):
    """一次观测的输出：口径标记、元数据与按规范次序排列的候选单位。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    probability_units: int
    mode_weights: tuple[int, ...]
    aggregation: Literal["marginalized", "mode_override"]
    overridden_mode: str | None = None
    candidates: tuple[MixedCandidate, ...]

    @model_validator(mode="after")
    def _require_well_formed(self) -> DistributionObservation:
        if self.probability_units <= 0:
            raise ObservationSemanticError("定点单位总和必须为正")
        if len(self.mode_weights) != len(OBSERVATION_MODES):
            raise ObservationSemanticError("模式权重与模式集合数量不一致")
        if any(weight <= 0 for weight in self.mode_weights):
            raise ObservationSemanticError("模式权重必须为正")
        if not self.candidates:
            raise ObservationSemanticError("观测输出不能为空")
        if self.aggregation == "marginalized":
            if self.overridden_mode is not None:
                raise ObservationSemanticError("合并口径不得携带单一模式标记")
        elif self.overridden_mode not in OBSERVATION_MODES:
            raise ObservationSemanticError("单一模式口径必须携带合法的模式标记")

        keys: list[tuple[ActionType, int]] = []
        for candidate in self.candidates:
            if candidate.action in _ZERO_AMOUNT_ACTIONS and candidate.amount != 0:
                raise ObservationSemanticError("该动作类型的输出金额必须为零")
            keys.append((candidate.action, candidate.amount))
        if len(set(keys)) != len(keys):
            raise ObservationSemanticError("同一动作类型与金额不得重复出现")
        if keys != sorted(keys, key=_canonical_key):
            raise ObservationSemanticError("候选必须按动作类型与金额的规范次序排列")
        if sum(item.units for item in self.candidates) != self.probability_units:
            raise ObservationSemanticError("候选单位总和必须恰等于定点单位总和")
        return self


def _canonical_key(key: tuple[ActionType, int]) -> tuple[int, int]:
    """候选的规范排序键：先动作类型序，再金额升序。"""
    return (_ACTION_ORDER_INDEX[key[0]], key[1])


# ------------------------------------------------------------------ 合并算术


def marginalize(
    per_mode: Mapping[str, MixedDistribution],
    modes: Sequence[str] = OBSERVATION_MODES,
    weights: Sequence[int] = MODE_WEIGHTS,
) -> tuple[MixedCandidate, ...]:
    """把逐模式的条件分布按固定整数权重合并，并做确定性取整。

    取整先把精确值向下取整，再把剩余单位按小数余数降序逐一加一；余数相同者按候选的
    规范次序决定先后。同一输入必得同一输出，不引入随机，也不依赖浮点。
    """
    if not modes or len(modes) != len(weights):
        raise ObservationSemanticError("模式与权重必须一一对应且非空")
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ObservationSemanticError("模式权重总和必须为正")

    numerators: dict[tuple[ActionType, int], int] = {}
    for mode, weight in zip(modes, weights, strict=True):
        distribution = per_mode.get(mode)
        if distribution is None:
            raise ObservationSemanticError(f"缺少模式 {mode!r} 的条件分布")
        if not distribution.candidates:
            raise ObservationSemanticError(f"模式 {mode!r} 未覆盖任何候选")
        for candidate in distribution.candidates:
            key = (candidate.action, candidate.amount)
            numerators[key] = numerators.get(key, 0) + weight * candidate.units

    units = {key: value // total_weight for key, value in numerators.items()}
    remainders = {key: value % total_weight for key, value in numerators.items()}
    leftover = PROBABILITY_UNITS - sum(units.values())
    if leftover < 0:
        raise ObservationSemanticError("合并后的整数单位已超过总量")
    ranked = sorted(
        (key for key in numerators if remainders[key] > 0),
        key=lambda key: (-remainders[key], _canonical_key(key)),
    )
    if leftover > len(ranked):
        raise ObservationSemanticError("剩余单位无法按余数分配完")
    for key in ranked[:leftover]:
        units[key] += 1

    total = 0
    for key, numerator in numerators.items():
        # 用整数比较代替除法：偏差小于一个单位等价于该不等式成立。
        if abs(units[key] * total_weight - numerator) >= total_weight:
            raise ObservationSemanticError("取整偏差超出一个定点单位")
        total += units[key]
    if total != PROBABILITY_UNITS:
        raise ObservationSemanticError("定点单位总和必须恰为常量")

    return tuple(
        MixedCandidate(action=key[0], amount=key[1], units=units[key])
        for key in sorted(numerators, key=_canonical_key)
    )


# ------------------------------------------------------------------ 观测入口


def _require_mode_override(mode: HandMode | str | None) -> str | None:
    """模式覆盖只允许受支持的模式或未指定，其它取值不构成合法观测。"""
    if mode is None:
        return None
    name = mode.value if isinstance(mode, HandMode) else mode
    if name not in OBSERVATION_MODES:
        raise IllegalObservationInputError(f"模式覆盖取值不受支持：{mode!r}")
    return name


def _require_coherent_legal_actions(legal: LegalActions) -> None:
    """拒绝自相矛盾或区间不成立的合法动作集：这类输入没有可观测局面。"""
    if legal.can_check and legal.can_call:
        raise IllegalObservationInputError("可过牌与可跟注同时为真")
    if legal.can_bet and legal.can_raise:
        raise IllegalObservationInputError("可下注与可加注同时为真")
    if legal.can_bet and legal.call_amount != 0:
        raise IllegalObservationInputError("可下注时不应存在待跟注额")
    for flag, low, high in (
        (legal.can_bet, legal.min_bet, legal.max_bet),
        (legal.can_raise, legal.min_raise_to, legal.max_raise_to),
    ):
        if flag and not 0 < low <= high:
            raise IllegalObservationInputError("主动动作的合法区间不合法")


def _verified_input(state: GameState) -> VerifiedMixedInput:
    """校验安全状态；不完整、越界或泄漏他人底牌的输入不构成可观测局面。"""
    try:
        return require_mixed_input(state)
    except MixedContextError as error:
        raise IllegalObservationInputError(f"安全状态不可用于观测：{error}") from error


@dataclass(frozen=True)
class DistributionObservationEntry:
    """绑定某个身份的观测句柄：只依赖该身份的口径，不持有任何对局状态。"""

    identifier: str
    declaration: CapabilityDeclaration
    rules: MixedPolicyRules

    def observe(
        self,
        state: GameState,
        legal: LegalActions,
        mode: HandMode | str | None = None,
    ) -> DistributionObservation:
        """给出本次局面的观测结果：未指定模式时返回合并口径，指定时返回单一模式。"""
        override = _require_mode_override(mode)
        verified = _verified_input(state)
        _require_coherent_legal_actions(legal)
        try:
            features = features_for(verified, legal)
        except (MixedContextError, MixedFeaturesError) as error:
            raise IllegalObservationInputError(f"输入不构成可观测局面：{error}") from error

        styles = seat_style_map(verified.context.bot_seats)
        style = styles.get(verified.actor_seat)
        if style is None:
            raise IllegalObservationInputError("当前行动者不在该身份的座位集合内")

        try:
            per_mode = {
                name: build_distribution(features, legal, style, HandMode(name), self.rules)
                for name in OBSERVATION_MODES
            }
        except MixedPolicyError as error:
            raise ObservationTechnicalError(f"分布构造失败：{error}") from error

        if override is None:
            observation = DistributionObservation(
                probability_units=PROBABILITY_UNITS,
                mode_weights=MODE_WEIGHTS,
                aggregation="marginalized",
                candidates=marginalize(per_mode),
            )
        else:
            observation = DistributionObservation(
                probability_units=PROBABILITY_UNITS,
                mode_weights=MODE_WEIGHTS,
                aggregation="mode_override",
                overridden_mode=override,
                candidates=per_mode[override].candidates,
            )

        _require_legal_conformance(observation, legal)
        _require_matching_declaration(observation, self.declaration)
        return observation


def _require_legal_conformance(
    observation: DistributionObservation, legal: LegalActions
) -> None:
    """确认输出的动作类型与金额都落在该节点的合法动作集与其闭区间内。"""
    allowed = {
        ActionType.FOLD: legal.can_fold,
        ActionType.CHECK: legal.can_check,
        ActionType.CALL: legal.can_call,
        ActionType.BET: legal.can_bet,
        ActionType.RAISE: legal.can_raise,
    }
    intervals = {
        ActionType.BET: (legal.min_bet, legal.max_bet),
        ActionType.RAISE: (legal.min_raise_to, legal.max_raise_to),
    }
    for candidate in observation.candidates:
        action = candidate.action
        if not allowed[action]:
            raise ObservationSemanticError(f"输出了合法动作集之外的候选：{action.value}")
        bounds = intervals.get(action)
        if bounds is not None and not bounds[0] <= candidate.amount <= bounds[1]:
            raise ObservationSemanticError(f"候选金额超出闭区间：{action.value}")


def _require_matching_declaration(
    observation: DistributionObservation, declaration: CapabilityDeclaration
) -> None:
    """确认输出的两项元数据与已通过的声明逐项一致。"""
    if observation.probability_units != declaration.probability_units:
        raise DeclarationBehaviourMismatchError("输出的定点单位总和与声明不一致")
    if observation.mode_weights != declaration.mode_weights:
        raise DeclarationBehaviourMismatchError("输出的模式权重与声明不一致")


# ------------------------------------------------------------------ 登记与读取

_ENTRIES: dict[str, DistributionObservationEntry] = {}


def register_observation_entry(
    identifier: str,
    declaration: CapabilityDeclaration,
    rules: MixedPolicyRules,
) -> None:
    """按规范标识登记一份声明与观测入口；重复登记视为配置错误。"""
    if identifier in _ENTRIES:
        raise ValueError(f"该标识已登记分布观测能力：{identifier}")
    _ENTRIES[identifier] = DistributionObservationEntry(
        identifier=identifier, declaration=declaration, rules=rules
    )


def declaration_for(identifier: str) -> CapabilityDeclaration:
    """按规范标识读取能力声明；声明不合规在此处即失败，不进入任何查询。"""
    entry = _entry_for(identifier)
    entry.declaration.validate()
    return entry.declaration


def entry_for(identifier: str) -> DistributionObservationEntry:
    """按规范标识取观测句柄；声明不合规时同样在读取阶段失败。"""
    entry = _entry_for(identifier)
    entry.declaration.validate()
    if not entry.declaration.supported:
        raise CapabilityUnavailableError(identifier)
    return entry


def health_status() -> CapabilityHealth:
    """无状态能力健康读取：不接受任何输入，也不读取对局状态。"""
    return CapabilityHealth.AVAILABLE if _ENTRIES else CapabilityHealth.UNAVAILABLE


def _entry_for(identifier: str) -> DistributionObservationEntry:
    entry = _ENTRIES.get(identifier)
    if entry is None:
        raise DeclarationMissingError(f"该标识未登记分布观测能力：{identifier!r}")
    return entry
