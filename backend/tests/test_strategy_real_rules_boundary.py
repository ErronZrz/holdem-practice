"""真实规则与受限抽象切片边界契约的回归测试。"""

import importlib
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.strategy import abstraction as abstraction_contract
from app.strategy import real_rules_boundary
from app.strategy.real_rules_boundary import (
    ABSTRACTION_ACTION_TOKENS,
    ABSTRACTION_ANTE,
    ABSTRACTION_BET,
    ABSTRACTION_GAME_ID,
    ABSTRACTION_GAME_VERSION,
    ABSTRACTION_PLAYER_COUNTS,
    PREREQUISITE_NONE,
    PREREQUISITES,
    REAL_RULES_BOUNDARY_BASIS,
    REAL_RULES_BOUNDARY_SCHEMA_VERSION,
    REAL_RULES_LIMITATION_NO_SILENT_FALLBACK,
    REAL_RULES_LIMITATION_NOT_REAL_EV,
    REAL_RULES_LIMITATIONS,
    RULE_BOUNDARY_CONTRACT_FIELDS,
    RULE_SLICE_BOUNDARY_FIELDS,
    BoundaryVerdict,
    RealRulesBoundaryContractError,
    RealRulesBoundaryError,
    RuleBoundaryContract,
    RuleSliceBoundary,
    UnknownBoundaryFeatureError,
    boundary_catalogue,
    boundary_features,
    boundary_for,
    build_rule_boundary_contract,
    features_with,
    require_in_abstraction_slice,
    verdict_for,
)

# 受控前置标识 -> 实际入口；两者的一致性在此锁定，生产代码不互相 import。
_PREREQUISITE_ENTRY_POINTS = {
    "abstraction-coverage": ("app.strategy.abstraction", "judge_coverage"),
    "candidate-call-pot-projection": ("app.poker.pot_projection", "project_candidate_call"),
    "position-projection": ("app.strategy.position_projection", "build_position_projection"),
    "range-assumption": ("app.strategy.range_assumption", "build_range_assumption"),
    "pot-ev-contract": ("app.strategy.pot_ev_contract", "build_pot_ev_contract"),
}

_CONTRACT_KWARGS = {
    "schema_version": REAL_RULES_BOUNDARY_SCHEMA_VERSION,
    "basis": REAL_RULES_BOUNDARY_BASIS,
    "abstraction_game_id": ABSTRACTION_GAME_ID,
    "abstraction_game_version": ABSTRACTION_GAME_VERSION,
    "abstraction_player_counts": ABSTRACTION_PLAYER_COUNTS,
    "abstraction_ante": ABSTRACTION_ANTE,
    "abstraction_bet": ABSTRACTION_BET,
    "limitations": REAL_RULES_LIMITATIONS,
}


# ---------------------------------------------------------------- 契约与字段


def test_slice_field_set_is_exactly_the_contract() -> None:
    assert tuple(RuleSliceBoundary.model_fields) == RULE_SLICE_BOUNDARY_FIELDS
    assert len(RULE_SLICE_BOUNDARY_FIELDS) == 5


def test_contract_field_set_is_exactly_the_contract() -> None:
    assert tuple(RuleBoundaryContract.model_fields) == RULE_BOUNDARY_CONTRACT_FIELDS
    assert len(RULE_BOUNDARY_CONTRACT_FIELDS) == 9


def test_contract_declares_the_abstraction_and_limitations() -> None:
    contract = build_rule_boundary_contract()

    assert contract.schema_version == REAL_RULES_BOUNDARY_SCHEMA_VERSION
    assert contract.basis == REAL_RULES_BOUNDARY_BASIS
    assert contract.abstraction_game_id == ABSTRACTION_GAME_ID
    assert contract.abstraction_game_version == ABSTRACTION_GAME_VERSION
    assert contract.abstraction_player_counts == ABSTRACTION_PLAYER_COUNTS
    assert contract.abstraction_ante == ABSTRACTION_ANTE
    assert contract.abstraction_bet == ABSTRACTION_BET
    assert tuple(contract.limitations) == REAL_RULES_LIMITATIONS
    assert REAL_RULES_LIMITATION_NOT_REAL_EV in contract.limitations
    assert REAL_RULES_LIMITATION_NO_SILENT_FALLBACK in contract.limitations
    assert contract.entries == boundary_catalogue()
    assert contract.entry_for("public-board").verdict is BoundaryVerdict.OUT_OF_ABSTRACTION
    with pytest.raises(UnknownBoundaryFeatureError):
        contract.entry_for("no-such-slice")


