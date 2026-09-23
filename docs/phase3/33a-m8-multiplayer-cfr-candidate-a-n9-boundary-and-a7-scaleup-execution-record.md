# 33a M8：多人 CFR 候选 A——N9 边界实跑与 A7 加轮执行记录

> 日期：2026-09-18。
>
> 本文件是 `docs/33` 的配套执行记录，沿用 `docs/30` D6 的拆分约定（`33a` 表示接在 `docs/33` 之后的追加文档）。`docs/33` 记录只读复核、证据边界与决策；本文件只记录**两个子项的实际回执与封存清单**。`docs/20` 至 `docs/32a` 未被改写。
>
> 执行时的冻结提交：`634c694f3894cbfa0e51e2ac823276832c1b0fc7`（`docs/33` 的提交）。执行期间工作区保持完全干净。
>
> **结果摘要：子项甲（N9 boundary）成功；子项乙（A7 加到 1000 轮）失败，且失败原因未能落盘。** 两个子项的授权都已按 `docs/33` 第 1 节一次性使用完毕，本文件不把任何一个结果表述为质量、收敛、均衡或生产可用性证据。

## 1. 授权与执行顺序

按 `docs/33` 第 1 节记录的用户答复：Q3 = 是（授权 N9 boundary）、Q4 = 先尝试 (c) 到 1000（授权 A7 加轮）、Q6 = 允许 commit + push。

实际顺序：

```text
1. docs/33 提交 -> HEAD = 634c694f3894cbfa0e51e2ac823276832c1b0fc7，工作区干净
2. 生成 N9 boundary manifest（工作树之外）
3. 只读校验 N9 计划 -> 执行 N9 boundary 一次（成功）
4. 生成 campaign-3 全部冻结输入 + 重跑 estimator preflight（passed = true）
5. 只读复验 campaign-3 -> 执行 a7-seed-7926-i1000（失败，授权已消耗）
```

两个子项的运行目录与冻结输入**全部位于工作树之外**，工作树内只新增 `docs/33` 与本文两个文档。

有一处必须如实披露的操作过程：`a7-seed-7926-i1000` 的**第一次** `--execute` 调用被我主动终止。原因是驱动脚本当时的收尾逻辑在只读校验模式下也写了执行日志，导致执行前会因该日志已存在而中止；该进程被终止时仍停留在 `_verify` 阶段（`require_campaign_preflight_files` 的核验重演中），**尚未获取 lease、未创建任何 run 目录**。终止后经核实：`campaign-ledger.json` 不存在、`runs/` 不存在，因此该次调用**没有消耗授权**。驱动缺陷在第二次调用前修复。

## 2. 子项甲：N9 boundary 实跑（成功）

### 2.1 输入身份

| 项 | 值 |
|---|---|
| manifest_id | `n9-boundary-traverser-0-seed-20260918` |
| manifest sha256 / 字节 | `c50f596f91f436e31f6d40901f12ddebf72ddc548b1ac2630bfa0444993d2e0b` / 891 |
| 冻结提交 | `634c694f3894cbfa0e51e2ac823276832c1b0fc7` |
| `trainer_version` | `candidate-a-campaign-v1` |
| `game` | `m8-unique-rank-single-open` / `m8-a-v1` / `player_count = 9` |
| `execution` | `kind = n9-boundary-sample`、`iteration = 1`、`traverser = 0`、`master_seed = 20260918` |
| `quality` | `profile_mode = not-requested`、`probe_manifest = null` |
| `artifacts` | `strategy = null`；`measurement = measurement.json`，上限 524 288 B |
| `budget.stages` | `boundary = 300 000 ms`、`measurement = 60 000 ms`（父端墙钟硬限 360 000 ms） |
| `budget` 其余 | `cpu_limit = 300 000 ms`、RSS 预警 6 GiB / 硬停 8 GiB、`retained_artifact_limit_bytes = 1 048 576` |
| 执行方式 | `campaign_lease = None`、`preflight_spec_path = None`、`preflight_attestation_path = None`、`probe_manifest_path = None` |

输入快照 `run/inputs/experiment.json` 的 sha256 与 manifest 相同（`c50f596f…`），说明执行用的就是这一份冻结字节。

### 2.2 父端监督回执（原文）

