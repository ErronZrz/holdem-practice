# 39a M8：P0-6 CFR/教学上线质量门槛——实施与验证回执

> 日期：2026-09-18。
>
> 本文件接在 `docs/39` 之后，沿用 `docs/30` D6 的编号族约定：`docs/39` 为规格与裁定冻结，本文件为同一轮的**实施与验证回执**。`docs/20` 至 `docs/39` 未被改写。
>
> 本文件只记录已实际落地的代码、测试与实跑输出；**不产生任何策略、质量或资源证据**，也**未启用任何门槛**。

## 1. 本轮提交与授权

| 次序 | commit | 内容 |
|---|---|---|
| 1 | `65cb4b2` | `docs/39` 规格与裁定冻结（仅文档） |
| 2 | 本文件同批 | P0-6 判定层实现、导出、单元测试、`docs/39a` |

用户答复原文（照录，四项均为推荐口径）：

- 门槛是否启用：「只冻结定义+判定函数，暂不启用（维持 (c)，推荐）(把「若将来设门槛必须遵守的完整规则」+ 可复算的纯判定函数入库；判定结果只作解释性输出，不绑定验收、不产生合格/不合格措辞。不反转决策一)」
- 作用对象：「以 probes.gains 为判定对象 + 双向 results[].delta 如实报告（推荐）(gains 已钳位、只反映「阈值策略更强」单侧；双向 delta 正负都报，避免只看一侧)」
- 人数区分：「区分：各自独立判定与报告，禁止跨人数归因（推荐）(N=6 与 N=7 分别出具判定，不用一侧结果外推另一侧)」
- 改动面：「允许在 tools/trainer/ 下新增只读门槛模块 + 单元测试（推荐）(纯函数、不读网络、不改任何既有训练/评估原语；可被 pytest 覆盖，是「可复算」最可靠的形式)」

据此本轮**只做 P0-6 的「定义 + 可复算判定层」**，**不启用门槛**，`docs/35` §3.1 决策一 (c) **未被反转**。超线处置沿用 `docs/31a` §3.3 已冻结口径，本轮未重新裁定。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 6]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -2 --oneline
175b952 feat: declare teaching reference scope and limitations with a non-mode contract
b6a0bbd docs: freeze p0-7 teaching reference and opponent separation contract specs

