"""验证运行器的失败类别：按发生阶段分开，调用方据此分别处置。

设计目的：
- 规格缺项、协议结构、审计材料、材料绑定、冻结绑定、发牌材料、注入前校验、
  身份映射与主键材料各自成类，不做笼统归并；
- 任何一类都不提供回退路径：失败即终止，不重取材料，也不改用随机开手。
"""

from __future__ import annotations


class VerificationError(Exception):
    """验证运行器相关失败的基类。"""


class SpecIncompleteError(VerificationError):
    """运行前规格缺项或取值不合法：必填项不得缺省，也不设默认值。"""


class ProtocolSpecError(VerificationError):
    """随机化协议的结构不自洽：用途、索引字段、输出域或遍历顺序不合规。"""


class ProtocolAuditError(VerificationError):
    """逐读取审计材料与转录、逐读取记录或承诺不一致。"""


class MaterialBindingError(ProtocolAuditError):
    """材料与审计中被接受并承诺的取值不一致：材料来源无法复核。"""


class FreezeBindingError(VerificationError):
    """冻结清单与本次输入不一致：摘要由内容重算后不匹配。"""


class DealMaterialError(VerificationError):
    """发牌材料或发牌映射不合规：抽取序列、牌面表示或分配规则不符。"""


class InjectionPrecheckError(VerificationError):
    """注入前硬失败校验未通过；携带项名与说明以便定位。"""

    def __init__(self, item: str, detail: str) -> None:
        # 合作式继承：先取父类代理再调用，保留多继承下的方法解析顺序语义。
        parent = super()
        parent.__init__(f"注入前校验未通过（{item}）：{detail}")
        self.item = item
        self.detail = detail


class IdentityMappingError(VerificationError):
    """身份构造映射缺失，或出现隐式的身份选择。"""


class MaterialKeyError(IdentityMappingError):
    """主键材料不是恰好 32 字节的字节串。"""
