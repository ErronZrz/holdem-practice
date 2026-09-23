# 41a M8：P0-2 实时 lookup 性能与内存预算——实施与测量回执

> 日期：2026-09-18。
>
> 本文件接在 `docs/41` 之后，沿用 `docs/30` D6 的编号族约定：`docs/41` 为规格与裁定冻结，本文件为同一轮的**实施与测量回执**。`docs/20` 至 `docs/41` 未被改写。
>
> 本文件记录已实际落地的代码、测试与实跑输出，以及**对既有 N=6/N=7 产物的只读本机性能观测**。**不产生任何策略或质量证据**；未启动任何受监督训练运行、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、未写回任何工件。

## 1. 本轮提交与授权

| 次序 | commit | 内容 |
|---|---|---|
| 1 | `3d3c7d1` | `docs/41` 规格与四个设计岔路裁定冻结（仅文档） |
| 2 | 本文件同批 | 受控产物加载与查表、预算与汇总层、导出、单元测试、opt-in 实测入口、`docs/41a` |

用户答复原文（四项均为推荐口径，照录于 `docs/41` §1.2）：交付范围「完整交付并实测真实产物」；测量输入「允许只读外部产物」；代码落点「生产层 + 显式测量入口」；未覆盖人数「如实报告并声明回退」。

据此**被授权**并已使用：`backend/app/strategy/` 新增加载/查表/预算模块、`backend/tests/` 新增测试、`docs/41*`、**只读**引用工作区外既有产物。
**被拒绝**且本轮确实未做：修改 `tools/trainer/**`；跨人数插值；最近桶近似；新增受监督运行或 campaign；追加 seed；重试 authorization。

`backend/app/api/` 的授权本轮**未被使用**：加载与查表自足，无需改动任何请求/响应模型或路由。

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

$ git rev-parse HEAD -> d6fa89ceaa74af664dce8b26dde60bcf88006b1c
```

工作区干净；`ahead 10` 属未 push 的正常形态。未做任何 `reset` / `clean` / `stash` / `checkout`；**未 push**；未消耗任何实验预算。

本轮结束前的改动面实测：

```text
 M backend/app/strategy/__init__.py
 M backend/app/strategy/abstraction.py
?? backend/app/strategy/artifact.py
?? backend/app/strategy/lookup_budget.py
?? backend/tests/test_lookup_benchmark.py
?? backend/tests/test_strategy_artifact.py
?? backend/tests/test_strategy_lookup_budget.py
```

## 3. 实际改动清单（文件级）

### 3.1 新增

| 文件 | 内容 |
|---|---|
| `backend/app/strategy/artifact.py` | 受控产物加载器（`load_strategy_artifact` / `load_lookup_table` / `load_lookup_registry`）与查表（`LookupTable` / `LookupRegistry` / `LookupOutcome`） |
| `backend/app/strategy/lookup_budget.py` | 预算常量、`ArtifactLoadSummary` / `DecisionLatencySummary` / `PlayerCountCoverage` / `LookupBudgetReport` 与纯汇总函数 |
| `backend/tests/test_strategy_artifact.py` | 51 个用例：加载器 11 类校验、键与投影一致性、查表七状态、无网络、无最近桶、2–9 参数化 |
| `backend/tests/test_strategy_lookup_budget.py` | 14 个用例：分位点、延迟汇总、冷加载汇总、报告装配与「逐人数完整覆盖 2–9」 |
| `backend/tests/test_lookup_benchmark.py` | 显式 opt-in 的真实产物实测入口（默认跳过） |
| `docs/41`、`docs/41a` | 规格冻结与实施回执 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/abstraction.py` | **仅扩展回退触发的值域**：新增闭类型 `FallbackTrigger`（既有三值 + `artifact-unavailable` / `artifact-mismatch` / `key-not-in-artifact`），`FallbackDeclaration.triggering_coverage` 的类型由 `CoverageStatus` 放宽为 `FallbackTrigger`。`CoverageStatus` 四值、各取值语义、`declared_fallback` 行为、`is_exact_solution` 恒 `False`、来源必须在注册表内——**全部不变**（见 §9.1） |
| `backend/app/strategy/__init__.py` | **仅新增导出**（加载/查表/预算层的 19 个名字）；既有导出名与语义不变 |

