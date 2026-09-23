"""第六版身份的两处口径回归：主动分支尺度、人数惩罚上限，以及旧身份的逐位隔离。

口径的验证一律采用「单开关隔离」：把第六版规则对象里的目标开关单独还原，
比较其余部分完全相同的两份分布，避免另一处改动混入结论。

只做有界单元回归与冻结节点回放：不跑性能矩阵、不对抗对局、不访问真实库。
"""

import hashlib
import json
from dataclasses import replace

import pytest

from app.poker.actions import LegalActions
from app.poker.state import Street
from app.strategy.mixed_features import MixedFeatures, extract_features
from app.strategy.mixed_policy import (
    MIXED_LOCAL_V1_RULES,
    MIXED_LOCAL_V2_RULES,
    MIXED_LOCAL_V3_RULES,
    MIXED_LOCAL_V4_RULES,
    MIXED_LOCAL_V5_RULES,
    MIXED_LOCAL_V6_RULES,
    HandMode,
    MixedDistribution,
    MixedPolicyRules,
    MixedStyle,
    build_distribution,
)
from app.strategy.mixed_strategy import (
    MIXED_STRATEGY_IDENTIFIER,
    MIXED_STRATEGY_IDENTIFIER_V2,
    MIXED_STRATEGY_IDENTIFIER_V3,
    MIXED_STRATEGY_IDENTIFIER_V4,
    MIXED_STRATEGY_IDENTIFIER_V5,
    MIXED_STRATEGY_IDENTIFIER_V6,
    MIXED_STRATEGY_IDENTIFIER_V7,
    MIXED_STRATEGY_IDENTIFIERS,
    rules_for_identifier,
)
from app.strategy.registry import create_strategy, spec_for

from .mixed_bot_states import applicable_player_counts, apply_node, build_node
from .mixed_bot_validation import DIGEST_RULE_FIELDS

# 改动前用旧实现捕获的逐动作摘要：改动后必须逐字复现。
PRE_CHANGE_LOSSY_DIGEST = (
    "6f96e7ccf9e2fd2a740e484866d76678e9a192dc46b092128f75c22a6314972c"
)
# 无损失黄金摘要：逐候选记录动作、金额与单位，额度结构的变化也会被它捕获。
FULL_GOLDEN_DIGEST = (
    "d41fc2b4421c1d0ae85c8f965c251cf4834be64bd65b740c4e09c83f9d57d37c"
)
# 改动前捕获时所用的身份与规则对应关系。
FROZEN_IDENTITIES = (
    (MIXED_STRATEGY_IDENTIFIER, MIXED_LOCAL_V1_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V2, MIXED_LOCAL_V2_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V3, MIXED_LOCAL_V3_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V4, MIXED_LOCAL_V4_RULES),
    (MIXED_STRATEGY_IDENTIFIER_V5, MIXED_LOCAL_V5_RULES),
)


def _features(**overrides: object) -> MixedFeatures:
    payload: dict[str, object] = {
        "street": Street.FLOP,
        "base": 500,
        "draw": 0,
        "position": 0,
        "texture": 0,
        "contenders": 1,
        "live_opponents": 1,
        "recent_aggression": 0,
        "limpers": 0,
        "price": 0,
        "eligible_pot": 100,
        "actual_call": 0,
        "pot": 100,
        "effective_stack": 1000,
        "big_blind": 10,
        "stack": 1000,
        "street_bet": 0,
        "preflop_unraised": False,
        "hole_ranks": (14, 13),
    }
    payload.update(overrides)
    return MixedFeatures(**payload)  # type: ignore[arg-type]


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


def _facing(street_bet: int = 100) -> LegalActions:
    """翻牌或河牌上面临下注：可弃、可跟、可加注，无可过牌与可下注。"""
    return _legal(
        can_fold=True,
        can_call=True,
        call_amount=street_bet,
        actual_call_amount=street_bet,
        can_raise=True,
        min_raise_to=2 * street_bet,
        max_raise_to=1000,
    )


def _with_contenders(count: int) -> MixedFeatures:
    """把同一局面改成人数的函数：对手数与有筹码对手数同步变化。"""
    return _features(
        base=760,
        price=1000,
        pot=300,
        eligible_pot=300,
        actual_call=100,
        street_bet=100,
        contenders=count,
        live_opponents=count,
    )


