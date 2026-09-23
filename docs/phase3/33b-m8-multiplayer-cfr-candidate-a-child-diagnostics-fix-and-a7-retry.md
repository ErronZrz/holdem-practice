# 33b M8：多人 CFR 候选 A——子进程诊断缺口修复与 A7 加轮重做

> 日期：2026-09-18。
>
> 本文件接在 `docs/33` / `docs/33a` 之后（沿用 `docs/30` D6 的编号族约定）。`docs/33` 记录只读复核、证据边界与决策；`docs/33a` 记录 N9 边界实跑与第一次 A7 加轮的执行回执；本文件记录**子进程诊断缺口的修复**，以及**修复后在新的冻结提交上重做 A7 加轮**的规格与回执。
>
> 本文件**分两次提交**：第一次随修复代码提交，只写第 1 至第 7 节；第二次在重做执行完成后追加第 8 节的实际回执。这样写是为了让"冻结提交"早于任何受监督运行，避免文档自身改动打断工作树干净前置。
>
> **第 1 至第 7 节提交时，A7 重做尚未启动，不声称已生成任何新策略、质量或资源证据。** `docs/20` 至 `docs/32a` 未被改写。

## 1. 本轮授权

用户答复原文：「没问题，我授权修复诊断缺口，接受 HEAD 更改。A7 1000 轮重做。请直接执行。如果需要创建文档，可从 33b 编号继续。」

由此被授权的事项：

1. 修复 `docs/33a` 第 3.6 节记录的诊断缺口，并明确接受该修复会改变 HEAD、使既有 `code_identity` 失效；
2. 在新的冻结提交上重做 A7 加轮（1000 轮）；
3. 新增文档使用 `docs/33b` 编号。

未授权、本轮不做的事项：跨 seed 稳定性实验（`docs/31a` D3.3 仍关闭）；N9 长期训练或 N9 策略导出；下一步主线变更（`docs/33` Q5 仍暂缓）。

## 2. 缺口的确认（已在 `docs/33a` 第 3.6 节记录）

第一次 A7 加轮（`a7-seed-7926-i1000`）以 `stop_reason = child-exit-nonzero`、`exit_code = 1` 失败，且**根因无法恢复**。原因有二，二者都在本次修复范围内：

1. 父端 supervisor 用 `subprocess.DEVNULL` 丢弃子进程的 `stdout` 与 `stderr`；
2. `SupervisorReceipt` 没有任何承载子进程错误信息的字段，因此即使保留输出也没有落盘位置。

后果：任何子进程异常都只能留下"退出码非零"这一条信息，与 `docs/32` 第 7.1 节 campaign-1 失败时的处境同类——**回执不含失败原因，失败原因只能被推断**。

## 3. 修复内容

改动只涉及两个源文件与一个测试文件：

| 文件 | 改动 |
|---|---|
| `tools/trainer/src/multiplayer_cfr/supervisor.py` | 捕获子进程合并输出并写入回执 |
| `tools/trainer/src/multiplayer_cfr/supervised_measurement.py` | 回执载荷与严格校验同步 |
| `tools/trainer/tests/test_multiplayer_supervisor.py` | 新增 3 条回归测试 |

### 3.1 捕获方式

- 子进程的 `stdout` 与 `stderr` 合并到**同一管道**（`stdout=PIPE`、`stderr=STDOUT`），不再丢弃；
- 父端在原有采样循环内**非阻塞排空**管道，并在子进程退出或被终止后于有限宽限期（200 ms）内读完剩余数据，避免"最后一屏回溯"丢失；
- 输出只在**内存**中保留受限部分：尾部上限 8 192 字节，写入回执时再截断为 2 048 个字符；同时累计**总字节数**与**全量 SHA-256**。

因此该诊断能力**不引入无界内存或磁盘占用**：即使子进程持续输出，父端也只保留尾部，且不会把输出写进工件根目录（工件根目录仍只允许预先声明的槽位）。

### 3.2 回执字段

`SupervisorReceipt` 新增三个字段（`supervisor_version` 由 `v1` 升为 `v2`，因为回执 schema 发生了变化）：

| 字段 | 含义 |
|---|---|
| `child_output_bytes` | 子进程合并输出的总字节数（全量计数，不只尾部） |
| `child_output_sha256` | 上述全量输出的 SHA-256 |
| `child_output_tail` | 输出的末尾至多 2 048 个字符（UTF-8 解码，非法字节以替换字符表示） |

`supervised_measurement._validate_receipt` 的严格字段集同步加入三项，并新增一条自洽校验：`child_output_bytes == 0` 时必须同时满足"尾部为空"且"摘要等于空串摘要"，防止"无输出"这一确定状态被伪造。

