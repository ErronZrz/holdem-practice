"""不可追加预算的 campaign manifest、互斥 lease 与终态 ledger。"""

from __future__ import annotations

import fcntl
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .estimator_preflight import (
    EstimatorAttestation,
    PreflightIdentity,
    load_attestation,
    load_preflight_spec,
    verify_attestation,
)
from .manifest import ExperimentPlan, ManifestIdentity
from .safeio import (
    MAX_TEXT_BYTES,
    SafeJsonError,
    canonical_json_bytes,
    load_canonical_json,
    replace_canonical_json,
    sha256_identity,
    write_canonical_json,
)

CAMPAIGN_TYPE = "multiplayer-cfr-campaign"
CAMPAIGN_LEDGER_TYPE = "multiplayer-cfr-campaign-ledger"
CAMPAIGN_SCHEMA_VERSION = 1

# 受控标识只允许小写字母数字与连字符，避免标识被拼进路径后越出约定根目录。
_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_LEASE_GUARD = object()
_EVENT_FIELDS = {
    "event",
    "authorization_id",
    "status",
    "supervisor_receipt_sha256",
    "final_measurement_sha256",
    "final_inventory",
}


class CampaignError(ValueError):
    """campaign 授权、共享预算、互斥 lease 或终态 ledger 不符合 fail-closed 契约时抛出。"""


@dataclass(frozen=True)
class CampaignIdentity:
    """规范 campaign manifest 的内容身份。"""

    campaign_id: str
    sha256: str
    byte_length: int

    def as_payload(self) -> dict[str, object]:
        return {
            "campaign_id": self.campaign_id,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
        }


@dataclass(frozen=True)
class CampaignAuthorization:
    """预注册的单次 experiment 授权与不可退还预算预留。"""

    authorization_id: str
    experiment_manifest: ManifestIdentity
    cpu_reservation_milliseconds: int
    wall_reservation_milliseconds: int
    artifact_reservation_bytes: int


@dataclass(frozen=True)
class CampaignManifest:
    """覆盖 A6/A7/seed/重试的固定授权列表和共享预算 envelope。"""

    identity: CampaignIdentity
    git_commit: str
    trainer_version: str
    preflight_attestation: PreflightIdentity
    cpu_limit_milliseconds: int
    wall_limit_milliseconds: int
    peak_rss_limit_bytes: int
    retained_artifact_limit_bytes: int
    authorizations: tuple[CampaignAuthorization, ...]


@dataclass
class CampaignLease:
    """持有 campaign 全生命周期互斥锁的单次不可重试 authorization lease。"""

    campaign: CampaignManifest
    authorization: CampaignAuthorization
    root: Path
    _lock_descriptor: int
    _finalized: bool = False
    _guard: object = None

    def __post_init__(self) -> None:
        if self._guard is not _LEASE_GUARD:
            raise CampaignError("authorization lease 只能由 campaign 互斥入口签发")

    def is_active(self) -> bool:
        """lease 仍持有互斥锁且尚未写入终态。"""

        return self._lock_descriptor >= 0 and not self._finalized

    def run_root(self) -> Path:
        """本次 authorization 独占的 run 根目录，并断言它未越出 campaign 根。"""

        run_root = self.root / "runs" / self.authorization.authorization_id
        if not _is_within(run_root, self.root):
            raise CampaignError("authorization run 目录越出 campaign 根")
        return run_root

    def create_run_directories(self) -> tuple[Path, Path, Path]:
        """新建空的 run、工件与快照目录；已存在即拒绝覆盖或重试。"""

        run_root = self.run_root()
        if run_root.exists():
            raise CampaignError("authorization 已有运行目录，campaign 不允许覆盖或重试")
        artifact_root = run_root / "artifacts"
        snapshot_root = run_root / "inputs"
        artifact_root.mkdir(parents=True)
        snapshot_root.mkdir()
        return run_root, artifact_root, snapshot_root

    def owns_path(self, path: str | Path) -> bool:
        """判断路径是否落在本 lease 的 run 目录之内。"""

        return _is_within(Path(path), self.run_root())

    def finalize(
        self,
        *,
        status: str,
        supervisor_receipt_sha256: str | None,
        final_measurement_sha256: str | None,
        final_inventory: list[dict[str, object]],
    ) -> None:
        """写入不可逆终态事件；已 lease 的授权不会自动释放或重试。"""

        if self._finalized:
            raise CampaignError("authorization lease 已终结")
        if status not in {"completed", "stopped", "failed", "inventory-failed"}:
            raise CampaignError("campaign 终态不兼容")
        if status == "completed" and (
            supervisor_receipt_sha256 is None or final_measurement_sha256 is None
        ):
            raise CampaignError("完成的 authorization 必须关联父回执和最终 measurement")
        ledger = _load_ledger(self.root, self.campaign)
        _append_event(
            ledger,
            {
                "event": "finalized",
                "authorization_id": self.authorization.authorization_id,
                "status": status,
                "supervisor_receipt_sha256": supervisor_receipt_sha256,
                "final_measurement_sha256": final_measurement_sha256,
                "final_inventory": final_inventory,
            },
        )
        _write_ledger(self.root, ledger)
        self._finalized = True

    def close(self) -> None:
        """释放活进程互斥锁；未终结 lease 保持 ledger 中的 fail-closed 状态。"""

        if self._lock_descriptor >= 0:
            fcntl.flock(self._lock_descriptor, fcntl.LOCK_UN)
            os.close(self._lock_descriptor)
            self._lock_descriptor = -1

    def __enter__(self) -> CampaignLease:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def create_campaign_manifest(payload: dict[str, object]) -> CampaignManifest:
    """验证内存 campaign manifest 并创建规范内容身份。"""

    parsed = _parse_campaign_payload(payload)
    raw_bytes = canonical_json_bytes(parsed)
    return _campaign_from_payload(parsed, raw_bytes)


