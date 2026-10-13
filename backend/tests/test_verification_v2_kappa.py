"""v2 已提交记录的校验。摘要来自夹具配置，不是战役身份。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.verification import (
    BASELINE_IDENTIFIER,
    UNDER_TEST_IDENTIFIER,
    DomainRunSpec,
    ExecutionIdentityRecord,
    FreezeBindingError,
    IdentityMappingError,
    InjectionPrecheckError,
    MaterialBindingError,
    MaterialEntry,
    MaterialManifest,
    ProtocolSpecError,
    RandomizationProtocolSpec,
    ReadRecord,
    SpecIncompleteError,
    build_domain_run_spec,
    build_kappa_decision_plan,
    campaign_configuration_digest,
    content_digest,
    protocol_digest,
    protocol_payload,
    randomization_protocol_v2_payload,
    require_verification_sources_non_executable,
    verify_frozen_inputs,
    verify_v2_frozen_records,
)
from app.verification.protocol import TranscriptCommitment

from .verification_helpers import (
    build_v2_frozen_fixture,
    fixture_campaign,
    fixture_lock_versions,
    fixture_projection_hex,
    v2_fixture_campaign,
    v2_protocol_spec,
    v2_run_spec,
)


def _digest(version: int) -> str:
    """夹具配置在指定协议版本下的摘要。"""
    return campaign_configuration_digest(
        num_players=2,
        starting_stack=200,
        small_blind=1,
        big_blind=2,
        baseline_identifier=BASELINE_IDENTIFIER,
        under_test_identifier=UNDER_TEST_IDENTIFIER,
        lock_versions=fixture_lock_versions(),
        randomization_protocol=version,
    )


def _records(
    campaign: str,
) -> tuple[
    list[tuple[str, tuple[str, ...]]],
    MaterialManifest,
    tuple[ReadRecord, ...],
    bytes,
]:
    deal = ("deal", (campaign, "0", "1", "0"))
    probed = ("arm_b", (campaign, "0", "1", "1", "0", fixture_projection_hex()))
    entries = [probed, deal]
    chunks = [b"\x00", (4).to_bytes(32, "big")]
    reads = (
        ReadRecord(
            read_index=0,
            purpose_label="deal",
            index_key=deal[1],
            bit_width=8,
            raw_offset=0,
            raw_value=0,
            accepted=True,
            output=0,
        ),
        ReadRecord(
            read_index=1,
            purpose_label="arm_b",
            index_key=probed[1],
            bit_width=256,
            raw_offset=1,
            raw_value=4,
            accepted=True,
            output=4,
        ),
    )
    manifest = MaterialManifest(
        entries=(
            MaterialEntry(purpose_label="deal", index_key=deal[1], value=0),
            MaterialEntry(purpose_label="arm_b", index_key=probed[1], value=4),
        )
    )
    return entries, manifest, reads, b"".join(chunks)


def test_v1_digest_is_unchanged_and_differs_from_v2() -> None:
    assert _digest(1) == fixture_campaign(num_players=2)
    assert _digest(2) != _digest(1)


def test_submitted_v2_records_bind_to_protocol_version_two() -> None:
    campaign = _digest(2)
    entries, manifest, reads, transcript = _records(campaign)
    verify_v2_frozen_records(
        entries,
        manifest,
        reads,
        transcript,
        probed_by_hand={1: 1},
        num_players=2,
        starting_stack=200,
        small_blind=1,
        big_blind=2,
        baseline_identifier=BASELINE_IDENTIFIER,
        under_test_identifier=UNDER_TEST_IDENTIFIER,
        lock_versions=fixture_lock_versions(),
    )


def test_version_one_digest_cannot_label_v2_keys() -> None:
    entries, manifest, reads, transcript = _records(_digest(1))
    with pytest.raises(ProtocolSpecError):
        verify_v2_frozen_records(
            entries,
            manifest,
            reads,
            transcript,
            probed_by_hand={1: 1},
            num_players=2,
            starting_stack=200,
            small_blind=1,
            big_blind=2,
            baseline_identifier=BASELINE_IDENTIFIER,
            under_test_identifier=UNDER_TEST_IDENTIFIER,
            lock_versions=fixture_lock_versions(),
        )


def test_manifest_order_and_seed_domain_are_checked() -> None:
    campaign = _digest(2)
    entries, manifest, reads, transcript = _records(campaign)
    reversed_manifest = MaterialManifest(entries=tuple(reversed(manifest.entries)))
    with pytest.raises(MaterialBindingError):
        verify_v2_frozen_records(
            entries,
            reversed_manifest,
            reads,
            transcript,
            probed_by_hand={1: 1},
            num_players=2,
            starting_stack=200,
            small_blind=1,
            big_blind=2,
            baseline_identifier=BASELINE_IDENTIFIER,
            under_test_identifier=UNDER_TEST_IDENTIFIER,
            lock_versions=fixture_lock_versions(),
        )


def test_protocol_v2_keeps_rejection_id_and_commitment_fields() -> None:
    payload = randomization_protocol_v2_payload()
    assert payload["schema"] == "randomization-protocol-v2"
    assert payload["rejection_rule"] == "rejection-whole-multiple-truncation-v1"
    assert payload["traversal_order"] == ["deal", "non_probed", "arm_m", "arm_b"]
    assert payload["commitment_fields"] == list(TranscriptCommitment.model_fields)
    purposes = {row["label"]: row for row in payload["purposes"]}  # type: ignore[index,union-attr]
    assert purposes["non_probed"]["index_fields"][-2:] == ["event_index", "sigma_public"]
    assert purposes["arm_b"]["index_fields"][-2:] == ["event_index", "sigma_public"]
    assert purposes["deal"]["index_fields"] == ["campaign", "block", "hand", "draw"]
    assert purposes["arm_m"]["index_fields"] == ["campaign", "block", "hand"]


def test_kappa_plan_records_defaults_without_constructing_strategy() -> None:
    plan = build_kappa_decision_plan("arm_b", ("ab" * 32, "0", "1", "1", "0", "cd"), 7)
    assert plan.identifier == "heuristic@1"
    assert plan.interface == "registry-seed"
    assert plan.samples == 500
    assert plan.bluff_freq == "0.10"
    assert plan.seed == 7
    with pytest.raises(IdentityMappingError):
        build_kappa_decision_plan("arm_b", plan.index_key, True)  # type: ignore[arg-type]


def test_real_v2_protocol_digest_carries_schema() -> None:
    spec = v2_run_spec()
    payload = protocol_payload(spec.protocol)
    assert spec.protocol.protocol_schema == "randomization-protocol-v2"
    assert payload["schema"] == "randomization-protocol-v2"
    assert protocol_digest(spec.protocol) == content_digest(payload, algorithm="sha256")
    assert payload["source_interface_id"] == "python-os-urandom@1"
    assert payload["environment_record"] == "local-single-process-no-parallel@1"


def test_v1_schema_rejects_v2_key_shape() -> None:
    fields = v2_protocol_spec().model_dump()
    fields["protocol_schema"] = "randomization-protocol-v1"
    with pytest.raises(ProtocolSpecError):
        RandomizationProtocolSpec.model_validate(fields)


def test_v2_spec_campaign_matches_protocol_version_two() -> None:
    spec = v2_run_spec()
    DomainRunSpec.model_validate(spec.model_dump())
    assert spec.campaign == v2_fixture_campaign(spec)
    assert spec.campaign != fixture_campaign(num_players=spec.num_players)
    fields = spec.model_dump()
    fields["campaign"] = fixture_campaign(num_players=spec.num_players)
    with pytest.raises(SpecIncompleteError, match="不一致"):
        DomainRunSpec.model_validate(fields)


def test_direct_v2_construction_uses_protocol_version_two() -> None:
    sample = v2_run_spec()
    built = build_domain_run_spec(
        num_players=sample.num_players,
        starting_stack=sample.starting_stack,
        small_blind=sample.small_blind,
        big_blind=sample.big_blind,
        engine_seed=sample.engine_seed,
        baseline_identifier=sample.baseline_identifier,
        under_test_identifier=sample.under_test_identifier,
        deal=sample.deal,
        protocol=sample.protocol,
        schedule=sample.schedule,
        block=sample.block,
        campaign_configuration=sample.campaign_configuration,
    )
    assert built.campaign == sample.campaign


def _verify_v2_chain(
    fixture,
    rows: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    identity: ExecutionIdentityRecord | None = None,
) -> None:
    manifests = fixture.source_manifests
    verify_frozen_inputs(
        manifest=fixture.manifest,
        spec=fixture.spec,
        caliber=fixture.caliber,
        bundle=fixture.bundle,
        audit=fixture.audit,
        execution_identity=fixture.identity if identity is None else identity,
        material_manifest=fixture.material_manifest,
        runner_manifest=manifests.runner,
        generator_manifest=manifests.generator,
        engine_manifest=manifests.engine,
        baseline_strategy_manifest=manifests.baseline_strategy,
        under_test_strategy_manifest=manifests.under_test_strategy,
        verification_manifest=manifests.verification,
        closed_entries=rows,
    )


def _identity_value(identity: ExecutionIdentityRecord, category: str, name: str) -> str:
    for entry in identity.entries_for(category):
        if entry.name == name:
            return entry.value
    raise AssertionError(name)


def _rewrite_identity(
    identity: ExecutionIdentityRecord,
    name: str,
    value: str | None = None,
    *,
    drop: bool = False,
) -> ExecutionIdentityRecord:
    """绕过记录构造期校验，只改或删一条，用来测冻结主链。"""
    categories = []
    for category, entries in identity.categories:
        updated = []
        for entry in entries:
            if entry.name != name:
                updated.append(entry)
            elif not drop:
                updated.append(entry.model_copy(update={"value": value}))
        categories.append((category, tuple(updated)))
    return identity.model_copy(update={"categories": tuple(categories)})


def test_v2_frozen_main_chain_binds_protocol_version_two() -> None:
    fixture, rows = build_v2_frozen_fixture()
    _verify_v2_chain(fixture, rows)
    campaign = fixture.spec.campaign
    assert campaign == v2_fixture_campaign(fixture.spec)
    assert campaign != fixture_campaign(num_players=fixture.spec.num_players)
    assert _identity_value(fixture.identity, "input-mapping", "campaign-configuration-digest") == (
        campaign
    )
    assert _identity_value(
        fixture.identity, "randomization-protocol", "randomization-protocol-schema"
    ) == "randomization-protocol-v2"
    assert all(key[0] == campaign for _label, key in rows)


def test_v2_frozen_main_chain_rejects_version_one_campaign_digest() -> None:
    fixture, rows = build_v2_frozen_fixture()
    version_one = fixture_campaign(num_players=fixture.spec.num_players)
    assert version_one != fixture.spec.campaign
    identity = _rewrite_identity(fixture.identity, "campaign-configuration-digest", version_one)
    with pytest.raises(IdentityMappingError, match="campaign-configuration-digest"):
        _verify_v2_chain(fixture, rows, identity=identity)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("randomization-protocol-schema", "randomization-protocol-v1"),
        ("closed-keyset-digest", "ab" * 32),
        ("kappa-key-rules-digest", "cd" * 32),
    ],
)
def test_v2_frozen_main_chain_rejects_tampered_binding(name: str, value: str) -> None:
    fixture, rows = build_v2_frozen_fixture()
    identity = _rewrite_identity(fixture.identity, name, value)
    with pytest.raises(IdentityMappingError, match=name):
        _verify_v2_chain(fixture, rows, identity=identity)


@pytest.mark.parametrize(
    "name",
    [
        "randomization-protocol-schema",
        "closed-keyset-digest",
        "kappa-key-rules-digest",
    ],
)
def test_v2_frozen_main_chain_rejects_missing_binding(name: str) -> None:
    fixture, rows = build_v2_frozen_fixture()
    identity = _rewrite_identity(fixture.identity, name, drop=True)
    with pytest.raises(IdentityMappingError, match=name):
        _verify_v2_chain(fixture, rows, identity=identity)


def test_frozen_main_chain_rejects_missing_closed_set() -> None:
    from .test_verification_runner import FIXTURE, _verify_fixture

    spec = FIXTURE.spec.model_copy(update={"protocol": v2_protocol_spec()})
    with pytest.raises(FreezeBindingError, match="闭合集"):
        _verify_fixture(FIXTURE, spec=spec)


def test_verification_package_does_not_import_execution_paths() -> None:
    root = Path(__file__).resolve().parents[1] / "app" / "verification"
    modules: list[str] = []
    calls: list[str] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    calls.append(func.id)
                elif isinstance(func, ast.Attribute):
                    calls.append(func.attr)
    require_verification_sources_non_executable(imported_modules=modules, called_names=calls)
    with pytest.raises(InjectionPrecheckError):
        require_verification_sources_non_executable(
            imported_modules=["app.poker.engine"],
            called_names=[],
        )
