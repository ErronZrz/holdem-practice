"""受控策略注册表：把版本化策略标识映射到工厂。

设计目的：
- 客户端只能提交注册表内的受控标识，不能提交类名、模块路径或属性链；
- 策略标识带版本（形如 ``name@version``），新策略不会被旧名称吞掉；
- 旧请求值通过固定别名表映射到各自的历史版本，别名不随新版本前移。
"""

from collections.abc import Callable
from dataclasses import dataclass

from .distribution_observation import (
    CapabilityDeclaration,
    CapabilityHealth,
    DeclarationMissingError,
    DistributionObservationEntry,
    declaration_for,
    entry_for,
    health_status,
    register_observation_entry,
    supported_declaration,
)
from .heuristic import HeuristicStrategy
from .interface import Strategy
from .mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
    MIXED_STRATEGY_IDENTIFIER_V4,
    MIXED_STRATEGY_IDENTIFIER_V5,
    MIXED_STRATEGY_IDENTIFIER_V6,
    MIXED_STRATEGY_IDENTIFIER_V7,
    MIXED_STRATEGY_IDENTIFIER_V8,
    MIXED_STRATEGY_IDENTIFIER_V9,
    MIXED_STRATEGY_IDENTIFIER_V10,
    MIXED_STRATEGY_IDENTIFIER_V11,
    MIXED_STRATEGY_IDENTIFIER_V12,
    MIXED_STRATEGY_IDENTIFIER_V13,
    MIXED_STRATEGY_IDENTIFIER_V14,
    MIXED_STRATEGY_IDENTIFIER_V15,
    MIXED_STRATEGY_RULES,
    MixedLocalStrategy,
)
from .random_strategy import RandomStrategy


class UnknownStrategyError(ValueError):
    """提交的策略标识不在受控注册表内。"""


@dataclass(frozen=True)
class StrategySpec:
    """一个受控策略的注册项。"""

    identifier: str
    name: str
    version: int
    factory: Callable[[int | None], Strategy]
    description: str


_REGISTRY: dict[str, StrategySpec] = {}
# 旧请求值 -> 规范标识；注册后不再变动，避免把新策略偷偷标成旧名称。
_LEGACY_ALIASES: dict[str, str] = {}


def register_strategy(spec: StrategySpec, aliases: tuple[str, ...] = ()) -> None:
    """注册一个策略；标识或别名重复都视为配置错误。"""
    if spec.identifier in _REGISTRY:
        raise ValueError(f"策略标识已注册：{spec.identifier}")
    for alias in aliases:
        if alias in _LEGACY_ALIASES:
            raise ValueError(f"策略别名已占用：{alias}")
    _REGISTRY[spec.identifier] = spec
    for alias in aliases:
        _LEGACY_ALIASES[alias] = spec.identifier


def resolve_identifier(value: str) -> str:
    """把客户端提交值规范化为注册表中的规范标识，未知标识直接失败。"""
    if isinstance(value, str):
        if value in _REGISTRY:
            return value
        alias = _LEGACY_ALIASES.get(value)
        if alias is not None:
            return alias
    raise UnknownStrategyError(f"未知策略标识：{value!r}")


def spec_for(value: str) -> StrategySpec:
    """取注册项，包含版本与描述。"""
    return _REGISTRY[resolve_identifier(value)]


def create_strategy(value: str, seed: int | None = None) -> Strategy:
    """按受控标识构造策略实例。"""
    return spec_for(value).factory(seed)


def known_identifiers() -> tuple[str, ...]:
    """返回全部规范标识，供诊断与测试枚举。"""
    return tuple(sorted(_REGISTRY))


def _canonical_identifier(value: str) -> str:
    """把提交值规范化为规范标识；未知标识按「没有能力声明」处理。"""
    try:
        return resolve_identifier(value)
    except UnknownStrategyError as error:
        raise DeclarationMissingError(f"未知策略标识，无能力声明：{value!r}") from error


def capability_declaration(value: str) -> CapabilityDeclaration:
    """声明读取入口：按规范标识取能力声明，不需要实例化被测策略。"""
    return declaration_for(_canonical_identifier(value))


def capability_health() -> CapabilityHealth:
    """能力健康读取入口：不接受任何输入，也不读取对局状态。"""
    return health_status()