def test_contract_is_frozen() -> None:
    contract = build_rule_boundary_contract()
    with pytest.raises(ValidationError):
        contract.abstraction_ante = 2  # type: ignore[misc]


def test_contract_round_trips_through_json() -> None:
    contract = build_rule_boundary_contract()
    assert RuleBoundaryContract.model_validate(contract.model_dump()) == contract


def test_models_reject_unregistered_fields() -> None:
    with pytest.raises(ValidationError):
        RuleSliceBoundary(
            feature="public-board",
            description="说明",
            verdict=BoundaryVerdict.OUT_OF_ABSTRACTION,
            prerequisite=PREREQUISITE_NONE,
            declaration="声明",
            board="As Kd",
        )


def test_error_types_are_distinct() -> None:
    assert issubclass(RealRulesBoundaryContractError, RealRulesBoundaryError)
    assert issubclass(UnknownBoundaryFeatureError, RealRulesBoundaryError)
    assert not issubclass(RealRulesBoundaryContractError, UnknownBoundaryFeatureError)
    assert not issubclass(UnknownBoundaryFeatureError, RealRulesBoundaryContractError)


# ---------------------------------------------------------------- 受限抽象事实


def test_abstraction_descriptor_is_declared() -> None:
    assert ABSTRACTION_GAME_ID == "m8-unique-rank-single-open"
    assert ABSTRACTION_GAME_VERSION == "m8-a-v1"
    assert ABSTRACTION_PLAYER_COUNTS == (6, 7, 9)
    assert ABSTRACTION_ANTE == ABSTRACTION_BET == 1
    assert ABSTRACTION_ACTION_TOKENS == ("b", "c", "f", "x")


def test_abstraction_facts_reuse_the_abstraction_contract() -> None:
    """版本、人数与动作只有一处事实源；本模块只复用，不另造一套。"""
    assert ABSTRACTION_GAME_VERSION == abstraction_contract.ABSTRACTION_GAME_VERSION
    assert tuple(
        sorted(abstraction_contract.ABSTRACTION_TRAINED_PLAYER_COUNTS)
    ) == ABSTRACTION_PLAYER_COUNTS
    assert tuple(sorted(abstraction_contract.ABSTRACTION_ACTIONS)) == ABSTRACTION_ACTION_TOKENS


def test_abstraction_descriptor_matches_the_trainer_slice() -> None:
    """只读训练器源文件锁定常量，不 import 该独立工程。"""
    repo_root = Path(real_rules_boundary.__file__).resolve().parents[3]
    game_path = repo_root / "tools" / "trainer" / "src" / "multiplayer_cfr" / "game.py"
    source = game_path.read_text(encoding="utf-8")

    assert 'GAME_ID = "m8-unique-rank-single-open"' in source
    assert 'GAME_VERSION = "m8-a-v1"' in source
    assert "ALLOWED_PLAYER_COUNTS = frozenset({6, 7, 9})" in source
    assert "ANTE = 1" in source
    assert "BET = 1" in source


# ---------------------------------------------------------------- 冻结目录


