# 41 M8：P0-2 实时 lookup 性能与内存预算（规格冻结）

> 日期：2026-09-18。
>
> 本文件接在 `docs/40` / `docs/40a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/41` 记录本轮**规格与决策冻结**，`docs/41a` 记录与之对应的**实施与测量回执**。`docs/20` 至 `docs/40a` 未被改写。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P0-2** 一项的规格冻结、四个设计岔路的裁定，以及**对 `docs/40` 已冻结契约的一处最小修订**（见 §4，修订原因与影响如实记录）。
>
> 本文件**不产生任何策略或质量证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作、**未启动任何受监督训练运行**。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项）

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P0-2 | 实时 lookup 性能与内存预算 | **是** |
| P0-1 / P0-3 / P0-4 / P0-5 / P0-6 / P0-7 | 注册表、抽象与回退、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**复用**；其中 P0-3 的契约有一处最小修订，见 §4） |
| P1-1 … P1-5 | 位置与公开行动历史投影、范围模型、逐池 EV、真实尺度、**性能复测** | 否（P1-5 与 P0-2 共享口径但**不属**本轮） |
| P2-1 … P2-4 | 2–9 人产品验收、N=9 结论、历史 `pot_results`、稳定性生产者 | 否 |

### 1.2 用户答复原文（四个设计岔路）

本轮采用「**先问用户**」。答复原文照录：

| 岔路 | 用户答复原文 |
|---|---|
| 一 交付范围 | 「完整交付并实测真实产物」(后端新增安全产物加载器 + lookup；用既有 N=6/N=7 产物真实实测冷加载、常驻内存、查询延迟分布；无产物人数如实报告并走声明式回退。) |
| 二 测量输入 | 「允许只读外部产物」(允许只读 `/Users/bryanylliu/holdem-campaigns/` 下既有 `strategy.json` 作为测量输入；路径由参数传入、不硬编码；不回写、不移动、不新增 authorization；不修改 `tools/trainer/**`。) |
| 三 代码落点 | 「生产层 + 显式测量入口」(加载器与 lookup 放 `backend/app/strategy/`（公开 API 用 Pydantic、可被将来 runtime 复用）；测量以显式 opt-in 入口提供，不进默认测试路径；单元测试用小样本。) |
| 四 未覆盖人数 | 「如实报告并声明回退」(逐人数报告：6/7 给实测值；2/3/4/5/8/9 明确标「无产物，未测」，并复用上轮 `declared_fallback` 标注回退来源；严格执行：不用插值、不用最近人数、不用最近桶冒充。) |

据此**被授权**：`backend/app/strategy/` 新增产物加载与查表模块、`backend/tests/` 新增测试、新增 `docs/41*`、**只读**引用工作区外既有产物作为测量输入、**最小必要**的 `backend/app/api/` 改动。
**被拒绝**：修改 `tools/trainer/**`；新增受监督运行或 campaign；追加 seed；重试 authorization；跨人数插值；任何「最近桶」近似；上云 / 转 GPU / 扩预算；恢复前端策略选择器。

### 1.3 本轮统一维持的纪律

1. 本轮测量是**只读的本机性能观测**，**不是**受监督训练运行：不消耗 authorization、不新增 campaign、不写回任何既有工件；
2. 结论一律标注为**本机单机型观测**，**不外推**云环境或生产容量；
3. `tools/trainer/**` 保持**只读**：仅引用其产物格式与字段语义，**不 import**、不执行其代码；数值上界（如产物大小上限）在本轮以**后端本地常量**重申；
4. 本轮**不**触碰 `backend/app/poker/**`（含结算与 equity）、`backend/app/analysis/**`、`backend/app/storage/**`、锁文件、真实数据库与前端。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 10]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -3 --oneline
d6fa89c feat: add controlled abstraction projection coverage verdict and fallback declaration
09b803c docs: freeze p0-3 abstraction mapping coverage and fallback contract specs
8c6ca64 feat: add read-only multi-seed quality gate verdict without enabling a threshold

