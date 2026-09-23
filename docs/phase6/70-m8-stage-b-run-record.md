# 70 M8：阶段 `B` 运行记录与峰值 RSS 口径发现

> 日期：2026-09-23。
>
> 本文件接在 `docs/phase6/69-m8-stage-a-retry-record.md` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。归档路径按 `docs/README.md` 的维护约定：本文件属第四次验证族，归档于 `phase6/`。
>
> 本文件记录 `J3` 阶段 `B`（单轮、不含补算）的实跑结果，并记录本轮发现的**峰值 RSS 口径问题**：模块自记的 `peak_rss_bytes` 取样时点早于大对象序列化，**系统性低于整个调用的真实峰值**。
>
> **本文件不产生判据读数**：只记录机械字段。判据读数属后续动作，须单独进行。
>
> **本文件不构成包络放宽**：任何包络数值**未改**；如何处置本轮的 RSS 口径发现须由用户另行裁定。

## 1. 授权原文与边界

用户裁定（选项照录）：

> 「A. 授权阶段 B（单轮，不含补算）」

该选项随附理由由助手在选项中提出、随选项被选定，此处照录以免与用户原话混淆：

> 「`docs/58` §13.1 要求 A / B / 补算各自单独一轮；阶段 B 估时 `450–600 s`、v8 同类实测 RSS `465.64 MiB` / 输出约 `63 MiB`，包络内但体量比阶段 A 大一个量级。执行方式：后台运行 + 轮询（日志写 `/tmp` 暂存，不是证据工件），输出落 `-v9/runs/stage-b/`，完事出独立回执；触及包络则停止并如实报告。」

| 项 | 内容 |
|---|---|
| 被授权 | 在 `-v9` 下**单轮**运行阶段 `B`（带 `--family-set=iqv`，门禁引用重试回执），写入 `runs/stage-b/`，并出独立回执 |
| 明确排除 | 确定性补算；删除或改写任何既有产物；改任何代码；改判据 / 门槛 / 族集 / 机会分母 / 估值块 / **包络数值**；默认策略切换；推送 |
| 包络处置 | 授权文本明确「触及包络则**停止并如实报告**」，**不自行扩容**（沿用模块 `budget_note` 的既有约定） |
| 未消耗 | **未消耗**补算的任何授权；`docs/37` §3.1 **未触发** |

## 2. 运行前只读基线核验

```text
$ git rev-parse HEAD
77c51d1874828fbafc56f176218741c53bf36ffd

$ git status --porcelain=v1 -uall | wc -l
0

$ shasum -a 256 <v9>/runs/stage-a-retry/mixed-validation-stage-A.json
7e845cd00abaa2ca0a92e3057719cabe9b130dffab9fad4d7fcd7b616fe47d43   （门禁回执，未变）

$ shasum -a 256 <v9>/input/frozen-fixture-manifest.json
499258c993d1e59d5c2f2c218b79f2944059d216e05e3c20998675c20704a7c6   （未变）

$ ls -d <v9>/runs/stage-b
ls: <v9>/runs/stage-b: No such file or directory
```

`<v9>` = `/Users/bryanylliu/holdem-mixed-bot-validation-v9`。门禁回执指向**重试**目录，而非失败轮目录。

## 3. 实跑命令

```text
$ cd backend && nohup /usr/bin/time -l uv run python -m tests.mixed_bot_validation \
    /Users/bryanylliu/holdem-mixed-bot-validation-v9/input/frozen-fixture-manifest.json \
    B /Users/bryanylliu/holdem-mixed-bot-validation-v9/runs/stage-b \
    --allow-stage=B --family-set=iqv --emit-observations \
    --stage-a-receipt=/Users/bryanylliu/holdem-mixed-bot-validation-v9/runs/stage-a-retry/mixed-validation-stage-A.json \
    > /dev/null 2> /tmp/v9-stage-b.log &
```

单进程、不并行；进程级读数取自 `/usr/bin/time -l` 的重定向日志（该日志是 `/tmp` 暂存，**不是**证据工件）。

## 4. 进程级实测与落盘产物

| 项 | 值 |
|---|---|
| `real` / `user` / `sys` | `503.76 s` / `494.39 s` / `3.44 s` |
| `maximum resident set size`（整调用） | `1,271,578,624 B`（**`1212.63 MiB`**） |
| `peak memory footprint` | `10,633,648 B` |

