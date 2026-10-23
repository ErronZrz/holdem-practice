"""第十版身份的反例回归：大额承诺少跟注，多人底池少打薄价值。

旧身份的分布不得改变。这里只比较可复现局面上的动作单位，不把份额变化写成质量结论。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.api.schemas import CreateGameRequest
from app.poker.actions import LegalActions
from app.poker.state import Street
from app.strategy.distribution_observation import supported_declaration
from app.strategy.mixed_features import MixedFeatures, extract_features
from app.strategy.mixed_policy import (
    MIXED_LOCAL_V9_RULES,
    MIXED_LOCAL_V10_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    _checked_value_floor,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V9,
    MIXED_STRATEGY_IDENTIFIER_V10,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.registry import (
    capability_declaration,
    create_strategy,
    observation_entry,
    spec_for,
)
from app.verification.config import (
    BASELINE_IDENTIFIER,
    UNDER_TEST_IDENTIFIER,
    UNDER_TEST_IDENTIFIERS,
    campaign_configuration_payload,
)
from app.verification.errors import IdentityMappingError, SpecIncompleteError
from app.verification.execution_identity import _require_entry_value
from app.verification.identity import require_locked_under_test_mapping

from .mixed_bot_states import apply_node, build_frozen_nodes
from .mixed_bot_validation import DIGEST_RULE_FIELDS, config_digest
from .verification_helpers import fixture_lock_versions, under_test_mapping

# 第十版配置摘要。字段集合变了才会变；行为常量不在摘要里，另由直接断言钉住。
_TENTH_CONFIG_DIGEST = (
    "d54f1d467ff56cffeb818e66646c25f5279492cd27098307f5b02ed1a16d5632"
)
_NINTH_CONFIG_DIGEST = (
    "2d3d750d1e3cdb5e9efcea89e44282013d491a1473f36f67731a615eaa862305"
)


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
        "position": 0,
        "texture": 0,
        "contenders": 2,
        "live_opponents": 2,
        "recent_aggression": 0,
        "limpers": 0,
        "price": 0,
        "eligible_pot": 0,
        "actual_call": 0,
        "pot": 40,
        "effective_stack": 400,
        "big_blind": 2,
        "stack": 400,
        "street_bet": 0,
        "preflop_unraised": False,
        "hole_ranks": (10, 8),
    }
    payload.update(overrides)
    return MixedFeatures(**payload)  # type: ignore[arg-type]


def _rows(
    rules: MixedPolicyRules,
    features: MixedFeatures,
    legal: LegalActions,
    style: MixedStyle = MixedStyle.CALLING,
    mode: HandMode = HandMode.NORMAL,
) -> tuple[tuple[str, int, int], ...]:
    distribution = build_distribution(features, legal, style, mode, rules)
    return tuple((item.action.value, item.amount, item.units) for item in distribution.candidates)


def _units(rows: tuple[tuple[str, int, int], ...], action: str) -> int:
    return sum(units for name, _amount, units in rows if name == action)


def _commit_spot() -> tuple[MixedFeatures, LegalActions]:
    """多人底池里面对至少一半筹码的大尺度跟注。"""
    features = _features(
        base=650,
        price=500,
        actual_call=500,
        pot=1000,
        stack=800,
        effective_stack=800,
        contenders=3,
        live_opponents=3,
        recent_aggression=2,
        big_blind=10,
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=500,
        actual_call_amount=500,
        can_raise=True,
        min_raise_to=1000,
        max_raise_to=1500,
    )
    return features, legal


def test_tenth_version_only_adds_the_defense_switch() -> None:
    """第十版只多一个收紧开关，关掉后必须与第九版逐字段相同。"""
    assert MIXED_LOCAL_V10_RULES.large_pot_defense is True
    assert MIXED_LOCAL_V9_RULES.large_pot_defense is False
    assert replace(MIXED_LOCAL_V10_RULES, large_pot_defense=False) == MIXED_LOCAL_V9_RULES


def test_tenth_identity_stays_selectable_when_default_is_fourteenth() -> None:
    """第十版可构造；未指定策略时创建对局使用第十六版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    tenth_at = ordered.index(MIXED_STRATEGY_IDENTIFIER_V10)
    assert ordered[tenth_at - 1] == MIXED_STRATEGY_IDENTIFIER_V9
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V10).version == 10
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V10, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V10
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V10) is MIXED_LOCAL_V10_RULES
    assert CreateGameRequest().bot_strategy == "mixed-local@17"
    selected = CreateGameRequest(bot_strategy=MIXED_STRATEGY_IDENTIFIER_V10)
    assert selected.bot_strategy == MIXED_STRATEGY_IDENTIFIER_V10


