"""终局净差上界与配对记录核对。

设计目的：
- 在不推进牌局的前提下，由筹码守恒推出单座净差区间，再推出两臂之差的上界；
- 只接受已经结束的两臂终局记录：开手筹码、终局筹码与发牌材料必须同时齐备。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import SpecIncompleteError, VerificationError


class ArmTerminal(BaseModel):
    """一臂的开手筹码、终局筹码与发牌材料。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    opening_stacks: tuple[int, ...]
    terminal_stacks: tuple[int, ...]
    deal_cards: tuple[str, ...]

    @model_validator(mode="after")
    def _require_integers(self) -> ArmTerminal:
        _require_int_row("开手筹码", self.opening_stacks)
        _require_int_row("终局筹码", self.terminal_stacks)
        if not self.deal_cards or any(not card for card in self.deal_cards):
            raise VerificationError("发牌材料不能为空")
        return self


class PairingTranscript(BaseModel):
    """两臂共用同一手的终局记录。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    num_players: int = Field(strict=True)
    starting_stack: int = Field(strict=True)
    probed_seat: int = Field(strict=True)
    measured: ArmTerminal
    baseline: ArmTerminal


def derived_difference_bound(num_players: int, starting_stack: int) -> int:
    """由单座净差区间推出两臂之差的上界。

    开手每人筹码为 S、终局非负且总和仍为 N·S 时，单座净差落在 [-S, (N-1)·S]。
    两臂同一座位的净差之差因此落在 [-N·S, N·S]。
    """
    if isinstance(num_players, bool) or not isinstance(num_players, int):
        raise SpecIncompleteError("人数必须是整数")
    if isinstance(starting_stack, bool) or not isinstance(starting_stack, int):
        raise SpecIncompleteError("起始筹码必须是整数")
    if not 2 <= num_players <= 23 or starting_stack < 1:
        raise SpecIncompleteError("人数或起始筹码超出可推导范围")
    lowest = -starting_stack
    highest = (num_players - 1) * starting_stack
    return highest - lowest


def require_pairing_transcript(record: PairingTranscript) -> int:
    """核对两臂发牌、开手重置与终局净差，并返回被测座位的两臂净差。"""
    if isinstance(record.num_players, bool) or not 2 <= record.num_players <= 23:
        raise VerificationError("人数必须是 2 到 23 的整数")
    if isinstance(record.starting_stack, bool) or record.starting_stack < 1:
        raise VerificationError("起始筹码必须是正整数")
    if record.measured.deal_cards != record.baseline.deal_cards:
        raise VerificationError("两臂发牌材料必须相同")
    _require_opening(record.measured, record.num_players, record.starting_stack)
    _require_opening(record.baseline, record.num_players, record.starting_stack)
    measured_net = _seat_net(
        record.measured, record.num_players, record.starting_stack, record.probed_seat
    )
    baseline_net = _seat_net(
        record.baseline, record.num_players, record.starting_stack, record.probed_seat
    )
    difference = measured_net - baseline_net
    bound = derived_difference_bound(record.num_players, record.starting_stack)
    if abs(difference) > bound:
        raise VerificationError("两臂净差超出由守恒推出的上界")
    return difference


def _require_int_row(label: str, values: tuple[int, ...]) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise VerificationError(f"{label}必须是整数")


def _require_opening(arm: ArmTerminal, num_players: int, starting_stack: int) -> None:
    if len(arm.opening_stacks) != num_players:
        raise VerificationError("开手筹码人数与规格不一致")
    if any(stack != starting_stack for stack in arm.opening_stacks):
        raise VerificationError("开手前每个座位的筹码都必须等于起始筹码")


def _seat_net(arm: ArmTerminal, num_players: int, starting_stack: int, probed_seat: int) -> int:
    if len(arm.terminal_stacks) != num_players:
        raise VerificationError("终局筹码人数与规格不一致")
    if probed_seat < 0 or probed_seat >= num_players:
        raise VerificationError("被测座位必须落在人数范围内")
    if any(stack < 0 for stack in arm.terminal_stacks):
        raise VerificationError("终局筹码不能为负")
    if sum(arm.terminal_stacks) != num_players * starting_stack:
        raise VerificationError("终局筹码必须守恒")
    net = arm.terminal_stacks[probed_seat] - starting_stack
    lowest = -starting_stack
    highest = (num_players - 1) * starting_stack
    if not lowest <= net <= highest:
        raise VerificationError("单座净差超出守恒区间")
    return net
