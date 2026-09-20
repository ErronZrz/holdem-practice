# 51a M8：P2-2——N=9 闸门放开与 campaign-8 标定运行（实施与执行回执）

> 日期：2026-09-20。
>
> 本文件是 `docs/51` 的配套实施与执行回执，沿用 `docs/30` D6 的编号族约定（`51a` 接在 `docs/51` 之后）。`docs/51` 记录规格冻结；本文件只记录**实际改动的代码/测试**与**一次受监督标定运行的封存回执**。`docs/20` 至 `docs/51` 未被改写。
>
> 本轮**消耗了 1 条不可重试 authorization**（`a9-calibration-i10`），**未**新建第二个 campaign、**未**追加 seed、**未**启动阶段二、**未**转云或转 GPU。
>
> 本文件中的全部数值均来自实际落盘工件与回执，不是外推、不是估计。结构性计数仍只能作上界引用。

## 1. 授权与范围

用户答复原文：

| 项 | 用户答复原文 |
|---|---|
| 本轮授权 | 「我确认授权 §5 闸门放开 + campaign-8。」 |

据该授权，本轮范围内：

1. 实施 `docs/51` §5 的**闸门放开**（`tools/trainer/**`，含正向与反向回归测试）；
2. 生成并执行 `docs/51` §7.2 的 **`m8-a-campaign-8`**（1 条 authorization）；
3. 按 `docs/51` §7.3 的派生规则给出**阶段二 envelope**（`m8-a-campaign-9`）。

**未授权**（继续有效）：启动阶段二、冻结 `m8-a-campaign-9` 的 campaign 文件、追加预注册以外的 seed、重试任何已消耗 authorization、开启 N=9 的 profile/probe 闸门、扩预算、转云、转 GPU、把 N=9 结果表述为任何质量结论。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch          -> ## master...origin/master [ahead 7]
$ git status --porcelain=v1 --untracked-files=all | wc -l   -> 0
$ git log -2 --oneline
4447f2c docs: freeze p2-2 n9 training and export feasibility campaign specs
d946e73 feat: wire cross-seed stability into supervised records and add cross-seed record type