def write_campaign_manifest(
    root: str | Path, relative_name: str, campaign: CampaignManifest
) -> CampaignManifest:
    """原子写入 campaign manifest 并回读其身份。"""

    write_canonical_json(
        root, relative_name, _campaign_payload(campaign), maximum_bytes=MAX_TEXT_BYTES
    )
    return load_campaign_manifest(Path(root) / relative_name)


def load_campaign_manifest(path: str | Path) -> CampaignManifest:
    """安全读取冻结 campaign manifest。"""

    try:
        payload, raw_bytes = load_canonical_json(path, maximum_bytes=MAX_TEXT_BYTES)
    except SafeJsonError as error:
        raise CampaignError("无法安全读取 campaign manifest") from error
    return _campaign_from_payload(_parse_campaign_payload(payload), raw_bytes)


def verify_campaign_preflight(
    campaign: CampaignManifest, attestation: EstimatorAttestation
) -> None:
    """在获取任何 experiment lease 前验证通过的 estimator attestation 内容身份。"""

    if not isinstance(attestation, EstimatorAttestation) or not attestation.payload["passed"]:
        raise CampaignError("campaign 必须关联通过的 estimator attestation")
    identity = campaign.preflight_attestation
    if (
        attestation.identity.record_id != identity.record_id
        or attestation.identity.sha256 != identity.sha256
        or attestation.identity.byte_length != identity.byte_length
        or attestation.payload["code_identity"]["git_commit"] != campaign.git_commit
        or attestation.payload["code_identity"]["trainer_version"] != campaign.trainer_version
    ):
        raise CampaignError("campaign preflight attestation 身份或代码版本不匹配")


def require_campaign_preflight_files(
    campaign: CampaignManifest,
    preflight_spec_path: str | Path,
    preflight_attestation_path: str | Path,
) -> None:
    """按真实文件字节重验冻结 preflight spec 与 attestation，并重演其固定核验。

    这是 A6/A7 的 preflight 门禁的唯一实现，供 campaign 授权入口与父端监督入口共用，
    避免两条入口各写一份判断而再次分叉。
    """

    spec = load_preflight_spec(preflight_spec_path)
    attestation = load_attestation(preflight_attestation_path)
    verify_campaign_preflight(campaign, attestation)
    verify_attestation(spec, attestation)


def require_authorization_within_reservation(
    authorization: CampaignAuthorization,
    plan: ExperimentPlan,
    campaign: CampaignManifest,
) -> None:
    """拒绝 experiment 资源上限超过 authorization 预留或 campaign envelope 的授权。

    墙钟按 manifest 声明的全部阶段求和；单并发下 experiment 的 RSS 硬停阈值与 campaign
    峰值 RSS 上限同口径绑定，避免用一份远超 envelope 的 experiment 绕过共享预算。
    """

    requested_wall = sum(stage.wall_time_milliseconds for stage in plan.manifest.stages)
    if (
        plan.manifest.cpu_limit_milliseconds > authorization.cpu_reservation_milliseconds
        or requested_wall > authorization.wall_reservation_milliseconds
        or plan.manifest.retained_artifact_limit_bytes > authorization.artifact_reservation_bytes
        or plan.manifest.rss_hard_limit_bytes > campaign.peak_rss_limit_bytes
    ):
        raise CampaignError("experiment 资源上限超过其 campaign authorization 预留")


