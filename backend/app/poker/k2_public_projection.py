"""把一次决策边界的公开局面编成规范串。

只读取局面与合法动作里已经点名的公开字段。私牌、姓名、牌堆与随机源都不进入结果。
本模块不依赖策略、校验、接口或模型层。
"""

from __future__ import annotations

from .actions import LegalActions
from .cards import Card
from .state import GameState, PlayerState

_SCHEMA = "k2-public-projection-v1"
_RANK_CHARS = set("23456789TJQKA")
_SUIT_CHARS = set("cdhs")
_HEX = set("0123456789abcdef")


class K2PublicProjectionError(ValueError):
    """公开投影无法按封闭字段集编码。"""


def encode_k2_public_v1(state: GameState, legal: LegalActions) -> str:
    """形成规范串。行序固定，最后一行之后没有换行。"""
    if not isinstance(state, GameState) or not isinstance(legal, LegalActions):
        raise K2PublicProjectionError("编码只接受局面与合法动作")
    player_count = len(state.players)
    if isinstance(player_count, bool) or player_count < 2:
        raise K2PublicProjectionError("公开投影至少需要两名玩家")
    lines = [
        f"schema={_SCHEMA}",
        f"street={_integer('street', int(state.street))}",
        f"hand_over={_flag('hand_over', state.hand_over)}",
        f"button={_integer('button', state.button)}",
        f"current_seat={_integer('current_seat', state.current_seat)}",
        f"pot={_integer('pot', state.pot)}",
        f"n_players={_integer('n_players', player_count)}",
        f"board_len={_integer('board_len', len(state.board))}",
    ]
    street = int(state.street)
    if street > 4:
        raise K2PublicProjectionError("街次超出公开投影的范围")
    for index, card in enumerate(state.board):
        lines.append(f"board.{index}={_card(f'board.{index}', card)}")
    for seat in range(player_count):
        player = _player_at(state, seat)
        prefix = f"player.{seat}"
        lines.extend(
            (
                f"{prefix}.stack={_integer(f'{prefix}.stack', player.stack)}",
                f"{prefix}.folded={_flag(f'{prefix}.folded', player.folded)}",
                f"{prefix}.all_in={_flag(f'{prefix}.all_in', player.all_in)}",
                f"{prefix}.street_bet={_integer(f'{prefix}.street_bet', player.street_bet)}",
                (
                    f"{prefix}.total_committed="
                    f"{_integer(f'{prefix}.total_committed', player.total_committed)}"
                ),
                (
                    f"{prefix}.has_acted_since_full_raise="
                    + _flag(
                        f"{prefix}.has_acted_since_full_raise",
                        player.has_acted_since_full_raise,
                    )
                ),
            )
        )
    lines.extend(
        (
            f"legal.can_fold={_flag('legal.can_fold', legal.can_fold)}",
            f"legal.can_check={_flag('legal.can_check', legal.can_check)}",
            f"legal.can_call={_flag('legal.can_call', legal.can_call)}",
            f"legal.call_amount={_integer('legal.call_amount', legal.call_amount)}",
            (
                "legal.actual_call_amount="
                f"{_integer('legal.actual_call_amount', legal.actual_call_amount)}"
            ),
            (
                "legal.is_short_all_in_call="
                f"{_flag('legal.is_short_all_in_call', legal.is_short_all_in_call)}"
            ),
            f"legal.can_bet={_flag('legal.can_bet', legal.can_bet)}",
            f"legal.min_bet={_integer('legal.min_bet', legal.min_bet)}",
            f"legal.max_bet={_integer('legal.max_bet', legal.max_bet)}",
            f"legal.can_raise={_flag('legal.can_raise', legal.can_raise)}",
            f"legal.min_raise_to={_integer('legal.min_raise_to', legal.min_raise_to)}",
            f"legal.max_raise_to={_integer('legal.max_raise_to', legal.max_raise_to)}",
        )
    )
    text = "\n".join(lines)
    if text.endswith("\n") or any("=" not in line or line.count("=") != 1 for line in lines):
        raise K2PublicProjectionError("规范串的行格式不成立")
    return text


def sigma_public_bytes(state: GameState, legal: LegalActions) -> bytes:
    """规范串的 UTF-8 字节。这不是摘要。"""
    encoded = encode_k2_public_v1(state, legal).encode("utf-8")
    if not encoded:
        raise K2PublicProjectionError("公开投影字节不能为空")
    return encoded


def sigma_public_hex(state: GameState, legal: LegalActions) -> str:
    """公开投影字节的小写十六进制，供材料键使用。"""
    raw = sigma_public_bytes(state, legal)
    text = raw.hex()
    if text != raw.hex() or len(text) != len(raw) * 2:
        raise K2PublicProjectionError("十六进制编码与字节不一致")
    sigma_hex_to_bytes(text)
    return text


def sigma_hex_to_bytes(text: str) -> bytes:
    """把已形成的小写十六进制还原成字节。不读取局面。"""
    if (
        not isinstance(text, str)
        or len(text) < 2
        or len(text) % 2 != 0
        or any(character not in _HEX for character in text)
    ):
        raise K2PublicProjectionError("十六进制必须是正偶数长度的小写文本")
    raw = bytes.fromhex(text)
    if raw.hex() != text:
        raise K2PublicProjectionError("十六进制必须是正偶数长度的小写文本")
    return raw


def _player_at(state: GameState, seat: int) -> PlayerState:
    found = [player for player in state.players if player.seat == seat]
    if len(found) != 1:
        raise K2PublicProjectionError("每个座位必须恰好有一名玩家")
    return found[0]


def _integer(name: str, value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise K2PublicProjectionError(f"规范整数不能为负：{name}")
    rendered = str(value)
    if not rendered.isdigit() or (rendered.startswith("0") and rendered != "0"):
        raise K2PublicProjectionError(f"规范整数格式不成立：{name}")
    return rendered


def _flag(name: str, value: bool) -> str:
    if not isinstance(value, bool):
        raise K2PublicProjectionError(f"规范布尔只能是真或假：{name}")
    return "1" if value else "0"


def _card(name: str, card: Card) -> str:
    if not isinstance(card, Card):
        raise K2PublicProjectionError(f"牌面类型不符：{name}")
    text = str(card)
    if len(text) != 2 or text[0] not in _RANK_CHARS or text[1] not in _SUIT_CHARS:
        raise K2PublicProjectionError(f"牌面格式不符：{name}")
    if "\n" in text or "=" in text:
        raise K2PublicProjectionError(f"牌面含有禁止字符：{name}")
    return text
