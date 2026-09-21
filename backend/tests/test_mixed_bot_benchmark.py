"""新 Bot 验证入口的回归与显式 opt-in 运行。

默认整轮测试只做有界核对：冻结配方的节点与不变量、清单门禁、报告门禁。
不跑成本矩阵、不跑对抗对局、不收集完整分布矩阵。

显式 opt-in（需要自备已冻结清单与空输出目录）：

    HOLDEM_MIXED_BENCHMARK=1 HOLDEM_MIXED_MANIFEST=<清单路径> \\
        HOLDEM_MIXED_OUTPUT=<空目录> HOLDEM_MIXED_STAGE=A \\
        uv run pytest -q -s tests/test_mixed_bot_benchmark.py
"""

import json
import os

import pytest

from app.poker.evaluator import evaluate_fast
from app.poker.state import Street
from app.strategy.mixed_policy import MixedStyle
from app.strategy.mixed_strategy import MixedLocalStrategy

from .mixed_bot_states import (
    MIXED_APPLICABLE_NODE_COUNT,
    MIXED_CATEGORY_IDS,
    MIXED_CATEGORY_STREET,
    MIXED_PLANNED_SLOT_COUNT,
    MIXED_PLAYER_COUNTS,
    MIXED_STREETS,
    MIXED_STRUCTURAL_HOLE_CATEGORIES,
    MIXED_STRUCTURAL_HOLE_COUNT,
    MixedFixtureManifest,
    MixedNodeFixture,
    MixedPublicAction,
    applicable_player_counts,
    apply_node,
    build_frozen_nodes,
    build_node,
    iter_planned_slots,
    planned_slots_by_category,
    structurally_not_applicable,
)
from .mixed_bot_validation import (
    ADVERSARIAL_ARMS,
    ADVERSARIAL_HANDS,
    ADVERSARIAL_MAX_VOLUNTARY_ACTIONS,
    ADVERSARIAL_OPPONENT_FAMILIES,
    BEHAVIOR_SMOKE_NODE_LIMIT,
    COST_CELLS_PER_PLAYER_COUNT,
    COST_DECISIONS_PER_PLAYER_COUNT,
    MIXED_DIRECT_DISTRIBUTION_COUNT,
    MIXED_MAIN_SEEDS,
    STAGE_A_ADVERSARIAL_HANDS,
    STAGE_A_COST_SAMPLES,
    SUPPLEMENTARY_TOTAL_SAMPLES,
    MixedValidationAuthorizationError,
    adversarial_schedule,
    cell_quota,
    collect_behavior,
    cost_cells,
    fixture_at_depth,
    frozen_manifest,
    prepare_output_dir,
    require_stage_permission,
    run_adversarial_batch,
    run_validation,
    usable_at_depth,
)

_ENV_SWITCH = "HOLDEM_MIXED_BENCHMARK"
_ENV_MANIFEST = "HOLDEM_MIXED_MANIFEST"
_ENV_OUTPUT = "HOLDEM_MIXED_OUTPUT"
_ENV_STAGE = "HOLDEM_MIXED_STAGE"


def _hu_fixture(**overrides: object) -> MixedNodeFixture:
    payload: dict[str, object] = {
        "node_id": "hu-unopened-open",
        "category": "unopened-open",
        "player_count": 2,
        "button": 0,
        "starting_stack": 1000,
        "hole_cards": (("As", "Kh"), ("2c", "2d")),
        "decision_street": Street.PREFLOP,
    }
    payload.update(overrides)
    return MixedNodeFixture(**payload)  # type: ignore[arg-type]


def _manifest(nodes: tuple[MixedNodeFixture, ...]) -> MixedFixtureManifest:
    return MixedFixtureManifest(
        strategy_id="mixed-local@1",
        code_identity="test-code-identity",
        config_digest="test-config-digest",
        seeds=MIXED_MAIN_SEEDS,
        nodes=nodes,
        scenario_order="按类别顺序 × 人数升序",
        seed_derivation="牌堆流不含焦点 arm 或人格",
        stage_plan=("阶段 A：有界标定", "阶段 B：剩余正式矩阵"),
        resource_envelope=("单进程 RSS ≤ 1GiB",),
        stop_conditions=("超预算立即停止并保留样本",),
        output_dir="/tmp/test-output",
        report_format="mixed-validation.v1",
    )


@pytest.fixture(scope="module")
def frozen() -> MixedFixtureManifest:
    """完整冻结清单：模块内只生成一次，供配方与摘要核对复用。"""
    return frozen_manifest(code_identity="test-code-identity", output_dir="/tmp/test-output")


