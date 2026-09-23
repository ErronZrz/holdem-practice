# 24 静态多人摊牌 share 原语：最小契约与实施确认

> 日期：2026-09-17。代码基线：`ffade90c59efcf0d4c6612f692b8fbcec5a3d84a`（`docs: record multiway tie share review`）。
>
> 状态：**已完成只读核对与方案 B 的候选契约；尚未获得本轮代码授权。** 本文不是实施确认，不修改 `equity()`、策略、复盘、API、前端、池层投影或结算。

## 1. 本轮目标、基线与确认边界

本轮唯一目标是为方案 B 定义一个独立的静态 share-aware 摊牌采样原语，并在实施前明确其最小契约、兼容性与测试范围。

开始时实际 Git 状态为：`master...origin/master`，工作区干净；`HEAD` 与上述基线一致。此前已经确认且继续有效的边界如下：

- `21` 的方案 B：翻后随机竞争集合包括所有未弃牌座位，包含全下者但排除弃牌者；这不是逐池货币 EV。
- `22` 的方案 B/C：完整欠注差额为 `C`，实际 CALL 支付为 `A`；`project_pot_layers()`、`project_candidate_call()` 与 `candidate_call_pot_projection()` 只做公开投入和资格投影；`_settle_showdown()` 继续是实际整数结算的权威实现。
- `23` 的结论：旧 `equity()` 对任意并列最强事件固定计入 `ties / 2`。它在单挑平局正确，但不代表三人及以上固定竞争集合的名义份额，也不是逐层或货币 EV。

本轮不开始 CFR、trainer、人格、位置、DeepSeek、UI 人数/布局或任何历史库诊断。没有修改真实库，也没有重新运行历史量化。

## 2. 现有事实与并行语义

### 2.1 旧 `equity()` 保持原样

`backend/app/poker/equity.py::equity()` 对每个样本从已知牌之外一次性抽取全部对手底牌与剩余公共牌，使用同一 runout 比较 Hero 和全部对手，但只保留最强对手牌力：

\[
E\left[\mathbf{1}_{Hero\;strictly\;wins}+\frac12\mathbf{1}_{Hero\;ties\;for\;best}\right]
\]

它的兼容契约不变：

- `num_opponents <= 0` 返回 `1.0`；
- 平局仍固定为 `ties / 2`；
- 每个样本仍只进行一次 `rng.sample(deck, need_opp + need_board)`；
- 既有调用的抽样顺序、固定 seed 回归和后续 RNG 状态不得改变。

这一点尤其影响 `HeuristicStrategy`：同一策略 RNG 先供 `equity()` 抽样，混合诈唬时又供动作采样。即使数值看似等价，重排旧 `equity()` 的随机消费也会改变固定 seed 下的后续动作序列。`hand_review` 同样继续使用旧 `equity()` 生成其既有展示、单池近似和保守参考输入。

### 2.2 候选新原语的语义

推荐新增一个与旧函数并行、且不替换旧调用的估计器：

```text
estimate_static_showdown_share(...) -> StaticShowdownShareEstimate
```

其只估计一个固定、单一、pooled 竞争集合下的静态名义摊牌份额：

\[
E\left[
  \begin{cases}
    1, & Hero\text{ 严格独赢}\\
    \frac{1}{k+1}, & Hero\text{ 与 }k\text{ 名对手同级最高}\\
    0, & Hero\text{ 未达到最高牌力}
  \end{cases}
\right]
\]

“并列最强事件”与“expected share”分开统计，不能把并列事件率当成期望份额。

## 3. 方案 B 的候选最小契约

### 3.1 名称、输入与输出

推荐在 `backend/app/poker/equity.py` 定义以下值对象和函数；名称刻意避免复用旧 `equity` 或暗示边池收益：

```text
@dataclass(frozen=True)
class StaticShowdownShareEstimate:
    strict_win_rate: float
    tie_for_best_rate: float
    expected_share: float

estimate_static_showdown_share(
    hole_cards: list[Card],
    board: tuple[Card, ...],
    num_opponents: int,
    rng: random.Random,
    samples: int = 1000,
) -> StaticShowdownShareEstimate
```

各字段含义固定如下：

| 字段 | 定义 | 不表示什么 |
|---|---|---|
| `strict_win_rate` | Hero 严格高于每名对手的样本比例 | 含平局的总胜率、货币赢率 |
| `tie_for_best_rate` | Hero 与至少一名对手同级、且共同达到样本最高牌力的比例 | 每次平局可分得的份额 |
| `expected_share` | 每个样本按 `1`、`1/(k+1)` 或 `0` 累加后的平均 | 边池 EV、整数派彩比例、CALL EV |

