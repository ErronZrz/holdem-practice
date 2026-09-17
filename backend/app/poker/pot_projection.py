"""候选 CALL 后的逐层资格投影。"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class PotParticipant:
    """用于分层计算的公开投入与弃牌状态。"""

    seat: int
    total_committed: int
    folded: bool


@dataclass(frozen=True)
class ProjectedParticipant:
    """候选 CALL 后的公开投入状态。"""

    seat: int
    total_committed: int
    folded: bool


@dataclass(frozen=True)
class PotRefund:
    """无人有资格争夺时按投入层退回的筹码。"""

    seat: int
    amount: int


@dataclass(frozen=True)
class PotLayer:
    """按累计投入切分的无副作用池层。"""

    lower_commitment: int
    upper_commitment: int
    amount: int
    contributor_seats: tuple[int, ...]
    eligible_seats: tuple[int, ...]
    refunds: tuple[PotRefund, ...]


class PotLayerKind(StrEnum):
    """候选 CALL 后单个投入层相对于当前行动者的资格状态。"""

    CONTESTED = "contested"
    CALLER_RECOVERY = "caller_recovery"
    OTHER_UNCONTESTED = "other_uncontested"
    NO_ELIGIBLE_RETURN = "no_eligible_return"


@dataclass(frozen=True)
class ProjectedPotLayer:
    """候选 CALL 后单个投入层的当前行动者资格。"""

    lower_commitment: int
    upper_commitment: int
    amount: int
    contributor_seats: tuple[int, ...]
    eligible_seats: tuple[int, ...]
    caller_is_eligible: bool
    kind: PotLayerKind
    refunds: tuple[PotRefund, ...]


@dataclass(frozen=True)
class CandidateCallProjection:
    """候选 CALL 后的投入层级与资格投影。"""

    caller_seat: int
    actual_call_amount: int
    participants: tuple[ProjectedParticipant, ...]
    layers: tuple[ProjectedPotLayer, ...]


def project_pot_layers(participants: Sequence[PotParticipant]) -> tuple[PotLayer, ...]:
    """按公开累计投入切分池层，不修改参与者状态。"""
    participant_list = tuple(participants)
    _validate_participants(participant_list)

    levels = sorted(
        {
            participant.total_committed
            for participant in participant_list
            if participant.total_committed
        }
    )
    layers: list[PotLayer] = []
    lower_commitment = 0

    for upper_commitment in levels:
        contributors = tuple(
            participant.seat
            for participant in participant_list
            if participant.total_committed >= upper_commitment
        )
        eligible = tuple(
            participant.seat
            for participant in participant_list
            if participant.seat in contributors and not participant.folded
        )
        amount_per_contributor = upper_commitment - lower_commitment
        amount = amount_per_contributor * len(contributors)
        refunds: tuple[PotRefund, ...] = ()
        if not eligible:
            refunds = tuple(
                PotRefund(seat=seat, amount=amount_per_contributor) for seat in contributors
            )

        layers.append(
            PotLayer(
                lower_commitment=lower_commitment,
                upper_commitment=upper_commitment,
                amount=amount,
                contributor_seats=contributors,
                eligible_seats=eligible,
                refunds=refunds,
            )
        )
        lower_commitment = upper_commitment

    return tuple(layers)


def project_candidate_call(
    participants: Sequence[PotParticipant],
    caller_seat: int,
    actual_call_amount: int,
) -> CandidateCallProjection:
    """根据公开投入状态投影一次实际 CALL 后的各层资格，不修改输入。"""
    participant_list = tuple(participants)
    _validate_participants(participant_list)
    if actual_call_amount <= 0:
        raise ValueError("实际 CALL 支付必须为正数")

    seats = {participant.seat for participant in participant_list}
    if caller_seat not in seats:
        raise ValueError("当前行动座位不存在")
    caller = next(
        participant for participant in participant_list if participant.seat == caller_seat
    )
    if caller.folded:
        raise ValueError("已弃牌座位不能候选 CALL")

    projected = tuple(
        ProjectedParticipant(
            seat=participant.seat,
            total_committed=participant.total_committed
            + (actual_call_amount if participant.seat == caller_seat else 0),
            folded=participant.folded,
        )
        for participant in participant_list
    )
    layers = tuple(
        _projected_layer(layer, caller_seat)
        for layer in project_pot_layers(
            tuple(
                PotParticipant(
                    seat=participant.seat,
                    total_committed=participant.total_committed,
                    folded=participant.folded,
                )
                for participant in projected
            )
        )
    )
    return CandidateCallProjection(
        caller_seat=caller_seat,
        actual_call_amount=actual_call_amount,
        participants=projected,
        layers=layers,
    )


def _validate_participants(participants: Sequence[PotParticipant]) -> None:
    seats = [participant.seat for participant in participants]
    if len(seats) != len(set(seats)):
        raise ValueError("座位不能重复")
    if any(participant.total_committed < 0 for participant in participants):
        raise ValueError("累计投入不能为负数")


def _projected_layer(layer: PotLayer, caller_seat: int) -> ProjectedPotLayer:
    caller_is_eligible = caller_seat in layer.eligible_seats
    if not layer.eligible_seats:
        kind = PotLayerKind.NO_ELIGIBLE_RETURN
    elif len(layer.eligible_seats) == 1 and caller_is_eligible:
        kind = PotLayerKind.CALLER_RECOVERY
    elif len(layer.eligible_seats) == 1:
        kind = PotLayerKind.OTHER_UNCONTESTED
    else:
        kind = PotLayerKind.CONTESTED
    return ProjectedPotLayer(
        lower_commitment=layer.lower_commitment,
        upper_commitment=layer.upper_commitment,
        amount=layer.amount,
        contributor_seats=layer.contributor_seats,
        eligible_seats=layer.eligible_seats,
        caller_is_eligible=caller_is_eligible,
        kind=kind,
        refunds=layer.refunds,
    )
