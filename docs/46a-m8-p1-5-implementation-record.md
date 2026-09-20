# 46a M8：P1-5 修复后 2–9 人实时决策性能复测（实施与实测回执）

> 日期：2026-09-20。
>
> 本文件是 `docs/46` 的**实施与实测回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/45a` 未被改写；`docs/46` 只新增说明、未做规格修订（见 §2）。
>
> 本文件记录已实际落地的代码、测试与**一次本机实跑**。**不产生任何策略、质量或资源证据**；未接入 CFR/lookup 到运行时、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、未写回任何工件。

## 1. 实施基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 5]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -3 --oneline
b30d71e docs: freeze p1-5 post-fix decision latency remeasurement specs
348f470 feat: add controlled real rules boundary contract
6388bba docs: freeze p1-4 real rules boundary contract specs

$ git rev-parse HEAD          -> b30d71e（`docs/46` 冻结提交）
$ git rev-parse origin/master -> f9e957bf9f9a1df89bb92957c01e031d5d48723d
```

`ahead 5` 即 P1-1…P1-4 的四个实现提交与五个规格/实现提交中的本地部分（含本轮 `docs/46` 冻结），本轮**不 push**；实施前工作区 0 行。未做任何 `reset` / `clean` / `stash` / `checkout`。

## 2. 实施期规格澄清（记录原因，不属修订）

本轮**没有**修订 `docs/46` 的任何裁定；实施中只澄清两处不改变结论的口径：

| # | 澄清 | 原因 |
|---|---|---|
| 1 | 异常分型：**模型内**一致性校验（缺项 / 重复 / 同时判为已测与未覆盖 / 街缺口不匹配 / 分组与声明街不符 / 环境键超白名单）由 Pydantic 包装为 `ValidationError`；**入口级**校验（空环境、非字符串键值、基础场景标识、补充场景重名或复用）由 `build_decision_latency_report` 抛 `DecisionLatencyError` | 与 P1-3 / P1-4 已确立的既有情形一致（`docs/44a`、`docs/45a` §2 第 2 条）。判据本身与 `docs/46` §4.4 完全一致，只是异常类型分型 |
| 2 | 强听牌局面的构造要点：公共牌必须含**两张**同花牌，单张补牌才可能成花 | 首版构造（公共牌仅一张同花牌）实测补牌数为 `8`，未达组合听牌阈值，因此**未触达**补牌统计分支；改为两张同花牌后补牌数为 `15`。这是构造细节，不是判据变更 |

