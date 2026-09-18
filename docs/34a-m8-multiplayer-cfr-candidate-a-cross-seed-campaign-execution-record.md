# 34a M8：多人 CFR 候选 A——跨 seed campaign 执行记录

> 日期：2026-09-18。
>
> 本文件是 `docs/34` 的配套执行记录，沿用 `docs/30` D6 的拆分约定（`34a` 表示接在 `docs/34` 之后的追加文档）。`docs/34` 记录决策、证据边界与冻结规格；本文件只记录**4 条 authorization 的实际回执、封存清单与事前注册的跨 seed 对照结果**。`docs/20` 至 `docs/33c` 未被改写。
>
> 执行时的冻结提交：`b566214b328a1c64f176be217ab60337ac7f8f9f`（`docs/34` 与 `measurement.py` 上限修复的提交）。执行期间工作区保持完全干净、HEAD 未变。
>
> **结果摘要：4 条 authorization 全部成功完成，这是候选 A 第一次产出多 seed 的可落盘质量记录。** 但必须同时记住：`probes.gains` 在 4 个 seed 上全部为 0 **不构成**收敛、均衡、NashConv、exploitability 或稳定性结论；策略概率的跨 seed 差异很大（详见第 5.4 节）。

## 1. 授权与执行顺序

按 `docs/34` 第 1 节记录的用户答复：Q10 = (c) 继续补证据、Q11 = 重开并授权新 campaign、Q12 = 统一 `measurement.py` 上限、Q13 = 暂缓、Q14 = 4 个 seed（含参考 7926）、Q15 = 20 min/条、Q16 = commit + push。

实际顺序：

```text
1. measurement.py 上限修复 + 回归测试（180 passed）
2. docs/34 第 1–9 节与上述修复一并提交 -> HEAD = b566214b328a1c64f176be217ab60337ac7f8f9f
3. push origin/master（af30918..b566214）
4. 生成 campaign-6 全部冻结输入 + 实跑 estimator preflight（passed = true）
5. 只读复验：通过，未获取 lease、未创建任何运行目录
6. 逐条执行 4 条 authorization（成功）
7. 事后只读跨 seed 对照（compare 脚本在工作树之外，仅读取已封存工件）
```

冻结输入、运行目录、驱动脚本、对照脚本与日志**全部位于工作树之外**（`/Users/bryanylliu/holdem-campaigns/m8-a-campaign-6/`）；工作树内只新增 `docs/34`、`docs/34a` 与本次 `measurement.py` 修复。

## 2. 执行前置核对

