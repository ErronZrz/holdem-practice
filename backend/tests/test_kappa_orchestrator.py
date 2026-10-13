"""包外编排只查已生成材料。夹具种子与键都不是战役材料。"""

from __future__ import annotations

import ast
import importlib.util
import sys
from inspect import signature
from pathlib import Path

import pytest

from app.poker.actions import Action, ActionType
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.strategy.registry import create_strategy


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
