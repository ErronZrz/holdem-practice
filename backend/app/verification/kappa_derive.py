"""由已提交的主值与决策键计算基线种子，并核对已提交的决策记录。

本模块只做字节拼接与摘要。它不读取随机源，不创建引擎，也不推进牌局。
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping, Sequence

from .errors import ProtocolSpecError

DERIVATION_ALGORITHM = "hmac-sha256-domain-separated-v1"
_DOMAIN_LABEL = "kappa-seed-derive-v1"
_DERIVED_PURPOSES = frozenset({"non_probed", "arm_b"})
_HEX = frozenset("0123456789abcdef")
_SEED_BOUND = 1 << 256


def derive_kappa_seed(master: bytes, purpose: str, index_key: Sequence[str]) -> int:
    """用主值与六字段键算出 [0, 2^256) 内的整数。"""
    _require_master(master)
    if purpose not in _DERIVED_PURPOSES:
        raise ProtocolSpecError("派生只接受两条基线用途")
    if isinstance(index_key, (str, bytes)) or len(index_key) != 6:
        raise ProtocolSpecError("派生键必须是六个字段")
    parts = [
        _prefixed(_DOMAIN_LABEL),
        _prefixed(purpose),
    ]
    for field in index_key:
        parts.append(_prefixed(field))
    blank = b""
    message = blank.join(parts)
    mac = hmac.new(master, message, hashlib.sha256)
    digest = mac.digest()
    return int.from_bytes(digest, "big")


def require_derived_decision_records(
    records: Sequence[Mapping[str, object]],
    *,
    master: bytes,
    campaign: str,
    block: int,
    num_players: int,
    probed_by_hand: Mapping[int, int],
) -> None:
    """核对已经提交的记录：键合法、不重复，且整数等于派生结果。

    这里看不见对局过程，因此不能判断有没有漏记。
    """
    _require_master(master)
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise ProtocolSpecError("决策记录必须是有限序列")
    if isinstance(block, bool) or not isinstance(block, int) or block < 0:
        raise ProtocolSpecError("块序号必须是非负整数")
    if (
        isinstance(num_players, bool)
        or not isinstance(num_players, int)
        or not 2 <= num_players <= 23
    ):
        raise ProtocolSpecError("人数必须是 2 到 23 的整数")
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {
            "purpose_label",
            "index_key",
            "value",
        }:
            raise ProtocolSpecError("决策记录的字段必须恰好是用途、索引和整数")
        purpose = record["purpose_label"]
        raw_key = record["index_key"]
        value = record["value"]
        if purpose not in _DERIVED_PURPOSES:
            raise ProtocolSpecError("决策记录的用途必须是两条基线用途之一")
        if isinstance(raw_key, (str, bytes)) or not isinstance(raw_key, Sequence):
            raise ProtocolSpecError("决策记录的索引必须是六个字符串")
        if len(raw_key) != 6 or any(not isinstance(field, str) for field in raw_key):
            raise ProtocolSpecError("决策记录的索引必须是六个字符串")
        index_key = tuple(raw_key)
        _require_key(
            purpose,
            index_key,
            campaign=campaign,
            block=block,
            num_players=num_players,
            probed_by_hand=probed_by_hand,
        )
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < _SEED_BOUND:
            raise ProtocolSpecError("决策记录的整数必须落在 [0, 2^256)")
        location = (purpose, index_key)
        if location in seen:
            raise ProtocolSpecError("同一完整键不得重复出现")
        seen.add(location)
        if value != derive_kappa_seed(master, purpose, index_key):
            raise ProtocolSpecError("决策记录的整数与派生结果不符")


def _require_master(master: object) -> None:
    if not isinstance(master, bytes) or len(master) != 32:
        raise ProtocolSpecError("主值必须是 32 字节")


def _prefixed(text: str) -> bytes:
    if not isinstance(text, str):
        raise ProtocolSpecError("派生字段必须是字符串")
    raw = text.encode("utf-8")
    size = len(raw)
    prefix = size.to_bytes(4, "big")
    return prefix + raw


def _require_key(
    purpose: str,
    index_key: tuple[str, ...],
    *,
    campaign: str,
    block: int,
    num_players: int,
    probed_by_hand: Mapping[int, int],
) -> None:
    key_campaign, raw_block, raw_hand, raw_seat, raw_event, sigma = index_key
    if key_campaign != campaign or len(campaign) != 64 or any(ch not in _HEX for ch in campaign):
        raise ProtocolSpecError("决策记录的 campaign 必须等于版本 3 的配置摘要")
    if _canonical(raw_block) != block:
        raise ProtocolSpecError("决策记录的块序号与规格不符")
    hand = _canonical(raw_hand)
    if hand not in probed_by_hand:
        raise ProtocolSpecError("决策记录的手序不在计划内")
    seat = _canonical(raw_seat)
    if not 0 <= seat < num_players:
        raise ProtocolSpecError("决策记录的座位超出人数范围")
    probed = probed_by_hand[hand]
    if purpose == "arm_b" and seat != probed:
        raise ProtocolSpecError("基线被测座位必须是该手的被测座位")
    if purpose == "non_probed" and (seat == probed or not 0 <= seat < num_players):
        raise ProtocolSpecError("非被测座位不得是该手的被测座位")
    _canonical(raw_event)
    if (
        len(sigma) < 2
        or len(sigma) % 2 != 0
        or any(character not in _HEX for character in sigma)
    ):
        raise ProtocolSpecError("公开投影的十六进制不规范")


def _canonical(raw: str) -> int:
    if not raw.isdigit() or (len(raw) > 1 and raw.startswith("0")):
        raise ProtocolSpecError("整数字段必须是无前导零的十进制")
    return int(raw)