| 路径 | 字节数 | `sha256` |
|---|---|---|
| `<v9>/runs/stage-b/mixed-validation-stage-B.json` | `20,686,354` | `963451e2c0e4d98abda8b007a7ee7db66c3c853dd1fb9b3ccbc6a44da827cf1f` |
| `<v9>/runs/stage-b/mixed-observations-stage-B.json` | `45,901,341` | `33920ec5a9088e023b5a17296fa75ce0801cb00822ae94e8bcb0c92a47dc9dd6` |

合计落盘 `66,587,695 B`（`63.50 MiB`）。运行后 `<v9>` 内文件为 **`7`** 个（与 v7 / v8 的结构一致）；既有八套证据目录的文件数**未变**（`5 / 4 / 4 / 4 / 4 / 5 / 7 / 7`）。

## 5. 报告自记的机械字段

| 字段 | 值 |
|---|---|
| `schema_version` / `stage` / `status` | `mixed-validation.v2` / `B` / `completed` |
| `strategy_id` / `config_digest` | `mixed-local@7` / `fd7433e35fc8260d03635774b34fbdc419ad5a04ba0448916b036e385a546665` |
| `manifest_digest` | `319cbb967d66dabdd795c19d60ab91962cd9397926ea71349583d855edc6a918` |
| `violations` | `[]` |
| `coverage` | `planned_nodes 128` / `executed_nodes 125` / `not_run_nodes 0` / `structurally_not_applicable 3`；成本格 `288/288`、**成本样本 `80000/80000`**、**补充场景 `240/240`**、**对抗对照 `33792/33792`** |
| `matches` | `planned_hands 33792` / `completed_hands 33792` / `truncated_hands 0` / `interval_status = not-estimated-small-fixed-seed-set` |
| `resources`（自记） | `wall_seconds = 501.6941`、`cpu_seconds = 496.0489`、**`peak_rss_bytes = 536,215,552`（`511.38 MiB`）**、`output_bytes = 20,686,354`、`single_process = True`、`parallel = False` |
| `timing` | 完整决策路径 `n = 80000`：`p95 0.4031 ms` / `p99 0.6795 ms` / `max 15.4823 ms`；`bot_step` `p95 0.4216` / `max 15.5009 ms`；`engine_apply` `p95 0.0095 ms`；`timeout_count 0`（`DECISION_BUDGET_MS = 100`） |
| `behavior`（结构计数） | 直接分布 `1125`、逐节点行 `18000`、类别 `48`、风格间 JS 距离 `3` |
| 观测工件 | 手数 `33792` |

`max 15.4823 ms` 是**最大值**而非分位；`p95 / p99` 与 `50 / 80 ms` 指导值均在范围内，`timeout_count = 0`。这是机械量，**不是**质量证据。

## 6. 包络核验（**双口径并列**）

| 口径 | wall | 峰值 RSS | 输出 | 与 `≤1 GiB` 的关系 |
|---|---|---|---|---|
| 报告自记 `resources`（**既有各轮回执所用的口径**） | `501.69 s` | **`511.38 MiB`** | `63.50 MiB` | **在包络内**（余量约 `50%`） |
| 整个调用的最大常驻集（`/usr/bin/time -l`） | `503.76 s` | **`1212.63 MiB`** | 同上 | **超出 `1 GiB`**（约 `+18.4%`） |

wall 与输出两项在两种口径下均落在 `≤1800 s` / `≤100 MiB` 之内；**只有 RSS 因口径不同而结论相反**。

**本轮按授权文本「触及包络则停止并如实报告」处置：阶段 `B` 之后停止，不进入补算，不自行扩容。**

## 7. 口径差异的归因（只读核对 + 受控探针）

### 7.1 受控探针：两口径在单进程下本应一致

在同一个 `uv run python` 调用里申请 `300 MiB` 并做自记读数：

```text
python 自记 ru_maxrss = 337,199,104 B  （321.6 MiB）
/usr/bin/time -l 报告    337,231,872 B  （321.6 MiB）
```

⇒ 两种测量在**单进程、无大对象序列化**的场合**一致**；因此本轮 `2.37×` 的差异**不是**通用口径差。

### 7.2 成因：自记读数取样于大对象序列化**之前**

`peak_rss_bytes()` 取自 `resource.getrusage(RUSAGE_SELF).ru_maxrss`，但它的**取样时点**早于本进程最占内存的两段工作：

| 模块 | 自记取样 | 之后才发生的大对象序列化 |
|---|---|---|
| `backend/tests/mixed_bot_validation.py` | 第 `2437` 行 | 第 `2454`–`2468` 行把整份报告（`18000` 行逐节点明细）`model_dump_json(indent=2)` **最多 `3` 轮**；第 `2469`–`2478` 行再构建并写出观测工件（`45,901,341 B`，来自 `33792` 手） |
| `backend/tests/mixed_bot_recheck.py` | 第 `471` 行 | 第 `480`–`489` 行同一模式 |

