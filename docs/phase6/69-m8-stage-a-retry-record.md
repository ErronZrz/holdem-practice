# 69 M8：阶段 `A` 重试记录（`iqv` 族集，有效轮次）

> 日期：2026-09-23。
>
> 本文件接在 `docs/phase6/68-m8-stage-a-run-record.md` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。归档路径按 `docs/README.md` 的维护约定：本文件属第四次验证族，归档于 `phase6/`。
>
> 本文件记录 `J3` 阶段 `A` 的**重试**：按 `docs/phase6/68` §6 定位的参量缺陷（漏传 `--family-set=iqv`）修正命令后重跑，产物写入新目录 `runs/stage-a-retry/`；`runs/stage-a/` 的失败轮产物**原样保留**。
>
> **本文件不产生判据读数**：只记录机械字段（覆盖、手数、资源、门禁）。判据读数属后续的判定动作，须单独进行。

## 1. 授权原文与边界

用户裁定（选项照录）：

> 「A. 授权阶段 A 重试（单轮，iqv 族集）」

该选项随附理由由助手在选项中提出、随选项被选定，此处照录以免与用户原话混淆：

> 「本轮产物因族集参量缺陷不可用，重试是唯一能把阶段 A 变成有效的一步；命令与 v8 逐字一致（`--family-set=iqv --emit-observations`），写入 `runs/stage-a-retry/`，保留失败轮原样；包络同前。」

| 项 | 内容 |
|---|---|
| 被授权 | 在 `-v9` 下**单轮**重跑阶段 `A`（带 `--family-set=iqv`），写入 `runs/stage-a-retry/`，并出独立回执 |
| 明确排除 | 阶段 `B`；确定性补算；删除或改写失败轮产物；改任何代码；改判据 / 门槛 / 族集 / 机会分母 / 估值块；默认策略切换；推送 |
| 未消耗 | **未消耗**阶段 `B` 与补算的任何授权；`docs/37` §3.1 **未触发** |

## 2. 运行前只读基线核验

```text
$ <v9>/runs/stage-a/mixed-validation-stage-A.json      sha256 ffdd79f49dd0aa5f…（未变）
$ <v9>/runs/stage-a/mixed-observations-stage-A.json    sha256 32d9d677fc75a284…（未变）
$ ls -d <v9>/runs/stage-a-retry
ls: <v9>/runs/stage-a-retry: No such file or directory
```

`<v9>` = `/Users/bryanylliu/holdem-mixed-bot-validation-v9`。运行前该目录内为 `3` 个文件（清单 + 失败轮报告与观测）；清单 `sha256` 仍为 `499258c9…`。

## 3. 实跑命令（与 v8 逐字一致，**已带族集**）

```text
$ cd backend && /usr/bin/time -l uv run python -m tests.mixed_bot_validation \
    /Users/bryanylliu/holdem-mixed-bot-validation-v9/input/frozen-fixture-manifest.json \
    A /Users/bryanylliu/holdem-mixed-bot-validation-v9/runs/stage-a-retry \
    --allow-stage=A --family-set=iqv --emit-observations > /dev/null
exit=0
```

进程级实测（`/usr/bin/time -l`，含 `uv` 父进程）：

| 项 | 值 |
|---|---|
| `real` | `5.27 s` |
| `user` / `sys` | `4.85 s` / `0.11 s` |
| `maximum resident set size` | `193,839,104 B`（`184.86 MiB`） |
| `peak memory footprint` | `10,551,680 B` |

## 4. 落盘产物

| 路径 | 字节数 | `sha256` |
|---|---|---|
| `<v9>/runs/stage-a-retry/mixed-validation-stage-A.json` | `10,432,837` | `7e845cd00abaa2ca0a92e3057719cabe9b130dffab9fad4d7fcd7b616fe47d43` |
| `<v9>/runs/stage-a-retry/mixed-observations-stage-A.json` | `167,411` | `5a26864327e79f9d77d2cb16d19979dbf733f1d6593c797619b6e707c7c02d79` |

合计 `10,600,248 B`（`10.11 MiB`）。运行后 `<v9>` 内文件为 `5` 个（清单 + 失败轮 `2` + 重试 `2`）；既有八套证据目录的文件数**未变**（`5 / 4 / 4 / 4 / 4 / 5 / 7 / 7`）。

## 5. 报告自记的机械字段