$ git rev-parse HEAD          -> 4447f2c33dfde02e5ba3bad84cce3afccb980b40   （本轮起始）
$ git rev-parse origin/master -> 133c99cbf541e9bf49d1f5f2e795ca6585e91d8d
```

本轮**冻结提交（campaign-8 的 `code_identity.git_commit`）**为闸门放开提交：

```text
2ee58e7ce877fc2d5fcde39b86fa51c2d291bef2
feat: allow n9 long-run training and export through a dedicated a9 training plan
```

## 3. 代码改动清单（文件级）

实现集中在 `tools/trainer/src/multiplayer_cfr/`，共 8 个源文件：

| 文件 | 改动 |
|---|---|
| `mccfr.py` | 移除 `run_iteration` / `completed_result` / `train` 的 N=9 拒绝（`docs/51` §3.3 闸门 1–3）；`run_audit_iteration` 的 N=9 拒绝**原样保留** |
| `control.py` | 移除 `run_controlled_training` 的 N=9 拒绝（闸门 4） |
| `policy.py` | 移除 `export_strategy` 的 N=9 拒绝（闸门 5） |
| `manifest.py` | 新增 `execution.kind = "a9-training"`（限 N=9）；`a9-training` 的质量必须为 `not-requested` 且不得绑定 probe；`a9-training` 的阶段**恰好**为 `(training, export, measurement)`；`derive_experiment_plan` 为 `a9-training` 派生训练配置 |
| `experiment_record.py` | 训练分支判定与子记录校验纳入 `a9-training`；`plan_kind` 改为写实际执行类型（不再硬编码 A6/A7）；`plan_kind` 白名单加入 `a9-training` |
| `orchestration.py` | `_run_a6_a7` 更名为 `_run_training`（该路径现已覆盖 N=6/7/9 长期训练），提示语同步 |
| `evaluation.py` | 拒绝语改为「只有 A6/A7 训练计划允许 profile 或 probe 评估」；**判定不变**（`a9-training` 仍被拒） |
| `supervised_executor.py` | 提示语与文档字符串区分「长期训练必须有 lease」与「N9 边界采样可独立执行」；**判定不变** |

**不变式（由测试断言）**：`a6-a7-training` 仍限 {6,7}；`n9-boundary-sample` 仍限 {iteration=1、单 traverser、禁 profile/probe/策略槽位}；`estimator_preflight` 仍固定 N=6；`evaluate_profile` 与 `measurement` 的完整 chance profile 仍限 {6,7}；`run_audit_iteration` 仍拒绝 N=9。策略 artifact **不新增字段、不升 `SCHEMA_VERSION`**。

### 3.1 测试改动（含必须披露的两处既有用例修改）

新增用例（+6）：

| 文件 | 新增 |
|---|---|
| `tests/test_multiplayer_boundaries.py` | N=9 增量 API 可跑完并得到完整信息集结果；N=9 导出仍然满足既有 artifact schema（顶层字段集合、`schema_version = 1`、`probability_units`）；N=9 仍拒绝 `run_audit_iteration` |
| `tests/test_multiplayer_manifest.py` | `a9-training` 往返与三阶段派生（含 `training_config` 非空、无 probe）；六类反向拒绝（请求 full-chance、绑定 probe、五阶段预算、缺策略槽位、人数非 9、`a6-a7-training` 配 9 人） |
| `tests/test_multiplayer_experiment_record.py` | `a9-training` 记录形状（`plan_kind`、`strategy` 存在、`profile`/`probes` 为 `null`、`stability = not-requested`）并可写读 |
| `tests/test_multiplayer_orchestration.py` | `a9-training` 端到端只写预声明工件（`strategy.json` + `measurement.json`） |

**必须披露：两处既有用例被就地修改**（不是删除、不是放宽，而是其断言的行为已被本轮授权变更）：

1. `tests/test_multiplayer_control.py`：原 `test_n9_requires_boundary_entry_and_returns_only_one_non_training_sample` 断言 `run_controlled_training` 对 N=9 抛 `ControlError`。该断言与本轮授权的闸门 4 直接冲突，故改名为 `test_n9_controlled_training_and_boundary_entry_are_both_available`，改为断言 N=9 受控训练**能完成**（新增 `result.infoset_count == 20736`、coverage 覆盖 9 个 traverser），并保留边界采样的一半断言。随之为失效的 `ControlError` 与 `pytest` 导入被移除。
2. `tests/test_multiplayer_boundaries.py`：原 `test_n9_rejects_iteration_training_result_and_top_level_train` 断言 `run_iteration`/`completed_result`/`train` 对 N=9 抛错。该断言与本轮授权的闸门 1–3 直接冲突，故拆为「N=9 增量 API 可运行」与「N=9 仍拒绝 audit iteration」两个用例；原 `test_n9_manual_result_cannot_bypass_strategy_export` **原样保留**（手工构造的未完成结果仍因信息集计数不符而被拒）。

除上述两处，**没有删除或放宽任何既有用例**。

## 4. 验证输出（实测）

```text
cd tools/trainer && uv run ruff check .   -> All checks passed!
cd tools/trainer && uv run pytest -q      -> 227 passed in 252.83s
cd backend       && uv run ruff check .   -> All checks passed!
cd backend       && uv run pytest -q      -> 668 passed, 2 skipped, 2 warnings in 14.72s
cd frontend      && npm run build         -> ✓ 24 modules transformed / ✓ built in 742ms
```

训练器基线由 **221 passed → 227 passed**（净增 6，符合 §3.1）；后端 668/2 skipped **不变**；前端模块数不变。工作树在每个检查点均保持干净。

## 5. campaign-8 冻结输入（工作树之外）

| 项 | 值 |
|---|---|
| campaign 根 | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-8/` |
| `campaign_id` | `m8-a-campaign-8` |
| 冻结提交 | `2ee58e7ce877fc2d5fcde39b86fa51c2d291bef2` |
| `trainer_version` | `candidate-a-campaign-v1` |
| 驱动脚本 | `generate_frozen_inputs.py`、`run_campaign.py`（**均在工作树之外，未入库**） |

