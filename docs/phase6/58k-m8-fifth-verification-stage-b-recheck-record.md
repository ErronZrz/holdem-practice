# 58k M8：第五次独立验证阶段 `B` 的确定性补算回执（`J3` 第三轮）

> 日期：2026-09-24。
>
> 本文件接在 `docs/phase6/58j-m8-fifth-verification-stage-b-run-record.md` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。归档路径按 `docs/README.md` 的维护约定：本文件属第四次验证族的**共用族号 `58`**（先例 `58a`–`58j`），故取 **`58k`**。
>
> 本文件记录 `J3` 第三轮：**阶段 `B` 的确定性补算**（`tests.mixed_bot_recheck`）的运行命令、实测读数与**双口径包络核验**。
>
> **本篇不给任何质量结论，也不做任何判据计算**：补算**不产生新对局、不产生新样本、不追加强制种子**；行为分区只做**结构与自洽核对**，L1–L5 的判定**留待单独进行的判定轮次**。

## 1. 授权原文与边界

用户裁定（原话照录）：

> 「授权 J3 确定性补算。」

助手在授权前给出的边界与估时陈述（此处照录以免与用户原话混淆）：

> 「外推 进程级 `wall ≈ 600–900 s`、整调用峰值 RSS `≈ 0.9–1.0 GiB`、输出 `≈ 0.3 MiB`」；包络为 `wall ≤1800 s` / 峰值 RSS `≤1.5 GiB`（整调用口径）/ 输出 `≤100 MiB`；触及任一上界即停止并如实报告、不自行扩容。

| 项 | 内容 |
|---|---|
| 被授权 | 在 `-v10` 下**单轮**运行阶段 `B` 的确定性补算；**新建**工作树外目录 `-v10/runs/stage-b-recheck/` 并写入补算报告；随后出独立回执 |
| 门禁 | 补算门禁**引用阶段 `B` 回执**（`-v10/runs/stage-b/mixed-validation-stage-B.json`），**非**阶段 `A` |
| 明确排除 | 任何判据计算或质量结论；**阶段 `B` 的重跑**；任何代码改动；改判据 / 门槛 / 族集 / 机会分母 / 估值块 / 区间方法 / **包络数值**；删除或改写任何既有产物；默认策略切换；推送 |
| 包络 | `wall ≤1800 s`；**峰值 RSS `≤1.5 GiB`（整调用口径）**（`docs/phase6/58g`）；输出 `≤100 MiB`；单进程、不并行；触及任一上界即停止并如实报告，**不自行扩容** |
| 未消耗 | **未消耗**判据判定与签收的任何授权；`docs/phase4/37` §3.1 **未触发** |

## 2. 只读基线核验（补算前）

```text
$ git rev-parse HEAD
ee97bd87013ad739ebcab3084428777cf7efac9f

$ git status --porcelain=v1 -uall | wc -l
0

$ ls -d -v10/runs/stage-b-recheck
ls: /Users/bryanylliu/holdem-mixed-bot-validation-v10/runs/stage-b-recheck: No such file or directory
```

补算前 `-v10` 内文件为 **`5`** 个，逐字复核如下（均**未变**）：

| 核验对象 | `sha256` |
|---|---|
| `-v10/input/frozen-fixture-manifest.json` | `7cf406fe59bd64a7f381f52a6d01f489f4374dd0630dd83a5a857c09e49a9190` |
| `-v10/runs/stage-a/mixed-validation-stage-A.json` | `f44758ed8ea8679f3fbc40cb652a71a775ca7157d6759c0567662b145df2b8db` |
| `-v10/runs/stage-a/mixed-observations-stage-A.json` | `e4d81f29d20d4847fac75b360fce908a7c22a337c53d276a693ed7244f1931d7` |
| `-v10/runs/stage-b/mixed-validation-stage-B.json`（**门禁回执**） | `4bc2ea116661e75ddcdf311a5d51b85df8020c930ee90c38e3cd88d190977f1d` |
| `-v10/runs/stage-b/mixed-observations-stage-B.json` | `2fa45fa8b2591228b80c9b392abec2b7363fe591555eeb744596b000038ee19f` |

