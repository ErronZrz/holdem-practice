"""逐手核对辅助工具：打印一手牌的复盘结论，以及参考动作判据的内部状态。

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
from app.poker.actions import ActionType  # noqa: E402
from app.poker.state import Street  # noqa: E402
from app.strategy.heuristic import (  # noqa: E402
    _AIR_EQ,
    _DRAW_STRONG_OUTS,
    _RAISE_EQ,
    _VALUE_BET_EQ,
    draw_outs,
)

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


def _install_probe() -> list[dict]:
    """包裹复盘内部的保守收窄函数，记录每个决策点的中间判据状态。

    复盘按决策点顺序调用该函数，因此记录顺序与 decisions 一一对应。
    """
    records: list[dict] = []
    original = hand_review._conservative_distribution

    def probed(snapshot, legal, me, eq, baseline):
        result = original(snapshot, legal, me, eq, baseline)
        postflop = snapshot.street != Street.PREFLOP
        to_call = legal.call_amount
        pot = snapshot.pot
        pot_odds = to_call / (pot + to_call) if to_call > 0 else None
        margin = (
            hand_review._call_margin(me.hole_cards, snapshot.board, to_call, pot)
            if to_call > 0
            else None
        )
        outs = (
            draw_outs(list(me.hole_cards), tuple(snapshot.board))
            if 3 <= len(snapshot.board) < 5
            else None
        )
        records.append(
            {
                "snapshot": snapshot,
                "legal": legal,
                "me": me,
                "equity": eq,
                "raw_dist": baseline,
                "reference_dist": result,
                "pot_odds": pot_odds,
                "margin": margin,
                "made_hand": hand_review._is_made_hand(me.hole_cards, snapshot.board)
                if postflop
                else None,
                "dominated_pair": hand_review._dominated_pair(
                    me.hole_cards, snapshot.board
                )
                if postflop
                else None,
                "weak_kicker": hand_review._weak_kicker_top_pair(
                    me.hole_cards, snapshot.board
                )
                if postflop
                else None,
                "outs": outs,
                "playable": hand_review._has_playable_strength(
                    me.hole_cards, snapshot.board, to_call, pot
                )
                if postflop and to_call > 0
                else None,
                "small_bet": to_call * hand_review._SMALL_BET_DEN
                <= pot * hand_review._SMALL_BET_NUM
                if to_call > 0
                else None,
            }
        )
        return result

    hand_review._conservative_distribution = probed
    return records


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
    for p in history["players"]:
        flag = "  <- 真人" if p["is_human"] else ""
        print(
            f"  seat {p['seat']} {p['name']:>10}  底牌={p['hole_cards']}  "
            f"起始筹码={p['starting_stack']}{flag}"
        )
    print("动作线：")
    for a in history["actions"]:
        street = a.get("street", "-")
        print(f"  {street:>7}  seat={a['seat']}  {a['action']:>11}  amount={a['amount']}")


def _format_dist(dist) -> str:
    """把动作概率分布格式化为一行可读文本。"""
    if not dist:
        return "-"
    items = [f"{action.type.value}({action.amount}) {weight:.0%}" for action, weight in dist]
    return " / ".join(items)


def _narrowing_note(rec: dict) -> str:
    """说明保守收窄相对基线转移了哪类动作质量，未收窄时返回空串。"""
    raw = rec.get("raw_dist") or []
    ref = rec.get("reference_dist") or []
    if not raw or not ref:
        return ""
    raw_types = {action.type for action, _ in raw}
    ref_types = {action.type for action, _ in ref}
    notes = []
    if ActionType.CALL in raw_types and ActionType.CALL not in ref_types:
        notes.append("跟注质量 → 弃牌（赔率无余量或无可继续牌力）")
    if ActionType.BET in raw_types and ActionType.BET not in ref_types:
        notes.append("下注质量 → 过牌（弱踢脚顶对）")
    return "；".join(notes)


def _bot_rationale(rec: dict) -> str:
    """推断启发式基线给出该动作的依据，便于解释参考动作从何而来。"""
    dist = rec.get("raw_dist") or []
    if not dist:
        return "-"
    snapshot = rec.get("snapshot")
    if snapshot is not None and snapshot.street == Street.PREFLOP:
        # 翻牌前由 Chen 分档决定，与胜率阈值无关，不能套用翻牌后的胜率口径。
        return "翻牌前按 Chen 分档（不适用胜率口径）"
    raw = dist[0][0]
    if rec.get("pot_odds") is not None:
        if raw.type == ActionType.RAISE:
            return f"胜率≥{_RAISE_EQ:.2f}，加注"
        if raw.type == ActionType.CALL:
            return f"胜率≥{_AIR_EQ:.2f} 且不低于底池赔率，跟注"
        return f"胜率低于赔率或低于 {_AIR_EQ:.2f}，弃牌"
    if raw.type == ActionType.BET:
        if rec["equity"] >= _VALUE_BET_EQ:
            return f"价值下注（胜率≥{_VALUE_BET_EQ:.2f}）"
        if (rec.get("outs") or 0) >= _DRAW_STRONG_OUTS:
            return f"半诈唬（补牌≥{_DRAW_STRONG_OUTS}）"
        return "纯空气诈唬（按诈唬频率配比）"
    return "过牌"


def _print_decisions(review: dict, records: list[dict]) -> None:
    print(_DIVIDER)
    print(f"参考口径={review['reference_strategy']}  human_seat={review['human_seat']}")
    print(f"mistake_count={review['mistake_count']}")
    for i, d in enumerate(review["decisions"]):
        rec = records[i] if i < len(records) else {}
        snap = rec.get("snapshot")
        preflop = snap is not None and snap.street == Street.PREFLOP
        hole = (
            [str(c) for c in snap.players[review["human_seat"]].hole_cards] if snap else "-"
        )
        print("-" * 90)
        print(f"决策点 #{i}  {d['street']:>7}  board={d['board']}  底牌={hole}")
        print(
            f"  底池={d['pot']}  跟注额={d['to_call']}  pot_odds={d['pot_odds']}  "
            f"equity={d['equity']:.4f}  call_ev={d['call_ev']}  对手数={d['opponents']}"
        )
        print(
            f"  真人动作={d['action']['action']}({d['action']['amount']})  "
            f"启发式基线={_format_dist(rec.get('raw_dist'))}"
        )
        print(
            f"  参考分布={_format_dist(rec.get('reference_dist'))}  "
            f"参考动作={d['bot_action']['action']}({d['bot_action']['amount']})  "
            f"启发式依据：{_bot_rationale(rec)}"
        )
        note = _narrowing_note(rec)
        if note:
            print(f"  保守收窄：{note}")
        if preflop:
            # 翻牌前的保守收窄不介入，赔率余量与牌力判据均不参与参考分布。
            print("  判据：翻牌前不适用（保守收窄不介入，沿用启发式基线）")
        else:
            if rec.get("pot_odds") is not None:
                margin = rec["margin"]
                threshold = rec["pot_odds"] + margin
                print(
                    f"  判据·赔率余量：equity({d['equity']:.4f}) > "
                    f"pot_odds({rec['pot_odds']:.4f})"
                    f" + margin({margin:.4f}) = {threshold:.4f}  ->  {rec['equity'] > threshold}"
                )
            else:
                print("  判据·赔率余量：无人下注，不适用")
            print(
                f"  判据·牌力：_is_made_hand={rec.get('made_hand')}  "
                f"draw_outs={rec.get('outs')}  "
                f"_has_playable_strength={rec.get('playable')}  "
                f"小注例外={rec.get('small_bet')}  "
                f"被压制对子={rec.get('dominated_pair')}  "
                f"弱踢脚顶对={rec.get('weak_kicker')}"
            )
        codes = [m["code"] for m in d["mistakes"]]
        print(f"  命中 mistakes={codes or '无'}")
        for m in d["mistakes"]:
            print(f"    - {m['code']}（{m['severity']}）：{m['message']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="打印一手牌的复盘与参考判据内部状态")
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

    records = _install_probe()
    review = hand_review.build_review(history)
    _print_decisions(review, records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