```json
{"cpu_time_milliseconds": 450, "exit_code": 0, "final_artifact_bytes": 1388,
 "initial_artifact_bytes": 0, "monitored_pids": [64514, 64516],
 "peak_rss_bytes": 45957120, "status": "completed", "stop_reason": "completed",
 "supervisor_id": "macos-process-tree-supervisor", "supervisor_version": "v1",
 "terminated_with_signal": null, "wall_time_milliseconds": 551, "warning_triggered": false}
```

子端 `execution` 与 `resources`：

```json
execution = {"plan_kind": "n9-boundary-sample", "stage": "boundary", "status": "completed",
             "stop_reason": "completed", "completed_iterations": 0, "iterations": 1,
             "player_count": 9, "traverser": 0, "master_seed": 20260918,
             "average_strategy_start_iteration": null}
resources = {"elapsed_milliseconds": 397, "wall_time_limit_milliseconds": 300000,
             "peak_rss_bytes": 0, "warning_triggered": false, ...}
diagnostics = {"boundary_traverser": 0, "boundary_infoset_count": 20736,
               "coverage": [], "importance_weights": []}
strategy = null; profile = null; probes = null
```

### 2.3 工件与封存清单

| 项 | 值 |
|---|---|
| `final_inventory` | `measurement.json`，2 645 B，sha256 `192a7afced892a3ea172c31d1f76fa66643dce431131428ae00c0ee9c73429f7` |
| `pre_final_inventory` | `measurement.json`，1 388 B，sha256 `765024364fb2fd9eb43f6ba35600bb8979ae86bd2704cbc93be1dd2913041128`（子端临时记录，已被父端最终记录替换） |
| 回执文件 | `n9-boundary-receipt.json`，sha256 `9eb47ea54ceec721ed3c5dd6a86d146d34847417a42797ba4a00e67bdb0e2b6c` |

### 2.4 如何解读（严格限定）

- 记录的是**一个相对座位、一次 sampled pass** 的边界采样。9 人规则树的构造规模为 `boundary_infoset_count = 20 736`，与 `docs/26` §11 的结构性计数一致。
- **`coverage` 与 `importance_weights` 是空数组，这是该路径的代码设计**（boundary 采样不做诊断汇总），因此本轮**没有**逐信息集的访问覆盖或重要性权重摘要；不得用别处数字替代。
- 实测成本极小：父端墙钟 551 ms、CPU 450 ms、峰值 RSS 45 957 120 B（约 43.8 MiB）。这是**单次采样的实测值**，**不是** N9 训练、清晰度或可行性基准。
- `docs/26` §11 与 `docs/29` §3.3 的结构性事实（20 736 个信息集、362 880 个 ordered deal、2 305 个终局历史、朴素全 chance 评估上界 836 438 400 叶）仍是**结构性上界**，不是本轮测得的数字；本轮唯一测得的结构量是 `boundary_infoset_count = 20 736`（信息集总数），其余未被测量。
- 本次执行**不构成** N9 可行性、质量、收敛或生产可用结论；也不改变「候选 A 只在 N=6/N=7 做质量验证、N=9 只允许 boundary sample」这一边界。

## 3. 子项乙：campaign-3（A7 加到 1000 轮）执行（失败）

### 3.1 冻结输入身份（全部在 `634c694` 上重新生成）

| 文件 | id | sha256 | 字节 |
|---|---|---|---:|
| `campaign.json` | `m8-a-campaign-3` | `c92b21db69ea9b8ffca0ddf04e91cb89b25df7d13e634c020c187e7596e128f1` | 1012 |
| `source/a7-probe.json` | `a7-probe-tight-loose-i1000` | `4cc96e9c44d80497de5f9fc710963c0f07c9fb79991b68293287c359bea7ee5a` | 458 |
| `source/a7-experiment.json` | `a7-seed-7926-i1000` | `0387177d177ab8c1433b9016cbb6523dc73fb91e6d0ba50602c6dc4531dbd74b` | 1304 |
| `source/preflight-spec.json` | `n6-estimator-preflight` | `bbb7c3bf7dd53eb9faec4498d90eaf27cdd4a23888d026c204bfe42af4e68067` | 527 |
| `source/preflight-attestation.json` | `n6-estimator-preflight` | `d21ab5e9fdea3eb2397fde9bd85fa8b62ae92d54979933e69c7f6d04720eea37` | 1018 |

