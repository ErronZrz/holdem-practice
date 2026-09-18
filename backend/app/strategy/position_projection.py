"""受控位置与公开行动线投影：把真实行动历史编码成相对座位口径的位置描述。

设计目的：
- 引擎快照不含行动历史，且含全部座位底牌；本模块把**公开**行动线编码成「动作 +
  相对座位」的位置描述，供后续信息集与范围工作消费；
- 相对座位以按钮为基准（按钮为 0），绝对座位与绝对按钮只在一次换算中出现，不进投影；
- 金额不进入投影，真实下注尺度与公共牌留给后续的尺度和筹码层；
- 位置或公开行动线不完整、不可编码时明确失败，不用最近位置、默认顺序或插值冒充。

边界：
- 本模块不重演引擎的下注状态机，只做结构性校验；因此不断言「首个行动者是否因全下被
  跳过」等依赖筹码与金额的事实；
- 从生产快照出发的入口先经信息边界投影，不新增第二条脱敏通道；
- 本模块不读取其他座位暗牌、未发出公共牌与运行中的随机源。
"""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from app.poker.state import GameState
from app.strategy.projection import project_for_actor

# 投影契约版本；字段集或口径变更时必须同步更新文档与测试。
POSITION_PROJECTION_VERSION = "position-line.v1"
# 相对座位的基准：按钮为 0，其余座位按顺时针相对按钮编号。
POSITION_BASIS = "relative-button"

# 投影只支持这些街；终局没有当前行动者，不构成可投影的位置。
POSITION_STREETS = ("preflop", "flop", "turn", "river")
# 公开动作线词表：真实动作名 -> 公开 token。只编码动作种类与相对座位，金额不进投影。
POSITION_ACTION_TOKENS = {
    "small_blind": "sb",
    "big_blind": "bb",
    "fold": "f",
    "check": "x",
    "call": "c",
    "bet": "b",
    "raise": "r",
}
# 强制盲注：翻前段必须以此二者开头。
POSITION_FORCED_ACTIONS = ("small_blind", "big_blind")
# 会重开行动的动作：同一街内某座位重复行动，必须由它们解释。
POSITION_REOPENING_ACTIONS = frozenset({"bet", "raise"})
# 投影字段集：新增或删减字段都属于契约变更，必须同步更新文档与测试。
POSITION_PROJECTION_FIELDS = (
    "player_count",
    "street",
    "relative_actor",
    "action_order",
    "players_to_act_before",
    "players_to_act_after",
    "public_action_line",
)


class PositionProjectionError(ValueError):
    """位置或公开行动线投影失败。"""


class PositionContractError(PositionProjectionError):
    """投影契约被违反（类型错误等结构性非法输入）。"""


class PositionEncodingError(PositionProjectionError):
    """位置或公开行动线不完整、不可编码。"""


