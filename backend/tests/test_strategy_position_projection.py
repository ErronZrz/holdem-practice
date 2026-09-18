"""位置与公开行动线投影的回归测试。"""

import inspect

import pytest
from pydantic import ValidationError

from app.poker.actions import Action, ActionType
from app.poker.engine import PokerEngine
from app.poker.state import GameState, PlayerState, Street
from app.strategy import position_projection
from app.strategy.position_projection import (
    POSITION_ACTION_TOKENS,
    POSITION_BASIS,
    POSITION_PROJECTION_FIELDS,
    POSITION_PROJECTION_VERSION,
    POSITION_STREETS,
    PositionContractError,
    PositionEncodingError,
    PositionProjection,
    PositionProjectionError,
    PublicAction,
    StreetActionLine,
    blind_relative_seats,
    build_position_projection,
    build_public_actions,
    project_position_for_actor,
    relative_seat,
    street_action_order,
)

from .helpers import cards


def _rec(street: str, seat: int, action: str, amount: int = 0) -> dict[str, object]:
    return {"street": street, "seat": seat, "action": action, "amount": amount}


def _blinds(
    num_players: int, button: int, small: int = 10, big: int = 20
) -> list[dict[str, object]]:
    """按人数规则给出翻前两条盲注记录（相对座位换算回绝对座位）。"""
    relative_small, relative_big = blind_relative_seats(num_players)
    return [
        _rec("preflop", (button + relative_small) % num_players, "small_blind", small),
        _rec("preflop", (button + relative_big) % num_players, "big_blind", big),
    ]


def _minimal_line(num_players: int, button: int) -> list[dict[str, object]]:
    """任何人数下都可编码的最小行动线：两条盲注加首个行动者弃牌。"""
    first_seat = (button + street_action_order(num_players, "preflop")[0]) % num_players
    return [*_blinds(num_players, button), _rec("preflop", first_seat, "fold")]


