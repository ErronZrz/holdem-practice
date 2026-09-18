"""候选 A 测量结果的只读多 seed 判定层：把「阈值偏离」的读法固定下来。

本模块只做两件事：

- **固定判定对象与方向**：判定对象是钳位后的逐座位最大非负增益 ``probes.gains``，
  同时必须如实报告双向 ``results[].delta``（正负都报），避免只看「阈值策略更强」的单侧；
- **强制多 seed 与人数隔离**：观测数少于两个时明确失败（单 seed 不判定），
  不同人数的观测不得合并判定（各自独立、不作跨人数归因）。

本模块**不产生合格 / 不合格结论**：判定结果只作解释性指标，门槛是否启用留给单独签收。
只读边界：不读文件系统与网络，不调用任何训练 / 评估 / 测量原语，不写回任何工件。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from .measurement import MeasurementRecord, RationalValue

# 阈值偏离的解释边界（BB/hand）：沿用既有的 0.05 解释线，不是本模块新设的门禁线。
DEFAULT_THRESHOLD = Fraction(1, 20)
# 单 seed 不判定：至少需要两个预注册 seed 的观测才给出判定。
MIN_OBSERVATIONS = 2
# 解释性状态取值：刻意不含「合格 / 不合格 / 通过 / 达标」措辞。
STATUS_EXCEEDS = "exceeds-threshold-observed"
STATUS_NOT_OBSERVED = "threshold-not-observed"


class QualityGateError(ValueError):
    """观测不满足多 seed 或人数隔离契约、或记录未完成探测时抛出。"""


def _require_fraction(value: object, label: str) -> Fraction:
    """只接受精确有理数，避免浮点近似悄悄进入判定。"""
    if not isinstance(value, Fraction):
        raise QualityGateError(f"{label} 必须是精确有理数")
    return value


def _require_non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise QualityGateError(f"{label} 必须是非负整数")
    return value


@dataclass(frozen=True)
class ProbeDelta:
    """一条阈值 probe 的收益差观测；正负都保留，用于双向报告。"""

    player: int
    probe_id: str
    delta: Fraction

    def __post_init__(self) -> None:
        _require_non_negative_int(self.player, "座位号")
        if not isinstance(self.probe_id, str) or not self.probe_id:
            raise QualityGateError("probe 标识必须是非空字符串")
        _require_fraction(self.delta, "probe delta")


@dataclass(frozen=True)
class SeedObservation:
    """单个预注册 seed 的一次测量观测（只读、来自已落盘记录）。

    构造时会校验钳位派生关系：``gains[player]`` 必须等于该座位全部 probe delta 的
    ``max(0, ...)``，否则判定对象与双向报告自相矛盾。
    """

    seed: int
    player_count: int
    gains: tuple[Fraction, ...]
    deltas: tuple[ProbeDelta, ...]

    def __post_init__(self) -> None:
        _require_non_negative_int(self.seed, "seed")
        player_count = self.player_count
        if isinstance(player_count, bool) or not isinstance(player_count, int) or player_count < 2:
            raise QualityGateError("人数必须是至少两人的整数")
        if len(self.gains) != player_count:
            raise QualityGateError("gains 长度必须等于人数")
        for gain in self.gains:
            _require_fraction(gain, "gains 元素")
            if gain < 0:
                raise QualityGateError("gains 不能为负（判定对象是钳位后的非负增益）")
        if not self.deltas:
            raise QualityGateError("观测必须包含双向 delta，否则无法如实报告偏离方向")
        covered = set()
        for item in self.deltas:
            if item.player >= player_count:
                raise QualityGateError("delta 座位号超出人数范围")
            covered.add(item.player)
        if covered != set(range(player_count)):
            raise QualityGateError("delta 必须覆盖全部座位，否则判定对象不完整")
        for player in range(player_count):
            clamped = max(
                (item.delta for item in self.deltas if item.player == player),
                default=Fraction(0),
            )
            if self.gains[player] != max(clamped, Fraction(0)):
                raise QualityGateError("gains 必须是同座位 delta 的钳位最大值")


@dataclass(frozen=True)
class ThresholdVerdict:
    """一组同人数观测的解释性判定结果；不含任何合格性结论。"""

    player_count: int
    threshold: Fraction
    seeds: tuple[int, ...]
    exceeded_seeds: tuple[int, ...]
    max_gain: Fraction
    max_gain_seed: int
    max_gain_player: int
    max_positive_delta: Fraction
    min_negative_delta: Fraction

    @property
    def status(self) -> str:
        """只在「观察到超线」与「未观察到超线」之间取值。"""
        return STATUS_EXCEEDS if self.exceeded_seeds else STATUS_NOT_OBSERVED

    def summary(self) -> dict[str, object]:
        """返回只读报告字段，供复算记录如实抄录。"""
        return {
            "player_count": self.player_count,
            "threshold": str(self.threshold),
            "seeds": list(self.seeds),
            "exceeded_seeds": list(self.exceeded_seeds),
            "max_gain": str(self.max_gain),
            "max_gain_seed": self.max_gain_seed,
            "max_gain_player": self.max_gain_player,
            "max_positive_delta": str(self.max_positive_delta),
            "min_negative_delta": str(self.min_negative_delta),
            "status": self.status,
        }


def evaluate_gains_threshold(
    observations: Iterable[SeedObservation],
    *,
    threshold: Fraction = DEFAULT_THRESHOLD,
) -> ThresholdVerdict:
    """对一组同人数的多 seed 观测给出解释性判定。

    单 seed、重复 seed 或混合人数的输入都**明确失败**，不产生判定。
    """
    _require_fraction(threshold, "阈值")
    if threshold <= 0:
        raise QualityGateError("阈值必须为正数")
    items = tuple(observations)
    if len(items) < MIN_OBSERVATIONS:
        raise QualityGateError("单 seed 不判定：至少需要两个预注册 seed 的观测")
    counts = {item.player_count for item in items}
    if len(counts) != 1:
        raise QualityGateError("不同人数的观测不得合并判定")
    seeds = tuple(item.seed for item in items)
    if len(set(seeds)) != len(seeds):
        raise QualityGateError("观测 seed 不能重复")

    exceeded: list[int] = []
    max_gain = Fraction(0)
    max_gain_seed = seeds[0]
    max_gain_player = 0
    for item in items:
        if max(item.gains) > threshold:
            exceeded.append(item.seed)
        for player, gain in enumerate(item.gains):
            if gain > max_gain:
                max_gain, max_gain_seed, max_gain_player = gain, item.seed, player

    deltas = [entry.delta for item in items for entry in item.deltas]
    return ThresholdVerdict(
        player_count=items[0].player_count,
        threshold=threshold,
        seeds=seeds,
        exceeded_seeds=tuple(sorted(exceeded)),
        max_gain=max_gain,
        max_gain_seed=max_gain_seed,
        max_gain_player=max_gain_player,
        max_positive_delta=max(Fraction(0), *deltas),
        min_negative_delta=min(Fraction(0), *deltas),
    )


def observation_from_measurement(record: MeasurementRecord, *, seed: int) -> SeedObservation:
    """从已严格验证的测量记录提取单 seed 观测。

    记录必须已完成阈值 probe；未完成的探测明确失败，避免把未测量值当成零偏离。
    本函数只消费调用方已读入并验证过的记录对象，不读文件、不触发任何测量。
    """
    if not isinstance(record, MeasurementRecord):
        raise QualityGateError("只能从已验证的测量记录提取观测")
    payload = record.payload
    game = payload.get("game")
    probes = payload.get("probes")
    if not isinstance(game, dict) or not isinstance(probes, dict):
        raise QualityGateError("测量记录缺少 game 或 probes 段")
    player_count = game.get("player_count")
    if isinstance(player_count, bool) or not isinstance(player_count, int):
        raise QualityGateError("测量记录缺少合法的人数")
    if probes.get("status") != "completed":
        raise QualityGateError("未完成的阈值 probe 观测不能参与判定")
    gains_raw = probes.get("gains")
    results_raw = probes.get("results")
    if not isinstance(gains_raw, list) or not isinstance(results_raw, list):
        raise QualityGateError("已完成的阈值 probe 必须包含 gains 与 results")
    deltas = tuple(
        ProbeDelta(
            player=_require_non_negative_int(entry["player"], "probe.player"),
            probe_id=str(entry["probe_id"]),
            delta=_fraction_from_payload(entry["delta"], "probe.delta"),
        )
        for entry in results_raw
        if isinstance(entry, dict)
    )
    if len(deltas) != len(results_raw):
        raise QualityGateError("probe 结果必须是有理数条目")
    return SeedObservation(
        seed=seed,
        player_count=player_count,
        gains=tuple(_fraction_from_payload(value, "probes.gains") for value in gains_raw),
        deltas=deltas,
    )


def _fraction_from_payload(value: object, label: str) -> Fraction:
    """按既有规范有理数类型解析 payload，不另写一套解析与约分逻辑。"""
    if not isinstance(value, dict):
        raise QualityGateError(f"{label} 必须是规范有理数对象")
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if not isinstance(numerator, str) or not isinstance(denominator, str):
        raise QualityGateError(f"{label} 必须是规范有理数对象")
    return RationalValue(numerator=numerator, denominator=denominator).as_fraction()