| 项 | 实测 |
|---|---|
| 工作区 | `git status --porcelain=v1 --untracked-files=all` 输出 0 行（生成、执行与对照前后均为 0） |
| 实际 HEAD | `b566214b328a1c64f176be217ab60337ac7f8f9f`（执行期间未变） |
| campaign root | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-6`（工作树之外） |
| 只读复验 | 4 条 authorization 的身份、资源预留、preflight 证据全部通过，`leased=no`，未创建任何运行目录、无 ledger |
| preflight | `run_preflight` 实跑，`passed = true`，`code_identity.git_commit = b566214…` |

## 3. 冻结输入身份（全部在 `b566214` 上重新生成）

`campaign.json`：`campaign_id = m8-a-campaign-6`，sha256 `9bb5bc7fd4092de233adbe7960c217ad3391570ceb3295b73ad373c4beb7b51d`，2157 字节。

| 文件 | id | sha256 | 字节 |
|---|---|---|---:|
| `source/probe-1215.json` | `a7-probe-tight-loose-c6-1215` | `5dc9302f1f6b9ae4f46eefcc682e6da591fad839be9c25b595e297e930e8f1d3` | 460 |
| `source/experiment-1215.json` | `a7-seed-1215-i1000` | `0606d4b7099e65fae31a3da37951bcd97f160f43d3bd30a3fce6138de55c8ee9` | 1304 |
| `source/probe-20260918.json` | `a7-probe-tight-loose-c6-20260918` | `5e6a98312830173800803caa1e92ac7495a66aeca6d866d013161599d8645fba` | 464 |
| `source/experiment-20260918.json` | `a7-seed-20260918-i1000` | `a54f5bb081ba72b392ed4c052ec1d2255131b13ba6afd68ea17c1da8fed0fa04` | 1316 |
| `source/probe-3311.json` | `a7-probe-tight-loose-c6-3311` | `e02d14bad8f34d473b8c9ffad9d68feca2b6bcfeb31cea3c8dc041caabfe29a5` | 460 |
| `source/experiment-3311.json` | `a7-seed-3311-i1000` | `897d1813cad6f53105f98fc0cd893242899cf2782c3af14e6e992f8bb4a8d625` | 1304 |
| `source/probe-7926.json` | `a7-probe-tight-loose-c6-7926-r4` | `2b1a736624714dc12fc292df3de360542a5ce223b5a51d373c83abacb1164c28` | 463 |
| `source/experiment-7926.json` | `a7-seed-7926-i1000-r4` | `860c7e6878ed73fa75fdb225879dc856a1341e9e0d26b4464957cab1196e06c8` | 1310 |
| `source/preflight-spec.json` | `n6-estimator-preflight` | `5d29a6e808b68ce97fa132377ca6e02d27aa21075acea2f8cf66fb7468331518` | 527 |
| `source/preflight-attestation.json` | `n6-estimator-preflight` | `3f3cc7dc8f8a5d2528b96f5aad1e88bb6afb0c18991a4fc73cbcf448946c6ab2` | 1018 |

4 条 authorization 的参数除 `master_seed` 外逐字相同（`player_count = 7`、`iterations = 1000`、`average_strategy_start_iteration = 100`），每条 cpu / wall 预留 `1 200 000 ms`（20 min）、工件预留 `16 777 216 B`；campaign `limits` 为 cpu / wall `4 800 000 ms`（80 min）、工件 `67 108 864 B`（64 MiB）、峰值 RSS 8 GiB。全部输入**未复用** campaign-2 / 3 / 4 / 5 的任何文件；未重试任何既有 authorization。

## 4. 逐条回执（父端监督）

4 条全部 `status = completed` / `stop_reason = completed` / `exit_code = 0` / 无信号终止，`warning_triggered = false`（未触及 CPU 上限、阶段墙钟、RSS 预警或硬停）。

| authorization | 墙钟 ms | CPU ms | 峰值 RSS B | 训练阶段 elapsed ms | measurement.json | strategy.json |
|---|---:|---:|---:|---:|---|---|
| `a7-seed-1215-i1000` | 334 995 | 331 040 | 55 296 000 | 7 003 | 15 724 B `8044d461…358f0b` | 1 143 244 B `126c038a…da75c7` |
| `a7-seed-20260918-i1000` | 415 406 | 403 780 | 49 070 080 | 5 336 | 16 710 B `603deac5…0677eb` | 1 142 938 B `a9a01f8c…bf32e9` |
| `a7-seed-3311-i1000` | 243 109 | 240 870 | 52 379 648 | 5 503 | 15 461 B `264e9193…23473f` | 1 143 373 B `e627eae3…4898a6` |
| `a7-seed-7926-i1000-r4` | 411 100 | 404 640 | 49 643 520 | 5 358 | 15 464 B `f13d146e…df8453` | 1 142 972 B `0f0b04cd…feb553` |

完整 sha256（父端回执原文）：

```text
a7-seed-1215-i1000       measurement 8044d4619de5eb82243f7788c82ed62c291546ea8078ead7699d70af25358f0b
                         strategy    126c038a0a4877c89ec312ee860605ac176709433d9bdd97e6978ea1f0da75c7
                         receipt     267d68cada24c6df…
a7-seed-20260918-i1000   measurement 603deac5fd5cd47cb989635244b5fc8d380832b8386d2853d6eded29620677eb
                         strategy    a9a01f8c1319fabccb1ef607582c0c0eeee2100c31891f8d32a8711e23bf32e9
                         receipt     df444286b7d972e2…
a7-seed-3311-i1000       measurement 264e9193b542f7645f0adf435915f4b9896727bbb514574eddc738ae3523473f
                         strategy    e627eae3a5c062a6dcb416d1fd9d3047303b0890b77c7c67d0d25794ee4898a6
                         receipt     81f49372ca266d0f…
a7-seed-7926-i1000-r4    measurement f13d146ed00ce1740b7ea160f75fcc5e97d6622d8b9db3344221d92209df8453
                         strategy    0f0b04cda6e002ed50a4f31c26cc1087018806055bbdab720e36a075fffeb553
                         receipt     2af8f4191a1f05e5…
