"""版本 3 的主值派生、决策记录与清单路径。夹具字节不是实际材料。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.verification.config import campaign_configuration_digest
from app.verification.errors import (
    IdentityMappingError,
    MaterialBindingError,
    ProtocolSpecError,
    SourceManifestError,
    SpecIncompleteError,
)
from app.verification.execution_identity import (
    SEED_SENTENCE_V1,
    SEED_SENTENCE_V2,
    SEED_SENTENCE_V3,
    ExecutionIdentityRecord,
)
from app.verification.instantiation import (
    materials_digest,
    plan_payload,
    require_instantiation_caliber,
)
from app.verification.kappa_derive import derive_kappa_seed, require_derived_decision_records
from app.verification.materials import (
    HandMaterials,
    MaterialEntry,
    MaterialManifest,
    manifest_digest,
    require_supplied_materials_order,
)
from app.verification.protocol import AuditedMaterials, verify_manifest_binding
from app.verification.runner import verify_frozen_inputs
from app.verification.source_manifest import require_v3_manifest_files
from tests.verification_helpers import (
    build_fixture,
    build_v2_frozen_fixture,
    build_v3_frozen_fixture,
    conflicting_baseline_caliber,
    construction_caliber,
    hand_source_manifest,
    v2_protocol_spec,
    v2_run_spec,
    v3_run_spec,
)
from tools.kappa_keyset import closed_keyset_from_entries
from tools.material_generator import generate_v3_fixture, generate_v3_materials


def _v3_spec():
    return v3_run_spec()


def _closed(spec):
    campaign = spec.campaign
    block = str(spec.block)
    rows = []
    draws = spec.deal.draw_count(spec.num_players)
    for plan in spec.schedule:
        hand = str(plan.hand_ordinal)
        for draw in range(draws):
            rows.append(("deal", (campaign, block, hand, str(draw))))
        rows.append(("arm_m", (campaign, block, hand)))
    return closed_keyset_from_entries(rows, version=3)


def _manifest(entrypoint: str, extra: tuple[str, ...] = ()):
    base = hand_source_manifest(entrypoint)
    files = list(base["files"])
    digest = files[0]["sha256"]
    for path in extra:
        files.append({"path": path, "sha256": digest})
    files.sort(key=lambda row: row["path"])
    base["files"] = files
    return base


def test_actual_path_rejects_injected_master() -> None:
    with pytest.raises(ProtocolSpecError, match="不得传入主值"):
        generate_v3_materials(None, None, None, injected_master=b"\x00" * 32)


def test_fixture_generation_keeps_baseline_counts_at_zero() -> None:
    spec = _v3_spec()
    draws = spec.deal.draw_count(spec.num_players)
    generated = generate_v3_fixture(
        _closed(spec),
        spec,
        hand_source_manifest("backend/tools/material_generator.py"),
        master=b"\x02" * 32,
        entropy=b"\x00" * (draws + 32),
    )
    counts = dict(generated.audit.commitment.entry_counts)
    rejections = dict(generated.audit.commitment.rejection_counts)
    assert counts["master"] == 1
    assert counts["non_probed"] == 0
    assert counts["arm_b"] == 0
    assert rejections["non_probed"] == 0
    assert rejections["arm_b"] == 0
    assert generated.audit.reads[0].purpose_label == "master"
    assert generated.audit.reads[0].read_index == 0
    labels = {entry.purpose_label for entry in generated.material_manifest.entries}
    assert "non_probed" not in labels
    assert "arm_b" not in labels
    plan = plan_payload(
        spec=spec,
        caliber=construction_caliber(),
        bundle=generated.bundle,
    )
    assert plan["schema"] == "construction-plan-v3"
    assert set(plan) == {
        "schema",
        "protocol_schema",
        "master_read_index",
        "derivation_algorithm",
    }


def test_version_payloads_do_not_reuse_each_other() -> None:
    spec = _v3_spec()
    draws = spec.deal.draw_count(spec.num_players)
    generated = generate_v3_fixture(
        _closed(spec),
        spec,
        hand_source_manifest("backend/tools/material_generator.py"),
        master=b"\x03" * 32,
        entropy=b"\x00" * (draws + 32),
    )
    version_three = plan_payload(
        spec=spec, caliber=construction_caliber(), bundle=generated.bundle
    )
    assert version_three["schema"] != "construction-plan-v2"
    assert v2_protocol_spec().protocol_schema == "randomization-protocol-v2"


def test_same_key_matches_and_distinct_projection_differs() -> None:
    master = b"\x11" * 32
    campaign = "ab" * 32
    left = (campaign, "0", "1", "0", "0", "ab")
    right = (campaign, "0", "1", "0", "0", "ac")
    assert derive_kappa_seed(master, "non_probed", left) == derive_kappa_seed(
        master, "non_probed", left
    )
    assert derive_kappa_seed(master, "non_probed", left) != derive_kappa_seed(
        master, "arm_b", left
    )
    assert derive_kappa_seed(master, "non_probed", left) != derive_kappa_seed(
        master, "non_probed", right
    )


def _record(purpose: str, key: tuple[str, ...], spec, master: bytes):
    return {
        "purpose_label": purpose,
        "index_key": key,
        "value": derive_kappa_seed(master, purpose, key),
    }


def test_decision_record_accepts_a_legal_key_and_rejects_bad_ones() -> None:
    spec = _v3_spec()
    master = b"\x04" * 32
    key = (spec.campaign, "0", "1", "0", "0", "ab")
    probed = {1: 1}
    require_derived_decision_records(
        [_record("non_probed", key, spec, master)],
        master=master,
        campaign=spec.campaign,
        block=0,
        num_players=2,
        probed_by_hand=probed,
    )
    bad_seat = (spec.campaign, "0", "1", "9", "0", "ab")
    wrong_arm = (spec.campaign, "0", "1", "0", "0", "ab")
    bad_sigma = (spec.campaign, "0", "1", "0", "0", "AB")
    other = campaign_configuration_digest(
        num_players=spec.num_players,
        starting_stack=spec.starting_stack,
        small_blind=spec.small_blind,
        big_blind=spec.big_blind,
        baseline_identifier=spec.baseline_identifier,
        under_test_identifier=spec.under_test_identifier,
        lock_versions=spec.campaign_configuration.lock_versions,
        randomization_protocol=1,
    )
    old_campaign = (other, "0", "1", "0", "0", "ab")
    cases = [
        _record("non_probed", bad_seat, spec, master),
        {
            "purpose_label": "arm_b",
            "index_key": wrong_arm,
            "value": derive_kappa_seed(master, "arm_b", wrong_arm),
        },
        _record("non_probed", bad_sigma, spec, master),
        _record("non_probed", old_campaign, spec, master),
    ]
    for record in cases:
        with pytest.raises(ProtocolSpecError):
            require_derived_decision_records(
                [record],
                master=master,
                campaign=spec.campaign,
                block=0,
                num_players=2,
                probed_by_hand=probed,
            )
    duplicate = _record("non_probed", key, spec, master)
    with pytest.raises(ProtocolSpecError, match="重复"):
        require_derived_decision_records(
            [duplicate, duplicate],
            master=master,
            campaign=spec.campaign,
            block=0,
            num_players=2,
            probed_by_hand=probed,
        )
    mismatched = dict(duplicate)
    mismatched["value"] = 1
    with pytest.raises(ProtocolSpecError, match="不符"):
        require_derived_decision_records(
            [mismatched],
            master=master,
            campaign=spec.campaign,
            block=0,
            num_players=2,
            probed_by_hand=probed,
        )


def test_manifest_files_must_name_derive_projection_and_orchestrator() -> None:
    derive = "backend/app/verification/kappa_derive.py"
    projection = "backend/app/poker/k2_public_projection.py"
    orchestrator = "backend/tools/kappa_orchestrator.py"
    generator = _manifest("backend/tools/material_generator.py", (derive,))
    verification = _manifest("backend/fixtures/verification.py", (derive,))
    engine = _manifest(projection, (orchestrator,))
    require_v3_manifest_files(generator, engine, verification)
    missing = _manifest("backend/tools/material_generator.py")
    with pytest.raises(SourceManifestError):
        require_v3_manifest_files(missing, engine, verification)
    entered = _manifest(projection, (orchestrator,))
    entered["entrypoints"] = sorted([projection, orchestrator])
    with pytest.raises(SourceManifestError):
        require_v3_manifest_files(generator, entered, verification)


def test_derive_module_does_not_import_execution_boundaries() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "app" / "verification" / "kappa_derive.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    assert "os" not in modules
    blocked = ("engine", "orchestr", "generator")
    assert not any(any(part in name for part in blocked) for name in modules)


def test_orchestrator_uses_master_instead_of_the_table(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util
    import sys

    from app.poker.actions import Action, ActionType
    from app.poker.cards import card_from_str
    from app.poker.engine import PokerEngine
    from app.strategy.registry import create_strategy

    path = Path(__file__).resolve().parents[1] / "tools" / "kappa_orchestrator.py"
    spec_loader = importlib.util.spec_from_file_location("kappa_orchestrator_v3", path)
    assert spec_loader is not None and spec_loader.loader is not None
    module = importlib.util.module_from_spec(spec_loader)
    sys.modules[spec_loader.name] = module
    spec_loader.loader.exec_module(module)
    calls: list[int | None] = []

    def spy(value: str, seed: int | None = None):
        calls.append(seed)
        return create_strategy(value, seed)

    monkeypatch.setattr(module, "create_strategy", spy)
    engine = PokerEngine(2, small_blind=1, big_blind=2, starting_stack=200, seed=1)
    engine.start_hand_with(
        button=0,
        hole_cards={
            0: [card_from_str("7c"), card_from_str("2d")],
            1: [card_from_str("As"), card_from_str("Ah")],
        },
        board=[
            card_from_str("2c"),
            card_from_str("3d"),
            card_from_str("4h"),
            card_from_str("5s"),
            card_from_str("9c"),
        ],
    )
    state = engine.snapshot()
    legal = engine.legal_actions()
    sigma = module.sigma_public_hex(state, legal)
    campaign = "cd" * 32
    master = b"\x07" * 32
    table = module.material_table_from_rows(())
    module.play_hand(
        engine,
        table,
        campaign=campaign,
        block=0,
        hand_ordinal=1,
        probed_seat=1,
        arm="baseline",
        master=master,
        under_test_choose=lambda _state, _legal, _seed: Action(ActionType.FOLD),
    )
    expected = derive_kappa_seed(
        master, "non_probed", (campaign, "0", "1", "0", "0", sigma)
    )
    assert calls[0] == expected


_OLD_SETTLED = "settled:v1-per-hand-arm_b-material/v2-per-kappa-arm_b-material"
_DERIVE_PATH = "backend/app/verification/kappa_derive.py"
_PROJECTION_PATH = "backend/app/poker/k2_public_projection.py"
_ORCHESTRATOR_PATH = "backend/tools/kappa_orchestrator.py"


def _verify_chain(
    fixture,
    rows=None,
    *,
    identity=None,
    caliber=None,
    bundle=None,
    audit=None,
    material_manifest=None,
    generator_manifest=None,
    engine_manifest=None,
    verification_manifest=None,
):
    manifests = fixture.source_manifests
    verify_frozen_inputs(
        manifest=fixture.manifest,
        spec=fixture.spec,
        caliber=fixture.caliber if caliber is None else caliber,
        bundle=fixture.bundle if bundle is None else bundle,
        audit=fixture.audit if audit is None else audit,
        execution_identity=fixture.identity if identity is None else identity,
        material_manifest=(
            fixture.material_manifest if material_manifest is None else material_manifest
        ),
        runner_manifest=manifests.runner,
        generator_manifest=(
            manifests.generator if generator_manifest is None else generator_manifest
        ),
        engine_manifest=manifests.engine if engine_manifest is None else engine_manifest,
        baseline_strategy_manifest=manifests.baseline_strategy,
        under_test_strategy_manifest=manifests.under_test_strategy,
        verification_manifest=(
            manifests.verification if verification_manifest is None else verification_manifest
        ),
        closed_entries=rows,
    )


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


def _identity_value(identity: ExecutionIdentityRecord, category: str, name: str) -> str:
    for entry in identity.entries_for(category):
        if entry.name == name:
            return entry.value
    raise AssertionError(name)


def _configuration_digest(spec, version: int) -> str:
    return campaign_configuration_digest(
        num_players=spec.num_players,
        starting_stack=spec.starting_stack,
        small_blind=spec.small_blind,
        big_blind=spec.big_blind,
        baseline_identifier=spec.baseline_identifier,
        under_test_identifier=spec.under_test_identifier,
        lock_versions=spec.campaign_configuration.lock_versions,
        randomization_protocol=version,
    )


def test_v3_frozen_main_chain_accepts_a_consistent_fixture() -> None:
    fixture, rows = build_v3_frozen_fixture()
    _verify_chain(fixture, rows)
    require_instantiation_caliber(
        fixture.identity,
        spec=fixture.spec,
        caliber=fixture.caliber,
        bundle=fixture.bundle,
        algorithm=fixture.spec.protocol.digest_algorithm,
        closed_entries=rows,
    )
    assert _identity_value(
        fixture.identity, "randomization-protocol", "randomization-protocol-version"
    ) == "3"
    assert _identity_value(
        fixture.identity, "randomization-protocol", "randomization-protocol-schema"
    ) == "randomization-protocol-v3"
    assert _identity_value(
        fixture.identity, "instantiation-caliber", "baseline-effective-seed"
    ) == SEED_SENTENCE_V3


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("randomization-protocol-version", "1"),
        ("randomization-protocol-version", "2"),
        ("randomization-protocol-schema", "randomization-protocol-v1"),
        ("randomization-protocol-schema", "randomization-protocol-v2"),
        ("kappa-key-rules-digest", "cd" * 32),
        ("closed-keyset-digest", "ab" * 32),
    ],
)
def test_v3_frozen_main_chain_rejects_tampered_binding(name: str, value: str) -> None:
    fixture, rows = build_v3_frozen_fixture()
    identity = _rewrite_identity(fixture.identity, name, value)
    with pytest.raises(IdentityMappingError, match=name):
        _verify_chain(fixture, rows, identity=identity)


@pytest.mark.parametrize(
    "name",
    [
        "randomization-protocol-version",
        "randomization-protocol-schema",
        "kappa-key-rules-digest",
        "closed-keyset-digest",
    ],
)
def test_v3_frozen_main_chain_rejects_missing_binding(name: str) -> None:
    fixture, rows = build_v3_frozen_fixture()
    identity = _rewrite_identity(fixture.identity, name, drop=True)
    with pytest.raises(IdentityMappingError, match=name):
        _verify_chain(fixture, rows, identity=identity)


@pytest.mark.parametrize("version", [1, 2])
def test_v3_frozen_main_chain_rejects_other_campaign_digests(version: int) -> None:
    fixture, rows = build_v3_frozen_fixture()
    foreign = _configuration_digest(fixture.spec, version)
    assert foreign != fixture.spec.campaign
    identity = _rewrite_identity(fixture.identity, "campaign-configuration-digest", foreign)
    with pytest.raises(IdentityMappingError, match="campaign-configuration-digest"):
        _verify_chain(fixture, rows, identity=identity)


def _chains():
    version_one = build_fixture()
    version_two, rows_two = build_v2_frozen_fixture()
    version_three, rows_three = build_v3_frozen_fixture()
    return (
        (version_one, None, SEED_SENTENCE_V1),
        (version_two, rows_two, SEED_SENTENCE_V2),
        (version_three, rows_three, SEED_SENTENCE_V3),
    )


@pytest.mark.parametrize("sentence", [SEED_SENTENCE_V1, SEED_SENTENCE_V2, SEED_SENTENCE_V3])
def test_seed_sentences_are_not_interchangeable(sentence: str) -> None:
    for fixture, rows, expected in _chains():
        if sentence == expected:
            continue
        identity = _rewrite_identity(fixture.identity, "baseline-effective-seed", sentence)
        with pytest.raises(IdentityMappingError, match="baseline-effective-seed"):
            _verify_chain(fixture, rows, identity=identity)


def test_old_settled_text_fails_on_every_protocol_version() -> None:
    for fixture, rows, _expected in _chains():
        identity = _rewrite_identity(fixture.identity, "arm-b-seed-scope-conflict", _OLD_SETTLED)
        with pytest.raises(IdentityMappingError, match="arm-b-seed-scope-conflict"):
            _verify_chain(fixture, rows, identity=identity)


def _without_file(manifest: dict[str, object], path: str) -> dict[str, object]:
    updated = dict(manifest)
    updated["files"] = [row for row in manifest["files"] if row["path"] != path]
    return updated


@pytest.mark.parametrize(
    "which",
    ["generator-derive", "verification-derive", "projection", "orchestrator", "entrypoint"],
)
def test_v3_frozen_main_chain_rejects_incomplete_manifests(which: str) -> None:
    fixture, rows = build_v3_frozen_fixture()
    manifests = fixture.source_manifests
    kwargs = {}
    if which == "generator-derive":
        kwargs["generator_manifest"] = _without_file(manifests.generator, _DERIVE_PATH)
    elif which == "verification-derive":
        kwargs["verification_manifest"] = _without_file(manifests.verification, _DERIVE_PATH)
    elif which == "projection":
        kwargs["engine_manifest"] = _without_file(manifests.engine, _PROJECTION_PATH)
    elif which == "orchestrator":
        kwargs["engine_manifest"] = _without_file(manifests.engine, _ORCHESTRATOR_PATH)
    else:
        engine = dict(manifests.engine)
        engine["entrypoints"] = sorted([*engine["entrypoints"], _ORCHESTRATOR_PATH])
        files = list(engine["files"])
        if _ORCHESTRATOR_PATH not in {row["path"] for row in files}:
            files.append({"path": _ORCHESTRATOR_PATH, "sha256": files[0]["sha256"]})
        engine["files"] = sorted(files, key=lambda row: row["path"])
        kwargs["engine_manifest"] = engine
    with pytest.raises(SourceManifestError):
        _verify_chain(fixture, rows, **kwargs)


def test_v3_frozen_main_chain_rejects_a_broken_baseline() -> None:
    fixture, rows = build_v3_frozen_fixture()
    with pytest.raises(IdentityMappingError):
        _verify_chain(fixture, rows, caliber=conflicting_baseline_caliber())


def _replace_purpose_campaign(fixture, purpose: str, campaign: str):
    def rewrite(label: str, key: tuple[str, ...]) -> tuple[str, ...]:
        if label != purpose:
            return key
        return (campaign, *key[1:])

    material_manifest = MaterialManifest(
        entries=tuple(
            MaterialEntry(
                purpose_label=entry.purpose_label,
                index_key=rewrite(entry.purpose_label, entry.index_key),
                value=entry.value,
            )
            for entry in fixture.material_manifest.entries
        )
    )
    reads = tuple(
        record.model_copy(
            update={"index_key": rewrite(record.purpose_label, record.index_key)}
        )
        for record in fixture.audit.reads
    )
    bundle = tuple(
        HandMaterials(
            hand_ordinal=hand.hand_ordinal,
            entries=tuple(
                MaterialEntry(
                    purpose_label=entry.purpose_label,
                    index_key=rewrite(entry.purpose_label, entry.index_key),
                    value=entry.value,
                )
                for entry in hand.entries
            ),
        )
        for hand in fixture.bundle
    )
    audit = AuditedMaterials(
        transcript=fixture.audit.transcript,
        reads=reads,
        commitment=fixture.audit.commitment,
    )
    return material_manifest, bundle, audit


@pytest.mark.parametrize("purpose", ["deal", "arm_m"])
@pytest.mark.parametrize("version", [1, 2])
def test_v3_retained_keys_reject_other_campaign_digests(purpose: str, version: int) -> None:
    fixture, rows = build_v3_frozen_fixture()
    foreign = _configuration_digest(fixture.spec, version)
    material_manifest, bundle, audit = _replace_purpose_campaign(fixture, purpose, foreign)
    with pytest.raises(ProtocolSpecError, match="campaign"):
        _verify_chain(
            fixture,
            rows,
            bundle=bundle,
            audit=audit,
            material_manifest=material_manifest,
        )


def test_v3_latch_failure_reads_no_entropy(monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.material_generator as module

    calls: list[int] = []

    def forbidden(size: int) -> bytes:
        calls.append(size)
        raise AssertionError(size)

    monkeypatch.setattr(module.os, "urandom", forbidden)
    spec = v3_run_spec()
    keyset = _closed(spec)
    manifest = hand_source_manifest("backend/tools/material_generator.py")
    bad_source = spec.protocol.model_copy(update={"source_interface_id": "other-source@1"})
    bad_environment = spec.protocol.model_copy(update={"environment_record": "other-env@1"})
    cases = (
        (keyset, spec.model_copy(update={"protocol": bad_source}), manifest),
        (keyset, spec.model_copy(update={"protocol": bad_environment}), manifest),
        (keyset, v2_run_spec(), manifest),
        (closed_keyset_from_entries((), version=3), spec, manifest),
        (keyset, spec, hand_source_manifest("backend/fixtures/other.py")),
    )
    for keyset_case, spec_case, manifest_case in cases:
        with pytest.raises(ProtocolSpecError):
            module.generate_v3_materials(keyset_case, spec_case, manifest_case)
    with pytest.raises(ProtocolSpecError):
        module.generate_v3_materials(keyset, spec, manifest, injected_master=b"\x00" * 32)
    assert calls == []


def test_v3_supplied_materials_digest_and_retained_manifest_consistency() -> None:
    """核验第三版送交材料四字段摘要、保留用途的手内排序，以及清单去掉主值后与手牌材料束逐项一致。"""
    fixture, rows = build_v3_frozen_fixture()
    spec = fixture.spec
    bundle = fixture.bundle
    manifest = fixture.material_manifest
    algorithm = spec.protocol.digest_algorithm

    expected_supplied_payload = {
        "schema": "supplied-materials-v3",
        "protocol_schema": "randomization-protocol-v3",
        "master_read_index": 0,
        "derivation_algorithm": "hmac-sha256-domain-separated-v1",
    }
    expected_plan_payload = plan_payload(
        spec=spec, caliber=fixture.caliber, bundle=bundle
    )
    assert expected_plan_payload["schema"] == "construction-plan-v3"
    from app.verification.digests import content_digest

    supplied_hash = materials_digest(
        bundle, spec=spec, algorithm=algorithm, closed_entries=rows
    )
    assert supplied_hash == content_digest(
        expected_supplied_payload, algorithm=algorithm
    )
    assert supplied_hash != content_digest(expected_plan_payload, algorithm=algorithm)
    assert supplied_hash != manifest_digest(manifest, algorithm=algorithm)

    require_supplied_materials_order(spec, bundle, closed_entries=rows)
    reversed_hand = HandMaterials(
        hand_ordinal=bundle[0].hand_ordinal,
        entries=tuple(reversed(bundle[0].entries)),
    )
    with pytest.raises(SpecIncompleteError, match="升序"):
        require_supplied_materials_order(
            spec, (reversed_hand, *bundle[1:]), closed_entries=rows
        )
    forbidden_entry = MaterialEntry(
        purpose_label="arm_b",
        index_key=(spec.campaign, "0", "1", "1", "0", "ab"),
        value=1,
    )
    with pytest.raises(SpecIncompleteError, match="不得列入"):
        require_supplied_materials_order(
            spec,
            (
                HandMaterials(
                    hand_ordinal=bundle[0].hand_ordinal,
                    entries=(*bundle[0].entries, forbidden_entry),
                ),
                *bundle[1:],
            ),
            closed_entries=rows,
        )

    assert manifest.entries[0].purpose_label == "master"
    assert fixture.audit.reads[0].purpose_label == "master"
    assert fixture.audit.reads[0].read_index == expected_supplied_payload["master_read_index"]
    retained_manifest = {
        (entry.purpose_label, entry.index_key): entry.value
        for entry in manifest.entries
        if entry.purpose_label != "master"
    }
    supplied_map = {
        (entry.purpose_label, entry.index_key): entry.value
        for hand in bundle
        for entry in hand.entries
    }
    assert set(entry.purpose_label for entry in manifest.entries) == {
        "master",
        "deal",
        "arm_m",
    }
    assert retained_manifest == supplied_map

    verify_manifest_binding(
        protocol=spec.protocol,
        manifest=manifest,
        reads=fixture.audit.reads,
        bundle=bundle,
        commitment=fixture.audit.commitment,
        spec=spec,
        closed_entries=rows,
    )
    tampered_first = MaterialEntry(
        purpose_label=bundle[0].entries[0].purpose_label,
        index_key=bundle[0].entries[0].index_key,
        value=bundle[0].entries[0].value + 1,
    )
    tampered_bundle = (
        HandMaterials(
            hand_ordinal=bundle[0].hand_ordinal,
            entries=(tampered_first, *bundle[0].entries[1:]),
        ),
        *bundle[1:],
    )
    with pytest.raises(MaterialBindingError, match="不一致"):
        verify_manifest_binding(
            protocol=spec.protocol,
            manifest=manifest,
            reads=fixture.audit.reads,
            bundle=tampered_bundle,
            commitment=fixture.audit.commitment,
            spec=spec,
            closed_entries=rows,
        )
