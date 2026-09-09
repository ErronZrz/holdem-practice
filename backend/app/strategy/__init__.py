"""Bot 策略层，插件式接口，与具体牌型解耦。"""

from .heuristic import HeuristicStrategy
from .interface import Strategy, hero
from .random_strategy import RandomStrategy

__all__ = ["Strategy", "hero", "RandomStrategy", "HeuristicStrategy"]
