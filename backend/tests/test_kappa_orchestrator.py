"""包外编排只查已生成材料。夹具种子与键都不是战役材料。"""

from __future__ import annotations

import ast
import importlib.util
import sys
from inspect import signature
from pathlib import Path

import pytest

from app.poker.actions import Action, ActionType, LegalActions
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.poker.state import GameState
from app.strategy.registry import create_strategy
from app.verification.errors import ProtocolSpecError
from app.verification.kappa_derive import require_derived_decision_records


def _load_orchestrator():
    path = Path(__file__).resolve().parents[1] / "tools" / "kappa_orchestrator.py"
    spec = importlib.util.spec_from_file_location("kappa_orchestrator_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _engine() -> PokerEngine:
    engine = PokerEngine(2, small_blind=1, big_blind=2, starting_stack=200, seed=1)
    engine.start_hand_with(
        button=0,
        hole_cards={
            0: [card_from_str("7c"), card_from_str("2d")],
            1: [card_from_str("As"), card_from_str("Ah")],
        },
        board=[
            card_from_str("2c"),
            card_from_str("3d"),
            card_from_str("4h"),
            card_from_str("5s"),
            card_from_str("9c"),
        ],
    )
    return engine


def test_material_table_rejects_seed_at_domain_bound() -> None:
    module = _load_orchestrator()
    with pytest.raises(module.KappaMaterialMiss):
        module.material_table_from_rows((("non_probed", ("ab",), 1 << 256),))
    table = module.material_table_from_rows((("non_probed", ("ab",), (1 << 256) - 1),))
    assert table.require("non_probed", ("ab",)) == (1 << 256) - 1


def test_orchestrator_source_has_no_generator_callback() -> None:
    path = Path(__file__).resolve().parents[1] / "tools" / "kappa_orchestrator.py"
    source = path.read_text(encoding="utf-8")
    assert "material_generator" not in source
    assert "os.urandom" not in source
    assert "generate_from_closed_keyset" not in source
    tree = ast.parse(source)
    assert not any(
        isinstance(node, ast.ImportFrom) and (node.module or "").endswith("material_generator")
        for node in ast.walk(tree)
    )


def test_missing_key_stops_without_constructing_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_orchestrator()
    calls: list[str] = []

    def spy(value: str, seed: int | None = None):
        calls.append(value)
        return create_strategy(value, seed)

    monkeypatch.setattr(module, "create_strategy", spy)
    engine = _engine()
    history = len(engine.history)
    table = module.material_table_from_rows(())
    with pytest.raises(module.KappaMaterialMiss):
        module.play_hand(
            engine,
            table,
            campaign="ab" * 32,
            block=0,
            hand_ordinal=1,
            probed_seat=1,
            arm="baseline",
        )
    assert calls == []
    assert engine.hand_over is False
    assert len(engine.history) == history
    assert "generator" not in signature(module.play_hand).parameters


def test_missing_key_on_under_test_arm_stops_without_calling_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """被测臂在空材料表下缺键时同样立即停止，不调用被测回调或构造基线实例。"""
    module = _load_orchestrator()
    calls: list[str] = []

    def spy(value: str, seed: int | None = None):
        calls.append(value)
        return create_strategy(value, seed)

    monkeypatch.setattr(module, "create_strategy", spy)
    engine = _engine()
    history = len(engine.history)
    table = module.material_table_from_rows(())
    under_test_called: list[int] = []
    with pytest.raises(module.KappaMaterialMiss):
        module.play_hand(
            engine,
            table,
            campaign="ab" * 32,
            block=0,
            hand_ordinal=1,
            probed_seat=0,
            arm="under-test",
            under_test_choose=lambda _state, _legal, seed: (
                under_test_called.append(seed) or Action(ActionType.FOLD)
            ),
        )
    assert calls == []
    assert under_test_called == []
    assert engine.hand_over is False
    assert len(engine.history) == history


def test_listed_key_injects_baseline_seed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_orchestrator()
    calls: list[tuple[str, int | None]] = []

    def spy(value: str, seed: int | None = None):
        calls.append((value, seed))
        return create_strategy(value, seed)

    monkeypatch.setattr(module, "create_strategy", spy)
    engine = _engine()
    state = engine.snapshot()
    legal = engine.legal_actions()
    sigma = module.sigma_public_hex(state, legal)
    campaign = "ab" * 32
    key = (campaign, "0", "1", "0", "0", sigma)
    table = module.material_table_from_rows((("non_probed", key, 7),))
    assert table.require("non_probed", key) == table.require("non_probed", key)
    module.play_hand(
        engine,
        table,
        campaign=campaign,
        block=0,
        hand_ordinal=1,
        probed_seat=1,
        arm="baseline",
    )
    assert engine.hand_over is True
    assert calls == [("heuristic@1", 7)]
    assert "mixed-local@9" not in {value for value, _seed in calls}


def test_under_test_seat_uses_caller_action_not_a_new_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_orchestrator()
    calls: list[str] = []
    monkeypatch.setattr(
        module,
        "create_strategy",
        lambda value, seed=None: calls.append(value),
    )
    engine = _engine()
    campaign = "ab" * 32
    table = module.material_table_from_rows((("arm_m", (campaign, "0", "1"), 9),))

    def fold(state, legal, seed: int):
        assert seed == 9
        return Action(ActionType.FOLD)

    module.play_hand(
        engine,
        table,
        campaign=campaign,
        block=0,
        hand_ordinal=1,
        probed_seat=0,
        arm="under-test",
        under_test_choose=fold,
    )
    assert calls == []
    assert engine.hand_over is True


def _same_deal() -> PokerEngine:
    """两臂共用的发牌。底牌固定，公共牌备好，不读取随机源。"""
    engine = PokerEngine(2, small_blind=1, big_blind=2, starting_stack=200, seed=1)
    engine.start_hand_with(
        button=0,
        hole_cards={
            0: [card_from_str("As"), card_from_str("Ah")],
            1: [card_from_str("Kd"), card_from_str("Kh")],
        },
        board=[
            card_from_str("2c"),
            card_from_str("7d"),
            card_from_str("9h"),
            card_from_str("3s"),
            card_from_str("Jc"),
        ],
    )
    return engine


def _different_continuing_action(legal, baseline_action: tuple[str, int]) -> Action:
    """选一个与基线不同、且不结束本手的动作，使之后的公开投影分叉。"""
    options: list[Action] = []
    if legal.can_call:
        options.append(Action(ActionType.CALL))
    if legal.can_check:
        options.append(Action(ActionType.CHECK))
    if legal.can_raise:
        options.append(Action(ActionType.RAISE, legal.min_raise_to))
    if legal.can_bet:
        options.append(Action(ActionType.BET, legal.min_bet))
    for action in options:
        if (action.type.value, action.amount) != baseline_action:
            return action
    raise AssertionError("没有与基线不同且能让本手继续的动作")


def _slot(record: dict[str, object]) -> tuple[str, str]:
    key = record["index_key"]
    assert isinstance(key, tuple)
    return (key[3], key[4])


def _merge_records(groups: list[list[dict[str, object]]]) -> list[dict[str, object]]:
    """两臂里完整键相同的决策只留一条。"""
    merged: list[dict[str, object]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for records in groups:
        for record in records:
            key = record["index_key"]
            assert isinstance(key, tuple)
            location = (str(record["purpose_label"]), key)
            if location in seen:
                continue
            seen.add(location)
            merged.append(record)
    return merged


def test_two_arms_share_seeds_before_the_fork_and_differ_after() -> None:
    module = _load_orchestrator()
    campaign = "ab" * 32
    master = b"\x11" * 32
    probed_seat = 1
    table = module.material_table_from_rows((("arm_m", (campaign, "0", "1"), 9),))
    common = {
        "campaign": campaign,
        "block": 0,
        "hand_ordinal": 1,
        "probed_seat": probed_seat,
        "master": master,
    }
    baseline_engine = _same_deal()
    baseline_records = module.play_hand(
        baseline_engine, table, arm="baseline", **common
    )
    assert baseline_records
    probed_history = [
        item for item in baseline_engine.history if item["seat"] == probed_seat
    ]
    assert probed_history
    baseline_probed = (probed_history[0]["action"], probed_history[0]["amount"])
    seen_under_test: list[int] = []

    def choose(state: GameState, legal: LegalActions, seed: int) -> Action:
        assert seed == 9
        seen_under_test.append(seed)
        return _different_continuing_action(legal, baseline_probed)

    under_engine = _same_deal()
    under_records = module.play_hand(
        under_engine,
        table,
        arm="under-test",
        under_test_choose=choose,
        **common,
    )
    assert under_records is not None
    assert seen_under_test
    assert baseline_engine.hand_over is True
    assert under_engine.hand_over is True
    assert any(record["purpose_label"] == "arm_b" for record in baseline_records)
    assert all(record["purpose_label"] == "non_probed" for record in under_records)
    assert all(_slot(record)[0] != str(probed_seat) for record in under_records)
    baseline_by_slot = {_slot(record): record for record in baseline_records}
    under_by_slot = {_slot(record): record for record in under_records}
    shared_before = []
    forked = []
    for slot in set(baseline_by_slot) & set(under_by_slot):
        left = baseline_by_slot[slot]
        right = under_by_slot[slot]
        left_key = left["index_key"]
        right_key = right["index_key"]
        assert isinstance(left_key, tuple) and isinstance(right_key, tuple)
        if left_key[5] == right_key[5]:
            assert left["value"] == right["value"]
            shared_before.append(slot)
        else:
            assert left["value"] != right["value"]
            forked.append(slot)
            with pytest.raises(module.KappaMaterialMiss, match="没有该键"):
                table.require("non_probed", right_key)
    assert shared_before
    assert forked
    merged = _merge_records([baseline_records, under_records])
    require_derived_decision_records(
        merged,
        master=master,
        campaign=campaign,
        block=0,
        num_players=2,
        probed_by_hand={1: probed_seat},
    )
    altered_value = dict(merged[0])
    altered_value["value"] = 0 if merged[0]["value"] != 0 else 1
    with pytest.raises(ProtocolSpecError, match="不符"):
        require_derived_decision_records(
            [altered_value, *merged[1:]],
            master=master,
            campaign=campaign,
            block=0,
            num_players=2,
            probed_by_hand={1: probed_seat},
        )
    altered_seat = dict(merged[0])
    key = altered_seat["index_key"]
    assert isinstance(key, tuple)
    altered_seat["index_key"] = (*key[:3], "1" if key[3] == "0" else "0", *key[4:])
    with pytest.raises(ProtocolSpecError):
        require_derived_decision_records(
            [altered_seat, *merged[1:]],
            master=master,
            campaign=campaign,
            block=0,
            num_players=2,
            probed_by_hand={1: probed_seat},
        )
    with pytest.raises(ProtocolSpecError, match="重复"):
        require_derived_decision_records(
            [merged[0], *merged],
            master=master,
            campaign=campaign,
            block=0,
            num_players=2,
            probed_by_hand={1: probed_seat},
        )
