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
from dataclasses import asdict

import pytest

from app.poker.actions import ActionType
from app.poker.evaluator import evaluate_fast
from app.poker.state import Street
from app.strategy.mixed_policy import (
    MIXED_DISTRIBUTION_UNITS,
    MIXED_LOCAL_V2_RULES,
    MixedStyle,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
    MIXED_STRATEGY_IDENTIFIER_V4,
    MIXED_STRATEGY_IDENTIFIER_V5,
    MIXED_STRATEGY_IDENTIFIERS,
    MixedLocalStrategy,
    MixedStrategyError,
    rules_for_identifier,
)

from . import mixed_bot_recheck
from . import mixed_bot_validation as validation
from .mixed_bot_recheck import (
    MixedRecheckError,
    aggregate_matches,
    compare_net_chips,
    recheck,
)
from .mixed_bot_states import (
    MIXED_APPLICABLE_NODE_COUNT,
    MIXED_BIG_BLIND,
    MIXED_CATEGORY_IDS,
    MIXED_CATEGORY_STREET,
    MIXED_DEPTHS_BB,
    MIXED_PLANNED_SLOT_COUNT,
    MIXED_PLAYER_COUNTS,
    MIXED_STREETS,
    MIXED_STRUCTURAL_HOLE_CATEGORIES,
    MIXED_STRUCTURAL_HOLE_COUNT,
    MixedFixtureError,
    MixedFixtureManifest,
    MixedNodeFixture,
    MixedPublicAction,
    applicable_player_counts,
    apply_node,
    build_frozen_nodes,
    build_node,
    iter_planned_slots,
    manifest_json,
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
    DIGEST_RULE_FIELDS,
    MIXED_DIRECT_DISTRIBUTION_COUNT,
    MIXED_MAIN_SEEDS,
    STAGE_A0_COST_SAMPLES,
    STAGE_A_ADVERSARIAL_HANDS,
    STAGE_A_COST_SAMPLES,
    STAGE_A_SUPPLEMENTARY_SAMPLES,
    SUPPLEMENTARY_TOTAL_SAMPLES,
    HandOutcome,
    MixedMatchFamilyRow,
    MixedValidationAuthorizationError,
    adversarial_schedule,
    cell_quota,
    collect_behavior,
    config_digest,
    cost_cells,
    fixture_at_depth,
    frozen_manifest,
    js_distance,
    matches_from_tally,
    peak_rss_bytes,
    prepare_output_dir,
    require_stage_permission,
    run_adversarial_batch,
    run_validation,
    strategy_rules,
    supplementary_plan,
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


def _manifest(
    nodes: tuple[MixedNodeFixture, ...],
    *,
    strategy_id: str = MIXED_STRATEGY_IDENTIFIER,
) -> MixedFixtureManifest:
    return MixedFixtureManifest(
        strategy_id=strategy_id,
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


# ------------------------------------------------------------------ 身份驱动


def test_first_version_config_digest_is_pinned() -> None:
    """首版配置摘要与已签收清单逐字绑定，任何改写都会在这里失败。"""
    assert (
        config_digest()
        == "bfe231419ecc31e54e9b73aaa16421026cc2392a21516ddb44e6a629936d1484"
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER) == config_digest()


def test_second_version_gets_its_own_config_digest() -> None:
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V2) != config_digest()


def test_second_version_config_digest_is_pinned() -> None:
    """第二版取摘要必须逐字等于已签收清单里的取值。"""
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V2)
        == "338a4863a68ca10eda44dcfdfdf26e510a4560cf8f7bbd1f97f048bc6ff6e794"
    )


def test_third_version_config_digest_is_pinned() -> None:
    """第三版取摘要同样钉死，它将来会被自己的标定回执引用。"""
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V3)
        == "5ed7992b36de67cc97b4035f075d2c563f989300b448c5878f31847eb001643f"
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V3) != config_digest(
        MIXED_STRATEGY_IDENTIFIER_V2
    )


def test_fourth_version_config_digest_is_pinned() -> None:
    """第四版取摘要同样钉死：它将来会被自己的标定回执引用。"""
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V4)
        == "52b03d5db65d92e3d0ee7a987a7f45169ff868e4273af4dd2ac8538772fb481d"
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V4) != config_digest(
        MIXED_STRATEGY_IDENTIFIER_V3
    )


