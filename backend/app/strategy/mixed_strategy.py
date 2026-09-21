"""新 Bot 的策略入口：随机源域分离、座位分派器与互不共享状态的子策略。

随机纪律：
- 主键只在 API/工厂边界产生，牌堆与 Bot 派生流互不可推；
- 分派器与子策略都不持有主键、不持有引擎、不共享底牌、特征或缓存；
- 子策略是无状态函数式实现：同一手号、事件数、输入与版本必然得到同一结果，
  查询分布不消耗行动随机流。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
from collections.abc import Iterable, Sequence

from app.poker.actions import Action, LegalActions
from app.poker.state import GameState

from .mixed_context import MixedContextError, VerifiedMixedInput, require_mixed_input
from .mixed_features import MixedFeatures, features_for
from .mixed_policy import (
    MIXED_STYLE_ORDER,
    HandMode,
    MixedDistribution,
    MixedStyle,
    build_distribution,
    hand_mode_for,
)

# 受控新身份：指本地规则、风格分配、尺寸表、概率量化与随机分流的整个配置集合。
MIXED_STRATEGY_IDENTIFIER = "mixed-local@1"
# 手模式取值的均匀整数上界。
_HAND_MODE_ROLL_RANGE = 100


class MixedStrategyError(ValueError):
    """座位集合不一致、行动者不属于 Bot 座位或未知座位时抛出。"""


def derive_root_key(seed: int | None) -> bytes:
    """由显式 seed 或一次性系统熵产生主键；主键不落库、不外发。"""
    if seed is None:
        return os.urandom(32)
    return hashlib.sha256(str(seed).encode("utf-8")).digest()


def _derive(parent_key: bytes, message: Sequence[object]) -> bytes:
    """按固定的 HMAC-SHA256 与紧凑 JSON 消息派生下一级键。"""
    payload = json.dumps(list(message), separators=(",", ":"), ensure_ascii=True)
    return hmac.new(parent_key, payload.encode("utf-8"), hashlib.sha256).digest()


def _derived_int(digest: bytes) -> int:
    """把派生摘要视为非负整数，作为标准库随机源的种子。"""
    return int.from_bytes(digest, "big")


def derive_deck_seed(root_key: bytes) -> int:
    """牌堆派生种子：与 Bot 派生流分离，可传给既有引擎 seed 参数。"""
    return _derived_int(_derive(root_key, (MIXED_STRATEGY_IDENTIFIER, "deck")))


def derive_bots_key(root_key: bytes) -> bytes:
    """Bot 分支的父级键：分派器与子策略只拿到它，拿不到主键。"""
    return _derive(root_key, (MIXED_STRATEGY_IDENTIFIER, "bots"))


def seat_style_map(bot_seats: Iterable[int]) -> dict[int, MixedStyle]:
    """按 Bot 座位升序循环分配三种风格；低人数桌不制造不存在的同桌差异。"""
    seats = sorted(bot_seats)
    return {
        seat: MIXED_STYLE_ORDER[index % len(MIXED_STYLE_ORDER)]
        for index, seat in enumerate(seats)
    }


class MixedSeatPolicy:
    """单个 Bot 座位的私有子策略：无状态、只持有本座位的派生键与固定风格。"""

    def __init__(self, *, seat: int, style: MixedStyle, seat_key: bytes) -> None:
        self._seat = seat
        self._style = style
        self._seat_key = seat_key

    @property
    def seat(self) -> int:
        """该子策略负责的座位。"""
        return self._seat

    @property
    def style(self) -> MixedStyle:
        """该座位的固定风格，session 内不变。"""
        return self._style

    def distribution_for(
        self,
        verified: VerifiedMixedInput,
        legal: LegalActions,
        mode: HandMode | None = None,
    ) -> MixedDistribution:
        """给出本次决策的分布；显式指定模式只供离线验证与测试使用。"""
        features = features_for(verified, legal)
        return build_distribution(features, legal, self._style, mode or self.hand_mode(verified))

    def features_for(self, verified: VerifiedMixedInput, legal: LegalActions) -> MixedFeatures:
        """暴露特征供离线验证与报告使用，不改变抽样路径。"""
        return features_for(verified, legal)

    def choose_action(self, verified: VerifiedMixedInput, legal: LegalActions) -> Action:
        """按本座位派生流采样一个动作；不读取其他座位或主键。"""
        mode = self.hand_mode(verified)
        distribution = build_distribution(features_for(verified, legal), legal, self._style, mode)
        return distribution.sample(self._action_rng(verified))

    def hand_mode(self, verified: VerifiedMixedInput) -> HandMode:
        """每手一次的隐变量；同一手号重复计算得到同一模式，不消耗行动流。"""
        digest = _derive(self._seat_key, ("hand", verified.context.hand_number, "mode"))
        roll = random.Random(_derived_int(digest)).randrange(_HAND_MODE_ROLL_RANGE)
        return hand_mode_for(roll)

    def _action_rng(self, verified: VerifiedMixedInput) -> random.Random:
        """本次动作专用随机源：按手号与事件数分离，可独立重放。"""
        digest = _derive(
            self._seat_key,
            ("hand", verified.context.hand_number, "action", verified.context.event_count),
        )
        return random.Random(_derived_int(digest))


class MixedLocalStrategy:
    """座位分派器：按上下文建立各 Bot 座位的私有子策略并转发决策。"""

    def __init__(
        self,
        seed: int | None = None,
        *,
        root_key: bytes | None = None,
        bot_seats: Sequence[int] | None = None,
    ) -> None:
        self._root_key = derive_root_key(seed) if root_key is None else root_key
        self._bots_key = derive_bots_key(self._root_key)
        self._policies: dict[int, MixedSeatPolicy] = {}
        self._bot_seats: tuple[int, ...] = ()
        if bot_seats is not None:
            self._bind(tuple(bot_seats))

    @property
    def bot_seats(self) -> tuple[int, ...]:
        """已绑定的 Bot 座位集合；未绑定时为空元组。"""
        return self._bot_seats

    def style_for(self, seat: int) -> MixedStyle:
        """查询某座位的固定风格，供离线报告与测试使用。"""
        self._require_binding()
        policy = self._policies.get(seat)
        if policy is None:
            raise MixedStrategyError(f"座位 {seat} 不属于本局 Bot 座位")
        return policy.style

    def choose_action(self, state: GameState, legal: LegalActions) -> Action:
        """按当前行动者座位转发决策；座位集合不一致时明确失败。"""
        verified = require_mixed_input(state)
        self._bind(verified.context.bot_seats)
        policy = self._policies.get(verified.actor_seat)
        if policy is None:
            raise MixedStrategyError(f"座位 {verified.actor_seat} 不在 Bot 座位集合内")
        return policy.choose_action(verified, legal)

    def distribution_for(
        self,
        state: GameState,
        legal: LegalActions,
        mode: HandMode | None = None,
    ) -> MixedDistribution:
        """离线查询当前行动者的分布；不消耗行动随机流。"""
        verified = require_mixed_input(state)
        self._bind(verified.context.bot_seats)
        policy = self._policies.get(verified.actor_seat)
        if policy is None:
            raise MixedStrategyError(f"座位 {verified.actor_seat} 不在 Bot 座位集合内")
        return policy.distribution_for(verified, legal, mode)

    # ------------------------------------------------------------------ 内部

    def _bind(self, seats: Sequence[int]) -> None:
        """首次绑定 Bot 座位并建立子策略；之后拒绝不一致的集合。"""
        candidate = tuple(seats)
        if self._bot_seats:
            if candidate != self._bot_seats:
                raise MixedStrategyError("同一对局内 Bot 座位集合发生了变化")
            return
        if not candidate:
            raise MixedContextError("公开摘要未提供 Bot 座位")
        self._bot_seats = candidate
        styles = seat_style_map(candidate)
        self._policies = {
            seat: MixedSeatPolicy(
                seat=seat,
                style=styles[seat],
                # 座位键由分派器派生后单向交给子策略，子策略拿不到父级键。
                seat_key=_derive(self._bots_key, ("seat", seat)),
            )
            for seat in candidate
        }

    def _require_binding(self) -> None:
        if not self._bot_seats:
            raise MixedStrategyError("尚未绑定 Bot 座位集合")
