# 58i M8：第五次独立验证阶段 `A` 运行记录

> 日期：2026-09-24。
>
> 本文件接在 `docs/phase6/58h-m8-sixth-fixture-freeze-record.md` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。归档路径按 `docs/README.md` 的维护约定：本文件属第四次验证族的**共用族号 `58`**（先例 `58a`–`58h`），故取 **`58i`**。
>
> 本文件记录 `J3` 的**阶段 `A`**：按已冻结的第六套清单（`docs/phase6/58h`）在 `-v10` 下新建 `runs/` 并落盘阶段产物。
>
> **本文件不产生判据读数**：只记录机械字段（覆盖、手数、资源、门禁）。任何质量指标的计算属后续的判定动作，须单独进行。

## 1. 授权原文与边界

用户裁定（原话照录）：

> 「授权 J3 阶段 A.」

助手在授权前给出的边界陈述（此处照录以免与用户原话混淆）：

> 「`J3` **仅阶段 `A`**（阶段 `B` 与补算仍各自单独一轮，不得合并）」；包络为 `wall ≤1800 s` / 峰值 RSS `≤1.5 GiB`（整调用口径）/ 输出 `≤100 MiB`；触及任一上界即停止并如实报告、不自行扩容。

| 项 | 内容 |
|---|---|
| 被授权 | 在 `-v10` 下**单轮**运行阶段 `A`：创建 `runs/stage-a/` 并落盘报告与观测工件，随后出独立回执 |
| 明确排除 | 阶段 `B`；确定性补算；改任何代码；改判据 / 门槛 / 族集 / 机会分母 / 估值块 / 区间方法 / 包络常量；改任一判定钉子；默认策略切换；推送 |
| 转写纪律 | 命令逐字记录；产物不删不改；不手写任何报告字段 |
| 未消耗 | **未消耗**阶段 `B` 与补算的任何授权；`docs/phase4/37` §3.1 **未触发** |

## 2. 运行前只读基线核验

```text
$ git status --short --branch
## master...origin/master

$ git status --porcelain=v1 -uall | wc -l
0

$ git rev-parse HEAD
256f0dc62cdb55678b689d783df0bb6fff1bdcdd

$ git rev-parse origin/master
256f0dc62cdb55678b689d783df0bb6fff1bdcdd

$ shasum -a 256 -v10/input/frozen-fixture-manifest.json
7cf406fe59bd64a7f381f52a6d01f489f4374dd0630dd83a5a857c09e49a9190

$ ls -d -v10/runs
ls: /Users/bryanylliu/holdem-mixed-bot-validation-v10/runs: No such file or directory
```

`-v10` = `/Users/bryanylliu/holdem-mixed-bot-validation-v10`。运行前该目录**只有** `input/frozen-fixture-manifest.json` 一份文件；工作区零改动且与 `origin/master` 同步。

## 3. 运行前估时（机械量外推，**不是**读数）

| 项 | 内容 |
|---|---|
| 锚点 | 第四次验证（`-v9`）阶段 `A` 重试的**机械量**：自记 `wall 4.6460 s` / 进程级 `5.27 s`；自记 `peak_rss 74.15 MiB` / 进程级 `184.86 MiB`；`125` 执行节点、`128` 手 |
| 外推 | 第六套清单同为 `125` 节点 / `16` 类别 / `16` 种子块，故预计阶段 `A` 进程级 `wall ≈ 5–8 s`、峰值 RSS `≈ 0.2 GiB` 量级 |
| 薄弱处（须一并声明） | 第六套牌面与动作线全新，截断与分支路径可能不同；该外推是**机械量类比**而非对第六套的实测；`uv` 冷启动与页缓存影响进程级读数；**不得**据外推承诺任何数值 |

## 4. 实跑命令（逐字记录）

```text
$ cd backend && /usr/bin/time -l uv run python -m tests.mixed_bot_validation \
    /Users/bryanylliu/holdem-mixed-bot-validation-v10/input/frozen-fixture-manifest.json \
    A /Users/bryanylliu/holdem-mixed-bot-validation-v10/runs/stage-a \
    --allow-stage=A --family-set=iqv --emit-observations > /dev/null
exit=0
```

命令与 `docs/phase6/69` 记录的有效轮命令**同形**（含 `--family-set=iqv`），仅清单路径与输出目录换成第六套。

进程级实测（`/usr/bin/time -l`，含 `uv` 父进程；**整调用口径**）：

