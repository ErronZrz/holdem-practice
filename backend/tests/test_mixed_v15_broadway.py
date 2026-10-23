"""第十五版身份的回归：翻前 A 高张有效基础分，以及旧身份的逐位隔离。

只比较可复现局面上的动作单位与基础分。不把这些读数写成质量结论。
"""

from __future__ import annotations

from dataclasses import replace

from app.api.schemas import CreateGameRequest
from app.poker.cards import card_from_str
from app.poker.engine import PokerEngine
from app.strategy.distribution_observation import supported_declaration
from app.strategy.mixed_context import MixedSummaryTracker, mixed_state, require_mixed_input
from app.strategy.mixed_features import features_for
from app.strategy.mixed_policy import (
    _STRONG_PREFLOP_BASE,
    MIXED_LOCAL_V14_RULES,
    MIXED_LOCAL_V15_RULES,
    HandMode,
    MixedStyle,
    _with_broadway_base,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V14,
    MIXED_STRATEGY_IDENTIFIER_V15,
    MIXED_STRATEGY_IDENTIFIER_V16,
    MIXED_STRATEGY_IDENTIFIER_V17,
    MIXED_STRATEGY_IDENTIFIERS,
    MixedLocalStrategy,
    rules_for_identifier,
)
from app.strategy.projection import project_for_actor
from app.strategy.registry import (
    capability_declaration,
    create_strategy,
    observation_entry,
    spec_for,
)
from app.verification.config import BASELINE_IDENTIFIER, UNDER_TEST_IDENTIFIERS

from .mixed_bot_states import apply_node, build_frozen_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, config_digest

_FIFTEENTH_CONFIG_DIGEST = (
    "39ae4ac9c60015df78aa9ca45340ca6a0325168e0bb1e48ea27d83ec49e4cdc9"
)

_POSTFLOP_CATEGORIES = frozenset(
    {
        "free-check",
        "flop-draw",
        "top-pair-weak-kicker",
        "turn-combo-draw",
        "one-side-all-in",
        "overpair-on-high-board",
        "missed-draw-river",
        "shared-board",
        "sizes-merged",
    }
)

_FILLERS = (
    ("2c", "3d"),
    ("4c", "5d"),
    ("6c", "8d"),
    ("9c", "2d"),
    ("3c", "4d"),
)


def _utg_features(holes: tuple[str, str]):
    """六人桌首位行动、尚未有人加注时的特征。"""
    dealt = (holes, *_FILLERS)
    engine = PokerEngine(6, 10, 20, 2000, seed=0)
    engine.start_hand_with(
        button=3,
        hole_cards={
            seat: [card_from_str(left), card_from_str(right)]
            for seat, (left, right) in enumerate(dealt)
        },
        board=[],
    )
    assert engine.current_seat == 0
    tracker = MixedSummaryTracker()
    tracker.begin_hand(
        hand_number=4,
        num_players=6,
        small_blind=10,
        big_blind=20,
        bot_seats=(0,),
        history=engine.history,
    )
    projected = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    legal = engine.legal_actions()
    features = features_for(require_mixed_input(projected), legal)
    return features, legal


def _type_units(rules, features, legal, style=MixedStyle.TIGHT) -> dict[str, int]:
    distribution = build_distribution(features, legal, style, HandMode.NORMAL, rules)
    totals: dict[str, int] = {}
    for item in distribution.candidates:
        totals[item.action.value] = totals.get(item.action.value, 0) + item.units
    return totals


def test_fifteenth_version_only_adds_the_broadway_adjustment() -> None:
    """第十五版只打开高张修正并写入三档加分，关掉后必须与第十四版逐字段相同。"""
    assert MIXED_LOCAL_V15_RULES.broadway_preflop_caliber is True
    assert MIXED_LOCAL_V15_RULES.broadway_high_rank == 14
    assert MIXED_LOCAL_V15_RULES.broadway_min_kicker == 11
    assert MIXED_LOCAL_V15_RULES.broadway_connector_bonus == 220
    assert MIXED_LOCAL_V15_RULES.broadway_one_gap_bonus == 150
    assert MIXED_LOCAL_V15_RULES.broadway_two_gap_bonus == 120
    assert MIXED_LOCAL_V14_RULES.broadway_preflop_caliber is False
    assert (
        replace(
            MIXED_LOCAL_V15_RULES,
            broadway_preflop_caliber=False,
            broadway_connector_bonus=0,
            broadway_one_gap_bonus=0,
            broadway_two_gap_bonus=0,
        )
        == MIXED_LOCAL_V14_RULES
    )


def test_fifteenth_identity_stays_registered_when_default_moves_on() -> None:
    """第十五版仍可构造；未指定策略时创建对局改用下一版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    assert ordered[-1] == MIXED_STRATEGY_IDENTIFIER_V17
    assert ordered[-2] == MIXED_STRATEGY_IDENTIFIER_V16
    assert ordered[-3] == MIXED_STRATEGY_IDENTIFIER_V15
    assert ordered[-4] == MIXED_STRATEGY_IDENTIFIER_V14
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V15).version == 15
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V15, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V15
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V15) is MIXED_LOCAL_V15_RULES
    assert CreateGameRequest().bot_strategy == "mixed-local@17"
    assert BASELINE_IDENTIFIER == "heuristic@1"
    assert "mixed-local@15" in UNDER_TEST_IDENTIFIERS
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V15) == supported_declaration()
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V15).rules is MIXED_LOCAL_V15_RULES


def test_fifteenth_digest_appends_only_its_own_fields() -> None:
    """摘要只追加第十五版自己的字段，第十四版摘要逐字不变。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V15][-6:] == (
        "broadway_preflop_caliber",
        "broadway_high_rank",
        "broadway_min_kicker",
        "broadway_connector_bonus",
        "broadway_one_gap_bonus",
        "broadway_two_gap_bonus",
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V15) == _FIFTEENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V15) != config_digest(
        MIXED_STRATEGY_IDENTIFIER_V14
    )


