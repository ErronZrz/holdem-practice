"""基于公开行动线的范围假设契约的回归测试。"""

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.analysis import reference_identity
from app.poker.state import GameState, PlayerState, Street
from app.strategy import range_assumption
from app.strategy.position_projection import (
    PositionProjection,
    blind_relative_seats,
    build_position_projection,
    project_position_for_actor,
)
from app.strategy.range_assumption import (
    DEFAULT_RANGE_PROFILE_IDENTIFIER,
    HAND_CLASS_ORDER,
    OPPONENT_RANGE_FIELDS,
    RANGE_ASSUMPTION_FIELDS,
    RANGE_ASSUMPTION_SCHEMA_VERSION,
    RANGE_CONTRAST_COVERAGE,
    RANGE_HAND_CLASS_COUNT,
    RANGE_LIMITATION_NO_BOARD_NARROWING,
    RANGE_LIMITATION_NOT_A_SOLVER,
    RANGE_LIMITATIONS,
    RANGE_PROFILE_FIELDS,
    RANGE_ROLE_AGGRESSOR,
    RANGE_ROLE_BLIND,
    RANGE_ROLE_CALLER,
    RANGE_ROLE_FOLDED,
    RANGE_ROLE_UNACTED,
    RANGE_ROLES,
    RANGE_SOURCE_DECLARED_ASSUMPTION,
    OpponentRange,
    OutOfProfileError,
    RangeAssumption,
    RangeAssumptionError,
    RangeContractError,
    RangeProfile,
    UnknownRangeProfileError,
    assign_opponent_roles,
    build_range_assumption,
    known_profile_identifiers,
    profile_for,
    register_range_profile,
    weights_for_class_count,
)

from .helpers import cards


def _rec(street: str, seat: int, action: str, amount: int = 0) -> dict[str, object]:
    return {"street": street, "seat": seat, "action": action, "amount": amount}


def _blinds(num_players: int, button: int = 0) -> list[dict[str, object]]:
    relative_small, relative_big = blind_relative_seats(num_players)
    return [
        _rec("preflop", (button + relative_small) % num_players, "small_blind", 10),
        _rec("preflop", (button + relative_big) % num_players, "big_blind", 20),
    ]


def _project(
    num_players: int = 6,
    *,
    button: int = 0,
    current_seat: int = 2,
    street: str = "preflop",
    history: list[dict[str, object]] | None = None,
) -> PositionProjection:
    if history is None:
        first = (button + 3) % num_players
        history = [*_blinds(num_players, button), _rec("preflop", first, "fold")]
    return build_position_projection(
        player_count=num_players,
        button=button,
        current_seat=current_seat,
        street=street,
        history=history,
    )


def _role_map(projection: PositionProjection) -> dict[int, str]:
    return dict(assign_opponent_roles(projection))


def _state(
    num_players: int,
    *,
    button: int = 0,
    current_seat: int = 0,
    board: str = "",
    opponent_holes: str = "2c 3d",
) -> GameState:
    """构造行动者为座位 0 的快照；对手底牌与公共牌只用于验证「不读取」。"""
    players = [PlayerState(seat=0, name="p0", hole_cards=cards("As Kd"), stack=1000)]
    for seat in range(1, num_players):
        players.append(
            PlayerState(seat=seat, name=f"p{seat}", hole_cards=cards(opponent_holes), stack=1000)
        )
    return GameState(
        street=Street.PREFLOP,
        board=tuple(cards(board)) if board else (),
        pot=15,
        current_seat=current_seat,
        button=button,
        hand_over=False,
        players=tuple(players),
    )


# ---------------------------------------------------------------- 契约与字段


def test_hand_class_order_is_169_unique_and_bounded() -> None:
    assert len(HAND_CLASS_ORDER) == RANGE_HAND_CLASS_COUNT == 169
    assert len(set(HAND_CLASS_ORDER)) == 169
    assert HAND_CLASS_ORDER[0] == "AA"
    assert HAND_CLASS_ORDER[-1] == "32o"
    assert HAND_CLASS_ORDER[13:15] == ("AKs", "AKo")


def test_profile_field_set_is_exactly_the_contract() -> None:
    assert tuple(RangeProfile.model_fields) == RANGE_PROFILE_FIELDS
    assert len(RANGE_PROFILE_FIELDS) == 9


