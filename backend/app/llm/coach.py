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
PROMPT_SCHEMA_VERSION = 3
_REASONING_SUMMARY_LIMIT = 500
_EMPTY = "教练解读暂时不可用，请稍后再试"

# 整手只出现一次的公开事实。决策点各自的指标不放在这里。
_HAND_FIELDS = (
    "seat",
    "hero_hole_cards",
    "public_actions",
    "revealed_hands",
    "reference_strategy",
    "reference_version",
    "evaluation_version",
    "reference_coverage",
    "reference_scope",
    "reference_limitations",
)
# 每个待点评决策点单独携带的指标。摘要仍按完整事实计算，不因这里的拆分改变。
_DECISION_FIELDS = (
    "action_index",
    "street",
    "board",
    "pot",
    "to_call",
    "actual_call_amount",
    "is_short_all_in_call",
    "opponents",
    "equity",
    "pot_odds",
    "call_ev",
    "action",
    "bot_action",
    "bot_distribution",
    "mistakes",
)

_SYSTEM_PROMPT = """\
你是德州扑克练习里的复盘教练。请先通盘看完整手牌的公开行动线，再针对待点评的每个决策点各写两三句简明中文。前后决策要连贯，不要逐街机械重复念胜率、赔率或期望数字。

指标口径：
- equity 是按未弃牌对手的公开行动线加权后的逐层摊牌份额，不是对随机两张牌，也不是求解器范围。
- pot_odds 与 call_ev 按候选跟注可达的池层计算。
  赔率是这次跟注相对该层底池的比例。
  期望净收益假设其余未弃牌对手都跟注到摊牌，不含加注的弃牌权益。
- 参考动作来自紧手标准模式（mixed-tight-normal）。
  当跟注是众数且 call_ev < 0 时，跟注质量已经挪到弃牌。
  参考只供对照，与参考不同本身不构成错误。

只能依据给出的事实，不要改写玩家动作、胜率、赔率、跟注期望或已标出的问题。
未出现在 revealed_hands 里的对手底牌是未知的，不要猜测具体牌面。

只输出一个 JSON 对象，不要加 Markdown 代码块，也不要附加说明。格式如下：
{"explanations":[{"action_index":0,"explanation":"两三句中文"}]}
explanations 必须恰好覆盖输入 decisions 中的每个 action_index，不得遗漏，也不得新增。
每个 explanation 都要有实质内容。
"""

_FENCE = re.compile(r"```(?:json)?[^\n]*\n?(.*?)```", re.DOTALL | re.IGNORECASE)

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
    """为每个真人决策点返回解读。全部命中缓存则不请求上游；未命中的点合并为一次请求。"""
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

    if not pending:
        return [item for item in results if item is not None]

    completion = provider.complete(render_messages([item[1] for item in pending]))
    texts = _explanations_for(
        completion.content,
        [item[0] for item in pending],
    )
    # 用量属于这一次合并请求，记在每个新写入的决策行上。
    summary = _reasoning_summary(completion.reasoning)
    for index, _payload, cache_key in pending:
        row, raced = _save_explanation(
            db,
            cache_key=cache_key,
            hand_id=hand_id,
            action_index=index,
            seat=human_seat,
            provider=provider.provider_name,
            model=provider.model_name,
            prompt_schema_version=PROMPT_SCHEMA_VERSION,
            explanation=texts[index],
            reasoning_summary=summary,
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


def render_messages(payloads: list[dict]) -> list[dict[str, str]]:
    """把本手公共上下文和待点评决策点渲染成同一次对话。不附带未公开的底牌。"""
    if not payloads:
        raise ValueError("没有待点评的决策点")
    body = json.dumps(_request_body(payloads), ensure_ascii=False, indent=2, sort_keys=True)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"请通盘看完这一手公开行动线，只点评下面这些决策点。\n{body}"},
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


def _request_body(payloads: list[dict]) -> dict:
    """公共上下文只取一份，每个决策点只保留自己的指标。"""
    hand = {key: payloads[0][key] for key in _HAND_FIELDS}
    decisions = []
    shared = set(_HAND_FIELDS)
    per_decision = set(_DECISION_FIELDS)
    for payload in payloads:
        decision = {key: payload[key] for key in _DECISION_FIELDS}
        decision.update(
            {
                key: value
                for key, value in payload.items()
                if key not in shared and key not in per_decision
            }
        )
        decisions.append(decision)
    return {"decisions": decisions, "hand": hand}


def _explanations_for(content: str, action_indexes: list[int]) -> dict[int, str]:
    """从一次响应里取出每个待点评决策点的正文。结构对不上时整批失败，不落库。"""
    candidate = _json_candidate(content)
    parsed = _load_json(candidate)
    if parsed is not None:
        found = _collect_explanations(parsed)
        if found is None or any(index not in found for index in action_indexes):
            raise CoachUnavailableError(_EMPTY)
        selected = {index: found[index] for index in action_indexes}
    elif len(action_indexes) == 1 and candidate and candidate[0] not in "{[":
        selected = {action_indexes[0]: candidate}
    else:
        raise CoachUnavailableError(_EMPTY)

    cleaned: dict[int, str] = {}
    for index, raw in selected.items():
        text = sanitize_explanation(raw)
        if not text:
            raise CoachUnavailableError(_EMPTY)
        cleaned[index] = text
    return cleaned


def _json_candidate(content: str) -> str:
    """去掉包住正文的 Markdown 代码块。没有代码块时保留原文。"""
    stripped = content.strip()
    match = _FENCE.search(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def _load_json(text: str) -> object | None:
    """尽量读出 JSON。正文前后若有多余说明，只截取最外层对象或数组。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start == -1 or end <= start:
            continue
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            continue
    return None


def _collect_explanations(parsed: object) -> dict[int, str] | None:
    """接受按决策序号组织的几种 JSON 形状。序号重复或正文不是字符串时视为无法解析。"""
    if isinstance(parsed, list):
        return _explanations_from_rows(parsed)
    if not isinstance(parsed, dict):
        return None
    rows = parsed.get("explanations")
    if isinstance(rows, list):
        return _explanations_from_rows(rows)
    if isinstance(rows, dict):
        return _explanations_from_mapping(rows)
    if "action_index" in parsed and "explanation" in parsed:
        return _explanations_from_rows([parsed])
    return _explanations_from_mapping(parsed)


def _explanations_from_rows(rows: list) -> dict[int, str] | None:
    found: dict[int, str] = {}
    for item in rows:
        if not isinstance(item, dict):
            return None
        index = _action_index(item.get("action_index"))
        text = item.get("explanation")
        if index is None or not isinstance(text, str) or index in found:
            return None
        found[index] = text
    return found


def _explanations_from_mapping(mapping: dict) -> dict[int, str] | None:
    found: dict[int, str] = {}
    for key, value in mapping.items():
        index = _action_index(key)
        text = value if isinstance(value, str) else None
        if text is None and isinstance(value, dict):
            nested = value.get("explanation")
            text = nested if isinstance(nested, str) else None
        if index is None or text is None or index in found:
            return None
        found[index] = text
    return found or None


def _action_index(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


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