def _project(**overrides: object) -> PositionProjection:
    kwargs: dict[str, object] = {
        "player_count": 6,
        "button": 0,
        "current_seat": 3,
        "street": "preflop",
        "history": _minimal_line(6, 0),
    }
    kwargs.update(overrides)
    return build_position_projection(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------- 契约与字段


def test_projection_field_set_is_exactly_the_contract() -> None:
    assert tuple(PositionProjection.model_fields) == POSITION_PROJECTION_FIELDS
    assert len(POSITION_PROJECTION_FIELDS) == 7


def test_street_action_line_field_set_is_exactly_the_contract() -> None:
    assert tuple(StreetActionLine.model_fields) == ("street", "tokens")


def test_projection_carries_no_seat_amount_or_hidden_fields() -> None:
    forbidden = {"seat", "button", "amount", "hole_cards", "board", "pot", "stack", "seed"}
    assert forbidden.isdisjoint(PositionProjection.model_fields)
    # 绝对座位与金额只允许存在于输入侧记录，不进入投影。
    assert set(PublicAction.model_fields) == {"street", "seat", "action", "amount"}


def test_projection_rejects_unregistered_fields() -> None:
    with pytest.raises(ValidationError):
        PositionProjection(
            player_count=6,
            street="preflop",
            relative_actor=0,
            action_order=(0, 1, 2, 3, 4, 5),
            players_to_act_before=0,
            players_to_act_after=5,
            public_action_line=(),
            board="As Kd",
        )


def test_projection_is_frozen() -> None:
    projection = _project()
    with pytest.raises(ValidationError):
        projection.player_count = 5  # type: ignore[misc]


def test_position_error_types_are_distinct() -> None:
    assert issubclass(PositionContractError, PositionProjectionError)
    assert issubclass(PositionEncodingError, PositionProjectionError)
    assert not issubclass(PositionContractError, PositionEncodingError)
    assert not issubclass(PositionEncodingError, PositionContractError)


def test_contract_constants_are_frozen() -> None:
    assert POSITION_PROJECTION_VERSION == "position-line.v1"
    assert POSITION_BASIS == "relative-button"
    assert POSITION_STREETS == ("preflop", "flop", "turn", "river")
    assert POSITION_ACTION_TOKENS["small_blind"] == "sb"
    assert POSITION_ACTION_TOKENS["raise"] == "r"


# ---------------------------------------------------------------- 相对座位与顺序


@pytest.mark.parametrize("num_players", range(2, 10))
@pytest.mark.parametrize("offset", range(3))
def test_relative_actor_is_measured_from_the_button(num_players: int, offset: int) -> None:
    button = offset % num_players
    seat = (button + num_players - 1) % num_players
    projection = build_position_projection(
        player_count=num_players,
        button=button,
        current_seat=seat,
        street="preflop",
        history=_minimal_line(num_players, button),
    )
    assert projection.relative_actor == relative_seat(num_players, button, seat)
    assert projection.relative_actor == num_players - 1


@pytest.mark.parametrize("num_players", range(2, 10))
def test_action_order_matches_the_blind_rules(num_players: int) -> None:
    expected = tuple((3 + step) % num_players for step in range(num_players))
    if num_players == 2:
        assert street_action_order(num_players, "preflop") == (0, 1)
        assert street_action_order(num_players, "flop") == (1, 0)
        assert blind_relative_seats(num_players) == (0, 1)
    else:
        assert street_action_order(num_players, "preflop") == expected
        assert blind_relative_seats(num_players) == (1, 2)
    assert street_action_order(num_players, "flop") == tuple(
        (1 + step) % num_players for step in range(num_players)
    )
    assert len(street_action_order(num_players, "river")) == num_players


@pytest.mark.parametrize("num_players", range(2, 10))
@pytest.mark.parametrize("street", POSITION_STREETS)
def test_players_to_act_counts_are_positional(num_players: int, street: str) -> None:
    for seat in range(num_players):
        projection = build_position_projection(
            player_count=num_players,
            button=0,
            current_seat=seat,
            street=street,
            history=_minimal_line(num_players, 0),
        )
        order = street_action_order(num_players, street)
        assert projection.players_to_act_before == order.index(projection.relative_actor)
        assert projection.players_to_act_before + projection.players_to_act_after == num_players - 1


def test_action_order_starts_at_the_engine_first_actor() -> None:
    for num_players in range(2, 10):
        engine = PokerEngine(
            num_players=num_players, small_blind=10, big_blind=20, starting_stack=1000, seed=3
        )
        engine.start_hand()
        state = engine.snapshot()
        relative_first = relative_seat(num_players, state.button, state.current_seat)
        assert street_action_order(num_players, "preflop")[0] == relative_first


# ---------------------------------------------------------------- 动作线编码


def test_action_line_is_segmented_by_street() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "fold"),
        _rec("flop", 2, "check"),
        _rec("flop", 4, "check"),
        _rec("turn", 2, "bet", 20),
    ]
    projection = build_position_projection(
        player_count=6, button=0, current_seat=3, street="turn", history=history
    )
    assert tuple(segment.street for segment in projection.public_action_line) == (
        "preflop",
        "flop",
        "turn",
    )
    assert projection.public_action_line[0].tokens == ("sb@1", "bb@2", "f@3")
    assert projection.public_action_line[1].tokens == ("x@2", "x@4")
    assert projection.public_action_line[2].tokens == ("b@2",)


def test_action_line_is_deterministic_and_amount_free() -> None:
    history = _minimal_line(6, 0)
    first = _project(history=history)
    second = _project(history=[dict(record) for record in history])
    assert first == second
    assert "amount" not in str(first.model_dump())


def test_bet_and_raise_keep_their_action_kind() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "raise", 60),
        _rec("preflop", 4, "fold"),
    ]
    projection = build_position_projection(
        player_count=6, button=0, current_seat=3, street="preflop", history=history
    )
    assert projection.public_action_line[0].tokens == ("sb@1", "bb@2", "r@3", "f@4")