⇒ **模块自记的 `peak_rss_bytes` 是真实峰值的下界**，不是峰值本身；阶段 `B` 的差距（`511.38 MiB` → `1212.63 MiB`）与「报告 + 观测序列化」的规模量级相符。

### 7.3 该发现的历史影响（**必须一并记账**）

1. v6 / v7 / v8 各轮回执中引用的「峰值 RSS」**都是同一口径的自记值**，因此**可能系统性低于真实峰值**；
2. 特别地，v8 阶段 `B` 补算的自记值 `958.73 MiB`（余量仅 `6.37%`）——同一模块族的同一取样时点（已核对 `mixed_bot_recheck.py:471`）——**也应视为下界**；其真实峰值**可能已经超过 `1 GiB`；
3. 这**不改变**任何已落盘工件、不改变任何回执文字，也**不构成**对历史结论的追溯改写；它只说明**已披露的余量偏乐观**；
4. **不得**由本发现推导出「包络已放宽」或「后续可超预算」；**不得**改动任何包络数值；用户的「RSS 预算未来允许适当放宽」表态**尚未**落地为任何数值变更，本文件**未**据它做任何处置。

## 8. `code_identity` 差异披露

- 清单与报告中的 `code_identity` = `ae3f74930f022a69a4b64a7fcb85188c47384a74`（**冻结时的 HEAD**）；
- 实际执行代码的 HEAD = `77c51d1874828fbafc56f176218741c53bf36ffd`（本文件的提交还会再移动 HEAD）；
- ⇒ 二者**不同**，须在每一次回执中如实标注。

## 9. 读数纪律与未做事项

- **本轮未计算任何质量指标**：覆盖率、类型熵、金额熵、锚点份额、三对 JS 距离、域一 / 域二差值、跨人数净值等**均未计算**；
- **未做**：确定性补算；任何补算准备动作；任何代码改动；任何判据 / 门槛 / 族集 / 分母 / 估值块 / **包络**改动；删除或改写任何产物；默认策略切换；推送；
- **仍未证**：第七版在第五套样本集上的任何表现（L1–L5 的判据读数全部未做）；补算的 wall / RSS；**补算在两种口径下各会达到多少**。

## 10. 契约、API 与默认策略

- **未改**任何代码；API 字段、数据库列、内部契约、报告与观测 schema、artifact schema **零改动**；`MixedFixtureManifest` **未加字段**；
- **未新增**策略身份或清单；`-v9` 清单 `sha256` 未变；
- 默认策略仍为 **`heuristic@1`**；`docs/37` §3.1 **未触发**。

## 11. 不得声称

- 不得把 `status = completed` 或 `violations = []` 说成「质量获支持」「验证通过」或「已达生产门槛」。
- 不得把本轮说成包络已放宽或已可外推；不得声称 `511.38 MiB` 是真实峰值。
- 不得用自记口径**单独**宣称包络内，也不得用整调用口径**单独**宣称包络被突破而不给出两者并列。
- 不得据此删除、覆盖或重写任何产物或历史回执；不得改写 v6 / v7 / v8 的任何记录。
- 不得把 §6 的双口径并列说成质量比较；不得把第五套样本集与 v6 / v7 / v8 的读数并列比较。
- 不得把本文件说成对 `docs/53c` / `55g` / `56h` / `57k` 任一签收结论的反转、修正或追认。
- 不得据本轮结论调整族集、门槛、配方、包络或任何取值。

## 12. 本篇唯一下一步

阶段 `A`（重试）与阶段 `B` 均已完成，`-v9` 现为 `7` 个文件。**但补算不宜立即进行**，原因是 §6 / §7 发现的口径问题会直接决定补算的包络判据：

**建议先裁定「峰值 RSS 的口径」**（一次只定一件事），可选处置（**不预设结论**）：

- **甲**：包络以**整调用最大常驻集**为准 —— 则本轮阶段 `B` 已超 `1 GiB`，须先如实记账并由用户决定是否放宽或改为分段运行；
- **乙**：包络继续以**模块自记值**为准 —— 则须同时声明「该值是下界」，并在补算回执中**并列**整调用读数；
- **丙**：先补一份**只读的口径诊断**（不改代码），把 v6 / v7 / v8 的整调用峰值补测或据现有证据说明可达范围，再裁定。

无论选哪一项：**不得**改动任何包络数值或任何已落盘工件；补算（`J3` 第三轮）**仍需单独授权**。
