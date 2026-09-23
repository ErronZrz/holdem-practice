# 51b M8：P2-2——N=9 四 seed 长期训练 campaign-9 执行回执

> 日期：2026-09-20。
>
> 本文件是 `docs/51a` §11 所建议动作的执行回执，沿用 `docs/30` D6 的编号族约定（`51b` 接在 `docs/51a` 之后）。`docs/51` 记录规格冻结、`docs/51a` 记录闸门放开与 campaign-8 标定回执；本文件只记录 **`m8-a-campaign-9` 的封存回执与实测数字**。`docs/20` 至 `docs/51a` 未被改写。
>
> 本轮**消耗 4 条不可重试 authorization**，全部成功；**未**追加 seed、**未**重试任何已消耗 authorization、**未**开启 N=9 的 profile/probe 闸门、**未**修改任何代码。
>
> 本文件全部数值来自实际落盘工件与回执，不是外推、不是估计。结构性计数仍只能作上界引用。

## 1. 授权与范围

| 项 | 用户答复原文 |
|---|---|
| 本轮授权 | 「好的，我授权启动 m8-a-campaign-9。」 |

据该授权与 `docs/51a` §11，本文件回答且仅回答三问：N=9 能否在显式预算下跑完 1000 轮、能否导出、以及实测资源是多少。

**未授权**（继续有效）：任何 N=9 质量结论；开启 N=9 的 profile/probe；新建第三个 N=9 campaign；追加预注册以外的 seed；改质量门槛；扩预算；转云或转 GPU。

## 2. 基线与冻结提交（只读）

```text
$ git status --short --branch        -> ## master...origin/master [ahead 9]
$ git status --porcelain=v1 --untracked-files=all | wc -l   -> 0
$ git rev-parse HEAD                 -> 92bd5655d6f90f5574d73504e533aeaa3818d691
$ git rev-parse origin/master        -> 133c99cbf541e9bf49d1f5f2e795ca6585e91d8d
```

本轮**冻结提交**（campaign-9 的 `code_identity.git_commit`）即 `92bd5655d6f90f5574d73504e533aeaa3818d691`（`docs: record n9 gate opening and the campaign-8 calibration receipt`）。执行期间工作树保持完全干净；四次执行各自在获取 lease 前重新核验了实际 HEAD 与冻结提交一致。

本轮零代码改动，提交前复跑全部检查以确认基线未漂移：

```text
cd tools/trainer && uv run ruff check .   -> All checks passed!
cd tools/trainer && uv run pytest -q      -> 227 passed in 221.29s
cd backend       && uv run ruff check .   -> All checks passed!
cd backend       && uv run pytest -q      -> 668 passed, 2 skipped, 2 warnings in 11.56s
cd frontend      && npm run build         -> ✓ 24 modules transformed / ✓ built in 494ms
```

## 3. campaign-9 冻结输入（工作树之外）