$ git rev-parse HEAD          -> d6fa89ceaa74af664dce8b26dde60bcf88006b1c
$ git rev-parse origin/master -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
```

与期望基线完全相符；未做任何 `reset` / `clean` / `stash` / `checkout` / `push`。

## 3. 既有产物事实（只读实测）

### 3.1 可测产物清单

```text
$ find /Users/bryanylliu/holdem-campaigns -name strategy.json -exec ls -l {} \;
```

| 人数 | 份数 | 字节数 | 所在 campaign / run |
|---|---:|---|---|
| N=6 | 5 | 401,445 / 401,513 / 401,598 / 401,604 / 401,604 | campaign-7（`a6-seed-1215-i1000`、`a6-seed-20260918-i1000`、`a6-seed-3311-i1000`、`a6-seed-6922-r3`）、campaign-2（`a6-seed-6922-r2`） |
| N=7 | 6 | 1,142,938 / 1,142,972 / 1,142,972 / 1,143,244 / 1,143,373 / 1,145,054 | campaign-6（4 份）、campaign-2（`a7-seed-7926-r2`）、campaign-5（`a7-seed-7926-i1000-r3`） |
| N=9 | **0** | — | 仅 `m8-a-n9-boundary` 的 `measurement.json`，**无**策略产物 |

**结论（本轮必须如实保留）**：产品声称统一支持 2–9 人，但既有策略产物**只有 6 与 7 两个人数**；**2/3/4/5/8/9 均无产物**。`m8-a-campaign-3` / `campaign-4` 的 `artifacts/` 目录只有 `measurement.json`（无 `strategy.json`）。

### 3.2 产物字段（只读实测）

```text
顶层键（恰好 8）：artifact_type / game / infosets / probability_units /
                  quality / resources / schema_version / training
artifact_type      = "multiplayer-cfr-average-strategy"
schema_version     = 1
probability_units  = 1000000000000
infosets           = 列表；N=6 有 1152 条，N=7 有 3136 条
单条 infoset 键（恰好 7）：actions / actor / history / key / legal_actions / public_state / rank
game 键（恰好 10）：action_tree_version / ante / bet / deck{copies_per_rank, rank_count} /
                    id / player_count / remainder_priority / seat_semantics / tie_rule / version