### 3.3 未触碰（边界逐项核验）

- **零改动**：`backend/app/poker/**`（含 `equity` / `estimate_static_showdown_share` / `pot_projection` / `_settle_showdown`）、`backend/app/analysis/**`、`backend/app/storage/**`（含 `models.py`：未加列、未迁移）。
- **零改动**：`backend/app/api/**`、`frontend/**`、`backend/data/holdem.db`、`backend/uv.lock`、`frontend/package-lock.json`。
- **零改动**：`tools/trainer/**`（含 `kuhn_cfr/**`）：仅**只读**引用其产物格式与字段语义，代码中不导入、不执行其内容。
- `backend/app/strategy/heuristic.py`、`random_strategy.py`、`interface.py`、`projection.py`、`registry.py` 的决策语义与分派语义**零改动**。
- 既有实验工件**只读**：`/Users/bryanylliu/holdem-campaigns/` 未被写入、未被移动、未新增 authorization。

## 4. 加载器与查表的实际形态

### 4.1 加载校验（实测全部生效）

| 类别 | 实际校验 |
|---|---|
| 文件 | 非链接描述符打开；必须是**非链接普通文件**（目录、链接均失败）；超过 `64 MiB` 本地上限失败 |
| 编码与 JSON | UTF-8；有效 JSON；**重复键**失败；**非有限数**（`NaN` / `Infinity`）失败；顶层必须是对象 |
| 顶层 | 键集**恰好** 8 个；`artifact_type` 必须是 `multiplayer-cfr-average-strategy`；`schema_version` 必须是 `1` |
| game | 键集**恰好** 10 个；`deck` 键集恰好 2 个；人数必须在抽象合法人数内；版本必须是 `m8-a-v1`；`deck.rank_count == player_count`；`copies_per_rank == 1`；`ante == 1`；`bet == 1` |
| 概率单位 | 必须是正整数；每条信息集的动作用整数单位**非负**且**之和恰等于** `probability_units` |
| 信息集 | 键集**恰好** 7 个；`actor` / `rank` 在人数范围内；`legal_actions` 必须是该阶段的固定两动作；`actions` 键集必须恰等于 `legal_actions`；动作必须在抽象动作集内 |
| **键一致性** | `key` 必须**逐字等于**由 `(version, N, actor, rank, history)` 本地重算的抽象键；历史必须是该抽象的规范公开决策历史；历史派生行动者必须等于 `actor` |
| **公开投影一致性** | 产物的 `public_state` 必须与由 `history` 复算的公开投影**逐字段相等**（`actor` / `opener` / `folded` / `active` / `contributions` / `pending_responders` / `terminal`）；错位一律失败 |
| 交叉核对 | 信息集条数必须与 `quality.coverage.total_infosets`、`resources.infoset_count` 三者一致；`resources.artifact_bytes` 必须等于真实文件字节数 |
| 唯一性 | 全部 `key` 不得重复 |
| 禁止项 | 不 pickle、不导入模块路径、不执行产物内容、未知键不回退 |

「公开投影一致性」与「字节数交叉核对」是实现在 `docs/41` §5.1 冻结清单之外的**额外**校验（同属 L7/L11 的「未知/缺失/错位一律失败」精神），在此如实标明。

### 4.2 查表七状态（实测）

`hit` / `out-of-abstraction` / `incomplete-infoset` / `version-mismatch` / `artifact-unavailable` / `artifact-mismatch` / `key-not-in-artifact`。
只有 `hit` 返回动作整数单位；其余六态的 `action_units` 与 `abstraction_key` 均为空（`artifact-unavailable` / `artifact-mismatch` / `key-not-in-artifact` 保留抽象键以便追溯），并各自附带回退来源声明。**没有任何**邻居键、默认桶、补零或插值路径。

