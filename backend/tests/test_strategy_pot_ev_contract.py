"""逐池货币收益契约的回归测试。"""

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.analysis import reference_identity
from app.poker.actions import Action, ActionType
from app.poker.engine import PokerEngine
from app.poker.pot_projection import (
    CandidateCallProjection,
    PotLayerKind,
    PotParticipant,
    ProjectedParticipant,
    ProjectedPotLayer,
    project_candidate_call,
)
from app.strategy import pot_ev_contract
from app.strategy.pot_ev_contract import (
    POT_EV_BASIS,
    POT_EV_CONTRACT_FIELDS,
    POT_EV_CONTRACT_SCHEMA_VERSION,
    POT_EV_DEFAULT_SCENARIO,
    POT_EV_INTEGER_PAYOUT_RULE,
    POT_EV_LAYER_FIELDS,
    POT_EV_LIMITATION_NO_SAMPLING,
    POT_EV_LIMITATION_NOT_FULL_EV,
    POT_EV_LIMITATION_NOT_QUALIFICATION_PROJECTION,
    POT_EV_LIMITATION_RANGE_DECLARED,
    POT_EV_LIMITATIONS,
    POT_EV_NOMINAL_SHARE_RULE,
    POT_EV_RANGE_PROFILE_IDENTIFIER,
    POT_EV_RANGE_SOURCE,
    POT_EV_RUNOUT_SCOPE,
    POT_EV_SCENARIO_CHECK_CALL,
    POT_EV_SCENARIOS,
    PotEvContract,
    PotEvContractError,
    PotEvDisposition,
    PotEvEncodingError,
    PotEvError,
    PotEvLayer,
    UnknownScenarioError,
    build_pot_ev_contract,
    disposition_for_kind,
    known_scenario_identifiers,
    scenario_description_for,
)
from app.strategy.range_assumption import (
    DEFAULT_RANGE_PROFILE_IDENTIFIER,
    RANGE_SOURCE_DECLARED_ASSUMPTION,
    known_profile_identifiers,
)

from .helpers import cards


def _participants(*items: tuple[int, int, bool]) -> tuple[PotParticipant, ...]:
    return tuple(
        PotParticipant(seat=seat, total_committed=total_committed, folded=folded)
        for seat, total_committed, folded in items
    )


def _contract(
    items: tuple[tuple[int, int, bool], ...] | list[tuple[int, int, bool]],
    *,
    caller_seat: int,
    actual_call_amount: int,
    call_amount: int | None = None,
) -> PotEvContract:
    projection = project_candidate_call(
        _participants(*items),
        caller_seat=caller_seat,
        actual_call_amount=actual_call_amount,
    )
    return build_pot_ev_contract(
        projection=projection,
        call_amount=actual_call_amount if call_amount is None else call_amount,
    )


def _handcrafted(
    layers: tuple[ProjectedPotLayer, ...],
    participants: tuple[ProjectedParticipant, ...] | None = None,
) -> CandidateCallProjection:
    """直接构造资格投影，用于验证契约层的分型失败语义。"""
    if participants is None:
        participants = (
            ProjectedParticipant(seat=0, total_committed=10, folded=False),
            ProjectedParticipant(seat=1, total_committed=10, folded=False),
        )
    return CandidateCallProjection(
        caller_seat=0,
        actual_call_amount=10,
        participants=participants,
        layers=layers,
    )


# ---------------------------------------------------------------- 契约与字段


def test_layer_field_set_is_exactly_the_contract() -> None:
    assert tuple(PotEvLayer.model_fields) == POT_EV_LAYER_FIELDS
    assert len(POT_EV_LAYER_FIELDS) == 10


def test_contract_field_set_is_exactly_the_contract() -> None:
    assert tuple(PotEvContract.model_fields) == POT_EV_CONTRACT_FIELDS
    assert len(POT_EV_CONTRACT_FIELDS) == 17


