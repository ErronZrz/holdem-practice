"""规范编码与内容摘要：摘要一律由内容重算，不由调用方转录。

设计目的：
- 同一内容必得同一摘要、内容不同摘要必不同，使「抄录一个摘要字符串」不能成为凭据；
- 编码固定为紧凑 JSON、键排序、ASCII 转义，杜绝同一内容的多种编码；
- 未实现的摘要算法显式失败，不静默替代。
"""

from __future__ import annotations

import hashlib
import json

from .errors import SpecIncompleteError, VerificationError

# 本模块已实现的摘要算法：其余取值一律显式失败。
DIGEST_ALGORITHMS: tuple[str, ...] = ("sha256",)


def require_algorithm(algorithm: str) -> str:
    """校验摘要算法受支持；未实现即失败。"""
    if algorithm not in DIGEST_ALGORITHMS:
        raise SpecIncompleteError(f"摘要算法未实现：{algorithm!r}")
    return algorithm


def canonical_bytes(payload: object) -> bytes:
    """把可序列化内容编成唯一确定的字节串。"""
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=True, sort_keys=True)
    return text.encode("utf-8")


def bytes_digest(payload: bytes, *, algorithm: str) -> str:
    """对字节串取摘要。"""
    require_algorithm(algorithm)
    if not isinstance(payload, bytes):
        raise VerificationError("摘要输入必须是字节串")
    hasher = hashlib.sha256(payload)
    return hasher.hexdigest()


def content_digest(payload: object, *, algorithm: str) -> str:
    """对可序列化内容取摘要：先规范编码，再取字节摘要。"""
    return bytes_digest(canonical_bytes(payload), algorithm=algorithm)
