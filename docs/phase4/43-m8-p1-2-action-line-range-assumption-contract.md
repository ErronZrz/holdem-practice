# 43 M8：P1-2 基于公开行动线的范围假设模型（规格冻结）

> 日期：2026-09-18。
>
> 本文件接在 `docs/42` / `docs/42a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/43` 记录本轮**规格与决策冻结**，`docs/43a` 记录与之对应的**实施与验证回执**。`docs/20` 至 `docs/42a` 未被改写。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P1-2** 一项的规格冻结与设计岔路裁定。代码与测试在随后一次提交中落地，回执见 `docs/43a`。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项）

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P1-2 | 范围模型替代「vs 随机底牌」 | **是** |
| P0-1 … P0-7 | 注册表、lookup 预算、抽象映射、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**复用**） |
| P1-1 | 位置与公开行动历史的信息集投影 | 否（已完成，仅**消费**其投影） |
| P1-3 | 逐池货币收益（短码 / 边池 / 多人平局） | 否 |
| P1-4 | 真实 Hold'em 的下注尺度与公共牌 | 否 |
| P1-5 | 修复后 6/7（及 2–9）人性能复测 | 否 |
| P2-1 … P2-4 | 2–9 人产品验收、N=9 结论、历史 `pot_results`、稳定性生产者 | 否 |

P1-2 **只是** `docs/35` §4.2 清单中的一项；本文件不改变其余条目的现状、优先级或失效条件。按 `docs/35` §4.3 的依赖，P1-2 是 **P1-3** 的先决项，但本轮**不**推进 P1-3。

### 1.2 用户答复原文（执行确认与三个设计岔路）

本轮采用「**先问用户**」而非「先在文档冻结规格」。答复原文照录：

| 项 | 用户答复原文 |
|---|---|
| 执行确认与边界 | 「确认执行；trainer 与 poker 只读」(允许改 `backend/app/strategy/`（新增范围假设模块，不改既有语义）、`backend/tests/`、`docs/43*`；`tools/trainer/**` 与 `backend/app/poker/**` 零改动、不 import（含不 import `equity.py`）) |
| 岔路一+四：载体与接入面 | 「新增独立模块，零接入」(新增 `backend/app/strategy/range_assumption.py`（不动 `heuristic.py` / `hand_review.py` / `equity.py` / api / 前端）；新模块**无生产调用方**，不改变任何运行时路径与对外响应；与 P1-1 的 `position_projection` 平行（推荐）) |
| 岔路二：范围表示形式 | 「按公开行动线角色给显式起手牌类权重」(受控 profile（标识 `name@version` + 来源标注）把公开行动线模式映射到每个对手**角色**（开池者/跟注者/盲注/未行动）的一套 **169 起手牌类显式权重**；排序与权重为**本模块本地冻结常量**，不 import heuristic 私有函数；**不随公共牌收窄**（如实声明为局限）；不可匹配的行动线**明确失败**，不用最近档/补零/插值（推荐）) |
| 岔路三：与 P0-5 参考身份关系 | 「不动 reference_identity.py」(范围假设自带独立 profile 版本与来源标注，仅以只读方式引用当前生产口径 vs-random 作为对照；**不新增 coverage 取值、不升 REFERENCE/EVALUATION 版本**，零对外响应与缓存键影响（推荐）) |

据此，**被授权**：在 `backend/app/strategy/` 新增范围假设模块（不改既有模块语义）、在 `backend/tests/` 新增回归测试、新增 `docs/43*`。
**被拒绝**（本轮不做）：`tools/trainer/**` 与 `backend/app/poker/**` 任何改动或不 import 之外的引用；`backend/app/analysis/**`（含 `reference_identity.py`）任何改动；`heuristic.py` 决策语义改动；任何生产接入（策略 / 复盘 / API / 前端）；逐池 EV、真实下注尺度、性能复测。

### 1.3 四项裁定（冻结）

