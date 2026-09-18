"""manifest 驱动实验的机械绑定测量记录。"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from .control import ControlledTrainingResult, N9BoundaryResult
from .evaluation import ManifestedEvaluation, ProbeEvaluation, ProfileEvaluation
from .manifest import EVALUATOR_ID, EVALUATOR_VERSION, ExperimentPlan
from .policy import ARTIFACT_TYPE, QuantizedStrategyArtifact
from .policy import SCHEMA_VERSION as STRATEGY_SCHEMA_VERSION
from .safeio import (
    MAX_TEXT_BYTES,
    SafeJsonError,
    canonical_json_bytes,
    load_canonical_json,
    sha256_identity,
    write_canonical_json,
)

EXPERIMENT_RECORD_TYPE = "multiplayer-cfr-manifested-measurement"
EXPERIMENT_RECORD_SCHEMA_VERSION = 1
_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")

# 精确有理数的位数只受规则树深度约束：每个动作的概率分母整除 10^12，单条历史至多
# 2N-1 个动作，因此 N=9 的分母理论上界也远小于该值。它不适用标识符字段的短上限。
MAX_RATIONAL_DIGITS = 4_096


class ExperimentRecordError(ValueError):
    """manifest 驱动测量记录的身份、阶段或规范 JSON 不一致时抛出。"""


@dataclass(frozen=True)
class SupervisorIdentity:
    """外层监督器的声明性身份；真实硬限制仍由该监督器负责实施。"""

    supervisor_id: str
    supervisor_version: str
    rss_scope: str
    enforcement_mode: str

    def __post_init__(self) -> None:
        if _ID_PATTERN.fullmatch(self.supervisor_id) is None:
            raise ExperimentRecordError("监督器标识不受控")
        if _ID_PATTERN.fullmatch(self.supervisor_version) is None:
            raise ExperimentRecordError("监督器版本不受控")
        if self.rss_scope != "process-tree" or self.enforcement_mode != "external-hard-limit":
            raise ExperimentRecordError("实际实验记录必须声明进程树外部硬监督")

    def as_payload(self) -> dict[str, str]:
        return {
            "supervisor_id": self.supervisor_id,
            "supervisor_version": self.supervisor_version,
            "rss_scope": self.rss_scope,
            "enforcement_mode": self.enforcement_mode,
        }


@dataclass(frozen=True)
class ExperimentRecord:
    """已规范化的 manifest 驱动测量记录及其字节身份。"""

    payload: dict[str, object]
    sha256: str
    record_bytes: int


def build_manifested_measurement_record(
    *,
    plan: ExperimentPlan,
    supervisor: SupervisorIdentity,
    training: ControlledTrainingResult | None = None,
    boundary: N9BoundaryResult | None = None,
    artifact: QuantizedStrategyArtifact | None = None,
    evaluation: ManifestedEvaluation | None = None,
) -> ExperimentRecord:
    """只从已验证计划、运行回执、量化策略和评估结果构造测量记录。"""

    if not isinstance(plan, ExperimentPlan) or not isinstance(supervisor, SupervisorIdentity):
        raise ExperimentRecordError("测量记录必须由已验证计划和监督器身份构造")
    manifest = plan.manifest
    if manifest.execution_kind == "a6-a7-training":
        if training is None or boundary is not None:
            raise ExperimentRecordError("A6/A7 记录必须关联唯一训练回执")
        execution, diagnostics, resources = _training_sections(training, supervisor, plan)
        if training.result is None:
            if artifact is not None or evaluation is not None:
                raise ExperimentRecordError("停止的训练不能关联策略或质量评估")
        else:
            _validate_artifact(plan, artifact)
            _validate_evaluation(plan, artifact, evaluation)
    else:
        if (
            boundary is None
            or training is not None
            or artifact is not None
            or evaluation is not None
        ):
            raise ExperimentRecordError("N9 boundary 记录不能关联训练结果、策略或质量评估")
        execution, diagnostics, resources = _boundary_sections(boundary, supervisor, plan)

    payload = {
        "schema_version": EXPERIMENT_RECORD_SCHEMA_VERSION,
        "record_type": EXPERIMENT_RECORD_TYPE,
        "experiment_manifest": manifest.identity.as_payload(),
        "game": {
            "id": "m8-unique-rank-single-open",
            "version": "m8-a-v1",
            "player_count": manifest.player_count,
        },
        "execution": execution,
        "supervisor": supervisor.as_payload(),
        "strategy": strategy_identity_payload(artifact),
        "profile": _profile_payload(evaluation.profile if evaluation is not None else None),
        "probes": _probes_payload(evaluation.probes if evaluation is not None else None),
        "diagnostics": diagnostics,
        "resources": resources,
    }
    _validate_payload(payload)
    raw_bytes = canonical_json_bytes(payload)
    digest, byte_length = sha256_identity(raw_bytes)
    return ExperimentRecord(payload=payload, sha256=digest, record_bytes=byte_length)


def write_manifested_measurement_record(
    root: str | Path,
    relative_name: str,
    record: ExperimentRecord,
    *,
    maximum_bytes: int,
) -> ExperimentRecord:
    """原子写入由 builder 创建的测量记录并回读身份。"""

    if not isinstance(record, ExperimentRecord):
        raise ExperimentRecordError("写入对象必须是 manifest 驱动测量记录")
    _validate_payload(record.payload)
    _, raw_bytes = write_canonical_json(
        root, relative_name, record.payload, maximum_bytes=maximum_bytes
    )
    loaded = load_manifested_measurement_record(Path(root) / relative_name)
    if loaded.sha256 != record.sha256 or loaded.record_bytes != len(raw_bytes):
        raise ExperimentRecordError("测量记录回读身份不一致")
    return loaded


def parse_manifested_measurement_payload(payload: dict[str, object]) -> ExperimentRecord:
    """严格验证内嵌的规范 child payload，并重算其唯一字节身份。"""

    _validate_payload(payload)
    raw_bytes = canonical_json_bytes(payload)
    digest, byte_length = sha256_identity(raw_bytes)
    return ExperimentRecord(payload=payload, sha256=digest, record_bytes=byte_length)


def load_manifested_measurement_record(path: str | Path) -> ExperimentRecord:
    """安全读取并严格验证 manifest 驱动测量记录。"""

    try:
        payload, raw_bytes = load_canonical_json(path, maximum_bytes=MAX_TEXT_BYTES)
    except SafeJsonError as error:
        raise ExperimentRecordError("无法安全读取 manifest 驱动测量记录") from error
    record = parse_manifested_measurement_payload(payload)
    if record.record_bytes != len(raw_bytes):
        raise ExperimentRecordError("manifest 驱动测量记录字节身份不一致")
    return record


def verify_child_record_against_plan(record: ExperimentRecord, plan: ExperimentPlan) -> None:
    """父端重验子进程记录的完整 schema、冻结参数和执行状态。"""

    if not isinstance(record, ExperimentRecord) or not isinstance(plan, ExperimentPlan):
        raise ExperimentRecordError("子记录复验必须关联已验证记录和实验计划")
    _validate_payload(record.payload)
    if record.payload["experiment_manifest"] != plan.manifest.identity.as_payload():
        raise ExperimentRecordError("子记录 manifest 身份与父端计划不一致")
    execution = record.payload["execution"]
    if not isinstance(execution, dict):
        raise ExperimentRecordError("子记录 execution 不兼容")
    if execution["plan_kind"] != plan.manifest.execution_kind:
        raise ExperimentRecordError("子记录执行类型与父端计划不一致")
    if (
        execution["player_count"] != plan.manifest.player_count
        or execution["master_seed"] != plan.manifest.master_seed
    ):
        raise ExperimentRecordError("子记录人数或 seed 与父端计划不一致")
    if plan.manifest.execution_kind == "a6-a7-training":
        if (
            execution["iterations"] != plan.manifest.iterations
            or execution["average_strategy_start_iteration"]
            != plan.manifest.average_strategy_start_iteration
            or execution["traverser"] is not None
        ):
            raise ExperimentRecordError("子记录训练配置与父端计划不一致")
        if (
            execution["status"] == "completed"
            and execution["completed_iterations"] != plan.manifest.iterations
        ):
            raise ExperimentRecordError("完成训练的 iteration 数与父端计划不一致")
    elif (
        execution["iterations"] != 1
        or execution["average_strategy_start_iteration"] is not None
        or execution["traverser"] != plan.manifest.n9_traverser
        or execution["completed_iterations"] != 0
    ):
        raise ExperimentRecordError("子记录 N9 boundary 参数与父端计划不一致")


def _validate_artifact(plan: ExperimentPlan, artifact: QuantizedStrategyArtifact | None) -> None:
    if artifact is None:
        raise ExperimentRecordError("完成训练必须关联量化回读策略")
    if artifact.artifact.game.player_count != plan.manifest.player_count:
        raise ExperimentRecordError("策略人数与实验计划不一致")
    if plan.manifest.strategy_slot is None:
        raise ExperimentRecordError("实验计划没有策略槽位")


def _validate_evaluation(
    plan: ExperimentPlan,
    artifact: QuantizedStrategyArtifact | None,
    evaluation: ManifestedEvaluation | None,
) -> None:
    if plan.manifest.profile_mode == "not-requested":
        if evaluation is not None and (
            evaluation.profile is not None or evaluation.probes is not None
        ):
            raise ExperimentRecordError("未请求质量评估的计划不能关联结果")
        return
    if artifact is None or evaluation is None or evaluation.profile is None:
        raise ExperimentRecordError("请求完整 profile 的计划必须关联同一量化策略的 profile")
    profile = evaluation.profile
    if profile.strategy_identity != artifact.identity:
        raise ExperimentRecordError("profile 策略身份与量化策略不匹配")
    if (
        profile.evaluator_identity.evaluator_id != EVALUATOR_ID
        or profile.evaluator_identity.evaluator_version != EVALUATOR_VERSION
    ):
        raise ExperimentRecordError("profile evaluator 身份不兼容")
    if plan.probe_manifest is None:
        if evaluation.probes is not None:
            raise ExperimentRecordError("未预注册 probe 的计划不能关联 probe 结果")
        return
    probes = evaluation.probes
    if probes is None or probes.strategy_identity != artifact.identity:
        raise ExperimentRecordError("probe 策略身份与量化策略不匹配")
    if probes.probe_manifest_identity != plan.probe_manifest.identity:
        raise ExperimentRecordError("probe manifest 身份与实验计划不匹配")


def _training_sections(
    result: ControlledTrainingResult,
    supervisor: SupervisorIdentity,
    plan: ExperimentPlan,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    execution = {
        "plan_kind": "a6-a7-training",
        "status": result.status.value,
        "stage": "training",
        "stop_reason": result.stop_reason.value,
        "completed_iterations": result.completed_iterations,
        "player_count": plan.manifest.player_count,
        "iterations": plan.manifest.iterations,
        "average_strategy_start_iteration": plan.manifest.average_strategy_start_iteration,
        "master_seed": plan.manifest.master_seed,
        "traverser": None,
    }
    diagnostics = {
        "average_strategy_start_iteration": plan.manifest.average_strategy_start_iteration,
        "coverage": [
            {
                "traverser": item.traverser,
                "visits": item.visits,
                "visited_infosets": item.visited_infosets,
                "total_infosets": item.total_infosets,
            }
            for item in result.diagnostics.coverage
        ],
        "importance_weights": [
            {
                "traverser": item.traverser,
                "visits": item.visits,
                "maximum_milli": _milli(item.maximum),
                "p50_milli": _milli(item.p50),
                "p95_milli": _milli(item.p95),
                "non_finite_count": item.non_finite_count,
            }
            for item in result.diagnostics.importance_weights
        ],
    }
    return execution, diagnostics, _resource_payload(result.resources, supervisor)


def _boundary_sections(
    result: N9BoundaryResult,
    supervisor: SupervisorIdentity,
    plan: ExperimentPlan,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    sample = result.sample
    execution = {
        "plan_kind": "n9-boundary-sample",
        "status": result.status.value,
        "stage": "boundary",
        "stop_reason": result.stop_reason.value,
        "completed_iterations": 0,
        "player_count": plan.manifest.player_count,
        "iterations": 1,
        "average_strategy_start_iteration": None,
        "master_seed": plan.manifest.master_seed,
        "traverser": plan.manifest.n9_traverser,
    }
    diagnostics = {
        "average_strategy_start_iteration": None,
        "coverage": [],
        "importance_weights": [],
        "boundary_traverser": sample.traverser if sample is not None else None,
        "boundary_infoset_count": sample.infoset_count if sample is not None else 0,
    }
    return execution, diagnostics, _resource_payload(result.resources, supervisor)


def _resource_payload(resources: Any, supervisor: SupervisorIdentity) -> dict[str, object]:
    return {
        "elapsed_milliseconds": _milli(resources.elapsed_seconds),
        "wall_time_limit_milliseconds": _milli(resources.wall_time_limit_seconds),
        "peak_rss_bytes": resources.peak_rss_bytes,
        "rss_warning_bytes": resources.rss_warning_bytes,
        "rss_hard_limit_bytes": resources.rss_hard_limit_bytes,
        "warning_triggered": resources.warning_triggered,
        "retained_artifact_bytes": resources.retained_artifact_bytes,
        "retained_artifact_limit_bytes": resources.retained_artifact_limit_bytes,
        "supervisor_id": supervisor.supervisor_id,
        "supervisor_version": supervisor.supervisor_version,
        "rss_scope": supervisor.rss_scope,
        "enforcement_mode": supervisor.enforcement_mode,
    }


def strategy_identity_payload(
    artifact: QuantizedStrategyArtifact | None,
) -> dict[str, object] | None:
    """父端与子端共用的策略身份形状，确保两侧记录逐字段可比。"""

    if artifact is None:
        return None
    return {
        "sha256": artifact.identity.sha256,
        "artifact_bytes": artifact.identity.artifact_bytes,
        "artifact_type": ARTIFACT_TYPE,
        "artifact_schema_version": STRATEGY_SCHEMA_VERSION,
    }


def _profile_payload(profile: ProfileEvaluation | None) -> dict[str, object] | None:
    if profile is None:
        return None
    return {
        "ordered_deal_count": profile.ordered_deal_count,
        "terminal_leaf_count": profile.terminal_leaf_count,
        "utilities": [_rational_payload(value) for value in profile.utilities],
        "strategy_sha256": profile.strategy_identity.sha256,
        "strategy_bytes": profile.strategy_identity.artifact_bytes,
        "evaluator_id": profile.evaluator_identity.evaluator_id,
        "evaluator_version": profile.evaluator_identity.evaluator_version,
        "probability_units": profile.evaluator_identity.probability_units,
    }


def _probes_payload(probes: ProbeEvaluation | None) -> dict[str, object] | None:
    if probes is None:
        return None
    if probes.probe_manifest_identity is None:
        raise ExperimentRecordError("受控 probe 结果必须绑定 probe manifest")
    return {
        "manifest": probes.probe_manifest_identity.as_payload(),
        "strategy_sha256": probes.strategy_identity.sha256,
        "strategy_bytes": probes.strategy_identity.artifact_bytes,
        "evaluator_id": probes.evaluator_identity.evaluator_id,
        "evaluator_version": probes.evaluator_identity.evaluator_version,
        "probability_units": probes.evaluator_identity.probability_units,
        "results": [
            {
                "player": result.player,
                "probe_id": result.probe_id,
                "utility": _rational_payload(result.utility),
                "delta": _rational_payload(result.delta),
            }
            for result in probes.results
        ],
        "gains": [_rational_payload(value) for value in probes.gains],
    }


def _rational_payload(value: Fraction) -> dict[str, str]:
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def _milli(value: float) -> int:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ExperimentRecordError("运行回执包含非有限时间或权重")
    if value < 0:
        raise ExperimentRecordError("运行回执不能包含负时间或权重")
    return round(value * 1000)


def _validate_payload(value: object) -> None:
    expected = {
        "schema_version",
        "record_type",
        "experiment_manifest",
        "game",
        "execution",
        "supervisor",
        "strategy",
        "profile",
        "probes",
        "diagnostics",
        "resources",
    }
    record = _exact_mapping(value, expected, "manifest 驱动测量记录")
    if (
        record["schema_version"] != EXPERIMENT_RECORD_SCHEMA_VERSION
        or record["record_type"] != EXPERIMENT_RECORD_TYPE
    ):
        raise ExperimentRecordError("manifest 驱动测量记录版本不兼容")
    player_count = _validate_game_payload(record["game"])
    _validate_identity_payload(record["experiment_manifest"], "experiment manifest")
    _validate_supervisor_payload(record["supervisor"])
    strategy_identity = _validate_strategy_payload(record["strategy"])
    profile_identity = _validate_profile_payload(record["profile"], strategy_identity, player_count)
    _validate_probes_payload(record["probes"], strategy_identity, profile_identity, player_count)
    _validate_execution_payload(
        record["execution"], record["strategy"], record["profile"], record["probes"]
    )
    _validate_resource_payload(record["resources"], record["supervisor"])


def _exact_mapping(value: object, expected: set[str], label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ExperimentRecordError(f"{label}字段不匹配")
    return value


def _validate_game_payload(value: object) -> int:
    game = _exact_mapping(value, {"id", "version", "player_count"}, "game")
    player_count = _require_int(game["player_count"], "game.player_count", minimum=0)
    if (
        game["id"] != "m8-unique-rank-single-open"
        or game["version"] != "m8-a-v1"
        or player_count not in {6, 7, 9}
    ):
        raise ExperimentRecordError("game 与候选 A 不兼容")
    return player_count


def _validate_strategy_payload(value: object) -> tuple[str, int] | None:
    if value is None:
        return None
    strategy = _exact_mapping(
        value,
        {"sha256", "artifact_bytes", "artifact_type", "artifact_schema_version"},
        "strategy",
    )
    sha256 = _require_hash(strategy["sha256"], "strategy.sha256")
    artifact_bytes = _require_int(strategy["artifact_bytes"], "strategy.artifact_bytes", minimum=1)
    if (
        strategy["artifact_type"] != ARTIFACT_TYPE
        or strategy["artifact_schema_version"] != STRATEGY_SCHEMA_VERSION
    ):
        raise ExperimentRecordError("strategy artifact 语义不兼容")
    return sha256, artifact_bytes


def _validate_profile_payload(
    value: object, strategy_identity: tuple[str, int] | None, player_count: int
) -> tuple[str, int, str, str, int] | None:
    if value is None:
        return None
    if strategy_identity is None:
        raise ExperimentRecordError("profile 不能脱离策略身份")
    profile = _exact_mapping(
        value,
        {
            "ordered_deal_count",
            "terminal_leaf_count",
            "utilities",
            "strategy_sha256",
            "strategy_bytes",
            "evaluator_id",
            "evaluator_version",
            "probability_units",
        },
        "profile",
    )
    if (
        _require_hash(profile["strategy_sha256"], "profile.strategy_sha256"),
        _require_int(profile["strategy_bytes"], "profile.strategy_bytes", minimum=1),
    ) != strategy_identity:
        raise ExperimentRecordError("profile 策略身份与 strategy 不一致")
    evaluator = (
        _require_string(profile["evaluator_id"], "profile.evaluator_id"),
        _require_string(profile["evaluator_version"], "profile.evaluator_version"),
        _require_int(profile["probability_units"], "profile.probability_units", minimum=1),
    )
    if evaluator != (EVALUATOR_ID, EVALUATOR_VERSION, 1_000_000_000_000):
        raise ExperimentRecordError("profile evaluator 不兼容")
    _require_int(profile["ordered_deal_count"], "profile.ordered_deal_count", minimum=1)
    _require_int(profile["terminal_leaf_count"], "profile.terminal_leaf_count", minimum=1)
    utilities = _validate_rational_array(profile["utilities"], player_count, "profile.utilities")
    if sum(utilities, Fraction(0)) != 0:
        raise ExperimentRecordError("profile utilities 未保持常和")
    return (*strategy_identity, *evaluator)


def _validate_probes_payload(
    value: object,
    strategy_identity: tuple[str, int] | None,
    profile_identity: tuple[str, int, str, str, int] | None,
    player_count: int,
) -> None:
    if value is None:
        return
    if strategy_identity is None or profile_identity is None:
        raise ExperimentRecordError("probe 不能脱离策略和 profile 身份")
    probes = _exact_mapping(
        value,
        {
            "manifest",
            "strategy_sha256",
            "strategy_bytes",
            "evaluator_id",
            "evaluator_version",
            "probability_units",
            "results",
            "gains",
        },
        "probes",
    )
    _validate_identity_payload(probes["manifest"], "probe manifest")
    if (
        _require_hash(probes["strategy_sha256"], "probes.strategy_sha256"),
        _require_int(probes["strategy_bytes"], "probes.strategy_bytes", minimum=1),
    ) != strategy_identity:
        raise ExperimentRecordError("probe 策略身份与 strategy 不一致")
    if (
        _require_string(probes["evaluator_id"], "probes.evaluator_id"),
        _require_string(probes["evaluator_version"], "probes.evaluator_version"),
        _require_int(probes["probability_units"], "probes.probability_units", minimum=1),
    ) != profile_identity[2:]:
        raise ExperimentRecordError("probe evaluator 身份与 profile 不一致")
    results = probes["results"]
    if not isinstance(results, list) or not results:
        raise ExperimentRecordError("probe 结果必须是非空数组")
    for result in results:
        entry = _exact_mapping(result, {"player", "probe_id", "utility", "delta"}, "probe result")
        player = _require_int(entry["player"], "probe player", minimum=0)
        if player >= player_count:
            raise ExperimentRecordError("probe player 超出范围")
        _require_string(entry["probe_id"], "probe id")
        _validate_rational(entry["utility"], "probe utility")
        _validate_rational(entry["delta"], "probe delta")
    gains = _validate_rational_array(probes["gains"], player_count, "probe gains")
    if any(gain < 0 for gain in gains):
        raise ExperimentRecordError("probe gains 不能为负")


def _validate_identity_payload(value: object, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {
        "manifest_type",
        "schema_version",
        "manifest_id",
        "sha256",
        "byte_length",
    }:
        raise ExperimentRecordError(f"{label} 身份字段不匹配")
    if not isinstance(value["sha256"], str) or len(value["sha256"]) != 64:
        raise ExperimentRecordError(f"{label} SHA-256 不兼容")


def _validate_supervisor_payload(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "supervisor_id",
        "supervisor_version",
        "rss_scope",
        "enforcement_mode",
    }:
        raise ExperimentRecordError("监督器字段不匹配")
    SupervisorIdentity(**value)


def _validate_execution_payload(
    execution: object, strategy: object, profile: object, probes: object
) -> None:
    if not isinstance(execution, dict) or set(execution) != {
        "plan_kind",
        "status",
        "stage",
        "stop_reason",
        "completed_iterations",
        "player_count",
        "iterations",
        "average_strategy_start_iteration",
        "master_seed",
        "traverser",
    }:
        raise ExperimentRecordError("执行回执字段不匹配")
    plan_kind = execution["plan_kind"]
    if plan_kind not in {"a6-a7-training", "n9-boundary-sample"}:
        raise ExperimentRecordError("执行计划类型不兼容")
    if plan_kind == "n9-boundary-sample" and any(
        value is not None for value in (strategy, profile, probes)
    ):
        raise ExperimentRecordError("N9 boundary 记录不能关联策略或质量结果")
    if execution["status"] == "completed" and execution["stop_reason"] != "completed":
        raise ExperimentRecordError("完成状态与停止原因不一致")


def _validate_resource_payload(resources: object, supervisor: object) -> None:
    expected = {
        "elapsed_milliseconds",
        "wall_time_limit_milliseconds",
        "peak_rss_bytes",
        "rss_warning_bytes",
        "rss_hard_limit_bytes",
        "warning_triggered",
        "retained_artifact_bytes",
        "retained_artifact_limit_bytes",
        "supervisor_id",
        "supervisor_version",
        "rss_scope",
        "enforcement_mode",
    }
    if not isinstance(resources, dict) or set(resources) != expected:
        raise ExperimentRecordError("资源回执字段不匹配")
    if not isinstance(supervisor, dict):
        raise ExperimentRecordError("监督器字段不兼容")
    for field in ("supervisor_id", "supervisor_version", "rss_scope", "enforcement_mode"):
        if resources[field] != supervisor[field]:
            raise ExperimentRecordError("资源回执监督器身份不一致")
    warning = _require_int(resources["rss_warning_bytes"], "resources.rss_warning_bytes", minimum=0)
    hard = _require_int(
        resources["rss_hard_limit_bytes"], "resources.rss_hard_limit_bytes", minimum=1
    )
    if warning >= hard:
        raise ExperimentRecordError("资源 RSS 预警阈值必须小于硬停阈值")
    retained = _require_int(
        resources["retained_artifact_bytes"], "resources.retained_artifact_bytes", minimum=0
    )
    limit = _require_int(
        resources["retained_artifact_limit_bytes"],
        "resources.retained_artifact_limit_bytes",
        minimum=1,
    )
    if retained > limit:
        raise ExperimentRecordError("资源保留工件额度不一致")
    _require_int(resources["elapsed_milliseconds"], "resources.elapsed_milliseconds", minimum=0)
    _require_int(
        resources["wall_time_limit_milliseconds"],
        "resources.wall_time_limit_milliseconds",
        minimum=1,
    )
    _require_int(resources["peak_rss_bytes"], "resources.peak_rss_bytes", minimum=0)
    if not isinstance(resources["warning_triggered"], bool):
        raise ExperimentRecordError("resources.warning_triggered 必须是布尔值")


def _require_int(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ExperimentRecordError(f"{label} 必须是不小于 {minimum} 的整数")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ExperimentRecordError(f"{label} 必须是长度受限的非空字符串")
    return value


def _require_rational_text(value: object, label: str) -> str:
    """校验精确有理数的分子或分母文本，其长度上界独立于标识符字段。"""

    if not isinstance(value, str) or not value or len(value) > MAX_RATIONAL_DIGITS:
        raise ExperimentRecordError(f"{label} 必须是长度受限的非空十进制字符串")
    return value


def _require_hash(value: object, label: str) -> str:
    value = _require_string(value, label)
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ExperimentRecordError(f"{label} 必须是小写 SHA-256")
    return value


def _validate_rational(value: object, label: str) -> Fraction:
    rational = _exact_mapping(value, {"numerator", "denominator"}, label)
    numerator = _require_rational_text(rational["numerator"], f"{label}.numerator")
    denominator = _require_rational_text(rational["denominator"], f"{label}.denominator")
    if (
        re.fullmatch(r"0|-?[1-9][0-9]*", numerator) is None
        or re.fullmatch(r"[1-9][0-9]*", denominator) is None
    ):
        raise ExperimentRecordError(f"{label} 必须使用规范十进制有理数")
    fraction = Fraction(int(numerator), int(denominator))
    if str(fraction.numerator) != numerator or str(fraction.denominator) != denominator:
        raise ExperimentRecordError(f"{label} 必须使用既约有理数")
    return fraction


def _validate_rational_array(value: object, length: int, label: str) -> tuple[Fraction, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise ExperimentRecordError(f"{label} 长度不匹配")
    return tuple(_validate_rational(entry, label) for entry in value)
