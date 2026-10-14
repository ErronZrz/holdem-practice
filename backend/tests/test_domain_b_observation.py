"""域 B 主判：合并口径下的桶质量与两身份之差。"""

from __future__ import annotations

import pytest

from app.poker.actions import ActionType
from app.strategy.distribution_observation import (
    PROBABILITY_UNITS,
    DistributionObservation,
    ObservationSemanticError,
    amount_bucket,
    bucket_mass_difference,
    marginalized_bucket_units,
)
from app.strategy.mixed_policy import MixedCandidate
from app.verification.domain_registry import amount_bucket as registered_bucket


def _observation(*rows: tuple[int, int]) -> DistributionObservation:
    return DistributionObservation(
        probability_units=PROBABILITY_UNITS,
        mode_weights=(8, 1, 1),
        aggregation="marginalized",
        candidates=tuple(
            MixedCandidate(action=ActionType.RAISE, amount=amount, units=units)
            for amount, units in rows
        ),
    )


def test_bucket_names_match_the_registered_partition() -> None:
    for amount in range(0, 21):
        assert amount_bucket(amount) == registered_bucket(amount)


def test_marginalized_bucket_mass_and_difference() -> None:
    observation = _observation((6, 400_000), (8, 300_000), (10, 300_000))
    assert marginalized_bucket_units(observation, (6, 8, 10), "BKT_MID") == 400_000
    assert marginalized_bucket_units(observation, (6, 8, 10), "BKT_LARGE") == 600_000
    numerator, denominator = bucket_mass_difference(400_000, 100_000, PROBABILITY_UNITS)
    assert (numerator, denominator) == (300_000, PROBABILITY_UNITS)
    assert abs(numerator) <= denominator


def test_mode_override_is_not_a_primary_bucket_query() -> None:
    observation = _observation((6, PROBABILITY_UNITS)).model_copy(
        update={"aggregation": "mode_override", "overridden_mode": "normal"}
    )
    with pytest.raises(ObservationSemanticError):
        marginalized_bucket_units(observation, (6,), "BKT_MID")
