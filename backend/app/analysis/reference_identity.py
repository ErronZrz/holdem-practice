"""复盘参考与评估的版本身份，以及决策级缓存键契约。

参考身份由参考实现、保守判据、胜率估计与采样配置共同决定；任何一项变化都必须升版本，
否则旧手牌会在同一标签下被静默重评。本模块是该身份的唯一事实源。

升版规则：改动参考实现、保守判据、胜率估计实现、采样数或固定种子中的任一项，
必须同步升版本并记录原因；已产出的历史结论不得追溯改写。
"""

# 参考来源标识：对外兼容字段，保持既有取值不变。
REFERENCE_STRATEGY = "heuristic-conservative"
# 参考实现版本：参考策略与其保守收窄判据的实现版本。
REFERENCE_VERSION = 1
# 评估口径版本：胜率估计、采样数、固定种子与错误判据的共同版本。
EVALUATION_VERSION = 1
# 覆盖范围标识：只做「vs 随机范围」的静态近似，不含位置与范围建模。
REFERENCE_COVERAGE = "vs-random"
# 缓存键格式版本：键结构本身变化时递增。
CACHE_KEY_VERSION = 1

# 参考适用域：说明参考动作在哪些局面经过保守收窄、哪些局面沿用启发式基线。
REFERENCE_SCOPE = (
    "翻牌后面对下注与无人下注的局面经过保守收窄；翻牌前与加注沿用启发式基线。"
)
# 参考局限：如实声明模型假设与不可推断事项，避免参考被当作求解器结论。
REFERENCE_LIMITATIONS = (
    "胜率口径为 vs 随机范围的静态近似，未做对手范围与位置建模。",
    "参考由启发式规则加保守收窄构成，属非均衡近似；不构成求解器或训练产物的质量结论。",
    "与参考动作或其分布众数不同，本身不构成错误；错误只来自既有判据。",
)


def reference_identity() -> dict[str, object]:
    """返回参考与评估的版本身份，供对外响应声明。"""
    return {
        "reference_strategy": REFERENCE_STRATEGY,
        "reference_version": REFERENCE_VERSION,
        "evaluation_version": EVALUATION_VERSION,
        "reference_coverage": REFERENCE_COVERAGE,
    }


def reference_declaration() -> dict[str, object]:
    """在版本身份之上叠加适用域与局限声明，供对外响应一次性声明参考契约。

    适用域与局限在此集中定义，界面上出现的说明文案也据此渲染，避免多处各写一份。
    """
    return {
        **reference_identity(),
        "reference_scope": REFERENCE_SCOPE,
        "reference_limitations": list(REFERENCE_LIMITATIONS),
    }


def decision_cache_key(
    *,
    hand_id: str,
    action_index: int,
    seat: int,
    input_digest: str,
    prompt_schema_version: int,
    provider: str,
    model: str,
) -> str:
    """构造决策级缓存键；参考与评估版本参与其中，版本升级即失效。

    将来的解释/评估缓存必须使用本函数产生的键，不得退化为仅按手牌 ID 缓存。
    """
    return "|".join(
        (
            f"v{CACHE_KEY_VERSION}",
            hand_id,
            str(action_index),
            str(seat),
            input_digest,
            f"ref={REFERENCE_VERSION}",
            f"eval={EVALUATION_VERSION}",
            f"prompt={prompt_schema_version}",
            provider,
            model,
        )
    )
