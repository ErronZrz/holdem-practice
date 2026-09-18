# 34b M8：多人 CFR 候选 A——N=6 跨 seed campaign 冻结与执行

> 日期：2026-09-18。
>
> 本文件接在 `docs/34` / `docs/34a` 之后，继续沿用 `docs/30` D6 的编号族约定：`docs/34` 记录决策与冻结规格、`docs/34a` 记录 campaign-6（N=7 跨 seed 四条）的执行回执；本文件补上**另一侧人数（N=6）的跨 seed 证据**，并记录预算口径的一处变更。
>
> 本文件**分两次提交**：第一次只写第 1 至第 8 节的授权、现状与冻结规格；第二次在执行完成后追加第 9 节的实际回执。这样写是为了让"冻结提交"早于任何受监督运行，避免文档自身改动打断工作树干净前置。
>
> **第 1 至第 8 节提交时，N=6 跨 seed campaign 尚未启动，不声称已生成任何新策略、质量或资源证据。** `docs/20` 至 `docs/34a` 未被改写。

## 1. 本轮授权与用户答复原文

用户答复原文：

> 我认可你的推荐：先补 N=6 的跨 seed 再说，决策四暂不做，其余部分先等跨 seed 完成再讨论。
>
> 关于决策五，我认为不用死守一个预算而在未来拒绝一些必要的轮次，未来允许放宽预算。

由此：

| 决策 | 答复 | 处置 |
|---|---|---|
| 决策一（质量判定门槛） | 先补证据 | **维持 (c)**：本轮仍不设任何合格线 |
| 决策二（下一步主线） | 等跨 seed 完成再讨论 | **暂缓** |
| 决策三（N=6 跨 seed） | 认可推荐 | **授权并执行**（本文件） |
| 决策四（代码内建稳定性指标） | 暂不做 | **不做**：本轮不改 `stability` 的生产者 |
| 决策五（预算口径） | 未来允许放宽预算 | **记录并变更口径**（见第 6 节） |

**本轮被授权**：新建冻结 campaign `m8-a-campaign-7`，以 4 个预注册 seed 补 N=6 的跨 seed 证据。

**未被授权**（继续有效）：不设质量合格线；不实现代码内建的稳定性指标；不转云、不转 GPU、不无限重跑；不重试任何已消耗 authorization；不追加预注册以外的 seed。

## 2. 前序状态（`docs/34a` 的结论摘要）

campaign-6（`m8-a-campaign-6`，冻结提交 `b566214`）的 4 条 authorization（N=7，seed 1215 / 20260918 / 3311 / 7926，1 000 轮）**全部成功完成**，这是候选 A 第一次产出多 seed 的可落盘质量记录：

- 4 条 `sum(utilities)` 精确为 0；`probes.gains` **全部为 0**、双向 `results[].delta` **全部为负**，按 `docs/31a` §3.2 口径（X = 0.05）四条均为「未观察到超过 0.05 的阈值偏离」；
- 策略概率的跨 seed 差异很大：约 74%–79% 的信息集在两 seed 间分布完全相同，其余不同，`p95 = 1.0`、`max_l1 = 2.0`；
- seed 7926 的 `strategy.json` 与 campaign-5（`bd1483d`）**逐字节一致**；
- 4 条记录的有理数分子最大位数 133 / 157 / 129 / 134，全部 > 128。

**由此暴露的缺口**：以上结论**只覆盖 N=7**。N=6 侧目前**只有 1 个 seed**（seed 6922，campaign-2），因此任何"区分 N=6 / N=7"的门槛口径在 N=6 上没有可验证的跨 seed 支撑。本文件补的正是这一侧。

## 3. N=6 现有证据边界（本轮不得扩张）

**已被证据支持**（全部来自 `docs/32a` 的落盘工件，本文件做的是复述）：

1. A6（N=6、seed 6922、1 000 轮、`average_strategy_start_iteration = 100`）一条受预算运行 `completed`；父端回执墙钟 18 247 ms / CPU 18 090 ms / 峰值 RSS 31 735 808 B。
2. 该条的 full-chance profile：ordered deal 720、终局叶 20 672、各座位 `utilities = [+0.062849, −0.002576, −0.029859, −0.012986, +0.000269, −0.017697]`，精确常和为 0。
3. 该条的 `probes.gains = [0, 0, 0, 0, 0, 0]`，双向 `delta` 全为负。
4. 落盘工件：`measurement.json` 12 450 B `8b2df276…b15b73`、`strategy.json` 401 604 B `0bc874e3…86a5c5a7`。