def test_big_blind_may_act_after_posting() -> None:
    history = [*_blinds(6, 0), _rec("preflop", 3, "call", 20), _rec("preflop", 2, "check")]
    projection = build_position_projection(
        player_count=6, button=0, current_seat=3, street="preflop", history=history
    )
    assert projection.public_action_line[0].tokens == ("sb@1", "bb@2", "c@3", "x@2")


# ---------------------------------------------------------------- 单挑盲位特例


def test_heads_up_button_posts_the_small_blind() -> None:
    history = [
        _rec("preflop", 0, "small_blind", 10),
        _rec("preflop", 1, "big_blind", 20),
        _rec("preflop", 0, "call", 10),
        _rec("preflop", 1, "check"),
    ]
    projection = build_position_projection(
        player_count=2, button=0, current_seat=1, street="flop", history=history
    )
    assert blind_relative_seats(2) == (0, 1)
    assert projection.action_order == (1, 0)
    assert projection.public_action_line[0].tokens == ("sb@0", "bb@1", "c@0", "x@1")


def test_heads_up_real_hand_matches_the_engine() -> None:
    engine = PokerEngine(num_players=2, small_blind=10, big_blind=20, starting_stack=1000, seed=7)
    engine.start_hand()
    assert engine.current_seat == engine.button
    engine.apply_action(Action(ActionType.CALL))
    engine.apply_action(Action(ActionType.CHECK))
    state = engine.snapshot()
    assert state.street is Street.FLOP
    projection = project_position_for_actor(state, engine.history)
    assert projection.player_count == 2
    assert projection.street == "flop"
    assert projection.public_action_line[0].tokens == ("sb@0", "bb@1", "c@0", "x@1")
    assert projection.action_order == street_action_order(2, "flop")
    assert projection.relative_actor == relative_seat(2, state.button, state.current_seat)


def test_real_six_player_hand_projects_relative_seats() -> None:
    engine = PokerEngine(num_players=6, small_blind=10, big_blind=20, starting_stack=1000, seed=11)
    engine.start_hand()
    assert engine.button == 0
    for _ in range(5):
        engine.apply_action(Action(ActionType.CALL))
    engine.apply_action(Action(ActionType.CHECK))
    state = engine.snapshot()
    assert state.street is Street.FLOP
    projection = project_position_for_actor(state, engine.history)
    assert projection.public_action_line[0].tokens == (
        "sb@1",
        "bb@2",
        "c@3",
        "c@4",
        "c@5",
        "c@0",
        "c@1",
        "x@2",
    )
    assert projection.action_order == street_action_order(6, "flop")
    assert projection.relative_actor == relative_seat(6, state.button, state.current_seat)


# ---------------------------------------------------------------- 绝对座位剥离


@pytest.mark.parametrize("shift", range(1, 6))
def test_shifting_every_absolute_seat_leaves_the_projection_unchanged(shift: int) -> None:
    base = _project()
    shifted_history = [
        {**record, "seat": (int(record["seat"]) + shift) % 6}  # type: ignore[arg-type]
        for record in _minimal_line(6, 0)
    ]
    shifted = build_position_projection(
        player_count=6,
        button=shift % 6,
        current_seat=(3 + shift) % 6,
        street="preflop",
        history=shifted_history,
    )
    assert shifted == base
    assert shifted.model_dump() == base.model_dump()


def test_projection_never_exposes_absolute_seats() -> None:
    projection = _project(button=4, current_seat=1, history=_minimal_line(6, 4))
    assert set(PositionProjection.model_fields) == set(POSITION_PROJECTION_FIELDS)
    assert "button" not in PositionProjection.model_fields
    assert projection.relative_actor == relative_seat(6, 4, 1) == 3


# ---------------------------------------------------------------- 信息边界