| 项 | 值 |
|---|---|
| campaign 根 | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-9/` |
| `campaign_id` / `sha256` / 字节 | `m8-a-campaign-9` / `67e2fd3c7c35af6e3c474e6a13985b3c9fc1b8b087190493e17529437d74adfb` / 2140 |
| `trainer_version` | `candidate-a-campaign-v1` |
| 驱动脚本 | `generate_frozen_inputs.py`、`run_campaign.py`（**均在工作树之外，未入库**） |
| 冻结 envelope | 单条 stages `(training 300 000 / export 60 000 / measurement 60 000)` = `420 000 ms`；工件预留 `20 971 520 B`（策略槽位 16 MiB、measurement 槽位 1 MiB）；RSS 预警 6 GiB / 硬停 8 GiB |

| 文件 | id | sha256 | 字节 |
|---|---|---|---:|
| `source/experiment-1215.json` | `a9-seed-1215-i1000` | `35123b6f6c98e1352463e74c1fe4faf5fed4657001c716e91bdf1cfb2c039617` | 995 |
| `source/experiment-20260918.json` | `a9-seed-20260918-i1000` | `12a32dc65647498c19631f8e1a027884aa0a186bf0918107803cbbed45658077` | 1003 |
| `source/experiment-3311.json` | `a9-seed-3311-i1000` | `a5d744d2d8e0cab312347ecb8143253ad07ab95ed28b52933e69919ad0a97c77` | 995 |
| `source/experiment-7926.json` | `a9-seed-7926-i1000` | `0faed9e93b51fe8d08b1d02e2ffc553e66a1c2b88e1d45df525a07c9f1b7eb6b` | 995 |
| `source/preflight-spec.json` | `n6-estimator-preflight` | `7f5c22591e9b7bfe49e6d22a5a38a3c37dfa1d74f63e36a9210db3aba3237523` | 527 |
| `source/preflight-attestation.json` | `n6-estimator-preflight` | `17c17ff6771f6f1029028e171b245fb527934af94bef30685e85a501bf316b0a` | 1018 |

- 四条 experiment 除 `master_seed` 外参数逐字相同：`execution.kind = a9-training`、`player_count = 9`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`quality.profile_mode = not-requested`、`quality.probe_manifest = null`。
- authorization id 按字符串升序冻结（`campaign._parse_authorizations` 的硬校验），四者即全部，**不得追加**。
- preflight attestation 由 `run_preflight` **实跑**产生，`passed = true`、`git_commit = 92bd565…`；按裁定三它仍是 **N=6 fixture** 的证据，**不**覆盖 N=9。
- 只读复验输出四条 `leased=no`、`stages_seconds=420`，并确认未获取 lease、未创建任何运行目录。

## 4. 四条 authorization 的回执（实测）

| authorization | seed | 父端墙钟 (ms) | 父端 CPU (ms) | 峰值 RSS (B) | 子端 training elapsed (ms) | 策略字节 | 最终 measurement 字节 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `a9-seed-1215-i1000` | 1215 | 24 788 | 24 490 | 220 676 096 | 21 278 | 8 229 831 | 4 931 |
| `a9-seed-20260918-i1000` | 20260918 | 33 402 | 31 140 | 213 876 736 | 28 942 | 8 229 740 | 4 955 |
| `a9-seed-3311-i1000` | 3311 | 25 955 | 25 490 | 226 213 888 | 21 959 | 8 229 778 | 4 930 |
| `a9-seed-7926-i1000` | 7926 | 24 666 | 24 300 | 212 189 184 | 21 120 | 8 229 231 | 4 931 |

四条的父端回执均为 `status = completed` / `stop_reason = completed` / `exit_code = 0` / `warning_triggered = false` / 无信号终止；`child_output_bytes = 0`（子进程未产生输出）。

| authorization | 最终 measurement sha256 | 策略 sha256 | 回执 sha256 |
|---|---|---|---|
| `a9-seed-1215-i1000` | `27331caaee65a08eaefe37e25f4a1f5dd4ee4c9ed8c5d1c1a2ef53b5170644a0` | `2acf8b736b7c843f7ed103ecc2865a1a28d9ee64e3367e5f94711fed648fde69` | `e129bde3b2b9ac26a41f0a629d9a1fbae98a5ef74a90aa7db7b26b4d1e03c971` |
| `a9-seed-20260918-i1000` | `ccb007ec545c87ae403e8e92e273d6d6fee902c6b2a9d94e035cb76e09391cc5` | `735aec8f4f7b3b41bc1ca16ac9e4c1362c96e84c331023c521673c1578ef5c97` | `0bcf10ecd41d4fe69e5b6c82b8a9352d7fd0ee22ca0523aaaf6f3ffc2c3e1e2c` |
| `a9-seed-3311-i1000` | `c28a76379bf7513ed0399d552ab6b4b60a3f14cf4592edc4a4d0f152de50ebf0` | `eefa6ac06906599b43bf338a1a99ed18ee83e32de46ab0a5525c040bab048ee1` | `f91e5abbd488ec11a12204a2d5edfad4f87275ae152740a70d8784007c6d8284` |
| `a9-seed-7926-i1000` | `c0586f451a2200ec51a2d246c210c21f13132b94a53ea503f85a4f96711b8f48` | `a6d58566b3774d58795d5e66d193b2a408f79c46dcc7547b630063c666536d0a` | `fb2ac40258ae5c115e0c97eacb5c1a2d5bddeb675e9f907643a2cafe7fdc5da7` |

账本终态：8 个事件（4 × `leased` + 4 × `finalized(status = completed)`），四条 `final_inventory` 与磁盘工件哈希**逐条一致**（已复核）。执行日志：`<authorization_id>-execution.log` 四份。

### 4.1 子进程记录的共同形状（以 seed 1215 为例）

```json
record_type = "multiplayer-cfr-supervised-measurement", schema_version = 2
child_execution.payload.execution = {"plan_kind": "a9-training", "status": "completed",
  "stage": "training", "stop_reason": "completed", "completed_iterations": 1000,
  "player_count": 9, "iterations": 1000, "average_strategy_start_iteration": 100,
  "master_seed": 1215, "traverser": null}