`artifact-mismatch` 是**防御性**路径：只有人工组装的错配注册表（把某人数产物挂到另一人数键下）才会命中；正常装载路径下不可达。

## 5. 真实产物实测（本机单机型观测，不外推）

命令与输入（路径由参数提供，代码不硬编码）：

```text
$ cd backend && HOLDEM_LOOKUP_BENCHMARK=1 \
    HOLDEM_ARTIFACT_ROOT=/Users/bryanylliu/holdem-campaigns \
    uv run pytest -q -s tests/test_lookup_benchmark.py
1 passed in 2.09s

环境：platform=darwin / python=3.13.8 / 观测时间 2026-09-18T18:05:13 / 每人数 10000 次查询
```

### 5.1 全部 11 份产物的冷加载观测（补充证据，不进入逐人数报告）

| 人数 | 字节 | 冷加载 ms | 进程峰值 RSS | sha256（前 16 位） | 产物 |
|---|---:|---:|---:|---|---|
| 6 | 401,604 | 23.06 | 39,632,896 | `0bc874e35895e6d1` | campaign-2/`a6-seed-6922-r2` |
| 7 | 1,145,054 | 61.80 | 47,824,896 | `9091c1e56dac5034` | campaign-2/`a7-seed-7926-r2` |
| 7 | 1,142,972 | 59.53 | 47,513,600 | `0f0b04cda6e002ed` | campaign-5/`a7-seed-7926-i1000-r3` |
| 7 | 1,143,244 | 60.53 | 47,841,280 | `126c038a0a4877c8` | campaign-6/`a7-seed-1215-i1000` |
| 7 | 1,142,938 | 59.97 | 47,480,832 | `a9a01f8c1319fabc` | campaign-6/`a7-seed-20260918-i1000` |
| 7 | 1,143,373 | 61.10 | 47,792,128 | `e627eae3a5c062a6` | campaign-6/`a7-seed-3311-i1000` |
| 7 | 1,142,972 | 60.81 | 47,874,048 | `0f0b04cda6e002ed` | campaign-6/`a7-seed-7926-i1000-r4` |
| 6 | 401,598 | 23.04 | 39,550,976 | `fbd4f71ccbc23f8a` | campaign-7/`a6-seed-1215-i1000` |
| 6 | 401,445 | 23.04 | 39,387,136 | `e6f506b4ca710e97` | campaign-7/`a6-seed-20260918-i1000` |
| 6 | 401,513 | 22.86 | 39,337,984 | `5509fdf70f80940c` | campaign-7/`a6-seed-3311-i1000` |
| 6 | 401,604 | 22.99 | 39,354,368 | `0bc874e35895e6d1` | campaign-7/`a6-seed-6922-r3` |

汇总口径（同一观测内）：

- **N=6**（5 份，401,445–401,604 B）：冷加载 **22.86–23.06 ms**；进程峰值 RSS **39.34–39.63 MB**；
- **N=7**（6 份，1,142,938–1,145,054 B）：冷加载 **59.53–61.80 ms**；进程峰值 RSS **47.48–47.87 MB**。

逐字节重复对照（**事后跨工件只读比较**，代码中没有稳定性生产者）：`0bc874e35895e6d1…`（401,604 B）同时出现在 campaign-2 与 campaign-7 的 `a6-seed-6922` 两份不同运行的产物上；`0f0b04cda6e002ed…`（1,142,972 B）同时出现在 campaign-5 与 campaign-6 的两份产物上。这与既有文档对 `0bc874e3…86a5c5a7` 与 `0f0b04cd…feb553` 的逐字节一致记录相符——**本文件只把它记为只读对照，不作稳定性结论**。

### 5.2 逐人数报告（进入报告的代表产物）

