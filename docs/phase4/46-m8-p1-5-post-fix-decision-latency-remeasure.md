# 46 M8：P1-5 修复后 2–9 人实时决策性能复测（规格冻结）

> 日期：2026-09-20。
>
> 本文件接在 `docs/45` / `docs/45a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/46` 记录本轮**规格与决策冻结**，`docs/46a` 记录与之对应的**实施与实测回执**。`docs/20` 至 `docs/45a` 未被改写。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P1-5** 一项的规格冻结与设计岔路裁定。代码、测试与实测回执在随后一次提交中落地。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作、**未启动任何受监督训练运行**。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项）

本轮用户明确授权的实施范围**只有一项**，来自 `docs/35` §4.2 的 P1 组：

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P1-5 | 修复后 6/7（及 2–9）人性能复测 | **是** |
| P0-1 … P0-7 | 注册表、lookup 预算、抽象映射、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**只读复用**其口径） |
| P1-1 | 位置与公开行动历史的信息集投影 | 否（已完成，仅**声明性引用**） |
| P1-2 | 范围模型替代「vs 随机底牌」 | 否（已完成，仅**声明性引用**） |
| P1-3 | 逐池货币收益（短码 / 边池 / 多人平局） | 否（已完成，仅**声明性引用**） |
| P1-4 | 真实 Hold'em 的下注尺度与公共牌 | 否（已完成，仅**声明性引用**） |
| P2-1 … P2-4 | 2–9 人产品验收、N=9 结论、历史 `pot_results`、稳定性生产者 | 否 |

P1-5 **只是** `docs/35` §4 清单中的一项；本文件不改变其余条目的现状、优先级或失效条件，也不构成任何实施授权。P1-5 完成后，`docs/35` §4.2 的 **P1 组全部完成**。

### 1.2 用户答复原文（执行确认与设计岔路）

本轮采用「**先问用户**」而非「先在文档冻结规格」。答复原文照录：

| 岔路 | 用户答复原文 |
|---|---|
| 执行确认与总口径 | 「口径+入口+实跑，写入 46a」(交付可复用口径、独立 opt-in 入口，并实跑本机启发式决策基准；逐人数中位数/p95/p99/max/超时数如实写入 `docs/46a`；「接入 lookup 后成本」如实标注为未建模（因 lookup 未接入 runtime）。) |
| 岔路一：测量入口落点 | 「新增独立 opt-in 入口」(新增 `backend/tests/test_decision_latency_benchmark.py`，仿既有 `test_lookup_benchmark.py` 的 skipif + 环境变量形态；与既有查询路径测量互不影响。) |
| 岔路二：交付范围 | 「口径+入口+实跑，写入 46a」(同第一行；不额外复测既有的查询路径。) |
| 岔路三：覆盖矩阵与样本 | 「基础矩阵+按需叠加」(先做「2–9 人 × 各街」基础矩阵，每人 10000 次决策；再按需叠加深浅筹码 / 强听牌 / 长会话场景。对齐 `docs/20` §6.3 验收面，重点 6/7/9。) |
| 岔路四：「接入 lookup 后的实时成本」如何表述 | 并入第一行答复：**如实标注为未建模**，不另立复测项。(lookup 未接入 runtime，本轮不重复测量既有的查询路径。) |
| 岔路五：越界授权 | 「全部保持只读」(本轮测量只需调用既有启发式与引擎构造局面，无需改动 `poker/**`、`analysis/**`、`api/**`、`frontend/**`；不接入复盘展示、不改对外响应。) |

据此，**被授权**：在 `backend/app/strategy/` 新增测量口径模块（不改既有模块语义）、在 `backend/tests/` 新增回归测试与显式 opt-in 实测入口、新增 `docs/46*`、在**本机**实跑一次启发式决策延迟测量并如实披露耗时。
**被拒绝**（本轮不做）：修改 `tools/trainer/**`（含 `kuhn_cfr/**`、`multiplayer_cfr/**`）；修改 `poker/**`、`analysis/**`、`api/**`、`frontend/**`、`storage/models.py`、锁文件、真实数据库；修改 `lookup_budget.py` 的既有常量取值；改 `heuristic.py` 决策语义、`equity()` 的 `ties/2` 或采样数；接入 CFR/lookup 到 runtime；启用 `docs/39` 门槛；恢复已移除的前端策略选择器；跨人数插值或折算；新增受监督运行或 campaign；追加 seed；重试任何已消耗 authorization；上云、转 GPU、扩预算。