child_execution.payload.profile   = null
child_execution.payload.probes    = null
child_execution.payload.stability = {"status": "not-requested", "seed_set_sha256": null,
  "audit_infosets_sha256": null, "max_l1": null}
strategy = {"artifact_bytes": 8229831, "artifact_schema_version": 1,
  "artifact_type": "multiplayer-cfr-average-strategy", "sha256": "2acf8b73…fde69"}
```

四条记录均通过既有 v2 校验并回读成功。

## 5. 汇总（实测）

```text
父端墙钟合计            108 811 ms
父端 CPU 合计           105 420 ms  （1.757 min）
子端 training 合计       93 299 ms  （1000 轮 × 4）
峰值 RSS 最大值         226 213 888 B （约 215.7 MiB）
工件合计                 32 938 327 B （策略 32 918 580 B + measurement 19 747 B）
```

**envelope 使用率（如实披露，不表述为「预算充足」）**：单条预留 CPU `420 000 ms`，实测 `24 300–31 140 ms`，即用去预留的 **5.8%–7.4%**；`training` 阶段预留 `300 000 ms`，实测 `21 120–28 942 ms`（**7.0%–9.6%**）；合计预留 `1 680 000 ms`，实测 `105 420 ms`（**6.3%**）。策略槽位 16 MiB 对实测 ≈7.85 MiB（**约 49%**）。

`docs/51a` §7 的派生规则本身含 5 倍余量与 300 s 下限，因此实测远低于预留是**规则设计使然**；**不得**把本节数字反向读成「预算不足」或「预算充足」，它只说明本轮的 envelope 是保守的。

## 6. 本轮结论（可证与不可证）

**已被本轮证据支持**：

1. **N=9 的 1 000 轮 external-sampling 训练与策略导出是可运行的**：四条 authorization 全部 `completed`，`completed_iterations = 1000`，无任何资源停止条件触发；
2. **导出产物符合既有 v1 artifact schema**：`artifact_schema_version = 1`、`artifact_type = multiplayer-cfr-average-strategy`，四条均落在预声明 16 MiB 槽位内（实测 8 229 231–8 229 831 B）；
3. **资源量级**：单条父端墙钟 24.7–33.4 s、CPU 24.3–31.1 s、峰值 RSS 约 204–216 MiB；
4. 受监督执行链在 N=9 上真实走通：快照 → lease → 门禁 → 父子身份核验 → 独占工件根 → 父端最终 measurement → 封存清单 → 账本终态。

**未被本轮证据支持（不得声称）**：

- N=9 的**质量通过、收敛、均衡、NashConv、exploitability、best response、真实牌局 EV、生产可用性**：本轮**没有** profile、**没有** probe，`profile` 与 `probes` 恒为 `null`；
- **跨 seed 稳定性**：四个 seed 产出**不同字节**的策略（sha256 各不相同），这**只是四个独立训练的产物事实**，既**不**构成「稳定」也**不**构成「不稳定」；本轮**未**做任何两两 L1 比较，也**未**冻结对照口径；
- **N=9 与其他人数之间的任何比较或归因**（人数与树规模同时不同）；
- **N=9 的训练充分性**：`iterations = 1000`、`average_strategy_start_iteration = 100` 是为与 A6/A7 同口径而取的固定参数，本轮**没有**任何欠训练/收敛判据；
- `n6-estimator-preflight` 的 `passed = true` 仍是 **N=6** 的证据，**不**覆盖 N=9。

## 7. 预算核算（实测）

```text
本轮新增实测（4 条父端 CPU 合计 105 420 ms）      1.76 min
截至本轮开始前落盘实测累计（docs/51a §8）         52.96 min
累计实测                                          54.72 min
```

- 落盘工件合计 32 938 327 B（≈ 31.4 MiB），远低于本机 1 GiB 保留上限；峰值 RSS 215.7 MiB，远低于 6 GiB 预警。
- 四条 authorization 均**已永久消耗**：不可重试、不可重置预算、不可追加 seed。
- estimator preflight 的核验重演（生成时 1 次 + 只读复验 1 次 + 每条执行期父子门禁）按 `docs/30` D3 **不计入**本机实验预算。
- 沿用既有边界：不转云、不转 GPU、不无限重跑；训练相关进程峰值 RSS 合计 8 GiB、保留实验工件 1 GiB 上限不变。

## 8. 版本影响与兼容性

| 项 | 结论 |
|---|---|
| 代码 / 测试 | 本轮**零代码改动**（工作树只新增本文件） |
| 后端 / 前端 / 锁文件 / 真实数据库 | **未改动** |
| 数据库 schema | 无新列、无迁移 |
| 策略 artifact schema | **未变**：仍 v1，`PROBABILITY_UNITS = 1e12`，无新增字段（四条实测 `artifact_schema_version = 1`） |
| experiment / measurement 记录 schema | **未变**：保持 v1/v2 双版本读取；四条记录均为既有 v2 形态 |
| 旧响应 / 旧历史 / 旧前端 / 策略分派语义 | 均无变化 |
| `call_ev` 与 `equity()` 语义 | 无变化 |
| `docs/37` §3.1 | **未触发** |
| 已封存工件再读取能力 | `holdem-campaigns` 现有 19 份 `measurement.json`、16 份 `strategy.json`。实测 19 份 measurement 中 **15 份**可被当前代码整体再加载（含 campaign-8 新增 1 份与 campaign-9 新增 4 份）；**4 份早期封存记录**（`a6-seed-6922-r2`、`a7-seed-7926-r2`、`a7-seed-7926-i1000`、`n9-boundary` 的 `run`）仍因 **既有** supervisor receipt 字段版本差异无法整体再加载——该差异在 `docs/50a` 已记录，本轮**未引入、未修复** |
| N=9 产物去向 | 仅封存于 campaign-9 目录内，**不入库、不被后端读取** |

## 9. 持续披露与不得声称

- macOS supervisor 是本机 `ps` **采样式进程组监督**，**不是不可逃逸的内核级 containment**；子进程输出捕获是**父端合作式观察**，四条均为 `child_output_bytes = 0`。
- campaign ledger **无哈希链**；「不可重试」依赖代码流程，而非账本自身的完整性证明；lease 守卫与门禁均为 **Python 级 API 约束**。
- **单测 / 标定运行 / 长期训练都不能替代质量证据**；本轮不新增任何质量、收敛或生产可用性结论。
- 必须如实延续三次 A7 加轮失败的代价记录（campaign-1 / campaign-3 / campaign-4 各消耗一条不可重试 authorization）；本轮四条成功**不**把那些失败变成「有价值的探索」。
- 本文件是**文档改动**；除本文件外未修改任何代码、测试、锁文件或真实数据库。

## 10. P2-2 的收尾口径与下一步

按 `docs/35` §4.2，P2-2 的缺口原文是「N=9 的训练/质量可行性**完全未证**」。本轮之后应如实修正为：

> **N=9 的「长期训练 + 策略导出」可行性已被四条受监督运行证明；N=9 的「质量可行性」仍未证，且需要一套新的采样式评估器才能进入。**

据此，`docs/35` §4.2 的 **P2 组（P2-1、P2-2、P2-3、P2-4）至此全部有结论**；唯一的残留是有意保留的 N=9 质量缺口，它**不是**本轮或其授权范围内的欠账。

未做：

- 未生成第三个 N=9 campaign；未追加 seed；未重试任何已消耗 authorization；
- 未放开任何 N=9 的 profile/probe 闸门；未分析跨 seed 差异；未改质量门槛；
- 未修改 `backend/**`、`frontend/**`、锁文件、真实数据库与 `docs/20` 至 `docs/51a`；
- 未 push（按惯例由用户手动执行）。

下一步**唯一建议动作**（需用户单独决策，本轮不自行执行）：

**决定是否把「N=9 采样式质量评估器」立为新范围。** 若立，它属于 `docs/35` §4.2 之外的新增能力（新 evaluator、新记录语义、新预注册指标与门槛口径），必须先单独冻结规格再实施；若不立，则候选 A 的收尾结论以 `docs/35` §3.1 的固定观察为准，N=9 保持在「训练与导出可行、质量未证」的已披露状态。
