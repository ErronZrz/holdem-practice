"""把一手牌的复盘结果收成可发给教练的提示，并按决策缓存解读。"""

import hashlib
import json
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analysis.reference_identity import decision_cache_key
from app.llm.types import (
    CoachDecisionNotFoundError,
    CoachNotReadyError,
    CoachProvider,
    CoachUnavailableError,
)
from app.poker.cards import Card, Rank, Suit, card_from_str
from app.poker.evaluator import evaluate
from app.poker.hand import HandCategory
from app.storage import repository
from app.storage.models import CoachExplanationModel, CoachMessageModel

# 提示词结构变化时递增，已缓存的解读随之失效。
PROMPT_SCHEMA_VERSION = 5
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
    "one_card_outs",
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
- one_card_outs 是翻牌或转牌上再发一张就能成顺或成花的补牌数。翻前、河牌，以及已经成顺或成花时为 0。
  这个数为 0 时，不要把这手写成听牌。
- 参考动作来自紧手标准模式（mixed-tight-normal）。
  待跟注大于 0 且 call_ev < 0 时：份额低于平均，跟注、下注和加注质量都挪到弃牌；
  份额不低于平均且已有加注或下注时，跟注并入其中概率最高的主动动作；
  翻前未加注、跟注额不超过一个大盲且负期望很小则保留跟注；其余情况跟注挪到弃牌。
  翻后无人下注，且份额低于空气线，或行动线档位已经偏高且份额低于平均时，下注和加注质量已经挪到过牌。
  弃牌会被标成放弃正期望时，弃牌质量已经挪到跟注。
  参考只供对照，与参考不同本身不构成错误。

只能依据给出的事实，不要改写玩家动作、胜率、赔率、跟注期望或已标出的问题。
未出现在 revealed_hands 里的对手底牌是未知的，不要猜测具体牌面。

只输出一个 JSON 对象，不要加 Markdown 代码块，也不要附加说明。格式如下：
{"explanations":[{"action_index":0,"recommended_action":"fold","explanation":"两三句中文"}]}
explanations 必须恰好覆盖输入 decisions 中的每个 action_index，不得遗漏，也不得新增。
recommended_action 是你认为该决策点更合适的动作，只能是 fold、check、call、bet、raise 之一。
每个 explanation 都要有实质内容。
"""

_FOLLOWUP_SYSTEM = """\
你是德州扑克练习里的复盘教练。玩家正在针对一个已经点评过的决策点追问。请结合整手公开事实、该决策点指标、已有教练解读和此前的追问，用两三句简明中文直接回答。

指标口径：
- equity 是按未弃牌对手的公开行动线加权后的逐层摊牌份额，不是对随机两张牌，也不是求解器范围。
- pot_odds 与 call_ev 按候选跟注可达的池层计算。
  赔率是这次跟注相对该层底池的比例。
  期望净收益假设其余未弃牌对手都跟注到摊牌，不含加注的弃牌权益。
- one_card_outs 是翻牌或转牌上再发一张就能成顺或成花的补牌数。翻前、河牌，以及已经成顺或成花时为 0。
  这个数为 0 时，不要把这手写成听牌。
- 参考动作来自紧手标准模式（mixed-tight-normal），只供对照。与参考不同本身不构成错误。

