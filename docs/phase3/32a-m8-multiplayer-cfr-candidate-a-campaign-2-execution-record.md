# 32a M8：多人 CFR 候选 A——campaign-2 执行记录

> 日期：2026-09-18。
>
> 本文件是 `docs/32` 的配套执行记录，沿用 `docs/30` D6 的拆分约定（`32a` 表示接在 `docs/32` 之后的追加文档）。`docs/32` 记录复核、修复、复验与重新冻结方案；本文件只记录**实际执行回执与封存清单**。`docs/20` 至 `docs/31`（含 `31a`）未被改写。
>
> 执行时的冻结提交：`4139c3a9b8a9a0bcd90cb4ada8456258b6f59983`（`docs/32` 与代码修复的提交）。执行期间工作区保持完全干净。
>
> **本文件记录的是受预算实验的实际回执；它仍然不是多人 Hold'em GTO、均衡、NashConv、exploitability、真实 EV 或生产可用性的证据。** 全部结论限于下文的固定抽象、固定预算与单 seed 口径。

## 1. 执行授权与边界

用户本轮授权：修复缺陷并补齐回归测试；新建 campaign-2 重跑 A6；A7 是否纳入由本人决定；命名与预算由本人依现状决定；seed 沿用 6922 / 7926；保留 campaign-1 记录；允许 commit、不允许 push；回归测试使用两组探针。

按 `docs/32` 第 8.3 节的决策，本轮 campaign-2 **包含** A6 与 A7 两条独立 authorization，且**先执行 A6、仅在其成功后才执行 A7**。两条均已执行并成功。

未扩预算、未转云、未转 GPU、未追加 seed、未重试 campaign-1 中已消耗的 `a6-seed-6922`、未修改冻结输入。

## 2. 执行前置核对

