# 31a M8：多人 CFR 候选 A——Canonical Campaign 冻结清单

> 日期：2026-09-18。
>
> 本文件是 `docs/31-m8-multiplayer-cfr-candidate-a-freeze-readiness-review.md` 的配套决策与冻结记录；`31a` 沿用 `docs/30` D6 记录的拆分约定，表示接在 `docs/31` 之后的追加文档。因此 `docs/31` 编号族在本轮恰好包含两个文件：`31` 为只读复核与加固记录，`31a` 为本冻结清单。`docs/20` 至 `docs/30` 未被改写。
>
> 状态：**决策已全部确认，本文件随本轮改动一并提交**。尚未生成任何真实 campaign manifest、probe manifest、preflight spec/attestation、策略工件、measurement 或 ledger，未启动任何 A6/A7 运行，也未获得一次性实际执行授权。
>
> 用途：把即将冻结的输入逐项写死，供生成实际文件时逐字段比对。**本文件中的数值在用于真实执行前，必须与最终生成的 manifest 逐字段一致。**
>
> 冻结 commit 的说明：本轮代码改动已提交为 `8f8d8fd feat: enforce campaign preflight and reservation gates at supervised entry`，`docs/31` 与 `docs/31a` 的定稿提交紧随其后。**冻结 commit 的实际哈希不写回任何被提交的文档**——写入哈希会使文档自身发生改动，从而改变 commit，形成循环；该哈希只记录在工作树之外生成的 manifest 文件中。

## 1. 决策汇总

| 决策 | 内容 |
|---|---|
| D1 | 采用方案 B：preflight 与授权预算校验下沉到共用门禁，父端监督入口强制校验。已在 `docs/31` 第 11 节实现并复验（172 passed）。 |
| D3.1 | A6/A7 **执行** full-chance profile。 |
| D3.2 | A6/A7 **执行**预注册 probe。 |
| D3.3 | 跨 seed 稳定性实验**不执行**；本轮只报告单 seed 结果，**不宣称稳定性**。 |
| D3.4 | probe 判定线 X = **0.05 BB/hand**，作为**解释边界**而非硬门禁；超过 X 时如实报告，**不重跑、不改阈值、不换 seed**。 |
| D4.1 | A6 = 1000 轮、seed 6922；A7 = 300 轮、seed 7926。iterations 走"保守设定、接受可能偏小"的路线。 |
| D4.3 | 接受 A7 没有 preflight 证据：estimator preflight 只覆盖 N=6。 |
| D4.4 | 本轮**不包含** N9 boundary authorization。 |
| D2 | `docs/31` 两个文件与 `tools/trainer/` 改动**在全部决策确认后一并 commit**；commit 后的 HEAD 才是冻结 commit。 |

游戏单位：`ANTE = 1`、`BET = 1`，即 1 单位 = 1 枚筹码 = 1 个大盲。profile 的 `utilities` 是"每手牌平均净收益"，因此 X = 0.05 表示每手 0.05 个大盲。

## 2. 已确认的 6 项配置决策

| # | 事项 | 已确认值 |
|---|---|---|
| C1 | 质量阶段超时的降级动作 | 选项 **(C)**：不动代码，把 profile/probe 预算配宽；若仍超时按 (A) 处理（整条授权失败、已声明工件被清理）。**不采用 (B)**，因此本轮不需要为"保留策略"新增代码或 schema 字段。 |
| C2 | X 的作用域 | 应用于 `probes.gains`（定义见第 3.2 节），同时如实报告双向 `results[].delta`。 |
| C3 | 质量阶段预算 | 按第 4 节实测锚点上调后的数值（A6 19 min / A7 79 min，合计 98 min）。 |
| C4 | `average_strategy_start_iteration` | A6 = `100`、A7 = `30`（各约 10% 预热）。 |
| C5 | probe 标识与阈值 | `tight-open`（open 4 / call 3）、`loose-open`（open 1 / call 0）。 |
| C6 | campaign root 绝对路径 | `/Users/bryanylliu/my4/holdem-campaigns/m8-a-campaign-1`（位于工作树之外） |

## 3. 质量判定口径（D3.4）

### 3.1 代码已内建的硬门禁（无需配置，违反即记录不合法）

