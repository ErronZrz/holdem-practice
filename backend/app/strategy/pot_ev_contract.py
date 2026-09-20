"""逐池货币收益契约：把候选 CALL 的资格投影组合成受控的逐层收益口径。

设计目的：
- 既有资格投影只回答「有哪些层、谁有资格、是否确定回收」，不含实际支付、确定回收与
  后续行动情景；本模块把这四类事实组合成受控字段，供后续逐池收益工作消费；
- 只组合口径、不实现抽样：跨层共享的联合 runout 与期望份额在这里是**未求值的占位**，
  由字段与声明承载，不产出任何行动价值数值；
- 范围来源只作声明性引用，不展开权重，也不随公共牌收窄。

边界：
- 唯一输入是既有的资格投影与完整差额，本模块在结构上无法读取其他座位暗牌、未来公共牌
  与运行中的随机源；
- 座位口径沿用资格投影的绝对座位，不与位置与范围投影的相对座位口径混用；
- 本模块不接入任何生产路径，也不改变既有结算与复盘语义。
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, field_validator

from app.poker.pot_projection import (
    CandidateCallProjection,
    PotLayerKind,
    ProjectedPotLayer,
)

# 契约结构版本：字段集或口径变更时必须同步更新文档与测试。
POT_EV_CONTRACT_SCHEMA_VERSION = "pot-ev-contract.v1"
# 口径基准：逐层资格集合，且所有竞争层在同一联合 runout 下评估。
POT_EV_BASIS = "per-layer-eligible-shared-runout"
# 联合 runout 的共享范围：竞争层之间结果相关，不得按层独立抽样。
POT_EV_RUNOUT_SCOPE = "shared-across-layers"

# 名义份额与整数派彩是两件不同的事，分别声明，避免相互冒充。
POT_EV_NOMINAL_SHARE_RULE = (
    "每层名义份额按该层同级赢家人数 k 取 1/k；它是概率意义上的份额，不是整数派彩比例。"
)
POT_EV_INTEGER_PAYOUT_RULE = (
    "每层整数派彩先取 amount // k，余数按赢家座位升序逐个分配；它是确定性派彩规则。"
)

# 后续行动情景：受控闭集，本轮只登记「其余座位全部 CHECK/CALL 到摊牌」这一显式假设。
POT_EV_SCENARIO_CHECK_CALL = "others-check-call-to-showdown@1"
POT_EV_SCENARIOS: Mapping[str, str] = MappingProxyType(
    {
        POT_EV_SCENARIO_CHECK_CALL: (
            "其余座位自本街起全部 CHECK/CALL 到摊牌；不再有新的下注或加注。"
        ),
    }
)
POT_EV_DEFAULT_SCENARIO = POT_EV_SCENARIO_CHECK_CALL

# 范围来源：只引用受控 profile 标识与来源标注，不复制范围目录（目录归属范围假设模块）。
# 二者与范围假设模块的一致性由测试锁定，生产代码不反向依赖该模块。
POT_EV_RANGE_PROFILE_IDENTIFIER = "action-line-roles@1"
POT_EV_RANGE_SOURCE = "declared-model-assumption"

# 局限声明：集中定义，避免调用方各写一份。
POT_EV_LIMITATION_NOT_FULL_EV = "本契约只定义逐池收益口径，不产出 CALL EV 数值，也不是 GTO。"
POT_EV_LIMITATION_NO_SAMPLING = "本轮不实现联合 runout 或份额抽样；期望项是未求值的占位。"
POT_EV_LIMITATION_RANGE_DECLARED = "范围由声明式假设提供，不随公共牌收窄，也不读取真实底牌。"
POT_EV_LIMITATION_NOT_QUALIFICATION_PROJECTION = "资格投影与静态 share 不等于逐池 EV。"
POT_EV_LIMITATIONS = (
    POT_EV_LIMITATION_NOT_FULL_EV,
    POT_EV_LIMITATION_NO_SAMPLING,
    POT_EV_LIMITATION_RANGE_DECLARED,
    POT_EV_LIMITATION_NOT_QUALIFICATION_PROJECTION,
)

# 各模型的字段集：新增或删减字段都属于契约变更，必须同步更新文档与测试。
POT_EV_LAYER_FIELDS = (
    "lower_commitment",
    "upper_commitment",
    "amount",
    "contributor_seats",
    "eligible_seats",
    "kind",
    "disposition",
    "caller_eligible",
    "enters_expected_share",
    "certain_recovery",
)
POT_EV_CONTRACT_FIELDS = (
    "schema_version",
    "basis",
    "scenario_identifier",
    "scenario_description",
    "range_profile_identifier",
    "range_source",
    "player_count",
    "caller_seat",
    "call_amount",
    "actual_call_amount",
    "is_short_all_in_call",
    "runout_scope",
    "nominal_share_rule",
    "integer_payout_rule",
    "layers",
    "certain_recovery_total",
    "limitations",
)


class PotEvError(ValueError):
    """逐池收益契约构造失败。"""


class PotEvContractError(PotEvError):
    """契约被违反（类型错误、层序不连续、金额不一致等结构性非法输入）。"""


class PotEvEncodingError(PotEvError):
    """资格投影不完整或不可编码（层内资格与金额自相矛盾等）。"""


class UnknownScenarioError(PotEvError):
    """后续行动情景标识未知或版本不受支持。"""


class PotEvDisposition(StrEnum):
    """逐层收益处置：与资格投影的四类资格一一对应。"""

    CONTESTED = "contested"
    CERTAIN_RECOVERY = "certain_recovery"
    NOT_ELIGIBLE = "not_eligible"
    REFUND = "refund"


# 资格类型 -> 收益处置：四值一一对应，改一处即契约变更。
_DISPOSITION_BY_KIND: Mapping[object, PotEvDisposition] = MappingProxyType(
    {
        PotLayerKind.CONTESTED: PotEvDisposition.CONTESTED,
        PotLayerKind.CALLER_RECOVERY: PotEvDisposition.CERTAIN_RECOVERY,
        PotLayerKind.OTHER_UNCONTESTED: PotEvDisposition.NOT_ELIGIBLE,
        PotLayerKind.NO_ELIGIBLE_RETURN: PotEvDisposition.REFUND,
    }
)


def _is_versioned_identifier(value: object) -> bool:
    """判断标识是否为受控的 name@version 形式。"""
    if not isinstance(value, str):
        return False
    name, separator, version = value.partition("@")
    return separator == "@" and bool(name) and version.isascii() and version.isdigit()


class _FrozenModel(BaseModel):
    """本模块全部对外模型的公共基类：冻结、禁止未登记字段。"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PotEvLayer(_FrozenModel):
    """单个池层在收益口径下的处置：是否进入期望项、是否确定回收。"""

    lower_commitment: int
    upper_commitment: int
    amount: int
    contributor_seats: tuple[int, ...]
    eligible_seats: tuple[int, ...]
    kind: str
    disposition: PotEvDisposition
    caller_eligible: bool
    enters_expected_share: bool
    certain_recovery: int

    def model_post_init(self, __context: object) -> None:
        """锁定资格、处置与符号之间的自洽，使收益口径可复核。"""
        _require_layer_consistency(
            lower_commitment=self.lower_commitment,
            upper_commitment=self.upper_commitment,
            amount=self.amount,
            contributor_seats=self.contributor_seats,
            eligible_seats=self.eligible_seats,
            kind=self.kind,
            disposition=self.disposition,
            caller_eligible=self.caller_eligible,
            enters_expected_share=self.enters_expected_share,
            certain_recovery=self.certain_recovery,
        )


