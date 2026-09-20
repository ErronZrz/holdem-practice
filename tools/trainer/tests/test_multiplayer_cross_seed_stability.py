import copy
from pathlib import Path

import pytest

from multiplayer_cfr.cross_seed_stability import (
    CROSS_SEED_STABILITY_SCHEMA_VERSION,
    CROSS_SEED_STABILITY_TYPE,
    CrossSeedStabilityError,
    SealedStrategySample,
    StabilitySource,
    build_cross_seed_stability_record,
    load_cross_seed_stability_record,
    parse_cross_seed_stability_payload,
    read_sealed_strategy,
    write_cross_seed_stability_record,
)
from multiplayer_cfr.game import infoset_by_key, infosets
from multiplayer_cfr.mccfr import MCCFRConfig, MCCFRResult
from multiplayer_cfr.measurement import audit_infosets_sha256, seed_set_sha256
from multiplayer_cfr.policy import export_strategy

_UNITS = 1000


def _uniform_units(player_count: int, units: int = _UNITS) -> dict[str, dict[str, int]]:
    """构造每个信息集均匀分配概率单位的策略，用于不依赖训练的聚合测试。"""

    return {
        spec.key: {action.value: units // len(spec.actions) for action in spec.actions}
        for spec in infosets(player_count)
    }


def _sample(seed: int, units: dict[str, dict[str, int]]) -> SealedStrategySample:
    return SealedStrategySample(
        seed=seed,
        units=units,
        source=StabilitySource(seed=seed, strategy_sha256="a" * 64, strategy_bytes=128),
    )


def _result(*, master_seed: int, deviate: bool = False) -> MCCFRResult:
    """构造一个可直接导出的完整结果；deviate 时让单个信息集偏离均匀。"""

    config = MCCFRConfig(
        player_count=6,
        iterations=1,
        master_seed=master_seed,
        average_strategy_start_iteration=1,
    )
    strategy = {
        spec.key: {action: 1.0 / len(spec.actions) for action in spec.actions}
        for spec in infosets(6)
    }
    if deviate:
        key = sorted(strategy)[0]
        first, second = infoset_by_key(6)[key].actions
        strategy[key] = {first: 0.4, second: 0.6}
    return MCCFRResult(
        config=config,
        average_strategy=strategy,
        infoset_count=len(strategy),
        completed_iterations=1,
    )


def _export(tmp_path: Path, name: str, *, master_seed: int, deviate: bool = False) -> Path:
    path = tmp_path / name
    export_strategy(
        path, _result(master_seed=master_seed, deviate=deviate), trainer_version="stability-test-v1"
    )
    return path


@pytest.mark.parametrize("player_count", [6, 7, 9])
def test_cross_seed_record_identity_follows_the_audit_set(player_count: int) -> None:
    uniform = _uniform_units(player_count)

    record = build_cross_seed_stability_record(
        player_count=player_count,
        samples=[_sample(1, dict(uniform)), _sample(2, dict(uniform))],
        probability_units=_UNITS,
    )

    stability = record.payload["stability"]
    assert record.payload["record_type"] == CROSS_SEED_STABILITY_TYPE
    assert record.payload["schema_version"] == CROSS_SEED_STABILITY_SCHEMA_VERSION
    assert stability["status"] == "measured"
    assert stability["max_l1"] == {"numerator": "0", "denominator": "1"}
    assert stability["seed_set_sha256"] == seed_set_sha256([1, 2])
    assert stability["audit_infosets_sha256"] == audit_infosets_sha256(player_count)
    assert [source["seed"] for source in record.payload["sources"]] == [1, 2]


def test_cross_seed_record_aggregates_sealed_strategies(tmp_path: Path) -> None:
    left = read_sealed_strategy(_export(tmp_path, "left.json", master_seed=1215))
    right = read_sealed_strategy(
        _export(tmp_path, "right.json", master_seed=3311, deviate=True)
    )

    record = build_cross_seed_stability_record(
        player_count=6, samples=[left, right], probability_units=1_000_000_000_000
    )

    # 两个来源按 seed 升序排列，且指标精确等于单信息集 0.4 / 0.6 的 L1 距离。
    assert [source["seed"] for source in record.payload["sources"]] == [1215, 3311]
    assert record.payload["stability"]["max_l1"] == {"numerator": "1", "denominator": "5"}
    assert record.payload["sources"][0]["strategy_sha256"] == left.source.strategy_sha256


def test_cross_seed_record_round_trips_through_canonical_json(tmp_path: Path) -> None:
    uniform = _uniform_units(6)
    record = build_cross_seed_stability_record(
        player_count=6,
        samples=[_sample(1, dict(uniform)), _sample(2, dict(uniform))],
        probability_units=_UNITS,
    )

    written = write_cross_seed_stability_record(tmp_path, "stability.json", record)
    loaded = load_cross_seed_stability_record(tmp_path / "stability.json")

    assert loaded == written
    assert loaded.sha256 == record.sha256


def test_cross_seed_record_rejects_fewer_than_two_samples_or_duplicate_seeds() -> None:
    uniform = _uniform_units(6)

    with pytest.raises(CrossSeedStabilityError):
        build_cross_seed_stability_record(
            player_count=6, samples=[_sample(1, dict(uniform))], probability_units=_UNITS
        )

    with pytest.raises(CrossSeedStabilityError):
        build_cross_seed_stability_record(
            player_count=6,
            samples=[_sample(1, dict(uniform)), _sample(1, dict(uniform))],
            probability_units=_UNITS,
        )


def test_cross_seed_record_rejects_an_incomplete_audit_coverage() -> None:
    complete = _uniform_units(6)
    incomplete = dict(complete)
    incomplete.pop(sorted(incomplete)[0])

    with pytest.raises(CrossSeedStabilityError):
        build_cross_seed_stability_record(
            player_count=6,
            samples=[_sample(1, complete), _sample(2, incomplete)],
            probability_units=_UNITS,
        )


def test_cross_seed_record_rejects_a_tampered_seed_identity() -> None:
    uniform = _uniform_units(6)
    record = build_cross_seed_stability_record(
        player_count=6,
        samples=[_sample(1, dict(uniform)), _sample(2, dict(uniform))],
        probability_units=_UNITS,
    )

    tampered = copy.deepcopy(record.payload)
    tampered["stability"]["seed_set_sha256"] = "d" * 64
    with pytest.raises(CrossSeedStabilityError):
        parse_cross_seed_stability_payload(tampered)

    tampered = copy.deepcopy(record.payload)
    tampered["stability"]["audit_infosets_sha256"] = "d" * 64
    with pytest.raises(CrossSeedStabilityError):
        parse_cross_seed_stability_payload(tampered)


def test_cross_seed_record_rejects_a_non_measured_stability_section() -> None:
    uniform = _uniform_units(6)
    record = build_cross_seed_stability_record(
        player_count=6,
        samples=[_sample(1, dict(uniform)), _sample(2, dict(uniform))],
        probability_units=_UNITS,
    )

    tampered = copy.deepcopy(record.payload)
    tampered["stability"] = {
        "status": "not-requested",
        "seed_set_sha256": None,
        "audit_infosets_sha256": None,
        "max_l1": None,
    }

    with pytest.raises(CrossSeedStabilityError):
        parse_cross_seed_stability_payload(tampered)


def test_cross_seed_record_rejects_a_mismatched_game_version() -> None:
    uniform = _uniform_units(6)
    record = build_cross_seed_stability_record(
        player_count=6,
        samples=[_sample(1, dict(uniform)), _sample(2, dict(uniform))],
        probability_units=_UNITS,
    )

    tampered = copy.deepcopy(record.payload)
    tampered["game"]["version"] = "m8-a-v2"

    with pytest.raises(CrossSeedStabilityError):
        parse_cross_seed_stability_payload(tampered)