```

- 子进程合并输出：4 条均为 `child_output_bytes = 0`（空串摘要 `e3b0c442…b855`）→ 成功路径**不产生任何输出**，诊断通道零开销。
- 终态 ledger：4 条均 `leased` → `finalized(status = "completed")`；`final_inventory` 与磁盘文件的 sha256/字节**逐项复算一致**。
- 子端 `supervisor_version = v2`。

## 5. 跨 seed 对照结果（`docs/34` 第 7.6 节事前注册的口径）

### 5.1 profile 值向量与终局叶计数

每手牌平均净效用（BB/hand，相对座位 0–6）：

| seed | `profile.utilities` | 终局叶 | 分子最大位数 |
|---|---|---:|---:|
| 1215 | `[+0.015882, −0.052914, −0.088474, +0.040020, +0.089767, +0.013687, −0.017969]` | 406 320 | 133 |
| 20260918 | `[−0.111931, −0.093357, −0.012635, +0.024692, +0.087904, +0.067094, +0.038234]` | 472 040 | 157 |
| 3311 | `[−0.085179, −0.063008, −0.004207, +0.088926, +0.024740, +0.061381, −0.022652]` | 255 081 | 129 |
| 7926 | `[−0.089260, −0.067165, −0.030841, +0.035470, +0.025627, +0.094592, +0.031576]` | 507 482 | 134 |

4 条的 `sum(utilities)` 以 `fractions.Fraction` 精确为 **0**（严格常和）。

逐座位跨 seed 窗口（min–max）：

| 座位 | min | max | 跨度 |
|---:|---:|---:|---:|
| 0 | −0.111931 | +0.015882 | 0.127813 |
| 1 | −0.093357 | −0.052914 | 0.040444 |
| 2 | −0.088474 | −0.004207 | 0.084266 |
| 3 | +0.024692 | +0.088926 | 0.064234 |
| 4 | +0.024740 | +0.089767 | 0.065027 |
| 5 | +0.013687 | +0.094592 | 0.080905 |
| 6 | −0.022652 | +0.038234 | 0.060885 |

### 5.2 probe 结果

4 个 seed 的 `probes.gains` **全部为 0**，故按 `docs/31a` §3.2 冻结口径（X = 0.05 作用于 `probes.gains`）：

| seed | `max_p gains[p]` | 结论 |
|---|---:|---|
| 1215 | `0.000000` | 未观察到超过 0.05 的阈值偏离 |
| 20260918 | `0.000000` | 未观察到超过 0.05 的阈值偏离 |
| 3311 | `0.000000` | 未观察到超过 0.05 的阈值偏离 |
| 7926 | `0.000000` | 未观察到超过 0.05 的阈值偏离 |

双向 `results[].delta` 在 4 个 seed、7 个座位上**全部为负**（即两组预注册阈值策略在该测量口径下都更差，两个方向都没有出现"阈值策略更强"）。范围示例：`loose-open` 约 `−0.109` 至 `−0.712`；`tight-open` 约 `−0.001` 至 `−0.284`。

### 5.3 可重放性（同 seed、跨 code_identity）

`a7-seed-7926-i1000-r4` 的 `strategy.json` sha256 = `0f0b04cda6e002ed50a4f31c26cc1087018806055bbdab720e36a075fffeb553`、1 142 972 B，与 campaign-5（冻结提交 `bd1483d`）**逐字节一致**；`profile.utilities`、终局叶 507 482、每座位访问覆盖（219/209/170/148/154/175/205）也与 `docs/33c` §8.4 逐项一致。

即：在本次的代码改动（仅 `measurement.py` 的校验上限与文档）下，同一 seed 产出**完全相同的策略字节**。这是"策略确定性可重放"的一次跨 code_identity 观察，**不是**质量或收敛结论。

需要区分的一致与不一致：**策略与质量结果一致**（策略字节、profile 值、终局叶、访问覆盖）；**测量值不一致**是计时本身——本次训练阶段 `elapsed_milliseconds = 5 358`，而 campaign-5 为 `5 295`，父端墙钟也不同（411 100 vs 414 312 ms）。这两项是运行时观测，不参与策略确定性。

### 5.4 策略概率的 L1 距离（全部 3 136 个信息集，精确有理数）

每座位支持集大小均为 1–2；非退化（至少两个正概率动作）信息集数为 2 863 / 2 834 / 2 873 / 2 835（共 3 136）。

| 对照 | `max_l1` | `mean_l1` | `p50` | `p95` | 分布完全相同的信息集 |
|---|---:|---:|---:|---:|---:|
| 1215 vs 20260918 | 2.000000 | 0.134345 | 0.000000 | 1.000000 | 2 348 / 3 136 |
| 1215 vs 3311 | 2.000000 | 0.112455 | 0.000000 | 1.000000 | 2 476 / 3 136 |
| 1215 vs 7926 | 2.000000 | 0.116036 | 0.000000 | 1.000000 | 2 414 / 3 136 |
| 20260918 vs 3311 | 2.000000 | 0.137840 | 0.000000 | 1.000000 | 2 380 / 3 136 |
| 20260918 vs 7926 | 2.000000 | 0.134364 | 0.000000 | 1.000000 | 2 321 / 3 136 |
| 3311 vs 7926 | 1.968479 | 0.115329 | 0.000000 | 1.000000 | 2 437 / 3 136 |

读法（严格限定）：约 **74%–79%** 的信息集在两个 seed 之间给出完全相同的量化策略；其余约 21%–26% 不同，其中 `p95 = 1.0` 意味着**至少 5% 的信息集在两个 seed 之间动作支持完全不同**（一侧把全部概率给一个动作、另一侧给另一个）。`max_l1 = 2.0` 即完全相反的决策。

### 5.5 抽样诊断

| seed | 每座位访问信息集 / visits | 重要性权重 `maximum_milli` 范围 | `p95_milli` 范围 |
|---|---|---|---|
| 1215 | 199/1845, 166/1667, 169/1524, 150/1397, 135/1210, 158/1118, 185/1000 | 64 000–951 742 | 4 934–8 000 |
| 20260918 | 234/1967, 197/1715, 177/1501, 143/1319, 159/1192, 190/1122, 217/1000 | 64 000–512 000 | 6 417–8 911 |
| 3311 | 185/1897, 152/1696, 134/1519, 117/1359, 135/1259, 143/1111, 173/1000 | 64 000–512 000 | 4 000–8 000 |
| 7926 | 219/1876, 209/1671, 170/1518, 148/1347, 154/1212, 175/1103, 205/1000 | 53 333–512 000 | 6 291–8 471 |

4 个 seed 的 `non_finite_count` 全为 0。

### 5.6 关于本轮测量记录长度的两点事实

1. 4 条记录中精确有理数的**分子最大位数分别为 133 / 157 / 129 / 134，全部超过旧上限 128**。即：这 4 条记录若在 `bd1483d` 之前执行，**每一条都会被 `experiment_record` 拒绝**。这为 `bd1483d` 的必要性提供了 4 个独立样本的直接证据。
2. 本轮最大值 157 **仍低于** `measurement.py` 的原上限 256；因此本轮 Q12 的统一修复**没有**被这 4 次运行实际触发。它消除的是两份 schema 的口径不一致，而不是修复一次已经发生的阻断——不得表述为"本轮证明了该修复必要"。

## 6. 如何解读（严格限定）

- 结果限于固定抽象 `m8-unique-rank-single-open` / `m8-a-v1`、固定 N=7、固定 1 000 轮、固定 `average_strategy_start_iteration = 100`，且只有 **4 个**预注册 seed。
- **`gains` 全为 0 与双向 `delta` 全为负**只说明：这两组**人工预注册的固定阈值策略**在 4 个 seed、全部座位上都没有发现增益，且在该测量口径下都更差。它**不是** best response、**不是** NashConv、**不是** exploitability，也**不代表不存在其它合法偏离**。
- **不得把"4 个 seed 都未观察到偏离"表述为稳健性或普适结论**：4 个 seed 是一个很小的预注册样本；`docs/31a` D3.3 定义的稳定性本身是**经验性诊断**，不是正确性或均衡质量。
- **不得把第 5.4 节的差异解释为"欠训练"或"未收敛"**：本轮没有做多轮次对照，也没有任何收敛判据；L1 差异只是"4 个采样轨迹下策略确实不同"这一事实。同理，也不得反过来把 `gains = 0` 解释为"已收敛"。
- **不得把第 5.3 节的字节一致表述为质量结论**：它只说明相同 seed 与相同参数下策略可重放。
- **跨 seed 稳定性在本切片是事后跨工件比较，不是代码内建的稳定性指标**：`measurement.py` 的 `stability` 字段只有校验、没有生产者，策略 artifact v1 的 `quality.stability` 恒为 `{"status": "not-measured"}`；任何读者都不得从 v1 artifact 读出稳定性结果。
- 本轮**仍不建立任何质量合格线**（Q10 = c）：第 5 节全部数值仍只是解释性指标。
- 本轮 **A6 与 N=6 未参与**，因此不能对 N=6 作任何跨 seed 陈述；`docs/34` 第 4.2 节的全部"不得声称"条目继续有效。
- 本轮 4 条成功**不改变**候选 A 不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略这一边界。
- 本轮成功也**不**把 campaign-1 / campaign-3 / campaign-4 的三次失败变成"有价值的探索"：那三次各消耗一条不可重试 authorization，其中 campaign-4 的评估结果算出来了却因校验器拒绝而无法落盘。

## 7. 预算核算（Q2 = b 口径，实测）

```text
campaign-1 A6（不可核算）            记 0            （记账约定，非"未消耗"）
campaign-2 A6 + A7（实测 CPU）       8.40 min
N9 boundary（实测 CPU 450 ms）       0.01 min
campaign-3 A7-1000（实测 CPU）       6.65 min
campaign-4 A7-1000-r2（实测 CPU）    6.61 min
campaign-5 A7-1000-r3（实测 CPU）    6.81 min
campaign-6 四条（实测 CPU 合计）     23.01 min
  └ 1215 5.52 / 20260918 6.73 / 3311 4.01 / 7926 6.74
