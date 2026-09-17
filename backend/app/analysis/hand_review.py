"""复盘分析：从一手牌历史确定性重放，对真人每个决策点做轻量 EV 分析与错误检测。

复盘只在牌局结束后进行，此时所有底牌与公共牌均已公开，因此可以：
- 确定性重放整手动作轨迹（复用引擎规则），重建每个决策点的局面；
- 用蒙特卡洛估算「自己底牌面对随机对手范围」的摊牌胜率——与打牌时的信息边界一致，
  不读取对手真实底牌来算胜率，避免上帝视角作弊；
- 给出轻量 EV 参考量（胜率、底池赔率、跟注期望收益）与明显错误标记；
- 附上「保守参考策略在同一局面会怎么做」作为对比：以启发式 Bot 的动作概率分布为基线，
  翻牌后面对下注时额外要求赔率有余量与可继续的牌力（真实成手牌或强听牌，且成手牌不被
  公共牌高张压制），强听牌的余量要求放宽；无人下注时弱踢脚顶对不做价值下注；
  避免用高张盲目跟注、用被压制的对子跟注、用弱踢脚顶对薄价值下注。

本模块只读引擎公开状态、不修改引擎，属于 analysis 层对 poker 层公开能力的消费。
"""

import random
from collections.abc import Sequence

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import Card, card_from_str
from app.poker.engine import PokerEngine
from app.poker.equity import equity
from app.poker.evaluator import evaluate
from app.poker.hand import HandCategory
from app.poker.state import GameState, PlayerState, Street
from app.strategy.heuristic import HeuristicStrategy, draw_outs

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
# 保守参考动作所需的强听牌补牌数下限（开放式顺子 / 同花听牌）。
_STRONG_DRAW_OUTS = 8
# 保守参考动作的小注例外：跟注额不超过底池的 1/3 时放宽牌力要求，高张也可便宜看牌。
_SMALL_BET_NUM = 1
_SMALL_BET_DEN = 3
# 强听牌的余量折扣：听牌的胜率主要来自补牌、隐含赔率更高，面对下注不必要求满额余量。
_DRAW_MARGIN_SCALE = 0.5


def _fold_margin(to_call: int, pot: int) -> float:
    """误弃判定所需的胜率优势：跟注占底池比例越大，要求越高。"""
    if pot <= 0:
        return _FOLD_EV_MARGIN
    return _FOLD_EV_MARGIN + _FOLD_BET_SCALE * (to_call / pot)


def _strong_draw(hole_cards: Sequence[Card], board: Sequence[Card]) -> bool:
    """是否强听牌：补牌数达标且公共牌尚未发完（翻牌前不适用）。"""
    if not 3 <= len(board) < 5:
        return False
    return draw_outs(list(hole_cards), tuple(board)) >= _STRONG_DRAW_OUTS


def _call_margin(
    hole_cards: Sequence[Card],
    board: Sequence[Card],
    to_call: int,
    pot: int,
) -> float:
    """跟注所需的胜率余量：强听牌折半，其余按跟注占底池比例放大。"""
    margin = _fold_margin(to_call, pot)
    if _strong_draw(hole_cards, board):
        return margin * _DRAW_MARGIN_SCALE
    return margin


def _is_made_hand(hole_cards: Sequence[Card], board: Sequence[Card]) -> bool:
    """底牌是否参与成牌：口袋对、与公共牌配对，或公共牌本身构成三条及以上。

    排除「仅靠公共牌成对」（底牌只当踢脚的一对/两对），这类牌面对下注难以兑现。
    """
    ranks = [c.rank.value for c in hole_cards]
    if ranks[0] == ranks[1]:
        return True
    board_ranks = {c.rank.value for c in board}
    if any(r in board_ranks for r in ranks):
        return True
    if len(board) < 3:
        return False
    return evaluate([*hole_cards, *board]).category >= HandCategory.THREE_OF_A_KIND


