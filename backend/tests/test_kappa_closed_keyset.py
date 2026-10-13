"""闭合键集门闩与生成器的非实际夹具。随机源是替身，不产生战役材料。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.verification import ProtocolSpecError
from tools.kappa_keyset import closed_keyset_from_entries

from .verification_helpers import (
    fixture_campaign,
    fixture_projection_hex,
    hand_source_manifest,
    v2_anchor_entries,
    v2_fixture_campaign,
    v2_run_spec,
)


def _load_generator():
    path = Path(__file__).resolve().parents[1] / "tools" / "material_generator.py"
    spec = importlib.util.spec_from_file_location("closed_keyset_generator_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict[str, object]:
    return hand_source_manifest("backend/tools/material_generator.py")


def _forbid_reads(monkeypatch: pytest.MonkeyPatch, module) -> None:
    def forbidden(size: int) -> bytes:
        raise AssertionError(f"门闩失败不得读取：{size}")

    monkeypatch.setattr(module.os, "urandom", forbidden)


def test_append_flag_fails_before_generation() -> None:
    with pytest.raises(ProtocolSpecError):
        closed_keyset_from_entries([], allow_append=True)


def test_duplicate_v2_key_does_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    _forbid_reads(monkeypatch, module)
    spec = v2_run_spec()
    rows = v2_anchor_entries(spec, fixture_projection_hex())
    rows.append(rows[-1])
    with pytest.raises(ProtocolSpecError):
        module.generate_from_closed_keyset(
            closed_keyset_from_entries(rows), spec, _manifest()
        )


def test_two_projections_cannot_share_an_event_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_generator()
    _forbid_reads(monkeypatch, module)
    spec = v2_run_spec()
    rows = v2_anchor_entries(spec, fixture_projection_hex(pot=6))
    other = fixture_projection_hex(pot=7)
    campaign = v2_fixture_campaign(spec)
    rows.append(("non_probed", (campaign, "0", "1", "0", "0", other)))
    with pytest.raises(ProtocolSpecError):
        module.generate_from_closed_keyset(
            closed_keyset_from_entries(rows), spec, _manifest()
        )


def test_v1_campaign_does_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    _forbid_reads(monkeypatch, module)
    spec = v2_run_spec()
    version_one = fixture_campaign(num_players=spec.num_players)
    rows = [
        (label, (version_one, *key[1:]))
        for label, key in v2_anchor_entries(spec, fixture_projection_hex())
    ]
    with pytest.raises(ProtocolSpecError):
        module.generate_from_closed_keyset(
            closed_keyset_from_entries(rows), spec, _manifest()
        )


def test_version_one_spec_campaign_does_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    _forbid_reads(monkeypatch, module)
    spec = v2_run_spec()
    version_one = fixture_campaign(num_players=spec.num_players)
    stale = spec.model_copy(update={"campaign": version_one})
    rows = v2_anchor_entries(spec, fixture_projection_hex())
    with pytest.raises(ProtocolSpecError):
        module.generate_from_closed_keyset(
            closed_keyset_from_entries(rows), stale, _manifest()
        )


def test_missing_purpose_does_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    _forbid_reads(monkeypatch, module)
    spec = v2_run_spec()
    rows = [
        row
        for row in v2_anchor_entries(spec, fixture_projection_hex())
        if row[0] != "arm_b"
    ]
    with pytest.raises(ProtocolSpecError):
        module.generate_from_closed_keyset(
            closed_keyset_from_entries(rows), spec, _manifest()
        )


def test_wrong_source_does_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    _forbid_reads(monkeypatch, module)
    spec = v2_run_spec()
    rows = v2_anchor_entries(spec, fixture_projection_hex())
    bad = spec.protocol.model_copy(update={"source_interface_id": "other-source@1"})
    with pytest.raises(ProtocolSpecError):
        module.generate_from_closed_keyset(
            closed_keyset_from_entries(rows),
            spec.model_copy(update={"protocol": bad}),
            _manifest(),
        )


def test_wrong_environment_does_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    _forbid_reads(monkeypatch, module)
    spec = v2_run_spec()
    rows = v2_anchor_entries(spec, fixture_projection_hex())
    bad = spec.protocol.model_copy(update={"environment_record": "other-env@1"})
    with pytest.raises(ProtocolSpecError):
        module.generate_from_closed_keyset(
            closed_keyset_from_entries(rows),
            spec.model_copy(update={"protocol": bad}),
            _manifest(),
        )


def test_illegal_sigma_does_not_read(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    _forbid_reads(monkeypatch, module)
    spec = v2_run_spec()
    rows = v2_anchor_entries(spec, "cd")
    with pytest.raises(ProtocolSpecError):
        module.generate_from_closed_keyset(
            closed_keyset_from_entries(rows), spec, _manifest()
        )


def test_closed_reader_covers_schedule_anchors(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    calls: list[int] = []

    def zeros(size: int) -> bytes:
        calls.append(size)
        return b"\x00" * size

    monkeypatch.setattr(module.os, "urandom", zeros)
    spec = v2_run_spec()
    rows = v2_anchor_entries(spec, fixture_projection_hex())
    generated = module.generate_from_closed_keyset(
        closed_keyset_from_entries(rows), spec, _manifest()
    )
    assert calls == [1] * 9 + [32, 32, 32]
    labels = [entry.purpose_label for entry in generated.material_manifest.entries]
    assert labels[:9] == ["deal"] * 9
    assert labels[9:] == ["non_probed", "arm_m", "arm_b"]
    assert generated.audit.commitment.source_interface_id == spec.protocol.source_interface_id
    assert generated.audit.commitment.environment_record == spec.protocol.environment_record
    assert len(generated.audit.reads) == len(rows)


def test_rejected_deal_byte_does_not_add_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_generator()
    payloads = [bytes([255]), bytes([0])] + [bytes([0])] * 8 + [b"\x00" * 32] * 3

    def scripted(size: int) -> bytes:
        chunk = payloads.pop(0)
        assert len(chunk) == size
        return chunk

    monkeypatch.setattr(module.os, "urandom", scripted)
    spec = v2_run_spec()
    rows = v2_anchor_entries(spec, fixture_projection_hex())
    generated = module.generate_from_closed_keyset(
        closed_keyset_from_entries(rows), spec, _manifest()
    )
    assert generated.audit.reads[0].accepted is False
    assert sum(1 for record in generated.audit.reads if record.accepted) == len(rows)
    assert len(generated.material_manifest.entries) == len(rows)
    assert payloads == []