def _states() -> dict[str, tuple[MixedFeatures, LegalActions]]:
    """改动前捕获黄金值时所用的全部局面，顺序与取值都必须逐字一致。"""
    return {
        "flop-facing-no-draw": (
            _features(
                base=400,
                draw=0,
                price=1000,
                actual_call=100,
                pot=300,
                eligible_pot=300,
                street_bet=100,
            ),
            _facing(),
        ),
        "flop-facing-draw": (
            _features(
                base=180,
                draw=140,
                price=1000,
                actual_call=100,
                pot=300,
                eligible_pot=300,
                street_bet=100,
            ),
            _facing(),
        ),
        "flop-facing-multiway": (
            _features(
                base=250,
                draw=100,
                contenders=5,
                live_opponents=5,
                price=1000,
                actual_call=100,
                pot=300,
                eligible_pot=300,
                street_bet=100,
            ),
            _facing(),
        ),
        "river-shared-locked": (
            _features(
                street=Street.RIVER,
                base=450,
                draw=0,
                shared_board_locked=True,
                contenders=3,
                live_opponents=3,
                price=1000,
                actual_call=200,
                pot=600,
                eligible_pot=600,
                street_bet=200,
            ),
            _facing(200),
        ),
        "river-no-blocker-no-draw": (
            _features(
                street=Street.RIVER,
                base=200,
                draw=0,
                contenders=2,
                live_opponents=2,
                price=1000,
                actual_call=200,
                pot=600,
                eligible_pot=600,
                street_bet=200,
                hole_ranks=(9, 8),
            ),
            _facing(200),
        ),
        "river-multiway-overpair": (
            _features(
                street=Street.RIVER,
                base=720,
                draw=0,
                contenders=7,
                live_opponents=7,
                price=1000,
                actual_call=200,
                pot=600,
                eligible_pot=600,
                street_bet=200,
                hole_ranks=(12, 12),
            ),
            _facing(200),
        ),
        "preflop-unraised-open": (
            _features(
                street=Street.PREFLOP,
                base=446,
                draw=0,
                position=20,
                preflop_unraised=True,
                price=0,
                actual_call=0,
                pot=15,
                eligible_pot=15,
                street_bet=10,
                hole_ranks=(12, 11),
            ),
            _legal(can_fold=True, can_raise=True, min_raise_to=20, max_raise_to=1000),
        ),
    }


def _digest(payload: object) -> str:
    material = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _distribution(
    normalized_features: MixedFeatures,
    legal: LegalActions,
    style: MixedStyle,
    rules: MixedPolicyRules,
) -> MixedDistribution:
    return build_distribution(normalized_features, legal, style, HandMode.NORMAL, rules)


def _active_share(
    normalized_features: MixedFeatures,
    legal: LegalActions,
    style: MixedStyle,
    rules: MixedPolicyRules,
) -> float:
    """主动份额：加注与下注单位之和除以总单位。"""
    candidates = _distribution(normalized_features, legal, style, rules).candidates
    total = sum(item.units for item in candidates)
    active = sum(
        item.units for item in candidates if item.action.value in ("bet", "raise")
    )
    return active / total


# ------------------------------------------------------------------ 取值与身份


def test_sixth_version_values_are_recorded() -> None:
    """第六版的两个开关取值被钉住，其余字段与第五版逐字一致。"""
    assert MIXED_LOCAL_V6_RULES.active_scale_percent == 10
    assert MIXED_LOCAL_V6_RULES.contender_penalty_cap == 70
    assert replace(
        MIXED_LOCAL_V6_RULES, active_scale_percent=1, contender_penalty_cap=0
    ) == MIXED_LOCAL_V5_RULES


def test_first_five_identities_keep_their_distributions() -> None:
    """旧身份在这批固定局面上必须逐位不变：新字段的默认值不得改动任何既有分布。"""
    full: dict[str, dict[str, dict[str, list[list[object]]]]] = {}
    lossy: dict[str, dict[str, dict[str, dict[str, int]]]] = {}
    for identifier, rules in FROZEN_IDENTITIES:
        full[identifier] = {}
        lossy[identifier] = {}
        for name, (normalized_features, legal) in _states().items():
            full[identifier][name] = {}
            lossy[identifier][name] = {}
            for style in MixedStyle:
                candidates = _distribution(
                    normalized_features, legal, style, rules
                ).candidates
                full[identifier][name][style.value] = [
                    [item.action.value, item.amount, item.units] for item in candidates
                ]
                # 有损投影只作为改动前捕获的交叉核对：同名动作只留最后一行。
                lossy[identifier][name][style.value] = {
                    item.action.value: item.units for item in candidates
                }
    assert _digest(full) == FULL_GOLDEN_DIGEST
    assert _digest(lossy) == PRE_CHANGE_LOSSY_DIGEST


