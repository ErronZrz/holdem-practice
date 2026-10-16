"""新 Bot 的规则策略层：固定风格参数、整数尺寸候选、危险尺度保护与联合分布。

规则来源与口径：
- 所有分数是 0–1000 的规则评分，不是概率、不是 EV；
- 候选一律为「动作类型 + 本街总额」，先夹紧、去重、合并偏好，再算质量；
- 危险尺度按最终实际金额判定，不靠「小注」标签绕过保护；
- 概率用精确有理数归一后量化到独立的一百万单位。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
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
# 连续式非价值进攻依据的基数：与人数表的最大值一致，使单挑量级不变。
_NON_VALUE_BASE = 12
# 位置分量的上限：与位置评分的整幅刻度同阶。
_NON_VALUE_POSITION_WEIGHT = 4
# 听牌质量分量的上限。
_NON_VALUE_DRAW_WEIGHT = 4
# 听牌分数的封顶：与翻牌听牌分数的上限一致，翻后按同一比例折算。
_NON_VALUE_DRAW_CAP = 180
# 主动门槛的基准容差：分化开关关闭时即为既有取值。
_VALUE_GATE_TOLERANCE = 120
# 局面指数的上限：与位置、听牌两项跨度之和一致。
_ACTIVE_GATE_INDEX_CAP = 100
# 局面指数里位置分量的跨度。
_ACTIVE_GATE_POSITION_SPAN = 60
# 局面指数里听牌分量的跨度。
_ACTIVE_GATE_DRAW_SPAN = 40
# 无人下注时，基础分达到这条下沿才补主动质量。下沿取已记录的顶对档之下、
# 中对与低口袋对之上，避免把空气和弱对也当成价值下注。
_CHECKED_VALUE_FLOOR = 600
# 补上的质量停在两对高出该下沿的跨度，已经越过原门槛的更强牌不再被这条抬高。
_CHECKED_VALUE_SPAN = 160
# 多人底池里，低于两张底牌都配对的这一档时，不再用成牌下限去打薄价值。
_THIN_VALUE_BASE = 760
# 待跟注不少于可争夺底池时，跟注价格达到这条线，视为大尺度。
_LARGE_PRICE = 500
# 大额承诺从被动分扣掉的量：两倍跟注缓冲，再抵消跟注型翻后已经加上的偏移。
_LARGE_COMMIT_PENALTY = 420
# 除自己以外至少还有两名未弃牌对手，才按多人底池收紧压迫尺度。
_MULTIWAY_CONTENDERS = 2
# 价值下限收得更晚：四人及以上才取消中等成牌的主动托底。
_MULTIWAY_VALUE_CONTENDERS = 3
# 翻前强牌下沿：口袋十及以上。低于这条线的翻前跟注不因强牌路径放宽。
_STRONG_PREFLOP_BASE = 780
# 强成牌的主动附加量：与成牌托底跨度同阶，用来把价值下注抬到免费过牌之上。
_STRONG_VALUE_BONUS = 160
# 翻前强牌的继续偏移：大约抵消一次弃牌缓冲，避免强牌在有价格时直接弃掉。
_STRONG_PREFLOP_CONTINUATION = 180
# 强成牌的尺度偏好：小注只留一点，中注与大注占多数，不把整叠当作默认尺度。
_STRONG_SIZE_PREFERENCES = (1, 6, 6, 0)
# 同花及以上才允许在无人下注时把整叠放进偏好。两对、三条和顺子仍不默认全下。
_NUT_BASE = 900
# 面对下注时，未到同花的强成牌把尺度收回小注，避免一层层把底池打大。
_PRESSURED_STRONG_PREFERENCES = (6, 2, 0, 0)
# 无人下注的同花及以上：大尺度和全下占多数，用来兑现已经成牌的价值。
_NUT_OPEN_PREFERENCES = (1, 2, 4, 6)
# 满员桌从八人座起收紧。收紧看开局座位数，不看还剩几人，避免人走了以后门槛消失。
_FULL_RING_SEATS = 8
# 满员桌翻前，低于中对这一档且价格已经不小，才少跟注。
_FULL_RING_WEAK_BASE = 500
_FULL_RING_PREFLOP_PRICE = 300
# 满员桌翻后收紧的是中对到两对高档之下，不收紧听牌，也不收紧两对高档及以上。


class MixedPolicyError(ValueError):
    """合法动作自相矛盾、参数越界或分布退化时抛出。"""


@dataclass(frozen=True)
class StyleCallBonus:
    """按风格取值的跟注偏移；价值主动分支不受它影响。

    字段名与风格取值一一对应，因此可直接按风格取值取出对应偏移；至于它作用于
    哪条街，由承载它的口径字段决定。
    """

    tight: int = 0
    aggressive: int = 0
    calling: int = 0


# 旧名保留为别名：既有身份与既有测试都按这个名字引用同一种结构。
PreflopCallBonus = StyleCallBonus


@dataclass(frozen=True)
class MixedPolicyRules:
    """一版规则口径的开关集合：新旧身份共用实现，但分布互不影响。

    各版取值都写进口径对象，使配置摘要能覆盖它们；首版与第二版取默认值，
    因此分布逐位不变。
    """

    # 锁定平分局面按分池口径处理：免除人数惩罚，并按共同分割底池的人数折减跟注价格。
    shared_board_chop_caliber: bool = False
    # 翻前跟注阈值的价格项权重；后翻后另用固定权重。
    preflop_price_weight: int = _PREFLOP_PRICE_WEIGHT
    # 翻前每多一名未弃牌对手的评分惩罚。
    preflop_contender_penalty: int = _CONTENDER_PENALTY
    # 翻前仅作用于跟注分支的风格偏移。
    preflop_call_bonus: StyleCallBonus = StyleCallBonus()
    # 翻后仅作用于跟注分支的风格偏移，用于拉开被动分支上的风格差异。
    postflop_call_bonus: StyleCallBonus = StyleCallBonus()
    # 主动分支的尺度倍率：取 1 时主动量与首版逐位相同，取更大值则与被动分支的
    # 整数刻度对齐，使风格倍率的差异不再被量级差淹没。
    active_scale_percent: int = 1
    # 人数惩罚的上限：取 0 表示不设上限；取正值时多人桌上的扣分到此封顶。
    contender_penalty_cap: int = 0
    # 非价值进攻依据的口径：取假沿用离散人数表，取真改用公开特征定义的连续量。
    # 默认取假，使既有各版身份的分布逐位不变。
    continuous_non_value_basis: bool = False
    # 翻后主动门槛是否随公开局面按风格分化：取假沿用与风格无关的门槛。
    # 默认取假，使既有各版身份的分布逐位不变。
    situational_active_gate: bool = False
    # 面对下注时，是否把听牌分原样并入非价值进攻。默认取假，听牌仍只走既有小额依据。
    facing_draw_continuation: bool = False
    # 无人下注时，是否用未加风格偏移的成牌基础分托住主动质量。默认取假。
    checked_value_realization: bool = False
    # 大额承诺与多人底池是否收紧跟注、压迫尺度和薄价值托底。默认取假，旧身份分布不变。
    large_pot_defense: bool = False
    # 强成牌是否加大主动质量，并把尺度从微注挪到中注与大注。默认取假。
    strong_value_sizing: bool = False
    # 满员桌是否收紧中等牌力的深跟注与大尺度。默认取假，人少的底池不受影响。
    full_ring_defense: bool = False
    # 强成牌的尺度是否按局面收回：翻前沿用风格原表，面对下注时未到同花只留小尺度，
    # 无人下注的同花及以上才把整叠放回偏好。默认取假，旧身份的尺度逐位不变。
    guarded_strong_commitment: bool = False
    # 主动尺度是否先按小盲对齐再夹紧。默认关闭，既有身份的候选金额逐位不变。
    align_bet_to_small_blind: bool = False


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
# 第五版口径：翻前与第四版逐字一致，只给跟注型加一个翻后被动的跟注偏移。
MIXED_LOCAL_V5_RULES = MixedPolicyRules(
    shared_board_chop_caliber=True,
    preflop_price_weight=150,
    preflop_contender_penalty=30,
    preflop_call_bonus=PreflopCallBonus(tight=30, aggressive=35, calling=110),
    postflop_call_bonus=StyleCallBonus(tight=0, aggressive=0, calling=100),
)
# 第六版口径：主动分支与被动分支放在同一尺度，并给人数惩罚设上限；
# 其余取值与第五版逐字一致，因此两版只在上述两处行为上不同。
MIXED_LOCAL_V6_RULES = MixedPolicyRules(
    shared_board_chop_caliber=True,
    preflop_price_weight=150,
    preflop_contender_penalty=30,
    preflop_call_bonus=PreflopCallBonus(tight=30, aggressive=35, calling=110),
    postflop_call_bonus=StyleCallBonus(tight=0, aggressive=0, calling=100),
    active_scale_percent=10,
    contender_penalty_cap=70,
)
# 第七版口径：只把非价值进攻依据改成连续量，其余七个字段与第六版逐字一致。
MIXED_LOCAL_V7_RULES = replace(MIXED_LOCAL_V6_RULES, continuous_non_value_basis=True)
# 第八版口径：只把翻后主动门槛改成随公开局面按风格分化，其余八个字段与第七版逐字一致。
MIXED_LOCAL_V8_RULES = replace(MIXED_LOCAL_V7_RULES, situational_active_gate=True)
# 第九版口径：面对下注时听牌分进入加注，无人下注时成牌基础分托住主动质量。
# 其余字段与第八版逐字一致，因此两版只在这两处行为上不同。
MIXED_LOCAL_V9_RULES = replace(
    MIXED_LOCAL_V8_RULES,
    facing_draw_continuation=True,
    checked_value_realization=True,
)
# 第十版口径：只在第九版上打开大额承诺与多人底池的收紧。其余字段逐字一致。
MIXED_LOCAL_V10_RULES = replace(MIXED_LOCAL_V9_RULES, large_pot_defense=True)
# 第十一版口径：强成牌加大兑现，满员桌收紧中等牌力。其余字段与第十版逐字一致。
MIXED_LOCAL_V11_RULES = replace(
    MIXED_LOCAL_V10_RULES,
    strong_value_sizing=True,
    full_ring_defense=True,
)
# 第十二版口径：强成牌仍兑现，但翻前不放大尺度，面对下注不层层加码，
# 同花及以上在无人下注时才把整叠打进去。其余字段与第十一版逐字一致。
MIXED_LOCAL_V12_RULES = replace(
    MIXED_LOCAL_V11_RULES,
    guarded_strong_commitment=True,
)
# 第十三版口径：主动尺度按小盲对齐，其余字段与第十二版逐字一致。
MIXED_LOCAL_V13_RULES = replace(
    MIXED_LOCAL_V12_RULES,
    align_bet_to_small_blind=True,
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
# 翻后主动门槛的逐风格权重：负值抬高门槛、正值放宽门槛，三档互不相等。
_ACTIVE_GATE_WEIGHT: dict[MixedStyle, int] = {
    MixedStyle.TIGHT: -6,
    MixedStyle.AGGRESSIVE: 8,
    MixedStyle.CALLING: 1,
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

    # 跟注偏移只作用于被动分支：价值主动质量仍按未偏移的评分计算。
    passive_score = score + (
        _preflop_call_bonus(rules, style) if is_preflop else _postflop_call_bonus(rules, style)
    )
    # 大额承诺只压低跟注，避免中等牌力在多人底池里把筹码跟光。
    commit_penalty = _large_commit_penalty(features, rules)
    # 满员桌的深跟注另算，人少或强成牌不走这条扣分。
    ring_penalty = _full_ring_call_penalty(features, rules)
    passive_score += _strong_preflop_continuation(features, rules)
    passive_score -= commit_penalty + ring_penalty
    fold_weight = max(0, call_threshold - passive_score + 160) * parameters.fold_percent
    call_weight = max(0, passive_score - call_threshold + 160) * parameters.call_percent
    gate = _active_gate(features, style, rules)
    threshold_quality = max(0, score - value_threshold + _VALUE_GATE_TOLERANCE + gate)
    # 托底只抬高没越过原门槛的成牌；已经更高的主动质量保持原值。
    value_quality = max(threshold_quality, _checked_value_floor(features, rules))
    if _strong_value_hand(features, rules):
        # 强成牌再加一截主动质量，避免只过牌或只打微注。
        value_quality += _STRONG_VALUE_BONUS
    # 分化只调整已有依据的幅度，不给没有公开依据的场合凭空加依据。
    bluff_raw = _non_value_quality(features, rules)
    bluff_quality = max(0, bluff_raw + gate) if bluff_raw > 0 else 0
    if commit_penalty or ring_penalty:
        # 同一笔不该跟的承诺上不再加注，避免把中等牌力打成更大的底池。
        value_quality = 0
        bluff_quality = 0
    aggression_scale = Fraction(
        parameters.aggression_percent
        * _MODE_AGGRESSION_PERCENT[mode]
        * rules.active_scale_percent,
        _PERCENT,
    )

    active = _active_candidates(
        features,
        legal,
        score,
        value_quality,
        bluff_quality,
        _size_preferences(features, parameters, rules),
        rules,
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
    if rules.contender_penalty_cap > 0:
        # 人数惩罚在此封顶：多人桌上不再按人数线性累加扣分。
        contender_penalty = min(contender_penalty, rules.contender_penalty_cap)
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


def _postflop_call_bonus(rules: MixedPolicyRules, style: MixedStyle) -> int:
    """取该风格在翻后跟注分支上的偏移；字段名与风格取值一一对应。"""
    return int(getattr(rules.postflop_call_bonus, style.value))


def _continuous_non_value_parts(features: MixedFeatures) -> tuple[int, int, int]:
    """连续式的三个分量：对手数、位置与听牌质量，各自封顶后再求和。

    准入已保证至少存在一名未弃牌对手，故除数恒不小于 1。
    """
    seats = max(1, _NON_VALUE_BASE // features.contenders)
    # 位置评分落在 -40..40：平移半幅后按整幅归一，最差位置得 0，最好位置得满幅。
    place = _NON_VALUE_POSITION_WEIGHT * (features.position + 40) // 80
    potential = (
        _NON_VALUE_DRAW_WEIGHT
        * min(features.draw, _NON_VALUE_DRAW_CAP)
        // _NON_VALUE_DRAW_CAP
    )
    return seats, place, potential


def _continuous_non_value_quality(features: MixedFeatures) -> int:
    """连续式非价值进攻依据：三个分量之和，再按基数封顶。"""
    return min(_NON_VALUE_BASE, sum(_continuous_non_value_parts(features)))


def _non_value_quality(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """非价值进攻质量：只在有公开依据时给分，否则为 0。"""
    if features.recent_aggression > 1 or features.live_opponents == 0:
        return 0
    if features.street is Street.PREFLOP:
        if features.position < 0 or features.base < 280:
            return 0
    elif features.draw <= 0 and not features.has_broadway_blocker:
        return 0
    if rules.continuous_non_value_basis:
        base = _continuous_non_value_quality(features)
    else:
        base = _SEAT_COUNT_FOR_U.get(features.contenders, 0)
    return base + _facing_draw_extra(features, rules)


def _facing_draw_extra(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """面对下注且存在听牌时，按与弃牌同阶的量把听牌分并入非价值依据。

    听牌分已经进入弃牌和跟注的评分，但主动一侧原先只留下个位数。
    没有待跟注、没有听牌或开关关闭时返回 0，过牌局面因此不变。
    调用方已排除连续进攻和没有对手的场合，这里不再重复放行。
    """
    if not rules.facing_draw_continuation:
        return 0
    if features.street is Street.PREFLOP or features.actual_call <= 0 or features.draw <= 0:
        return 0
    scale = rules.active_scale_percent
    if scale <= 0:
        return 0
    # 主动权重会再乘尺度倍率。先除回去，使一点听牌推动加注的量级与它推动弃牌的量级同阶。
    return features.draw // scale


def _checked_value_floor(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """无人下注时，用未加风格偏移的成牌基础分给出主动质量下限。

    风格扣分会把顶对压到主动门槛之下，主动质量变成 0 后，过牌权重就与牌力无关。
    下限只在可以免费行动、且基础分达到成牌下沿时出现；面对下注不走这条路径。
    """
    if not rules.checked_value_realization:
        return 0
    if features.street is Street.PREFLOP or features.actual_call > 0:
        return 0
    if features.base < _CHECKED_VALUE_FLOOR:
        return 0
    # 人多时中等成牌不再被托住下注；两对及以上、以及人少的底池仍沿用原下限。
    if (
        rules.large_pot_defense
        and features.contenders >= _MULTIWAY_VALUE_CONTENDERS
        and features.base < _THIN_VALUE_BASE
    ):
        return 0
    return min(features.base - _CHECKED_VALUE_FLOOR, _CHECKED_VALUE_SPAN)


def _strong_value_hand(features: MixedFeatures, rules: MixedPolicyRules) -> bool:
    """强成牌或翻前强牌。开关关闭时恒为假，旧身份的尺度与跟注因此不变。"""
    if not rules.strong_value_sizing:
        return False
    if features.street is Street.PREFLOP:
        return features.base >= _STRONG_PREFLOP_BASE
    return features.base >= _THIN_VALUE_BASE


def _strong_preflop_continuation(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """翻前强牌的继续偏移。翻后与非强牌返回 0，不改动原有跟注分。"""
    if features.street is not Street.PREFLOP or not _strong_value_hand(features, rules):
        return 0
    return _STRONG_PREFLOP_CONTINUATION


def _full_ring_call_penalty(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """满员桌上中等牌力面对深跟注时的被动扣分。

    人少的桌子、听牌和两对高档及以上都不扣。翻前只扣低于中对档且价格已经不小的跟注，
    避免把还能看到翻牌的强牌一并弃掉。
    """
    if not rules.full_ring_defense or features.seat_count < _FULL_RING_SEATS:
        return 0
    committing = features.actual_call * 2 >= features.stack
    if features.street is Street.PREFLOP:
        if features.base >= _FULL_RING_WEAK_BASE or features.actual_call <= 0:
            return 0
        if features.price < _FULL_RING_PREFLOP_PRICE and not committing:
            return 0
        return _LARGE_COMMIT_PENALTY
    if features.actual_call <= 0:
        return 0
    if features.base < _FULL_RING_WEAK_BASE or features.base >= _THIN_VALUE_BASE:
        return 0
    if not (committing or features.price >= _LARGE_PRICE):
        return 0
    return _LARGE_COMMIT_PENALTY


def _size_preferences(
    features: MixedFeatures, parameters: StyleParameters, rules: MixedPolicyRules
) -> tuple[int, int, int, int]:
    """按牌力改尺度偏好。未命中时原样返回该风格的固定偏好。"""
    base = parameters.size_preferences
    if _strong_value_hand(features, rules):
        return _guarded_strong_preferences(features, parameters, rules)
    thin_full_ring = (
        rules.full_ring_defense
        and features.seat_count >= _FULL_RING_SEATS
        and features.street is not Street.PREFLOP
        and _FULL_RING_WEAK_BASE <= features.base < _THIN_VALUE_BASE
    )
    if thin_full_ring:
        # 满员桌上的中等成牌不再打大注或全下，小注与中注仍保留。
        return (base[0], base[1], 0, 0)
    return base


def _guarded_strong_preferences(
    features: MixedFeatures, parameters: StyleParameters, rules: MixedPolicyRules
) -> tuple[int, int, int, int]:
    """强成牌的尺度。开关关闭时仍是中注和大注，旧身份因此逐位不变。

    翻前放大开池会把还没看到公共牌的强牌打成大底池。面对下注时，未到同花的成牌
    继续加到中大尺度，会在对方一层层施压时把筹码打进去。只有无人下注、且牌力
    已经到同花及以上，才把整叠放回偏好。
    """
    if not rules.guarded_strong_commitment:
        return _STRONG_SIZE_PREFERENCES
    if features.street is Street.PREFLOP:
        return parameters.size_preferences
    if features.actual_call > 0 and features.base < _NUT_BASE:
        return _PRESSURED_STRONG_PREFERENCES
    if features.actual_call <= 0 and features.base >= _NUT_BASE:
        return _NUT_OPEN_PREFERENCES
    return _STRONG_SIZE_PREFERENCES


def _large_commit_penalty(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """大额承诺上的被动扣分。开关关闭、翻前、或牌力已到成牌下沿时为 0。

    顶对及以上仍按原跟注。只在四人及以上、且待跟注至少吃掉一半剩余筹码或价格已到大尺度时
    扣分。人少的底池继续跟注，避免把单挑里能跟的牌一并弃掉。
    """
    if not rules.large_pot_defense:
        return 0
    if features.street is Street.PREFLOP or features.actual_call <= 0:
        return 0
    if features.base >= _CHECKED_VALUE_FLOOR:
        return 0
    if features.contenders < _MULTIWAY_VALUE_CONTENDERS:
        return 0
    committing = features.actual_call * 2 >= features.stack
    large_price = features.price >= _LARGE_PRICE
    if not (committing or large_price):
        return 0
    return _LARGE_COMMIT_PENALTY


def _active_gate(
    features: MixedFeatures, style: MixedStyle, rules: MixedPolicyRules
) -> int:
    """翻后主动门槛的偏移：按本风格权重缩放公开局面指数。

    指数只由公开的位置与听牌质量构成；翻前或分化关闭时恒为零，因此这两种情形
    与未分化口径逐位一致。全部为整数运算，同一输入必得同一偏移。
    """
    if not rules.situational_active_gate or features.street is Street.PREFLOP:
        return 0
    index = clip(
        (features.position + 40) * _ACTIVE_GATE_POSITION_SPAN // 80
        + min(features.draw, _NON_VALUE_DRAW_CAP) * _ACTIVE_GATE_DRAW_SPAN // _NON_VALUE_DRAW_CAP,
        0,
        _ACTIVE_GATE_INDEX_CAP,
    )
    return _ACTIVE_GATE_WEIGHT[style] * index // _ACTIVE_GATE_INDEX_CAP


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
    rules: MixedPolicyRules = MIXED_LOCAL_V1_RULES,
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
    chip_unit = max(1, features.big_blind // 2) if rules.align_bet_to_small_blind else 1
    for target, preference in zip((small, medium, large), size_preferences[:3], strict=True):
        # 偏好为 0 的尺度不进入候选，避免造出永远抽不中的空额度。
        if preference <= 0:
            continue
        aligned = target if chip_unit <= 1 else _align_to_unit(target, chip_unit)
        amount = clip(aligned, legal_min, upper)
        merged[amount] = merged.get(amount, 0) + preference
    if all_in_total <= upper and size_preferences[3] > 0:
        merged[all_in_total] = merged.get(all_in_total, 0) + size_preferences[3]

    pot_reference = max(features.pot, features.big_blind)
    candidates: list[tuple[tuple[ActionType, int, int], int]] = []
    for amount in sorted(merged):
        payment = amount - street_bet
        dangerous = payment == stack or payment > _DANGEROUS_POT_MULTIPLE * pot_reference
        if dangerous:
            if value_quality <= 0:
                continue
            short_ok = features.spr_at_most(1) and score >= _DANGEROUS_SCORE_SHORT
            # 多人底池里，低于成牌下沿的牌力不能借短码例外打出压迫尺度。
            if (
                rules.large_pot_defense
                and features.contenders >= _MULTIWAY_CONTENDERS
                and features.base < _CHECKED_VALUE_FLOOR
            ):
                short_ok = False
            # 无人下注的同花及以上允许打出整叠，不因位置或人数扣分被挡在门槛下。
            nut_open = (
                rules.guarded_strong_commitment
                and features.street is not Street.PREFLOP
                and features.actual_call <= 0
                and features.base >= _NUT_BASE
            )
            if not (score >= _DANGEROUS_SCORE_STRONG or short_ok or nut_open):
                continue
        # 危险候选一律禁用非价值质量，避免把压迫性尺度用在无价值依据的场合。
        quality = value_quality + (0 if dangerous else bluff_quality)
        candidates.append(((action_type, amount, quality), merged[amount]))
    return candidates


def _align_to_unit(amount: int, unit: int) -> int:
    """把金额对齐到给定正整数单位；对半时向上取整。"""
    quotient, remainder = divmod(amount, unit)
    if remainder * 2 >= unit:
        return (quotient + 1) * unit
    return quotient * unit


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
