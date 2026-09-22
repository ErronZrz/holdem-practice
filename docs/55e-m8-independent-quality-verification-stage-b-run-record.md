# 55e M8：独立质量验证的阶段 B 运行回执

> 日期：2026-09-22。
>
> 本文件接在 `docs/55d` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。`docs/20` 至 `docs/55d` 未被改写。
>
> 本文件记录：**阶段 B 在 v6 上的首次实跑与其真实读数**（§5），并把它与 `docs/55d` §8 的**估算**并列对照（§6）。
>
> **本篇全部 wall/RSS/延迟数字都是实测读数**；与之并列的 265–332 s 是**估算**，不得当作耗时读数或成本验收。
>
> **本篇不给出任何质量结论**：L1–L5 判据的判定**不在本篇进行**（见 §9、§11）。

## 1. 授权原文与边界

本轮用户答复原文为：

> 「A.」

指向的是上一轮摆在用户面前的选项 A 原文：

> 「A. 授权执行阶段 B（补算另行一轮）」——「包络沿用既有口径、保持 `docs/55d` §12 的『运行与补算各自单独一轮』分轮纪律；补算可在其后一轮迅速执行」

| 项 | 内容 |
|---|---|
| 被授权 | 在 v6 下执行**阶段 B**一次，回执写入 `<v6>/runs/stage-b/`；在运行中实测并监控包络；随后按惯例提交回执文档 |
| 明确排除 | **确定性补算**（另立一轮）；L1–L5 判据判定与质量签收；重新冻结清单；改参数、策略口径或对手族集默认值；默认策略切换；M2-3；触碰 v1–v5 |
| 保留 | v6 的**失败阶段 A 回执**（`86e84fed…`）与**重跑阶段 A 回执**（`332607ca…`）**原样保留**，不删除、不改写；失败回执不得被表述为「未发生过」 |

## 2. 只读基线核验（本轮开始前）

```text
$ git status --short --branch
## master...origin/master

$ git status --porcelain=v1 -uall | wc -l
0

$ git rev-parse HEAD
2a64f7d4a5e565dd5943de706f3570be1b7d74f9

$ git rev-parse origin/master
2a64f7d4a5e565dd5943de706f3570be1b7d74f9

$ git --no-pager log -6 --oneline
2a64f7d docs: record the fixture defect fix, the stage-a rerun and the cost estimate
a9a6d3f fix: rebuild depth-scaled fixtures from their own recipe set and derive recheck schedules from receipts
a007861 docs: record the frozen fixture manifest for independent quality verification
2aee211 docs: record the test-side changes for independent quality verification
25d721f feat: add a second fixture set, probe families and seed overrides for independent verification
ecdb2a9 docs: approve the unpredictability criteria and bind them to this sign-off

$ find /Users/bryanylliu/holdem-mixed-bot-validation-v6 -type f
…/v6/input/frozen-fixture-manifest.json
…/v6/runs/stage-a/mixed-validation-stage-A.json
…/v6/runs/stage-a-retry/mixed-validation-stage-A.json
```

外部证据逐条复核（起始状态，`3` 个文件）：

| 对象 | sha256（前 8 位） | 核对 |
|---|---|---|
| v6 清单 | `0cb1dad4` | 与 `docs/55c`/`55d` 一致 |
| v6 失败阶段 A 回执 | `86e84fed` | 原样存在，未被触碰 |
| v6 重跑阶段 A 回执 | `332607ca` | 原样存在，未被触碰 |

六套外部证据的清单、阶段 A、阶段 B、补算全部 sha256 与接手基线逐条相符；v1–v5 未被读写。仓库计数（`strategy/*.py` 18、`tests/test_*.py` 37、`tests/*.py` 43、trainer 27/25、`docs/` 102）亦与基线一致。

## 3. 执行命令与门禁前置

实际执行的命令（工作目录 `backend/`）：

```bash
HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 \
uv run python -m tests.mixed_bot_validation \
  /Users/bryanylliu/holdem-mixed-bot-validation-v6/input/frozen-fixture-manifest.json \
  B /Users/bryanylliu/holdem-mixed-bot-validation-v6/runs/stage-b \
  --allow-stage=B \
  --stage-a-receipt=/Users/bryanylliu/holdem-mixed-bot-validation-v6/runs/stage-a-retry/mixed-validation-stage-A.json \
  --family-set=iqv
```

门禁前置如实核对：