- attestation 由 `run_preflight` 实跑产生，`passed = true`，`code_identity.git_commit = 634c694…`。
- 唯一一条 authorization：`a7-seed-7926-i1000`，`player_count = 7`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`master_seed = 7926`；预留 cpu / wall `4 740 000 ms`、工件 `16 777 216 B`。
- 运行输入快照的 sha256 与 `source/` 同名文件一致（`0387177d…` / `4cc96e9c…`），说明执行用的是这一份冻结字节。
- 与 campaign-2 **没有任何输入文件复用**：campaign-2 的 `a7-seed-7926-r2` 从未被重试，本项目也从未重试 campaign-1 的 `a6-seed-6922`。

### 3.2 回执与终态

| 项 | 值 |
|---|---|
| 父监督回执 | `status = failed` / `stop_reason = child-exit-nonzero` / `exit_code = 1` / 无信号终止 |
| 墙钟 / CPU | `401 925 ms`（6 min 42 s）/ `399 150 ms`（6 min 39 s） |
| 峰值 RSS | `49 479 680 B`（约 47.2 MiB） |
| 警告触发 | `false`（**未**触及 CPU 上限、未触及阶段墙钟、未触及 RSS 预警或硬停） |
| 失败时工件总量 | `final_artifact_bytes = 1 142 972` |
| 终态 ledger | `leased` → `finalized(status = "failed")` |
| `final_measurement_sha256` | `5e440e84a21bfa9cc3c1ab4e4bb075f387da221672c9d5a7b5e48122ce697dc0` |
| `supervisor_receipt_sha256` | `fbe55a58ae81e60b1dc39aa307fc2db2c17b90bb2e4c56d39c2f6072773fd4c0` |
| `final_inventory` | `measurement.json`，1 206 B，sha256 `5e440e84…697dc0` |

终态记录（`record_type = multiplayer-cfr-supervised-measurement`）中 `child_execution = null`、`strategy = null`、`pre_final_inventory = []`。即：**这是一条失败记录，不含任何策略或质量结果**。

### 3.3 可以确证的事实

1. 子进程走过了训练与导出阶段：失败时工件总量约 1 143 KB，与 A7 量化策略 JSON 的量级一致（campaign-2 的 A7 策略为 1 145 054 B），说明 `strategy.json` 已写出。
2. 失败后按 fail-closed 流程清理：`runs/a7-seed-7926-i1000/artifacts/` 现在只剩失败 measurement，`strategy.json` **已被删除**，其内容不可恢复。
3. **失败不是预算耗尽**：CPU 399 s 远低于 4 740 s 预留，墙钟 401.9 s 远低于 4 740 s 硬限，`warning_triggered = false`。作为对照，campaign-2 的 A7（300 轮）在**同一代码身份与同一 probe 集合**下整条跑完只用了 492.3 s——本次在 401.9 s 就退出，早于那次的总时长。
4. 失败发生在**质量阶段（profile 或 probe）**，且子进程未写出临时 measurement。

### 3.4 无法确定的根因（必须如实标注为未知）

**子进程的 `stdout` 与 `stderr` 被父端 supervisor 以 `subprocess.DEVNULL` 丢弃**（`supervisor.py` 启动子进程处），因此子进程抛出的异常类型与回溯**没有写入任何工件、日志或回执**。可用的证据只有：退出码 1、无预算触发、失败时已写出策略、无临时 measurement。

据此**不能**判定根因，本轮也不作因果猜测为事实。可检验的候选机制（**以下均为未验证假设，不得当作结论**）：

- 评估阶段抛出了某个 `EvaluationError`（例如量化策略与规则信息集不匹配）；
- 评估阶段在未触及已配置阶段预算的前提下被其它条件中断；
- 子进程在质量阶段遇到与 1000 轮产物相关的其它异常。

需要特别指出：本轮**未能**回答「加大 iterations 是否能让 A7 的 probe 偏离收敛」这一 Q4 目标——因为该次运行没有产出任何质量结果。

### 3.5 代价（不淡化）

