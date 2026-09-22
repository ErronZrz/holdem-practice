"""新 Bot 的规则策略层：固定风格参数、整数尺寸候选、危险尺度保护与联合分布。

规则来源与口径：
- 所有分数是 0–1000 的规则评分，不是概率、不是 EV；
- 候选一律为「动作类型 + 本街总额」，先夹紧、去重、合并偏好，再算质量；
- 危险尺度按最终实际金额判定，不靠「小注」标签绕过保护；
- 概率用精确有理数归一后量化到独立的一百万单位。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.state import Street

from .mixed_features import MixedFeatures, clip

# 分布单位：只服务新策略内部，与训练产物的概率单位互不影响。
MIXED_DISTRIBUTION_UNITS = 1_000_000
MIXED_DISTRIBUTION_SCHEMA_VERSION = "mixed-distribution.v1"

# 免费过牌与人格倍率的统一百分刻度。
_PERCENT = 100
_CHECK_RAW_WEIGHT = 200
# 危险尺度：一次投入超过该倍数的底池（或大盲）即视为压迫性尺度。
_DANGEROUS_POT_MULTIPLE = 3
# 危险尺度仍可保留所需的评分门槛。
_DANGEROUS_SCORE_STRONG = 850
_DANGEROUS_SCORE_SHORT = 550
# 人数风险惩罚：每多一名未弃牌对手。
_CONTENDER_PENALTY = 35
# 跟注阈值的价格项权重：后翻后固定，翻前由规则口径给出。
_PREFLOP_PRICE_WEIGHT = 450
_POSTFLOP_PRICE_WEIGHT = 450
# 连续进攻的封顶计数。
_AGGRESSION_CAP = 3
_SEAT_COUNT_FOR_U = {1: 12, 2: 6, 3: 3}


class MixedPolicyError(ValueError):
    """合法动作自相矛盾、参数越界或分布退化时抛出。"""


@dataclass(frozen=True)
class PreflopCallBonus:
    """仅作用于翻前跟注分支的风格偏移；价值主动分支不受它影响。

    字段名与风格取值一一对应，因此可直接按风格取值取出对应偏移。
    """

    tight: int = 0
    aggressive: int = 0
    calling: int = 0


@dataclass(frozen=True)
class MixedPolicyRules:
    """一版规则口径的开关集合：新旧身份共用实现，但分布互不影响。

    翻前三项取值都写进口径对象，使配置摘要能覆盖它们；首版与第二版取默认值，
    因此分布逐位不变。
    """

    # 锁定平分局面按分池口径处理：免除人数惩罚，并按共同分割底池的人数折减跟注价格。
    shared_board_chop_caliber: bool = False
    # 翻前跟注阈值的价格项权重；后翻后另用固定权重。
    preflop_price_weight: int = _PREFLOP_PRICE_WEIGHT
    # 翻前每多一名未弃牌对手的评分惩罚。
    preflop_contender_penalty: int = _CONTENDER_PENALTY
    # 翻前仅作用于跟注分支的风格偏移。
    preflop_call_bonus: PreflopCallBonus = PreflopCallBonus()


# 首版口径：共享牌面封顶后仍按普通跟注处理。
MIXED_LOCAL_V1_RULES = MixedPolicyRules()
# 第二版口径：锁定平分局面改用分池口径。
MIXED_LOCAL_V2_RULES = MixedPolicyRules(shared_board_chop_caliber=True)
# 第三版口径：在第二版基础上放宽翻前跟注门槛，并让三档风格在翻前分开。
MIXED_LOCAL_V3_RULES = MixedPolicyRules(
    shared_board_chop_caliber=True,
    preflop_price_weight=150,
    preflop_contender_penalty=30,
    preflop_call_bonus=PreflopCallBonus(tight=0, aggressive=35, calling=110),
)
# 第四版口径：只把紧密型的翻前跟注偏移提高，其余取值与第三版逐字一致。
MIXED_LOCAL_V4_RULES = MixedPolicyRules(
    shared_board_chop_caliber=True,
    preflop_price_weight=150,
    preflop_contender_penalty=30,
    preflop_call_bonus=PreflopCallBonus(tight=30, aggressive=35, calling=110),
)


class MixedStyle(StrEnum):
    """首期三种基础风格；名称不是强度认证。"""

    TIGHT = "tight"
    AGGRESSIVE = "aggressive"
    CALLING = "calling"


# Bot 座位升序按该顺序循环分配风格。
MIXED_STYLE_ORDER: tuple[MixedStyle, ...] = (
    MixedStyle.TIGHT,
    MixedStyle.AGGRESSIVE,
    MixedStyle.CALLING,
)


class HandMode(StrEnum):
    """每手一次的隐变量：只改变受控幅度，不改变合法集与安全排除项。"""

    NORMAL = "normal"
    CAUTIOUS = "cautious"
    PRESSED = "pressed"


# 手模式由 [0,100) 均匀整数分区决定，一手内固定。
HAND_MODE_ROLL_BOUNDS = (80, 90, 100)
_MODE_SCORE_OFFSET = {HandMode.NORMAL: 0, HandMode.CAUTIOUS: -15, HandMode.PRESSED: 15}
_MODE_AGGRESSION_PERCENT = {HandMode.NORMAL: 100, HandMode.CAUTIOUS: 85, HandMode.PRESSED: 115}


@dataclass(frozen=True)
class StyleParameters:
    """一种风格的固定参数：评分偏移、被动/主动倍率与尺度偏好。"""

    looseness: int
    fold_percent: int
    call_percent: int
    aggression_percent: int
    size_preferences: tuple[int, int, int, int]


STYLE_PARAMETERS: dict[MixedStyle, StyleParameters] = {
    MixedStyle.TIGHT: StyleParameters(
        looseness=-35,
        fold_percent=130,
        call_percent=90,
        aggression_percent=90,
        size_preferences=(5, 4, 1, 1),
    ),
    MixedStyle.AGGRESSIVE: StyleParameters(
        looseness=35,
        fold_percent=85,
        call_percent=110,
        aggression_percent=140,
        size_preferences=(3, 5, 3, 2),
    ),
    MixedStyle.CALLING: StyleParameters(
        looseness=10,
        fold_percent=70,
        call_percent=150,
        aggression_percent=60,
        size_preferences=(6, 3, 1, 1),
    ),
}


def hand_mode_for(roll: int) -> HandMode:
    """把 [0,100) 的均匀整数映射到三种手模式。"""
    if not 0 <= roll < 100:
        raise MixedPolicyError(f"手模式取值必须落在 [0,100)，收到 {roll}")
    normal, cautious, _ = HAND_MODE_ROLL_BOUNDS
    if roll < normal:
        return HandMode.NORMAL
    if roll < cautious:
        return HandMode.CAUTIOUS
    return HandMode.PRESSED


class MixedCandidate(BaseModel):
    """一个受控候选：动作类型、本街总额与非负整数单位。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ActionType
    amount: int = Field(ge=0)
    units: int = Field(ge=0)


