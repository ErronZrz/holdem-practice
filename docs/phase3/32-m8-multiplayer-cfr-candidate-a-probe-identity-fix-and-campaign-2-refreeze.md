# 32 M8：多人 CFR 候选 A——probe 身份校验缺陷修复与 campaign-2 重新冻结

> 日期：2026-09-18。
>
> 实测起点：`git status --short --branch` 输出 `## master...origin/master [ahead 3]`（无改动），`git log -9 --oneline` 顶部为 `dc79ee9 docs: correct 31/31a naming and finalize campaign freeze checklist`，`git rev-parse HEAD` 为 `dc79ee95c5b18379a6d27f43fad9ef29681a15f8`，`git rev-parse origin/master` 为 `9881050a53fb6f8e7e74a998153b43910cd5dee6`。与期望基线完全相符，未做任何 reset / clean / stash / checkout。
>
> 本轮是**修复轮**：经用户授权修复父端 probe 身份校验缺陷、补齐真实 probe 路径的回归测试，并在此提交之上重新冻结一轮 campaign（campaign-2）。
>
> 本文只记录到"提交前"的复核、修复、复验与重新冻结方案；campaign-2 的实际执行回执另记于 `docs/32a`（沿用 `docs/30` D6 的拆分约定）。`docs/20` 至 `docs/31`（含 `31a`）未被改写。
>
> 本文不声称任何训练质量、资源基准、均衡或生产可用性结论。

## 1. 本轮边界

1. 修复父端最终 measurement 对 probe 槽位的身份判据（P0）；
2. 补齐"携带真实 probe manifest 的 A6 受监督成功路径"回归测试；
3. 重跑全量离线校验；
4. 在同一提交上重新冻结 campaign-2（新 campaign 根、新 authorization 标识、同一组 seed 与已确认的 C 系列参数），并在用户授权范围内执行 A6、按 A6 结果决定是否执行 A7。

本轮**不**修改任何既有严格校验的强度（详见第 4 节），**不**扩预算、**不**转云或 GPU、**不**重试 campaign-1 中已消耗的 authorization、**不**追加 seed。

## 2. 缺陷确认（P0）

### 2.1 唯一错误点

`tools/trainer/src/multiplayer_cfr/supervised_measurement.py` 的私有校验函数 `_validate_identity` 只有一套判据，其中硬编码要求 `manifest_type == "multiplayer-cfr-experiment"`，但该函数被三个槽位共用：

| 调用点 | 槽位 | 期望类型 | 修复前 |
|---|---|---|---|
| `_validate_payload`（原 231 行） | `experiment_manifest` | experiment | 正确 |
| `_validate_execution_snapshots`（原 262 行） | `execution_snapshots.experiment` | experiment | 正确 |
| `_validate_execution_snapshots`（原 266 行） | `execution_snapshots.probe` | probe | **错误：用 experiment 判据校验 probe 身份** |

probe 身份类型是 `multiplayer-cfr-threshold-probes`，因此父端在拼装最终 measurement 的最后一步必然抛出 `SupervisedMeasurementError: experiment manifest 身份不兼容`。凡是携带 probe manifest 的 A6/A7 受监督运行都走这条路径，因此 A6 与 A7 在修复前都无法产出最终 measurement。

### 2.2 机械复现

用仓库自带解释器直接调用该判据，输入两种真实形状的身份：

```text
experiment identity -> ACCEPTED
probe identity -> SupervisedMeasurementError: experiment manifest 身份不兼容
  File ".../supervised_measurement.py", line 303, in _validate_identity
```

该复现只证明**判据本身**错误，不构成"整条执行链已被验证"的证据。

### 2.3 与 campaign-1 失败记录的一致性

`campaign-1` 的终态 ledger 为 `a6-seed-6922` 先 `leased`、后 `finalized(status="failed")`，`supervisor_receipt_sha256` 与 `final_measurement_sha256` 均为 `null`、`final_inventory = []`；`runs/a6-seed-6922/artifacts/` 为空，`inputs/` 保留两份冻结快照。失败时序与上述判据一致：异常发生在 `finalize_from_child_path` 的 completed 分支内、`replace_with_final_measurement` 之前，穿出 `run_supervised_manifest_executor` 后由 `campaign_executor` 的异常路径按 `_failure_status` 清理已声明工件并写 `failed`。

## 3. 影响面与覆盖缺口的只读复核

### 3.1 除该处外不存在第二条把 probe 身份送进 experiment-only 校验的路径