1. `profile.utilities` 必须严格常和（`sum == 0`）。
2. profile/probes 必须绑定同一份量化策略的 `sha256` 与字节数。
3. probes 必须绑定其 probe manifest 身份。
4. evaluator 身份必须是当前固定 id/version/概率单位。

### 3.2 唯一的自定义判定线

预注册判定（写入本轮记录，不写入代码）：

```text
对每位玩家 p，gains[p] = 该玩家在全部预注册 probe 下相对基线策略的最大非负收益差。
若 max_p gains[p] > 0.05（BB/hand），本轮报告为"存在超过 0.05 的阈值偏离"；
否则报告为"未观察到超过 0.05 的阈值偏离"。
```

**钳位说明（重要）**：`gains[p] = max(0, max over probes of delta)`。也就是说：

- 它只反映"预注册阈值策略相对训练策略**更强**"的方向；
- "阈值策略明显**更差**"（delta < 0）**不会**体现在 `gains` 里，只能从 `probes.results[].delta` 读出。

因此本轮同时如实报告：

- `gains` 向量（用于判定线）；
- `results[].delta` 的完整集合（正负都报），以便观察反方向偏离。

### 3.3 不通过时的处理（已冻结）

如实报告，且**不得**：延长阶段预算、修改 X、更换 seed、只挑选通过的子集报告、把结论表述为均衡或 exploitability。

## 4. 质量阶段预算的重估依据（为什么与我上一轮口头估计不同）

上一轮我按 `docs/29` 第 3.2 节的 15 / 20 分钟档给出了口头建议，但当时**没有实测锚点**。本轮补测如下（**单元测试 / 评测器口径的墙钟观察，不是受控实验证据，也不能作为任何质量或资源结论**）：

| 观察项 | 数值 | 说明 |
|---|---:|---|
| A6 完整 profile（均匀混合策略） | 10.18 s | 进程内 `evaluate_profile` |
| A6 两组 probe（含 baseline profile） | 69.04 s | 进程内 `evaluate_threshold_probes`，12 次替换评估 |
| A7 完整 profile（均匀混合策略） | 191.42 s | 进程内 `evaluate_profile` |
| A7 两组 probe（按 A6 单次替换成本外推） | ≈ 22 min | 14 次替换评估，**外推值，未实测** |
| A6 受监督 1 iteration + 导出（单元测试口径） | 0.78 s | 含子进程启动、身份核验、父端终结 |
| estimator preflight 首次重演 | 61.8–64.9 s | oracle 首次构建；同进程复算 0.18 s |

**关键结论：A7 的质量成本远高于 A6**（树规模约为 16 倍），因此 `docs/29` 那种"A6 15 分钟 / A7 20 分钟"的对称假设不成立。本轮把质量阶段预算按实测锚点的 3–12 倍配置，同时把训练阶段预算从 `docs/29` 的 25 / 30 分钟下调（因为 iterations 已刻意保守）。

## 5. Experiment manifest 冻结字段

### 5.1 公共字段

| 字段 | 值 |
|---|---|
| `schema_version` | 由 `create_experiment_manifest` 固定 |
| `manifest_type` | `multiplayer-cfr-experiment` |
| `code_identity.git_commit` | **冻结 commit（commit 后确定）** |
| `code_identity.workspace_state` | `clean` |
| `code_identity.trainer_version` | `candidate-a-campaign-v1` |
| `game.id` / `game.version` | `m8-unique-rank-single-open` / `m8-a-v1` |
| `quality.profile_mode` | `full-chance` |
| `quality.probe_manifest` | 指向对应 probe manifest 的身份（第 5.3 节） |
| `budget.max_concurrency` | `1` |
| `budget.rss_warning_bytes` | `6_442_450_944`（6 GiB） |
| `budget.rss_hard_limit_bytes` | `8_589_934_592`（8 GiB） |

### 5.2 A6 / A7 差异字段

