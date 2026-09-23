# 33 M8：多人 CFR 候选 A——质量判定口径复核与 N9 边界授权

> 日期：2026-09-18。
>
> 本文件是 M8 候选 A 收尾轮的**只读复核与决策记录**：冻结候选 A 当前真实证据边界、如实更正上一轮交接中的一处口径错误、记录用户对本轮六项决策的答复，并写明在两个子项获得一次性授权后的执行规格与禁止项。
>
> 实际执行回执另记于 `docs/33a`（沿用 `docs/30` D6 的拆分约定）。`docs/20` 至 `docs/32a`（含 `31`、`31a`、`32`、`32a`）未被改写。
>
> **本文提交时，N9 boundary 与 A7 加轮 campaign 均尚未启动；本文不声称已生成任何新策略、质量或资源证据。** 既有 A6/A7 事实全部来自 `docs/32a` 的落盘工件，本文对其做的是**复算与对账**，不是重跑。

## 1. 本轮授权边界与用户答复原文

用户本轮答复（原文照录）：

| 编号 | 问题 | 用户答复 |
|---|---|---|
| Q1 | 质量判定门槛 | 「我倾向 (c)」——**先补证据再定门槛** |
| Q2 | 预算口径 | 「(b)，不可核算消耗暂不确定如何处理」——**本机累计口径，campaign-1 不可核算部分暂记 0** |
| Q3 | 是否授权 N9 边界实跑 | 「是」 |
| Q4 | Task 3 第二子项 | 「先尝试 (c) 到 1000」——**加大 iterations，A7 重训到 1000 轮** |
| Q5 | 下一步主线 | 「暂不决定」 |
| Q6 | commit / push | 「允许 commit + push」 |

由此**被授权**的事项：按第 6 节规格执行 N9 boundary 一次；按第 7 节规格新建一轮冻结 campaign 并把 A7 重训到 1000 轮；在文档定稿后 commit 并 push。
**被拒绝或未决**的事项：本轮**不设**任何质量合格线（Q1 = c）；跨 seed 稳定性实验**不执行**（`docs/31a` D3.3 保持关闭）；下一步主线**未定**（Q5 暂缓，不在本轮推进候选 B / 生产接入 / M6）。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 5]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -9 --oneline
ce35dfb docs: record campaign-2 execution results
4139c3a fix: validate supervised measurement identity per manifest slot
dc79ee9 docs: correct 31/31a naming and finalize campaign freeze checklist
41c9d8a docs: record freeze readiness review and canonical campaign freeze checklist
8f8d8fd feat: enforce campaign preflight and reservation gates at supervised entry
9881050 docs: record execution integrity review and fixes
b9c4554 feat: harden campaign execution integrity
8601a4b feat: harden supervised campaign execution
9074b69 docs: record experiment readiness review