| 岔路 | 裁定 |
|---|---|
| 一 | 新增 `backend/app/strategy/range_assumption.py` 作为**纯函数 + Pydantic 模型**入口；**不改动** `heuristic.py`、`hand_review.py`、`reference_identity.py`、`poker/equity.py`、API 与前端；新模块**无生产调用方**，不改变任何运行时路径、对外响应与缓存键。 |
| 二 | 范围假设的**唯一输入**是 P1-1 的 `PositionProjection`（公开信息）；**不接收**公共牌、底池金额、筹码与任何真实底牌，因此在结构上无法随公共牌收窄、也无法读取对手暗牌。 |
| 三 | 范围内容由**受控 profile**（标识 `name@version` + 来源标注 + 依据声明）给出：按对手**角色**赋予「取冻结起手牌类顺序前 N 个类」的显式权重；排序与权重均为**后端本地冻结常量**，不 import `heuristic.py` 任何内容。 |
| 四 | **不动** `backend/app/analysis/reference_identity.py`：不新增 coverage 取值、不升 `REFERENCE_VERSION` / `EVALUATION_VERSION`、不改 `REFERENCE_COVERAGE`。范围假设的版本与来源由本模块**自带**；与生产参考口径的对照只在**文档**与本模块的**声明字段**中给出，且由一条测试锁定两者不漂移。 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 14]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -5 --oneline
0e5fd52 feat: add controlled position and public action line projection
bf6794d docs: freeze p1-1 position and public action line projection specs
9c684e7 feat: add controlled artifact lookup with budget contract and opt-in measurement
3d3c7d1 docs: freeze p0-2 lookup performance and memory budget specs
d6fa89c feat: add controlled abstraction projection coverage verdict and fallback declaration

$ git rev-parse HEAD          -> 0e5fd52fda69e6420e68c1d197d6b48b174c9946
$ git rev-parse origin/master -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
$ find /Users/bryanylliu/holdem-campaigns -name strategy.json | wc -l
11

$ ls -1 backend/app/strategy/
__init__.py  abstraction.py  artifact.py  heuristic.py  interface.py  lookup_budget.py
position_projection.py  projection.py  random_strategy.py  registry.py