class MixedDistribution(BaseModel):
    """冻结的联合分布：候选按规范顺序排列，总单位恰等于一百万。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["mixed-distribution.v1"] = MIXED_DISTRIBUTION_SCHEMA_VERSION
    candidates: tuple[MixedCandidate, ...]

    @model_validator(mode="after")
    def _require_normalized(self) -> MixedDistribution:
        if not self.candidates:
            raise MixedPolicyError("分布不能为空")
        if sum(item.units for item in self.candidates) != MIXED_DISTRIBUTION_UNITS:
            raise MixedPolicyError("分布单位总和必须恰等于一百万")
        keys = [(item.action, item.amount) for item in self.candidates]
        if len(set(keys)) != len(keys):
            raise MixedPolicyError("分布中不允许出现重复的候选")
        return self

    def sample(self, rng: random.Random) -> Action:
        """按规范顺序的累计区间抽样；零单位项不会被抽到。"""
        roll = rng.randrange(MIXED_DISTRIBUTION_UNITS)
        cumulative = 0
        for candidate in self.candidates:
            cumulative += candidate.units
            if candidate.units and roll < cumulative:
                return Action(candidate.action, candidate.amount)
        raise MixedPolicyError("分布未覆盖抽样区间")


def build_distribution(
    features: MixedFeatures,
    legal: LegalActions,
    style: MixedStyle,
    mode: HandMode,
    rules: MixedPolicyRules = MIXED_LOCAL_V1_RULES,
) -> MixedDistribution:
    """按固定规则计算当前局面的联合动作/尺度分布。"""
    _require_coherent_legal(legal)
    parameters = STYLE_PARAMETERS[style]
    score = _score(features, parameters, mode, rules)

    depth = 0
    if features.spr_at_most(1):
        depth = -40
    elif features.spr_at_least(6):
        depth = 25
    aggression_penalty = 25 * features.recent_aggression
    is_preflop = features.street is Street.PREFLOP
    price_weight = rules.preflop_price_weight if is_preflop else _POSTFLOP_PRICE_WEIGHT
    call_price = features.price
    if rules.shared_board_chop_caliber and features.shared_board_locked:
        # 锁定平分局面上底池要与在场者共同分割，跟注价格按人数折减。
        call_price = features.price // (features.contenders + 1)
    call_threshold = (310 if is_preflop else 350) + (
        price_weight * call_price
    ) // 1000 + aggression_penalty + depth
    value_threshold = _VALUE_THRESHOLDS[features.street] + aggression_penalty + depth

    # 翻前风格偏移只作用于被动分支：价值主动质量仍按未偏移的评分计算。
    passive_score = score + (_preflop_call_bonus(rules, style) if is_preflop else 0)
    fold_weight = max(0, call_threshold - passive_score + 160) * parameters.fold_percent
    call_weight = max(0, passive_score - call_threshold + 160) * parameters.call_percent
    value_quality = max(0, score - value_threshold + 120)
    bluff_quality = _non_value_quality(features)
    aggression_scale = Fraction(
        parameters.aggression_percent * _MODE_AGGRESSION_PERCENT[mode], _PERCENT
    )

    active = _active_candidates(
        features, legal, score, value_quality, bluff_quality, parameters.size_preferences
    )
    total_active_preference = sum(preference for _, preference in active)

    weights: list[tuple[ActionType, int, Fraction]] = []
    if legal.can_fold:
        weights.append((ActionType.FOLD, 0, Fraction(fold_weight)))
    if legal.can_check:
        weights.append((ActionType.CHECK, 0, Fraction(_CHECK_RAW_WEIGHT * _PERCENT)))
    if legal.can_call:
        weights.append((ActionType.CALL, 0, Fraction(call_weight)))
    for (action_type, amount, quality), preference in active:
        share = Fraction(preference, total_active_preference)
        weights.append((action_type, amount, share * aggression_scale * quality))

    total = sum((weight for _, _, weight in weights), Fraction(0))
    if total <= 0:
        raise MixedPolicyError("全部合法候选质量为 0，拒绝任意选择动作")

    units = _quantize([weight for _, _, weight in weights], total)
    candidates = tuple(
        MixedCandidate(action=action_type, amount=amount, units=unit)
        for (action_type, amount, _), unit in zip(weights, units, strict=True)
    )
    return MixedDistribution(candidates=candidates)


# ------------------------------------------------------------------ 规则评分


def _score(
    features: MixedFeatures,
    parameters: StyleParameters,
    mode: HandMode,
    rules: MixedPolicyRules = MIXED_LOCAL_V1_RULES,
) -> int:
    """人格与每手模式变换后的规则评分 S，最终夹在 0–1000。"""
    per_opponent = _CONTENDER_PENALTY
    if features.street is Street.PREFLOP:
        per_opponent = rules.preflop_contender_penalty
    contender_penalty = per_opponent * (features.contenders - 1)
    if rules.shared_board_chop_caliber and features.shared_board_locked:
        # 锁定平分局面上英雄不会输，人数不再降低其权益，故不施加人数惩罚。
        contender_penalty = 0
    return clip(
        features.base
        + features.draw
        + features.position
        + parameters.looseness
        + _MODE_SCORE_OFFSET[mode]
        - contender_penalty
        - features.texture,
        0,
        1000,
    )


def _preflop_call_bonus(rules: MixedPolicyRules, style: MixedStyle) -> int:
    """取该风格在翻前跟注分支上的偏移；字段名与风格取值一一对应。"""
    return int(getattr(rules.preflop_call_bonus, style.value))


def _non_value_quality(features: MixedFeatures) -> int:
    """非价值进攻质量：只在有公开依据时给分，否则为 0。"""
    if features.recent_aggression > 1 or features.live_opponents == 0:
        return 0
    if features.street is Street.PREFLOP:
        if features.position < 0 or features.base < 280:
            return 0
    elif features.draw <= 0 and not features.has_broadway_blocker:
        return 0
    return _SEAT_COUNT_FOR_U.get(features.contenders, 0)


_VALUE_THRESHOLDS = {
    Street.PREFLOP: 600,
    Street.FLOP: 650,
    Street.TURN: 700,
    Street.RIVER: 740,
}

def _require_coherent_legal(legal: LegalActions) -> None:
    """拒绝自相矛盾的合法动作集合，避免在无定义局面上打分。"""
    if legal.can_check and legal.can_call:
        raise MixedPolicyError("可过牌与可跟注同时为真")
    if legal.can_bet and legal.can_raise:
        raise MixedPolicyError("可下注与可加注同时为真")
    if legal.can_bet and legal.call_amount != 0:
        raise MixedPolicyError("可下注时不应存在待跟注额")
    for flag, low, high in (
        (legal.can_bet, legal.min_bet, legal.max_bet),
        (legal.can_raise, legal.min_raise_to, legal.max_raise_to),
    ):
        if flag and not 0 < low <= high:
            raise MixedPolicyError("主动动作的合法区间不合法")


def _active_candidates(
    features: MixedFeatures,
    legal: LegalActions,
    score: int,
    value_quality: int,
    bluff_quality: int,
    size_preferences: tuple[int, int, int, int],
) -> list[tuple[tuple[ActionType, int, int], int]]:
    """生成通过夹紧、合并与危险尺度保护后的主动候选及其质量与偏好。"""
    if legal.can_bet:
        action_type = ActionType.BET
        legal_min, legal_max = legal.min_bet, legal.max_bet
    elif legal.can_raise:
        action_type = ActionType.RAISE
        legal_min, legal_max = legal.min_raise_to, legal.max_raise_to
    else:
        return []

    stack = features.stack
    street_bet = features.street_bet
    upper = min(legal_max, street_bet + features.effective_stack)
    if upper < legal_min or features.live_opponents == 0:
        return []

    all_in_total = street_bet + stack
    if features.street is Street.PREFLOP and features.preflop_unraised:
        big_blind = features.big_blind
        small = -(-(5 + 2 * features.limpers) * big_blind // 2)
        medium = (3 + features.limpers) * big_blind
        large = (4 + features.limpers) * big_blind
    else:
        pot_target = max(features.big_blind, features.pot + features.actual_call)
        call_point = street_bet + legal.call_amount
        small = call_point + -(-pot_target // 3)
        medium = call_point + -(-3 * pot_target // 4)
        large = call_point + -(-5 * pot_target // 4)

    merged: dict[int, int] = {}
    for target, preference in zip((small, medium, large), size_preferences[:3], strict=True):
        amount = clip(target, legal_min, upper)
        merged[amount] = merged.get(amount, 0) + preference
    if all_in_total <= upper:
        merged[all_in_total] = merged.get(all_in_total, 0) + size_preferences[3]

    pot_reference = max(features.pot, features.big_blind)
    candidates: list[tuple[tuple[ActionType, int, int], int]] = []
    for amount in sorted(merged):
        payment = amount - street_bet
        dangerous = payment == stack or payment > _DANGEROUS_POT_MULTIPLE * pot_reference
        if dangerous:
            if value_quality <= 0:
                continue
            if not (
                score >= _DANGEROUS_SCORE_STRONG
                or (features.spr_at_most(1) and score >= _DANGEROUS_SCORE_SHORT)
            ):
                continue
        # 危险候选一律禁用非价值质量，避免把压迫性尺度用在无价值依据的场合。
        quality = value_quality + (0 if dangerous else bluff_quality)
        candidates.append(((action_type, amount, quality), merged[amount]))
    return candidates


def _quantize(weights: list[Fraction], total: Fraction) -> list[int]:
    """精确有理数归一后量化到整数单位，再按小数余数补齐差额。"""
    exact = [weight * MIXED_DISTRIBUTION_UNITS / total for weight in weights]
    units = [int(value) for value in exact]
    leftover = MIXED_DISTRIBUTION_UNITS - sum(units)
    if leftover <= 0:
        return units
    remainders = [value - int(value) for value in exact]
    order = sorted(
        (index for index, remainder in enumerate(remainders) if remainder > 0),
        key=lambda index: (-remainders[index], index),
    )
    for index in order[:leftover]:
        units[index] += 1
    return units
