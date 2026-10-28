"""复盘参考与评估的版本身份，以及决策级缓存键契约。

参考身份由参考实现、发布前保护、份额估计与采样配置共同决定；任何一项变化都必须升版本，
否则旧手牌会在同一标签下被静默重评。本模块是该身份的唯一事实源。

升版规则：改动参考实现、发布前保护、份额估计实现、采样数或固定种子中的任一项，
必须同步升版本并记录原因；已产出的历史结论不得追溯改写。
"""

# 参考来源标识：紧手标准模式。该字面量只在本模块出现。
REFERENCE_STRATEGY = "mixed-tight-normal"
# 参考实现版本：第二十版紧手标准模式，参考分布关闭手号设伏与过牌保护。
# 面对下注且没过主动门槛时，未到同花不再白拿强牌加分。
# 顶对加更低公对按手中未配对底牌计踢脚，河牌与多人底池收紧托底。
# 四张同花面上低于皇后的单张同花不再按坚果尺度打。
# 翻后份额低于平均时，河牌或中等行动线的主动下注收成过牌；面对下注则把加注收成跟注。
REFERENCE_VERSION = 9
# 评估口径版本：行动线加权份额使用有效翻前分；过线先验落在一到两倍；
# 翻后连接度按档位门槛放大，没过翻前门槛的公共牌放大不超过 1。
EVALUATION_VERSION = 3
# 覆盖范围标识：按公开行动线给未弃牌对手加权。
REFERENCE_COVERAGE = "action-line-weighted"
# 缓存键格式版本：键结构本身变化时递增。
CACHE_KEY_VERSION = 1

# 参考适用域：说明发布前哪些参考质量会被份额和跟注期望改写。
REFERENCE_SCOPE = (
    "参考动作为紧手标准模式，且不随手号抽取设伏与过牌保护。"
    "短码对手尚未全下但盖不住完整最小加注、且主动价值质量为正时，保留合法最小加注。"
    "底牌配成牌面最高点数且另一对是更低公对时，有效基础分不低于同一张牌的顶对分。"
    "众数先按动作类型汇总概率，再取该类型里概率最高的尺度。"
    "面对下注且跟注期望为负时：份额低于当前人数的平均份额，则跟注、下注和加注都挪到弃牌；"
    "份额不低于平均且分布里已有加注或下注时，跟注质量并入其中概率最高的一条；"
    "翻前尚未加注、跟注额不超过大盲、且负期望不超过跟注容差时，保留跟注；"
    "其余情况把跟注挪到弃牌。"
    "翻后无人下注，且份额低于平均份额的一半，或对手行动线已达中等以上且份额低于平均，"
    "或河牌份额低于平均，或翻牌弱顶对份额低于平均时，主动质量挪到过牌。"
    "翻后面对下注、跟注期望不为负但份额低于平均时，加注和下注质量挪到跟注。"
    "弃牌会被标成放弃正期望时，弃牌质量挪到跟注。"
    "翻后面对下注、跟注期望为正且底牌具备可继续牌力时，弃牌质量挪到跟注。"
    "对外的跟注金额是当时实际要投入的筹码。"
)
# 参考局限：如实声明模型假设与不可推断事项，避免参考被当作求解器结论。
REFERENCE_LIMITATIONS = (
    "权重是公开行动线的人为分档，不是求解器范围。",
    "逐层跟注期望假定其他人跟注到摊牌，不含加注的弃牌权益。",
    "参考属非均衡近似，不构成求解器或训练产物的质量结论。",
    "与参考动作或其分布众数不同，本身不构成错误。",
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
