# 68 M8：阶段 `A` 运行记录（**本轮含运行参量缺陷，非有效阶段 A**）

> 日期：2026-09-23。
>
> 本文件接在 `docs/phase6/67-m8-fifth-fixture-freeze-record.md` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。归档路径按 `docs/README.md` 的维护约定：本文件属第四次验证族，归档于 `phase6/`。
>
> 本文件记录 `J3` 第一轮（阶段 `A`）的实跑结果与**一处由助手引入的运行参量缺陷**：**未传 `--family-set=iqv`**。因此本轮**不是**一次符合冻结口径的有效阶段 `A`；其产物**原样保留**为使缺陷证据，重试须**另行授权**并写入新目录 `runs/stage-a-retry/`（沿用 `docs/phase6/55d` 的处置先例）。
>
> **本文件不产生任何可用读数**：本轮的报告与观测工件**未被**用于计算任何质量指标，也**不得**被当作读数或证据。

## 1. 授权原文与边界

用户裁定（选项照录）：

> 「A. 授权 `J3` 阶段 A（单轮）」

该选项随附理由由助手在选项中提出、随选项被选定，此处照录以免与用户原话混淆：

> 「它是冻结顺序的第 5 步中成本最低的一步（v8 实测 `3.949 s` / `73.22 MiB`），可最先暴露清单或入口链问题；包络 `≤1800 s` / `≤1 GiB` / `≤100 MiB`；输出落到 `-v9/runs/stage-a/`（报告 + 观测），出独立回执；不碰任何既有证据目录。」

| 项 | 内容 |
|---|---|
| 被授权 | 在 `-v9` 下**单轮**运行阶段 `A`：在 `runs/stage-a/` 落盘报告与观测工件，并出独立回执 |
| 明确排除 | 阶段 `B`；确定性补算；创建 `runs/stage-a-retry/`；改任何代码；改判据 / 门槛 / 族集 / 机会分母 / 估值块；默认策略切换；推送 |
| 未消耗 | **未消耗**阶段 `B` 与补算的任何授权；`docs/37` §3.1 **未触发** |

## 2. 运行前只读基线核验

```text
$ git rev-parse HEAD
38a98d4281d047fe5efffa3726fd2bb4cfb9917c

$ git status --porcelain=v1 -uall | wc -l
0

$ shasum -a 256 <v9>/input/frozen-fixture-manifest.json
499258c993d1e59d5c2f2c218b79f2944059d216e05e3c20998675c20704a7c6

$ ls -d <v9>/runs
ls: <v9>/runs: No such file or directory
```

`<v9>` = `/Users/bryanylliu/holdem-mixed-bot-validation-v9`。运行前该目录**只有** `input/frozen-fixture-manifest.json`。

## 3. 实跑命令（**逐字记录，含缺陷**）

```text
$ cd backend && /usr/bin/time -l uv run python -m tests.mixed_bot_validation \
    /Users/bryanylliu/holdem-mixed-bot-validation-v9/input/frozen-fixture-manifest.json \
    A /Users/bryanylliu/holdem-mixed-bot-validation-v9/runs/stage-a \
    --allow-stage=A --emit-observations > /dev/null
exit=0
```

**缺陷**：命令中**缺少 `--family-set=iqv`**（见 §6）。`docs/phase6/57g` 记录的 v8 阶段 `A` 实跑命令是 `--allow-stage=A --family-set=iqv --emit-observations`。

进程级实测（`/usr/bin/time -l`，含 `uv` 父进程）：

| 项 | 值 |
|---|---|
| `real` | `4.51 s` |
| `user` / `sys` | `4.15 s` / `0.10 s` |
| `maximum resident set size` | `192,593,920 B`（`183.67 MiB`） |
| `peak memory footprint` | `10,568,088 B` |

## 4. 产物与报告自记读数

### 4.1 落盘产物

| 路径 | 字节数 | `sha256` |
|---|---|---|
| `<v9>/runs/stage-a/mixed-validation-stage-A.json` | `10,413,245` | `ffdd79f49dd0aa5f2c91fb4f27cf1ab8652ab5bef52b2e255d5e741c0ac764a6` |
| `<v9>/runs/stage-a/mixed-observations-stage-A.json` | `63,208` | `32d9d677fc75a2841da616deabf769af79aa35b48e67c9cccf43e36fb8851c66` |