def test_opponent_range_field_set_is_exactly_the_contract() -> None:
    assert tuple(OpponentRange.model_fields) == OPPONENT_RANGE_FIELDS
    assert len(OPPONENT_RANGE_FIELDS) == 5


def test_assumption_field_set_is_exactly_the_contract() -> None:
    assert tuple(RangeAssumption.model_fields) == RANGE_ASSUMPTION_FIELDS
    assert len(RANGE_ASSUMPTION_FIELDS) == 8


def test_role_class_count_fields_cover_every_role() -> None:
    mapping = range_assumption.RANGE_ROLE_CLASS_COUNT_FIELDS
    assert set(mapping) == set(RANGE_ROLES)
    assert set(mapping.values()) <= set(RANGE_PROFILE_FIELDS)


def test_models_reject_unregistered_fields() -> None:
    with pytest.raises(ValidationError):
        RangeProfile(
            profile_identifier="x@1",
            source=RANGE_SOURCE_DECLARED_ASSUMPTION,
            basis="basis",
            aggressor_class_count=1,
            caller_class_count=1,
            blind_class_count=1,
            unacted_class_count=1,
            folded_class_count=0,
            max_aggressive_actions_per_street=1,
            board="As Kd",
        )


def test_assumption_is_frozen() -> None:
    assumption = build_range_assumption(projection=_project())
    with pytest.raises(ValidationError):
        assumption.player_count = 5  # type: ignore[misc]


def test_error_types_are_distinct() -> None:
    assert issubclass(RangeContractError, RangeAssumptionError)
    assert issubclass(UnknownRangeProfileError, RangeAssumptionError)
    assert issubclass(OutOfProfileError, RangeAssumptionError)
    assert not issubclass(RangeContractError, OutOfProfileError)
    assert not issubclass(OutOfProfileError, UnknownRangeProfileError)
    assert not issubclass(UnknownRangeProfileError, RangeContractError)


def test_profile_identifier_must_be_versioned() -> None:
    with pytest.raises(ValidationError):
        RangeProfile(
            profile_identifier="no-version",
            source=RANGE_SOURCE_DECLARED_ASSUMPTION,
            basis="basis",
            aggressor_class_count=1,
            caller_class_count=1,
            blind_class_count=1,
            unacted_class_count=1,
            folded_class_count=0,
            max_aggressive_actions_per_street=1,
        )


def test_source_must_be_a_declared_assumption() -> None:
    with pytest.raises(ValidationError):
        RangeProfile(
            profile_identifier="x@1",
            source="from-solver",
            basis="basis",
            aggressor_class_count=1,
            caller_class_count=1,
            blind_class_count=1,
            unacted_class_count=1,
            folded_class_count=0,
            max_aggressive_actions_per_street=1,
        )


def test_folded_class_count_must_be_zero() -> None:
    with pytest.raises(ValidationError):
        RangeProfile(
            profile_identifier="x@1",
            source=RANGE_SOURCE_DECLARED_ASSUMPTION,
            basis="basis",
            aggressor_class_count=1,
            caller_class_count=1,
            blind_class_count=1,
            unacted_class_count=1,
            folded_class_count=10,
            max_aggressive_actions_per_street=1,
        )


def test_max_aggressive_bound_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        RangeProfile(
            profile_identifier="x@1",
            source=RANGE_SOURCE_DECLARED_ASSUMPTION,
            basis="basis",
            aggressor_class_count=1,
            caller_class_count=1,
            blind_class_count=1,
            unacted_class_count=1,
            folded_class_count=0,
            max_aggressive_actions_per_street=0,
        )


# ---------------------------------------------------------------- 档位与权重


@pytest.mark.parametrize("class_count", [0, 1, 40, 80, 110, 130, 169])
def test_weights_are_an_indicative_prefix(class_count: int) -> None:
    weights = weights_for_class_count(class_count)
    assert len(weights) == RANGE_HAND_CLASS_COUNT
    assert sum(weights) == float(class_count)
    assert weights[:class_count] == (1.0,) * class_count
    assert set(weights[class_count:]) <= {0.0}