def _state(
    num_players: int,
    *,
    button: int = 0,
    current_seat: int = 0,
    street: Street = Street.PREFLOP,
    board: str = "",
    opponent_holes: str = "2c 3d",
) -> GameState:
    """构造行动者视角的快照；对手底牌与公共牌只用于验证「不读取」。"""
    players = [PlayerState(seat=0, name="p0", hole_cards=cards("As Kd"), stack=1000)]
    for seat in range(1, num_players):
        players.append(
            PlayerState(seat=seat, name=f"p{seat}", hole_cards=cards(opponent_holes), stack=1000)
        )
    return GameState(
        street=street,
        board=tuple(cards(board)) if board else (),
        pot=15,
        current_seat=current_seat,
        button=button,
        hand_over=False,
        players=tuple(players),
    )


def test_projection_ignores_opponent_hole_cards_and_board() -> None:
    history = _minimal_line(6, 0)
    plain = project_position_for_actor(
        _state(6, button=0, current_seat=3, street=Street.FLOP), history
    )
    masked = project_position_for_actor(
        _state(
            6,
            button=0,
            current_seat=3,
            street=Street.FLOP,
            board="Ah Qh 7s 2d",
            opponent_holes="9s 9h",
        ),
        history,
    )
    assert masked == plain


def test_game_state_entry_rejects_terminal_street() -> None:
    with pytest.raises(PositionEncodingError):
        project_position_for_actor(
            _state(6, current_seat=0, street=Street.SHOWDOWN, board="Ah Qh 7s 2d 3c"),
            _minimal_line(6, 0),
        )


# ---------------------------------------------------------------- 不可编码与不完整


def test_empty_action_line_fails() -> None:
    with pytest.raises(PositionEncodingError):
        _project(history=[])


def test_action_line_must_start_at_preflop() -> None:
    history = [_rec("flop", 2, "check"), _rec("flop", 3, "check")]
    with pytest.raises(PositionEncodingError, match="必须自翻前开始"):
        _project(history=history)


def test_unknown_street_in_record_fails() -> None:
    history = [*_blinds(6, 0), _rec("riverb", 3, "check")]
    with pytest.raises(PositionEncodingError, match="未知街"):
        _project(history=history)


def test_duplicated_street_fails() -> None:
    history = [
        *_blinds(6, 0),
        _rec("flop", 2, "check"),
        _rec("preflop", 3, "fold"),
    ]
    with pytest.raises(PositionEncodingError, match="重复的街"):
        _project(history=history)


def test_street_regression_fails() -> None:
    history = [
        *_blinds(6, 0),
        _rec("turn", 2, "check"),
        _rec("flop", 3, "check"),
    ]
    with pytest.raises(PositionEncodingError, match="街序回退"):
        _project(history=history)


def test_current_street_earlier_than_last_action_fails() -> None:
    history = [*_blinds(6, 0), _rec("flop", 2, "check")]
    with pytest.raises(PositionEncodingError, match="早于最后一段动作"):
        _project(history=history, street="preflop")


def test_missing_blinds_fails() -> None:
    with pytest.raises(PositionEncodingError, match="缺少盲注记录"):
        _project(history=[_rec("preflop", 3, "fold")])


def test_blind_structure_must_match_the_rules() -> None:
    history = [
        _rec("preflop", 2, "small_blind", 10),
        _rec("preflop", 3, "big_blind", 20),
    ]
    with pytest.raises(PositionEncodingError, match="盲注结构与规则不符"):
        _project(history=history)


def test_unknown_action_fails() -> None:
    history = [*_blinds(6, 0), _rec("preflop", 3, "all_in")]
    with pytest.raises(PositionEncodingError, match="不在公开动作线词表内"):
        _project(history=history)


def test_forced_blind_must_not_repeat_mid_street() -> None:
    history = [*_blinds(6, 0), _rec("preflop", 3, "small_blind", 10)]
    with pytest.raises(PositionEncodingError, match="强制盲注只允许出现在翻前段开头"):
        _project(history=history)


