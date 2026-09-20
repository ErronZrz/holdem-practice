"""决策延迟测量用的局面构造与计时辅助（非用例文件，只被回归测试与 opt-in 入口引用）。

构造方式：用引擎的合法动作把牌局推进到目标街，并注入确定性的底牌与公共牌序列。
测量只把只读快照交给策略，因此不读取对手暗牌、未来牌，也不读取任何运行中的 seed。
"""

import random
import time

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import Card, Rank, Suit
from app.poker.engine import PokerEngine
from app.poker.state import GameState, Street
from app.strategy.heuristic import HeuristicStrategy

from .helpers import cards

_FULL_DECK = [Card(rank, suit) for suit in Suit for rank in Rank]

STREET_ORDER = (Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER)
STREET_LABELS = {
    Street.PREFLOP: "preflop",
    Street.FLOP: "flop",
    Street.TURN: "turn",
    Street.RIVER: "river",
}
STREET_BY_LABEL = {label: street for street, label in STREET_LABELS.items()}
BOARD_SIZE = {Street.PREFLOP: 0, Street.FLOP: 3, Street.TURN: 4, Street.RIVER: 5}

SMALL_BLIND = 5
BIG_BLIND = 10
DEFAULT_STARTING_STACK = 1_000
SHALLOW_STARTING_STACK = 200
DEEP_STARTING_STACK = 20_000
# 每个（人数, 街）单元轮转的局面变体数，用于覆盖不同牌力分支。
BASELINE_VARIANTS = 4
# 固定构造种子：只决定测量到哪些局面，不会被写入任何报告。
CONSTRUCTION_SEED = 20260920

# 强听牌局面：自己持同花 + 顺子组合听牌且无人下注，从而触达补牌统计分支。
# 公共牌含两张同花牌，使单张补牌即可成同花，补牌数足以覆盖组合听牌阈值。
_STRONG_DRAW_HOLE = ("Jh", "Th")
_STRONG_DRAW_BOARD = {
    "flop": ("9h", "8h", "2c"),
    "turn": ("9h", "8h", "2c", "3s"),
}


def _advance(engine: PokerEngine, target: Street) -> None:
    """用合法动作把牌局推进到目标街：面对下注则跟注，否则过牌。"""
    guard = 0
    while engine.street < target:
        guard += 1
        if guard > 4 * engine.num_players + 8:
            raise AssertionError("无法用合法动作推进到目标街")
        legal = engine.legal_actions()
        if legal.can_check:
            engine.apply_action(Action(ActionType.CHECK))
        elif legal.can_call:
            engine.apply_action(Action(ActionType.CALL))
        else:
            raise AssertionError("缺少可用的合法推进动作")
    if engine.hand_over:
        raise AssertionError("局面在目标街之前已经结束")


def build_state(
    player_count: int,
    street: Street,
    *,
    starting_stack: int = DEFAULT_STARTING_STACK,
    variant: int = 0,
    holes: dict[int, list[Card]] | None = None,
    board: list[Card] | None = None,
) -> tuple[GameState, LegalActions]:
    """构造目标街上的一个合法决策局面，返回只读快照与合法动作。"""
    if holes is None or board is None:
        pool = random.Random(CONSTRUCTION_SEED + player_count * 1_000 + variant).sample(
            _FULL_DECK, player_count * 2 + 5
        )
        holes = {seat: pool[2 * seat : 2 * seat + 2] for seat in range(player_count)}
        board = pool[2 * player_count :]
    engine = PokerEngine(
        player_count, SMALL_BLIND, BIG_BLIND, starting_stack, seed=CONSTRUCTION_SEED
    )
    engine.start_hand_with(0, holes, board)
    _advance(engine, street)
    state = engine.snapshot()
    if len(state.board) != BOARD_SIZE[street]:
        raise AssertionError("目标街的公共牌数量不符")
    return state, engine.legal_actions()


def build_strong_draw_state(
    player_count: int,
    street: Street,
    *,
    starting_stack: int = DEFAULT_STARTING_STACK,
) -> tuple[GameState, LegalActions]:
    """构造强听牌局面：先探测行动座位，再把听牌底牌发给该座位。"""
    label = STREET_LABELS[street]
    board = cards(" ".join(_STRONG_DRAW_BOARD[label]))
    probe, probe_legal = build_state(player_count, street, starting_stack=starting_stack)
    del probe_legal
    hero = probe.current_seat

    used = set(board) | set(cards(" ".join(_STRONG_DRAW_HOLE)))
    rest = [card for card in _FULL_DECK if card not in used]
    holes: dict[int, list[Card]] = {}
    cursor = 0
    for seat in range(player_count):
        if seat == hero:
            holes[seat] = cards(" ".join(_STRONG_DRAW_HOLE))
            continue
        holes[seat] = rest[cursor : cursor + 2]
        cursor += 2

    state, legal = build_state(
        player_count,
        street,
        starting_stack=starting_stack,
        holes=holes,
        board=board,
    )
    if state.current_seat != hero:
        raise AssertionError("强听牌局面的行动座位与探测结果不一致")
    return state, legal


def baseline_cases(
    player_count: int,
    starting_stack: int = DEFAULT_STARTING_STACK,
) -> dict[str, list[tuple[GameState, LegalActions]]]:
    """按街给出基础矩阵的局面对集合：每街若干确定性变体。"""
    return {
        STREET_LABELS[street]: [
            build_state(
                player_count,
                street,
                starting_stack=starting_stack,
                variant=variant,
            )
            for variant in range(BASELINE_VARIANTS)
        ]
        for street in STREET_ORDER
    }


def make_strategy(seed_offset: int = 0) -> HeuristicStrategy:
    """按固定种子构造测量用策略实例，使随机源可复现。"""
    return HeuristicStrategy(seed=CONSTRUCTION_SEED + seed_offset)


def measure_decision_latencies(
    strategy: HeuristicStrategy,
    cases: list[tuple[GameState, LegalActions]],
    rounds: int,
) -> list[float]:
    """对给定局面轮转测量若干次决策，返回每次决策的耗时（毫秒）。"""
    if rounds <= 0:
        raise AssertionError("测量轮数必须为正")
    if not cases:
        raise AssertionError("测量至少需要一个局面")
    durations: list[float] = []
    for index in range(rounds):
        state, legal = cases[index % len(cases)]
        started = time.perf_counter()
        distribution = strategy.action_distribution(state, legal)
        durations.append((time.perf_counter() - started) * 1000.0)
        total_weight = sum(item_weight for _, item_weight in distribution)
        if not distribution or abs(total_weight - 1.0) > 1e-9:
            raise AssertionError("策略分布不合法，本次测量结果不可用")
    return durations
