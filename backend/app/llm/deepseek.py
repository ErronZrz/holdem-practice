"""DeepSeek 对话补全适配。只负责发请求和解析响应，不组装牌局提示词。"""

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from app.llm.types import CoachUnavailableError, Completion

# 本机密钥文件。环境变量优先；这里只在进程没注入时兜底，密钥本身不入库。
KEY_FILE = Path.home() / ".config" / "deepseek" / "env"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
# 思考模式会先写思维链。超时留足余量，避免正文还没开始就被客户端掐断。
DEFAULT_TIMEOUT_SECONDS = 120.0

_MISSING_KEY = "未配置 DeepSeek 接口密钥，暂时无法生成教练解读"
_UPSTREAM = "教练解读暂时不可用，请稍后再试"
_TRUNCATED = "教练解读生成超出长度限制，请稍后再试"

Opener = Callable[[urllib.request.Request, float], object]


def resolve_api_key() -> str | None:
    """从环境变量或本机密钥文件读取接口密钥。两处都没有时返回空。"""
    configured = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if configured:
        return configured
    return _read_key_file(KEY_FILE)


class DeepSeekProvider:
    """调用 DeepSeek 对话补全，并保持思考模式开启。"""

    provider_name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        opener: Opener | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model_name = model
        self._timeout = timeout
        self._opener = opener

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
    ) -> Completion:
        """发送一次非流式补全。思考模式固定开启；只有结构化解读才要求 JSON。"""
        api_key = self._current_key()
        if not api_key:
            raise CoachUnavailableError(_MISSING_KEY)
        payload: dict[str, object] = {
            "model": self.model_name,
            "messages": messages,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        raw = self._read(request)
        return _parse_completion(raw)

    def _current_key(self) -> str | None:
        if self._api_key is not None:
            stripped = self._api_key.strip()
            return stripped or None
        return resolve_api_key()

    def _read(self, request: urllib.request.Request) -> bytes:
        opener = self._opener or _open_url
        try:
            response = opener(request, self._timeout)
            with response:
                return response.read()
        except CoachUnavailableError:
            raise
        except Exception as exc:
            raise CoachUnavailableError(_UPSTREAM) from exc


def _open_url(request: urllib.request.Request, timeout: float):
    """用关键字传入超时，避免把秒数当成请求体。"""
    return urllib.request.urlopen(request, timeout=timeout)


def _parse_completion(raw: bytes) -> Completion:
    """从补全响应取出正文、思维链和用量。空正文视为上游失败。"""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoachUnavailableError(_UPSTREAM) from exc
    if not isinstance(data, dict):
        raise CoachUnavailableError(_UPSTREAM)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise CoachUnavailableError(_UPSTREAM)
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise CoachUnavailableError(_UPSTREAM)
    content = message.get("content")
    text = content.strip() if isinstance(content, str) else ""
    if not text:
        if choice.get("finish_reason") == "length":
            raise CoachUnavailableError(_TRUNCATED)
        raise CoachUnavailableError(_UPSTREAM)
    reasoning = message.get("reasoning_content")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    details = usage.get("completion_tokens_details")
    reasoning_tokens = 0
    if isinstance(details, dict):
        reasoning_tokens = _as_int(details.get("reasoning_tokens"))
    return Completion(
        content=text,
        reasoning=reasoning.strip() if isinstance(reasoning, str) else "",
        prompt_tokens=_as_int(usage.get("prompt_tokens")),
        completion_tokens=_as_int(usage.get("completion_tokens")),
        reasoning_tokens=reasoning_tokens,
        total_tokens=_as_int(usage.get("total_tokens")),
    )


def _read_key_file(path: Path) -> str | None:
    """解析本机密钥文件中的导出语句。读不到文件就当作没配置。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        found = _parse_key_line(line)
        if found:
            return found
    return None


def _parse_key_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    name, separator, value = stripped.partition("=")
    if separator != "=" or name.strip() != "DEEPSEEK_API_KEY":
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()
    return value or None


def _as_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