**未被证据支持**（本轮不得声称，也不得因本次执行而新增）：

- N=6 的**跨 seed 稳定性**（本轮才首次执行，结论以第 9 节回执为准）；
- N=6 与 N=7 之间的**横向可比性**：两者人数不同、树规模不同（信息集 1 152 vs 3 136、终局叶 20 672 vs 507 482），任何数值差异**不得**归因于人数，除非另行设计对照；
- N=9 的任何训练或质量结论（仍只有一次单 traverser 采样）；
- 收敛、均衡、NashConv、exploitability、best response、真实牌局 EV、生产可用性。

## 4. 冻结规格

### 4.1 seed 集合与 authorization（预注册，不得追加）

| authorization_id / experiment `manifest_id` | probe `manifest_id` | `master_seed` |
|---|---|---|
| `a6-seed-1215-i1000` | `a6-probe-tight-loose-c7-1215` | `1215` |
| `a6-seed-20260918-i1000` | `a6-probe-tight-loose-c7-20260918` | `20260918` |
| `a6-seed-3311-i1000` | `a6-probe-tight-loose-c7-3311` | `3311` |
| `a6-seed-6922-r3` | `a6-probe-tight-loose-c7-6922-r3` | `6922`（参考，在新 HEAD 上重跑） |

- 表中 4 个 seed **就是全部**：实验开始后不得追加、不得替换、不得重跑；
- authorization 已按 id 升序排列（`campaign.py` 的硬校验）；
- 4 条中前 3 个 seed 与 campaign-6 的 N=7 侧**同名**，便于两侧结构平行；但**不构成**跨人数的配对比较（人数不同）；
- `6922` 在新冻结提交上重跑，可与 campaign-2（`4139c3a`）的 A6 `strategy.json` sha256 `0bc874e3…86a5c5a7`（401 604 B）逐字对照——与 `docs/34a` 第 5.3 节对 7926 的做法相同，用于检验同一 seed 在同一参数下的可重放性。

### 4.2 参数与预算 envelope

参数（4 条逐字相同）：`player_count = 6`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`execution.kind = a6-a7-training`、`quality.profile_mode = full-chance`、probe 沿用 `tight-open`（4/3）与 `loose-open`（1/0）（与 `docs/31a` C5、campaign-2 的 A6 同值）。

| 项 | 值 |
|---|---|
| 阶段预算（ms） | `training 90_000` / `export 30_000` / `profile 60_000` / `probe 90_000` / `measurement 30_000` |
| stages 之和 = 父端墙钟硬限（ms） | `300_000`（5 min） |
| `budget.cpu_limit_milliseconds` | `300_000` |
| 工件预留 | `8_388_608`（8 MiB）；strategy 槽位 4 MiB、measurement 槽位 1 MiB |
| RSS | 预警 6 GiB、硬停 8 GiB |
| `max_concurrency` | `1` |
| campaign `limits` | cpu / wall `1_200_000`（20 min）、工件 `33_554_432`（32 MiB）、峰值 RSS 8 GiB |

约束自检：

- `2 × measurement.maximum_bytes + strategy.maximum_bytes = 2×1_048_576 + 4_194_304 = 6_291_456 ≤ 8_388_608` ✓；
- `strategy.maximum_bytes = 4 MiB ≤ min(64 MiB, A6 静态预算 4 MiB)` ✓；
- stages **恰好**按 `training, export, profile, probe, measurement` 顺序 ✓；
- 预留总和 `4 × 300_000 = 1_200_000 ≤ limits` ✓。

**envelope 依据与风险的如实披露**：A6 的实测单次成本是**墙钟 18 247 ms / CPU 18 090 ms**（`docs/32a`），本 envelope 相对它是约 16 倍；其中 `profile + probe` 合计 150 s，相对 A6 实测的评估部分（整条 18.2 s 减去训练 2.9 s，约 15 s）约为 10 倍。相比 `docs/34` §7.3 对 N=7 收紧到的 20 min/条，本次进一步收紧到 5 min/条，依据是 N=6 的树规模小得多（信息集 1 152、终局叶 20 672）。风险：若某个 seed 的评估显著慢于既有观测，该条 authorization 会因阶段墙钟触发而失败**并已永久消耗**。

