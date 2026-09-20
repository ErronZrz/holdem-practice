"""真实 Hold'em 规则切片与受限抽象切片之间的边界契约。

设计目的：
- 离线受限抽象只实现单街道、单次开池、唯一 rank、固定投入的常和整数博弈，其结论不是
  真实牌局 EV；本模块把「受限抽象切片的界」与「真实规则切片」逐条划分清楚，供后续工作
  判断哪些真实规则尚未建模；
- 判定取值与前置标识都是受控闭集，判定不可由调用方改写；抽象之外的切片必须明确失败，
  不得用最近桶、补零、默认尺度或插值冒充映射；
- 本模块只做分类与声明，不判定任何真实局面是否落入抽象，也不实现真实牌堆、公共牌、
  真实下注尺度、牌力评估或抽样。

边界：
- 抽象事实只复用既有的抽象契约模块常量，并补充它没有的标识与固定投入单位；本模块不导入
  离线训练器，也不导入其他应用模块，训练器描述的逐字一致由测试读取其源文件锁定；
- 本模块不接收生产快照、真实底牌、公共牌与运行中的随机源，不接入任何运行时路径。
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, field_validator

from app.strategy.abstraction import (
    ABSTRACTION_ACTIONS,
    ABSTRACTION_GAME_VERSION,
    ABSTRACTION_TRAINED_PLAYER_COUNTS,
)

# 契约结构版本：字段集或口径变更时必须同步更新文档与测试。
REAL_RULES_BOUNDARY_SCHEMA_VERSION = "real-rules-boundary.v1"
# 口径基准：受限抽象切片与真实规则切片之间的逐条划分。
REAL_RULES_BOUNDARY_BASIS = "abstraction-slice-vs-real-rule-slices"

# 受限抽象描述：版本、人数与动作从抽象契约模块复用，其余补充声明；不导入离线训练器。
ABSTRACTION_GAME_ID = "m8-unique-rank-single-open"
ABSTRACTION_PLAYER_COUNTS = tuple(sorted(ABSTRACTION_TRAINED_PLAYER_COUNTS))
ABSTRACTION_ACTION_TOKENS = tuple(sorted(ABSTRACTION_ACTIONS))
ABSTRACTION_ANTE = 1
ABSTRACTION_BET = 1

# 切片标识的词表：小写连字符形式，从结构上排除模块路径、下划线与文档编号。
FEATURE_ALPHABET = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")

# 受控前置标识：语义化连字符形式，对应的实际模块入口由测试逐一导入锁定。
PREREQUISITE_NONE = "none"
PREREQUISITES = (
    "abstraction-coverage",
    "candidate-call-pot-projection",
    "position-projection",
    "range-assumption",
    "pot-ev-contract",
)

# 局限声明：集中定义，避免调用方各写一份。
REAL_RULES_LIMITATION_NOT_REAL_EV = "受限抽象的结果不是真实牌局 EV，也不构成生产可用策略。"
REAL_RULES_LIMITATION_NO_IMPLEMENTATION = (
    "真实下注尺度与公共牌被划到抽象之外的界，本轮不实现真实牌堆或公共牌。"
)
REAL_RULES_LIMITATION_CONTRACTED_NOT_WIRED = (
    "已有受控契约承载的切片仍未接入生产，也不构成任何质量证据。"
)
REAL_RULES_LIMITATION_NO_SILENT_FALLBACK = (
    "抽象之外的切片必须明确失败，不得用最近桶、补零或插值冒充精确。"
)
REAL_RULES_LIMITATIONS = (
    REAL_RULES_LIMITATION_NOT_REAL_EV,
    REAL_RULES_LIMITATION_NO_IMPLEMENTATION,
    REAL_RULES_LIMITATION_CONTRACTED_NOT_WIRED,
    REAL_RULES_LIMITATION_NO_SILENT_FALLBACK,
)

# 各模型的字段集：新增或删减字段都属于契约变更，必须同步更新文档与测试。
RULE_SLICE_BOUNDARY_FIELDS = (
    "feature",
    "description",
    "verdict",
    "prerequisite",
    "declaration",
)
RULE_BOUNDARY_CONTRACT_FIELDS = (
    "schema_version",
    "basis",
    "abstraction_game_id",
    "abstraction_game_version",
    "abstraction_player_counts",
    "abstraction_ante",
    "abstraction_bet",
    "entries",
    "limitations",
)


class RealRulesBoundaryError(ValueError):
    """真实规则边界契约构造或查询失败。"""


class RealRulesBoundaryContractError(RealRulesBoundaryError):
    """契约被违反：条目与冻结目录不一致，或主张越界。"""


class UnknownBoundaryFeatureError(RealRulesBoundaryError):
    """切片标识不在冻结目录内。"""


class BoundaryVerdict(StrEnum):
    """单个真实规则切片相对于受限抽象切片的边界判定。"""

    IN_ABSTRACTION_SLICE = "in-abstraction-slice"
    OUT_OF_ABSTRACTION = "out-of-abstraction"
    CONTRACTED_NOT_WIRED = "contracted-not-wired"


class _FrozenModel(BaseModel):
    """本模块全部对外模型的公共基类：冻结、禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class RuleSliceBoundary(_FrozenModel):
    """单条边界：真实规则切片、判定、受控前置与边界声明。"""

    feature: str
    description: str
    verdict: BoundaryVerdict
    prerequisite: str
    declaration: str

    @field_validator("feature")
    @classmethod
    def _feature_must_be_a_controlled_identifier(cls, value: str) -> str:
        """切片标识只能是小写连字符形式，避免混入模块路径或下划线。"""
        if not value or any(char not in FEATURE_ALPHABET for char in value):
            raise ValueError("切片标识只能由小写字母、数字与连字符组成")
        return value

    @field_validator("prerequisite")
    @classmethod
    def _prerequisite_must_be_controlled(cls, value: str) -> str:
        if value != PREREQUISITE_NONE and value not in PREREQUISITES:
            raise ValueError(f"未知的受控前置标识：{value!r}")
        return value

    @field_validator("description", "declaration")
    @classmethod
    def _text_must_not_be_empty(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("说明与边界声明不能为空")
        return value

    def model_post_init(self, __context: object) -> None:
        """锁定判定与前置的关系：只有已有受控契约承载的切片才声明前置。"""
        if self.verdict is BoundaryVerdict.CONTRACTED_NOT_WIRED:
            if self.prerequisite == PREREQUISITE_NONE:
                raise RealRulesBoundaryContractError("已有受控契约承载的切片必须声明前置标识")
        elif self.prerequisite != PREREQUISITE_NONE:
            raise RealRulesBoundaryContractError("界内与界外切片不得声明受控前置标识")


class RuleBoundaryContract(_FrozenModel):
    """一次边界划分：受限抽象切片事实与逐条真实规则切片的边界。"""

    schema_version: str
    basis: str
    abstraction_game_id: str
    abstraction_game_version: str
    abstraction_player_counts: tuple[int, ...]
    abstraction_ante: int
    abstraction_bet: int
    entries: tuple[RuleSliceBoundary, ...]
    limitations: tuple[str, ...]

    @field_validator("schema_version")
    @classmethod
    def _schema_version_must_match(cls, value: str) -> str:
        if value != REAL_RULES_BOUNDARY_SCHEMA_VERSION:
            raise ValueError(
                f"边界契约结构版本不匹配：期望 {REAL_RULES_BOUNDARY_SCHEMA_VERSION}，"
                f"收到 {value!r}"
            )
        return value

    @field_validator("limitations")
    @classmethod
    def _must_declare_the_required_limitations(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        for required in (
            REAL_RULES_LIMITATION_NOT_REAL_EV,
            REAL_RULES_LIMITATION_NO_SILENT_FALLBACK,
        ):
            if required not in value:
                raise ValueError(f"缺少必需的局限声明：{required}")
        return value

    def model_post_init(self, __context: object) -> None:
        """锁定抽象事实与逐条边界：判定与冻结目录必须逐字一致，不可改写。"""
        if self.basis != REAL_RULES_BOUNDARY_BASIS:
            raise RealRulesBoundaryContractError("口径基准与契约不一致")
        if self.abstraction_game_id != ABSTRACTION_GAME_ID:
            raise RealRulesBoundaryContractError("受限抽象标识与契约不一致")
        if self.abstraction_game_version != ABSTRACTION_GAME_VERSION:
            raise RealRulesBoundaryContractError("受限抽象版本与契约不一致")
        if self.abstraction_player_counts != ABSTRACTION_PLAYER_COUNTS:
            raise RealRulesBoundaryContractError("受限抽象人数与契约不一致")
        if self.abstraction_ante != ABSTRACTION_ANTE or self.abstraction_bet != ABSTRACTION_BET:
            raise RealRulesBoundaryContractError("受限抽象投入单位与契约不一致")
        if len(self.entries) != len(_CATALOGUE):
            raise RealRulesBoundaryContractError("边界条目必须恰好覆盖冻结目录，不重不漏")
        for entry, expected in zip(self.entries, _CATALOGUE, strict=True):
            if entry != expected:
                raise RealRulesBoundaryContractError("边界条目与冻结目录不一致，判定不可改写")

    def entry_for(self, feature: str) -> RuleSliceBoundary:
        """按标识取本契约内的条目；未知标识明确失败。"""
        for entry in self.entries:
            if entry.feature == feature:
                return entry
        raise UnknownBoundaryFeatureError(f"本契约不含切片标识：{feature!r}")


def _slice(
    feature: str,
    description: str,
    verdict: BoundaryVerdict,
    declaration: str,
    prerequisite: str = PREREQUISITE_NONE,
) -> RuleSliceBoundary:
    return RuleSliceBoundary(
        feature=feature,
        description=description,
        verdict=verdict,
        prerequisite=prerequisite,
        declaration=declaration,
    )


# 冻结目录：顺序即契约顺序；判定与前置不可由调用方改写。
_CATALOGUE: tuple[RuleSliceBoundary, ...] = (
    _slice(
        "relative-seat-order",
        "相对座位与行动次序",
        BoundaryVerdict.IN_ABSTRACTION_SLICE,
        "抽象用相对座位 0..N-1 表达次序；不携带生产绝对座位、按钮或盲位。",
    ),
    _slice(
        "public-action-history",
        "公开行动线",
        BoundaryVerdict.IN_ABSTRACTION_SLICE,
        "抽象用规范 token 历史唯一派生行动者、投入与待回应顺序；金额不进历史口径。",
    ),
    _slice(
        "fold-and-alive-state",
        "弃牌与存活状态",
        BoundaryVerdict.IN_ABSTRACTION_SLICE,
        "弃牌跨行动持久，弃牌者投入为死钱；弃牌者不参与摊牌。",
    ),
    _slice(
        "fixed-integer-contributions",
        "固定整数投入",
        BoundaryVerdict.IN_ABSTRACTION_SLICE,
        "抽象只使用固定 ante 与固定 bet 的整数筹码单位，不表达可变尺度。",
    ),
    _slice(
        "constant-sum-utility",
        "常和整数收益",
        BoundaryVerdict.IN_ABSTRACTION_SLICE,
        "抽象每个终局满足派彩之和等于池、净收益之和为零。",
    ),
    _slice(
        "private-information-key",
        "私有信息与信息集键",
        BoundaryVerdict.IN_ABSTRACTION_SLICE,
        "信息集键只含行动者自己的 rank 与规范公开历史，不含其他座位私牌。",
    ),
    _slice(
        "blinds-and-forced-bets",
        "盲注与强制投入",
        BoundaryVerdict.OUT_OF_ABSTRACTION,
        "抽象没有盲注结构；真实盲注与强制投入不映射进抽象。",
    ),
    _slice(
        "multi-street-betting",
        "多街道下注轮",
        BoundaryVerdict.OUT_OF_ABSTRACTION,
        "抽象只有单街道单次开池；翻牌、转牌、河牌的下注轮不映射进抽象。",
    ),
    _slice(
        "public-board",
        "公共牌",
        BoundaryVerdict.OUT_OF_ABSTRACTION,
        "抽象没有公共牌；真实公共牌的发出与牌面不映射进抽象。",
    ),
    _slice(
        "variable-bet-sizing",
        "可变下注尺度",
        BoundaryVerdict.OUT_OF_ABSTRACTION,
        "抽象固定 bet 单位；真实下注尺度、最小加注与底池比例不映射进抽象。",
    ),
    _slice(
        "re-raise-multi-level",
        "再加注与多层加注",
        BoundaryVerdict.OUT_OF_ABSTRACTION,
        "抽象只允许一次开池；再加注与多层加注不映射进抽象。",
    ),
    _slice(
        "real-card-evaluation",
        "真实牌力评估",
        BoundaryVerdict.OUT_OF_ABSTRACTION,
        "抽象只比较唯一 rank；真实牌面与牌型评估不映射进抽象。",
    ),
    _slice(
        "opponent-real-hole-cards",
        "对手真实底牌",
        BoundaryVerdict.OUT_OF_ABSTRACTION,
        "对手真实底牌不进入任何投影、假设或收益口径。",
    ),
    _slice(
        "all-in-and-short-stack",
        "全下与短码",
        BoundaryVerdict.CONTRACTED_NOT_WIRED,
        "只有实际支付与逐层资格的可读投影；未接入策略或复盘的行动价值。",
        prerequisite="candidate-call-pot-projection",
    ),
    _slice(
        "side-pots",
        "边池",
        BoundaryVerdict.CONTRACTED_NOT_WIRED,
        "只有按公开投入的逐层资格投影；真实边池结算与逐层货币收益未建模。",
        prerequisite="candidate-call-pot-projection",
    ),
    _slice(
        "multiway-tie-share",
        "多人平局份额",
        BoundaryVerdict.CONTRACTED_NOT_WIRED,
        "只有名义份额与整数派彩的分开声明；期望项未求值，不作为已算出的收益。",
        prerequisite="pot-ev-contract",
    ),
    _slice(
        "per-pot-monetary-payoff",
        "逐池货币收益口径",
        BoundaryVerdict.CONTRACTED_NOT_WIRED,
        "只有逐层处置、确定回收与实际支付的口径；不产出任何行动价值数值。",
        prerequisite="pot-ev-contract",
    ),
    _slice(
        "position-and-action-line-projection",
        "位置与公开行动线投影",
        BoundaryVerdict.CONTRACTED_NOT_WIRED,
        "只有相对座位与按街分段的公开动作线投影；未接入生产路径。",
        prerequisite="position-projection",
    ),
    _slice(
        "action-line-range-assumption",
        "基于公开行动线的范围假设",
        BoundaryVerdict.CONTRACTED_NOT_WIRED,
        "只有声明式范围假设；不随公共牌收窄，也不是求解器输出。",
        prerequisite="range-assumption",
    ),
    _slice(
        "abstraction-mapping-and-coverage",
        "抽象映射与覆盖判定",
        BoundaryVerdict.CONTRACTED_NOT_WIRED,
        "只有受控抽象键与覆盖判定入口；不代劳真实局面到抽象的映射。",
        prerequisite="abstraction-coverage",
    ),
)

_CATALOGUE_BY_FEATURE: Mapping[str, RuleSliceBoundary] = MappingProxyType(
    {entry.feature: entry for entry in _CATALOGUE}
)


def boundary_catalogue() -> tuple[RuleSliceBoundary, ...]:
    """返回冻结的边界目录，顺序即契约顺序。"""
    return _CATALOGUE


def boundary_features() -> tuple[str, ...]:
    """返回全部切片标识的升序元组，供诊断与测试枚举。"""
    return tuple(sorted(_CATALOGUE_BY_FEATURE))


def _parse_verdict(value: object) -> BoundaryVerdict:
    if isinstance(value, BoundaryVerdict):
        return value
    if isinstance(value, str):
        try:
            return BoundaryVerdict(value)
        except ValueError as error:
            raise RealRulesBoundaryContractError(f"未知的边界判定取值：{value!r}") from error
    raise RealRulesBoundaryContractError(
        f"边界判定必须是受控取值，收到 {type(value).__name__}"
    )


def boundary_for(feature: object) -> RuleSliceBoundary:
    """按标识取边界条目；不在冻结目录内即明确失败。"""
    if not isinstance(feature, str):
        raise RealRulesBoundaryContractError(
            f"切片标识必须是字符串，收到 {type(feature).__name__}"
        )
    entry = _CATALOGUE_BY_FEATURE.get(feature)
    if entry is None:
        raise UnknownBoundaryFeatureError(f"未知的真实规则切片标识：{feature!r}")
    return entry


def verdict_for(feature: object) -> BoundaryVerdict:
    """返回某切片的边界判定；未知标识明确失败。"""
    return boundary_for(feature).verdict


def features_with(verdict: BoundaryVerdict | str) -> tuple[str, ...]:
    """返回某判定取值下的全部切片标识，顺序与冻结目录一致。"""
    parsed = _parse_verdict(verdict)
    return tuple(entry.feature for entry in _CATALOGUE if entry.verdict is parsed)


def require_in_abstraction_slice(feature: object) -> RuleSliceBoundary:
    """断言某切片在受限抽象切片的界内；界外或仅契约承载一律明确失败。"""
    entry = boundary_for(feature)
    if entry.verdict is not BoundaryVerdict.IN_ABSTRACTION_SLICE:
        raise RealRulesBoundaryContractError(
            f"切片 {entry.feature!r} 不在受限抽象切片的界内（判定为 {entry.verdict}），"
            "不得用近似映射冒充"
        )
    return entry


def build_rule_boundary_contract() -> RuleBoundaryContract:
    """构造边界契约；只声明事实与边界，不判定任何真实局面。"""
    return RuleBoundaryContract(
        schema_version=REAL_RULES_BOUNDARY_SCHEMA_VERSION,
        basis=REAL_RULES_BOUNDARY_BASIS,
        abstraction_game_id=ABSTRACTION_GAME_ID,
        abstraction_game_version=ABSTRACTION_GAME_VERSION,
        abstraction_player_counts=ABSTRACTION_PLAYER_COUNTS,
        abstraction_ante=ABSTRACTION_ANTE,
        abstraction_bet=ABSTRACTION_BET,
        entries=_CATALOGUE,
        limitations=REAL_RULES_LIMITATIONS,
    )
