from collections.abc import Mapping
from math import fsum

import pytest

from multiplayer_cfr.estimator_oracle import exact_external_sampling_targets
from multiplayer_cfr.game import Action, information_set_key
from multiplayer_cfr.mccfr import MCCFRConfig, SynchronousExternalSamplingMCCFR


def _nonuniform_trainer(master_seed: int) -> SynchronousExternalSamplingMCCFR:
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(
            player_count=6,
            iterations=1,
            master_seed=master_seed,
            average_strategy_start_iteration=1,
        )
    )
    for node in trainer._nodes.values():
        first, second = node.actions
        node.regret_sum = {first: 1.0, second: 3.0}
    return trainer


def _update_values(
    updates: tuple[tuple[str, tuple[tuple[Action, float], ...]], ...], key: str
) -> Mapping[Action, float]:
    return dict(dict(updates).get(key, ()))


def test_n6_oracle_matches_fixed_seed_sample_means_for_regret_and_average_updates() -> None:
    root_key = information_set_key(6, actor=0, own_rank=3, history="-")
    response_key = information_set_key(6, actor=1, own_rank=3, history="b@0")
    frozen_policy = _nonuniform_trainer(0)._freeze_policy()
    oracle = exact_external_sampling_targets(frozen_policy, (root_key, response_key))
    expected = {target.infoset_key: target for target in oracle.targets}
    sampled_regrets = {
        key: {action: 0.0 for action in expected[key].regret_deltas} for key in expected
    }
    sampled_sums = {
        key: {action: 0.0 for action in expected[key].strategy_sum_deltas} for key in expected
    }
    sample_count = 128

    for master_seed in range(sample_count):
        trace = _nonuniform_trainer(master_seed).run_iteration(1)
        for key in expected:
            regrets = _update_values(trace.update.regret_deltas, key)
            strategy_sums = _update_values(trace.update.strategy_sum_deltas, key)
            for action in sampled_regrets[key]:
                sampled_regrets[key][action] += regrets.get(action, 0.0)
                sampled_sums[key][action] += strategy_sums.get(action, 0.0)

    for key, target in expected.items():
        for action, value in target.regret_deltas.items():
            assert sampled_regrets[key][action] / sample_count == pytest.approx(
                float(value), abs=0.6
            )
        for action, value in target.strategy_sum_deltas.items():
            assert sampled_sums[key][action] / sample_count == pytest.approx(float(value), abs=0.12)


def test_n6_oracle_and_production_pass_disable_average_updates_before_start_iteration() -> None:
    root_key = information_set_key(6, actor=0, own_rank=3, history="-")
    oracle = exact_external_sampling_targets(
        _nonuniform_trainer(0)._freeze_policy(),
        (root_key,),
        accumulate_average=False,
    )
    trainer = SynchronousExternalSamplingMCCFR(
        MCCFRConfig(
            player_count=6,
            iterations=2,
            master_seed=101,
            average_strategy_start_iteration=2,
        )
    )
    for node in trainer._nodes.values():
        first, second = node.actions
        node.regret_sum = {first: 1.0, second: 0.0}

    trace = trainer.run_iteration(1)

    assert fsum(float(value) for value in oracle.targets[0].strategy_sum_deltas.values()) == 0.0
    assert trace.update.strategy_sum_deltas == ()