| 项 | 值 |
|---|---|
| 引用的阶段 A 回执 | **重跑**回执（`runs/stage-a-retry/`），**不是**失败回执 |
| 该回执的 `stage` / `status` | `A` / `completed`（门禁要求二者同时成立） |
| 对手族集 | `iqv`（第二套 8 族：四旧 + 四新；未注册名称会显式失败，不退回默认集合） |
| 输出目录 | 运行前**不存在**；入口要求目标目录为空，不覆盖已有文件 |
| 主种子块 | 8 个（清单内 `seeds` 字段，逐字为 `docs/55c` 预承诺值） |

## 4. 运行方式与运行中实测监控

前台执行有被工具超时截断的风险，故改为**后台执行 + 轮询**：不中断进程、不丢样本；临时日志写在 `/tmp`（**不写入工作树、不写入证据目录**），运行结束后清理。

| 时点 | 进程 | 当前 RSS（`ps -o rss`） |
|---|---|---|
| `17:05:29`（启动） | `uv` PID 46640 / Python PID 46649 | — |
| `17:06:53`（+84 s） | 存活 | `30,352 KB` ≈ **29.6 MiB** |
| `17:08:56`（+207 s） | 存活 | `31,296 KB` ≈ **30.6 MiB** |
| `17:11:03` | **已退出** | 回执已落盘 |

监控期间**未触及**任何包络上限（wall ≤1800 s、RSS ≤1 GiB、输出 ≤100 MiB）；回执自报 `single_process=true`、`parallel=false`。

## 5. 阶段 B 实测读数（真实读数）

| 项 | 实测 |
|---|---|
| 路径 | `<v6>/runs/stage-b/mixed-validation-stage-B.json` |
| 文件 sha256 | `7ad4318bd98fa0a7cd0a2071e3fb686a3edc062eddf7360e1fdae824a8af9e82` |
| 文件大小 | `5,177,100 B`（≈4.94 MiB） |
| `schema_version` | `mixed-validation.v1` |
| `stage` | `B` |
| `status` | **`completed`** |
| `violations` | `[]`（空） |
| 被测身份 | `mixed-local@5` |
| `config_digest` | `8896013bbcd873cd493c6319756c353365b49cc7b4e846e927c4216d6d1f82f2` |
| `manifest_digest` | `381d205ee8e1d00622aabd5ff16d0ff9d2d1647614ddc48086233c83f2d73ccf` |
| `environment` | Python `3.13.8`、`macOS-26.6.2-arm64`、`cpu_count=10`、`local-machine-single-host-observation` |

**覆盖（`coverage` 原样）**

| 项 | 计划 | 执行 |
|---|---|---|
| 成本矩阵格 | `288` | `288` |
| 成本样本 | `80,000` | `80,000` |
| 补充场景样本 | `240` | `240` |
| 对抗对照手数 | `16,896` | `16,896` |
| 节点 | `128`（含 3 个结构性不适用） | `executed_nodes=125`、`not_run_nodes=0` |

**资源（`resources` 原样）**

| 项 | 实测 |
|---|---|
| wall | **`283.146 s`**（4.72 分钟） |
| CPU | `279.504 s` |
| 峰值 RSS | `76,742,656 B` = **73.19 MiB** |
| 输出字节 | `5,177,100 B` |
| 单进程 / 并行 | `true` / `false` |

**决策延迟（`timing` 原样，阈值 100 ms）**

| 路径 | 样本 | p50 | p95 | p99 | max | 超 100 ms |
|---|---|---|---|---|---|---|
| `decision_path`（整次决策，不含 apply） | `80,000` | `0.276` | `0.371` | `0.540` | **`37.212`** | **`0`** |
| `bot_step`（含 apply 的完整单步） | `80,000` | `0.288` | `0.388` | `0.560` | `37.267` | `0` |
| `engine_apply` | `80,000` | `0.005` | `0.008` | `0.246` | `1.664` | `0` |
| `public_summary_update` | `80,000` | `0.002` | `0.003` | `0.005` | `0.372` | `0` |
| `supplementary_decision_path` | `240` | `0.144` | `0.334` | `0.424` | `0.608` | `0` |

单位均为 ms；分组读数（按人数 / 街 / 风格 / 深度）一并落在回执内。`50 ms` 与 `80 ms` 只是指导值，不是新门槛。

**对抗对照与截断**

