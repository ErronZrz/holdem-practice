"""受控策略产物加载与查表：把已冻结的离线产物变成可查的动作分布。

设计目的：
- 产物是**不可信输入**：只接受受限的 JSON，逐项校验字段、版本、人数、动作与概率单位，
  不 pickle、不导入模块路径、不执行产物内任何内容、对未知键不回退；
- 查表只认受控抽象键：命中才返回动作整数单位，未命中一律明确失败，
  绝不用最近桶、默认桶、补零、插值或跨人数折算来冒充精确；
- 未覆盖时只给出可追溯的回退来源声明，不执行任何回退动作，也不改变策略分派。

本模块不联网、不读环境变量、不写文件：它只把调用方给定的路径读成内存中的查表结构。
"""

import json
import os
import stat
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from app.strategy.abstraction import (
    ABSTRACTION_ACTIONS,
    ABSTRACTION_GAME_VERSION,
    ABSTRACTION_ROOT_HISTORY,
    ABSTRACTION_TRAINED_PLAYER_COUNTS,
    DEFAULT_FALLBACK_IDENTIFIER,
    FallbackDeclaration,
    FallbackTrigger,
    declared_fallback,
    judge_coverage,
)

ARTIFACT_TYPE = "multiplayer-cfr-average-strategy"
ARTIFACT_SCHEMA_VERSION = 1
# 产物大小上限：与离线导出侧的声明上界同量级，在此以本地常量重申，不依赖任何外部代码。
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

_EXPECTED_TOP_LEVEL_KEYS = frozenset(
    {
        "artifact_type",
        "game",
        "infosets",
        "probability_units",
        "quality",
        "resources",
        "schema_version",
        "training",
    }
)
_EXPECTED_GAME_KEYS = frozenset(
    {
        "action_tree_version",
        "ante",
        "bet",
        "deck",
        "id",
        "player_count",
        "remainder_priority",
        "seat_semantics",
        "tie_rule",
        "version",
    }
)
_EXPECTED_DECK_KEYS = frozenset({"copies_per_rank", "rank_count"})
_EXPECTED_INFOSET_KEYS = frozenset(
    {"actions", "actor", "history", "key", "legal_actions", "public_state", "rank"}
)
_EXPECTED_PUBLIC_STATE_KEYS = frozenset(
    {
        "active",
        "actor",
        "contributions",
        "folded",
        "opener",
        "pending_responders",
        "terminal",
    }
)
_LEGAL_ACTION_SETS = (frozenset({"x", "b"}), frozenset({"c", "f"}))

LookupStatus = Literal[
    "hit",
    "out-of-abstraction",
    "incomplete-infoset",
    "version-mismatch",
    "artifact-unavailable",
    "artifact-mismatch",
    "key-not-in-artifact",
]


class StrategyArtifactError(ValueError):
    """策略产物违反受控格式或抽象边界时抛出。"""