## 3. 实际改动（文件级）

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/decision_latency.py`（**新增**，314 行） | 测量口径：路径与查表接入状态声明、`DECISION_STREETS`、场景闭集、`LatencyGroupSummary` / `PlayerCountDecisionLatency` / `DecisionCoverageGap` / `DecisionScenarioLatency` / `DecisionLatencyReport`，纯函数 `summarize_latency_group` / `summarize_player_count_latency` / `build_decision_latency_report`。**无生产调用方** |
| `backend/app/strategy/__init__.py`（修改，+38 行） | 导出新模块的公开符号；既有导出与顺序语义不变 |
| `backend/tests/decision_latency_states.py`（**新增**，173 行） | 局面构造与计时辅助（非 test 文件，不被自动收集）：确定性构造各街局面、强听牌局面、基础矩阵变体、固定种子策略、计时循环 |
| `backend/tests/test_strategy_decision_latency.py`（**新增**，589 行） | 50 条常驻回归测试，见 §5 |
| `backend/tests/test_decision_latency_benchmark.py`（**新增**，266 行） | 显式 opt-in 实测入口（默认跳过） |
| `docs/46-m8-…-remeasure.md`（**新增**，`b30d71e`） | 规格冻结 |
| `docs/46a-…md`（本文件） | 实施与实测回执 |

**未改动**（`git status` 可证）：`backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/api/**`、`backend/app/storage/models.py`、`backend/app/strategy/lookup_budget.py`、`backend/app/strategy/heuristic.py`、`frontend/**`、`tools/trainer/**`、`backend/uv.lock`、`frontend/package-lock.json`、真实数据库 `backend/data/holdem.db`、`docs/20` 至 `docs/45a`。

实施中另有一个**临时规模探测脚本**（`backend/_sizing_probe.py`），仅用于估算实跑耗时，**在 `docs/46` 提交前已删除**，不属本轮交付物，其数字见 §9。

## 4. 测量对象与覆盖的实际形态

| 项 | 实际取值 |
|---|---|
| 被计时路径 | `HeuristicStrategy.action_distribution(state, legal)` 单次调用（翻前 Chen 分档；翻后 `equity()` 蒙特卡洛，采样数沿用策略默认值） |
| 计时窗口 | `time.perf_counter()` 紧包该调用；不含局面构造、`BOT_DELAY`、HTTP、数据库、序列化 |
| 报告路径标识 | `measured_path = "heuristic-action-distribution"` |
| 查表接入状态 | `lookup_runtime_integration = "not-integrated-unmodeled"`（附说明文本） |
| 人数 | `2, 3, 4, 5, 6, 7, 8, 9`（全部真实构造） |
| 基础矩阵单元 | 每（人数, 街）`4` 个确定性变体轮转；每人数 `10000` 次决策（每街 `2500`） |
| 补充场景人数 | `6, 7, 9`（每场景每人 `1000` 次） |
| 局面构造 | 固定构造种子；盲注 `5/10`；起始筹码 `1000`（深 `20000` / 浅 `200`） |
| 总决策次数 | `92000`（基础 `80000` + 场景 `12000`） |
| 未写入报告的信息 | 构造种子、对手暗牌、未来公共牌均不进入报告；`environment` 只含白名单键（§6.2） |

## 5. 新增测试与覆盖对应

`backend/tests/test_strategy_decision_latency.py`，**50 passed**（`0.22s`）。对应 `docs/46` §4.7：

| 验收项 | 覆盖（用例） |
|---|---|
| D1 口径复用 | `test_module_reuses_the_existing_budget_constants`（常量与函数**同一对象**）、`test_module_does_not_restate_any_budget_number`（源文件不含预算数值字面量） |
| D2 分位与超时边界 | `test_group_summary_uses_the_nearest_rank`、`test_group_summary_counts_the_budget_boundary_as_a_timeout`（恰好 `100.0ms` 计超时）、`test_group_summary_matches_the_existing_timeout_rule`、`test_group_summary_rejects_an_inconsistent_budget_flag` |
| D3 逐人数完整性 | `test_scenario_requires_every_player_count_to_be_accounted_for`、`test_scenario_rejects_a_count_both_measured_and_uncovered`、`test_scenario_rejects_duplicate_measured_counts`、`test_scenario_exposes_measured_and_uncovered_counts` |
| D4 无合并均值 | `test_report_has_no_aggregate_field`（字段集恰为 11 项，且不含 mean/average/weighted/aggregate）、`test_report_requires_every_player_count_via_the_scenario` |
| D5 口径自洽 | `test_player_count_summary_merges_the_groups`、`test_player_count_entry_rejects_a_group_total_mismatch`、`test_recommended_scale_stays_self_consistent`（`decision_count == 建议样本量`、逐街之和等于总数） |
| D6 未覆盖无延迟值 | `test_uncovered_gap_carries_no_latency_value`（字段集恰为 `{dimension, key, reasons}`，多余字段失败） |
| D7 失败语义 | `test_timeout_is_reported_per_player_count_and_never_hidden`、`test_guidance_flags_are_reported_but_not_enforced` |
| D8 路径如实 | `test_report_exposes_the_path_and_the_lookup_status` |
| D9 opt-in 与默认零影响 | `test_benchmark_entry_is_opt_in_by_default`；整轮默认套件中该入口保持 skip |
| D10 不写回工件 | `test_new_code_never_writes_files`（三个文件均无写入调用） |
| D11 信息边界 | `test_measured_path_ignores_hidden_cards`（替换对手暗牌后同种子分布不变）、`test_report_requires_a_whitelisted_environment`（白名单外键失败，白名单无 seed 键） |
| D12 2–9 参数化 | `test_player_count_summary_supports_every_player_count`（2–9 参数化）、`test_state_builder_produces_a_legal_decision_point`（2–9 参数化 × 4 街） |
| D13 既有语义零改动 | 完整套件 649 passed（基线 599 + 本轮 50，无既有用例被删改）；`lookup_budget.py` 未被修改 |

另含：分组分位与超时输入校验、报告冻结、场景闭集（未知场景失败）、街顺序与街缺口校验、分组与声明街一致性、`docs/46` §4.3 的样本分配与场景聚焦校验、`strong-draw` 触达补牌分支的构造校验、计时辅助的参数校验。

## 6. 实际验证输出

### 6.1 静态检查与测试

```text
$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
649 passed, 2 skipped, 2 warnings in 9.70s
（本轮起点基线 599 passed, 1 skipped；新增 50 条，599 + 50 = 649；
 2 skipped 为两个显式 opt-in 实测入口，默认整轮测试不触发任何真实测量）

$ cd frontend && npm run build
✓ 23 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.31 kB
dist/assets/index-C7nR2Wox.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 468ms
```

两条 warning 均为既有的 Starlette/httpx 与 AnyIO 弃用提示。前端产物文件名与体积与 `docs/45a` §5 **逐字相同**，证明本轮改动未越出后端。`tools/trainer/` **未触碰**，故未运行其 `ruff` / `pytest`。

### 6.2 实跑命令与报告环境（本机单机型观测）

```text
$ cd backend && HOLDEM_DECISION_LATENCY_BENCHMARK=1 \
      uv run pytest -q -s tests/test_decision_latency_benchmark.py
1 passed in 1146.19s (0:19:06)
```

报告环境（白名单键，`git status` 可证**未写回任何工件**，报告只打印到终端）：

| 键 | 值 |
|---|---|
| `scope` | `local-machine-single-host-observation` |
| `platform` / `python` | `darwin` / `3.13.8` |
| `measured_at_local_time` | `2026-09-20T14:59:32` |
| `decision_samples_per_player_count` | `10000` |
| `scenario_samples_per_player_count` | `1000` |
| `state_source` | `deterministic-construction` |
| `measured_path` | `heuristic-action-distribution` |
| `lookup_runtime_integration` | `not-integrated-unmodeled` |
| `decision_budget_ms` / `p95_guidance_ms` / `p99_guidance_ms` | `100.0` / `50.0` / `80.0` |

## 7. 实跑测量结果（本机单机型观测，**不外推**）

### 7.1 基础矩阵：逐人数判定（唯一判定依据）

样本量：每人数 `10000`（跨 4 街合并），总计 `80000`。

| 人数 | 样本 | 中位数 ms | p95 ms | p99 ms | max ms | 超时数（≥100ms） | 硬预算判定 |
|---|---:|---:|---:|---:|---:|---:|---|
| 2 | 10000 | 5.2748 | 7.9823 | 8.1750 | 22.9237 | 0 | 未观察到超预算决策 |
| 3 | 10000 | 7.9139 | 10.6352 | 10.8584 | 23.9943 | 0 | 未观察到超预算决策 |
| 4 | 10000 | 11.0184 | 13.3270 | 14.0956 | **91.0890** | 0 | 未观察到超预算决策 |
| 5 | 10000 | 13.6596 | 16.1538 | 20.2409 | 46.0710 | 0 | 未观察到超预算决策 |
| 6 | 10000 | 15.9640 | 18.2818 | 19.1360 | 38.1176 | 0 | 未观察到超预算决策 |
| 7 | 10000 | 18.6129 | 21.0195 | 23.1062 | 59.4583 | 0 | 未观察到超预算决策 |
| 8 | 10000 | 21.3131 | 28.0998 | 42.1221 | **92.6219** | 0 | 未观察到超预算决策 |
| 9 | 10000 | 23.7091 | 28.1281 | 41.0636 | **93.6615** | 0 | 未观察到超预算决策 |

- **硬预算**：8 个人数全部 `超时数 = 0`，`max < 100.0ms` → 在本机该样本上**未观察到超预算决策**。
- **建议余量**（只报告不判定）：全部人数的 `p95 < 50.0ms` 且 `p99 < 80.0ms` → 建议余量亦全部满足。
- **必须同时看到的事实**：极端样本已接近硬预算——`9-turn` 的 `max = 93.6615ms`（约为硬预算的 `93.7%`），`8-flop` 为 `92.6219ms`，`4-turn` 为 `91.0890ms`。**不得**把本表表述为「余量充足」；单次样本距硬预算仅约 `6.3ms`。

### 7.2 基础矩阵：逐街明细（覆盖证据，不单独作判定）

| 人数-街 | 样本 | 中位数 ms | p95 ms | p99 ms | max ms | 超时数 |
|---|---:|---:|---:|---:|---:|---:|
| 2-preflop | 2500 | 0.0012 | 0.0013 | 0.0013 | 0.0072 | 0 |
| 2-flop | 2500 | 6.1508 | 6.4884 | 6.8835 | 13.4689 | 0 |
| 2-turn | 2500 | 7.8162 | 8.1410 | 8.3255 | 22.9237 | 0 |
| 2-river | 2500 | 5.1599 | 5.3875 | 5.5303 | 14.5123 | 0 |
| 3-preflop | 2500 | 0.0012 | 0.0013 | 0.0014 | 0.0204 | 0 |
| 3-flop | 2500 | 8.7405 | 9.0223 | 9.1939 | 20.0081 | 0 |
| 3-turn | 2500 | 10.3994 | 10.8031 | 11.0590 | 23.9943 | 0 |
| 3-river | 2500 | 7.7615 | 8.0954 | 8.3172 | 17.0374 | 0 |
| 4-preflop | 2500 | 0.0012 | 0.0013 | 0.0013 | 0.0048 | 0 |
| 4-flop | 2500 | 11.3185 | 11.8079 | 12.3101 | 47.2496 | 0 |
| 4-turn | 2500 | 13.1037 | 13.7834 | 17.0182 | **91.0890** | 0 |
| 4-river | 2500 | 10.3416 | 10.6416 | 10.8620 | 24.2940 | 0 |
| 5-preflop | 2500 | 0.0012 | 0.0012 | 0.0013 | 0.0045 | 0 |
| 5-flop | 2500 | 13.8448 | 14.1802 | 14.5800 | 27.8100 | 0 |
| 5-turn | 2500 | 15.7392 | 17.2108 | 25.4190 | 46.0710 | 0 |
| 5-river | 2500 | 12.9180 | 14.8409 | 25.0304 | 36.5881 | 0 |
| 6-preflop | 2500 | 0.0012 | 0.0015 | 0.0025 | 0.0382 | 0 |
| 6-flop | 2500 | 16.2777 | 16.8817 | 18.7642 | 38.1176 | 0 |
| 6-turn | 2500 | 18.0809 | 18.7457 | 21.5300 | 37.9361 | 0 |
| 6-river | 2500 | 15.2032 | 15.6305 | 16.3024 | 31.1134 | 0 |
| 7-preflop | 2500 | 0.0011 | 0.0013 | 0.0015 | 0.0549 | 0 |
| 7-flop | 2500 | 19.0056 | 19.9354 | 25.8533 | 59.4583 | 0 |
| 7-turn | 2500 | 20.7160 | 21.4457 | 26.2403 | 38.2911 | 0 |
| 7-river | 2500 | 17.9470 | 18.5982 | 23.1399 | 40.2054 | 0 |
| 8-preflop | 2500 | 0.0012 | 0.0012 | 0.0013 | 0.0117 | 0 |
| 8-flop | 2500 | 21.5647 | 23.0066 | 29.6360 | **92.6219** | 0 |
| 8-turn | 2500 | 25.0385 | 38.2850 | 48.3999 | 76.4382 | 0 |
| 8-river | 2500 | 20.7492 | 22.9295 | 35.2355 | 80.8450 | 0 |
| 9-preflop | 2500 | 0.0012 | 0.0017 | 0.0018 | 0.0141 | 0 |
| 9-flop | 2500 | 24.1952 | 28.7655 | 47.0938 | 83.3337 | 0 |
| 9-turn | 2500 | 25.7120 | 30.6908 | 46.0773 | **93.6615** | 0 |
| 9-river | 2500 | 22.8905 | 23.9824 | 28.9479 | 52.6235 | 0 |

翻前低于 `0.06ms`（Chen 分档，不做蒙特卡洛）；成本集中在翻后，且随「自己以外未弃牌座位数」单调上升（`2-flop` 约 `6.15ms` → `9-flop` 约 `24.20ms`）。`8/9` 的 `turn/flop` 尾部最厚（`8-turn p99 = 48.40ms`、`9-flop p99 = 47.09ms`）。

### 7.3 补充场景（补充证据，**不进入逐人数判定**）

每（场景, 人数）`1000` 次决策，仅 `6/7/9` 有实测值。

| 场景 | 人数 | 样本 | 中位数 ms | p95 ms | p99 ms | max ms | 超时数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `deep-stack`（200 BB） | 6 | 1000 | 15.8096 | 18.2036 | 18.5105 | 28.1078 | 0 |
| `deep-stack` | 7 | 1000 | 18.4194 | 20.7323 | 21.7757 | 33.9096 | 0 |
| `deep-stack` | 9 | 1000 | 23.3207 | 25.6459 | 26.1631 | 36.8406 | 0 |
| `shallow-stack`（20 BB） | 6 | 1000 | 15.8125 | 18.2378 | 19.9241 | 33.5019 | 0 |
| `shallow-stack` | 7 | 1000 | 18.3025 | 20.5751 | 20.8545 | 35.7295 | 0 |
| `shallow-stack` | 9 | 1000 | 23.2550 | 25.5296 | 26.0311 | 38.5727 | 0 |
| `strong-draw`（翻牌/转牌） | 6 | 1000 | 17.4744 | 18.0513 | 18.6111 | 41.5394 | 0 |
| `strong-draw` | 7 | 1000 | 19.9091 | 20.8562 | 21.9944 | 38.5225 | 0 |
| `strong-draw` | 9 | 1000 | 24.7859 | 25.8958 | 28.6021 | 41.0521 | 0 |
| `long-session`（河牌连续流） | 6 | 1000 | 15.2131 | 15.5626 | 15.8772 | 30.5094 | 0 |
| `long-session` | 7 | 1000 | 17.8319 | 18.3132 | 18.7987 | 30.6064 | 0 |
| `long-session` | 9 | 1000 | 22.6337 | 23.1613 | 24.7349 | 37.9698 | 0 |

观察（只作描述，不作结论）：

1. **筹码深度**：深/浅筹码与默认筹码的分布几乎重合（`9` 的中位数 `23.32 / 23.26 / 23.71 ms`）。筹码深度通过策略的隐含赔率与下注夹紧分支间接进入计算，但**未**观察到对决策耗时的一阶影响。
2. **强听牌**：该场景中位数略高于同街道的基础矩阵单元（`6/7/9` 分别 `17.47 / 19.91 / 24.79 ms`），与「触达补牌统计分支」的预期方向一致；但**未**做对照实验，不主张因果。
3. **长会话**：同一河牌局面连续 `1000` 次决策的分布与基础矩阵的河牌单元接近，**未**观察到随时间上升的趋势。该场景是**同一进程内的连续决策流**代理，**不是**多手真实会话，也**不产生**任何稳定性或漂移结论（代码中没有稳定性生产者）。

### 7.4 未覆盖面（如实声明，不插值、不折算）

| 维度 | 未覆盖项 | 状态 |
|---|---|---|
| 补充场景的人数 | `2, 3, 4, 5, 8` | **未测**：`docs/20` §6.3 明确场景验收重点为 6/7/9，场景层为补充证据；报告中以 `DecisionCoverageGap(dimension="player-count")` 显式声明，**不带任何延迟值** |
| `strong-draw` 的街 | `preflop`、`river` | **未测**：该场景定义为强听牌路径，只在翻牌/转牌存在；以 `DecisionCoverageGap(dimension="street")` 显式声明 |
| 各街 `long-session` | `preflop`、`flop`、`turn` | **未测**：该场景定义为连续决策流，只落在河牌 |
| 基础矩阵 | 无缺口 | 2–9 × 4 街全部有实测值，`baseline.uncovered == ()` |

逐人数判定**没有**任何合并均值参与：报告字段集不含均值/合计字段，且单个人数的汇总在结构上无法充当「全人数通过」。

### 7.5 必须同时声明的三件事

1. **被计时的是启发式单次决策，不是含查表的端到端决策。** 离线查表**未接入**运行时决策路径，因此「接入查表后的实时成本」本轮**未建模**（报告中 `lookup_runtime_integration = "not-integrated-unmodeled"`）。**不得**把本文件任何数字与既有查询路径数字（`docs/41a` §5）混读，也**不得**把两者相加或相除。
2. **旧样本未被沿用。** `docs/20` §2.8 的旧样本（翻后 1–4 对手，中位数 5.314–13.865 ms）是**方案 B 之前**、单牌面的观测，本轮数字是**独立重新测量**的结果，两者不可互相替代；`docs/21` §4.2 / §6.4 声明的「修复后未复测」在本轮被**首次复测**。
3. **有限样本不能证明未来不会超时。** 观测到 8 个人数全部 `超时数 = 0`，只能表述为「在本机该样本上未观察到超预算决策」。极端样本已达 `93.66ms`，距硬预算仅约 `6.3ms`；不同的机器、负载、Python 版本、GC 时机或局面分布均可能改变尾部。本轮**未**对极值样本的成因（调度噪声 / GC / 页面回收）做对照调查，因此**不主张**其为调度噪声。

## 8. 版本影响与兼容性

| 对象 | 实际行为 |
|---|---|
| `heuristic.py` 决策语义 | **零改动**（只被调用；阈值、分支、`_num_pot_contenders` 语义不变） |
| `equity()` 的 `ties/2` 与调用采样数 | **零改动**；策略默认采样数未被改动 |
| 参考实现 / 保守判据 / 固定种子 | **零改动** → **不触发** `docs/37` §3.1 升版 |
| `lookup_budget.py` | **零改动**：`DECISION_BUDGET_MS` / `P95_GUIDANCE_MS` / `P99_GUIDANCE_MS` / `RECOMMENDED_DECISION_SAMPLES` / `PLAYER_COUNT_RANGE` / `MEASUREMENT_SCOPE` 取值不变；既有 14 条断言继续通过 |
| 既有策略语义 / 分派 | **零改动**；新模块**无生产调用方**，未新增任何运行时回退动作 |
| API 与前端 | **零改动**；不新增或改名字段；不恢复已移除的前端策略选择器 |
| 数据库 | **不加列、不迁移**；真实数据库只读，未被写入 |
| 旧历史 / 旧响应 | 结构不变；`history_json` 未被改写 |
| 既有实验工件 | **只读**：`/Users/bryanylliu/holdem-campaigns/` 仍为 8 个目录、11 份 `strategy.json`（本轮未打开任何产物） |
| 锁文件 | `backend/uv.lock` 与 `frontend/package-lock.json` 零改动（不新增依赖） |
| 缺项与未覆盖面的处置 | 只声明状态与原因，不给延迟值；**不**插值、**不**用 6/7 折算 2–9、**不**用最近桶或补零 |

## 9. 预算核算（实跑后更正）

```text
本轮实跑墙钟耗时（本机，含 92000 次决策与报告打印）   1146.19 s ≈ 19.1 min
设计期临时探测脚本（已删除，不属交付物）               约 0.7 min
```

- `docs/46` §6 的预估为「20 分钟以内」，**实测 19.1 分钟，与预估相符**（设计期抽样对耗时的估算误差在 `5%` 以内）。
- 本轮**未消耗任何本机实验预算 / authorization**：这是**只读的本机性能观测**，不是受监督训练运行，未新建 campaign、未追加 seed、未重试任何已消耗 authorization。
- 仍**不**上云、**不**转 GPU、**不**无限重跑；训练相关进程峰值 RSS 合计 `8 GiB`、保留实验工件 `1 GiB` 上限不变。

## 10. 边界声明与不得声称

- 本轮改动是**测量口径与一次本机观测**，**不是** CFR 接入，也**不构成**任何质量、收敛或生产可用性证据。
- 所有数字均为**本机单机型观测**（`local-machine-single-host-observation`：`darwin` / `Python 3.13.8`），**不外推**云环境或其他机型；**有限样本不能证明未来不会超时**。
- **不得**把 P0-2 的**查询路径**数字（`docs/41a` §5）表述为端到端 Bot 决策延迟；**不得**把 `docs/20` §2.8 的旧样本表述为修复后结果；**不得**用 6/7 结果插值或折算 2–9。
- 「**接入 lookup 后的实时成本**」在查表未接入运行时前保持**未建模**；本轮**未**给出、也**未**暗示该数字。
- **不得**把本轮结果表述为「性能达标可上生产」；`<100ms` 是**实时 Bot 决策**预算，**不是**整手复盘预算，也**不覆盖**未来的查表、范围模型或逐池收益接入。
- **不得**把极值样本（`91–93.7ms`）淡化为「无影响」，也**不得**反过来升级为「必然超时」；成因**未调查**。
- **单元测试不等于 A6/A7 实验结果**；本轮**不新增**任何质量、收敛或稳定性结论。
- `long-session` 是连续决策流的成本观测，**不是**稳定性证据；任何稳定性结论都必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者）。
- 未改写 `docs/20` 至 `docs/45a`；未改 `lookup_budget.py` 的既有常量取值；未改 `heuristic.py` 决策语义与 `equity()`。
- 本轮共两次提交，均为**本地**提交，**未 push**。

## 11. 未做事项与下一步唯一建议动作

未做：

- **未接入 runtime**：未把查表接进 Bot 决策路径，未实现任何回退动作；`registry` / API 的策略分派零改动。
- **未实现未建模项**：范围假设、逐池货币收益、真实规则边界契约仍**无生产调用方**，本轮只作声明性引用。
- 未改 `poker/**`、`analysis/**`、`api/**`、`frontend/**`、`storage/models.py`、锁文件、真实数据库、`tools/trainer/**`、`docs/20` 至 `docs/45a`。
- 未启用 `docs/39` 的质量门槛；未恢复已移除的前端策略选择器。
- 未新增受监督运行或 campaign；未追加 seed；未重试任何已消耗 authorization；未上云、未转 GPU。
- **未调查极值样本的成因**（未做调度噪声 / GC 对照实验），因此未对其做任何归因。
- 未把基础矩阵的补充场景扩展到 `2/3/4/5/8`（按 `docs/46` §4.3 聚焦 6/7/9 并显式声明未覆盖）。
- 未 push。

至此 `docs/35` §4.2 的 **P1 组（P1-1 … P1-5）全部完成**。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**从 `docs/35` §4.2 的 P2 组中选定唯一一项并单独授权**。若需建议，优先级最高的是 **P2-1（2–9 人产品验收）**——它是唯一覆盖「用户可见上限 9 人」的需求项，且与 P2-2（N=9 更强结论）、P2-3（历史 `pot_results` 不一致）、P2-4（稳定性生产者）互不依赖，可独立排期。若更关心实时成本的尾部风险，则应单独授权一个**极值样本成因调查切片**（对同一测量对象做受控对照复测），它**不**由本轮自动覆盖，也**不**改变本轮的硬预算判据。