def observation_entry(value: str) -> DistributionObservationEntry:
    """查询调用入口：返回绑定该身份的观测句柄。

    句柄的观测输入为安全状态、合法动作集与可选的模式覆盖三项。
    """
    return entry_for(_canonical_identifier(value))


# 三项能力入口的登记：静态检查只读这张表，不发起任何调用。
OBSERVATION_ENTRYPOINTS: dict[str, Callable[..., object]] = {
    "declaration": capability_declaration,
    "health": capability_health,
    "query": observation_entry,
}


register_strategy(
    StrategySpec(
        identifier="heuristic@1",
        name="heuristic",
        version=1,
        factory=lambda seed: HeuristicStrategy(seed=seed),
        description="基于胜率与底池赔率的启发式策略，同时是教学参考基线",
    ),
    aliases=("heuristic",),
)
register_strategy(
    StrategySpec(
        identifier="random@1",
        name="random",
        version=1,
        factory=lambda seed: RandomStrategy(seed=seed),
        description="从合法动作中均匀随机选择的基线策略",
    ),
    aliases=("random",),
)
# 新身份不设无版本别名：调用方必须显式提交版本化标识，旧名称不会被悄悄换掉。
register_strategy(
    StrategySpec(
        identifier="mixed-local@1",
        name="mixed-local",
        version=1,
        factory=lambda seed: MixedLocalStrategy(seed=seed),
        description="本地规则型混合对手：座位分派多风格、动作与尺度联合混合、随机源域分离",
    ),
)
# 第二版与首版并存：首版的身份含义、分布与证据保持不变，不覆盖也不迁移。
register_strategy(
    StrategySpec(
        identifier="mixed-local@2",
        name="mixed-local",
        version=2,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V2
        ),
        description="本地规则型混合对手第二版：锁定平分局面按分池价格处理，其余规则与首版一致",
    ),
)
# 第三版为累积版：含第二版口径，并放宽翻前跟注门槛、让三档风格在翻前分开。
register_strategy(
    StrategySpec(
        identifier="mixed-local@3",
        name="mixed-local",
        version=3,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V3
        ),
        description="本地规则型混合对手第三版：翻前跟注门槛与风格偏移，累积第二版的分池口径",
    ),
)
# 第四版为累积版：只把紧密型的翻前跟注偏移提高，其余口径与第三版一致。
register_strategy(
    StrategySpec(
        identifier="mixed-local@4",
        name="mixed-local",
        version=4,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V4
        ),
        description="本地规则型混合对手第四版：提高紧密型翻前跟注偏移，累积第三版口径",
    ),
)
# 第五版为累积版：翻前与第四版一致，只给跟注型加翻后被动的跟注偏移。
register_strategy(
    StrategySpec(
        identifier="mixed-local@5",
        name="mixed-local",
        version=5,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V5
        ),
        description="本地规则型混合对手第五版：跟注型翻后更黏，累积第四版口径",
    ),
)
# 第六版为累积版：主动分支与被动分支同尺度，人数惩罚带上限，其余口径与第五版一致。
register_strategy(
    StrategySpec(
        identifier="mixed-local@6",
        name="mixed-local",
        version=6,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V6
        ),
        description="本地规则型混合对手第六版：主动分支与被动分支同尺度、人数惩罚带上限，累积第五版口径",
    ),
)
# 第七版为累积版：非价值进攻依据改为公开特征定义的连续量，其余口径与第六版一致。
register_strategy(
    StrategySpec(
        identifier="mixed-local@7",
        name="mixed-local",
        version=7,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V7
        ),
        description="本地规则型混合对手第七版：非价值进攻依据改为连续量，累积第六版口径",
    ),
)
# 第八版为累积版：翻后主动门槛随公开局面按风格分化，其余口径与第七版一致。
register_strategy(
    StrategySpec(
        identifier="mixed-local@8",
        name="mixed-local",
        version=8,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V8
        ),
        description="本地规则型混合对手第八版：翻后主动门槛随公开局面按风格分化，累积第七版口径",
    ),
)
# 第九版为累积版：面对下注时听牌进入加注，无人下注时成牌托住主动质量。
register_strategy(
    StrategySpec(
        identifier="mixed-local@9",
        name="mixed-local",
        version=9,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V9
        ),
        description="本地规则型混合对手第九版：面对下注的听牌延续与无人下注的成牌兑现，累积第八版口径",
    ),
)
# 第十版为累积版：只收紧大额承诺的跟注与多人底池的薄价值，其余口径与第九版一致。
register_strategy(
    StrategySpec(
        identifier="mixed-local@10",
        name="mixed-local",
        version=10,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V10
        ),
        description="本地规则型混合对手第十版：大额承诺少跟注，多人底池少打薄价值，累积第九版口径",
    ),
)
# 第十一版为累积版：强成牌加大尺度兑现，满员桌收紧中等牌力的深跟注。
register_strategy(
    StrategySpec(
        identifier="mixed-local@11",
        name="mixed-local",
        version=11,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V11
        ),
        description="本地规则型混合对手第十一版：强成牌加大兑现，满员桌少做深跟注，累积第十版口径",
    ),
)
# 第十二版为累积版：强成牌仍兑现，但翻前不放大尺度，面对下注不层层加码。
register_strategy(
    StrategySpec(
        identifier="mixed-local@12",
        name="mixed-local",
        version=12,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V12
        ),
        description="本地规则型混合对手第十二版：强成牌少把底池打大，同花及以上在无人下注时兑现整叠，累积第十一版口径",
    ),
)
# 第十三版为累积版：主动尺度按小盲对齐，其余口径与第十二版一致。
register_strategy(
    StrategySpec(
        identifier="mixed-local@13",
        name="mixed-local",
        version=13,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V13
        ),
        description="本地规则型混合对手第十三版：下注与加注按小盲对齐，累积第十二版口径",
    ),
)
# 第十四版为累积版：强成牌可设伏，空气可续枪，听牌面对下注按覆盖率跟注。
register_strategy(
    StrategySpec(
        identifier="mixed-local@14",
        name="mixed-local",
        version=14,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V14
        ),
        description="本地规则型混合对手第十四版：强成牌设伏、空气续枪、听牌按覆盖率跟注，累积第十三版口径",
    ),
)
# 第十五版为累积版：翻前 A 高张用有效基础分开池，其余口径与第十四版一致。
register_strategy(
    StrategySpec(
        identifier="mixed-local@15",
        name="mixed-local",
        version=15,
        factory=lambda seed: MixedLocalStrategy(
            seed=seed, identifier=MIXED_STRATEGY_IDENTIFIER_V15
        ),
        description="本地规则型混合对手第十五版：翻前高张开池，累积第十四版口径",
    ),
)
# 分布观测按身份显式登记。第八版与第九版保持原声明；第十版使用自己的规则。
register_observation_entry(
    MIXED_STRATEGY_IDENTIFIER_V8,
    supported_declaration(),
    MIXED_STRATEGY_RULES[MIXED_STRATEGY_IDENTIFIER_V8],
)
register_observation_entry(
    MIXED_STRATEGY_IDENTIFIER_V9,
    supported_declaration(),
    MIXED_STRATEGY_RULES[MIXED_STRATEGY_IDENTIFIER_V9],
)
register_observation_entry(
    MIXED_STRATEGY_IDENTIFIER_V10,
    supported_declaration(),
    MIXED_STRATEGY_RULES[MIXED_STRATEGY_IDENTIFIER_V10],
)
register_observation_entry(
    MIXED_STRATEGY_IDENTIFIER_V11,
    supported_declaration(),
    MIXED_STRATEGY_RULES[MIXED_STRATEGY_IDENTIFIER_V11],
)
register_observation_entry(
    MIXED_STRATEGY_IDENTIFIER_V12,
    supported_declaration(),
    MIXED_STRATEGY_RULES[MIXED_STRATEGY_IDENTIFIER_V12],
)
register_observation_entry(
    MIXED_STRATEGY_IDENTIFIER_V13,
    supported_declaration(),
    MIXED_STRATEGY_RULES[MIXED_STRATEGY_IDENTIFIER_V13],
)
register_observation_entry(
    MIXED_STRATEGY_IDENTIFIER_V14,
    supported_declaration(),
    MIXED_STRATEGY_RULES[MIXED_STRATEGY_IDENTIFIER_V14],
)
register_observation_entry(
    MIXED_STRATEGY_IDENTIFIER_V15,
    supported_declaration(),
    MIXED_STRATEGY_RULES[MIXED_STRATEGY_IDENTIFIER_V15],
)
