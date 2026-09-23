# 51 M8：P2-2——N=9 训练与导出可行性 campaign 设计冻结（规格）

> 日期：2026-09-20。
>
> 本文件接在 `docs/50` / `docs/50a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/51` 记录本轮**规格与决策冻结**；若下一轮真正落地代码或启动受监督运行，其回执另起 `docs/51a`。本文件**只写规格，不写回执**。
>
> 本文**不实施任何代码、不启动任何受监督运行**。未接入 CFR/查表、未新建 campaign、未生成任何 probe / experiment / preflight / attestation 输入、未追加 seed、未重试任何已消耗 authorization、未做任何云端或 GPU 操作。
>
> **本文件不构成授权。** 第 5 节的闸门放开、第 6 节的 preflight 复用、第 7 节的两个 campaign 与预算 envelope，**都必须另经用户单独授权**方可实施。本文只把「要放开什么、按什么口径放开、按什么口径核算」写死，供授权时逐项比对。
>
> **本文件不产生任何策略、质量或资源证据。**

## 1. 授权范围与设计岔路裁定

### 1.1 用户答复原文（逐项照录）

本轮采用「先问用户」，共问两轮。

第一轮（本轮范围）：

| 岔路 | 用户答复原文 |
|---|---|
| P2-2 本轮范围 | 「A. 仅冻结设计文档（推荐）」——只提交 `docs/51`：N=9 campaign / 预算 envelope 规格，零代码改动、不启动受监督运行，下一轮再实施 |

第二轮（设计冻结前的四项裁定）：

| 岔路 | 用户答复原文 |
|---|---|
| Q1 目标形态 | 「A. 只证训练+导出可行性（推荐）」——仅放开训练与导出闸门；profile/probe 闸门保持关闭；N=9 不产出任何质量结论 |
| Q2 estimator preflight | 「A. 沿用 n6 preflight attestation（推荐）」——与 campaign-6/7 一致；如实披露 preflight 只覆盖 N=6、且 N=9 无 profile/probe |
| Q3 seed 集合 | 「A. 沿用 4 个预注册 seed（推荐）」——`{1215, 20260918, 3311, 7926}` |
| Q4 轮次策略 | 「A. 先标定再冻结长期值（推荐）」——campaign 内第一条 authorization 做小轮次标定，据实测再放开长期轮次；长期候选 1000 轮 / 预热 100 |

### 1.2 裁定（冻结）

| 裁定 | 内容 |
|---|---|
| 一 | **目标形态限定为「长期训练 + 策略导出」可行性**。N=9 的 profile / probe 闸门**一律保持关闭**，因此 N=9 **不产出任何质量结论**（既不产出、也不声称）。 |
| 二 | **新增 `execution.kind = "a9-training"`**，不改动既有 `a6-a7-training`（仍限 {6,7}）与 `n9-boundary-sample`（仍限 iteration=1、单 traverser、禁 profile/probe）的语义。 |
| 三 | **estimator preflight 沿用 N=6 fixture**（`n6-estimator-preflight`）。理由与先例见第 6 节。 |
| 四 | **seed 集合预注册为 `{1215, 20260918, 3311, 7926}`**，与 campaign-6 / campaign-7 同一集合；执行开始后不得追加、不得替换、不得因结果不理想而重跑。 |
| 五 | **两阶段拆解**：先 `m8-a-campaign-8` 做 N=9 小轮次标定（1 条 authorization），阶段一实测回执落盘后**才**冻结 `m8-a-campaign-9` 的长期 envelope（4 条 authorization）。 |
| 六 | **不启动任何受监督运行**：本轮零代码、零 campaign、零预算消耗。 |

### 1.3 与 `docs/37` §3.1 的关系

`docs/37` §3.1 的升版规则只作用于**后端复盘参考 / 评估身份**（`backend/app/analysis/reference_identity.py`）。本文件的全部改动**只在 `tools/trainer/**`**：既不涉及 `reference_identity.py`，也**不触发**该 §3.1 升版；后端 `backend/app/strategy/artifact.py` 与 11 份已封存 `strategy.json` 均不受影响（见 §9）。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 6]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git --no-pager log -8 --oneline
d946e73 feat: wire cross-seed stability into supervised records and add cross-seed record type
0f3924f docs: freeze p2-4 supervised stability and cross-seed record specs
b32cd4b feat: add code-built cross-seed stability producer for measurement records
fae65bd docs: freeze p2-4 cross-seed stability producer specs
5e94d8a docs: record p2-3 historical pot results read-only diagnosis
4a41951 docs: freeze p2-3 historical pot results diagnosis specs
133c99c feat: enforce 2-9 player product range and geometry-driven seat layout
2ac96dd docs: freeze p2-1 player count product acceptance specs