| 字段 | 值 |
|---|---|
| `schema_version` / `stage` / `status` | `mixed-validation.v2` / `A` / `completed` |
| `strategy_id` / `config_digest` | `mixed-local@7` / `fd7433e35fc8260d03635774b34fbdc419ad5a04ba0448916b036e385a546665` |
| `manifest_digest` | `319cbb967d66dabdd795c19d60ab91962cd9397926ea71349583d855edc6a918`（与清单一致） |
| `violations` | `[]` |
| `coverage` | `planned_nodes 128` / `executed_nodes 125` / `not_run_nodes 0` / `structurally_not_applicable 3`；成本格 `288/288`、成本样本 `288/288`、补充场景 `24/24`；**对抗对照 `128/128`** |
| `matches` | `planned_hands 128` / `completed_hands 128` / `truncated_hands 0` / `interval_status = not-estimated-small-fixed-seed-set` |
| `resources` | `wall_seconds = 4.6460`、`cpu_seconds = 4.6124`、`peak_rss_bytes = 77,742,080`（`74.15 MiB`）、`output_bytes = 10,432,837`、`single_process = True`、`parallel = False` |
| `timing` | `decision_budget_ms = 100`；完整决策路径 `p95 0.3729 ms` / `p99 0.5076 ms` / `max 0.5365 ms`；`bot_step` `p95 0.3990 ms` / `max 0.5464 ms`；`timeout_count 0` |
| `behavior`（结构计数） | 直接分布 `1125`、逐节点行 `18000`、类别 `48`、风格间 JS 距离 `3` |
| 观测工件 | 手数 `128`、`output_bytes = 167,411` |

**与失败轮的差异**：对抗对照手数由 `64` 恢复为冻结要求的 `128`，观测工件随之由 `63,208 B` 增至 `167,411 B`；其余机械字段（节点覆盖、成本样本、补充场景、直接分布计数）逐项相同。

## 6. 包络核验与机械量对照

| 包络 | 上限 | 本轮实测 | 结论 |
|---|---|---|---|
| wall | `≤1800 s` | `4.65 s`（自记）/ `5.27 s`（进程级） | 内 |
| 峰值 RSS | `≤1 GiB` | `74.15 MiB`（自记）/ `184.86 MiB`（进程级） | 内 |
| 输出 | `≤100 MiB` | `10.11 MiB` | 内 |

**机械量对照（仅供成本外推，不是质量比较）**：v8 阶段 `A` 的自记读数为 `3.949 s` / `73.22 MiB` / `128` 手。本轮为 `4.646 s` / `74.15 MiB` / `128` 手，同量级。**不得**把两者的任何**质量**读数作同样比较（不同节点集、不同种子集、不同策略身份）。

## 7. `code_identity` 差异披露

- 清单与报告中的 `code_identity` = `ae3f74930f022a69a4b64a7fcb85188c47384a74`（**冻结时的 HEAD**）；
- 实际执行代码的 HEAD = `38a98d4281d047fe5efffa3726fd2bb4cfb9917c`（本文件的提交还会再移动 HEAD）；
- ⇒ 二者**不同**，须在每一次回执中如实标注；**不得**把清单或本轮产物说成由执行代码的 HEAD 产生。

## 8. 读数纪律与未做事项

- **本轮未计算任何质量指标**：覆盖率、类型熵、金额熵、锚点份额、三对 JS 距离、域一 / 域二差值、跨人数净值等**均未计算**；
- **未做**：阶段 `B`；确定性补算；阶段 `B` 的任何准备动作；任何代码改动；任何判据 / 门槛 / 族集 / 分母 / 估值块改动；删除或改写失败轮产物；默认策略切换；推送；
- **仍未证**：第七版在第五套样本集上的任何表现；阶段 `B` 与补算的成本与峰值 RSS（`docs/phase6/58` §13 的估时仍是估算，且补算峰值 RSS **从未有过可用估算**）。

## 9. 契约、API 与默认策略

- **未改**任何代码；API 字段、数据库列、内部契约、报告与观测 schema、artifact schema **零改动**；`MixedFixtureManifest` **未加字段**；
- **未新增**策略身份或清单；`-v9` 清单 `sha256` 未变；
- 默认策略仍为 **`heuristic@1`**；`docs/37` §3.1 **未触发**。

## 10. 不得声称

- 不得把本轮的 `status = completed` 或 `violations = []` 说成「质量获支持」「验证通过」或「已达生产门槛」。
- 不得把本轮说成判据已可判定；判据读数须在后续动作中单独计算并单独签收。
- 不得把 `runs/stage-a-retry/` 说成对失败轮 `runs/stage-a/` 的改写或替换：两者**并存**，失败轮作为缺陷证据保留。
- 不得把 §6 的机械量对照说成质量比较；不得把第五套样本集与 v6 / v7 / v8 的读数并列比较。
- 不得据此修改 `docs/` 下任何已归档文档与任何已落盘工件；不得改写 `@1`–`@7` 任一身份的历史含义。
- 不得把本记录说成对 `docs/53c` / `55g` / `56h` / `57k` 任一签收结论的反转、修正或追认。

## 11. 本篇唯一下一步

阶段 `A` 已取得**有效**回执。据 `docs/phase6/62` §12 与 `docs/phase6/58` §13.1，下一步是 **`J3` 的阶段 `B`**（单独一轮、需单独授权），且其门禁**必须引用本轮的 `runs/stage-a-retry/` 回执**，而不是 `runs/stage-a/` 的失败回执。

阶段 `B` 的已知风险（须在授权时一并声明）：`docs/phase6/58` §13.2 的估时为 `450–600 s`；**补算峰值 RSS 在 v7 / v8 两次均未归因**（v8 `958.73 MiB`、余量仅 `6.37%`），**无可靠外推依据**。**建议**：先单独授权阶段 `B`（不含补算），补算在其回执之后再单独授权。