`-v10` = `/Users/bryanylliu/holdem-mixed-bot-validation-v10`。既有九套证据目录文件数 `5 / 4 / 4 / 4 / 4 / 5 / 7 / 7 / 8`（含 v6 失败阶段 A `86e84fed…`，**原样保留**）**未变**。

**入口核验（只读）**：`backend/tests/mixed_bot_recheck.py` 的 CLI 与门禁（`--allow-recheck` 缺省拒绝；要求 `status=completed`；阶段 ∈ `{A,B}`；回执 `strategy_id` 须等于清单 `strategy_id`；重算行为指标须与回执一致；目标文件存在即拒写且**不写报告**）与 `docs/phase6/58` §13 的补算约定相符，本轮**未改**该模块。

## 3. 运行命令与工件

```text
$ cd backend && nohup /usr/bin/time -l uv run python -m tests.mixed_bot_recheck \
    /Users/bryanylliu/holdem-mixed-bot-validation-v10/input/frozen-fixture-manifest.json \
    /Users/bryanylliu/holdem-mixed-bot-validation-v10/runs/stage-b/mixed-validation-stage-B.json \
    /Users/bryanylliu/holdem-mixed-bot-validation-v10/runs/stage-b-recheck --allow-recheck \
    > /tmp/v10-stage-b-recheck.stdout.log 2> /tmp/v10-stage-b-recheck.log &
```

单进程、不并行；`/usr/bin/time -l` 的进程级读数取自 `/tmp` 暂存日志（**不是**证据工件，仅用于交叉核对整调用口径）。运行以「后台启动 + 轮询」进行，全程一次调用、**首跑成功、无重试**。

| 工件 | `sha256` | 字节数 |
|---|---|---|
| `-v10/runs/stage-b-recheck/mixed-recheck-stage-B.json`（**本轮新增**） | `34ba8899c6063608b4301f16c31b334e82f74853594c6d4ed0fa6175bbf3e27c` | `324,486` |

- `-v10` 文件数由 `5` 变为 **`6`**；既有五份工件**零改写**（§2 的 sha 在补算后复核仍逐字一致）；
- 落盘工件与同一调用的 stdout 报告**逐字一致**（stdout = 工件内容 + 单个结尾换行，已校验：`324,487 = 324,486 + 1`）；stdout 与 `/tmp` 日志中**无** `traceback` / `MixedRecheckError` / 错误行，入口正常返回；
- 本轮在 `-v10` 内新增**一个**目录、**一个**文件；未触及既有九套证据目录。

## 4. 实测读数

### 4.1 身份与结论字段

| 项 | 读数 |
|---|---|
| `schema_version` / `source_stage` / `status` | `mixed-recheck.v1` / `B` / `completed` |
| `strategy_id` | `mixed-local@8` |
| `config_digest` | `393ca127fc16ef47d22cab29d287f43dde5aa94ee4a5cbb34ed15b4a12f627a2` |
| `manifest_digest` | `296af53055c8a2e2f8c5310e2d93cf252290fcfc4cfef5511574397d47a5782f` |
| `code_identity` | `d46c780a3c962bf17dcbe62443e0bde926caf372`（**清单冻结时的 HEAD**，见 §6） |
| `environment` | `macOS-26.6.2-arm64-arm-64bit-Mach-O / python 3.13.8` |

身份与 `docs/phase6/58h` / `58i` / `58j` 逐字一致：`config_digest` 与 `manifest_digest` 均未变。

### 4.2 一致性核对（回执自带字段）

| 项 | 读数 |
|---|---|
| `consistency.source_receipt` | `-v10/runs/stage-b/mixed-validation-stage-B.json` |
| `consistency.source_receipt_sha256` | `4bc2ea116661e75ddcdf311a5d51b85df8020c930ee90c38e3cd88d190977f1d`（**与阶段 `B` 报告逐字一致**） |
| `consistency.hands_compared` | `33,792`（与阶段 `B` 的计划 / 完成对抗手数一致） |
| `consistency.net_chips_exact` | `true`（逐手净筹码按排期顺序**完全一致**） |
| `consistency.behavior_exact` | `true`（行为指标**完全一致**） |

