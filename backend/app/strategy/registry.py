"""受控策略注册表：把版本化策略标识映射到工厂。

设计目的：
- 客户端只能提交注册表内的受控标识，不能提交类名、模块路径或属性链；
- 策略标识带版本（形如 ``name@version``），新策略不会被旧名称吞掉；
- 旧请求值通过固定别名表映射到各自的历史版本，别名不随新版本前移。
"""

from collections.abc import Callable
from dataclasses import dataclass

from .heuristic import HeuristicStrategy
from .interface import Strategy
from .mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
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
