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
    MIXED_LOCAL_V1_RULES,
    MIXED_LOCAL_V2_RULES,
    MIXED_LOCAL_V3_RULES,
    MIXED_LOCAL_V4_RULES,
    MIXED_LOCAL_V5_RULES,
    MIXED_LOCAL_V6_RULES,
    MIXED_LOCAL_V7_RULES,
    MIXED_STYLE_ORDER,
    HandMode,
    MixedDistribution,
    MixedPolicyRules,
    MixedStyle,
    build_distribution,
    hand_mode_for,
)

# 受控新身份：指本地规则、风格分配、尺寸表、概率量化与随机分流的整个配置集合。
MIXED_STRATEGY_IDENTIFIER = "mixed-local@1"
# 第二版身份：只改共享牌面的跟注价格口径，其余规则与首版逐项一致。
MIXED_STRATEGY_IDENTIFIER_V2 = "mixed-local@2"
# 第三版身份：在第二版基础上放宽翻前跟注门槛，并让三档风格在翻前分开。
MIXED_STRATEGY_IDENTIFIER_V3 = "mixed-local@3"
# 第四版身份：在第三版基础上提高紧密型的翻前跟注偏移，其余规则逐项一致。
MIXED_STRATEGY_IDENTIFIER_V4 = "mixed-local@4"
# 第五版身份：在第四版基础上给跟注型加一个只作用于翻后被动分支的跟注偏移。
MIXED_STRATEGY_IDENTIFIER_V5 = "mixed-local@5"
# 第六版身份：在第五版基础上把主动分支放到与被动分支同一尺度，并给人数惩罚设上限。
MIXED_STRATEGY_IDENTIFIER_V6 = "mixed-local@6"
# 第七版身份：在第六版基础上把非价值进攻依据由离散人数表改为连续量，其余口径一致。
MIXED_STRATEGY_IDENTIFIER_V7 = "mixed-local@7"
MIXED_STRATEGY_IDENTIFIERS: tuple[str, ...] = (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
    MIXED_STRATEGY_IDENTIFIER_V4,
    MIXED_STRATEGY_IDENTIFIER_V5,
    MIXED_STRATEGY_IDENTIFIER_V6,
    MIXED_STRATEGY_IDENTIFIER_V7,
)
# 身份到规则口径的映射；旧身份的含义与分布不随新身份改变。
MIXED_STRATEGY_RULES: dict[str, MixedPolicyRules] = {
    MIXED_STRATEGY_IDENTIFIER: MIXED_LOCAL_V1_RULES,
    MIXED_STRATEGY_IDENTIFIER_V2: MIXED_LOCAL_V2_RULES,
    MIXED_STRATEGY_IDENTIFIER_V3: MIXED_LOCAL_V3_RULES,
    MIXED_STRATEGY_IDENTIFIER_V4: MIXED_LOCAL_V4_RULES,
    MIXED_STRATEGY_IDENTIFIER_V5: MIXED_LOCAL_V5_RULES,
    MIXED_STRATEGY_IDENTIFIER_V6: MIXED_LOCAL_V6_RULES,
    MIXED_STRATEGY_IDENTIFIER_V7: MIXED_LOCAL_V7_RULES,
}
# 手模式取值的均匀整数上界。
_HAND_MODE_ROLL_RANGE = 100


class MixedStrategyError(ValueError):
    """座位集合不一致、行动者不属于 Bot 座位或身份未注册时抛出。"""


def _require_identifier(identifier: str) -> str:
    """未注册的身份直接失败，避免为不存在的版本派生随机流。"""
    if identifier not in MIXED_STRATEGY_RULES:
        raise MixedStrategyError(f"未注册的新策略身份：{identifier}")
    return identifier


def rules_for_identifier(identifier: str) -> MixedPolicyRules:
    """取身份对应的规则口径。"""
    return MIXED_STRATEGY_RULES[_require_identifier(identifier)]


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


def derive_deck_seed(root_key: bytes, identifier: str = MIXED_STRATEGY_IDENTIFIER) -> int:
    """牌堆派生种子：与 Bot 派生流分离，可传给既有引擎 seed 参数。"""
    return _derived_int(_derive(root_key, (_require_identifier(identifier), "deck")))


def derive_bots_key(root_key: bytes, identifier: str = MIXED_STRATEGY_IDENTIFIER) -> bytes:
    """Bot 分支的父级键：分派器与子策略只拿到它，拿不到主键。"""
    return _derive(root_key, (_require_identifier(identifier), "bots"))


def seat_style_map(bot_seats: Iterable[int]) -> dict[int, MixedStyle]:
    """按 Bot 座位升序循环分配三种风格；低人数桌不制造不存在的同桌差异。"""
    seats = sorted(bot_seats)
    return {
        seat: MIXED_STYLE_ORDER[index % len(MIXED_STYLE_ORDER)]
        for index, seat in enumerate(seats)
    }


class MixedSeatPolicy:
    """单个 Bot 座位的私有子策略：无状态、只持有本座位的派生键与固定风格。"""

    def __init__(
        self,
        *,
        seat: int,
        style: MixedStyle,
        seat_key: bytes,
        rules: MixedPolicyRules = MIXED_LOCAL_V1_RULES,
    ) -> None:
        self._seat = seat
        self._style = style
        self._seat_key = seat_key
        self._rules = rules

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
        return build_distribution(
            features, legal, self._style, mode or self.hand_mode(verified), self._rules
        )

    def features_for(self, verified: VerifiedMixedInput, legal: LegalActions) -> MixedFeatures:
        """暴露特征供离线验证与报告使用，不改变抽样路径。"""
        return features_for(verified, legal)

    def choose_action(self, verified: VerifiedMixedInput, legal: LegalActions) -> Action:
        """按本座位派生流采样一个动作；不读取其他座位或主键。"""
        mode = self.hand_mode(verified)
        distribution = build_distribution(
            features_for(verified, legal), legal, self._style, mode, self._rules
        )
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
        identifier: str = MIXED_STRATEGY_IDENTIFIER,
    ) -> None:
        self._identifier = _require_identifier(identifier)
        self._rules = MIXED_STRATEGY_RULES[self._identifier]
        self._root_key = derive_root_key(seed) if root_key is None else root_key
        self._bots_key = derive_bots_key(self._root_key, self._identifier)
        self._policies: dict[int, MixedSeatPolicy] = {}
        self._bot_seats: tuple[int, ...] = ()
        if bot_seats is not None:
            self._bind(tuple(bot_seats))

    @property
    def bot_seats(self) -> tuple[int, ...]:
        """已绑定的 Bot 座位集合；未绑定时为空元组。"""
        return self._bot_seats

    @property
    def identifier(self) -> str:
        """本实例的版本身份。"""
        return self._identifier

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
                rules=self._rules,
            )
            for seat in candidate
        }

    def _require_binding(self) -> None:
        if not self._bot_seats:
            raise MixedStrategyError("尚未绑定 Bot 座位集合")
