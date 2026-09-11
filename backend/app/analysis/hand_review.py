"""复盘分析：从一手牌历史确定性重放，对真人每个决策点做轻量 EV 分析与错误检测。

复盘只在牌局结束后进行，此时所有底牌与公共牌均已公开，因此可以：
- 确定性重放整手动作轨迹（复用引擎规则），重建每个决策点的局面；
- 用蒙特卡洛估算「自己底牌面对随机对手范围」的摊牌胜率——与打牌时的信息边界一致，
  不读取对手真实底牌来算胜率，避免上帝视角作弊；
- 给出轻量 EV 参考量（胜率、底池赔率、跟注期望收益）与明显错误标记；
- 附上「参考 Bot（heuristic）在同一局面会怎么做」作为对比。

本模块只读引擎公开状态、不修改引擎，属于 analysis 层对 poker 层公开能力的消费。
"""

import random

from app.poker.actions import Action, ActionType
from app.poker.cards import Card, card_from_str
from app.poker.engine import PokerEngine
from app.poker.equity import equity
from app.strategy.heuristic import HeuristicStrategy

# 复盘胜率采样数：高于策略层的 500，复盘可接受更慢以求更稳。
_EQUITY_SAMPLES = 1000
# 复盘与 Bot 对比使用的固定随机种子，保证结果可复现。
_REVIEW_SEED = 0

# 弃牌放弃正 EV 的容差基准：胜率需高出底池赔率这么多才判「该跟却弃」。
_FOLD_EV_MARGIN = 0.15
# 容差随「跟注占底池比例」放大的系数：注越大，对手范围越强，vs 随机胜率越偏乐观。
_FOLD_BET_SCALE = 0.10
# 翻牌前误弃的胜率下限：vs 随机胜率无法反映加注范围，踢脚弱的高张牌易被误判。
_FOLD_MIN_EQ_PREFLOP = 0.55
# 跟注赔率不足的容差：胜率需低于底池赔率这么多才判错误，避免 EV 约等于 0 的边缘误报。
_BAD_CALL_EQ_MARGIN = 0.03
# 价值下注胜率阈值（复盘口径比策略层更保守，降低薄价值过牌的误报）。
_VALUE_BET_EQ = 0.80
# 下注过小的胜率阈值与额度比例（下注额 < 底池 / 2 视为过小）。
_UNDERBET_EQ = 0.80
_UNDERBET_DEN = 2
# 慢玩（强牌面对下注只跟不加）胜率阈值。
_SLOWPLAY_EQ = 0.90
# 纯空气胜率阈值（与 heuristic 保持一致）。
_AIR_EQ = 0.25
# 低胜率加注视为过度激进的上限。
_OVER_AGGRESSIVE_EQ = 0.50


def _fold_margin(to_call: int, pot: int) -> float:
    """误弃判定所需的胜率优势：跟注占底池比例越大，要求越高。"""
    if pot <= 0:
        return _FOLD_EV_MARGIN
    return _FOLD_EV_MARGIN + _FOLD_BET_SCALE * (to_call / pot)


def _history_action(record: dict) -> Action:
    """把历史动作记录还原为动作对象（加注额为历史记录的本次增量）。"""
    return Action(ActionType(record["action"]), int(record["amount"]))


def _replay_action(engine: PokerEngine, seat: int, action: Action) -> Action:
    """把历史动作换算为可交给引擎执行的动作。

    历史里的加注额记录的是本次增量，引擎要求的是加注后总额，需叠加该座位已投入部分。
    """
    if action.type == ActionType.RAISE:
        return Action(ActionType.RAISE, engine.players[seat].street_bet + action.amount)
    return action


def _detect_mistakes(
    action: Action,
    equity: float,
    pot_odds: float | None,
    to_call: int,
    board_len: int,
    pot: int,
    can_raise: bool,
) -> list[dict]:
    """按既定规则对单个决策点做错误检测，返回命中的错误标记列表。"""
    postflop = board_len > 0
    mistakes: list[dict] = []

    if to_call > 0:
        # 面对下注：赔率错误 +（翻牌后）慢玩 / 过度激进。
        if (
            action.type == ActionType.CALL
            and pot_odds is not None
            and equity < pot_odds - _BAD_CALL_EQ_MARGIN
        ):
            mistakes.append(
                {
                    "code": "bad_call",
                    "severity": "error",
                    "message": f"胜率 {equity:.0%} 明显低于底池赔率 {pot_odds:.0%}，跟注赔率不足",
                }
            )
        if action.type == ActionType.FOLD and pot_odds is not None:
            # 翻牌前胜率不足时，弃牌不构成明显错误。
            strong_enough = postflop or equity >= _FOLD_MIN_EQ_PREFLOP
            if strong_enough and equity > pot_odds + _fold_margin(to_call, pot):
                message = f"胜率 {equity:.0%} 明显高于赔率 {pot_odds:.0%}，弃牌可能放弃正 EV"
                mistakes.append(
                    {"code": "bad_fold", "severity": "warning", "message": message}
                )
        if postflop and action.type == ActionType.CALL and equity >= _SLOWPLAY_EQ and can_raise:
            mistakes.append(
                {
                    "code": "slowplay",
                    "severity": "warning",
                    "message": f"强牌（胜率 {equity:.0%}）只跟不加，慢玩可能丢失价值",
                }
            )
        if postflop and action.type == ActionType.RAISE and equity < _OVER_AGGRESSIVE_EQ:
            mistakes.append(
                {
                    "code": "over_aggressive",
                    "severity": "warning",
                    "message": f"低胜率（{equity:.0%}）加注过度激进",
                }
            )
    elif postflop:
        # 无人下注：价值丢失 / 下注过小 / 空气诈唬。
        if action.type == ActionType.CHECK and equity >= _VALUE_BET_EQ:
            mistakes.append(
                {
                    "code": "value_missed",
                    "severity": "warning",
                    "message": f"强牌（胜率 {equity:.0%}）无人下注时过牌，可能丢失价值",
                }
            )
        if action.type == ActionType.BET:
            if equity >= _UNDERBET_EQ and action.amount * _UNDERBET_DEN < pot:
                mistakes.append(
                    {
                        "code": "underbet",
                        "severity": "info",
                        "message": f"强牌下注偏小（{action.amount}，底池 {pot}）",
                    }
                )
            if equity < _AIR_EQ:
                mistakes.append(
                    {
                        "code": "air_bluff",
                        "severity": "info",
                        "message": f"低胜率（{equity:.0%}）下注，若非有意诈唬则偏激进",
                    }
                )

    return mistakes