$ git rev-parse HEAD          -> d946e731aa07a7109214f13bd32a9ce0e4956828
$ git rev-parse origin/master -> 133c99cbf541e9bf49d1f5f2e795ca6585e91d8d

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l        -> 8
$ find /Users/bryanylliu/holdem-campaigns -name strategy.json | wc -l     -> 11
$ find /Users/bryanylliu/holdem-campaigns -name measurement.json | wc -l  -> 14
$ ls -1 backend/app/strategy/*.py | wc -l                 -> 14
$ ls -1 backend/tests/test_*.py | wc -l                   -> 28
$ ls -1 tools/trainer/src/multiplayer_cfr/*.py | wc -l    -> 27
$ ls -1 tools/trainer/tests/test_*.py | wc -l             -> 25
$ ls -1 docs/ | tail -6   -> 48 / 48a / 49 / 49a / 50 / 50a
```

与期望基线完全相符（`## master...origin/master` ahead 6、工作区 0 行、`HEAD = d946e73`、`origin/master = 133c99c`）；未做任何 `reset` / `clean` / `stash` / `checkout` / `push`。

`/Users/bryanylliu/holdem-campaigns/` 下 8 个目录为 `m8-a-campaign-1` … `m8-a-campaign-7` 与 `m8-a-n9-boundary`；**下一组 campaign 编号从 `8` 起**。

本轮为撰写第 3、5、6 节而做的只读代码核对（不构成任何实验证据）：

| 项 | 实测 |
|---|---|
| `game.ALLOWED_PLAYER_COUNTS` | `frozenset({6, 7, 9})`（`game.py:12`） |
| `resources._STATE_BUDGET_BYTES` / `_ARTIFACT_BUDGET_BYTES` | 6→32 MiB/4 MiB、7→96 MiB/12 MiB、**9→512 MiB/64 MiB**（`resources.py:10-11`） |
| `policy.MAX_ARTIFACT_BYTES` / `PROBABILITY_UNITS` / `SCHEMA_VERSION` | `64 MiB` / `1e12` / `1`（`policy.py:39-42`） |
| `policy.load_quantized_strategy` 读取上限 | `MAX_ARTIFACT_BYTES`（64 MiB），**不是** `safeio.MAX_TEXT_BYTES`（4 MiB） |
| `profile` 为 `null` 的训练记录 | **已被接受**：`experiment_record._validate_profile_payload` 在 `value is None` 时直接返回（与 `strategy` 是否存在无关） |
| 受监督运行控制路径 | `supervised_executor._require_campaign_authorization`：`n9-boundary-sample` 免 lease；其余计划**必须**有 lease + preflight spec/attestation |
| `campaign._parse_authorizations` | `authorization_id` 必须**按字符串升序**且不重复；预留总和不得超过 campaign `limits` |
| 累计实测预算（截至本轮） | `52.90 min`（`docs/34b` §9.8 → `docs/35` §6 转述） |

## 3. N=9 现状：结构性上界与代码闸门（只读核验）

### 3.1 结构性上界（**只能作上界引用，不是测量值**）

来源：`docs/26` §5.2 与 §11、`docs/29` §3.3。这些是闭式规则计数与朴素枚举规模，不是任何运行结果：

| 量 | N=9 |
|---|---:|
| ordered deals（`9!`） | 362 880 |
| 公开决策历史（`N·2^(N-1)`） | 2 304 |
| 信息集总数 | 20 736 |
| 终局历史 | 2 305 |
| 固定策略全 chance 叶子评估上界 | 836 438 400 |

### 3.2 已有的一次 N=9 实测（`docs/33a`，不得外推）

`n9-boundary-sample` 一次免 lease 采样：`boundary_infoset_count = 20 736`（与上表信息集总数一致，这是唯一被实测的结构量）、父端墙钟 551 ms、CPU 450 ms、峰值 RSS 45 957 120 B（约 43.8 MiB）、`coverage` 与 `importance_weights` 为空数组（该路径的代码设计）。

不得由它推出：N=9 的单 iteration 成本、长期训练可行性、RSS 增长、导出可行性、质量。它是**构造 + 单 traverser 单次 pass** 的观测。

### 3.3 代码闸门清单（实测 `file:line`）

用户提示词按模块汇总为「8 处」；按可独立断言的闸门位置展开实为 **12 处**（含新增 kind 必须同步的 4 处记录/分派），下表为准：

| # | 位置 | 现状行为 | 本轮口径 |
|---:|---|---|---|
| 1 | `mccfr.py:232`（`run_iteration`） | N=9 抛错 | **放开** |
| 2 | `mccfr.py:477`（`train`） | N=9 抛错 | **放开** |
| 3 | `mccfr.py:267`（`completed_result`） | N=9 抛错 | **放开**（导出需要） |
| 4 | `control.py:197`（`run_controlled_training`） | N=9 抛错 | **放开** |
| 5 | `policy.py:656`（导出） | N=9 抛错 | **放开** |
| 6 | `manifest.py:472-479`（`execution.kind = a6-a7-training`） | 限 {6,7} | **不动**；新增 kind `a9-training`（限 9） |
| 7 | `manifest.py:548-552`（阶段列表） | kind 决定 `(training, export, profile, probe, measurement)` 或 `(boundary, measurement)` | 为 `a9-training` 定义 `(training, export, measurement)` |
| 8 | `manifest.py:515-528`（`quality`） | `n9-boundary-sample` 禁 profile/probe；probe 限 {6,7} | `a9-training` **必须** `profile_mode = not-requested` 且 `probe_manifest = null` |
| 9 | `manifest.py:593-614`（`artifacts`） | `n9-boundary-sample` 禁声明策略槽位 | `a9-training` **必须**声明策略槽位（导出用） |
| 10 | `experiment_record.py:644`（`plan_kind` 白名单） | `{a6-a7-training, n9-boundary-sample}` | 加入 `a9-training` |
| 11 | `experiment_record.py:282`（`_training_sections`） | `plan_kind` 硬编码为 `a6-a7-training` | 改为写实际计划类型，避免 N=9 记录自称 A6/A7 |
| 12 | `orchestration.py:123-125`（分派） | 仅二分到 N9 boundary 或 A6/A7 路径 | 新 kind 走训练路径（`profile_mode = not-requested` 时该路径本就跳过评估） |
| — | `mccfr.py:429`（`run_audit_iteration`） | N=9 抛错 | **保持关闭** |
| — | `evaluation.py:232`（完整 chance profile） | 限 {6,7} | **保持关闭** |
| — | `measurement.py:408`（profile `completed`） | 限 {6,7} | **保持关闭** |
| — | `manifest.py:524-527`（probe） | 限 {6,7} 且须 `full-chance` | **保持关闭** |
| — | `manifest.py:498-511`（`n9-boundary-sample`） | 强制 iteration=1、单 traverser | **保持关闭** |
| — | `estimator_preflight.py:126` | `player_count` 固定 6 | **保持关闭**（见第 6 节） |
| — | `experiment_record.py:646-649` | N9 boundary 不得关联策略/质量 | **保持关闭** |

第 1–5 与第 10–12 项是「让 `a9-training` 计划可达」的最小改动；第 6–9 项是「让该计划可被冻结与校验」的配套改动。全部集中在 `tools/trainer/src/multiplayer_cfr/`，不触碰后端、前端、锁文件与真实数据库。

## 4. 目标形态（冻结）

### 4.1 本轮（授权后）要回答与**不**回答的问题

要回答（且仅此三问）：

1. N=9 能否在显式预算下跑完 **E** 轮 external-sampling 训练而不触及资源硬停；
2. N=9 的训练结果能否**导出**为符合既有 artifact schema 的量化策略（v1、`PROBABILITY_UNITS = 1e12`），并落在预声明槽位内；
3. 上述两项的**实测资源**（CPU / 墙钟 / 峰值 RSS / 工件字节）。

**不**回答：N=9 的任何质量、收敛、均衡、NashConv、exploitability、真实 EV、生产可用性；N=9 与其他人数之间的任何比较或归因。

### 4.2 为什么 N=9 不做质量评估（上界论证，非测量）

完整 chance profile 需要枚举 `ordered deals × terminal histories` 规模的叶子；按 §3.1 的闭式上界，N=9 为 836 438 400 叶，而既有 `evaluate_profile` 明确只服务 {6,7}（`evaluation.py:232`）。因此「N=9 质量可行性」在本设计里**不是被推迟，而是被排除**：它需要一套**采样式**评估器，属新代码与新记录语义，不在本文件范围（用户 Q1 已选 A）。

据此：`a9-training` 计划**必须**声明 `quality.profile_mode = "not-requested"`，其测量记录中 `profile` 与 `probes` 均为 `null`，`stability` 恒为 `not-requested`（单条记录只有一个 seed）。这与既有 schema 完全兼容（见 §2 实测）。

## 5. 需放开的闸门清单（冻结）

### 5.1 必须放开

即 §3.3 第 1–5、10–12 项。放开后的**不变式**（必须由新增回归测试断言）：

1. `a9-training` 的 `game.player_count` **必须**为 9；`a6-a7-training` 仍**必须**为 {6,7}；`n9-boundary-sample` 仍**必须**为 9 且 `iteration = 1`；
2. `a9-training` 的 `quality.profile_mode` **只能**是 `not-requested`，`probe_manifest` **必须**为 `null`；反例（请求 full-chance 或绑定 probe）必须被拒；
3. `a9-training` 的 `artifacts.strategy` **必须**非空，且 `maximum_bytes ≤ min(MAX_ARTIFACT_BYTES, estimate_resources(9).artifact_budget_bytes)`；
4. `budget.stages` 必须**恰好**为 `(training, export, measurement)` 三阶段且按序；
5. 导出后的策略 artifact 仍满足既有 schema 校验（`artifact_type`、`game.player_count = 9`、概率归一、字节上限），即**不新增 artifact 字段、不升 `SCHEMA_VERSION`**；
6. 测量记录中 `plan_kind = "a9-training"`，`profile = null`、`probes = null`，且仍通过既有 `experiment_record` v2 校验。

### 5.2 必须保持关闭

即 §3.3 关闭清单 7 项。必须配**反向**回归测试（对 N=9 断言仍抛错），防止后续无意放开：

- `run_audit_iteration(9)` 仍拒绝；
- `evaluate_profile` / `evaluate_manifested_plan` 对 N=9 仍拒绝；
- 含 `full_chance: true` 的 profile 对 N=9 仍被 `measurement` 拒绝；
- 任何 N=9 计划绑定 probe manifest 仍被 `manifest` 拒绝；
- `n9-boundary-sample` 的 iteration/traverser/profile/probe/策略槽位五条限制不变；
- `estimator_preflight` 的 spec 仍固定 N=6。

### 5.3 被本设计**明确拒绝**的替代做法

- 不把 `a6-a7-training` 的 `{6,7}` 放宽成 `{6,7,9}`（会让 N=9 记录自称 A6/A7，语义不自洽）；
- 不给 `a9-training` 保留 `profile` / `probe` 阶段槽位（保留等于暗示将来会跑，与裁定一冲突）；
- 不为 N=9 引入「按人数分支的 estimator preflight」或任何新 preflight record（见第 6 节）；
- 不新增任何后端读取端、不加列、不迁移（N=9 策略产物仅封存在 campaign 目录内，不入库、不被后端读取）。

## 6. estimator preflight 方案（冻结）

**沿用 `n6-estimator-preflight`**：

1. preflight spec 的 `fixture_id`、`sample_seeds`、`target_infosets`（三个 N=6 信息集键）、两个 tolerance 与既有 campaign 逐字一致；
2. preflight **核验的对象是 estimator 实现身份**（`run_audit_iteration` / oracle 一致性），而不是人数；`a6-a7-training` 与 `a9-training` 走的是**同一份** MCCFR 更新代码；
3. **先例**：campaign-6 与 campaign-7 跑的是 N=7，其 `campaign.json` 引用的仍是 `n6-estimator-preflight` 的 attestation（`docs/34b` §7、`docs/31a` D4.3）。本设计沿用同一做法。

**必须如实披露的三点**：

- preflight **只覆盖 N=6**，因此 N=9 的 estimator **没有**人数专属的 preflight 证据；
- 该证据**不**覆盖任何质量评估（N=9 本就不做）；
- attestation 绑定 `code_identity.git_commit`，因此在**任何新冻结提交**上都必须由驱动脚本重新生成 spec 并**实跑** `run_preflight` 得到 attestation（不得手工构造、不得跨提交复用字节）。

## 7. campaign 与预算 envelope（冻结）

### 7.1 两阶段拆解（裁定五）

campaign manifest 的 `authorizations` 预留**必须在执行前一次性冻结**，因此「先标定再决定长期值」无法在单个 campaign 内实现。本设计据此拆成两个 campaign：

```text
阶段一  m8-a-campaign-8   1 条 authorization（N=9 小轮次标定）
        └─ 目的：实测 N=9 的每轮训练成本、导出成本、工件字节、峰值 RSS
阶段二  m8-a-campaign-9   4 条 authorization（N=9 四 seed 长期训练）
        └─ envelope 在第 7.3 节的派生规则下、用阶段一实测锚定后另行冻结
```

**阶段二未冻结前不得启动**；阶段一失败即终止，不自动进入阶段二。

### 7.2 阶段一：`m8-a-campaign-8`（标定，1 条）

| 项 | 值 |
|---|---|
| `campaign_id` | `m8-a-campaign-8` |
| campaign 根（工作树之外） | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-8/` |
| authorization / `manifest_id` | `a9-calibration-i10` |
| `game` | `m8-unique-rank-single-open` / `m8-a-v1` / `player_count = 9` |
| `execution.kind` | `a9-training` |
| `execution.iterations` | `10` |
| `execution.average_strategy_start_iteration` | `1`（10 轮全部纳入平均策略累计，使导出有非平凡内容） |
| `execution.master_seed` | `20260918` |
| `quality` | `profile_mode = not-requested`、`probe_manifest = null` |
| `artifacts.strategy` | `strategy.json`，`maximum_bytes = 16_777_216`（16 MiB） |
| `artifacts.measurement` | `measurement.json`，`maximum_bytes = 1_048_576`（1 MiB） |
| `budget.stages` | `training 300_000` / `export 60_000` / `measurement 60_000`（和 = `420_000`） |
| `budget.cpu_limit_milliseconds` | `420_000` |
| RSS | 预警 `6_442_450_944`（6 GiB）、硬停 `8_589_934_592`（8 GiB） |
| `budget.retained_artifact_limit_bytes` | `20_971_520`（20 MiB） |
| campaign `limits` | cpu / wall `420_000`、工件 `20_971_520`、峰值 RSS 8 GiB、`max_concurrency = 1` |
| preflight | 在阶段一冻结提交上重新生成的 `n6-estimator-preflight` spec + 实跑 attestation |

约束自检（口径同 `docs/31a` §5.2）：

- `2 × 1_048_576 + 16_777_216 = 18_874_368 ≤ 20_971_520` ✓；
- `strategy.maximum_bytes = 16 MiB ≤ min(64 MiB, N=9 静态预算 64 MiB)` ✓；
- `stages` **恰好**按 `training, export, measurement` 顺序 ✓；
- 预留总和 `420_000 ≤ limits` ✓。

**预算取值理由（必须如实标为估计，不是测量）**：`training` 阶段 300 s 相对 `docs/33a` 的 N=9 单次采样（子端 elapsed 397 ms）刻意放宽约 750 倍，目的是**不让阶段墙钟成为标定本身的干扰**——阶段超时无害（只停该次运行），而**预留不足一旦触发则整条不可重试的 authorization 作废**。因此本阶段刻意取宽，且**不**据此推断 N=9 长期成本。

### 7.3 阶段二：`m8-a-campaign-9`（四 seed 长期训练，4 条）

**派生规则（冻结，先于结果）**：阶段一落盘后，按下式确定每条 authorization 的 `training` 阶段预算：

```text
单轮成本锚点 = 阶段一 training 阶段实测 CPU ÷ 10
training 阶段预算 = ceil(单轮成本锚点 × 1000 × 5 ÷ 60_000) × 60_000  （毫秒，向上取整到 60 s，且 ≥ 300_000）
```

乘 5 是显式余量系数；`export` 阶段取 `max(60_000, 阶段一 export 实测 × 5)`；`measurement` 阶段固定 `60_000`。

**硬上限（任一超出即不得冻结 stage-2，必须回调用户）**：

| 项 | 上限 |
|---|---|
| 单条 authorization cpu / wall | `1_800_000` ms（30 min） |
| campaign-9 合计 cpu / wall | `7_200_000` ms（120 min） |
| 单条 authorization 工件预留 | `20_971_520` B（20 MiB） |
| 单条 `strategy.maximum_bytes` | `16_777_216` B（16 MiB） |
| campaign `peak_rss_limit_bytes` | `8_589_934_592` B（8 GiB） |

其余冻结字段（四 seed 逐字相同）：`player_count = 9`、`execution.kind = a9-training`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`quality.profile_mode = not-requested`、`quality.probe_manifest = null`、`max_concurrency = 1`、RSS 预警 6 GiB / 硬停 8 GiB。

**若阶段一实测锚点使派生值超过硬上限**，则视为「N=9 长期训练在本预算姿态下不可行」，**停止**并回调用户，不得自行放大上限、不得转云 / 转 GPU。

### 7.4 seed 集合与 authorization（预注册，不得追加）

| authorization_id / `manifest_id` | `master_seed` |
|---|---|
| `a9-seed-1215-i1000` | `1215` |
| `a9-seed-20260918-i1000` | `20260918` |
| `a9-seed-3311-i1000` | `3311` |
| `a9-seed-7926-i1000` | `7926` |

- 四者**就是全部**：开始后不得追加、不得替换、不得因某个 seed 结果不理想而重跑；
- id 已按**字符串升序**排列（`campaign._parse_authorizations` 的硬校验）；
- 与 campaign-6 / campaign-7 使用同一 seed 集合，只用于**降低成本观测噪音**；**不得**据此做跨人数比较或归因（人数与树规模同时不同）。

### 7.5 目录与驱动脚本（全部在工作树之外）

| 项 | 值 |
|---|---|
| 阶段一 / 阶段二 campaign 根 | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-8/`、`/Users/bryanylliu/holdem-campaigns/m8-a-campaign-9/` |
| 目录内约定 | `generate_frozen_inputs.py`、`run_campaign.py`、`source/`、`runs/<authorization_id>/{artifacts,inputs}`、`campaign.json`、`campaign-ledger.json` |
| Python 解释器 | `/Users/bryanylliu/my4/holdem-practice/tools/trainer/.venv/bin/python` |

沿用 `docs/33a` §1 与 `docs/33b` §8.7 记录的驱动教训：`generate_frozen_inputs.py` 须核对工作树干净与实际 HEAD、生成并**回读逐项比对**身份、拒绝覆盖既有文件；`run_campaign.py` **默认只读复验**（不获取 lease、不创建运行目录、不写执行日志），只有 `--execute <authorization_id>` 才消费一条 lease，且**一次只允许一条**。

### 7.6 停止条件（冻结）

1. **运行时硬停止**（代码已强制，与 A6/A7 同口径）：RSS 预警 6 GiB、RSS 硬停 8 GiB、阶段墙钟、父端墙钟、工件配额、外部取消；
2. **阶段一之后的决策停止**：派生值超 §7.3 硬上限 → 不冻结阶段二，回调用户；
3. **任何 authorization 失败即终止该阶段**并如实报告；不重试、不追加 seed、不重置预算、不换算法名称、不降低指标口径；
4. **导出超槽位即失败**：若 N=9 策略字节数超过预声明槽位，该 authorization 失败并**已永久消耗**；不得在 campaign 冻结之后静默放大槽位。

### 7.7 预算核算与披露

```text
本轮新增实测                                     0.00 min   （无任何受监督运行）
截至本轮开始前落盘实测累计（docs/34b §9.8）      52.90 min
累计实测                                         52.90 min
```

按 `docs/35` §6 已变更的口径：不再以「本机累计 2 小时」作为**拒绝必要轮次**的条件，改为逐轮按实测锚点配置 envelope 并如实核算、披露。以下边界不变：不转云、不转 GPU、不无限重跑、不追加预注册以外的 seed；每条 authorization 仍**不可重试**；训练相关进程峰值 RSS 合计 8 GiB、保留实验工件 1 GiB 上限不变；estimator preflight 的核验重演按 `docs/30` D3 **不计入**本机实验预算。

**预留不是消耗**：阶段一 `420_000` ms 与阶段二派生值是**上界**；实际核算以落盘回执为准，并须在阶段二回执中逐条列出。

## 8. 不得声称

- 不得把 N=9 的训练完成表述为 N=9 **质量通过**、收敛、均衡、NashConv、exploitability、best response、真实牌局 EV 或生产可用策略；
- 不得把一次采样（`docs/33a` 的 boundary sample）表述为 A9 训练完成或质量通过；
- 不得把 §3.1 的结构性计数表述为实测值；唯一被实测的结构量是 `boundary_infoset_count = 20 736`；
- 不得跨人数比较或归因（N=9 与 N=6/N=7 的人数与树规模同时不同）；
- 不得把 `n6-estimator-preflight` 表述为 N=9 的 estimator 证据（它只覆盖 N=6）；
- 不得把本轮实现表述为「已完成 N=9 实验」；
- 不得把「历史记录缺 `pot_results` 字段」表述为「结算错误」（沿用 `docs/48a`）。

## 9. 边界（沿用不可回退边界）

- **只读 / 不得修改**：`backend/**`（含 `storage/models.py` 不加列不迁移、`api/**`、`poker/**` 的结算语义）、`frontend/**`、真实数据库 `backend/data/holdem.db`、锁文件 `backend/uv.lock` 与 `frontend/package-lock.json`、`heuristic.py` 决策语义、`equity()` 的 `ties/2`、`lookup_budget.py` 常量、`policy.py` 的 artifact schema 与 `PROBABILITY_UNITS`、质量判定门槛（`docs/39` 继续不启用）；`docs/20` 至 `docs/50a`。
- **必须保持**：统一支持 2–9 人；公开 API 一律 Pydantic model；筹码/金额统一整数单位；`history_json` 原始事实不被改写；信息边界硬要求；所有随机过程可注入 seed；**已封存 v1 子记录的再读取能力**（`holdem-campaigns` 下 14 份 `measurement.json`、11 份 `strategy.json`）。
- **artifact schema 不变**：`a9-training` 复用 v1 artifact schema，不新增字段、不升 `SCHEMA_VERSION`；N=9 产物只封存在 campaign 目录内，不入库、不被后端读取。
- **记录 schema 不变**：`experiment_record` 保持 v1/v2 双版本读取；`a9-training` 记录用现有 v2 形态（`profile = null`、`probes = null`、`stability = not-requested`），不新增字段。

## 10. 不在本轮范围

- 不写任何代码、不改任何测试、不改任何既有文档；
- 不生成 probe / experiment / preflight / attestation / campaign 输入；
- 不启动任何受监督运行、不消耗任何预算、不重试任何已消耗 authorization；
- 不实现 N=9 的采样质量评估器、不放开 `run_audit_iteration` 或 `evaluate_profile`；
- 不扩展策略 artifact v1、不触发 `docs/37` §3.1 升版；
- 不把 N=9 产物接入 `campaign.py` 账本之外的后端路径。

## 11. 本轮未做事项与下一步

未做：

- 未修改任何代码或测试；工作树只新增本文件一个；
- 未新建 campaign、未追加 seed、未重试任何已消耗 authorization；
- 未启动任何受监督运行或 N=9 相关运行；
- 未改写 `docs/20` 至 `docs/50a`；既有 campaign 记录与工件原样保留。

下一步**唯一建议动作**（需用户单独授权，本轮不自行执行）：

**在 `docs/51` 被确认后，先授权实施第 5 节的闸门放开（一次 `feat:` 提交，含正向与反向回归测试），再授权阶段一 `m8-a-campaign-8` 的受监督运行。** 两者都应分次授权：闸门放开本身不消耗预算，且可在无运行的情况下被独立复核；阶段一则一旦启动即消耗一条不可重试的 authorization。

不建议在阶段一之前直接冻结阶段二 envelope——那正是裁定五与 §7.3 派生规则要避免的做法。