def test_contract_declares_version_basis_scenario_and_rules() -> None:
    contract = _contract(
        [(0, 80, False), (1, 60, False), (2, 30, False)],
        caller_seat=0,
        actual_call_amount=20,
    )
    assert contract.schema_version == POT_EV_CONTRACT_SCHEMA_VERSION
    assert contract.basis == POT_EV_BASIS
    assert contract.runout_scope == POT_EV_RUNOUT_SCOPE
    assert contract.scenario_identifier == POT_EV_DEFAULT_SCENARIO
    assert contract.scenario_description == POT_EV_SCENARIOS[POT_EV_SCENARIO_CHECK_CALL]
    assert contract.nominal_share_rule == POT_EV_NOMINAL_SHARE_RULE
    assert contract.integer_payout_rule == POT_EV_INTEGER_PAYOUT_RULE
    assert tuple(contract.limitations) == POT_EV_LIMITATIONS
    for required in (
        POT_EV_LIMITATION_NOT_FULL_EV,
        POT_EV_LIMITATION_NO_SAMPLING,
        POT_EV_LIMITATION_RANGE_DECLARED,
        POT_EV_LIMITATION_NOT_QUALIFICATION_PROJECTION,
    ):
        assert required in contract.limitations


def test_contract_rejects_a_foreign_schema_version() -> None:
    contract = _contract([(0, 30, False), (1, 30, False)], caller_seat=0, actual_call_amount=10)
    payload = contract.model_dump()
    payload["schema_version"] = "pot-ev-contract.v2"
    with pytest.raises(ValidationError):
        PotEvContract.model_validate(payload)


def test_contract_rejects_a_solver_style_range_source() -> None:
    contract = _contract([(0, 30, False), (1, 30, False)], caller_seat=0, actual_call_amount=10)
    payload = contract.model_dump()
    payload["range_source"] = "cfr-training-output"
    with pytest.raises(ValidationError):
        PotEvContract.model_validate(payload)


def test_contract_requires_the_declared_limitations() -> None:
    contract = _contract([(0, 30, False), (1, 30, False)], caller_seat=0, actual_call_amount=10)
    payload = contract.model_dump()
    payload["limitations"] = (POT_EV_LIMITATION_NOT_FULL_EV,)
    with pytest.raises(ValidationError):
        PotEvContract.model_validate(payload)


def test_models_reject_unregistered_fields() -> None:
    with pytest.raises(ValidationError):
        PotEvLayer(
            lower_commitment=0,
            upper_commitment=10,
            amount=20,
            contributor_seats=(0, 1),
            eligible_seats=(0, 1),
            kind="contested",
            disposition=PotEvDisposition.CONTESTED,
            caller_eligible=True,
            enters_expected_share=True,
            certain_recovery=0,
            board="As Kd",
        )


def test_contract_is_frozen() -> None:
    contract = _contract([(0, 30, False), (1, 30, False)], caller_seat=0, actual_call_amount=10)
    with pytest.raises(ValidationError):
        contract.player_count = 5  # type: ignore[misc]


def test_error_types_are_distinct() -> None:
    assert issubclass(PotEvContractError, PotEvError)
    assert issubclass(PotEvEncodingError, PotEvError)
    assert issubclass(UnknownScenarioError, PotEvError)
    assert not issubclass(PotEvContractError, PotEvEncodingError)
    assert not issubclass(PotEvEncodingError, UnknownScenarioError)
    assert not issubclass(UnknownScenarioError, PotEvContractError)


def test_layer_rejects_mismatched_disposition() -> None:
    with pytest.raises(ValidationError):
        PotEvLayer(
            lower_commitment=0,
            upper_commitment=10,
            amount=20,
            contributor_seats=(0, 1),
            eligible_seats=(0, 1),
            kind="contested",
            disposition=PotEvDisposition.NOT_ELIGIBLE,
            caller_eligible=True,
            enters_expected_share=False,
            certain_recovery=0,
        )


def test_layer_rejects_recovery_without_eligibility() -> None:
    with pytest.raises(ValidationError):
        PotEvLayer(
            lower_commitment=0,
            upper_commitment=10,
            amount=20,
            contributor_seats=(0, 1),
            eligible_seats=(1,),
            kind="caller_recovery",
            disposition=PotEvDisposition.CERTAIN_RECOVERY,
            caller_eligible=False,
            enters_expected_share=False,
            certain_recovery=20,
        )


# ---------------------------------------------------------------- 处置映射