### 4.3 目录与驱动脚本（全部在工作树之外）

| 项 | 值 |
|---|---|
| campaign 根 | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-7/` |
| 目录内约定 | `generate_frozen_inputs.py`、`run_campaign.py`、`source/`、`runs/<authorization_id>/{artifacts,inputs}`、`campaign.json`、`campaign-ledger.json` |
| Python 解释器 | `/Users/bryanylliu/my4/holdem-practice/tools/trainer/.venv/bin/python` |

`generate_frozen_inputs.py`：核对工作树干净与实际 HEAD，在内存中构造 4 份 probe manifest、4 份 experiment manifest、preflight spec、attestation 与 campaign manifest，**实跑一次 `run_preflight`** 并确认 `passed = true`，随后原子写入并回读逐项比对身份；拒绝覆盖既有文件。

`run_campaign.py`：默认只读复验（不获取 lease、不创建运行目录）；只有 `--execute <authorization_id>` 才消费一条 lease。日志按 authorization 分开且已存在不覆盖。沿用 `docs/33a` / `docs/33b` 记录的两条驱动缺陷教训（只读模式不得写执行日志；打印回执不得把 `SupervisedExecutionResult` 当作 `CampaignExecutionResult`）。

### 4.4 执行顺序与冻结前置

```text
1. 提交本文第 1–8 节 -> 记录新 HEAD（= 冻结提交）
2. 确认工作区重新完全干净（--untracked-files=all 为 0 行）
3. 在工作树之外建 campaign-7 根与 source/，生成并回读全部冻结输入（含实跑 preflight）
4. 只读复验 campaign-7（不获取 lease）
5. 逐条执行 4 条 authorization（每条 lease 一次，成功或失败均不重跑）
6. 只按实际回执写第 9 节
```

硬前置（代码已强制，违反即 fail-closed）：工作区完全干净；manifest 的 `code_identity.git_commit` 等于启动时刻实际 HEAD；全部输入与运行目录都在工作树之外；每条 authorization 只 lease 一次；**不复用**任何既有 campaign 的输入文件。

## 5. 预注册的 N=6 跨 seed 对照口径（在结果产生之前冻结）

与 `docs/34` §7.6 同构，对 4 条成功记录做**只读**比较：

1. **策略概率的 L1 距离**：对每一对 (seed i, seed j)，在**全部**信息集上（N=6 每座位 1 152 个，不抽样）计算 `Σ_a |p_i(a) − p_j(a)|`，报告每信息集最大值与均值/分位；概率以整数单位 `1e12` 表示，用 `fractions.Fraction` 精确计算。同时报告有效支持集大小与两两分布完全相同的信息集占比。
2. **profile 值区间**：逐座位报告 4 个 seed 的 `profile.utilities`（BB/hand）的 min–max 区间（精确有理数）。
3. **probe 结果区间**：逐座位报告 `probes.gains` 与双向 `results[].delta` 的 min–max 区间，以及按 X = 0.05 口径的"是否观察到超过 0.05 的阈值偏离"。
4. **终局叶计数与抽样诊断**：逐 seed 报告终局叶计数、每座位访问覆盖与重要性权重分位。
5. **可重放性**：seed 6922 本轮 `strategy.json` 的 sha256/字节数与 campaign-2 的对照。

**本口径不设任何合格线**（决策一维持 (c)）：区间窄不构成"稳定"结论、区间宽不构成"不稳定"结论；不得据此声称收敛、均衡、NashConv、exploitability 或真实 EV。同样**不得**把 N=6 的区间与 N=7 的区间直接比较并归因于人数。

## 6. 预算口径的变更记录（决策五）

**用户答复原文**：「不用死守一个预算而在未来拒绝一些必要的轮次，未来允许放宽预算。」

据此，本轮起记录以下口径变更：

| 项 | 变更前 | 变更后 |
|---|---|---|
| 硬约束 | 「本机累计 2 小时」（Q2 = b 口径，`docs/33` §8 / `docs/33c` §8.7 沿用） | **不再作为拒绝必要轮次的条件** |
| 每轮的实际做法 | 以累计余量倒推可用 envelope | 每轮按该项的实测锚点配置 envelope，**逐轮如实核算并披露**实际消耗与预留 |

**这不是无限制授权**，以下边界继续有效：

- 仍**不**转云、**不**转 GPU、**不**无限重跑、**不**追加预注册以外的 seed；
- 每条 authorization 仍**不可重试**，预算不因新启动进程而归零；
- 训练相关进程峰值 RSS 合计 8 GiB、保留实验工件 1 GiB 的上限**不变**；
- 每轮的预留与实测消耗仍必须在文档中逐项列出，不得只给结论。

**本轮的实际预算核算（供对照）**：campaign-7 预留合计 `4 × 5 min = 20 min`；按 A6 实测（18.2 s/次）预计实测约 `1.2 min`。截止本轮开始前的已落盘实测累计为 `51.49 min`（`docs/34a` §7）。按变更前口径，20 min 预留 + 51.49 min 累计 = 71.49 min ≤ 120 min，同样未越限——即**本轮并未实际使用这项放宽**，变更只影响未来轮次的可用空间。

## 7. 持续披露与不得声称

- macOS supervisor 是本机 `ps` **采样式进程组监督**，**不是不可逃逸的内核级 containment**；子进程输出捕获是**父端合作式观察**，只保留受限尾部（8 KiB 字节 / 2 048 字符），不是安全边界。
- campaign ledger **无哈希链**；"不可重试"依赖代码流程，而非账本自身的完整性证明；lease 守卫与门禁均为 **Python 级 API 约束**，不是对抗性安全边界；训练原语（`run_manifested_experiment`、`manifest_executor`、`mccfr.train`、`evaluate_profile` 等）**直接调用属流程违规**。
- 跨 seed 稳定性在本切片仍是**事后跨工件比较**，不是代码内建的稳定性指标（决策四未授权实现）：`measurement.py` 的 `stability` 字段只有校验、没有生产者，策略 artifact v1 的 `quality.stability` 恒为 `{"status": "not-measured"}`，任何读者都不得从中读出稳定性结果。
- **单元测试 / estimator preflight 不等于 A6/A7 实验结果**；本轮 4 条成功也不构成质量、收敛或生产可用性结论。
- 必须如实延续三次 A7 加轮失败的代价记录（campaign-1 / campaign-3 / campaign-4），不得写成"验证了链路"或"有价值的探索"。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**

## 8. 本轮未做事项（截至本文提交）

- 未修改任何代码或测试（本轮唯一改动是新增本文档）；`kuhn_cfr`、后端、前端、锁文件、真实数据库均未触碰。
- 未实现代码内建的稳定性指标（决策四暂不做）。
- 未执行 N=6 跨 seed campaign（在第 4.4 节第 5 步才启动）；未重试 campaign-1 至 campaign-6 的任何 authorization。
- 未修订质量判定门槛（决策一维持 (c)）；未定下一步主线（决策二暂缓）。
- 未改写 `docs/20` 至 `docs/34a`；既有 campaign 记录与工件原样保留。

## 9. N=6 跨 seed 的实际回执（第二次提交追加）

### 9.1 结论摘要

**4 条 authorization 全部成功完成，这是候选 A 第一次产出 N=6 的多 seed 质量记录；并且它给出了本次切片最重要的发现：判定结果随 seed 反转。**

1. 4 条均 `completed`，`sum(utilities)` 精确为 0；
2. **seed 1215 出现超线偏离**：`probes.gains = [+0.805839, 0, 0, +0.328938, 0, 0]`，按 `docs/31a` §3.2 的 X = 0.05 口径为「**存在超过 0.05 的阈值偏离**」；其余 3 个 seed（20260918 / 3311 / 6922）为「未观察到超过 0.05 的阈值偏离」；
3. 即：**同一固定抽象、同一 N=6、同一 1 000 轮与同一预热下，只换 `master_seed`，预注册口径的判定就从"未观察到"翻转为"存在"**。因此单 seed 的判定**不能**作为合格/不合格依据；
4. seed 6922 的策略与 campaign-2 的 A6 **逐字节一致**（401 604 B、同 sha256），profile 值、终局叶与双向 `delta` 也与 `docs/32a` §4.3 逐项一致——完整重现了 campaign-2 的 A6 证据；
5. 以上**仍然不是**收敛、均衡、NashConv、exploitability 或生产可用性证据；第 9.7 节的严格限定全部适用。

### 9.2 冻结输入身份（全部在 `eda4f9c` 上重新生成）

`campaign.json`：`campaign_id = m8-a-campaign-7`，sha256 `68d1b6f217431b203dbbcbffe7b8b9b123e63bdb4752d062c75a4df03fe17950`，2133 字节。preflight 由 `run_preflight` 实跑，`passed = true`，`code_identity.git_commit = eda4f9c…`。

| 文件 | id | sha256 | 字节 |
|---|---|---|---:|
| `source/probe-1215.json` | `a6-probe-tight-loose-c7-1215` | `d05a3311d65fb7f853e88357248b9e1995a131e6c2a1224375c22160ad8bdf5a` | 460 |
| `source/experiment-1215.json` | `a6-seed-1215-i1000` | `46fa19b7a24ecaddeaa5fbf1c29e812a773155461cd96a6ad8ed527f94660cc6` | 1297 |
| `source/probe-20260918.json` | `a6-probe-tight-loose-c7-20260918` | `5b621a082d9eb2ef2ed2b7a57bd65273b09d4cafd8360a4a6f6a669837f34493` | 464 |
| `source/experiment-20260918.json` | `a6-seed-20260918-i1000` | `33ccc156bb322d0f4790241f523047ebe7997c8f7d3fe24a9de8e8922fe2df6d` | 1309 |
| `source/probe-3311.json` | `a6-probe-tight-loose-c7-3311` | `0911661feecfcf818f4496b4de953173c60a0d68bb7973e7fc0166fa6d6c2eb0` | 460 |
| `source/experiment-3311.json` | `a6-seed-3311-i1000` | `b50b2b0da25bf3dbb9b994a445ce10fabfc0a3b96bc00e04b323a25319de53ac` | 1297 |
| `source/probe-6922.json` | `a6-probe-tight-loose-c7-6922-r3` | `84a46351330f6767e290f40c05b884f4cc3c4710ecdeddfcda20e13b0a4345d3` | 463 |
| `source/experiment-6922.json` | `a6-seed-6922-r3` | `e7201d606784fc0898942835fb4d8b26b8ff4ac0a6e135f238f5394b82861562` | 1297 |
| `source/preflight-spec.json` | `n6-estimator-preflight` | `4c09ef1f4b2fc45e4fc56d2b814e35f20325f1c92093753430b0e0972a142944` | 527 |
| `source/preflight-attestation.json` | `n6-estimator-preflight` | `a18a0c49076453f1c1cddceb918baf57baf8b1bc269473a734a3aaa9a1201b6f` | 1018 |

4 条 authorization 的参数除 `master_seed` 外逐字相同（`player_count = 6`、`iterations = 1000`、`average_strategy_start_iteration = 100`），每条 cpu / wall 预留 `300 000 ms`（5 min）、工件预留 `8 388 608 B`；campaign `limits` 为 cpu / wall `1 200 000 ms`（20 min）、工件 `33 554 432 B`（32 MiB）、峰值 RSS 8 GiB。**未复用** campaign-2 至 campaign-6 的任何输入文件；未重试任何既有 authorization。

### 9.3 逐条回执（父端监督）

4 条全部 `completed` / `stop_reason = completed` / `exit_code = 0` / 无信号终止，`warning_triggered = false`（未触及 CPU 上限、阶段墙钟、RSS 预警或硬停），`child_output_bytes = 0`。

| authorization | 墙钟 ms | CPU ms | 峰值 RSS B | 训练阶段 ms | measurement.json | strategy.json |
|---|---:|---:|---:|---:|---|---|
| `a6-seed-1215-i1000` | 18 321 | 17 820 | 32 948 224 | 2 995 | 13 126 B `82c77b9b…e06412` | 401 598 B `fbd4f71c…5f37ac` |
| `a6-seed-20260918-i1000` | 21 904 | 21 500 | 32 718 848 | 3 093 | 13 165 B `1cb443fd…957b84` | 401 445 B `e6f506b4…267036` |
| `a6-seed-3311-i1000` | 27 286 | 26 930 | 32 194 560 | 2 947 | 13 442 B `04e0a0d8…8bd6ae` | 401 513 B `5509fdf7…57e00a` |
| `a6-seed-6922-r3` | 18 529 | 18 320 | 33 095 680 | 2 974 | 12 600 B `b52489fd…b32b42` | 401 604 B `0bc874e3…86a5c5a7` |

完整 sha256 与父端回执原文：

```text
a6-seed-1215-i1000       measurement 82c77b9b00857df7754216264d4b597d67a109b999a776c88bf00296afe06412
                         strategy    fbd4f71ccbc23f8ad245a1c3dd0b93e66986d9e5381ec9f4fe9601bf345f37ac
                         receipt     699d83cf68ba32e632e9ef0a70c71438cfd2c3e82c08e45c93c1e8342f5b4fe7
