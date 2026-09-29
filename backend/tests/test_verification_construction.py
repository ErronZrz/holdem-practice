"""发牌映射、注入前校验、身份映射、材料校验与构造计划的契约回归。

只做有界单元回归：不跑对局、不生成材料、不写任何工件，也不构成任何质量结论。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.poker.cards import Card, Suit
from app.verification import (
    BASELINE_IDENTIFIER,
    PRECHECK_ITEMS,
    Arm,
    ConstructionCaliber,
    ConstructionInterface,
    ConstructionMapping,
    DealMaterialError,
    HandDeal,
    HandMaterials,
    IdentityMappingError,
    InjectionPrecheckError,
    MaterialEntry,
    MaterialKeyError,
    SeatScope,
    SpecIncompleteError,
    build_arm_construction_plan,
    construction_caliber_digest,
    construction_caliber_payload,
    content_digest,
    deal_for_hand,
    draw_order,
    instantiation_caliber_entries,
    material_key_from_integer,
    plan_by_seat,
    plan_payload,
    precheck_injection,
    precheck_rule_entries,
    probed_seat_style,
    require_baseline_limits,
    require_caliber_matches_spec,
    require_explicit_seed,
    require_identifier_match,
    require_material_key,
    require_materials,
    require_registry_seed_mapping,
    require_same_deal,
    same_deal,
    scope_seats,
)

from .verification_helpers import (
    BASELINE_LABEL,
    DEAL_LABEL,
    DECK_ORDER,
    INDEX_PREFIX,
    NON_PROBED_LABEL,
    UNDER_TEST_IDENTIFIER,
    UNDER_TEST_LABEL,
    baseline_mapping,
    build_fixture,
    conflicting_baseline_caliber,
    construction_caliber,
    deal_spec,
    entries_of,
    replace_entries,
    run_spec,
    under_test_mapping,
)

# ------------------------------------------------------------------ 发牌映射


def test_deal_follows_fixed_assignment() -> None:
    """全零取值等价于不移动任何牌位，可直接核验分配规则本身。"""
    deal = deal_for_hand(deal_spec(), num_players=3, steps=(0,) * 11)
    assert [str(card) for card in deal.hole_cards[0]] == ["2c", "2d"]
    assert [str(card) for card in deal.hole_cards[1]] == ["2h", "2s"]
    assert [str(card) for card in deal.hole_cards[2]] == ["3c", "3d"]
    assert [str(card) for card in deal.board] == ["3h", "3s", "4c", "4d", "4h"]


def test_deal_is_deterministic_for_same_steps() -> None:
    steps = tuple(range(9))
    assert deal_for_hand(deal_spec(), num_players=2, steps=steps) == deal_for_hand(
        deal_spec(), num_players=2, steps=steps
    )


def test_deal_rejects_step_out_of_remaining_range() -> None:
    with pytest.raises(DealMaterialError):
        draw_order(deal_spec(), (0, 1, 51))
    with pytest.raises(DealMaterialError):
        draw_order(deal_spec(), (0, True))


def test_deal_rejects_wrong_step_count() -> None:
    with pytest.raises(DealMaterialError):
        deal_for_hand(deal_spec(), num_players=2, steps=(0,) * 8)
    with pytest.raises(DealMaterialError):
        deal_for_hand(deal_spec(), num_players=2, steps=(0,) * 10)


def test_deal_spec_requires_full_deck_permutation() -> None:
    with pytest.raises(DealMaterialError):
        deal_spec(deck_order=DECK_ORDER[:-1])
    with pytest.raises(DealMaterialError):
        deal_spec(deck_order=(*DECK_ORDER[:-1], DECK_ORDER[0]))
    with pytest.raises(DealMaterialError):
        deal_spec(deck_order=(*DECK_ORDER[:-1], "1x"))
    with pytest.raises(DealMaterialError):
        deal_spec().draw_count(1)


# ------------------------------------------------------------------ 注入前校验


def _valid_deal(num_players: int = 3) -> HandDeal:
    return deal_for_hand(
        deal_spec(), num_players=num_players, steps=tuple(range(2 * num_players + 5))
    )


def test_precheck_items_are_seven_in_fixed_order() -> None:
    assert len(PRECHECK_ITEMS) == 7
    assert [name for _, name in precheck_rule_entries()] == list(PRECHECK_ITEMS)


def test_precheck_accepts_well_formed_deal() -> None:
    deal = _valid_deal()
    precheck_injection(deal, num_players=3, button=2, counterpart=deal)


def _precheck_failure(
    deal: HandDeal,
    *,
    num_players: int = 3,
    button: int = 2,
    counterpart: HandDeal | None = None,
) -> InjectionPrecheckError:
    with pytest.raises(InjectionPrecheckError) as error:
        precheck_injection(
            deal,
            num_players=num_players,
            button=button,
            counterpart=deal if counterpart is None else counterpart,
        )
    return error.value


def test_precheck_requires_complete_seat_coverage() -> None:
    deal = _valid_deal()
    broken = HandDeal(
        hole_cards={0: deal.hole_cards[0], 1: deal.hole_cards[1], 3: deal.hole_cards[2]},
        board=deal.board,
    )
    assert _precheck_failure(broken).item == PRECHECK_ITEMS[0]


def test_precheck_requires_two_hole_cards_per_seat() -> None:
    deal = _valid_deal()
    cards = dict(deal.hole_cards)
    cards[1] = (*cards[1], deal.board[0])
    broken = HandDeal(hole_cards=cards, board=deal.board)
    assert _precheck_failure(broken).item == PRECHECK_ITEMS[1]


def test_precheck_requires_five_board_cards() -> None:
    deal = _valid_deal()
    broken = HandDeal(hole_cards=deal.hole_cards, board=deal.board[:4])
    assert _precheck_failure(broken).item == PRECHECK_ITEMS[2]


def test_precheck_requires_globally_unique_cards() -> None:
    deal = _valid_deal()
    cards = dict(deal.hole_cards)
    cards[0] = (deal.board[0], cards[0][1])
    broken = HandDeal(hole_cards=cards, board=deal.board)
    assert _precheck_failure(broken).item == PRECHECK_ITEMS[3]


def test_precheck_requires_card_objects_within_deck_range() -> None:
    deal = _valid_deal()
    cards = dict(deal.hole_cards)
    cards[0] = ("2c", cards[0][1])
    assert _precheck_failure(HandDeal(hole_cards=cards, board=deal.board)).item == (
        PRECHECK_ITEMS[4]
    )

    cards[0] = (Card(99, Suit.CLUBS), cards[0][1])
    assert _precheck_failure(HandDeal(hole_cards=cards, board=deal.board)).item == (
        PRECHECK_ITEMS[4]
    )


@pytest.mark.parametrize("button", [3, -1, True])
def test_precheck_requires_button_in_range(button: int) -> None:
    assert _precheck_failure(_valid_deal(), button=button).item == PRECHECK_ITEMS[5]


def test_precheck_requires_identical_deal_on_both_arms() -> None:
    deal = _valid_deal()
    other = HandDeal(hole_cards=deal.hole_cards, board=tuple(reversed(deal.board)))
    assert _precheck_failure(deal, counterpart=other).item == PRECHECK_ITEMS[6]


def test_require_same_deal_reports_mismatch() -> None:
    deal = _valid_deal()
    require_same_deal(deal, deal)
    assert same_deal(deal, deal) is True
    with pytest.raises(InjectionPrecheckError):
        require_same_deal(deal, HandDeal(hole_cards={}, board=deal.board))


# ------------------------------------------------------------------ 身份构造映射


def test_material_key_requires_exactly_32_bytes() -> None:
    assert require_material_key(b"\x00" * 32) == b"\x00" * 32
    for value in (b"\x00" * 31, b"\x00" * 33, "x" * 32, bytearray(32), None):
        with pytest.raises(MaterialKeyError):
            require_material_key(value)


def test_material_key_from_integer_covers_32_byte_range() -> None:
    assert material_key_from_integer(0) == b"\x00" * 32
    assert material_key_from_integer((1 << 256) - 1) == b"\xff" * 32
    for value in (-1, 1 << 256, True):
        with pytest.raises(MaterialKeyError):
            material_key_from_integer(value)


def test_explicit_seed_rejects_empty_and_non_integer() -> None:
    assert require_explicit_seed(0) == 0
    assert require_explicit_seed((1 << 64) - 1) == (1 << 64) - 1
    for value in (None, True, "7", 1.0):
        with pytest.raises(IdentityMappingError):
            require_explicit_seed(value)


def test_identifier_match_uses_exact_key_only() -> None:
    """身份选择只做规范标识的精确相等：别名与近似写法都不成立。"""
    mapping = under_test_mapping()
    require_identifier_match(UNDER_TEST_IDENTIFIER, mapping)
    for value in ("mixed-local", "mixedlocal@8", "mixed-local@9", ""):
        with pytest.raises(IdentityMappingError):
            require_identifier_match(value, mapping)


def test_caliber_requires_two_explicit_distinct_sides() -> None:
    """构造口径由调用方显式给出，两侧标识相同或整体缺项都失败。"""
    caliber = construction_caliber()
    assert caliber.baseline.identifier == BASELINE_IDENTIFIER
    assert caliber.under_test.identifier == UNDER_TEST_IDENTIFIER
    with pytest.raises(IdentityMappingError):
        ConstructionCaliber(baseline=baseline_mapping(), under_test=baseline_mapping())
    with pytest.raises(ValidationError):
        ConstructionCaliber.model_validate({})


def test_mapping_requires_scope_only_when_summary_is_needed() -> None:
    with pytest.raises(SpecIncompleteError):
        ConstructionMapping(
            identifier="probe@1",
            interface=ConstructionInterface.MATERIAL_KEY,
            requires_public_summary=True,
        )
    with pytest.raises(SpecIncompleteError):
        ConstructionMapping(
            identifier="probe@2",
            interface=ConstructionInterface.REGISTRY_SEED,
            requires_public_summary=False,
            seat_scope=SeatScope.ALL_SEATS,
        )
    with pytest.raises(SpecIncompleteError):
        ConstructionMapping(
            identifier="   ",
            interface=ConstructionInterface.REGISTRY_SEED,
            requires_public_summary=False,
        )


# ------------------------------------------------------------------ 材料结构


def test_material_entry_rejects_ill_formed_values() -> None:
    with pytest.raises(SpecIncompleteError):
        MaterialEntry(purpose_label="  ", index_key=("a",), value=1)
    with pytest.raises(SpecIncompleteError):
        MaterialEntry(purpose_label=DEAL_LABEL, index_key=(), value=1)
    with pytest.raises(SpecIncompleteError):
        MaterialEntry(purpose_label=DEAL_LABEL, index_key=("  ",), value=1)
    with pytest.raises(SpecIncompleteError):
        MaterialEntry(purpose_label=DEAL_LABEL, index_key=("a",), value=-1)
    with pytest.raises(SpecIncompleteError):
        MaterialEntry(purpose_label=DEAL_LABEL, index_key=("a",), value=True)


def test_hand_materials_reject_ill_formed_hand() -> None:
    entry = MaterialEntry(purpose_label=DEAL_LABEL, index_key=("a",), value=1)
    with pytest.raises(SpecIncompleteError):
        HandMaterials(hand_ordinal=0, entries=(entry,))
    with pytest.raises(SpecIncompleteError):
        HandMaterials(hand_ordinal=1, entries=())
    with pytest.raises(SpecIncompleteError):
        HandMaterials(hand_ordinal=1, entries=(entry, entry))


# ------------------------------------------------------------------ 材料一致性


def test_require_materials_accepts_fixture_bundle() -> None:
    fixture = build_fixture(hands=2)
    require_materials(fixture.spec, fixture.bundle)


def test_require_materials_requires_matching_hand_count() -> None:
    fixture = build_fixture(hands=2)
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, fixture.bundle[:1])
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, (*fixture.bundle, fixture.bundle[0]))


def test_require_materials_requires_matching_hand_ordinal() -> None:
    fixture = build_fixture()
    renamed = HandMaterials(
        hand_ordinal=fixture.bundle[0].hand_ordinal + 1, entries=fixture.bundle[0].entries
    )
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, (renamed,))


def test_require_materials_rejects_undeclared_purpose_label() -> None:
    fixture = build_fixture()
    entries = entries_of(fixture.bundle, 0)
    entries[0] = MaterialEntry(
        purpose_label="unknown-purpose",
        index_key=entries[0].index_key,
        value=entries[0].value,
    )
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, replace_entries(fixture.bundle, 0, entries))


def test_require_materials_requires_full_deal_material() -> None:
    fixture = build_fixture()
    entries = entries_of(fixture.bundle, 0)
    with pytest.raises(SpecIncompleteError):
        require_materials(
            fixture.spec, replace_entries(fixture.bundle, 0, entries[1:])
        )


def test_require_materials_requires_contiguous_draw_index() -> None:
    fixture = build_fixture()
    entries = entries_of(fixture.bundle, 0)
    last = entries[10]
    entries[10] = MaterialEntry(
        purpose_label=last.purpose_label,
        index_key=(*last.index_key[:-1], "99"),
        value=last.value,
    )
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, replace_entries(fixture.bundle, 0, entries))


def test_require_materials_checks_deal_value_domain() -> None:
    fixture = build_fixture()
    entries = entries_of(fixture.bundle, 0)
    last = entries[10]
    entries[10] = MaterialEntry(
        purpose_label=last.purpose_label, index_key=last.index_key, value=60
    )
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, replace_entries(fixture.bundle, 0, entries))


def test_require_materials_checks_index_key_length() -> None:
    fixture = build_fixture()
    entries = entries_of(fixture.bundle, 0)
    index = next(
        position
        for position, entry in enumerate(entries)
        if entry.purpose_label == NON_PROBED_LABEL
    )
    entries[index] = MaterialEntry(
        purpose_label=NON_PROBED_LABEL,
        index_key=INDEX_PREFIX,
        value=entries[index].value,
    )
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, replace_entries(fixture.bundle, 0, entries))


def test_require_materials_requires_single_value_per_hand_purpose() -> None:
    fixture = build_fixture()
    entries = entries_of(fixture.bundle, 0)
    entries.append(
        MaterialEntry(
            purpose_label=BASELINE_LABEL, index_key=("cfg", "b1", "extra"), value=1
        )
    )
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, replace_entries(fixture.bundle, 0, entries))


def test_require_materials_checks_single_value_domain() -> None:
    fixture = build_fixture()
    entries = entries_of(fixture.bundle, 0)
    index = next(
        position
        for position, entry in enumerate(entries)
        if entry.purpose_label == UNDER_TEST_LABEL
    )
    entries[index] = MaterialEntry(
        purpose_label=UNDER_TEST_LABEL, index_key=entries[index].index_key, value=1 << 256
    )
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, replace_entries(fixture.bundle, 0, entries))


def test_require_materials_requires_seat_coverage() -> None:
    fixture = build_fixture()
    entries = entries_of(fixture.bundle, 0)
    index = next(
        position
        for position, entry in enumerate(entries)
        if entry.purpose_label == NON_PROBED_LABEL and entry.index_key[-1] == "2"
    )
    entries[index] = MaterialEntry(
        purpose_label=NON_PROBED_LABEL,
        index_key=(*INDEX_PREFIX, "1", "5"),
        value=entries[index].value,
    )
    with pytest.raises(SpecIncompleteError):
        require_materials(fixture.spec, replace_entries(fixture.bundle, 0, entries))


# ------------------------------------------------------------------ 构造计划


def test_seat_scope_decides_probed_seat_style() -> None:
    assert scope_seats(SeatScope.PROBED_SEAT_ONLY, num_players=3, probed_seat=1) == (1,)
    assert scope_seats(SeatScope.ALL_SEATS, num_players=3, probed_seat=1) == (0, 1, 2)
    assert probed_seat_style(SeatScope.PROBED_SEAT_ONLY, num_players=3, probed_seat=1) == "tight"
    assert probed_seat_style(SeatScope.ALL_SEATS, num_players=3, probed_seat=1) == "aggressive"


def test_construction_plan_covers_every_seat() -> None:
    fixture = build_fixture(num_players=3, probed_seat=1)
    under_test = build_arm_construction_plan(
        fixture.spec,
        fixture.caliber,
        Arm.UNDER_TEST,
        fixture.spec.schedule[0],
        fixture.bundle[0],
    )
    assert sorted(plan_by_seat(under_test)) == [0, 1, 2]
    assert under_test.summary_seats == (1,)
    assert under_test.summary_scope == (1,)
    assert under_test.probed_seat_style == "tight"
    assert plan_by_seat(under_test)[0].identifier == BASELINE_IDENTIFIER
    probed = under_test.entry_for(1)
    assert probed.identifier == UNDER_TEST_IDENTIFIER
    assert probed.interface is ConstructionInterface.MATERIAL_KEY
    assert probed.material.purpose_label == UNDER_TEST_LABEL

    baseline = build_arm_construction_plan(
        fixture.spec,
        fixture.caliber,
        Arm.BASELINE,
        fixture.spec.schedule[0],
        fixture.bundle[0],
    )
    assert baseline.summary_seats == ()
    assert baseline.summary_scope == ()
    assert baseline.probed_seat_style is None
    baseline_probed = baseline.entry_for(1)
    assert baseline_probed.identifier == BASELINE_IDENTIFIER
    assert baseline_probed.material.purpose_label == BASELINE_LABEL


def test_construction_plan_carries_all_seats_scope() -> None:
    caliber = construction_caliber(SeatScope.ALL_SEATS, identifier="mixed-local@7")
    spec = run_spec(num_players=3, probed_seat=1, under_test_identifier="mixed-local@7")
    fixture = build_fixture(num_players=3, probed_seat=1)
    plan = build_arm_construction_plan(
        spec, caliber, Arm.UNDER_TEST, spec.schedule[0], fixture.bundle[0]
    )
    assert plan.summary_scope == (0, 1, 2)
    assert plan.probed_seat_style == "aggressive"


def test_construction_plan_requires_matching_identifier() -> None:
    """规格里的标识与显式构造口径不一致时，构造计划即失败。"""
    fixture = build_fixture()
    mismatched = run_spec(num_players=3, probed_seat=1, under_test_identifier="absent@1")
    with pytest.raises(IdentityMappingError):
        build_arm_construction_plan(
            mismatched,
            fixture.caliber,
            Arm.UNDER_TEST,
            mismatched.schedule[0],
            fixture.bundle[0],
        )


def test_run_spec_rejects_non_single_baseline() -> None:
    # 基线标识被硬限定为单一基线身份：规格阶段即失败，不接受任意受控标识。
    with pytest.raises(SpecIncompleteError):
        run_spec(baseline_identifier="mixed-local@7")
    with pytest.raises(SpecIncompleteError):
        run_spec(baseline_identifier="random@1")


def test_construction_plan_requires_registry_seed_baseline() -> None:
    key_baseline = ConstructionMapping(
        identifier=BASELINE_IDENTIFIER,
        interface=ConstructionInterface.MATERIAL_KEY,
        requires_public_summary=True,
        seat_scope=SeatScope.PROBED_SEAT_ONLY,
    )
    with pytest.raises(IdentityMappingError):
        require_registry_seed_mapping(key_baseline)
    with pytest.raises(IdentityMappingError):
        ConstructionCaliber(baseline=key_baseline, under_test=under_test_mapping())
    assert require_registry_seed_mapping(baseline_mapping()) is not None


def test_baseline_limits_cover_all_three_constraints() -> None:
    """基线口径的接口、公开摘要与座位范围三项约束必须同时成立。"""
    assert require_baseline_limits(baseline_mapping()).identifier == BASELINE_IDENTIFIER
    with pytest.raises(IdentityMappingError):
        require_baseline_limits(
            ConstructionMapping(
                identifier=BASELINE_IDENTIFIER,
                interface=ConstructionInterface.MATERIAL_KEY,
                requires_public_summary=False,
            )
        )
    with pytest.raises(IdentityMappingError):
        require_baseline_limits(
            ConstructionMapping(
                identifier=BASELINE_IDENTIFIER,
                interface=ConstructionInterface.REGISTRY_SEED,
                requires_public_summary=True,
                seat_scope=SeatScope.PROBED_SEAT_ONLY,
            )
        )
    # 主链入口与模型校验同时生效：绕过模型校验的对象也会在入口被拦下。
    with pytest.raises(IdentityMappingError):
        require_caliber_matches_spec(run_spec(), conflicting_baseline_caliber())


def test_construction_plan_rejects_conflicting_baseline_caliber() -> None:
    """与基线约束冲突的口径即便绕过模型校验，构造计划入口仍会硬失败。"""
    fixture = build_fixture()
    conflicting = conflicting_baseline_caliber()
    with pytest.raises(IdentityMappingError):
        build_arm_construction_plan(
            fixture.spec,
            conflicting,
            Arm.UNDER_TEST,
            fixture.spec.schedule[0],
            fixture.bundle[0],
        )
    with pytest.raises(IdentityMappingError):
        plan_payload(spec=fixture.spec, caliber=conflicting, bundle=fixture.bundle)


def test_caliber_content_decides_construction_plan_digest() -> None:
    """构造口径的内容不同，则由它唯一确定的构造计划摘要必然不同。"""
    fixture = build_fixture()
    other = construction_caliber(SeatScope.ALL_SEATS)
    algorithm = fixture.spec.protocol.digest_algorithm
    assert construction_caliber_digest(
        spec=fixture.spec, caliber=fixture.caliber, bundle=fixture.bundle,
        algorithm=algorithm,
    ) != construction_caliber_digest(
        spec=fixture.spec, caliber=other, bundle=fixture.bundle, algorithm=algorithm
    )


def test_baseline_execution_caliber_comes_from_strategy_code() -> None:
    """基线执行口径取自策略代码的只读属性：位置、参数布局、有效取值与代码载荷摘要。"""
    fixture = build_fixture()
    algorithm = fixture.spec.protocol.digest_algorithm
    entries = dict(
        instantiation_caliber_entries(
            spec=fixture.spec,
            caliber=fixture.caliber,
            bundle=fixture.bundle,
            algorithm=algorithm,
        )
    )
    assert entries["baseline-registry-location"] == "app.strategy.registry.create_strategy"
    assert entries["baseline-entry-point"].endswith("HeuristicStrategy.__init__")
    assert "samples" in entries["baseline-parameter-layout"]
    assert entries["baseline-effective-samples"] == "500"
    assert entries["baseline-effective-bluff-freq"] == "0.1"
    assert entries["baseline-effective-seed"] == "none"
    assert len(entries["baseline-entry-code-digest"]) == 64
    assert entries["baseline-requires-public-summary"] == "false"
    assert entries["baseline-seat-scope"] == "none"


def test_caliber_payload_carries_baseline_execution_binding() -> None:
    """基线执行口径进入构造口径载荷，因此也进入第十项内容摘要。"""
    fixture = build_fixture()
    algorithm = fixture.spec.protocol.digest_algorithm
    payload = construction_caliber_payload(
        spec=fixture.spec,
        caliber=fixture.caliber,
        bundle=fixture.bundle,
        algorithm=algorithm,
    )
    execution = payload["baseline_execution"]
    assert execution["registry_location"] == "app.strategy.registry.create_strategy"
    defaults = execution["entry_point"]["positional_defaults"]
    assert defaults["samples"] == 500
    assert defaults["bluff_freq"] == 0.1
    layout = execution["entry_point"]["code"]["parameter_layout"]
    assert layout["positional_or_keyword"] == 4
    assert execution["entry_point"]["code"]["code"]
    without_execution = {
        key: value for key, value in payload.items() if key != "baseline_execution"
    }
    assert content_digest(without_execution, algorithm=algorithm) != construction_caliber_digest(
        spec=fixture.spec,
        caliber=fixture.caliber,
        bundle=fixture.bundle,
        algorithm=algorithm,
    )
