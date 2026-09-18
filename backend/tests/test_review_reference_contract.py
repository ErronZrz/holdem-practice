"""复盘参考契约测试：来源/版本/适用域/覆盖可追溯、非众数不判错、保护判据未被改动。"""

import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.analysis.hand_review as hand_review_module
from app.analysis.hand_review import _detect_mistakes, build_review
from app.analysis.reference_identity import (
    CACHE_KEY_VERSION,
    EVALUATION_VERSION,
    REFERENCE_VERSION,
    reference_declaration,
    reference_identity,
)
from app.main import app
from app.poker.actions import Action, ActionType
from app.poker.engine import PokerEngine
from app.storage.db import init_db
from app.storage.hand_history import build_hand_history

from .helpers import cards

# 错误判定允许产出的全部错误码；非众数本身不在其中。
_KNOWN_MISTAKE_CODES = {
    "bad_call",
    "bad_fold",
    "slowplay",
    "over_aggressive",
    "value_missed",
    "underbet",
    "air_bluff",
}

# 不得用于标注参考的求解器/最优性字样（"均衡" 只允许出现在否定语境）。
_FORBIDDEN_TOKENS = ("gto", "nashconv", "exploitab", "最优")

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    init_db(str(tmp_path / "test.db"))
    monkeypatch.setattr("app.api.games.BOT_DELAY", 0.0)
    yield


def _play(moves: list[ActionType], *, button: int, hole: dict, board: list) -> dict:
    """按给定动作脚本打完一手牌并返回复盘结果。"""
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(button=button, hole_cards=hole, board=board)
    for action_type in moves:
        engine.apply_action(Action(action_type))
    assert engine.hand_over
    return build_review(build_hand_history(engine, hand_number=1, human_seat=0))


def _limp_miss_review() -> dict:
    """真人是小盲、用垃圾牌补齐盲注：真人动作（跟注）不是参考众数（弃牌）。"""
    return _play(
        [ActionType.CALL, *([ActionType.CHECK] * 7)],
        button=0,
        hole={0: cards("7c 2d"), 1: cards("As Ad")},
        board=cards("Kc Qd 9h Ts 3c"),
    )


def _value_missed_review() -> dict:
    """真人是大盲、持 AA 在无人下注时过牌：命中既有的价值丢失判据。"""
    return _play(
        [ActionType.CALL, *([ActionType.CHECK] * 7)],
        button=1,
        hole={0: cards("As Ad"), 1: cards("7c 2d")},
        board=cards("2c 7d 9h 3s Kd"),
    )


def _assert_no_solver_labels(text: str) -> None:
    """断言文本未把参考表述为求解器/均衡/最优打法。"""
    lowered = text.lower()
    for token in _FORBIDDEN_TOKENS:
        assert token not in lowered, f"出现禁止字样：{token}"
    assert re.search(r"(?<!非)均衡", text) is None, "「均衡」只能出现在否定语境"


# ------------------------------------------------------------------ 契约可追溯


def test_reference_declaration_extends_identity() -> None:
    # 参考契约在版本身份之上叠加适用域与局限，不复制既有取值。
    declaration = reference_declaration()
    assert {key: declaration[key] for key in reference_identity()} == reference_identity()
    assert isinstance(declaration["reference_scope"], str) and declaration["reference_scope"]
    limitations = declaration["reference_limitations"]
    assert isinstance(limitations, list) and limitations
    assert all(isinstance(item, str) and item for item in limitations)


def test_review_uses_the_single_source_declaration() -> None:
    review = _limp_miss_review()
    for key, value in reference_declaration().items():
        assert review[key] == value


def test_review_endpoint_declares_the_contract() -> None:
    client = TestClient(app)
    created = client.post("/games", json={"num_players": 2, "target_hands": 5, "seed": 7}).json()
    finished = client.post(
        f"/games/{created['session_id']}/actions", json={"action": "fold"}
    ).json()
    body = client.get(f"/hands/{finished['last_hand_id']}/review").json()

    for key, value in reference_declaration().items():
        assert body[key] == value


def test_reference_source_literal_is_single() -> None:
    # 参考来源字面量在 analysis 与 api 层只允许出现一次（唯一事实源）。
    hits: list[str] = []
    for folder in ("analysis", "api"):
        for path in (_REPO_ROOT / "backend" / "app" / folder).rglob("*.py"):
            hits.extend(
                f"{path.name}" for _ in re.finditer("heuristic-conservative", path.read_text())
            )
    assert hits == ["reference_identity.py"]