| 人数 | 样本数 | 中位数 ms | p95 ms | p99 ms | max ms | 超时数（≥100ms） | 判定 |
|---|---:|---:|---:|---:|---:|---:|---|
| 6 | 10000 | 0.006125 | 0.007000 | 0.008000 | 0.135500 | 0 | 未观察到超预算查询 |
| 7 | 10000 | 0.006458 | 0.007333 | 0.008250 | 0.081750 | 0 | 未观察到超预算查询 |
| 2 | — | — | — | — | — | — | **无产物，未测**（`out-of-abstraction`） |
| 3 | — | — | — | — | — | — | **无产物，未测**（`out-of-abstraction`） |
| 4 | — | — | — | — | — | — | **无产物，未测**（`out-of-abstraction`） |
| 5 | — | — | — | — | — | — | **无产物，未测**（`out-of-abstraction`） |
| 8 | — | — | — | — | — | — | **无产物，未测**（`out-of-abstraction`） |
| 9 | — | — | — | — | — | — | **无产物，未测**（`artifact-unavailable`，键 `m8/m8-a-v1/n=9/actor=0/rank=0/history=-`） |

代表产物与冷加载（同一次运行）：

| 人数 | 产物 | 字节 | sha256（前 16 位） | 冷加载 ms | 进程峰值 RSS |
|---|---:|---:|---|---:|---:|
| 6 | campaign-2/`a6-seed-6922-r2` | 401,604 | `0bc874e35895e6d1` | 23.06 | 39,632,896 B |
| 7 | campaign-2/`a7-seed-7926-r2` | 1,145,054 | `9091c1e56dac5034` | 61.80 | 47,824,896 B |

对照口径：本轮报告的 idle 内存参照上界为 `536,870,912 B`（512 MiB，平台既有「数百 MB」量级的对照值，**本轮不新设门槛**）。两个代表产物的进程峰值 RSS（约 39.6 MB 与 47.8 MB）都远低于该参照值，但**这只是本机单机型的冷加载观测**。

逐人数完整覆盖 2–9：`measured_player_counts == (6, 7)`，`uncovered_player_counts == (2, 3, 4, 5, 8, 9)`，两者并集恰为 2–9。

### 5.3 必须同时声明的三件事

1. **产品声称支持 2–9 人，但既有产物只有 6 与 7 两个人数。** 2/3/4/5/8/9 六个**没有**产物覆盖；本轮**没有**用 6/7 的结果插值或折算给它们。把「6/7 有实测」读成「2–9 已覆盖」是**错误**的。
2. **测到的是查询路径，不是端到端牌局决策。** 本轮没有把 CFR 接入 runtime，被计时的是「抽象投影校验 + 定长键查表」，因此这些数值**不构成**任何端到端 Bot 决策预算结论；`<100ms` 是**实时 Bot 决策**预算，不是整手复盘预算。
3. **有限样本不能证明未来不会超时。** 观测到 `max≈0.0818–0.1355 ms`、超时数 0，只能表述为「在本机该样本上未观察到超预算查询」。这也**不**替代 P1-5（修复后 2–9 人性能复测），后者仍未被授权。

## 6. 新增测试（65 个）

```text
$ cd backend && uv run pytest -q --collect-only \
    tests/test_strategy_artifact.py tests/test_strategy_lookup_budget.py | tail -1
65 tests collected
```

