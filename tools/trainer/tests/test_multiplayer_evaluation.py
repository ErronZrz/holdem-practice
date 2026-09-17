from fractions import Fraction
from pathlib import Path

import pytest

from multiplayer_cfr.evaluation import (
    EvaluationError,
    EvaluationStopped,
    ThresholdProbe,
    evaluate_profile,
    evaluate_threshold_probes,
)
from multiplayer_cfr.game import GameConfig, infosets
from multiplayer_cfr.mccfr import MCCFRConfig, MCCFRResult
from multiplayer_cfr.policy import (
    QuantizedStrategyArtifact,
    StrategyArtifact,
    StrategyArtifactIdentity,
    export_strategy,
    load_quantized_strategy,
)


def _deterministic_result(player_count: int) -> MCCFRResult:
    config = MCCFRConfig(
        player_count=player_count,
        iterations=1,
        master_seed=211,
        average_strategy_start_iteration=1,
    )
    strategy = {
        spec.key: {action: 1.0 if action is spec.actions[0] else 0.0 for action in spec.actions}
        for spec in infosets(player_count)
    }
    return MCCFRResult(
        config=config,
        average_strategy=strategy,
        infoset_count=len(strategy),
        completed_iterations=1,
    )


def _quantized_artifact(tmp_path: Path, player_count: int) -> QuantizedStrategyArtifact:
    path = tmp_path / f"a{player_count}.json"
    export_strategy(
        path, _deterministic_result(player_count), trainer_version="candidate-a-evaluator-v1"
    )
    return load_quantized_strategy(path)


def test_a6_and_a7_quantized_profiles_preserve_exact_constant_sum(tmp_path: Path) -> None:
    for player_count in (6, 7):
        profile = evaluate_profile(_quantized_artifact(tmp_path, player_count))

        assert profile.ordered_deal_count == {6: 720, 7: 5040}[player_count]
        assert profile.terminal_leaf_count == profile.ordered_deal_count
        assert profile.utilities == (Fraction(0),) * player_count


def test_threshold_probes_use_only_rank_and_public_phase(tmp_path: Path) -> None:
    artifact = _quantized_artifact(tmp_path, 6)
    probes = (
        ThresholdProbe("median", open_threshold=3, call_threshold=3),
        ThresholdProbe("high-open", open_threshold=5, call_threshold=3),
    )

    evaluated = evaluate_threshold_probes(artifact, probes)

    assert len(evaluated.results) == 12
    assert len(evaluated.gains) == 6
    assert all(gain >= 0 for gain in evaluated.gains)
    assert all(result.probe_id in {"median", "high-open"} for result in evaluated.results)


def test_evaluator_stops_only_at_deal_checkpoint_and_rejects_n9_full_chance(tmp_path: Path) -> None:
    artifact = _quantized_artifact(tmp_path, 6)

    with pytest.raises(EvaluationStopped):
        evaluate_profile(artifact, checkpoint=lambda completed_deals: completed_deals < 1)

    n9 = QuantizedStrategyArtifact(
        artifact=StrategyArtifact(
            game=GameConfig(9),
            strategy={},
            training={},
            quality={},
            resources={},
        ),
        action_units={},
        identity=StrategyArtifactIdentity(sha256="0" * 64, artifact_bytes=1),
    )
    with pytest.raises(EvaluationError):
        evaluate_profile(n9)