def test_fifth_version_config_digest_is_pinned() -> None:
    """第五版取摘要同样钉死：它将来会被自己的标定回执引用。"""
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V5)
        == "8896013bbcd873cd493c6319756c353365b49cc7b4e846e927c4216d6d1f82f2"
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V5) != config_digest(
        MIXED_STRATEGY_IDENTIFIER_V4
    )


def test_digest_fields_are_registered_per_identity() -> None:
    """每个身份的摘要字段都按身份登记，且字段名必须是该身份规则对象里的真实字段。"""
    assert set(DIGEST_RULE_FIELDS) <= set(MIXED_STRATEGY_IDENTIFIERS)
    assert MIXED_STRATEGY_IDENTIFIER not in DIGEST_RULE_FIELDS
    for identifier, fields in DIGEST_RULE_FIELDS.items():
        rules = asdict(rules_for_identifier(identifier))
        assert fields, identifier
        assert set(fields) <= set(rules), identifier
    # 第二版只引入分池口径，翻前门槛字段不属于它的口径。
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V2] == ("shared_board_chop_caliber",)


def test_every_non_first_identity_has_registered_digest_fields() -> None:
    """新注册身份若漏登摘要字段，必须在测试阶段就失败，而不是等到运行期。"""
    for identifier in MIXED_STRATEGY_IDENTIFIERS:
        if identifier == MIXED_STRATEGY_IDENTIFIER:
            continue
        assert identifier in DIGEST_RULE_FIELDS, identifier


def test_extra_rule_fields_do_not_move_earlier_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    """规则对象将来多出字段时，已登记身份的摘要必须逐字不变。"""
    real_asdict = asdict
    monkeypatch.setattr(
        validation,
        "asdict",
        lambda rules: {**real_asdict(rules), "future_caliber_flag": True},
    )
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V2)
        == "338a4863a68ca10eda44dcfdfdf26e510a4560cf8f7bbd1f97f048bc6ff6e794"
    )
    assert (
        config_digest(MIXED_STRATEGY_IDENTIFIER_V3)
        == "5ed7992b36de67cc97b4035f075d2c563f989300b448c5878f31847eb001643f"
    )


def test_config_digest_refuses_an_unregistered_identity() -> None:
    with pytest.raises(MixedStrategyError):
        config_digest("mixed-local@6")