| 项 | 实测 |
|---|---|
| 工作区 | `git status --porcelain=v1 --untracked-files=all` 输出 0 行 |
| 实际 HEAD | `4139c3a9b8a9a0bcd90cb4ada8456258b6f59983` |
| campaign root | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-2`（工作树之外） |
| 只读复验 | 两条 authorization 的 experiment 身份、资源预留、preflight 证据全部通过，未获取 lease、未创建运行目录 |

## 3. 冻结输入身份（campaign-2）

`campaign.json`：`campaign_id = m8-a-campaign-2`，sha256 `bcd7709441bd1ddfc6b600f85ec5894913880223630219f6eff180ec85494d6a`，1376 字节。

| 文件 | id | sha256 | 字节 |
|---|---|---|---:|
| `source/a6-probe.json` | `a6-probe-tight-loose-r2` | `de4a66f7a7bf952903cba092e1cbc1865794cbb68a755ed00c1c12dea569d695` | 455 |
| `source/a7-probe.json` | `a7-probe-tight-loose-r2` | `5b698c6640e13a5da83f4292673aa1256122df584bbde86cca80528cf4d8d621` | 455 |
| `source/a6-experiment.json` | `a6-seed-6922-r2` | `46aca0e7ec2354a4629fb230d41430a25c2f70340a7063fe26832141d0b46e14` | 1293 |
| `source/a7-experiment.json` | `a7-seed-7926-r2` | `f97d9c46d0eaffb3c663123cc0e80e419b539d1fe5ea96ce96194aa1cf52d254` | 1296 |
| `source/preflight-spec.json` | `n6-estimator-preflight` | `ad7d3085845d8ea0693202d609d786d917653a628fa96eedfb9b6c5126e01db3` | 527 |
| `source/preflight-attestation.json` | `n6-estimator-preflight` | `a0133023077f2dc3dadc9fed5bec36e5752ba0f97ce7a2c2194fe7d12f57f194` | 1018 |

attestation 由 `run_preflight` 实跑产生，`passed = true`；它与 campaign manifest、两个 experiment manifest 及两份执行快照的 `code_identity.git_commit` 全部等于 `4139c3a9b8a9a0bcd90cb4ada8456258b6f59983`（已逐文件核验）。

## 4. A6（`a6-seed-6922-r2`）

### 4.1 回执与终态

| 项 | 值 |
|---|---|
| 父监督回执 | `completed` / `stop_reason = completed` / `exit_code = 0` / 无信号终止 |
| 墙钟 / CPU | `18_247 ms` / `18_090 ms` |
| 峰值 RSS（父端 `ps` 采样） | `31_735_808 B`（约 30.3 MiB） |
| 警告触发 | `false` |
| 终态 ledger | `leased` → `finalized(status = "completed")` |
| `final_measurement_sha256` | `8b2df27622634c6339e3164f2a9406841d1ffd1987bd6b9539207010d3b15b73` |
| `supervisor_receipt_sha256` | `4a1105301df551a70ed689aee3d00e2e53b5f821010bb9241e99c1fae128c74f` |

`final_inventory`（已按文件字节复算，与 ledger 逐项一致）：

| relative_name | byte_length | sha256 |
|---|---:|---|
| `measurement.json` | 12450 | `8b2df27622634c6339e3164f2a9406841d1ffd1987bd6b9539207010d3b15b73` |
| `strategy.json` | 401604 | `0bc874e35895e6d1456d3bb16fdf9bed9b80707be5e289069a9c3a0e86a5c5a7` |

### 4.2 训练与诊断

- 子端记录 `completed`，`completed_iterations = 1000 / iterations = 1000`；`average_strategy_start_iteration = 100`。
- 每座位信息集总数 1152；累计区间内的访问覆盖为：座位 0–5 分别访问 111 / 86 / 84 / 82 / 89 / 101 个信息集，visit 数 1661 / 1530 / 1411 / 1325 / 1149 / 1000。
- 重要性权重摘要：`maximum` 为 32×–512×，`p50` 为 1×，`p95` 为 2.96×–4.96×，`non_finite_count` 全为 0。

### 4.3 质量结果（预注册口径）

- full-chance profile：ordered deal 720，终局叶 20 672；各座位每手牌平均净效用（BB/hand，按相对座位顺序）
  `[+0.062849, −0.002576, −0.029859, −0.012986, +0.000269, −0.017697]`（严格常和，和为 0）。
- probe：绑定 `a6-probe-tight-loose-r2`（`tight-open` 4/3 与 `loose-open` 1/0）。
  `gains = [0, 0, 0, 0, 0, 0]`。
  双向 `results[].delta` 全为负：`loose-open` 为 `−0.0847 / −0.3365 / −0.4790 / −0.3085 / −0.5323 / −0.4833`，`tight-open` 为 `−0.0252 / −0.0920 / −0.1708 / −0.0727 / −0.1660 / −0.1421`（顺序同座位 0–5）。

## 5. A7（`a7-seed-7926-r2`）

### 5.1 回执与终态

| 项 | 值 |
|---|---|
| 父监督回执 | `completed` / `stop_reason = completed` / `exit_code = 0` / 无信号终止 |
| 墙钟 / CPU | `492_293 ms`（8 min 12 s）/ `487_630 ms`（8 min 8 s） |
| 峰值 RSS（父端 `ps` 采样） | `46_809_088 B`（约 44.6 MiB） |
| 警告触发 | `false` |
| 终态 ledger | `leased` → `finalized(status = "completed")` |
| `final_measurement_sha256` | `32aa3052d026be9a986c389bd098a68e43f29736533ae7026a8947935d1eb3e0` |
| `supervisor_receipt_sha256` | `91f0855a3f91464415c75f2a7c56f5cb0d2c045702cc7eb958fe4c6bd0367699` |

`final_inventory`（已按文件字节复算，与 ledger 逐项一致）：

| relative_name | byte_length | sha256 |
|---|---:|---|
| `measurement.json` | 15495 | `32aa3052d026be9a986c389bd098a68e43f29736533ae7026a8947935d1eb3e0` |
| `strategy.json` | 1145054 | `9091c1e56dac5034360e2728907a19dff2c710e6f2c79aa8326b6c7abbe7b9a3` |

### 5.2 训练与诊断

- 子端记录 `completed`，`completed_iterations = 300 / iterations = 300`；`average_strategy_start_iteration = 30`。
- 每座位信息集总数 3136；访问覆盖为：座位 0–6 分别访问 176 / 144 / 109 / 86 / 101 / 128 / 171 个信息集，visit 数 597 / 496 / 402 / 338 / 313 / 300 / 300。
- 重要性权重摘要：`maximum` 为 32×–512×，`p50` 为 1×–2.07×，`p95` 为 10.9×–32.0×，`non_finite_count` 全为 0。

### 5.3 质量结果（预注册口径）

- full-chance profile：ordered deal 5040，终局叶 718 988；各座位每手牌平均净效用
  `[−0.009483, −0.006776, +0.172092, +0.232448, +0.103706, −0.126777, −0.365210]`（严格常和，和为 0）。
- probe：绑定 `a7-probe-tight-loose-r2`。
  `gains = [+0.097016, 0, +0.007912, +0.015214, +0.064847, +0.183337, +0.361573]`（座位 0–6）。
  双向 `results[].delta`：
  - `loose-open` 全为负：`−0.2636 / −0.4148 / −0.3350 / −0.3998 / −0.3479 / −0.2416 / −0.0636`；
  - `tight-open` 多数为正：`+0.0970 / −0.0045 / +0.0079 / +0.0152 / +0.0648 / +0.1833 / +0.3616`。

## 6. 预注册判定（X = 0.05 BB/hand，`probes.gains`）

`docs/31a` 第 3.2 节冻结的判定线与钳位说明原样适用：`gains[p] = max(0, max over probes of delta)`，只反映"预注册阈值策略相对训练策略更强"的方向；反方向（阈值策略更差）只能从 `results[].delta` 读出。

| 运行 | `max_p gains[p]` | 按预注册口径的结论 |
|---|---:|---|
| A6（N=6，seed 6922） | `0.0` | **未观察到超过 0.05 的阈值偏离** |
| A7（N=7，seed 7926） | `0.361573`（座位 6） | **存在超过 0.05 的阈值偏离** |

A7 中超过 0.05 的座位为 0（+0.097016）、4（+0.064847）、5（+0.183337）、6（+0.361573）；座位 2（+0.007912）与 3（+0.015214）未超过，座位 1（`tight-open` 为 −0.0045）未超过。

按 `docs/31a` 第 3.3 节，该结果**如实报告**，不延长阶段预算、不修改 X、不更换 seed、不挑选通过的子集，也不把结论表述为均衡或 exploitability。

**如何理解这条偏离（严格限定）**：在固定的候选 A 抽象（unique-rank-single-open）、固定的 N=7、固定的 300 轮与固定 seed 下，把**单个**座位替换为一个不看对手历史、只按自身 rank 与公开阶段决策的预注册保守阈值策略（`tight-open` 4/3），可使该座位的每手牌平均净效用相对训练所得的量化平均策略提高最多 0.361573 个 BB。这只说明该有限 probe 集合在这些座位上存在可见缺口，**不是** best response、**不是** NashConv 或 exploitability、**不是**真实牌局 EV，也不代表存在可稳定利用的漏洞——probe 仅是两组人工预注册的固定策略。

## 7. 资源与预算核算

### 7.1 实测（父端 `ps` 采样回执，非静态估算）

| 运行 | 墙钟 | CPU | 峰值 RSS | 落盘工件合计 |
|---|---:|---:|---:|---:|
| A6 | 18 247 ms | 18 090 ms | 30.3 MiB | 414 054 B |
| A7 | 492 293 ms | 487 630 ms | 44.6 MiB | 1 160 549 B |
| 合计 | 510 540 ms（约 8.5 min） | 505 720 ms（约 8.4 min） | ≤ 44.6 MiB | 1 574 603 B（约 1.50 MiB） |

两条 authorization 均未触碰任何预算上限（`warning_triggered = false`，无阶段截止、无 RSS 硬停）。落盘工件总量约占 campaign 保留额度 24 MiB 的 6%，也远低于本机 1 GiB 保留上限。

一处需如实说明的口径细节：回执中的 `final_artifact_bytes` 在两次运行中都等于 `pre_final_inventory` 之和（A6 `401604 + 10725 = 412329`；A7 `1145054 + 13765 = 1158819`），即它是父端替换最终 measurement **之前**的采样值，不是最终落盘字节数。

### 7.2 预算合规

按本轮沿用的保守口径（预留上界计入）：

```text
campaign-1 A6（失败, 实际值未落盘）  ≤ 19 min
campaign-2 A6（实测 CPU 0.30 min）  ≤ 19 min
campaign-2 A7（实测 CPU 8.13 min）  ≤ 79 min
合计                                ≤ 117 min ≤ 120 min
```

实测已知部分：campaign-1 的 A6 未落盘、不可核算；campaign-2 两条合计实测 CPU 约 8.4 min。因此无论按预留上界还是按已落盘的实测值，本机累计 CPU 都未越过 2 小时上限。estimator preflight 的重演按 `docs/30` D3 不计入本机实验预算。

## 8. 与上一轮预估的偏差（如实更正）

`docs/31a` 第 4 节的锚点是**进程内评测器口径**的观察，本轮首次获得受监督运行的真实回执，两者偏差较大，记录如下：

| 项 | `docs/31a` 预估 | 本轮实测 | 说明 |
|---|---:|---:|---|
| A6 完整 profile + 两组 probe | 10.18 s + 69.04 s | 包含在整条 18.2 s 内 | 预估基于均匀混合策略，明显高于实际量化平均策略 |
| A7 完整 profile | 191.42 s | 包含在整条 492.3 s 内 | — |
| A7 两组 probe | 约 22 min（外推，未实测） | 包含在整条 8.2 min 内 | 外推值高估约 3 倍以上 |
| 树规模比 | "约 16 倍" | 信息集 3136 / 1152 ≈ 2.72 倍；full-chance 叶 718 988 / 20 672 ≈ 34.8 倍 | 原表述口径不清，两种比值分别为 2.7 与 34.8 |

结论：`docs/31a` 的预算是**偏保守**的，A6 / A7 都在远小于预留的时间内完成；但保守配置本身是 C1 选择 (C) 的直接后果，本轮不予下调，也不因此改判任何已确认决策。

## 9. 边界 7 核对（策略 artifact v1 未被写回测量结果）

两份 `strategy.json` 都保持确定性纯策略 JSON（`artifact_type = multiplayer-cfr-average-strategy`、`schema_version = 1`），其 `quality` 块为静态占位：

```text
quality = {coverage: {total_infosets: <1152|3136>, visited_infosets: 0}, full_chance: false,
           probe_gains: [0, ...], probe_manifest_id: "not-measured", profile_id: "not-measured",
           sample_count: 0, sample_seed: null, stability: {status: "not-measured"}, utilities: [0, ...]}
