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

## 8. A7 加轮重做的实际回执

见本文件第二次提交追加的内容。
