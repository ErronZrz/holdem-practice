from math import factorial

import pytest

from multiplayer_cfr.chance import CandidateAChance, iter_ordered_deals, ordered_deal_count
from multiplayer_cfr.game import CandidateARuleError


@pytest.mark.parametrize("player_count", [6, 7, 9])
def test_ordered_deal_space_has_factorial_size_and_unique_ranks(player_count: int) -> None:
    observed = 0
    for deal in iter_ordered_deals(player_count):
        assert len(deal.ranks) == player_count
        assert set(deal.ranks) == set(range(player_count))
        observed += 1

    assert observed == factorial(player_count)
    assert ordered_deal_count(player_count) == factorial(player_count)


@pytest.mark.parametrize("player_count", [6, 7, 9])
def test_seeded_chance_sampling_is_reproducible_and_deals_without_duplicates(
    player_count: int,
) -> None:
    first = CandidateAChance(player_count, seed=20260917)
    second = CandidateAChance(player_count, seed=20260917)
    different = CandidateAChance(player_count, seed=20260918)

    first_draws = [first.sample_ordered_deal().ranks for _ in range(12)]
    second_draws = [second.sample_ordered_deal().ranks for _ in range(12)]
    different_draws = [different.sample_ordered_deal().ranks for _ in range(12)]

    assert first_draws == second_draws
    assert first_draws != different_draws
    assert all(set(deal) == set(range(player_count)) for deal in first_draws)


@pytest.mark.parametrize("player_count", [5, 8, 10])
def test_chance_rejects_unsupported_player_counts(player_count: int) -> None:
    with pytest.raises(CandidateARuleError):
        CandidateAChance(player_count, seed=1)


@pytest.mark.parametrize("seed", [True, 1.5, "1"])
def test_chance_requires_an_explicit_integer_seed(seed: object) -> None:
    with pytest.raises(CandidateARuleError):
        CandidateAChance(6, seed=seed)  # type: ignore[arg-type]
