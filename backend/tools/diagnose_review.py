"""只读重放复盘，对照参考分布、错误标记和已缓存的教练解读。

用法（在 backend 目录下）：
    uv run python tools/diagnose_review.py <hand_id>
    uv run python tools/diagnose_review.py --scan

数据库以只读方式打开。份额、跟注期望和参考分布沿用复盘同一条重放路径。
不写库，也不推进在线对局。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.analysis.action_line_equity import ActionLineTracker, estimate_decision  # noqa: E402
from app.analysis.hand_review import (  # noqa: E402
    _AIR_FAIR_SCALE,
    _EQUITY_SAMPLES,
    _REVIEW_SEED,
    _detect_mistakes,
    _distribution_rows,
    _fair_share,
    _folding_gives_up_value,
    _guard_reference_distribution,
    _history_action,
    _mode_action,
    _publish_reference,
    _replay_action,
)
from app.analysis.reference_identity import (  # noqa: E402
    EVALUATION_VERSION,
    REFERENCE_VERSION,
)
from app.llm.coach import PROMPT_SCHEMA_VERSION  # noqa: E402
from app.poker.actions import Action  # noqa: E402
from app.poker.cards import card_from_str  # noqa: E402
from app.poker.engine import PokerEngine  # noqa: E402
from app.strategy.mixed_context import (  # noqa: E402
    MixedSummaryTracker,
    mixed_state,
    require_mixed_input,
)
from app.strategy.mixed_features import features_for  # noqa: E402
from app.strategy.mixed_policy import (  # noqa: E402
    _CHECKED_VALUE_FLOOR,
    _DRAW_SUPPORT_BASE,
    _POSTFLOP_PRICE_WEIGHT,
    _STRONG_VALUE_BONUS,
    _VALUE_GATE_TOLERANCE,
    _VALUE_THRESHOLDS,
    STYLE_PARAMETERS,
    HandMode,
    _active_gate,
    _checked_defense_bonus,
    _checked_value_floor,
    _facing_draw_support,
    _facing_pair_raise_applies,
    _full_ring_call_penalty,
    _large_commit_penalty,
    _postflop_call_bonus,
    _preflop_call_bonus,
    _score,
    _skips_unqualified_value_bonus,
    _strong_preflop_continuation,
    _strong_value_hand,
    _with_effective_base,
)
from app.strategy.mixed_strategy import (  # noqa: E402
    MIXED_STRATEGY_IDENTIFIER_V20,
    MixedLocalStrategy,
    rules_for_identifier,
)
from app.strategy.projection import project_for_actor  # noqa: E402

# 参考分布里达到这一份额，仍被标成错误，就记成判据和分布冲突。
_NOTABLE_SHARE = 0.25
# 行动线达到这一档，视为已经出现再加注或翻后中等以上的主动投入。
_STRONG_LINE_LEVEL = 3
# 低于这个筹码数的数字多半是点数或人数，不拿来对参考金额。
_MIN_MENTIONED_CHIPS = 15
# 这些错误是在否定玩家当时的动作类型；下注偏小只比较尺度。
_MASS_CONFLICT_CODES = frozenset(
    {
        "bad_call",
        "bad_fold",
        "slowplay",
        "over_aggressive",
        "value_missed",
        "air_bluff",
    }
)
_AGGRESSIVE = frozenset({"bet", "raise"})
_CODE_ORDER = (
    "a_negative_continue",
    "a_mode_call",
    "a_mode_raise",
    "a_residual_call",
    "a_residual_raise",
    "a_bad_call_vs_raise",
    "b_positive_fold",
    "b_cheap_preflop",
    "b_priced_preflop",
    "b_postflop",
    "b_would_flag_bad_fold",
    "c_low_equity_lead",
    "c_stale_line",
    "c_static_floor",
    "c_below_air",
    "c_residual_lead",
    "c_preflop_free_raise",
    "d_call_amount_zero",
    "e_bad_fold_matches_reference",
    "e_marked_despite_mass",
    "e_slowplay_negative_call",
    "e_coach_opposes",
    "e_coach_accepts_other",
    "e_coach_misstates",
    "e_coach_legacy_amount",
    "e_coach_unknown_amount",
    "e_coach_false_draw",
    "e_coach_hindsight",
    "e_coach_stale_schema",
)
_LABELS = {
    "a_negative_continue": "A 面对下注且跟注期望为负，保护后仍建议或残留跟注/加注",
    "a_mode_call": "A 保护后众数仍是跟注",
    "a_mode_raise": "A 保护后众数是加注",
    "a_residual_call": "A 众数已是弃牌，分布里仍有跟注",
    "a_residual_raise": "A 众数不是加注，分布里仍有加注",
    "a_bad_call_vs_raise": "A 玩家跟注被标赔率不足，参考却是加注",
    "b_positive_fold": "B 面对下注且跟注期望为正，参考却是弃牌",
    "b_cheap_preflop": "B 翻前补盲或溜入这种廉价跟注",
    "b_priced_preflop": "B 翻前要跟的注已经超过一个大盲",
    "b_postflop": "B 翻后正期望却建议弃牌",
    "b_would_flag_bad_fold": "B 若玩家弃牌会触发弃掉正期望",
    "c_low_equity_lead": "C 翻后无人下注且份额低于平均，参考仍主动下注或加注",
    "c_stale_line": "C 本街尚无对手进攻，但行动线档位已经偏高",
    "c_static_floor": "C 评分未过主动门槛，成牌基础分仍在托底线上",
    "c_below_air": "C 份额低于空气线，参考仍主动",
    "c_residual_lead": "C 翻后份额低于平均，众数是过牌但分布仍残留主动下注",
    "c_preflop_free_raise": "C 翻前免费位加注，份额低于平均（单独计数）",
    "d_call_amount_zero": "D 待跟注大于零，参考跟注金额仍是 0",
    "e_bad_fold_matches_reference": "E 弃掉正期望，但参考自己也是弃牌",
    "e_marked_despite_mass": "E 玩家动作在参考分布里占比不低，仍被标错",
    "e_slowplay_negative_call": "E 被标慢玩，但跟注期望为负",
    "e_coach_opposes": "E 教练明确倾向与参考众数不同",
    "e_coach_accepts_other": "E 教练接受了与参考不同的玩家动作",
    "e_coach_misstates": "E 教练对参考动作的描述对不上众数",
    "e_coach_legacy_amount": "E 教练写下的参考金额对上保护前的本街总额",
    "e_coach_unknown_amount": "E 教练写下的参考金额对不上现有分布",
    "e_coach_false_draw": "E 教练写成听牌，但这手没有再发一张就能完成的听牌",
    "e_coach_hindsight": "E 教练把摊牌底牌或事后结果写成当时的决策依据",
    "e_coach_stale_schema": "E 教练缓存来自更早的提示词版本",
}
_DRAW_CLAIM = re.compile(r"(?:带|持有|击中)[^，。；]{0,8}?(?:同花听牌|顺子听牌|卡顺听牌)")
_STREET_ZH = {
    "preflop": "翻牌前",
    "flop": "翻牌",
    "turn": "转牌",
    "river": "河牌",
}
_WORD_TO_ACTION = {
    "再加注": "raise",
    "反加注": "raise",
    "加注": "raise",
    "raise": "raise",
    "下注": "bet",
    "小注": "bet",
    "bet": "bet",
    "弃牌": "fold",
    "fold": "fold",
    "过牌": "check",
    "check": "check",
    "跟注": "call",
    "call": "call",
}
_ACTION_PATTERNS = tuple(
    (action, re.compile(pattern, re.IGNORECASE))
    for action, pattern in (
        ("raise", r"再加注|反加注|加注|(?<![A-Za-z_])raise(?![A-Za-z_])"),
        ("bet", r"下注|小注|(?<![A-Za-z_])bet(?![A-Za-z_])"),
        ("fold", r"弃牌|(?<![A-Za-z_])fold(?![A-Za-z_])"),
        ("check", r"过牌|(?<![A-Za-z_])check(?![A-Za-z_])"),
        ("call", r"跟注|(?<![A-Za-z_])call(?![A-Za-z_])"),
    )
)
_REFERENCE_STOP = re.compile(r"但|不过|然而|。|；|，")
_ADVICE_RULES = (
    (re.compile(r"(弃牌|跟注|过牌|下注|再加注|加注|小注)优于"), 3),
    (re.compile(r"(?:应该|应当|建议|优先)(?:直接|选择)?(弃牌|跟注|过牌|下注|再加注|加注)"), 3),
    (re.compile(r"(?<!不)应(弃牌|跟注|过牌|下注|再加注|加注)"), 3),
)
# 判断词往前只看同一分句里最近的动作，避免把前面的对手行动当成建议。
_JUDGMENT_TAILS = (
    (re.compile(r"(?<!不)更合适"), 3),
    (re.compile(r"(?<!不)合理"), 2),
    (re.compile(r"(?<!不)正确"), 2),
    (re.compile(r"未被标错"), 1),
    (re.compile(r"并不构成错误"), 1),
    (re.compile(r"没有额外问题"), 1),
)
_JUDGMENT_LOOKBACK = 8
_PERCENT_TAIL = re.compile(r"(?:\.\d+)?%")
_CALL_TAIL = ("期望", "赔率", "门槛")


def db_path() -> Path:
    """与后端一致：环境变量优先，否则使用 backend/data 下的库。"""
    import os

    env = os.environ.get("HOLDEM_DB_PATH")
    if env:
        return Path(env)
    return _BACKEND / "data" / "holdem.db"


def connect_readonly(path: Path | None = None) -> sqlite3.Connection:
    """只读打开牌局库，诊断过程不能写入。"""
    target = path or db_path()
    return sqlite3.connect(f"file:{target}?mode=ro", uri=True)


def _mass(rows: list[dict], *kinds: str) -> float:
    wanted = set(kinds)
    return sum(float(item["probability"]) for item in rows if item["action"] in wanted)


def _has_amount_zero(rows: list[dict], kind: str) -> bool:
    return any(
        item["action"] == kind and int(item["amount"]) == 0 and item["probability"] > 0
        for item in rows
    )


def classify_point(point: dict) -> list[str]:
    """根据一个决策点的指标、保护后分布和教练读法列出矛盾代码。"""
    to_call = int(point["to_call"])
    call_ev = point["call_ev"]
    equity = float(point["equity"])
    opponents = int(point["opponents"])
    street = str(point["street"])
    big_blind = int(point["big_blind"])
    mode = str(point["mode"])
    rows = list(point["distribution"])
    player = str(point["player_action"])
    mistakes = set(point["mistakes"])
    recent = int(point["recent_aggression"])
    max_line = int(point["max_line"])
    base = int(point["base"])
    score = int(point["score"])
    value_threshold = int(point["value_threshold"])
    codes: list[str] = []

    call_left = _mass(rows, "call")
    raise_left = _mass(rows, "raise")
    negative_call = to_call > 0 and call_ev is not None and float(call_ev) < 0
    if negative_call and (mode in ("call", "raise") or call_left > 0 or raise_left > 0):
        codes.append("a_negative_continue")
        if mode == "call":
            codes.append("a_mode_call")
        if mode == "raise":
            codes.append("a_mode_raise")
        if mode == "fold" and call_left > 0:
            codes.append("a_residual_call")
        if mode != "raise" and raise_left > 0:
            codes.append("a_residual_raise")
        if player == "call" and "bad_call" in mistakes and mode == "raise":
            codes.append("a_bad_call_vs_raise")

    positive_fold = to_call > 0 and call_ev is not None and float(call_ev) > 0 and mode == "fold"
    if positive_fold:
        codes.append("b_positive_fold")
        cheap = street == "preflop" and to_call <= big_blind
        if cheap:
            codes.append("b_cheap_preflop")
        elif street == "preflop":
            codes.append("b_priced_preflop")
        else:
            codes.append("b_postflop")
        if point.get("fold_probe_bad_fold"):
            codes.append("b_would_flag_bad_fold")

    fair = _fair_share(opponents) if opponents > 0 else 1.0
    postflop_lead = street != "preflop" and to_call == 0 and mode in _AGGRESSIVE and equity < fair
    if postflop_lead:
        codes.append("c_low_equity_lead")
        if recent == 0 and max_line >= _STRONG_LINE_LEVEL:
            codes.append("c_stale_line")
        if base >= _CHECKED_VALUE_FLOOR and score < value_threshold:
            codes.append("c_static_floor")
        if equity < _AIR_FAIR_SCALE * fair:
            codes.append("c_below_air")
    lead_mass = _mass(rows, "bet", "raise")
    if (
        street != "preflop"
        and to_call == 0
        and opponents > 0
        and equity < fair
        and mode not in _AGGRESSIVE
        and lead_mass >= _NOTABLE_SHARE
    ):
        codes.append("c_residual_lead")
    if (
        street == "preflop"
        and to_call == 0
        and mode in _AGGRESSIVE
        and opponents > 0
        and equity < fair
    ):
        codes.append("c_preflop_free_raise")

    published_call_zero = _has_amount_zero(rows, "call")
    mode_call_zero = mode == "call" and int(point.get("mode_amount") or 0) == 0
    if to_call > 0 and (published_call_zero or mode_call_zero):
        codes.append("d_call_amount_zero")

    if "bad_fold" in mistakes and mode == "fold":
        codes.append("e_bad_fold_matches_reference")
    player_share = _mass(rows, player)
    if mistakes & _MASS_CONFLICT_CODES and player_share >= _NOTABLE_SHARE:
        codes.append("e_marked_despite_mass")
    if "slowplay" in mistakes and call_ev is not None and float(call_ev) < 0:
        codes.append("e_slowplay_negative_call")

    coach = point.get("coach")
    if isinstance(coach, dict):
        if coach.get("stale"):
            codes.append("e_coach_stale_schema")
        else:
            if coach.get("opposes"):
                codes.append("e_coach_opposes")
            elif coach.get("accepts_other"):
                codes.append("e_coach_accepts_other")
            if coach.get("misstates"):
                codes.append("e_coach_misstates")
            if coach.get("legacy_amounts"):
                codes.append("e_coach_legacy_amount")
            if coach.get("unknown_amounts"):
                codes.append("e_coach_unknown_amount")
            if int(point.get("draw") or 0) == 0 and _claims_live_draw(str(coach.get("text") or "")):
                codes.append("e_coach_false_draw")
            if _claims_hindsight_basis(str(coach.get("text") or "")):
                codes.append("e_coach_hindsight")

    order = {code: index for index, code in enumerate(_CODE_ORDER)}
    return sorted(set(codes), key=lambda code: order.get(code, len(order)))


# 把终局摊牌或对手真实底牌写成「当时已经知道」的依据。事后印证若先写明当时逻辑，不应只靠这些词。
_HINDSIGHT_BASIS = (
    re.compile(r"公开(?:摊牌|底牌)"),
    re.compile(r"摊牌显示"),
    re.compile(r"实际只有"),
    re.compile(r"亮出"),
    re.compile(r"对手只有"),
    re.compile(r"因为对手(?:实际|摊牌|亮)"),
)


def _claims_hindsight_basis(text: str) -> bool:
    """正文是否把摊牌底牌或事后结果当成当时应该做某动作的依据。"""
    return any(pattern.search(text) for pattern in _HINDSIGHT_BASIS)


def _claims_live_draw(text: str) -> bool:
    """正文是否把这手说成再发一张就能完成的听牌。后门或明确否定不算。"""
    for match in _DRAW_CLAIM.finditer(text):
        prefix = text[max(0, match.start() - 6) : match.start()]
        if "后门" in prefix or any(token in prefix for token in ("没", "无", "不是", "并非")):
            continue
        return True
    return False


def _reference_spans(text: str) -> list[tuple[int, int]]:
    """参考一词往后，直到转折或句号，视为在描述参考动作。"""
    spans: list[tuple[int, int]] = []
    for match in re.finditer("参考", text):
        rest = text[match.end() :]
        stop = _REFERENCE_STOP.search(rest)
        end = match.end() + (stop.start() if stop else min(len(rest), 40))
        spans.append((match.start(), end))
    return spans


def _nearest_action_before(text: str, end: int) -> str | None:
    """在判断词前的短窗里取最近的动作。窗不跨过逗号和句号。"""
    start = max(0, end - _JUDGMENT_LOOKBACK)
    clause = text[start:end]
    for separator in ("，", "。", "；", "、"):
        cut = clause.rfind(separator)
        if cut != -1:
            clause = clause[cut + 1 :]
    nearest: tuple[int, str] | None = None
    for action, pattern in _ACTION_PATTERNS:
        for match in pattern.finditer(clause):
            if action == "call" and clause[match.end() :].startswith(_CALL_TAIL):
                continue
            if nearest is None or match.start() >= nearest[0]:
                nearest = (match.start(), action)
    if nearest is None:
        return None
    return nearest[1]


def _covered(start: int, spans: list[tuple[int, int]]) -> bool:
    return any(begin <= start < end for begin, end in spans)


def _actions_in(fragment: str) -> set[str]:
    found: set[str] = set()
    for action, pattern in _ACTION_PATTERNS:
        for match in pattern.finditer(fragment):
            if action == "call" and fragment[match.end() :].startswith(_CALL_TAIL):
                continue
            found.add(action)
    return found


def _mentioned_chips(fragment: str) -> list[int]:
    chips: list[int] = []
    for match in re.finditer(r"\d+", fragment):
        if _PERCENT_TAIL.match(fragment[match.end() :]):
            continue
        value = int(match.group())
        if value >= _MIN_MENTIONED_CHIPS:
            chips.append(value)
    return chips


def _cache_matches_reference(cache_key: str | None) -> bool:
    """缓存键同时含当前参考版本和评估版本才算仍有效。"""
    if not cache_key:
        return False
    return (
        f"|ref={REFERENCE_VERSION}|" in cache_key
        and f"|eval={EVALUATION_VERSION}|" in cache_key
    )


def coach_reading(
    text: str,
    *,
    mode: str,
    published_amounts: set[int],
    raw_amounts: set[int],
    ignore_amounts: set[int] | None = None,
    schema: int | None = None,
    recommended_action: str | None = None,
    cache_key: str | None = None,
) -> dict:
    """从一段教练正文里抽出动作倾向，并和参考众数、金额对照。

    库里已经记下建议动作时直接用它比较；空着才退回关键词，并标明是推断。
    提示词版本，或缓存键里的参考版本、评估版本对不上当前口径时，记为过期缓存。
    """
    spans = _reference_spans(text)
    attributed: set[str] = set()
    legacy: list[int] = []
    unknown: list[int] = []
    known = {amount for amount in published_amounts if amount > 0}
    known.update(amount for amount in (ignore_amounts or set()) if amount > 0)
    raw_only = {amount for amount in raw_amounts if amount > 0 and amount not in known}
    for begin, end in spans:
        fragment = text[begin:end]
        attributed.update(_actions_in(fragment))
        for value in _mentioned_chips(fragment):
            if value in known or value in legacy or value in unknown:
                continue
            if value in raw_only:
                legacy.append(value)
            elif value not in known:
                unknown.append(value)
    scores: dict[str, int] = {}
    for pattern, strength in _ADVICE_RULES:
        for match in pattern.finditer(text):
            if _covered(match.start(), spans):
                continue
            word = next((group for group in match.groups() if group), "")
            action = _WORD_TO_ACTION.get(word.casefold(), _WORD_TO_ACTION.get(word))
            if action is None:
                continue
            scores[action] = max(scores.get(action, 0), strength)
    for pattern, strength in _JUDGMENT_TAILS:
        for match in pattern.finditer(text):
            if _covered(match.start(), spans):
                continue
            action = _nearest_action_before(text, match.start())
            if action is None:
                continue
            scores[action] = max(scores.get(action, 0), strength)
    preference = None
    strength = 0
    if scores:
        best = max(scores.values())
        leaders = [action for action, value in scores.items() if value == best]
        if len(leaders) == 1:
            preference = leaders[0]
            strength = best
    stored = _canonical_action(recommended_action)
    if stored is not None:
        preference = stored
        strength = 3
        opposes = stored != mode
        accepts_other = False
        source = "stored"
    else:
        opposes = preference is not None and strength >= 2 and preference != mode
        accepts_other = preference is not None and strength == 1 and preference != mode
        source = "inferred"
    return {
        "preference": preference,
        "strength": strength,
        "reference_actions": sorted(attributed),
        "opposes": opposes,
        "accepts_other": accepts_other,
        "misstates": bool(attributed) and mode not in attributed,
        "legacy_amounts": legacy,
        "unknown_amounts": unknown,
        "schema": schema,
        "cache_key": cache_key,
        "stale": (schema is not None and schema != PROMPT_SCHEMA_VERSION)
        or not _cache_matches_reference(cache_key),
        "recommended_action": stored,
        "action_source": source,
        "text": text,
    }


def _canonical_action(value: object) -> str | None:
    """只认已经落库的五个动作词。认不出就当作没有结构化动作。"""
    if not isinstance(value, str):
        return None
    token = value.strip().casefold()
    if token in {"fold", "check", "call", "bet", "raise"}:
        return token
    return None


def _rows_from_pairs(pairs: list[tuple[Action, float]]) -> list[dict]:
    return [
        {"action": action.type.value, "amount": action.amount, "probability": weight}
        for action, weight in pairs
        if weight > 0
    ]


def _value_line_quality(features, style, rules, score: int, value_threshold: int) -> int:
    """主动质量。听牌支撑只在这条线仍为 0 时进入展示用的被动分。"""
    gate = _active_gate(features, style, rules)
    threshold_quality = max(0, score - value_threshold + _VALUE_GATE_TOLERANCE + gate)
    quality = max(threshold_quality, _checked_value_floor(features, rules))
    if _strong_value_hand(features, rules) and not _skips_unqualified_value_bonus(
        features, rules, threshold_quality
    ):
        quality += _STRONG_VALUE_BONUS
    return quality


def _score_features(features, style, rules) -> dict:
    """用和参考分布相同的紧手标准模式公式，拆开评分与两条门槛。"""
    features = _with_effective_base(features, rules)
    parameters = STYLE_PARAMETERS[style]
    score = _score(features, parameters, HandMode.NORMAL, rules)
    if features.spr_at_most(1):
        depth = -40
    elif features.spr_at_least(6):
        depth = 25
    else:
        depth = 0
    aggression_penalty = 25 * features.recent_aggression
    is_preflop = features.street.name.lower() == "preflop"
    price_weight = rules.preflop_price_weight if is_preflop else _POSTFLOP_PRICE_WEIGHT
    call_price = features.price
    if rules.shared_board_chop_caliber and features.shared_board_locked:
        call_price = features.price // (features.contenders + 1)
    call_base = 310 if is_preflop else 350
    call_threshold = call_base + (price_weight * call_price) // 1000 + aggression_penalty + depth
    value_threshold = _VALUE_THRESHOLDS[features.street] + aggression_penalty + depth
    bonus = (
        _preflop_call_bonus(rules, style) if is_preflop else _postflop_call_bonus(rules, style)
    )
    commit_penalty = _large_commit_penalty(features, rules)
    ring_penalty = _full_ring_call_penalty(features, rules)
    passive = score + bonus + _strong_preflop_continuation(features, rules)
    passive -= commit_penalty + ring_penalty
    # 没有承诺惩罚、也没越过主动价值线时，听牌支撑会进实际被动分，展示跟着加。
    if (
        commit_penalty == 0
        and ring_penalty == 0
        and rules.effective_draw_support
        and features.base < _DRAW_SUPPORT_BASE
        and _value_line_quality(features, style, rules, score, value_threshold) == 0
    ):
        supported = _facing_draw_support(features, rules)
        if supported is not None:
            passive += supported[0]
    if commit_penalty == 0 and ring_penalty == 0:
        # 过牌后的成牌补分进实际被动分，展示跟着加。
        passive += _checked_defense_bonus(features, rules)
    return {
        "base": features.base,
        "draw": features.draw,
        "score": score,
        "value_threshold": value_threshold,
        "call_threshold": call_threshold,
        "passive_score": passive,
        "recent_aggression": features.recent_aggression,
        "price": features.price,
        "depth": depth,
        "aggression_penalty": aggression_penalty,
        "capped_board_two_pair": features.capped_board_two_pair,
        "top_pair_board_pair_base": features.top_pair_board_pair_base,
        "top_pair_board_pair_visible_base": features.top_pair_board_pair_visible_base,
        "weak_board_flush_base": features.weak_board_flush_base,
        "pair_raise_applies": _facing_pair_raise_applies(features, rules, style),
    }


def _inspect_decision(
    engine: PokerEngine,
    human_seat: int,
    action: Action,
    action_index: int,
    reference_bot: MixedLocalStrategy,
    context: object,
    levels: ActionLineTracker,
    rules,
    coach_row: dict | None,
) -> dict:
    """重放路径上摘一个真人决策点，并标出这一拍命中的矛盾。"""
    snapshot = engine.snapshot()
    legal = engine.legal_actions()
    hero = snapshot.players[human_seat]
    live = levels.live_opponents(snapshot.players, human_seat)
    projection = engine.candidate_call_pot_projection()
    valued = estimate_decision(
        hero_cards=hero.hole_cards,
        board=snapshot.board,
        opponents=live,
        projection=projection,
        pot=snapshot.pot,
        hero_seat=human_seat,
        actual_call_amount=legal.actual_call_amount,
        samples=_EQUITY_SAMPLES,
        rng=random.Random(_REVIEW_SEED),
    )
    projected = mixed_state(project_for_actor(snapshot), context)
    features = features_for(require_mixed_input(projected), legal)
    style = reference_bot.style_for(human_seat)
    selected = reference_bot.distribution_for(
        projected, legal, mode=HandMode.NORMAL, trap_roll=None, protect_roll=None
    )
    raw_pairs = _distribution_rows(selected)
    max_line = max((level for _seat, level in live), default=0)
    bad_fold = _folding_gives_up_value(
        equity=valued.equity,
        call_ev=valued.call_ev,
        pot_odds=valued.pot_odds,
        to_call=legal.call_amount,
        actual_call=legal.actual_call_amount,
        pot=snapshot.pot,
        contested=valued.contested,
        can_raise=legal.can_raise,
        opponents=len(live),
        hole_cards=hero.hole_cards,
        board=snapshot.board,
        big_blind=engine.big_blind,
    )
    guarded_pairs = _guard_reference_distribution(
        raw_pairs,
        to_call=legal.call_amount,
        call_ev=valued.call_ev,
        equity=valued.equity,
        opponents=len(live),
        postflop=len(snapshot.board) > 0,
        max_line=max_line,
        bad_fold=bad_fold,
        big_blind=engine.big_blind,
        contested=valued.contested,
        hole_cards=hero.hole_cards,
        board=snapshot.board,
        pot=snapshot.pot,
    )
    mode_action = _mode_action(guarded_pairs)
    published_action, published_rows = _publish_reference(
        guarded_pairs,
        mode_action,
        hero.street_bet,
        hero.stack,
        legal.actual_call_amount,
    )
    mistakes = _detect_mistakes(
        action=action,
        equity=valued.equity,
        call_ev=valued.call_ev,
        pot_odds=valued.pot_odds,
        to_call=legal.call_amount,
        actual_call=legal.actual_call_amount,
        pot=snapshot.pot,
        contested=valued.contested,
        can_raise=legal.can_raise,
        opponents=len(live),
        hole_cards=hero.hole_cards,
        board=snapshot.board,
        big_blind=engine.big_blind,
        reference=mode_action,
    )
    scored = _score_features(features, style, rules)
    raw_rows = _rows_from_pairs(raw_pairs)
    point = {
        "action_index": action_index,
        "street": snapshot.street.name.lower(),
        "board": [str(card) for card in snapshot.board],
        "hero_cards": [str(card) for card in hero.hole_cards],
        "pot": snapshot.pot,
        "to_call": legal.call_amount,
        "big_blind": engine.big_blind,
        "opponents": len(live),
        "opponent_levels": [{"seat": seat, "level": level} for seat, level in live],
        "max_line": max_line,
        "equity": valued.equity,
        "pot_odds": valued.pot_odds,
        "call_ev": valued.call_ev,
        "call_ev_shown": None if valued.call_ev is None else int(round(valued.call_ev)),
        "player_action": action.type.value,
        "player_amount": action.amount,
        "mode": published_action["action"],
        "mode_amount": published_action["amount"],
        "distribution": published_rows,
        "raw_distribution": raw_rows,
        "mistakes": [item["code"] for item in mistakes],
        "mistake_messages": [item["message"] for item in mistakes],
        "fold_probe_bad_fold": bad_fold,
        "style": style.value,
        **scored,
    }
    if coach_row is not None:
        schema = int(coach_row.get("schema") or 0)
        point["coach"] = coach_reading(
            str(coach_row.get("explanation") or ""),
            mode=point["mode"],
            published_amounts={int(item["amount"]) for item in published_rows},
            raw_amounts={int(item["amount"]) for item in raw_rows},
            ignore_amounts={legal.call_amount, snapshot.pot, action.amount, engine.big_blind},
            schema=schema,
            recommended_action=(
                str(coach_row["recommended_action"])
                if coach_row.get("recommended_action")
                else None
            ),
            cache_key=None if coach_row.get("cache_key") is None else str(coach_row["cache_key"]),
        )
        point["coach"]["model"] = coach_row.get("model")
    else:
        point["coach"] = None
    point["contradictions"] = classify_point(point)
    return point


def diagnose_history(
    history: dict,
    *,
    hand_id: str = "",
    coach_rows: dict[int, dict] | None = None,
) -> dict:
    """重放一手历史里的真人决策。无法重放时返回错误，不抛给扫描循环。"""
    try:
        return _replay(history, hand_id=hand_id, coach_rows=coach_rows or {})
    except Exception as exc:
        return {
            "hand_id": hand_id,
            "error": f"{type(exc).__name__}: {exc}",
            "decisions": [],
        }


def _replay(history: dict, *, hand_id: str, coach_rows: dict[int, dict]) -> dict:
    num_players = history["num_players"]
    small_blind = history["small_blind"]
    big_blind = history["big_blind"]
    hole_cards: dict[int, list] = {}
    starting: dict[int, int] = {}
    human_seat = None
    hero_labels: list[str] = []
    for player in history["players"]:
        seat = int(player["seat"])
        hole_cards[seat] = [card_from_str(card) for card in player["hole_cards"]]
        starting[seat] = int(player["starting_stack"])
        if player.get("is_human"):
            human_seat = seat
            hero_labels = [str(card) for card in player["hole_cards"]]
    if human_seat is None:
        raise ValueError("历史中没有标记真人座位")
    board = [card_from_str(card) for card in history["board"]]
    engine = PokerEngine(num_players, small_blind, big_blind, max(starting.values()))
    for seat, stack in starting.items():
        engine.players[seat].stack = stack
    engine.start_hand_with(history["button"], hole_cards, board)
    rules = rules_for_identifier(MIXED_STRATEGY_IDENTIFIER_V20)
    reference_bot = MixedLocalStrategy(
        seed=_REVIEW_SEED,
        bot_seats=(human_seat,),
        identifier=MIXED_STRATEGY_IDENTIFIER_V20,
    )
    tracker = MixedSummaryTracker()
    tracker.begin_hand(
        hand_number=int(history["hand_number"]),
        num_players=num_players,
        small_blind=small_blind,
        big_blind=big_blind,
        bot_seats=(human_seat,),
        history=engine.history,
    )
    levels = ActionLineTracker(num_players)
    decisions: list[dict] = []
    action_index = 0
    for record in history["actions"]:
        if record["action"] in ("small_blind", "big_blind"):
            continue
        seat = int(record["seat"])
        if engine.current_seat != seat:
            raise ValueError(f"重放状态不一致：期望座位 {seat}，实际 {engine.current_seat}")
        action = _history_action(record)
        levels.begin_street(str(record["street"]))
        if seat == human_seat:
            decisions.append(
                _inspect_decision(
                    engine,
                    human_seat,
                    action,
                    action_index,
                    reference_bot,
                    tracker.context(),
                    levels,
                    rules,
                    coach_rows.get(action_index),
                )
            )
            action_index += 1
        levels.commit(
            seat=seat,
            action=action.type.value,
            amount=action.amount,
            pot_before=engine.pot,
            big_blind=big_blind,
        )
        engine.apply_action(_replay_action(engine, seat, action))
        tracker.consume_after_action(engine.history)
    return {
        "hand_id": hand_id,
        "hand_number": history.get("hand_number"),
        "human_seat": human_seat,
        "hero_cards": hero_labels,
        "num_players": num_players,
        "big_blind": big_blind,
        "button": history.get("button"),
        "final_board": list(history.get("board") or []),
        "decisions": decisions,
    }


def load_coach_index(connection: sqlite3.Connection) -> dict[str, dict[int, dict]]:
    """按手牌和决策序号归并教练缓存。同一点保留较新的提示词版本。"""
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(coach_explanations)").fetchall()
    }
    has_action = "recommended_action" in columns
    has_cache_key = "cache_key" in columns
    selected = [
        "hand_id",
        "action_index",
        "explanation",
        "prompt_schema_version",
        "model",
        "created_at",
    ]
    if has_action:
        selected.append("recommended_action")
    if has_cache_key:
        selected.append("cache_key")
    rows = connection.execute(
        f"SELECT {', '.join(selected)} FROM coach_explanations"
    ).fetchall()
    index: dict[str, dict[int, dict]] = {}
    for row in rows:
        hand_id, action_index, explanation, schema, model, created_at = row[:6]
        cursor = 6
        recommended = None
        cache_key = None
        if has_action:
            recommended = row[cursor]
            cursor += 1
        if has_cache_key:
            cache_key = row[cursor]
        bucket = index.setdefault(str(hand_id), {})
        incoming = {
            "explanation": explanation,
            "schema": int(schema),
            "model": model,
            "created_at": str(created_at or ""),
            "recommended_action": recommended,
            "cache_key": None if cache_key is None else str(cache_key),
        }
        current = bucket.get(int(action_index))
        if current is None or _prefer_coach(incoming, current):
            bucket[int(action_index)] = incoming
    return index


def _prefer_coach(incoming: dict, current: dict) -> bool:
    if incoming["schema"] != current["schema"]:
        return incoming["schema"] > current["schema"]
    return incoming["created_at"] >= current["created_at"]


def load_history(connection: sqlite3.Connection, hand_id: str) -> dict | None:
    row = connection.execute(
        "SELECT history_json FROM hands WHERE id = ?",
        (hand_id,),
    ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def iter_histories(connection: sqlite3.Connection) -> list[tuple[str, dict]]:
    rows = connection.execute(
        "SELECT id, history_json FROM hands ORDER BY created_at, id"
    ).fetchall()
    return [(str(hand_id), json.loads(raw)) for hand_id, raw in rows]


def summarize_reports(reports: list[dict], *, limit: int = 8) -> dict:
    """把多手诊断收成各类矛盾的次数和代表手牌。"""
    codes = {
        code: {"decisions": 0, "hands": set(), "examples": []}
        for code in _CODE_ORDER
    }
    mistake_counts: dict[str, int] = {}
    decisions = 0
    facing_bet = 0
    free_action = 0
    errors: list[dict] = []
    for report in reports:
        if report.get("error"):
            errors.append({"hand_id": report.get("hand_id", ""), "error": report["error"]})
            continue
        seen: set[str] = set()
        for point in report.get("decisions") or []:
            decisions += 1
            if int(point["to_call"]) > 0:
                facing_bet += 1
            else:
                free_action += 1
            for code in point["mistakes"]:
                mistake_counts[code] = mistake_counts.get(code, 0) + 1
            for code in point["contradictions"]:
                bucket = codes[code]
                bucket["decisions"] += 1
                if code not in seen:
                    bucket["hands"].add(report.get("hand_id", ""))
                    seen.add(code)
                if len(bucket["examples"]) < limit:
                    bucket["examples"].append(_example(report, point))
    packed = {}
    for code, bucket in codes.items():
        packed[code] = {
            "label": _LABELS[code],
            "decisions": bucket["decisions"],
            "hands": len(bucket["hands"]),
            "examples": bucket["examples"],
        }
    return {
        "hands": len(reports),
        "replay_errors": errors,
        "decisions": decisions,
        "facing_bet": facing_bet,
        "free_action": free_action,
        "mistake_counts": mistake_counts,
        "codes": packed,
    }


def _example(report: dict, point: dict) -> dict:
    coach = point.get("coach") if isinstance(point.get("coach"), dict) else {}
    return {
        "hand_id": report.get("hand_id", ""),
        "action_index": point["action_index"],
        "street": point["street"],
        "to_call": point["to_call"],
        "call_ev": None if point["call_ev"] is None else round(float(point["call_ev"]), 1),
        "equity": round(float(point["equity"]), 4),
        "mode": point["mode"],
        "mode_amount": point["mode_amount"],
        "player_action": point["player_action"],
        "player_amount": point["player_amount"],
        "mistakes": list(point["mistakes"]),
        "max_line": point["max_line"],
        "recent_aggression": point["recent_aggression"],
        "base": point["base"],
        "score": point["score"],
        "value_threshold": point["value_threshold"],
        "call_threshold": point["call_threshold"],
        "passive_score": point["passive_score"],
        "continue_mass": round(_mass(point["distribution"], "call", "raise", "bet"), 3),
        "preference": coach.get("preference"),
        "reference_actions": coach.get("reference_actions") or [],
        "legacy_amounts": coach.get("legacy_amounts") or [],
        "unknown_amounts": coach.get("unknown_amounts") or [],
    }


def _format_rows(rows: list[dict]) -> str:
    if not rows:
        return "-"
    parts = []
    for item in rows:
        percent = float(item["probability"]) * 100
        parts.append(f"{item['action']}{item['amount']}:{percent:.1f}%")
    return " ".join(parts)


def _format_example(item: dict) -> str:
    ev = "-" if item["call_ev"] is None else item["call_ev"]
    mistakes = ",".join(item["mistakes"]) or "-"
    return (
        f"{item['hand_id']} #{item['action_index']} {item['street']} "
        f"玩家{item['player_action']}{item['player_amount']} "
        f"参考{item['mode']}{item['mode_amount']} "
        f"ev={ev} equity={item['equity']:.2%} "
        f"线={item['max_line']} 本街进攻={item['recent_aggression']} "
        f"base={item['base']} score={item['score']}/{item['value_threshold']} "
        f"被动={item['passive_score']}/{item['call_threshold']} "
        f"继续={item.get('continue_mass', 0):.0%} 错误={mistakes}"
    )


def format_report(report: dict) -> str:
    """把单手诊断收成可直接阅读的文本。"""
    if report.get("error"):
        return f"{report.get('hand_id', '')} 重放失败：{report['error']}"
    lines = [
        "=" * 88,
        (
            f"{report['hand_id']}  第{report['hand_number']}手  "
            f"{report['num_players']}人  大盲={report['big_blind']}  "
            f"真人=玩家{report['human_seat']} {report['hero_cards']}  "
            f"公共牌={report['final_board'] or '-'}"
        ),
    ]
    if not report["decisions"]:
        lines.append("  没有真人决策点")
        return "\n".join(lines)
    for point in report["decisions"]:
        lines.extend(_format_point(point))
    return "\n".join(lines)


def _format_point(point: dict) -> list[str]:
    street = _STREET_ZH.get(point["street"], point["street"])
    ev = "-" if point["call_ev"] is None else f"{float(point['call_ev']):.1f}"
    shown = "-" if point["call_ev_shown"] is None else str(point["call_ev_shown"])
    odds = "-" if point["pot_odds"] is None else f"{float(point['pot_odds']):.2%}"
    levels = " ".join(
        f"座位{item['seat']}:档{item['level']}" for item in point["opponent_levels"]
    ) or "-"
    mistakes = "、".join(point["mistakes"]) or "无"
    codes = "、".join(point["contradictions"]) or "无"
    lines = [
        (
            f"  [{point['action_index']}] {street}  公共牌={point['board'] or '-'}  "
            f"玩家 {point['player_action']} {point['player_amount']}  "
            f"参考 {point['mode']} {point['mode_amount']}"
        ),
        f"    对手行动线 {levels}  最高={point['max_line']}  本街进攻={point['recent_aggression']}",
        (
            f"    特征 base={point['base']} draw={point['draw']} score={point['score']} "
            f"value_threshold={point['value_threshold']} call_threshold={point['call_threshold']} "
            f"被动={point['passive_score']} 价格={point['price']} "
            f"盖住口袋对={'是' if point.get('capped_board_two_pair') else '否'} "
            f"单对加注收口={'是' if point.get('pair_raise_applies') else '否'}"
        ),
        f"    原始分布 {_format_rows(point['raw_distribution'])}",
        f"    保护后 {_format_rows(point['distribution'])}",
        (
            f"    equity={float(point['equity']):.2%} pot_odds={odds} "
            f"call_ev={ev}（展示 {shown}） 底池={point['pot']} 待跟={point['to_call']}"
        ),
        f"    错误 {mistakes}",
    ]
    coach = point.get("coach")
    if isinstance(coach, dict):
        preference = coach.get("preference") or "-"
        referenced = "、".join(coach.get("reference_actions") or []) or "-"
        how = "记录" if coach.get("action_source") == "stored" else "推断"
        stale = " 缓存版本较旧" if coach.get("stale") else ""
        lines.append(
            f"    教练倾向 {preference}（{how}）  文中参考动作 {referenced}{stale}"
        )
        if coach.get("legacy_amounts") or coach.get("unknown_amounts"):
            lines.append(
                "    教练金额 "
                f"对上保护前总额={coach.get('legacy_amounts') or '-'} "
                f"对不上={coach.get('unknown_amounts') or '-'}"
            )
        lines.append(f"    教练正文 {coach.get('text')}")
    else:
        lines.append("    教练缓存 无")
    lines.append(f"    矛盾 {codes}")
    return lines


def format_scan(summary: dict) -> str:
    """把全库汇总收成计数和代表手牌。"""
    lines = [
        (
            f"手牌 {summary['hands']}  重放失败 {len(summary['replay_errors'])}  "
            f"真人决策 {summary['decisions']}  "
            f"面对下注 {summary['facing_bet']}  无人下注 {summary['free_action']}"
        ),
        "错误标记 "
        + (
            "  ".join(
                f"{code}={count}" for code, count in sorted(summary["mistake_counts"].items())
            )
            or "无"
        ),
    ]
    for item in summary["replay_errors"]:
        lines.append(f"  重放失败 {item['hand_id']} {item['error']}")
    for code in _CODE_ORDER:
        bucket = summary["codes"][code]
        lines.append(
            f"{bucket['label']}  决策={bucket['decisions']}  手牌={bucket['hands']}"
        )
        for example in bucket["examples"]:
            lines.append(f"    {_format_example(example)}")
    return "\n".join(lines)


def scan_database(path: Path | None = None, *, limit: int = 8) -> dict:
    """只读扫描整库手牌和教练缓存。"""
    connection = connect_readonly(path)
    try:
        coaches = load_coach_index(connection)
        histories = iter_histories(connection)
    finally:
        connection.close()
    reports = []
    total = len(histories)
    for index, (hand_id, history) in enumerate(histories, start=1):
        reports.append(
            diagnose_history(history, hand_id=hand_id, coach_rows=coaches.get(hand_id))
        )
        if index % 50 == 0 or index == total:
            print(f"已重放 {index}/{total}", file=sys.stderr)
    return summarize_reports(reports, limit=limit)


def diagnose_hand(hand_id: str, path: Path | None = None) -> dict:
    """只读取出一手并诊断。找不到时带 error 返回。"""
    connection = connect_readonly(path)
    try:
        history = load_history(connection, hand_id)
        coaches = load_coach_index(connection).get(hand_id, {})
    finally:
        connection.close()
    if history is None:
        return {"hand_id": hand_id, "error": "未找到手牌", "decisions": []}
    return diagnose_history(history, hand_id=hand_id, coach_rows=coaches)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读诊断复盘参考、错误标记和教练缓存是否一致")
    parser.add_argument("hand_id", nargs="*", help="手牌 ID；与 --scan 二选一")
    parser.add_argument("--scan", action="store_true", help="扫描全库并汇总各类矛盾")
    parser.add_argument("--limit", type=int, default=8, help="每类矛盾列出的代表手牌数")
    args = parser.parse_args(argv)
    if args.scan == bool(args.hand_id):
        parser.print_help()
        return 2
    try:
        if args.scan:
            print(format_scan(scan_database(limit=args.limit)))
            return 0
        failed = False
        for hand_id in args.hand_id:
            report = diagnose_hand(hand_id)
            print(format_report(report))
            if report.get("error"):
                failed = True
        return 1 if failed else 0
    except sqlite3.Error as exc:
        print(f"无法只读打开 {db_path()}：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