合计落盘 `10,476,453 B`（`9.99 MiB`）。运行后 `<v9>` 内文件为 `3` 个（清单 + 报告 + 观测）；既有八套证据目录的文件数**未变**（`5 / 4 / 4 / 4 / 4 / 5 / 7 / 7`）。

### 4.2 报告自记的资源与门禁字段（机械字段，**不是质量读数**）

| 字段 | 值 |
|---|---|
| `schema_version` / `stage` / `status` | `mixed-validation.v2` / `A` / `completed` |
| `strategy_id` / `config_digest` | `mixed-local@7` / `fd7433e35fc8260d03635774b34fbdc419ad5a04ba0448916b036e385a546665` |
| `manifest_digest` | `319cbb967d66dabdd795c19d60ab91962cd9397926ea71349583d855edc6a918`（与 `docs/phase6/67` 一致） |
| `code_identity` | `ae3f74930f022a69a4b64a7fcb85188c47384a74`（来自清单，见 §7） |
| `violations` | `[]` |
| `resources` | `wall_seconds = 3.9554`、`cpu_seconds = 3.9105`、`peak_rss_bytes = 76,677,120`（`73.13 MiB`）、`output_bytes = 10,413,245`、`single_process = True`、`parallel = False` |
| `coverage` | `planned_nodes 128` / `executed_nodes 125` / `not_run_nodes 0` / `structurally_not_applicable 3`；成本格 `288/288`、成本样本 `288/288`、补充场景 `24/24`；**对抗对照 `64/64`（缺陷所在）** |
| `matches` | `planned_hands 64` / `completed_hands 64` / `truncated_hands 0` / `interval_status = not-estimated-small-fixed-seed-set` |
| `timing` | `decision_budget_ms = 100`；完整决策路径 `p95 0.4185 ms` / `p99 0.7723 ms` / `max 0.9529 ms`，`timeout_count 0`；`bot_step` `max 0.9938 ms` |
| `behavior`（结构计数） | 直接分布 `1125`、逐节点行 `18000`、类别 `48`、风格间 JS 距离 `3` |

**进程级 RSS 与报告自记 RSS 的口径不同**：`183.67 MiB` 是 `/usr/bin/time -l` 对整个 `uv` 调用（含父进程与解释器驻留）的读数；`73.13 MiB` 是本模块自记的峰值。**两者都必须照实标注**，不得混用，也不得只报有利的一个。

## 5. 包络核验

| 包络 | 上限 | 本轮实测 | 结论 |
|---|---|---|---|
| wall | `≤1800 s` | `3.96 s`（报告自记）/ `4.51 s`（进程级） | 内 |
| 峰值 RSS | `≤1 GiB` | `73.13 MiB`（自记）/ `183.67 MiB`（进程级） | 内 |
| 输出 | `≤100 MiB` | `9.99 MiB` | 内 |

## 6. 缺陷：漏传 `--family-set=iqv`（本轮的关键事实）

**现象**：本轮报告的 `matches.planned_hands` 与 `coverage.adversarial_hands_*` 均为 **`64`**，观测工件含 **`64`** 手；而 v8 阶段 `A` 对应值为 **`128`**。

**成因（已定位，只读核对）**：

- 阶段 `A` 的对抗排期条数 = `族个数 × 2`（`mixed-focus` / `legacy-focus`）× `8`（人数）；
- 族集有两套：`first-batch`（`4` 族 ⇒ 阶段 `A` **`64`** 手）与 `iqv`（`8` 族 ⇒ 阶段 `A` **`128`** 手）；
- 入口的 `--family-set` **默认取 `first-batch`**；本轮命令未显式给出，因此落到 `64` 手。

**为什么这是缺陷而不只是参量差异**：

1. 冻结判据原文要求「对手族集沿用 `--family-set=iqv` 的既有 `8` 族：**不得**增删、重定义或替换」（`docs/phase6/66` §6，转写自 `docs/55` §10.5）；用 `first-batch` 运行等价于**替换族集**；
2. 清单自身声明的阶段计划文本写的是「对抗对照 **`128`** 手」（`stage_plan[0]`），与本轮实际执行的 `64` 手**不一致**——报告与自己的清单自述互相矛盾；
3. v8 的实跑命令明确带有 `--family-set=iqv`（`docs/phase6/57g`）。

