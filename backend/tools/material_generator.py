"""包外材料生成：按协议遍历顺序串行读取随机字节，失败则不返回任何结果。

随机源在源码中直接调用 os.urandom，不提供可替换参数。本模块不写文件，也不推进牌局。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from app.verification.config import DomainRunSpec
from app.verification.digests import bytes_digest
from app.verification.errors import ProtocolAuditError, ProtocolSpecError
from app.verification.materials import (
    HandMaterials,
    MaterialEntry,
    MaterialManifest,
    manifest_digest,
)
from app.verification.protocol import (
    AuditedMaterials,
    PurposeRole,
    PurposeSpec,
    ReadRecord,
    TranscriptCommitment,
    read_record_digest,
    resolve_read,
)
from app.verification.source_manifest import require_source_manifest, source_manifest_digest

_GENERATOR_ENTRYPOINT = "backend/tools/material_generator.py"


@dataclass(frozen=True)
class GeneratedMaterials:
    """一次成功生成的材料束、清单与承诺。失败路径不会构造本对象。"""

    bundle: tuple[HandMaterials, ...]
    material_manifest: MaterialManifest
    audit: AuditedMaterials


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _index_key(
    spec: DomainRunSpec,
    purpose: PurposeSpec,
    hand: int,
    *,
    draw: int | None = None,
    seat: int | None = None,
) -> tuple[str, ...]:
    values: list[str] = []
    for name in purpose.index_fields:
        if name == "campaign":
            values.append(spec.campaign)
        elif name == "block":
            values.append(str(spec.block))
        elif name == "hand":
            values.append(str(hand))
        elif name == purpose.draw_index_field:
            if draw is None:
                raise ProtocolSpecError("发牌索引缺少抽取次序")
            values.append(str(draw))
        elif name == purpose.seat_index_field:
            if seat is None:
                raise ProtocolSpecError("座位索引缺少座位号")
            values.append(str(seat))
        else:
            raise ProtocolSpecError(f"无法填写索引字段：{name}")
    return tuple(values)


def _keys_for(
    spec: DomainRunSpec, purpose: PurposeSpec, hand: int, probed_seat: int
) -> tuple[tuple[str, ...], ...]:
    if purpose.role is PurposeRole.DEAL:
        count = spec.deal.draw_count(spec.num_players)
        return tuple(
            _index_key(spec, purpose, hand, draw=draw) for draw in range(count)
        )
    if purpose.role is PurposeRole.NON_PROBED_SEED:
        return tuple(
            _index_key(spec, purpose, hand, seat=seat)
            for seat in range(spec.num_players)
            if seat != probed_seat
        )
    return (_index_key(spec, purpose, hand),)


def _read_accepted(
    purpose: PurposeSpec,
    key: tuple[str, ...],
    *,
    step_index: int,
    transcript: bytearray,
    reads: list[ReadRecord],
    rejections: dict[str, int],
) -> int:
    """同一索引连续读取，直到接受。异常或长度不符直接向外传播。"""
    label = purpose.label
    while True:
        nbytes = purpose.bit_width // 8
        raw = os.urandom(nbytes)
        if len(raw) != nbytes:
            raise ProtocolAuditError("随机源返回的长度不符")
        value = int.from_bytes(raw, "big", signed=False)
        offset = len(transcript)
        transcript.extend(raw)
        output = resolve_read(
            value,
            bit_width=purpose.bit_width,
            domain_size=purpose.domain.domain_size(step_index),
        )
        reads.append(
            ReadRecord(
                read_index=len(reads),
                purpose_label=label,
                index_key=key,
                bit_width=purpose.bit_width,
                raw_offset=offset,
                raw_value=value,
                accepted=output is not None,
                output=output,
            )
        )
        if output is None:
            rejections[label] += 1
            continue
        return output


def generate_materials(
    spec: DomainRunSpec,
    generator_manifest: Mapping[str, object],
) -> GeneratedMaterials:
    """按遍历顺序生成材料。只有全部成功才返回；任何较早的失败都不构造结果。"""
    manifest = require_source_manifest(generator_manifest)
    if tuple(manifest["entrypoints"]) != (_GENERATOR_ENTRYPOINT,):
        raise ProtocolSpecError("生成器清单的入口必须是材料生成模块")
    algorithm = spec.protocol.digest_algorithm
    generator_code_digest = source_manifest_digest(manifest, algorithm=algorithm)
    started = datetime.now(UTC)
    protocol = spec.protocol
    transcript = bytearray()
    reads: list[ReadRecord] = []
    accepted: list[MaterialEntry] = []
    rejections = {purpose.label: 0 for purpose in protocol.purposes}
    accepted_counts = {purpose.label: 0 for purpose in protocol.purposes}
    for label in protocol.traversal_order:
        purpose = protocol.purpose_for_label(label)
        for plan in spec.schedule:
            for key in _keys_for(spec, purpose, plan.hand_ordinal, plan.probed_seat):
                step_index = (
                    purpose.draw_index_of(key) if purpose.role is PurposeRole.DEAL else 0
                )
                output = _read_accepted(
                    purpose,
                    key,
                    step_index=step_index,
                    transcript=transcript,
                    reads=reads,
                    rejections=rejections,
                )
                accepted.append(
                    MaterialEntry(purpose_label=label, index_key=key, value=output)
                )
                accepted_counts[label] += 1
    by_hand: dict[int, list[MaterialEntry]] = {
        plan.hand_ordinal: [] for plan in spec.schedule
    }
    for entry in accepted:
        purpose = protocol.purpose_for_label(entry.purpose_label)
        by_hand[purpose.field_integer(entry.index_key, "hand")].append(entry)
    bundle = tuple(
        HandMaterials(hand_ordinal=plan.hand_ordinal, entries=tuple(by_hand[plan.hand_ordinal]))
        for plan in spec.schedule
    )
    material_manifest = MaterialManifest(entries=tuple(accepted))
    raw = bytes(transcript)
    finished = datetime.now(UTC)
    if finished < started:
        raise ProtocolAuditError("生成结束时刻早于开始时刻")
    commitment = TranscriptCommitment(
        source_interface_id=protocol.source_interface_id,
        environment_record=protocol.environment_record,
        generation_started_at=_stamp(started),
        generation_finished_at=_stamp(finished),
        traversal_order=protocol.traversal_order,
        entry_counts=tuple(
            (label, accepted_counts[label]) for label in protocol.traversal_order
        ),
        rejection_counts=tuple((label, rejections[label]) for label in protocol.traversal_order),
        transcript_digest=bytes_digest(raw, algorithm=algorithm),
        read_record_digest=read_record_digest(
            reads, encoding=protocol.read_record_encoding, algorithm=algorithm
        ),
        manifest_digest=manifest_digest(material_manifest, algorithm=algorithm),
        generator_code_digest=generator_code_digest,
        digest_algorithm=algorithm,
        read_record_encoding=protocol.read_record_encoding,
        audit_format_version=protocol.audit_format_version,
    )
    return GeneratedMaterials(
        bundle=bundle,
        material_manifest=material_manifest,
        audit=AuditedMaterials(transcript=raw, reads=tuple(reads), commitment=commitment),
    )