| 项 | 实测 |
|---|---|
| `planned_hands` / `completed_hands` | `16,896` / `16,896` |
| `truncated_hands` | **`0`**（逐手行中的 `truncated_hands` 求和亦为 `0`） |
| 种子块 | `8` 个 |
| 对手族 | `8` 个（`random@1`、`heuristic@1`、`passive-call-probe`、`fixed-pressure-probe`、`size-signal-probe`、`position-pressure-probe`、`marginal-call-pressure-probe`、`aggression-rate-probe`） |
| 区间口径 | `interval_status=not-estimated-small-fixed-seed-set`（8 个固定种子块**不给**总体覆盖承诺） |

**行为聚合（回执字段原样转录，本篇不作判据判定）**

| 风格 | 分布数 | 动作熵（bit） | 额度熵（bit） | 有效档位数 | 结构性单档 | 无活跃候选 |
|---|---|---|---|---|---|---|
| `tight` | `375` | `0.3716` | `1.2391` | `189` | `6` | `308` |
| `aggressive` | `375` | `0.4345` | `1.4336` | `230` | `6` | `295` |
| `calling` | `375` | `0.3485` | `1.1974` | `217` | `6` | `299` |

| 风格对 | 节点数 | 平均 JS | 最大 JS |
|---|---|---|---|
| `tight` vs `aggressive` | `125` | `0.1871` | `0.4526` |
| `tight` vs `calling` | `125` | `0.3004` | `0.6377` |
| `aggressive` vs `calling` | `125` | `0.1627` | `0.4497` |

**转录边界（必须一并记账）**：上两表只是把回执中已有的字段搬过来。`docs/55` §7.2 的判据中，**实质动作混合覆盖率**、**额度多样性两档锚点占比**、**风格可分度的「预先指定两个机会域」百分点**、**风格稳定性方向**这几项**不在回执字段中**，需按 §7.2 与 `docs/55a` §7.5 的口径另行计算；**该计算与判定不在本篇进行**，也不得据本节数字宣称任何判据已满足或未满足。

## 6. 估算 vs 读数（`docs/55d` §8 的估算至此可对照）

| 项 | `docs/55d` §8 的**估算** | 本篇**读数** | 对照 |
|---|---|---|---|
| 阶段 B wall | 约 `265–332 s` | **`283.146 s`** | 落在估算带内（偏带内中部） |
| 阶段 B 峰值 RSS | **无可靠外推依据**，只能实测监控 | **`73.19 MiB`** | v5 阶段 B 为 `72.2 MiB`：**+1.4%**，而未归因的对抗手数是 v5 的 4 倍 |
| 阶段 B 输出大小 | 「4–5 MB 量级」的粗估 | **`5,177,100 B`**（≈4.94 MiB） | 粗估量级得到印证 |
| 包络 | wall ≤1800 s / RSS ≤1 GiB / 输出 ≤100 MiB | 全部**未触及** | 无需扩容，未自行扩容 |
| `>=100 ms` 决策 | 「不因阶段 A 的 0 次推定必然满足」 | 80,000 样本下 **`0` 次** | **本轮实测**，非推定 |

**记账纪律（不得混淆）**：

1. 估算带「碰上了」不等于估算方法可靠——`docs/54h` 已有「估算偏差 41%」的先例；本篇的 `283.146 s` 是读数，`265–332 s` 永远是估算。
2. RSS 的 **+1.4%** 只是本次观测；v5 相对 v4 的 `+19%` **归因问题至今未解决**，本篇不声称已归因。
3. 本轮实测只覆盖**一台本机、单进程、不并行**；不构成跨机器或云端外推。

## 7. 身份差异（如实标注，不掩饰）

| 项 | 值 |
|---|---|
| 回执中的 `code_identity`（**清单冻结时的预承诺值**） | `2aee211cee8c506939e51f1f630430eebc419e9f` |
| **本次阶段 B 实际执行的代码** | `a9a6d3f1fc60f910a731fff8dcbd69df4992e898`（fix 提交；工作树 HEAD 为 `2a64f7d4…`，其内容与 `a9a6d3f1…` 的代码相同，差异仅为文档） |
| 清单内容是否改动 | **零改动**：清单文件 sha256 仍为 `0cb1dad4371a93543ab0257dcb4ca5a4c894cf48c2fa961e4a5dc50a6a77811c`，`manifest_digest` 仍为 `381d205e…3ccf` |

**结论口径**：回执里的 `code_identity` **不等于**执行代码的提交。**不得**把本回执表述为「由 `2aee211` 代码产生」；也不得把三处代码提交（`25d721f` / `a9a6d3f` / 本次为文档提交）混为一谈。

## 8. 契约、API 与默认策略