class PotEvContract(_FrozenModel):
    """一次候选 CALL 的逐池收益口径：逐层处置、确定回收、实际支付与后续行动情景。"""

    schema_version: str
    basis: str
    scenario_identifier: str
    scenario_description: str
    range_profile_identifier: str
    range_source: str
    player_count: int
    caller_seat: int
    call_amount: int
    actual_call_amount: int
    is_short_all_in_call: bool
    runout_scope: str
    nominal_share_rule: str
    integer_payout_rule: str
    layers: tuple[PotEvLayer, ...]
    certain_recovery_total: int
    limitations: tuple[str, ...]

    @field_validator("schema_version")
    @classmethod
    def _schema_version_must_match(cls, value: str) -> str:
        if value != POT_EV_CONTRACT_SCHEMA_VERSION:
            raise ValueError(
                f"逐池收益契约结构版本不匹配：期望 {POT_EV_CONTRACT_SCHEMA_VERSION}，"
                f"收到 {value!r}"
            )
        return value

    @field_validator("range_profile_identifier")
    @classmethod
    def _profile_identifier_must_be_versioned(cls, value: str) -> str:
        """标识必须是 name@version 形式，避免出现无法追溯版本的范围来源。"""
        if not _is_versioned_identifier(value):
            raise ValueError("范围 profile 标识必须形如 name@version")
        return value

    @field_validator("range_source")
    @classmethod
    def _range_source_must_be_declared(cls, value: str) -> str:
        """来源只允许声明式假设，从结构上禁止冒充求解器或训练产物。"""
        if value != POT_EV_RANGE_SOURCE:
            raise ValueError(f"不支持的范围来源标注：{value!r}")
        return value

    @field_validator("limitations")
    @classmethod
    def _must_declare_the_required_limitations(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        """必须同时声明四条局限，缺一即说明收益口径被当成完整结论。"""
        for required in (
            POT_EV_LIMITATION_NOT_FULL_EV,
            POT_EV_LIMITATION_NO_SAMPLING,
        ):
            if required not in value:
                raise ValueError(f"缺少必需的局限声明：{required}")
        return value

    def model_post_init(self, __context: object) -> None:
        """锁定人数、现金成本、情景与确定回收合计，使契约可复核。"""
        if self.player_count < 2:
            raise PotEvContractError("人数必须至少为 2")
        if not 0 <= self.caller_seat < self.player_count:
            raise PotEvContractError("当前行动者的绝对座位越界")
        if self.actual_call_amount < 1:
            raise PotEvContractError("实际支付必须为正数")
        if self.call_amount < self.actual_call_amount:
            raise PotEvContractError("完整差额不得小于实际支付")
        if self.is_short_all_in_call != (self.call_amount > self.actual_call_amount):
            raise PotEvContractError("短码全下标记必须与完整差额、实际支付一致")
        if self.runout_scope != POT_EV_RUNOUT_SCOPE:
            raise PotEvContractError(f"联合 runout 口径必须为 {POT_EV_RUNOUT_SCOPE}")
        if not self.layers:
            raise PotEvContractError("逐池收益契约至少需要一个池层")
        if not any(layer.caller_eligible for layer in self.layers):
            raise PotEvEncodingError("当前行动者在任何层都没有资格，投影不完整")
        expected_recovery = sum(layer.certain_recovery for layer in self.layers)
        if self.certain_recovery_total != expected_recovery:
            raise PotEvContractError("确定回收合计与逐层确定回收不一致")
        if self.scenario_identifier not in POT_EV_SCENARIOS:
            raise UnknownScenarioError(f"未知的后续行动情景：{self.scenario_identifier!r}")
        if self.scenario_description != POT_EV_SCENARIOS[self.scenario_identifier]:
            raise PotEvContractError("情景描述与已登记内容不一致")

    def layers_with(self, disposition: PotEvDisposition) -> tuple[PotEvLayer, ...]:
        """按处置筛选层，便于调用方复核期望项与确定回收各自的构成。"""
        return tuple(layer for layer in self.layers if layer.disposition == disposition)


def _require_positive_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PotEvContractError(f"{name} 必须是整数，收到 {type(value).__name__}")
    if value <= 0:
        raise PotEvContractError(f"{name} 必须为正数，收到 {value}")


def _require_profile_identifier(identifier: object) -> str:
    """校验范围 profile 标识的形式；不复制范围目录本身。"""
    if not _is_versioned_identifier(identifier):
        raise PotEvContractError(
            f"范围 profile 标识必须形如 name@version，收到 {identifier!r}"
        )
    return str(identifier)


def _require_projection(projection: object) -> CandidateCallProjection:
    if not isinstance(projection, CandidateCallProjection):
        raise PotEvContractError(
            f"逐池收益契约只接受候选 CALL 的资格投影，收到 {type(projection).__name__}"
        )
    return projection


def disposition_for_kind(kind: object) -> PotEvDisposition:
    """把资格层的资格类型映射成收益处置；不在四值内即明确失败。"""
    try:
        disposition = _DISPOSITION_BY_KIND.get(kind)
    except TypeError as error:
        raise PotEvEncodingError(f"未知的池层资格类型：{kind!r}") from error
    if disposition is None:
        raise PotEvEncodingError(f"未知的池层资格类型：{kind!r}")
    return disposition


def known_scenario_identifiers() -> tuple[str, ...]:
    """返回已登记情景标识的升序元组，供诊断与测试枚举。"""
    return tuple(sorted(POT_EV_SCENARIOS))


def scenario_description_for(identifier: object) -> str:
    """取受控情景的显式描述；未知标识明确失败，不回落默认情景。"""
    if not isinstance(identifier, str):
        raise PotEvContractError(
            f"情景标识必须是字符串，收到 {type(identifier).__name__}"
        )
    description = POT_EV_SCENARIOS.get(identifier)
    if description is None:
        raise UnknownScenarioError(f"未知的后续行动情景：{identifier!r}")
    return description


def _require_layer_consistency(
    *,
    lower_commitment: int,
    upper_commitment: int,
    amount: int,
    contributor_seats: tuple[int, ...],
    eligible_seats: tuple[int, ...],
    kind: object,
    disposition: object,
    caller_eligible: bool,
    enters_expected_share: bool,
    certain_recovery: int,
) -> None:
    """校验单层的资格、处置与符号自洽；不自洽即明确失败。"""
    if upper_commitment <= lower_commitment:
        raise PotEvContractError("层的上界必须大于下界")
    if amount <= 0:
        raise PotEvEncodingError("层的金额必须为正数")
    contributor = set(contributor_seats)
    eligible = set(eligible_seats)
    if not eligible <= contributor:
        raise PotEvEncodingError("层的资格者必须同时是该层贡献者")
    expected = disposition_for_kind(kind)
    if disposition != expected:
        raise PotEvEncodingError("层的收益处置与资格类型不一致")
    if enters_expected_share != (expected == PotEvDisposition.CONTESTED):
        raise PotEvEncodingError("只有竞争层可以进入期望项")
    if expected == PotEvDisposition.CERTAIN_RECOVERY:
        if not caller_eligible or certain_recovery != amount:
            raise PotEvEncodingError("确定回收层要求行动者有资格，且回收额等于层金额")
    elif certain_recovery != 0:
        raise PotEvEncodingError("非确定回收层不得携带确定回收额")


def _build_layer(layer: ProjectedPotLayer, caller_seat: int) -> PotEvLayer:
    """把单层资格记录组合成收益口径的层；自相矛盾即明确失败。"""
    disposition = disposition_for_kind(layer.kind)
    contributor = set(layer.contributor_seats)
    eligible = set(layer.eligible_seats)
    if not eligible <= contributor:
        raise PotEvEncodingError("层的资格者必须同时是该层贡献者")
    caller_eligible = caller_seat in eligible
    if bool(layer.caller_is_eligible) != caller_eligible:
        raise PotEvEncodingError("层的行动者资格标记与资格集合不一致")
    if disposition == PotEvDisposition.CERTAIN_RECOVERY and not caller_eligible:
        raise PotEvEncodingError("确定回收层要求行动者在该层有资格")
    if disposition == PotEvDisposition.REFUND and caller_seat in contributor:
        raise PotEvEncodingError("无人有资格的退款层不应包含未弃牌的行动者")
    certain_recovery = layer.amount if disposition == PotEvDisposition.CERTAIN_RECOVERY else 0
    return PotEvLayer(
        lower_commitment=layer.lower_commitment,
        upper_commitment=layer.upper_commitment,
        amount=layer.amount,
        contributor_seats=tuple(layer.contributor_seats),
        eligible_seats=tuple(layer.eligible_seats),
        kind=str(layer.kind),
        disposition=disposition,
        caller_eligible=caller_eligible,
        enters_expected_share=disposition == PotEvDisposition.CONTESTED,
        certain_recovery=certain_recovery,
    )


def _require_contiguous_layers(layers: tuple[PotEvLayer, ...]) -> None:
    """校验层序连续且金额与投入、贡献者数量一致，避免分层口径漂移。"""
    previous_upper = 0
    for layer in layers:
        if layer.lower_commitment != previous_upper:
            raise PotEvContractError("池层必须自 0 起连续切分，不得跳层或重叠")
        expected_amount = (layer.upper_commitment - layer.lower_commitment) * len(
            layer.contributor_seats
        )
        if layer.amount != expected_amount:
            raise PotEvContractError("层金额必须等于投入区间乘以贡献者数量")
        previous_upper = layer.upper_commitment


def build_pot_ev_contract(
    *,
    projection: CandidateCallProjection,
    call_amount: int,
    scenario_identifier: str = POT_EV_DEFAULT_SCENARIO,
    range_profile_identifier: str = POT_EV_RANGE_PROFILE_IDENTIFIER,
) -> PotEvContract:
    """由候选 CALL 的资格投影构造逐池收益口径；不做任何抽样或估值。

    只接受公开的资格投影、完整差额与受控情景标识，因此在结构上无法读取其他座位暗牌、
    未来公共牌与运行中的随机源。范围来源只引用受控 profile 标识，不展开其权重，也不
    复制范围目录（目录归属范围假设模块，二者一致性由测试锁定）。
    """
    _require_projection(projection)
    _require_positive_int("call_amount", call_amount)
    actual_call_amount = projection.actual_call_amount
    _require_positive_int("actual_call_amount", actual_call_amount)
    if call_amount < actual_call_amount:
        raise PotEvContractError(
            f"完整差额 {call_amount} 不得小于实际支付 {actual_call_amount}"
        )

    description = scenario_description_for(scenario_identifier)
    range_profile = _require_profile_identifier(range_profile_identifier)

    participants = tuple(projection.participants)
    player_count = len(participants)
    if player_count < 2:
        raise PotEvContractError(f"人数必须至少为 2，收到 {player_count}")
    caller_seat = projection.caller_seat
    if caller_seat not in {participant.seat for participant in participants}:
        raise PotEvContractError("当前行动座位不在参与者中")
    caller = next(participant for participant in participants if participant.seat == caller_seat)
    if caller.folded:
        raise PotEvEncodingError("已弃牌座位不能构造逐池收益契约")
    if not projection.layers:
        raise PotEvContractError("资格投影没有任何池层，无法组合逐池收益口径")

    layers = tuple(_build_layer(layer, caller_seat) for layer in projection.layers)
    _require_contiguous_layers(layers)
    if not any(layer.caller_eligible for layer in layers):
        raise PotEvEncodingError("当前行动者在任何层都没有资格，投影不完整")

    return PotEvContract(
        schema_version=POT_EV_CONTRACT_SCHEMA_VERSION,
        basis=POT_EV_BASIS,
        scenario_identifier=scenario_identifier,
        scenario_description=description,
        range_profile_identifier=range_profile,
        range_source=POT_EV_RANGE_SOURCE,
        player_count=player_count,
        caller_seat=caller_seat,
        call_amount=call_amount,
        actual_call_amount=actual_call_amount,
        is_short_all_in_call=call_amount > actual_call_amount,
        runout_scope=POT_EV_RUNOUT_SCOPE,
        nominal_share_rule=POT_EV_NOMINAL_SHARE_RULE,
        integer_payout_rule=POT_EV_INTEGER_PAYOUT_RULE,
        layers=layers,
        certain_recovery_total=sum(layer.certain_recovery for layer in layers),
        limitations=POT_EV_LIMITATIONS,
    )