# ------------------------------------------------------------------ 设计核对


def test_planned_slots_match_the_frozen_matrix() -> None:
    assert MIXED_APPLICABLE_NODE_COUNT == 125
    assert MIXED_STRUCTURAL_HOLE_COUNT == 3
    assert MIXED_PLANNED_SLOT_COUNT == 128
    assert len(tuple(iter_planned_slots())) == MIXED_PLANNED_SLOT_COUNT
    assert MIXED_DIRECT_DISTRIBUTION_COUNT == 1125


def test_structural_holes_are_exactly_the_declared_three() -> None:
    holes = {
        category
        for category in MIXED_CATEGORY_IDS
        for count in structurally_not_applicable(category)
        if count == 2
    }
    assert holes == set(MIXED_STRUCTURAL_HOLE_CATEGORIES)
    for category in MIXED_STRUCTURAL_HOLE_CATEGORIES:
        assert applicable_player_counts(category) == (3, 4, 5, 6, 7, 8, 9)
    assert all(
        len(planned_slots_by_category(category)) == len(MIXED_PLAYER_COUNTS)
        for category in MIXED_CATEGORY_IDS
    )


def test_cost_cells_and_quotas_cover_the_declared_totals() -> None:
    cells = cost_cells()
    assert len(cells) == COST_CELLS_PER_PLAYER_COUNT
    assert len(set(cells)) == COST_CELLS_PER_PLAYER_COUNT
    assert sum(cell_quota(index) for index in range(len(cells))) == COST_DECISIONS_PER_PLAYER_COUNT
    assert [cell_quota(index) for index in range(28)] == [278] * 28
    assert [cell_quota(index) for index in range(28, 36)] == [277] * 8


def test_supplementary_and_adversarial_totals() -> None:
    assert SUPPLEMENTARY_TOTAL_SAMPLES == 240
    assert ADVERSARIAL_HANDS == 4224
    assert ADVERSARIAL_MAX_VOLUNTARY_ACTIONS == 256
    assert len(ADVERSARIAL_OPPONENT_FAMILIES) == 4
    assert len(ADVERSARIAL_ARMS) == 2


def test_adversarial_schedules_are_bounded_and_paired() -> None:
    stage_a = adversarial_schedule("A")
    assert len(stage_a) == STAGE_A_ADVERSARIAL_HANDS
    assert {entry[0] for entry in stage_a} == {MIXED_MAIN_SEEDS[0]}
    assert {entry[1] for entry in stage_a} == {MixedStyle.TIGHT}
    assert {entry[5] for entry in stage_a} == {0}
    full = adversarial_schedule("B")
    assert len(full) == ADVERSARIAL_HANDS
    # 两个 arm 使用同一牌堆派生流，因此同格的其余关键字段必须成对出现。
    mixed = {(e[0], e[1], e[2], e[4], e[5]) for e in full if e[3] == "mixed-focus"}
    legacy = {(e[0], e[1], e[2], e[4], e[5]) for e in full if e[3] == "legacy-focus"}
    assert mixed == legacy


def test_stage_a_cost_sample_target_matches_one_cell_per_configuration() -> None:
    assert len(cost_cells()) * len(MIXED_PLAYER_COUNTS) == STAGE_A_COST_SAMPLES


# ------------------------------------------------------------------ 配方与清单


def test_frozen_nodes_cover_every_planned_slot(frozen: MixedFixtureManifest) -> None:
    assert len(frozen.nodes) == MIXED_APPLICABLE_NODE_COUNT
    pairs = {(node.category, node.player_count) for node in frozen.nodes}
    assert len(pairs) == MIXED_APPLICABLE_NODE_COUNT
    for category in MIXED_CATEGORY_IDS:
        for count in applicable_player_counts(category):
            assert (category, count) in pairs
    # 每个价格与每条街都必须有人数覆盖，否则成本矩阵会出现空洞。
    for count in MIXED_PLAYER_COUNTS:
        streets = {node.decision_street for node in frozen.nodes if node.player_count == count}
        assert streets == set(MIXED_STREETS)


def test_frozen_node_category_order_matches_the_inventory(frozen: MixedFixtureManifest) -> None:
    order = [node.category for node in frozen.nodes]
    assert order == list(MIXED_CATEGORY_IDS) or order == sorted(
        order, key=lambda name: MIXED_CATEGORY_IDS.index(name)
    )
    for node in frozen.nodes:
        assert node.decision_street is MIXED_CATEGORY_STREET[node.category]