- `campaign.py` 的身份解析强制 authorization 绑定 experiment，是**正确**用法；
- `manifest_executor.py` 分别以 experiment 与 probe 类型构造两份子端身份，是**正确**用法；
- `manifest.py` 的 `_parse_identity_reference` 对 experiment 引用的 probe 槽位强制 probe 类型，是**正确**用法；
- `experiment_record._validate_identity_payload`（覆盖 `probes.manifest`）只校验字段集合与 SHA-256 形状，不绑类型；
- `execution_snapshot._require_document_identity` 走 `ExperimentManifest` / `ProbeManifest` 类型分支；
- `manifest.derive_experiment_plan` 按 `probe_manifest_ref` 比对，不经该判据。

全仓 `manifest_type` 字面量比较仅存在于上述各点与 `manifest.py` 的类型常量定义。

### 3.2 修复没有放松任何既有校验

experiment 槽位的两条字段级断言逐字不变；probe 槽位由"必须是 experiment 类型"改为"必须是 probe 类型"，语义上更严——修复前该槽位任何合法 probe 身份都必然失败，等于从未被真正校验过。

### 3.3 覆盖缺口比上一轮描述的更宽

上一轮把缺口描述为"A6 受监督成功路径未携带 probe"。实际复核结果更宽：**`probe_manifest_path` 在整个测试集中从未被传入过**，包括 `supervised_executor` 与 `campaign_executor` 两条入口。具体地：

1. `test_multiplayer_supervised_executor.py` 的 A6 计划继承 N9 计划的 `quality = {profile_mode: "not-requested", probe_manifest: None}`，因此 `snapshot.probe_identity` 恒为 `None`，probe 分支永不进入；N9 测试与 `docs/31` 新增的三条测试同理。
2. `test_multiplayer_orchestration.py` 中唯一的 full-chance 用例同样固定 `probe_manifest=None`。

因此子端的 probe 评估、以及子进程 measurement 记录中的整段 `probes`，此前**从未由真实路径构造过一次**，仅在 `test_multiplayer_experiment_record.py` 中以合成记录覆盖 schema。本轮新增的测试同时闭合父端判据与子端 probe 阶段的覆盖缺口。

## 4. 修复内容

改动只涉及 `tools/trainer/src/multiplayer_cfr/supervised_measurement.py`：

1. 把 `_validate_identity` 参数化为 `_validate_identity(value, expected_type, label)`，由调用方声明该槽位的期望 manifest 类型；
2. 两个 experiment 槽位传入 experiment 类型常量，probe 槽位传入 probe 类型常量；类型常量取自 `manifest.py`，顺带消除本文件内第三处字面量重复；
3. 报错文案按槽位区分（experiment / probe），使失败信息能直接指出是哪个槽位不兼容。

未触碰 `kuhn_cfr`、后端、前端、锁文件、真实数据库、equity / static share / 池层投影与生产结算。

## 5. 新增回归测试

`tests/test_multiplayer_supervised_executor.py` 新增一条真实 probe 的 A6 受监督成功路径：

- 先写入真实的冻结 probe manifest（`tight-open` 4/3 与 `loose-open` 1/0 两组，与 C5 同值）；
- experiment 计划引用该 probe 身份，并按 schema 要求使用 `full-chance` profile；阶段预算按实测锚点配置（profile 120 s、probe 300 s）；
- 使用真实冻结 preflight spec 与由其实跑得到的 attestation、真实 campaign lease、真实子进程与本地 supervisor 原语；
- 断言：父端回执为 `completed`；最终 measurement 的 `execution_snapshots.probe` 等于 probe 身份；子进程记录中 `probes` 非空；`pre_final_inventory` 与 `final_inventory` 均为 `measurement.json` 与 `strategy.json`。

该测试是**单元测试**：显式 1 iteration、临时 Git 工作树、单机原语。它不是受预算实验，不能作为 A6 训练质量、策略质量、RSS 或耗时的实测证据；它只证明"携带 probe 的受监督成功路径在代码层面可完成"。