def _dominated_pair(hole_cards: Sequence[Card], board: Sequence[Card]) -> bool:
    """是否「一对且该对低于公共牌最高点数」：被公共牌高张压制的成手牌。

    作为跟注侧的牌力质量门槛，与价值下注侧的弱踢脚顶对门槛对称：这类牌面对下注时
    只能赢对手诈唬，兑现能力差。顶对与超对不受影响；两对、三条等更强牌力不适用。
    """
    if len(board) < 3:
        return False
    rank = evaluate([*hole_cards, *board])
    if rank.category != HandCategory.ONE_PAIR:
        return False
    pair_rank = rank.tiebreak[0]
    if not any(c.rank.value == pair_rank for c in hole_cards):
        return False
    return pair_rank < max(c.rank.value for c in board)


def _has_playable_strength(
    hole_cards: Sequence[Card],
    board: Sequence[Card],
    to_call: int,
    pot: int,
) -> bool:
    """是否具备可继续的牌力：真实成手牌或强听牌；跟注额很小时放宽。

    被公共牌高张压制的对子不算可继续牌力，但若同时构成强听牌仍可继续。
    """
    if to_call * _SMALL_BET_DEN <= pot * _SMALL_BET_NUM:
        return True
    if _is_made_hand(hole_cards, board) and not _dominated_pair(hole_cards, board):
        return True
    return _strong_draw(hole_cards, board)


def _weak_kicker_top_pair(hole_cards: Sequence[Card], board: Sequence[Card]) -> bool:
    """是否「顶对 + 弱踢脚」，作为价值下注的牌力质量门槛（与误弃的牌力要求对称）。

    判定条件：最强牌力恰为一对、该对由底牌配中公共牌最高点数，且另一张底牌（踢脚）
    低于公共牌去重后第二高的点数。超对、两对、三条等更强牌力不适用；仅靠公共牌
    成对（底牌只是踢脚）也不算真实顶对。
    """
    if len(board) < 3:
        return False
    rank = evaluate([*hole_cards, *board])
    if rank.category != HandCategory.ONE_PAIR:
        return False
    board_ranks = sorted({c.rank.value for c in board}, reverse=True)
    if len(board_ranks) < 2 or rank.tiebreak[0] != board_ranks[0]:
        return False
    hole_ranks = sorted((c.rank.value for c in hole_cards), reverse=True)
    if hole_ranks[0] != rank.tiebreak[0]:
        return False
    return hole_ranks[1] < board_ranks[1]


def _shift_mass(
    distribution: list[tuple[Action, float]],
    from_type: ActionType,
    to_action: Action,
) -> list[tuple[Action, float]]:
    """把某类动作的概率质量整体转移到目标动作，用于复盘的保守收窄。

    目标动作已在分布中则叠加权重，否则新增一项；无该类动作时原样返回。
    """
    moved = sum(weight for action, weight in distribution if action.type == from_type)
    if moved <= 0.0:
        return distribution
    kept = [(action, weight) for action, weight in distribution if action.type != from_type]
    for i, (action, weight) in enumerate(kept):
        if action.type == to_action.type:
            kept[i] = (action, weight + moved)
            return kept
    return [*kept, (to_action, moved)]


def _conservative_distribution(
    snapshot: GameState,
    legal: LegalActions,
    me: PlayerState,
    eq: float,
    baseline: list[tuple[Action, float]],
) -> list[tuple[Action, float]]:
    """在启发式基线分布上做保守收窄，返回复盘参考分布。

    翻牌后面对下注：胜率对底池赔率无余量或底牌无可继续的牌力时，把跟注概率质量
    转移到弃牌（跟注额很小时放宽，强听牌的余量要求放宽）；翻牌后无人下注：
    弱踢脚顶对不做价值下注，把下注质量转移到过牌。翻牌前与其它动作原样沿用基线。
    """
    if snapshot.street == Street.PREFLOP:
        return baseline
    if legal.call_amount > 0:
        pot_odds = legal.call_amount / (snapshot.pot + legal.call_amount)
        margin = _call_margin(
            me.hole_cards, snapshot.board, legal.call_amount, snapshot.pot
        )
        has_margin = eq > pot_odds + margin
        playable = _has_playable_strength(
            me.hole_cards, snapshot.board, legal.call_amount, snapshot.pot
        )
        if has_margin and playable:
            return baseline
        return _shift_mass(baseline, ActionType.CALL, Action(ActionType.FOLD))
    if _weak_kicker_top_pair(me.hole_cards, snapshot.board):
        return _shift_mass(baseline, ActionType.BET, Action(ActionType.CHECK))
    return baseline