| 对象 | 状态 |
|---|---|
| 公开 API 字段 / 数据库列 / `history_json` | **零改动** |
| `experiment` / `measurement` / 候选 A artifact schema | **零改动** |
| 清单文件（v6） | **零改动**（sha256 与摘要不变） |
| 新策略身份 / 新清单 | **均未新增**；被测身份仍为 `mixed-local@5` |
| 对手族集 | 仅作为**运行参数**（`--family-set=iqv`）；清单模型未加字段，故族集不能进清单 |
| `docs/37` §3.1 | **不触发**（未触碰参考实现、保守判据、`equity` 实现、采样数或固定种子） |
| 默认策略 | **仍为 `heuristic@1`**（未获质量签收必须保持） |
| v1–v5 外部证据 | **零触碰** |

## 9. 未做事项与仍未证

- **未做**：确定性补算实跑；L1–L5 判据判定；质量签收；默认切换；抗针对的 best response；M2-3；重新冻结清单；任何参数或口径改动。
- **仍未证**：任何质量结论——`docs/53c` 的「质量结论未获支持」**未被本轮改变**；可剥削性/抗针对检验**仍未做过**（阶段 B 的 8 族 × 3 风格是**机械探针 + 对手族对照**，**不是** best response）；跨机器与云端成本；总体（非 8 固定种子块）覆盖。
- **口径提示**：`coverage.executed_nodes` 为 `125`，是**清单库存**口径，不是本轮执行的节点数。
- **未消耗**：本轮**未消耗**任何 authorization，也不涉及「永久已消耗的 A9 授权」清单（该清单的授权**一律不得重试**，与本轮无关）；本轮仅获**包络级**预算批准（≤1800 s / ≤1 GiB / ≤100 MiB），不构成更大规模运行的授权。
- 证据目录文件数由 `3` 增至 `4`：新增的只有 `runs/stage-b/mixed-validation-stage-B.json`；两份阶段 A 回执（含失败回执）未被改动。

## 10. 不得声称

- 不得把 `status=completed` 与 `violations=[]` 表述为质量证据、强度认证或验证通过。
- 不得把本篇的行为聚合表表述为 L3 判据已满足或未满足；该判定不在本篇。
- 不得把 8 个对手族 × 3 风格 × 8 种子块的机械对照表述为抗针对检验已完成或优势已被证明。
- 不得把 `283.146 s` / `73.19 MiB` 表述为预算保证、跨机器外推或成本验收（它们是**本机单次读数**）。
- 不得把 `docs/55d` §8 的估算数字当作读数；也不得因为估算带「碰上了」而声称估算方法可靠。
- 不得把本回执表述为「由 `2aee211` 代码产生」（§7）。
- 不得删除或改写 v6 的失败阶段 A 回执，也不得把它说成「未发生过」；两份阶段 A 回执**并存**，不得只引用其一。
- 不得把确定性补算当作新样本或新证据；不得据此修改 `docs/20` 至 `docs/55d` 与任何已落盘证据；不得改写 `@1`–`@5` 任一身份的历史含义。

## 11. 本篇唯一下一步

阶段 B 已在 v6 上完成并留下真实读数。

**关于 `docs/55` §11 的前置表**：该表的 P1–P6 状态栏是 **2026-09-22 起草时的快照**（例如 P2「未冻结」、P5「未评估」、P6「未执行」在起草后各自已有进展）。本篇**不逐项重述该表**，以免与 `docs/55c`/`docs/55d` 及本篇的事实重复或矛盾；需要的读者应以 `docs/55c`–`docs/55e` 的实际回执为准。

按 `docs/55d` §12 第 3 项与 §11 的判据闭环，**确定性补算仍未执行**，它是「按判据出具结论与签收」之前的最后一步。

**建议的唯一下一步（需用户裁定，本文件不自行执行）**：**单独授权并单独一轮执行确定性补算**——

```bash
cd /Users/bryanylliu/my4/holdem-practice/backend && \
HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 \
uv run python -m tests.mixed_bot_recheck \
  /Users/bryanylliu/holdem-mixed-bot-validation-v6/input/frozen-fixture-manifest.json \
  /Users/bryanylliu/holdem-mixed-bot-validation-v6/runs/stage-b/mixed-validation-stage-B.json \
  /Users/bryanylliu/holdem-mixed-bot-validation-v6/runs/stage-b-recheck \
  --allow-recheck
```

要点：补算**先核对行为指标、再逐手核对净筹码**，任何差异立即中止且**不写报告**；补算**不重算配置摘要**；补算**不是**新样本、**不是**新证据。补算完成后，才谈按 `docs/55` §7 的 L1–L5 判据出具结论与签收。