def acquire_campaign_lease(
    root: str | Path,
    campaign: CampaignManifest,
    authorization_id: str,
) -> CampaignLease:
    """独占并不可重试地 lease 一个预注册 authorization，按预留上界消耗 campaign 预算。"""

    campaign_root = _require_campaign_root(root)
    descriptor = _acquire_lock(campaign_root)
    try:
        ledger = _load_ledger(campaign_root, campaign)
        authorization = _find_authorization(campaign, authorization_id)
        events = ledger["events"]
        if any(event["authorization_id"] == authorization_id for event in events):
            raise CampaignError("authorization 已被 lease，campaign 不允许自动重试或预算重置")
        _append_event(
            ledger,
            {
                "event": "leased",
                "authorization_id": authorization_id,
                "status": "leased",
                "supervisor_receipt_sha256": None,
                "final_measurement_sha256": None,
                "final_inventory": [],
            },
        )
        _write_ledger(campaign_root, ledger)
    except Exception:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        raise
    return CampaignLease(campaign, authorization, campaign_root, descriptor, _guard=_LEASE_GUARD)


def verify_active_lease(lease: CampaignLease) -> None:
    """确认 lease 由 campaign 互斥入口签发、仍然有效且与 ledger 记录一致。"""

    if not isinstance(lease, CampaignLease) or lease._guard is not _LEASE_GUARD:
        raise CampaignError("执行必须持有由 campaign 签发的 authorization lease")
    if not lease.is_active():
        raise CampaignError("authorization lease 已释放或已终结")
    _find_authorization(lease.campaign, lease.authorization.authorization_id)
    ledger = _load_ledger(lease.root, lease.campaign)
    if not any(
        event["authorization_id"] == lease.authorization.authorization_id
        and event["event"] == "leased"
        for event in ledger["events"]
    ):
        raise CampaignError("campaign ledger 未记录该 authorization 的 lease")


def _campaign_from_payload(payload: dict[str, object], raw_bytes: bytes) -> CampaignManifest:
    digest, byte_length = sha256_identity(raw_bytes)
    identity = CampaignIdentity(payload["campaign_id"], digest, byte_length)
    authorizations = tuple(
        CampaignAuthorization(
            authorization_id=entry["authorization_id"],
            experiment_manifest=_manifest_identity(entry["experiment_manifest"]),
            cpu_reservation_milliseconds=entry["cpu_reservation_milliseconds"],
            wall_reservation_milliseconds=entry["wall_reservation_milliseconds"],
            artifact_reservation_bytes=entry["artifact_reservation_bytes"],
        )
        for entry in payload["authorizations"]
    )
    return CampaignManifest(
        identity=identity,
        git_commit=payload["code_identity"]["git_commit"],
        trainer_version=payload["code_identity"]["trainer_version"],
        preflight_attestation=_preflight_identity(payload["preflight_attestation"]),
        cpu_limit_milliseconds=payload["limits"]["cpu_limit_milliseconds"],
        wall_limit_milliseconds=payload["limits"]["wall_limit_milliseconds"],
        peak_rss_limit_bytes=payload["limits"]["peak_rss_limit_bytes"],
        retained_artifact_limit_bytes=payload["limits"]["retained_artifact_limit_bytes"],
        authorizations=authorizations,
    )


def _campaign_payload(campaign: CampaignManifest) -> dict[str, object]:
    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "record_type": CAMPAIGN_TYPE,
        "campaign_id": campaign.identity.campaign_id,
        "code_identity": {
            "git_commit": campaign.git_commit,
            "trainer_version": campaign.trainer_version,
        },
        "preflight_attestation": campaign.preflight_attestation.as_payload(),
        "limits": {
            "cpu_limit_milliseconds": campaign.cpu_limit_milliseconds,
            "wall_limit_milliseconds": campaign.wall_limit_milliseconds,
            "peak_rss_limit_bytes": campaign.peak_rss_limit_bytes,
            "retained_artifact_limit_bytes": campaign.retained_artifact_limit_bytes,
            "max_concurrency": 1,
        },
        "authorizations": [
            {
                "authorization_id": authorization.authorization_id,
                "experiment_manifest": authorization.experiment_manifest.as_payload(),
                "cpu_reservation_milliseconds": authorization.cpu_reservation_milliseconds,
                "wall_reservation_milliseconds": authorization.wall_reservation_milliseconds,
                "artifact_reservation_bytes": authorization.artifact_reservation_bytes,
            }
            for authorization in campaign.authorizations
        ],
    }