合计实测                             51.49 min ≤ 120 min   （余约 68.5 min）
```

按预留上界口径：campaign-6 预留合计 80 min，冻结时剩余余量 91.52 min，未越限。campaign-6 落盘工件合计约 `4 × 1.15 MiB ≈ 4.6 MiB`，远低于 1 GiB 保留上限；峰值 RSS 最大 55 296 000 B（约 52.7 MiB），远低于 6 GiB 预警与 8 GiB 硬停。

一处必须如实说明：本轮为在共享预算内纳入 4 个 seed，把单条 envelope 从 A7-1000 原值 79 min **收紧**到 20 min（`docs/34` §7.3）。实测 4 条墙钟为 243–416 s，均在 `training` 240 s 与 `profile + probe` 780 s 的限额内，但这是**事后观察**，不构成"该 envelope 总是足够"的结论。

estimator preflight 的核验重演（生成时 1 次 `run_preflight` 实跑，加上只读复验、父端门禁与子端门禁的重演）按 `docs/30` D3 **不计入**本机实验预算。

## 8. 本轮未做事项与下一步

未做：

- 未修改 `kuhn_cfr`、后端、前端、锁文件或真实数据库；本轮代码改动只有 `measurement.py` 的校验上限与其测试。
- 未重试 campaign-1 的 `a6-seed-6922`、campaign-3 的 `a7-seed-7926-i1000`、campaign-4 的 `a7-seed-7926-i1000-r2`、campaign-5 的 `a7-seed-7926-i1000-r3`。
- 未执行 A6（N=6）的跨 seed 实验；未追加预注册 seed 之外的 seed；未执行 N9 长期训练或 N9 策略导出。
- 未修订质量判定门槛（Q10 = c）；未定下一步主线（Q13 暂缓）。
- 未改写 `docs/20` 至 `docs/33c`；campaign-1 至 campaign-5 的全部记录与工件原样保留。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**据本次多 seed 证据回到质量判定门槛的讨论**（`docs/34` 第 5 节 / `docs/33` 第 7 节），即决定 Q10 是否从 (c) 转为 (b)。若转为 (b)，必须写明三点：作用对象（`probes.gains` 还是双向 `results[].delta`）、是否区分 N=6 与 N=7、超线后的处置动作。与此同时仍建议保留一条主线选择（Q13：M8 收尾 / 候选 B / 生产接入前置清单 / 转 M6 中文教练）。

## 9. 持续披露

- macOS supervisor 是本机 `ps` 采样式进程组监督，**不是不可逃逸的内核级 containment**；子进程输出捕获是**父端合作式观察**，只保留受限尾部（8 KiB 字节 / 2 048 字符），不是安全边界。
- campaign ledger **无哈希链**；"不可重试"依赖代码流程，而非账本自身的完整性证明。
- lease 守卫与门禁均为 **Python 级 API 约束**，不是对抗性安全边界；`run_manifested_experiment`、`manifest_executor`、`mccfr.train`、`evaluate_profile` 属训练原语，直接调用属流程违规。
- 事后跨 seed 对照脚本位于工作树之外，**只读取已封存工件**，不启动训练、不修改任何工件；其指标定义在任何结果产生之前已写入 `docs/34` 第 7.6 节。
- **单元测试 / N9 boundary / estimator preflight 不等于 A6/A7 实验结果**；本轮 4 条成功也不构成质量、收敛或生产可用性结论。