def test_tenth_identity_declares_distribution_observation() -> None:
    """第十版登记与第九版相同的能力声明，规则对象仍是第十版自己的。"""
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V10) == supported_declaration()
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V10).rules is MIXED_LOCAL_V10_RULES
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V10).rules is not (
        observation_entry(MIXED_STRATEGY_IDENTIFIER_V9).rules
    )


def test_tenth_digest_appends_only_the_new_switch() -> None:
    """摘要只追加第十版自己的开关，不改写第九版摘要。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V10][-1] == "large_pot_defense"
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V10) == _TENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V9) == _NINTH_CONFIG_DIGEST


def test_flop_facing_bets_match_the_ninth_version() -> None:
    """首套翻牌面对下注节点上，第十版与第九版逐风格、逐模式相同。"""
    nodes = [node for node in build_frozen_nodes() if node.category == "flop-draw"]
    assert len(nodes) == 8
    for node in nodes:
        applied = apply_node(node)
        legal = applied.legal_actions()
        features = extract_features(applied.actor_state(), legal)
        assert features.street is Street.FLOP
        assert features.actual_call > 0
        assert features.price < 500
        for style in MixedStyle:
            for mode in HandMode:
                assert _rows(MIXED_LOCAL_V10_RULES, features, legal, style, mode) == _rows(
                    MIXED_LOCAL_V9_RULES, features, legal, style, mode
                )


def test_large_commitment_below_top_pair_folds() -> None:
    """多人底池里，低于顶对的牌力面对大额承诺时改为弃牌，第九版仍会跟注。"""
    features, legal = _commit_spot()
    weak = replace(features, base=520)
    ninth = _rows(MIXED_LOCAL_V9_RULES, weak, legal)
    tenth = _rows(MIXED_LOCAL_V10_RULES, weak, legal)
    assert _units(ninth, "call") > _units(ninth, "fold")
    assert _units(tenth, "fold") == 1_000_000
    assert _units(tenth, "call") == 0
    assert _units(tenth, "raise") == 0


def test_top_pair_and_heads_up_single_bet_stay_with_the_ninth_version() -> None:
    """顶对，以及单挑的一次下注，不因收紧开关改变分布。"""
    features, legal = _commit_spot()
    assert _rows(MIXED_LOCAL_V10_RULES, features, legal) == _rows(
        MIXED_LOCAL_V9_RULES, features, legal
    )
    heads_up = _features(
        base=650,
        price=500,
        actual_call=200,
        pot=400,
        stack=2000,
        effective_stack=2000,
        contenders=1,
        live_opponents=1,
        recent_aggression=1,
        big_blind=10,
    )
    heads_legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=200,
        actual_call_amount=200,
        can_raise=True,
        min_raise_to=400,
        max_raise_to=2000,
    )
    assert _rows(MIXED_LOCAL_V10_RULES, heads_up, heads_legal, MixedStyle.TIGHT) == _rows(
        MIXED_LOCAL_V9_RULES, heads_up, heads_legal, MixedStyle.TIGHT
    )


def test_short_handed_pressure_stays_with_the_ninth_version() -> None:
    """三人及以下的大额承诺不收紧，避免把人少底池里的跟注一并弃掉。"""
    features = _features(
        base=520,
        price=600,
        actual_call=600,
        pot=800,
        stack=900,
        effective_stack=900,
        contenders=2,
        live_opponents=2,
        recent_aggression=2,
        big_blind=10,
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=600,
        actual_call_amount=600,
        can_raise=True,
        min_raise_to=1200,
        max_raise_to=1500,
    )
    assert _rows(MIXED_LOCAL_V10_RULES, features, legal, MixedStyle.AGGRESSIVE) == _rows(
        MIXED_LOCAL_V9_RULES, features, legal, MixedStyle.AGGRESSIVE
    )


def test_preflop_large_price_is_unchanged() -> None:
    """收紧只发生在翻后，翻前的大额跟注与第九版逐位相同。"""
    features = _features(
        street=Street.PREFLOP,
        base=700,
        price=700,
        actual_call=400,
        pot=200,
        stack=600,
        effective_stack=600,
        contenders=4,
        live_opponents=4,
        recent_aggression=2,
        big_blind=10,
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=400,
        actual_call_amount=400,
        can_raise=True,
        min_raise_to=800,
        max_raise_to=1000,
    )
    assert _rows(MIXED_LOCAL_V10_RULES, features, legal) == _rows(
        MIXED_LOCAL_V9_RULES, features, legal
    )


def test_multiway_checked_medium_hand_loses_the_value_floor() -> None:
    """四人及以上、无人下注时，一对不再被托住下注；人少时下限仍在。"""
    multiway = _features(base=650, contenders=4, live_opponents=4, actual_call=0, pot=80)
    heads_up = _features(base=650, contenders=1, live_opponents=1, actual_call=0, pot=40)
    assert _checked_value_floor(multiway, MIXED_LOCAL_V9_RULES) > 0
    assert _checked_value_floor(multiway, MIXED_LOCAL_V10_RULES) == 0
    assert _checked_value_floor(heads_up, MIXED_LOCAL_V10_RULES) == _checked_value_floor(
        heads_up, MIXED_LOCAL_V9_RULES
    )
    assert _checked_value_floor(heads_up, MIXED_LOCAL_V10_RULES) > 0


def test_multiway_short_stack_does_not_jam_below_top_pair() -> None:
    """短码的多人底池里，低于顶对的牌力不能再打出全下尺度。"""
    features = _features(
        base=590,
        pot=1000,
        stack=400,
        effective_stack=400,
        contenders=3,
        live_opponents=3,
        big_blind=10,
        actual_call=0,
        price=0,
    )
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=400)
    ninth = _rows(MIXED_LOCAL_V9_RULES, features, legal, MixedStyle.AGGRESSIVE)
    tenth = _rows(MIXED_LOCAL_V10_RULES, features, legal, MixedStyle.AGGRESSIVE)
    assert sum(units for _name, amount, units in ninth if amount == 400) > 0
    assert sum(units for _name, amount, units in tenth if amount == 400) == 0
    assert _units(tenth, "bet") > 0


def test_under_test_whitelist_accepts_the_tenth_identity() -> None:
    """被测白名单同时接受第九版到第十六版，其它标识仍然失败。"""
    assert UNDER_TEST_IDENTIFIER == "mixed-local@9"
    assert frozenset(
        {
            "mixed-local@9",
            "mixed-local@10",
            "mixed-local@11",
            "mixed-local@12",
            "mixed-local@13",
            "mixed-local@14",
            "mixed-local@15",
            "mixed-local@16",
            "mixed-local@17",
        }
    ) == (
        UNDER_TEST_IDENTIFIERS
    )
    accepted = require_locked_under_test_mapping(
        under_test_mapping(identifier=MIXED_STRATEGY_IDENTIFIER_V10)
    )
    assert accepted.identifier == MIXED_STRATEGY_IDENTIFIER_V10
    require_locked_under_test_mapping(under_test_mapping())
    with pytest.raises(IdentityMappingError):
        require_locked_under_test_mapping(under_test_mapping(identifier="absent@1"))
    _require_entry_value("under-test-identifier", MIXED_STRATEGY_IDENTIFIER_V10)
    _require_entry_value("under-test-identifier", UNDER_TEST_IDENTIFIER)
    with pytest.raises(SpecIncompleteError):
        _require_entry_value("under-test-identifier", "absent@1")
    versions = fixture_lock_versions()
    common = {
        "num_players": 3,
        "starting_stack": 200,
        "small_blind": 1,
        "big_blind": 2,
        "baseline_identifier": BASELINE_IDENTIFIER,
        "lock_versions": versions,
    }
    ninth = campaign_configuration_payload(
        **common, under_test_identifier=UNDER_TEST_IDENTIFIER
    )
    tenth = campaign_configuration_payload(
        **common, under_test_identifier=MIXED_STRATEGY_IDENTIFIER_V10
    )
    assert ninth["identities"]["under_test"] == "mixed-local@9"
    assert tenth["identities"]["under_test"] == "mixed-local@10"
    with pytest.raises(SpecIncompleteError):
        campaign_configuration_payload(**common, under_test_identifier="absent@1")