@pytest.mark.parametrize("bad", [-1, 170, True, "40", 1.5])
def test_weights_reject_out_of_range_or_illegal_input(bad: object) -> None:
    with pytest.raises(RangeContractError):
        weights_for_class_count(bad)  # type: ignore[arg-type]


def test_default_profile_declares_the_frozen_class_counts() -> None:
    profile = profile_for(DEFAULT_RANGE_PROFILE_IDENTIFIER)
    assert profile.source == RANGE_SOURCE_DECLARED_ASSUMPTION
    assert profile.basis.strip()
    assert profile.class_count_for(RANGE_ROLE_AGGRESSOR) == 40
    assert profile.class_count_for(RANGE_ROLE_CALLER) == 80
    assert profile.class_count_for(RANGE_ROLE_BLIND) == 110
    assert profile.class_count_for(RANGE_ROLE_UNACTED) == 130
    assert profile.class_count_for(RANGE_ROLE_FOLDED) == 0
    assert profile.max_aggressive_actions_per_street == 1


def test_unknown_profile_identifier_fails() -> None:
    with pytest.raises(UnknownRangeProfileError):
        profile_for("action-line-roles@2")
    with pytest.raises(RangeContractError):
        profile_for(1)  # type: ignore[arg-type]


def test_known_profiles_contain_the_default() -> None:
    assert DEFAULT_RANGE_PROFILE_IDENTIFIER in known_profile_identifiers()
    assert known_profile_identifiers() == tuple(sorted(known_profile_identifiers()))


def test_registering_a_duplicate_profile_fails() -> None:
    with pytest.raises(ValueError):
        register_range_profile(profile_for(DEFAULT_RANGE_PROFILE_IDENTIFIER))


# ---------------------------------------------------------------- 角色派生


def test_roles_follow_the_public_action_line() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "raise", 60),
        _rec("preflop", 4, "call", 60),
        _rec("preflop", 5, "call", 60),
        _rec("preflop", 0, "fold"),
        _rec("preflop", 1, "fold"),
        _rec("preflop", 2, "call", 40),
    ]
    roles = _role_map(_project(current_seat=2, history=history))
    assert roles[3] == RANGE_ROLE_AGGRESSOR
    assert roles[4] == RANGE_ROLE_CALLER
    assert roles[5] == RANGE_ROLE_CALLER
    assert roles[0] == RANGE_ROLE_FOLDED
    assert roles[1] == RANGE_ROLE_FOLDED


def test_actor_is_not_given_a_range() -> None:
    projection = _project(current_seat=2)
    roles = _role_map(projection)
    assert projection.relative_actor not in roles
    assumption = build_range_assumption(projection=projection)
    seats = [opponent.relative_seat for opponent in assumption.opponents]
    assert projection.relative_actor not in seats


def test_blind_role_requires_no_voluntary_action() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "fold"),
        _rec("preflop", 4, "fold"),
        _rec("preflop", 5, "fold"),
        _rec("preflop", 1, "fold"),
    ]
    roles = _role_map(_project(current_seat=0, history=history))
    assert roles[2] == RANGE_ROLE_BLIND
    assert roles[1] == RANGE_ROLE_FOLDED


def test_check_does_not_narrow_the_assumed_range() -> None:
    history = [*_blinds(6, 0), _rec("flop", 4, "check")]
    roles = _role_map(_project(current_seat=2, street="flop", history=history))
    assert roles[4] == RANGE_ROLE_UNACTED
    assert roles[5] == RANGE_ROLE_UNACTED


def test_fold_is_persistent_across_streets() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 5, "fold"),
        _rec("flop", 4, "check"),
    ]
    roles = _role_map(_project(current_seat=2, street="flop", history=history))
    assert roles[5] == RANGE_ROLE_FOLDED


def test_roles_come_from_the_last_segment_only() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "raise", 60),
        _rec("preflop", 4, "call", 60),
        _rec("preflop", 5, "fold"),
        _rec("preflop", 0, "fold"),
        _rec("preflop", 1, "fold"),
        _rec("preflop", 2, "fold"),
        _rec("flop", 3, "check"),
        _rec("flop", 4, "check"),
    ]
    roles = _role_map(_project(current_seat=2, street="flop", history=history))
    # 翻前的加注者在翻牌过牌后不再带有收紧信息。
    assert roles[3] == RANGE_ROLE_UNACTED
    assert roles[4] == RANGE_ROLE_UNACTED


