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
# 被公共牌两对盖住的口袋对：低于成牌托底，高于完全没参与公共牌对子的记分。
_CAPPED_BOARD_PAIR_BASE = 400
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
# 设伏预算按牌面风险与人数递减，封顶后不再升高。
_TRAP_TEXTURE_DIVISOR = 10
_TRAP_BUDGET_CAP = 40
# 设伏过牌后再面对下注时，补回半段强牌加分，避免只剩加注。
_TRAP_RELEASE = 80
# 续枪只记住上一街有限次进攻，并按牌面风险折减。
_STORY_COUNT_CAP = 2
_STORY_COUNT_STEP = 2
_STORY_TEXTURE_DIVISOR = 8
# 听牌支撑只覆盖基础分低于这条线的听牌，人数再多也至少留下四成覆盖率。
_DRAW_SUPPORT_BASE = 400
_DRAW_RETENTION_FLOOR = 400
_DRAW_CROWD_STEP = 150
# 翻前国王后补上旧基础分漏掉的连张分。同花与非同花加同一笔，原有同花差留在基础分里。
_KQ_CONNECTOR_BONUS = 50
# 未开池且前位已有弃牌时，按弃牌人数把位置从最前档往回拉。
_UNOPENED_POSITION_SPAN = 80
# 修正后达到这一档的翻前牌才吃未开池后位加分，弱杂牌不加。
_UNOPENED_PLAYABLE_BASE = 470
_UNOPENED_BASE_STEP = 65
_UNOPENED_BASE_CAP = 160
# 翻牌至少八张补牌时改按两街成牌率给支撑，并从第四名对手起才打折。
_STRONG_FLOP_DRAW_OUTS = 8
_STRONG_FLOP_DRAW_SPAN = 420
_STRONG_FLOP_DRAW_FREE_OPPONENTS = 3
# 听牌分整除还原补牌数时使用的权重与未见牌张数，翻牌与转牌分开。
_DRAW_FLOP_OUTS_WEIGHT = 12
_DRAW_TURN_OUTS_WEIGHT = 8
_DRAW_FLOP_UNSEEN = 47
_DRAW_TURN_UNSEEN = 46
# 跟注开口与弃牌、跟注权重里的缓冲是同一跨度。
_PASSIVE_SLACK = 160
# 顶对带过牌保护：只覆盖这一基础分区间，两对高档及以上仍走原来的设伏。
_PROTECTION_BASE_FLOOR = 600
_PROTECTION_BASE_CEILING = 760
_PROTECTION_WEAK_KICKER = 660
_PROTECTION_WEAK_KICKER_PERCENT = 10
_PROTECTION_TEXTURE_LINE = 40
_PROTECTION_TEXTURE_PERCENT = 8
_PROTECTION_CROWD_PERCENT = 6
_PROTECTION_BUDGET_CAP = 40
# 本街已经过牌、面对单次常规下注时，只给有摊牌价值的成牌补跟注。
_DEFENSE_BASE_FLOOR = 360
_DEFENSE_BASE_CEILING = 760
_DEFENSE_CROWD_SPAN = 80
_DEFENSE_PRICE_HALVE = 400
_DEFENSE_PRICE_CAP = 500
_DEFENSE_CONTENDER_CAP = 3
# 单挑过牌示弱时，给没有摊牌价值的空气补一小段下注质量。
_PROBE_BASE_CEILING = 200
_PROBE_CHECKED_BONUS = 2
_PROBE_RIVER_BONUS = 2
_PROBE_QUALITY_CAP = 8
_PROBE_TEXTURE_DIVISOR = 40
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
    # 翻牌与转牌的强成牌是否按手牌级隐变量整段过牌。默认关闭。
    trap_allocation: bool = False
    # 单挑、牌面风险为 0 时的设伏预算百分数，再按人数与牌面往下减。
    trap_base_percent: int = 24
    # 每多一名对手从设伏预算里扣掉的百分数。
    trap_crowd_percent: int = 8
    # 上一街由自己收尾进攻后，这一街是否给无阻断空气补一点下注质量。默认关闭。
    story_momentum: bool = False
    # 续枪质量的起点，再按上一街进攻次数上调、按牌面风险下调。
    story_quality_base: int = 10
    # 听牌面对下注时是否按覆盖率抬跟注并收口加注。默认关闭。
    effective_draw_support: bool = False
    # 覆盖率满额时加进被动分的跨度。
    draw_support_span: int = 360
    # 翻前非对子高张是否改用有效基础分。默认关闭，旧身份仍读原来的基础分。
    broadway_preflop_caliber: bool = False
    # 只修正这一高张。低于它的连张不加分，避免带动未开池节点里的国王后。
    broadway_high_rank: int = 14
    # 踢脚至少到这一档才修正，覆盖 AK、AQ、AJ，不把更弱的高张一并抬上去。
    broadway_min_kicker: int = 11
    # 紧邻连张补上的分。同花与非同花加同一笔，原有同花差留在基础分里。
    broadway_connector_bonus: int = 0
    # 隔一张时补上的分。
    broadway_one_gap_bonus: int = 0
    # 隔两张时补上的分。
    broadway_two_gap_bonus: int = 0
    # 翻前未开池后位与翻牌强听牌是否改用修正口径。默认关闭，旧身份的分布逐位不变。
    late_unopened_draw_caliber: bool = False
    # 翻牌与转牌的顶对带是否按另一条手牌级隐变量整段过牌。默认关闭。
    check_range_protection: bool = False
    # 单挑、牌面风险为 0、基础分不低于弱踢脚下沿时的过牌预算百分数。
    check_base_percent: int = 16
    # 本街已经过牌、面对单次常规下注时，是否给有摊牌价值的成牌补跟注。默认关闭。
    checked_continue: bool = False
    # 单挑、价格还没到折半线时补进被动分的跨度。
    checked_defense_span: int = 160
    # 单挑过牌示弱时，是否给没有摊牌价值的空气补一点下注质量。默认关闭。
    delayed_probe: bool = False
    # 探测质量的起点，再按上一条街过牌、河牌上调，按牌面风险下调。
    delayed_probe_quality: int = 4
    # 激进型翻后面对下注时，收掉低于两对高档的单对加注；
    # 公共牌已是两对且口袋对更低时，把基础分记到成牌托底之下。默认关闭。
    postflop_pair_caliber: bool = False
    # 对手尚未全下、但剩余不足一个完整最小加注增量时，主动价值是否仍保留合法最小加注。
    # 默认关闭。纯诈唬，或对手在跟注额内已经全下时，即使打开也不加注。
    short_stack_min_raise: bool = False
    # 底牌配成牌面最高点数、另一对是更低公对时，有效基础分是否至少按同一张底牌的顶对计。
    # 默认关闭。低对或中对配上更高公对不抬。
    top_pair_board_pair_caliber: bool = False


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
# 第十四版口径：在第十三版上打开设伏、续枪与听牌覆盖率。整型系数沿用默认值。
MIXED_LOCAL_V14_RULES = replace(
    MIXED_LOCAL_V13_RULES,
    trap_allocation=True,
    story_momentum=True,
    effective_draw_support=True,
)
# 第十五版口径：只抬翻前 A 高张的有效基础分，修连张漏分，并让 AK、AQ 在前位开得动。
# 国王后及更低的非对子不加分，翻后基础分也不改。
MIXED_LOCAL_V15_RULES = replace(
    MIXED_LOCAL_V14_RULES,
    broadway_preflop_caliber=True,
    broadway_connector_bonus=220,
    broadway_one_gap_bonus=150,
    broadway_two_gap_bonus=120,
)
# 第十六版口径：补上国王后的连张分，未开池且前位已有弃牌时恢复后位，
# 翻牌八张及以上补牌按两街成牌率给支撑。其余字段与第十五版逐字一致。
MIXED_LOCAL_V16_RULES = replace(
    MIXED_LOCAL_V15_RULES,
    late_unopened_draw_caliber=True,
)
# 第十七版口径：顶对带可整段过牌且转牌不再设伏，过牌后的成牌补跟注，
# 单挑过牌线上给空气补一小段探测。其余字段与第十六版逐字一致。
MIXED_LOCAL_V17_RULES = replace(
    MIXED_LOCAL_V16_RULES,
    check_range_protection=True,
    checked_continue=True,
    delayed_probe=True,
)
# 第十八版口径：只打开翻后对子收口。其余字段与第十七版逐字一致。
MIXED_LOCAL_V18_RULES = replace(
    MIXED_LOCAL_V17_RULES,
    postflop_pair_caliber=True,
)
# 第十九版口径：短码对手盖不住完整增量时保留合法最小加注，
# 顶对加更低公对的有效基础分不低于同一张牌的顶对分。其余字段与第十八版逐字一致。
MIXED_LOCAL_V19_RULES = replace(
    MIXED_LOCAL_V18_RULES,
    short_stack_min_raise=True,
    top_pair_board_pair_caliber=True,
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
    trap_roll: int | None = None,
    protect_roll: int | None = None,
) -> MixedDistribution:
    """按固定规则计算当前局面的联合动作/尺度分布。

    ``trap_roll`` 与 ``protect_roll`` 缺省时对应通道保持关闭，
    避免没有座位键的查询路径自行抽数。
    """
    features = _with_effective_base(features, rules)
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
    penalties_clear = commit_penalty == 0 and ring_penalty == 0
    if (
        penalties_clear
        and rules.effective_draw_support
        and features.base < _DRAW_SUPPORT_BASE
        and value_quality == 0
    ):
        # 先把覆盖率支撑加进被动分，再用跟注还活着的比例收口非价值加注。
        supported = _facing_draw_support(features, rules)
        if supported is not None:
            support, coverage = supported
            passive_score += support
            opening = max(0, passive_score - call_threshold + _PASSIVE_SLACK)
            survival = min(coverage, opening * 1000 // _PASSIVE_SLACK)
            bluff_quality = bluff_quality * survival // 1000
            fold_weight = max(0, call_threshold - passive_score + _PASSIVE_SLACK) * (
                parameters.fold_percent
            )
            call_weight = max(0, passive_score - call_threshold + _PASSIVE_SLACK) * (
                parameters.call_percent
            )
    if penalties_clear:
        # 承诺没有把主动质量清掉时，才把上一街自己的进攻补进这一街的空气下注。
        bluff_quality += _story_quality(features, rules)
    if _protection_applies(features, rules, protect_roll) and (
        legal.can_check or (features.actor_checks > 0 and features.actual_call > 0)
    ):
        # 命中过牌保护：可以免费过牌，或本街已经过牌再面对下注时，不再主动投入。
        value_quality = 0
        bluff_quality = 0
    if _trap_applies(features, rules, trap_roll):
        if legal.can_check:
            # 设伏命中且可以免费行动：这一街整段过牌，不保留半诈唬。
            value_quality = 0
            bluff_quality = 0
        if features.actor_checks > 0 and features.actual_call > 0:
            # 本街已经过牌再面对下注：强牌价值保留，只把一小段质量还到跟注。
            passive_score += _TRAP_RELEASE
            fold_weight = max(0, call_threshold - passive_score + _PASSIVE_SLACK) * (
                parameters.fold_percent
            )
            call_weight = max(0, passive_score - call_threshold + _PASSIVE_SLACK) * (
                parameters.call_percent
            )
    if penalties_clear:
        # 承诺没有清掉主动质量时，才补探测和过牌后的跟注。跟注不加主动质量。
        bluff_quality += _delayed_probe_quality(features, rules)
        defense = _checked_defense_bonus(features, rules)
        if defense:
            passive_score += defense
            fold_weight = max(0, call_threshold - passive_score + _PASSIVE_SLACK) * (
                parameters.fold_percent
            )
            call_weight = max(0, passive_score - call_threshold + _PASSIVE_SLACK) * (
                parameters.call_percent
            )
    # 故事分、探测分和过牌保护都已结算后再收口，避免把后来补上的非价值质量提前清掉。
    value_quality, bluff_quality = _close_facing_pair_raise(
        features, rules, style, value_quality, bluff_quality
    )
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


def _broadway_bonus(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """翻前 A 高张相对旧基础分的加分。关闭、翻后、对子或踢脚不够时为 0。

    同花与否已经含在旧基础分里：同花恰好多 45，非同花不多不少。这里只按点差补一笔，
    同花和非同花因此保持原来的差距。
    """
    if not rules.broadway_preflop_caliber or features.street is not Street.PREFLOP:
        return 0
    high = max(features.hole_ranks)
    low = min(features.hole_ranks)
    if high <= low or high != rules.broadway_high_rank or low < rules.broadway_min_kicker:
        return 0
    gap = high - low - 1
    if gap == 0:
        return rules.broadway_connector_bonus
    if gap == 1:
        return rules.broadway_one_gap_bonus
    if gap == 2:
        return rules.broadway_two_gap_bonus
    return 0


def _with_effective_base(features: MixedFeatures, rules: MixedPolicyRules) -> MixedFeatures:
    """先做既有修正，再按第十九版口径抬顶对加更低公对。"""
    adjusted = _with_capped_board_base(_with_broadway_base(features, rules), rules)
    return _with_top_pair_board_base(adjusted, rules)


def _with_top_pair_board_base(
    features: MixedFeatures, rules: MixedPolicyRules
) -> MixedFeatures:
    """开关关闭或没有可抬的顶对分时原样返回，避免改动旧身份的特征对象。"""
    if not rules.top_pair_board_pair_caliber or features.top_pair_board_pair_base <= 0:
        return features
    lifted = max(features.base, features.top_pair_board_pair_base)
    if lifted == features.base:
        return features
    return replace(features, base=lifted)


def _with_capped_board_base(features: MixedFeatures, rules: MixedPolicyRules) -> MixedFeatures:
    """开关关闭或局面未标记时原样返回，避免改动旧身份的特征对象。"""
    if not rules.postflop_pair_caliber or not features.capped_board_two_pair:
        return features
    if features.base == _CAPPED_BOARD_PAIR_BASE:
        return features
    return replace(features, base=_CAPPED_BOARD_PAIR_BASE)


def _facing_pair_raise_applies(
    features: MixedFeatures, rules: MixedPolicyRules, style: MixedStyle
) -> bool:
    """激进型翻后面对下注，且有效基础分还没到两对高档。"""
    return bool(
        rules.postflop_pair_caliber
        and style is MixedStyle.AGGRESSIVE
        and features.street is not Street.PREFLOP
        and features.actual_call > 0
        and features.base < _THIN_VALUE_BASE
    )


def _close_facing_pair_raise(
    features: MixedFeatures,
    rules: MixedPolicyRules,
    style: MixedStyle,
    value_quality: int,
    bluff_quality: int,
) -> tuple[int, int]:
    """收掉单对价值加注；没有听牌且基础分达到成牌下沿时，非价值加注也收掉。

    半诈唬、无人下注和两对高档及以上保持原质量。开关关闭时原样返回。
    """
    if not _facing_pair_raise_applies(features, rules, style):
        return value_quality, bluff_quality
    value_quality = 0
    if features.draw == 0 and features.base >= _CHECKED_VALUE_FLOOR:
        bluff_quality = 0
    return value_quality, bluff_quality


def _with_broadway_base(features: MixedFeatures, rules: MixedPolicyRules) -> MixedFeatures:
    """需要修正时换上有效翻前基础分；否则原样返回，避免改动旧身份的特征对象。"""
    bonus = _broadway_bonus(features, rules)
    adjusted = (
        features
        if bonus == 0
        else replace(features, base=clip(features.base + bonus, 0, 1000))
    )
    return _with_unopened_late_caliber(adjusted, rules)


def _with_unopened_late_caliber(
    features: MixedFeatures, rules: MixedPolicyRules
) -> MixedFeatures:
    """翻前补国王后连张分，并在未开池、前位已有弃牌时恢复后位。

    开关关闭或不是翻前时原样返回。一旦已有人加注，未开池加成为 0。
    低于强牌下沿的牌加上后位分后停在强牌通道之外。
    """
    if not rules.late_unopened_draw_caliber or features.street is not Street.PREFLOP:
        return features
    base = features.base
    high = max(features.hole_ranks)
    low = min(features.hole_ranks)
    if high == 13 and low == 12:
        base = clip(base + _KQ_CONNECTOR_BONUS, 0, 1000)
    position = features.position
    folded = max(0, features.seat_count - 1 - features.contenders)
    if features.preflop_unraised and features.limpers == 0 and folded > 0:
        position = clip(
            features.position
            + (_UNOPENED_POSITION_SPAN * folded) // max(1, features.seat_count - 1),
            -40,
            40,
        )
        if base >= _UNOPENED_PLAYABLE_BASE:
            added = min(_UNOPENED_BASE_CAP, _UNOPENED_BASE_STEP * folded)
            if base < _STRONG_PREFLOP_BASE:
                base = min(base + added, _STRONG_PREFLOP_BASE - 1)
            else:
                base = clip(base + added, 0, 1000)
    if base == features.base and position == features.position:
        return features
    return replace(features, base=base, position=position)


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


def _facing_draw_support(
    features: MixedFeatures, rules: MixedPolicyRules
) -> tuple[int, int] | None:
    """翻牌或转牌听牌面对下注时的支撑分与覆盖率。

    街不对、没有待跟注或还原不出补牌时返回空，调用方不改被动分，也不收口加注。
    """
    if features.street is Street.FLOP:
        outs_weight, unseen = _DRAW_FLOP_OUTS_WEIGHT, _DRAW_FLOP_UNSEEN
    elif features.street is Street.TURN:
        outs_weight, unseen = _DRAW_TURN_OUTS_WEIGHT, _DRAW_TURN_UNSEEN
    else:
        return None
    if features.price <= 0 or features.actual_call <= 0 or features.draw <= 0:
        return None
    outs = features.draw // outs_weight
    if outs <= 0:
        return None
    # 翻牌强听牌按两街都没中的补集计成牌率，并推迟多人折扣。不足八张补牌或转牌仍按单街。
    strong_flop_draw = (
        rules.late_unopened_draw_caliber
        and features.street is Street.FLOP
        and outs >= _STRONG_FLOP_DRAW_OUTS
    )
    if strong_flop_draw:
        equity = 1000 - (
            1000
            * (unseen - outs)
            * (unseen - 1 - outs)
            // (unseen * (unseen - 1))
        )
        span = _STRONG_FLOP_DRAW_SPAN
        crowd_start = _STRONG_FLOP_DRAW_FREE_OPPONENTS
    else:
        equity = 1000 * outs // unseen
        span = rules.draw_support_span
        crowd_start = 2
    required = 1000 * features.price // (features.price + 1000)
    coverage = 1000 if required <= 0 else min(1000, 1000 * equity // required)
    retention = max(
        _DRAW_RETENTION_FLOOR,
        1000 - _DRAW_CROWD_STEP * max(0, features.contenders - crowd_start),
    )
    coverage = coverage * retention // 1000
    support = span * coverage // 1000
    return support, coverage


def _story_quality(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """无人下注时，把上一街自己收尾的进攻补进没有听牌也没有 A/K 的空气。"""
    if not rules.story_momentum:
        return 0
    if features.street not in (Street.TURN, Street.RIVER):
        return 0
    if not features.prior_street_aggressor or features.actual_call > 0:
        return 0
    if features.draw > 0 or features.base >= _CHECKED_VALUE_FLOOR:
        return 0
    if features.has_broadway_blocker or features.contenders > 1:
        return 0
    if features.recent_aggression > 1 or features.effective_stack <= 2 * features.pot:
        return 0
    raw = (
        rules.story_quality_base
        + _STORY_COUNT_STEP * min(features.prior_street_aggression, _STORY_COUNT_CAP)
        - features.texture // _STORY_TEXTURE_DIVISOR
    )
    return max(0, raw)


def _protection_budget(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """顶对带在翻牌或转牌可以整段过牌的百分预算。河牌和这条区间以外为 0。"""
    if not rules.check_range_protection:
        return 0
    if features.street not in (Street.FLOP, Street.TURN):
        return 0
    if not _PROTECTION_BASE_FLOOR <= features.base < _PROTECTION_BASE_CEILING:
        return 0
    budget = rules.check_base_percent
    if features.base < _PROTECTION_WEAK_KICKER:
        budget += _PROTECTION_WEAK_KICKER_PERCENT
    if features.texture >= _PROTECTION_TEXTURE_LINE:
        budget += _PROTECTION_TEXTURE_PERCENT
    if features.contenders > 1:
        budget += _PROTECTION_CROWD_PERCENT * (features.contenders - 1)
    if features.street is Street.TURN:
        budget //= 2
    return min(_PROTECTION_BUDGET_CAP, budget)


def _protection_applies(
    features: MixedFeatures,
    rules: MixedPolicyRules,
    protect_roll: int | None,
) -> bool:
    """开关关闭或未传入隐变量时恒不保护。传入值必须落在百分区间。"""
    if not rules.check_range_protection or protect_roll is None:
        return False
    if not 0 <= protect_roll < 100:
        raise MixedPolicyError(f"过牌保护取值必须落在 [0,100)，收到 {protect_roll}")
    return protect_roll < _protection_budget(features, rules)


def _checked_defense_bonus(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """本街已过牌、面对单次常规下注时，给有摊牌价值的成牌补的被动分。"""
    if not rules.checked_continue:
        return 0
    if features.actor_checks <= 0 or features.actual_call <= 0:
        return 0
    if features.recent_aggression > 1 or features.contenders >= _DEFENSE_CONTENDER_CAP:
        return 0
    if features.price >= _DEFENSE_PRICE_CAP:
        return 0
    if not _DEFENSE_BASE_FLOOR <= features.base < _DEFENSE_BASE_CEILING:
        return 0
    bonus = (
        _DEFENSE_CROWD_SPAN if features.contenders >= 2 else rules.checked_defense_span
    )
    if features.price >= _DEFENSE_PRICE_HALVE:
        bonus //= 2
    return bonus


def _delayed_probe_quality(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """单挑、无人下注、没有摊牌价值时补进非价值质量的一小段探测。"""
    if not rules.delayed_probe or features.street is Street.PREFLOP:
        return 0
    if features.actual_call > 0 or features.draw > 0 or features.has_broadway_blocker:
        return 0
    if features.base >= _PROBE_BASE_CEILING or features.contenders > 1:
        return 0
    if features.recent_aggression > 0 or features.prior_street_aggressor:
        return 0
    if features.effective_stack <= features.pot:
        return 0
    if features.position < 0 and not features.prior_street_checked_through:
        return 0
    quality = rules.delayed_probe_quality
    if features.prior_street_checked_through:
        quality += _PROBE_CHECKED_BONUS
    if features.street is Street.RIVER:
        quality += _PROBE_RIVER_BONUS
    quality -= features.texture // _PROBE_TEXTURE_DIVISOR
    return min(_PROBE_QUALITY_CAP, max(0, quality))


def _trap_budget(features: MixedFeatures, rules: MixedPolicyRules) -> int:
    """强成牌在翻牌或转牌可以慢打的百分预算。短码、河牌和中等成牌为 0。"""
    if not rules.trap_allocation:
        return 0
    if features.street not in (Street.FLOP, Street.TURN):
        return 0
    if features.street is Street.TURN and rules.check_range_protection:
        return 0
    if features.base < _THIN_VALUE_BASE or features.effective_stack <= features.pot:
        return 0
    raw = (
        rules.trap_base_percent
        - features.texture // _TRAP_TEXTURE_DIVISOR
        - rules.trap_crowd_percent * max(0, features.contenders - 1)
    )
    return max(0, min(_TRAP_BUDGET_CAP, raw))


def _trap_applies(
    features: MixedFeatures,
    rules: MixedPolicyRules,
    trap_roll: int | None,
) -> bool:
    """开关关闭或未传入隐变量时恒不设伏。传入值必须落在百分区间。"""
    if not rules.trap_allocation or trap_roll is None:
        return False
    if not 0 <= trap_roll < 100:
        raise MixedPolicyError(f"设伏取值必须落在 [0,100)，收到 {trap_roll}")
    return trap_roll < _trap_budget(features, rules)


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


def _retains_short_stack_min_raise(
    features: MixedFeatures,
    legal: LegalActions,
    value_quality: int,
    rules: MixedPolicyRules,
) -> bool:
    """主动价值面对短码对手时，是否把上限抬到合法最小加注。

    对手在跟注额内已经全下，或主动质量不是价值时，返回假。
    """
    if not rules.short_stack_min_raise or not legal.can_raise:
        return False
    if features.live_opponents <= 0 or value_quality <= 0:
        return False
    if features.effective_stack <= legal.call_amount:
        return False
    legal_min = legal.min_raise_to
    legal_max = legal.max_raise_to
    covered = features.street_bet + features.effective_stack
    return covered < legal_min <= legal_max


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
    covered = street_bet + features.effective_stack
    upper = min(legal_max, covered)
    if _retains_short_stack_min_raise(features, legal, value_quality, rules):
        # 合法最小加注已经高于对手全下总额；保留这一档，迫使对手全下。
        upper = min(legal_max, max(legal_min, covered))
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
