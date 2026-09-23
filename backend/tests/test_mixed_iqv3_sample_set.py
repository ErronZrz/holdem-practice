"""第四套样本集的回归：节点正交性、类别语义、种子正交性与两条 opt-in 入口链。

只做有界单元回归与冻结节点回放：不跑性能矩阵、不对抗对局、不访问真实库。
"""

import json
from pathlib import Path

import pytest

from app.poker.evaluator import evaluate_fast
from app.strategy.mixed_policy import MixedStyle
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V6,
    MIXED_STRATEGY_IDENTIFIER_V7,
    MIXED_STRATEGY_IDENTIFIER_V8,
)

from . import mixed_bot_recheck
from . import mixed_bot_validation as validation
from .mixed_bot_states import (
    MIXED_APPLICABLE_NODE_COUNT,
    MIXED_CATEGORY_IDS,
    MIXED_CATEGORY_STREET,
    MIXED_DEPTHS_BB,
    MIXED_IQV2_NODE_ID_SUFFIX,
    MIXED_IQV3_NODE_ID_SUFFIX,
    MIXED_IQV_NODE_ID_SUFFIX,
    MIXED_PLAYER_COUNTS,
    MIXED_STREETS,
    MixedNodeFixture,
    applicable_player_counts,
    apply_node,
    build_frozen_iqv2_nodes,
    build_frozen_iqv3_nodes,
    build_frozen_iqv_nodes,
    build_frozen_nodes,
    manifest_json,
)
from .mixed_bot_validation import (
    MIXED_IQV2_MAIN_SEEDS,
    MIXED_IQV2_VALIDATION_LIMITATIONS,
    MIXED_IQV3_MAIN_SEEDS,
    MIXED_IQV_MAIN_SEEDS,
    MIXED_MAIN_SEEDS,
    MIXED_VALIDATION_SCHEMA_VERSION_V2,
    derive_iqv3_main_seeds,
    fixture_at_depth,
    frozen_iqv3_manifest,
    validation_limitations,
)

FOURTH_SET = build_frozen_iqv3_nodes()
EARLIER_SETS = {
    "首套": build_frozen_nodes(),
    "第二套": build_frozen_iqv_nodes(),
    "第三套": build_frozen_iqv2_nodes(),
}


def _acting_seat(fixture: MixedNodeFixture) -> int:
    """回放节点后的行动座位：主题牌面必须落在这一席上。"""
    return apply_node(fixture).engine.current_seat


def _themes(nodes: tuple[MixedNodeFixture, ...]) -> dict[tuple[str, int], tuple]:
    """逐（类别 × 人数）的主题：公共牌与行动座位自己的底牌。"""
    return {
        (node.category, node.player_count): (
            tuple(node.board),
            tuple(node.hole_cards[_acting_seat(node)]),
        )
        for node in nodes
    }


def _action_line(fixture: MixedNodeFixture) -> tuple[tuple[int, str, int], ...]:
    return tuple((action.seat, action.action, action.amount) for action in fixture.actions)


# ------------------------------------------------------------------ 节点集


def test_fourth_set_has_the_frozen_size_and_suffix() -> None:
    assert len(FOURTH_SET) == MIXED_APPLICABLE_NODE_COUNT
    assert all(node.node_id.endswith(MIXED_IQV3_NODE_ID_SUFFIX) for node in FOURTH_SET)
    assert MIXED_IQV3_NODE_ID_SUFFIX != MIXED_IQV_NODE_ID_SUFFIX
    assert MIXED_IQV3_NODE_ID_SUFFIX != MIXED_IQV2_NODE_ID_SUFFIX


def test_fourth_set_covers_every_planned_slot() -> None:
    pairs = {(node.category, node.player_count) for node in FOURTH_SET}
    assert len(pairs) == MIXED_APPLICABLE_NODE_COUNT
    for category in MIXED_CATEGORY_IDS:
        for count in applicable_player_counts(category):
            assert (category, count) in pairs
    for count in MIXED_PLAYER_COUNTS:
        streets = {node.decision_street for node in FOURTH_SET if node.player_count == count}
        assert streets == set(MIXED_STREETS)
    for node in FOURTH_SET:
        assert node.decision_street is MIXED_CATEGORY_STREET[node.category]