def test_frozen_nodes_replay_cleanly(frozen: MixedFixtureManifest) -> None:
    for node in frozen.nodes:
        applied = apply_node(node)
        legal = applied.legal_actions()
        assert (
            legal.can_fold
            or legal.can_check
            or legal.can_call
            or legal.can_bet
            or legal.can_raise
        ), node.node_id
        assert applied.engine.street is node.decision_street
        assert not (legal.can_check and legal.can_call), node.node_id
        assert not (legal.can_bet and legal.can_raise), node.node_id


def test_frozen_node_cards_are_disjoint(frozen: MixedFixtureManifest) -> None:
    for node in frozen.nodes:
        cards = [*node.board, *(token for pair in node.hole_cards for token in pair)]
        assert len(set(cards)) == len(cards), node.node_id
        assert len(node.board) == {
            Street.PREFLOP: 0,
            Street.FLOP: 3,
            Street.TURN: 4,
            Street.RIVER: 5,
        }[node.decision_street]


def test_category_specific_invariants_hold(frozen: MixedFixtureManifest) -> None:
    """按类别核对配方确实构造出了它声称的局面，而不是只生成了合法牌局。"""
    for node in frozen.nodes:
        applied = apply_node(node)
        engine = applied.engine
        legal = applied.legal_actions()
        actor = engine.players[engine.current_seat]
        opponents = [p for p in engine.players if p.seat != actor.seat]
        if node.category == "short-stack-call":
            assert legal.is_short_all_in_call, node.node_id
            assert legal.actual_call_amount < legal.call_amount, node.node_id
        elif node.category == "incomplete-raise":
            assert not legal.can_raise, node.node_id
            assert legal.call_amount > 0, node.node_id
        elif node.category == "one-side-all-in":
            assert sum(1 for p in opponents if p.all_in) == 1, node.node_id
            assert any(not p.folded and not p.all_in for p in opponents), node.node_id
        elif node.category == "free-check":
            assert legal.can_check and legal.call_amount == 0, node.node_id
        elif node.category == "shared-board":
            hero = evaluate_fast([*actor.hole_cards, *engine.board])
            board = evaluate_fast(list(engine.board))
            assert hero == board, node.node_id


def test_frozen_nodes_are_deterministic(frozen: MixedFixtureManifest) -> None:
    again = build_frozen_nodes()
    assert [node.model_dump() for node in again] == [node.model_dump() for node in frozen.nodes]


def test_frozen_manifest_digest_is_stable(frozen: MixedFixtureManifest) -> None:
    assert len(frozen.digest()) == 64
    other = frozen_manifest(code_identity="another-identity", output_dir="/tmp/test-output")
    assert other.digest() != frozen.digest()
    assert frozen.seeds == MIXED_MAIN_SEEDS
    assert frozen.stage_plan and frozen.resource_envelope and frozen.stop_conditions
    assert frozen.output_dir and frozen.report_format


def test_depth_scaling_rules(frozen: MixedFixtureManifest) -> None:
    scalable = next(node for node in frozen.nodes if node.depth_scalable)
    scaled = fixture_at_depth(scalable, 15)
    assert scaled.starting_stack == 150
    assert all(stack == 150 for stack in scaled.stacks)
    assert usable_at_depth(scalable, 15) and usable_at_depth(scalable, 1000)
    fixed = next(node for node in frozen.nodes if not node.depth_scalable)
    assert not usable_at_depth(fixed, 15)
    assert usable_at_depth(fixed, 100)
    assert fixture_at_depth(fixed, 1000) is fixed
    assert {node.category for node in frozen.nodes if not node.depth_scalable} == {
        "short-stack-call",
        "incomplete-raise",
        "one-side-all-in",
    }


# ------------------------------------------------------------------ 门禁核对


def test_stage_gate_refuses_without_explicit_permission() -> None:
    manifest = _manifest((_hu_fixture(),))
    with pytest.raises(MixedValidationAuthorizationError):
        run_validation(manifest=manifest, stage="A", allow_stage=None)
    with pytest.raises(MixedValidationAuthorizationError):
        run_validation(manifest=manifest, stage="A", allow_stage="B")
    with pytest.raises(MixedValidationAuthorizationError):
        run_validation(manifest=None, stage="A", allow_stage="A")


def test_stage_gate_refuses_an_incomplete_manifest() -> None:
    incomplete = MixedFixtureManifest(
        strategy_id="mixed-local@1",
        code_identity="test-code-identity",
        config_digest="test-config-digest",
        seeds=MIXED_MAIN_SEEDS,
        nodes=(_hu_fixture(),),
    )
    with pytest.raises(MixedValidationAuthorizationError):
        require_stage_permission(stage="A", allow_stage="A", manifest=incomplete)


