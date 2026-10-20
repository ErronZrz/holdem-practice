"""复盘诊断脚本：用注入的决策点核对矛盾分类，并用短牌局核对重放。"""

import sqlite3

import pytest

import tools.diagnose_review as diagnose
from app.llm.coach import PROMPT_SCHEMA_VERSION
from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str as card
from app.poker.engine import PokerEngine
from app.storage.hand_history import build_hand_history


def _point(**overrides) -> dict:
    """一份没有矛盾的翻后过牌，供各用例改一两项。"""
    base = {
        "to_call": 0,
        "call_ev": None,
        "equity": 0.62,
        "opponents": 1,
        "street": "flop",
        "big_blind": 20,
        "mode": "check",
        "mode_amount": 0,
        "distribution": [{"action": "check", "amount": 0, "probability": 1.0}],
        "player_action": "check",
        "mistakes": [],
        "recent_aggression": 0,
        "max_line": 0,
        "base": 400,
        "score": 420,
        "value_threshold": 650,
        "fold_probe_bad_fold": False,
        "coach": None,
    }
    base.update(overrides)
    return base


def test_negative_call_keeps_raise_and_zero_call_amount() -> None:
    # 跟注期望为负且众数是加注时，保护不会改写加注，跟注金额仍是 0。
    codes = diagnose.classify_point(
        _point(
            to_call=160,
            call_ev=-20.0,
            mode="raise",
            mode_amount=200,
            player_action="call",
            mistakes=["bad_call"],
            distribution=[
                {"action": "raise", "amount": 200, "probability": 0.55},
                {"action": "call", "amount": 0, "probability": 0.45},
            ],
        )
    )
    assert "a_negative_continue" in codes
    assert "a_mode_raise" in codes
    assert "a_bad_call_vs_raise" in codes
    assert "d_call_amount_zero" in codes
    assert "e_marked_despite_mass" in codes


def test_guarded_fold_with_no_continue_mass_is_not_type_a() -> None:
    codes = diagnose.classify_point(
        _point(
            to_call=40,
            call_ev=-8.0,
            mode="fold",
            distribution=[{"action": "fold", "amount": 0, "probability": 1.0}],
            player_action="call",
            mistakes=["bad_call"],
        )
    )
    assert "a_negative_continue" not in codes
    assert "d_call_amount_zero" not in codes


def test_positive_fold_splits_cheap_blind_from_postflop() -> None:
    cheap = diagnose.classify_point(
        _point(
            street="preflop",
            to_call=10,
            big_blind=20,
            call_ev=4.0,
            mode="fold",
            distribution=[{"action": "fold", "amount": 0, "probability": 1.0}],
        )
    )
    assert "b_cheap_preflop" in cheap
    assert "b_postflop" not in cheap

    priced = diagnose.classify_point(
        _point(
            street="preflop",
            to_call=60,
            big_blind=20,
            call_ev=12.0,
            mode="fold",
            distribution=[{"action": "fold", "amount": 0, "probability": 1.0}],
        )
    )
    assert "b_priced_preflop" in priced

    postflop = diagnose.classify_point(
        _point(
            street="turn",
            to_call=80,
            call_ev=30.0,
            mode="fold",
            fold_probe_bad_fold=True,
            player_action="fold",
            mistakes=["bad_fold"],
            distribution=[{"action": "fold", "amount": 0, "probability": 0.8}],
        )
    )
    assert "b_postflop" in postflop
    assert "b_would_flag_bad_fold" in postflop
    assert "e_bad_fold_matches_reference" in postflop


def test_stale_line_still_bets_a_made_hand_below_the_value_gate() -> None:
    # 本街对手还没进攻，行动线却已经偏高，评分没过门槛仍主动下注。
    codes = diagnose.classify_point(
        _point(
            street="turn",
            to_call=0,
            call_ev=None,
            equity=0.19,
            opponents=1,
            mode="bet",
            mode_amount=180,
            distribution=[{"action": "bet", "amount": 180, "probability": 0.7}],
            recent_aggression=0,
            max_line=4,
            base=700,
            score=640,
            value_threshold=700,
        )
    )
    assert "c_low_equity_lead" in codes
    assert "c_stale_line" in codes
    assert "c_static_floor" in codes
    assert "c_below_air" in codes


def test_check_mode_can_still_leave_a_low_equity_bet() -> None:
    codes = diagnose.classify_point(
        _point(
            street="river",
            equity=0.16,
            opponents=1,
            mode="check",
            distribution=[
                {"action": "check", "amount": 0, "probability": 0.65},
                {"action": "bet", "amount": 180, "probability": 0.35},
            ],
        )
    )
    assert "c_residual_lead" in codes
    assert "c_low_equity_lead" not in codes