| 项 | 值 |
|---|---|
| `real` | `4.27 s` |
| `user` / `sys` | `3.88 s` / `0.09 s` |
| `maximum resident set size` | `192,495,616 B`（`183.57 MiB`） |
| `peak memory footprint` | `10,617,216 B` |

## 5. 落盘产物

| 路径 | 字节数 | `sha256` |
|---|---|---|
| `-v10/runs/stage-a/mixed-validation-stage-A.json` | `10,356,532` | `f44758ed8ea8679f3fbc40cb652a71a775ca7157d6759c0567662b145df2b8db` |
| `-v10/runs/stage-a/mixed-observations-stage-A.json` | `164,348` | `e4d81f29d20d4847fac75b360fce908a7c22a337c53d276a693ed7244f1931d7` |

合计 `10,520,880 B`（`10.03 MiB`）。运行后 `-v10` 内文件为 `3` 个（清单 + 报告 + 观测）；既有九套证据目录的文件数**未变**（`5 / 4 / 4 / 4 / 4 / 5 / 7 / 7 / 8`），其工件 `sha256` 亦未变。

## 6. 报告自记的机械字段

| 字段 | 值 |
|---|---|
| `schema_version` / `stage` / `status` | `mixed-validation.v2` / `A` / `completed` |
| `strategy_id` / `config_digest` | `mixed-local@8` / `393ca127fc16ef47d22cab29d287f43dde5aa94ee4a5cbb34ed15b4a12f627a2` |
| `manifest_digest` | `296af53055c8a2e2f8c5310e2d93cf252290fcfc4cfef5511574397d47a5782f`（与清单一致） |
| `code_identity` | `d46c780a3c962bf17dcbe62443e0bde926caf372`（**清单冻结时的 HEAD**，见 §8） |
| `violations` | `[]` |
| `coverage` | `planned_nodes 128` / `executed_nodes 125` / `not_run_nodes 0` / `structurally_not_applicable 3`；成本格 `288/288`、成本样本 `288/288`、补充场景 `24/24`；**对抗对照 `128/128`** |
| `matches` | `planned_hands 128` / `completed_hands 128` / `truncated_hands 0` / `interval_status = not-estimated-small-fixed-seed-set` |
| `resources` | `wall_seconds = 3.6551`、`cpu_seconds = 3.6363`、`peak_rss_bytes = 77,201,408`（`73.63 MiB`）、`output_bytes = 10,356,532`、`single_process = True`、`parallel = False` |
| `environment` | `python 3.13.8` / `macOS-26.6.2-arm64` / `cpu_count 10` |
| `timing`（完整决策路径） | `samples 288`、`p50 0.2861 ms`、`p95 0.3813 ms`、`p99 0.5974 ms`、`max 0.8785 ms`、`timeout_count 0` |
| `behavior`（结构计数） | 直接分布 `1125`、逐节点行 `18000`、类别 `48`、风格间 JS 距离 `3` |
| 观测工件 | 手数 `128`、`output_bytes = 164,348` |
| `limitations` | `5` 条（与既定报告口径一致） |

**两条必须并列的标注**：

1. `coverage.executed_nodes = 125` 是**清单库存口径**（第六套清单的全部可执行节点），**不是**本轮实际执行的节点数；本轮实际执行的手数由 `matches` 给出；
2. 报告字段中**不含**族集参量：`--family-set=iqv` 的生效由 `coverage.adversarial_hands_planned/executed = 128/128` 与既有排期机械手数（`8` 族 × `2` arm × `8` 人数）间接对应确认；默认族集为 `first-batch`（手数 `64`），本轮读数**不是**该默认值下的产物。

## 7. 包络核验与机械量对照

| 包络 | 上限 | 本轮实测 | 结论 |
|---|---|---|---|
| `wall`（阶段 `A` 累计） | 清单文本 `≤120 s`；本轮判定上界 `≤1800 s` | `3.66 s`（自记）/ `4.27 s`（进程级） | 内 |
| 峰值 RSS | `≤1.5 GiB`（整调用口径） | `183.57 MiB`（进程级整调用）/ `73.63 MiB`（自记，**只是下界**） | 内 |
| 输出 | `≤100 MiB` | `10.03 MiB` | 内 |
| 并发 | 单进程、不并行 | `single_process = True`、`parallel = False` | 一致 |