def test_first_five_digest_fields_stay_registered() -> None:
    """旧身份的摘要字段登记逐字不变，新身份不得顺带改动它们的摘要。"""
    assert DIGEST_RULE_FIELDS["mixed-local@2"] == ("shared_board_chop_caliber",)
    assert DIGEST_RULE_FIELDS["mixed-local@3"] == (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
    )
    assert DIGEST_RULE_FIELDS["mixed-local@4"] == DIGEST_RULE_FIELDS["mixed-local@3"]
    assert DIGEST_RULE_FIELDS["mixed-local@5"] == (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
        "postflop_call_bonus",
    )
    assert DIGEST_RULE_FIELDS[MIXED_STRATEGY_IDENTIFIER_V6] == (
        "shared_board_chop_caliber",
        "preflop_price_weight",
        "preflop_contender_penalty",
        "preflop_call_bonus",
        "postflop_call_bonus",
        "active_scale_percent",
        "contender_penalty_cap",
    )


def test_sixth_identity_is_registered_and_cumulative() -> None:
    """第六版已注册、可构造，并与第五版共用除两个开关以外的全部口径。"""
    assert MIXED_STRATEGY_IDENTIFIERS == (
        MIXED_STRATEGY_IDENTIFIER,
        MIXED_STRATEGY_IDENTIFIER_V2,
        MIXED_STRATEGY_IDENTIFIER_V3,
        MIXED_STRATEGY_IDENTIFIER_V4,
        MIXED_STRATEGY_IDENTIFIER_V5,
        MIXED_STRATEGY_IDENTIFIER_V6,
        MIXED_STRATEGY_IDENTIFIER_V7,
    )
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V6).version == 6
    assert spec_for(MIXED_STRATEGY_IDENTIFIER_V6).name == "mixed-local"
    assert create_strategy(MIXED_STRATEGY_IDENTIFIER_V6, 5).identifier == (
        MIXED_STRATEGY_IDENTIFIER_V6
    )
    assert rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V6) is MIXED_LOCAL_V6_RULES
    assert MIXED_LOCAL_V6_RULES.shared_board_chop_caliber is True


# ------------------------------------------------------------------ 主动分支尺度


def test_flat_scale_switch_reproduces_the_fifth_version() -> None:
    """把尺度开关还原为 1、人数上限还原为 0，第六版的规则对象必须与第五版逐字一致。"""
    flat = replace(
        MIXED_LOCAL_V6_RULES, active_scale_percent=1, contender_penalty_cap=0
    )
    assert flat == MIXED_LOCAL_V5_RULES


@pytest.mark.parametrize(
    "name", ["flop-facing-no-draw", "flop-facing-draw", "preflop-unraised-open"]
)
def test_active_scale_changes_every_unsaturated_branch(name: str) -> None:
    """放大尺度必须改变每个尚未饱和的分支；主动份额已为 1 的分支本就不可能再变。"""
    normalized_features, legal = _states()[name]
    flat = replace(MIXED_LOCAL_V6_RULES, active_scale_percent=1, contender_penalty_cap=0)
    changed = 0
    for style in MixedStyle:
        unchanged = _active_share(normalized_features, legal, style, flat) >= 1.0
        if unchanged:
            continue
        assert _distribution(
            normalized_features, legal, style, MIXED_LOCAL_V6_RULES
        ) != _distribution(normalized_features, legal, style, flat)
        changed += 1
    assert changed > 0


@pytest.mark.parametrize(
    "name", ["flop-facing-no-draw", "flop-facing-draw", "preflop-unraised-open"]
)
@pytest.mark.parametrize("style", list(MixedStyle))
def test_active_scale_renormalizes_exactly_as_declared(name: str, style: MixedStyle) -> None:
    """把主动权重整体放大十倍，归一化后的份额必须等于该倍率的解析解。

    主动量放大到十倍、被动量不变时，份额满足 s10 = 10·s1 / (1 + 9·s1)；
    这不是取值断言，而是「尺度确实被整体放大十倍」的直接推论。
    """
    normalized_features, legal = _states()[name]
    flat = replace(MIXED_LOCAL_V6_RULES, active_scale_percent=1, contender_penalty_cap=0)
    scaled = replace(MIXED_LOCAL_V6_RULES, contender_penalty_cap=0)
    base_share = _active_share(normalized_features, legal, style, flat)
    scaled_share = _active_share(normalized_features, legal, style, scaled)
    expected = (10 * base_share) / (1 + 9 * base_share)
    assert scaled_share == pytest.approx(expected, abs=2e-5)


