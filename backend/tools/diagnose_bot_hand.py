"""按手牌 ID 只读重放 Bot 决策，拆开混合策略的评分与三种手模式分布。

用法（在 backend 目录下）：
    uv run python tools/diagnose_bot_hand.py <hand_id> [--seat 4] [--street turn]
    uv run python tools/diagnose_bot_hand.py                 # 列出最近的手牌

数据库以只读方式打开。默认使用该手历史里记录的混合策略身份；
座位号与牌桌上的「玩家N」一致。不写库，也不推进在线对局。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from itertools import combinations
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.poker.actions import Action, ActionType  # noqa: E402
from app.poker.cards import Card, Rank, Suit, card_from_str  # noqa: E402
from app.poker.engine import PokerEngine  # noqa: E402
from app.poker.evaluator import evaluate_fast  # noqa: E402
from app.poker.hand import HandCategory  # noqa: E402
from app.strategy.mixed_context import (  # noqa: E402
    MixedSummaryTracker,
    mixed_state,
    require_mixed_input,
)
from app.strategy.mixed_features import features_for  # noqa: E402
from app.strategy.mixed_policy import (  # noqa: E402
    _CONTENDER_PENALTY,
    _DANGEROUS_POT_MULTIPLE,
    _MODE_SCORE_OFFSET,
    _NUT_BASE,
    _POSTFLOP_PRICE_WEIGHT,
    _STRONG_PREFLOP_BASE,
    _STRONG_VALUE_BONUS,
    _THIN_VALUE_BASE,
    _TRAP_RELEASE,
    _VALUE_GATE_TOLERANCE,
    _VALUE_THRESHOLDS,
    STYLE_PARAMETERS,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    _active_candidates,
    _active_gate,
    _checked_defense_bonus,
    _checked_value_floor,
    _close_facing_pair_raise,
    _delayed_probe_quality,
    _facing_draw_support,
    _facing_pair_raise_applies,
    _full_ring_call_penalty,
    _large_commit_penalty,
    _non_value_quality,
    _protection_applies,
    _retains_short_stack_min_raise,
    _score,
    _size_preferences,
    _story_quality,
    _strong_preflop_continuation,
    _strong_value_hand,
    _trap_budget,
    _with_effective_base,
    build_distribution,
)
from app.strategy.mixed_strategy import (  # noqa: E402
    MIXED_STRATEGY_IDENTIFIER_V19,
    MIXED_STRATEGY_RULES,
    MIXED_STYLE_ORDER,
    rules_for_identifier,
    seat_style_map,
)
from app.strategy.projection import project_for_actor  # noqa: E402

# 与分布函数里的跟注门槛底数一致：翻前 310，翻后 350。
_PREFLOP_CALL_BASE = 310
_POSTFLOP_CALL_BASE = 350
# 手模式在 [0,100) 上的分区：标准 80%，保守与施压各 10%。
_MODE_WEIGHT = {
    HandMode.NORMAL: 80,
    HandMode.CAUTIOUS: 10,
    HandMode.PRESSED: 10,
}
_STREET_ALIASES = {
    "preflop": "preflop",
    "翻牌前": "preflop",
    "flop": "flop",
    "翻牌": "flop",
    "turn": "turn",
    "转牌": "turn",
    "river": "river",
    "河牌": "river",
}
_STREET_ZH = {
    "preflop": "翻牌前",
    "flop": "翻牌",
    "turn": "转牌",
    "river": "河牌",
}
_CATEGORY_ZH = {
    HandCategory.HIGH_CARD: "高牌",
    HandCategory.ONE_PAIR: "一对",
    HandCategory.TWO_PAIR: "两对",
    HandCategory.THREE_OF_A_KIND: "三条",
    HandCategory.STRAIGHT: "顺子",
    HandCategory.FLUSH: "同花",
    HandCategory.FULL_HOUSE: "葫芦",
    HandCategory.FOUR_OF_A_KIND: "四条",
    HandCategory.STRAIGHT_FLUSH: "同花顺",
}
_MODES = (HandMode.CAUTIOUS, HandMode.NORMAL, HandMode.PRESSED)


def db_path() -> Path:
    """与后端一致：环境变量优先，否则使用 backend/data 下的库。"""
    import os

    env = os.environ.get("HOLDEM_DB_PATH")
    if env:
        return Path(env)
    return _BACKEND / "data" / "holdem.db"


def connect_readonly() -> sqlite3.Connection:
    """只读打开牌局库，诊断过程不能写入。"""
    return sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)


def parse_streets(raw: list[str]) -> set[str]:
    """把命令行上的街名收成引擎使用的四个标识。"""
    chosen: set[str] = set()
    for item in raw:
        street = _STREET_ALIASES.get(item.strip())
        if street is None:
            known = "、".join(_STREET_ALIASES)
            raise ValueError(f"无法识别的街：{item}。可用 {known}")
        chosen.add(street)
    return chosen


def _tier(base: int, street: str) -> str:
    """把基础分对上规则里实际使用的档位，便于和门槛对照。"""
    if street == "preflop":
        if base >= _STRONG_PREFLOP_BASE:
            return f"翻前强牌（≥{_STRONG_PREFLOP_BASE}）"
        if base >= 500:
            return "翻前中等（≥500，满员桌弱牌线之上）"
        return "翻前偏弱（<500，满员桌可被深跟注惩罚）"
    if base >= _NUT_BASE:
        return f"同花及以上（≥{_NUT_BASE}，无人下注可走坚果尺度）"
    if base >= 860:
        return "顺子档（860，强成牌但未到坚果尺度）"
    if base >= _THIN_VALUE_BASE:
        return f"两对高档及以上（≥{_THIN_VALUE_BASE}，薄价值线之上）"
    if base >= 600:
        return "成牌下沿及以上（≥600，可被无人下注托底）"
    return "成牌下沿之下（<600，不托底价值）"


def _nuts(holes: list[Card], board: list[Card]) -> dict:
    """枚举其余底牌，判断当前公共牌上这手是不是坚果。只供阅读，不进入策略。"""
    if len(board) < 3:
        return {"checked": False}
    hero = evaluate_fast([*holes, *board])
    used = set(holes) | set(board)
    deck = [Card(rank, suit) for suit in Suit for rank in Rank if Card(rank, suit) not in used]
    beaten_by = 0
    tied = 0
    best_other = None
    for pair in combinations(deck, 2):
        rank = evaluate_fast([*pair, *board])
        if rank > hero:
            beaten_by += 1
            if best_other is None or rank > best_other:
                best_other = rank
        elif rank == hero:
            tied += 1
    return {
        "checked": True,
        "category": _CATEGORY_ZH[hero.category],
        "is_nuts": beaten_by == 0,
        "chop_possible": tied > 0,
        "beaten_by_combos": beaten_by,
        "tie_combos": tied,
        "best_other": (
            None
            if best_other is None
            else f"{_CATEGORY_ZH[best_other.category]}:{best_other.tiebreak}"
        ),
    }


def _resolve_rules(history: dict, identity: str | None) -> tuple[str, MixedPolicyRules]:
    """优先使用显式身份，否则用这手历史里记下的混合策略。"""
    recorded = history.get("bot_strategy")
    chosen = identity or (recorded if isinstance(recorded, str) else None)
    if not chosen or chosen not in MIXED_STRATEGY_RULES:
        known = "、".join(MIXED_STRATEGY_RULES)
        if identity:
            raise ValueError(
                f"指定的策略 {identity!r} 没有可拆的混合规则。"
                f"这手记录的是 {recorded!r}。可用：{known}"
            )
        raise ValueError(
            f"这手记录的策略是 {recorded!r}，没有可拆的混合规则。"
            f"可用 --identity 指定其一：{known}"
        )
    return chosen, rules_for_identifier(chosen)


def _explain(
    features,
    legal,
    style: str,
    mode: HandMode,
    rules: MixedPolicyRules,
    trap_roll: int | None = None,
    protect_roll: int | None = None,
) -> dict:
    """按同一次分布计算拆开评分、门槛、尺度和过滤后的候选。

    未传入设伏或过牌保护隐变量时，这两条通道保持关闭，与没有座位键的分布观测同一口径。
    过牌后的跟注和延迟探测只看规则开关，不另抽隐变量。
    展示用的基础分与这次分布使用的有效基础分相同。
    """
    features = _with_effective_base(features, rules)
    style_value = MixedStyle(style)
    parameters = STYLE_PARAMETERS[style_value]
    score = _score(features, parameters, mode, rules)
    depth = -40 if features.spr_at_most(1) else (25 if features.spr_at_least(6) else 0)
    aggression_penalty = 25 * features.recent_aggression
    is_preflop = features.street.name.lower() == "preflop"
    per_opponent = rules.preflop_contender_penalty if is_preflop else _CONTENDER_PENALTY
    contender_penalty = per_opponent * (features.contenders - 1)
    if rules.shared_board_chop_caliber and features.shared_board_locked:
        contender_penalty = 0
    if rules.contender_penalty_cap > 0:
        contender_penalty = min(contender_penalty, rules.contender_penalty_cap)
    price_weight = rules.preflop_price_weight if is_preflop else _POSTFLOP_PRICE_WEIGHT
    call_price = features.price
    if rules.shared_board_chop_caliber and features.shared_board_locked:
        call_price = features.price // (features.contenders + 1)
    call_base = _PREFLOP_CALL_BASE if is_preflop else _POSTFLOP_CALL_BASE
    call_threshold = call_base + (price_weight * call_price) // 1000 + aggression_penalty + depth
    value_threshold = _VALUE_THRESHOLDS[features.street] + aggression_penalty + depth
    bonus = (
        int(getattr(rules.preflop_call_bonus, style))
        if is_preflop
        else int(getattr(rules.postflop_call_bonus, style))
    )
    commit_penalty = _large_commit_penalty(features, rules)
    ring_penalty = _full_ring_call_penalty(features, rules)
    continuation = _strong_preflop_continuation(features, rules)
    passive = score + bonus + continuation - commit_penalty - ring_penalty
    fold_weight = max(0, call_threshold - passive + 160) * parameters.fold_percent
    call_weight = max(0, passive - call_threshold + 160) * parameters.call_percent
    gate = _active_gate(features, style_value, rules)
    threshold_quality = max(0, score - value_threshold + _VALUE_GATE_TOLERANCE + gate)
    floor = _checked_value_floor(features, rules)
    strong = _strong_value_hand(features, rules)
    value_quality = max(threshold_quality, floor) + (_STRONG_VALUE_BONUS if strong else 0)
    bluff_raw = _non_value_quality(features, rules)
    bluff_quality = max(0, bluff_raw + gate) if bluff_raw > 0 else 0
    aggression_zeroed = bool(commit_penalty or ring_penalty)
    if aggression_zeroed:
        value_quality = 0
        bluff_quality = 0
    draw_support = 0
    draw_coverage = 0
    draw_survival = 1000
    penalties_clear = not aggression_zeroed
    if (
        penalties_clear
        and rules.effective_draw_support
        and features.base < 400
        and value_quality == 0
    ):
        supported = _facing_draw_support(features, rules)
        if supported is not None:
            draw_support, draw_coverage = supported
            passive += draw_support
            opening = max(0, passive - call_threshold + 160)
            draw_survival = min(draw_coverage, opening * 1000 // 160)
            bluff_quality = bluff_quality * draw_survival // 1000
            fold_weight = max(0, call_threshold - passive + 160) * parameters.fold_percent
            call_weight = max(0, passive - call_threshold + 160) * parameters.call_percent
    story_quality = _story_quality(features, rules) if penalties_clear else 0
    bluff_quality += story_quality
    if _protection_applies(features, rules, protect_roll) and (
        legal.can_check or (features.actor_checks > 0 and features.actual_call > 0)
    ):
        value_quality = 0
        bluff_quality = 0
    trap_budget = _trap_budget(features, rules)
    trap_hit = trap_roll is not None and 0 <= trap_roll < trap_budget
    if trap_hit and legal.can_check:
        value_quality = 0
        bluff_quality = 0
    if trap_hit and features.actor_checks > 0 and features.actual_call > 0:
        passive += _TRAP_RELEASE
        fold_weight = max(0, call_threshold - passive + 160) * parameters.fold_percent
        call_weight = max(0, passive - call_threshold + 160) * parameters.call_percent
    if penalties_clear:
        bluff_quality += _delayed_probe_quality(features, rules)
        defense = _checked_defense_bonus(features, rules)
        if defense:
            passive += defense
            fold_weight = max(0, call_threshold - passive + 160) * parameters.fold_percent
            call_weight = max(0, passive - call_threshold + 160) * parameters.call_percent
    pair_raise_applies = _facing_pair_raise_applies(features, rules, style_value)
    value_quality, bluff_quality = _close_facing_pair_raise(
        features, rules, style_value, value_quality, bluff_quality
    )
    short_stack_min_raise = _retains_short_stack_min_raise(
        features, legal, value_quality, rules
    )
    preferences = _size_preferences(features, parameters, rules)
    active = _active_candidates(
        features, legal, score, value_quality, bluff_quality, preferences, rules
    )
    distribution = build_distribution(
        features,
        legal,
        style_value,
        mode,
        rules,
        trap_roll=trap_roll,
        protect_roll=protect_roll,
    )
    rows = [
        {
            "action": item.action.value,
            "amount": item.amount,
            "units": item.units,
            "pct": round(item.units / 10000, 2),
        }
        for item in distribution.candidates
        if item.units > 0
    ]
    return {
        "mode": mode.value,
        "looseness": parameters.looseness,
        "mode_offset": _MODE_SCORE_OFFSET[mode],
        "contender_penalty": contender_penalty,
        "score": score,
        "depth_adjust": depth,
        "aggression_penalty": aggression_penalty,
        "call_price": call_price,
        "call_threshold": call_threshold,
        "passive_bonus": bonus,
        "strong_preflop_continuation": continuation,
        "commit_penalty": commit_penalty,
        "full_ring_penalty": ring_penalty,
        "passive_score": passive,
        "fold_weight": fold_weight,
        "call_weight": call_weight,
        "value_threshold": value_threshold,
        "active_gate": gate,
        "threshold_quality": threshold_quality,
        "checked_value_floor": floor,
        "strong_value_hand": strong,
        "value_quality_after_guards": value_quality,
        "bluff_raw": bluff_raw,
        "bluff_quality_after_guards": bluff_quality,
        "draw_support": draw_support,
        "draw_coverage": draw_coverage,
        "draw_survival": draw_survival,
        "story_quality": story_quality,
        "pair_raise_applies": pair_raise_applies,
        "short_stack_min_raise": short_stack_min_raise,
        "top_pair_board_pair_base": features.top_pair_board_pair_base,
        "trap_budget": trap_budget,
        "trap_hit": trap_hit,
        "aggression_zeroed_by_penalty": aggression_zeroed,
        "size_preferences_small_medium_large_allin": list(preferences),
        "dangerous_pot_multiple": _DANGEROUS_POT_MULTIPLE,
        "active_after_dangerous_filter": [
            {
                "action": kind.value,
                "amount": amount,
                "quality": quality,
                "preference": preference,
            }
            for (kind, amount, quality), preference in active
        ],
        "distribution": rows,
    }


def _marginal_rows(modes: list[dict]) -> list[dict]:
    """按 80/10/10 把三种手模式的单位合成边缘分布，避免先四舍五入再加权。"""
    marginal: dict[tuple[str, int], int] = {}
    for mode_row, mode in zip(modes, _MODES, strict=True):
        weight = _MODE_WEIGHT[mode]
        for item in mode_row["distribution"]:
            key = (item["action"], item["amount"])
            marginal[key] = marginal.get(key, 0) + item["units"] * weight
    return [
        {
            "action": action,
            "amount": amount_key,
            "pct": round(units / 1_000_000, 2),
        }
        for (action, amount_key), units in sorted(marginal.items(), key=lambda item: -item[1])
    ]


def _match_amount(action: str, recorded_amount: int, street_bet: int) -> int:
    """历史金额是本次投入；分布里的加注额是本街总额。"""
    if action == "raise":
        return street_bet + recorded_amount
    if action == "bet":
        return recorded_amount
    return 0


def _wanted(seat: int, street: str, seats: set[int] | None, streets: set[str] | None) -> bool:
    if seats is not None and seat not in seats:
        return False
    return streets is None or street in streets


def diagnose_history(
    history: dict,
    *,
    hand_id: str = "",
    seats: set[int] | None = None,
    streets: set[str] | None = None,
    identity: str | None = None,
) -> dict:
    """重放一手历史，在指定 Bot 座位和街上拆开决策。座位省略时覆盖全部 Bot。"""
    try:
        rules_name, rules = _resolve_rules(history, identity)
    except ValueError as exc:
        return {"hand_id": hand_id, "error": str(exc)}

    players = history["players"]
    human = next((p for p in players if p.get("is_human")), None)
    if human is None:
        return {"hand_id": hand_id, "error": "历史中没有标记真人座位"}
    bot_seats = tuple(sorted(p["seat"] for p in players if not p.get("is_human")))
    styles = {seat: style.value for seat, style in seat_style_map(bot_seats).items()}
    hole_cards = {p["seat"]: [card_from_str(c) for c in p["hole_cards"]] for p in players}
    starting = {p["seat"]: p["starting_stack"] for p in players}
    board = [card_from_str(c) for c in history["board"]]
    engine = PokerEngine(
        history["num_players"],
        history["small_blind"],
        history["big_blind"],
        max(starting.values()),
    )
    for seat, stack in starting.items():
        engine.players[seat].stack = stack
    engine.start_hand_with(history["button"], hole_cards, board)
    tracker = MixedSummaryTracker()
    tracker.begin_hand(
        hand_number=history["hand_number"],
        num_players=history["num_players"],
        small_blind=history["small_blind"],
        big_blind=history["big_blind"],
        bot_seats=bot_seats,
        history=engine.history,
    )
    decisions: list[dict] = []
    action_line: list[dict] = []
    for record in history["actions"]:
        token = record["action"]
        if token in ("small_blind", "big_blind"):
            action_line.append(record)
            continue
        seat = int(record["seat"])
        if engine.hand_over or engine.current_seat != seat:
            decisions.append(
                {
                    "error": (
                        "牌局已结束，历史仍有动作"
                        if engine.hand_over
                        else f"重放座位不一致：历史 {seat}，引擎 {engine.current_seat}"
                    ),
                    "record": record,
                }
            )
            break
        street = engine.street.name.lower()
        actor = engine.players[seat]
        street_bet = actor.street_bet
        if seat in styles and _wanted(seat, street, seats, streets):
            decisions.append(
                _capture(
                    engine,
                    tracker,
                    actor,
                    styles[seat],
                    token,
                    int(record["amount"]),
                    street,
                    street_bet,
                    rules,
                )
            )
        played = Action(ActionType(token), int(record["amount"]))
        if played.type == ActionType.RAISE:
            played = Action(ActionType.RAISE, street_bet + played.amount)
        engine.apply_action(played)
        action_line.append(
            {
                "street": street,
                "seat": seat,
                "name": f"玩家{seat}",
                "action": token,
                "amount": int(record["amount"]),
            }
        )
        if engine.hand_over:
            break
        tracker.consume_after_action(engine.history)
    return {
        "hand_id": hand_id,
        "rules_identity": rules_name,
        "recorded_bot_strategy": history.get("bot_strategy"),
        "hand_number": history["hand_number"],
        "num_players": history["num_players"],
        "blinds": [history["small_blind"], history["big_blind"]],
        "button": history["button"],
        "human_seat": human["seat"],
        "bot_seats": list(bot_seats),
        "styles": styles,
        "style_order": [item.value for item in MIXED_STYLE_ORDER],
        "players": [
            {
                "seat": p["seat"],
                "name": p["name"],
                "is_human": bool(p.get("is_human")),
                "hole_cards": p["hole_cards"],
                "starting_stack": p["starting_stack"],
                "style": styles.get(p["seat"]),
            }
            for p in players
        ],
        "final_board": history["board"],
        "winners": history.get("winners"),
        "action_line": action_line,
        "decisions": decisions,
        "skipped_human_seats": sorted(seats & {human["seat"]}) if seats else [],
    }


def _capture(
    engine,
    tracker,
    actor,
    style: str,
    token: str,
    amount: int,
    street: str,
    street_bet: int,
    rules: MixedPolicyRules,
) -> dict:
    """在动作提交前记下这一决策的特征与三档分布。"""
    legal = engine.legal_actions()
    state = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    features = _with_effective_base(features_for(require_mixed_input(state), legal), rules)
    holes = list(actor.hole_cards)
    board_now = list(engine.board)
    category = _CATEGORY_ZH[evaluate_fast([*holes, *board_now]).category] if board_now else None
    modes = [_explain(features, legal, style, mode, rules) for mode in _MODES]
    actual_amount = _match_amount(token, amount, street_bet)
    marginal_rows = _marginal_rows(modes)
    hit = next(
        (
            item
            for item in marginal_rows
            if item["action"] == token and item["amount"] == actual_amount
        ),
        None,
    )
    trap_budget = _trap_budget(features, rules)
    trap_hit_marginal: list[dict] = []
    if trap_budget > 0:
        hit_modes = [
            _explain(features, legal, style, mode, rules, trap_roll=0) for mode in _MODES
        ]
        trap_hit_marginal = _marginal_rows(hit_modes)
    return {
        "street": street,
        "street_zh": _STREET_ZH[street],
        "seat": actor.seat,
        "name": actor.name,
        "style": style,
        "hole_cards": [str(card) for card in holes],
        "board": [str(card) for card in board_now],
        "category": category,
        "nuts": _nuts(holes, board_now),
        "actual": {
            "action": token,
            "recorded_amount": amount,
            "distribution_amount": actual_amount,
        },
        "pot": engine.pot,
        "stack": actor.stack,
        "features": {
            "base": features.base,
            "draw": features.draw,
            "position": features.position,
            "texture": features.texture,
            "contenders": features.contenders,
            "live_opponents": features.live_opponents,
            "recent_aggression": features.recent_aggression,
            "limpers": features.limpers,
            "price": features.price,
            "actual_call": features.actual_call,
            "effective_stack": features.effective_stack,
            "preflop_unraised": features.preflop_unraised,
            "shared_board_locked": features.shared_board_locked,
            "seat_count": features.seat_count,
            "actor_checks": features.actor_checks,
            "prior_street_aggressor": features.prior_street_aggressor,
            "prior_street_aggression": features.prior_street_aggression,
            "capped_board_two_pair": features.capped_board_two_pair,
            "top_pair_board_pair_base": features.top_pair_board_pair_base,
            "trap_budget": trap_budget,
            "made_tier": _tier(features.base, street),
        },
        "modes": modes,
        "marginal_80_10_10": marginal_rows,
        "trap_hit_marginal_80_10_10": trap_hit_marginal,
        "actual_marginal_pct": None if hit is None else hit["pct"],
    }


def _load(hand_id: str) -> dict | None:
    connection = connect_readonly()
    try:
        row = connection.execute(
            "SELECT history_json FROM hands WHERE id = ?",
            (hand_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return json.loads(row[0])


def _list_recent(limit: int) -> None:
    connection = connect_readonly()
    try:
        rows = connection.execute(
            "SELECT id, hand_number, created_at, history_json FROM hands "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        print("库中暂无手牌记录")
        return
    print(f"最近 {len(rows)} 手：")
    for hand_id, hand_number, created_at, history_json in rows:
        history = json.loads(history_json)
        strategy = history.get("bot_strategy", "-")
        print(f"  {hand_id}  第{hand_number}手  {created_at}  策略={strategy}")


def _print_hand(hand: dict) -> None:
    if "error" in hand and "decisions" not in hand:
        print(hand.get("hand_id", ""), hand["error"])
        return
    print("=" * 88)
    print(
        f"{hand['hand_id']}  策略={hand['rules_identity']}  "
        f"记录={hand['recorded_bot_strategy']}  "
        f"{hand['num_players']}人  盲注={hand['blinds'][0]}/{hand['blinds'][1]}  "
        f"庄家=玩家{hand['button']}"
    )
    if hand["rules_identity"] != hand["recorded_bot_strategy"]:
        print("  本次按命令行指定的身份重放，与历史记录不同。")
    for player in hand["players"]:
        role = "真人" if player["is_human"] else player["style"]
        print(
            f"  玩家{player['seat']}  {player['hole_cards']}  "
            f"起始={player['starting_stack']}  {role}"
        )
    if hand["skipped_human_seats"]:
        skipped = "、".join(f"玩家{seat}" for seat in hand["skipped_human_seats"])
        print(f"  {skipped} 是真人，没有 Bot 风格，已跳过。")
    print(
        "  动作线:",
        " | ".join(
            f"{item['street'][:1]}{item['seat']}:{item['action']}{item['amount']}"
            for item in hand["action_line"]
        ),
    )
    shown = 0
    for decision in hand["decisions"]:
        if "error" in decision:
            print("  重放中断:", decision["error"])
            continue
        shown += 1
        _print_decision(decision)
    if shown == 0:
        print("  没有符合座位与街筛选的 Bot 决策。")


def _print_decision(decision: dict) -> None:
    actual = decision["actual"]
    features = decision["features"]
    nuts = decision["nuts"]
    nuts_text = "-" if not nuts.get("checked") else ("坚果" if nuts["is_nuts"] else "非坚果")
    print(
        f"  {decision['street_zh']} 玩家{decision['seat']} {decision['style']}  "
        f"{decision['hole_cards']}  公共牌={decision['board'] or '-'}  "
        f"{decision['category'] or '-'}  {nuts_text}"
    )
    print(
        f"    实际 {actual['action']} {actual['distribution_amount']}  "
        f"边缘概率={decision['actual_marginal_pct']}%  "
        f"底池={decision['pot']}  后手={decision['stack']}"
    )
    print(
        f"    基础分={features['base']}  听牌分={features['draw']}  "
        f"位置={features['position']}  牌面风险={features['texture']}  "
        f"对手={features['contenders']}  价格={features['price']}  "
        f"本街过牌={features['actor_checks']}  "
        f"上街进攻={'是' if features['prior_street_aggressor'] else '否'}"
        f"/{features['prior_street_aggression']}  "
        f"设伏预算={features['trap_budget']}  "
        f"盖住口袋对={'是' if features['capped_board_two_pair'] else '否'}  "
        f"顶对公对分={features['top_pair_board_pair_base']}  "
        f"档位={features['made_tier']}"
    )
    for mode in decision["modes"]:
        dist = "  ".join(
            f"{item['action']}{item['amount']}:{item['pct']}%" for item in mode["distribution"]
        )
        extra = ""
        if (
            mode["draw_support"]
            or mode["story_quality"]
            or mode["trap_hit"]
            or mode["pair_raise_applies"]
            or mode["short_stack_min_raise"]
            or mode["top_pair_board_pair_base"]
        ):
            extra = (
                f"  听牌支撑={mode['draw_support']}/{mode['draw_coverage']}"
                f"  存活={mode['draw_survival']}"
                f"  续枪={mode['story_quality']}"
                f"  设伏={'中' if mode['trap_hit'] else '未中'}"
                f"  单对加注收口={'是' if mode['pair_raise_applies'] else '否'}"
                f"  短码最小加注={'保留' if mode['short_stack_min_raise'] else '否'}"
                f"  顶对公对分={mode['top_pair_board_pair_base']}"
            )
        print(
            f"    {mode['mode']:9} 评分={mode['score']}  被动={mode['passive_score']}"
            f"/{mode['call_threshold']}  价值质量={mode['value_quality_after_guards']}"
            f"  非价值={mode['bluff_quality_after_guards']}"
            f"  尺度={mode['size_preferences_small_medium_large_allin']}  {dist}{extra}"
        )
    top = "  ".join(
        f"{item['action']}{item['amount']}:{item['pct']}%"
        for item in decision["marginal_80_10_10"][:4]
    )
    print(f"    边缘化(80/10/10，未设伏)  {top}")
    if decision["trap_hit_marginal_80_10_10"]:
        trapped = "  ".join(
            f"{item['action']}{item['amount']}:{item['pct']}%"
            for item in decision["trap_hit_marginal_80_10_10"][:4]
        )
        print(f"    边缘化(80/10/10，设伏命中)  {trapped}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读拆开指定手牌里 Bot 的混合策略决策")
    parser.add_argument("hand_id", nargs="*", help="手牌 ID，可多个；省略时列出最近的手牌")
    parser.add_argument(
        "--seat",
        action="append",
        default=[],
        help="座位号，与玩家N 的 N 相同，可重复",
    )
    parser.add_argument(
        "--street",
        action="append",
        default=[],
        help="preflop、flop、turn、river，或翻牌前、翻牌、转牌、河牌",
    )
    parser.add_argument(
        "--identity",
        help=f"覆盖历史中的策略身份，例如 {MIXED_STRATEGY_IDENTIFIER_V19}",
    )
    parser.add_argument("--json", type=Path, help="把完整结果另存为 JSON")
    parser.add_argument("--recent", type=int, default=20, help="无 ID 时列出的手牌条数")
    args = parser.parse_args(argv)

    try:
        streets = parse_streets(args.street)
    except ValueError as exc:
        print(exc)
        return 2
    seats = {int(seat) for seat in args.seat} or None

    if not args.hand_id:
        try:
            _list_recent(args.recent)
        except sqlite3.Error as exc:
            print(f"无法只读打开 {db_path()}：{exc}")
            return 1
        return 0

    payload = []
    failed = False
    for hand_id in args.hand_id:
        try:
            history = _load(hand_id)
        except sqlite3.Error as exc:
            print(f"无法只读打开 {db_path()}：{exc}")
            return 1
        if history is None:
            print(f"未找到手牌 {hand_id}")
            failed = True
            continue
        hand = diagnose_history(
            history,
            hand_id=hand_id,
            seats=seats,
            streets=streets or None,
            identity=args.identity,
        )
        payload.append(hand)
        _print_hand(hand)
        replay_broke = any("error" in decision for decision in hand.get("decisions", ()))
        if "error" in hand and "decisions" not in hand or replay_broke:
            failed = True
    if args.json:
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入 {args.json}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