只能依据给出的事实和已有解读，不要改写玩家动作、胜率、赔率、跟注期望、参考动作或已标出的问题。
未出现在 revealed_hands 里的对手底牌是未知的，不要猜测具体牌面。
直接用自然语言回答，不要输出 JSON，也不要加 Markdown 代码块。
"""

# 结构化动作只接受这五个词。中文说法在解析时折成同一个枚举。
_ACTION_ALIASES = {
    "fold": "fold",
    "check": "check",
    "call": "call",
    "bet": "bet",
    "raise": "raise",
    "弃牌": "fold",
    "过牌": "check",
    "跟注": "call",
    "下注": "bet",
    "加注": "raise",
    "再加注": "raise",
}


class _InvalidAction:
    """建议动作无法映射时的占位，用来和「单点允许缺字段」区分开。"""


_INVALID = _InvalidAction()
# 再发一张后只把成顺、成花算作听牌补牌，不含两对或三条升成葫芦。
_ONE_CARD_MADE = frozenset(
    {
        HandCategory.STRAIGHT,
        HandCategory.FLUSH,
        HandCategory.STRAIGHT_FLUSH,
    }
)

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
        payload, cache_key = _cache_binding(
            hand_id=hand_id,
            history=history,
            review=review,
            action_index=index,
            provider=provider,
        )
        existing = repository.get_coach_explanation(db, cache_key)
        if existing is not None:
            results[index] = _view(
                existing,
                street=str(decision["street"]),
                cached=True,
                messages=repository.list_coach_messages(db, cache_key),
            )
            continue
        pending.append((index, payload, cache_key))

    if not pending:
        return [item for item in results if item is not None]

    completion = provider.complete(render_messages([item[1] for item in pending]))
    parsed = _explanations_for(
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
            explanation=parsed[index][0],
            recommended_action=parsed[index][1],
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
            messages=repository.list_coach_messages(db, cache_key),
        )
    return [item for item in results if item is not None]


def cached_explanations(
    db: Session,
    *,
    hand_id: str,
    history: dict,
    review: dict,
    provider: CoachProvider,
) -> list[dict]:
    """只读取当前提示词版本下已经落库的解读和追问，不访问上游。"""
    found: list[dict] = []
    for index, decision in enumerate(review["decisions"]):
        _payload, cache_key = _cache_binding(
            hand_id=hand_id,
            history=history,
            review=review,
            action_index=index,
            provider=provider,
        )
        existing = repository.get_coach_explanation(db, cache_key)
        if existing is None:
            continue
        found.append(
            _view(
                existing,
                street=str(decision["street"]),
                cached=True,
                messages=repository.list_coach_messages(db, cache_key),
            )
        )
    return found


def ask_decision(
    db: Session,
    *,
    hand_id: str,
    history: dict,
    review: dict,
    action_index: int,
    question: str,
    provider: CoachProvider,
) -> dict:
    """围绕一个已有解读的决策点追问。提问和回复在上游成功后一起落库。"""
    decisions = review["decisions"]
    if action_index < 0 or action_index >= len(decisions):
        raise CoachDecisionNotFoundError("决策点不存在")
    payload, cache_key = _cache_binding(
        hand_id=hand_id,
        history=history,
        review=review,
        action_index=action_index,
        provider=provider,
    )
    existing = repository.get_coach_explanation(db, cache_key)
    if existing is None:
        raise CoachNotReadyError("请先获取该决策点的教练解读")
    prior = [
        {"role": row.role, "content": row.content}
        for row in repository.list_coach_messages(db, cache_key)
        if row.role in {"user", "assistant"}
    ]
    completion = provider.complete(
        render_followup_messages(
            payload,
            explanation=existing.explanation,
            recommended_action=existing.recommended_action,
            history=prior,
            question=question,
        ),
        json_mode=False,
    )
    reply = _followup_reply(completion.content)
    _save_followup(
        db,
        cache_key=cache_key,
        hand_id=hand_id,
        action_index=action_index,
        question=question,
        reply=reply,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
        reasoning_tokens=completion.reasoning_tokens,
        total_tokens=completion.total_tokens,
    )
    return _view(
        existing,
        street=str(decisions[action_index]["street"]),
        cached=True,
        messages=repository.list_coach_messages(db, cache_key),
    )


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
        "one_card_outs": _one_card_outs(
            _hero_cards(history, human_seat),
            [str(card) for card in decision["board"]],
        ),
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


def render_followup_messages(
    payload: dict,
    *,
    explanation: str,
    recommended_action: str | None,
    history: list[dict[str, str]],
    question: str,
) -> list[dict[str, str]]:
    """拼出追问对话。历史轮次只保留角色和正文，不回传思维链。"""
    facts = {
        "hand": {key: payload[key] for key in _HAND_FIELDS},
        "decision": {key: payload[key] for key in _DECISION_FIELDS},
        "coach": {
            "explanation": explanation,
            "recommended_action": recommended_action,
        },
    }
    encoded = json.dumps(facts, ensure_ascii=False, indent=2, sort_keys=True)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": _FOLLOWUP_SYSTEM},
        {
            "role": "user",
            "content": (
                "下面是这一手可以公开的事实、当前决策点和已有教练解读。"
                "请据此回答后面的追问。\n"
                f"{encoded}"
            ),
        },
    ]
    for item in history:
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content:
            continue
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages


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


def _cache_binding(
    *,
    hand_id: str,
    history: dict,
    review: dict,
    action_index: int,
    provider: CoachProvider,
) -> tuple[dict, str]:
    """算出这个决策点的公开事实和当前版本缓存键。"""
    payload = build_decision_payload(history, review, action_index)
    cache_key = decision_cache_key(
        hand_id=hand_id,
        action_index=action_index,
        seat=int(review["human_seat"]),
        input_digest=input_digest(payload),
        prompt_schema_version=PROMPT_SCHEMA_VERSION,
        provider=provider.provider_name,
        model=provider.model_name,
    )
    return payload, cache_key


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


def _save_followup(
    db: Session,
    *,
    cache_key: str,
    hand_id: str,
    action_index: int,
    question: str,
    reply: str,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_tokens: int,
    total_tokens: int,
) -> None:
    """提问和回复放进同一事务。上游失败时调用方不会走到这里。"""
    try:
        repository.add_coach_message(
            db,
            cache_key=cache_key,
            hand_id=hand_id,
            action_index=action_index,
            role="user",
            content=question,
            prompt_tokens=0,
            completion_tokens=0,
            reasoning_tokens=0,
            total_tokens=0,
        )
        repository.add_coach_message(
            db,
            cache_key=cache_key,
            hand_id=hand_id,
            action_index=action_index,
            role="assistant",
            content=reply,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def _view(
    row: CoachExplanationModel,
    *,
    street: str,
    cached: bool,
    messages: list[CoachMessageModel] | None = None,
) -> dict:
    visible = [
        _message_view(item)
        for item in messages or []
        if item.role in {"user", "assistant"}
    ]
    return {
        "action_index": row.action_index,
        "seat": row.seat,
        "street": street,
        "explanation": row.explanation,
        "recommended_action": row.recommended_action,
        "cached": cached,
        "provider": row.provider,
        "model": row.model,
        "messages": visible,
    }


def _message_view(row: CoachMessageModel) -> dict:
    return {
        "role": row.role,
        "content": row.content,
        "created_at": row.created_at.isoformat(timespec="seconds"),
    }


def _followup_reply(content: str) -> str:
    """追问正文以自然语言为准。整段是 JSON 时才取出回复字段，避免误切正文。"""
    candidate = _json_candidate(content)
    parsed = _whole_json(candidate)
    text = candidate
    if isinstance(parsed, str):
        text = parsed
    elif isinstance(parsed, dict):
        picked = _reply_field(parsed)
        if picked is None:
            raise CoachUnavailableError(_EMPTY)
        text = picked
    elif parsed is not None:
        raise CoachUnavailableError(_EMPTY)
    cleaned = sanitize_explanation(text)
    if not cleaned:
        raise CoachUnavailableError(_EMPTY)
    return cleaned


def _whole_json(text: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _reply_field(parsed: dict) -> str | None:
    for key in ("reply", "answer", "explanation"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


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


def _explanations_for(
    content: str,
    action_indexes: list[int],
) -> dict[int, tuple[str, str | None]]:
    """从一次响应里取出每个决策点的正文和建议动作。结构对不上时整批失败，不落库。"""
    require_action = len(action_indexes) > 1
    candidate = _json_candidate(content)
    parsed = _load_json(candidate)
    if parsed is not None:
        found = _collect_explanations(parsed, require_action=require_action)
        if found is None or set(found) != set(action_indexes):
            raise CoachUnavailableError(_EMPTY)
        selected = {index: found[index] for index in action_indexes}
    elif len(action_indexes) == 1 and candidate and candidate[0] not in "{[":
        selected = {action_indexes[0]: (candidate, None)}
    else:
        raise CoachUnavailableError(_EMPTY)

    cleaned: dict[int, tuple[str, str | None]] = {}
    for index, (raw, action) in selected.items():
        text = sanitize_explanation(raw)
        if not text:
            raise CoachUnavailableError(_EMPTY)
        cleaned[index] = (text, action)
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


def _collect_explanations(
    parsed: object,
    *,
    require_action: bool,
) -> dict[int, tuple[str, str | None]] | None:
    """接受按决策序号组织的几种 JSON 形状。序号重复或正文不是字符串时视为无法解析。"""
    if isinstance(parsed, list):
        return _explanations_from_rows(parsed, require_action=require_action)
    if not isinstance(parsed, dict):
        return None
    rows = parsed.get("explanations")
    if isinstance(rows, list):
        return _explanations_from_rows(rows, require_action=require_action)
    if isinstance(rows, dict):
        return _explanations_from_mapping(rows, require_action=require_action)
    if "action_index" in parsed and "explanation" in parsed:
        return _explanations_from_rows([parsed], require_action=require_action)
    return _explanations_from_mapping(parsed, require_action=require_action)


def _explanations_from_rows(
    rows: list,
    *,
    require_action: bool,
) -> dict[int, tuple[str, str | None]] | None:
    found: dict[int, tuple[str, str | None]] = {}
    for item in rows:
        if not isinstance(item, dict):
            return None
        index = _action_index(item.get("action_index"))
        text = item.get("explanation")
        action = _recommended_action(item.get("recommended_action"), required=require_action)
        if index is None or not isinstance(text, str) or action is _INVALID or index in found:
            return None
        found[index] = (text, action)
    return found


def _explanations_from_mapping(
    mapping: dict,
    *,
    require_action: bool,
) -> dict[int, tuple[str, str | None]] | None:
    found: dict[int, tuple[str, str | None]] = {}
    for key, value in mapping.items():
        index = _action_index(key)
        text = value if isinstance(value, str) else None
        raw_action = None
        if isinstance(value, dict):
            nested = value.get("explanation")
            text = nested if isinstance(nested, str) else None
            raw_action = value.get("recommended_action")
        action = _recommended_action(raw_action, required=require_action)
        if index is None or text is None or action is _INVALID or index in found:
            return None
        found[index] = (text, action)
    return found or None


def _recommended_action(value: object, *, required: bool) -> str | None | _InvalidAction:
    """把建议动作折成五个枚举之一。缺字段在单点可空，非法取值一律作废。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return _INVALID if required else None
    if not isinstance(value, str):
        return _INVALID
    token = value.strip()
    mapped = _ACTION_ALIASES.get(token)
    if mapped is None:
        mapped = _ACTION_ALIASES.get(token.casefold())
    if mapped is None:
        return _INVALID
    return mapped


def _one_card_outs(hole_labels: list[str], board_labels: list[str]) -> int:
    """翻牌或转牌上，再发一张才能成顺或成花的补牌数。已成顺花、翻前和河牌记 0。"""
    if len(board_labels) not in (3, 4) or len(hole_labels) != 2:
        return 0
    try:
        hole = [card_from_str(label) for label in hole_labels]
        board = [card_from_str(label) for label in board_labels]
    except (KeyError, ValueError):
        return 0
    if evaluate([*hole, *board]).category >= HandCategory.STRAIGHT:
        return 0
    known = set(hole) | set(board)
    outs = 0
    for suit in Suit:
        for rank in Rank:
            card = Card(rank, suit)
            if card in known:
                continue
            if evaluate([*hole, *board, card]).category in _ONE_CARD_MADE:
                outs += 1
    return outs


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
