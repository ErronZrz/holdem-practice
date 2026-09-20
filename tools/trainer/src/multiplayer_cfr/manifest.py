"""候选 A 实验与阈值 probe 的冻结 manifest 契约。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .game import GAME_ID, GAME_VERSION, validate_player_count
from .mccfr import MCCFRConfig
from .policy import MAX_ARTIFACT_BYTES, PROBABILITY_UNITS
from .resources import estimate_resources
from .safeio import (
    MAX_TEXT_BYTES,
    SafeJsonError,
    canonical_json_bytes,
    load_canonical_json,
    sha256_identity,
    write_canonical_json,
)

EXPERIMENT_MANIFEST_TYPE = "multiplayer-cfr-experiment"
PROBE_MANIFEST_TYPE = "multiplayer-cfr-threshold-probes"
MANIFEST_SCHEMA_VERSION = 1
EVALUATOR_ID = "candidate-a-full-chance-evaluator"
EVALUATOR_VERSION = "v1"

_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")


class ManifestError(ValueError):
    """冻结 manifest、预算或从 manifest 派生的实验计划不符合契约时抛出。"""


@dataclass(frozen=True)
class ManifestIdentity:
    """由安全读取的规范 manifest 字节派生的不可变身份。"""

    manifest_type: str
    schema_version: int
    manifest_id: str
    sha256: str
    byte_length: int

    def as_payload(self) -> dict[str, object]:
        return {
            "manifest_type": self.manifest_type,
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
        }


@dataclass(frozen=True)
class ProbeSpec:
    """预注册的、只读自身 rank 与公开阶段的阈值策略。"""

    probe_id: str
    open_threshold: int
    call_threshold: int


@dataclass(frozen=True)
class ProbeManifest:
    """与游戏和固定 evaluator 绑定的阈值 probe manifest。"""

    identity: ManifestIdentity
    player_count: int
    probes: tuple[ProbeSpec, ...]


@dataclass(frozen=True)
class StageBudget:
    """单阶段墙钟预算，单位为整数毫秒。"""

    name: str
    wall_time_milliseconds: int


@dataclass(frozen=True)
class ArtifactSlot:
    """受限根目录内预声明的单个工件槽位。"""

    relative_name: str
    maximum_bytes: int


@dataclass(frozen=True)
class ExperimentManifest:
    """训练前冻结的 A6/A7、N9 长期训练或 N9 boundary 实验定义。"""

    identity: ManifestIdentity
    code_commit: str
    trainer_version: str
    player_count: int
    execution_kind: str
    iterations: int
    average_strategy_start_iteration: int | None
    master_seed: int
    n9_traverser: int | None
    profile_mode: str
    probe_manifest_ref: ManifestIdentity | None
    cpu_limit_milliseconds: int
    max_concurrency: int
    rss_warning_bytes: int
    rss_hard_limit_bytes: int
    retained_artifact_limit_bytes: int
    stages: tuple[StageBudget, ...]
    strategy_slot: ArtifactSlot | None
    measurement_slot: ArtifactSlot


@dataclass(frozen=True)
class ExperimentPlan:
    """仅由已验证 manifest 唯一派生的运行与评估计划。"""

    manifest: ExperimentManifest
    probe_manifest: ProbeManifest | None
    training_config: MCCFRConfig | None
    stage_budgets: dict[str, StageBudget]


@dataclass(frozen=True)
class LoadedManifest:
    """保留验证后的 manifest payload、规范原始字节及强类型定义。"""

    payload: dict[str, object]
    raw_bytes: bytes
    value: ExperimentManifest | ProbeManifest


def create_probe_manifest(payload: dict[str, object]) -> LoadedManifest:
    """验证内存 probe payload 并为其规范字节创建身份。"""

    parsed = _parse_probe_payload(payload)
    canonical = canonical_json_bytes(parsed)
    identity = _identity_from_payload(parsed, canonical)
    game = cast(dict[str, object], parsed["game"])
    return LoadedManifest(
        payload=parsed,
        raw_bytes=canonical,
        value=ProbeManifest(
            identity,
            _require_int(game["player_count"], "probe manifest game.player_count", minimum=0),
            _probe_specs_from_payload(parsed["probes"]),
        ),
    )


def create_experiment_manifest(payload: dict[str, object]) -> LoadedManifest:
    """验证内存 experiment payload 并为其规范字节创建身份。"""

    parsed = _parse_experiment_payload(payload)
    canonical = canonical_json_bytes(parsed)
    identity = _identity_from_payload(parsed, canonical)
    return LoadedManifest(
        payload=parsed,
        raw_bytes=canonical,
        value=_experiment_from_payload(parsed, identity),
    )


def write_probe_manifest(
    root: str | Path, relative_name: str, manifest: LoadedManifest
) -> ProbeManifest:
    """原子写入已验证 probe manifest，并回读其真实身份。"""

    if not isinstance(manifest.value, ProbeManifest):
        raise ManifestError("写入对象必须是已验证的 probe manifest")
    write_canonical_json(root, relative_name, manifest.payload, maximum_bytes=MAX_TEXT_BYTES)
    return load_probe_manifest(Path(root) / relative_name)


def write_experiment_manifest(
    root: str | Path, relative_name: str, manifest: LoadedManifest
) -> ExperimentManifest:
    """原子写入已验证 experiment manifest，并回读其真实身份。"""

    if not isinstance(manifest.value, ExperimentManifest):
        raise ManifestError("写入对象必须是已验证的 experiment manifest")
    write_canonical_json(root, relative_name, manifest.payload, maximum_bytes=MAX_TEXT_BYTES)
    return load_experiment_manifest(Path(root) / relative_name)


def load_probe_manifest_document(path: str | Path) -> LoadedManifest:
    """安全读取 probe manifest，并保留用于执行快照的同一份规范字节。"""

    payload, raw_bytes = _load_json(path)
    parsed = _parse_probe_payload(payload)
    identity = _identity_from_payload(parsed, raw_bytes)
    game = cast(dict[str, object], parsed["game"])
    return LoadedManifest(
        payload=parsed,
        raw_bytes=raw_bytes,
        value=ProbeManifest(
            identity,
            _require_int(game["player_count"], "probe manifest game.player_count", minimum=0),
            _probe_specs_from_payload(parsed["probes"]),
        ),
    )


def load_probe_manifest(path: str | Path) -> ProbeManifest:
    """安全读取并严格验证一个预注册阈值 probe manifest。"""

    document = load_probe_manifest_document(path)
    assert isinstance(document.value, ProbeManifest)
    return document.value


def load_experiment_manifest_document(path: str | Path) -> LoadedManifest:
    """安全读取 experiment manifest，并保留用于执行快照的同一份规范字节。"""

    payload, raw_bytes = _load_json(path)
    parsed = _parse_experiment_payload(payload)
    identity = _identity_from_payload(parsed, raw_bytes)
    return LoadedManifest(
        payload=parsed,
        raw_bytes=raw_bytes,
        value=_experiment_from_payload(parsed, identity),
    )


def load_experiment_manifest(path: str | Path) -> ExperimentManifest:
    """安全读取并严格验证一个实验 manifest。"""

    document = load_experiment_manifest_document(path)
    assert isinstance(document.value, ExperimentManifest)
    return document.value


def derive_experiment_plan(
    manifest: ExperimentManifest,
    probe_manifest: ProbeManifest | None,
) -> ExperimentPlan:
    """从冻结 manifest 唯一派生训练、预算与评估计划。"""

    if not isinstance(manifest, ExperimentManifest):
        raise ManifestError("实验计划必须来自已验证的 experiment manifest")
    if manifest.probe_manifest_ref is None:
        if probe_manifest is not None:
            raise ManifestError("实验 manifest 未引用 probe 时不能注入 probe manifest")
    elif probe_manifest is None or probe_manifest.identity != manifest.probe_manifest_ref:
        raise ManifestError("probe manifest 身份与 experiment manifest 引用不匹配")
    if probe_manifest is not None and probe_manifest.player_count != manifest.player_count:
        raise ManifestError("probe manifest 人数与 experiment manifest 不匹配")

    stage_budgets = {stage.name: stage for stage in manifest.stages}
    if manifest.execution_kind in {"a6-a7-training", "a9-training"}:
        assert manifest.average_strategy_start_iteration is not None
        training_config = MCCFRConfig(
            player_count=manifest.player_count,
            iterations=manifest.iterations,
            master_seed=manifest.master_seed,
            average_strategy_start_iteration=manifest.average_strategy_start_iteration,
        )
    else:
        training_config = None
    return ExperimentPlan(
        manifest=manifest,
        probe_manifest=probe_manifest,
        training_config=training_config,
        stage_budgets=stage_budgets,
    )


def _load_json(path: str | Path) -> tuple[dict[str, Any], bytes]:
    try:
        return load_canonical_json(path, maximum_bytes=MAX_TEXT_BYTES)
    except SafeJsonError as error:
        raise ManifestError("无法安全读取规范 manifest") from error


def _identity_from_payload(payload: dict[str, object], raw_bytes: bytes) -> ManifestIdentity:
    manifest_type = payload["manifest_type"]
    manifest_id = payload["manifest_id"]
    schema_version = payload["schema_version"]
    assert isinstance(manifest_type, str)
    assert isinstance(manifest_id, str)
    assert isinstance(schema_version, int)
    digest, byte_length = sha256_identity(raw_bytes)
    return ManifestIdentity(manifest_type, schema_version, manifest_id, digest, byte_length)


def _parse_probe_payload(value: object) -> dict[str, object]:
    payload = _exact_keys(
        value,
        {"schema_version", "manifest_type", "manifest_id", "game", "evaluator", "probes"},
        "probe manifest",
    )
    _require_manifest_header(payload, PROBE_MANIFEST_TYPE)
    player_count = _parse_game(payload["game"])
    evaluator = _exact_keys(
        payload["evaluator"],
        {"evaluator_id", "evaluator_version", "probability_units"},
        "probe manifest.evaluator",
    )
    if (
        evaluator["evaluator_id"] != EVALUATOR_ID
        or evaluator["evaluator_version"] != EVALUATOR_VERSION
        or _require_int(
            evaluator["probability_units"], "probe evaluator probability units", minimum=1
        )
        != PROBABILITY_UNITS
    ):
        raise ManifestError("probe manifest evaluator 不兼容")
    probes = _parse_probe_specs(payload["probes"], player_count)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": PROBE_MANIFEST_TYPE,
        "manifest_id": payload["manifest_id"],
        "game": _game_payload(player_count),
        "evaluator": {
            "evaluator_id": EVALUATOR_ID,
            "evaluator_version": EVALUATOR_VERSION,
            "probability_units": PROBABILITY_UNITS,
        },
        "probes": [
            {
                "probe_id": probe.probe_id,
                "open_threshold": probe.open_threshold,
                "call_threshold": probe.call_threshold,
            }
            for probe in probes
        ],
    }


def _parse_experiment_payload(value: object) -> dict[str, object]:
    payload = _exact_keys(
        value,
        {
            "schema_version",
            "manifest_type",
            "manifest_id",
            "code_identity",
            "game",
            "execution",
            "quality",
            "budget",
            "artifacts",
        },
        "experiment manifest",
    )
    _require_manifest_header(payload, EXPERIMENT_MANIFEST_TYPE)
    player_count = _parse_game(payload["game"])
    code_identity = _parse_code_identity(payload["code_identity"])
    execution = _parse_execution(payload["execution"], player_count)
    execution_kind = _require_string(execution["kind"], "execution.kind")
    quality = _parse_quality(payload["quality"], player_count, execution_kind)
    budget = _parse_budget(payload["budget"], execution_kind)
    artifacts = _parse_artifacts(payload["artifacts"], player_count, execution_kind, budget)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "manifest_type": EXPERIMENT_MANIFEST_TYPE,
        "manifest_id": payload["manifest_id"],
        "code_identity": code_identity,
        "game": _game_payload(player_count),
        "execution": execution,
        "quality": quality,
        "budget": budget,
        "artifacts": artifacts,
    }


def _experiment_from_payload(
    payload: dict[str, object], identity: ManifestIdentity
) -> ExperimentManifest:
    code_identity = payload["code_identity"]
    game = payload["game"]
    execution = payload["execution"]
    quality = payload["quality"]
    budget = payload["budget"]
    artifacts = payload["artifacts"]
    assert isinstance(code_identity, dict)
    assert isinstance(game, dict)
    assert isinstance(execution, dict)
    assert isinstance(quality, dict)
    assert isinstance(budget, dict)
    assert isinstance(artifacts, dict)
    parsed_stages = cast(list[dict[str, object]], budget["stages"])
    stages = tuple(
        StageBudget(
            _require_string(stage["name"], "stage.name"),
            _require_int(
                stage["wall_time_milliseconds"], "stage.wall_time_milliseconds", minimum=1
            ),
        )
        for stage in parsed_stages
    )
    probe_ref = quality["probe_manifest"]
    strategy_slot = _slot_from_payload(artifacts["strategy"])
    measurement_slot = _slot_from_payload(artifacts["measurement"])
    if measurement_slot is None:
        raise ManifestError("experiment manifest 必须声明 measurement 槽位")
    return ExperimentManifest(
        identity=identity,
        code_commit=_require_string(code_identity["git_commit"], "code_identity.git_commit"),
        trainer_version=_require_string(
            code_identity["trainer_version"], "code_identity.trainer_version"
        ),
        player_count=_require_int(game["player_count"], "game.player_count", minimum=0),
        execution_kind=_require_string(execution["kind"], "execution.kind"),
        iterations=_require_int(execution.get("iterations", 1), "execution.iterations", minimum=1),
        average_strategy_start_iteration=cast(
            int | None, execution.get("average_strategy_start_iteration")
        ),
        master_seed=_require_integer(execution["master_seed"], "execution.master_seed"),
        n9_traverser=cast(int | None, execution.get("traverser")),
        profile_mode=_require_string(quality["profile_mode"], "quality.profile_mode"),
        probe_manifest_ref=_identity_from_reference(probe_ref) if probe_ref is not None else None,
        cpu_limit_milliseconds=_require_int(
            budget["cpu_limit_milliseconds"], "budget.cpu_limit_milliseconds", minimum=1
        ),
        max_concurrency=_require_int(
            budget["max_concurrency"], "budget.max_concurrency", minimum=1
        ),
        rss_warning_bytes=_require_int(
            budget["rss_warning_bytes"], "budget.rss_warning_bytes", minimum=0
        ),
        rss_hard_limit_bytes=_require_int(
            budget["rss_hard_limit_bytes"], "budget.rss_hard_limit_bytes", minimum=1
        ),
        retained_artifact_limit_bytes=_require_int(
            budget["retained_artifact_limit_bytes"],
            "budget.retained_artifact_limit_bytes",
            minimum=1,
        ),
        stages=stages,
        strategy_slot=strategy_slot,
        measurement_slot=measurement_slot,
    )


def _parse_code_identity(value: object) -> dict[str, object]:
    code = _exact_keys(value, {"git_commit", "workspace_state", "trainer_version"}, "code_identity")
    commit = _require_string(code["git_commit"], "code_identity.git_commit")
    trainer_version = _require_string(code["trainer_version"], "code_identity.trainer_version")
    if (
        _COMMIT_PATTERN.fullmatch(commit) is None
        or _VERSION_PATTERN.fullmatch(trainer_version) is None
    ):
        raise ManifestError("code identity 格式不兼容")
    if code["workspace_state"] != "clean":
        raise ManifestError("实际实验 manifest 只允许干净工作区")
    return {"git_commit": commit, "workspace_state": "clean", "trainer_version": trainer_version}


def _parse_game(value: object) -> int:
    game = _exact_keys(value, {"id", "version", "player_count"}, "manifest.game")
    player_count = validate_player_count(
        _require_int(game["player_count"], "manifest.game.player_count", minimum=0)
    )
    if game["id"] != GAME_ID or game["version"] != GAME_VERSION:
        raise ManifestError("manifest 游戏版本不兼容")
    return player_count


def _game_payload(player_count: int) -> dict[str, object]:
    return {"id": GAME_ID, "version": GAME_VERSION, "player_count": player_count}


def _parse_execution(value: object, player_count: int) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManifestError("execution 必须是对象")
    kind = value.get("kind")
    if kind in {"a6-a7-training", "a9-training"}:
        execution = _exact_keys(
            value,
            {"kind", "iterations", "average_strategy_start_iteration", "master_seed"},
            "execution",
        )
        if kind == "a6-a7-training" and player_count not in {6, 7}:
            raise ManifestError("长期训练只允许 A6 或 A7")
        if kind == "a9-training" and player_count != 9:
            raise ManifestError("N9 长期训练只允许 9 名相对座位")
        iterations = _require_int(execution["iterations"], "execution.iterations", minimum=1)
        average_start = _require_int(
            execution["average_strategy_start_iteration"],
            "execution.average_strategy_start_iteration",
            minimum=1,
        )
        if average_start > iterations:
            raise ManifestError("平均策略起始轮次超出 iteration 范围")
        return {
            "kind": kind,
            "iterations": iterations,
            "average_strategy_start_iteration": average_start,
            "master_seed": _require_integer(execution["master_seed"], "execution.master_seed"),
        }
    if kind == "n9-boundary-sample":
        execution = _exact_keys(
            value, {"kind", "iteration", "traverser", "master_seed"}, "execution"
        )
        if (
            player_count != 9
            or _require_int(execution["iteration"], "execution.iteration", minimum=1) != 1
        ):
            raise ManifestError("N9 只允许 iteration 1 的单次边界采样")
        traverser = _require_int(execution["traverser"], "execution.traverser", minimum=0)
        if traverser >= 9:
            raise ManifestError("N9 boundary traverser 超出座位范围")
        return {
            "kind": kind,
            "iteration": 1,
            "traverser": traverser,
            "master_seed": _require_integer(execution["master_seed"], "execution.master_seed"),
        }
    raise ManifestError("execution.kind 不兼容")


def _parse_quality(value: object, player_count: int, execution_kind: str) -> dict[str, object]:
    quality = _exact_keys(value, {"profile_mode", "probe_manifest"}, "quality")
    profile_mode = quality["profile_mode"]
    reference = quality["probe_manifest"]
    if execution_kind in {"n9-boundary-sample", "a9-training"}:
        if profile_mode != "not-requested" or reference is not None:
            raise ManifestError("N9 执行类型不能请求 profile 或 probe")
    elif profile_mode not in {"full-chance", "not-requested"}:
        raise ManifestError("A6/A7 quality profile 模式不兼容")
    if reference is not None:
        _parse_identity_reference(reference, PROBE_MANIFEST_TYPE)
        if player_count not in {6, 7} or profile_mode != "full-chance":
            raise ManifestError("probe 只允许绑定 A6/A7 的完整 profile")
    return {"profile_mode": profile_mode, "probe_manifest": reference}


def _parse_budget(value: object, execution_kind: str) -> dict[str, object]:
    budget = _exact_keys(
        value,
        {
            "cpu_limit_milliseconds",
            "max_concurrency",
            "rss_warning_bytes",
            "rss_hard_limit_bytes",
            "retained_artifact_limit_bytes",
            "stages",
        },
        "budget",
    )
    warning = _require_int(budget["rss_warning_bytes"], "budget.rss_warning_bytes", minimum=0)
    hard = _require_int(budget["rss_hard_limit_bytes"], "budget.rss_hard_limit_bytes", minimum=1)
    if warning >= hard:
        raise ManifestError("RSS 预警阈值必须小于硬停阈值")
    if execution_kind in {"a6-a7-training", "a9-training"}:
        # 仅 N=6/7 的长期训练允许质量阶段，N=9 训练按三阶段冻结。
        expected_stages = (
            ("training", "export", "profile", "probe", "measurement")
            if execution_kind == "a6-a7-training"
            else ("training", "export", "measurement")
        )
    else:
        expected_stages = ("boundary", "measurement")
    stages = _parse_stages(budget["stages"], expected_stages)
    return {
        "cpu_limit_milliseconds": _require_int(
            budget["cpu_limit_milliseconds"], "budget.cpu_limit_milliseconds", minimum=1
        ),
        "max_concurrency": _require_int(
            budget["max_concurrency"], "budget.max_concurrency", minimum=1
        ),
        "rss_warning_bytes": warning,
        "rss_hard_limit_bytes": hard,
        "retained_artifact_limit_bytes": _require_int(
            budget["retained_artifact_limit_bytes"],
            "budget.retained_artifact_limit_bytes",
            minimum=1,
        ),
        "stages": stages,
    }


def _parse_stages(value: object, expected_names: tuple[str, ...]) -> list[dict[str, int | str]]:
    if not isinstance(value, list) or len(value) != len(expected_names):
        raise ManifestError("budget.stages 必须完整覆盖固定阶段")
    stages = []
    for entry in value:
        stage = _exact_keys(entry, {"name", "wall_time_milliseconds"}, "budget.stage")
        stages.append(
            {
                "name": _require_string(stage["name"], "budget.stage.name"),
                "wall_time_milliseconds": _require_int(
                    stage["wall_time_milliseconds"],
                    "budget.stage.wall_time_milliseconds",
                    minimum=1,
                ),
            }
        )
    if tuple(stage["name"] for stage in stages) != expected_names:
        raise ManifestError("budget.stages 必须按固定顺序完整覆盖")
    return stages


def _parse_artifacts(
    value: object,
    player_count: int,
    execution_kind: str,
    budget: dict[str, object],
) -> dict[str, object]:
    artifacts = _exact_keys(value, {"strategy", "measurement"}, "artifacts")
    strategy = artifacts["strategy"]
    if execution_kind == "n9-boundary-sample":
        if strategy is not None:
            raise ManifestError("N9 boundary 不允许声明策略工件")
        parsed_strategy = None
    else:
        parsed_strategy = _parse_slot(strategy, "artifacts.strategy")
        static_limit = min(
            MAX_ARTIFACT_BYTES, estimate_resources(player_count).artifact_budget_bytes
        )
        strategy_bytes = _require_int(
            parsed_strategy["maximum_bytes"], "artifacts.strategy.maximum_bytes", minimum=1
        )
        if strategy_bytes > static_limit:
            raise ManifestError("策略槽位超过候选 A 静态产物预算")
    measurement = _parse_slot(artifacts["measurement"], "artifacts.measurement")
    measurement_bytes = _require_int(
        measurement["maximum_bytes"], "artifacts.measurement.maximum_bytes", minimum=1
    )
    strategy_bytes = (
        0
        if parsed_strategy is None
        else _require_int(
            parsed_strategy["maximum_bytes"], "artifacts.strategy.maximum_bytes", minimum=1
        )
    )
    total_reserved = 2 * measurement_bytes + strategy_bytes
    retained_limit = _require_int(
        budget["retained_artifact_limit_bytes"],
        "budget.retained_artifact_limit_bytes",
        minimum=1,
    )
    if total_reserved > retained_limit:
        raise ManifestError("预声明工件槽位总和超过保留产物上限")
    return {"strategy": parsed_strategy, "measurement": measurement}


def _parse_slot(value: object, label: str) -> dict[str, object]:
    slot = _exact_keys(value, {"relative_name", "maximum_bytes"}, label)
    name = _require_string(slot["relative_name"], f"{label}.relative_name")
    if Path(name).is_absolute() or len(Path(name).parts) != 1 or Path(name).name != name:
        raise ManifestError(f"{label}.relative_name 不能包含目录")
    if not name.endswith(".json"):
        raise ManifestError(f"{label}.relative_name 必须使用 .json")
    return {
        "relative_name": name,
        "maximum_bytes": _require_int(slot["maximum_bytes"], f"{label}.maximum_bytes", minimum=1),
    }


def _slot_from_payload(value: object) -> ArtifactSlot | None:
    if value is None:
        return None
    assert isinstance(value, dict)
    return ArtifactSlot(value["relative_name"], value["maximum_bytes"])


def _parse_probe_specs(value: object, player_count: int) -> list[ProbeSpec]:
    if not isinstance(value, list) or not 1 <= len(value) <= 2:
        raise ManifestError("probe manifest 必须包含一至两组阈值策略")
    probes = []
    for entry in value:
        probe = _exact_keys(entry, {"probe_id", "open_threshold", "call_threshold"}, "probe")
        probes.append(
            ProbeSpec(
                probe_id=_require_string(probe["probe_id"], "probe.probe_id"),
                open_threshold=_require_rank_threshold(
                    probe["open_threshold"], player_count, "probe.open_threshold"
                ),
                call_threshold=_require_rank_threshold(
                    probe["call_threshold"], player_count, "probe.call_threshold"
                ),
            )
        )
    if [probe.probe_id for probe in probes] != sorted(probe.probe_id for probe in probes):
        raise ManifestError("probe 必须按 probe_id 递增排列")
    if len({probe.probe_id for probe in probes}) != len(probes):
        raise ManifestError("probe_id 不能重复")
    return probes


def _probe_specs_from_payload(value: object) -> tuple[ProbeSpec, ...]:
    if not isinstance(value, list):
        raise ManifestError("规范 probe payload 必须包含数组")
    return tuple(
        ProbeSpec(
            probe_id=entry["probe_id"],
            open_threshold=entry["open_threshold"],
            call_threshold=entry["call_threshold"],
        )
        for entry in value
        if isinstance(entry, dict)
    )


def _parse_identity_reference(value: object, expected_type: str) -> ManifestIdentity:
    reference = _exact_keys(
        value,
        {"manifest_type", "schema_version", "manifest_id", "sha256", "byte_length"},
        "manifest reference",
    )
    manifest_type = _require_string(reference["manifest_type"], "manifest reference.type")
    if manifest_type != expected_type:
        raise ManifestError("manifest reference 类型不兼容")
    return ManifestIdentity(
        manifest_type=manifest_type,
        schema_version=_require_int(
            reference["schema_version"], "manifest reference.schema", minimum=1
        ),
        manifest_id=_require_identifier(reference["manifest_id"], "manifest reference.id"),
        sha256=_require_hash(reference["sha256"], "manifest reference.sha256"),
        byte_length=_require_int(
            reference["byte_length"], "manifest reference.byte_length", minimum=1
        ),
    )


def _identity_from_reference(value: object) -> ManifestIdentity:
    return _parse_identity_reference(value, PROBE_MANIFEST_TYPE)


def _require_manifest_header(payload: dict[str, Any], expected_type: str) -> None:
    if (
        _require_int(payload["schema_version"], "manifest schema_version", minimum=1)
        != MANIFEST_SCHEMA_VERSION
    ):
        raise ManifestError("manifest schema 版本不兼容")
    if payload["manifest_type"] != expected_type:
        raise ManifestError("manifest 类型不兼容")
    _require_identifier(payload["manifest_id"], "manifest_id")


def _exact_keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ManifestError(f"{label} 字段不匹配")
    return value


def _require_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{label} 必须是整数")
    return value


def _require_int(value: object, label: str, *, minimum: int) -> int:
    value = _require_integer(value, label)
    if value < minimum:
        raise ManifestError(f"{label} 不能小于 {minimum}")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ManifestError(f"{label} 必须是长度受限的非空字符串")
    return value


def _require_identifier(value: object, label: str) -> str:
    value = _require_string(value, label)
    if _ID_PATTERN.fullmatch(value) is None:
        raise ManifestError(f"{label} 不是受控标识")
    return value


def _require_hash(value: object, label: str) -> str:
    value = _require_string(value, label)
    if _HASH_PATTERN.fullmatch(value) is None:
        raise ManifestError(f"{label} 必须是小写 SHA-256")
    return value


def _require_rank_threshold(value: object, player_count: int, label: str) -> int:
    value = _require_int(value, label, minimum=0)
    if value >= player_count:
        raise ManifestError(f"{label} 超出私有 rank 范围")
    return value