def test_flush_draw_claim_needs_a_one_card_draw() -> None:
    text = "翻牌上击中顶对并带同花听牌，参考更偏向小注。"
    reading = diagnose.coach_reading(
        text,
        mode="bet",
        published_amounts={20},
        raw_amounts={20},
        schema=PROMPT_SCHEMA_VERSION,
    )
    codes = diagnose.classify_point(_point(draw=0, mode="bet", coach=reading))
    assert "e_coach_false_draw" in codes
    denied = diagnose.coach_reading(
        "这里没有听牌。",
        mode="check",
        published_amounts=set(),
        raw_amounts=set(),
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert "e_coach_false_draw" not in diagnose.classify_point(_point(draw=0, coach=denied))


def test_preflop_free_raise_is_counted_apart_from_postflop() -> None:
    codes = diagnose.classify_point(
        _point(
            street="preflop",
            to_call=0,
            equity=0.2,
            opponents=3,
            mode="raise",
            mode_amount=60,
            distribution=[{"action": "raise", "amount": 60, "probability": 1.0}],
        )
    )
    assert codes == ["c_preflop_free_raise"]


def test_coach_fold_preference_opposes_a_raise_reference() -> None:
    text = (
        "这次跟注已被标为 bad_call。这里的被动补牌不够，弃牌优于跟注；"
        "若继续也应更偏向参考中的加注施压，而不是负期望地跟。"
    )
    reading = diagnose.coach_reading(
        text,
        mode="raise",
        published_amounts={200},
        raw_amounts={360},
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert reading["preference"] == "fold"
    assert reading["reference_actions"] == ["raise"]
    assert reading["opposes"] is True
    assert reading["misstates"] is False
    point = _point(
        to_call=160,
        call_ev=-20.0,
        mode="raise",
        mode_amount=200,
        distribution=[{"action": "raise", "amount": 200, "probability": 1.0}],
        coach=reading,
    )
    assert "e_coach_opposes" in diagnose.classify_point(point)


def test_coach_check_is_reasonable_while_reference_bets() -> None:
    text = (
        "实际 check 过牌控制底池是合理的，避免用边缘权益继续扩大对抗。"
        "参考虽偏向小注 180，但这里与参考不同不构成错误。"
    )
    reading = diagnose.coach_reading(
        text,
        mode="bet",
        published_amounts={180},
        raw_amounts={180},
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert reading["preference"] == "check"
    assert reading["reference_actions"] == ["bet"]
    assert reading["opposes"] is True
    assert reading["misstates"] is False
    assert 180 not in reading["unknown_amounts"]


def test_denial_does_not_count_as_endorsing_the_action() -> None:
    reading = diagnose.coach_reading(
        "这里跟注不合理，应该弃牌。参考动作是弃牌。",
        mode="fold",
        published_amounts=set(),
        raw_amounts=set(),
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert reading["preference"] == "fold"
    assert reading["opposes"] is False


def test_legacy_total_and_unknown_amount_are_separated() -> None:
    reading = diagnose.coach_reading(
        "700相比参考的1540尺度偏小，参考动作是加注。",
        mode="raise",
        published_amounts={700},
        raw_amounts={1540},
        ignore_amounts={700},
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert reading["legacy_amounts"] == [1540]
    assert reading["unknown_amounts"] == []
    assert reading["misstates"] is False


def test_misstated_reference_and_stale_schema() -> None:
    reading = diagnose.coach_reading(
        "参考只选择跟注，但实际再加注仍符合价值逻辑。",
        mode="raise",
        published_amounts={400},
        raw_amounts={400},
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert reading["reference_actions"] == ["call"]
    assert reading["misstates"] is True
    stale = diagnose.coach_reading(
        "参考动作是跟注。",
        mode="call",
        published_amounts=set(),
        raw_amounts=set(),
        schema=1,
    )
    point = _point(mode="call", coach=stale)
    codes = diagnose.classify_point(point)
    assert "e_coach_stale_schema" in codes
    assert "e_coach_misstates" not in codes


def test_judgment_attaches_to_the_nearest_action() -> None:
    reading = diagnose.coach_reading(
        "面对再加注后弃牌是合理的。参考分布也偏向弃牌。",
        mode="fold",
        published_amounts=set(),
        raw_amounts=set(),
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert reading["preference"] == "fold"
    assert reading["opposes"] is False


def test_punctuation_keeps_a_later_judgment_off_the_raise() -> None:
    # 「避免被加注，是合理的」说的是过牌，不能把合理安到加注上。
    reading = diagnose.coach_reading(
        "过牌控制底池、避免被听牌加注，是合理的。",
        mode="check",
        published_amounts=set(),
        raw_amounts=set(),
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert reading["preference"] != "raise"
    assert reading["opposes"] is False


def test_ambiguous_advice_does_not_pick_a_side() -> None:
    reading = diagnose.coach_reading(
        "过牌合理，跟注也合理。",
        mode="check",
        published_amounts=set(),
        raw_amounts=set(),
        schema=PROMPT_SCHEMA_VERSION,
    )
    assert reading["preference"] is None
    assert reading["opposes"] is False


def test_summarize_counts_hands_once_per_code() -> None:
    report = {
        "hand_id": "h1",
        "decisions": [
            _point(
                to_call=20,
                call_ev=-3.0,
                mode="raise",
                mode_amount=40,
                distribution=[
                    {"action": "raise", "amount": 40, "probability": 0.7},
                    {"action": "call", "amount": 0, "probability": 0.3},
                ],
            ),
            _point(
                to_call=20,
                call_ev=-1.0,
                mode="call",
                distribution=[{"action": "call", "amount": 0, "probability": 1.0}],
            ),
        ],
    }
    for point in report["decisions"]:
        point["action_index"] = 0
        point["player_amount"] = 20
        point["passive_score"] = 300
        point["call_threshold"] = 400
        point["contradictions"] = diagnose.classify_point(point)
    broken = {"hand_id": "bad", "error": "boom", "decisions": []}
    summary = diagnose.summarize_reports([report, broken])
    assert summary["hands"] == 2
    assert summary["decisions"] == 2
    assert len(summary["replay_errors"]) == 1
    assert summary["codes"]["a_negative_continue"]["decisions"] == 2
    assert summary["codes"]["a_negative_continue"]["hands"] == 1
    assert summary["codes"]["d_call_amount_zero"]["decisions"] == 2


def test_broken_history_is_reported_without_raising() -> None:
    result = diagnose.diagnose_history({"actions": []}, hand_id="bad")
    assert result["hand_id"] == "bad"
    assert result["decisions"] == []
    assert "error" in result


def test_readonly_connection_rejects_writes(tmp_path) -> None:
    path = tmp_path / "sample.db"
    setup = sqlite3.connect(path)
    setup.execute("CREATE TABLE hands (id TEXT)")
    setup.execute("INSERT INTO hands VALUES ('h1')")
    setup.commit()
    setup.close()
    readonly = diagnose.connect_readonly(path)
    try:
        with pytest.raises(sqlite3.OperationalError):
            readonly.execute("INSERT INTO hands VALUES ('h2')")
    finally:
        readonly.close()


def test_replay_exposes_features_and_cached_reading() -> None:
    engine = PokerEngine(2, 5, 10, 1000)
    engine.start_hand_with(
        button=1,
        hole_cards={0: [card("Kd"), card("Js")], 1: [card("2c"), card("7h")]},
        board=[],
    )
    engine.apply_action(Action(ActionType.RAISE, 40))
    engine.apply_action(Action(ActionType.FOLD))
    assert engine.hand_over
    history = build_hand_history(engine, hand_number=7, human_seat=0)
    text = "面对加注，弃牌更合适。参考动作是弃牌。"
    result = diagnose.diagnose_history(
        history,
        hand_id="sample",
        coach_rows={
            0: {
                "explanation": text,
                "schema": PROMPT_SCHEMA_VERSION,
                "model": "deepseek-flash",
                "created_at": "2026-10-20",
            }
        },
    )
    assert "error" not in result
    assert len(result["decisions"]) == 1
    point = result["decisions"][0]
    assert point["street"] == "preflop"
    assert point["hero_cards"] == ["Kd", "Js"]
    assert {"base", "draw", "score", "value_threshold", "call_threshold"} <= set(point)
    assert point["raw_distribution"]
    assert point["distribution"]
    assert abs(sum(item["probability"] for item in point["distribution"]) - 1) < 0.02
    assert 0.0 <= point["equity"] <= 1.0
    assert point["coach"]["text"] == text
    assert isinstance(point["contradictions"], list)
    rendered = diagnose.format_report(result)
    assert "特征" in rendered
    assert "保护后" in rendered