| 字段 | A6 | A7 |
|---|---|---|
| `manifest_id` | `a6-seed-6922` | `a7-seed-7926` |
| `game.player_count` | 6 | 7 |
| `execution.kind` | `a6-a7-training` | `a6-a7-training` |
| `execution.iterations` | `1000` | `300` |
| `execution.average_strategy_start_iteration` | `100` | `30` |
| `execution.master_seed` | `6922` | `7926` |
| `budget.cpu_limit_milliseconds` | `1_140_000`（19 min） | `4_740_000`（79 min） |
| `budget.retained_artifact_limit_bytes` | `8_388_608`（8 MiB） | `16_777_216`（16 MiB） |
| `budget.stages[training]` | `600_000` | `900_000` |
| `budget.stages[export]` | `60_000` | `120_000` |
| `budget.stages[profile]` | `120_000` | `600_000` |
| `budget.stages[probe]` | `300_000` | `3_000_000` |
| `budget.stages[measurement]` | `60_000` | `120_000` |
| stages 之和（同时是父端墙钟硬限） | `1_140_000` | `4_740_000` |
| `artifacts.strategy.relative_name` | `strategy.json` | `strategy.json` |
| `artifacts.strategy.maximum_bytes` | `4_194_304`（4 MiB，静态上限） | `12_582_912`（12 MiB，静态上限） |
| `artifacts.measurement.relative_name` | `measurement.json` | `measurement.json` |
| `artifacts.measurement.maximum_bytes` | `1_048_576`（1 MiB） | `1_048_576`（1 MiB） |

约束自检（写入前必须复算）：

- `2 × measurement.maximum_bytes + strategy.maximum_bytes ≤ retained_artifact_limit_bytes`：A6 `2×1_048_576 + 4_194_304 = 6_291_456 ≤ 8_388_608` ✓；A7 `2×1_048_576 + 12_582_912 = 14_680_064 ≤ 16_777_216` ✓。
- `strategy.maximum_bytes ≤ min(64 MiB, 人数静态预算)`：A6 `4 MiB ≤ 4 MiB` ✓；A7 `12 MiB ≤ 12 MiB` ✓。
- stages 必须**恰好**按 `training, export, profile, probe, measurement` 顺序排列 ✓。

### 5.3 Probe manifest 冻结字段

每个 epoch 人数对应一份 probe manifest（`player_count` 必须等于 experiment 的 `player_count`）。

| 字段 | 值 |
|---|---|
| `probes` | 两组（数量上限为 2） |
| probe 1 `probe_id` / `open_threshold` / `call_threshold` | `tight-open` / `4` / `3` |
| probe 2 `probe_id` / `open_threshold` / `call_threshold` | `loose-open` / `1` / `0` |

阈值语义：`open_threshold` 越高越少主动下注（越保守），`call_threshold` 越高越常弃牌。阈值必须落在 `0 ≤ t < player_count`，上述取值对 N=6 与 N=7 同时合法，因此两个 epoch 可共用同一组阈值、便于横向比较。

## 6. Campaign manifest 冻结字段

| 字段 | 值 |
|---|---|
| `campaign_id` | `m8-a-campaign-1` |
| `code_identity.git_commit` | **冻结 commit（与两个 experiment 一致）** |
| `code_identity.trainer_version` | `candidate-a-campaign-v1` |
| `preflight_attestation` | 由第 7 节 spec 实跑得到的 attestation 身份三元组 |
| `limits.cpu_limit_milliseconds` | `5_880_000`（98 min） |
| `limits.wall_limit_milliseconds` | `5_880_000`（98 min） |
| `limits.peak_rss_limit_bytes` | `8_589_934_592`（8 GiB，与单条 experiment 硬停同口径） |
| `limits.retained_artifact_limit_bytes` | `25_165_824`（24 MiB） |
| `limits.max_concurrency` | `1` |
| `authorizations[0]` | `a6-seed-6922` / A6 身份 / cpu `1_140_000` / wall `1_140_000` / artifact `8_388_608` |
| `authorizations[1]` | `a7-seed-7926` / A7 身份 / cpu `4_740_000` / wall `4_740_000` / artifact `16_777_216` |

约束自检：

- 预留总和 `1_140_000 + 4_740_000 = 5_880_000 ≤ 5_880_000` ✓
- 工件预留总和 `8_388_608 + 16_777_216 = 25_165_824 ≤ 25_165_824` ✓
- 每条 experiment 的 `rss_hard_limit_bytes`（8 GiB）`≤` campaign `peak_rss_limit_bytes`（8 GiB）✓
- `authorization_id` 按升序排列且不重复 ✓
- 总 CPU / 墙钟 98 min `< 120 min`（本机累计上限）✓

## 7. Preflight spec 冻结字段

