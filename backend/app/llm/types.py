"""教练上游的返回结构与失败类型。"""

from dataclasses import dataclass
from typing import Protocol


class CoachUnavailableError(Exception):
    """密钥缺失或上游失败。调用方将其转成可展示的错误，不影响复盘数字。"""


@dataclass(frozen=True)
class Completion:
    """一次补全的正文、思维链与用量。"""

    content: str
    reasoning: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    total_tokens: int


class CoachProvider(Protocol):
    """可替换的教练上游。测试用替身，线上用 DeepSeek。"""

    provider_name: str
    model_name: str

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        """根据已构造好的对话返回一条解读。"""