### 3.3 未放松的既有校验

- `supervisor_id`、状态字段、资源字段、PID 字段的既有判据逐字未变；
- 工件根目录仍只允许普通文件与预先声明的槽位；
- 没有新增文件路径约定，因此不触碰 lease 的 run 目录归属、工件封存清单或 1 GiB 保留额度。

## 4. 修复的边界与残留限制（必须持续披露）

- 该修复**不改变** `docs/33a` 第 3.6 节的定性：受监督链仍是**本机 `ps` 采样式进程组监督**，不是内核级 containment；新的诊断通道是**父端的合作式观察**，不是安全边界。
- 子进程被终止（预算触发）时，管道中未排空的部分最多保留到 200 ms 宽限期内可读到的字节；**完整输出不留存**，只留摘要与尾部。定位异常回溯足够，但不足以做完整日志审计。
- 管道有背压：若子进程以极高速度输出，它会因管道写满而变慢，直到父端下一次排空。当前的受控子进程（`manifest_executor`）在成功路径上不产生任何输出，因此这一项是理论风险而非现实开销；本轮如实记录而非隐瞒。
- **向后不兼容**：`campaign-2`、`docs/33a` 记录的 N9 boundary 与第一次 A7 加轮的 measurement 都携带 `supervisor_version = v1` 的回执，**不会被新的严格校验器接受**。这些记录是已冻结的历史证据，本轮**不重写、不补字段**，原样保留。

## 5. 离线复验

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
176 passed in 184.85s (0:03:04)
```

测试数由 `173` 增至 `176`，新增的三条都在 `tests/test_multiplayer_supervisor.py`：

1. 子进程静默成功时，三项输出字段分别为 0 / 空串摘要 / 空串；
2. 子进程向 `stderr` 写出固定诊断文本并以退出码 3 结束时，回执的字节数、SHA-256 与尾部与该文本逐字一致（即"失败原因可直接从回执读出"）；
3. 子进程写出 16 000 字节并以退出码 1 结束时，尾部被精确截断为最后 2 048 个字符，而字节数与 SHA-256 仍为**全量**值。

这仍是**单元测试**：它证明"子进程诊断在代码层面不再被丢弃"，**不等于**任何 A6/A7 实验结果、质量或资源基准。

## 6. 本轮未做事项（截至第 7 节提交）

- 未修改 `kuhn_cfr`、后端、前端、锁文件或真实数据库；
- 未执行 A7 重做（在第 7 节规格提交之后才启动）；
- 未重试 campaign-3 的 `a7-seed-7926-i1000`（已消耗，不可重试），未重试 campaign-1 / campaign-2 的任何 authorization；
- 未追加 seed、未扩预算、未转云、未转 GPU。

## 7. A7 加轮重做的规格（在提交后的新 HEAD 上重新冻结）

按 `docs/33a` 第 3.5 节的教训与用户授权，重做不沿用上一次的任何输入：

| 项 | 值 |
|---|---|
| campaign 根（工作树之外） | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-4` |
| `campaign_id` | `m8-a-campaign-4` |
| `authorization_id` / experiment `manifest_id` | `a7-seed-7926-i1000-r2` |
| probe `manifest_id` | `a7-probe-tight-loose-i1000-r2` |
| 参数 | `player_count = 7`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`master_seed = 7926` |
| 阶段预算 | `training / export / profile / probe / measurement = 900 000 / 120 000 / 600 000 / 3 000 000 / 120 000` ms |
| 其余预算 | cpu / wall `4 740 000 ms`、工件预留 16 MiB、策略槽位 12 MiB、measurement 槽位 1 MiB、RSS 6 GiB / 8 GiB |

与上一次的唯一差别是：全部输入在**新 HEAD** 上重新生成并重跑 estimator preflight；参数与预算 envelope **不扩额、不下调**。重做**仍无 estimator preflight 证据**（preflight 只覆盖 N=6，D4.3），且仍是单 seed。

若重做再次失败，按 `docs/33a` 的先例如实记录代价，**不自动发起第三次**。

## 8. A7 加轮重做的实际回执（第二次提交追加）

### 8.1 结论摘要

**重做再次失败，但诊断修复生效：失败根因第一次被完整落盘。** 根因不是预算、不是训练质量，而是**测量记录校验器对一个字段的长度上限过紧**，导致子进程在质量阶段完成后无法写出记录并以退出码 1 结束。该根因属于**第三个独立缺陷**，本轮**未修复**（见第 8.5 节），也**未自动发起第三次运行**。