def test_ace_broadway_ordering_and_utg_open() -> None:
    """A 高张修掉连张倒挂，六人桌首位紧手标准模式对 AK、AQ 以加注为主。"""
    samples = {}
    raw = {}
    for label, holes in (
        ("AKs", ("As", "Ks")),
        ("AKo", ("Ad", "Kh")),
        ("AQs", ("Ac", "Qc")),
        ("AQo", ("Ad", "Qh")),
        ("AJs", ("Ah", "Jh")),
        ("KQs", ("Kd", "Qd")),
        ("77", ("7c", "7d")),
    ):
        features, legal = _utg_features(holes)
        raw[label] = features.base
        samples[label] = _with_broadway_base(features, MIXED_LOCAL_V15_RULES).base
        assert features.position == -40
        if label in {"AKs", "AKo", "AQs", "AQo"}:
            units = _type_units(MIXED_LOCAL_V15_RULES, features, legal)
            assert units.get("raise", 0) > units.get("fold", 0)
            assert units.get("raise", 0) > units.get("call", 0)
            assert units.get("raise", 0) > 500_000
            previous = _type_units(MIXED_LOCAL_V14_RULES, features, legal)
            assert previous.get("raise", 0) == 0
    assert raw["AKo"] == 542
    assert raw["AQo"] == 567
    assert raw["AKs"] == 587
    assert raw["AQs"] == 612
    assert samples["AKs"] > samples["AKo"] == samples["AQs"] > samples["AQo"] >= samples["AJs"]
    assert samples["AKs"] >= _STRONG_PREFLOP_BASE
    assert samples["KQs"] == raw["KQs"]
    assert samples["77"] == raw["77"]
    kq_features, kq_legal = _utg_features(("Kd", "Qd"))
    assert _type_units(MIXED_LOCAL_V15_RULES, kq_features, kq_legal) == _type_units(
        MIXED_LOCAL_V14_RULES, kq_features, kq_legal
    )
    pair_features, pair_legal = _utg_features(("7c", "7d"))
    assert _type_units(MIXED_LOCAL_V15_RULES, pair_features, pair_legal) == _type_units(
        MIXED_LOCAL_V14_RULES, pair_features, pair_legal
    )


def test_case_hand_shape_opens_in_the_reference_style() -> None:
    """案例手那种六人桌前位 Ad Qh，紧手标准模式的主导动作是加注。"""
    features, legal = _utg_features(("Ad", "Qh"))
    bot = MixedLocalStrategy(
        seed=1, bot_seats=(0,), identifier=MIXED_STRATEGY_IDENTIFIER_V15
    )
    tracker = MixedSummaryTracker()
    engine = PokerEngine(6, 10, 20, 2000, seed=0)
    engine.start_hand_with(
        button=3,
        hole_cards={
            seat: [card_from_str(left), card_from_str(right)]
            for seat, (left, right) in enumerate((("Ad", "Qh"), *_FILLERS))
        },
        board=[],
    )
    tracker.begin_hand(
        hand_number=9,
        num_players=6,
        small_blind=10,
        big_blind=20,
        bot_seats=(0,),
        history=engine.history,
    )
    projected = mixed_state(project_for_actor(engine.snapshot()), tracker.context())
    selected = bot.distribution_for(
        projected, engine.legal_actions(), mode=HandMode.NORMAL, trap_roll=None
    )
    totals: dict[str, int] = {}
    for item in selected.candidates:
        totals[item.action.value] = totals.get(item.action.value, 0) + item.units
    assert max(totals, key=totals.__getitem__) == "raise"
    assert _with_broadway_base(features, MIXED_LOCAL_V15_RULES).base >= 700


def test_postflop_and_unopened_king_queen_stay_with_the_previous_identity() -> None:
    """翻后九类节点，以及未开池的同花国王后，相对上一身份零位移。"""
    nodes = build_frozen_nodes()
    assert len(nodes) == 125
    postflop = 0
    unopened = 0
    current = observation_entry(MIXED_STRATEGY_IDENTIFIER_V15)
    previous = observation_entry(MIXED_STRATEGY_IDENTIFIER_V14)
    for node in nodes:
        if node.category not in _POSTFLOP_CATEGORIES and node.category != "unopened-open":
            continue
        applied = apply_node(node)
        state = applied.actor_state()
        legal = applied.legal_actions()
        assert (
            current.observe(state, legal).candidates
            == previous.observe(state, legal).candidates
        )
        if node.category == "unopened-open":
            unopened += 1
            actor = applied.engine.current_seat
            assert node.hole_cards[actor] == ("Kd", "Qd")
        else:
            postflop += 1
    assert postflop > 0
    assert unopened > 0
    assert len(_POSTFLOP_CATEGORIES) == 9