class _FrozenModel(BaseModel):
    """本模块全部对外模型的公共基类：冻结、禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PublicAction(_FrozenModel):
    """输入侧的受控动作记录，镜像引擎历史条目的公开字段。

    ``amount`` 只用于判定「短码全下加注」这一不可编码情形，不进入任何投影字段。
    """

    street: str
    seat: int
    action: str
    amount: int = 0


class StreetActionLine(_FrozenModel):
    """一条街的公开动作线：街名与 ``action@relative-seat`` token 序列。"""

    street: str
    tokens: tuple[str, ...]


class PositionProjection(_FrozenModel):
    """位置与公开行动线投影：相对按钮口径，绝对座位与金额均不在其中。"""

    player_count: int
    street: str
    relative_actor: int
    action_order: tuple[int, ...]
    players_to_act_before: int
    players_to_act_after: int
    public_action_line: tuple[StreetActionLine, ...]


def _require_str(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise PositionContractError(f"{name} 必须是字符串，收到 {type(value).__name__}")


def _require_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PositionContractError(f"{name} 必须是整数，收到 {type(value).__name__}")


def relative_seat(player_count: int, button: int, seat: int) -> int:
    """把绝对座位换算成相对按钮座位；按钮自身恒为 0。"""
    return (seat - button) % player_count


def blind_relative_seats(player_count: int) -> tuple[int, int]:
    """返回相对按钮的（小盲, 大盲）座位：单挑时按钮即小盲。"""
    if player_count == 2:
        return 0, 1
    return 1, 2


def street_action_order(player_count: int, street: str) -> tuple[int, ...]:
    """返回该街的位置行动顺序（相对座位）：由人数与街唯一确定。

    翻前自大盲后一位起手（单挑自按钮起手，即按钮先行动）；翻后自按钮后一位起手。
    """
    if player_count < 2:
        raise PositionContractError(f"人数必须至少为 2，收到 {player_count}")
    if street not in POSITION_STREETS:
        raise PositionEncodingError(f"街 {street!r} 没有可投影的行动顺序")
    if street == "preflop":
        _, relative_big_blind = blind_relative_seats(player_count)
        first = (relative_big_blind + 1) % player_count if player_count > 2 else 0
    else:
        first = 1 % player_count
    return tuple((first + step) % player_count for step in range(player_count))


def build_public_actions(history: Sequence[Mapping[str, object]]) -> tuple[PublicAction, ...]:
    """把引擎风格的历史条目规范化为受控记录；结构性非法输入明确失败。"""
    records: list[PublicAction] = []
    for index, entry in enumerate(history):
        if not isinstance(entry, Mapping):
            raise PositionContractError(
                f"第 {index} 条历史不是映射类型：{type(entry).__name__}"
            )
        for key in ("street", "seat", "action"):
            if key not in entry:
                raise PositionContractError(f"第 {index} 条历史缺少必需键：{key}")
        street = entry["street"]
        seat = entry["seat"]
        action = entry["action"]
        amount = entry.get("amount", 0)
        _require_str("street", street)
        _require_int("seat", seat)
        _require_str("action", action)
        _require_int("amount", amount)
        records.append(PublicAction(street=street, seat=seat, action=action, amount=amount))
    return tuple(records)


def _normalize_actions(
    history: Sequence[Mapping[str, object]] | Sequence[PublicAction],
) -> tuple[PublicAction, ...]:
    """把受控记录或引擎风格条目统一收敛到同一条校验路径。"""
    entries: list[Mapping[str, object]] = []
    for index, entry in enumerate(history):
        if isinstance(entry, PublicAction):
            entries.append(
                {
                    "street": entry.street,
                    "seat": entry.seat,
                    "action": entry.action,
                    "amount": entry.amount,
                }
            )
        elif isinstance(entry, Mapping):
            entries.append(entry)
        else:
            raise PositionContractError(
                f"第 {index} 条历史不是映射类型：{type(entry).__name__}"
            )
    return build_public_actions(entries)


def _require_seat_in_range(player_count: int, seat: int) -> None:
    if not 0 <= seat < player_count:
        raise PositionEncodingError(
            f"动作记录的绝对座位 {seat} 越界（应为 0..{player_count - 1}）"
        )


def _encode_street(
    player_count: int,
    button: int,
    street: str,
    records: Sequence[PublicAction],
    folded: set[int],
    min_raise_baseline: int,
) -> tuple[list[str], set[int], int]:
    """编码一条街的 token；返回（token 序列, 更新后的弃牌集合, 该街大盲额）。

    只做结构性校验：不重演筹码与下注闭合，只校验街内顺序、重开解释与短码全下加注。
    """
    tokens: list[str] = []
    # 相对座位 -> 本街上一次自愿动作的记录下标，用于判定重复行动是否被重开解释。
    # 盲注是强制投入而非自愿动作，不登记：大盲在全员跟注后仍可再行动。
    last_seen: dict[int, int] = {}
    # 下注状态仅用于判定短码全下加注这一不可编码情形，金额不进入投影。
    current_bet = 0
    min_raise = min_raise_baseline
    big_blind_amount = min_raise_baseline
    start_index = 0

    if street == "preflop":
        if len(records) < len(POSITION_FORCED_ACTIONS):
            raise PositionEncodingError("翻前缺少盲注记录，无法编码位置")
        relative_small, relative_big = blind_relative_seats(player_count)
        expected = (
            (POSITION_FORCED_ACTIONS[0], relative_small),
            (POSITION_FORCED_ACTIONS[1], relative_big),
        )
        for offset, (action_name, expected_seat) in enumerate(expected):
            record = records[offset]
            _require_seat_in_range(player_count, record.seat)
            actual_seat = relative_seat(player_count, button, record.seat)
            if record.action != action_name or actual_seat != expected_seat:
                raise PositionEncodingError(
                    f"翻前盲注结构与规则不符：期望 {action_name}@{expected_seat}，"
                    f"收到 {record.action}@{actual_seat}"
                )
            tokens.append(f"{POSITION_ACTION_TOKENS[action_name]}@{expected_seat}")
        big_blind_amount = records[1].amount
        current_bet = max(records[0].amount, records[1].amount)
        min_raise = big_blind_amount
        start_index = len(POSITION_FORCED_ACTIONS)

    for index in range(start_index, len(records)):
        record = records[index]
        _require_seat_in_range(player_count, record.seat)
        token = POSITION_ACTION_TOKENS.get(record.action)
        if token is None:
            raise PositionEncodingError(f"动作 {record.action!r} 不在公开动作线词表内")
        if record.action in POSITION_FORCED_ACTIONS:
            raise PositionEncodingError(f"强制盲注只允许出现在翻前段开头：{record.action!r}")
        actor = relative_seat(player_count, button, record.seat)
        if actor in folded:
            raise PositionEncodingError(f"相对座位 {actor} 已弃牌，不能再行动")
        previous = last_seen.get(actor)
        if previous is not None and not _reopened_between(records, previous, index):
            raise PositionEncodingError(
                f"相对座位 {actor} 在同一街重复行动，但其间没有下注或加注重开行动"
            )
        if record.action == "fold":
            folded.add(actor)
        elif record.action == "bet":
            current_bet = record.amount
            min_raise = record.amount
        elif record.action == "raise":
            increment = record.amount - current_bet
            if increment < min_raise:
                raise PositionEncodingError(
                    "加注增量小于当时的最小加注额（短码全下加注）；token 行动线无法表达"
                    "「未重开行动」，故不可编码"
                )
            current_bet = record.amount
            min_raise = increment
        tokens.append(f"{token}@{actor}")
        last_seen[actor] = index

    return tokens, folded, big_blind_amount


def _reopened_between(records: Sequence[PublicAction], start: int, end: int) -> bool:
    """判断两次出现之间是否存在会重开行动的下注或加注。"""
    return any(
        records[index].action in POSITION_REOPENING_ACTIONS
        for index in range(start + 1, end)
    )


def _encode_action_line(
    player_count: int,
    button: int,
    actions: Sequence[PublicAction],
) -> tuple[StreetActionLine, ...]:
    """把受控记录按街分段编码；街序、盲注结构与不可编码情形在这里统一校验。"""
    if not actions:
        raise PositionEncodingError("公开行动线为空：缺少翻前盲注记录，无法编码位置")

    grouped: list[tuple[str, list[PublicAction]]] = []
    for record in actions:
        if record.street not in POSITION_STREETS:
            raise PositionEncodingError(f"动作记录含未知街：{record.street!r}")
        if not grouped or grouped[-1][0] != record.street:
            grouped.append((record.street, []))
        grouped[-1][1].append(record)

    street_names = [name for name, _ in grouped]
    if len(set(street_names)) != len(street_names):
        raise PositionEncodingError("公开行动线出现重复的街，说明记录乱序或拼接错误")
    if street_names[0] != POSITION_STREETS[0]:
        raise PositionEncodingError("公开行动线必须自翻前开始（引擎在翻前记录盲注）")
    indexes = [POSITION_STREETS.index(name) for name in street_names]
    if indexes != sorted(indexes):
        raise PositionEncodingError("公开行动线的街序回退，无法编码位置")

    segments: list[StreetActionLine] = []
    folded: set[int] = set()
    min_raise_baseline = 0
    for name, records in grouped:
        tokens, folded, big_blind_amount = _encode_street(
            player_count, button, name, records, folded, min_raise_baseline
        )
        if name == "preflop":
            min_raise_baseline = big_blind_amount
        segments.append(StreetActionLine(street=name, tokens=tuple(tokens)))
    return tuple(segments)


def build_position_projection(
    *,
    player_count: int,
    button: int,
    current_seat: int,
    street: str,
    history: Sequence[Mapping[str, object]] | Sequence[PublicAction],
) -> PositionProjection:
    """构造受控位置投影；不完整或不可编码时明确失败。

    绝对座位与绝对按钮只参与一次相对化换算，不进投影。最小加注额以本手大盲的实际
    记录金额为基准；大盲因短码未足额时该基准偏小，本层不重演筹码机，故如实标注为
    已知局限，不做近似修补。
    """
    _require_int("player_count", player_count)
    _require_int("button", button)
    _require_int("current_seat", current_seat)
    _require_str("street", street)
    if player_count < 2:
        raise PositionContractError(f"人数必须至少为 2，收到 {player_count}")
    if not 0 <= button < player_count:
        raise PositionContractError(f"按钮 {button} 越界（应为 0..{player_count - 1}）")
    if not 0 <= current_seat < player_count:
        raise PositionContractError(
            f"当前座位 {current_seat} 越界（应为 0..{player_count - 1}）"
        )
    if street not in POSITION_STREETS:
        raise PositionEncodingError(
            f"街 {street!r} 没有当前行动者，无法构造位置投影（仅支持 {POSITION_STREETS}）"
        )

    actions = _normalize_actions(history)
    segments = _encode_action_line(player_count, button, actions)
    last_street = segments[-1].street
    if POSITION_STREETS.index(street) < POSITION_STREETS.index(last_street):
        raise PositionEncodingError(
            f"当前街 {street!r} 早于最后一段动作所在的街 {last_street!r}，说明记录与快照不一致"
        )

    order = street_action_order(player_count, street)
    actor = relative_seat(player_count, button, current_seat)
    before = order.index(actor)
    return PositionProjection(
        player_count=player_count,
        street=street,
        relative_actor=actor,
        action_order=order,
        players_to_act_before=before,
        players_to_act_after=player_count - 1 - before,
        public_action_line=segments,
    )


def project_position_for_actor(
    state: GameState,
    history: Sequence[Mapping[str, object]] | Sequence[PublicAction],
) -> PositionProjection:
    """从生产快照构造投影：先经信息边界投影只保留行动者视角，再编码公开行动线。"""
    projected = project_for_actor(state)
    return build_position_projection(
        player_count=len(projected.players),
        button=projected.button,
        current_seat=projected.current_seat,
        street=projected.street.name.lower(),
        history=history,
    )
