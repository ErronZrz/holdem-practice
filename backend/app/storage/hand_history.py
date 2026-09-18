"""把一手结束后的引擎状态序列化为 Hand History（JSON，source of truth）。

该模块只读取引擎的公开属性（players / board / history / winners / last_net / street /
showdown_hands / pot_results），不修改引擎，属于持久化层的序列化职责。

对外输出另有白名单投影：历史 JSON 是服务端事实，客户端只能看到投影后的字段，
未登记字段（含将来可能出现的敏感键）一律被丢弃。
"""

from app.poker.engine import PokerEngine
from app.poker.evaluator import evaluate
from app.poker.state import Street

# 历史 JSON 的结构版本；新增/变更字段时必须同时更新投影白名单与配套测试。
HAND_HISTORY_SCHEMA_VERSION = "hand-history.v1"
# 旧数据缺失版本或策略标识时的取值，不得补成当前版本。
UNKNOWN_VERSION = "unknown"

# 对外投影白名单：只有这些键允许出现在 API 响应里。
_PROJECTED_PAYLOAD_KEYS = (
    "hand_number",
    "num_players",
    "small_blind",
    "big_blind",
    "button",
    "board",
    "players",
    "actions",
    "street",
    "showdown",
    "winners",
    "net",
    "showdown_hands",
    "pot_results",
)


def build_hand_history(
    engine: PokerEngine,
    hand_number: int,
    human_seat: int,
    *,
    bot_strategy: str = UNKNOWN_VERSION,
) -> dict:
    """构造一手牌的完整历史字典，键与值均为 JSON 可序列化类型。"""
    players = []
    for p in engine.players:
        start_stack = p.stack - engine.last_net.get(p.seat, 0)
        players.append(
            {
                "seat": p.seat,
                "name": p.name,
                "is_human": p.seat == human_seat,
                "hole_cards": [str(c) for c in p.hole_cards],
                "starting_stack": start_stack,
            }
        )
    result = {
        "schema_version": HAND_HISTORY_SCHEMA_VERSION,
        "bot_strategy": bot_strategy,
        "hand_number": hand_number,
        "num_players": engine.num_players,
        "small_blind": engine.small_blind,
        "big_blind": engine.big_blind,
        "button": engine.button,
        "board": [str(c) for c in engine.board],
        "players": players,
        "actions": list(engine.history),
        "street": engine.street.name.lower(),
        "showdown": engine.street == Street.SHOWDOWN,
        "winners": list(engine.winners),
        "net": {str(seat): net for seat, net in engine.last_net.items()},
    }
    if engine.street == Street.SHOWDOWN:
        result["showdown_hands"] = {
            str(seat): {
                "cards": [str(c) for c in cards],
                "category": evaluate(cards).category.name,
            }
            for seat, cards in engine.showdown_hands.items()
        }
        result["pot_results"] = [
            {
                "amount": pr["amount"],
                "winners": list(pr["winners"]),
                "shares": {str(k): v for k, v in pr["shares"].items()},
            }
            for pr in engine.pot_results
        ]
    return result


def project_hand_history(history: dict) -> dict:
    """按白名单裁剪历史 JSON，并把版本与策略标识规范化为字符串。

    旧数据缺少版本字段时按 ``unknown`` 读取，不假设其等于当前版本；白名单外的键一律丢弃。
    """
    version = history.get("schema_version")
    strategy = history.get("bot_strategy")
    projected = {
        "schema_version": version if _is_non_empty_str(version) else UNKNOWN_VERSION,
        "bot_strategy": strategy if _is_non_empty_str(strategy) else UNKNOWN_VERSION,
    }
    for key in _PROJECTED_PAYLOAD_KEYS:
        if key in history:
            projected[key] = history[key]
    return projected


def _is_non_empty_str(value: object) -> bool:
    """判断是否为可用的非空字符串（用于版本与策略标识的规范化）。"""
    return isinstance(value, str) and bool(value.strip())