**机械量对照（仅供成本外推，不是质量比较）**：`-v9` 阶段 `A` 重试为 自记 `4.646 s` / `74.15 MiB` / `128` 手；本轮为 自记 `3.655 s` / `73.63 MiB` / `128` 手，同量级。**不得**把两者的任何**质量**读数作同样比较（不同节点集、不同种子集、不同策略身份）。

## 8. `code_identity` 差异披露

- 清单与报告中的 `code_identity` = `d46c780a3c962bf17dcbe62443e0bde926caf372`（**清单冻结时的 HEAD**）；
- 实际执行代码的 HEAD = `256f0dc62cdb55678b689d783df0bb6fff1bdcdd`；
- ⇒ 二者**不同**，须在每一次回执中如实标注；**不得**把清单或本轮产物说成由执行代码的 HEAD 产生；
- 本文件的提交还会再移动 HEAD，差异仍成立。

## 9. 读数纪律与未做事项

- **本轮未计算任何质量指标**：覆盖率、类型熵、金额熵、锚点份额、三对 JS 距离、域一 / 域二差值、跨人数净值等**均未计算**，也**未**从产物中推断；
- **未做**：阶段 `B`；确定性补算；阶段 `B` 的任何准备动作；任何代码改动；任何判据 / 门槛 / 族集 / 分母 / 估值块 / 区间改动；任何产物改写；默认策略切换；推送；
- **未触及任何包络上界**，故不存在「达界停跑」情形；
- **仍未证**：第八版在第六套样本集上的任何质量表现；阶段 `B` 与补算的成本与峰值 RSS（`docs/phase6/58` §13 的估时仍是估算，补算峰值 RSS **从未有过可用估算**）。

## 10. 契约、API 与默认策略

- **未改**任何代码；API 字段、数据库列、内部契约、报告与观测 schema、artifact schema **零改动**；`MixedFixtureManifest` **未加字段**；
- **未新增**策略身份或清单；`-v10` 清单 `sha256` 仍为 `7cf406fe…`；
- 默认策略仍为 **`heuristic@1`**；四份「质量未获支持」签收（`docs/phase5/53c`、`docs/phase6/55g`、`56h`、`57k`）**未被反转**；`docs/phase4/37` §3.1 **未触发**。

## 11. 不得声称

- 不得把本轮的 `status = completed` 或 `violations = []` 说成「质量获支持」「验证通过」或「已达生产门槛」。
- 不得把本轮说成判据已可判定；判据读数须在后续动作中单独计算并单独签收。
- 不得在阶段 `B` 与补算完成之前，据本轮产物**计算、推断或预告**任何质量指标。
- 不得把 §7 的机械量对照说成质量比较；不得把第六套样本集与 v6 / v7 / v8 / v9 的**质量**读数并列比较。
- 不得把模块自记 `peak_rss_bytes` 说成真实峰值；不得只报一种 RSS 口径；历史轮次未记录整调用口径，其是否超包络**只能标注为未知**。
- 不得把 §3 的估时说成读数或承诺；不得把 `docs/phase6/58h` 的清单冻结说成质量结论。
- 不得据此修改 `docs/` 下任何已归档文档与任何已落盘工件；不得重跑或改写 v6 / v7 / v8 / v9 的冻结集合与任何已落盘工件；不得改写 `@1`–`@8` 任一身份的历史含义。
- 不得把本记录说成对 `docs/phase5/53c` / `docs/phase6/55g` / `56h` / `57k` 任一签收结论的反转、修正或追认。

## 12. 本篇唯一下一步

阶段 `A` 已取得**有效**回执。据 `docs/phase6/58c` §13 与 `docs/phase6/58` §13.1，下一步是 **`J3` 的阶段 `B`**（**单独一轮、需单独授权**），且其门禁**必须引用本轮的 `-v10/runs/stage-a/` 回执**。

阶段 `B` 的已知风险（须在授权时一并声明）：`docs/phase6/58` §13.2 的估时为 `450–600 s`；**峰值 RSS 在 v7 / v8 两次均未归因**，**无可靠外推依据**；本轮判定上界为整调用 `≤1.5 GiB`，`-v9` 阶段 `B` 的整调用读数为 `1212.63 MiB`（旧上界下超出 `18.4%`，`docs/phase6/58g` §5），故阶段 `B` 的 RSS 余量**不可假定充足**。**建议**：先单独授权阶段 `B`（不含补算），补算在其回执之后再单独授权。