$ git rev-parse HEAD -> 175b95263d55502e460652a4b7779884a14837be

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
```

工作区干净；`ahead 6` 属未 push 的正常形态。未做任何 `reset` / `clean` / `stash` / `checkout`；**未 push**；未消耗任何本机实验预算。

## 3. 实际改动清单（文件级）

### 3.1 新增

| 文件 | 内容 |
|---|---|
| `tools/trainer/src/multiplayer_cfr/quality_gate.py` | 只读多 seed 判定层：`ProbeDelta` / `SeedObservation` / `ThresholdVerdict` / `observation_from_measurement` / `evaluate_gains_threshold` |
| `tools/trainer/tests/test_multiplayer_quality_gate.py` | 17 个用例：多 seed 规则、观测校验、复算已冻结读数、措辞守卫、记录提取 |
| `docs/39`、`docs/39a` | 规格冻结与实施回执 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `tools/trainer/src/multiplayer_cfr/__init__.py` | 新增 12 个导出（`DEFAULT_THRESHOLD` / `MIN_OBSERVATIONS` / `STATUS_EXCEEDS` / `STATUS_NOT_OBSERVED` / `ProbeDelta` / `QualityGateError` / `SeedObservation` / `ThresholdVerdict` / `evaluate_gains_threshold` / `observation_from_measurement` 等），不改变任何既有导出 |

### 3.3 未触碰（边界逐项核验）

- **零改动**：`evaluation.py`、`measurement.py`、`experiment_record.py`、`supervised_measurement.py`、`mccfr.py`、`manifest.py`、`campaign*.py`、`supervisor.py` 等**全部既有训练 / 评估 / 测量 / 监督原语**；`kuhn_cfr/**` 未触碰。
- **零改动**：`backend/**`、`frontend/**`、`README.md`、`AGENTS.md`、锁文件、真实数据库。
- 未新增任何 JSON schema、未新增依赖、未写回任何已落盘工件。
- `git status` 实测改动面（无任何多余产物）：

```text
 M tools/trainer/src/multiplayer_cfr/__init__.py
?? tools/trainer/src/multiplayer_cfr/quality_gate.py
?? tools/trainer/tests/test_multiplayer_quality_gate.py
```

## 4. 判定层的实际形态

| 名称 | 实际语义 |
|---|---|
| `DEFAULT_THRESHOLD` | `Fraction(1, 20)`，沿用既有 0.05 解释线；**不是**本轮新设的门禁线 |
| `MIN_OBSERVATIONS` | `2`；观测数不足即明确失败（**单 seed 不判定**） |
| `ProbeDelta` | 一条 `(player, probe_id, delta)`；只接受精确 `Fraction`，浮点直接失败 |
| `SeedObservation` | 单 seed 观测；构造时校验：人数 ≥ 2、`gains` 长度等于人数且非负、`delta` 覆盖全部座位、`gains[p] == max(0, 同座位 delta 最大值)` |
| `ThresholdVerdict` | 判定结果；`status` 只在 `exceeds-threshold-observed` / `threshold-not-observed` 取值；`summary()` 同时给出**最大正偏离与最小负偏离** |
| `evaluate_gains_threshold` | 纯函数；单 seed、重复 seed、混合人数均明确失败，不产生判定 |
| `observation_from_measurement` | 从**已严格验证**的 `MeasurementRecord` 提取观测；`probes.status != "completed"` 明确失败，避免把未测量值当成零偏离 |

只读边界（已落地）：模块不读文件系统与网络、不读环境变量、不调用任何训练 / 评估 / 测量原语、不写回任何工件；`observation_from_measurement` 只消费调用方已读入并验证过的记录对象。规范有理数解析复用既有的 `RationalValue`，**未另写一套解析与约分逻辑**。

`gains` 的钳位派生关系由 `SeedObservation` 强制校验：判定对象若与双向 delta 自相矛盾，构造即失败——这从结构上防止「只报单侧方向」的读数。

## 5. 复算已冻结证据（实测输出）

判定层对**2 份跨 seed 报告**（N=6 的 campaign-7、N=7 的 campaign-6，各 4 个预注册 seed）逐值复算，实测输出：

```text
N=6 {"player_count": 6, "threshold": "1/20", "seeds": [1215, 20260918, 3311, 6922],
     "exceeded_seeds": [1215], "max_gain": "805839/1000000", "max_gain_seed": 1215,
     "max_gain_player": 0, "max_positive_delta": "805839/1000000",
     "min_negative_delta": "-147439/200000", "status": "exceeds-threshold-observed"}

N=7 {"player_count": 7, "threshold": "1/20", "seeds": [1215, 20260918, 3311, 7926],
     "exceeded_seeds": [], "max_gain": "0", "max_gain_seed": 1215, "max_gain_player": 0,
     "max_positive_delta": "0", "min_negative_delta": "-178037/250000",
     "status": "threshold-not-observed"}
```

与 `docs/34b` §9.4 的读数一致：N=6 侧 `max_p gains = 0.805839`（座位 0、seed 1215）**存在超过 0.05 的阈值偏离**；N=7 侧 4 个 seed **未观察到**。复算同时如实给出两侧的**最负偏离**（`-0.737195` 与 `-0.712148`），避免只看 `gains` 的单侧方向。

**这一步不产生任何新证据**：输入是既有已冻结读数，输出是解释性判定，两侧均未被赋予「合格 / 不合格」含义。

## 6. 新增测试（17 个）

```text
$ uv run pytest -q --collect-only tests/test_multiplayer_quality_gate.py | tail -1
17 tests collected
```

| 验收项 | 对应用例 | 锁定的事实 |
|---|---|---|
| C3 单 seed 不判定 | `test_single_seed_is_not_judged`、`test_duplicate_seeds_are_rejected` | 观测数 <2 或 seed 重复时**明确失败**，不回到默认结论 |
| C4 人数隔离 | `test_mixed_player_counts_are_rejected`、`test_verdicts_are_isolated_per_player_count` | 混合人数失败；N=6 / N=7 判定互不影响 |
| C2 可复算 | `test_recomputes_frozen_n6_reading`、`test_recomputes_frozen_n7_reading`、`test_verdict_does_not_mutate_observations` | 对已冻结读数给出确定结果且不修改入参 |
| 观测契约 | `test_observation_rejects_gains_that_are_not_clamped_deltas`、`test_observation_rejects_negative_gains`、`test_observation_requires_deltas_for_every_seat`、`test_observation_rejects_float_deltas` | 钳位派生、非负、全座位覆盖、精确有理数四项校验 |
| C5 非合格性措辞 | `test_status_wording_contains_no_acceptance_terms`、`test_summary_reports_both_directions` | 状态取值不含「合格 / 不合格 / 通过 / 达标」；报告含双向偏离 |
| 记录提取 | `test_observation_from_measurement_reads_completed_probes`、`test_observation_from_measurement_rejects_unfinished_probes`、`test_observation_from_measurement_rejects_non_rational_values` | 只读提取已完成的 probe；未完成与非规范有理数明确失败 |
| 阈值健全性 | `test_threshold_must_be_positive` | 非正阈值与浮点阈值明确失败 |

## 7. 实跑验证输出

```text
$ cd tools/trainer && uv run ruff check .
All checks passed!

$ cd tools/trainer && uv run pytest -q
197 passed in 185.43s (0:03:05)          （180 → 197，新增 17）

$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
208 passed, 2 warnings in 10.41s         （与上一轮相同，未受影响）

$ cd frontend && npm run build
✓ 23 modules transformed.
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 545ms
```

后端与前端输出与上一轮**逐字相同**，证明本轮改动未越出 `tools/trainer/`。

## 8. 版本影响与兼容性

| 对象 | 实际行为 |
|---|---|
| 门槛状态 | **未启用**：判定结果只作解释性输出，不绑定验收、不阻塞接入；`docs/35` §3.1 决策一 (c) 与 `docs/33` §7 / `docs/34` §5 继续有效 |
| 既有原语 | 训练 / 评估 / 测量 / 监督模块零改动；`gains` 的生产者仍是 `evaluate_threshold_probes`，本轮**未新增任何测量能力** |
| 已落盘工件 | 只读消费，未写回、未迁移、未回填；`/Users/bryanylliu/holdem-campaigns/` 原样保留 |
| `__init__.py` | 仅新增导出，既有导出名与语义不变 |
| 后端 / 前端 | 零改动；后端 `208 passed` 与前端构建输出与上一轮一致 |
| 预算 | 本轮**未消耗任何实验预算**（无新受监督运行；仅单元测试与文档撰写） |

## 9. 边界声明与不得声称

- 本轮改动是**门槛定义与只读判定层**，**不是**门槛签收，**不是** CFR 接入，也**不构成任何质量证据**。
- 判定层的输出**不代表合格 / 不合格 / 通过 / 达标**；不得据此改变候选 A 的收尾口径。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- 阈值 probe 的收益差是**精确**计算（全 chance 枚举），但「预注册阈值策略」只是有限的探针集合，**不是** best response，也**不是** exploitability 度量。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」；代码中仍**不存在**稳定性生产者。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据**（本轮即属此情况）。
- 未改写 `docs/20` 至 `docs/39`。

## 10. 未做事项与下一步唯一建议动作

未做：

- **未启用门槛、未设任何合格线**；未反转 `docs/35` §3.1 决策一；未改动 `docs/31a` §3.3 的超线处置。
- 未实施 `docs/35` §4 清单中 P0-6 以外的任何一项；P0-2 / P0-3 与 P1 / P2 组全部未动。
- 未改动任何既有训练 / 评估 / 测量 / 监督原语；`kuhn_cfr/**` 零改动；未新增 JSON schema 或依赖。
- 未新增受监督运行或 campaign；未追加 seed；未重试任何已消耗 authorization；未消耗实验预算；未做云端操作。
- 未改动后端与前端；未改锁文件与真实数据库。
- 未 push（`ahead 8` 由用户决定何时推送）。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**实施 `docs/35` §4.2 的 P0-3（抽象映射、覆盖与回退）**。理由：按 `docs/35` §4.3 的依赖，P0-7 与 P0-6 已完成，P0 组只剩 **P0-3 → P0-2** 这条链路，且顺序不可交换——`P0-3` 先定义「抽象键 → 生产局面」的映射与抽象外/版本不匹配的**明确失败**与回退约定，`P0-2` 的 lookup 性能基准才有可比口径（否则测的是没有覆盖定义的查询）。P0-3 属契约层、不引入新实验，风险与 P0-1 / P0-4 / P0-5 / P0-7 同级；`docs/26` §10 已给出受控抽象投影与失败语义的既有口径可直接复用。