def _analyze_decision(
    engine: PokerEngine,
    human_seat: int,
    action: Action,
    reference_bot: HeuristicStrategy,
    rng: random.Random,
) -> dict:
    """分析真人一个决策点：胜率 / 赔率 / EV + 参考 Bot 动作 + 错误检测。"""
    snapshot = engine.snapshot()
    legal = engine.legal_actions()
    hero_state = snapshot.players[human_seat]
    opponents = sum(1 for p in snapshot.players if p.seat != human_seat and not p.folded)

    eq = equity(hero_state.hole_cards, snapshot.board, opponents, rng, _EQUITY_SAMPLES)
    to_call = legal.call_amount
    pot_odds = to_call / (snapshot.pot + to_call) if to_call > 0 else None
    call_ev = round(eq * (snapshot.pot + to_call) - to_call) if to_call > 0 else None
    bot_action = reference_bot.choose_action(snapshot, legal)

    return {
        "street": snapshot.street.name.lower(),
        "board": [str(c) for c in snapshot.board],
        "pot": snapshot.pot,
        "to_call": to_call,
        "opponents": opponents,
        "equity": round(eq, 4),
        "pot_odds": round(pot_odds, 4) if pot_odds is not None else None,
        "call_ev": call_ev,
        "action": {"action": action.type.value, "amount": action.amount},
        "bot_action": {"action": bot_action.type.value, "amount": bot_action.amount},
        "mistakes": _detect_mistakes(
            action=action,
            equity=eq,
            pot_odds=pot_odds,
            to_call=to_call,
            board_len=len(snapshot.board),
            pot=snapshot.pot,
            can_raise=legal.can_raise,
        ),
    }


def build_review(history: dict) -> dict:
    """根据一手牌历史构造复盘结果。

    history 为 hand_history.build_hand_history 产出的 JSON 字典（已反序列化）。
    """
    num_players = history["num_players"]
    small_blind = history["small_blind"]
    big_blind = history["big_blind"]
    button = history["button"]

    hole_cards: dict[int, list[Card]] = {}
    starting_stacks: dict[int, int] = {}
    human_seat: int | None = None
    for p in history["players"]:
        seat = p["seat"]
        hole_cards[seat] = [card_from_str(c) for c in p["hole_cards"]]
        starting_stacks[seat] = p["starting_stack"]
        if p["is_human"]:
            human_seat = seat
    if human_seat is None:
        raise ValueError("历史中没有标记真人座位")
    board = [card_from_str(c) for c in history["board"]]

    engine = PokerEngine(num_players, small_blind, big_blind, max(starting_stacks.values()))
    # 各玩家在本手起始时的筹码可能不同（此前输赢或补码），需逐人还原，否则下注区间会失真。
    for seat, stack in starting_stacks.items():
        engine.players[seat].stack = stack
    engine.start_hand_with(button, hole_cards, board)

    decisions: list[dict] = []
    for record in history["actions"]:
        if record["action"] in ("small_blind", "big_blind"):
            continue
        seat = int(record["seat"])
        if engine.current_seat != seat:
            raise ValueError(f"重放状态不一致：期望座位 {seat}，实际 {engine.current_seat}")
        action = _history_action(record)
        if seat == human_seat:
            rng = random.Random(_REVIEW_SEED)
            reference_bot = HeuristicStrategy(seed=_REVIEW_SEED)
            decisions.append(
                _analyze_decision(engine, human_seat, action, reference_bot, rng)
            )
        engine.apply_action(_replay_action(engine, seat, action))

    return {
        "hand_number": history["hand_number"],
        "human_seat": human_seat,
        "reference_strategy": "heuristic",
        "decisions": decisions,
        "mistake_count": sum(len(d["mistakes"]) for d in decisions),
    }