game.version       = "m8-a-v1"；game.id = "m8-unique-rank-single-open"
resources.artifact_bytes = 该文件的真实字节数
```

`key` 与 `docs/40` §4.2 的抽象键**逐字一致**（实测 `m8/m8-a-v1/n=6/actor=0/rank=0/history=-`），因此「P0-3 抽象键 → 产物查表」的对照关系已就位，无需任何键转换。

### 3.3 既有预算口径（只读引用，不新设）

| 口径 | 取值 | 说明 |
|---|---|---|
| 单次决策硬预算 | `< 100ms`（`≥100ms` 为**失败**，不放宽） | 实时 Bot 决策预算，**不是**整手复盘预算 |
| 建议余量 | `p95 < 50ms`、`p99 < 80ms` | 建议值，非门槛 |
| 决策样本量 | 建议总计至少 `10000` 次 | 逐人数分别报告，不把合并均值当各人数通过 |
| 逐人数输出 | 中位数 / p95 / p99 / max / 超时数 | 覆盖 2–9，重点 6/7/9 |
| 产物 | 预加载；测**冷加载**与内存 | — |
| 平台 idle 内存 | 数百 MB 量级 | 作**对照上界**引用，本轮不新设门槛 |

## 4. 对 `docs/40` 已冻结契约的一处最小修订（如实记录）

### 4.1 修订内容

`docs/40` §4.5 把回退声明的触发值域冻结为「覆盖取值三选一」（`out-of-abstraction` / `incomplete-infoset` / `version-mismatch`）。实现 P0-2 时确认该值域**不足以表达产物层触发**：

| 新增触发值 | 含义 | 为什么不能合并进既有三值 |
|---|---|---|
| `artifact-unavailable` | 该人数**没有**已加载产物 | 例如 N=9 落在抽象博弈的合法人数内（P0-3 判 `in-abstraction`），却**从未有产物**；记为「抽象外」是错误陈述 |
| `artifact-mismatch` | 产物与请求的版本或人数不一致 | 输入本身合法，问题出在加载的产物 |
| `key-not-in-artifact` | 抽象内但产物**未收录**该键 | 产物不完整或与抽象不一致，属产物缺陷，不是局面问题 |

### 4.2 修订方式与影响

1. **只扩展值域、不改既有取值语义**：在 `backend/app/strategy/abstraction.py` 中新增闭类型 `FallbackTrigger`，其成员为既有三值 **加上**上述三值；`FallbackDeclaration.triggering_coverage` 的类型由 `CoverageStatus` 放宽为 `FallbackTrigger`；
2. **既有取值与行为不变**：`out-of-abstraction` / `incomplete-infoset` / `version-mismatch` 的语义、`declared_fallback` 的名字与行为、`is_exact_solution` 恒 `False`、来源必须在受控注册表内——全部不变；
3. **`in-abstraction` 仍不是合法触发值**：`FallbackTrigger` 不包含它，且既有的「抽象内不得声明回退」校验继续保留；
4. **`CoverageStatus` 本身不变**：P0-3 的覆盖判定四值语义**零改动**；本修订只影响回退声明的触发标注。

修订理由按 `docs/35` §4.1 第 5 条执行：结论被后续实施证据修正，**记录原因，不静默修改**；`docs/40` 原文**不改写**，修订事实记录于本文件与 `docs/41a`。

### 4.3 一处必须同时澄清的口径（不属修订，属澄清）

`docs/40` 的 `in-abstraction` 表示「落在**抽象博弈**的合法空间内」，**不**表示「存在已训练产物」。P0-2 引入产物层状态正是为了把这两件事分开：**抽象内 ≠ 有产物**。任何把 N=9 的 `in-abstraction` 读成「N=9 已有可用策略」的说法都是错误的。

## 5. P0-2 规格（冻结）

### 5.1 受控产物加载器

新增 `backend/app/strategy/artifact.py`，作为**唯一**的产物读取入口。加载必须完成下列校验，任一项不通过即抛**明确异常**（不修补、不跳过、不部分接受）：

| # | 校验 | 要求 |
|---|---|---|
| L1 | 文件安全 | 通过非链接描述符打开；必须是**非链接普通文件**；超过**大小上限**即失败 |
| L2 | 编码与 JSON | 必须是 UTF-8；必须是有效 JSON；**拒绝重复键**；**拒绝非有限数值**（NaN/Infinity）；顶层必须是对象 |
| L3 | 顶层字段 | 键集**恰好**为 §3.2 的 8 个；`artifact_type` 必须等于 `multiplayer-cfr-average-strategy`；`schema_version` 必须为 `1` |
| L4 | game | 键集**恰好**为 §3.2 的 10 个；`deck` 键集恰好 2 个；`player_count` 必须在抽象合法人数内；`version` 必须是抽象受支持版本；`deck.rank_count` 必须等于 `player_count`；`copies_per_rank` 必须为 `1` |
| L5 | probability_units | 必须是**正整数** |
| L6 | infosets | 必须是列表；条数必须与 `quality.coverage.total_infosets`、`resources.infoset_count` 三者**一致**；条数必须为正 |
| L7 | 单条 infoset | 键集**恰好**为 7 个；`actor` / `rank` 必须落在该人数范围内；`legal_actions` 必须恰好是抽象规则的两个合法动作；`actions` 的键集必须**恰好**等于 `legal_actions` |
| L8 | 概率单位 | 每个动作的整数单位必须**非负**；单条内动作单位之和必须**恰好**等于 `probability_units` |
| L9 | 键一致性 | **重新计算**规范键：`key` 必须逐字等于由 `(version, N, actor, rank, history)` 生成的抽象键；`history` 必须是该抽象的规范公开决策历史；`history` 派生的行动者必须等于 `actor` |
| L10 | 键唯一性 | 全部 `key` 不得重复 |
| L11 | 禁止项 | 不 pickle、不导入模块路径、不执行产物内任何内容、**未知键不回退**、未知/缺失字段一律失败 |

产物读取**只读**：加载不写回、不移动、不修改任何工件。

### 5.2 查表语义与状态取值

查表输入为 `docs/40` §4.1 的受控抽象投影五项。查表输出为**冻结的 Pydantic 结果对象**，其 `status` 取下列七值之一：

| `status` | 含义 |
|---|---|
| `hit` | 命中共且仅有该键对应的动作整数单位 |
| `out-of-abstraction` | P0-3 判定：抽象外 |
| `incomplete-infoset` | P0-3 判定：信息不完整 |
| `version-mismatch` | P0-3 判定：版本不匹配 |
| `artifact-unavailable` | 该人数**没有**已加载产物 |
| `artifact-mismatch` | 已加载产物的版本或人数与请求不一致 |
| `key-not-in-artifact` | 抽象内但产物未收录该键 |

硬性要求：

1. **只有 `hit` 返回动作分布**；其余六种状态的动作分布字段必须为**空**；
2. **不存在最近桶、默认桶、补零、插值或跨人数折算**：`key-not-in-artifact` 绝不返回邻居键的动作；
3. 非 `hit` 状态一律附带**回退来源声明**（见 §5.4），使回退**可复现、可追溯、可标注**；
4. 查表**不得**读取对手暗牌、未公开公共牌、运行中 seed 或对手内部参数——它只接受五项抽象投影输入；
5. 查表**不得**发起任何网络调用或 LLM 调用（零 LLM 由结构保证，并由测试以「屏蔽 socket 后仍可完成查表」验证）。

### 5.3 预算与测量口径（冻结）

新增 `backend/app/strategy/lookup_budget.py`，只承载**预算常量、测量汇总模型与纯汇总函数**；它不采集数据、不读文件、不联网。

| 常量 | 取值 | 性质 |
|---|---|---|
| 单次决策硬预算 | `100.0 ms` | 硬预算；`≥` 该值为**失败** |
| p95 建议余量 | `50.0 ms` | 建议，非门槛 |
| p99 建议余量 | `80.0 ms` | 建议，非门槛 |
| 建议决策样本量 | `10000` | 建议，非门槛 |
| 平台 idle 内存对照上界 | `512 MiB` | **对照**用，本轮**不新设**门槛 |

测量口径：

1. **冷加载**：在**全新子进程**中加载并校验产物，读取该进程的峰值常驻内存；进程峰值内存按平台口径换算为字节；
2. **常驻内存**：以子进程峰值常驻内存报告，并如实标注其口径（进程峰值，不是「产物独占增量」）；
3. **决策延迟**：在**固定 seed** 下按固定顺序遍历产物的全部信息集键，逐次查表并记录耗时；报告 `中位数 / p95 / p99 / max / 超时数(= ≥100ms) / 样本数`；
4. **逐人数**分别报告，**不**合并成单一均值；`2–9` 逐人数出现，有产物的给实测值，无产物的标「无产物，未测」；
5. 超时数统计的是**查询路径**；由于本轮不接入 runtime，报告**不**声称任何端到端牌局决策预算的结论。

### 5.4 未覆盖人数的处置与回退口径

1. 逐人数报告：**6 与 7** 给实测值；**2/3/4/5/8/9** 明确标注「无产物，未测」，并给出 `artifact-unavailable` 的回退声明；
2. 回退声明的来源复用 `docs/40` §4.5 的口径：必须是受控注册表内的规范标识、来源标注为契约声明、`is_exact_solution` 恒 `False`；
3. **不**用 6/7 的结果插值、折算或外推给其他人数；**不**把「无产物」表述为「已覆盖」；
4. 本轮**不实现**任何回退动作：只产出声明，不改动策略分派路径。

### 5.5 测量入口（opt-in）

1. 测量以**显式 opt-in 入口**提供，**不进**默认测试路径：默认整轮 `pytest` 必须**不**触发任何真实产物加载或长样本计时；
2. 入口需要显式提供产物根目录（**不硬编码路径**）；未提供時**跳过并如实报告跳过**，不得伪称为通过；
3. 单元测试只用**小样本合成产物**（测试内构造，不属既有工件）验证加载严格性、查表语义与汇总数学；
4. 实测输出（含命令、产物身份、逐人数数值）如实记录在 `docs/41a`。

### 5.6 P0-2 验收口径

对照 `docs/35` §4.2 P0-2 原文口径（逐人数报告冷加载、常驻内存、决策中位数/p95/p99/max/超时数；`<100ms`、零 LLM、线上只 lookup；未覆盖场景走明确且可复现的 fallback）：

| # | 验收项 | 判据 |
|---|---|---|
| D1 | 受控加载 | 11 项校验（L1–L11）各自有失败用例；损坏/超限/重复键/非有限数/未知字段/错版本/错人数/非法动作/概率和不匹配全部明确失败 |
| D2 | `hit` 唯一且精确 | 命中返回的动作整数单位与产物逐字相等；单位之和等于 `probability_units` |
| D3 | 无最近桶 | 抽象外、无产物、产物不匹配、产物未收录四类均**不返回**动作分布，且不回退到任何邻居键 |
| D4 | 回退可追溯 | 全部非 `hit` 状态都带触发值、抽象键（如有）与原因；来源标识在受控注册表内；`is_exact_solution` 恒 `False` |
| D5 | 零 LLM / 无网络 | 屏蔽 socket 后查表仍可完成；模块不导入任何 LLM 或网络客户端 |
| D6 | 逐人数如实 | 2–9 逐人数出现；仅 6/7 有实测值；其余标「无产物，未测」并给 `artifact-unavailable` 回退声明 |
| D7 | `<100ms` 口径 | 报告给出逐人数 `max` 与超时数；`max < 100ms` 方可表述为「在本机该样本上未观察到超预算查询」 |
| D8 | 默认测试不受影响 | 默认 `pytest` 不含真实产物加载与长样本计时 |

## 6. 版本影响与兼容性（预期）

| 对象 | 影响 |
|---|---|
| P0-3 覆盖判定 | `CoverageStatus` 四值与语义**零改动**；仅回退声明的触发值域放宽（§4） |
| `FallbackDeclaration` | 字段名与既有取值不变；新增三个**产物层**触发取值 |
| 既有策略语义 / 分派 | **零改动**；不新增运行时回退动作，不改 `registry` / `games.py` / API 行为 |
| 引擎 / 结算 / 分析 / 存储 | 零改动；不加列、不迁移；真实数据库只读 |
| 旧历史 / 旧响应 / 前端 | 结构不变；不改前端；不恢复策略选择器 |
| 既有实验工件 | **只读**；不写回、不移动、不新增 authorization；`/Users/bryanylliu/holdem-campaigns/` 原样保留 |
| 锁文件 | `backend/uv.lock` 与 `frontend/package-lock.json` 零改动（不新增依赖） |
| 抽象外/无产物局面的实际处置 | 不产生动作分布；给出七值之一的显式状态与**声明式**回退来源 |

## 7. 边界声明与不得声称

- 本轮改动是**加载、查表与测量**，**不是** CFR 接入 runtime；`backend/app/strategy/` 仍无任何在线 CFR 决策路径，**没有**任何运行时可用的回退动作。
- 本轮数值是**本机单机型性能观测**，**不构成**质量证据、收敛证据或生产容量结论；**不外推**云环境。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- **不得**把回退路径表述为「已覆盖」「已支持 CFR」或「精确解」。
- **不得**把「6/7 有产物」外推为「2–9 人已覆盖」；产品上限定 9 人的验收仍属 P2-1。
- P0-2 的测量**不**替代 P1-5（修复后 2–9 人性能复测），也**不**为其提供结论。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」；代码中仍**不存在**稳定性生产者。
- 未启动实际运行前，不得伪称已生成策略、质量或资源证据。
- 不得修改 `backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/storage/models.py`、真实数据库、锁文件、`tools/trainer/**`、`docs/20` 至 `docs/40a`。

## 8. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码/测试/前端/锁文件/真实数据库；未实施 P0-2 的实现；未实施清单其余任何一项；未启动任何受监督运行或 campaign；未追加 seed；未重试 authorization；未 push。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P0-2，并在 `docs/41a` 中给出文件级改动、新增测试、`ruff` / `pytest` / `npm run build` 的实跑输出，以及 N=6/N=7 真实产物的冷加载、常驻内存与逐人数决策延迟分布。**

P0-2 完成后，`docs/35` §4.2 的 P0 组已全部完成；建议的下一个清单项为 **P0-6 门槛签收**（当前仍只报告不设门槛）或 **P1-1（位置与公开行动历史投影）**——后者是 P1-2 → P1-3 链路的前置，也是把真实局面真正映射进抽象所必需的一步；两者均需**单独授权**。
