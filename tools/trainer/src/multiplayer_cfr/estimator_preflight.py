"""N6 external-sampling estimator 的冻结 preflight attestation。"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import fsum
from pathlib import Path
from typing import Any

from .estimator_oracle import exact_external_sampling_targets
from .game import Action, information_set_key, infosets
from .mccfr import MCCFRConfig, run_audit_iteration
from .safeio import (
    MAX_TEXT_BYTES,
    SafeJsonError,
    canonical_json_bytes,
    load_canonical_json,
    sha256_identity,
    write_canonical_json,
)

PREFLIGHT_MANIFEST_TYPE = "multiplayer-cfr-estimator-preflight"
PREFLIGHT_ATTESTATION_TYPE = "multiplayer-cfr-estimator-attestation"
PREFLIGHT_SCHEMA_VERSION = 1
FIXTURE_ID = "three-to-one-regret-v1"
_ORACLE_CACHE: dict[tuple[tuple[str, ...], bool], object] = {}


class EstimatorPreflightError(ValueError):
    """冻结 estimator preflight 的 schema、审计目标或样本结果不符合契约时抛出。"""


@dataclass(frozen=True)
class PreflightIdentity:
    """由规范 JSON 字节派生的 preflight manifest 或 attestation 身份。"""

    record_type: str
    schema_version: int
    record_id: str
    sha256: str
    byte_length: int

    def as_payload(self) -> dict[str, object]:
        return {
            "record_type": self.record_type,
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
        }


@dataclass(frozen=True)
class EstimatorPreflightSpec:
    """实际 A6/A7 前必须冻结的 N6 estimator 核验输入。"""

    identity: PreflightIdentity
    git_commit: str
    trainer_version: str
    sample_seeds: tuple[int, ...]
    target_infosets: tuple[str, ...]
    regret_tolerance_micros: int
    strategy_sum_tolerance_micros: int


@dataclass(frozen=True)
class EstimatorAttestation:
    """冻结 preflight spec 的可复核有限采样结果。"""

    payload: dict[str, object]
    identity: PreflightIdentity


def create_preflight_spec(payload: dict[str, object]) -> EstimatorPreflightSpec:
    """验证内存 preflight manifest 并创建规范内容身份。"""

    parsed = _parse_preflight_payload(payload)
    raw_bytes = canonical_json_bytes(parsed)
    return _spec_from_payload(parsed, raw_bytes)


def write_preflight_spec(
    root: str | Path, relative_name: str, spec: EstimatorPreflightSpec
) -> EstimatorPreflightSpec:
    """原子写入已验证 preflight manifest 并回读其身份。"""

    payload = _spec_payload(spec)
    write_canonical_json(root, relative_name, payload, maximum_bytes=MAX_TEXT_BYTES)
    return load_preflight_spec(Path(root) / relative_name)


def load_preflight_spec(path: str | Path) -> EstimatorPreflightSpec:
    """安全读取冻结 estimator preflight manifest。"""

    try:
        payload, raw_bytes = load_canonical_json(path, maximum_bytes=MAX_TEXT_BYTES)
    except SafeJsonError as error:
        raise EstimatorPreflightError("无法安全读取 estimator preflight manifest") from error
    parsed = _parse_preflight_payload(payload)
    return _spec_from_payload(parsed, raw_bytes)


def run_preflight(spec: EstimatorPreflightSpec) -> EstimatorAttestation:
    """按冻结 seeds、targets 和容差运行独立 oracle 与生产单 iteration 核验。"""

    if not isinstance(spec, EstimatorPreflightSpec):
        raise EstimatorPreflightError("preflight 必须来自已验证 spec")
    frozen_policy, initial_regrets = _fixture_policy_and_regrets()
    case_payloads = []
    overall_pass = True
    for accumulate_average in (False, True):
        cache_key = (spec.target_infosets, accumulate_average)
        oracle = _ORACLE_CACHE.get(cache_key)
        if oracle is None:
            oracle = exact_external_sampling_targets(
                frozen_policy,
                spec.target_infosets,
                accumulate_average=accumulate_average,
            )
            _ORACLE_CACHE[cache_key] = oracle
        observed_regrets = _empty_updates(spec.target_infosets)
        observed_sums = _empty_updates(spec.target_infosets)
        for seed in spec.sample_seeds:
            config = MCCFRConfig(
                player_count=6,
                iterations=2 if not accumulate_average else 1,
                master_seed=seed,
                average_strategy_start_iteration=2 if not accumulate_average else 1,
            )
            trace = run_audit_iteration(config, initial_regrets)
            _accumulate_updates(observed_regrets, trace.update.regret_deltas)
            _accumulate_updates(observed_sums, trace.update.strategy_sum_deltas)
        case = _compare_case(
            oracle,
            observed_regrets,
            observed_sums,
            sample_count=len(spec.sample_seeds),
            regret_tolerance_micros=spec.regret_tolerance_micros,
            strategy_sum_tolerance_micros=spec.strategy_sum_tolerance_micros,
        )
        case["accumulate_average"] = accumulate_average
        overall_pass = overall_pass and case["passed"]
        case_payloads.append(case)
    payload = {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "record_type": PREFLIGHT_ATTESTATION_TYPE,
        "record_id": spec.identity.record_id,
        "preflight_manifest": spec.identity.as_payload(),
        "code_identity": {
            "git_commit": spec.git_commit,
            "trainer_version": spec.trainer_version,
        },
        "fixture_id": FIXTURE_ID,
        "sample_seeds": list(spec.sample_seeds),
        "target_infosets": list(spec.target_infosets),
        "regret_tolerance_micros": spec.regret_tolerance_micros,
        "strategy_sum_tolerance_micros": spec.strategy_sum_tolerance_micros,
        "cases": case_payloads,
        "passed": overall_pass,
    }
    _validate_attestation_payload(payload)
    raw_bytes = canonical_json_bytes(payload)
    return EstimatorAttestation(
        payload=payload, identity=_identity_from_payload(payload, raw_bytes)
    )


def write_attestation(
    root: str | Path, relative_name: str, attestation: EstimatorAttestation
) -> EstimatorAttestation:
    """原子写入通过或失败的 preflight attestation，并回读其身份。"""

    if not isinstance(attestation, EstimatorAttestation):
        raise EstimatorPreflightError("attestation 必须是已验证对象")
    _validate_attestation_payload(attestation.payload)
    write_canonical_json(root, relative_name, attestation.payload, maximum_bytes=MAX_TEXT_BYTES)
    return load_attestation(Path(root) / relative_name)


def load_attestation(path: str | Path) -> EstimatorAttestation:
    """安全读取并严格验证 estimator attestation。"""

    try:
        payload, raw_bytes = load_canonical_json(path, maximum_bytes=MAX_TEXT_BYTES)
    except SafeJsonError as error:
        raise EstimatorPreflightError("无法安全读取 estimator attestation") from error
    _validate_attestation_payload(payload)
    return EstimatorAttestation(
        payload=payload, identity=_identity_from_payload(payload, raw_bytes)
    )


def verify_attestation(spec: EstimatorPreflightSpec, attestation: EstimatorAttestation) -> None:
    """父端重跑固定有限核验并验证 attestation 内容与冻结 spec 完全一致。"""

    if attestation.payload["preflight_manifest"] != spec.identity.as_payload():
        raise EstimatorPreflightError("attestation 未引用当前冻结 preflight manifest")
    if not attestation.payload["passed"]:
        raise EstimatorPreflightError("estimator attestation 未通过")
    recomputed = run_preflight(spec)
    if recomputed.payload != attestation.payload:
        raise EstimatorPreflightError("attestation 与固定 production/oracle 重验结果不一致")


def _fixture_policy_and_regrets() -> tuple[
    dict[str, dict[Action, float]], dict[str, dict[Action, float]]
]:
    policy = {}
    regrets = {}
    for spec in infosets(6):
        first, second = spec.actions
        policy[spec.key] = {first: 0.25, second: 0.75}
        regrets[spec.key] = {first: 1.0, second: 3.0}
    return policy, regrets


def _empty_updates(keys: tuple[str, ...]) -> dict[str, dict[Action, float]]:
    return {key: {} for key in keys}


def _accumulate_updates(
    target: dict[str, dict[Action, float]],
    updates: tuple[tuple[str, tuple[tuple[Action, float], ...]], ...],
) -> None:
    for key, values in updates:
        if key not in target:
            continue
        for action, value in values:
            target[key][action] = fsum((target[key].get(action, 0.0), value))


def _compare_case(
    oracle: object,
    observed_regrets: dict[str, dict[Action, float]],
    observed_sums: dict[str, dict[Action, float]],
    *,
    sample_count: int,
    regret_tolerance_micros: int,
    strategy_sum_tolerance_micros: int,
) -> dict[str, object]:
    from .estimator_oracle import EstimatorOracleResult

    if not isinstance(oracle, EstimatorOracleResult):
        raise EstimatorPreflightError("oracle 结果类型不兼容")
    maximum_regret_error = 0
    maximum_strategy_sum_error = 0
    for target in oracle.targets:
        for action, expected in target.regret_deltas.items():
            observed = observed_regrets[target.infoset_key].get(action, 0.0) / sample_count
            maximum_regret_error = max(
                maximum_regret_error,
                _micros(abs(Fraction(str(observed)) - expected)),
            )
        for action, expected in target.strategy_sum_deltas.items():
            observed = observed_sums[target.infoset_key].get(action, 0.0) / sample_count
            maximum_strategy_sum_error = max(
                maximum_strategy_sum_error,
                _micros(abs(Fraction(str(observed)) - expected)),
            )
    return {
        "maximum_regret_error_micros": maximum_regret_error,
        "maximum_strategy_sum_error_micros": maximum_strategy_sum_error,
        "passed": (
            maximum_regret_error <= regret_tolerance_micros
            and maximum_strategy_sum_error <= strategy_sum_tolerance_micros
        ),
    }


def _micros(value: Fraction) -> int:
    return int(value * 1_000_000)


def _spec_from_payload(payload: dict[str, object], raw_bytes: bytes) -> EstimatorPreflightSpec:
    return EstimatorPreflightSpec(
        identity=_identity_from_payload(payload, raw_bytes),
        git_commit=payload["code_identity"]["git_commit"],
        trainer_version=payload["code_identity"]["trainer_version"],
        sample_seeds=tuple(payload["sample_seeds"]),
        target_infosets=tuple(payload["target_infosets"]),
        regret_tolerance_micros=payload["regret_tolerance_micros"],
        strategy_sum_tolerance_micros=payload["strategy_sum_tolerance_micros"],
    )


def _spec_payload(spec: EstimatorPreflightSpec) -> dict[str, object]:
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "record_type": PREFLIGHT_MANIFEST_TYPE,
        "record_id": spec.identity.record_id,
        "code_identity": {"git_commit": spec.git_commit, "trainer_version": spec.trainer_version},
        "fixture_id": FIXTURE_ID,
        "sample_seeds": list(spec.sample_seeds),
        "target_infosets": list(spec.target_infosets),
        "regret_tolerance_micros": spec.regret_tolerance_micros,
        "strategy_sum_tolerance_micros": spec.strategy_sum_tolerance_micros,
    }


def _parse_preflight_payload(value: object) -> dict[str, object]:
    payload = _exact_mapping(
        value,
        {
            "schema_version",
            "record_type",
            "record_id",
            "code_identity",
            "fixture_id",
            "sample_seeds",
            "target_infosets",
            "regret_tolerance_micros",
            "strategy_sum_tolerance_micros",
        },
        "estimator preflight manifest",
    )
    if (
        payload["schema_version"] != PREFLIGHT_SCHEMA_VERSION
        or payload["record_type"] != PREFLIGHT_MANIFEST_TYPE
        or payload["fixture_id"] != FIXTURE_ID
    ):
        raise EstimatorPreflightError("estimator preflight manifest 版本或 fixture 不兼容")
    code_identity = _exact_mapping(
        payload["code_identity"], {"git_commit", "trainer_version"}, "code identity"
    )
    targets = _parse_targets(payload["target_infosets"])
    seeds = _parse_seeds(payload["sample_seeds"])
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "record_type": PREFLIGHT_MANIFEST_TYPE,
        "record_id": _require_id(payload["record_id"], "record_id"),
        "code_identity": {
            "git_commit": _require_commit(code_identity["git_commit"]),
            "trainer_version": _require_version(code_identity["trainer_version"]),
        },
        "fixture_id": FIXTURE_ID,
        "sample_seeds": seeds,
        "target_infosets": targets,
        "regret_tolerance_micros": _require_int(
            payload["regret_tolerance_micros"], "regret_tolerance_micros", minimum=1
        ),
        "strategy_sum_tolerance_micros": _require_int(
            payload["strategy_sum_tolerance_micros"], "strategy_sum_tolerance_micros", minimum=1
        ),
    }


def _validate_attestation_payload(value: object) -> None:
    payload = _exact_mapping(
        value,
        {
            "schema_version",
            "record_type",
            "record_id",
            "preflight_manifest",
            "code_identity",
            "fixture_id",
            "sample_seeds",
            "target_infosets",
            "regret_tolerance_micros",
            "strategy_sum_tolerance_micros",
            "cases",
            "passed",
        },
        "estimator attestation",
    )
    if (
        payload["schema_version"] != PREFLIGHT_SCHEMA_VERSION
        or payload["record_type"] != PREFLIGHT_ATTESTATION_TYPE
        or payload["fixture_id"] != FIXTURE_ID
        or not isinstance(payload["passed"], bool)
    ):
        raise EstimatorPreflightError("estimator attestation 版本或状态不兼容")
    _parse_identity(payload["preflight_manifest"])
    _parse_preflight_payload(
        {
            "schema_version": PREFLIGHT_SCHEMA_VERSION,
            "record_type": PREFLIGHT_MANIFEST_TYPE,
            "record_id": payload["record_id"],
            "code_identity": payload["code_identity"],
            "fixture_id": payload["fixture_id"],
            "sample_seeds": payload["sample_seeds"],
            "target_infosets": payload["target_infosets"],
            "regret_tolerance_micros": payload["regret_tolerance_micros"],
            "strategy_sum_tolerance_micros": payload["strategy_sum_tolerance_micros"],
        }
    )
    cases = payload["cases"]
    if not isinstance(cases, list) or len(cases) != 2:
        raise EstimatorPreflightError("estimator attestation 必须包含两个平均策略模式 case")
    modes = []
    for case in cases:
        parsed = _exact_mapping(
            case,
            {
                "accumulate_average",
                "maximum_regret_error_micros",
                "maximum_strategy_sum_error_micros",
                "passed",
            },
            "estimator attestation case",
        )
        if not isinstance(parsed["accumulate_average"], bool) or not isinstance(
            parsed["passed"], bool
        ):
            raise EstimatorPreflightError("estimator attestation case 状态不兼容")
        _require_int(parsed["maximum_regret_error_micros"], "最大 regret 误差", minimum=0)
        _require_int(parsed["maximum_strategy_sum_error_micros"], "最大策略累计误差", minimum=0)
        modes.append(parsed["accumulate_average"])
    if modes != [False, True]:
        raise EstimatorPreflightError("estimator attestation case 必须按 average 模式排序")


def _parse_targets(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) < 2 or value != sorted(value):
        raise EstimatorPreflightError("target infosets 必须是排序且至少两个的数组")
    expected = {
        information_set_key(6, 0, 3, "-"),
        information_set_key(6, 1, 3, "b@0"),
        information_set_key(6, 2, 3, "b@0|c@1"),
    }
    targets = []
    for key in value:
        if not isinstance(key, str) or key not in expected:
            raise EstimatorPreflightError("target infoset 不属于冻结 preflight 目标集")
        targets.append(key)
    if len(targets) != len(set(targets)):
        raise EstimatorPreflightError("target infoset 不能重复")
    return targets


def _parse_seeds(value: object) -> list[int]:
    if not isinstance(value, list) or not 8 <= len(value) <= 256:
        raise EstimatorPreflightError("preflight seeds 必须包含 8 至 256 个显式 seed")
    seeds = [_require_int(seed, "preflight seed", minimum=0) for seed in value]
    if seeds != sorted(seeds) or len(seeds) != len(set(seeds)):
        raise EstimatorPreflightError("preflight seeds 必须按升序且不重复")
    return seeds


def _parse_identity(value: object) -> PreflightIdentity:
    payload = _exact_mapping(
        value,
        {"record_type", "schema_version", "record_id", "sha256", "byte_length"},
        "preflight identity",
    )
    if payload["record_type"] != PREFLIGHT_MANIFEST_TYPE:
        raise EstimatorPreflightError("preflight identity 类型不兼容")
    return PreflightIdentity(
        record_type=PREFLIGHT_MANIFEST_TYPE,
        schema_version=_require_int(payload["schema_version"], "preflight schema", minimum=1),
        record_id=_require_id(payload["record_id"], "preflight record_id"),
        sha256=_require_hash(payload["sha256"]),
        byte_length=_require_int(payload["byte_length"], "preflight byte_length", minimum=1),
    )


def _identity_from_payload(payload: dict[str, object], raw_bytes: bytes) -> PreflightIdentity:
    digest, byte_length = sha256_identity(raw_bytes)
    return PreflightIdentity(
        record_type=payload["record_type"],
        schema_version=payload["schema_version"],
        record_id=payload["record_id"],
        sha256=digest,
        byte_length=byte_length,
    )


def _exact_mapping(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise EstimatorPreflightError(f"{label}字段不匹配")
    return value


def _require_int(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EstimatorPreflightError(f"{label}必须是不小于 {minimum} 的整数")
    return value


def _require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise EstimatorPreflightError(f"{label}必须是长度受限的非空字符串")
    return value


def _require_commit(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EstimatorPreflightError("git_commit 必须是小写完整提交")
    return value


def _require_version(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise EstimatorPreflightError("trainer_version 必须是长度受限的非空字符串")
    return value


def _require_hash(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EstimatorPreflightError("SHA-256 必须是小写十六进制")
    return value