def test_catalogue_partitions_every_feature_into_three_verdicts() -> None:
    catalogue = boundary_catalogue()
    features = [entry.feature for entry in catalogue]

    assert len(catalogue) == 20
    assert len(set(features)) == len(catalogue)
    assert len(set(BoundaryVerdict)) == 3

    in_slice = features_with(BoundaryVerdict.IN_ABSTRACTION_SLICE)
    out_of_slice = features_with(BoundaryVerdict.OUT_OF_ABSTRACTION)
    contracted = features_with(BoundaryVerdict.CONTRACTED_NOT_WIRED)

    assert (len(in_slice), len(out_of_slice), len(contracted)) == (6, 7, 7)
    assert set(in_slice) | set(out_of_slice) | set(contracted) == set(features)
    assert boundary_features() == tuple(sorted(features))


def test_prerequisites_follow_the_verdict() -> None:
    for entry in boundary_catalogue():
        if entry.verdict is BoundaryVerdict.CONTRACTED_NOT_WIRED:
            assert entry.prerequisite in PREREQUISITES
        else:
            assert entry.prerequisite == PREREQUISITE_NONE


def test_bet_sizing_and_board_are_out_of_abstraction() -> None:
    assert verdict_for("variable-bet-sizing") is BoundaryVerdict.OUT_OF_ABSTRACTION
    assert verdict_for("public-board") is BoundaryVerdict.OUT_OF_ABSTRACTION
    assert verdict_for("relative-seat-order") is BoundaryVerdict.IN_ABSTRACTION_SLICE
    assert verdict_for("side-pots") is BoundaryVerdict.CONTRACTED_NOT_WIRED


def test_prerequisite_identifiers_resolve_to_real_entry_points() -> None:
    for identifier, (module_name, attribute) in _PREREQUISITE_ENTRY_POINTS.items():
        module = importlib.import_module(module_name)
        assert callable(getattr(module, attribute)), identifier
    assert set(_PREREQUISITE_ENTRY_POINTS) == set(PREREQUISITES)


# ---------------------------------------------------------------- 明确失败


def test_contract_rejects_a_rewritten_verdict() -> None:
    original = boundary_for("public-board")
    rewritten = RuleSliceBoundary(
        feature=original.feature,
        description=original.description,
        verdict=BoundaryVerdict.IN_ABSTRACTION_SLICE,
        prerequisite=PREREQUISITE_NONE,
        declaration=original.declaration,
    )
    entries = tuple(
        rewritten if entry.feature == "public-board" else entry
        for entry in boundary_catalogue()
    )
    # 模型构造期的目录一致性检查由 Pydantic 包装为 ValidationError；构造不可能产出被改写的契约。
    with pytest.raises(ValidationError, match="判定不可改写"):
        RuleBoundaryContract(entries=entries, **_CONTRACT_KWARGS)


def test_contract_rejects_missing_duplicate_or_reordered_entries() -> None:
    catalogue = boundary_catalogue()
    for entries in (
        (),
        catalogue[:-1],
        (*catalogue, catalogue[0]),
        tuple(reversed(catalogue)),
    ):
        with pytest.raises(ValidationError):
            RuleBoundaryContract(entries=entries, **_CONTRACT_KWARGS)


def test_contract_rejects_a_foreign_version_or_basis_or_abstraction() -> None:
    catalogue = boundary_catalogue()
    with pytest.raises(ValidationError):
        RuleBoundaryContract(
            entries=catalogue,
            **{**_CONTRACT_KWARGS, "schema_version": "real-rules-boundary.v2"},
        )
    for override in (
        {"basis": "something-else"},
        {"abstraction_game_id": "other-game"},
        {"abstraction_game_version": "other-version"},
        {"abstraction_player_counts": (2, 3)},
        {"abstraction_ante": 2},
        {"abstraction_bet": 2},
    ):
        with pytest.raises(ValidationError):
            RuleBoundaryContract(entries=catalogue, **{**_CONTRACT_KWARGS, **override})


def test_contract_requires_the_declared_limitations() -> None:
    with pytest.raises(ValidationError):
        RuleBoundaryContract(
            entries=boundary_catalogue(),
            **{**_CONTRACT_KWARGS, "limitations": (REAL_RULES_LIMITATION_NOT_REAL_EV,)},
        )