def _parse_campaign_payload(value: object) -> dict[str, object]:
    payload = _exact_mapping(
        value,
        {
            "schema_version",
            "record_type",
            "campaign_id",
            "code_identity",
            "preflight_attestation",
            "limits",
            "authorizations",
        },
        "campaign manifest",
    )
    if (
        payload["schema_version"] != CAMPAIGN_SCHEMA_VERSION
        or payload["record_type"] != CAMPAIGN_TYPE
    ):
        raise CampaignError("campaign manifest 版本不兼容")
    code = _exact_mapping(
        payload["code_identity"], {"git_commit", "trainer_version"}, "campaign code identity"
    )
    limits = _exact_mapping(
        payload["limits"],
        {
            "cpu_limit_milliseconds",
            "wall_limit_milliseconds",
            "peak_rss_limit_bytes",
            "retained_artifact_limit_bytes",
            "max_concurrency",
        },
        "campaign limits",
    )
    if limits["max_concurrency"] != 1:
        raise CampaignError("campaign 只允许单并发")
    authorizations = _parse_authorizations(payload["authorizations"])
    reservations = {
        field: sum(entry[field] for entry in authorizations)
        for field in (
            "cpu_reservation_milliseconds",
            "wall_reservation_milliseconds",
            "artifact_reservation_bytes",
        )
    }
    parsed = {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "record_type": CAMPAIGN_TYPE,
        "campaign_id": _require_id(payload["campaign_id"], "campaign_id"),
        "code_identity": {
            "git_commit": _require_commit(code["git_commit"]),
            "trainer_version": _require_version(code["trainer_version"]),
        },
        "preflight_attestation": _preflight_identity(payload["preflight_attestation"]).as_payload(),
        "limits": {
            "cpu_limit_milliseconds": _require_int(
                limits["cpu_limit_milliseconds"], "campaign CPU 上限", minimum=1
            ),
            "wall_limit_milliseconds": _require_int(
                limits["wall_limit_milliseconds"], "campaign 墙钟上限", minimum=1
            ),
            "peak_rss_limit_bytes": _require_int(
                limits["peak_rss_limit_bytes"], "campaign RSS 上限", minimum=1
            ),
            "retained_artifact_limit_bytes": _require_int(
                limits["retained_artifact_limit_bytes"], "campaign 工件上限", minimum=1
            ),
            "max_concurrency": 1,
        },
        "authorizations": authorizations,
    }
    if reservations["cpu_reservation_milliseconds"] > parsed["limits"]["cpu_limit_milliseconds"]:
        raise CampaignError("authorization CPU 预留总和超过 campaign 上限")
    if reservations["wall_reservation_milliseconds"] > parsed["limits"]["wall_limit_milliseconds"]:
        raise CampaignError("authorization 墙钟预留总和超过 campaign 上限")
    if (
        reservations["artifact_reservation_bytes"]
        > parsed["limits"]["retained_artifact_limit_bytes"]
    ):
        raise CampaignError("authorization 工件预留总和超过 campaign 上限")
    return parsed


