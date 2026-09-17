from math import fsum

import pytest

from kuhn_cfr.cfr import DEFAULT_ITERATIONS, TrainingConfig, _InfoSetNode, train
from kuhn_cfr.game import Action
from kuhn_cfr.quality import evaluate_quality


def test_regret_matching_uses_uniform_distribution_without_positive_regret() -> None:
    node = _InfoSetNode((Action.CHECK, Action.BET))

    assert node.current_strategy() == {Action.CHECK: 0.5, Action.BET: 0.5}
    node.regret_sum = {Action.CHECK: -2.0, Action.BET: 0.0}
    assert node.current_strategy() == {Action.CHECK: 0.5, Action.BET: 0.5}


def test_regret_matching_is_non_negative_and_normalized() -> None:
    node = _InfoSetNode((Action.CHECK, Action.BET))
    node.regret_sum = {Action.CHECK: 3.0, Action.BET: 1.0}

    strategy = node.current_strategy()

    assert strategy == {Action.CHECK: 0.75, Action.BET: 0.25}
    assert all(probability >= 0.0 for probability in strategy.values())
    assert fsum(strategy.values()) == pytest.approx(1.0)


def test_average_strategy_is_non_negative_and_normalized() -> None:
    result = train(TrainingConfig(iterations=200, seed=9))

    assert result.infoset_count == 12
    for probabilities in result.average_strategy.values():
        assert all(probability >= 0.0 for probability in probabilities.values())
        assert fsum(probabilities.values()) == pytest.approx(1.0)


def test_training_is_deterministic_for_same_configuration() -> None:
    config = TrainingConfig(iterations=300, seed=17)

    first = train(config)
    second = train(config)

    assert first == second
    assert evaluate_quality(first.average_strategy) == evaluate_quality(second.average_strategy)


def test_default_training_reaches_the_kuhn_quality_threshold() -> None:
    result = train(TrainingConfig(iterations=DEFAULT_ITERATIONS, seed=0))
    quality = evaluate_quality(result.average_strategy)

    assert quality.nash_conv <= 0.05
    assert quality.exploitability == pytest.approx(quality.nash_conv / 2.0)
    assert result.elapsed_seconds < 7_200


@pytest.mark.parametrize(
    "config",
    [
        TrainingConfig(iterations=1, average_strategy_start_iteration=1),
        TrainingConfig(iterations=5, average_strategy_start_iteration=5),
    ],
)
def test_valid_training_configurations(config: TrainingConfig) -> None:
    assert config.iterations >= config.average_strategy_start_iteration


@pytest.mark.parametrize(
    "kwargs",
    [
        {"iterations": 0},
        {"iterations": -1},
        {"iterations": 5, "average_strategy_start_iteration": 0},
        {"iterations": 5, "average_strategy_start_iteration": 6},
        {"iterations": 5, "seed": True},
    ],
)
def test_invalid_training_configurations_are_rejected(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        TrainingConfig(**kwargs)