| 验收项（`docs/41` §5.6） | 覆盖情况 |
|---|---|
| D1 受控加载 | 重复键、非有限数、非对象顶层、非 UTF-8、目录路径、超限、缺字段/未知字段、错类型、错结构版本、错游戏版本、非法人数、牌组不匹配、重复 rank 牌组、非正概率单位、条数矛盾、字节数不符、键不符、终局历史、未知动作、单位和不匹配、负单位、重复信息集键、动作与阶段不符、公开投影错位、公开投影含未登记字段——**逐项失败用例** |
| D2 命中唯一且精确 | `hit` 的动作整数单位与产物逐字相等，且之和等于 `probability_units` |
| D3 无最近桶 | 抽象外 / 无产物 / 产物错配 / 产物未收录四类均无动作分布；未收录时给出该抽象键且不返回邻居单位 |
| D4 回退可追溯 | 全部非命中态都带回退声明；来源标识在受控注册表内；来源标注为契约声明；`is_exact_solution` 恒 `False` |
| D5 零 LLM / 无网络 | 屏蔽 `socket.socket` 与 `socket.create_connection` 后查表仍命中；查表签名只接受五项抽象投影输入 |
| D6 逐人数如实 | 报告要求并集恰为 2–9；未覆盖人数只带状态与回退声明，不带任何延迟值 |
| D7 `<100ms` 口径 | 报告给出逐人数 `max` 与超时数；边界样本恰为 100ms 时计为超时 |
| D8 默认测试不受影响 | 实测入口默认跳过；整轮默认测试**不**加载任何真实产物 |

## 7. 实跑验证输出

```text
$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
333 passed, 1 skipped, 2 warnings in 10.61s      （268 → 333，新增 65；1 skipped 为实测入口）

$ cd backend && HOLDEM_LOOKUP_BENCHMARK=1 HOLDEM_ARTIFACT_ROOT=/Users/bryanylliu/holdem-campaigns \
      uv run pytest -q -s tests/test_lookup_benchmark.py
1 passed in 2.09s

$ cd frontend && npm run build
✓ 23 modules transformed.
dist/assets/index-C7nR2Wox.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 614ms
```

前端产物文件名与体积与 `docs/39a` §7、`docs/40a` §6 记录**逐字相同**，证明本轮改动未越出后端。`tools/trainer/` 未改动，故未运行其 `ruff` / `pytest`。

## 8. 版本影响与兼容性

| 对象 | 实际行为 |
|---|---|
| P0-3 覆盖判定 | `CoverageStatus` 四值与语义**零改动**；仅回退声明的触发值域放宽（§9.1） |
| `FallbackDeclaration` | 字段名与既有取值不变；新增三个**产物层**触发取值；`is_exact_solution` 仍恒 `False` |
| 既有策略语义 / 分派 | **零改动**；`registry` / `games.py` / API 行为不变；**未新增**任何运行时回退动作，也**未接入**任何在线 CFR 决策路径 |
| API 与前端 | 零改动；不改请求/响应字段；不恢复已移除的前端策略选择器 |
| 数据库 | 不加列、不迁移；真实数据库只读，未被写入 |
| 旧历史 / 旧响应 | 结构不变；`history_json` 未被改写 |
| 既有实验工件 | **只读**；`/Users/bryanylliu/holdem-campaigns/` 原样保留（11 份产物字节与哈希在本轮前后一致） |
| 锁文件 | `backend/uv.lock` 与 `frontend/package-lock.json` 零改动（不新增依赖） |
| 抽象外/无产物局面 | 不产生动作分布；给出七值之一的显式状态与**声明式**回退来源 |

## 9. 规格修订与口径细化（如实记录）

### 9.1 对 `docs/40` 回退触发值域的扩展（已在 `docs/41` §4 预先声明的修订）

`docs/40` §4.5 的回退触发值域原为「覆盖取值三选一」，不足以表达产物层触发（无产物 / 产物错配 / 产物未收录）。本轮新增闭类型 `FallbackTrigger`（既有三值 + 三值），只扩展值域，不改既有取值语义；`CoverageStatus` 与既有测试**全部不受影响**（P0-3 的回退相关断言在整轮 `333 passed` 中继续通过，无需修改任何既有用例）。

### 9.2 实施中细化的口径：`docs/41` §5.4 的「未覆盖人数状态」

`docs/41` §5.4 原文把 2/3/4/5/8/9 笼统写成「给出 `artifact-unavailable` 的回退声明」。实施中按 `docs/41` §4.1 自身的定义细分，**这是修正，不是改变结论**：

