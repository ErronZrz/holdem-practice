"""第十七版身份的回归：过牌保护、过牌后跟注、延迟探测，以及旧身份的逐位隔离。

只比较可复现局面上的动作单位。不把这些读数写成质量结论。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

import pytest

from app.api.schemas import CreateGameRequest
from app.poker.actions import LegalActions
from app.poker.state import Street
from app.strategy.distribution_observation import supported_declaration
from app.strategy.mixed_context import require_mixed_input
from app.strategy.mixed_features import MixedFeatures, features_for
from app.strategy.mixed_policy import (
    MIXED_LOCAL_V16_RULES,
    MIXED_LOCAL_V17_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    _checked_defense_bonus,
    _delayed_probe_quality,
    _protection_budget,
    _trap_budget,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V16,
    MIXED_STRATEGY_IDENTIFIER_V17,
    MIXED_STRATEGY_IDENTIFIER_V18,
    MIXED_STRATEGY_IDENTIFIER_V19,
    MIXED_STRATEGY_IDENTIFIERS,
    MixedSeatPolicy,
    rules_for_identifier,
)
from app.strategy.registry import (
    capability_declaration,
    create_strategy,
    observation_entry,
    spec_for,
)
from app.verification.config import BASELINE_IDENTIFIER, UNDER_TEST_IDENTIFIERS
from tools.diagnose_bot_hand import diagnose_history
from tools.diagnose_review import connect_readonly, load_history

from .mixed_bot_states import apply_node, build_frozen_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, config_digest

_SEVENTEENTH_CONFIG_DIGEST = (
    "d2516f80702f8b951b6b118fd3905b87518a1fae25084d1cddc60f0c558dc07c"
)
_SIXTEENTH_CONFIG_DIGEST = (
    "941f756d1cd5e5034cf757b1d211ec9d0cd06e23486f07b92bb76970a5eab2f5"
)
_CASE_HAND = "555285f9dc2242649a2cf90134435823"
_MODE_WEIGHT = {HandMode.NORMAL: 80, HandMode.CAUTIOUS: 10, HandMode.PRESSED: 10}


def _legal(**overrides: object) -> LegalActions:
    payload: dict[str, object] = {
        "can_fold": False,
        "can_check": False,
        "can_call": False,
        "call_amount": 0,
        "actual_call_amount": 0,
        "is_short_all_in_call": False,
        "can_bet": False,
        "min_bet": 0,
        "max_bet": 0,
        "can_raise": False,
        "min_raise_to": 0,
        "max_raise_to": 0,
    }
    payload.update(overrides)
    return LegalActions(**payload)  # type: ignore[arg-type]


def _features(**overrides: object) -> MixedFeatures:
    payload: dict[str, object] = {
        "street": Street.FLOP,
        "base": 180,
        "draw": 0,
        "position": 40,
        "texture": 0,
        "contenders": 1,
        "live_opponents": 1,
        "recent_aggression": 0,
        "limpers": 1,
        "price": 0,
        "eligible_pot": 0,
        "actual_call": 0,
        "pot": 40,
        "effective_stack": 1800,
        "big_blind": 20,
        "stack": 1800,
        "street_bet": 0,
        "preflop_unraised": False,
        "hole_ranks": (12, 8),
        "seat_count": 2,
        "actor_checks": 0,
        "prior_street_aggressor": False,
        "prior_street_aggression": 0,
        "prior_street_checked_through": True,
    }
    payload.update(overrides)
    return MixedFeatures(**payload)  # type: ignore[arg-type]


def _free_check() -> LegalActions:
    return _legal(can_check=True, can_bet=True, min_bet=20, max_bet=1800)


def _facing_bet() -> LegalActions:
    return _legal(
        can_fold=True,
        can_call=True,
        call_amount=40,
        actual_call_amount=40,
        can_raise=True,
        min_raise_to=80,
        max_raise_to=1800,
    )


def _rows(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    *,
    style: MixedStyle = MixedStyle.CALLING,
    mode: HandMode = HandMode.NORMAL,
    trap_roll: int | None = None,
    protect_roll: int | None = None,
) -> tuple[tuple[str, int, int], ...]:
    distribution = build_distribution(
        features,
        legal,
        style,
        mode,
        rules,
        trap_roll=trap_roll,
        protect_roll=protect_roll,
    )
    return tuple((item.action.value, item.amount, item.units) for item in distribution.candidates)


def _marginal(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    *,
    style: MixedStyle = MixedStyle.CALLING,
    trap_roll: int | None = None,
    protect_roll: int | None = None,
) -> dict[str, float]:
    totals: dict[str, int] = defaultdict(int)
    for mode, weight in _MODE_WEIGHT.items():
        for action, _amount, units in _rows(
            rules,
            features,
            legal,
            style=style,
            mode=mode,
            trap_roll=trap_roll,
            protect_roll=protect_roll,
        ):
            totals[action] += units * weight
    return {action: round(units / 1_000_000, 2) for action, units in totals.items()}


def test_seventeenth_version_only_opens_three_switches() -> None:
    """第十七版只打开三个新开关；关掉后必须与第十六版逐字段相同。"""
    assert MIXED_LOCAL_V17_RULES.check_range_protection is True
    assert MIXED_LOCAL_V17_RULES.checked_continue is True
    assert MIXED_LOCAL_V17_RULES.delayed_probe is True
    assert MIXED_LOCAL_V17_RULES.check_base_percent == 16
    assert MIXED_LOCAL_V17_RULES.checked_defense_span == 160
    assert MIXED_LOCAL_V17_RULES.delayed_probe_quality == 4
    assert (
        replace(
            MIXED_LOCAL_V17_RULES,
            check_range_protection=False,
            checked_continue=False,
            delayed_probe=False,
        )
        == MIXED_LOCAL_V16_RULES
    )
    for identifier in MIXED_STRATEGY_IDENTIFIERS:
        rules = rules_for_identifier(identifier)
        enabled = identifier in (
            MIXED_STRATEGY_IDENTIFIER_V17,
            MIXED_STRATEGY_IDENTIFIER_V18,
            MIXED_STRATEGY_IDENTIFIER_V19,
            "mixed-local@20",
        )
        assert rules.check_range_protection is enabled
        assert rules.checked_continue is enabled
        assert rules.delayed_probe is enabled


def test_seventeenth_stays_registered_when_default_moves_on() -> None:
    """第十七版可构造；未指定策略时创建对局改用第十九版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    assert ordered[-1] == "mixed-local@20"
    assert ordered[-2] == MIXED_STRATEGY_IDENTIFIER_V19
    assert ordered[-3] == MIXED_STRATEGY_IDENTIFIER_V18
    assert ordered[-4] == MIXED_STRATEGY_IDENTIFIER_V17
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V17).version == 17
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V17, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V17
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V17) is MIXED_LOCAL_V17_RULES
    assert CreateGameRequest().bot_strategy == "mixed-local@20"
    assert "mixed-local@17" in UNDER_TEST_IDENTIFIERS
    assert BASELINE_IDENTIFIER == "heuristic@1"
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V17) == supported_declaration()
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V17).rules is MIXED_LOCAL_V17_RULES