def test_crowd_cap_does_not_disturb_the_scale_check() -> None:
    """人数上限只影响多人桌：单人桌上的两份第六版分布必须逐位一致。"""
    normalized_features, legal = _states()["flop-facing-no-draw"]
    no_cap = replace(MIXED_LOCAL_V6_RULES, contender_penalty_cap=0)
    for style in MixedStyle:
        assert _distribution(
            normalized_features, legal, style, MIXED_LOCAL_V6_RULES
        ) == _distribution(normalized_features, legal, style, no_cap)


def test_flop_draw_node_separates_the_three_styles() -> None:
    """冻结的翻牌面对下注节点上，三档风格的主动份额必须出现非零差。"""
    count = applicable_player_counts("flop-draw")[0]
    node = apply_node(build_node("flop-draw", count))
    normalized_features = extract_features(node.actor_state(), node.legal_actions())
    legal = node.legal_actions()
    fifth = {
        style: _active_share(normalized_features, legal, style, MIXED_LOCAL_V5_RULES)
        for style in MixedStyle
    }
    sixth = {
        style: _active_share(normalized_features, legal, style, replace(
            MIXED_LOCAL_V6_RULES, contender_penalty_cap=0
        ))
        for style in MixedStyle
    }
    assert max(fifth.values()) - min(fifth.values()) > 0
    assert max(sixth.values()) - min(sixth.values()) > 0
    assert max(sixth.values()) - min(sixth.values()) > (
        max(fifth.values()) - min(fifth.values())
    )
    # 攻击型在主动分支上的倍率最高，其主动份额必须高于跟注型。
    assert sixth[MixedStyle.AGGRESSIVE] > sixth[MixedStyle.CALLING]


# ------------------------------------------------------------------ 人数惩罚上限


@pytest.mark.parametrize("contenders", [1, 2, 3])
def test_crowd_cap_has_no_effect_up_to_two_extra_opponents(contenders: int) -> None:
    """额外对手不超过两名时，扣分本就在上限之内，两份分布必须逐位一致。"""
    normalized_features = _with_contenders(contenders)
    legal = _facing()
    no_cap = replace(MIXED_LOCAL_V6_RULES, contender_penalty_cap=0)
    for style in MixedStyle:
        assert _distribution(
            normalized_features, legal, style, MIXED_LOCAL_V6_RULES
        ) == _distribution(normalized_features, legal, style, no_cap)


@pytest.mark.parametrize("contenders", [4, 5, 7])
def test_crowd_cap_binds_beyond_two_extra_opponents(contenders: int) -> None:
    """额外对手超过两名后，上限开始生效，两份分布必须不同。"""
    normalized_features = _with_contenders(contenders)
    legal = _facing()
    no_cap = replace(MIXED_LOCAL_V6_RULES, contender_penalty_cap=0)
    for style in MixedStyle:
        assert _distribution(
            normalized_features, legal, style, MIXED_LOCAL_V6_RULES
        ) != _distribution(normalized_features, legal, style, no_cap)


@pytest.mark.parametrize("style", list(MixedStyle))
def test_crowd_cap_makes_larger_tables_agree(style: MixedStyle) -> None:
    """封顶之后，额外对手从三名起再加人的扣分不再累加，分布随之一致。"""
    legal = _facing()
    reference = _distribution(_with_contenders(4), legal, style, MIXED_LOCAL_V6_RULES)
    for contenders in (5, 7):
        assert (
            _distribution(_with_contenders(contenders), legal, style, MIXED_LOCAL_V6_RULES)
            == reference
        )


def test_crowd_cap_lifts_the_multiway_collapse() -> None:
    """不设上限时最大人数桌上的紧密型会退化为全弃牌；设上限后仍有自愿投入。

    只断言方向，不写任何门槛数值。
    """
    normalized_features = _with_contenders(7)
    legal = _facing()
    no_cap = replace(MIXED_LOCAL_V6_RULES, contender_penalty_cap=0)
    collapsed = _distribution(
        normalized_features, legal, MixedStyle.TIGHT, no_cap
    ).candidates
    capped = _distribution(
        normalized_features, legal, MixedStyle.TIGHT, MIXED_LOCAL_V6_RULES
    ).candidates
    assert [item.units for item in collapsed][0] == 1_000_000
    assert capped[0].units < 1_000_000