def test_disposition_covers_all_four_layer_kinds() -> None:
    assert disposition_for_kind(PotLayerKind.CONTESTED) is PotEvDisposition.CONTESTED
    assert disposition_for_kind(PotLayerKind.CALLER_RECOVERY) is PotEvDisposition.CERTAIN_RECOVERY
    assert disposition_for_kind(PotLayerKind.OTHER_UNCONTESTED) is PotEvDisposition.NOT_ELIGIBLE
    assert disposition_for_kind(PotLayerKind.NO_ELIGIBLE_RETURN) is PotEvDisposition.REFUND
    assert len(set(PotEvDisposition)) == 4


def test_unknown_layer_kind_fails() -> None:
    with pytest.raises(PotEvEncodingError):
        disposition_for_kind("mystery")
    with pytest.raises(PotEvEncodingError):
        disposition_for_kind(PotLayerKind.CONTESTED.value + "-x")


# ---------------------------------------------------------------- 逐层组合


def test_layers_follow_actual_call_amount_and_dispositions() -> None:
    contract = _contract(
        [(0, 80, False), (1, 60, False), (2, 30, False)],
        caller_seat=0,
        actual_call_amount=20,
    )

    assert contract.player_count == 3
    assert contract.caller_seat == 0
    assert contract.actual_call_amount == 20
    assert contract.call_amount == 20
    assert contract.is_short_all_in_call is False
    assert [layer.disposition for layer in contract.layers] == [
        PotEvDisposition.CONTESTED,
        PotEvDisposition.CONTESTED,
        PotEvDisposition.CERTAIN_RECOVERY,
    ]
    assert [layer.certain_recovery for layer in contract.layers] == [0, 0, 40]
    assert contract.certain_recovery_total == 40
    assert contract.layers_with(PotEvDisposition.CONTESTED) == contract.layers[:2]
    for layer in contract.layers:
        assert layer.enters_expected_share is (
            layer.disposition is PotEvDisposition.CONTESTED
        )


def test_other_uncontested_layer_is_excluded() -> None:
    contract = _contract(
        [(0, 110, False), (1, 10, False), (2, 10, False)],
        caller_seat=1,
        actual_call_amount=60,
        call_amount=100,
    )

    assert contract.actual_call_amount == 60
    assert contract.call_amount == 100
    assert contract.is_short_all_in_call is True
    assert [layer.disposition for layer in contract.layers] == [
        PotEvDisposition.CONTESTED,
        PotEvDisposition.CONTESTED,
        PotEvDisposition.NOT_ELIGIBLE,
    ]
    top = contract.layers[-1]
    assert top.caller_eligible is False
    assert top.enters_expected_share is False
    assert top.certain_recovery == 0
    assert contract.certain_recovery_total == 0


def test_no_eligible_return_layer_is_excluded_from_payoff() -> None:
    contract = _contract(
        [(0, 50, True), (1, 10, False), (2, 30, False)],
        caller_seat=1,
        actual_call_amount=20,
    )

    assert [layer.disposition for layer in contract.layers] == [
        PotEvDisposition.CONTESTED,
        PotEvDisposition.REFUND,
    ]
    refund = contract.layers[-1]
    assert refund.caller_eligible is False
    assert refund.enters_expected_share is False
    assert refund.certain_recovery == 0
    assert contract.certain_recovery_total == 0


def test_dead_money_and_nine_players_are_projected_without_shrinking() -> None:
    contract = _contract(
        [
            (0, 5, False),
            (1, 30, False),
            (2, 20, True),
            (3, 15, False),
            (4, 10, False),
            (5, 30, True),
            (6, 5, False),
            (7, 20, False),
            (8, 0, False),
        ],
        caller_seat=0,
        actual_call_amount=10,
    )

    assert contract.player_count == 9
    first = contract.layers[0]
    assert first.contributor_seats == (0, 1, 2, 3, 4, 5, 6, 7)
    assert first.eligible_seats == (0, 1, 3, 4, 6, 7)
    assert set(first.contributor_seats) - set(first.eligible_seats) == {2, 5}
    top = contract.layers[-1]
    assert top.disposition is PotEvDisposition.NOT_ELIGIBLE
    assert top.caller_eligible is False