### 8.2 冻结输入身份（全部在 `578a56565b3a74ee99b86fbf9a5a235a8c1c1c42` 上重新生成）

| 文件 | id | sha256 | 字节 |
|---|---|---|---:|
| `campaign.json` | `m8-a-campaign-4` | `2f87586ffe3ed707c00972c8cfed317c22474ed483ea5fc486e215cd5d518411` | 1018 |
| `source/a7-probe.json` | `a7-probe-tight-loose-i1000-r2` | `e7540557702c0e9b62db1dc4b40d3c0bcad7090463be72544b4c11170b1f6421` | 461 |
| `source/a7-experiment.json` | `a7-seed-7926-i1000-r2` | `1590f9776cb14507e6e060f7a3ca595c6b2ef9852d2ea8e84b6f78b5f122f19f` | 1310 |
| `source/preflight-spec.json` | `n6-estimator-preflight` | `d4995c7c475f0ace488f1d0addcf0cc648ef4e0cd8c4a270b896f59299c8d801` | 527 |
| `source/preflight-attestation.json` | `n6-estimator-preflight` | `61f9d6076dbc0d3aca9f7105a18bac6540ef251d9737ca8b269e16440c6e023e` | 1018 |

attestation 由 `run_preflight` 实跑产生，`passed = true`。参数与预算 envelope 与第一次尝试逐字相同（`player_count = 7`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`master_seed = 7926`、cpu / wall `4 740 000 ms`）。

### 8.3 回执与终态

| 项 | 值 |
|---|---|
| 父监督回执 | `status = failed` / `stop_reason = child-exit-nonzero` / `exit_code = 1` / 无信号终止 |
| 墙钟 / CPU | `399 117 ms`（6 min 39 s）/ `396 580 ms`（6 min 37 s） |
| 峰值 RSS | `49 872 896 B`（约 47.6 MiB） |
| 警告触发 | `false`（未触及 CPU、阶段墙钟、RSS 任一阈值） |
| 失败时工件总量 | `final_artifact_bytes = 1 142 972`（= 已写出的 `strategy.json`） |
| 终态 ledger | `leased` → `finalized(status = "failed")` |
| `final_measurement_sha256` | `91bfd85405303fb420388f2e4778f5a9bac5dbf82cd893c989aa5e5f628e5a1d` |
| `supervisor_receipt_sha256` | `8c26a0ec1891f7dfc6476a9cd51b15da01790cdff9f9b01e047d7beb557038cc` |
| `final_inventory` | `measurement.json`，3 495 B |

`strategy.json` 已按 fail-closed 清理；`monitored_pids = [34735]`。

### 8.4 失败根因（本次由回执直接给出，不再靠推断）

回执新增字段的实测值：

```text
child_output_bytes  = 3152
child_output_sha256 = 6a9d3a4d5f8772713d27a5b0ffbe9519131dda131fb62815569ff8042e502a74
child_output_tail   = （截取尾部，见下）
```

`child_output_tail` 的末尾即子进程异常回溯（原文照录，前面被尾部截断）：

```text
  File ".../experiment_record.py", line 121, in build_manifested_measurement_record
    _validate_payload(payload)
  File ".../experiment_record.py", line 430, in _validate_payload
    profile_identity = _validate_profile_payload(record["profile"], strategy_identity, player_count)
  File ".../experiment_record.py", line 509, in _validate_profile_payload
    utilities = _validate_rational_array(profile["utilities"], player_count, "profile.utilities")
  File ".../experiment_record.py", line 704, in _validate_rational_array
    return tuple(_validate_rational(entry, label) for entry in value)
  File ".../experiment_record.py", line 688, in _validate_rational
    numerator = _require_string(rational["numerator"], f"{label}.numerator")
  File ".../experiment_record.py", line 675, in _require_string
    raise ExperimentRecordError(f"{label} 必须是长度受限的非空字符串")
multiplayer_cfr.experiment_record.ExperimentRecordError: profile.utilities.numerator 必须是长度受限的非空字符串
```

即：**质量阶段（profile 与 probe）已经算完**，子进程在构造测量记录时被 `_require_string` 拒绝，因而退出码 1。

### 8.5 根因的机制与影响面（需要用户另作决定，本轮未修）