def _parse_authorizations(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise CampaignError("campaign 必须预注册至少一个 authorization")
    parsed = []
    for entry in value:
        authorization = _exact_mapping(
            entry,
            {
                "authorization_id",
                "experiment_manifest",
                "cpu_reservation_milliseconds",
                "wall_reservation_milliseconds",
                "artifact_reservation_bytes",
            },
            "campaign authorization",
        )
        parsed.append(
            {
                "authorization_id": _require_id(
                    authorization["authorization_id"], "authorization_id"
                ),
                "experiment_manifest": _manifest_identity(
                    authorization["experiment_manifest"]
                ).as_payload(),
                "cpu_reservation_milliseconds": _require_int(
                    authorization["cpu_reservation_milliseconds"], "CPU 预留", minimum=1
                ),
                "wall_reservation_milliseconds": _require_int(
                    authorization["wall_reservation_milliseconds"], "墙钟预留", minimum=1
                ),
                "artifact_reservation_bytes": _require_int(
                    authorization["artifact_reservation_bytes"], "工件预留", minimum=1
                ),
            }
        )
    if [entry["authorization_id"] for entry in parsed] != sorted(
        entry["authorization_id"] for entry in parsed
    ):
        raise CampaignError("authorization 必须按 id 升序冻结")
    if len({entry["authorization_id"] for entry in parsed}) != len(parsed):
        raise CampaignError("authorization id 不能重复")
    return parsed


def _manifest_identity(value: object) -> ManifestIdentity:
    payload = _exact_mapping(
        value,
        {"manifest_type", "schema_version", "manifest_id", "sha256", "byte_length"},
        "experiment manifest identity",
    )
    if payload["manifest_type"] != "multiplayer-cfr-experiment":
        raise CampaignError("authorization 必须绑定 experiment manifest")
    return ManifestIdentity(
        manifest_type=payload["manifest_type"],
        schema_version=_require_int(payload["schema_version"], "experiment schema", minimum=1),
        manifest_id=_require_id(payload["manifest_id"], "experiment manifest_id"),
        sha256=_require_hash(payload["sha256"]),
        byte_length=_require_int(payload["byte_length"], "experiment byte_length", minimum=1),
    )


def _preflight_identity(value: object) -> PreflightIdentity:
    payload = _exact_mapping(
        value,
        {"record_type", "schema_version", "record_id", "sha256", "byte_length"},
        "preflight attestation identity",
    )
    if payload["record_type"] != "multiplayer-cfr-estimator-attestation":
        raise CampaignError("campaign 必须绑定 estimator attestation")
    return PreflightIdentity(
        record_type=payload["record_type"],
        schema_version=_require_int(payload["schema_version"], "preflight schema", minimum=1),
        record_id=_require_id(payload["record_id"], "preflight record_id"),
        sha256=_require_hash(payload["sha256"]),
        byte_length=_require_int(payload["byte_length"], "preflight byte_length", minimum=1),
    )


def _require_campaign_root(root: str | Path) -> Path:
    path = Path(root)
    if not path.is_dir() or path.is_symlink():
        raise CampaignError("campaign 根目录必须是现有非链接目录")
    return path


def _is_within(path: Path, root: Path) -> bool:
    """解析后判断路径是否位于根目录之内，用于拒绝越界拼接。"""

    try:
        resolved_root = root.resolve()
        resolved = path.resolve()
    except OSError:
        return False
    return resolved == resolved_root or resolved.is_relative_to(resolved_root)


def _acquire_lock(root: Path) -> int:
    lock_path = root / ".campaign.lock"
    try:
        descriptor = os.open(
            lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        raise CampaignError("campaign 已被其他执行占用") from error
    return descriptor


def _load_ledger(root: Path, campaign: CampaignManifest) -> dict[str, object]:
    ledger_path = root / "campaign-ledger.json"
    if not ledger_path.exists():
        return {
            "schema_version": CAMPAIGN_SCHEMA_VERSION,
            "record_type": CAMPAIGN_LEDGER_TYPE,
            "campaign": campaign.identity.as_payload(),
            "events": [],
        }
    try:
        payload, _ = load_canonical_json(ledger_path, maximum_bytes=MAX_TEXT_BYTES)
    except SafeJsonError as error:
        raise CampaignError("无法安全读取 campaign ledger") from error
    ledger = _exact_mapping(
        payload, {"schema_version", "record_type", "campaign", "events"}, "campaign ledger"
    )
    if (
        ledger["schema_version"] != CAMPAIGN_SCHEMA_VERSION
        or ledger["record_type"] != CAMPAIGN_LEDGER_TYPE
        or ledger["campaign"] != campaign.identity.as_payload()
        or not isinstance(ledger["events"], list)
    ):
        raise CampaignError("campaign ledger 与冻结 campaign 不兼容")
    for event in ledger["events"]:
        _exact_mapping(event, _EVENT_FIELDS, "campaign ledger event")
    return ledger


def _write_ledger(root: Path, ledger: dict[str, object]) -> None:
    replace_canonical_json(root, "campaign-ledger.json", ledger, maximum_bytes=MAX_TEXT_BYTES)


def _append_event(ledger: dict[str, object], event: dict[str, object]) -> None:
    events = ledger["events"]
    if not isinstance(events, list):
        raise CampaignError("campaign ledger events 不兼容")
    events.append(event)


def _find_authorization(campaign: CampaignManifest, authorization_id: str) -> CampaignAuthorization:
    for authorization in campaign.authorizations:
        if authorization.authorization_id == authorization_id:
            return authorization
    raise CampaignError("authorization 不属于冻结 campaign")


def _exact_mapping(value: object, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise CampaignError(f"{label}字段不匹配")
    return value


def _require_int(value: object, label: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CampaignError(f"{label}必须是不小于 {minimum} 的整数")
    return value


def _require_id(value: object, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise CampaignError(f"{label}必须是受控标识")
    return value


def _require_commit(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise CampaignError("campaign git_commit 不兼容")
    return value


def _require_version(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise CampaignError("campaign trainer_version 不兼容")
    return value


def _require_hash(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise CampaignError("SHA-256 不兼容")
    return value
