"""运行前规格：全部必填，任何缺项即失败，本包不提供任何默认值。

设计目的：
- 把人数、筹码、盲注、显式引擎种子、两侧身份标识、发牌映射、随机化协议与手序计划
  集中成一份可校验的规格：缺项或取值越界都在构造阶段失败，不进入任何运行结构；
- 单一基线身份由常量给定并在规格中硬性核对，不接受任意受控标识充当比较基线；
- 手序计划由调用方逐手显式给出：庄位与轮换规则尚待冻结，本包不代为实现，也不推断。
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .deal import DealMappingSpec
from .digests import content_digest
from .errors import SpecIncompleteError
from .protocol import RandomizationProtocolSpec

StrictInt = Annotated[int, Field(strict=True)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]

# 单一基线身份：两臂的全部非被测座位与基线臂的被测座位共用该规范标识。
BASELINE_IDENTIFIER = "heuristic@1"


class HandPlan(BaseModel):
    """一手牌的定位：块内手序、庄位与被测座位。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hand_ordinal: PositiveInt
    button: NonNegativeInt
    probed_seat: NonNegativeInt


class DomainRunSpec(BaseModel):
    """一次配对比较的运行前规格。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    num_players: PositiveInt
    starting_stack: PositiveInt
    small_blind: PositiveInt
    big_blind: PositiveInt
    # 显式提供的引擎种子：注入开手路径不消耗引擎随机源，仍须显式给出以免依赖系统熵。
    engine_seed: StrictInt
    # 两侧身份都以规范标识给出，构造口径由身份映射决定，不在规格里隐式选择。
    baseline_identifier: str
    under_test_identifier: str
    deal: DealMappingSpec
    protocol: RandomizationProtocolSpec
    schedule: tuple[HandPlan, ...]

    @model_validator(mode="after")
    def _require_well_formed(self) -> Self:
        if self.num_players < 2:
            raise SpecIncompleteError("人数不得少于 2")
        if self.small_blind > self.big_blind:
            raise SpecIncompleteError("小盲不得超过大盲")
        declared = (
            ("baseline_identifier", self.baseline_identifier),
            ("under_test_identifier", self.under_test_identifier),
        )
        for name, value in declared:
            if not value.strip():
                raise SpecIncompleteError(f"身份标识不能为空：{name}")
        if self.baseline_identifier != BASELINE_IDENTIFIER:
            raise SpecIncompleteError("比较基线只能是单一基线身份")
        if self.baseline_identifier == self.under_test_identifier:
            raise SpecIncompleteError("两侧身份标识必须不同，否则配对比较退化")
        if not self.schedule:
            raise SpecIncompleteError("手序计划不能为空")
        ordinals = [plan.hand_ordinal for plan in self.schedule]
        if ordinals != sorted(set(ordinals)):
            raise SpecIncompleteError("块内手序必须严格递增且互不重复")
        for plan in self.schedule:
            if plan.button >= self.num_players or plan.probed_seat >= self.num_players:
                raise SpecIncompleteError("庄位与被测座位必须落在人数范围内")
        return self

    def plan_for(self, hand_ordinal: int) -> HandPlan:
        """按块内手序取出手计划；不存在即失败。"""
        for plan in self.schedule:
            if plan.hand_ordinal == hand_ordinal:
                return plan
        raise SpecIncompleteError(f"手序计划不含该手：{hand_ordinal}")


def spec_digest(spec: DomainRunSpec) -> str:
    """由域规格内容重算摘要：内容相同才可能得到相同摘要。"""
    return content_digest(
        spec.model_dump(mode="json"), algorithm=spec.protocol.digest_algorithm
    )


def schedule_digest(spec: DomainRunSpec) -> str:
    """由手序计划内容重算摘要：与消息顺序无关，只与逐手定位有关。"""
    payload = [plan.model_dump(mode="json") for plan in spec.schedule]
    return content_digest(payload, algorithm=spec.protocol.digest_algorithm)