def test_folded_seat_is_not_an_aggressor() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "raise", 60),
        _rec("flop", 3, "fold"),
    ]
    roles = _role_map(_project(current_seat=2, street="flop", history=history))
    assert roles[3] == RANGE_ROLE_FOLDED


# ---------------------------------------------------------------- 假设整体


@pytest.mark.parametrize("num_players", range(2, 10))
def test_assumption_covers_every_other_seat(num_players: int) -> None:
    projection = _project(num_players, current_seat=num_players - 1)
    assumption = build_range_assumption(projection=projection)
    assert assumption.player_count == num_players
    assert len(assumption.opponents) == num_players - 1
    assert [opponent.relative_seat for opponent in assumption.opponents] == [
        seat for seat in range(num_players) if seat != projection.relative_actor
    ]


def test_assumption_declares_model_inference_and_limitations() -> None:
    assumption = build_range_assumption(projection=_project())
    assert assumption.source == RANGE_SOURCE_DECLARED_ASSUMPTION
    assert assumption.schema_version == RANGE_ASSUMPTION_SCHEMA_VERSION
    assert assumption.profile_identifier == DEFAULT_RANGE_PROFILE_IDENTIFIER
    assert RANGE_LIMITATION_NOT_A_SOLVER in assumption.limitations
    assert RANGE_LIMITATION_NO_BOARD_NARROWING in assumption.limitations
    assert tuple(assumption.limitations) == RANGE_LIMITATIONS


def test_assumption_rejects_a_solver_style_source() -> None:
    with pytest.raises(ValidationError):
        RangeAssumption(
            schema_version=RANGE_ASSUMPTION_SCHEMA_VERSION,
            profile_identifier=DEFAULT_RANGE_PROFILE_IDENTIFIER,
            source="cfr-training-output",
            player_count=2,
            street="preflop",
            relative_actor=0,
            opponents=(
                OpponentRange(
                    relative_seat=1,
                    role=RANGE_ROLE_CALLER,
                    contests_pot=True,
                    class_count=10,
                    weights=weights_for_class_count(10),
                ),
            ),
            limitations=RANGE_LIMITATIONS,
        )


def test_assumption_rejects_a_foreign_schema_version() -> None:
    with pytest.raises(ValidationError):
        RangeAssumption(
            schema_version="range-assumption.v2",
            profile_identifier=DEFAULT_RANGE_PROFILE_IDENTIFIER,
            source=RANGE_SOURCE_DECLARED_ASSUMPTION,
            player_count=2,
            street="preflop",
            relative_actor=0,
            opponents=(),
            limitations=RANGE_LIMITATIONS,
        )


def test_unknown_profile_stops_the_construction() -> None:
    with pytest.raises(UnknownRangeProfileError):
        build_range_assumption(projection=_project(), profile_identifier="nope@1")


def test_opponent_range_rejects_inconsistent_weights() -> None:
    with pytest.raises(ValidationError):
        OpponentRange(
            relative_seat=1,
            role=RANGE_ROLE_CALLER,
            contests_pot=True,
            class_count=10,
            weights=weights_for_class_count(20),
        )


def test_contending_role_cannot_carry_an_empty_range() -> None:
    with pytest.raises(ValidationError):
        OpponentRange(
            relative_seat=1,
            role=RANGE_ROLE_CALLER,
            contests_pot=True,
            class_count=0,
            weights=weights_for_class_count(0),
        )


def test_folded_role_cannot_contest_the_pot() -> None:
    with pytest.raises(ValidationError):
        OpponentRange(
            relative_seat=1,
            role=RANGE_ROLE_FOLDED,
            contests_pot=True,
            class_count=0,
            weights=weights_for_class_count(0),
        )


def test_folded_opponents_are_declared_without_a_range() -> None:
    assumption = build_range_assumption(projection=_project(current_seat=2))
    for opponent in assumption.opponents:
        if opponent.role == RANGE_ROLE_FOLDED:
            assert opponent.contests_pot is False
            assert opponent.class_count == 0
            assert sum(opponent.weights) == 0.0
        else:
            assert opponent.contests_pot is True
            assert opponent.class_count >= 1