`num_opponents == 0` 的候选语义为 `strict_win_rate=1.0`、`tie_for_best_rate=0.0`、`expected_share=1.0`。推荐新函数拒绝负对手数和非正 `samples`，并继续让牌数不足、重复已知牌等与现有抽样相同的无效输入按底层牌堆计算失败。该参数校验仅属于新 API，不改变旧 `equity()` 对 `num_opponents <= 0` 的兼容行为。

### 3.2 每个样本的定义

对每一个样本：

1. 从排除 Hero 底牌和已公开公共牌后的牌堆中，一次无放回抽取 `2 * num_opponents + (5 - len(board))` 张；
2. 前段按每名对手两张分配，后段作为**同一次**联合 runout；
3. 使用现有 `evaluate_fast()` 评估 Hero 与每一名对手的完整牌力；
4. Hero 严格独赢时记录独赢事件与份额 `1`；
5. 任一对手更强时记录份额 `0`；
6. Hero 与 `k` 名对手同级且最高时记录并列事件与份额 `1 / (k + 1)`。

新函数应独立实现上述循环，不能调用或修改旧 `equity()`。两者可以复用 `_FULL_DECK`、已知牌排除、对手切片和联合 runout 的排列方式，但新函数必须保留全部对手牌力，不能只保留 `best_opp`。

### 3.3 随机性与信息边界

- 随机源继续由调用方注入 `random.Random`；相同的输入、seed 和样本数应得到相同的结构化结果。
- 新函数只使用 Hero 底牌、当时已公开公共牌、固定对手数和随机抽样；不接收真实对手底牌、未来公共牌、后续行动、终局边池或历史摊牌结果。
- 新函数本身仅推进其**显式传入的** RNG。当前没有调用方，不能在现有策略或复盘的 RNG 流中“顺便”调用它。

## 4. 为什么它只表示静态 pooled share

固定 `num_opponents` 表示一个单层、共同资格、无金额区分的竞争集合。该模型可以准确表达该集合内多人并列最强时的名义份额，却不能表达以下事实：

- 同一次 CALL 的不同 `PotLayer` / `ProjectedPotLayer` 可以具有不同 `eligible_seats`；
- 当前行动者可能只参与部分层，或在 `CALLER_RECOVERY` 中确定回收；
- `OTHER_UNCONTESTED`、`NO_ELIGIBLE_RETURN` 和弃牌死钱都不属于 Hero 的多人竞争 share；
- 实际层金额会按整数除法和既有座位顺序分配余数；
- 未来待行动者的 CALL、RAISE、FOLD 会改变后续投入与层级；
- 范围、位置、公开行动历史和后续策略假设尚未建模。

因此该原语只能称为“固定 pooled 竞争集合的静态名义 expected share”，不能称为边池 EV、完整 CALL EV、实际整数派彩或 GTO。

## 5. 与池层、整数余数和未来逐池模型的关系

现有分层和结算职责保持不变：

| 能力 | 当前权威来源 | 与候选 share 原语的关系 |
|---|---|---|
| 公开投入、贡献者、资格者与退款 | `project_pot_layers()` | 将来可提供逐层模型的公开输入；本轮不接入 |
| 候选实际 CALL 后层级资格 | `project_candidate_call()` / `candidate_call_pot_projection()` | 能说明 Hero 可争哪些层；不提供牌力、赢家或 share |
| 同级赢家与整数分配 | `_settle_showdown()` / `pot_results.shares` | 已正确按每层同级赢家均分并按座位分配余数；不修改 |
| 静态 pooled expected share | 候选 `estimate_static_showdown_share()` | 无层金额、无逐层资格、无整数余数 |

未来的逐池收益模型需要对每个竞争层使用对应 eligible 集合，在同一联合 runout 下计算层级赢家份额，再组合层金额、确定回收、实际支付 `A`、范围和明确后续行动情景。该未来模型不属于本轮方案 B。

## 6. 修复候选、实际最小实现与兼容代价

| 方案 | 内容 | 结论 |
|---|---|---|
| A | 保持旧 `equity()`，仅记录 `23` 的诊断 | 已完成，但不提供新的静态 share 能力 |
| B | 新增独立结构化静态 share 原语，不接入现有消费者 | **已获本轮确认并实施** |
| C | 将旧 `equity()` 改为按同级赢家人数计份额 | 不推荐；会静默改变策略、复盘、API 和固定 seed 行为 |
| D | 直接以新 share 计算逐池或 CALL 收益 | 不属于本轮；缺层级金额、资格、范围和后续行动模型 |

实际改动如下：

| 文件 | 实际改动 |
|---|---|
| `backend/app/poker/equity.py` | 新增冻结值对象 `StaticShowdownShareEstimate` 与 `estimate_static_showdown_share()`；逐样本保留全部对手牌力，分别累计严格独赢、并列最强事件和名义 expected share。旧 `equity()` 函数体与随机消费不改。 |
| `backend/tests/test_equity.py` | 锁定旧 `equity(0)` 和三人公共牌必平时的 `0.5`；新增 2/3/4/9 人必平、独赢、落败、输入校验、范围及固定 seed 回归。 |
| `backend/tests/test_engine.py` | 新增同一皇家同花 runout 下主池三人/边池两人资格差异、三人平分奇数余数，以及 2/3/4/9 人平局筹码守恒回归。 |
| 本文 | 记录确认、实际改动、测试结果与后续边界。 |