| 文件 | id | sha256 | 字节 |
|---|---|---|---:|
| `source/experiment-20260918.json` | `a9-calibration-i10` | `64734ade74e6c61f3f6ce22a0da47f9308e60bc03c540187ef5476f811b4c48d` | 995 |
| `source/preflight-spec.json` | `n6-estimator-preflight` | `6efb3b823f2c59f09929d534d8489fbbea27f60c1eaec0a3fd1b195d93c8ef00` | 527 |
| `source/preflight-attestation.json` | `n6-estimator-preflight` | `bee696b8b366e2aa908d931666846dd10881f51ec39fc6820f7a1ff3cbde6457` | 1018 |
| `campaign.json` | `m8-a-campaign-8` | `e9759707279d763b352d1d56ed4addef7b5b605cdf111ddd5c280634ec18b9ef` | 1007 |

- preflight attestation 由 `run_preflight` **实跑**产生，`passed = true`，`git_commit = 2ee58e7…`。按裁定三，它仍是 **N=6 fixture** 的 estimator 证据，**不**覆盖 N=9。
- 唯一 authorization：`a9-calibration-i10`，`kind = a9-training`、`player_count = 9`、`iterations = 10`、`average_strategy_start_iteration = 1`、`master_seed = 20260918`、`quality.profile_mode = not-requested`、`probe_manifest = null`；预留 cpu / wall `420 000 ms`、工件 `20 971 520 B`。
- 只读复验（`run_campaign.py`，无参数）输出 `leased=no`、`stages_seconds=420`，并确认**未获取 lease、未创建任何运行目录**。

## 6. 标定运行回执（实测，原文数值）

### 6.1 父端监督回执

```json
{"child_output_bytes": 0, "child_output_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
 "child_output_tail": "", "cpu_time_milliseconds": 3520, "exit_code": 0,
 "final_artifact_bytes": 8236884, "initial_artifact_bytes": 0, "monitored_pids": [77358],
 "peak_rss_bytes": 225722368, "status": "completed", "stop_reason": "completed",
 "supervisor_id": "macos-process-tree-supervisor", "supervisor_version": "v2",
 "terminated_with_signal": null, "wall_time_milliseconds": 3657, "warning_triggered": false}
```

### 6.2 子进程记录

```json
execution   = {"plan_kind": "a9-training", "status": "completed", "stage": "training",
               "stop_reason": "completed", "completed_iterations": 10, "player_count": 9,
               "iterations": 10, "average_strategy_start_iteration": 1,
               "master_seed": 20260918, "traverser": null}
profile     = null
probes      = null
stability   = {"status": "not-requested", "seed_set_sha256": null,
               "audit_infosets_sha256": null, "max_l1": null}
resources   = {"elapsed_milliseconds": 200, "wall_time_limit_milliseconds": 300000,
               "peak_rss_bytes": 0, "warning_triggered": false, ...}
strategy    = {"artifact_bytes": 8233662, "artifact_schema_version": 1,
               "artifact_type": "multiplayer-cfr-average-strategy",
               "sha256": "412491bfd12284df57da2e3acbe270287c73937a68e3fa03decef6def30855e5"}
```

按人数逐 traverser 的覆盖与重要性权重**非空**（与 N9 boundary 采样该字段为空数组不同）：9 个 traverser 全部出现，`visited_infosets` 为 10–16、`visits` 为 10–20，`non_finite_count` 全为 0。

### 6.3 工件与封存清单

| 项 | 值 |
|---|---|
| 最终 measurement | `measurement.json`（`multiplayer-cfr-supervised-measurement` v2），4 885 B，sha256 `e3a05d2459cfcf8ec9a815173898e2a4e56ff64355a99aa814f499ddb60872d8` |
| `pre_final_inventory` | `measurement.json` 3 222 B（sha `0a568fade2ade00ed74709f8b0417a2ace24ccf4fd6da2cf294831bbb0d18457`）+ `strategy.json` 8 233 662 B（sha `412491bf…30855e5`） |
| 策略产物 | `strategy.json`，8 233 662 B（约 7.85 MiB），sha256 `412491bfd12284df57da2e3acbe270287c73937a68e3fa03decef6def30855e5`，`artifact_schema_version = 1` |
| 子记录身份 | sha256 `0a568fade2ade00ed74709f8b0417a2ace24ccf4fd6da2cf294831bbb0d18457` |
| 回执身份 | `supervisor_receipt_sha256 = a625d42600cc638816ab38c48dc39786be0ad304a2cb35ac27e37dc0e5834293` |
| 终态 ledger | `leased` → `finalized(status = "completed")` |
| 执行日志 | `a9-calibration-i10-execution.log` |

### 6.4 可以确证的事实（严格限定）

