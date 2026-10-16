"""手牌诊断脚本：用注入的牌局确认能按座位和街拆开混合策略。"""

import tools.diagnose_bot_hand as diagnose
from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.storage.hand_history import build_hand_history

_HOLES = (
    ("As", "Kd"),
    ("2c", "3c"),
    ("4d", "5d"),
    ("6h", "7h"),
    ("8s", "9s"),
    ("Tc", "Jc"),
)


def _folded_history() -> dict:
    """六人桌翻前依次弃牌，直到这手结束。玩家4 会在其中弃牌。"""
    engine = PokerEngine(6, 10, 20, 2000)
    holes = {
        seat: [card_from_str(a), card_from_str(b)] for seat, (a, b) in enumerate(_HOLES)
    }
    engine.start_hand_with(0, holes, [])
    while not engine.hand_over:
        engine.apply_action(Action(ActionType.FOLD))
    return build_hand_history(engine, 1, human_seat=0, bot_strategy="mixed-local@12")


def test_fold_exposes_style_and_three_modes() -> None:
    history = _folded_history()
    result = diagnose.diagnose_history(history, hand_id="sample", seats={4}, streets={"preflop"})
    assert result["rules_identity"] == "mixed-local@12"
    assert result["styles"][4] == "tight"
    assert len(result["decisions"]) == 1
    decision = result["decisions"][0]
    assert decision["actual"]["action"] == "fold"
    assert {mode["mode"] for mode in decision["modes"]} == {"cautious", "normal", "pressed"}
    total = sum(item["pct"] for item in decision["marginal_80_10_10"])
    assert abs(total - 100) < 1


def test_street_filter_skips_preflop_only_actions() -> None:
    history = _folded_history()
    result = diagnose.diagnose_history(history, seats={4}, streets={"flop"})
    assert result["decisions"] == []


def test_bad_identity_override_names_the_given_value() -> None:
    history = _folded_history()
    result = diagnose.diagnose_history(history, identity="absent@1")
    assert "absent@1" in result["error"]


def test_unknown_strategy_is_reported_without_replaying() -> None:
    history = _folded_history()
    history["bot_strategy"] = "heuristic@1"
    result = diagnose.diagnose_history(history)
    assert "混合规则" in result["error"]


def test_street_alias_accepts_chinese_names() -> None:
    assert diagnose.parse_streets(["转牌", "river"]) == {"turn", "river"}
