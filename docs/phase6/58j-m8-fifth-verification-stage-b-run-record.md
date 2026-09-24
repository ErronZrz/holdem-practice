# 58j M8：第五次独立验证阶段 `B` 运行记录

> 日期：2026-09-24。
>
> 本文件接在 `docs/phase6/58i-m8-fifth-verification-stage-a-run-record.md` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。归档路径按 `docs/README.md` 的维护约定：本文件属第四次验证族的**共用族号 `58`**（先例 `58a`–`58i`），故取 **`58j`**。
>
> 本文件记录 `J3` 的**阶段 `B`**（单轮、不含补算）：门禁引用阶段 `A` 回执，产物落盘 `-v10/runs/stage-b/`。
>
> **本文件不产生判据读数**：只记录机械字段（覆盖、手数、资源、门禁）。任何质量指标的计算属后续动作，须单独进行。

## 1. 授权原文与边界

用户裁定（原话照录）：

> 「授权 J3 阶段 B.」

助手在授权前给出的边界与估时陈述（此处照录以免与用户原话混淆）：

> 「`J3` **仅阶段 `B`**（不含补算）」；外推 进程级 `wall ≈ 500–600 s`、整调用峰值 RSS `≈ 1.1–1.3 GiB`、输出 `≈ 60–70 MiB`；包络为 `wall ≤1800 s` / 峰值 RSS `≤1.5 GiB`（整调用口径）/ 输出 `≤100 MiB`；触及任一上界即停止并如实报告、不自行扩容。

| 项 | 内容 |
|---|---|
| 被授权 | 在 `-v10` 下**单轮**运行阶段 `B`（带 `--family-set=iqv`，门禁引用阶段 `A` 回执），创建 `runs/stage-b/` 并落盘报告与观测工件，随后出独立回执 |
| 明确排除 | 确定性补算；删除或改写任何既有产物；改任何代码；改判据 / 门槛 / 族集 / 机会分母 / 估值块 / 区间方法 / **包络数值**；改任一判定钉子；默认策略切换；推送 |
| 包络处置 | 授权文本明确「触及包络则**停止并如实报告**」，**不自行扩容**（沿用模块 `budget_note` 的既有约定） |
| 未消耗 | **未消耗**补算的任何授权；`docs/phase4/37` §3.1 **未触发** |

## 2. 运行前只读基线核验

```text
$ git rev-parse HEAD
c518fee732ea6ac6176a6e962bce8a2e9ff2f0cd

$ git status --porcelain=v1 -uall | wc -l
0

$ shasum -a 256 -v10/input/frozen-fixture-manifest.json
7cf406fe59bd64a7f381f52a6d01f489f4374dd0630dd83a5a857c09e49a9190   （未变）

$ shasum -a 256 -v10/runs/stage-a/mixed-validation-stage-A.json
f44758ed8ea8679f3fbc40cb652a71a775ca7157d6759c0567662b145df2b8db   （门禁回执，未变）

$ ls -d -v10/runs/stage-b
ls: /Users/bryanylliu/holdem-mixed-bot-validation-v10/runs/stage-b: No such file or directory
```

`-v10` = `/Users/bryanylliu/holdem-mixed-bot-validation-v10`。运行前该目录为 `3` 个文件（清单 + 阶段 `A` 报告与观测）；门禁回执指向 `-v10/runs/stage-a/`。

## 3. 运行前估时（机械量外推，**不是**读数）

| 项 | 内容 |
|---|---|
| 锚点 | 第四次验证（`-v9`）阶段 `B` 的**机械量**：自记 `wall 501.69 s` / 进程级 `503.76 s`；整调用峰值 RSS `1212.63 MiB`；自记 `511.38 MiB`；手数 `33792`；输出 `63.50 MiB` |
| 外推 | 第六套清单同为 `125` 节点 / `16` 种子块、阶段 `B` 手数同为 `33792`，故预计 进程级 `wall ≈ 500–600 s`、整调用峰值 RSS `≈ 1.1–1.3 GiB`、输出 `≈ 60–70 MiB` |
| 薄弱处（须一并声明） | 锚点读数已达整调用上界（`1.5 GiB`）的约 `75%`，**余量约 `21%` 且不是承诺**；第六套牌面与动作线全新，截断与分支路径可能不同；该外推是**机械量类比**而非对第六套的实测；**不得**据外推承诺任何数值 |

## 4. 实跑命令（逐字记录）

```text
$ cd backend && nohup /usr/bin/time -l uv run python -m tests.mixed_bot_validation \
    /Users/bryanylliu/holdem-mixed-bot-validation-v10/input/frozen-fixture-manifest.json \
    B /Users/bryanylliu/holdem-mixed-bot-validation-v10/runs/stage-b \
    --allow-stage=B --family-set=iqv --emit-observations \
    --stage-a-receipt=/Users/bryanylliu/holdem-mixed-bot-validation-v10/runs/stage-a/mixed-validation-stage-A.json \
    > /dev/null 2> /tmp/v10-stage-b.log &
```