### 1.3 三项裁定（冻结）

| 岔路 | 裁定 |
|---|---|
| 一 | 新增 `backend/app/strategy/decision_latency.py` 作为**纯口径 + 冻结 Pydantic 模型**入口；`lookup_budget.py` 的既有常量、模型与断言**零改动**，只被 import 复用。另有独立 opt-in 入口 `backend/tests/test_decision_latency_benchmark.py` 与共用的局面构造辅助 `backend/tests/decision_latency_states.py`（非 test 文件）。本模块**无生产调用方**，不改变任何运行时路径与对外响应。 |
| 二 | 本轮交付**测量口径 + opt-in 入口 + 一次本机实跑**：逐人数（2–9）中位数/p95/p99/max/超时数写入 `docs/46a`。**不**接入 CFR/lookup 到 runtime，**不**实现任何回退动作，**不**为 2–9 之外的推断提供数值。 |
| 三 | 判据严格沿用既有预算：单次决策 `< 100.0ms` 为通过，`>= 100.0ms` 为**失败**且**不放宽**；`p95 < 50.0ms`、`p99 < 80.0ms` **仅作余量提示**，只报告不判定。覆盖缺失（人数 / 街 / 场景）必须显式声明原因，**不插值、不用 6/7 折算 2–9、不把合并均值当逐人数通过、不用最近桶/补零/掩码**。 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 4]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -6 --oneline
348f470 feat: add controlled real rules boundary contract
6388bba docs: freeze p1-4 real rules boundary contract specs
edcc224 feat: add controlled per-pot monetary payoff contract
01dcb29 docs: freeze p1-3 per-pot monetary payoff contract specs
f9e957b feat: add controlled action-line range assumption contract
3ea9140 docs: freeze p1-2 action-line range assumption contract specs

$ git rev-parse HEAD          -> 348f4709f7b95f6e8ac71848b215cdee29e46bfa
$ git rev-parse origin/master -> f9e957bf9f9a1df89bb92957c01e031d5d48723d

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
$ find /Users/bryanylliu/holdem-campaigns -name strategy.json | wc -l
11