- **任何差异都会中止且不写报告**：两处 `true` 是「确定性重放通过」的**唯一证据形式**；本轮回执工件的产出本身也意味着未触发中止路径；
- **观测工件一致性核对**：本轮补算旁**存在**观测工件（`2fa45fa8…ee19f`，`45,527,112 B`），因此该项核对**参与并已通过**。该结论**不带报告字段标记**；**只有工件存在时该结论才成立**，后续引用必须连同「工件存在」一并陈述。

### 4.3 结构自洽（**不做判据计算**）

| 项 | 读数 |
|---|---|
| `aggregates` 行数 | `384` |
| `worst_opponents` 条目数 | `6` |
| `behavior.direct_distributions` | `1,125` |
| `behavior.style_js_distances` | `3` |
| `behavior.categories` | `48` |
| `limitations` 条目数 | `4`（按 `16` 块沿用已登记文本，原样落盘、未改写） |

- 上表只证明**分区齐全、条目数自洽**；三分域、两个机会域与机会分母**均未在本轮触碰**，所有取值**未解读**，**不得**作为判定输入。

### 4.4 资源与包络（**双口径并列**，包络为人工比对，代码不据此改 `status`）

| 口径 | wall | 峰值 RSS | 输出 |
|---|---|---|---|
| 模块自记 `resources`（**下界**） | `435.49 s` | `965,132,288 B`（`920.42 MiB`） | `324,486 B` |
| **整个调用的最大常驻集**（`/usr/bin/time -l`，**判定口径**） | `436.41 s` `real`（`user 429.00 s` / `sys 2.61 s`） | **`997,130,240 B`（`950.94 MiB`）** | 同上 |

| 包络项 | 上界 | 整调用实测 | 余量 | 结论 |
|---|---|---|---|---|
| wall | `≤1800 s` | `436.41 s` | 约 `75.8%` | **内** |
| 峰值 RSS | **`≤1.5 GiB`（`1,610,612,736 B`）** | `997,130,240 B`（`950.94 MiB`） | `585.06 MiB`（约 `38.1%`） | **内** |
| 输出 | `≤100 MiB`（`104,857,600 B`） | `324,486 B`（≈`316.9 KiB`） | 远未触及 | **内** |
| 并发 | 单进程、不并行 | `single_process=true`、`parallel=false` | — | 满足 |

- 另记：`peak memory footprint = 10,879,408 B`（`/usr/bin/time -l` 的另一计量，非 RSS）；
- **未触及任何上界**，故不存在「达界停跑」情形；
- 自记与整调用之比为约 `1.033×`，与 `docs/phase6/58a` §4.5 记录的同类比值（`1.028×`）同量级；**但**自记值**仍是下界**，**不得**单独据此宣称余量。

**估时对照（如实记账）**：授权前估时区间为 进程级 `600–900 s`，实测 `436.41 s`，**低于估时区间下沿**。这**不构成**对任何估时方法的校准，也**不构成**对后续轮次耗时的承诺。

## 5. 与既有同类补算的**机械量**对照（仅供成本参照，**不是质量比较**）

| 项 | 上一轮同类补算（`docs/phase6/58a`） | 更早一轮同类补算 | 本轮 |
|---|---|---|---|
| 自记 `wall` | `650.97 s` | `456.751 s` | `435.49 s` |
| 整调用 `wall` | `651.81 s` | 未记录 | `436.41 s` |
| 整调用峰值 RSS | `918.44 MiB` | — | `950.94 MiB` |
| 输出 | `324,436 B` | ≈`317 KiB` 量级 | `324,486 B` |
| 对比手数 | `33,792` | — | `33,792` |

**不得**把上表读作质量比较（不同节点集、不同种子集、不同策略身份）；也不得据此推断后续轮次的耗时或内存。

## 6. `code_identity` 差异披露

