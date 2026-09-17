import json
from math import fsum

import pytest

from kuhn_cfr.cfr import TrainingConfig, train
from kuhn_cfr.game import Action, Card, KuhnRuleError, Player
from kuhn_cfr.policy import (
    GAME_ID,
    GAME_VERSION,
    PROBABILITY_UNITS,
    StrategyArtifactError,
    TrainingMetadata,
    export_strategy,
    load_strategy,
    lookup,
)


def _metadata(iterations: int) -> TrainingMetadata:
    return TrainingMetadata(
        algorithm="vanilla-cfr-full-chance-v1",
        iterations=iterations,
        average_strategy_start_iteration=1,
        seed=0,
    )


def test_export_load_and_lookup_a_legal_infoset(tmp_path) -> None:
    result = train(TrainingConfig(iterations=200))
    artifact = export_strategy(tmp_path / "strategy.json", result.average_strategy, _metadata(200))

    probabilities = lookup(artifact, Player.P0, Card.QUEEN, "")

    assert artifact.metadata.iterations == 200
    assert artifact.metadata.seed == 0
    assert artifact.quality["nash_conv"] >= 0.0
    assert set(probabilities) == {Action.CHECK, Action.BET}
    assert fsum(probabilities.values()) == pytest.approx(1.0)


def test_identical_input_has_identical_canonical_export(tmp_path) -> None:
    result = train(TrainingConfig(iterations=300, seed=17))
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    first = export_strategy(first_path, result.average_strategy, _metadata(300))
    second = export_strategy(second_path, result.average_strategy, _metadata(300))

    assert first == second
    assert first_path.read_bytes() == second_path.read_bytes()


def test_loader_rejects_unknown_top_level_fields(tmp_path) -> None:
    result = train(TrainingConfig(iterations=20))
    path = tmp_path / "strategy.json"
    export_strategy(path, result.average_strategy, _metadata(20))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = "value"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StrategyArtifactError):
        load_strategy(path)


def test_loader_rejects_invalid_probability_units(tmp_path) -> None:
    result = train(TrainingConfig(iterations=20))
    path = tmp_path / "strategy.json"
    export_strategy(path, result.average_strategy, _metadata(20))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["infosets"][0]["actions"] = {"x": PROBABILITY_UNITS - 1, "b": 0}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StrategyArtifactError):
        load_strategy(path)


def test_loader_rejects_incompatible_game_version(tmp_path) -> None:
    result = train(TrainingConfig(iterations=20))
    path = tmp_path / "strategy.json"
    export_strategy(path, result.average_strategy, _metadata(20))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["game"] = {"id": GAME_ID, "version": f"{GAME_VERSION}-other"}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StrategyArtifactError):
        load_strategy(path)


def test_lookup_rejects_illegal_information_set(tmp_path) -> None:
    result = train(TrainingConfig(iterations=20))
    artifact = export_strategy(tmp_path / "strategy.json", result.average_strategy, _metadata(20))

    with pytest.raises(KuhnRuleError):
        lookup(artifact, Player.P1, Card.JACK, "")
