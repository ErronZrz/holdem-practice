"""第十一版身份的反例回归：强成牌打中大尺度，满员桌少做深跟注。

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
    HandMode,
    MixedPolicyRules,
    MixedStyle,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER_V10,
    MIXED_STRATEGY_IDENTIFIER_V11,
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

# 第十一版配置摘要。字段集合变了才会变；行为常量不在摘要里，另由直接断言钉住。
_ELEVENTH_CONFIG_DIGEST = (
    "86daf64b09b196d5619606180e246ccbf585d36bed231257667c538ab8c3ba69"
)
_TENTH_CONFIG_DIGEST = (
    "d54f1d467ff56cffeb818e66646c25f5279492cd27098307f5b02ed1a16d5632"
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


def _open_pot() -> tuple[MixedFeatures, LegalActions]:
    """无人下注、筹码很深，小中大三种尺度都落在合法区间里。"""
    features = _features(base=860, pot=200, stack=2000, effective_stack=2000)
    legal = _legal(can_check=True, can_bet=True, min_bet=10, max_bet=2000)
    return features, legal


def test_eleventh_version_only_adds_two_switches() -> None:
    """第十一版只多两个开关，关掉后必须与第十版逐字段相同。"""
    assert MIXED_LOCAL_V11_RULES.strong_value_sizing is True
    assert MIXED_LOCAL_V11_RULES.full_ring_defense is True
    assert MIXED_LOCAL_V10_RULES.strong_value_sizing is False
    assert MIXED_LOCAL_V10_RULES.full_ring_defense is False
    assert (
        replace(
            MIXED_LOCAL_V11_RULES,
            strong_value_sizing=False,
            full_ring_defense=False,
        )
        == MIXED_LOCAL_V10_RULES
    )


def test_eleventh_identity_stays_selectable_when_default_is_fourteenth() -> None:
    """第十一版可构造；未指定策略时创建对局使用第十四版。"""
    ordered = MIXED_STRATEGY_IDENTIFIERS
    eleventh_at = ordered.index(MIXED_STRATEGY_IDENTIFIER_V11)
    assert ordered[eleventh_at - 1] == MIXED_STRATEGY_IDENTIFIER_V10
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V11).version == 11
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V11, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V11
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V11) is MIXED_LOCAL_V11_RULES
    assert CreateGameRequest().bot_strategy == "mixed-local@14"
    selected = CreateGameRequest(bot_strategy=MIXED_STRATEGY_IDENTIFIER_V11)
    assert selected.bot_strategy == MIXED_STRATEGY_IDENTIFIER_V11


def test_eleventh_identity_declares_distribution_observation() -> None:
    """第十一版登记与第十版相同的能力声明，规则对象仍是第十一版自己的。"""
    assert capability_declaration(MIXED_STRATEGY_IDENTIFIER_V11) == supported_declaration()
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V11).rules is MIXED_LOCAL_V11_RULES
    assert observation_entry(MIXED_STRATEGY_IDENTIFIER_V11).rules is not (
        observation_entry(MIXED_STRATEGY_IDENTIFIER_V10).rules
    )


def test_eleventh_digest_appends_only_the_new_switches() -> None:
    """摘要只追加第十一版自己的开关，不改写第十版摘要。"""
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V11][-2:] == (
        "strong_value_sizing",
        "full_ring_defense",
    )
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V11) == _ELEVENTH_CONFIG_DIGEST
    assert config_digest(MIXED_STRATEGY_IDENTIFIER_V10) == _TENTH_CONFIG_DIGEST


def test_flop_facing_bets_match_the_tenth_version() -> None:
    """首套翻牌面对下注节点上，第十一版与第十版逐风格、逐模式相同。"""
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
                assert _rows(MIXED_LOCAL_V11_RULES, features, legal, style, mode) == _rows(
                    MIXED_LOCAL_V10_RULES, features, legal, style, mode
                )


def test_strong_made_hand_shifts_weight_onto_larger_sizes() -> None:
    """两对高档以上、无人下注时，主动单位从微注挪到更大的尺度，第十版仍偏小。"""
    features, legal = _open_pot()
    tenth = _rows(MIXED_LOCAL_V10_RULES, features, legal)
    eleventh = _rows(MIXED_LOCAL_V11_RULES, features, legal)
    assert _units(eleventh, "bet") > _units(tenth, "bet")
    assert _modal_active_amount(eleventh) > _modal_active_amount(tenth)
    assert _units(eleventh, "check") < _units(tenth, "check")


def test_strong_sizing_also_applies_when_the_table_is_short() -> None:
    """强成牌的尺度上移不依赖满员桌；两人桌同样离开微注。"""
    features, legal = _open_pot()
    short = replace(features, seat_count=2, contenders=1, live_opponents=1)
    tenth = _rows(MIXED_LOCAL_V10_RULES, short, legal, MixedStyle.TIGHT)
    eleventh = _rows(MIXED_LOCAL_V11_RULES, short, legal, MixedStyle.TIGHT)
    assert _modal_active_amount(eleventh) > _modal_active_amount(tenth)


def test_top_pair_on_a_short_table_stays_with_the_tenth_version() -> None:
    """顶对在人少的桌子上不因强成牌路径改变分布。"""
    features, legal = _open_pot()
    top_pair = replace(features, base=650, seat_count=3, contenders=1, live_opponents=1)
    assert _rows(MIXED_LOCAL_V11_RULES, top_pair, legal) == _rows(
        MIXED_LOCAL_V10_RULES, top_pair, legal
    )


def test_full_ring_medium_hand_folds_a_deep_call() -> None:
    """满员桌只剩两人时，中等牌力面对深跟注改为弃牌；第十版仍会跟。"""
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
    tenth = _rows(MIXED_LOCAL_V10_RULES, features, legal)
    eleventh = _rows(MIXED_LOCAL_V11_RULES, features, legal)
    assert _units(tenth, "call") > _units(tenth, "fold")
    assert _units(eleventh, "fold") == 1_000_000
    assert _units(eleventh, "call") == 0
    assert _units(eleventh, "raise") == 0
    short = replace(features, seat_count=6)
    assert _rows(MIXED_LOCAL_V11_RULES, short, legal) == _rows(
        MIXED_LOCAL_V10_RULES, short, legal
    )


def test_full_ring_does_not_fold_a_strong_made_hand() -> None:
    """同一口深跟注上，两对高档及以上仍然留在第十版的跟注或加注里，不被满员桌规则弃掉。"""
    features = _features(
        base=840,
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
    assert _units(eleventh, "fold") < 1_000_000
    assert _units(eleventh, "call") + _units(eleventh, "raise") > _units(eleventh, "fold")


def test_full_ring_weak_preflop_call_folds() -> None:
    """满员桌翻前，低于中对档且价格已经不小时改为弃牌；人少时与第十版相同。"""
    features = _features(
        street=Street.PREFLOP,
        base=331,
        price=343,
        actual_call=55,
        pot=80,
        stack=990,
        effective_stack=990,
        contenders=2,
        live_opponents=2,
        seat_count=9,
        big_blind=10,
        hole_ranks=(7, 2),
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=55,
        actual_call_amount=55,
        can_raise=True,
        min_raise_to=110,
        max_raise_to=990,
    )
    tenth = _rows(MIXED_LOCAL_V10_RULES, features, legal)
    eleventh = _rows(MIXED_LOCAL_V11_RULES, features, legal)
    assert _units(tenth, "call") > _units(tenth, "fold")
    assert _units(eleventh, "fold") > _units(eleventh, "call")
    short = replace(features, seat_count=5)
    assert _rows(MIXED_LOCAL_V11_RULES, short, legal) == _rows(
        MIXED_LOCAL_V10_RULES, short, legal
    )


def test_premium_preflop_is_not_folded_by_the_full_ring_rule() -> None:
    """翻前强牌在满员桌上仍不弃牌，第十版本来就不弃的继续被保留。"""
    features = _features(
        street=Street.PREFLOP,
        base=850,
        price=343,
        actual_call=55,
        pot=80,
        stack=990,
        effective_stack=990,
        contenders=6,
        live_opponents=6,
        seat_count=9,
        big_blind=10,
        hole_ranks=(12, 12),
    )
    legal = _legal(
        can_fold=True,
        can_call=True,
        call_amount=55,
        actual_call_amount=55,
        can_raise=True,
        min_raise_to=110,
        max_raise_to=990,
    )
    tenth = _rows(MIXED_LOCAL_V10_RULES, features, legal, MixedStyle.TIGHT)
    eleventh = _rows(MIXED_LOCAL_V11_RULES, features, legal, MixedStyle.TIGHT)
    assert _units(tenth, "fold") == 0
    assert _units(eleventh, "fold") == 0
    assert _units(eleventh, "raise") + _units(eleventh, "call") == 1_000_000


def test_full_ring_medium_hand_drops_the_large_size() -> None:
    """满员桌无人下注时，中等成牌不再把单位放在最大的主动尺度上。"""
    features, legal = _open_pot()
    medium = replace(features, base=650, seat_count=8, contenders=5, live_opponents=5)
    tenth = _rows(MIXED_LOCAL_V10_RULES, medium, legal, MixedStyle.AGGRESSIVE)
    eleventh = _rows(MIXED_LOCAL_V11_RULES, medium, legal, MixedStyle.AGGRESSIVE)

    def largest(rows: tuple[tuple[str, int, int], ...]) -> int:
        amounts = [amount for name, amount, units in rows if name == "bet" and units > 0]
        assert amounts
        return max(amounts)

    assert largest(eleventh) < largest(tenth)
    assert _units(eleventh, "bet") > 0


def test_under_test_whitelist_accepts_the_eleventh_identity() -> None:
    """被测白名单同时接受第九版到第十四版，其它标识仍然失败。"""
    assert UNDER_TEST_IDENTIFIER == "mixed-local@9"
    assert frozenset(
        {
            "mixed-local@9",
            "mixed-local@10",
            "mixed-local@11",
            "mixed-local@12",
            "mixed-local@13",
            "mixed-local@14",
        }
    ) == (
        UNDER_TEST_IDENTIFIERS
    )
    accepted = require_locked_under_test_mapping(
        under_test_mapping(identifier=MIXED_STRATEGY_IDENTIFIER_V11)
    )
    assert accepted.identifier == MIXED_STRATEGY_IDENTIFIER_V11
    _require_entry_value("under-test-identifier", MIXED_STRATEGY_IDENTIFIER_V11)
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
    eleventh = campaign_configuration_payload(
        **common, under_test_identifier=MIXED_STRATEGY_IDENTIFIER_V11
    )
    assert ninth["identities"]["under_test"] == "mixed-local@9"
    assert eleventh["identities"]["under_test"] == "mixed-local@11"
    with pytest.raises(IdentityMappingError):
        require_locked_under_test_mapping(under_test_mapping(identifier="absent@1"))
    with pytest.raises(SpecIncompleteError):
        campaign_configuration_payload(**common, under_test_identifier="absent@1")
