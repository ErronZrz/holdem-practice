"""候选 A 的确定性训练随机流派生。"""

from __future__ import annotations

from hashlib import sha256

from .game import validate_player_count

SEED_DERIVATION_ID = "sha256-64be-v1"
CHANCE_PURPOSE = "chance"
OPPONENT_ACTION_PURPOSE = "opponent-action"
_ALLOWED_PURPOSES = frozenset({CHANCE_PURPOSE, OPPONENT_ACTION_PURPOSE})


class SeedDerivationError(ValueError):
    """训练随机流参数不完整或不属于固定语义时抛出。"""


def _require_int(value: int, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SeedDerivationError(f"{label} 必须是整数")
    if minimum is not None and value < minimum:
        raise SeedDerivationError(f"{label} 不能小于 {minimum}")
    return value


def derive_seed(
    master_seed: int,
    *,
    player_count: int,
    iteration: int,
    traverser: int,
    purpose: str,
) -> int:
    """为单个 traverser pass 派生彼此独立且可重放的整数 seed。"""

    master_seed = _require_int(master_seed, "master seed")
    player_count = validate_player_count(player_count)
    iteration = _require_int(iteration, "iteration", minimum=1)
    traverser = _require_int(traverser, "traverser", minimum=0)
    if traverser >= player_count:
        raise SeedDerivationError("traverser 超出相对座位范围")
    if purpose not in _ALLOWED_PURPOSES:
        raise SeedDerivationError("随机流 purpose 不属于候选 A 契约")

    payload = "\x1f".join(
        (
            SEED_DERIVATION_ID,
            str(master_seed),
            str(player_count),
            str(iteration),
            str(traverser),
            purpose,
        )
    ).encode("ascii")
    return int.from_bytes(sha256(payload).digest()[:8], byteorder="big", signed=False)
