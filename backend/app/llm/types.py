"""教练上游的返回结构与失败类型。"""

from dataclasses import dataclass
from typing import Protocol


class CoachUnavailableError(Exception):
    """密钥缺失或上游失败。调用方将其转成可展示的错误，不影响复盘数字。"""


class CoachNotReadyError(Exception):
    """该决策点还没有当前版本的初始解读，不能直接追问。"""


class CoachDecisionNotFoundError(Exception):
    """追问序号不在这手真人决策点里。"""


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

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = True,
    ) -> Completion:
        """根据已构造好的对话返回一条回复。json_mode 为假时按自然语言读取正文。"""
