from pathlib import Path

import pytest

from multiplayer_cfr.mccfr import (
    MCCFRConfig,
    MCCFRError,
    MCCFRResult,
    SynchronousExternalSamplingMCCFR,
    sample_n9_boundary,
    train,
)
from multiplayer_cfr.policy import StrategyArtifactError, export_strategy


def _n9_config() -> MCCFRConfig:
    return MCCFRConfig(
        player_count=9,
        iterations=1,
        master_seed=17,
        average_strategy_start_iteration=1,
    )


def test_n9_rejects_iteration_training_result_and_top_level_train() -> None:
    trainer = SynchronousExternalSamplingMCCFR(_n9_config())

    with pytest.raises(MCCFRError):
        trainer.run_iteration(1)
    with pytest.raises(MCCFRError):
        trainer.completed_result()
    with pytest.raises(MCCFRError):
        train(_n9_config())

    boundary = sample_n9_boundary(master_seed=17, traverser=3)
    assert boundary.traverser == 3
    assert boundary.infoset_count == 20736


def test_n9_manual_result_cannot_bypass_strategy_export(tmp_path: Path) -> None:
    result = MCCFRResult(
        config=_n9_config(),
        average_strategy={},
        infoset_count=0,
        completed_iterations=1,
    )

    with pytest.raises(StrategyArtifactError):
        export_strategy(
            tmp_path / "strategy.json", result, trainer_version="candidate-a-boundary-v1"
        )