@pytest.mark.parametrize("name", sorted(EARLIER_SETS))
def test_fourth_set_reuses_no_earlier_node(name: str) -> None:
    """与既有各套必须正交：标识、主题牌面与行动线都不重合。"""
    earlier = EARLIER_SETS[name]
    assert not {node.node_id for node in FOURTH_SET} & {node.node_id for node in earlier}
    ours, theirs = _themes(FOURTH_SET), _themes(earlier)
    common = set(ours) & set(theirs)
    assert len(common) == MIXED_APPLICABLE_NODE_COUNT
    for key in common:
        board, holes = ours[key]
        other_board, other_holes = theirs[key]
        assert holes != other_holes, key
        if board:
            assert board != other_board, key
    # 行动线本身由形状决定，跨套相同属正常；判定的是「牌面 + 行动线」这一组合不重合。
    def combined(nodes: tuple[MixedNodeFixture, ...]) -> set[tuple]:
        return {
            (
                node.category,
                node.player_count,
                tuple(node.board),
                tuple(node.hole_cards[_acting_seat(node)]),
                _action_line(node),
            )
            for node in nodes
        }

    assert not combined(FOURTH_SET) & combined(earlier)


def test_fourth_set_cards_are_disjoint_and_deterministic() -> None:
    for node in FOURTH_SET:
        cards = [*node.board, *(token for pair in node.hole_cards for token in pair)]
        assert len(set(cards)) == len(cards), node.node_id
    again = build_frozen_iqv3_nodes()
    assert [node.model_dump() for node in again] == [
        node.model_dump() for node in FOURTH_SET
    ]


def test_fourth_set_replays_cleanly_and_keeps_category_semantics() -> None:
    """逐个节点核对：回放后局面合法，且配方确实构造出了它声称的类别。"""
    for node in FOURTH_SET:
        applied = apply_node(node)
        engine = applied.engine
        legal = applied.legal_actions()
        actor = engine.players[engine.current_seat]
        opponents = [player for player in engine.players if player.seat != actor.seat]
        assert (
            legal.can_fold or legal.can_check or legal.can_call or legal.can_bet or legal.can_raise
        ), node.node_id
        assert engine.street is node.decision_street, node.node_id
        assert not (legal.can_check and legal.can_call), node.node_id
        assert not (legal.can_bet and legal.can_raise), node.node_id
        if node.category == "short-stack-call":
            assert legal.is_short_all_in_call, node.node_id
            assert legal.actual_call_amount < legal.call_amount, node.node_id
        elif node.category == "incomplete-raise":
            assert not legal.can_raise, node.node_id
            assert legal.call_amount > 0, node.node_id
        elif node.category == "one-side-all-in":
            assert sum(1 for player in opponents if player.all_in) == 1, node.node_id
            assert any(
                not player.folded and not player.all_in for player in opponents
            ), node.node_id
        elif node.category == "free-check":
            assert legal.can_check and legal.call_amount == 0, node.node_id
        elif node.category == "shared-board":
            hero = evaluate_fast([*actor.hole_cards, *engine.board])
            board = evaluate_fast(list(engine.board))
            assert hero == board, node.node_id


def test_fourth_set_nodes_rebuild_at_other_depths() -> None:
    scalable = next(node for node in FOURTH_SET if node.depth_scalable)
    for depth_bb in MIXED_DEPTHS_BB:
        scaled = fixture_at_depth(scalable, depth_bb)
        assert scaled.node_id == scalable.node_id
        assert scaled.starting_stack == depth_bb * 10
        assert apply_node(scaled).engine.street is scaled.decision_street
    fixed = next(node for node in FOURTH_SET if not node.depth_scalable)
    assert fixture_at_depth(fixed, 15).model_dump() == fixed.model_dump()


# ------------------------------------------------------------------ 种子与清单


def test_fourth_set_seeds_are_derived_and_disjoint() -> None:
    assert derive_iqv3_main_seeds() == MIXED_IQV3_MAIN_SEEDS
    assert len(MIXED_IQV3_MAIN_SEEDS) == 16
    assert len(set(MIXED_IQV3_MAIN_SEEDS)) == 16
    for earlier in (MIXED_IQV2_MAIN_SEEDS, MIXED_IQV_MAIN_SEEDS, MIXED_MAIN_SEEDS):
        assert not set(MIXED_IQV3_MAIN_SEEDS) & set(earlier)