- `a7-seed-7926-i1000` **已永久消耗**：不可重试、不可重置预算、不可追加 seed。
- 该次 1000 轮训练与质量评估的算力**全部白费**，未换回任何策略、质量或资源证据；策略 JSON 已被清理。
- 累计实测 CPU 消耗 399.15 s（约 6.65 min）计入本机预算。
- 与 campaign-1 的失败（`docs/32` 第 7 节）相比：两者都不是「有价值的探索」，都消耗了一条不可重试 authorization 且没有换取证据。差别在于：campaign-1 的根因**已被代码定位并修复**；本次的根因**连代码定位都没有落盘**。
- 本文件**不**把本次失败表述为「验证了 fail-closed 清理流程」。它只说明该流程按设计执行了一次，而这本身不是一项新发现。

### 3.6 本轮暴露的具体缺口（可行动）

**受监督链在子进程失败时不保留子进程的诊断输出。** 父端 supervisor 以 `DEVNULL` 丢弃子进程 `stdout` / `stderr`，`SupervisorReceipt` 也没有承载子进程错误信息的字段，因此任何子进程异常都只能留下「退出码非零」这一条信息。

这与 `docs/31` 的教训属于同一类问题：**在未覆盖的形状上，代码自洽性未被验证**。此时新增的缺口形状是「质量阶段失败」，而它的诊断信息在架构上就被丢弃了。需要用户另行决定是否授权修改（这会改变 HEAD 并使既有 `code_identity` 全部失效）。

## 4. 预算核算（Q2 = b 口径，实测）

```text
campaign-1 A6（不可核算）        记 0            （记账约定，非"未消耗"）
campaign-2 A6 + A7（实测 CPU）   8.40 min
N9 boundary（实测 CPU 450 ms）   0.01 min
campaign-3 A7-1000（实测 CPU）   6.65 min
合计实测                         15.06 min ≤ 120 min   （余约 105 min）
```

如实说明两点：

1. 按**预留上界**口径，campaign-3 的 envelope 是 79 min、N9 是 5 min，合计上界 92.4 min，同样未越限。实测远低于上界。
2. 本轮额外发生了若干次 estimator preflight **核验重演**（campaign-3 生成时 `run_preflight` 实跑一次；此后每次只读复验、父端门禁与子端门禁各重演一次，量级约每次 1 分钟）。按 `docs/30` D3，这类重演**不计入**本机实验预算。

## 5. 持续披露与不得声称

- macOS supervisor 是本机 `ps` 采样式进程组监督，**不是不可逃逸的内核级 containment**。
- campaign ledger **无哈希链**；「不可重试」依赖代码流程，而非账本自身的完整性证明。
- lease 守卫与门禁均为 **Python 级 API 约束**，不是对抗性安全边界；`run_manifested_experiment`、`manifest_executor`、`mccfr.train` 属训练原语，直接调用属流程违规。
- **N9 boundary 不等于 A6/A7 实验结果**；它不产出策略、不做 profile/probe，也不构成 N9 可行性结论。
- campaign-3 的失败**不是**质量结论，也**不改变** A7（300 轮）已在 `docs/32a` 中记录的 probe 偏离事实；「A7 偏离的成因是欠训练还是结构性缺口」**仍然是未解问题**。
- 本轮任何数值都**不得**被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 本轮仍是**单 seed**（7926 / 20260918），**不构成任何稳定性结论**；`docs/31a` D3.3 的跨 seed 实验仍未执行。

## 6. 本轮未做事项与下一步

未做：

- 未修改任何代码或测试；未修改 `kuhn_cfr`、后端、前端、锁文件或真实数据库（工作树只新增 `docs/33` 与本文）。
- 未重试 `a7-seed-7926-i1000`、未重试 campaign-1 / campaign-2 的任何 authorization、未新建第二个加轮 campaign、未追加 seed。
- 未执行跨 seed 稳定性实验；未做长期 N9 训练或 N9 策略导出。
- 未改写 `docs/20` 至 `docs/32a`；campaign-1 与 campaign-2 的全部记录原样保留。

下一步**唯一建议动作**（需用户另行授权，本轮不自行执行）：

**先决定是否授权修复「子进程失败时丢弃诊断输出」这一缺口，再决定 A7 加轮是否重做。** 在没有后者所需的诊断能力之前，重做 A7-1000 只是再消耗一条不可重试 authorization 去换取同一条「退出码 1」。
