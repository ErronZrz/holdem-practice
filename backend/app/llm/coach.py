"""把一手牌的复盘结果收成可发给教练的提示，并按决策缓存解读。"""

import hashlib
import json
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.reference_identity import decision_cache_key
from app.llm.types import CoachProvider, CoachUnavailableError
from app.storage import repository
from app.storage.models import CoachExplanationModel

# 提示词结构变化时递增，已缓存的解读随之失效。
PROMPT_SCHEMA_VERSION = 1
_REASONING_SUMMARY_LIMIT = 500
_EMPTY = "教练解读暂时不可用，请稍后再试"

_SYSTEM_PROMPT = (
    "你是德州扑克练习里的复盘教练。请只用中文，用两三句话点评这一个决策。\n"
    "只能依据给出的事实：不要改写玩家动作、胜率、赔率、跟注期望或已标出的问题。\n"
    "参考动作来自启发式加保守收窄，只供对照。\n"
    "已公开摊牌之外的对手底牌是未知的，不要猜测具体牌面。"
)

# 去掉把参考说成求解器结论的字样；否定语境保留。
_REPLACEMENTS = (
    (re.compile(r"nashconv", re.IGNORECASE), "参考偏差"),
    (re.compile(r"exploitab\w*", re.IGNORECASE), "可被针对"),
    (re.compile(r"gto", re.IGNORECASE), "参考"),
    (re.compile("最优"), "参考"),
    (re.compile(r"(?<!非)均衡"), "近似"),
)


def explain_decisions(
    db: Session,
    *,
    hand_id: str,
    history: dict,
    review: dict,
    provider: CoachProvider,
) -> list[dict]:
    """为每个真人决策点返回解读。命中缓存则不再请求上游；没有决策点时直接返回空列表。"""
    decisions = review["decisions"]
    if not decisions:
        return []
    human_seat = int(review["human_seat"])
    results: list[dict | None] = [None] * len(decisions)
    pending: list[tuple[int, dict, str]] = []
    for index, decision in enumerate(decisions):
        payload = build_decision_payload(history, review, index)
        cache_key = decision_cache_key(
            hand_id=hand_id,
            action_index=index,
            seat=human_seat,
            input_digest=input_digest(payload),
            prompt_schema_version=PROMPT_SCHEMA_VERSION,
            provider=provider.provider_name,
            model=provider.model_name,
        )
        existing = repository.get_coach_explanation(db, cache_key)
        if existing is not None:
            results[index] = _view(existing, street=str(decision["street"]), cached=True)
            continue
        pending.append((index, payload, cache_key))

    for index, payload, cache_key in pending:
        completion = provider.complete(render_messages(payload))
        text = sanitize_explanation(completion.content)
        if not text:
            raise CoachUnavailableError(_EMPTY)
        row, raced = _save_explanation(
            db,
            cache_key=cache_key,
            hand_id=hand_id,
            action_index=index,
            seat=human_seat,
            provider=provider.provider_name,
            model=provider.model_name,
            prompt_schema_version=PROMPT_SCHEMA_VERSION,
            explanation=text,
            reasoning_summary=_reasoning_summary(completion.reasoning),
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            reasoning_tokens=completion.reasoning_tokens,
            total_tokens=completion.total_tokens,
        )
        results[index] = _view(
            row,
            street=str(decisions[index]["street"]),
            cached=raced,
        )
    return [item for item in results if item is not None]