| 人数 | 诚实状态 | 理由 |
|---|---|---|
| 2 / 3 / 4 / 5 / 8 | `out-of-abstraction` | 这些人数**根本不在抽象合法人数内**，标成「产物不可用」是错误陈述 |
| 9 | `artifact-unavailable` | 9 **在**抽象合法人数内且判定为抽象内，但**从未有产物** |

六个人数**全部**如实标为「无产物，未测」，回退来源一律为受控注册表内的 `heuristic@1`，`is_exact_solution` 恒 `False`。

### 9.3 实施中新增的两项额外校验

除 `docs/41` §5.1 冻结的校验清单外，本实现另加两项（更严，不放松）：产物 `public_state` 与 `history` 的**逐字段一致性**；`resources.artifact_bytes` 与真实文件字节数的**一致性**。两者都是「宁可失败也不接受可疑产物」的方向。

## 10. 边界声明与不得声称

- 本轮改动是**离线产物的加载、查表与测量**，**不是** CFR 接入 runtime；`backend/app/strategy/` 仍**没有**任何在线 CFR 决策路径，也**没有**任何运行时可用的回退动作。
- §5 的数值是**本机单机型性能观测**，**不构成**质量证据、收敛证据或生产容量结论，且**不外推**云环境或其他机型。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- **不得**把回退路径表述为「已覆盖」「已支持 CFR」或「精确解」；回退仍只是**声明的来源标注**。
- **不得**把「6/7 有产物」外推为「2–9 人已覆盖」；产品上限定 9 人的验收仍属 P2-1。
- 本轮观测**不替代** P1-5（修复后 2–9 人性能复测），也**不**为其提供结论；`<100ms` 是**实时 Bot 决策**预算，不是整手复盘预算。
- 逐字节重复对照必须标注为「事后跨工件只读比较」；代码中仍**不存在**稳定性生产者。
- 未启动实际运行前，不得伪称已生成策略、质量或资源证据。
- 未改写 `docs/20` 至 `docs/41`。
- 未 push（`ahead 12` 由用户决定何时推送）。

## 11. 未做事项与下一步唯一建议动作

未做：

- **未接入 runtime**：没有把 CFR 查表接进 Bot 决策路径，没有实现任何回退动作，`games.py` / `registry` 的策略分派零改动。
- **未测量端到端 Bot 决策预算**，也**未**为 2/3/4/5/8/9 提供任何推断值或插值。
- 未实施 `docs/35` §4 清单中 P0-2 以外的任何一项；P1 / P2 组全部未动；**P0-6 门槛仍未签收**（维持只报告不设门槛）。
- 未改动 `backend/app/api/**`（授权但不需要）、前端、`poker/**`、`analysis/**`、`storage/**`、锁文件与真实数据库。
- 未改动 `tools/trainer/**`；未新增 JSON schema 或依赖。
- 未新增受监督运行或 campaign；未追加 seed；未重试任何已消耗 authorization；未消耗实验预算；未做云端操作。
- 未 push。

至此 `docs/35` §4.2 的 **P0 组（P0-1 … P0-7）已全部完成**。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**实施 P1-1（位置与公开行动历史的信息集投影）**。理由：P0-3 已把「抽象键 + 覆盖判定」备好，但真实局面到抽象投影的映射**仍然缺失**——这正是 §5.3 中「人数匹配也只判不完整信息集」的原因；P1-1 是 `P1-1 → P1-2 → P1-3` 链路的前置，也是把真实局面真正映射进抽象的必经一步，需**单独授权**。

不建议立即做的是：在 P1-1 之前推进 P0-6 门槛签收——按 `docs/35` §4.3，门槛的必要性论证更适合在真实局面覆盖口径确定之后进行；若你更希望先把门槛形式化签收，也应作为一个**独立授权项**处理，且不得反转既有的「只报告不设门槛」结论。