- 该判据是 `experiment_record._require_string` 的 `len(value) > 128` 上限；它被复用于所有字符串字段，其中也包括**精确有理数的分子与分母**。
- 精确有理数的位数**由规则树结构决定**，不由轮次决定：候选 A 在开池前每座位可 check/bet、开池后至多 N−1 个回应者，因此单条历史的动作数至多 `2N − 1`（N=6 → 11，N=7 → 13，N=9 → 17）；每个动作的概率分母整除 `10^12`，故分母位数上界约为 `12 × (2N − 1)`（N=7 → 约 156 位），再经约分后变小。
- 既有**通过**记录的实测最大位数是 **110**（A6 为 `probes[loose-open][3].delta.numerator`；A7（300 轮）为 `profile.utilities[3].denominator`）——距 128 只有 18 位余量。是否超过 128 取决于该策略量化后分子分母的**约分程度**，因此**同一人数在不同轮次下时通过、时失败**。
- 结论：`128` 不是该字段的安全上界，**N=6 也存在同样的边缘风险**（其理论上界约 132 位）。另一份独立测量 schema（`measurement.py`）对同类字段用的是 `256`，两份 schema 的口径彼此不一致。

**建议的最小修复（本轮未实施）**：给有理数的分子/分母一个独立的、宽裕的长度上限（例如 `1 024` 或 `4 096`），不改变标识符字段仍在 `128` 的既有强度；整条记录的字节上限（`MAX_TEXT_BYTES` 与 measurement 槽位上限）仍然独立生效。

### 8.6 代价（不淡化）

- `a7-seed-7926-i1000-r2` **已永久消耗**：不可重试、不可重置预算、不可追加 seed。
- 该次 1000 轮训练与完整质量评估的算力**全部白费**——注意此处比 campaign-1 / campaign-3 更可惜：**评估结果确实算出来了，只因校验器不接受而无法落盘**。
- 累计实测 CPU 消耗 396.58 s（约 6.61 min）计入本机预算。
- 两轮 A7 加轮尝试合计消耗两条不可重试 authorization 与约 13.3 min CPU，**均未换回任何质量证据**。
- 本文**不**把本次结果表述为"验证了诊断修复"或"有价值的探索"；它是一次**有实际代价的失败**，唯一的新增可用物是**根因本身**（这正是修复的直接目的）。

一处必须如实说明的影响：第一次尝试（`docs/33a` 第 3.5 节）的根因**当时未落盘**，现在只能作为**有证据支持的推断**——其可观测事实（质量阶段、已写出策略、退出码 1、约 400 s）与本次记录的机制完全一致，可以据此推断两次是同一根因，但**不得当作已记录的事实**。

### 8.7 campaign-4 驱动脚本自身的缺陷（如实记录）

驱动脚本在打印回执时把 `SupervisedExecutionResult` 当作 `CampaignExecutionResult` 使用，抛出了 `AttributeError`，因此**驱动输出日志只留下了只读复验段**，未包含回执打印。该缺陷**不影响证据**：终态 ledger 与最终 measurement 由受监督链在驱动崩溃之前就已写入，本次根因正是从 measurement 工件中读出的。缺陷已在原处修正。

### 8.8 预算核算（更新）

```text
campaign-1 A6（不可核算）          记 0            （记账约定，非"未消耗"）
campaign-2 A6 + A7（实测 CPU）     8.40 min
N9 boundary（实测 CPU 450 ms）     0.01 min
campaign-3 A7-1000（实测 CPU）     6.65 min
campaign-4 A7-1000-r2（实测 CPU）  6.61 min
合计实测                           21.67 min ≤ 120 min   （余约 98 min）
```

本轮同样发生了若干次 estimator preflight 核验重演（生成时 1 次 `run_preflight`，加上只读复验、父端门禁与子端门禁的重演），按 `docs/30` D3 **不计入**本机实验预算。

### 8.9 本轮未做事项与下一步

未做：未修复第 8.5 节的校验器上限缺口；未发起第三次 A7 加轮；未重试任何已消耗 authorization；未追加 seed、未扩预算、未转云、未转 GPU；未改写 `docs/20` 至 `docs/32a`。

下一步**唯一建议动作**（需用户另行授权）：先决定是否按第 8.5 节的最小方案修复有理数长度上限（会再次改变 HEAD，使既有 `code_identity` 失效），再决定是否在新 HEAD 上发起第三次 A7 加轮。按第 7 节的先例，**在获得授权之前不自动重跑**。

### 8.10 持续披露（延续）

本轮结论仍限于固定抽象、固定人数、固定 seed 与固定轮次；macOS supervisor 仍是本机 `ps` 采样式进程组监督，**不是内核级 containment**；新增的子进程输出捕获是**父端合作式观察**，不是安全边界，且只保留受限尾部（8 KiB 字节 / 2 048 字符），完整输出不留存。即使未来 A7 加轮成功，候选 A 也不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
