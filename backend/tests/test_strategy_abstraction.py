"""抽象投影、覆盖判定与回退声明的回归测试。"""

import pytest
from pydantic import ValidationError

from app.poker.state import GameState, PlayerState, Street
from app.strategy.abstraction import (
    ABSTRACTION_GAME_VERSION,
    ABSTRACTION_PROJECTION_FIELDS,
    ABSTRACTION_TRAINED_PLAYER_COUNTS,
    COVERAGE_IN_ABSTRACTION,
    COVERAGE_INCOMPLETE_INFOSET,
    COVERAGE_OUT_OF_ABSTRACTION,
    COVERAGE_VERSION_MISMATCH,
    DEFAULT_FALLBACK_IDENTIFIER,
    FALLBACK_SOURCE_DECLARED_CONTRACT,
    AbstractionContractError,
    AbstractProjection,
    FallbackDeclaration,
    FallbackSourceError,
    IncompleteInfosetError,
    OutOfAbstractionError,
    VersionMismatchError,
    build_abstract_projection,
    build_abstraction_key,
    declared_fallback,
    judge_coverage,
    judge_game_state_coverage,
    require_in_abstraction,
)
from app.strategy.registry import known_identifiers

from .helpers import cards


def _state(num_players: int, *, opponent_holes: str = "2c 3d", board: str = "") -> GameState:
    """构造行动者为座位 0 的快照；对手底牌与公共牌只用于验证「不读取」。"""
    players = [PlayerState(seat=0, name="p0", hole_cards=cards("As Kd"), stack=1000)]
    for seat in range(1, num_players):
        players.append(
            PlayerState(seat=seat, name=f"p{seat}", hole_cards=cards(opponent_holes), stack=1000)
        )
    return GameState(
        street=Street.PREFLOP if not board else Street.FLOP,
        board=tuple(cards(board)) if board else (),
        pot=15,
        current_seat=0,
        button=0,
        hand_over=False,
        players=tuple(players),
    )


def _in_abstraction_verdict(*, player_count: int = 6, relative_actor: int = 0, own_rank: int = 0):
    return judge_coverage(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=player_count,
        relative_actor=relative_actor,
        own_rank=own_rank,
        canonical_public_history="-",
    )


def _out_of_abstraction_verdict():
    return judge_coverage(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=8,
        relative_actor=0,
        own_rank=0,
        canonical_public_history="-",
    )


# ---------------------------------------------------------------- 字段齐备


def test_projection_field_set_is_exactly_the_contract() -> None:
    assert tuple(AbstractProjection.model_fields) == ABSTRACTION_PROJECTION_FIELDS
    assert len(ABSTRACTION_PROJECTION_FIELDS) == 5


def test_projection_rejects_unregistered_fields() -> None:
    with pytest.raises(ValidationError):
        AbstractProjection(
            game_version=ABSTRACTION_GAME_VERSION,
            player_count=6,
            relative_actor=0,
            own_rank=0,
            canonical_public_history="-",
            board="As Kd Qc",
        )


def test_build_projection_returns_the_contract_record() -> None:
    projection = build_abstract_projection(ABSTRACTION_GAME_VERSION, 7, 2, 5, "x@0|x@1")
    assert projection == AbstractProjection(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=7,
        relative_actor=2,
        own_rank=5,
        canonical_public_history="x@0|x@1",
    )


# ---------------------------------------------------------------- 键格式


def test_key_matches_the_declared_format_at_root() -> None:
    verdict = _in_abstraction_verdict()
    assert verdict.coverage == COVERAGE_IN_ABSTRACTION
    assert verdict.abstraction_key == "m8/m8-a-v1/n=6/actor=0/rank=0/history=-"
    assert verdict.projection is not None


def test_key_matches_the_declared_format_mid_history() -> None:
    verdict = judge_coverage(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=6,
        relative_actor=3,
        own_rank=5,
        canonical_public_history="x@0|b@1|c@2",
    )
    assert verdict.coverage == COVERAGE_IN_ABSTRACTION
    assert verdict.abstraction_key == "m8/m8-a-v1/n=6/actor=3/rank=5/history=x@0|b@1|c@2"


def test_build_abstraction_key_uses_the_same_format() -> None:
    projection = build_abstract_projection(ABSTRACTION_GAME_VERSION, 9, 0, 8, "-")
    assert build_abstraction_key(projection) == "m8/m8-a-v1/n=9/actor=0/rank=8/history=-"


# ---------------------------------------------------------------- 抽象外


@pytest.mark.parametrize("player_count", [2, 3, 4, 5, 8, 10])
def test_untrained_player_count_is_out_of_abstraction(player_count: int) -> None:
    verdict = judge_coverage(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=player_count,
        relative_actor=0,
        own_rank=0,
        canonical_public_history="-",
    )
    assert verdict.coverage == COVERAGE_OUT_OF_ABSTRACTION
    assert verdict.abstraction_key is None
    assert verdict.projection is None