| 字段 | 值 |
|---|---|
| `record_id` | `n6-estimator-preflight` |
| `code_identity.git_commit` | **冻结 commit（与 campaign 一致）** |
| `code_identity.trainer_version` | `candidate-a-campaign-v1` |
| `fixture_id` | `three-to-one-regret-v1`（代码固定值，不可改） |
| `sample_seeds` | `[0, 1, 2, 3, 4, 5, 6, 7]` |
| `target_infosets` | 三个 N=6 信息集键：相对座位 0 的根、相对座位 1 的 `b@0`、相对座位 2 的 `b@0\|c@1` |
| `regret_tolerance_micros` | `1_000_000` |
| `strategy_sum_tolerance_micros` | `1_000_000` |

该组合与既有测试使用的 fixture 完全一致，可复现出 `passed == true` 的 attestation。attestation 的 `record_id` 与 spec 相同，且必须由 `run_preflight` 真实执行产生，不得手工构造。

## 8. 目录与执行前置

| 项 | 值 |
|---|---|
| 冻结 commit 的工作树 | `/Users/bryanylliu/my4/holdem-practice` |
| Python 解释器 | `/Users/bryanylliu/my4/holdem-practice/tools/trainer/.venv/bin/python` |
| campaign root | `/Users/bryanylliu/my4/holdem-campaigns/m8-a-campaign-1` |
| 源 manifest / preflight 文件目录 | 同上目录下的 `source/` |
| 每条 authorization 的运行目录 | `<campaign root>/runs/<authorization_id>/`（`artifacts/`、`inputs/` 由代码创建） |

硬前置（代码已强制，违反即 fail-closed）：

1. 工作区完全干净——`git status --porcelain=v1 --untracked-files=all` 必须为空，因此**以上所有执行期输入都必须在工作树之外**，工作树内不得残留任何未提交文件。
2. 冻结 commit 必须等于启动时刻实际 `HEAD`，且同时等于两个 experiment manifest 与 campaign manifest 的 `code_identity.git_commit`。
3. 每条 authorization 只 lease 一次；run 目录只创建一次。
4. 本轮全部代码改动与 `docs/31`、`docs/31a` 文档必须先提交，否则工作区不干净。
5. `docs/31` 编号族只允许两个已提交文件（`31` 复核、`31a` 清单）；不得再新增同族文件，也不得让同名文件同时以两个路径存在。

## 9. 执行顺序（冻结后）

```text
1. 确认 C1–C6（已完成）
2. 提交 docs/31 与 docs/31a（代码改动已在 8f8d8fd 提交），记录新 HEAD
3. 在工作树之外建 campaign root 与 source/
4. 写 probe manifest（A6、A7 各一份）与两个 experiment manifest，code_identity 用第 2 步的 HEAD
5. 写 preflight spec（同一 commit）→ run_preflight → 写 attestation
6. 写 campaign manifest（引用第 4、5 步的真实身份）
7. 执行 authorization a6-seed-6922
8. 执行 authorization a7-seed-7926
9. 只按实际回执与封存清单记录结果
```

第 2 步之后工作区必须重新回到完全干净状态，否则第 7、8 步会被父端身份核验拒绝。

第 7、8 步之间不追加 seed、不重试、不重置预算。任一步失败即终止并报告。

## 10. 持续披露与解释边界

- macOS supervisor 是本机 `ps` 采样式进程组监督，**不是不可逃逸的内核级 containment**。
- campaign ledger 无哈希链；"不可重试"依赖代码流程而非账本自身的完整性证明。
- lease 守卫与门禁均为 **Python 级 API 约束**，不是对抗性安全边界；`run_manifested_experiment`、`manifest_executor` 与 `mccfr.train` 属训练原语，直接调用它们运行 A6/A7 属流程违规。
- estimator preflight **只覆盖 N=6**，A7 的 estimator 没有 preflight 证据。
- 本轮为单 seed，**不构成任何稳定性结论**。
- 即使 campaign 完成，候选 A 也不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 本文件中的墙钟数值是**单元测试 / 评测器口径的观察**，用于配置预算，不是资源基准，也不是 A6/A7 实验证据。
- 第 4 节 A7 probe 的 ≈22 min 是外推值，未实测；这也是 C1 选择 (C) 后仍保留失败可能的原因。