def test_main_three_way_and_side_two_way_share_one_runout() -> None:
    contract = _contract(
        [(0, 100, False), (1, 100, False), (2, 50, False)],
        caller_seat=0,
        actual_call_amount=100,
    )

    contested = contract.layers_with(PotEvDisposition.CONTESTED)
    assert [len(layer.eligible_seats) for layer in contested] == [3, 2]
    assert [layer.amount for layer in contested] == [150, 100]
    assert contract.runout_scope == POT_EV_RUNOUT_SCOPE
    assert contract.layers[-1].disposition is PotEvDisposition.CERTAIN_RECOVERY
    assert contract.certain_recovery_total == 100


def test_short_all_in_call_covers_only_the_layers_it_reaches() -> None:
    contract = _contract(
        [(0, 200, False), (1, 50, False), (2, 100, False)],
        caller_seat=1,
        actual_call_amount=50,
        call_amount=150,
    )

    assert contract.actual_call_amount == 50
    assert contract.call_amount == 150
    assert contract.is_short_all_in_call is True
    assert len(contract.layers) == 2
    assert contract.layers[0].disposition is PotEvDisposition.CONTESTED
    assert len(contract.layers[0].eligible_seats) == 3
    assert contract.layers[1].disposition is PotEvDisposition.NOT_ELIGIBLE


def test_nominal_share_and_integer_payout_are_declared_separately() -> None:
    contract = _contract(
        [(0, 100, False), (1, 100, False), (2, 100, False)],
        caller_seat=0,
        actual_call_amount=100,
    )

    assert "1/k" in contract.nominal_share_rule
    assert "amount // k" in contract.integer_payout_rule
    assert contract.nominal_share_rule != contract.integer_payout_rule
    contested = contract.layers[0]
    assert len(contested.eligible_seats) == 3
    assert contested.certain_recovery == 0
    assert contract.layers_with(PotEvDisposition.CERTAIN_RECOVERY)[0].certain_recovery == 100


# ---------------------------------------------------------------- 人数与纯度


@pytest.mark.parametrize("num_players", range(2, 10))
def test_contract_is_parameterized_over_player_counts(num_players: int) -> None:
    participants = tuple(
        PotParticipant(seat=seat, total_committed=30, folded=False)
        for seat in range(num_players)
    )
    projection = project_candidate_call(participants, caller_seat=0, actual_call_amount=30)
    contract = build_pot_ev_contract(projection=projection, call_amount=30)

    assert contract.player_count == num_players
    assert len(contract.layers) == 2
    assert contract.layers[0].disposition is PotEvDisposition.CONTESTED
    assert len(contract.layers[0].eligible_seats) == num_players
    assert contract.layers[1].disposition is PotEvDisposition.CERTAIN_RECOVERY
    assert contract.certain_recovery_total == 30


def test_build_does_not_mutate_the_projection() -> None:
    participants = _participants((0, 80, False), (1, 60, False))
    projection = project_candidate_call(participants, caller_seat=0, actual_call_amount=20)
    before = (projection.participants, projection.layers)

    build_pot_ev_contract(projection=projection, call_amount=20)

    assert (projection.participants, projection.layers) == before


def test_contract_round_trips_through_json() -> None:
    contract = _contract([(0, 30, False), (1, 30, False)], caller_seat=0, actual_call_amount=10)
    assert PotEvContract.model_validate(contract.model_dump()) == contract


# ---------------------------------------------------------------- 情景与范围


def test_known_scenarios_are_a_closed_set() -> None:
    assert known_scenario_identifiers() == (POT_EV_SCENARIO_CHECK_CALL,)
    assert POT_EV_DEFAULT_SCENARIO in known_scenario_identifiers()
    assert scenario_description_for(POT_EV_SCENARIO_CHECK_CALL).strip()
    with pytest.raises(UnknownScenarioError):
        scenario_description_for("others-check-call-to-showdown@2")


def test_unknown_scenario_stops_the_construction() -> None:
    projection = project_candidate_call(
        _participants((0, 30, False), (1, 30, False)),
        caller_seat=0,
        actual_call_amount=10,
    )
    with pytest.raises(UnknownScenarioError):
        build_pot_ev_contract(
            projection=projection,
            call_amount=10,
            scenario_identifier="others-check-call-to-showdown@2",
        )
    with pytest.raises(PotEvContractError):
        build_pot_ev_contract(
            projection=projection,
            call_amount=10,
            scenario_identifier=1,  # type: ignore[arg-type]
        )


