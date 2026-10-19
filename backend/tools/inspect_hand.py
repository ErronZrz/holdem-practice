"""逐手核对辅助工具：打印一手牌的复盘结论。

用法（在 backend 目录下）：
    uv run python tools/inspect_hand.py <hand_id>   # 核对指定手牌
    uv run python tools/inspect_hand.py             # 列出最近的手牌，便于取 ID

只读数据库，不修改任何状态；重放逻辑直接复用复盘模块，避免与其漂移。
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# 让脚本在任意工作目录下都能导入 app 包。
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.analysis import hand_review  # noqa: E402

_DIVIDER = "=" * 100


def _db_path() -> Path:
    """与后端一致的库路径解析：环境变量优先，否则落在 backend/data 下。"""
    env = os.environ.get("HOLDEM_DB_PATH")
    if env:
        return Path(env)
    return _BACKEND_DIR / "data" / "holdem.db"


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(_db_path())


def _list_recent(limit: int) -> None:
    """列出最近的手牌，便于从前端之外直接取 ID。"""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT id, hand_number, net, created_at, history_json "
            "FROM hands ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        con.close()
    if not rows:
        print("库中暂无手牌记录")
        return
    print(f"最近 {len(rows)} 手：")
    for hid, hand_number, net, created_at, history_json in rows:
        history = json.loads(history_json)
        human = next((p for p in history["players"] if p["is_human"]), None)
        hole = human["hole_cards"] if human else []
        print(
            f"  {hid}  第{hand_number}手  net={net:>6}  {created_at}  "
            f"底牌={hole}  公共牌={history['board']}"
        )


def _format_distribution(items: list[dict]) -> str:
    """把对外的参考分布格式化为一行可读文本。"""
    if not items:
        return "-"
    return " / ".join(
        f"{item['action']}({item['amount']}) {item['probability']:.0%}" for item in items
    )


def _print_hand_header(
    hand_id: str, session_id: str, hand_number: int, net: int, history: dict
) -> None:
    print(_DIVIDER)
    print(f"hand_id={hand_id}  session={session_id}  hand_number={hand_number}  net={net}")
    print(
        f"num_players={history['num_players']}  "
        f"blinds={history['small_blind']}/{history['big_blind']}  button={history['button']}"
    )
    print(f"公共牌={history['board']}  street={history['street']}  winners={history['winners']}")
    for player in history["players"]:
        flag = "  <- 真人" if player["is_human"] else ""
        print(
            f"  seat {player['seat']} {player['name']:>10}  底牌={player['hole_cards']}  "
            f"起始筹码={player['starting_stack']}{flag}"
        )
    print("动作线：")
    for action in history["actions"]:
        street = action.get("street", "-")
        print(
            f"  {street:>7}  seat={action['seat']}  {action['action']:>11}  "
            f"amount={action['amount']}"
        )


def _print_decisions(review: dict, history: dict) -> None:
    human = next(player for player in history["players"] if player["is_human"])
    print(_DIVIDER)
    print(
        f"参考口径={review['reference_strategy']}  "
        f"覆盖={review['reference_coverage']}  human_seat={review['human_seat']}"
    )
    print(f"适用域：{review['reference_scope']}")
    print(f"mistake_count={review['mistake_count']}")
    for index, decision in enumerate(review["decisions"]):
        print("-" * 90)
        print(
            f"决策点 #{index}  {decision['street']:>7}  board={decision['board']}  "
            f"底牌={human['hole_cards']}"
        )
        print(
            f"  底池={decision['pot']}  完整欠注={decision['to_call']}  "
            f"实际支付={decision['actual_call_amount']}  equity={decision['equity']:.4f}  "
            f"对手数={decision['opponents']}"
        )
        if decision["pot_odds"] is None and decision["call_ev"] is None:
            print("  无人下注：不填赔率与跟注期望")
        else:
            print(f"  pot_odds={decision['pot_odds']}  call_ev={decision['call_ev']}")
        if decision["is_short_all_in_call"]:
            print("  短码全下：赔率与跟注期望按实际支付和池层计算")
        print(
            f"  真人动作={decision['action']['action']}({decision['action']['amount']})  "
            f"参考动作={decision['bot_action']['action']}({decision['bot_action']['amount']})"
        )
        print(f"  参考分布={_format_distribution(decision['bot_distribution'])}")
        codes = [item["code"] for item in decision["mistakes"]]
        print(f"  命中 mistakes={codes or '无'}")
        for item in decision["mistakes"]:
            print(f"    - {item['code']}（{item['severity']}）：{item['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="打印一手牌的复盘结论")
    parser.add_argument("hand_id", nargs="?", help="手牌 ID；省略时列出最近的手牌")
    parser.add_argument("--recent", type=int, default=20, help="无 ID 时列出的手牌条数")
    args = parser.parse_args()

    if not args.hand_id:
        _list_recent(args.recent)
        return 0

    con = _connect()
    try:
        row = con.execute(
            "SELECT id, session_id, hand_number, net, history_json FROM hands WHERE id = ?",
            (args.hand_id,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        print(f"未找到手牌 {args.hand_id}")
        return 1

    hand_id, session_id, hand_number, net, history_json = row
    history = json.loads(history_json)
    _print_hand_header(hand_id, session_id, hand_number, net, history)
    _print_decisions(hand_review.build_review(history), history)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