def build_decision_payload(history: dict, review: dict, action_index: int) -> dict:
    """摘出这一个决策点可以公开的事实。未摊牌的对手底牌不进入结果。"""
    decision = review["decisions"][action_index]
    human_seat = int(review["human_seat"])
    return {
        "action_index": action_index,
        "seat": human_seat,
        "hero_hole_cards": _hero_cards(history, human_seat),
        "board": [str(card) for card in decision["board"]],
        "street": decision["street"],
        "pot": decision["pot"],
        "to_call": decision["to_call"],
        "actual_call_amount": decision["actual_call_amount"],
        "is_short_all_in_call": decision["is_short_all_in_call"],
        "opponents": decision["opponents"],
        "equity": decision["equity"],
        "pot_odds": decision["pot_odds"],
        "call_ev": decision["call_ev"],
        "action": _choice(decision["action"]),
        "bot_action": _choice(decision["bot_action"]),
        "bot_distribution": [_probability(item) for item in decision["bot_distribution"]],
        "mistakes": [_mistake(item) for item in decision["mistakes"]],
        "public_actions": _public_actions(history),
        "revealed_hands": _revealed_opponents(history, human_seat),
        "reference_strategy": review["reference_strategy"],
        "reference_version": review["reference_version"],
        "evaluation_version": review["evaluation_version"],
        "reference_coverage": review["reference_coverage"],
        "reference_scope": review["reference_scope"],
        "reference_limitations": list(review["reference_limitations"]),
    }


def input_digest(payload: dict) -> str:
    """对公开事实做稳定摘要，供决策缓存键使用。"""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def render_messages(payload: dict) -> list[dict[str, str]]:
    """把同一份公开事实渲染成对话。不额外附带历史里的底牌字段。"""
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"请点评下面这个决策点。\n{body}"},
    ]


def sanitize_explanation(text: str) -> str:
    """净化教练正文，避免把参考表述成求解器结论。"""
    cleaned = text
    for pattern, replacement in _REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned.strip()


def _save_explanation(db: Session, **fields) -> tuple[CoachExplanationModel, bool]:
    """写入解读。并发下若键已存在，改读已有行，避免重复失败。"""
    try:
        row = repository.add_coach_explanation(db, **fields)
        db.commit()
        return row, False
    except IntegrityError:
        db.rollback()
        found = repository.get_coach_explanation(db, fields["cache_key"])
        if found is None:
            raise
        return found, True


def _view(row: CoachExplanationModel, *, street: str, cached: bool) -> dict:
    return {
        "action_index": row.action_index,
        "seat": row.seat,
        "street": street,
        "explanation": row.explanation,
        "cached": cached,
        "provider": row.provider,
        "model": row.model,
    }


def _reasoning_summary(reasoning: str) -> str | None:
    cleaned = sanitize_explanation(reasoning)
    if not cleaned:
        return None
    if len(cleaned) > _REASONING_SUMMARY_LIMIT:
        return cleaned[:_REASONING_SUMMARY_LIMIT]
    return cleaned


def _hero_cards(history: dict, human_seat: int) -> list[str]:
    for player in history.get("players") or []:
        if isinstance(player, dict) and player.get("seat") == human_seat:
            cards = player.get("hole_cards") or []
            return [str(card) for card in cards]
    return []


def _revealed_opponents(history: dict, human_seat: int) -> list[dict]:
    showdown = history.get("showdown_hands") or {}
    if not isinstance(showdown, dict):
        return []
    revealed: list[dict] = []
    for seat_key, info in showdown.items():
        if not isinstance(info, dict):
            continue
        try:
            seat = int(seat_key)
        except (TypeError, ValueError):
            continue
        if seat == human_seat:
            continue
        cards = info.get("cards")
        if not isinstance(cards, list):
            continue
        revealed.append(
            {
                "seat": seat,
                "cards": [str(card) for card in cards],
                "category": str(info.get("category") or ""),
            }
        )
    revealed.sort(key=lambda item: int(item["seat"]))
    return revealed


def _public_actions(history: dict) -> list[dict]:
    actions = []
    for record in history.get("actions") or []:
        if not isinstance(record, dict):
            continue
        actions.append(
            {
                "street": record.get("street"),
                "seat": record.get("seat"),
                "action": record.get("action"),
                "amount": record.get("amount"),
            }
        )
    return actions


def _choice(choice: dict) -> dict:
    return {"action": choice["action"], "amount": choice["amount"]}


def _probability(item: dict) -> dict:
    return {
        "action": item["action"],
        "amount": item["amount"],
        "probability": item["probability"],
    }


def _mistake(item: dict) -> dict:
    return {
        "code": item["code"],
        "severity": item["severity"],
        "message": item["message"],
    }