# ---------------------------------------------------------------- 超范围与明确失败


def test_second_aggressive_action_per_street_is_out_of_profile() -> None:
    history = [
        *_blinds(6, 0),
        _rec("preflop", 3, "raise", 60),
        _rec("preflop", 4, "raise", 200),
    ]
    with pytest.raises(OutOfProfileError, match="preflop"):
        build_range_assumption(projection=_project(current_seat=3, history=history))


def test_malformed_token_is_out_of_profile() -> None:
    projection = _project(current_seat=2)
    broken = projection.model_copy(
        update={
            "public_action_line": (
                projection.public_action_line[0].model_copy(update={"tokens": ("zz@1",)}),
            )
        }
    )
    with pytest.raises(OutOfProfileError):
        assign_opponent_roles(broken)


def test_non_projection_input_is_a_contract_violation() -> None:
    with pytest.raises(RangeContractError):
        build_range_assumption(projection={"street": "preflop"})  # type: ignore[arg-type]
    with pytest.raises(RangeContractError):
        assign_opponent_roles("not-a-projection")  # type: ignore[arg-type]


# ---------------------------------------------------------------- 信息边界与版本化


def test_entry_accepts_only_the_public_projection() -> None:
    parameters = set(inspect.signature(build_range_assumption).parameters)
    assert parameters == {"projection", "profile_identifier"}


def test_assumption_fields_carry_no_cards_or_amounts() -> None:
    forbidden = {
        "board",
        "runout",
        "hole_cards",
        "pot",
        "stack",
        "amount",
        "seat",
        "button",
        "seed",
    }
    assert forbidden.isdisjoint(RangeAssumption.model_fields)
    assert forbidden.isdisjoint(OPPONENT_RANGE_FIELDS)
    assert forbidden.isdisjoint(RANGE_PROFILE_FIELDS)


def test_module_never_imports_lookup_equity_analysis_or_storage() -> None:
    source = inspect.getsource(range_assumption)
    for forbidden in (
        "app.poker.equity",
        "app.poker.engine",
        "app.analysis",
        "app.storage",
        "app.llm",
        "heuristic",
    ):
        assert forbidden not in source


def test_module_has_no_production_caller() -> None:
    app_root = Path(range_assumption.__file__).resolve().parents[1]
    offenders = [
        path.name
        for path in app_root.rglob("*.py")
        if path.name not in {"range_assumption.py", "__init__.py"}
        and "range_assumption" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_contrast_coverage_mirrors_the_frozen_reference_identity() -> None:
    assert RANGE_CONTRAST_COVERAGE == reference_identity.REFERENCE_COVERAGE


def test_production_reference_identity_is_unchanged() -> None:
    identity = reference_identity.reference_identity()
    assert identity["reference_strategy"] == "heuristic-conservative"
    assert identity["reference_version"] == 1
    assert identity["evaluation_version"] == 1


def test_assumption_ignores_hidden_cards_and_board() -> None:
    history = [*_blinds(6, 0), _rec("preflop", 3, "fold")]
    plain_state = _state(6, current_seat=2)
    masked_state = _state(
        6, current_seat=2, opponent_holes="9s 9h", board="Ah Qh 7s 2d"
    )
    plain = build_range_assumption(projection=project_position_for_actor(plain_state, history))
    masked = build_range_assumption(projection=project_position_for_actor(masked_state, history))
    assert masked == plain


# ---------------------------------------------------------------- 纯度


def test_build_does_not_mutate_the_projection() -> None:
    projection = _project(current_seat=2)
    before = projection.model_dump()
    build_range_assumption(projection=projection)
    assert projection.model_dump() == before


def test_assumption_round_trips_through_json() -> None:
    assumption = build_range_assumption(projection=_project(current_seat=2))
    assert RangeAssumption.model_validate(assumption.model_dump()) == assumption


def test_opponent_lookup_rejects_the_actor_and_out_of_range_seats() -> None:
    assumption = build_range_assumption(projection=_project(current_seat=2))
    with pytest.raises(RangeContractError):
        assumption.opponent_at(assumption.relative_actor)
    with pytest.raises(RangeContractError):
        assumption.opponent_at(assumption.player_count)
