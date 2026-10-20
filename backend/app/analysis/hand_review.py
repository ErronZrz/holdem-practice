"""复盘分析：从一手牌历史确定性重放，对真人每个决策点做份额估计与错误检测。

复盘只在牌局结束后进行，重放整手动作以重建每个决策点。份额与跟注期望只使用英雄底牌、
公共牌和截至该决策点的公开行动，不读取对手真实底牌。参考动作来自紧手标准模式，
发布前会收回和这些指标打架的质量：面对下注且跟注期望为负时，跟注质量挪到弃牌，
份额低于平均时下注和加注也挪到弃牌；翻后无人下注且份额过低或行动线已经偏高时，
主动质量挪到过牌；弃牌会被标成放弃正期望时，弃牌质量挪到跟注。跟注的对外金额
是当时实际要投入的筹码。错误来自份额、跟注期望和牌力门槛；与参考众数不同本身不是错误，
参考动作只用来否决与参考自己方向相反的标记。

本模块只读引擎公开状态，不修改引擎。
"""

import random
from collections.abc import Sequence

from app.analysis.action_line_equity import ActionLineTracker, estimate_decision
from app.analysis.reference_identity import reference_declaration
from app.poker.actions import Action, ActionType
from app.poker.cards import Card, card_from_str
from app.poker.engine import PokerEngine
from app.poker.evaluator import evaluate
from app.poker.hand import HandCategory
from app.strategy.heuristic import draw_outs
from app.strategy.mixed_context import MixedSummaryTracker, mixed_state
from app.strategy.mixed_policy import MIXED_DISTRIBUTION_UNITS, HandMode, MixedDistribution
from app.strategy.mixed_strategy import MIXED_STRATEGY_IDENTIFIER_V13, MixedLocalStrategy
from app.strategy.projection import project_for_actor

# 复盘采样数与固定种子：牌局结束后可以多采样，结果必须可复现。
_EQUITY_SAMPLES = 1000
_REVIEW_SEED = 0

# 弃牌放弃正期望的容差：跟注占底池比例越大，要求的正期望越高。
_FOLD_EV_MARGIN = 0.15
_FOLD_BET_SCALE = 0.10
# 跟注亏损需超过竞争层的这个比例，才避免把接近零的期望判成错误。
_BAD_CALL_FRACTION = 0.03
# 相对单挑公平份额的倍数。单挑时公平份额是 1/2，这些倍数与原先的固定胜率线重合。
_VALUE_FAIR_SCALE = 1.6
_SLOWPLAY_FAIR_SCALE = 1.8
_AIR_FAIR_SCALE = 0.5
# 公开行动线达到这一档，说明此前已经出现再加注或翻后较大的主动投入。
_HIGH_ACTION_LINE = 3
# 下注额小于底池的这个比例视为过小。
_UNDERBET_DEN = 2
# 强听牌补牌数下限（开放式顺子 / 同花听牌）。
_STRONG_DRAW_OUTS = 8
# 跟注额不超过底池的这个比例时，放宽可继续牌力的要求。
_SMALL_BET_NUM = 1
_SMALL_BET_DEN = 3


def _call_ev_margin(actual_call: int, pot: int, contested: int, big_blind: int) -> float:
    """弃牌仍算明显正期望时，跟注期望需要超过的筹码数。"""
    ratio = (actual_call / pot) if pot > 0 else 0.0
    scaled = (_FOLD_EV_MARGIN + _FOLD_BET_SCALE * ratio) * contested
    return max(float(big_blind), scaled)


def _bad_call_tolerance(contested: int, big_blind: int) -> float:
    """跟注亏损在这个幅度以内不标错误。"""
    return max(float(big_blind), _BAD_CALL_FRACTION * contested)


def _fair_share(opponents: int) -> float:
    """当前未弃牌人数下的平均份额。"""
    return 1.0 / (opponents + 1)