⇒ **本轮不是一次符合冻结口径的有效阶段 `A`**；其对抗探针体量只有应有的一半。

**观测工件规模差异（`63,208 B` vs v8 的 `179,574 B`）已归因**：观测工件逐手记录，手数 `64` vs `128` 是规模差的主因（`128 / 64 = 2`），叠加每手行动数不同（本轮逐手行数合计 `836`、v8 为 `2606`）。

## 7. `code_identity` 差异披露（必须逐次如实标注）

- 清单与报告中的 `code_identity` = `ae3f74930f022a69a4b64a7fcb85188c47384a74`，即**冻结时的 HEAD**；
- 实际执行代码的 HEAD = `38a98d4281d047fe5efffa3726fd2bb4cfb9917c`（本文件的提交还会再移动 HEAD）；
- ⇒ **两者不同**（冻结后 `docs/phase6/67` 的回执提交已使 HEAD 前移）。这是「先冻结、后落回执」的固有结果，**必须**在每一次回执中标注；**不得**把本清单或本轮产物说成由 `38a98d4…` 产生。

## 8. 处置（沿用 `docs/phase6/55d` 的先例）

1. **保留** `<v9>/runs/stage-a/` 的两个工件**原样**，不删除、不移动、不覆盖、不改写；它们是**缺陷证据**；
2. 重试**必须写入新目录** `<v9>/runs/stage-a-retry/`，并**单独授权**后执行；
3. 重试的实跑命令须带 `--allow-stage=A --family-set=iqv --emit-observations`（与 v8 逐字一致）；
4. 阶段 `B` 的门禁前置此后**必须引用重试回执**（`runs/stage-a-retry/mixed-validation-stage-A.json`），**不得**引用本轮失败回执；
5. 本轮的 `status = completed` **不等于**验证通过，更**不等于**本轮有效。

## 9. 读数纪律与未做事项

- **本轮未从该报告计算任何质量指标**：未计算覆盖率、类型熵、金额熵、锚点份额、三对 JS 距离、域一 / 域二差值、跨人数净值等任何判据读数；**不得**用本轮产物去算它们（本轮不是有效阶段 `A`）；
- **未做**：阶段 `B`；确定性补算；重试；任何补算重跑；任何代码改动；任何判据 / 门槛 / 族集 / 分母 / 估值块改动；默认策略切换；推送；
- **仍未证**：第七版在第五套样本集上的任何表现；阶段 `B` 与补算的成本（`docs/phase6/58` §13 的估时仍是估算）；峰值 RSS 的外推依据。

## 10. 契约、API 与默认策略

- **未改**任何代码；API 字段、数据库列、内部契约、报告与观测 schema、artifact schema **零改动**；`MixedFixtureManifest` **未加字段**；
- **未新增**策略身份或清单；`-v9` 清单的 `sha256` 未变（`499258c9…`）；
- 默认策略仍为 **`heuristic@1`**；`docs/37` §3.1 **未触发**。

## 11. 不得声称

- 不得把本轮说成「阶段 `A` 通过」「验证通过」或「已达生产门槛」；本轮**不是**有效阶段 `A`。
- 不得把本轮的 `status = completed` 或 `violations = []` 当作质量证据。
- 不得用本轮产物计算或引用任何判据读数；不得把它与 v6 / v7 / v8 的读数并列比较。
- 不得把 `runs/stage-a/` 的工件删除、覆盖或改写成「重试结果」。
- 不得把本文件说成对 `docs/53c` / `55g` / `56h` / `57k` 任一签收结论的反转、修正或追认；也不得据此修改任何已归档文档与已落盘工件。
- 不得据本轮读数式结果调整族集、门槛、配方或任何取值。

## 12. 本篇唯一下一步

**建议**：授权**阶段 `A` 重试**（单轮、单独授权），命令与 v8 逐字一致：

```text
uv run python -m tests.mixed_bot_validation <v9>/input/frozen-fixture-manifest.json \
    A <v9>/runs/stage-a-retry --allow-stage=A --family-set=iqv --emit-observations
```

预期机械数值（外推 v8 同规模读数，**估算不是读数**）：对抗对照 `128` 手、wall `5 s` 量级、峰值 RSS `73 MiB` 量级。重试完成后出独立回执，之后才谈阶段 `B`。
