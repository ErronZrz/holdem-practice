"""行为诊断模块的实现层测试：合成用例锁口径，黄金样本锁复现性。

两层用意：
- 合成用例：把面对状态、街道取值、焦点动作筛选与桶聚合的自由度钉死在测试里；
- 黄金样本：用已封存的 v8 工件断言读数逐位复现；工件缺失时自动跳过，
  使本测试在没有外部证据的机器上仍可运行。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests import mixed_bot_behavior_diagnostic as diagnostic
from tests.mixed_bot_behavior_diagnostic import BehaviorDiagnosticError

V8_DIR = Path("/Users/bryanylliu/holdem-mixed-bot-validation-v8")

# 已封存工件的摘要：黄金样本测试前先核对，避免工件被改写后仍「通过」。
V8_DIGESTS = {
    "runs/stage-b/mixed-validation-stage-B.json":
        "6d3838fb09d9b419bb4d9f16b510a692989428c2064c7ef4716fa8b682fff27b",
    "runs/stage-b/mixed-observations-stage-B.json":
        "087e0d024658c7e75038977f82c5ab392754c3688fe5f56cce3990fc09425132",
}

V8_OBSERVATIONS = V8_DIR / "runs/stage-b/mixed-observations-stage-B.json"
V8_REPORT = V8_DIR / "runs/stage-b/mixed-validation-stage-B.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 合成夹具
# ---------------------------------------------------------------------------


def action(street: str, seat: int, label: str, amount: int = 0) -> dict[str, object]:
    """造一条公开动作行。"""
    return {"street": street, "seat": seat, "action": label, "amount": amount}


def hand_row(
    *,
    arm: str,
    rotation: int = 0,
    player_count: int = 2,
    style: str = "tight",
    opponent: str = "probe",
    block: int = 7,
    net_chips: int = 0,
    actions: list[dict[str, object]] | None = None,
    pots: dict[str, int] | None = None,
    strength: object = "weak",
) -> dict[str, object]:
    """造一条观测逐手行；牌力档可显式置空以覆盖缺失分支。"""
    row: dict[str, object] = {
        "hand_index": 0,
        "player_count": player_count,
        "style": style,
        "opponent": opponent,
        "arm": arm,
        "seed_block": block,
        "rotation": rotation,
        "actions": actions or [],
        "pot_after_street": pots or {},
        "net_chips": net_chips,
    }
    if strength is not None:
        row["focus_strength_bucket"] = strength
    return row


def pair(
    *,
    rotation: int,
    mixed_net: int,
    legacy_net: int,
    mixed_actions: list[dict[str, object]],
    legacy_actions: list[dict[str, object]],
    pots: dict[str, int] | None = None,
    mixed_strength: object = "weak",
    player_count: int = 2,
    opponent: str = "probe",
) -> list[dict[str, object]]:
    """造一对同键的两臂观测行。"""
    common = {
        "rotation": rotation,
        "player_count": player_count,
        "opponent": opponent,
        "pots": pots,
    }
    return [
        hand_row(
            arm="mixed-focus",
            net_chips=mixed_net,
            actions=mixed_actions,
            strength=mixed_strength,
            **common,
        ),
        hand_row(arm="legacy-focus", net_chips=legacy_net, actions=legacy_actions, **common),
    ]


def write_observations(tmp_path: Path, hands: list[dict[str, object]]) -> str:
    """把合成观测写成临时工件，返回路径。"""
    path = tmp_path / "observations.json"
    path.write_text(
        json.dumps({"strategy_id": "synthetic@0", "hands": hands}, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(path)


SYNTHETIC_HANDS: list[dict[str, object]] = [
    # 轮换 0：焦点在 0 号座，翻前主动后手下注，整手无「面对」事件。
    *pair(
        rotation=0,
        mixed_net=100,
        legacy_net=40,
        mixed_actions=[action("preflop", 1, "call"), action("preflop", 0, "raise", 20)],
        legacy_actions=[action("preflop", 0, "call")],
        mixed_strength="strong",
    ),
    # 轮换 1：焦点在 1 号座，翻牌面对 0 号座的下注后跟注。
    *pair(
        rotation=1,
        mixed_net=-50,
        legacy_net=10,
        mixed_actions=[action("flop", 0, "bet", 30), action("flop", 1, "call")],
        legacy_actions=[action("flop", 0, "bet", 30), action("flop", 1, "raise", 90)],
        pots={"preflop": 20},
        mixed_strength=None,
    ),
]


def diagnose_synthetic(tmp_path: Path, hands: list[dict[str, object]] | None = None):
    """对合成观测跑一次诊断。"""
    return diagnostic.diagnose(
        observations_path=write_observations(tmp_path, hands or SYNTHETIC_HANDS),
        allow_diagnosis=True,
    )


# ---------------------------------------------------------------------------
# 合成用例
# ---------------------------------------------------------------------------


def test_diagnose_requires_explicit_permission(tmp_path: Path) -> None:
    """未显式允许时不得计算，也不得触碰任何工件。"""
    missing = tmp_path / "不存在.json"
    with pytest.raises(BehaviorDiagnosticError, match="默认拒绝"):
        diagnostic.diagnose(observations_path=str(missing), allow_diagnosis=False)


def test_diagnose_rejects_artifact_without_hands(tmp_path: Path) -> None:
    """工件缺少逐手粒度时显式失败，不回退到任何均值。"""
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"strategy_id": "x"}), encoding="utf-8")
    with pytest.raises(BehaviorDiagnosticError, match="hands"):
        diagnostic.diagnose(observations_path=str(path), allow_diagnosis=True)


def test_diagnose_rejects_incomplete_pairs(tmp_path: Path) -> None:
    """缺少任一臂的配对必须显式失败，不得静默丢弃。"""
    hands = [hand_row(arm="mixed-focus", net_chips=1)]
    with pytest.raises(BehaviorDiagnosticError, match="不完整配对"):
        diagnose_synthetic(tmp_path, hands)


def test_facing_state_uses_first_facing_event_street() -> None:
    """有「面对」事件时街道取该事件的街，而不是最后一次动作的街。"""
    hand = hand_row(
        arm="mixed-focus",
        rotation=1,
        actions=[
            action("flop", 0, "bet", 30),
            action("flop", 1, "call"),
            action("turn", 1, "check"),
        ],
        pots={"preflop": 20},
    )
    assert diagnostic.facing_state_and_street(hand) == ("facing-bet", "flop")


def test_no_facing_street_uses_last_focus_action() -> None:
    """无「面对」事件时街道取焦点座位最后一次动作所在的街。"""
    hand = hand_row(
        arm="mixed-focus",
        rotation=0,
        actions=[action("preflop", 1, "call"), action("preflop", 0, "raise", 20)],
    )
    assert diagnostic.facing_state_and_street(hand) == ("no-facing-bet", "preflop")


def test_no_facing_without_focus_action_is_listed_separately() -> None:
    """焦点整手未行动时单列，不用其它街代替。"""
    hand = hand_row(arm="mixed-focus", rotation=1, actions=[action("preflop", 0, "fold")])
    state, street = diagnostic.facing_state_and_street(hand)
    assert (state, street) == ("no-facing-bet", diagnostic.NO_ACTION_STREET)


def test_action_units_count_only_focus_seat() -> None:
    """行为构成只统计焦点座位的动作；同一手内多次动作按次数计。"""
    hand = hand_row(
        arm="mixed-focus",
        rotation=0,
        actions=[
            action("preflop", 1, "raise", 30),
            action("preflop", 0, "call"),
            action("flop", 0, "bet", 40),
        ],
    )
    units = diagnostic._unit_map(diagnostic.focus_action_rows(hand))
    assert units == {"call": 1, "bet": 1}
    assert diagnostic._active_share(units) == pytest.approx(0.5)


def test_strength_label_falls_back_when_field_missing_or_blank() -> None:
    """牌力档直读字段；缺失或空串时单列。"""
    assert diagnostic.strength_label(hand_row(arm="mixed-focus", strength="strong")) == "strong"
    assert diagnostic.strength_label(hand_row(arm="mixed-focus", strength=None)) == "None"
    assert diagnostic.strength_label(hand_row(arm="mixed-focus", strength="")) == "None"


def test_bucket_differences_marginals_and_cells(tmp_path: Path) -> None:
    """差分、边际与五维格按固定桶序输出，数值口径可逐项核对。"""
    payload = diagnose_synthetic(tmp_path)
    assert (payload.pairs, payload.pair_anomalies) == (2, 0)
    assert (payload.facing_pairs, payload.no_facing_pairs) == (1, 1)
    assert payload.total_diff_net_chips == 0  # 60 与 -60 相消
    assert payload.facing_diff_net_chips == -60
    assert payload.no_facing_diff_net_chips == 60
    # 总差为 0 时占比显式归零，不产生 NaN。
    assert payload.no_facing_diff_share == 0.0

    states = {row.bucket: row for row in payload.by_facing_state}
    assert states["facing-bet"].pairs == 1
    assert states["facing-bet"].mixed_action_units == {"call": 1}
    assert states["facing-bet"].legacy_action_units == {"raise": 1}
    assert states["facing-bet"].mixed_active_share == pytest.approx(0.0)
    assert states["facing-bet"].legacy_active_share == pytest.approx(1.0)
    assert states["no-facing-bet"].mixed_action_units == {"raise": 1}
    assert states["no-facing-bet"].legacy_action_units == {"call": 1}

    streets = {row.bucket: row for row in payload.by_street}
    assert sorted(streets) == ["flop", "preflop"]
    assert streets["flop"].diff_net_chips == -60
    assert streets["preflop"].diff_net_chips == 60

    strengths = {row.bucket: row for row in payload.by_strength}
    assert sorted(strengths) == ["None", "strong"]

    assert len(payload.cells) == 2
    keys = [
        (cell.player_count, cell.style, cell.strength, cell.street, cell.facing_state)
        for cell in payload.cells
    ]
    assert keys == sorted(keys)
    gaps = {cell.diff_net_chips: cell.active_share_gap for cell in payload.cells}
    assert gaps[-60] == pytest.approx(-1.0)
    assert gaps[60] == pytest.approx(1.0)


def test_sparse_bucket_is_flagged_not_dropped(tmp_path: Path) -> None:
    """低于稀疏线的桶照样输出并标记，避免小样本被当成结论。"""
    payload = diagnose_synthetic(tmp_path)
    assert all(row.sparse for row in payload.by_street)
    assert all(row.sparse for row in payload.cells)


def test_bb_conversion_uses_pinned_big_blind(tmp_path: Path) -> None:
    """每百手差按固定大盲换算；同口径换算下两对差值的均值可逐项核对。"""
    payload = diagnose_synthetic(tmp_path)
    streets = {row.bucket: row for row in payload.by_street}
    assert streets["flop"].mean_bb_per_100_diff == pytest.approx(-60 * 100 / 10)
    assert streets["preflop"].mean_bb_per_100_diff == pytest.approx(60 * 100 / 10)


def test_cross_check_rejects_report_with_mismatched_conversion(tmp_path: Path) -> None:
    """报告与固定大盲口径不一致时停止诊断，不静默继续。"""
    observations = write_observations(tmp_path, SYNTHETIC_HANDS)
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "matches": {
                    "rows": [
                        {
                            "player_count": 2,
                            "style": "tight",
                            "opponent": "probe",
                            "arm": "mixed-focus",
                            "seed_block": 7,
                            "rotation": 0,
                            "hands": 1,
                            "truncated_hands": 0,
                            "net_chips": -10,
                            "bb_per_100": -50.0,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(BehaviorDiagnosticError, match="换算"):
        diagnostic.diagnose(
            observations_path=observations,
            report_path=str(report),
            allow_diagnosis=True,
        )


def test_cross_check_accepts_consistent_report(tmp_path: Path) -> None:
    """换算一致时交叉核对通过，正常出载荷。"""
    observations = write_observations(tmp_path, SYNTHETIC_HANDS)
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "matches": {
                    "rows": [
                        {
                            "player_count": 2,
                            "style": "tight",
                            "opponent": "probe",
                            "arm": "mixed-focus",
                            "seed_block": 7,
                            "rotation": 0,
                            "hands": 1,
                            "truncated_hands": 0,
                            "net_chips": -10,
                            "bb_per_100": -100.0,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    payload = diagnostic.diagnose(
        observations_path=observations,
        report_path=str(report),
        allow_diagnosis=True,
    )
    assert payload.pairs == 2


# ---------------------------------------------------------------------------
# 黄金样本
# ---------------------------------------------------------------------------


def _require_v8() -> None:
    if not V8_OBSERVATIONS.exists():
        pytest.skip("v8 观测工件不在本机，跳过黄金样本")
    for relative, expected in V8_DIGESTS.items():
        actual = _sha256(V8_DIR / relative)
        assert actual == expected, f"{relative} 摘要与封存值不一致，停止复现"


def test_golden_v8_readings_reproduce() -> None:
    """已封存 v8 工件上的读数逐项复现。"""
    _require_v8()
    payload = diagnostic.diagnose(
        observations_path=str(V8_OBSERVATIONS),
        report_path=str(V8_REPORT),
        allow_diagnosis=True,
    )
    assert payload.payload_version == diagnostic.DIAGNOSTIC_PAYLOAD_VERSION
    assert payload.strategy_id == "mixed-local@6"
    assert (payload.pairs, payload.pair_anomalies) == (16_896, 0)
    assert (payload.facing_pairs, payload.no_facing_pairs) == (5_507, 11_389)
    assert payload.total_diff_net_chips == -495_211
    assert payload.facing_diff_net_chips == -148_270
    assert payload.no_facing_diff_net_chips == -346_941
    assert payload.no_facing_diff_share == pytest.approx(0.7005922727887709)

    states = {row.bucket: row for row in payload.by_facing_state}
    assert states["facing-bet"].mixed_active_share == pytest.approx(0.06772764264400036)
    assert states["facing-bet"].legacy_active_share == pytest.approx(0.038232288828337874)

    strengths = {row.bucket: row for row in payload.by_strength}
    assert strengths["strong"].pairs == 941
    assert strengths["strong"].diff_net_chips == -149_237
    assert strengths["strong"].mixed_active_share == pytest.approx(0.24882137244630698)
    assert strengths["strong"].legacy_active_share == pytest.approx(0.1923828125)

    assert len(payload.cells) == 516


def test_golden_v8_cell_for_no_facing_preflop_medium() -> None:
    """9 人桌翻前无人下注、中等牌力、紧手档的格可逐项复现。"""
    _require_v8()
    payload = diagnostic.diagnose(
        observations_path=str(V8_OBSERVATIONS),
        allow_diagnosis=True,
    )
    key = ("no-facing-bet", "medium", "preflop", 9, "tight")
    matches = [
        cell
        for cell in payload.cells
        if (cell.facing_state, cell.strength, cell.street, cell.player_count, cell.style) == key
    ]
    assert len(matches) == 1
    cell = matches[0]
    assert cell.pairs == 200
    assert cell.diff_net_chips == -44_907
    assert cell.mixed_active_share == pytest.approx(0.0)
    assert cell.legacy_active_share == pytest.approx(0.11171662125340599)
    assert cell.active_share_gap == pytest.approx(-0.11171662125340599)


def test_golden_v8_payload_is_byte_stable() -> None:
    """同一工件重复诊断必须逐字节相同，保证读数可复算。"""
    _require_v8()
    first = diagnostic.diagnose(
        observations_path=str(V8_OBSERVATIONS),
        report_path=str(V8_REPORT),
        allow_diagnosis=True,
    )
    second = diagnostic.diagnose(
        observations_path=str(V8_OBSERVATIONS),
        report_path=str(V8_REPORT),
        allow_diagnosis=True,
    )
    assert first.model_dump_json() == second.model_dump_json()