def _strong_draw(hole_cards: Sequence[Card], board: Sequence[Card]) -> bool:
    """是否强听牌：补牌数达标且公共牌尚未发完（翻牌前不适用）。"""
    if not 3 <= len(board) < 5:
        return False
    return draw_outs(list(hole_cards), tuple(board)) >= _STRONG_DRAW_OUTS


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

    作为跟注侧的牌力质量门槛：这类牌面对下注时只能赢对手诈唬。顶对与超对不受影响；
    两对、三条等更强牌力不适用。
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
    """是否「顶对 + 弱踢脚」，作为价值下注的牌力质量门槛。

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


def _mode_action(distribution: list[tuple[Action, float]]) -> Action:
    """取分布中概率最高的动作（并列时取列表靠前者）。"""
    return max(distribution, key=lambda item: item[1])[0]


def _move_mass(
    distribution: list[tuple[Action, float]],
    sources: frozenset[ActionType],
    target: ActionType,
) -> list[tuple[Action, float]]:
    """把若干动作的概率质量归并到目标动作。目标已在分布里就累加，否则追加一条。"""
    moved = sum(weight for action, weight in distribution if action.type in sources)
    if moved <= 0.0:
        return distribution
    kept = [(action, weight) for action, weight in distribution if action.type not in sources]
    for index, (action, weight) in enumerate(kept):
        if action.type == target:
            kept[index] = (action, weight + moved)
            return kept
    return [*kept, (Action(target), moved)]


def _guard_negative_call(
    distribution: list[tuple[Action, float]],
    call_ev: float | None,
    *,
    to_call: int,
    equity: float,
    opponents: int,
) -> list[tuple[Action, float]]:
    """面对下注且跟注期望为负时，把继续质量收成弃牌。

    跟注一律挪走。份额低于当前人数的平均份额时，下注和加注也一并挪走；
    份额并不低时加注保留，因为跟注期望不含加注后的弃牌权益。
    """
    if to_call <= 0 or call_ev is None or call_ev >= 0.0:
        return distribution
    sources = {ActionType.CALL}
    if equity < _fair_share(opponents):
        sources.update((ActionType.BET, ActionType.RAISE))
    return _move_mass(distribution, frozenset(sources), ActionType.FOLD)


def _guard_low_equity_lead(
    distribution: list[tuple[Action, float]],
    *,
    to_call: int,
    postflop: bool,
    equity: float,
    opponents: int,
    max_line: int,
) -> list[tuple[Action, float]]:
    """翻后无人下注时，把过低份额或高行动线下的主动质量收成过牌。"""
    if not postflop or to_call != 0:
        return distribution
    fair = _fair_share(opponents)
    below_air = equity < _AIR_FAIR_SCALE * fair
    high_line = max_line >= _HIGH_ACTION_LINE and equity < fair
    if not below_air and not high_line:
        return distribution
    return _move_mass(
        distribution,
        frozenset({ActionType.BET, ActionType.RAISE}),
        ActionType.CHECK,
    )


def _guard_bad_fold(
    distribution: list[tuple[Action, float]],
    *,
    to_call: int,
    bad_fold: bool,
) -> list[tuple[Action, float]]:
    """弃牌会被标成放弃正期望时，把弃牌质量挪到跟注。"""
    if to_call <= 0 or not bad_fold:
        return distribution
    return _move_mass(distribution, frozenset({ActionType.FOLD}), ActionType.CALL)


def _folding_gives_up_value(
    *,
    equity: float,
    call_ev: float | None,
    pot_odds: float | None,
    to_call: int,
    actual_call: int,
    pot: int,
    contested: int,
    can_raise: bool,
    opponents: int,
    hole_cards: Sequence[Card],
    board: Sequence[Card],
    big_blind: int,
) -> bool:
    """用弃牌探针判断这一下会不会被标成放弃正期望。"""
    if to_call <= 0:
        return False
    found = _detect_mistakes(
        action=Action(ActionType.FOLD),
        equity=equity,
        call_ev=call_ev,
        pot_odds=pot_odds,
        to_call=to_call,
        actual_call=actual_call,
        pot=pot,
        contested=contested,
        can_raise=can_raise,
        opponents=opponents,
        hole_cards=hole_cards,
        board=board,
        big_blind=big_blind,
        reference=Action(ActionType.FOLD),
    )
    return any(item["code"] == "bad_fold" for item in found)


def _guard_reference_distribution(
    distribution: list[tuple[Action, float]],
    *,
    to_call: int,
    call_ev: float | None,
    equity: float,
    opponents: int,
    postflop: bool,
    max_line: int,
    bad_fold: bool,
) -> list[tuple[Action, float]]:
    """发布前收回和份额、跟注期望打架的质量。调用方在全部归并之后再取众数。"""
    guarded = _guard_negative_call(
        distribution,
        call_ev,
        to_call=to_call,
        equity=equity,
        opponents=opponents,
    )
    guarded = _guard_low_equity_lead(
        guarded,
        to_call=to_call,
        postflop=postflop,
        equity=equity,
        opponents=opponents,
        max_line=max_line,
    )
    return _guard_bad_fold(guarded, to_call=to_call, bad_fold=bad_fold)


def _distribution_rows(selected: MixedDistribution) -> list[tuple[Action, float]]:
    """把整数单位的混合分布换成概率。零单位候选不进入展示。"""
    scale = float(MIXED_DISTRIBUTION_UNITS)
    rows: list[tuple[Action, float]] = []
    for item in selected.candidates:
        if item.units <= 0:
            continue
        rows.append((Action(item.action, item.amount), item.units / scale))
    return rows


def _reference_chips(
    action: Action,
    street_bet: int,
    stack: int,
    actual_call_amount: int,
) -> int:
    """把参考动作金额换成与历史相同的本次投入，且不超过当时剩余筹码。

    策略里的加注额是本街总额，跟注额固定写成 0。历史和牌桌展示用的是这一下实际投入。
    跟注改为当时要支付的筹码；下注和加注仍按本次投入换算。
    """
    if action.type == ActionType.RAISE:
        chips = action.amount - street_bet
    elif action.type == ActionType.BET:
        chips = action.amount
    elif action.type == ActionType.CALL:
        chips = actual_call_amount
    else:
        chips = 0
    if chips < 0:
        chips = 0
    return min(chips, max(0, stack))


def _publish_reference(
    distribution: list[tuple[Action, float]],
    mode: Action,
    street_bet: int,
    stack: int,
    actual_call_amount: int,
) -> tuple[dict, list[dict]]:
    """发布参考动作与分布。加注额改成本次投入，跟注额改为实际支付，相同投入合并概率。"""
    presented = _present_distribution(distribution, mode)
    merged: dict[tuple[str, int], float] = {}
    order: list[tuple[str, int]] = []
    for item in presented:
        kind = item["action"]
        amount = _reference_chips(
            Action(ActionType(kind), int(item["amount"])),
            street_bet,
            stack,
            actual_call_amount,
        )
        key = (kind, amount)
        if key not in merged:
            order.append(key)
            merged[key] = 0.0
        merged[key] += float(item["probability"])
    rows = [
        {"action": kind, "amount": amount, "probability": round(merged[(kind, amount)], 4)}
        for kind, amount in order
    ]
    mode_amount = _reference_chips(mode, street_bet, stack, actual_call_amount)
    return {"action": mode.type.value, "amount": mode_amount}, rows


def _present_distribution(
    distribution: list[tuple[Action, float]],
    mode: Action,
) -> list[dict]:
    """按概率从高到低展示，并把四舍五入的余数放在众数上，使展示总和为 1。"""
    ordered = sorted(
        distribution,
        key=lambda item: (item[1], item[0] == mode),
        reverse=True,
    )
    shown = [round(weight, 4) for _action, weight in ordered]
    mode_index = next(
        (index for index, (action, _weight) in enumerate(ordered) if action == mode),
        0,
    )
    if shown:
        shown[mode_index] = round(shown[mode_index] + (1.0 - sum(shown)), 4)
        top = max(shown)
        if shown[mode_index] + 1e-9 < top:
            donor = shown.index(top)
            gap = round(top - shown[mode_index], 4)
            shown[donor] = round(shown[donor] - gap, 4)
            shown[mode_index] = round(shown[mode_index] + gap, 4)
    return [
        {"action": action.type.value, "amount": action.amount, "probability": probability}
        for (action, _weight), probability in zip(ordered, shown, strict=True)
    ]


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
    call_ev: float | None,
    pot_odds: float | None,
    to_call: int,
    actual_call: int,
    pot: int,
    contested: int,
    can_raise: bool,
    opponents: int,
    hole_cards: Sequence[Card],
    board: Sequence[Card],
    big_blind: int,
    reference: Action,
) -> list[dict]:
    """按份额和跟注期望标记明显错误。参考动作只用于方向否决。"""
    postflop = len(board) > 0
    fair = _fair_share(opponents)
    value_bar = _VALUE_FAIR_SCALE * fair
    slowplay_bar = _SLOWPLAY_FAIR_SCALE * fair
    air_bar = _AIR_FAIR_SCALE * fair
    # 翻牌前跟注额不超过一个大盲（补齐盲注 / limp）属廉价看牌，不判赔率不足。
    cheap_preflop = not postflop and to_call <= big_blind
    mistakes: list[dict] = []
    facing_bet = to_call > 0 and call_ev is not None and pot_odds is not None

    if facing_bet:
        assert call_ev is not None
        if (
            action.type == ActionType.CALL
            and not cheap_preflop
            and call_ev < -_bad_call_tolerance(contested, big_blind)
        ):
            shown = int(round(call_ev))
            mistakes.append(
                {
                    "code": "bad_call",
                    "severity": "error",
                    "message": f"跟注期望 {shown}，亏损超过容差，跟注赔率不足",
                }
            )
        if action.type == ActionType.FOLD:
            # 翻牌前份额不足时，弃牌不构成明显错误；
            # 翻牌后还要求底牌有可继续的牌力。
            playable = not postflop or _has_playable_strength(hole_cards, board, to_call, pot)
            strong_enough = postflop or equity >= fair
            margin = _call_ev_margin(actual_call, pot, contested, big_blind)
            if playable and strong_enough and call_ev > margin:
                shown = int(round(call_ev))
                mistakes.append(
                    {
                        "code": "bad_fold",
                        "severity": "warning",
                        "message": f"跟注期望 {shown}，弃牌可能放弃正 EV",
                    }
                )
        if (
            postflop
            and action.type == ActionType.CALL
            and can_raise
            and equity >= slowplay_bar
            and reference.type == ActionType.RAISE
        ):
            mistakes.append(
                {
                    "code": "slowplay",
                    "severity": "warning",
                    "message": f"强牌（胜率 {equity:.0%}）只跟不加，慢玩可能丢失价值",
                }
            )
        if (
            postflop
            and action.type == ActionType.RAISE
            and equity < fair
            and reference.type not in (ActionType.BET, ActionType.RAISE)
        ):
            mistakes.append(
                {
                    "code": "over_aggressive",
                    "severity": "warning",
                    "message": f"低胜率（{equity:.0%}）加注过度激进",
                }
            )
    elif postflop:
        reference_bets = reference.type == ActionType.BET
        if (
            action.type == ActionType.CHECK
            and equity >= value_bar
            and not _weak_kicker_top_pair(hole_cards, board)
            and reference_bets
        ):
            mistakes.append(
                {
                    "code": "value_missed",
                    "severity": "warning",
                    "message": f"强牌（胜率 {equity:.0%}）无人下注时过牌，可能丢失价值",
                }
            )
        if action.type == ActionType.BET:
            if (
                equity >= value_bar
                and action.amount * _UNDERBET_DEN < pot
                and reference_bets
                and reference.amount > action.amount
            ):
                mistakes.append(
                    {
                        "code": "underbet",
                        "severity": "info",
                        "message": f"强牌下注偏小（{action.amount}，底池 {pot}）",
                    }
                )
            if equity < air_bar and reference.type == ActionType.CHECK:
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
    reference_bot: MixedLocalStrategy,
    context: object,
    levels: ActionLineTracker,
    rng: random.Random,
) -> dict:
    """分析真人一个决策点：份额 / 赔率 / 跟注期望 + 参考动作 + 错误检测。"""
    snapshot = engine.snapshot()
    legal = engine.legal_actions()
    hero_state = snapshot.players[human_seat]
    live = levels.live_opponents(snapshot.players, human_seat)
    projection = engine.candidate_call_pot_projection()
    valued = estimate_decision(
        hero_cards=hero_state.hole_cards,
        board=snapshot.board,
        opponents=live,
        projection=projection,
        pot=snapshot.pot,
        hero_seat=human_seat,
        actual_call_amount=legal.actual_call_amount,
        samples=_EQUITY_SAMPLES,
        rng=rng,
    )
    projected = mixed_state(project_for_actor(snapshot), context)
    selected = reference_bot.distribution_for(projected, legal, mode=HandMode.NORMAL)
    baseline = _distribution_rows(selected)
    to_call = legal.call_amount
    opponents = len(live)
    max_line = max((level for _seat, level in live), default=0)
    bad_fold = _folding_gives_up_value(
        equity=valued.equity,
        call_ev=valued.call_ev,
        pot_odds=valued.pot_odds,
        to_call=to_call,
        actual_call=legal.actual_call_amount,
        pot=snapshot.pot,
        contested=valued.contested,
        can_raise=legal.can_raise,
        opponents=opponents,
        hole_cards=hero_state.hole_cards,
        board=snapshot.board,
        big_blind=engine.big_blind,
    )
    distribution = _guard_reference_distribution(
        baseline,
        to_call=to_call,
        call_ev=valued.call_ev,
        equity=valued.equity,
        opponents=opponents,
        postflop=len(snapshot.board) > 0,
        max_line=max_line,
        bad_fold=bad_fold,
    )
    bot_action = _mode_action(distribution)
    paid = 0
    if action.type in (ActionType.BET, ActionType.CALL, ActionType.RAISE):
        paid = max(0, action.amount)
    paid = min(paid, hero_state.stack)
    stack_after = hero_state.stack - paid
    published_action, published_distribution = _publish_reference(
        distribution,
        bot_action,
        hero_state.street_bet,
        hero_state.stack,
        legal.actual_call_amount,
    )

    return {
        "street": snapshot.street.name.lower(),
        "board": [str(c) for c in snapshot.board],
        "pot": snapshot.pot,
        "to_call": to_call,
        "actual_call_amount": legal.actual_call_amount,
        "is_short_all_in_call": legal.is_short_all_in_call,
        "opponents": opponents,
        "equity": round(valued.equity, 4),
        "pot_odds": None if valued.pot_odds is None else round(valued.pot_odds, 4),
        # 展示四舍五入到筹码单位；错误判定使用上面的浮点期望，避免一个筹码的舍入改判。
        "call_ev": None if valued.call_ev is None else int(round(valued.call_ev)),
        "action": {"action": action.type.value, "amount": action.amount},
        "stack_after": stack_after,
        "bot_action": published_action,
        "bot_distribution": published_distribution,
        "mistakes": _detect_mistakes(
            action=action,
            equity=valued.equity,
            call_ev=valued.call_ev,
            pot_odds=valued.pot_odds,
            to_call=to_call,
            actual_call=legal.actual_call_amount,
            pot=snapshot.pot,
            contested=valued.contested,
            can_raise=legal.can_raise,
            opponents=opponents,
            hole_cards=hero_state.hole_cards,
            board=snapshot.board,
            big_blind=engine.big_blind,
            reference=bot_action,
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
    for player in history["players"]:
        seat = player["seat"]
        hole_cards[seat] = [card_from_str(c) for c in player["hole_cards"]]
        starting_stacks[seat] = player["starting_stack"]
        if player["is_human"]:
            human_seat = seat
    if human_seat is None:
        raise ValueError("历史中没有标记真人座位")
    board = [card_from_str(c) for c in history["board"]]

    engine = PokerEngine(num_players, small_blind, big_blind, max(starting_stacks.values()))
    # 各玩家在本手起始时的筹码可能不同（此前输赢或补码），需逐人还原，否则下注区间会失真。
    for seat, stack in starting_stacks.items():
        engine.players[seat].stack = stack
    engine.start_hand_with(button, hole_cards, board)

    # 座位集合只放真人自己，分派后的风格固定为紧手，手模式固定为标准。
    reference_bot = MixedLocalStrategy(
        seed=_REVIEW_SEED,
        bot_seats=(human_seat,),
        identifier=MIXED_STRATEGY_IDENTIFIER_V13,
    )
    tracker = MixedSummaryTracker()
    tracker.begin_hand(
        hand_number=int(history["hand_number"]),
        num_players=num_players,
        small_blind=small_blind,
        big_blind=big_blind,
        bot_seats=(human_seat,),
        history=engine.history,
    )
    levels = ActionLineTracker(num_players)

    decisions: list[dict] = []
    for record in history["actions"]:
        if record["action"] in ("small_blind", "big_blind"):
            continue
        seat = int(record["seat"])
        if engine.current_seat != seat:
            raise ValueError(f"重放状态不一致：期望座位 {seat}，实际 {engine.current_seat}")
        action = _history_action(record)
        levels.begin_street(str(record["street"]))
        if seat == human_seat:
            decisions.append(
                _analyze_decision(
                    engine,
                    human_seat,
                    action,
                    reference_bot,
                    tracker.context(),
                    levels,
                    random.Random(_REVIEW_SEED),
                )
            )
        pot_before = engine.pot
        levels.commit(
            seat=seat,
            action=action.type.value,
            amount=action.amount,
            pot_before=pot_before,
            big_blind=big_blind,
        )
        engine.apply_action(_replay_action(engine, seat, action))
        tracker.consume_after_action(engine.history)

    return {
        "hand_number": history["hand_number"],
        "human_seat": human_seat,
        # 参考契约（来源/版本/覆盖/适用域/局限）来自唯一事实源，避免在分析层另写字面量。
        **reference_declaration(),
        "decisions": decisions,
        "mistake_count": sum(len(d["mistakes"]) for d in decisions),
    }