# ------------------------------------------------------------------ 非 GTO 标注


def test_limitations_disclose_scope_and_non_mode_rule() -> None:
    declaration = reference_declaration()
    text = declaration["reference_scope"] + "".join(declaration["reference_limitations"])
    _assert_no_solver_labels(text)
    assert "非均衡" in text
    assert "众数不同" in text, "必须声明非众数动作本身不构成错误"


def test_frontend_reference_text_has_no_solver_labels() -> None:
    source = (_REPO_ROOT / "frontend" / "src" / "reviewText.js").read_text()
    _assert_no_solver_labels(source)
    assert "export function referenceScopeText" in source
    assert "export function referenceLimitationText" in source


def test_both_review_views_render_scope_and_limitations() -> None:
    for name in ("HistoryView.vue", "GameTable.vue"):
        source = (_REPO_ROOT / "frontend" / "src" / "components" / name).read_text()
        assert "referenceScopeText(review)" in source
        assert "referenceLimitationText(review)" in source
        _assert_no_solver_labels(source)


# ------------------------------------------------------------------ 非众数不判错


def test_mistake_detection_does_not_read_reference_distribution() -> None:
    # 判据函数既不接收分布/众数参数，也不在实现中引用它们。
    params = set(inspect.signature(_detect_mistakes).parameters)
    assert params == {
        "action",
        "equity",
        "pot_odds",
        "to_call",
        "pot",
        "can_raise",
        "hole_cards",
        "board",
        "big_blind",
    }
    source = inspect.getsource(_detect_mistakes)
    assert "bot_distribution" not in source
    assert "_mode_action" not in source


def test_non_mode_action_without_existing_rule_is_not_flagged() -> None:
    # 跟注不等于参考众数（弃牌），但没有命中任何既有判据，故不产生错误标记。
    review = _limp_miss_review()
    preflop = review["decisions"][0]
    assert preflop["street"] == "preflop"
    assert preflop["action"]["action"] == "call"
    assert preflop["bot_action"]["action"] == "fold"
    assert preflop["bot_action"]["action"] != preflop["action"]["action"]
    assert preflop["mistakes"] == []


def test_mistake_codes_come_only_from_existing_rules() -> None:
    codes = {
        mistake["code"]
        for review in (_limp_miss_review(), _value_missed_review())
        for decision in review["decisions"]
        for mistake in decision["mistakes"]
    }
    assert "value_missed" in codes, "样例应至少命中一个既有判据，否则本用例无意义"
    assert codes <= _KNOWN_MISTAKE_CODES


# ------------------------------------------------------------------ 保护判据冻结


def test_conservative_protection_constants_are_frozen() -> None:
    module = hand_review_module
    assert module._EQUITY_SAMPLES == 1000
    assert module._REVIEW_SEED == 0
    assert module._FOLD_EV_MARGIN == 0.15
    assert module._FOLD_BET_SCALE == 0.10
    assert module._FOLD_MIN_EQ_PREFLOP == 0.55
    assert module._BAD_CALL_EQ_MARGIN == 0.03
    assert module._VALUE_BET_EQ == 0.80
    assert module._UNDERBET_EQ == 0.80
    assert module._UNDERBET_DEN == 2
    assert module._SLOWPLAY_EQ == 0.90
    assert module._AIR_EQ == 0.25
    assert module._OVER_AGGRESSIVE_EQ == 0.50
    assert module._STRONG_DRAW_OUTS == 8
    assert module._SMALL_BET_NUM == 1
    assert module._SMALL_BET_DEN == 3
    assert module._DRAW_MARGIN_SCALE == 0.5
    # 误弃容差随跟注占底池比例放大：跟注半池时余量为 0.15 + 0.10 × 0.5。
    assert module._fold_margin(100, 200) == pytest.approx(0.20)


def test_reference_semantics_versions_unchanged() -> None:
    # 本轮只新增声明性字段，参考语义与版本号不变。
    assert REFERENCE_VERSION == 1
    assert EVALUATION_VERSION == 1
    assert CACHE_KEY_VERSION == 1
    assert reference_identity()["reference_strategy"] == "heuristic-conservative"
