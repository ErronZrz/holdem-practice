"""基于公开行动线的范围假设契约：把位置投影映射成对手起手牌类的显式假设。

设计目的：
- 既有估值口径是「面对随机底牌」的静态近似，无法利用公开行动线收紧对手范围；
- 本模块把 P1-1 的位置投影按对手**角色**映射成一套**显式的起手牌类权重**，并如实声明
  这是模型推断而不是读取真实底牌；
- 假设自带受控 profile 标识（``name@version``）与来源标注，与参考来源一起版本化。

边界：
- 唯一输入是位置投影；本模块不接收公共牌、底池、筹码与任何真实底牌，因此在结构上既
  无法读取对手暗牌与未来牌，也无法随公共牌收窄；
- 权重不是概率：把起手牌类权重组合成具体组合概率需要组合数步骤，不在本模块范围；
- 本模块不接入任何生产路径，也不实现采样、胜率、share 或 EV。
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.strategy.position_projection import POSITION_ACTION_TOKENS, PositionProjection

# 契约结构版本：字段集或口径变更时必须同步更新文档与测试。
RANGE_ASSUMPTION_SCHEMA_VERSION = "range-assumption.v1"
# 内置受控 profile 标识：新增档位或改动排序都属于契约变更，必须升版本。
DEFAULT_RANGE_PROFILE_IDENTIFIER = "action-line-roles@1"
# 来源标注：本模块只产出「声明的模型假设」，不接受求解器或训练产物口径。
RANGE_SOURCE_DECLARED_ASSUMPTION = "declared-model-assumption"
RANGE_ALLOWED_SOURCES = (RANGE_SOURCE_DECLARED_ASSUMPTION,)
# 对照口径：当前生产参考仍为「vs 随机范围」，本模块只作声明性对照，不复制其事实源。
RANGE_CONTRAST_COVERAGE = "vs-random"

# 起手牌类顺序的 rank 序列：仅用于生成冻结顺序，不代表牌力。
RANGE_RANKS = ("A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2")
# 权重取值：起手牌类是否落在假设内。
RANGE_WEIGHT_INCLUDED = 1.0
RANGE_WEIGHT_EXCLUDED = 0.0
# 起手牌类总数：对子 13 个加非对子 156 个。
RANGE_HAND_CLASS_COUNT = 169

# 对手角色：闭集，由公开行动线唯一派生。
RANGE_ROLE_AGGRESSOR = "aggressor"
RANGE_ROLE_CALLER = "caller"
RANGE_ROLE_BLIND = "blind"
RANGE_ROLE_UNACTED = "unacted"
RANGE_ROLE_FOLDED = "folded"
RangeRole = Literal["aggressor", "caller", "blind", "unacted", "folded"]
RANGE_ROLES = (
    RANGE_ROLE_AGGRESSOR,
    RANGE_ROLE_CALLER,
    RANGE_ROLE_BLIND,
    RANGE_ROLE_UNACTED,
    RANGE_ROLE_FOLDED,
)
# 角色 -> profile 中对应的档位字段：两者必须保持一一对应，改一处即契约变更。
RANGE_ROLE_CLASS_COUNT_FIELDS = {
    RANGE_ROLE_AGGRESSOR: "aggressor_class_count",
    RANGE_ROLE_CALLER: "caller_class_count",
    RANGE_ROLE_BLIND: "blind_class_count",
    RANGE_ROLE_UNACTED: "unacted_class_count",
    RANGE_ROLE_FOLDED: "folded_class_count",
}

# 局限声明：集中定义，避免调用方各写一份。
RANGE_LIMITATION_NOT_A_SOLVER = "范围假设是人为声明的模型假设，不是求解器输出。"
RANGE_LIMITATION_NO_BOARD_NARROWING = "范围假设只由公开行动线派生，不随公共牌收窄。"
RANGE_LIMITATION_NOT_PROBABILITY = "权重是起手牌类的包含指示，不是概率。"
RANGE_LIMITATION_NOT_REAL_CARDS = "假设与对手真实底牌无关，与假设不符不算错误。"
RANGE_LIMITATIONS = (
    RANGE_LIMITATION_NOT_A_SOLVER,
    RANGE_LIMITATION_NO_BOARD_NARROWING,
    RANGE_LIMITATION_NOT_PROBABILITY,
    RANGE_LIMITATION_NOT_REAL_CARDS,
)

# 各模型的字段集：新增或删减字段都属于契约变更，必须同步更新文档与测试。
RANGE_PROFILE_FIELDS = (
    "profile_identifier",
    "source",
    "basis",
    "aggressor_class_count",
    "caller_class_count",
    "blind_class_count",
    "unacted_class_count",
    "folded_class_count",
    "max_aggressive_actions_per_street",
)
OPPONENT_RANGE_FIELDS = (
    "relative_seat",
    "role",
    "contests_pot",
    "class_count",
    "weights",
)
RANGE_ASSUMPTION_FIELDS = (
    "schema_version",
    "profile_identifier",
    "source",
    "player_count",
    "street",
    "relative_actor",
    "opponents",
    "limitations",
)

# 公开行动线 token 词表与关键 token：从位置投影模块派生，避免两处各写一份。
_POSITION_TOKEN_VALUES = frozenset(POSITION_ACTION_TOKENS.values())
_AGGRESSIVE_TOKENS = frozenset(
    {POSITION_ACTION_TOKENS["bet"], POSITION_ACTION_TOKENS["raise"]}
)
_FORCED_TOKENS = frozenset(
    {POSITION_ACTION_TOKENS["small_blind"], POSITION_ACTION_TOKENS["big_blind"]}
)
_FOLD_TOKEN = POSITION_ACTION_TOKENS["fold"]
_CALL_TOKEN = POSITION_ACTION_TOKENS["call"]
_CHECK_TOKEN = POSITION_ACTION_TOKENS["check"]


class RangeAssumptionError(ValueError):
    """范围假设构造失败。"""


class RangeContractError(RangeAssumptionError):
    """范围假设契约被违反（类型错误、档位越界等结构性非法输入）。"""


class UnknownRangeProfileError(RangeAssumptionError):
    """profile 标识未知或版本不受支持。"""


class OutOfProfileError(RangeAssumptionError):
    """输入超出该 profile 的建模范围（如单街主动下注次数过多）。"""


class _FrozenModel(BaseModel):
    """本模块全部对外模型的公共基类：冻结、禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _build_hand_class_order() -> tuple[str, ...]:
    """按显式约定生成 169 个起手牌类：对子优先、高牌降序、同花先于非同花。

    该顺序只用于把档位换算成确定的起手牌类集合，不是牌力排序。
    """
    order = [rank + rank for rank in RANGE_RANKS]
    for high_index, high in enumerate(RANGE_RANKS):
        for low in RANGE_RANKS[high_index + 1 :]:
            order.append(f"{high}{low}s")
            order.append(f"{high}{low}o")
    return tuple(order)


