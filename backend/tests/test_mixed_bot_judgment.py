"""判定器的实现层测试：合成用例锁口径，黄金样本锁复现性。

两层用意：
- 合成用例：把每个自由度都钉死在测试里，避免实现被悄悄改宽或改窄；
- 黄金样本：用已封存的外部工件断言历史读数逐位复现；工件缺失时自动跳过，
  使本测试在没有外部证据的机器上仍可运行。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests import mixed_bot_judgment as judgment
from tests.mixed_bot_judgment import MixedJudgmentError

V7_DIR = Path("/Users/bryanylliu/holdem-mixed-bot-validation-v7")
V8_DIR = Path("/Users/bryanylliu/holdem-mixed-bot-validation-v8")
HAND_MODES = ("normal", "cautious", "pressed")
SCALE = 1_000_000

# 已封存工件的摘要：黄金样本测试前先核对，避免工件被改写后仍「通过」。
V7_DIGESTS = {
    "input/frozen-fixture-manifest.json":
        "a68e9776c180400b80fccecd9698b0d12a32e7b95ddf650246f87c2c487cae61",
    "runs/stage-a/mixed-validation-stage-A.json":
        "980a62f6503c533501c7640b136bd2e71e77819132ecb7d6e89833c3b0a34571",
    "runs/stage-a-recheck/mixed-recheck-stage-A.json":
        "dd89e5fb114b1074178ecdb8d8dd40e38fbe1962baa72d70eff494e055482104",
    "runs/stage-b/mixed-validation-stage-B.json":
        "f2b83bc1a7cbd0f451c72efec3e818ffdc38ef8521ada00f0d7350035ae97c4c",
    "runs/stage-b/mixed-observations-stage-B.json":
        "04a5acb2e57058f9929f3f39e0c0e64d2d1b490032f3bff3de2ea300a5043b13",
    "runs/stage-b-recheck/mixed-recheck-stage-B.json":
        "215835e5c89eed73d58c3cda60d809b88d5a016a732822eefa13eb8a8bbcbb6d",
}
V8_DIGESTS = {
    "input/frozen-fixture-manifest.json":
        "484a6ce83687be436a2676081c6f9c35a7deed5c4e867b9bb95eec868141a225",
    "runs/stage-a/mixed-validation-stage-A.json":
        "b96420985ba2e0a16e76c892f4e7895ec62f2ac384b30cc0d0379b0601ce3319",
    "runs/stage-a-recheck/mixed-recheck-stage-A.json":
        "974a019c6f2dce9f141b955b0133ce829e176d882db408dd6fbe33128ce411b5",
    "runs/stage-b/mixed-validation-stage-B.json":
        "6d3838fb09d9b419bb4d9f16b510a692989428c2064c7ef4716fa8b682fff27b",
    "runs/stage-b/mixed-observations-stage-B.json":
        "087e0d024658c7e75038977f82c5ab392754c3688fe5f56cce3990fc09425132",
    "runs/stage-b-recheck/mixed-recheck-stage-B.json":
        "a3c945906ba87de675b1c463540aac929ba559d05d397160422582f8088dda54",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 合成夹具
# ---------------------------------------------------------------------------


def shares_of(share: float, action: str = "call", other: str = "fold") -> dict[str, float]:
    """按份额造一组动作 units：份额恰好落在门槛上时可做边界断言。"""
    top = round(share * SCALE)
    return {action: top, other: SCALE - top}


def node_row(
    node: str,
    category: str,
    style: str,
    mode: str,
    block: int,
    units: dict[str, float],
    **extra: object,
) -> dict[str, object]:
    """造一条逐节点分布行，默认字段与工件字段语义一致。"""
    scale_units = extra.pop("scale_units", None) or {}
    return {
        "node_id": node,
        "category": category,
        "player_count": 2,
        "style": style,
        "hand_mode": mode,
        "seed_block": block,
        "action_units": units,
        "scale_units": scale_units,
        "action_entropy": extra.pop("action_entropy", 0.5),
        "scale_entropy": extra.pop("scale_entropy", None),
        "effective_scale_count": len(scale_units),
        "structural_single_size": extra.pop("structural_single_size", 0),
        "has_active_candidate": bool(scale_units),
    }


def domain_rows(
    block: int, category: str, action: str, shares: dict[str, float], node: str
) -> list[dict[str, object]]:
    """为一个机会域造某块的全部行：每个风格 × 三个手模式。"""
    return [
        node_row(node, category, style, mode, block, shares_of(share, action))
        for style, share in shares.items()
        for mode in HAND_MODES
    ]


def match_row(
    opponent: str, block: int, arm: str, net_chips: int, player_count: int = 2
) -> dict[str, object]:
    """造一条对抗对照行；单手行的 bb/100 恰为净筹码的十倍。"""
    return {
        "player_count": player_count,
        "style": "tight",
        "opponent": opponent,
        "arm": arm,
        "seed_block": block,
        "rotation": 0,
        "hands": 1,
        "truncated_hands": 0,
        "net_chips": net_chips,
        "bb_per_100": float(net_chips * 10),
    }


def hand_row(
    block: int,
    arm: str,
    net_chips: int,
    opponent: str = "probe",
    rotation: int = 0,
    actions: list[dict[str, object]] | None = None,
    pots: dict[str, int] | None = None,
) -> dict[str, object]:
    """造一条观测逐手行。"""
    return {
        "hand_index": 0,
        "player_count": 2,
        "style": "tight",
        "opponent": opponent,
        "arm": arm,
        "seed_block": block,
        "rotation": rotation,
        "actions": actions or [],
        "pot_after_street": pots or {},
        "net_chips": net_chips,
        "focus_strength_bucket": "weak",
    }


# ---------------------------------------------------------------------------
# 合成用例
# ---------------------------------------------------------------------------


def test_judge_requires_explicit_permission(tmp_path: Path) -> None:
    """未显式允许时不得计算，也不得触碰任何工件。"""
    missing = tmp_path / "不存在.json"
    with pytest.raises(MixedJudgmentError, match="默认拒绝"):
        judgment.judge(
            manifest_path=str(missing),
            reports=[("阶段回执", str(missing))],
            observations_path=str(missing),
            allow_judgment=False,
        )


def test_mix_rule_uses_second_highest_share_with_ten_percent_floor() -> None:
    """混合判定看次高份额：恰好 10% 算混合，略低于 10% 不算。"""
    assert judgment._is_substantively_mixed({"a": 900_000, "b": 100_000}) is True
    assert judgment._is_substantively_mixed({"a": 900_001, "b": 99_999}) is False
    assert judgment._is_substantively_mixed({"a": 1_000_000}) is False
    assert judgment._is_substantively_mixed({"a": 0, "b": 0}) is False


def test_coverage_splits_domains_and_aggregates_nodes() -> None:
    """覆盖率分母是逐节点分布；分域按类别分区；节点读数先合并 units 再套规则。"""
    rows = [
        node_row("pre", "unopened-open", "tight", "normal", 7, shares_of(0.8)),
        node_row("pre", "unopened-open", "tight", "cautious", 7, shares_of(1.0)),
        node_row("face", "flop-draw", "tight", "normal", 7, shares_of(0.2, "raise")),
        node_row("free", "free-check", "tight", "normal", 7, {"check": 1_000_000}),
    ]
    reading = judgment.coverage_reading(rows)
    assert (reading.unit_mixed, reading.unit_total) == (2, 4)
    assert reading.share == pytest.approx(0.5)
    assert (reading.preflop_mixed, reading.preflop_total) == (1, 2)
    assert reading.preflop_share == pytest.approx(0.5)
    assert (reading.facing_bet_mixed, reading.facing_bet_total) == (1, 1)
    assert (reading.free_action_mixed, reading.free_action_total) == (0, 1)
    # 节点聚合：同一节点的两个手模式合并后次高份额 25%，仍算混合。
    assert (reading.node_mixed, reading.node_total) == (2, 3)


def test_entropy_averages_distribution_entropy_per_style() -> None:
    """类型熵按风格取分布熵的算术均值，不按样本量加权。"""
    rows = [
        node_row("n1", "unopened-open", "tight", "normal", 7, {"call": 1}, action_entropy=0.2),
        node_row("n2", "unopened-open", "tight", "normal", 7, {"call": 1}, action_entropy=0.6),
        node_row("n3", "unopened-open", "calling", "normal", 7, {"call": 1}, action_entropy=0.1),
    ]
    reading = judgment.entropy_reading(rows)
    assert reading.per_style["tight"] == pytest.approx(0.4)
    assert reading.per_style["calling"] == pytest.approx(0.1)
    assert reading.per_style["aggressive"] == pytest.approx(0.0)
    assert reading.above_threshold is False


def test_scale_anchors_count_sizes_above_fifteen_percent() -> None:
    """额度锚点按同额合并后的份额分档：两档达标才算满足，单档结构行照实计入分母。"""
    rows = [
        node_row(
            "n1", "unopened-open", "tight", "normal", 7, {"raise": 1},
            scale_units={"300": 600_000, "600": 400_000}, scale_entropy=1.2,
        ),
        node_row(
            "n2", "unopened-open", "tight", "normal", 7, {"raise": 1},
            scale_units={"300": 800_000, "600": 200_000}, scale_entropy=0.6,
        ),
        node_row(
            "n3", "unopened-open", "tight", "normal", 7, {"raise": 1},
            scale_units={"300": 1_000_000}, scale_entropy=0.1, structural_single_size=1,
        ),
    ]
    reading = judgment.scale_anchor_reading(rows)
    assert (reading.anchor_satisfied, reading.unit_total) == (2, 3)
    assert reading.structurally_single == 1
    assert reading.mean_scale_entropy == pytest.approx((1.2 + 0.6 + 0.1) / 3)
    assert reading.anchors_above_threshold is False
    assert reading.scale_entropy_above_threshold is True


def test_opportunity_domain_needs_two_pairs_in_both_domains() -> None:
    """两个机会域都要至少两对达标；只有单域达标不算满足。"""
    block = 7
    rows = domain_rows(block, "unopened-open", "call",
                       {"tight": 0.2, "aggressive": 0.9, "calling": 0.5}, "entry")
    # 主动域三档几乎无差异，故该域零对达标。
    rows += domain_rows(block, "flop-draw", "raise",
                        {"tight": 0.010, "aggressive": 0.011, "calling": 0.0095}, "active")
    reading, _ = judgment.opportunity_reading(rows)
    assert reading.entry_pairs_above == 3
    assert reading.active_pairs_above == 0
    assert reading.satisfied is False


def test_stability_requires_same_sign_across_blocks() -> None:
    """方向稳定按配对逐域检查：换块后符号翻转即不稳定，并标注分布是否随块变化。"""
    stable: list[dict[str, object]] = []
    shifting: list[dict[str, object]] = []
    for block, aggressive in ((1, 0.9), (2, 0.9), (3, 0.1)):
        stable += domain_rows(block, "unopened-open", "call",
                              {"tight": 0.2, "aggressive": 0.9, "calling": 0.9}, "entry")
        shifting += domain_rows(block, "unopened-open", "call",
                                {"tight": 0.2, "aggressive": aggressive, "calling": 0.9}, "entry")
    steady = judgment.stability_reading(stable, [1, 2, 3])
    assert steady.direction_stable is True
    assert steady.blocks_vary is False
    moving = judgment.stability_reading(shifting, [1, 2, 3])
    assert moving.direction_stable is False
    assert moving.blocks_vary is True


def test_non_degradation_reports_worst_family_and_both_calibers() -> None:
    """不劣化逐人数取最差族；t 区间与块极值两口径并列，任一不过即判未满足。"""
    rows: list[dict[str, object]] = []
    for block in range(1, 17):
        rows.append(match_row("good-probe", block, "mixed-focus", 100))
        rows.append(match_row("good-probe", block, "legacy-focus", 0))
        loss = -100 if block % 2 else -5_000
        rows.append(match_row("bad-probe", block, "mixed-focus", loss))
        rows.append(match_row("bad-probe", block, "legacy-focus", 0))
    reading = judgment.non_degradation_reading({"matches": {"rows": rows}}, "合成工件")
    assert reading.pairs == 32
    assert reading.players_satisfied == 0
    worst = reading.players[0]
    assert worst.worst_family == "bad-probe"
    assert worst.interval_satisfied is False
    assert worst.block_extreme_satisfied is False
    assert worst.best_family == "good-probe"
    assert worst.best_mean_bb_per_100 == pytest.approx(1000.0)


def test_pair_table_rejects_incomplete_pairs() -> None:
    """缺一臂的配对必须显式失败，不得按可用的一臂凑数。"""
    rows = [match_row("probe", 1, "mixed-focus", 10)]
    with pytest.raises(MixedJudgmentError, match="不完整配对"):
        judgment.pair_table(rows, "合成工件")


def test_node_granularity_missing_is_refused() -> None:
    """工件缺少逐节点分布时显式失败，不回退到类别或风格均值。"""
    with pytest.raises(MixedJudgmentError, match="逐节点分布行"):
        judgment.node_rows({"behavior": {"direct_distributions": 1125}}, "合成工件")


def test_first_facing_event_uses_street_start_pot() -> None:
    """面对事件取被测座位首次面对对手下注/加注，参照量是街起始底池。"""
    hand = {
        "player_count": 2,
        "rotation": 0,
        "actions": [
            {"street": "preflop", "seat": 1, "action": "raise", "amount": 30},
            {"street": "preflop", "seat": 0, "action": "call", "amount": 0},
            {"street": "flop", "seat": 1, "action": "bet", "amount": 40},
            {"street": "flop", "seat": 0, "action": "fold", "amount": 0},
        ],
        "pot_after_street": {"preflop": 60, "flop": 100},
    }
    assert judgment._first_facing_event(hand) == ("preflop", 30, 15)
    assert judgment._scale_bucket(30, 15) == ">100%"
    assert judgment._scale_bucket(7, 15) == "≤50%"
    assert judgment._scale_bucket(12, 15) == "50–100%"
    assert judgment._scale_bucket(30, 0) == "起始底池缺失"


def test_targeting_short_segment_follows_manifest_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """短段按清单种子序取前若干对，而不是按种子数值大小排序。"""
    monkeypatch.setattr(judgment, "SHORT_SEGMENT_PAIRS_PER_GROUP", 1)
    hands = [
        hand_row(9, "mixed-focus", 500),
        hand_row(9, "legacy-focus", 0),
        hand_row(1, "mixed-focus", -500),
        hand_row(1, "legacy-focus", 0),
    ]
    reading = judgment.targeting_diagnostic({"hands": hands}, {"seeds": [9, 1]}, "合成观测")
    family = reading.families[0]
    assert family.short_pairs == 1
    assert family.short_mean_bb_per_100 == pytest.approx(5_000.0)
    assert family.long_mean_bb_per_100 == pytest.approx(-5_000.0)
    assert reading.pairs_with_facing == 0
    assert reading.facing_share == 0.0


def test_irreproducible_readings_are_pinned() -> None:
    """把「上一轮两组读数复现不出来」钉成常量：公布值与本实现值各自固定且不同。"""
    gaps = judgment.IRREPRODUCIBLE_REFERENCE["previous_opportunity_gaps_pp"]
    assert gaps["published"] != gaps["this_implementation"]
    assert gaps["this_implementation"]["entry"] == (30.71, 54.92, 24.22)
    assert gaps["this_implementation"]["active"] == (0.62, 0.25, 0.37)
    counts = judgment.IRREPRODUCIBLE_REFERENCE["previous_facing_pair_counts"]
    assert counts["published"] == {"short": 42, "long": 1303}
    assert counts["this_implementation"] == {"short": 175, "long": 5191}
    assert "不可考" in judgment.IRREPRODUCIBLE_NOTE


# ---------------------------------------------------------------------------
# 黄金样本：用已封存的外部工件断言复现性
# ---------------------------------------------------------------------------

v7_available = pytest.mark.skipif(
    not (V7_DIR / "runs/stage-b/mixed-validation-stage-B.json").exists(),
    reason="上一轮的外部证据目录不在本机",
)
v8_available = pytest.mark.skipif(
    not (V8_DIR / "runs/stage-b/mixed-validation-stage-B.json").exists(),
    reason="第四套外部证据目录不在本机",
)


def sealed(root: Path, relative: str) -> dict:
    with open(root / relative, encoding="utf-8") as handle:
        return json.load(handle)


def valuation_rows(root: Path) -> list[dict]:
    """按清单种子序取出估值块的逐节点分布行。"""
    manifest = sealed(root, "input/frozen-fixture-manifest.json")
    report = sealed(root, "runs/stage-b/mixed-validation-stage-B.json")
    block = manifest["seeds"][judgment.VALUATION_BLOCK_INDEX]
    return [row for row in report["behavior"]["nodes"] if row["seed_block"] == block]


@pytest.mark.parametrize("root,digests", [(V7_DIR, V7_DIGESTS), (V8_DIR, V8_DIGESTS)])
def test_sealed_artifacts_are_unchanged(root: Path, digests: dict[str, str]) -> None:
    """黄金样本依赖的工件必须逐字未变；变了就说明证据被改写过。"""
    for relative, expected in digests.items():
        assert _sha256(root / relative) == expected, relative


@v7_available
def test_previous_round_readings_are_reproduced() -> None:
    """上一轮的可复现项逐位复现：覆盖率、类型熵、额度锚点、逐族收益、短长段。"""
    report = sealed(V7_DIR, "runs/stage-b/mixed-validation-stage-B.json")
    rows = valuation_rows(V7_DIR)
    coverage = judgment.coverage_reading(rows)
    assert coverage.share == pytest.approx(0.3982, abs=5e-5)
    assert coverage.preflop_share == pytest.approx(0.5638, abs=5e-5)
    assert coverage.facing_bet_share == pytest.approx(0.3069, abs=5e-5)
    assert coverage.free_action_share == pytest.approx(0.0)
    assert coverage.node_share == pytest.approx(0.5040, abs=5e-5)
    entropy = judgment.entropy_reading(rows)
    assert entropy.per_style["tight"] == pytest.approx(0.3181, abs=5e-5)
    assert entropy.per_style["aggressive"] == pytest.approx(0.4221, abs=5e-5)
    assert entropy.per_style["calling"] == pytest.approx(0.3838, abs=5e-5)
    scale = judgment.scale_anchor_reading(rows)
    assert (scale.anchor_satisfied, scale.unit_total) == (237, 237)
    assert scale.mean_scale_entropy == pytest.approx(1.3999, abs=5e-5)
    families = judgment.family_reading(report, "上一轮阶段回执")
    assert {f.opponent: f.net_chips for f in families} == {
        "aggression-rate-probe": 44493,
        "fixed-pressure-probe": 114981,
        "heuristic@1": -19893,
        "marginal-call-pressure-probe": 165536,
        "passive-call-probe": 22975,
        "position-pressure-probe": 28964,
        "random@1": 120520,
        "size-signal-probe": 14093,
    }
    diagnostic = judgment.targeting_diagnostic(
        sealed(V7_DIR, "runs/stage-b/mixed-observations-stage-B.json"),
        sealed(V7_DIR, "input/frozen-fixture-manifest.json"),
        "上一轮观测",
    )
    gains = {f.opponent: f.gain_bb_per_100 for f in diagnostic.families}
    assert gains["aggression-rate-probe"] == pytest.approx(599.39, abs=0.005)
    assert gains["heuristic@1"] == pytest.approx(-719.50, abs=0.005)
    assert gains["marginal-call-pressure-probe"] == pytest.approx(-2199.38, abs=0.005)


@v7_available
def test_previous_round_gaps_and_non_degradation_are_reproduced() -> None:
    """上一轮的两组不可复现读数与不劣化读数在本实现下各有固定值。"""
    report = sealed(V7_DIR, "runs/stage-b/mixed-validation-stage-B.json")
    rows = valuation_rows(V7_DIR)
    opportunity, _ = judgment.opportunity_reading(rows)
    pinned = judgment.IRREPRODUCIBLE_REFERENCE["previous_opportunity_gaps_pp"]
    entry = tuple(round(abs(v), 2) for v in opportunity.entry_gaps_pp.values())
    active = tuple(round(abs(v), 2) for v in opportunity.active_gaps_pp.values())
    assert entry == pinned["this_implementation"]["entry"]
    assert active == pinned["this_implementation"]["active"]
    assert entry != pinned["published"]["entry"]
    diagnostic = judgment.targeting_diagnostic(
        sealed(V7_DIR, "runs/stage-b/mixed-observations-stage-B.json"),
        sealed(V7_DIR, "input/frozen-fixture-manifest.json"),
        "上一轮观测",
    )
    counts = judgment.IRREPRODUCIBLE_REFERENCE["previous_facing_pair_counts"]
    assert diagnostic.pairs_with_facing > counts["published"]["short"]
    assert diagnostic.pairs_with_facing != sum(counts["published"].values())
    non_degradation = judgment.non_degradation_reading(report, "上一轮阶段回执")
    assert non_degradation.pairs == 16896
    assert non_degradation.players_satisfied == 0
    first = {p.player_count: p for p in non_degradation.players}[2]
    assert first.worst_family == "marginal-call-pressure-probe"
    assert first.worst_mean_bb_per_100 == pytest.approx(-522.92, abs=0.005)
    assert first.worst_lower_bound_bb_per_100 == pytest.approx(-1556.41, abs=0.005)
    assert first.worst_block_min_bb_per_100 == pytest.approx(-5160.00, abs=0.005)
    assert first.worst_block_max_bb_per_100 == pytest.approx(3216.67, abs=0.005)


@v8_available
def test_fourth_sample_set_readings_match_the_judgment_receipt() -> None:
    """第四套样本集（当前被测身份）的读数与本轮判定回执逐项一致。"""
    report = sealed(V8_DIR, "runs/stage-b/mixed-validation-stage-B.json")
    manifest = sealed(V8_DIR, "input/frozen-fixture-manifest.json")
    rows = valuation_rows(V8_DIR)
    coverage = judgment.coverage_reading(rows)
    assert coverage.share == pytest.approx(0.5333, abs=5e-5)
    assert coverage.preflop_share == pytest.approx(0.6790, abs=5e-5)
    assert coverage.facing_bet_share == pytest.approx(0.4762, abs=5e-5)
    assert coverage.free_action_share == pytest.approx(0.0)
    assert coverage.node_share == pytest.approx(0.6800, abs=5e-5)
    assert coverage.above_threshold is True
    entropy = judgment.entropy_reading(rows)
    assert entropy.per_style["tight"] == pytest.approx(0.5333, abs=5e-5)
    assert entropy.per_style["aggressive"] == pytest.approx(0.5518, abs=5e-5)
    assert entropy.per_style["calling"] == pytest.approx(0.3856, abs=5e-5)
    scale = judgment.scale_anchor_reading(rows)
    assert (scale.anchor_satisfied, scale.unit_total) == (246, 264)
    assert scale.anchor_share == pytest.approx(0.9318, abs=5e-5)
    assert scale.mean_scale_entropy == pytest.approx(1.3090, abs=5e-5)
    assert scale.anchors_above_threshold is False
    assert scale.structurally_single == 18
    opportunity, _ = judgment.opportunity_reading(rows)
    entry = tuple(round(v, 2) for v in opportunity.entry_gaps_pp.values())
    active = tuple(round(v, 2) for v in opportunity.active_gaps_pp.values())
    assert entry == (-18.57, -18.57, 0.00)
    assert active == (-4.51, -1.66, 2.85)
    assert opportunity.entry_pairs_above == 2
    assert opportunity.active_pairs_above == 0
    assert opportunity.satisfied is False
    style_js = judgment.js_reading(report)
    assert tuple(round(v, 4) for v in style_js.distances.values()) == (0.2498, 0.3156, 0.1938)
    assert style_js.thinnest_pair == "aggressive-calling"
    assert style_js.above_threshold is True
    stability = judgment.unpredictability_reading(
        report, manifest, "第四套阶段回执"
    ).stability
    assert stability.direction_stable is True
    assert (stability.consistent_combinations, stability.total_combinations) == (6, 6)
    # 直接分布不随种子块变化：稳定性读数因此是结构性必然，测试把它钉死。
    assert stability.blocks_vary is False


@v8_available
def test_fourth_sample_set_non_degradation_and_targeting() -> None:
    """第四套样本集的不劣化与抗针对读数与本轮判定回执逐项一致。"""
    report = sealed(V8_DIR, "runs/stage-b/mixed-validation-stage-B.json")
    manifest = sealed(V8_DIR, "input/frozen-fixture-manifest.json")
    non_degradation = judgment.non_degradation_reading(report, "第四套阶段回执")
    assert non_degradation.pairs == 16896
    assert non_degradation.players_satisfied == 0
    assert non_degradation.players_satisfied_block_extreme == 0
    expected = {
        2: ("random@1", -488.23),
        3: ("position-pressure-probe", -1556.25),
        4: ("fixed-pressure-probe", -1011.20),
        5: ("marginal-call-pressure-probe", -1497.75),
        6: ("marginal-call-pressure-probe", -1541.49),
        7: ("marginal-call-pressure-probe", -880.80),
        8: ("random@1", -935.62),
        9: ("size-signal-probe", -652.13),
    }
    for player in non_degradation.players:
        family, mean = expected[player.player_count]
        assert player.worst_family == family
        assert player.worst_mean_bb_per_100 == pytest.approx(mean, abs=0.005)
    assert non_degradation.total_net_chips_mixed == 1472108
    assert non_degradation.total_net_chips_legacy == 1967319
    assert non_degradation.blocks_mixed_higher == 4
    families = judgment.family_reading(report, "第四套阶段回执")
    assert {f.opponent: f.net_chips for f in families} == {
        "aggression-rate-probe": 227509,
        "fixed-pressure-probe": 241291,
        "heuristic@1": 21429,
        "marginal-call-pressure-probe": 300232,
        "passive-call-probe": 200260,
        "position-pressure-probe": 208327,
        "random@1": 226202,
        "size-signal-probe": 46858,
    }
    diagnostic = judgment.targeting_diagnostic(
        sealed(V8_DIR, "runs/stage-b/mixed-observations-stage-B.json"), manifest, "第四套观测"
    )
    assert diagnostic.pairs == 16896
    assert diagnostic.pairs_with_facing == 5507
    assert diagnostic.facing_share == pytest.approx(0.3259, abs=5e-5)
    gains = {f.opponent: f.gain_bb_per_100 for f in diagnostic.families}
    assert gains["aggression-rate-probe"] == pytest.approx(2357.51, abs=0.005)
    assert gains["size-signal-probe"] == pytest.approx(-19.96, abs=0.005)
    buckets = {(b.dimension, b.bucket): b for b in diagnostic.buckets}
    no_facing = (judgment.SCALE_BUCKET_DIMENSION, judgment.NO_FACING_BUCKET)
    assert buckets[no_facing].long_pairs == 11047
    assert buckets[(judgment.SCALE_BUCKET_DIMENSION, "≤50%")].short_pairs == 33
    assert buckets[(judgment.STREET_BUCKET_DIMENSION, "river")].short_pairs == 0


@v8_available
def test_fourth_sample_set_mechanics_and_cost() -> None:
    """机制与成本读数：违规与截断为零、摘要一致、重放逐手一致、硬预算未触发。"""
    payload = judgment.judge(
        manifest_path=str(V8_DIR / "input/frozen-fixture-manifest.json"),
        reports=[("阶段 B", str(V8_DIR / "runs/stage-b/mixed-validation-stage-B.json"))],
        observations_path=str(V8_DIR / "runs/stage-b/mixed-observations-stage-B.json"),
        recheck_paths=[
            ("阶段 A 补算", str(V8_DIR / "runs/stage-a-recheck/mixed-recheck-stage-A.json")),
            ("阶段 B 补算", str(V8_DIR / "runs/stage-b-recheck/mixed-recheck-stage-B.json")),
        ],
        allow_judgment=True,
    )
    assert payload.valuation_seed_block == 2992123152
    assert payload.mechanics.violations == ()
    assert payload.mechanics.truncated_hands == 0
    assert payload.mechanics.digests_consistent is True
    assert payload.mechanics.replay_hands_compared == 128 + 33792
    assert payload.mechanics.replay_net_chips_exact is True
    assert payload.mechanics.replay_behavior_exact is True
    assert payload.cost.hard_budget_satisfied is True
    assert payload.cost.guidance_satisfied is True
    assert payload.cost.timeout_count == 0
    assert payload.cost.per_player_timeouts == {player: 0 for player in range(2, 10)}
    assert payload.cost.per_player_p95_range[0] == pytest.approx(0.3417, abs=5e-5)
    assert payload.cost.per_player_p95_range[1] == pytest.approx(0.3798, abs=5e-5)
    assert payload.unpredictability.unsatisfied_items == (
        "额度锚点档数",
        "两个机会域的风格可分度",
    )
    assert payload.non_degradation.satisfied is False


@v8_available
def test_judgment_payload_is_deterministic() -> None:
    """同一批工件重复判定必须得到同一载荷：口径不得依赖字典序或时间。"""
    arguments = {
        "manifest_path": str(V8_DIR / "input/frozen-fixture-manifest.json"),
        "reports": [("阶段 B", str(V8_DIR / "runs/stage-b/mixed-validation-stage-B.json"))],
        "observations_path": str(V8_DIR / "runs/stage-b/mixed-observations-stage-B.json"),
        "allow_judgment": True,
    }
    assert judgment.judge(**arguments).model_dump_json() == judgment.judge(
        **arguments
    ).model_dump_json()


def test_module_registers_pins_and_limitations() -> None:
    """判定器必须显式登记实现层钉子与适用边界，便于审阅时逐条核对。"""
    assert judgment.JUDGMENT_PAYLOAD_VERSION == "mixed-judgment-payload.v1"
    assert len(judgment.PINS) >= 10
    assert any("清单种子序" in pin for pin in judgment.PINS)
    assert any("不落盘" in line or "不写出任何文件" in line for line in judgment.LIMITATIONS)