`backend/tests/test_pot_projection.py` 未修改；其已有回归继续覆盖死钱、短码全下、`CALLER_RECOVERY`、`OTHER_UNCONTESTED` 和 `NO_ELIGIBLE_RETURN`，并已在完整后端测试中运行。

没有修改 `strategy/heuristic.py`、`analysis/hand_review.py`、API schema、前端、`pot_projection.py`、`candidate_call_pot_projection()` 或 `_settle_showdown()`。新函数当前没有生产调用方，因此实时 Bot、复盘、历史动态重评、接口和 UI 行为不变。

## 7. 实施后测试与验收

本轮已覆盖：

1. 旧 `equity(0) == 1.0` 不变；三人公共牌必平时旧 `equity(..., 2)` 仍为 `0.5`。
2. 新原语的公共牌必平：2 人总人数为 `1/2`，3 人为 `1/3`，4 人为 `1/4`，9 人为 `1/9`；相应 `tie_for_best_rate=1`、`strict_win_rate=0`。
3. Hero 严格独赢、强制落败、单挑平局与多人平局分别覆盖；结构化字段均受 `[0, 1]` 范围约束。
4. 相同 seed、输入和样本数产生相同结果；旧 `equity()` 的已有同 seed 语义不变。
5. 引擎继续在同一 runout 下按主池三人和边池两人的不同资格集合结算；四人局三人平分的奇数余数仅写入 `pot_results.shares`。
6. 已有投影测试继续验证死钱、全下覆盖层、`CALLER_RECOVERY`、`OTHER_UNCONTESTED` 和 `NO_ELIGIBLE_RETURN` 不被表述为竞争 share。
7. 2/3/4/9 人的强制平局均验证赢家、金额 shares 与筹码守恒。

实际验证结果：

| 检查 | 结果 |
|---|---|
| 相关测试：`test_equity.py test_engine.py test_pot_projection.py` | `45 passed`，0.61s |
| 后端 `uv run ruff check .` | `All checks passed!` |
| 后端 `uv run pytest -q` | `160 passed, 2 warnings`，9.07s |
| 前端 `npm run build` | 通过，Vite 6.4.3，22 modules transformed |
| `git diff --check` | 通过 |

两条 warning 均为既有 Starlette/httpx 与 AnyIO 的弃用提示。本轮没有启动应用、重放真实历史或读写真实手牌库。

## 8. 用户确认记录

### 已确认

- 多人平局份额属于 CFR 前置核验；单层 static share 不得冒充逐池 EV 或 GTO。
- 旧 `equity()` 的 `ties / 2` 兼容语义、`21` 的全下竞争人数修复、`22` 的 `C/A` 与逐层资格能力不得回退。
- 真实历史库只读；除非代码或库摘要变化，不重复已有历史量化。
- 本轮开始前应核对 Git 状态，不覆盖用户改动。
- 用户已明确确认实施方案 B；本节名称、结构化返回和参数校验按此前候选契约落地。

### 尚未确认

- 将 share 能力接入 strategy、review、API、UI、训练或逐池收益模型；
- commit 或 push。

方案 B 的实现确认不构成这些后续变更、提交或推送授权。

## 9. 本轮实际改动、版本影响、遗留与下一小步

本轮新增 `StaticShowdownShareEstimate` 和 `estimate_static_showdown_share()`，以及对应的 equity / 引擎回归测试和本文档。旧 `equity()`、生产策略、复盘、API、前端、逐层资格投影、实际结算和真实手牌库均未修改。

版本影响仅限新增纯 Python API：既有调用方不导入或调用它，因此没有现有运行时输出、随机轨迹或历史格式变化。新 API 对负对手数和非正采样数抛出 `ValueError`；零对手返回严格独赢率与 expected share 均为 `1.0`、并列事件率为 `0.0`。

遗留：

1. 旧 `equity()` 仍会在多人平局样本中固定计入 `1/2`，策略和复盘的既有语义不变；
2. 新原语只解决固定 pooled 静态 share，不解决逐层货币收益；
3. 逐池模型仍需要逐层 eligible 集合、联合 runout、范围、实际支付、确定回收与后续行动情景；
4. 6/7/9 人的策略质量、CFR、人格、位置、行动历史和 UI 验收都不在本轮范围。

下一小步仅在新的明确确认后决定：可以评审新原语是否在严格限定的模型中接入后续逐层估值，也可以保持它作为训练前置的独立原语。当前等待本轮验收，以及单独的 commit/push 授权。