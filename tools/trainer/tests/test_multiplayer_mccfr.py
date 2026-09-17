import random
from math import fsum

import pytest

from multiplayer_cfr import mccfr
from multiplayer_cfr.game import Action, infoset_by_key, structure_counts
from multiplayer_cfr.mccfr import (
    MCCFRConfig,
    MCCFRError,
    SynchronousExternalSamplingMCCFR,
    _InfoSetNode,
    _sample_action,
    train,
)
from multiplayer_cfr.randomness import (
    CHANCE_PURPOSE,
    OPPONENT_ACTION_PURPOSE,
    SeedDerivationError,
    derive_seed,
)


def test_regret_matching_uses_uniform_distribution_without_positive_regret() -> None:
    node = _InfoSetNode((Action.CHECK, Action.BET))

    assert node.current_strategy() == {Action.CHECK: 0.5, Action.BET: 0.5}
    node.regret_sum = {Action.CHECK: -2.0, Action.BET: 0.0}

    assert node.current_strategy() == {Action.CHECK: 0.5, Action.BET: 0.5}


def test_regret_matching_and_average_strategy_are_non_negative_and_normalized() -> None:
    node = _InfoSetNode((Action.CHECK, Action.BET))
    node.regret_sum = {Action.CHECK: 3.0, Action.BET: 1.0}
    node.strategy_sum = {Action.CHECK: 5.0, Action.BET: 15.0}

    assert node.current_strategy() == {Action.CHECK: 0.75, Action.BET: 0.25}
    assert node.average_strategy() == {Action.CHECK: 0.25, Action.BET: 0.75}


@pytest.mark.parametrize("player_count", [6, 7, 9])
def test_trainer_preallocates_exact_rule_infosets(player_count: int) -> None:
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(
            player_count=player_count,
            iterations=1,
            master_seed=7,
            average_strategy_start_iteration=1,
        )
    )

    assert trainer.infoset_count == structure_counts(player_count).infosets
    assert set(trainer._nodes) == set(infoset_by_key(player_count))
    assert all(
        node.actions == infoset_by_key(player_count)[key].actions
        for key, node in trainer._nodes.items()
    )


def test_one_iteration_uses_all_traversers_and_commits_only_after_all_passes(monkeypatch) -> None:
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(
            player_count=6,
            iterations=1,
            master_seed=19,
            average_strategy_start_iteration=1,
        )
    )
    seen_policy_ids: list[int] = []
    state_was_pristine: list[bool] = []
    original_collect = trainer._collect_pass

    def observe_pass(*args, **kwargs):
        seen_policy_ids.append(id(args[2]))
        state_was_pristine.append(
            all(
                all(value == 0.0 for value in node.regret_sum.values())
                and all(value == 0.0 for value in node.strategy_sum.values())
                for node in trainer._nodes.values()
            )
        )
        return original_collect(*args, **kwargs)

    monkeypatch.setattr(trainer, "_collect_pass", observe_pass)

    trace = trainer.run_iteration(1)

    assert [item.traverser for item in trace.passes] == list(range(6))
    assert len(set(seen_policy_ids)) == 1
    assert all(state_was_pristine)
    assert any(
        any(value != 0.0 for value in node.regret_sum.values()) for node in trainer._nodes.values()
    )


def test_each_traverser_pass_samples_exactly_one_chance_deal(monkeypatch) -> None:
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(
            player_count=6,
            iterations=1,
            master_seed=21,
            average_strategy_start_iteration=1,
        )
    )
    sampled_seeds: list[int] = []
    original_sample = mccfr.CandidateAChance.sample_ordered_deal

    def observe_sample(chance):
        sampled_seeds.append(chance.seed)
        return original_sample(chance)

    monkeypatch.setattr(mccfr.CandidateAChance, "sample_ordered_deal", observe_sample)

    trace = trainer.run_iteration(1)

    assert sampled_seeds == [item.chance_seed for item in trace.passes]
    assert len(sampled_seeds) == 6


