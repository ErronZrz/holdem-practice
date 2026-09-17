"""候选 A 的静态资源结构估算，不采集或运行训练。"""

from __future__ import annotations

from dataclasses import dataclass

from .game import StructureCounts, structure_counts, validate_player_count

_MEBIBYTE = 1024 * 1024
_STATE_BUDGET_BYTES = {6: 32 * _MEBIBYTE, 7: 96 * _MEBIBYTE, 9: 512 * _MEBIBYTE}
_ARTIFACT_BUDGET_BYTES = {6: 4 * _MEBIBYTE, 7: 12 * _MEBIBYTE, 9: 64 * _MEBIBYTE}


@dataclass(frozen=True)
class ResourceEstimate:
    """来自已确认预算表的结构预留，不是 RSS 或耗时实测。"""

    structure: StructureCounts
    state_budget_bytes: int
    artifact_budget_bytes: int


def estimate_resources(player_count: int) -> ResourceEstimate:
    """按人数返回规则树规模及对应的静态预留上限。"""

    player_count = validate_player_count(player_count)
    return ResourceEstimate(
        structure=structure_counts(player_count),
        state_budget_bytes=_STATE_BUDGET_BYTES[player_count],
        artifact_budget_bytes=_ARTIFACT_BUDGET_BYTES[player_count],
    )
