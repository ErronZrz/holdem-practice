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
# 被测身份在配置载荷中的规范标识。这里只锁定字符串，不创建该身份。
UNDER_TEST_IDENTIFIER = "mixed-local@9"
_CAMPAIGN_ROOT = "74-domain-c"
_LOCKED_VERSIONS: tuple[tuple[str, int], ...] = (
    ("deal_mapping", 1),
    ("construction_mapping", 1),
    ("randomization_protocol", 1),
    ("execution_identity_schema", 1),
)


class HandPlan(BaseModel):
    """一手牌的定位：块内手序、庄位与被测座位。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hand_ordinal: PositiveInt
    button: NonNegativeInt
    probed_seat: NonNegativeInt


class CampaignLockVersions(BaseModel):
    """五个尚未锁定对象的版本号。此模型只承载这些版本，不表示最终运行冻结。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pairing_and_reset: PositiveInt
    per_hand_bound: PositiveInt
    fragment_template: PositiveInt
    weight_class: PositiveInt
    seat_rotation: PositiveInt


class CampaignConfiguration(BaseModel):
    """跨块稳定配置中尚未锁定的版本号。摘要由组成字段另行计算。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lock_versions: CampaignLockVersions


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
    block: NonNegativeInt
    campaign: str
    campaign_configuration: CampaignConfiguration

    @model_validator(mode="after")
    def _require_well_formed(self) -> Self:
        if isinstance(self.num_players, bool) or not 2 <= self.num_players <= 23:
            raise SpecIncompleteError("人数必须是 2 到 23 的整数")
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
        if not _is_lower_hex64(self.campaign):
            raise SpecIncompleteError("campaign 必须是小写 64 位十六进制")
        expected = campaign_configuration_digest(
            num_players=self.num_players,
            starting_stack=self.starting_stack,
            small_blind=self.small_blind,
            big_blind=self.big_blind,
            baseline_identifier=self.baseline_identifier,
            under_test_identifier=self.under_test_identifier,
            lock_versions=self.campaign_configuration.lock_versions,
        )
        if self.campaign != expected:
            raise SpecIncompleteError("campaign 与配置摘要不一致")
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


def _is_lower_hex64(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_game_count(name: str, value: int, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SpecIncompleteError(f"配置项不合法：{name}")
    return value


def campaign_configuration_payload(
    *,
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    baseline_identifier: str,
    under_test_identifier: str,
    lock_versions: CampaignLockVersions,
) -> dict[str, object]:
    """由组成字段组装配置载荷。载荷不含自身摘要，也不接受整份运行规格。"""
    if baseline_identifier != BASELINE_IDENTIFIER or under_test_identifier != UNDER_TEST_IDENTIFIER:
        raise SpecIncompleteError("身份标识与锁定常数不符")
    _require_game_count("num_players", num_players, minimum=2)
    if num_players > 23:
        raise SpecIncompleteError("人数不得超过 23")
    _require_game_count("starting_stack", starting_stack, minimum=1)
    _require_game_count("small_blind", small_blind, minimum=1)
    _require_game_count("big_blind", big_blind, minimum=1)
    versions: dict[str, int] = dict(_LOCKED_VERSIONS)
    versions.update(
        {
            "pairing_and_reset": lock_versions.pairing_and_reset,
            "per_hand_bound": lock_versions.per_hand_bound,
            "fragment_template": lock_versions.fragment_template,
            "weight_class": lock_versions.weight_class,
            "seat_rotation": lock_versions.seat_rotation,
        }
    )
    return {
        "schema": "campaign-configuration-v1",
        "campaign_root": _CAMPAIGN_ROOT,
        "game": {
            "num_players": num_players,
            "starting_stack": starting_stack,
            "small_blind": small_blind,
            "big_blind": big_blind,
        },
        "identities": {
            "baseline": BASELINE_IDENTIFIER,
            "under_test": UNDER_TEST_IDENTIFIER,
        },
        "lock_versions": versions,
    }


def campaign_configuration_digest(
    *,
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    baseline_identifier: str,
    under_test_identifier: str,
    lock_versions: CampaignLockVersions,
) -> str:
    """由组成字段重算配置摘要。调用时还不需要一份已经构造好的运行规格。"""
    payload = campaign_configuration_payload(
        num_players=num_players,
        starting_stack=starting_stack,
        small_blind=small_blind,
        big_blind=big_blind,
        baseline_identifier=baseline_identifier,
        under_test_identifier=under_test_identifier,
        lock_versions=lock_versions,
    )
    if "campaign" in payload or "block" in payload:
        raise SpecIncompleteError("配置载荷不得包含自身摘要或块序号")
    return content_digest(payload, algorithm="sha256")


def build_domain_run_spec(
    *,
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    engine_seed: int,
    baseline_identifier: str,
    under_test_identifier: str,
    deal: DealMappingSpec,
    protocol: RandomizationProtocolSpec,
    schedule: tuple[HandPlan, ...],
    block: int,
    campaign_configuration: CampaignConfiguration,
) -> DomainRunSpec:
    """先按组成字段计算摘要，再走普通构造。摘要写错会被构造校验拒绝。"""
    campaign = campaign_configuration_digest(
        num_players=num_players,
        starting_stack=starting_stack,
        small_blind=small_blind,
        big_blind=big_blind,
        baseline_identifier=baseline_identifier,
        under_test_identifier=under_test_identifier,
        lock_versions=campaign_configuration.lock_versions,
    )
    return DomainRunSpec(
        num_players=num_players,
        starting_stack=starting_stack,
        small_blind=small_blind,
        big_blind=big_blind,
        engine_seed=engine_seed,
        baseline_identifier=baseline_identifier,
        under_test_identifier=under_test_identifier,
        deal=deal,
        protocol=protocol,
        schedule=schedule,
        block=block,
        campaign=campaign,
        campaign_configuration=campaign_configuration,
    )


def schedule_payload(spec: DomainRunSpec) -> dict[str, object]:
    """手序计划的封闭载荷：含块序号，不含 campaign。"""
    return {
        "schema": "schedule-v1",
        "block": spec.block,
        "hands": [
            {
                "hand_ordinal": plan.hand_ordinal,
                "button": plan.button,
                "probed_seat": plan.probed_seat,
            }
            for plan in spec.schedule
        ],
    }


def schedule_digest(spec: DomainRunSpec) -> str:
    """由手序封闭载荷重算摘要。冻结清单与执行身份使用同一函数。"""
    payload = schedule_payload(spec)
    if "campaign" in payload:
        raise SpecIncompleteError("手序载荷不得包含 campaign")
    return content_digest(payload, algorithm=spec.protocol.digest_algorithm)
