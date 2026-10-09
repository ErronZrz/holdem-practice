"""第一层锁定口径的夹具回归。

只使用手造规格与非实际材料。不生成实际配置摘要、源码清单或代码身份，
也不把通过这些断言当作质量结论。
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.verification import (
    BASELINE_IDENTIFIER,
    UNDER_TEST_IDENTIFIER,
    CampaignConfiguration,
    DealMappingSpec,
    DealMaterialError,
    DomainRunSpec,
    IdentityMappingError,
    MaterialKeyError,
    ProtocolAuditError,
    SpecIncompleteError,
    TranscriptCommitment,
    build_domain_run_spec,
    build_execution_identity_record,
    campaign_configuration_digest,
    deal_for_hand,
    encode_baseline_entry_payload,
    material_key_from_integer,
    require_explicit_seed,
)
from app.verification.deal import _require_player_count
from app.verification.execution_identity import _CLOSED_ENTRIES
from app.verification.instantiation import (
    _constant_payload,
    _require_bluff_freq,
    _require_expected_defaults,
)

from .verification_helpers import (
    DECK_ORDER,
    fixture_lock_versions,
    identity_categories,
    protocol_spec,
    run_spec,
)


def test_player_count_accepts_bounds_and_rejects_bool_and_overflow() -> None:
    _require_player_count(2)
    _require_player_count(23)
    deal = DealMappingSpec(deck_order=DECK_ORDER)
    assert deal.draw_count(23) == 51
    with pytest.raises(DealMaterialError):
        _require_player_count(True)
    with pytest.raises(DealMaterialError):
        _require_player_count(1)
    with pytest.raises(DealMaterialError):
        deal.draw_count(24)
    with pytest.raises(SpecIncompleteError):
        run_spec(num_players=24)


def test_campaign_must_match_component_digest_and_rejects_model_bypass() -> None:
    spec = run_spec()
    assert spec.campaign == campaign_configuration_digest(
        num_players=spec.num_players,
        starting_stack=spec.starting_stack,
        small_blind=spec.small_blind,
        big_blind=spec.big_blind,
        baseline_identifier=spec.baseline_identifier,
        under_test_identifier=spec.under_test_identifier,
        lock_versions=spec.campaign_configuration.lock_versions,
    )
    fields = spec.model_dump()
    fields["campaign"] = "ab" * 32
    with pytest.raises(SpecIncompleteError, match="不一致"):
        DomainRunSpec.model_validate(fields)
    with pytest.raises(ValidationError):
        DomainRunSpec.model_validate({"num_players": 2})
    with pytest.raises(SpecIncompleteError):
        campaign_configuration_digest(
            num_players=2,
            starting_stack=200,
            small_blind=1,
            big_blind=2,
            baseline_identifier=BASELINE_IDENTIFIER,
            under_test_identifier="absent@1",
            lock_versions=fixture_lock_versions(),
        )


def test_direct_spec_construction_uses_the_same_digest() -> None:
    built = build_domain_run_spec(
        num_players=2,
        starting_stack=200,
        small_blind=1,
        big_blind=2,
        engine_seed=1,
        baseline_identifier=BASELINE_IDENTIFIER,
        under_test_identifier=UNDER_TEST_IDENTIFIER,
        deal=DealMappingSpec(deck_order=DECK_ORDER),
        protocol=protocol_spec(),
        schedule=run_spec(num_players=2).schedule,
        block=0,
        campaign_configuration=CampaignConfiguration(lock_versions=fixture_lock_versions()),
    )
    assert built.block == 0
    assert built.campaign == run_spec(num_players=2).campaign


def test_seed_and_material_key_reject_bool_and_upper_bound() -> None:
    assert require_explicit_seed(0) == 0
    assert require_explicit_seed((1 << 256) - 1) == (1 << 256) - 1
    with pytest.raises(IdentityMappingError):
        require_explicit_seed(None)
    with pytest.raises(IdentityMappingError):
        require_explicit_seed(True)
    with pytest.raises(IdentityMappingError):
        require_explicit_seed(-1)
    with pytest.raises(IdentityMappingError):
        require_explicit_seed(1 << 256)
    encoded = material_key_from_integer(0x0102)
    assert len(encoded) == 32
    assert encoded == (0x0102).to_bytes(32, "big")
    with pytest.raises(MaterialKeyError):
        material_key_from_integer(True)
    with pytest.raises(MaterialKeyError):
        material_key_from_integer(1 << 256)


def test_generation_timestamps_reject_offsets_and_reversed_order() -> None:
    fields = {
        "source_interface_id": "python-os-urandom@1",
        "environment_record": "local-single-process-no-parallel@1",
        "generation_started_at": "2026-09-29T00:00:00.000000Z",
        "generation_finished_at": "2026-09-29T00:00:01.000000Z",
        "traversal_order": ("deal",),
        "entry_counts": (),
        "rejection_counts": (),
        "transcript_digest": "ab" * 32,
        "read_record_digest": "ab" * 32,
        "manifest_digest": "ab" * 32,
        "generator_code_digest": "ab" * 32,
        "digest_algorithm": "sha256",
        "read_record_encoding": "compact-json-v1",
        "audit_format_version": 1,
    }
    TranscriptCommitment.model_validate(fields)
    for started, finished in (
        ("2026-09-29T00:00:00+00:00", "2026-09-29T00:00:01.000000Z"),
        ("2026-09-29T00:00:00.00000Z", "2026-09-29T00:00:01.000000Z"),
        ("2026-02-31T00:00:00.000000Z", "2026-03-01T00:00:00.000000Z"),
        ("2026-09-29T00:00:02.000000Z", "2026-09-29T00:00:01.000000Z"),
    ):
        fields["generation_started_at"] = started
        fields["generation_finished_at"] = finished
        with pytest.raises(ProtocolAuditError):
            TranscriptCommitment.model_validate(fields)


def test_closed_categories_contain_forty_one_entries() -> None:
    assert sum(len(names) for names in _CLOSED_ENTRIES.values()) == 41
    record = build_execution_identity_record(identity_categories())
    assert [name for name, _ in record.categories] == list(_CLOSED_ENTRIES)
    assert sum(len(entries) for _, entries in record.categories) == 41


def test_bluff_freq_encoding_rejects_other_numeric_forms() -> None:
    class FloatChild(float):
        pass

    payload = {
        "positional_defaults": {"bluff_freq": 0.1, "samples": 500, "seed": None},
        "code": {"constants": [None, "name"]},
    }
    encoded = encode_baseline_entry_payload(payload)
    assert b'"bluff_freq":0.1' in encoded
    assert b"0.10" not in encoded
    _require_bluff_freq(0.1)
    for value in (
        FloatChild(0.1),
        Decimal("0.1"),
        1,
        True,
        math.copysign(0.0, -1.0),
        math.nan,
        math.inf,
        0.2,
    ):
        with pytest.raises(IdentityMappingError):
            encode_baseline_entry_payload({"positional_defaults": {"bluff_freq": value}})
    for value in (1.5, 1 + 2j, ..., frozenset({1})):
        with pytest.raises(IdentityMappingError):
            _constant_payload(value)


def test_baseline_defaults_reject_extra_or_wrong_values() -> None:
    """多出的默认参数、改掉的种子或采样数都不能再生成这一版入口载荷。"""
    closed = {"seed": None, "samples": 500, "bluff_freq": 0.1}
    _require_expected_defaults(closed)
    for defaults in (
        {**closed, "extra": 1},
        {"seed": 0, "samples": 500, "bluff_freq": 0.1},
        {"seed": None, "samples": 100, "bluff_freq": 0.1},
        {"seed": None, "samples": True, "bluff_freq": 0.1},
        {"samples": 500, "bluff_freq": 0.1},
    ):
        with pytest.raises(IdentityMappingError):
            _require_expected_defaults(defaults)
    for positional_defaults in (
        {**closed, "extra": 0},
        {"seed": None, "samples": 1, "bluff_freq": 0.1},
        {"seed": 1, "samples": 500, "bluff_freq": 0.1},
    ):
        with pytest.raises(IdentityMappingError):
            encode_baseline_entry_payload({"positional_defaults": positional_defaults})


def test_deal_for_hand_still_rejects_short_draw_lists() -> None:
    with pytest.raises(DealMaterialError):
        deal_for_hand(
            DealMappingSpec(deck_order=DECK_ORDER), num_players=2, steps=(0,) * 8
        )