def test_unknown_feature_or_verdict_fails() -> None:
    with pytest.raises(UnknownBoundaryFeatureError):
        boundary_for("no-such-slice")
    with pytest.raises(RealRulesBoundaryContractError):
        boundary_for(1)  # type: ignore[arg-type]
    with pytest.raises(RealRulesBoundaryContractError):
        features_with("not-a-verdict")


def test_require_in_abstraction_slice_fails_outside_the_slice() -> None:
    entry = require_in_abstraction_slice("relative-seat-order")
    assert entry.verdict is BoundaryVerdict.IN_ABSTRACTION_SLICE
    for feature in ("public-board", "side-pots", "action-line-range-assumption"):
        with pytest.raises(RealRulesBoundaryContractError):
            require_in_abstraction_slice(feature)
    with pytest.raises(UnknownBoundaryFeatureError):
        require_in_abstraction_slice("no-such-slice")


@pytest.mark.parametrize(
    "bad",
    ["Public-Board", "public_board", "app/poker", "public.board", "public board", ""],
)
def test_slice_identifier_must_be_controlled(bad: str) -> None:
    with pytest.raises(ValidationError):
        RuleSliceBoundary(
            feature=bad,
            description="说明",
            verdict=BoundaryVerdict.OUT_OF_ABSTRACTION,
            prerequisite=PREREQUISITE_NONE,
            declaration="声明",
        )


def test_contracted_slice_must_declare_a_known_prerequisite() -> None:
    with pytest.raises(ValidationError, match="必须声明前置标识"):
        RuleSliceBoundary(
            feature="public-board",
            description="说明",
            verdict=BoundaryVerdict.CONTRACTED_NOT_WIRED,
            prerequisite=PREREQUISITE_NONE,
            declaration="声明",
        )
    with pytest.raises(ValidationError):
        RuleSliceBoundary(
            feature="public-board",
            description="说明",
            verdict=BoundaryVerdict.CONTRACTED_NOT_WIRED,
            prerequisite="not-a-prerequisite",
            declaration="声明",
        )


def test_in_slice_entry_must_not_declare_a_prerequisite() -> None:
    with pytest.raises(ValidationError, match="不得声明受控前置标识"):
        RuleSliceBoundary(
            feature="public-board",
            description="说明",
            verdict=BoundaryVerdict.OUT_OF_ABSTRACTION,
            prerequisite="pot-ev-contract",
            declaration="声明",
        )


# ---------------------------------------------------------------- 信息边界


def test_entry_has_no_real_state_input() -> None:
    assert list(inspect.signature(build_rule_boundary_contract).parameters) == []
    assert list(inspect.signature(require_in_abstraction_slice).parameters) == ["feature"]


def test_contract_fields_carry_no_real_state() -> None:
    forbidden = {
        "board",
        "hole_cards",
        "pot",
        "stack",
        "seat",
        "seed",
        "runout",
        "state",
        "bet_sizing",
        "equity",
    }
    assert forbidden.isdisjoint(RuleBoundaryContract.model_fields)
    assert forbidden.isdisjoint(RULE_SLICE_BOUNDARY_FIELDS)


def test_module_only_reuses_the_abstraction_contract() -> None:
    """只复用抽象契约模块的常量，不导入其他应用模块，也不导入离线训练器。"""
    source = inspect.getsource(real_rules_boundary)
    for forbidden in (
        "app.poker",
        "app.analysis",
        "app.storage",
        "app.llm",
        "app.api",
        "tools",
        "range_assumption",
        "pot_ev_contract",
        "position_projection",
        "heuristic",
        "equity",
    ):
        assert forbidden not in source
    assert "from app.strategy.abstraction import" in source


def test_module_has_no_production_caller() -> None:
    app_root = Path(real_rules_boundary.__file__).resolve().parents[1]
    offenders = [
        path.name
        for path in app_root.rglob("*.py")
        if path.name not in {"real_rules_boundary.py", "__init__.py"}
        and "real_rules_boundary" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