def test_stage_b_requires_a_completed_stage_a_receipt() -> None:
    manifest = _manifest((_hu_fixture(),))
    with pytest.raises(MixedValidationAuthorizationError):
        require_stage_permission(
            stage="B", allow_stage="B", manifest=manifest, stage_a_receipt=None
        )


def test_eval_runs_are_refused_by_default() -> None:
    with pytest.raises(MixedValidationAuthorizationError):
        run_adversarial_batch(stage="A")
    with pytest.raises(MixedValidationAuthorizationError):
        collect_behavior(_manifest(tuple(build_frozen_nodes()[: BEHAVIOR_SMOKE_NODE_LIMIT + 1])))


def test_output_directory_is_never_overwritten(tmp_path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "existing.json").write_text("{}", encoding="utf-8")
    with pytest.raises(MixedValidationAuthorizationError):
        prepare_output_dir(str(occupied))
    empty = tmp_path / "empty"
    empty.mkdir()
    assert prepare_output_dir(str(empty)) == str(empty)
    assert prepare_output_dir(None) is None


def test_node_rejects_structurally_inapplicable_player_count() -> None:
    with pytest.raises(ValueError):
        _hu_fixture(category="incomplete-raise", player_count=2)
    with pytest.raises(ValueError):
        build_node("incomplete-raise", 2)


def test_node_rejects_unknown_category() -> None:
    with pytest.raises(ValueError):
        _hu_fixture(category="not-a-category")


def test_node_rejects_board_length_mismatch() -> None:
    with pytest.raises(ValueError):
        _hu_fixture(decision_street=Street.FLOP)


# ------------------------------------------------------------------ 回放与行为


def test_apply_node_replays_a_preflop_node() -> None:
    applied = apply_node(_hu_fixture())
    assert applied.engine.street is Street.PREFLOP
    assert applied.tracker.active is True
    assert applied.tracker.hand_number == 1
    action = MixedLocalStrategy(seed=MIXED_MAIN_SEEDS[0], bot_seats=(0, 1)).choose_action(
        applied.actor_state(), applied.legal_actions()
    )
    assert action.type.name.lower() in {"fold", "check", "call", "bet", "raise"}


def test_apply_node_replays_a_postflop_node() -> None:
    fixture = _hu_fixture(
        node_id="hu-flop-draw",
        category="flop-draw",
        hole_cards=(("As", "Ks"), ("2c", "2d")),
        board=("Qs", "7s", "2h"),
        decision_street=Street.FLOP,
        actions=(
            MixedPublicAction(street=Street.PREFLOP, seat=0, action="call", amount=0),
            MixedPublicAction(street=Street.PREFLOP, seat=1, action="check", amount=0),
        ),
    )
    applied = apply_node(fixture)
    assert applied.engine.street is Street.FLOP
    assert len(applied.engine.board) == 3


def test_apply_node_rejects_actions_that_end_the_hand() -> None:
    fixture = _hu_fixture(
        node_id="hu-ended",
        actions=(MixedPublicAction(street=Street.PREFLOP, seat=0, action="fold", amount=0),),
    )
    with pytest.raises(ValueError):
        apply_node(fixture)


def test_behavior_collection_smoke_is_bounded_and_labelled() -> None:
    fixture = build_node("unopened-open", 2)
    behavior = collect_behavior(_manifest((fixture,)))
    assert behavior.direct_distributions == 9
    assert {row.style for row in behavior.styles} == {style.value for style in MixedStyle}
    assert all(row.distributions == 3 for row in behavior.styles)


# ------------------------------------------------------------------ 显式 opt-in


@pytest.mark.skipif(
    os.environ.get(_ENV_SWITCH) != "1",
    reason="离线验证阶段是显式 opt-in：需设置 HOLDEM_MIXED_BENCHMARK=1 与清单/输出目录",
)
def test_run_validation_stage_opt_in() -> None:
    manifest_path = os.environ[_ENV_MANIFEST]
    output_dir = os.environ[_ENV_OUTPUT]
    stage = os.environ.get(_ENV_STAGE, "A")
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = MixedFixtureManifest.model_validate(json.load(handle))
    report = run_validation(
        manifest=manifest,
        stage=stage,  # type: ignore[arg-type]
        allow_stage=stage,
        output_dir=output_dir,
    )
    print(report.model_dump_json(indent=2))
    assert report.status.startswith(("completed", "stopped-"))