def _mode_action(distribution: list[tuple[Action, float]]) -> Action:
    """取分布中概率最高的动作作为参考动作（并列时取列表靠前者）。"""
    return max(distribution, key=lambda item: item[1])[0]


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
    pot: int,
    can_raise: bool,
    hole_cards: Sequence[Card],
    board: Sequence[Card],
    big_blind: int,
) -> list[dict]:
    """按既定规则对单个决策点做错误检测，返回命中的错误标记列表。"""
    postflop = len(board) > 0
    # 翻牌前跟注额不超过一个大盲（补齐盲注 / limp）属廉价看牌，不判赔率不足。
    cheap_preflop = not postflop and to_call <= big_blind
    mistakes: list[dict] = []

    if to_call > 0:
        # 面对下注：赔率错误 +（翻牌后）慢玩 / 过度激进。
        if (
            action.type == ActionType.CALL
            and pot_odds is not None
            and not cheap_preflop
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
            # 翻牌前胜率不足时，弃牌不构成明显错误；
            # 翻牌后还要求底牌有可继续的牌力，与保守参考动作的跟注标准一致。
            strong_enough = postflop or equity >= _FOLD_MIN_EQ_PREFLOP
            playable = not postflop or _has_playable_strength(hole_cards, board, to_call, pot)
            margin = _call_margin(hole_cards, board, to_call, pot)
            if strong_enough and playable and equity > pot_odds + margin:
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
        # 弱踢脚顶对属薄价值，过牌不算丢失价值，与参考动作共用同一门槛。
        if (
            action.type == ActionType.CHECK
            and equity >= _VALUE_BET_EQ
            and not _weak_kicker_top_pair(hole_cards, board)
        ):
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
    actual_call_amount = legal.actual_call_amount
    is_short_all_in_call = legal.is_short_all_in_call
    reference_pot_odds = to_call / (snapshot.pot + to_call) if to_call > 0 else None
    reference_call_ev = (
        round(eq * (snapshot.pot + to_call) - to_call) if to_call > 0 else None
    )
    baseline = reference_bot.action_distribution(snapshot, legal)
    distribution = _conservative_distribution(snapshot, legal, hero_state, eq, baseline)
    bot_action = _mode_action(distribution)

    return {
        "street": snapshot.street.name.lower(),
        "board": [str(c) for c in snapshot.board],
        "pot": snapshot.pot,
        "to_call": to_call,
        "actual_call_amount": actual_call_amount,
        "is_short_all_in_call": is_short_all_in_call,
        "opponents": opponents,
        "equity": round(eq, 4),
        "pot_odds": (
            round(reference_pot_odds, 4)
            if reference_pot_odds is not None and not is_short_all_in_call
            else None
        ),
        "call_ev": reference_call_ev if not is_short_all_in_call else None,
        "action": {"action": action.type.value, "amount": action.amount},
        "bot_action": {"action": bot_action.type.value, "amount": bot_action.amount},
        "bot_distribution": [
            {"action": act.type.value, "amount": act.amount, "probability": round(weight, 4)}
            for act, weight in sorted(distribution, key=lambda item: item[1], reverse=True)
        ],
        "mistakes": _detect_mistakes(
            action=action,
            equity=eq,
            pot_odds=reference_pot_odds,
            to_call=to_call,
            pot=snapshot.pot,
            can_raise=legal.can_raise,
            hole_cards=hero_state.hole_cards,
            board=snapshot.board,
            big_blind=engine.big_blind,
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
        "reference_strategy": "heuristic-conservative",
        "decisions": decisions,
        "mistake_count": sum(len(d["mistakes"]) for d in decisions),
    }
