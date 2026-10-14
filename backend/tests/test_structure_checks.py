"""片段、权重、终局上界与配对记录的直接断言。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.verification import (
    CampaignLockVersions,
    DomainRunSpec,
    FragmentSpan,
    HandPlan,
    SpecIncompleteError,
    VerificationError,
    campaign_configuration_payload,
)
from app.verification.structure_checks import (
    ArmTerminal,
    PairingTranscript,
    derived_difference_bound,
    require_pairing_transcript,
)

from .verification_helpers import fixture_lock_versions, run_spec


def test_difference_bound_is_the_width_of_two_nets() -> None:
    assert derived_difference_bound(6, 200) == 6 * 200
    assert derived_difference_bound(2, 1) == 2
    with pytest.raises(SpecIncompleteError):
        derived_difference_bound(1, 200)


def test_single_hand_block_must_declare_degeneracy() -> None:
    spec = run_spec(hands=1)
    assert spec.k_min_degenerate is True
    fields = spec.model_dump()
    fields["k_min_degenerate"] = False
    with pytest.raises(SpecIncompleteError, match="退化"):
        DomainRunSpec.model_validate(fields)


def test_split_fragments_must_use_exact_hand_shares() -> None:
    spec = run_spec(hands=4, num_players=2)
    fields = spec.model_dump()
    fields["fragments"] = [
        {"start_ordinal": 1, "end_ordinal": 2},
        {"start_ordinal": 3, "end_ordinal": 4},
    ]
    fields["weights"] = [
        {"numerator": 1, "denominator": 2},
        {"numerator": 1, "denominator": 2},
    ]
    fields["k_min_degenerate"] = False
    rebuilt = DomainRunSpec.model_validate(fields)
    assert rebuilt.fragments == (
        FragmentSpan(start_ordinal=1, end_ordinal=2),
        FragmentSpan(start_ordinal=3, end_ordinal=4),
    )
    fields["weights"] = [
        {"numerator": 2, "denominator": 4},
        {"numerator": 1, "denominator": 2},
    ]
    with pytest.raises(SpecIncompleteError, match="既约"):
        DomainRunSpec.model_validate(fields)


def test_fragment_gap_is_rejected() -> None:
    spec = run_spec(hands=2, num_players=2)
    fields = spec.model_dump()
    fields["schedule"] = [
        HandPlan(hand_ordinal=1, button=0, probed_seat=0).model_dump(),
        HandPlan(hand_ordinal=3, button=1, probed_seat=1).model_dump(),
    ]
    fields["fragments"] = [{"start_ordinal": 1, "end_ordinal": 1}]
    fields["weights"] = [{"numerator": 1, "denominator": 1}]
    with pytest.raises((SpecIncompleteError, ValidationError)):
        DomainRunSpec.model_validate(fields)


def test_domain_lock_versions_reject_anything_but_one() -> None:
    payload = campaign_configuration_payload(
        num_players=2,
        starting_stack=200,
        small_blind=1,
        big_blind=2,
        baseline_identifier="heuristic@1",
        under_test_identifier="mixed-local@9",
        lock_versions=fixture_lock_versions(),
    )
    versions = payload["lock_versions"]
    assert isinstance(versions, dict)
    for name in (
        "domain_ab_node_registry",
        "domain_ab_bucket_registry",
        "domain_ab_layer_partition",
        "domain_ab_layer_weights",
        "domain_ab_block_template",
        "domain_ab_support_bounds",
    ):
        assert versions[name] == 1
    raw = fixture_lock_versions().model_dump()
    raw["domain_ab_support_bounds"] = 2
    with pytest.raises(SpecIncompleteError):
        CampaignLockVersions.model_validate(raw)


def test_pairing_transcript_checks_deal_reset_and_bound() -> None:
    deal = ("As", "Kh", "Qd", "Jc")
    measured = ArmTerminal(
        opening_stacks=(200, 200),
        terminal_stacks=(199, 201),
        deal_cards=deal,
    )
    baseline = ArmTerminal(
        opening_stacks=(200, 200),
        terminal_stacks=(201, 199),
        deal_cards=deal,
    )
    difference = require_pairing_transcript(
        PairingTranscript(
            num_players=2,
            starting_stack=200,
            probed_seat=0,
            measured=measured,
            baseline=baseline,
        )
    )
    assert difference == (199 - 200) - (201 - 200)

    broken = baseline.model_copy(update={"deal_cards": ("2c", "3d", "4h", "5s")})
    with pytest.raises(VerificationError, match="发牌"):
        require_pairing_transcript(
            PairingTranscript(
                num_players=2,
                starting_stack=200,
                probed_seat=0,
                measured=measured,
                baseline=broken,
            )
        )

    leaked = measured.model_copy(update={"terminal_stacks": (198, 201)})
    with pytest.raises(VerificationError, match="守恒"):
        require_pairing_transcript(
            PairingTranscript(
                num_players=2,
                starting_stack=200,
                probed_seat=0,
                measured=leaked,
                baseline=baseline,
            )
        )
