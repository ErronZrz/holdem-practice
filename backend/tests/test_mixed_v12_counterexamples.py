"""第十二版身份的反例回归：强成牌少把底池打大，同花及以上在无人下注时兑现整叠。

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
    MIXED_LOCAL_V10_RULES,
    MIXED_LOCAL_V11_RULES,
    MIXED_LOCAL_V12_RULES,
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V11,
    MIXED_STRATEGY_IDENTIFIER_V12,
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

# 第十二版配置摘要。字段集合变了才会变；行为常量不在摘要里，另由直接断言钉住。
_TWELFTH_CONFIG_DIGEST = (
    "ca5a4fe9d5ce5f8bcda98dac622fc80afa97ae9fde1fba2976cea16e94a58e24"
)
_ELEVENTH_CONFIG_DIGEST = (
    "86daf64b09b196d5619606180e246ccbf585d36bed231257667c538ab8c3ba69"
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
        "pot": 200,
        "effective_stack": 2000,
        "big_blind": 10,
        "stack": 2000,
        "street_bet": 0,
        "preflop_unraised": False,
        "hole_ranks": (14, 14),
        "seat_count": 6,
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


def _active_amounts(rows: tuple[tuple[str, int, int], ...]) -> tuple[int, ...]:
    return tuple(
        amount for name, amount, units in rows if name in ("bet", "raise") and units > 0
    )


def _modal_active_amount(rows: tuple[tuple[str, int, int], ...]) -> int:
    """主动单位最多的额度；并列时取更大的额度，用来看尺度有没有上移。"""
    active = [
        (amount, units)
        for name, amount, units in rows
        if name in ("bet", "raise") and units > 0
    ]
    assert active
    best = max(units for _amount, units in active)
    return max(amount for amount, units in active if units == best)


def _open_pot(base: int = 860) -> tuple[MixedFeatures, LegalActions]:
    """无人下注、筹码很深，小中大与全下都落在合法区间里。"""
    features = _features(base=base, pot=200, stack=2000, effective_stack=2000)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=2000)
    return features, legal


def test_twelfth_version_only_adds_the_guard() -> None:
    """第十二版只多一个尺度收回开关，关掉后必须与第十一版逐字段相同。"""
    assert MIXED_LOCAL_V12_RULES.guarded_strong_commitment is True
    assert MIXED_LOCAL_V11_RULES.guarded_strong_commitment is False
    assert MIXED_LOCAL_V12_RULES.strong_value_sizing is True
    assert MIXED_LOCAL_V12_RULES.full_ring_defense is True
    assert (
        replace(MIXED_LOCAL_V12_RULES, guarded_strong_commitment=False)
        == MIXED_LOCAL_V11_RULES
    )


def test_twelfth_identity_stays_selectable_when_default_is_fourteenth() -> None:
    """第十二版可构造；未指定策略时创建对局使用第十六版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    twelfth_at = ordered.index(MIXED_STRATEGY_IDENTIFIER_V12)
    assert ordered[twelfth_at - 1] == MIXED_STRATEGY_IDENTIFIER_V11
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V12).version == 12
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V12, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V12
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V12) is MIXED_LOCAL_V12_RULES
    assert CreateGameRequest().bot_strategy == "mixed-local@18"
    selected = CreateGameRequest(bot_strategy=MIXED_STRATEGY_IDENTIFIER_V12)
    assert selected.bot_strategy == MIXED_STRATEGY_IDENTIFIER_V12


def test_twelfth_identity_declares_distribution_observation() -> None:
    """第十二版登记与第十一版相同的能力声明，规则对象仍是第十二版自己的。"""
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V12) == supported_declaration()
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V12).rules is MIXED_LOCAL_V12_RULES
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V12).rules is not (
        observation_entry(MIXED_STRATEGY_IDENTIFIER_V11).rules
    )