def test_fourth_manifest_carries_the_sixth_identity() -> None:
    manifest = frozen_iqv3_manifest(
        code_identity="0" * 40,
        output_dir="/tmp/unused/runs",
        strategy_id=MIXED_STRATEGY_IDENTIFIER_V6,
    )
    assert manifest.strategy_id == MIXED_STRATEGY_IDENTIFIER_V6
    assert manifest.seeds == MIXED_IQV3_MAIN_SEEDS
    assert manifest.nodes == FOURTH_SET
    assert manifest.report_format.startswith(MIXED_VALIDATION_SCHEMA_VERSION_V2)
    assert manifest.config_digest == validation.config_digest(MIXED_STRATEGY_IDENTIFIER_V6)
    assert not validation.required_envelope_fields(manifest)


def test_fourth_set_block_count_reuses_the_registered_limitations() -> None:
    """局限说明按种子块个数取：第四套与前一套块数相同，因此沿用同一条登记文本。"""
    manifest = frozen_iqv3_manifest(
        code_identity="0" * 40,
        output_dir="/tmp/unused/runs",
        strategy_id=MIXED_STRATEGY_IDENTIFIER_V6,
    )
    assert validation_limitations(len(manifest.seeds)) is (
        MIXED_IQV2_VALIDATION_LIMITATIONS
    )


# ------------------------------------------------------------------ opt-in 入口链


@pytest.mark.parametrize(
    "strategy_id",
    [
        MIXED_STRATEGY_IDENTIFIER_V6,
        MIXED_STRATEGY_IDENTIFIER_V7,
        MIXED_STRATEGY_IDENTIFIER_V8,
    ],
)
def test_fourth_set_runs_through_stage_a_and_the_recheck_entry(
    tmp_path: Path, strategy_id: str
) -> None:
    """两条 opt-in 入口链必须真正走通：阶段 A 与小规模补算都按清单声明的身份执行。"""
    full = frozen_iqv3_manifest(
        code_identity="0" * 40,
        output_dir=str(tmp_path / "runs"),
        strategy_id=strategy_id,
    )
    # 只留一个节点：本条核对的是入口链与身份分派，不是节点覆盖面。
    manifest = full.model_copy(update={"nodes": (full.nodes[0],)})
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(manifest_json(manifest), encoding="utf-8")

    stage_a_dir = tmp_path / "stage-a"
    assert (
        validation.main([str(manifest_path), "A", str(stage_a_dir), "--allow-stage=A"]) == 0
    )
    receipt = json.loads(
        (stage_a_dir / "mixed-validation-stage-A.json").read_text(encoding="utf-8")
    )
    assert receipt["strategy_id"] == strategy_id
    assert receipt["schema_version"] == MIXED_VALIDATION_SCHEMA_VERSION_V2
    assert receipt["violations"] == []
    # 逐节点行按（节点 × 风格 × 手模式 × 种子块）给出，块集合与清单一致。
    rows = receipt["behavior"]["nodes"]
    assert len(rows) == len(MixedStyle) * 3 * len(manifest.seeds)
    assert {row["seed_block"] for row in rows} == set(manifest.seeds)
    assert all(row["node_id"].endswith(MIXED_IQV3_NODE_ID_SUFFIX) for row in rows)

    recheck_dir = tmp_path / "stage-a-recheck"
    assert (
        mixed_bot_recheck.main(
            [
                str(manifest_path),
                str(stage_a_dir / "mixed-validation-stage-A.json"),
                str(recheck_dir),
                "--allow-recheck",
            ]
        )
        == 0
    )
    recheck = json.loads(
        (recheck_dir / "mixed-recheck-stage-A.json").read_text(encoding="utf-8")
    )
    assert recheck["status"] == "completed"
    assert recheck["consistency"]["net_chips_exact"] is True
    assert recheck["consistency"]["behavior_exact"] is True
    assert recheck["consistency"]["hands_compared"] == receipt["matches"]["completed_hands"]