单进程、不并行；进程级读数取自 `/usr/bin/time -l` 的重定向日志（该日志是 `/tmp` 暂存，**不是**证据工件）。运行以「后台启动 + 轮询」进行，全程一次调用、无重试。

## 5. 进程级实测与落盘产物

| 项 | 值 |
|---|---|
| `real` / `user` / `sys` | `507.40 s` / `496.40 s` / `3.54 s` |
| `maximum resident set size`（**整调用**） | `1,259,339,776 B`（`1201.00 MiB`） |
| `peak memory footprint` | `10,797,488 B` |

| 路径 | 字节数 | `sha256` |
|---|---|---|
| `-v10/runs/stage-b/mixed-validation-stage-B.json` | `20,615,417` | `4bc2ea116661e75ddcdf311a5d51b85df8020c930ee90c38e3cd88d190977f1d` |
| `-v10/runs/stage-b/mixed-observations-stage-B.json` | `45,527,112` | `2fa45fa8b2591228b80c9b392abec2b7363fe591555eeb744596b000038ee19f` |

合计落盘 `66,142,529 B`（`63.08 MiB`）。运行后 `-v10` 内文件为 **`5`** 个（清单 + 阶段 `A` 两份 + 阶段 `B` 两份）；既有九套证据目录的文件数**未变**（`5 / 4 / 4 / 4 / 4 / 5 / 7 / 7 / 8`），其工件 `sha256` 亦未变。

## 6. 报告自记的机械字段

| 字段 | 值 |
|---|---|
| `schema_version` / `stage` / `status` | `mixed-validation.v2` / `B` / `completed` |
| `strategy_id` / `config_digest` | `mixed-local@8` / `393ca127fc16ef47d22cab29d287f43dde5aa94ee4a5cbb34ed15b4a12f627a2` |
| `manifest_digest` | `296af53055c8a2e2f8c5310e2d93cf252290fcfc4cfef5511574397d47a5782f`（与清单、与阶段 `A` 一致） |
| `code_identity` | `d46c780a3c962bf17dcbe62443e0bde926caf372`（**清单冻结时的 HEAD**，见 §8） |
| `violations` | `[]` |
| `coverage` | `planned_nodes 128` / `executed_nodes 125` / `not_run_nodes 0` / `structurally_not_applicable 3`；成本格 `288/288`、**成本样本 `80000/80000`**、**补充场景 `240/240`**、**对抗对照 `33792/33792`** |
| `matches` | `planned_hands 33792` / `completed_hands 33792` / `truncated_hands 0` / 逐行 `rows` `33792` 条 / `interval_status = not-estimated-small-fixed-seed-set` |
| `resources`（自记） | `wall_seconds = 505.3324`、`cpu_seconds = 498.2446`、**`peak_rss_bytes = 495,583,232`（`472.63 MiB`，下界）**、`output_bytes = 20,615,417`、`single_process = True`、`parallel = False` |
| `environment` | `python 3.13.8` / `macOS-26.6.2-arm64` / `cpu_count 10` |
| `timing`（完整决策路径） | `samples 80000`、`p50 0.2839 ms`、`p95 0.3889 ms`、`p99 0.6535 ms`、`max 21.7436 ms`、`timeout_count 0`（`DECISION_BUDGET_MS = 100`） |
| `timing`（`bot_step`） | `samples 80000`、`p95 0.4027 ms`、`p99 0.6758 ms`、`max 21.8011 ms`、`timeout_count 0` |
| `timing`（`engine_apply`） | `samples 80000`、`p95 0.0084 ms`、`max 0.7253 ms`、`timeout_count 0` |
| `behavior`（结构计数） | 直接分布 `1125`、逐节点行 `18000`、类别 `48`、风格间 JS 距离 `3` |
| 观测工件 | 手数 `33792`、`output_bytes = 45,527,112` |
| `limitations` | `5` 条（与既定报告口径一致） |

**两条必须并列的标注**：

1. `coverage.executed_nodes = 125` 是**清单库存口径**（第六套清单的全部可执行节点），**不是**本轮实际执行的节点数；本轮实际执行的手数由 `matches` 给出；
2. `max 21.7436 ms` 是**最大值**而非分位；`p95 / p99` 与 `50 / 80 ms` 指导值均在范围内，`timeout_count = 0`。这些是机械量，**不是**质量证据。

## 7. 包络核验（**双口径并列**）

| 口径 | wall | 峰值 RSS | 输出 | 与判定上界（整调用 `≤1.5 GiB`）的关系 |
|---|---|---|---|---|
| 整个调用的最大常驻集（`/usr/bin/time -l`，**判定口径**） | `507.40 s` | **`1201.00 MiB`** | `63.08 MiB` | **在包络内**，余量 `351,272,960 B`（约 `21.8%`） |
| 报告自记 `resources.peak_rss_bytes`（**只是下界**） | `505.33 s` | **`472.63 MiB`** | 同上 | 在包络内（余量约 `70.6%`），但**不得**单独据此宣称余量 |