@pytest.mark.parametrize(
    "history",
    [
        "",
        "x@0|x@1|x@2|x@3|x@4|x@5",
        "b@0|b@1",
        "b@1",
        "x@0|b@2",
        "x@0|f@1",
        "x@0|",
    ],
)
def test_history_outside_abstraction_fails(history: str) -> None:
    verdict = judge_coverage(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=6,
        relative_actor=0,
        own_rank=0,
        canonical_public_history=history,
    )
    assert verdict.coverage == COVERAGE_OUT_OF_ABSTRACTION
    assert verdict.abstraction_key is None
    assert verdict.reasons


@pytest.mark.parametrize(
    ("relative_actor", "own_rank"),
    [(6, 0), (0, 6), (0, -1), (-1, 3)],
)
def test_actor_or_rank_out_of_range_is_out_of_abstraction(
    relative_actor: int, own_rank: int
) -> None:
    verdict = judge_coverage(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=6,
        relative_actor=relative_actor,
        own_rank=own_rank,
        canonical_public_history="-",
    )
    assert verdict.coverage == COVERAGE_OUT_OF_ABSTRACTION
    assert verdict.abstraction_key is None


def test_history_actor_must_match_relative_actor() -> None:
    verdict = judge_coverage(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=6,
        relative_actor=0,
        own_rank=0,
        canonical_public_history="x@0",
    )
    assert verdict.coverage == COVERAGE_OUT_OF_ABSTRACTION
    assert verdict.abstraction_key is None


# ---------------------------------------------------------------- 版本不匹配


@pytest.mark.parametrize("version", ["m8-a-v0", "m8-b-v1", "unknown"])
def test_version_mismatch_fails(version: str) -> None:
    verdict = judge_coverage(
        game_version=version,
        player_count=6,
        relative_actor=0,
        own_rank=0,
        canonical_public_history="-",
    )
    assert verdict.coverage == COVERAGE_VERSION_MISMATCH
    assert verdict.abstraction_key is None


# ---------------------------------------------------------------- 不完整信息集


@pytest.mark.parametrize(
    "missing_field",
    ["game_version", "player_count", "relative_actor", "own_rank", "canonical_public_history"],
)
def test_missing_field_is_incomplete_infoset(missing_field: str) -> None:
    payload: dict[str, object] = {
        "game_version": ABSTRACTION_GAME_VERSION,
        "player_count": 6,
        "relative_actor": 0,
        "own_rank": 0,
        "canonical_public_history": "-",
    }
    payload[missing_field] = None

    verdict = judge_coverage(**payload)
    assert verdict.coverage == COVERAGE_INCOMPLETE_INFOSET
    # 不完整信息集与抽象外是彼此独立的结论，不得合并。
    assert verdict.coverage != COVERAGE_OUT_OF_ABSTRACTION
    assert verdict.abstraction_key is None


def test_structural_illegal_input_raises_contract_error() -> None:
    with pytest.raises(AbstractionContractError):
        judge_coverage(
            game_version=ABSTRACTION_GAME_VERSION,
            player_count="6",
            relative_actor=0,
            own_rank=0,
            canonical_public_history="-",
        )
    with pytest.raises(AbstractionContractError):
        judge_coverage(
            game_version=ABSTRACTION_GAME_VERSION,
            player_count=6,
            relative_actor=0,
            own_rank=0,
            canonical_public_history=0,
        )
    with pytest.raises(AbstractionContractError):
        build_abstract_projection(ABSTRACTION_GAME_VERSION, True, 0, 0, "-")


# ---------------------------------------------------------------- 明确失败，无最近桶


def test_out_of_abstraction_never_yields_a_key() -> None:
    verdict = _out_of_abstraction_verdict()
    assert verdict.abstraction_key is None
    assert verdict.projection is None
    with pytest.raises(OutOfAbstractionError):
        build_abstraction_key(
            AbstractProjection(
                game_version=ABSTRACTION_GAME_VERSION,
                player_count=8,
                relative_actor=0,
                own_rank=0,
                canonical_public_history="-",
            )
        )


def test_build_abstraction_key_rejects_unresolved_history() -> None:
    with pytest.raises(OutOfAbstractionError):
        build_abstraction_key(
            AbstractProjection(
                game_version=ABSTRACTION_GAME_VERSION,
                player_count=6,
                relative_actor=0,
                own_rank=0,
                canonical_public_history="x@0|x@1|x@2|x@3|x@4|x@5",
            )
        )