def test_config_digest_refuses_an_identity_without_registered_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已注册身份若漏登摘要字段，取摘要必须显式失败，不静默改用整份规则对象。"""
    monkeypatch.delitem(DIGEST_RULE_FIELDS, MIXED_STRATEGY_IDENTIFIER_V3)
    with pytest.raises(MixedStrategyError):
        config_digest(MIXED_STRATEGY_IDENTIFIER_V3)


def test_frozen_manifest_carries_the_requested_identity() -> None:
    first = frozen_manifest(
        code_identity="test-code-identity",
        output_dir="/tmp/test-output",
        strategy_id=MIXED_STRATEGY_IDENTIFIER,
    )
    second = frozen_manifest(
        code_identity="test-code-identity",
        output_dir="/tmp/test-output",
        strategy_id=MIXED_STRATEGY_IDENTIFIER_V2,
    )
    assert first.strategy_id == MIXED_STRATEGY_IDENTIFIER
    assert second.strategy_id == MIXED_STRATEGY_IDENTIFIER_V2
    assert second.config_digest == config_digest(MIXED_STRATEGY_IDENTIFIER_V2)
    assert second.digest() != first.digest()
    assert [node.model_dump() for node in second.nodes] == [
        node.model_dump() for node in first.nodes
    ]


def test_frozen_manifest_refuses_an_unregistered_identity() -> None:
    with pytest.raises(MixedStrategyError):
        frozen_manifest(
            code_identity="test-code-identity",
            output_dir="/tmp/test-output",
            strategy_id="mixed-local@6",
        )


def test_strategy_rules_follow_the_manifest_identity() -> None:
    fixture = build_node("shared-board", 2)
    assert strategy_rules(_manifest((fixture,))).shared_board_chop_caliber is False
    second = _manifest((fixture,), strategy_id=MIXED_STRATEGY_IDENTIFIER_V2)
    assert strategy_rules(second).shared_board_chop_caliber is True
    with pytest.raises(MixedStrategyError):
        strategy_rules(_manifest((fixture,), strategy_id="mixed-local@6"))


def test_behavior_collection_follows_the_manifest_identity() -> None:
    """行为矩阵必须按清单身份计算：第二版在共享牌面上的跟注质量高于首版。"""
    fixture = build_node("shared-board", 2)
    first = collect_behavior(_manifest((fixture,)))
    second = collect_behavior(
        _manifest((fixture,), strategy_id=MIXED_STRATEGY_IDENTIFIER_V2)
    )
    first_rows = {row.style: row for row in first.categories}
    second_rows = {row.style: row for row in second.categories}
    assert set(first_rows) == set(second_rows)
    for style, row in first_rows.items():
        assert second_rows[style].mean_call_units > row.mean_call_units


def test_adversarial_batch_refuses_an_unregistered_identity() -> None:
    with pytest.raises(MixedStrategyError):
        run_adversarial_batch(stage="A", allow_matches=True, identifier="mixed-local@6")


def test_recheck_replays_with_the_receipt_caliber(monkeypatch) -> None:
    """补算的对照回放必须收到回执身份对应的口径，且不得与清单身份不一致。"""
    manifest = _manifest(
        (build_node("shared-board", 2),), strategy_id=MIXED_STRATEGY_IDENTIFIER_V2
    )
    receipt = run_validation(manifest=manifest, stage="A", allow_stage="A")
    seen: list[object] = []
    original = mixed_bot_recheck.play_adversarial_hand

    def _record(**kwargs: object) -> HandOutcome:
        seen.append(kwargs.get("rules"))
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(mixed_bot_recheck, "play_adversarial_hand", _record)
    report = recheck(
        manifest=manifest,
        receipt=receipt,
        receipt_path=__file__,
        allow_recheck=True,
    )
    assert report.status == "completed"
    assert seen and all(item is MIXED_LOCAL_V2_RULES for item in seen)
    mismatched = receipt.model_copy(update={"strategy_id": MIXED_STRATEGY_IDENTIFIER})
    with pytest.raises(MixedRecheckError):
        recheck(
            manifest=manifest,
            receipt=mismatched,
            receipt_path=__file__,
            allow_recheck=True,
        )


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


def test_depth_derived_nodes_replay_legally(frozen: MixedFixtureManifest) -> None:
    """浅深两档的派生节点必须全部可回放：开注额只能落在当时的合法区间内。"""
    for node in frozen.nodes:
        for depth in MIXED_DEPTHS_BB:
            if not usable_at_depth(node, depth):
                continue
            derived = fixture_at_depth(node, depth)
            assert derived.starting_stack == depth * MIXED_BIG_BLIND, (node.node_id, depth)
            applied = apply_node(derived)
            assert applied.engine.street is node.decision_street, (node.node_id, depth)
    # 9 人桌在浅码档曾经出现「清单金额超过剩余筹码」：派生节点必须按当时的上限开注。
    baseline = next(
        node for node in frozen.nodes if node.category == "flop-draw" and node.player_count == 9
    )
    shallow = fixture_at_depth(baseline, 15)
    assert shallow.stacks == (15 * MIXED_BIG_BLIND,) * 9
    assert [action.amount for action in shallow.actions if action.action == "bet"] == [120]
    # 浅码派生只允许翻后开注额与清单不同，翻前形状必须逐条一致。
    assert [
        action.model_dump() for action in shallow.actions if action.street is Street.PREFLOP
    ] == [
        action.model_dump() for action in baseline.actions if action.street is Street.PREFLOP
    ]


def test_depth_derivation_refuses_a_non_recipe_node() -> None:
    """非配方产物不得被静默按深度改写牌面。"""
    with pytest.raises(MixedValidationAuthorizationError):
        fixture_at_depth(_hu_fixture(), 15)


# ------------------------------------------------------------------ 门禁核对


def test_earlier_receipts_without_the_block_keys_still_load() -> None:
    """更早落盘的回执没有主种子块与轮换号：读回时必须给 None，而不是报错或编造数值。"""
    payload = {
        "player_count": 6,
        "style": "tight",
        "opponent": "random@1",
        "arm": "mixed-focus",
        "hands": 1,
        "truncated_hands": 0,
        "net_chips": 0,
        "bb_per_100": 0.0,
    }
    row = MixedMatchFamilyRow.model_validate(payload)
    assert row.seed_block is None
    assert row.rotation is None


def test_cli_requires_the_stage_a_receipt_for_stage_b(tmp_path, frozen) -> None:
    """阶段 B 的入口必须载入阶段 A 回执：缺失或不合格都拒绝，且拒绝发生在建目录之前。"""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest_json(frozen), encoding="utf-8")
    output_dir = tmp_path / "stage-b"
    with pytest.raises(MixedValidationAuthorizationError):
        validation.main([str(manifest_path), "B", str(output_dir), "--allow-stage=B"])
    assert not output_dir.exists()
    # 用前哨回执冒充：证明回执确实被载入并参与校验，而不是只有文件名被接受。
    sentinel = run_validation(manifest=frozen, stage="A0", allow_stage="A0")
    receipt = tmp_path / "receipt.json"
    receipt.write_text(sentinel.model_dump_json(), encoding="utf-8")
    with pytest.raises(MixedValidationAuthorizationError):
        validation.main(
            [
                str(manifest_path),
                "B",
                str(output_dir),
                "--allow-stage=B",
                f"--stage-a-receipt={receipt}",
            ]
        )
    assert not output_dir.exists()


def test_peak_rss_is_measured_where_the_platform_provides_it() -> None:
    """资源包络的 RSS 一项必须给实测读数，取不到时显式 None，不得填 0 冒充已测。"""
    pytest.importorskip("resource")
    measured = peak_rss_bytes()
    assert measured is not None
    assert measured > 0


def test_supplementary_plan_is_recorded_per_stage() -> None:
    """补充样本计划数按阶段记账，阶段 B 的总数不得写进阶段 A 的回执。"""
    assert supplementary_plan("A0") == 0
    assert supplementary_plan("A") == STAGE_A_SUPPLEMENTARY_SAMPLES == 24
    assert supplementary_plan("B") == SUPPLEMENTARY_TOTAL_SAMPLES == 240


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


def test_adversarial_rows_carry_the_seed_block_and_rotation(monkeypatch) -> None:
    """逐手行必须带主种子块与轮换号，按块聚合才不需要额外信息。"""
    monkeypatch.setattr(
        validation,
        "play_adversarial_hand",
        lambda **kwargs: validation.HandOutcome(net_chips=5, truncated=False),
    )
    tally = run_adversarial_batch(stage="A", allow_matches=True)
    assert len(tally.rows) == STAGE_A_ADVERSARIAL_HANDS
    assert {row.seed_block for row in tally.rows} == {MIXED_MAIN_SEEDS[0]}
    assert {row.rotation for row in tally.rows} == {0}
    matches = matches_from_tally(tally, planned_hands=STAGE_A_ADVERSARIAL_HANDS)
    assert matches.planned_hands == STAGE_A_ADVERSARIAL_HANDS
    assert matches.completed_hands == STAGE_A_ADVERSARIAL_HANDS
    assert matches.truncated_hands == 0
    blocks = {
        (row.player_count, row.style, row.opponent, row.seed_block) for row in tally.rows
    }
    assert len(blocks) == len(ADVERSARIAL_OPPONENT_FAMILIES) * len(MIXED_PLAYER_COUNTS)


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


def test_a0_sentinel_is_gated_bounded_and_not_a_stage_a_receipt(frozen, tmp_path) -> None:
    """A0 是阶段 A 的受限子集：需显式许可、用量有界，且不能充当阶段 B 的前置回执。"""
    with pytest.raises(MixedValidationAuthorizationError):
        run_validation(manifest=frozen, stage="A0", allow_stage=None)
    with pytest.raises(MixedValidationAuthorizationError):
        run_validation(manifest=frozen, stage="A0", allow_stage="A")
    report = run_validation(
        manifest=frozen,
        stage="A0",
        allow_stage="A0",
        output_dir=str(tmp_path / "sentinel"),
    )
    assert report.stage == "A0"
    assert report.status == "completed"
    assert report.coverage.cost_cells_planned == STAGE_A0_COST_SAMPLES
    assert report.coverage.cost_cells_executed == STAGE_A0_COST_SAMPLES
    # 格口径与样本口径分列：每格 1 样本时两者相等，配额大于 1 时会相差三个数量级。
    assert report.coverage.cost_samples_planned == STAGE_A0_COST_SAMPLES
    assert report.coverage.cost_samples_executed == STAGE_A0_COST_SAMPLES
    assert report.timing.decision_path is not None
    assert report.timing.decision_path.samples == STAGE_A0_COST_SAMPLES
    # 完整单步必须单独成列，且逐样本不小于其中的决策段。
    assert report.timing.bot_step is not None
    assert report.timing.bot_step.samples == STAGE_A0_COST_SAMPLES
    assert report.timing.bot_step.max_ms >= report.timing.decision_path.max_ms
    # 未运行的三项必须显式标为未运行，而不是填成已完成。
    assert report.timing.supplementary_decision_path is None
    assert report.coverage.supplementary_samples_planned == 0
    assert report.matches.completed_hands == 0
    assert report.behavior.direct_distributions == 0
    assert any("A0" in item for item in report.limitations)
    # 分组读数按单人数 × 四街 × 单风格 × 单深度逐维列出，空分组不伪造。
    groups = report.timing.decision_path_groups
    counts = {
        dimension: sum(1 for group in groups if group.dimension == dimension)
        for dimension in ("player_count", "street", "style", "depth")
    }
    assert counts == {"player_count": 1, "street": 4, "style": 1, "depth": 1}
    assert next(group for group in groups if group.dimension == "player_count").path.samples == 4
    assert all(group.path.samples == 1 for group in groups if group.dimension == "street")
    written = tmp_path / "sentinel" / "mixed-validation-stage-A0.json"
    assert written.exists()
    size = written.stat().st_size
    assert report.resources.output_bytes == size
    assert json.loads(written.read_text(encoding="utf-8"))["resources"]["output_bytes"] == size
    with pytest.raises(MixedValidationAuthorizationError):
        require_stage_permission(
            stage="B", allow_stage="B", manifest=frozen, stage_a_receipt=report
        )


def test_replay_failure_stops_and_reports_instead_of_raising(monkeypatch) -> None:
    """一致性错误必须按冻结停止条件转成 stopped-* 报告，并保留已完成计数。"""
    manifest = _manifest((build_node("unopened-open", 2),))
    original = validation.time_decision
    calls = {"count": 0}

    def flaky(*args: object, **kwargs: object) -> object:
        calls["count"] += 1
        if calls["count"] > 1:
            raise MixedFixtureError("模拟回放失败")
        return original(*args, **kwargs)

    monkeypatch.setattr(validation, "time_decision", flaky)
    report = run_validation(manifest=manifest, stage="A", allow_stage="A")
    assert report.status == "stopped-consistency-error"
    assert calls["count"] == 2
    assert report.coverage.cost_cells_executed == 1
    assert report.timing.decision_path is not None
    assert report.timing.decision_path.samples == 1
    # 未跑到的部分记为未运行，不得填成已完成。
    assert report.matches.completed_hands == 0
    assert report.behavior.direct_distributions == 0
    assert [violation.kind for violation in report.violations] == ["replay-error"]


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


def test_behavior_reports_style_distances_and_category_rows() -> None:
    """风格间距离与按类别明细必须在有界冒烟路径上就能读出。"""
    manifest = _manifest((build_node("shared-board", 2),))
    behavior = collect_behavior(manifest)
    assert len(behavior.style_js_distances) == 3
    assert all(row.nodes == 1 for row in behavior.style_js_distances)
    assert all(0.0 <= row.mean_js_distance <= 1.0 for row in behavior.style_js_distances)
    assert {row.category for row in behavior.categories} == {"shared-board"}
    assert {row.style for row in behavior.categories} == {style.value for style in MixedStyle}
    shared = next(row for row in behavior.categories if row.style == "tight")
    total = (
        shared.mean_fold_units
        + shared.mean_check_units
        + shared.mean_call_units
        + shared.mean_bet_units
        + shared.mean_raise_units
    )
    assert abs(total - MIXED_DISTRIBUTION_UNITS) <= 3


def test_js_distance_is_zero_on_identity_and_one_on_disjoint_supports() -> None:
    left = {(ActionType.CHECK, 0): 500.0, (ActionType.BET, 100): 500.0}
    right = {(ActionType.FOLD, 0): 1000.0}
    assert js_distance(left, left) == 0.0
    assert js_distance(left, right) == pytest.approx(1.0)
    with pytest.raises(MixedValidationAuthorizationError):
        js_distance({}, left)


def test_aggregate_matches_reports_block_stats_and_rates() -> None:
    """按块聚合与 VPIP/PFR 必须能从不含对局的结果集合算出。"""
    schedule = adversarial_schedule("A")
    outcomes = [
        HandOutcome(
            net_chips=1,
            truncated=False,
            vpip=True,
            pfr=False,
            aggressive_actions=2,
            total_actions=4,
        )
        for _ in schedule
    ]
    aggregates, worst = aggregate_matches(schedule, outcomes)
    assert len(aggregates) == len(ADVERSARIAL_OPPONENT_FAMILIES) * 2 * len(MIXED_PLAYER_COUNTS)
    row = next(item for item in aggregates if item.arm == "mixed-focus")
    assert row.hands == 1
    assert row.vpip == 1.0
    assert row.pfr == 0.0
    assert row.aggression_rate == 0.5
    assert row.block_means == (1.0,)
    assert row.block_std == 0.0
    # 冒烟排期只含单一风格，因此最差对手只按两个 arm 各出一行。
    assert {row.style for row in worst} == {MixedStyle.TIGHT.value}
    assert len(worst) == 2
    full = adversarial_schedule("B")
    rows_full, _ = aggregate_matches(
        full, [HandOutcome(net_chips=index % 5, truncated=False) for index in range(len(full))]
    )
    assert len(rows_full) == len(MIXED_PLAYER_COUNTS) * len(MixedStyle) * 4 * 2
    two_handed = next(
        item
        for item in rows_full
        if item.player_count == 2 and item.style == "tight" and item.arm == "mixed-focus"
    )
    # 完整排期下每格覆盖四个主种子块 × 该人数的全部轮换。
    assert two_handed.hands == 4 * 2
    assert len(two_handed.block_means) == 4
    _, worst_full = aggregate_matches(
        full, [HandOutcome(net_chips=0, truncated=False) for _ in full]
    )
    assert {row.style for row in worst_full} == {style.value for style in MixedStyle}
    assert len(worst_full) == len(MixedStyle) * 2


def test_compare_net_chips_stops_on_any_mismatch() -> None:
    """逐手比对必须严到任何一位差异都中止，且不返回部分结论。"""
    schedule = adversarial_schedule("A")
    rows = [
        MixedMatchFamilyRow(
            player_count=entry[4],
            style=entry[1].value,
            opponent=entry[2],
            arm=entry[3],
            hands=1,
            truncated_hands=0,
            net_chips=0,
            bb_per_100=0.0,
        )
        for entry in schedule
    ]
    same = [HandOutcome(net_chips=0, truncated=False) for _ in schedule]
    assert compare_net_chips(rows, schedule, same) == len(schedule)
    drifted = list(same)
    drifted[7] = HandOutcome(net_chips=1, truncated=False)
    with pytest.raises(MixedRecheckError):
        compare_net_chips(rows, schedule, drifted)
    with pytest.raises(MixedRecheckError):
        compare_net_chips(rows, schedule, same[:-1])


def test_recheck_is_refused_by_default_and_for_non_stage_receipts() -> None:
    """补算默认拒绝；对非阶段回执同样拒绝，且拒绝发生在建目录之前。"""
    manifest = _manifest((build_node("unopened-open", 2),))
    with pytest.raises(MixedRecheckError):
        recheck(manifest=manifest, receipt=None, receipt_path=None)
    with pytest.raises(MixedRecheckError):
        recheck(manifest=None, receipt=None, receipt_path=None, allow_recheck=True)
    sentinel = run_validation(manifest=manifest, stage="A0", allow_stage="A0")
    with pytest.raises(MixedRecheckError):
        recheck(
            manifest=manifest,
            receipt=sentinel,
            receipt_path=__file__,
            allow_recheck=True,
            output_dir=None,
        )


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