$ git rev-parse HEAD          -> ce35dfb866c180ddaeb066531837252e91b01a5e
$ git rev-parse origin/master -> 9881050a53fb6f8e7e74a998153b43910cd5dee6
```

与期望基线完全相符；未做任何 `reset` / `clean` / `stash` / `checkout`。

## 3. campaign-2 身份的只读对账（全部一致）

对 `docs/32a` 第 3 节与第 4、5 节的落盘事实逐项复算：

| 项 | 复算方式 | 结果 |
|---|---|---|
| `campaign.json` | `shasum -a 256` | `bcd7709441bd1ddfc6b600f85ec5894913880223630219f6eff180ec85494d6a`，1376 B，与 ledger 的 `campaign.sha256` 一致 |
| 6 份 `source/*.json` | `shasum -a 256` + `stat` | 与 `docs/32a` 第 3 节表**逐项**一致（含两份 probe / 两份 experiment / preflight spec 与 attestation） |
| 两份 `runs/*/inputs/{experiment,probe}.json` | `shasum -a 256` | 与 `source/` 同名文件同哈希，说明执行用的是同一份冻结输入 |
| A6 两份工件 | `shasum -a 256` | `measurement.json` `8b2df276…b15b73`（12 450 B）、`strategy.json` `0bc874e3…86a5c5a7`（401 604 B），与 `final_inventory` 一致 |
| A7 两份工件 | `shasum -a 256` | `measurement.json` `32aa3052…5d1eb3e0`（15 495 B）、`strategy.json` `9091c1e5…bbe7b9a3`（1 145 054 B），与 `final_inventory` 一致 |
| campaign-1 记录 | 读 ledger 与目录 | 仍为 `leased` → `finalized(status="failed")`、`final_inventory=[]`、`runs/` 下无工件；记录未被删除或改写 |

## 4. 质量数值的独立复算

用 `fractions.Fraction` 对 `measurement.json` 中的有理数字段做**精确**运算，不依赖浮点：

| 项 | A6（N=6, seed 6922, 1000 轮） | A7（N=7, seed 7926, 300 轮） |
|---|---|---|
| `profile.utilities`（精确求和） | `sum == 0` 精确成立 | `sum == 0` 精确成立 |
| profile 规模 | ordered deal 720 / 终局叶 20 672 | ordered deal 5 040 / 终局叶 718 988 |
| `probes.gains` | `[0, 0, 0, 0, 0, 0]` | `[0.097016, 0, 0.007912, 0.015214, 0.064847, 0.183337, 0.361573]` |
| `max_p gains[p]` | `0.0` | `0.361573`（座位 6） |
| 双向 `results[].delta` | `loose-open` 六座位全负；`tight-open` 六座位全负 | `loose-open` 七座位全负；`tight-open` 除座位 1（−0.0045）外为正 |

结论：`docs/32a` 第 4.3、5.3、6 节的数值与磁盘工件**完全一致**；`docs/31a` 第 3.2 节冻结的 X = 0.05 口径下，A6 为「未观察到超过 0.05 的阈值偏离」、A7 为「存在超过 0.05 的阈值偏离」。本轮不改写该结论，也不把它升级为任何门禁判定。

## 5. 一处必须如实更正的交接口径

上一轮交接记录称「两条运行的回执只有总墙钟/总 CPU，没有逐阶段耗时，因此 A7 的 8.2 min 无法在训练与质量阶段之间归因」。经代码与工件核对，**该判断不准确**：

`measurement.json` 的 `child_execution.payload.resources` 来自 `control.RunResources`，其 `elapsed_seconds` 自**训练阶段**起点计时，`wall_time_limit_seconds` 即该阶段的墙钟预算。实测：

| 运行 | `payload.resources.elapsed_milliseconds` | 其 `wall_time_limit_milliseconds` | 对应阶段预算 | 父端总墙钟 |
|---|---:|---:|---|---:|
| A6 | 2 932 | 600 000 | A6 `training` = 600 000 | 18 247 |
| A7 | 1 471 | 900 000 | A7 `training` = 900 000 | 492 293 |

因此**训练阶段耗时是落盘的**，只是父端回执（`supervisor_receipt`）本身不含逐阶段细分。据此可作如下归因：

- A6：训练 2.93 s，其余约 15.3 s 在 export + profile + probe 与进程启动；
- A7：训练 **1.47 s（约 0.3%）**，其余约 **490.8 s（约 99.7%）** 在 export + profile + probe 与进程启动。

**该更正对解释有直接后果**：`docs/32a` 与上一轮交接把「A7 是否欠训练」列为待验证假设，但耗时证据**不支持**把 A7 的成本归因于训练——A7 的算力几乎全部花在质量评估上。因此：(1) 单纯加大 iterations 只改变那 1.47 s 的部分，**未必**能改变 A7 的 probe 结果；(2) 本轮 Q4 选择 (c) 是按「补证据」的目标执行，不预设它会消除偏离。真实证据仍以 `docs/33a` 的实跑回执为准。

另需注意：`payload.resources.peak_rss_bytes` 恒为 `0`（子端未采样自身 RSS），真实峰值 RSS 只来自父端 `ps` 采样回执（A6 31 735 808 B、A7 46 809 088 B）。

## 6. 候选 A 当前证据边界表（本轮冻结）

### 6.1 已被证据支持

1. **固定抽象与身份**：`game.id = m8-unique-rank-single-open`、`game.version = m8-a-v1`，冻结提交 `4139c3a9b8a9a0bcd90cb4ada8456258b6f59983`。
2. **两条单 seed 受预算运行完成**：A6（N=6, seed 6922, 1 000 轮）与 A7（N=7, seed 7926, 300 轮），`completed_iterations == iterations`，父端 `stop_reason = completed`、`exit_code = 0`、无信号终止。
3. **常和效用精确为零**：两份 full-chance profile 的 `utilities` 以有理数精确求和为 0。
4. **固定 evaluator 的 full-chance profile 值**：`candidate-a-full-chance-evaluator` / `v1`，`probability_units = 1e12`；A6 叶 20 672、A7 叶 718 988。
5. **两组预注册 probe 的 gains 与双向 delta**：见第 4 节表。
6. **受监督执行链在 A6/A7 上真实走通一次**：快照 → lease → 门禁 → 父子身份核验 → 独占工件根 → 父端最终 measurement → 封存清单；`final_inventory` 与磁盘逐字节复算一致。
7. **实测资源与工件字节**（父端 `ps` 采样）：A6 18 247 ms / 18 090 ms / 31 735 808 B；A7 492 293 ms / 487 630 ms / 46 809 088 B；工件合计 A6 414 054 B、A7 1 160 549 B。
8. **训练阶段耗时**（第 5 节更正）：A6 2 932 ms、A7 1 471 ms。

### 6.2 未被证据支持（不得声称）

- 任何**收敛、均衡、NashConv、exploitability、best response、真实牌局 EV、生产可用性**结论；
- **跨 seed 稳定性**（`docs/31a` D3.3 未执行，本轮仍不执行）；
- **N=9 的任何训练或质量结论**（此前只有单元测试路径，从未真实执行）；
- 真实 Hold'em 的**位置、范围、真实下注尺度、公共牌、all-in/边池、逐层多人平局与整数结算、短码 CALL 收益**；
- **A7 偏离的成因**（欠训练 vs 结构性缺口）：第 5 节的耗时归因反而削弱「欠训练」这一解释，但仍属假设；
- **A6 与 A7 的横向可比性**：人数（6 vs 7）与轮次（1 000 vs 300）均不同；
- campaign ledger 的**哈希链**完整性：不存在，"不可重试"仅依赖代码流程。

### 6.3 与既有质量口径文档的对应

| 本文结论 | 对应条款 |
|---|---|
| 只有守恒、固定 profile 值与有限 probe 集可报告 | `docs/26` §8 指标表 |
| `probe_gain = 0` 或未超 X 只是「这两个特定阈值策略未发现增益」 | `docs/26` §8、`docs/29` §4.2 |
| 严禁把常和、regret、归一化、单 seed 可重放、短路径测试表述为收敛或充分训练 | `docs/29` §4.3 |
| coverage/权重只是抽样诊断，不是有效样本量或均衡质量 | `docs/29` §4.1 |
| X = 0.05 BB/hand 是**解释边界**而非硬门禁；超线如实报告、不重跑、不改阈值、不换 seed | `docs/31a` §3.2 / §3.3、D3.4 |
| estimator preflight 只覆盖 N=6；A7 无 preflight 证据 | D4.3 |

## 7. 质量判定口径的现状（Q1 = c 的落地）

**本轮不建立任何质量合格线。** 现状如实记录为：

1. `docs/20` §9.3 把「CFR/教学上线质量门槛」留给实现轮约定，至今**未被约定**；
2. `docs/31a` D3.4 已明确 X = 0.05 BB/hand 只是**解释边界**，不是门禁；
3. 因此候选 A 在 N=6 / N=7 上「合格」目前**没有已签收的定义**；
4. 按 Q1 = (c)，本轮的动作是**先补证据**（即第 8 节的 N9 boundary 与第 9 节的 A7 加轮），据证据再约定门槛；在门槛被约定并签收之前，`gains` / `delta` 一律只作**解释性指标**报告。

若后续要建立门槛，必须先写明三点：作用对象（`probes.gains` 还是双向 `results[].delta`）、是否区分 N=6 与 N=7、超线后的处置动作。

## 8. 预算口径（Q2 = b 的落地）与累计核算

用户选定口径：**本机累计 2 小时**；campaign-1 那次不可核算的 A6 消耗**暂记 0**。

必须显式披露的两点：

1. 「暂记 0」是**记账约定**，不是「该次没有消耗算力」。campaign-1 的 `a6-seed-6922` 已**永久消耗、不可重试**，其 1 000 轮训练与质量评估算力**全部白费、未换回任何证据**（详见第 11 节）。
2. `docs/20` §9.2 原文是「每轮训练累计 ≤2 小时（同一轮的重试/断点续跑计入，不因新启动进程而归零）」。本轮采用的「本机累计」比该原文**更严**；该更严口径是 M8 前两轮的既成事实，本轮沿用并如实标注其与原文的差异。

累计核算（全部按预留上界计，除已落盘实测外）：

```text
campaign-1 A6（不可核算）           记 0          （记账约定；实际已消耗，算力白费）
campaign-2 A6 + A7（实测 CPU）      8.4 min
N9 boundary（cpu 预留上界）          5.0 min
campaign-3 A7-1000（cpu 预留上界）  79.0 min
合计                                92.4 min ≤ 120 min   （余约 27.6 min）
```

estimator preflight 的重演按 `docs/30` D3 **不计入**本机实验预算。

## 9. 子项甲：N9 boundary 一次性授权（Q3 = 是）

### 9.1 技术规格（已由现有代码承接，本轮不改代码）

- 入口：`run_supervised_manifest_executor`，且 `campaign_lease=None`、`preflight_spec_path=None`、`preflight_attestation_path=None`。`n9-boundary-sample` 是唯一**免 lease**路径；传入 preflight 证据会被拒绝。
- manifest：`execution = {kind: "n9-boundary-sample", iteration: 1, traverser: <0..8>, master_seed: <显式整数>}`；`quality = {profile_mode: "not-requested", probe_manifest: null}`；`artifacts.strategy = null`；`stages` 恰好为 `boundary, measurement` 且按该顺序；`game.player_count = 9`；`code_identity` 取**启动时刻实际 HEAD**、`workspace_state = "clean"`。
- 预算：`boundary` 300 000 ms、`measurement` 60 000 ms（两者之和即父端墙钟硬限 6 min，落在 `docs/29` §3.2 的 A9 10 分钟档内）；`cpu_limit_milliseconds` 300 000；`rss_warning_bytes` 6 GiB、`rss_hard_limit_bytes` 8 GiB；`measurement.json` `maximum_bytes` 524 288；`retained_artifact_limit_bytes` = 1 048 576（= 2 × measurement 上限，满足代码的峰值预留自检）。
- 目录：artifact 根与 snapshot 根必须是**新建空目录**，且**都在工作树之外**：`/Users/bryanylliu/holdem-campaigns/m8-a-n9-boundary/`（运行目录由代码创建）。它**不是 campaign**：不写 campaign manifest、不使用 lease、不建 ledger。
- 驱动脚本放在工作树之外；**无参数 = 只读校验**（不建目录、不启动子进程），必须拒绝覆盖已存在文件、拒绝重复执行。

### 9.2 记录口径与禁止项

只按实际回执写：单 traverser 采样的实际耗时、CPU、RSS、`boundary_infoset_count`、停止原因。**注意**：boundary 记录的 `coverage` 与 `importance_weights` 按代码设计为**空数组**（该路径不做诊断汇总），因此「访问覆盖」只能以 `boundary_infoset_count` 与结构性计数表达，不得伪造逐信息集覆盖。

禁止：长期 N9 训练、策略导出、profile / probe、把一次采样写成 A9 训练完成或质量通过。`docs/26` §11 记录的 N=9 结构性事实（20 736 个信息集、362 880 个 ordered deal、2 305 个终局历史、朴素全 chance 评估上界 836 438 400 叶）只能作为**结构性上界**引用，不是本轮测得的数字。

## 10. 子项乙：A7 加轮的新冻结 campaign（Q4 = c）

### 10.1 规格

- **新建一轮冻结 campaign**：`campaign_id = m8-a-campaign-3`，根目录 `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-3`（工作树之外）。
- 单条 authorization：`authorization_id = a7-seed-7926-i1000`；experiment `manifest_id` 同名；probe `manifest_id = a7-probe-tight-loose-i1000`。
- 参数：`player_count = 7`、`iterations = 1000`、`average_strategy_start_iteration = 100`（沿用 C4 的 10% 预热比例）、`master_seed = 7926`（沿用，便于与 300 轮结果直接对照）。
- 预算：envelope 与 A7 原值一致，`cpu / wall` = 4 740 000 ms（79 min）、工件预留 16 MiB、`strategy` 槽位 12 MiB、`measurement` 槽位 1 MiB、阶段 `training/export/profile/probe/measurement = 900 000 / 120 000 / 600 000 / 3 000 000 / 120 000`；RSS 阈值 6 GiB / 8 GiB；`max_concurrency = 1`。**不扩额**（既不上调也不下调）。
- 全部输入（probe / experiment / preflight spec / attestation / campaign）在**提交后的新 HEAD** 上**重新生成**并**重跑 preflight**；**不复用 campaign-2 的任何输入文件**，也**不重试** campaign-1 / campaign-2 已消耗的 authorization。

### 10.2 与 C1 / D4.3 的关系

- C1 选择 (C)：质量阶段超时按「整条失败、已声明工件清理」处理，不采用 (B)（不保留策略）。本轮沿用。
- D4.3：estimator preflight 只覆盖 N=6，A7 无 preflight 证据。新 campaign 的 preflight spec 仍是 N=6 口径，因此 A7-1000 **同样没有 estimator preflight 证据**，这一点不得因重跑 preflight 而被表述为「A7 已有 preflight」。
- 本轮**不**执行跨 seed 实验：`master_seed` 仍为 7926，不追加第二个 seed。

## 11. campaign-1 的 A6 失败：如实延续（不淡化）

- `a6-seed-6922` **已永久消耗**：不可重试、不可重置预算、不可追加 seed。
- 该次 1 000 轮训练与质量评估的算力**全部白费**，没有产出任何策略、质量或资源证据；策略 JSON 与子进程临时 measurement 已被 fail-closed 清理（`runs/a6-seed-6922/artifacts/` 为空）。
- 唯一留下的可用物是两份冻结输入快照与 ledger 中的失败事件。
- 根因：`supervised_measurement` 的私有身份判据对 **probe 槽位**复用了 experiment 专用期望类型，导致任何携带 probe manifest 的 A6/A7 受监督运行在父端最后一步必然失败；已于 `4139c3a` 修复并补齐回归测试（离线校验 173 passed）。
- **教训（保留原表述）**：`docs/31` 第 3、4 节曾写「已重建的执行链骨架在代码层面自洽」，**该判断过强**——受监督路径的全部测试都基于 `probe_manifest = None` 的计划，因此「执行 probe」这一决策第一次被真实使用时才暴露缺陷。正确表述应是：**在未覆盖的形状上，代码自洽性未被验证**。
- 因此本文件**不**把该失败表述为「验证了链路」或「有价值的探索」，而是一次**有实际代价的失败尝试**。

## 12. 持续披露与不得声称

- macOS supervisor 是本机 `ps` **采样式进程组监督**，**不是不可逃逸的内核级 containment**。
- campaign ledger **无哈希链**；「不可重试」依赖代码流程，而非账本自身的完整性证明。
- 门禁（lease 守卫、preflight 复验、预算预留校验）均为 **Python 级 API 约束**，不是对抗性安全边界。
- 训练原语（`run_manifested_experiment`、`manifest_executor`、`mccfr.train`）**直接调用**属流程违规。
- **单元测试 / N9 boundary / estimator preflight / 短路径回归 / 采样累计量 / 常和性质 / 策略稳定性，均不等于 A6/A7 实验结果**，也不是质量或资源基准。
- 即使 N9 boundary 与 A7-1000 全部成功，候选 A 也不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 本轮结论限于固定抽象、固定人数、固定 seed 与固定轮次；**单 seed 不构成稳定性结论**。

## 13. 本轮未做事项（截至本文提交）

- 未修改任何代码（本轮唯一改动是新增本文档；`kuhn_cfr`、后端、前端、锁文件、真实数据库均未触碰）。
- 未执行 N9 boundary，未执行 A7-1000 campaign（两者在本文提交后才启动）。
- 未执行跨 seed 稳定性实验（D3.3 保持关闭）。
- 未改写 `docs/20` 至 `docs/32a`；未删除或改写 campaign-1 的任何记录。
- 未扩预算、未转云、未转 GPU、未追加 seed。