$ cd backend && uv run pytest -q
599 passed, 1 skipped, 2 warnings in 11.25s
```

`ahead 4` 即 P1-1…P1-4 的四个实现提交与四个规格冻结提交中的**本地**部分，本轮不改变该状态、**不 push**；工作区 0 行。未做任何 `reset` / `clean` / `stash` / `checkout`。

本轮**不需要**读取任何既有实验工件：测量对象是启发式的本地构造局面，与 N=6/N=7 产物无关（故 11 份 `strategy.json` 在本轮未被打开）。

## 3. P1-5 现状锚点（只读核验，不照抄）

### 3.1 权威依据与原文口径

`docs/35` §4.2 P1-5 行：

> 现状：`docs/21` 方案 B 修复后**未复测**逐人数决策延迟，既有性能样本未被外推为新结果（`docs/21` §4.2、§6.4）。缺口：修复后与将来接入 lookup 后的实时成本未知。需要产出：逐人数中位数/p95/p99/max/超时数。验收：`<100ms`；≥100ms 为失败且不放宽原硬预算。

依据列为 `docs/20` §6.3 与 `docs/21` §4.2 / §6.4。

### 3.2 验收面（`docs/20` §6.3，逐条对齐）

| 口径 | 原文要求 | 本轮处置 |
|---|---|---|
| 硬预算 | 维持 Bot 每次决策 `<100ms`、零 LLM 调用 | 唯一性能判据；超时按 `>= 100.0ms` 计 |
| 覆盖 | 2–9 人、各街、深浅筹码、强听牌路径与长会话，重点 6/7/9 | 基础矩阵覆盖 `2–9 × 各街`；四个场景层在 6/7/9 上叠加，其余人数**显式声明未覆盖** |
| 样本量 | 建议总计至少 10000 次决策且**逐人数**报告中位数/p95/p99/max/超时数 | 每个**人数** `10000` 次（总计 80000 次），逐人数分别报告 |
| 不合并 | 不把合并均值当各人数通过 | 报告字段集**不含任何均值/合计**字段（§4.4） |
| 余量 | 建议 p95 `<50ms`、p99 `<80ms` 留余量 | 只报告布尔值，**不**作通过判据 |
| 失败处置 | ≥100ms 为失败，调查调度噪声后复测，**不放宽原硬预算** | 出现即如实记为失败，不放宽、不改判据 |
| 有限性 | 有限测试不能证明所有未来调用都不会超时 | §7 强制声明 |
| 预算归属 | 离线训练/评估可以慢，不能搬到实时调用 | 本轮不接入任何在线求解 |

### 3.3 旧样本与「未复测」声明（**不得外推**）

- `docs/20` §2.8 的旧样本（最近会话翻前 / 翻后 1–4 对手，中位数 0.002–13.865 ms、p95 0.005–14.485 ms）是**方案 B 之前**、且只覆盖**单个四对手牌面**的观测，`docs/20` 已声明「§2 的四对手耗时不外推」「尚未验证新方案、长会话、冷启动或云服务器」。
- `docs/21` §4.2 结尾与 §6.4 结尾均声明：方案 B 修复后**未**复测逐人数决策延迟；§4.2 另写明「候选 B 也会使每个受影响节点多抽样一个或数个随机对手，实时开销可能上升」。
- 因此本轮**必须重新测量**，且**不得**把 §2.8 的旧数字表述为修复后结果，也**不得**把 6/7 的结果外推给 2–9。

### 3.4 与 P0-2 的职责边界（最可能的混淆点）

| 项 | P0-2（已完成） | P1-5（本轮） |
|---|---|---|
| 测量对象 | 受控产物**冷加载** + 「抽象投影校验 + 定长键查表」查询路径 | **启发式单次决策**（含翻前 Chen 分档与翻后 `equity()` 蒙特卡洛） |
| 人数覆盖 | 只有 6 与 7 有产物；2/3/4/5/8/9 无产物、未测 | 2–9 **全部**可测（启发式不依赖产物） |
| 路径标识 | 查询路径 | `heuristic-action-distribution`，与查询路径**显式区分** |
| 是否端到端 | **不是**端到端决策 | **是**启发式的端到端单次决策，但**不含** CFR/lookup（未接入 runtime） |

`docs/41a` §5.3 第 3 条已写明：P0-2 的观测「**不**替代 P1-5（修复后 2–9 人性能复测）」。本轮必须继续遵守：**不得**把 P0-2 的查询路径数字（`max≈0.0818–0.1355 ms`）表述为端到端 Bot 决策延迟。

## 4. P1-5 规格（冻结）

### 4.1 测量对象与被计时路径

1. 计时对象是 `HeuristicStrategy.action_distribution(state, legal)` 的**单次调用**，即线上 Bot 在某一合法决策点上的一次完整决策计算（翻前走 Chen 分档；翻后走 `equity()` 蒙特卡洛，采样数沿用策略默认值）。
2. 计时窗口由 `time.perf_counter()` 紧包该调用；**不含**局面构造、**不含** `BOT_DELAY`、**不含** HTTP / 数据库 / JSON 序列化 / 座位渲染。
3. 报告必须显式给出被计时路径标识 `measured_path = "heuristic-action-distribution"`，以及 lookup 的接入状态字段（§4.4）；两者共同防止把本轮数字误读为「含 lookup 的端到端决策」。
4. 随机性可注入且可复现：局面构造使用固定构造种子，策略实例使用固定种子；报告**不外发**任何 seed（§4.4 白名单）。
5. **零 LLM**：测量路径不调用任何模型或网络客户端（策略本身即为纯本地计算）。

### 4.2 口径复用（不另造一套）

| 复用项 | 来源 | 本轮是否改动 |
|---|---|---|
| `DECISION_BUDGET_MS = 100.0` | `lookup_budget.py` | **零改动**（只 import） |
| `P95_GUIDANCE_MS = 50.0` / `P99_GUIDANCE_MS = 80.0` | 同上 | 零改动 |
| `RECOMMENDED_DECISION_SAMPLES = 10_000` | 同上 | 零改动 |
| `PLAYER_COUNT_RANGE = (2..9)` | 同上 | 零改动 |
| `MEASUREMENT_SCOPE = "local-machine-single-host-observation"` | 同上 | 零改动 |
| `percentile_ms`（最近秩法） | 同上 | 零改动 |
| `summarize_decision_latencies` → `DecisionLatencySummary`（逐人数判定单元，含 `>= DECISION_BUDGET_MS` 超时计数） | 同上 | 零改动 |

新增模块 `decision_latency.py` 只做三件事，**不重定义**任何预算或分位：

1. **测量路径与 lookup 接入状态的显式声明**：`MEASURED_DECISION_PATH`、`LOOKUP_RUNTIME_INTEGRATION_STATUS = "not-integrated-unmodeled"`、说明文本；
2. **逐街（分组）明细**：`LatencyGroupSummary` 与 `summarize_latency_group`，其超时判据与分位法与 `lookup_budget` **逐字一致**（同一常量、同一函数），并由测试锁定一致性；
3. **逐场景补充层与未覆盖声明的装配校验**：模型与 `build_decision_latency_report`。

**扩展方式与边界**：`lookup_budget.py` 的既有模型、常量取值与既有断言**零改动**；逐街/逐场景所需的新字段**只**存在于新模块，且不改变 P0-2 的逐人数判定语义（同一 `DecisionLatencySummary`、同一分位法、同一超时判据）。

### 4.3 覆盖矩阵与样本分配

**基础矩阵（唯一判定依据）**

| 维度 | 取值 |
|---|---|
| 人数 | `2, 3, 4, 5, 6, 7, 8, 9`（全部真实构造，不写死两人） |
| 街 | `preflop / flop / turn / river` |
| 每（人数, 街）单元 | `4` 个确定性构造的局面变体轮转，覆盖不同牌力分支 |
| 每个**人数**的样本量 | `RECOMMENDED_DECISION_SAMPLES = 10000`，按街均分（`10000/4 = 2500`；非整除时余数自翻前起逐街 `+1`，保证总数恰为设定值） |
| 盲注 / 起始筹码 | `5 / 10` / `1000` |
| 总计 | `8 × 10000 = 80000` 次决策 |

逐人数的中位数 / p95 / p99 / max / 超时数由该人数的**全部 4 街样本合并**给出（`summarize_decision_latencies`）；逐街分位同时作为**覆盖证据**报告。

**补充场景层（补充证据，不进入逐人数判定）**

仅在重点人数 `6/7/9` 上叠加，每个（场景, 人数）样本量为 `SUPPLEMENTARY_DECISION_SAMPLES = 1000`：

| 场景 | 街范围 | 构造要点 |
|---|---|---|
| `deep-stack` | 4 街 | 起始筹码 `20000`（200 BB） |
| `shallow-stack` | 4 街 | 起始筹码 `200`（20 BB） |
| `strong-draw` | flop / turn | 自己持强组合听牌且无人下注，**触达**补牌统计分支 |
| `long-session` | river | 同一局面上的**连续决策流**（同一策略实例、同一进程），作为长会话代理 |

2/3/4/5/8 的场景叠加**未覆盖**，在报告中以 `DecisionCoverageGap(dimension="player-count", key="<人数>")` **显式声明**，原因为「`docs/20` §6.3 明确场景验收重点为 6/7/9，场景层为补充证据」。`strong-draw` 未覆盖的 `preflop` / `river` 同样显式声明（`dimension="street"`）。

`long-session` 是**同一进程内的连续决策流**（sustained stream）代理，**不是**多手真实会话，也**不产生**任何稳定性或漂移结论；其数字只作实时成本的补充证据。

### 4.4 报告模型与校验（冻结）

新增模型（全部 `frozen=True, extra="forbid"`）：

| 模型 | 字段 |
|---|---|
| `LatencyGroupSummary` | `label`、`decision_count`、`median_ms`、`p95_ms`、`p99_ms`、`max_ms`、`timeout_count`、`within_hard_budget` |
| `PlayerCountDecisionLatency` | `player_count`、`summary`（`DecisionLatencySummary`）、`groups`（`tuple[LatencyGroupSummary, ...]`） |
| `DecisionCoverageGap` | `dimension`（闭集 `player-count` / `street`）、`key`、`reasons`——**不含任何延迟值** |
| `DecisionScenarioLatency` | `scenario`、`description`、`streets`、`player_counts`、`uncovered` |
| `DecisionLatencyReport` | `scope`、`measured_path`、`lookup_runtime_integration`、`lookup_runtime_integration_note`、`decision_budget_ms`、`p95_guidance_ms`、`p99_guidance_ms`、`recommended_decision_samples`、`environment`、`baseline`、`supplements` |

`build_decision_latency_report` 的校验（不通过即抛明确异常）：

1. `baseline.scenario` 必须是 `baseline`；补充场景名必须唯一且不等于 `baseline`；
2. **每个场景**的「已测人数 ∪ 未覆盖人数」必须**恰为** 2–9：不得缺项、不得重复、**不得同时判为已测与未覆盖**；
3. 每个场景声明的 `streets` 必须是 `DECISION_STREETS` 的**非空子集**；`DECISION_STREETS` 中未覆盖的街必须以 `dimension="street"` 显式声明；
4. 每个已测人数的分组 `label` 集合必须**恰等于**该场景声明的 `streets`；
5. `environment` 的键必须是 `REPORTED_ENVIRONMENT_KEYS` 的**子集**（该白名单不含任何 seed 字段），防止把隐藏信息带入报告；
6. 报告**不含**任何均值 / 合计 / 加权字段：逐人数通过只能由 `player_counts` 逐项给出；用单个人数的汇总充当「全人数通过」在结构上**不可表达**。

### 4.5 失败与未覆盖语义

1. **超时**：任何逐人数 / 逐街 / 逐场景出现 `timeout_count > 0`（即存在 `>= 100.0ms` 的样本）即**失败**；不放宽硬预算、不改判据；如实记录并说明是否复测。
2. **余量**：`p95 < 50.0ms`、`p99 < 80.0ms` 只作为布尔值报告，**不**作为通过判据。
3. **覆盖缺失**：人数 / 街 / 场景层面的缺口必须显式声明并给出原因；**不插值、不用 6/7 折算 2–9、不把合并均值当逐人数通过、不用最近桶/补零/掩码**。
4. **未覆盖单元**只带维度与原因，**不带任何延迟值**（模型层面保证）。

### 4.6 opt-in 测量入口

1. 新增 `backend/tests/test_decision_latency_benchmark.py`，`pytestmark = pytest.mark.skipif(...)`；默认整轮测试**不触发**任何真实测量（与既有 opt-in 入口互不影响）。
2. 环境变量：`HOLDEM_DECISION_LATENCY_BENCHMARK=1`（总开关）；`HOLDEM_DECISION_SAMPLES`（逐人数样本量，默认 10000）；`HOLDEM_DECISION_FOCUS_SAMPLES`（逐场景逐人数样本量，默认 1000）；`HOLDEM_DECISION_SCENARIOS`（场景名单，默认全部四个，`none` 表示只跑基础矩阵）。
3. **不猜任何路径**：本轮测量不需要任何外部产物，入口不读取工作区以外的文件。
4. **只读**：只打印报告，**不写回、不移动**任何工件；不消耗 authorization、不新增 campaign、不移动既有实验工件。
5. 局面构造与计时辅助放 `backend/tests/decision_latency_states.py`（非 `test_` 前缀，不会被自动收集为用例），供 opt-in 入口与常驻回归测试共用，避免两套构造。
6. 单元测试只用**小样本**，不触发真实测量。

### 4.7 验收口径

| # | 验收项 | 判据 |
|---|---|---|
| D1 | 口径复用 | 预算常量、分位法、逐人数汇总全部来自既有模块；新模块源文件不含任何预算数值字面量，也不含独立的超时阈值 |
| D2 | 分位与超时边界 | 恰好 `100.0ms` 计为超时；街分组与逐人数汇总在同一批样本上超时计数**一致**；分位取最近秩 |
| D3 | 逐人数完整性 | 2–9 不得缺项、不得重复、不得同时判为已测与未覆盖（每个场景均校验） |
| D4 | 无合并均值 | 报告字段集冻结且不含均值/合计字段；用单个人数充当「全人数通过」结构上不可表达 |
| D5 | 10000 次口径自洽 | 逐人数 `decision_count` 等于设定样本量；逐街计数之和等于逐人数总数 |
| D6 | 未覆盖只带状态与原因 | `DecisionCoverageGap` 字段集恰为 `{dimension, key, reasons}`，无延迟值 |
| D7 | 失败语义 | `>= 100.0ms` 计失败；p95/p99 建议值只报告不判定 |
| D8 | 路径如实 | 报告显式给出被计时路径与「lookup 未接入 → 未建模」状态 |
| D9 | opt-in 与默认零影响 | 默认整轮测试不触发真实测量（保持既有 skip 语义） |
| D10 | 不写回工件 | 新增的两个代码文件均无任何文件写入调用 |
| D11 | 信息边界 | 测量路径不读取对手暗牌、未来牌与运行中 seed；替换对手暗牌不改变同种子下的策略分布；报告 `environment` 键受白名单约束 |
| D12 | 2–9 参数化 | 局面构造与汇总对 2–9 全部生效，不写死两人 |
| D13 | 既有语义零改动 | `lookup_budget.py` 常量取值与既有断言不变；后端完整套件基线不减少、无既有用例被删改 |

## 5. 版本影响与兼容性（预期）

| 对象 | 预期影响 |
|---|---|
| `heuristic.py` 决策语义 | **零改动**（只被调用） |
| `equity()` 的 `ties/2` 与调用采样数 | **零改动**（不触发 `docs/37` §3.1 升版） |
| 参考实现 / 保守判据 / 固定种子 | **零改动**（不触发升版） |
| `lookup_budget.py` | **零改动**：常量取值、模型、既有断言全部不变（只被 import） |
| `poker/**`、`analysis/**`、`api/**`、`frontend/**`、`storage/models.py` | **零改动**；不加列、不迁移 |
| 锁文件 / 真实数据库 / `tools/trainer/**` | **零改动** |
| 新增模块 | 新增口径模块与导出；**无生产调用方**，不改变运行时路径与对外响应 |
| 旧响应 / 旧历史 / 旧前端 | 结构不变；`history_json` 未被改写 |

## 6. 预算核算（预期，实跑后按实测锚点更正）

- 本机 CPU 时间：设计期只读抽样（临时脚本，实施完成后删除，**不属测量结果**）显示单次决策中位数在 N=9 时最高约 `23–26 ms`（翻后），翻前低于 `0.01 ms`。
- 据此预估：基础矩阵 `80000` 次决策约 `15` 分钟；四个补充场景（3 人数 × 4 场景 × 1000 次）约 `5` 分钟；合计预估 `20` 分钟以内。**实际耗时在 `docs/46a` 如实披露**。
- 本轮不新增受监督运行、不消耗 authorization、不追加 seed、不上云、不转 GPU；每条 authorization 仍**不可重试**。

## 7. 边界声明与不得声称

- 本轮是**性能口径与测量**工作，**不是** CFR 接入，也**不是**质量证据；测量入口与测量结果**不得**被表述为策略质量、收敛或生产可用性结论。
- 所有性能数字必须标注为**本机单机型观测**（`MEASUREMENT_SCOPE`），**不外推**云环境或生产容量；**有限样本不能证明未来不会超时**。
- **不得**把 P0-2 的**查询路径**数字（`docs/41a` §5）表述为端到端 Bot 决策延迟；**不得**把 `docs/20` §2.8 的旧样本表述为修复后结果；**不得**用 6/7 结果插值或折算 2–9。
- 「**接入 lookup 后的实时成本**」在 lookup 未接入 runtime 前必须标注为**未建模**；本轮**不**以任何形式给出该数字。
- 若出现稳定性类结论，必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者）；本轮**不产生**该类结论（`long-session` 只是连续决策流的成本观测）。
- **单元测试不等于 A6/A7 实验结果**；未启动实际运行前，不得伪称已生成策略、质量或资源证据。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- 不得修改 `docs/20` 至 `docs/45a`；不得改 `lookup_budget.py` 的既有常量取值；不得改 `heuristic.py` 决策语义与 `equity()`。

## 8. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码 / 测试 / 前端 / 锁文件 / 真实数据库；未实施 P1-5 的实现；未实施清单其余任何一项；未接入 CFR/lookup；未启用质量门槛；未启动任何受监督运行或 campaign；未追加 seed；未重试 authorization；未 push。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P1-5，并在 `docs/46a` 中给出文件级改动、新增测试、`ruff` / `pytest` / `npm run build` 的实跑输出，以及 2–9 逐人数的中位数 / p95 / p99 / max / 超时数与四个补充场景的实测数字。**

P1-5 完成后，`docs/35` §4.2 的 **P1 组全部完成**。P2 组（2–9 人产品验收、N=9 任何更强结论、历史 `pot_results` 不一致、稳定性生产者）相互独立，可各自单独排期。