a6-seed-20260918-i1000   measurement 1cb443fd27fde3dd7111a98218fd6a6a513c288f913276bce9ba272ac1957b84
                         strategy    e6f506b4ca710e97c7f189fc60bfe88ac51ae9fda66729b2b414d4eab8267036
                         receipt     df1693c619d956d163d8c20aafcaa357db15ba78746aff5130e75a4044ae09a9
a6-seed-3311-i1000       measurement 04e0a0d8870381f46685e089258907de448b029afc7423c7dca2d772168bd6ae
                         strategy    5509fdf70f80940c9cbe782df7a3f5a745ae6acb1071831f8d2bcdad6757e00a
                         receipt     bc50edd6aacd4f3a1a1d7721c39a31aae79ef71e02acfd0e9d9f491e39bb2267
a6-seed-6922-r3          measurement b52489fd5d23691b695465cff228ca027851a11410ee26df7c548ed46fb32b42
                         strategy    0bc874e35895e6d1456d3bb16fdf9bed9b80707be5e289069a9c3a0e86a5c5a7
                         receipt     6ba598dc7611042f0ee6aba130a989d3564b4dc894fbd109cc6f290d09cdf1ad
```

终态 ledger：4 条均 `leased` → `finalized(status = "completed")`；`final_inventory` 与磁盘文件的 sha256/字节**逐项复算一致**。子端 `supervisor_version = v2`。

### 9.4 质量结果（预注册口径）

| seed | `profile.utilities`（座位 0–5） | 终局叶 | 分子最大位数 |
|---|---|---:|---:|
| 1215 | `[+0.037243, −0.016175, −0.012495, +0.008229, −0.007337, −0.009465]` | 17 924 | 121 |
| 20260918 | `[−0.007813, −0.006927, −0.043943, +0.028494, +0.008678, +0.021511]` | 25 642 | 120 |
| 3311 | `[−0.048656, −0.020010, −0.048374, +0.044713, +0.081681, −0.009355]` | 38 421 | 120 |
| 6922 | `[+0.062849, −0.002576, −0.029859, −0.012986, +0.000269, −0.017697]` | 20 672 | 110 |

4 条 `sum(utilities)` 以 `fractions.Fraction` 精确为 **0**。ordered deal 均为 720。

`probes.gains` 与双向 `results[].delta`（座位 0–5）：

| seed | `gains` | `loose-open` delta | `tight-open` delta |
|---|---|---|---|
| 1215 | `[+0.805839, 0, 0, +0.328938, 0, 0]` | `[+0.805839, −0.737195, −0.348910, +0.328938, −0.512568, −0.736942]` | `[+0.160267, −0.233903, −0.167716, +0.023752, −0.183449, −0.238766]` |
| 20260918 | `[0, 0, 0, 0, 0, 0]` | `[−0.707201, −0.646676, −0.226977, −0.167230, −0.703166, −0.733546]` | `[−0.220863, −0.212635, −0.082016, −0.081912, −0.216290, −0.237853]` |
| 3311 | `[0, 0, 0, 0, 0, 0]` | `[−0.675680, −0.675052, −0.673262, −0.494762, −0.567044, −0.681279]` | `[−0.178736, −0.195042, −0.175046, −0.133913, −0.168196, −0.181974]` |
| 6922 | `[0, 0, 0, 0, 0, 0]` | `[−0.084731, −0.336459, −0.479041, −0.308508, −0.532295, −0.483283]` | `[−0.025205, −0.092041, −0.170782, −0.072681, −0.166034, −0.142132]` |

判定（X = 0.05 作用于 `probes.gains`，`docs/31a` §3.2）：

| seed | `max_p gains[p]` | 结论 |
|---|---:|---|
| 1215 | `0.805839`（座位 0） | **存在超过 0.05 的阈值偏离** |
| 20260918 | `0.000000` | 未观察到超过 0.05 的阈值偏离 |
| 3311 | `0.000000` | 未观察到超过 0.05 的阈值偏离 |
| 6922 | `0.000000` | 未观察到超过 0.05 的阈值偏离 |

### 9.5 跨 seed 对照（第 5 节事前注册的口径）

profile 值逐座位跨 seed 窗口：

| 座位 | min | max | 跨度 |
|---:|---:|---:|---:|
| 0 | −0.048656 | +0.062849 | 0.111505 |
| 1 | −0.020010 | −0.002576 | 0.017433 |
| 2 | −0.048374 | −0.012495 | 0.035879 |
| 3 | −0.012986 | +0.044713 | 0.057699 |
| 4 | −0.007337 | +0.081681 | 0.089018 |
| 5 | −0.017697 | +0.021511 | 0.039208 |

策略概率的 L1 距离（全部 1 152 个信息集，不抽样；支持集大小均为 1–2，非退化信息集 953–967）：

| 对照 | `max_l1` | `mean_l1` | `p50` | `p95` | 分布完全相同的信息集 |
|---|---:|---:|---:|---:|---:|
| 1215 vs 20260918 | 2.000000 | 0.138021 | 0.000000 | 1.000000 | 837 / 1 152 |
| 1215 vs 3311 | 2.000000 | 0.157867 | 0.000000 | 1.000000 | 792 / 1 152 |
| 1215 vs 6922 | 2.000000 | 0.147763 | 0.000000 | 1.000000 | 851 / 1 152 |
| 20260918 vs 3311 | 2.000000 | 0.163451 | 0.000000 | 1.000000 | 769 / 1 152 |
| 20260918 vs 6922 | 2.000000 | 0.147384 | 0.000000 | 1.000000 | 824 / 1 152 |
| 3311 vs 6922 | 2.000000 | 0.178779 | 0.000000 | 1.000000 | 767 / 1 152 |

即约 **67%–74%** 的信息集在两 seed 间分布完全相同，其余不同，`p95 = 1.0`、`max_l1 = 2.0`——与 `docs/34a` 第 5.4 节在 N=7 上看到的量级相当。每座位访问覆盖与重要性权重摘要见运行日志与 `runs/*/artifacts/measurement.json`；4 条 `non_finite_count` 全为 0。

### 9.6 可重放性（同 seed、跨 code_identity）

`a6-seed-6922-r3` 的 `strategy.json` sha256 = `0bc874e35895e6d1456d3bb16fdf9bed9b80707be5e289069a9c3a0e86a5c5a7`、401 604 B，与 campaign-2（冻结提交 `4139c3a`）的 A6 **逐字节一致**；profile 值、终局叶 20 672、双向 `delta` 也与 `docs/32a` §4.3 逐项一致。测量值（墙钟 18 529 ms vs 18 247 ms）不同，属运行时观测，不参与策略确定性。

### 9.7 如何解读（严格限定）

- 结果限于固定抽象、固定 N=6、固定 1 000 轮与固定预热，且只有 **4 个**预注册 seed。
- 第 9.4 节的超线**只针对两组人工预注册的固定阈值策略**（`loose-open` 在座位 0、3 为正；`tight-open` 在座位 0 为正）。它**不是** best response、**不是** NashConv、**不是** exploitability，也不代表存在可稳定利用的漏洞。
- **不得**把 seed 1215 的超线与 N=7 侧"4 个 seed 均未观察到偏离"直接比较并归因于人数：两侧在人数与树规模（信息集 1 152 vs 3 136）上不同，本轮**没有**为此设计对照；3 个共同 seed（1215 / 20260918 / 3311）上判定不同这一观察，同样**不能**归因。
- **不得**把第 9.5 节的 L1 差异或本节的判定反转解释为"欠训练"或"未收敛"：本轮没有做多轮次对照，也没有任何收敛判据；反之也不得把"3 个 seed 未观察到偏离"解释为稳定。
- 本轮结论**不改变**候选 A 不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略这一边界；`docs/34` 第 4.2 节与第 5 节的"不得声称"条目继续有效。
- **对门槛讨论的直接后果**：若把 X = 0.05 的线当作"合格/不合格"依据，则在 N=6 上仅凭 seed 就会在同一套参数下给出相反判定。因此任何门槛若要成立，必须先规定"以多 seed 结论为准、单 seed 不判定"，并以更多 seed 估计反转频率——这正是决策一维持 (c) 的额外理由。
- 一处与长度的对照事实：本轮 4 条记录的有理数分子最大位数为 110–121，**全部 ≤ 128**；即仅 N=6 不会触发 `bd1483d` 之前的旧上限，这与 `docs/33b` 第 8.5 节"N=6 理论位数上界约 132、处于边缘"的判断一致（N=7 侧则 4 条全部超线）。

### 9.8 预算核算

```text
campaign-7 预留合计（4 × 5 min）                 20.00 min
campaign-7 实测 CPU 合计                         1.41 min
  └ 1215 0.30 / 20260918 0.36 / 3311 0.45 / 6922 0.31
本轮开始前已落盘实测累计（docs/34a §7）          51.49 min
累计实测                                         52.90 min
```

落盘工件合计约 `4 × 0.41 MiB ≈ 1.66 MiB`；峰值 RSS 最大 33 095 680 B（约 31.6 MiB）。按变更前口径（累计 ≤ 120 min）本轮同样合规——即**本轮并未实际使用决策五的放宽**。estimator preflight 的核验重演按 `docs/30` D3 **不计入**本机实验预算。

### 9.9 未做事项与下一步

未做：

- 未修改任何代码或测试；未实现代码内建的稳定性指标（决策四暂不做）；未修改 `kuhn_cfr`、后端、前端、锁文件或真实数据库。
- 未重试 campaign-1 至 campaign-6 的任何 authorization；未追加预注册 seed 之外的 seed；未执行 N9 长期训练或 N9 策略导出。
- 未修订质量判定门槛（决策一维持 (c)）；未定下一步主线（决策二暂缓）。
- 未改写 `docs/20` 至 `docs/34a`；既有 campaign 记录与工件原样保留。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**回到决策一与决策二**。现在两侧（N=6 / N=7）都有 4 个 seed 的证据，且本轮首次给出了"判定随 seed 反转"的直接观察，足以支撑一次正式的门槛讨论：

1. 若定门槛，必须同时写入"以多 seed 结论为准、单 seed 不判定"，并明确作用对象（`probes.gains` 还是双向 `results[].delta`）、是否区分 N=6 / N=7、超线后的处置动作；
2. 若暂不设门槛，则把候选 A 的结论如实收尾为"固定抽象下、两侧各 4 个 seed 的一次观察：N=7 未观察到偏离，N=6 在 1/4 个 seed 上观察到"；同时按决策二选择下一步主线（M8 收尾 / 候选 B / 生产接入前置清单 / 转 M6 中文教练）。

### 9.10 持续披露（延续）

- macOS supervisor 是本机 `ps` 采样式进程组监督，**不是不可逃逸的内核级 containment**；campaign ledger **无哈希链**；lease 守卫与门禁均为 **Python 级 API 约束**；训练原语直接调用属流程违规。
- 跨 seed 稳定性仍是**事后跨工件比较**，不是代码内建的稳定性指标；策略 artifact v1 的 `quality.stability` 恒为 `{"status": "not-measured"}`。
- 事后对照脚本位于工作树之外，只读取已封存工件；其指标定义在任何结果产生之前已写入本文件第 5 节。
- 本轮 4 条成功**不**把 campaign-1 / campaign-3 / campaign-4 的三次失败变成"有价值的探索"；也不构成质量、收敛或生产可用性结论。