## 6. 复验结果

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
173 passed in 183.94s (0:03:03)
```

`172` 增至 `173` 即第 5 节的新测试。套件耗时由上一轮的 `154.42s` 增至 `183.94s`：估算的约 80 秒增量中大部分被同进程内 estimator oracle 缓存与既有测试的公共部分吸收，实际边际约 30 秒。

覆盖范围仍限于规则、有限 estimator preflight、N9 boundary、父子协议、快照、封存清单、campaign 预算 / lease / 门禁、阶段截止，以及本轮新增的 probe 受监督单元成功路径。**不包含**任何 A6/A7 受预算训练、跨 seed 稳定性、资源基准或保留工件结论。

## 7. campaign-1 的 A6 失败：如实记录

必须先说明的是：上一轮（`docs/31` 轮）已获得一次性执行授权，只执行了 A6（authorization `a6-seed-6922`），**执行失败且未产出任何工件**。本轮修复的正是导致该失败的唯一代码缺陷。

### 7.1 代价（不淡化）

- `a6-seed-6922` **已永久消耗**：不可重试、不可重置预算、不可追加 seed。
- 该次 1000 轮训练与质量评估的算力**全部白费**，没有产出任何策略、质量或资源证据；策略 JSON 与子进程临时 measurement 已被 fail-closed 清理。
- 累计 CPU 预算核算：该次消耗**实际值未落盘、不可精确核算**；保守按 authorization 预留上界计 `1_140_000 ms`（19 min），计入本机 2 小时上限。
- 唯一留下的可用物是两份冻结输入快照（`runs/a6-seed-6922/inputs/experiment.json` 与 `probe.json`）与 ledger 中的失败事件。

### 7.2 教训

`docs/31` 第 3、4 节曾写"已重建的执行链骨架在代码层面自洽"。**该判断过强**：受监督路径的全部测试都基于 `probe_manifest = None` 的计划，因此"执行 probe"这一决策第一次真正被使用时才暴露缺陷。正确表述应是：**在未覆盖的形状上，代码自洽性未被验证**。

因此本文件不把该失败表述为"验证了链路"或"有价值的探索"，而是一次**有实际代价的失败尝试**：它消耗了一条不可重试的 authorization 与全部算力，未换回任何证据。其唯一可复用的产物是"缺口必须按真实形状覆盖"这一要求，已由第 5 节的测试落实。

另需如实标注：子进程"已完成训练、导出、profile 与 probe 且未触碰预算上限"这一结论，来自父端在 `finalize_from_child_path` 的 completed 分支内失败的**可推断性**，其回执未落盘，**不可引用为耗时或资源基准**。

## 8. 修复后的连带影响与 campaign-2 重新冻结

### 8.1 代码改动使整条冻结链失效

- 代码一改就必须提交 → HEAD 变化 → 所有 experiment manifest 与 campaign manifest 的 `code_identity.git_commit` 失效；
- preflight spec 与 attestation 绑 commit → 必须重新生成 spec 并重跑 `run_preflight`（首次重演约 62–65 秒）；
- 一处事实更正：probe manifest 的字段集合为 `{schema_version, manifest_type, manifest_id, game, evaluator, probes}`，**不含 `code_identity`**。因此它的字节身份并不依赖 commit；其"失效"来自必须与新的 experiment 引用同源，而非自身内容。本轮仍在 campaign-2 下重新生成一份，使整轮输入保持单一来源。
- `a7-seed-7926` 在 campaign-1 内从未 lease，但它同样携带 probe，修复前不可执行。

### 8.2 用户已确认的本轮决策

| 事项 | 决策 |
|---|---|
| 修复与回归测试 | 授权修复并补齐 |
| campaign-2 | 新建并重跑 A6 |
| A7 是否一并纳入 | 由本人决定（见 8.3） |
| campaign_id / authorization_id 命名 | 由本人决定（见 8.4） |
| seed | 沿用 A6 = 6922、A7 = 7926 |
| 预算 | 由本人依现状决定（见 8.5） |
| campaign-1 记录 | 保留，不删除 |
| commit / push | 允许 commit，不允许 push |
| 回归测试的 probe 组数 | 两组 |

### 8.3 A7 纳入本轮 campaign-2

决策：**纳入**。理由：

1. A6 与 A7 是同一 campaign 下的两条独立 authorization，各自独立 lease 与终结。因此先执行 A6、仅在其成功后才执行 A7，检查点粒度不损失；
2. 若把 A7 排除，A7 仍需另立一轮 campaign，总账不变（见 8.5）却多一次冻结与 preflight 重演；
3. A7 的已知不确定性（estimator preflight 只覆盖 N=6，故 A7 无 preflight 证据；其 probe 成本为外推值）已由 D4.3 与 C1 接受：C1 选择 (C)，即不动代码、配宽质量预算，若仍超时则整条失败、已声明工件按流程清理，**不重跑、不改阈值、不换 seed**；
4. 若 A6 失败，则**不再执行 A7**，直接终止并报告。

### 8.4 命名

| 项 | 值 |
|---|---|
| campaign root | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-2`（工作树之外） |
| `campaign_id` | `m8-a-campaign-2` |
| A6 `authorization_id` | `a6-seed-6922-r2` |
| A7 `authorization_id` | `a7-seed-7926-r2` |
| probe `manifest_id` | `a6-probe-tight-loose-r2` / `a7-probe-tight-loose-r2` |