wall（`507.40 s ≤ 1800 s`）、峰值 RSS（`1201.00 MiB ≤ 1.5 GiB`）、输出（`63.08 MiB ≤ 100 MiB`）三项**在两种口径下均落在包络内**；并发约定（`single_process = True`、`parallel = False`）**一致**。**未触及任何上界**，故不存在「达界停跑」情形。

自记与整调用之比为约 `2.54×`，与 `docs/phase6/70` §7 已记录的成因一致（自记取样时点早于「报告 + 观测」的大对象序列化）。**不得**把自记值说成真实峰值。

**机械量对照（仅供成本外推，不是质量比较）**：`-v9` 阶段 `B` 为 自记 `501.69 s` / 整调用 `1212.63 MiB` / `33792` 手；本轮为 自记 `505.33 s` / 整调用 `1201.00 MiB` / `33792` 手，同量级。**不得**把两者的任何**质量**读数作同样比较（不同节点集、不同种子集、不同策略身份）。

## 8. `code_identity` 差异披露

- 清单与报告中的 `code_identity` = `d46c780a3c962bf17dcbe62443e0bde926caf372`（**清单冻结时的 HEAD**）；
- 实际执行代码的 HEAD = `c518fee732ea6ac6176a6e962bce8a2e9ff2f0cd`；
- ⇒ 二者**不同**，须在每一次回执中如实标注；**不得**把清单或本轮产物说成由执行代码的 HEAD 产生；
- 本文件的提交还会再移动 HEAD，差异仍成立。

## 9. 读数纪律与未做事项

- **本轮未计算任何质量指标**：覆盖率、类型熵、金额熵、锚点份额、三对 JS 距离、域一 / 域二差值、跨人数净值等**均未计算**，也**未**从产物中推断；
- **未做**：确定性补算；任何补算准备动作；任何代码改动；任何判据 / 门槛 / 族集 / 分母 / 估值块 / 区间 / **包络**改动；删除或改写任何产物；默认策略切换；推送；
- **未触及任何包络上界**；
- **仍未证**：第八版在第六套样本集上的任何质量表现（L1–L5 的判据读数**全部未做**）；补算的 wall 与峰值 RSS（`docs/phase6/58` §13 的估时仍是估算；补算的整调用峰值 RSS **从未有过可用估算**，`-v9` 的补算仅有自记下界 `918.44 MiB`）。

## 10. 契约、API 与默认策略

- **未改**任何代码；API 字段、数据库列、内部契约、报告与观测 schema、artifact schema **零改动**；`MixedFixtureManifest` **未加字段**；
- **未新增**策略身份或清单；`-v10` 清单 `sha256` 仍为 `7cf406fe…`；阶段 `A` 两份产物 `sha256` 亦未变；
- 默认策略仍为 **`heuristic@1`**；四份「质量未获支持」签收（`docs/phase5/53c`、`docs/phase6/55g`、`56h`、`57k`）**未被反转**；`docs/phase4/37` §3.1 **未触发**。

## 11. 不得声称

- 不得把 `status = completed` 或 `violations = []` 说成「质量获支持」「验证通过」或「已达生产门槛」。
- 不得把本轮说成包络已放宽或已可外推；不得声称 `472.63 MiB` 是真实峰值。
- 不得用自记口径**单独**宣称包络内，也不得用整调用口径**单独**宣称包络被突破而不给出两者并列。
- 不得在确定性补算完成之前，据本轮产物**计算、推断或预告**任何质量指标。
- 不得把 §7 的机械量对照说成质量比较；不得把第六套样本集与 v6 / v7 / v8 / v9 的**质量**读数并列比较。
- 不得据此删除、覆盖或重写任何产物或历史回执；不得改写 v6 / v7 / v8 / v9 的任何记录。
- 不得把 §3 的估时说成读数或承诺；不得把 `docs/phase6/58h` 的清单冻结或 `58i` 的阶段 `A` 回执说成质量结论。
- 不得把本记录说成对 `docs/phase5/53c` / `docs/phase6/55g` / `56h` / `57k` 任一签收结论的反转、修正或追认。
- 不得据本轮结论调整族集、门槛、配方、包络或任何取值。

## 12. 本篇唯一下一步

阶段 `A` 与阶段 `B` 均已完成，`-v10` 现为 `5` 个文件。据 `docs/phase6/58c` §13 与 `docs/phase6/58` §13.1，下一步是 `J3` 的**第三轮：确定性补算**（**单独一轮、需单独授权**，不得与阶段 `A` / `B` 合并）。

补算的已知风险（须在授权时一并声明）：`-v9` 的同类补算为 自记 `893.05 MiB` / **整调用 `918.44 MiB`**，`wall` 自记 `650.969 s` / 整调用 `651.81 s`，输出 `324,436 B`（`docs/phase6/58a` §4；`docs/phase6/58g` §5 记为整调用 `918.44 MiB`）；本轮整调用口径的判定上界为 `1.5 GiB`。**但**补算的 wall 在既有两轮中均**未归因**（v8 同类为 `450–650 s` 估时区间的**上端**），峰值 RSS 亦**无可靠外推依据**；因此须在授权前给出估时并声明其薄弱处，运行中须以**双口径并列**报告，触及任一上界即停止并如实报告、不自行扩容。