1. **N=9 的 10 轮长期训练与策略导出在显式预算下真实跑通**：`completed / completed / exit_code = 0`，信息集计数 20 736 与闭式结构计数一致，导出产物通过既有 v1 artifact schema 校验。
2. **成本极小**：父端墙钟 3 657 ms、CPU 3 520 ms；子进程 `training` 阶段自身实测 elapsed 200 ms（10 轮）。
3. **峰值 RSS 225 722 368 B（约 215.3 MiB）**：低于该人数静态状态预留 512 MiB，远低于 6 GiB 预警。
4. **子进程输出为空**（`child_output_bytes = 0`），未触及任何资源停止条件（`warning_triggered = false`）。
5. 导出策略 8 233 662 B，落在预声明 16 MiB 槽位内。

**必须如实说明的一点**：`docs/51` §7.2 那 300 s 的 `training` 阶段预算是**刻意放大**以不让阶段墙钟干扰标定；本次实测仅用去该预算的 0.07%，因此**不得**把「300 s 预算」读成「N=9 单轮成本」的度量。

### 6.5 不得由此声称

- 不得由本次运行声称 N=9 的**质量、收敛、均衡、NashConv、exploitability、真实牌局 EV 或生产可用性**——本轮**没有** profile、**没有** probe，`profile`/`probes` 均为 `null`；
- 不得把 20 736 信息集之外的任何结构量（362 880 ordered deals、2 305 终局历史、836 438 400 叶上界）表述为本次测得；
- 不得跨人数比较或归因（N=9 与 N=6/N=7 的人数与树规模同时不同）；
- 不得把 `n6-estimator-preflight` 的 `passed = true` 表述为 N=9 的 estimator 证据；
- 不得把 10 轮结果表述为「训练充分」；`iterations = 10` 与 `average_strategy_start_iteration = 1` 都是**标定参数**，不是最终口径。

## 7. 阶段二 envelope（按 `docs/51` §7.3 派生规则计算）

派生输入（全部为本次实测）：子进程 `training` 阶段 elapsed `200 ms` 覆盖 10 轮 → 单轮成本锚点 `20 ms`。

```text
training 阶段预算 = ceil(20 ms × 1000 × 5 ÷ 60_000) × 60_000 = ceil(1.667) × 60_000 = 120_000 ms
                   取与 300_000 ms 的下限较大者                = 300_000 ms
export  阶段预算 = max(60_000, 非训练部分(父端墙钟 3 657 ms − 训练 200 ms) × 5) = 60_000 ms
measurement 阶段预算（固定）                                   = 60_000 ms
────────────────────────────────────────────────────────────────────────────
单条 stages 之和 = 父端墙钟硬限 = cpu_limit                    = 420_000 ms
```

| 项 | 派生值 | `docs/51` §7.3 硬上限 | 是否合规 |
|---|---:|---:|---|
| 单条 authorization cpu / wall | `420_000 ms`（7 min） | `1_800_000 ms` | ✓ |
| campaign-9 合计（4 条） | `1_680_000 ms`（28 min） | `7_200_000 ms` | ✓ |
| 单条工件预留 | `20_971_520 B`（20 MiB） | `20_971_520 B` | ✓ |
| 单条 `strategy.maximum_bytes` | `16 777 216 B`（16 MiB） | 同 | ✓（实测导出 8 233 662 B） |
| campaign `peak_rss_limit_bytes` | `8 589 934 592 B`（8 GiB） | 同 | ✓（实测 215.3 MiB） |

四 seed 逐字相同参数：`player_count = 9`、`execution.kind = a9-training`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`quality.profile_mode = not-requested`、`quality.probe_manifest = null`、`max_concurrency = 1`、RSS 预警 6 GiB / 硬停 8 GiB。

约束自检：`2 × 1_048_576 + 16_777_216 = 18_874_368 ≤ 20_971_520` ✓；`stages` 恰好按 `training, export, measurement` 顺序 ✓；预留总和 `420 000 ≤ limits` ✓。

**结论：派生值全部落在硬上限之内，`m8-a-campaign-9` 的 envelope 已可冻结**——但按授权范围，本轮**不**生成该 campaign 的任何文件、**不**启动它。

## 8. 预算核算（实测）

```text
本轮新增实测（a9-calibration-i10 父端 CPU 3 520 ms）      0.06 min
截至本轮开始前落盘实测累计（docs/34b §9.8）              52.90 min
累计实测                                                 52.96 min
```