class _FrozenModel(BaseModel):
    """本模块全部对外模型的公共基类：冻结、禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ArtifactIdentity(_FrozenModel):
    """产物字节身份：用于把测量结果绑定到确定的产物内容。"""

    sha256: str
    byte_length: int


class ArtifactGame(_FrozenModel):
    """产物声明的抽象博弈标识。"""

    game_id: str
    game_version: str
    player_count: int


class StrategyInfoset(_FrozenModel):
    """一条已验证的信息集：动作整数单位之和恒等于全局概率单位。"""

    key: str
    actor: int
    rank: int
    history: str
    legal_actions: tuple[str, ...]
    action_units: dict[str, int]


class StrategyArtifact(_FrozenModel):
    """一份已验证的策略产物；质量、训练与资源段落原样保留供审计。"""

    identity: ArtifactIdentity
    schema_version: int
    artifact_type: str
    game: ArtifactGame
    probability_units: int
    infosets: tuple[StrategyInfoset, ...]
    quality: dict[str, Any]
    training: dict[str, Any]
    resources: dict[str, Any]


class LookupOutcome(_FrozenModel):
    """一次查表的结果：只有命中有动作分布，其余状态一律为空并附带回退声明。"""

    status: LookupStatus
    artifact_identity: ArtifactIdentity | None = None
    abstraction_key: str | None = None
    action_units: dict[str, int] | None = None
    reasons: tuple[str, ...] = ()
    fallback: FallbackDeclaration | None = None

    @property
    def is_hit(self) -> bool:
        """是否精确命中了产物中的该信息集。"""
        return self.status == "hit"


class LookupTable(_FrozenModel):
    """一份已验证产物的查表索引。"""

    artifact: StrategyArtifact
    _index: dict[str, StrategyInfoset] = PrivateAttr(default_factory=dict)

    @model_validator(mode="after")
    def _index_infosets(self) -> "LookupTable":
        index = {item.key: item for item in self.artifact.infosets}
        if len(index) != len(self.artifact.infosets):
            raise ValueError("策略产物存在重复信息集键")
        object.__setattr__(self, "_index", index)
        return self

    @property
    def player_count(self) -> int:
        """该产物声明的人数。"""
        return self.artifact.game.player_count

    @property
    def infoset_count(self) -> int:
        """该产物收录的信息集条数。"""
        return len(self.artifact.infosets)

    def entry_for(self, key: str) -> StrategyInfoset | None:
        """按键精确取信息集；不存在即返回 None，不做任何近似。"""
        return self._index.get(key)


class LookupRegistry(_FrozenModel):
    """按人数装载的产物集合；缺失或错配一律明确报告，不静默降级。"""

    by_player_count: dict[int, LookupTable] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_duplicate_player_counts(self) -> "LookupRegistry":
        counts = list(self.by_player_count)
        if any(isinstance(count, bool) or not isinstance(count, int) for count in counts):
            raise ValueError("产物人数键必须是整数")
        return self

    @property
    def loaded_player_counts(self) -> tuple[int, ...]:
        """已装载产物的人数，供报告与测试枚举。"""
        return tuple(sorted(self.by_player_count))

    def lookup(
        self,
        *,
        game_version: str | None = None,
        player_count: int | None = None,
        relative_actor: int | None = None,
        own_rank: int | None = None,
        canonical_public_history: str | None = None,
    ) -> LookupOutcome:
        """按受控抽象投影查表；未命中给出显式状态与回退来源声明。"""
        verdict = judge_coverage(
            game_version=game_version,
            player_count=player_count,
            relative_actor=relative_actor,
            own_rank=own_rank,
            canonical_public_history=canonical_public_history,
        )
        if not verdict.is_in_abstraction or verdict.projection is None:
            fallback = declared_fallback(verdict)
            if fallback is None:
                raise StrategyArtifactError("抽象外局面必须能够声明回退来源")
            return LookupOutcome(
                status=verdict.coverage,
                abstraction_key=verdict.abstraction_key,
                reasons=verdict.reasons,
                fallback=fallback,
            )

        projection = verdict.projection
        table = self.by_player_count.get(projection.player_count)
        if table is None:
            return _uncovered_outcome(
                "artifact-unavailable",
                verdict.abstraction_key,
                (f"人数 {projection.player_count} 没有已加载的策略产物",),
            )
        if (
            table.artifact.game.player_count != projection.player_count
            or table.artifact.game.game_version != projection.game_version
        ):
            return _uncovered_outcome(
                "artifact-mismatch",
                verdict.abstraction_key,
                (
                    "已加载产物与请求不一致："
                    f"产物 n={table.artifact.game.player_count}"
                    f"/version={table.artifact.game.game_version}，"
                    f"请求 n={projection.player_count}/version={projection.game_version}",
                ),
                identity=table.artifact.identity,
            )

        entry = table.entry_for(verdict.abstraction_key)
        if entry is None:
            return _uncovered_outcome(
                "key-not-in-artifact",
                verdict.abstraction_key,
                ("该信息集在抽象内，但此产物未收录，按未覆盖处理",),
                identity=table.artifact.identity,
            )
        return LookupOutcome(
            status="hit",
            artifact_identity=table.artifact.identity,
            abstraction_key=verdict.abstraction_key,
            action_units=dict(entry.action_units),
        )


def _uncovered_outcome(
    trigger: FallbackTrigger,
    abstraction_key: str | None,
    reasons: tuple[str, ...],
    *,
    identity: ArtifactIdentity | None = None,
) -> LookupOutcome:
    """构造一个未覆盖结果：无动作分布，只有状态、原因与回退来源声明。"""
    return LookupOutcome(
        status=trigger,
        artifact_identity=identity,
        abstraction_key=abstraction_key,
        action_units=None,
        reasons=reasons,
        fallback=FallbackDeclaration(
            fallback_identifier=DEFAULT_FALLBACK_IDENTIFIER,
            triggering_coverage=trigger,
            abstraction_key=abstraction_key,
            reasons=reasons,
        ),
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise StrategyArtifactError(f"策略产物存在重复键：{key}")
        payload[key] = value
    return payload


def _reject_non_finite_constant(value: str) -> None:
    raise StrategyArtifactError(f"策略产物不允许非有限数值：{value}")


def _read_regular_file(path: str | Path) -> bytes:
    """通过非链接描述符读取受限大小的普通文件。"""
    try:
        descriptor = os.open(Path(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise StrategyArtifactError("无法读取策略产物") from error
    try:
        details = os.fstat(descriptor)
    except OSError as error:
        os.close(descriptor)
        raise StrategyArtifactError("无法读取策略产物") from error
    if not stat.S_ISREG(details.st_mode):
        os.close(descriptor)
        raise StrategyArtifactError("策略产物必须是非链接普通文件")
    try:
        with os.fdopen(descriptor, "rb") as source:
            raw_bytes = source.read(MAX_ARTIFACT_BYTES + 1)
    except OSError as error:
        raise StrategyArtifactError("无法读取策略产物") from error
    if len(raw_bytes) > MAX_ARTIFACT_BYTES:
        raise StrategyArtifactError("策略产物超过大小上限")
    return raw_bytes


def _decode_payload(raw_bytes: bytes) -> dict[str, Any]:
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeError as error:
        raise StrategyArtifactError("策略产物必须是 UTF-8 文本") from error
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite_constant,
        )
    except json.JSONDecodeError as error:
        raise StrategyArtifactError("策略产物不是有效 JSON") from error
    if not isinstance(payload, dict):
        raise StrategyArtifactError("策略产物顶层必须是对象")
    return payload


def _require_exact_keys(value: Any, expected: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise StrategyArtifactError(f"{label} 字段集不匹配")
    return value


def _require_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StrategyArtifactError(f"{label} 必须是整数")
    if minimum is not None and value < minimum:
        raise StrategyArtifactError(f"{label} 不能小于 {minimum}")
    return value


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise StrategyArtifactError(f"{label} 必须是非空字符串")
    return value


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise StrategyArtifactError(f"{label} 必须是布尔值")
    return value


def _require_int_or_none(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, label, minimum=0)


def _require_int_list(value: Any, label: str) -> list[int]:
    if not isinstance(value, list):
        raise StrategyArtifactError(f"{label} 必须是数组")
    return [_require_int(item, label, minimum=0) for item in value]


def _derive_public_projection(player_count: int, history: str) -> dict[str, Any]:
    """由规范公开历史复算公开投影，用于核对产物自述的投影字段。

    这里只做 token 计数与顺序算术：历史本身的规则合法性已由抽象层校验。
    """
    tokens = () if history == ABSTRACTION_ROOT_HISTORY else tuple(history.split("|"))
    folded: set[int] = set()
    contributions = [1] * player_count
    opener: int | None = None
    replies = 0
    for token in tokens:
        action, separator, seat_text = token.partition("@")
        if separator != "@" or not seat_text.isdigit():
            raise StrategyArtifactError("信息集公开历史形式不规范")
        seat = int(seat_text)
        if seat >= player_count:
            raise StrategyArtifactError("信息集公开历史的座位超出人数范围")
        if action == "b":
            opener = seat
            contributions[seat] += 1
        elif action == "c":
            contributions[seat] += 1
            replies += 1
        elif action == "f":
            folded.add(seat)
            replies += 1
    if opener is None:
        actor = len(tokens)
        pending: list[int] = []
    else:
        response_order = [(opener + offset) % player_count for offset in range(1, player_count)]
        actor = response_order[replies]
        pending = response_order[replies:]
    return {
        "actor": actor,
        "opener": opener,
        "folded": sorted(folded),
        "active": sorted(set(range(player_count)) - folded),
        "contributions": contributions,
        "pending_responders": pending,
        "terminal": False,
    }


def _parse_public_state(value: Any, *, history: str, player_count: int) -> None:
    """核对产物自述的公开投影与公开历史是否一致，错位一律失败。"""
    projection = _require_exact_keys(value, _EXPECTED_PUBLIC_STATE_KEYS, "infoset.public_state")
    normalized = {
        "actor": _require_int(projection["actor"], "public_state.actor", minimum=0),
        "opener": _require_int_or_none(projection["opener"], "public_state.opener"),
        "folded": _require_int_list(projection["folded"], "public_state.folded"),
        "active": _require_int_list(projection["active"], "public_state.active"),
        "contributions": _require_int_list(
            projection["contributions"], "public_state.contributions"
        ),
        "pending_responders": _require_int_list(
            projection["pending_responders"], "public_state.pending_responders"
        ),
        "terminal": _require_bool(projection["terminal"], "public_state.terminal"),
    }
    if normalized != _derive_public_projection(player_count, history):
        raise StrategyArtifactError("信息集公开投影与公开历史不一致")


def _parse_game(value: Any) -> ArtifactGame:
    game = _require_exact_keys(value, _EXPECTED_GAME_KEYS, "game")
    deck = _require_exact_keys(game["deck"], _EXPECTED_DECK_KEYS, "game.deck")
    player_count = _require_int(game["player_count"], "game.player_count", minimum=1)
    if player_count not in ABSTRACTION_TRAINED_PLAYER_COUNTS:
        raise StrategyArtifactError("策略产物人数不在抽象合法人数内")
    if _require_int(deck["rank_count"], "game.deck.rank_count", minimum=1) != player_count:
        raise StrategyArtifactError("策略产物的牌组规模与人数不一致")
    if _require_int(deck["copies_per_rank"], "game.deck.copies_per_rank", minimum=1) != 1:
        raise StrategyArtifactError("策略产物必须使用唯一 rank 牌组")
    game_version = _require_str(game["version"], "game.version")
    if game_version != ABSTRACTION_GAME_VERSION:
        raise StrategyArtifactError("策略产物的抽象版本不受支持")
    if _require_int(game["ante"], "game.ante", minimum=1) != 1:
        raise StrategyArtifactError("策略产物的 ante 与抽象不一致")
    if _require_int(game["bet"], "game.bet", minimum=1) != 1:
        raise StrategyArtifactError("策略产物的固定下注与抽象不一致")
    return ArtifactGame(
        game_id=_require_str(game["id"], "game.id"),
        game_version=game_version,
        player_count=player_count,
    )


def _declared_infoset_count(payload: dict[str, Any]) -> int:
    """从质量与资源段落交叉核对收录条数，任一处缺失或不一致都失败。"""
    quality = payload["quality"]
    if not isinstance(quality, dict):
        raise StrategyArtifactError("quality 必须是对象")
    coverage = quality.get("coverage")
    if not isinstance(coverage, dict):
        raise StrategyArtifactError("quality.coverage 必须是对象")
    resources = payload["resources"]
    if not isinstance(resources, dict):
        raise StrategyArtifactError("resources 必须是对象")
    from_quality = _require_int(
        coverage.get("total_infosets"), "quality.coverage.total_infosets", minimum=1
    )
    from_resources = _require_int(
        resources.get("infoset_count"), "resources.infoset_count", minimum=1
    )
    if from_quality != from_resources:
        raise StrategyArtifactError("质量与资源段落的收录条数互相矛盾")
    return from_quality


def _expected_legal_actions(history: str) -> tuple[str, ...]:
    """由公开历史判断当前阶段：开池前只允许开池或过牌，开池后只允许跟注或弃牌。"""
    actions = {
        token.partition("@")[0]
        for token in history.split("|")
        if token and token != ABSTRACTION_ROOT_HISTORY
    }
    return ("c", "f") if "b" in actions else ("x", "b")


def _parse_infoset(
    value: Any,
    *,
    game: ArtifactGame,
    probability_units: int,
    seen_keys: set[str],
) -> StrategyInfoset:
    entry = _require_exact_keys(value, _EXPECTED_INFOSET_KEYS, "infoset")
    actor = _require_int(entry["actor"], "infoset.actor", minimum=0)
    rank = _require_int(entry["rank"], "infoset.rank", minimum=0)
    if actor >= game.player_count or rank >= game.player_count:
        raise StrategyArtifactError("信息集的行动者或 rank 超出人数范围")
    history = _require_str(entry["history"], "infoset.history")
    key = _require_str(entry["key"], "infoset.key")

    legal_raw = entry["legal_actions"]
    if not isinstance(legal_raw, list):
        raise StrategyArtifactError("信息集 legal_actions 必须是数组")
    legal_actions = tuple(_require_str(item, "infoset.legal_actions") for item in legal_raw)
    if frozenset(legal_actions) not in _LEGAL_ACTION_SETS or len(legal_actions) != 2:
        raise StrategyArtifactError("信息集合法动作不是该抽象的两个固定动作")
    if frozenset(legal_actions) != frozenset(_expected_legal_actions(history)):
        raise StrategyArtifactError("信息集合法动作与公开历史所处阶段不一致")

    actions_raw = entry["actions"]
    if not isinstance(actions_raw, dict):
        raise StrategyArtifactError("信息集 actions 必须是对象")
    for action in actions_raw:
        if action not in ABSTRACTION_ACTIONS:
            raise StrategyArtifactError("信息集包含未知动作")
    if set(actions_raw) != set(legal_actions):
        raise StrategyArtifactError("信息集动作集合与合法动作不一致")
    action_units = {
        action: _require_int(units, f"infoset.actions.{action}", minimum=0)
        for action, units in actions_raw.items()
    }
    if sum(action_units.values()) != probability_units:
        raise StrategyArtifactError("信息集动作单位之和与概率单位不一致")

    verdict = judge_coverage(
        game_version=game.game_version,
        player_count=game.player_count,
        relative_actor=actor,
        own_rank=rank,
        canonical_public_history=history,
    )
    if not verdict.is_in_abstraction or verdict.abstraction_key is None:
        raise StrategyArtifactError("信息集不在该抽象内")
    if verdict.abstraction_key != key:
        raise StrategyArtifactError("信息集键与规范重算结果不一致")
    _parse_public_state(entry["public_state"], history=history, player_count=game.player_count)
    if key in seen_keys:
        raise StrategyArtifactError("策略产物存在重复信息集键")
    seen_keys.add(key)
    return StrategyInfoset(
        key=key,
        actor=actor,
        rank=rank,
        history=history,
        legal_actions=legal_actions,
        action_units=action_units,
    )


def load_strategy_artifact(path: str | Path) -> StrategyArtifact:
    """读取并逐项校验一份策略产物；任一项不通过即明确失败。"""
    raw_bytes = _read_regular_file(path)
    payload = _require_exact_keys(_decode_payload(raw_bytes), _EXPECTED_TOP_LEVEL_KEYS, "策略产物")
    if _require_str(payload["artifact_type"], "artifact_type") != ARTIFACT_TYPE:
        raise StrategyArtifactError("策略产物类型不受支持")
    schema_version = _require_int(payload["schema_version"], "schema_version", minimum=1)
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        raise StrategyArtifactError("策略产物结构版本不受支持")
    probability_units = _require_int(payload["probability_units"], "probability_units", minimum=1)
    game = _parse_game(payload["game"])

    declared_count = _declared_infoset_count(payload)
    infosets_raw = payload["infosets"]
    if not isinstance(infosets_raw, list) or not infosets_raw:
        raise StrategyArtifactError("策略产物必须包含非空的信息集列表")
    if len(infosets_raw) != declared_count:
        raise StrategyArtifactError("信息集条数与声明条数不一致")

    identity = ArtifactIdentity(sha256=sha256(raw_bytes).hexdigest(), byte_length=len(raw_bytes))
    declared_bytes = _require_int(
        payload["resources"].get("artifact_bytes"), "artifact_bytes", minimum=1
    )
    if declared_bytes != identity.byte_length:
        raise StrategyArtifactError("策略产物声明的字节数与实际不一致")

    seen_keys: set[str] = set()
    infosets = tuple(
        _parse_infoset(
            value,
            game=game,
            probability_units=probability_units,
            seen_keys=seen_keys,
        )
        for value in infosets_raw
    )
    if len(seen_keys) != len(infosets):
        raise StrategyArtifactError("策略产物存在重复信息集键")
    training = payload["training"]
    if not isinstance(training, dict):
        raise StrategyArtifactError("training 必须是对象")
    return StrategyArtifact(
        identity=identity,
        schema_version=schema_version,
        artifact_type=ARTIFACT_TYPE,
        game=game,
        probability_units=probability_units,
        infosets=infosets,
        quality=dict(payload["quality"]),
        training=dict(training),
        resources=dict(payload["resources"]),
    )


def load_lookup_table(path: str | Path) -> LookupTable:
    """读取产物并建立查表索引。"""
    return LookupTable(artifact=load_strategy_artifact(path))


def load_lookup_registry(paths: Iterable[str | Path]) -> LookupRegistry:
    """按各产物自报人数装载查表集合；同一人数出现多份产物即明确失败。"""
    by_player_count: dict[int, LookupTable] = {}
    for path in paths:
        table = load_lookup_table(path)
        if table.player_count in by_player_count:
            raise StrategyArtifactError(f"人数 {table.player_count} 装载了多份产物")
        by_player_count[table.player_count] = table
    return LookupRegistry(by_player_count=by_player_count)