def test_require_in_abstraction_raises_typed_errors() -> None:
    with pytest.raises(VersionMismatchError):
        require_in_abstraction(
            judge_coverage(
                game_version="m8-a-v0",
                player_count=6,
                relative_actor=0,
                own_rank=0,
                canonical_public_history="-",
            )
        )
    with pytest.raises(IncompleteInfosetError):
        require_in_abstraction(judge_coverage())
    with pytest.raises(OutOfAbstractionError):
        require_in_abstraction(_out_of_abstraction_verdict())

    projection = require_in_abstraction(_in_abstraction_verdict())
    assert projection.canonical_public_history == "-"


# ---------------------------------------------------------------- 回退声明


def test_declared_fallback_is_traceable_and_labeled() -> None:
    verdict = _out_of_abstraction_verdict()
    declaration = declared_fallback(verdict)

    assert declaration is not None
    assert declaration.fallback_identifier == DEFAULT_FALLBACK_IDENTIFIER
    assert declaration.fallback_identifier in known_identifiers()
    assert declaration.triggering_coverage == COVERAGE_OUT_OF_ABSTRACTION
    assert declaration.reasons == verdict.reasons
    assert declaration.abstraction_key is None
    assert declaration.source == FALLBACK_SOURCE_DECLARED_CONTRACT
    assert declaration.is_exact_solution is False


def test_declared_fallback_is_reproducible() -> None:
    assert declared_fallback(_out_of_abstraction_verdict()) == declared_fallback(
        _out_of_abstraction_verdict()
    )


def test_declared_fallback_is_none_in_abstraction() -> None:
    assert declared_fallback(_in_abstraction_verdict()) is None


def test_fallback_source_must_be_registered() -> None:
    with pytest.raises(FallbackSourceError):
        declared_fallback(_out_of_abstraction_verdict(), fallback_identifier="gto@9")
    with pytest.raises(ValidationError):
        FallbackDeclaration(
            fallback_identifier="gto@9",
            triggering_coverage=COVERAGE_OUT_OF_ABSTRACTION,
        )


def test_fallback_declaration_cannot_claim_exactness_or_coverage() -> None:
    with pytest.raises(ValidationError):
        FallbackDeclaration(
            fallback_identifier=DEFAULT_FALLBACK_IDENTIFIER,
            triggering_coverage=COVERAGE_OUT_OF_ABSTRACTION,
            is_exact_solution=True,
        )
    with pytest.raises(ValidationError):
        FallbackDeclaration(
            fallback_identifier=DEFAULT_FALLBACK_IDENTIFIER,
            triggering_coverage=COVERAGE_IN_ABSTRACTION,
        )


# ---------------------------------------------------------------- 信息边界


def test_projection_carries_no_hidden_or_future_fields() -> None:
    forbidden = {"hole_cards", "board", "seed", "master_seed", "rng_state", "opponent_cards"}
    assert forbidden.isdisjoint(AbstractProjection.model_fields)
    assert forbidden.isdisjoint(FallbackDeclaration.model_fields)


def test_game_state_verdict_ignores_hidden_and_future_cards() -> None:
    state_a = _state(6, opponent_holes="2c 3d", board="")
    state_b = _state(6, opponent_holes="9h 9s", board="As Kd Qc")
    assert state_a != state_b

    verdict_a = judge_game_state_coverage(state_a)
    verdict_b = judge_game_state_coverage(state_b)
    assert verdict_a == verdict_b
    assert verdict_a.abstraction_key is None


def test_game_state_verdict_reads_only_actor_view() -> None:
    # 六人桌人数落在训练抽象内，但快照没有公开行动历史与相对行动者，只能如实报告缺项。
    verdict = judge_game_state_coverage(_state(6))
    assert verdict.coverage == COVERAGE_INCOMPLETE_INFOSET
    assert len(verdict.reasons) == 3


# ---------------------------------------------------------------- 2–9 人参数化


@pytest.mark.parametrize("player_count", range(2, 10))
def test_coverage_is_parameterized_by_player_count(player_count: int) -> None:
    verdict = judge_coverage(
        game_version=ABSTRACTION_GAME_VERSION,
        player_count=player_count,
        relative_actor=0,
        own_rank=0,
        canonical_public_history="-",
    )
    if player_count in ABSTRACTION_TRAINED_PLAYER_COUNTS:
        assert verdict.coverage == COVERAGE_IN_ABSTRACTION
        assert verdict.abstraction_key is not None
        assert f"n={player_count}" in verdict.abstraction_key
    else:
        assert verdict.coverage == COVERAGE_OUT_OF_ABSTRACTION
        assert verdict.abstraction_key is None


@pytest.mark.parametrize("player_count", range(2, 10))
def test_game_state_coverage_is_parameterized_by_player_count(player_count: int) -> None:
    verdict = judge_game_state_coverage(_state(player_count))
    expected = (
        COVERAGE_INCOMPLETE_INFOSET
        if player_count in ABSTRACTION_TRAINED_PLAYER_COUNTS
        else COVERAGE_OUT_OF_ABSTRACTION
    )
    assert verdict.coverage == expected
