"""德州扑克规则引擎：发牌、下注轮、街流转、摊牌与结算。

纯 Python、无 Web 依赖，按 N 人设计。筹码统一使用整数单位。
"""

import random

from .actions import Action, ActionType, IllegalActionError, LegalActions
from .cards import Card
from .deck import Deck
from .evaluator import best_five, evaluate
from .state import GameState, PlayerState, Street


class PokerEngine:
    """规则引擎。生命周期：start_hand() -> 循环 apply_action() -> hand_over。"""

    def __init__(
        self,
        num_players: int,
        small_blind: int,
        big_blind: int,
        starting_stack: int,
        seed: int | None = None,
    ) -> None:
        if num_players < 2:
            raise ValueError("至少需要 2 名玩家")
        if not (0 < small_blind <= big_blind):
            raise ValueError("盲注配置不合法")
        self.num_players = num_players
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.starting_stack = starting_stack
        self._rng = random.Random(seed)
        self.deck = Deck(self._rng)
        self.players = [
            PlayerState(seat=i, name=f"玩家{i}", stack=starting_stack) for i in range(num_players)
        ]
        # 首手庄位为最后一个座位，之后每手顺时针轮转。
        self.button = num_players - 1
        self.street = Street.PREFLOP
        self.board: list[Card] = []
        self.current_bet = 0
        self.min_raise = big_blind
        self.current_seat = 0
        self.hand_over = True
        self.winners: list[int] = []
        self.last_net: dict[int, int] = {}
        self.history: list[dict[str, object]] = []
        self._hand_start_stacks: list[int] = []
        # 摊牌结算的展示明细：各玩家最佳 5 张牌、各边池归属（仅摊牌时填充）。
        self.showdown_hands: dict[int, list[Card]] = {}
        self.pot_results: list[dict[str, object]] = []

    # ------------------------------------------------------------------ 对外只读

    @property
    def pot(self) -> int:
        """当前底池总额（所有玩家整手累计投入之和）。"""
        return sum(p.total_committed for p in self.players)

    @property
    def current_player(self) -> PlayerState:
        return self.players[self.current_seat]

    def snapshot(self) -> GameState:
        """生成只读快照，供策略等外部模块使用。"""
        players = tuple(
            PlayerState(
                seat=p.seat,
                name=p.name,
                stack=p.stack,
                hole_cards=list(p.hole_cards),
                folded=p.folded,
                all_in=p.all_in,
                street_bet=p.street_bet,
                total_committed=p.total_committed,
                has_acted_since_full_raise=p.has_acted_since_full_raise,
            )
            for p in self.players
        )
        return GameState(
            street=self.street,
            board=tuple(self.board),
            pot=self.pot,
            current_seat=self.current_seat,
            button=self.button,
            hand_over=self.hand_over,
            players=players,
        )

    # ------------------------------------------------------------------ 一手牌

    def _reset_players(self) -> None:
        """重置每手牌的状态，并为筹码清零的玩家自动补码。"""
        for p in self.players:
            p.hole_cards = []
            p.folded = False
            p.all_in = False
            p.street_bet = 0
            p.total_committed = 0
            p.has_acted_since_full_raise = False
            if p.stack <= 0:
                p.stack = self.starting_stack

    def start_hand(self) -> None:
        """开始一手新牌：轮转庄位、发底牌、下盲注并确定首个行动者。"""
        self.button = (self.button + 1) % self.num_players
        self._reset_players()
        self.board = []
        self.street = Street.PREFLOP
        self.hand_over = False
        self.winners = []
        self.last_net = {}
        self.history = []
        self._hand_start_stacks = [p.stack for p in self.players]
        self.showdown_hands = {}
        self.pot_results = []

        self.deck.shuffle()
        for _ in range(2):
            for p in self.players:
                p.hole_cards.extend(self.deck.draw(1))

        self._post_blinds()
        self.current_bet = max(p.street_bet for p in self.players)
        self.min_raise = self.big_blind
        self._resolve_start()

    def apply_action(self, action: Action) -> None:
        """执行一次动作，自动推进街/结算。非法动作抛出 IllegalActionError。"""
        if self.hand_over:
            raise IllegalActionError("本手牌已结束")
        self._validate(action)
        self._apply(action)
        self._resolve_after_action()

    def legal_actions(self) -> LegalActions:
        """当前玩家的合法动作集合。"""
        p = self.current_player
        if self.hand_over or p.folded or p.all_in:
            return LegalActions(False, False, False, 0, False, 0, 0, False, 0, 0)

        to_call = self.current_bet - p.street_bet
        all_in_total = p.street_bet + p.stack

        can_check = to_call == 0
        can_call = to_call > 0
        can_bet = False
        can_raise = False
        min_bet = 0
        max_bet = 0
        min_raise_to = 0
        max_raise_to = 0

        if p.stack > 0:
            if to_call == 0 and self.street != Street.PREFLOP:
                # 翻牌后无人下注时，第一个投入是下注。
                can_bet = True
                min_bet = min(self.big_blind, all_in_total)
                max_bet = all_in_total
            elif all_in_total > self.current_bet and (
                to_call == 0 or not p.has_acted_since_full_raise
            ):
                # 其余可继续投入的情况（翻牌前大盲加注、翻牌后面对下注再加注）都是加注。
                can_raise = True
                full_min = self.current_bet + self.min_raise
                min_raise_to = full_min if all_in_total >= full_min else all_in_total
                max_raise_to = all_in_total

        return LegalActions(
            # 面对下注时才可弃牌；可免费过牌时不提供弃牌（过牌是严格更优的免费选项）。
            can_fold=to_call > 0,
            can_check=can_check,
            can_call=can_call,
            call_amount=to_call,
            can_bet=can_bet,
            min_bet=min_bet,
            max_bet=max_bet,
            can_raise=can_raise,
            min_raise_to=min_raise_to,
            max_raise_to=max_raise_to,
        )

    # ------------------------------------------------------------------ 盲注与行动顺序

    def _blind_seats(self) -> tuple[int, int]:
        if self.num_players == 2:
            # 单挑时庄位即小盲。
            return self.button, (self.button + 1) % 2
        return (self.button + 1) % self.num_players, (self.button + 2) % self.num_players

    def _preflop_first(self) -> int:
        if self.num_players == 2:
            return self.button
        return (self._blind_seats()[1] + 1) % self.num_players

    def _post_blinds(self) -> None:
        sb, bb = self._blind_seats()
        self._post_blind(sb, self.small_blind, "small_blind")
        self._post_blind(bb, self.big_blind, "big_blind")

    def _post_blind(self, seat: int, amount: int, label: str) -> None:
        p = self.players[seat]
        commit = min(amount, p.stack)
        p.stack -= commit
        p.street_bet += commit
        p.total_committed += commit
        if p.stack == 0:
            p.all_in = True
        self._record(seat, label, commit)

    def _first_active_from(self, start_seat: int) -> int:
        """从 start_seat 起（含）顺时针找第一个可行动玩家。"""
        for step in range(self.num_players):
            seat = (start_seat + step) % self.num_players
            p = self.players[seat]
            if not p.folded and not p.all_in:
                return seat
        return start_seat

    def _next_active_after(self, seat: int) -> int:
        return self._first_active_from((seat + 1) % self.num_players)

    def _num_can_bet(self) -> int:
        return sum(1 for p in self.players if not p.folded and not p.all_in)

    def _num_not_folded(self) -> int:
        return sum(1 for p in self.players if not p.folded)

    def _betting_round_complete(self) -> bool:
        for p in self.players:
            if p.folded or p.all_in:
                continue
            if p.street_bet != self.current_bet:
                return False
            if not p.has_acted_since_full_raise:
                return False
        return True

    # ------------------------------------------------------------------ 动作校验与执行

    def _validate(self, action: Action) -> None:
        legal = self.legal_actions()
        if action.type == ActionType.FOLD:
            if not legal.can_fold:
                raise IllegalActionError("当前无法弃牌")
        elif action.type == ActionType.CHECK:
            if not legal.can_check:
                raise IllegalActionError("当前无法过牌")
        elif action.type == ActionType.CALL:
            if not legal.can_call:
                raise IllegalActionError("当前无法跟注")
        elif action.type == ActionType.BET:
            if not legal.can_bet:
                raise IllegalActionError("当前无法下注")
            if not legal.min_bet <= action.amount <= legal.max_bet:
                raise IllegalActionError("下注金额不合法")
        elif action.type == ActionType.RAISE:
            if not legal.can_raise:
                raise IllegalActionError("当前无法加注")
            if not legal.min_raise_to <= action.amount <= legal.max_raise_to:
                raise IllegalActionError("加注金额不合法")
        else:
            raise IllegalActionError("未知动作类型")

    def _apply(self, action: Action) -> None:
        p = self.current_player
        if action.type == ActionType.FOLD:
            p.folded = True
            self._record(p.seat, action.type, 0)
        elif action.type == ActionType.CHECK:
            p.has_acted_since_full_raise = True
            self._record(p.seat, action.type, 0)
        elif action.type == ActionType.CALL:
            commit = min(self.current_bet - p.street_bet, p.stack)
            p.street_bet += commit
            p.total_committed += commit
            p.stack -= commit
            p.has_acted_since_full_raise = True
            if p.stack == 0:
                p.all_in = True
            self._record(p.seat, action.type, commit)
        elif action.type == ActionType.BET:
            commit = min(action.amount, p.stack)
            p.street_bet += commit
            p.total_committed += commit
            p.stack -= commit
            self.current_bet = p.street_bet
            self.min_raise = commit
            self._reopen_after_full_raise(p)
            if p.stack == 0:
                p.all_in = True
            self._record(p.seat, action.type, commit)
        elif action.type == ActionType.RAISE:
            commit = action.amount - p.street_bet
            p.street_bet = action.amount
            p.total_committed += commit
            p.stack -= commit
            increment = action.amount - self.current_bet
            if increment >= self.min_raise:
                self.current_bet = action.amount
                self.min_raise = increment
                self._reopen_after_full_raise(p)
            else:
                # 短码全下加注，不重开其他玩家已结束的行动。
                self.current_bet = action.amount
            if p.stack == 0:
                p.all_in = True
            self._record(p.seat, action.type, commit)

    def _reopen_after_full_raise(self, actor: PlayerState) -> None:
        for p in self.players:
            p.has_acted_since_full_raise = False
        actor.has_acted_since_full_raise = True

    # ------------------------------------------------------------------ 推进与结算

    def _resolve_start(self) -> None:
        if self._num_not_folded() <= 1:
            self._end_hand(showdown=False)
        elif self._num_can_bet() == 0:
            # 无人可行动（全员全下），直接发完进入摊牌。
            self._run_out()
        else:
            # 即使只剩一人有筹码，仍需给其跟注/弃牌的决策机会。
            self.current_seat = self._first_active_from(self._preflop_first())

    def _resolve_after_action(self) -> None:
        if self.hand_over:
            return
        if self._num_not_folded() <= 1:
            self._end_hand(showdown=False)
            return
        if self._betting_round_complete():
            if self.street == Street.RIVER:
                self._end_hand(showdown=True)
            else:
                self._advance_street()
                if not self.hand_over and self._num_can_bet() <= 1:
                    self._run_out()
        else:
            self.current_seat = self._next_active_after(self.current_seat)

    def _advance_street(self) -> None:
        self.street = Street(self.street + 1)
        if self.street == Street.FLOP:
            self.board.extend(self.deck.draw(3))
        else:
            self.board.extend(self.deck.draw(1))
        self.current_bet = 0
        self.min_raise = self.big_blind
        for p in self.players:
            p.street_bet = 0
            p.has_acted_since_full_raise = False
        self.current_seat = self._first_active_from((self.button + 1) % self.num_players)

    def _run_out(self) -> None:
        """无人可继续下注时，直接发完剩余公共牌进入摊牌。"""
        while self.street < Street.RIVER:
            self.street = Street(self.street + 1)
            if self.street == Street.FLOP:
                self.board.extend(self.deck.draw(3))
            else:
                self.board.extend(self.deck.draw(1))
        self._end_hand(showdown=True)

    def _end_hand(self, showdown: bool) -> None:
        if showdown:
            self.street = Street.SHOWDOWN
            self._settle_showdown()
        else:
            winner = next(i for i, p in enumerate(self.players) if not p.folded)
            self.players[winner].stack += self.pot
            self.winners = [winner]
        self._record_last_net()
        self.hand_over = True

    def _settle_showdown(self) -> None:
        contribs = [p.total_committed for p in self.players]
        pots: list[tuple[int, list[int]]] = []
        returns = [0] * self.num_players

        # 按所有玩家的投入层级切分边池；某层若无人可争夺，则整层退还给投入者本人。
        levels = sorted({c for c in contribs if c > 0})
        prev = 0
        for level in levels:
            contributors = [i for i in range(self.num_players) if contribs[i] >= level]
            eligible = [i for i in contributors if not self.players[i].folded]
            amount = (level - prev) * len(contributors)
            if amount > 0:
                if eligible:
                    pots.append((amount, eligible))
                else:
                    share = level - prev
                    for i in contributors:
                        returns[i] += share
            prev = level

        for i in range(self.num_players):
            self.players[i].stack += returns[i]

        ranks = {
            i: evaluate(self.players[i].hole_cards + self.board)
            for i in range(self.num_players)
            if not self.players[i].folded
        }
        self.showdown_hands = {
            i: best_five(self.players[i].hole_cards + self.board)
            for i in range(self.num_players)
            if not self.players[i].folded
        }
        winners: set[int] = set()
        self.pot_results = []
        for amount, eligible in pots:
            best = max(ranks[i] for i in eligible)
            pot_winners = [i for i in eligible if ranks[i] == best]
            ordered = sorted(pot_winners)
            share = amount // len(pot_winners)
            remainder = amount % len(pot_winners)
            shares = {w: share + (1 if idx < remainder else 0) for idx, w in enumerate(ordered)}
            for w in pot_winners:
                self.players[w].stack += share
                winners.add(w)
            # 余数筹码按座位号升序依次分配，保证确定性。
            for w in ordered[:remainder]:
                self.players[w].stack += 1
            self.pot_results.append({"amount": amount, "winners": ordered, "shares": shares})
        self.winners = sorted(winners)

    def _record_last_net(self) -> None:
        self.last_net = {
            p.seat: self.players[p.seat].stack - self._hand_start_stacks[p.seat]
            for p in self.players
        }

    def _record(self, seat: int, action: object, amount: int) -> None:
        action_name = action.value if isinstance(action, ActionType) else str(action)
        self.history.append(
            {
                "street": self.street.name.lower(),
                "seat": seat,
                "action": action_name,
                "amount": amount,
            }
        )