- 清单与补算报告中的 `code_identity` = `d46c780a3c962bf17dcbe62443e0bde926caf372`（**清单冻结时的 HEAD**）；
- 实际执行代码的 HEAD = `ee97bd87013ad739ebcab3084428777cf7efac9f`；
- ⇒ 二者**不同**。这是「先冻结、后回执」的固有结果，**不是**清单或本轮产物的缺陷。**不得**把本轮补算回执表述为「由执行代码的 HEAD 产生」，也**不得**说成由清单内的 `d46c780a…` 产生（实际执行代码是该 HEAD 之后的内容）；
- 本文件的提交还会再移动 HEAD，差异仍成立。

## 7. 读数纪律与未做事项

- **本轮未计算任何质量指标**：覆盖率、类型熵、金额熵、锚点份额、三对 JS 距离、域一 / 域二差值、跨人数净值等**均未计算**，也**未**从补算工件中推断；
- **未做**：任何判据判定或质量签收；阶段 `B` 的重跑；任何代码改动；任何判据 / 门槛 / 族集 / 分母 / 估值块 / 区间 / **包络**改动；删除或改写任何产物；默认策略切换；推送；
- **补算的边界**：**不产生新对局、不产生新样本、不追加强制种子**；`net_chips_exact` / `behavior_exact` 是**确定性重放**结果，**不得**当作新证据、新样本或质量证据；
- **仍未证**：第八版在第六套样本集上的任何质量表现（L1–L5 的判据读数**全部未做**）；第六套上的任何质量签收结论**均未产生**。

## 8. 契约、API 与默认策略

- **未改**任何代码；API 字段、数据库列、内部契约、报告与观测 schema、补算 schema、artifact schema **零改动**；`MixedFixtureManifest` **未加字段**；
- **未新增**策略身份或清单；`-v10` 清单 `sha256` 仍为 `7cf406fe…`；阶段 `A` / `B` 四份产物 `sha256` 亦未变；
- 默认策略仍为 **`heuristic@1`**；四份「质量未获支持」签收（`docs/phase5/53c`、`docs/phase6/55g`、`56h`、`57k`）**未被反转**；`docs/phase4/37` §3.1 **未触发**。

## 9. 不得声称

- 不得把本次补算的 `status = completed`、`net_chips_exact = true`、`behavior_exact = true` 说成**质量证据**、判据达标或「验证通过」；不得把「补算通过」说成阶段 `B` 已被独立复核。
- 不得把确定性补算当作**新样本**或**新证据**；不得从本回执或补算工件中顺带计算任何判据读数并作为判定输入。
- 不得把自记口径**单独**用于宣称包络内；两种 RSS 口径必须并列。
- 不得把 §5 的机械量对照说成质量比较；不得把第六套样本集与 v6 / v7 / v8 / v9 的**质量**读数并列比较。
- 不得把 §4.4 的估时对照说成对任何估时方法的校准或对后续耗时的承诺。
- 不得据此重跑本次补算，也不得重跑 `-v10` 已完成的阶段 `A` / 阶段 `B`；不得删除、覆盖或重写任何产物或历史回执。
- 不得把本记录说成对 `docs/phase5/53c` / `docs/phase6/55g` / `56h` / `57k` 任一签收结论的反转、修正或追认；不得说成对 `docs/phase6/58b`「质量未获支持」结论的改动。
- 不得据本轮结论调整族集、门槛、配方、包络或任何取值。

## 10. 本篇唯一下一步

`J3` 的三轮（阶段 `A`、阶段 `B`、确定性补算）**均已完成**，`-v10` 现为 `6` 个文件。据 `docs/phase6/58f` §11，下一步是**判据判定轮次**：在已冻结样本上按 `docs/phase6/58f` §4–§9 计算 L1–L5 读数（含机会分母、两个机会域、区间方法与固定估值种子块），并如实并列既有纪律（邻近阈值不算稳健、不得剔除结构恒等节点、不得按结果放宽、门槛一经批准即锁定）。

该动作**尚未授权**：判定轮次**尚未产生任何读数**，其结论将**直接决定本次质量签收**；判定必须**逐人数各自独立**、**禁止跨人数归因**，且**不得**新增或修改判据、**不得**删除失败样本。**建议**：单独授权判定轮次（`J4`），一次只做判定、不做任何签收，签收另起一轮。
