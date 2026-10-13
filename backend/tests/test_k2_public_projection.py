"""公开投影的非实际夹具。不产生战役键或材料。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.poker.actions import LegalActions
from app.poker.cards import Card, Rank, Suit
from app.poker.k2_public_projection import (
    K2PublicProjectionError,
    encode_k2_public_v1,
    sigma_hex_to_bytes,
    sigma_public_bytes,
    sigma_public_hex,
)
from app.poker.state import GameState, PlayerState, Street


def _player(seat: int, *, name: str = "n", stack: int = 100) -> PlayerState:
    return PlayerState(
        seat=seat,
        name=name,
        stack=stack,
        hole_cards=[Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.HEARTS)],
    )


def _legal(**overrides: bool | int) -> LegalActions:
    fields: dict[str, bool | int] = {
        "can_fold": True,
        "can_check": False,
        "can_call": True,
        "call_amount": 2,
        "actual_call_amount": 2,
        "is_short_all_in_call": False,
        "can_bet": False,
        "min_bet": 0,
        "max_bet": 0,
        "can_raise": True,
        "min_raise_to": 4,
        "max_raise_to": 100,
    }
    fields.update(overrides)
    return LegalActions(**fields)  # type: ignore[arg-type]


def _state(**overrides: object) -> GameState:
    players = (
        _player(0, name="left", stack=98),
        _player(1, name="right", stack=96),
    )
    fields: dict[str, object] = {
        "street": Street.PREFLOP,
        "board": (),
        "pot": 6,
        "current_seat": 0,
        "button": 0,
        "hand_over": False,
        "players": players,
    }
    fields.update(overrides)
    return GameState(**fields)  # type: ignore[arg-type]


def test_projection_imports_only_poker_types() -> None:
    path = Path(__file__).resolve().parents[1] / "app" / "poker" / "k2_public_projection.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "strategy" not in module
            assert "verification" not in module
            assert ".api" not in module and module != "api"
            assert "llm" not in module


def test_encode_is_stable_and_ignores_private_fields() -> None:
    state = _state()
    legal = _legal()
    text = encode_k2_public_v1(state, legal)
    assert text.startswith("schema=k2-public-projection-v1\n")
    assert not text.endswith("\n")
    assert "hole" not in text
    assert "left" not in text
    renamed = _state(
        players=(
            _player(0, name="other", stack=98),
            _player(
                1,
                name="right",
                stack=96,
            ),
        )
    )
    renamed.players[0].hole_cards = [Card(Rank.TWO, Suit.CLUBS), Card(Rank.SEVEN, Suit.DIAMONDS)]
    assert encode_k2_public_v1(renamed, legal) == text
    assert encode_k2_public_v1(_state(pot=7), legal) != text


def test_sigma_hex_roundtrip_uses_utf8_not_a_digest() -> None:
    state = _state()
    legal = _legal()
    raw = sigma_public_bytes(state, legal)
    text = sigma_public_hex(state, legal)
    assert sigma_hex_to_bytes(text) == raw
    assert raw == encode_k2_public_v1(state, legal).encode("utf-8")
    assert len(text) == len(raw) * 2


def test_encode_rejects_negative_integers_and_missing_seats() -> None:
    with pytest.raises(K2PublicProjectionError):
        encode_k2_public_v1(_state(pot=-1), _legal())
    with pytest.raises(K2PublicProjectionError):
        encode_k2_public_v1(
            _state(players=(_player(0),)),
            _legal(),
        )
    with pytest.raises(K2PublicProjectionError):
        encode_k2_public_v1(
            _state(players=(_player(0), _player(0))),
            _legal(),
        )


def test_sigma_hex_rejects_odd_or_uppercase_text() -> None:
    with pytest.raises(K2PublicProjectionError):
        sigma_hex_to_bytes("abc")
    with pytest.raises(K2PublicProjectionError):
        sigma_hex_to_bytes("AB")