$ ls -1 backend/app/analysis/
__init__.py  hand_review.py  reference_identity.py
```

与期望基线完全相符；未做任何 `reset` / `clean` / `stash` / `checkout`；**未 push**；未消耗任何本机实验预算。

## 3. 现状事实与必然落差（只读核验）

### 3.1 现有估值口径与消费方

- `backend/app/poker/equity.py::equity()` 的精确语义是 \(E[\mathbf 1_{严格独赢}+\tfrac12\mathbf 1_{并列最强}]\)，`num_opponents <= 0` 返回 `1.0`，平局一律折半（`docs/23` §2.1）。它在函数内**只保留所有对手中的最高牌力**，不统计同级赢家人数；`docs/23` §2.2 已确认它不是逐层 share，也不是逐池货币 EV。
- `backend/app/strategy/heuristic.py` 翻后把「自己以外未弃牌座位数」（`_num_pot_contenders`）传给 `equity()`，阈值 `_VALUE_BET_EQ = 0.70`、`_RAISE_EQ = 0.90`、`_AIR_EQ = 0.25` 消费同一数字。**决策语义为冻结区。**
- `backend/app/analysis/hand_review.py` 以固定 seed 调用 `equity()`，其中「容忍度随跟注占比放大」的系数注释已明确写着「注越大，对手范围越强，vs 随机胜率越偏乐观」——即**既有实现已知范围缺失，并用系数粗略补偿**。本模块不改变该补偿。
- `backend/app/analysis/reference_identity.py` 是参考/评估的**唯一事实源**：`REFERENCE_COVERAGE = "vs-random"`，并冻结了升版规则（`docs/37` §3.1）。本轮**零改动**。

### 3.2 后端不存在的能力（本轮要补的缺口）

经只读 grep 核验：后端**不存在**任何对手范围模型、起手牌类（169 / 1326）排序或组合权重原语；`lookup_budget.percentile_ms` 是**延迟**统计，与本项无关。`hand_review.py` 只以**注释**说明「注越大范围越强」，没有任何数据结构承载该假设。

### 3.3 必然落差（必须如实写明）

1. 候选 A 的 probe 与既有启发式**都是 vs 随机范围**（`docs/21` §4.2、`docs/35` §4.2）。本轮交付的是**基于公开行动线的范围假设契约与模型**，它**不**是求解器输出，**不**来自 CFR 训练，也**不**声称接近均衡。
2. 本轮的权重是**显式声明的人为假设**（「按冻结顺序取前 N 个起手牌类」），**不是**牌力排序、不是 GTO 范围、不是 exploitability 意义上的最优范围。文档与代码都必须如此表述。
3. 范围假设**不随公共牌收窄**：本模块的唯一输入是 P1-1 的位置投影，**不接收** `board`，因此翻后仍沿用同一份起手牌类权重。这是一条**被声明的局限**，不是被忽略的细节。
4. 本轮**不实现**采样、胜率、share 或 EV。把权重变成实际的组合概率、并据此计算行动价值，属 P1-3 及其后续单独授权的工作。
5. 因此：**不得**把本轮交付表述为「已替代 vs 随机」「已实现范围化 EV」「已支持 CFR」或「已覆盖真实局面」。

## 4. P1-2 规格（冻结）

### 4.1 起手牌类顺序 `HAND_CLASS_ORDER`（冻结）

`HAND_CLASS_ORDER` 是长度恰为 **169** 的元组，由**显式本地规则**生成，不以字面量硬编码：

1. 先列 13 个**对子**，按 rank 降序：`AA, KK, QQ, …, 22`；
2. 再列**非对子**：按高牌 rank 降序；同一高牌下按低牌 rank 降序；每个 `(高, 低)` 组合**同花先于非同花**，形如 `AKs, AKo, AQs, AQo, …, 32o`。

**必须如实声明的性质**（同时写进代码与文档）：

- 该顺序是**本模块的显式约定**，用于把「档位」换算成**确定的起手牌类集合**，使假设**可审计、可复现**；
- 它**不是**牌力排序，**不是**组合数排序，**不来自**求解器或任何外部来源；
- 它不构成任何质量结论，也不得被表述为「正确范围」或「GTO 范围」。

### 4.2 对手角色 `RANGE_ROLES`（冻结，闭集）

角色由 P1-1 投影的公开动作线**唯一派生**，取值恰为下列五个：

| 角色 | 派生条件（依据 `public_action_line` 的**最后一段**） |
|---|---|
| `aggressor` | 该座位最近一次自愿动作是下注（`b`）或加注（`r`） |
| `caller` | 该座位最近一次自愿动作是跟注（`c`） |
| `blind` | 该座位在最后一段中有盲注 token（`sb` / `bb`），且**没有**任何自愿动作 |
| `unacted` | 其余情形：本段无自愿动作且非盲注座位，或最近一次自愿动作是过牌（`x`） |
| `folded` | 该座位在**任一街**出现过弃牌 token（`f`） |

口径澄清：

- **弃牌是跨街持久的**：一旦在任一街弃牌，后续角色恒为 `folded`；
- **过牌不提供收紧信息**，因此最近一次动作是 `x` 的座位归入 `unacted`，不单独设角色；
- 行动者自己（`relative_actor`）**不被赋予范围**（他不与自己竞争），但仍占据一个相对座位。

### 4.3 受控 profile `RangeProfile`（冻结）

`RangeProfile` 是**冻结的 Pydantic model**，字段恰好为下列九项：

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `profile_identifier` | `str` | 形如 `name@version` 的受控标识 |
| 2 | `source` | `str` | 来源标注（恒为「声明的模型假设」这一类常量，不得为空） |
| 3 | `basis` | `str` | 依据声明：说明档位与排序的来源与性质 |
| 4 | `aggressor_class_count` | `int` | `aggressor` 取前多少**个起手牌类** |
| 5 | `caller_class_count` | `int` | 同上，`caller` |
| 6 | `blind_class_count` | `int` | 同上，`blind` |
| 7 | `unacted_class_count` | `int` | 同上，`unacted` |
| 8 | `folded_class_count` | `int` | 同上，`folded`（恒为 `0`，见 §4.6） |
| 9 | `max_aggressive_actions_per_street` | `int` | 该 profile 建模的**单街主动下注/加注次数上限** |

约束：

1. 每个 `*_class_count` 必须落在 `0..169`；`folded_class_count` **必须为 `0`**；
2. profile 登记在**受控目录**中，形如 `profile_identifier -> RangeProfile`；目录是**只读**的，新增 profile 属于契约变更（需同步文档与测试）；
3. profile 的字段集即契约，`extra="forbid"` 拒绝未登记字段。

内置目录至少登记一个 profile：`action-line-roles@1`（来源＝声明的模型假设；档位取值见 §4.4）。

### 4.4 内置 profile 的档位取值（显式声明）

`action-line-roles@1` 的档位如下（**显式常数**，不是从任何数据拟合出来的）：

| 角色 | `*_class_count` | 含义（声明口径） |
|---|---:|---|
| `aggressor` | `40` | 主动下注/加注者被假设为更紧更集中 |
| `caller` | `80` | 跟注者被假设为中等宽 |
| `blind` | `110` | 仅投盲注、被动投入者被假设为较宽 |
| `unacted` | `130` | 尚未行动或仅过牌者被假设为最宽 |
| `folded` | `0` | 已弃牌者不持有可争池范围 |

`max_aggressive_actions_per_street = 1`：该 profile **只建模单街一次主动下注/加注**；某街出现**第二次**主动下注/加注即判**超出建模范围**，明确失败（§4.6），**不**取最近档、**不**插值。

**档位是假设，不是测量**：上述四个数字**没有**任何数据或求解器来源，仅是为使假设可复现而显式冻结的取值；文档与代码都必须如此表述。

### 4.5 范围假设 `RangeAssumption` 与 `OpponentRange`（冻结）

`OpponentRange` 是**冻结的 Pydantic model**，字段恰好五项：

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `relative_seat` | `int` | 对手的**相对座位**（相对按钮；不是绝对 seat） |
| 2 | `role` | `str` | §4.2 的五个角色之一 |
| 3 | `contests_pot` | `bool` | 该对手是否仍可能争池（`folded` 恒为 `False`） |
| 4 | `class_count` | `int` | 生效的起手牌类档位 |
| 5 | `weights` | `tuple[float, ...]` | **恰好 169 项**的显式权重，按 `HAND_CLASS_ORDER` 对齐；取值 `1.0`（在该假设内）或 `0.0`（不在） |

`RangeAssumption` 是**冻结的 Pydantic model**，字段恰好八项：

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `schema_version` | `str` | 本契约的结构版本（当前唯一受支持值 `range-assumption.v1`） |
| 2 | `profile_identifier` | `str` | 生效的受控 profile 标识 |
| 3 | `source` | `str` | 来源标注（与 profile 一致） |
| 4 | `player_count` | `int` | `N`（2–9，透传自投影） |
| 5 | `street` | `str` | 透传自投影的当前街 |
| 6 | `relative_actor` | `int` | 透传自投影的行动者相对座位（**不**赋予范围） |
| 7 | `opponents` | `tuple[OpponentRange, ...]` | 对其余 `N − 1` 个相对座位各一项，按相对座位升序 |
| 8 | `limitations` | `tuple[str, ...]` | 局限声明（含「不随公共牌收窄」与「非求解器输出」） |

约束：

1. `opponents` **恰好**覆盖除 `relative_actor` 外的全部相对座位，**每座一项、不重不漏**；
2. `RangeAssumption` 与 `OpponentRange` **不得**包含：公共牌、底池金额、筹码、真实底牌、绝对 seat、运行中 seed、对手内部参数、未来行动或结算结果；
3. **权重不是概率**：`weights` 是起手牌类的**包含指示**；把它组合成具体组合概率需要组合数步骤，该步骤**不在本轮范围**（留给 P1-3 及其后续）。
4. **全零不是补零近似**：`folded` 角色的 `weights` 全为 `0.0`，是「该对手已弃牌、不参与竞争」的**显式事实声明**，不是用零值冒充未知范围。

### 4.6 构造入口与明确失败语义（冻结）

入口（均为纯函数）：

| 入口 | 输入 | 输出 |
|---|---|---|
| `build_range_assumption(*, projection, profile_identifier=DEFAULT_RANGE_PROFILE_IDENTIFIER)` | P1-1 的 `PositionProjection` + 受控 profile 标识 | `RangeAssumption` |
| `assign_opponent_roles(projection)` | P1-1 的 `PositionProjection` | `relative_seat -> role` 的有序元组 |
| `weights_for_class_count(class_count)` | 档位 | 169 项权重元组 |
| `profile_for(identifier)` | 标识 | `RangeProfile` |
| `known_profile_identifiers()` | — | 已登记标识的升序元组 |

失败的**分类型**异常（三者互不继承，与 P0-3 的「四值独立」口径一致）：

| 异常 | 含义 | 触发条件 |
|---|---|---|
| `RangeContractError` | **契约违规**（结构性非法输入） | `projection` 不是 `PositionProjection`；`player_count < 2`；档位越界（非 `0..169`）；`folded_class_count != 0`；`schema_version` 非法 |
| `UnknownRangeProfileError` | **标识未知或版本不受支持** | `profile_identifier` 不在受控目录内（含未知版本与历史版本） |
| `OutOfProfileError` | **超出该 profile 的建模范围** | 某街主动下注/加注次数超过 `max_aggressive_actions_per_street`；或动作线中出现词表外的 token 形式 |

**禁止静默回退**：任何未知、缺失或超出建模范围的输入都不得被当作「已假设」处理，也不得回落到默认档位、最近档、补零或插值后仍声称构造成功。

### 4.7 信息边界与不读对手暗牌 / 未来牌

1. 唯一输入是 P1-1 的 `PositionProjection`，其字段集已在 `docs/42` §4.1 冻结为**不含**暗牌、公共牌、筹码与随机源；
2. 本模块**不接收** `board` / `pot` / `stack` / 任何 `hole_cards` 参数，因此**在结构上**无法读取对手暗牌、无法读取未来公共牌、也无法随公共牌收窄；
3. 本模块**不 import** `app.poker.equity`、`app.poker.engine`、`app.analysis.*`、`app.storage.*`；对 P0-5 当前生产口径的**对照**只以**声明常量**形式存在，并由**一条测试**锁定其与 `reference_identity.REFERENCE_COVERAGE` 不漂移（生产代码不依赖该模块，避免 `strategy → analysis` 反向依赖）。

### 4.8 P1-2 验收口径

对照 `docs/35` §4.2 P1-2 原文口径（基于公开行动线的范围假设模型，明确其是模型推断而非读取真实牌；验收：不得读取对手暗牌/未来牌；范围假设与参考来源一起版本化）：

| # | 验收项 | 判据 |
|---|---|---|
| C1 | 基于**公开行动线** | 角色只由 `PositionProjection.public_action_line` 派生；同行动线必得同角色 |
| C2 | 明确是**模型推断** | `RangeAssumption.source` 为声明的假设来源；`limitations` 含「非求解器输出」与「不随公共牌收窄」；模型拒绝把 `source` 置为求解器/训练产物口径 |
| C3 | 不读取对手暗牌 | `build_range_assumption` 只接受 `PositionProjection`；字段集中不存在 `hole_cards`；替换对手暗牌与公共牌后结果不变 |
| C4 | 不读取未来牌 | 模块不接受 `board`；字段集中不存在 `board` / `runout` / 未来动作 |
| C5 | 与参考来源**一起版本化** | `profile_identifier`（`name@version`）+ `schema_version` + `source` 三者齐备；未登记标识明确失败 |
| C6 | 角色派生正确 | 五个角色按 §4.2 逐条锁定；弃牌跨街持久；过牌归 `unacted`；行动者自身不被赋范围 |
| C7 | 起手牌类顺序确定 | `HAND_CLASS_ORDER` 长度恰好 169、元素唯一、`AA` 居首、`32o` 居末 |
| C8 | 权重与档位一致 | `weights_for_class_count(k)` 的前 `k` 项为 `1.0`、其余为 `0.0`；长度恒为 169 |
| C9 | 不完整 / 超出建模范围**明确失败** | 第二次单街主动下注/加注 → `OutOfProfileError`；未登记 profile → `UnknownRangeProfileError`；类型错误与档位越界 → `RangeContractError`；三者类型互不继承 |
| C10 | 不接入任何生产路径 | 模块无生产调用方；不 import `heuristic` / `equity` / `analysis` / `storage`；`reference_identity.py` 零改动；对外响应与缓存键不变 |
| C11 | 2–9 人参数化 | `N = 2..9` 逐人数构造成功；`opponents` 恒为 `N − 1` 项 |
| C12 | 不写回历史 | 模块不持有引擎引用、不写任何存储；结果为纯值对象，输入不被改写 |

## 5. 版本影响与兼容性（预期）

| 对象 | 影响 |
|---|---|
| 既有策略语义 | **零改动**：`heuristic.py` 的阈值、分支与 `equity()` 调用完全不变 |
| 复盘与参考身份 | **零改动**：`hand_review.py` 与 `reference_identity.py` 不触碰；`REFERENCE_VERSION` / `EVALUATION_VERSION` / `REFERENCE_COVERAGE` 取值不变 |
| API 与前端 | **零改动**：不新增或改名字段；缓存键不变 |
| 数据库 | **不加列、不迁移**；真实数据库只读 |
| 引擎 / 结算 | 零改动；`equity` / `estimate_static_showdown_share` / `pot_projection` / `_settle_showdown` 语义不变 |
| 锁文件 | 零改动（不新增依赖） |
| 新模块 | 新增独立模块与导出；**目前无生产调用方**，不改变任何运行时路径 |
| 超范围局面的实际处置 | **不产生假设、不产生动作**；抛分类型明确异常；无最近档、无默认档、无插值 |

## 6. 边界声明与不得声称

- 本轮改动是**契约与假设模型层**，**不是** CFR 接入，也**不构成任何质量证据**。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- **不得**把范围假设表述为「正确范围」「GTO 范围」「已替代 vs 随机」「已实现范围化 EV」或「已覆盖真实局面」；它只是一份**显式声明的人为假设**。
- **不得**用「最近档」「补零」「掩码」「线性插值」把未覆盖局面**冒充**为已假设；本轮在结构上不提供这类路径。
- 现有 `equity()` 固定 `ties/2` 的边界（`docs/23` §2.1）**不变**；`docs/23` §7「不把新 share 静默塞入既有字段、不把资格投影说成收益」继续有效。
- 与候选 A 受限抽象的落差（`docs/40` §3.3）继续有效；本轮不涉及抽象映射或覆盖判定。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 本轮不追加 seed、不新建冻结 campaign、不重试任何已消耗 authorization、不上云、不转 GPU、不扩预算。
- 不得修改 `backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/storage/models.py`、真实数据库 `backend/data/holdem.db`、锁文件、`tools/trainer/**`、`docs/20` 至 `docs/42a`。

## 7. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码/测试/前端/锁文件/真实数据库；未实施 P1-2 的实现；未实施清单其余任何一项；未改质量门槛或启用 `docs/39` 门槛；未新增受监督运行或 campaign；未追加 seed；未重试 authorization；未 push。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P1-2，并在实施回执（`docs/43a`）中给出文件级改动、新增/修改测试与 `ruff` / `pytest` / `npm run build` 的实跑输出。** 若用户对 §1.3 的任一项裁定有不同意见，应在实施前先修订本文件并记录原因。

P1-2 完成之后的下一个清单项是 **P1-3（逐池货币收益：短码 / 边池 / 多人平局）**；按 `docs/35` §4.3 的依赖它紧随 P1-2，须**单独授权**，并注意它与 `equity()` 固定 `ties/2`、`project_pot_layers()` / `project_candidate_call()` 的资格投影、以及 `docs/23` §3.2 的跨层货币收益定义相互耦合——**不得**把资格投影或静态 share 表述为逐池 EV。
