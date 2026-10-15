"""本地混合身份的开发标定入口。

只在命令行显式带上运行开关时才查询分布或推进对局。默认导入不做任何实测。
默认被测身份仍是第九版；传入第十版时沿用同一节点集与同一配对排期。
读数供开发对照，不代替独立验证，也不改默认策略。

用法（在 backend 目录下）：
    uv run python tools/ninth_identity_calibration.py --run
    uv run python tools/ninth_identity_calibration.py --run --identity mixed-local@10
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.api.schemas import CreateGameRequest  # noqa: E402
from app.strategy.distribution_observation import (  # noqa: E402
    PROBABILITY_UNITS,
    supported_declaration,
)
from app.strategy.mixed_strategy import (  # noqa: E402
    MIXED_STRATEGY_IDENTIFIER_V8,
    MIXED_STRATEGY_IDENTIFIER_V9,
    MIXED_STRATEGY_IDENTIFIER_V10,
    rules_for_identifier,
)
from app.strategy.registry import (  # noqa: E402
    capability_declaration,
    capability_health,
    observation_entry,
)
from tests.mixed_bot_judgment import (  # noqa: E402
    ACTIVE_ACTIONS,
    ACTIVE_DOMAIN_CATEGORY,
    OPPORTUNITY_MIN_GAP_PP,
    STYLE_PAIRS,
    opportunity_reading,
    targeting_diagnostic,
)
from tests.mixed_bot_states import apply_node, build_frozen_nodes  # noqa: E402
from tests.mixed_bot_validation import (  # noqa: E402
    ADVERSARIAL_FAMILY_SETS,
    MIXED_BIG_BLIND,
    MIXED_MAIN_SEEDS,
    _node_rows,
    adversarial_schedule,
    config_digest,
    frozen_manifest,
    play_adversarial_hand,
    run_adversarial_batch,
)


def _candidate_rows(observation: object) -> tuple[tuple[str, int, int], ...]:
    candidates = observation.candidates  # type: ignore[attr-defined]
    return tuple((item.action.value, item.amount, item.units) for item in candidates)


def _previous_identifier(identifier: str) -> str:
    """标定对照的上一身份。只接受已经登记分布观测的相邻两版。"""
    order = (
        MIXED_STRATEGY_IDENTIFIER_V8,
        MIXED_STRATEGY_IDENTIFIER_V9,
        MIXED_STRATEGY_IDENTIFIER_V10,
    )
    if identifier not in order[1:]:
        raise ValueError(f"标定身份必须是已登记分布观测的新身份，收到 {identifier}")
    return order[order.index(identifier) - 1]


def _observe_frozen_nodes(identifier: str) -> dict[str, object]:
    """在首套冻结节点上查询当前身份的分布，并与上一身份逐节点对照。"""
    current = observation_entry(identifier)
    previous = observation_entry(_previous_identifier(identifier))
    declaration = capability_declaration(identifier)
    nodes = build_frozen_nodes()
    compared = 0
    differed = 0
    differed_by_category: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    unit_failures = 0
    for fixture in nodes:
        applied = apply_node(fixture)
        state = applied.actor_state()
        legal = applied.legal_actions()
        category_counts[fixture.category] += 1
        left = current.observe(state, legal)
        right = previous.observe(state, legal)
        compared += 1
        if sum(item.units for item in left.candidates) != PROBABILITY_UNITS:
            unit_failures += 1
        if left.aggregation != "marginalized" or right.aggregation != "marginalized":
            unit_failures += 1
        if _candidate_rows(left) != _candidate_rows(right):
            differed += 1
            differed_by_category[fixture.category] += 1
    return {
        "health": capability_health().value,
        "declaration_matches_supported": declaration == supported_declaration(),
        "probability_units": PROBABILITY_UNITS,
        "nodes": len(nodes),
        "compared": compared,
        "unit_failures": unit_failures,
        "compared_with": _previous_identifier(identifier),
        "differed_from_previous": differed,
        "differed_by_category": dict(sorted(differed_by_category.items())),
        "category_counts": dict(sorted(category_counts.items())),
    }


def _rates(reading: object) -> dict[str, object]:
    """把机会域读数收成可序列化的百分比，保留判定器原有的配对顺序。"""
    active = reading.active_probabilities  # type: ignore[attr-defined]
    entry = reading.entry_probabilities  # type: ignore[attr-defined]
    return {
        "active_percent": {style: 100.0 * active[style] for style in active},
        "active_gaps_pp": dict(reading.active_gaps_pp),  # type: ignore[attr-defined]
        "active_pairs_at_least_reference": reading.active_pairs_above,  # type: ignore[attr-defined]
        "entry_percent": {style: 100.0 * entry[style] for style in entry},
        "entry_gaps_pp": dict(reading.entry_gaps_pp),  # type: ignore[attr-defined]
    }


def _style_gaps(identifier: str) -> dict[str, object]:
    """按节点等权计算当前身份与上一身份在翻牌面对下注上的主动率。"""
    payloads: dict[str, object] = {}
    seed_identical = True
    for subject in (_previous_identifier(identifier), identifier):
        manifest = frozen_manifest(
            code_identity="development-calibration",
            output_dir="not-written",
            strategy_id=subject,
        )
        rows = [row.model_dump() for row in _node_rows(manifest)]
        by_key: dict[tuple[str, str, str], dict[int, str]] = defaultdict(dict)
        for row in rows:
            key = (row["node_id"], row["style"], row["hand_mode"])
            by_key[key][int(row["seed_block"])] = json.dumps(row["action_units"], sort_keys=True)
        if any(len(set(values.values())) != 1 for values in by_key.values()):
            seed_identical = False
        reading, _domains = opportunity_reading(rows)
        flop_nodes = sorted({row["node_id"] for row in rows if row["category"] == "flop-draw"})
        payloads[subject] = {
            "config_digest": config_digest(subject),
            "direct_rows": len(rows),
            "flop_draw_nodes": len(flop_nodes),
            "rates": _rates(reading),
        }
    return {
        "seeds": list(MIXED_MAIN_SEEDS),
        "seed_blocks_identical": seed_identical,
        "active_domain": ACTIVE_DOMAIN_CATEGORY,
        "active_actions": list(ACTIVE_ACTIONS),
        "style_pairs": [f"{left}-{right}" for left, right in STYLE_PAIRS],
        "reference_gap_pp": OPPORTUNITY_MIN_GAP_PP,
        "identities": payloads,
    }


def _pair_key(row: object) -> tuple[int, str, str, int, int]:
    return (
        row.player_count,  # type: ignore[attr-defined]
        row.style,  # type: ignore[attr-defined]
        row.opponent,  # type: ignore[attr-defined]
        int(row.seed_block),  # type: ignore[attr-defined]
        int(row.rotation),  # type: ignore[attr-defined]
    )


def _pairing(schedule_size: int, identifier: str) -> dict[str, object]:
    """按既有完整轮换，把当前身份的焦点臂与启发式焦点臂配成对。"""
    tally = run_adversarial_batch(
        stage="B",
        allow_matches=True,
        identifier=identifier,
        seeds=MIXED_MAIN_SEEDS,
        family_set="iqv",
        observe=True,
    )
    paired: dict[tuple[int, str, str, int, int], dict[str, object]] = defaultdict(dict)
    for row in tally.rows:
        paired[_pair_key(row)][row.arm] = row
    complete = {
        key: arms
        for key, arms in paired.items()
        if set(arms) == {"mixed-focus", "legacy-focus"}
    }
    by_opponent: dict[str, list[float]] = defaultdict(list)
    by_player: dict[tuple[int, str], list[float]] = defaultdict(list)
    by_seed: dict[tuple[int, str], list[float]] = defaultdict(list)
    signs = {"mixed_higher": 0, "legacy_higher": 0, "tie": 0}
    for (player_count, _style, opponent, seed, _rotation), arms in complete.items():
        mixed = arms["mixed-focus"]
        legacy = arms["legacy-focus"]
        diff = float(mixed.bb_per_100) - float(legacy.bb_per_100)  # type: ignore[attr-defined]
        by_opponent[opponent].append(diff)
        by_player[(player_count, opponent)].append(diff)
        by_seed[(seed, opponent)].append(diff)
        if diff > 0:
            signs["mixed_higher"] += 1
        elif diff < 0:
            signs["legacy_higher"] += 1
        else:
            signs["tie"] += 1
    families = []
    for opponent in ADVERSARIAL_FAMILY_SETS["iqv"]:
        values = by_opponent[opponent]
        families.append(
            {
                "opponent": opponent,
                "pairs": len(values),
                "mean_paired_bb_per_100": sum(values) / len(values),
                "median_paired_bb_per_100": statistics.median(values),
            }
        )
    heuristic_by_seed = []
    for seed in MIXED_MAIN_SEEDS:
        values = by_seed[(seed, "heuristic@1")]
        heuristic_by_seed.append(
            {
                "seed_block": seed,
                "pairs": len(values),
                "mean_paired_bb_per_100": sum(values) / len(values),
                "median_paired_bb_per_100": statistics.median(values),
            }
        )
    per_player = []
    for player_count in range(2, 10):
        ranked = []
        for opponent in ADVERSARIAL_FAMILY_SETS["iqv"]:
            values = by_player[(player_count, opponent)]
            ranked.append((sum(values) / len(values), opponent, len(values)))
        ranked.sort()
        per_player.append(
            {
                "player_count": player_count,
                "worst_opponent": ranked[0][1],
                "worst_mean_paired_bb_per_100": ranked[0][0],
                "heuristic_mean_paired_bb_per_100": next(
                    mean for mean, name, _count in ranked if name == "heuristic@1"
                ),
                "pairs_per_opponent": ranked[0][2],
            }
        )
    hands = [hand.model_dump() for hand in tally.observations]
    diagnostic = targeting_diagnostic(
        {"hands": hands},
        {"seeds": list(MIXED_MAIN_SEEDS)},
        "开发标定观测",
    )
    return {
        "family_set": "iqv",
        "families": [item["opponent"] for item in families],
        "schedule_hands": schedule_size,
        "completed_hands": len(tally.rows),
        "truncated_hands": tally.truncated,
        "complete_pairs": len(complete),
        "incomplete_pairs": len(paired) - len(complete),
        "big_blind": MIXED_BIG_BLIND,
        "signs": signs,
        "heuristic_by_seed": heuristic_by_seed,
        "by_opponent": families,
        "by_player_count": per_player,
        "probe_segments": [item.model_dump() for item in diagnostic.families],
        "probe_buckets": [item.model_dump() for item in diagnostic.buckets],
        "pairs_with_facing": diagnostic.pairs_with_facing,
    }


def _replay_sample(identifier: str) -> dict[str, object]:
    """用排期开头的一小段重复打两次，核对同输入的净筹码是否一致。"""
    schedule = adversarial_schedule("B", seeds=MIXED_MAIN_SEEDS, family_set="iqv")
    sample = schedule[:16]
    mismatches = 0
    rules = rules_for_identifier(identifier)
    for seed, style, opponent, arm, player_count, rotation in sample:
        kwargs = {
            "seed": seed,
            "style": style,
            "opponent": opponent,
            "arm": arm,
            "player_count": player_count,
            "rotation": rotation,
            "rules": rules,
        }
        first = play_adversarial_hand(**kwargs)
        second = play_adversarial_hand(**kwargs)
        if first.net_chips != second.net_chips or first.truncated != second.truncated:
            mismatches += 1
    return {"hands": len(sample), "mismatches": mismatches}


def run(identifier: str = MIXED_STRATEGY_IDENTIFIER_V9) -> dict[str, object]:
    started = time.perf_counter()
    observation = _observe_frozen_nodes(identifier)
    gaps = _style_gaps(identifier)
    schedule = adversarial_schedule("B", seeds=MIXED_MAIN_SEEDS, family_set="iqv")
    pairing = _pairing(len(schedule), identifier)
    replay = _replay_sample(identifier)
    return {
        "strategy_id": identifier,
        "default_bot_strategy": CreateGameRequest().bot_strategy,
        "config_digest": config_digest(identifier),
        "observation": observation,
        "style_gaps": gaps,
        "pairing": pairing,
        "replay": replay,
        "wall_seconds": time.perf_counter() - started,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地混合身份的开发标定")
    parser.add_argument("--run", action="store_true", help="显式允许查询分布并推进对照对局")
    parser.add_argument(
        "--identity",
        default=MIXED_STRATEGY_IDENTIFIER_V9,
        help="被测身份，默认第九版；第十版沿用同一排期",
    )
    args = parser.parse_args(argv)
    if not args.run:
        print("须显式传入 --run 才会实测", file=sys.stderr)
        return 2
    json.dump(run(args.identity), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