def test_seventeenth_digest_appends_only_its_own_fields() -> None:
    """摘要只追加第十七版自己的六个字段，第十六版摘要逐字不变。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V17][-6:] == (
        "check_range_protection",
        "check_base_percent",
        "checked_continue",
        "checked_defense_span",
        "delayed_probe",
        "delayed_probe_quality",
    )
    assert (
        DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V17][:-6]
        == DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V16]
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V16) == _SIXTEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V17) == _SEVENTEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V17) != _SIXTEENTH_CONFIG_DIGEST


def test_three_channels_stay_inside_their_entries() -> None:
    """三条通道各自只改自己的入口；关掉开关或入口对不上时与第十六版逐位相同。"""
    legal = _free_check()
    air = _features()
    assert _delayed_probe_quality(air, MIXED_LOCAL_V17_RULES) == 6
    assert _delayed_probe_quality(air, MIXED_LOCAL_V16_RULES) == 0
    sixteenth = _rows(MIXED_LOCAL_V16_RULES, air, legal)
    assert _rows(MIXED_LOCAL_V17_RULES, air, legal) != sixteenth
    closed = replace(
        MIXED_LOCAL_V17_RULES,
        check_range_protection=False,
        checked_continue=False,
        delayed_probe=False,
    )
    assert _rows(closed, air, legal, protect_roll=0) == sixteenth
    blocked = (
        replace(air, street=Street.PREFLOP),
        replace(air, draw=64),
        replace(air, hole_ranks=(14, 8)),
        replace(air, base=200),
        replace(air, contenders=2, live_opponents=2),
        replace(air, actual_call=40, price=250, recent_aggression=1),
        replace(air, prior_street_aggressor=True),
        replace(air, effective_stack=40, stack=40, pot=40),
        replace(air, position=-40, prior_street_checked_through=False),
    )
    facing = _facing_bet()
    for features in blocked:
        chosen = facing if features.actual_call > 0 else legal
        assert _rows(MIXED_LOCAL_V17_RULES, features, chosen) == _rows(
            MIXED_LOCAL_V16_RULES, features, chosen
        )

    top = _features(base=650, hole_ranks=(14, 8), prior_street_checked_through=False)
    assert _protection_budget(top, MIXED_LOCAL_V17_RULES) == 26
    assert _rows(MIXED_LOCAL_V17_RULES, top, legal, protect_roll=0) != _rows(
        MIXED_LOCAL_V16_RULES, top, legal
    )
    checked = _marginal(MIXED_LOCAL_V17_RULES, top, legal, protect_roll=0)
    assert checked.get("bet", 0.0) == 0.0
    assert checked.get("check", 0.0) == 100.0
    assert _rows(MIXED_LOCAL_V17_RULES, top, legal, protect_roll=99) == _rows(
        MIXED_LOCAL_V16_RULES, top, legal
    )
    pressured = replace(top, actual_call=40, price=250, recent_aggression=1)
    assert _rows(MIXED_LOCAL_V17_RULES, pressured, facing, protect_roll=0) == _rows(
        MIXED_LOCAL_V16_RULES, pressured, facing
    )

    strong = _features(
        street=Street.TURN,
        base=900,
        hole_ranks=(12, 12),
        prior_street_checked_through=False,
        pot=150,
        effective_stack=1700,
        stack=1700,
    )
    assert _trap_budget(strong, MIXED_LOCAL_V16_RULES) > 0
    assert _trap_budget(strong, MIXED_LOCAL_V17_RULES) == 0
    assert _rows(MIXED_LOCAL_V16_RULES, strong, legal, trap_roll=0) != _rows(
        MIXED_LOCAL_V17_RULES, strong, legal, trap_roll=0
    )
    assert _rows(MIXED_LOCAL_V17_RULES, strong, legal, trap_roll=0) == _rows(
        MIXED_LOCAL_V16_RULES, strong, legal, trap_roll=99
    )

    made = _features(
        base=450,
        actor_checks=1,
        actual_call=40,
        price=200,
        recent_aggression=1,
        hole_ranks=(10, 9),
        prior_street_checked_through=False,
    )
    assert _checked_defense_bonus(made, MIXED_LOCAL_V17_RULES) == 160
    assert _checked_defense_bonus(made, MIXED_LOCAL_V16_RULES) == 0
    before = _marginal(MIXED_LOCAL_V16_RULES, made, facing)
    after = _marginal(MIXED_LOCAL_V17_RULES, made, facing)
    assert after["call"] > before["call"]
    assert after.get("raise", 0.0) == pytest.approx(before.get("raise", 0.0), abs=0.05)
    air_facing = replace(made, base=180)
    assert _rows(MIXED_LOCAL_V17_RULES, air_facing, facing) == _rows(
        MIXED_LOCAL_V16_RULES, air_facing, facing
    )


def test_frozen_nodes_do_not_move_when_the_entries_are_absent() -> None:
    """冻结节点碰不到三条入口，开关打开后观测分布仍与第十六版逐位相同。"""
    nodes = build_frozen_nodes()
    assert len(nodes) == 125
    current = observation_entry(MIXED_STRATEGY_IDENTIFIER_V17)
    previous = observation_entry(MIXED_STRATEGY_IDENTIFIER_V16)
    for node in nodes:
        applied = apply_node(node)
        state = applied.actor_state()
        legal = applied.legal_actions()
        assert current.observe(state, legal).candidates == previous.observe(state, legal).candidates


def test_seat_policy_shares_one_protect_roll(monkeypatch: pytest.MonkeyPatch) -> None:
    """持有座位键的两条路径传入同一个保护数；显式传入空值则关闭。"""
    node = next(item for item in build_frozen_nodes() if item.category == "free-check")
    applied = apply_node(node)
    legal = applied.legal_actions()
    state = applied.actor_state()
    verified = require_mixed_input(state)
    policy = MixedSeatPolicy(
        seat=verified.actor_seat,
        style=MixedStyle.CALLING,
        seat_key=b"seat-key",
        rules=MIXED_LOCAL_V17_RULES,
    )
    roll = policy.protect_roll(verified)
    assert 0 <= roll < 100
    assert policy.protect_roll(verified) == roll
    seen: list[int | None] = []
    real = build_distribution

    def spy(*args: object, **kwargs: object):
        seen.append(kwargs.get("protect_roll"))  # type: ignore[arg-type]
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("app.strategy.mixed_strategy.build_distribution", spy)
    policy.distribution_for(verified, legal)
    policy.choose_action(verified, legal)
    assert seen == [roll, roll]
    seen.clear()
    closed = policy.distribution_for(verified, legal, protect_roll=None)
    assert seen == [None]
    assert closed == build_distribution(
        features_for(verified, legal),
        legal,
        policy.style,
        policy.hand_mode(verified),
        MIXED_LOCAL_V17_RULES,
        trap_roll=policy.trap_roll(verified),
        protect_roll=None,
    )


def test_case_hand_seat_two_probes_the_checked_through_lines() -> None:
    """案例手座位 2 在翻牌和河牌补上探测，转牌听牌与翻前分布保持原样。"""
    connection = connect_readonly()
    try:
        history = load_history(connection, _CASE_HAND)
    finally:
        connection.close()
    assert history is not None
    current = diagnose_history(history, hand_id=_CASE_HAND, identity=MIXED_STRATEGY_IDENTIFIER_V17)
    previous = diagnose_history(history, hand_id=_CASE_HAND, identity=MIXED_STRATEGY_IDENTIFIER_V16)
    seat = [item for item in current["decisions"] if item["seat"] == 2]
    before = [item for item in previous["decisions"] if item["seat"] == 2]
    assert [item["street"] for item in seat] == ["preflop", "flop", "turn", "river"]

    def percent(decision: dict) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for row in decision["marginal_80_10_10"]:
            totals[row["action"]] += float(row["pct"])
        return {action: round(value, 2) for action, value in totals.items()}

    assert percent(seat[0]) == percent(before[0])
    assert percent(seat[2]) == percent(before[2])
    flop = percent(seat[1])
    river = percent(seat[3])
    assert flop["check"] == pytest.approx(70.45, abs=0.02)
    assert flop["bet"] == pytest.approx(29.55, abs=0.02)
    assert river["check"] == pytest.approx(64.14, abs=0.02)
    assert river["bet"] == pytest.approx(35.86, abs=0.02)
    assert seat[1]["features"]["base"] == 180
    assert seat[1]["features"]["draw"] == 0
    assert seat[3]["features"]["draw"] == 0