def test_external_sampling_enumerates_traverser_actions_and_samples_opponents() -> None:
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(
            player_count=6,
            iterations=1,
            master_seed=23,
            average_strategy_start_iteration=1,
        )
    )

    trace = trainer.run_iteration(1)
    first_pass = trace.passes[0]

    assert first_pass.traverser == 0
    assert "/actor=0/" in first_pass.traverser_visits[0].infoset_key
    assert first_pass.traverser_visits[0].infoset_key.endswith("/history=-")
    assert {history for history, _ in first_pass.sampled_opponent_actions} >= {"x@0", "b@0"}
    assert all(visit.opponent_sampling_probability > 0.0 for visit in first_pass.traverser_visits)
    assert all(
        visit.average_importance_weight == pytest.approx(1.0 / visit.opponent_sampling_probability)
        for visit in first_pass.traverser_visits
    )


def test_average_strategy_is_complete_normalized_and_seed_repeatable() -> None:
    config = MCCFRConfig(
        player_count=6,
        iterations=2,
        master_seed=31,
        average_strategy_start_iteration=1,
    )

    first = train(config)
    second = train(config)

    assert first == second
    assert first.infoset_count == 1152
    assert first.completed_iterations == 2
    for probabilities in first.average_strategy.values():
        assert all(probability >= 0.0 for probability in probabilities.values())
        assert fsum(probabilities.values()) == pytest.approx(1.0)


def test_average_strategy_accumulation_respects_configured_start_iteration() -> None:
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(
            player_count=6,
            iterations=2,
            master_seed=37,
            average_strategy_start_iteration=2,
        )
    )

    trainer.run_iteration(1)

    assert all(
        all(value == 0.0 for value in node.strategy_sum.values())
        for node in trainer._nodes.values()
    )
    trainer.run_iteration(2)
    assert any(
        any(value > 0.0 for value in node.strategy_sum.values()) for node in trainer._nodes.values()
    )


def test_zero_probability_action_is_never_sampled() -> None:
    action = _sample_action(
        (Action.CHECK, Action.BET),
        {Action.CHECK: 1.0, Action.BET: 0.0},
        random.Random(5),
    )

    assert action is Action.CHECK


def test_iteration_order_and_configuration_validation() -> None:
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(player_count=6, iterations=2, master_seed=1, average_strategy_start_iteration=2)
    )

    with pytest.raises(MCCFRError):
        trainer.run_iteration(2)
    trainer.run_iteration(1)
    with pytest.raises(MCCFRError):
        trainer.run_iteration(1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "player_count": 5,
            "iterations": 1,
            "master_seed": 0,
            "average_strategy_start_iteration": 1,
        },
        {
            "player_count": 6,
            "iterations": 0,
            "master_seed": 0,
            "average_strategy_start_iteration": 1,
        },
        {
            "player_count": 6,
            "iterations": 1,
            "master_seed": True,
            "average_strategy_start_iteration": 1,
        },
        {
            "player_count": 6,
            "iterations": 1,
            "master_seed": 0,
            "average_strategy_start_iteration": 2,
        },
        {"player_count": 6, "iterations": 1, "master_seed": 0},
    ],
)
def test_invalid_configuration_is_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises((MCCFRError, TypeError, ValueError)):
        MCCFRConfig(**kwargs)


def test_seed_derivation_is_stable_and_isolates_streams() -> None:
    first = derive_seed(
        41,
        player_count=6,
        iteration=1,
        traverser=2,
        purpose=CHANCE_PURPOSE,
    )

    assert first == derive_seed(
        41,
        player_count=6,
        iteration=1,
        traverser=2,
        purpose=CHANCE_PURPOSE,
    )
    assert first != derive_seed(
        41,
        player_count=6,
        iteration=1,
        traverser=2,
        purpose=OPPONENT_ACTION_PURPOSE,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"player_count": 6, "iteration": 0, "traverser": 0, "purpose": CHANCE_PURPOSE},
        {"player_count": 6, "iteration": 1, "traverser": 6, "purpose": CHANCE_PURPOSE},
        {"player_count": 6, "iteration": 1, "traverser": 0, "purpose": "other"},
    ],
)
def test_seed_derivation_rejects_non_contract_inputs(kwargs: dict[str, object]) -> None:
    with pytest.raises(SeedDerivationError):
        derive_seed(0, **kwargs)
