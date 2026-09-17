import pytest

from kuhn_cfr.game import INFOSETS, Action, Player
from kuhn_cfr.policy import uniform_strategy
from kuhn_cfr.quality import best_response_value, evaluate_quality, expected_utility_p0


def _check_then_fold_strategy():
    strategy = uniform_strategy()
    for spec in INFOSETS:
        chosen = Action.CHECK if spec.history in {"", "x"} else Action.FOLD
        strategy[spec.key] = {action: 1.0 if action is chosen else 0.0 for action in spec.actions}
    return strategy


def test_exact_best_response_for_fixed_profile() -> None:
    strategy = _check_then_fold_strategy()

    quality = evaluate_quality(strategy)

    assert expected_utility_p0(strategy, strategy) == pytest.approx(0.0)
    assert best_response_value(Player.P0, strategy) == pytest.approx(1.0)
    assert best_response_value(Player.P1, strategy) == pytest.approx(1.0)
    assert quality.profile_value_p0 == pytest.approx(0.0)
    assert quality.best_response_value_p0 == pytest.approx(1.0)
    assert quality.best_response_value_p1 == pytest.approx(1.0)
    assert quality.nash_conv == pytest.approx(2.0)
    assert quality.exploitability == pytest.approx(1.0)


def test_best_response_uses_only_legal_pure_information_set_policies() -> None:
    strategy = _check_then_fold_strategy()

    value_p0 = best_response_value(Player.P0, strategy)
    value_p1 = best_response_value(Player.P1, strategy)

    assert value_p0 <= 1.0
    assert value_p1 <= 1.0