def test_twelfth_digest_appends_only_the_new_switch() -> None:
    """摘要只追加第十二版自己的开关，不改写第十一版摘要。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V12][-1:] == (
        "guarded_strong_commitment",
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V12) == _TWELFTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V11) == _ELEVENTH_CONFIG_DIGEST


def test_flop_facing_bets_match_the_eleventh_version() -> None:
    """首套翻牌面对下注节点上，第十二版与第十一版逐风格、逐模式相同。"""
    nodes = [node for node in build_frozen_nodes() if node.category == "flop-draw"]
    assert len(nodes) == 8
    for node in nodes:
        applied = apply_node(node)
        legal = applied.legal_actions()
        features = extract_features(applied.actor_state(), legal)
        assert features.street is Street.FLOP
        assert features.actual_call > 0
        assert features.base < 500
        for style in MixedStyle:
            for mode in HandMode:
                assert _rows(MIXED_LOCAL_V12_RULES, features, legal, style, mode) == _rows(
                    MIXED_LOCAL_V11_RULES, features, legal, style, mode
                )


def test_preflop_strong_hand_keeps_the_style_sizes() -> None:
    """翻前强牌不再改用中大尺度；第十一版的开池额度更大。"""
    features = _features(
        street=Street.PREFLOP,
        base=920,
        pot=15,
        stack=1000,
        effective_stack=1000,
        actual_call=10,
        price=400,
        street_bet=0,
        preflop_unraised=True,
        big_blind=10,
        hole_ranks=(14, 14),
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=10,
        actual_call_amount=10,
        can_raise=True,
        min_raise_to=20,
        max_raise_to=1000,
    )
    tenth = _rows(MIXED_LOCAL_V10_RULES, features, legal)
    eleventh = _rows(MIXED_LOCAL_V11_RULES, features, legal)
    twelfth = _rows(MIXED_LOCAL_V12_RULES, features, legal)
    assert _active_amounts(twelfth) == _active_amounts(tenth)
    assert _modal_active_amount(eleventh) > _modal_active_amount(twelfth)
    assert _units(twelfth, "fold") <= _units(eleventh, "fold")


def test_pressured_strong_hand_uses_the_smaller_raise() -> None:
    """面对下注时，未到同花的强成牌把加注收回较小额度，但仍保留加注。"""
    features = _features(
        base=780,
        pot=400,
        actual_call=100,
        price=250,
        stack=2000,
        effective_stack=2000,
        street_bet=0,
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=100,
        actual_call_amount=100,
        can_raise=True,
        min_raise_to=200,
        max_raise_to=2000,
    )
    eleventh = _rows(MIXED_LOCAL_V11_RULES, features, legal)
    twelfth = _rows(MIXED_LOCAL_V12_RULES, features, legal)
    assert _units(twelfth, "raise") > 0
    assert _modal_active_amount(twelfth) < _modal_active_amount(eleventh)


def test_checked_to_nuts_restore_the_all_in() -> None:
    """无人下注的同花及以上把整叠放回偏好；第十一版这条额度是空的。"""
    features, legal = _open_pot(900)
    eleventh = _rows(MIXED_LOCAL_V11_RULES, features, legal)
    twelfth = _rows(MIXED_LOCAL_V12_RULES, features, legal)
    assert _units(eleventh, "bet") > 0
    assert sum(units for name, amount, units in eleventh if amount == 2000) == 0
    assert sum(units for name, amount, units in twelfth if amount == 2000) > 0


def test_checked_to_straight_stays_with_the_eleventh_version() -> None:
    """顺子仍走第十一版的中大尺度，不因为同花门槛把整叠打进去。"""
    features, legal = _open_pot(860)
    assert _rows(MIXED_LOCAL_V12_RULES, features, legal) == _rows(
        MIXED_LOCAL_V11_RULES, features, legal
    )
    twelfth = _rows(MIXED_LOCAL_V12_RULES, features, legal)
    assert sum(units for _name, amount, units in twelfth if amount == 2000) == 0


def test_top_pair_stays_with_the_eleventh_version() -> None:
    """顶对不进入强成牌路径，分布与第十一版相同。"""
    features, legal = _open_pot(650)
    assert _rows(MIXED_LOCAL_V12_RULES, features, legal) == _rows(
        MIXED_LOCAL_V11_RULES, features, legal
    )


def test_full_ring_medium_hand_still_folds_a_deep_call() -> None:
    """满员桌的深跟注收紧保持第十一版，人少的桌子仍不收紧。"""
    features = _features(
        base=520,
        price=500,
        actual_call=400,
        pot=800,
        stack=2000,
        effective_stack=2000,
        contenders=2,
        live_opponents=2,
        recent_aggression=1,
        seat_count=9,
        big_blind=10,
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=400,
        actual_call_amount=400,
        can_raise=True,
        min_raise_to=800,
        max_raise_to=2000,
    )
    eleventh = _rows(MIXED_LOCAL_V11_RULES, features, legal)
    twelfth = _rows(MIXED_LOCAL_V12_RULES, features, legal)
    assert twelfth == eleventh
    assert _units(twelfth, "fold") == 1_000_000
    short = replace(features, seat_count=6)
    assert _rows(MIXED_LOCAL_V12_RULES, short, legal) == _rows(
        MIXED_LOCAL_V11_RULES, short, legal
    )


def test_under_test_whitelist_accepts_the_twelfth_identity() -> None:
    """被测白名单同时接受第九版到第十六版；既有第九版载荷仍写第九版。"""
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
            "mixed-local@18",
        }
    ) == UNDER_TEST_IDENTIFIERS
    accepted = require_locked_under_test_mapping(
        under_test_mapping(identifier=MIXED_STRATEGY_IDENTIFIER_V12)
    )
    assert accepted.identifier == MIXED_STRATEGY_IDENTIFIER_V12
    _require_entry_value("under-test-identifier", MIXED_STRATEGY_IDENTIFIER_V12)
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
    twelfth = campaign_configuration_payload(
        **common, under_test_identifier=MIXED_STRATEGY_IDENTIFIER_V12
    )
    assert ninth["identities"]["under_test"] == "mixed-local@9"
    assert twelfth["identities"]["under_test"] == "mixed-local@12"
    with pytest.raises(IdentityMappingError):
        require_locked_under_test_mapping(under_test_mapping(identifier="absent@1"))
    with pytest.raises(SpecIncompleteError):
        campaign_configuration_payload(**common, under_test_identifier="absent@1")
