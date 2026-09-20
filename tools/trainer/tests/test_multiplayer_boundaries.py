import json
from pathlib import Path

import pytest

from multiplayer_cfr.mccfr import (
    MCCFRConfig,
    MCCFRError,
    MCCFRResult,
    SynchronousExternalSamplingMCCFR,
    run_audit_iteration,
    sample_n9_boundary,
    train,
)
from multiplayer_cfr.policy import (
    ARTIFACT_TYPE,
    PROBABILITY_UNITS,
    StrategyArtifactError,
    export_strategy,
    load_quantized_strategy,
)

# 9 人规则树的信息集总数，与闭式结构计数一致。
_N9_INFOSETS = 20736

# 策略产物允许出现的顶层字段；新增字段会让该集合不相等。
_ARTIFACT_FIELDS = {
    "schema_version",
    "artifact_type",
    "game",
    "training",
    "probability_units",
    "infosets",
    "quality",
    "resources",
}


def _n9_config() -> MCCFRConfig:
    return MCCFRConfig(
        player_count=9,
        iterations=1,
        master_seed=17,
        average_strategy_start_iteration=1,
    )


def test_n9_incremental_api_runs_iteration_and_completes_result() -> None:
    trainer = SynchronousExternalSamplingMCCFR(_n9_config())

    trace = trainer.run_iteration(1)

    assert len(trace.passes) == 9
    assert trainer.completed_iterations == 1
    assert trainer.completed_result().infoset_count == _N9_INFOSETS
    assert train(_n9_config()).infoset_count == _N9_INFOSETS


def test_n9_export_keeps_the_existing_artifact_schema(tmp_path: Path) -> None:
    result = train(_n9_config())

    path = tmp_path / "strategy.json"
    artifact = export_strategy(path, result, trainer_version="candidate-a-n9-v1")
    reloaded = load_quantized_strategy(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert artifact.resources["artifact_bytes"] == path.stat().st_size
    assert reloaded.identity.artifact_bytes == path.stat().st_size
    assert reloaded.artifact.game.player_count == 9
    assert len(reloaded.action_units) == _N9_INFOSETS
    assert set(payload) == _ARTIFACT_FIELDS
    assert payload["schema_version"] == 1
    assert payload["artifact_type"] == ARTIFACT_TYPE
    assert payload["probability_units"] == PROBABILITY_UNITS


def test_n9_keeps_the_boundary_sampling_entry_and_rejects_audit_iteration() -> None:
    boundary = sample_n9_boundary(master_seed=17, traverser=3)

    assert boundary.traverser == 3
    assert boundary.infoset_count == _N9_INFOSETS

    with pytest.raises(MCCFRError):
        run_audit_iteration(_n9_config(), {})


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
