"""Bot 策略层，插件式接口，与具体牌型解耦。"""

from .heuristic import HeuristicStrategy
from .interface import Strategy, hero
from .projection import project_for_actor
from .random_strategy import RandomStrategy
from .registry import StrategySpec, UnknownStrategyError, create_strategy, resolve_identifier

__all__ = [
    "Strategy",
    "hero",
    "RandomStrategy",
    "HeuristicStrategy",
    "StrategySpec",
    "UnknownStrategyError",
    "create_strategy",
    "resolve_identifier",
    "project_for_actor",
]