HAND_CLASS_ORDER = _build_hand_class_order()


def _require_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RangeContractError(f"{name} 必须是整数，收到 {type(value).__name__}")


def _require_class_count(name: str, value: object) -> None:
    """档位必须是 0..169 的整数；越界属于契约违规，不做夹紧。"""
    _require_int(name, value)
    if not 0 <= value <= RANGE_HAND_CLASS_COUNT:
        raise RangeContractError(
            f"{name} 必须在 0..{RANGE_HAND_CLASS_COUNT} 之间，收到 {value}"
        )


def weights_for_class_count(class_count: int) -> tuple[float, ...]:
    """把档位换算成 169 项显式权重：前 N 个起手牌类计入，其余不计入。"""
    _require_class_count("class_count", class_count)
    return tuple(
        RANGE_WEIGHT_INCLUDED if index < class_count else RANGE_WEIGHT_EXCLUDED
        for index in range(RANGE_HAND_CLASS_COUNT)
    )


class RangeProfile(_FrozenModel):
    """受控范围档位：按对手角色声明起手牌类档位与建模上限。"""

    profile_identifier: str
    source: str
    basis: str
    aggressor_class_count: int
    caller_class_count: int
    blind_class_count: int
    unacted_class_count: int
    folded_class_count: int
    max_aggressive_actions_per_street: int

    @field_validator("profile_identifier")
    @classmethod
    def _identifier_must_be_versioned(cls, value: str) -> str:
        """标识必须是 name@version 形式，避免出现无法追溯版本的范围来源。"""
        if not isinstance(value, str) or "@" not in value:
            raise ValueError("profile 标识必须形如 name@version")
        name, _, version = value.partition("@")
        if not name or not version.isascii() or not version.isdigit():
            raise ValueError("profile 标识必须形如 name@version")
        return value

    @field_validator("source")
    @classmethod
    def _source_must_be_declared_assumption(cls, value: str) -> str:
        """来源只允许「声明的模型假设」，从结构上禁止冒充求解器或训练产物。"""
        if value not in RANGE_ALLOWED_SOURCES:
            raise ValueError(f"不支持的范围来源标注：{value!r}")
        return value

    @field_validator("basis")
    @classmethod
    def _basis_must_not_be_empty(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("依据声明不能为空")
        return value

    @field_validator(
        "aggressor_class_count",
        "caller_class_count",
        "blind_class_count",
        "unacted_class_count",
        "folded_class_count",
        mode="before",
    )
    @classmethod
    def _class_counts_must_be_in_range(cls, value: object) -> object:
        _require_class_count("class_count", value)
        return value

    @field_validator("folded_class_count")
    @classmethod
    def _folded_range_must_be_empty(cls, value: int) -> int:
        """已弃牌者不持有可争池范围；用非零值表示它不是假设而是错误。"""
        if value != 0:
            raise ValueError("已弃牌角色的档位必须为 0")
        return value

    @field_validator("max_aggressive_actions_per_street")
    @classmethod
    def _aggressive_bound_must_be_positive(cls, value: int) -> int:
        _require_int("max_aggressive_actions_per_street", value)
        if value < 1:
            raise ValueError("单街主动下注/加注的建模上限必须至少为 1")
        return value

    def class_count_for(self, role: str) -> int:
        """取某角色在本 profile 下的档位；未知角色明确失败。"""
        field = RANGE_ROLE_CLASS_COUNT_FIELDS.get(role)
        if field is None:
            raise RangeContractError(f"未知对手角色：{role!r}")
        return int(getattr(self, field))


class OpponentRange(_FrozenModel):
    """单个对手座位的范围假设：角色、是否争池与 169 项显式权重。"""

    relative_seat: int
    role: RangeRole
    contests_pot: bool
    class_count: int
    weights: tuple[float, ...]

    @field_validator("class_count")
    @classmethod
    def _class_count_in_range(cls, value: int) -> int:
        _require_class_count("class_count", value)
        return value

    @field_validator("weights")
    @classmethod
    def _weights_must_match_the_order(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) != RANGE_HAND_CLASS_COUNT:
            raise ValueError(f"权重必须恰好为 {RANGE_HAND_CLASS_COUNT} 项")
        return value

    def model_post_init(self, __context: object) -> None:
        """锁定角色、争池标志、档位与权重之间的自洽，使假设可审计。"""
        if self.role == RANGE_ROLE_FOLDED:
            if self.contests_pot:
                raise RangeContractError("已弃牌角色不参与争池")
            if self.class_count != 0:
                raise RangeContractError("已弃牌角色的档位必须为 0")
        else:
            if not self.contests_pot:
                raise RangeContractError("非弃牌角色仍可能争池")
            if self.class_count < 1:
                raise RangeContractError("争池角色的档位至少为 1，不得用空范围冒充")
        if self.weights != weights_for_class_count(self.class_count):
            raise RangeContractError("权重必须与档位一致，不得另行注入")


class RangeAssumption(_FrozenModel):
    """一次范围假设：受控 profile 标识、来源标注、逐座位角色与显式权重。"""

    schema_version: str
    profile_identifier: str
    source: str
    player_count: int
    street: str
    relative_actor: int
    opponents: tuple[OpponentRange, ...]
    limitations: tuple[str, ...]

    @field_validator("schema_version")
    @classmethod
    def _schema_version_must_match(cls, value: str) -> str:
        if value != RANGE_ASSUMPTION_SCHEMA_VERSION:
            raise ValueError(
                f"范围假设结构版本不匹配：期望 {RANGE_ASSUMPTION_SCHEMA_VERSION}，收到 {value!r}"
            )
        return value

    @field_validator("source")
    @classmethod
    def _source_must_be_declared_assumption(cls, value: str) -> str:
        if value not in RANGE_ALLOWED_SOURCES:
            raise ValueError(f"不支持的范围来源标注：{value!r}")
        return value

    @field_validator("limitations")
    @classmethod
    def _must_declare_the_required_limitations(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        """必须同时声明「非求解器输出」与「不随公共牌收窄」两条局限。"""
        for required in (
            RANGE_LIMITATION_NOT_A_SOLVER,
            RANGE_LIMITATION_NO_BOARD_NARROWING,
        ):
            if required not in value:
                raise ValueError(f"缺少必需的局限声明：{required}")
        return value

    def model_post_init(self, __context: object) -> None:
        """锁定人数、行动者与逐座位覆盖，使假设可复核。"""
        if self.player_count < 2:
            raise RangeContractError("人数必须至少为 2")
        if not 0 <= self.relative_actor < self.player_count:
            raise RangeContractError("行动者相对座位越界")
        expected = [seat for seat in range(self.player_count) if seat != self.relative_actor]
        actual = [opponent.relative_seat for opponent in self.opponents]
        if actual != expected:
            raise RangeContractError(
                "对手范围必须恰好覆盖除行动者外的全部相对座位，按升序且不重不漏"
            )

    def opponent_at(self, relative_seat: int) -> OpponentRange:
        """取某相对座位的假设；行动者自身或被越界座位明确失败。"""
        for opponent in self.opponents:
            if opponent.relative_seat == relative_seat:
                return opponent
        raise RangeContractError(f"相对座位 {relative_seat} 没有对手范围（行动者自身或越界）")


def _default_basis() -> str:
    return (
        "档位按本模块冻结的起手牌类顺序（对子优先、高牌降序、同花先于非同花）取前 N 个类；"
        "该顺序是显式约定，不是牌力排序，也不来自求解器或任何外部来源。"
    )


_BUILTIN_PROFILES: dict[str, RangeProfile] = {}


def register_range_profile(profile: RangeProfile) -> None:
    """登记一个受控 profile；标识重复视为配置错误。"""
    if profile.profile_identifier in _BUILTIN_PROFILES:
        raise ValueError(f"范围 profile 已登记：{profile.profile_identifier}")
    _BUILTIN_PROFILES[profile.profile_identifier] = profile


def range_profiles() -> Mapping[str, RangeProfile]:
    """返回只读的 profile 目录。"""
    return MappingProxyType(_BUILTIN_PROFILES)


def known_profile_identifiers() -> tuple[str, ...]:
    """返回已登记标识的升序元组，供诊断与测试枚举。"""
    return tuple(sorted(_BUILTIN_PROFILES))


def profile_for(identifier: str) -> RangeProfile:
    """取受控 profile；未知标识或版本明确失败，不回落默认档位。"""
    if not isinstance(identifier, str):
        raise RangeContractError(f"profile 标识必须是字符串，收到 {type(identifier).__name__}")
    profile = _BUILTIN_PROFILES.get(identifier)
    if profile is None:
        raise UnknownRangeProfileError(f"未知范围 profile：{identifier!r}")
    return profile


register_range_profile(
    RangeProfile(
        profile_identifier=DEFAULT_RANGE_PROFILE_IDENTIFIER,
        source=RANGE_SOURCE_DECLARED_ASSUMPTION,
        basis=_default_basis(),
        aggressor_class_count=40,
        caller_class_count=80,
        blind_class_count=110,
        unacted_class_count=130,
        folded_class_count=0,
        max_aggressive_actions_per_street=1,
    )
)


def _require_projection(projection: object) -> PositionProjection:
    if not isinstance(projection, PositionProjection):
        raise RangeContractError(
            f"范围假设只接受位置投影，收到 {type(projection).__name__}"
        )
    if projection.player_count < 2:
        raise RangeContractError(f"人数必须至少为 2，收到 {projection.player_count}")
    return projection


def _parse_token(token: object, player_count: int) -> tuple[str, int]:
    """解析 action@relative-seat token；形式或座位不合法即判超出建模范围。"""
    if not isinstance(token, str):
        raise OutOfProfileError(f"公开动作 token 必须是字符串，收到 {type(token).__name__}")
    action, separator, seat_text = token.partition("@")
    if (
        separator != "@"
        or "@" in seat_text
        or not seat_text.isascii()
        or not seat_text.isdigit()
        or seat_text != str(int(seat_text))
        or action not in _POSITION_TOKEN_VALUES
    ):
        raise OutOfProfileError(f"公开动作 token 形式超出建模范围：{token!r}")
    seat = int(seat_text)
    if not 0 <= seat < player_count:
        raise OutOfProfileError(f"公开动作 token 的相对座位越界：{token!r}")
    return action, seat


def assign_opponent_roles(projection: PositionProjection) -> tuple[tuple[int, str], ...]:
    """按公开行动线派生每个对手座位的角色；行动者自身不赋范围。

    弃牌跨街持久；过牌不提供收紧信息，归入未行动；仅投盲注且无自愿动作者为盲注角色。
    """
    _require_projection(projection)
    player_count = projection.player_count
    segments = projection.public_action_line

    folded: set[int] = set()
    for segment in segments:
        for token in segment.tokens:
            action, seat = _parse_token(token, player_count)
            if action == _FOLD_TOKEN:
                folded.add(seat)

    last_actions: dict[int, str] = {}
    blind_seats: set[int] = set()
    if segments:
        for token in segments[-1].tokens:
            action, seat = _parse_token(token, player_count)
            if action in _FORCED_TOKENS:
                blind_seats.add(seat)
            elif action in _AGGRESSIVE_TOKENS or action in (_CALL_TOKEN, _CHECK_TOKEN):
                last_actions[seat] = action

    roles: list[tuple[int, str]] = []
    for seat in range(player_count):
        if seat == projection.relative_actor:
            continue
        roles.append((seat, _role_for(seat, folded, blind_seats, last_actions)))
    return tuple(roles)


def _role_for(
    seat: int,
    folded: set[int],
    blind_seats: set[int],
    last_actions: dict[int, str],
) -> str:
    if seat in folded:
        return RANGE_ROLE_FOLDED
    action = last_actions.get(seat)
    if action in _AGGRESSIVE_TOKENS:
        return RANGE_ROLE_AGGRESSOR
    if action == _CALL_TOKEN:
        return RANGE_ROLE_CALLER
    if action == _CHECK_TOKEN:
        return RANGE_ROLE_UNACTED
    if seat in blind_seats:
        return RANGE_ROLE_BLIND
    return RANGE_ROLE_UNACTED


def _require_within_profile(projection: PositionProjection, profile: RangeProfile) -> None:
    """校验行动线未超出该 profile 的建模范围；超出即明确失败，不取最近档。"""
    for segment in projection.public_action_line:
        aggressive = 0
        for token in segment.tokens:
            action, _ = _parse_token(token, projection.player_count)
            if action in _AGGRESSIVE_TOKENS:
                aggressive += 1
        if aggressive > profile.max_aggressive_actions_per_street:
            raise OutOfProfileError(
                f"街 {segment.street!r} 出现 {aggressive} 次主动下注/加注，"
                f"超出 profile {profile.profile_identifier} 的建模上限"
                f"（{profile.max_aggressive_actions_per_street}）"
            )


def build_range_assumption(
    *,
    projection: PositionProjection,
    profile_identifier: str = DEFAULT_RANGE_PROFILE_IDENTIFIER,
) -> RangeAssumption:
    """由位置投影构造范围假设；未覆盖或不可匹配时明确失败。

    唯一输入是公开信息的位置投影，因此本函数在结构上无法读取对手暗牌、未来公共牌，
    也无法随公共牌收窄范围。
    """
    _require_projection(projection)
    profile = profile_for(profile_identifier)
    _require_within_profile(projection, profile)

    opponents = tuple(
        OpponentRange(
            relative_seat=seat,
            role=role,
            contests_pot=role != RANGE_ROLE_FOLDED,
            class_count=profile.class_count_for(role),
            weights=weights_for_class_count(profile.class_count_for(role)),
        )
        for seat, role in assign_opponent_roles(projection)
    )
    return RangeAssumption(
        schema_version=RANGE_ASSUMPTION_SCHEMA_VERSION,
        profile_identifier=profile.profile_identifier,
        source=profile.source,
        player_count=projection.player_count,
        street=projection.street,
        relative_actor=projection.relative_actor,
        opponents=opponents,
        limitations=RANGE_LIMITATIONS,
    )