resources = {artifact_bytes: <401604|1145054>, elapsed_seconds: 0.0, peak_rss_bytes: 0, ...}
```

即：profile / probe 结果、真实资源、campaign 回执**没有**写回 v1 artifact，全部只存在于独立的 measurement 与 ledger 中。**任何读者都不得从 v1 artifact 的 `quality` / `resources` 块读出质量或资源结论**——它们是"未测量"占位。

## 10. 解释边界与不得声称

- 本轮结果限于固定抽象 `m8-unique-rank-single-open` / `m8-a-v1`、固定 N=6 与 N=7、固定 seed 与固定轮次的**单 seed** 运行。**不构成任何稳定性结论**（`docs/31a` D3.3：跨 seed 实验未执行）。
- 不得表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- macOS supervisor 是本机 `ps` 采样式进程组监督，**不是不可逃逸的内核级 containment**；campaign ledger 无哈希链，"不可重试"依赖代码流程而非账本自身的完整性证明；门禁均为 Python 级 API 约束，不是对抗性安全边界。
- estimator preflight 只覆盖 N=6；A7 的 estimator 没有 preflight 证据（D4.3 已接受）。
- profile 是对**指定抽象、指定量化策略、指定测量器**的收益基线；probe 是两组人工预注册的固定阈值策略，不是 best response。
- 本轮的两条成功运行**不**使 campaign-1 的失败变成"有价值的验证"：那仍是一次消耗了一条不可重试 authorization、未换回任何证据的失败（见 `docs/32` 第 7 节）。
- 本次修复本身由 173 条单元测试覆盖，但**单元测试不等于实验结果**；本轮实验成功只说明该缺陷已不再阻断受监督路径。

## 11. 本轮未做事项与留存

- 未执行 N9 boundary authorization（D4.4）；未执行跨 seed 稳定性实验（D3.3）。
- 未修改 `docs/20` 至 `docs/31`（含 `31a`）；未修改 `kuhn_cfr`、后端、前端、锁文件或真实数据库；未扩预算、未转云、未转 GPU。
- campaign-1 的全部记录（含失败的 `a6-seed-6922`、终态 ledger 与两份输入快照）**原样保留**，未删除、未改写。
- 本文写入后 HEAD 再次变化，但已产出的 A6 / A7 工件与 ledger 绑定的是执行时的冻结提交 `4139c3a9b8a9a0bcd90cb4ada8456258b6f59983`，该身份已固化在输入快照、measurement 与 campaign manifest 中，不因后续提交而改变。