- 落盘工件合计约 `8 238 547 B`（≈ 7.86 MiB），远低于本机 1 GiB 保留上限；峰值 RSS 215.3 MiB。
- `a9-calibration-i10` **已永久消耗**：不可重试、不可重置预算。
- estimator preflight 的核验重演（生成时 1 次 + 只读复验 1 次 + 执行期父子门禁）按 `docs/30` D3 **不计入**本机实验预算。
- 沿用既有边界：不转云、不转 GPU、不无限重跑、不追加预注册以外的 seed；训练相关进程峰值 RSS 合计 8 GiB、保留实验工件 1 GiB 上限不变。

## 9. 版本影响与兼容性

| 项 | 结论 |
|---|---|
| 后端 / 前端 / 锁文件 / 真实数据库 | **未改动**（`backend/**`、`frontend/**`、两份锁文件、`holdem.db` 全部只读） |
| 数据库 schema | 无新列、无迁移 |
| 策略 artifact schema | **未变**：仍 v1（`SCHEMA_VERSION = 1`），`PROBABILITY_UNITS = 1e12` 不变，无新增字段（本次导出实测 `artifact_schema_version = 1`） |
| experiment / measurement 记录 schema | **未变**：experiment 记录保持 v1/v2 双版本读取；`a9-training` 记录复用既有 v2 形态（`profile`/`probes` 为 `null`、`stability = not-requested`），不新增字段 |
| 旧响应 / 旧历史 / 旧前端 / 策略分派语义 | 均无变化 |
| `call_ev` 与 `equity()` 语义 | 无变化 |
| `docs/37` §3.1 | **未触发**（该节只管后端复盘参考/评估身份，与 `tools/trainer/**` 无关） |
| 已封存工件再读取能力 | 保持：`holdem-campaigns` 下既有 14 份 `measurement.json`、11 份 `strategy.json` 与本次新增 2 份工件全部可读 |
| 缺项与未覆盖面 | N=9 无 profile/probe（按裁定一）；N=9 无人数专属 estimator preflight（按裁定三）；二者均在 §6.5 显式标注为「未覆盖」 |

## 10. 持续披露与不得声称

- macOS supervisor 是本机 `ps` **采样式进程组监督**，**不是不可逃逸的内核级 containment**；子进程输出捕获是**父端合作式观察**，只保留受限尾部，不是安全边界。本次 `child_output_bytes = 0`。
- campaign ledger **无哈希链**；「不可重试」依赖代码流程，而非账本自身的完整性证明；lease 守卫与门禁均为 **Python 级 API 约束**，不是对抗性安全边界。
- **单测 / 标定运行 / estimator preflight 都不等于质量结论**；本轮不因此新增任何质量、收敛或生产可用性结论。
- 必须如实延续三次 A7 加轮失败的代价记录（campaign-1 / campaign-3 / campaign-4 各消耗一条不可重试 authorization），本次成功**不**把那些失败变成「有价值的探索」。
- 本轮唯一被完整回答的问题是「N=9 能否训练并导出」；**它能否作为可用策略，本轮完全未证**。

## 11. 未做事项与下一步

未做：

- 未生成 `m8-a-campaign-9` 的任何文件，未冻结其 campaign，未启动其任何 authorization；
- 未追加 seed、未重试任何已消耗 authorization、未新建第二个标定 campaign；
- 未放开任何 N=9 的 profile/probe 闸门；未改质量门槛（`docs/39` 继续不启用）；
- 未修改 `backend/**`、`frontend/**`、锁文件、真实数据库与 `docs/20` 至 `docs/51`；
- 未 push（按惯例由用户手动执行）。

下一步**唯一建议动作**（需用户单独授权，本轮不自行执行）：

**授权冻结并启动 `m8-a-campaign-9`（N=9 四 seed、1000 轮、预热 100）**，其 envelope 即为 §7 的派生值（单条 420 000 ms、合计 1 680 000 ms、工件 20 MiB / 条）。该授权会一次性预注册 4 条不可重试 authorization；若其中任一条失败，按 `docs/51` §7.6 终止并如实报告，不重试、不追加 seed。

不建议在本轮之后扩大范围：N=9 的质量可行性需要**新的采样式评估器**（属新代码与新记录语义），在本轮授权之外。
