"""逐条预注册的有限完整键集。

列表本身就是来源：这里不从分量做积展开，也不读取随机字节。
生成前必须对照运行规格核对协议版本 2 的 campaign、来源、环境与手序锚点。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.verification.config import DomainRunSpec, campaign_configuration_digest
from app.verification.errors import ProtocolSpecError
from app.verification.protocol import (
    LOCKED_ENVIRONMENT_RECORD,
    LOCKED_SOURCE_INTERFACE,
    PROTOCOL_SCHEMA_V2,
    protocol_declares_v2_keys,
    require_v2_schedule_anchors,
    validate_explicit_v2_keyset,
)


@dataclass(frozen=True)
class ClosedKeyEntry:
    """一条完整索引键。不含材料值。"""

    purpose_label: str
    index_key: tuple[str, ...]


@dataclass(frozen=True)
class ClosedKeyset:
    """生成前已经闭合的键集。版本标记 2 表示 L-3 v2，不是配置摘要。"""

    version: int
    entries: tuple[ClosedKeyEntry, ...]


def closed_keyset_from_entries(
    entries: Sequence[tuple[str, tuple[str, ...]]],
    *,
    version: int = 2,
    allow_append: bool = False,
) -> ClosedKeyset:
    """把调用方逐条写下的键收成闭合集。允许追加则直接失败，不改写列表。"""
    if allow_append:
        raise ProtocolSpecError("闭合集不允许运行中追加")
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise ProtocolSpecError("条目必须是有限序列")
    built: list[ClosedKeyEntry] = []
    for label, key in entries:
        built.append(ClosedKeyEntry(purpose_label=label, index_key=tuple(key)))
    return ClosedKeyset(version=version, entries=tuple(built))


def validate_closed_keyset(keyset: ClosedKeyset, spec: DomainRunSpec) -> str:
    """第一次读取随机字节之前的只读门闩。失败时调用方不得读取。

    规格上的 campaign 与每条键都必须等于协议版本 2 的配置摘要。这不是战役身份。
    """
    if isinstance(keyset.version, bool) or keyset.version != 2:
        raise ProtocolSpecError("闭合集版本标记必须是 2")
    if not keyset.entries:
        raise ProtocolSpecError("闭合集没有可生成的键")
    if spec.protocol.protocol_schema != PROTOCOL_SCHEMA_V2 or not protocol_declares_v2_keys(
        spec.protocol
    ):
        raise ProtocolSpecError("闭合集生成必须使用 randomization-protocol-v2")
    source = spec.protocol.source_interface_id
    environment = spec.protocol.environment_record
    if source != LOCKED_SOURCE_INTERFACE or environment != LOCKED_ENVIRONMENT_RECORD:
        raise ProtocolSpecError("来源或环境与锁定值不符")
    digest_fields = {
        "num_players": spec.num_players,
        "starting_stack": spec.starting_stack,
        "small_blind": spec.small_blind,
        "big_blind": spec.big_blind,
        "baseline_identifier": spec.baseline_identifier,
        "under_test_identifier": spec.under_test_identifier,
        "lock_versions": spec.campaign_configuration.lock_versions,
    }
    campaign_v1 = campaign_configuration_digest(**digest_fields, randomization_protocol=1)
    campaign_v2 = campaign_configuration_digest(**digest_fields, randomization_protocol=2)
    if spec.campaign != campaign_v2 or campaign_v1 == campaign_v2:
        raise ProtocolSpecError("规格上的 campaign 必须是协议版本 2 的配置摘要")
    rows = tuple((entry.purpose_label, entry.index_key) for entry in keyset.entries)
    probed_by_hand = {plan.hand_ordinal: plan.probed_seat for plan in spec.schedule}
    validate_explicit_v2_keyset(
        rows, probed_by_hand=probed_by_hand, num_players=spec.num_players
    )
    for _label, index_key in rows:
        if index_key[0] == campaign_v1 or index_key[0] != campaign_v2:
            raise ProtocolSpecError("闭合集的 campaign 必须是协议版本 2 的配置摘要")
    require_v2_schedule_anchors(
        rows,
        campaign=campaign_v2,
        block=spec.block,
        draw_count=spec.deal.draw_count(spec.num_players),
        num_players=spec.num_players,
        probed_by_hand=probed_by_hand,
    )
    return campaign_v2