`-r2` 后缀使本轮输入与 campaign-1 的失败尝试在同名 seed 下仍可逐字区分；`authorization_id` 仍满足受控标识约束。所有 game、evaluator、iterations、`average_strategy_start_iteration`、master_seed、阶段预算、工件槽位与 RSS 阈值均与 `docs/31a` 冻结清单逐字段一致（仅 seed 与轮次标识按本轮决策确定）。

### 8.5 预算：沿用 C3 原值，不压缩

| 项 | 值 |
|---|---|
| A6 envelope（cpu / wall / artifact） | `1_140_000 ms` / `1_140_000 ms` / `8_388_608 B` |
| A7 envelope（cpu / wall / artifact） | `4_740_000 ms` / `4_740_000 ms` / `16_777_216 B` |
| campaign 总 CPU / 墙钟 | `5_880_000 ms`（98 min） |
| campaign 峰值 RSS / 工件上限 | `8 GiB` / `25_165_824 B` |
| `max_concurrency` | `1` |

决策理由：campaign-1 的 A6 子进程回执为 `completed` 且未触碰任何预算上限，说明 19 min 档**足够**；但其实际耗时未落盘，无法量化余量。压缩 envelope 会引入"因预算不足而失败"的新失败模式，代价是再次浪费一条不可重试的 authorization，因此不压缩。

累计核算（保守，全部按预留上界计入）：

```text
campaign-1 A6  ≤ 19 min   （实际值未落盘，按上界计）
campaign-2 A6  ≤ 19 min
campaign-2 A7  ≤ 79 min
合计           ≤ 117 min  ≤ 120 min
```

**余量仅 3 min**，这一点必须显式披露：本机累计 CPU 上限为 2 小时，本轮之后几乎没有空间再发起任何受预算训练。estimator preflight 的重演按 `docs/30` D3 不计入本机实验预算。

## 9. 执行前必须满足的前置（已核对）

1. 冻结 commit 等于启动时刻的实际 `HEAD`，且等于两个 experiment manifest 与 campaign manifest 的 `code_identity.git_commit`；
2. 工作区完全干净——`runtime_identity` 使用 `/usr/bin/git status --porcelain=v1 --untracked-files=all`，因此 campaign 根、ledger、锁文件、源 manifest、preflight spec / attestation 与 run 目录全部位于工作树之外；
3. 每条 authorization 只 lease 一次、run 目录只创建一次；
4. campaign-2 的输入由工作树之外的生成脚本一次性写入，脚本拒绝覆盖已存在文件。

## 10. 持续披露与解释边界

- macOS supervisor 是本机 `ps` 采样式进程组监督，**不是不可逃逸的内核级 containment**。
- campaign ledger 无哈希链；"不可重试"依赖代码流程而非账本自身的完整性证明；lease 守卫与门禁均为 **Python 级 API 约束**，不是对抗性安全边界。`run_manifested_experiment`、`manifest_executor` 与 `mccfr.train` 属训练原语，直接调用它们运行 A6/A7 属流程违规。
- estimator preflight **只覆盖 N=6**；A7 的 estimator 没有 preflight 证据。
- 单 seed 运行**不构成稳定性结论**；probe 判定线 X = 0.05 BB/hand 是**解释边界**而非硬门禁。
- 单元测试（含本轮新增的 probe 回归测试）、N9 boundary、有限 estimator preflight、短路径回归、采样累计量、常和性质或策略稳定性，均**不等于** A6/A7 训练结果、质量证据或资源基准。
- 即使 campaign-2 全部完成，候选 A 也不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 本轮文档不得声称已生成任何策略、质量或资源证据——这些只能在 `docs/32a` 中按实际回执与封存清单记录。

## 11. 本轮未做事项（截至本文提交）

未改写 `docs/20` 至 `docs/31`（含 `31a`）；未修改 `kuhn_cfr`、后端、前端、锁文件或真实数据库；未扩预算、未转云、未转 GPU；未删除或改写 campaign-1 的任何记录；在本文提交之前未启动任何受预算 A6/A7 训练。