def test_range_reference_mirrors_the_controlled_catalogue() -> None:
    """只引用受控标识并由测试锁定，生产代码不反向依赖范围假设模块。"""
    assert POT_EV_RANGE_PROFILE_IDENTIFIER == DEFAULT_RANGE_PROFILE_IDENTIFIER
    assert POT_EV_RANGE_SOURCE == RANGE_SOURCE_DECLARED_ASSUMPTION
    assert POT_EV_RANGE_PROFILE_IDENTIFIER in known_profile_identifiers()

    projection = project_candidate_call(
        _participants((0, 30, False), (1, 30, False)),
        caller_seat=0,
        actual_call_amount=10,
    )
    contract = build_pot_ev_contract(projection=projection, call_amount=10)

    assert contract.range_profile_identifier == POT_EV_RANGE_PROFILE_IDENTIFIER
    assert contract.range_source == POT_EV_RANGE_SOURCE


def test_range_profile_identifier_must_be_versioned() -> None:
    projection = project_candidate_call(
        _participants((0, 30, False), (1, 30, False)),
        caller_seat=0,
        actual_call_amount=10,
    )
    with pytest.raises(PotEvContractError):
        build_pot_ev_contract(
            projection=projection,
            call_amount=10,
            range_profile_identifier="action-line-roles",
        )
    with pytest.raises(PotEvContractError):
        build_pot_ev_contract(
            projection=projection,
            call_amount=10,
            range_profile_identifier=42,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------- 明确失败


def test_non_projection_input_is_a_contract_violation() -> None:
    with pytest.raises(PotEvContractError):
        build_pot_ev_contract(projection={"layers": ()}, call_amount=10)  # type: ignore[arg-type]


@pytest.mark.parametrize("amount", [0, -10, True, "10"])
def test_call_amount_must_be_a_positive_integer(amount: object) -> None:
    projection = project_candidate_call(
        _participants((0, 30, False), (1, 30, False)),
        caller_seat=0,
        actual_call_amount=10,
    )
    with pytest.raises(PotEvContractError):
        build_pot_ev_contract(projection=projection, call_amount=amount)  # type: ignore[arg-type]


def test_call_amount_below_the_actual_payment_fails() -> None:
    projection = project_candidate_call(
        _participants((0, 30, False), (1, 30, False)),
        caller_seat=0,
        actual_call_amount=10,
    )
    with pytest.raises(PotEvContractError):
        build_pot_ev_contract(projection=projection, call_amount=5)


def test_eligible_seats_must_be_contributors() -> None:
    layer = ProjectedPotLayer(
        lower_commitment=0,
        upper_commitment=10,
        amount=20,
        contributor_seats=(1,),
        eligible_seats=(0, 1),
        caller_is_eligible=True,
        kind=PotLayerKind.CONTESTED,
        refunds=(),
    )
    with pytest.raises(PotEvEncodingError):
        build_pot_ev_contract(projection=_handcrafted((layer,)), call_amount=10)


def test_folded_caller_cannot_build_a_payoff_contract() -> None:
    participants = (
        ProjectedParticipant(seat=0, total_committed=10, folded=True),
        ProjectedParticipant(seat=1, total_committed=10, folded=False),
    )
    layer = ProjectedPotLayer(
        lower_commitment=0,
        upper_commitment=10,
        amount=20,
        contributor_seats=(0, 1),
        eligible_seats=(1,),
        caller_is_eligible=False,
        kind=PotLayerKind.CONTESTED,
        refunds=(),
    )
    with pytest.raises(PotEvEncodingError):
        build_pot_ev_contract(
            projection=_handcrafted((layer,), participants),
            call_amount=10,
        )


def test_caller_without_eligibility_is_incomplete() -> None:
    layer = ProjectedPotLayer(
        lower_commitment=0,
        upper_commitment=10,
        amount=20,
        contributor_seats=(1, 2),
        eligible_seats=(1, 2),
        caller_is_eligible=False,
        kind=PotLayerKind.CONTESTED,
        refunds=(),
    )
    participants = tuple(
        ProjectedParticipant(seat=seat, total_committed=10, folded=False) for seat in range(3)
    )
    with pytest.raises(PotEvEncodingError):
        build_pot_ev_contract(
            projection=_handcrafted((layer,), participants),
            call_amount=10,
        )


def test_non_contiguous_layers_fail() -> None:
    layer = ProjectedPotLayer(
        lower_commitment=5,
        upper_commitment=10,
        amount=20,
        contributor_seats=(0, 1),
        eligible_seats=(0, 1),
        caller_is_eligible=True,
        kind=PotLayerKind.CONTESTED,
        refunds=(),
    )
    with pytest.raises(PotEvContractError):
        build_pot_ev_contract(projection=_handcrafted((layer,)), call_amount=10)


# ---------------------------------------------------------------- 信息边界


def test_entry_accepts_only_public_projection_and_declarations() -> None:
    parameters = set(inspect.signature(build_pot_ev_contract).parameters)
    assert parameters == {
        "projection",
        "call_amount",
        "scenario_identifier",
        "range_profile_identifier",
    }


def test_contract_fields_carry_no_cards_board_or_seed() -> None:
    forbidden = {
        "board",
        "runout",
        "hole_cards",
        "pot",
        "stack",
        "seat",
        "button",
        "seed",
        "cards",
        "equity",
    }
    assert forbidden.isdisjoint(PotEvContract.model_fields)
    assert forbidden.isdisjoint(POT_EV_LAYER_FIELDS)


def test_module_never_imports_engine_equity_analysis_or_storage() -> None:
    source = inspect.getsource(pot_ev_contract)
    for forbidden in (
        "app.poker.engine",
        "app.poker.equity",
        "app.analysis",
        "app.storage",
        "app.llm",
        "heuristic",
        "call_ev",
        "ties",
    ):
        assert forbidden not in source


def test_module_has_no_production_caller() -> None:
    app_root = Path(pot_ev_contract.__file__).resolve().parents[1]
    offenders = [
        path.name
        for path in app_root.rglob("*.py")
        if path.name not in {"pot_ev_contract.py", "__init__.py"}
        and "pot_ev_contract" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def _short_call_scenario(hole_text: str, *, seed: int = 0) -> PotEvContract:
    """用引擎推进到短码候选 CALL 节点；对手底牌与公共牌只用于让引擎能跑完。"""
    engine = PokerEngine(3, small_blind=5, big_blind=10, starting_stack=110, seed=seed)
    engine.players[1].stack = 70
    engine.players[2].stack = 1000
    engine.start_hand_with(
        button=0,
        hole_cards={
            0: cards("As Kd"),
            1: cards(hole_text),
            2: cards("9c 8d"),
        },
        board=cards("2c 7d 9h Ts 3c"),
    )
    for action in (
        Action(ActionType.CALL),
        Action(ActionType.CALL),
        Action(ActionType.CHECK),
        Action(ActionType.CHECK),
        Action(ActionType.CHECK),
        Action(ActionType.BET, 100),
    ):
        engine.apply_action(action)

    legal = engine.legal_actions()
    projection = engine.candidate_call_pot_projection()
    assert projection is not None
    return build_pot_ev_contract(projection=projection, call_amount=legal.call_amount)


def test_contract_uses_actual_short_payment_from_the_engine() -> None:
    contract = _short_call_scenario("Qh Jc")

    assert contract.actual_call_amount == 60
    assert contract.is_short_all_in_call is True
    assert contract.call_amount > contract.actual_call_amount
    assert contract.layers[-1].disposition is PotEvDisposition.NOT_ELIGIBLE


def test_contract_ignores_hidden_cards_board_and_seed() -> None:
    assert _short_call_scenario("Qh Jc") == _short_call_scenario("3s 4h")
    assert _short_call_scenario("Qh Jc", seed=0) == _short_call_scenario("Qh Jc", seed=987654)


# ---------------------------------------------------------------- 既有语义未变


def test_production_reference_identity_is_unchanged() -> None:
    identity = reference_identity.reference_identity()
    assert identity["reference_strategy"] == "heuristic-conservative"
    assert identity["reference_version"] == 1
    assert identity["evaluation_version"] == 1
    assert identity["reference_coverage"] == "vs-random"