def test_out_of_range_seat_fails() -> None:
    history = [*_blinds(6, 0), _rec("preflop", 9, "fold")]
    with pytest.raises(PositionEncodingError, match="越界"):
        _project(history=history)


def test_folded_seat_cannot_act_again() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "fold"),
        _rec("flop", 3, "check"),
    ]
    with pytest.raises(PositionEncodingError, match="已弃牌"):
        _project(history=history, street="flop")


def test_repeat_action_without_reopen_fails() -> None:
    history = [*_blinds(6, 0), _rec("preflop", 3, "call", 20), _rec("preflop", 3, "call", 20)]
    with pytest.raises(PositionEncodingError, match="重复行动"):
        _project(history=history)


def test_repeat_action_after_a_raise_is_allowed() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "call", 20),
        _rec("preflop", 4, "raise", 40),
        _rec("preflop", 3, "call", 20),
    ]
    projection = _project(history=history)
    assert projection.public_action_line[0].tokens == ("sb@1", "bb@2", "c@3", "r@4", "c@3")


def test_short_all_in_raise_is_not_encodable() -> None:
    history = [*_blinds(6, 0), _rec("preflop", 3, "raise", 30)]
    with pytest.raises(PositionEncodingError, match="短码全下加注"):
        _project(history=history)


def test_terminal_street_has_no_actor() -> None:
    with pytest.raises(PositionEncodingError, match="没有当前行动者"):
        _project(street="showdown")


# ---------------------------------------------------------------- 契约违规


@pytest.mark.parametrize(
    "overrides",
    [
        {"player_count": "6"},
        {"button": True},
        {"current_seat": 1.5},
        {"street": 1},
    ],
)
def test_structural_illegal_arguments_raise_contract_error(overrides: dict[str, object]) -> None:
    with pytest.raises(PositionContractError):
        _project(**overrides)


def test_out_of_range_button_raises_contract_error() -> None:
    with pytest.raises(PositionContractError):
        _project(button=6)
    with pytest.raises(PositionContractError):
        _project(current_seat=-1)


@pytest.mark.parametrize(
    "entry",
    [
        "not-a-mapping",
        {"street": "preflop", "seat": 1},
        {"street": "preflop", "seat": True, "action": "fold", "amount": 0},
        {"street": 1, "seat": 1, "action": "fold", "amount": 0},
        {"street": "preflop", "seat": 1, "action": 2, "amount": 0},
        {"street": "preflop", "seat": 1, "action": "fold", "amount": "10"},
    ],
)
def test_malformed_history_entries_raise_contract_error(entry: object) -> None:
    with pytest.raises(PositionContractError):
        build_public_actions([entry])  # type: ignore[list-item]


def test_build_public_actions_returns_contract_records() -> None:
    records = build_public_actions(_minimal_line(6, 0))
    assert all(isinstance(record, PublicAction) for record in records)
    assert records[0].action == "small_blind"
    assert records[0].amount == 10


def test_public_action_records_are_accepted_directly() -> None:
    records = build_public_actions(_minimal_line(6, 0))
    projection = build_position_projection(
        player_count=6, button=0, current_seat=3, street="preflop", history=records
    )
    assert projection.public_action_line[0].tokens == ("sb@1", "bb@2", "f@3")


# ---------------------------------------------------------------- 纯度与不写回


def test_projection_does_not_mutate_the_input_history() -> None:
    history = _minimal_line(6, 0)
    snapshot = [dict(record) for record in history]
    build_position_projection(
        player_count=6, button=0, current_seat=3, street="preflop", history=history
    )
    assert history == snapshot


def test_projection_round_trips_through_json() -> None:
    projection = _project()
    assert PositionProjection.model_validate(projection.model_dump()) == projection


def test_module_never_imports_storage_or_engine() -> None:
    source = inspect.getsource(position_projection)
    assert "app.storage" not in source
    assert "app.poker.engine" not in source
    assert "app.poker.actions" not in source
