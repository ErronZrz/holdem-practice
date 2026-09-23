# 55f M8：独立质量验证的阶段 B 补算（确定性核对）回执

> 日期：2026-09-22。
>
> 本文件接在 `docs/55e` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。`docs/20` 至 `docs/55e` 未被改写。
>
> 本文件记录：对**阶段 B 回执**执行的一次**确定性补算**（`--allow-recheck`）与其真实读数，以及补算新增的指标字段。
>
> **补算不是新样本、不是新证据**：它不产生新对局、不产生新种子，只把已有回执缺失的指标按确定性口径重算，并逐手核对净筹码。
>
> **本篇不给出任何质量结论**：L1–L5 判据的判定**不在本篇进行**（见 §9、§12）。

## 1. 授权原文与边界

本轮用户答复原文为：

> 「好的，请继续。」

其所指向的是上一轮选项 A 原文中被授权但**按分轮纪律留到本轮**的那一项：

> 「A. 授权提交上述 `docs:` 一条，并授权下一轮单独执行确定性补算」——「补算按 `docs/55d` §12 分轮纪律独立成轮」

| 项 | 内容 |
|---|---|
| 被授权 | 单独一轮执行**确定性补算**，回执写入 `<v6>/runs/stage-b-recheck/`；随后按惯例提交回执文档 |
| 明确排除 | 按 L1–L5 判据出具**结论与质量签收**；重跑阶段 B 或阶段 A；重新冻结清单；改参数、策略口径或对手族集默认值；默认策略切换；M2-3；触碰 v1–v5 |
| 保留 | v6 的**失败阶段 A 回执**（`86e84fed…`）、**重跑阶段 A 回执**（`332607ca…`）、**阶段 B 回执**（`7ad4318b…`）**原样保留**，不删除、不改写 |

## 2. 只读基线核验（本轮开始前）

```text
$ git status --short --branch
## master...origin/master [ahead 1]

$ git rev-parse HEAD
63fdba97f6e22f95605eb5a9f9a6f5fb1c6894ae

$ ls -ld /Users/bryanylliu/holdem-mixed-bot-validation-v6/runs/stage-b-recheck
ls: …: No such file or directory        # 补算输出目录在运行前不存在

$ find /Users/bryanylliu/holdem-mixed-bot-validation-v6 -type f | wc -l
4
```

| 对象 | sha256（前 8 位） | 核对 |
|---|---|---|
| v6 清单 | `0cb1dad4` | 未变 |
| v6 失败阶段 A 回执 | `86e84fed` | 原样存在，未被触碰 |
| v6 重跑阶段 A 回执 | `332607ca` | 原样存在，未被触碰 |
| v6 阶段 B 回执 | `7ad4318b` | 未变（补算的**输入**） |

## 3. 执行命令与前置

```bash
cd /Users/bryanylliu/my4/holdem-practice/backend && \
HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 \
uv run python -m tests.mixed_bot_recheck \
  /Users/bryanylliu/holdem-mixed-bot-validation-v6/input/frozen-fixture-manifest.json \
  /Users/bryanylliu/holdem-mixed-bot-validation-v6/runs/stage-b/mixed-validation-stage-B.json \
  /Users/bryanylliu/holdem-mixed-bot-validation-v6/runs/stage-b-recheck \
  --allow-recheck
```

| 项 | 值 |
|---|---|
| 显式开关 | `--allow-recheck`（缺省即拒绝执行） |
| 输入 | 清单 + **阶段 B 回执**（`source_stage` 记为其来源阶段） |
| 补算排期来源 | 由**回执内容**重建，不由模块常量假定 |
| 输出目录 | 运行前不存在；入口按「不得覆盖已有文件」处理 |
| 是否重算配置摘要 | **否**（补算不重算 `config_digest`） |
| 差异处理 | 任何差异**立即中止且不写报告** |

## 4. 运行方式与运行中实测监控

仍采用**后台执行 + 轮询**（不中断进程、不丢样本）；临时日志写在 `/tmp`，运行结束后清理。

| 时点 | 进程 | 当前 RSS（`ps -o rss`） |
|---|---|---|
| `17:39:10`（启动） | `uv` PID 1635 / Python PID 1703 | — |
| `17:41:06`（+116 s） | 存活 | `43,088 KB` ≈ **42.1 MiB** |
| `17:43:20` | **已退出** | 回执已落盘 |

`17:43:20` 时点进程已退出，回执文件存在；本次监控期间**未触及**任何包络上限。

## 5. 补算实测读数（真实读数）

| 项 | 实测 |
|---|---|
| 路径 | `<v6>/runs/stage-b-recheck/mixed-recheck-stage-B.json` |
| 文件 sha256 | `5597d221924a3775408dc25060899dcfb3fa519741ea9edd7468dc4ed159e2e2` |
| 文件大小 | `261,170 B` |
| `schema_version` | `mixed-recheck.v1` |
| `source_stage` | `B` |
| `status` | **`completed`** |
| 被测身份 | `mixed-local@5` |
| `config_digest` | `8896013bbcd873cd493c6319756c353365b49cc7b4e846e927c4216d6d1f82f2`（与阶段 B 一致，补算不重算摘要） |
| `manifest_digest` | `381d205ee8e1d00622aabd5ff16d0ff9d2d1647614ddc48086233c83f2d73ccf` |
| `environment` | `macOS-26.6.2-arm64-arm-64bit-Mach-O / python 3.13.8` |

**一致性块（`consistency` 原样）**

| 项 | 值 |
|---|---|
| `source_receipt` | `<v6>/runs/stage-b/mixed-validation-stage-B.json` |
| `source_receipt_sha256` | `7ad4318bd98fa0a7cd0a2071e3fb686a3edc062eddf7360e1fdae824a8af9e82`（与 §2 核对值一致） |
| `hands_compared` | **`16,896`** |
| `net_chips_exact` | **`true`** |
| `behavior_exact` | **`true`** |

**资源（`resources` 原样）**

| 项 | 实测 |
|---|---|
| wall | **`234.209 s`**（3.90 分钟） |
| CPU | `229.501 s` |
| 峰值 RSS | `94,289,920 B` = **89.92 MiB** |
| 输出字节 | `261,170 B` |
| 单进程 / 并行 | `true` / `false` |

**核对范围与截断**

| 项 | 实测 |
|---|---|
| 逐手比对手数 | `16,896`（与阶段 B 的 `completed_hands` 相同；按同一排期与同一主种子**确定性重放同一批对局**，**不产生新对局、不新增样本**） |
| 聚合单元行数 | `384`（= 人数 2–9 共 8 × 风格 3 × 对手族 8 × 焦点臂 2） |
| 聚合行 `hands` 合计 | `16,896` |
| 聚合行 `truncated_hands` 合计 | **`0`** |

## 6. 补算逐字一致的两类核对（机制层结论，非质量层）

| 核对 | 结果 | 含义（严格限定） |
|---|---|---|
| 行为指标（分布、熵、JS 距离等） | **完全一致**（`behavior_exact=true`） | 同一清单 + 同一身份下，行为指标的**重算可复现** |
| 逐手净筹码（按排期顺序） | **完全一致**（`net_chips_exact=true`） | 阶段 B 的逐手读数是**确定性**的，不是随机漂移的产物 |

**口径限定（不得越界）**：

1. 补算的 `completed` / `true` 是**机制与可复现性**结论，**不是**质量证据、**不是**强度认证、**不是**验证通过。
2. 补算的样本与阶段 B **是同一批对局**：它**不增加**有效样本量，**不得**当作独立验证、**不得**与阶段 B 的读数相加以扩大统计功效。
3. JS 距离在两次运行中逐字相同（`tight/aggressive` `0.1871`、`tight/calling` `0.3004`、`aggressive/calling` `0.1627` 均值），这**只**说明该指标是确定性的，**不**说明其**是否达到** `docs/55` §7.2 第 4b 项的门槛。

## 7. 补算新增的指标字段（回执原样转录，本篇不作判据判定）

补算在阶段 B 回执之外，按确定性口径补出了两类此前缺失的指标。

### 7.1 行为统计（每个聚合单元）

`vpip` / `pfr` / `aggression_rate` 已按 `384` 个「人数 × 风格 × 对手族 × 焦点臂」单元补齐（阶段 B 回执不含这三项）。**口径**：焦点座位的逐手机械统计，**不是**范围强度、盈亏平衡频率或均衡频率。

### 7.2 最差对手配对（`worst_opponents`，共 6 行，原样）

| 风格 | 焦点臂 | 对手族 | `bb_per_100` |
|---|---|---|---|
| `tight` | `mixed-focus` | `fixed-pressure-probe` | `-785.0` |
| `tight` | `legacy-focus` | `fixed-pressure-probe` | `-1263.39` |
| `aggressive` | `mixed-focus` | `fixed-pressure-probe` | `-1092.86` |
| `aggressive` | `legacy-focus` | `fixed-pressure-probe` | `-1263.39` |
| `calling` | `mixed-focus` | `fixed-pressure-probe` | `-1825.0` |
| `calling` | `legacy-focus` | `fixed-pressure-probe` | `-1263.39` |

**转录边界（必须一并记账）**：

1. 该表是**机械探针**（`fixed-pressure-probe`）的配对读数，**不是** best response，**不构成**可剥削性结论；**不得**据此声称「已被证明可被针对」。
2. 该表**不是** `docs/55` §7 的 **D4 统计量**。D4 要求的是**相对 `heuristic@1`** 的最差族配对收益差 **95% 区间下界 ≥ −5 BB/100**；本条列表既非相对 `heuristic@1`，也未给区间。
3. 本节**不判定**任何门槛是否满足。D4 及 L1–L5 的计算与判定**不在本篇进行**（§12）。

## 8. 资源与包络对照

| 项 | 包络 | 阶段 B 读数 | **本篇补齐算读数** | 是否触及 |
|---|---|---|---|---|
| wall | ≤1800 s | `283.146 s` | **`234.209 s`** | 否 |
| RSS | ≤1 GiB | `73.19 MiB` | **`89.92 MiB`** | 否 |
| 输出 | ≤100 MiB | `4.94 MiB` | `261,170 B` | 否 |
| 并行 | 单进程 | `single_process=true` | `single_process=true` | — |

**未归因项（如实记账）**：补算峰值 RSS `89.92 MiB` 比阶段 B 的 `73.19 MiB` **高 22.9%**，而补算的重放规模与阶段 B 相同。此前 v5→v4 的 `+19%` 亦未归因；两次现象均**未有解释**，本篇不声称已归因。

## 9. 身份差异（如实标注，不掩饰）

| 项 | 值 |
|---|---|
| 回执中的 `code_identity`（**清单冻结时的预承诺值**） | `2aee211cee8c506939e51f1f630430eebc419e9f` |
| **本次补算实际执行的代码** | `63fdba97f6e22f95605eb5a9f9a6f5fb1c6894ae`（工作树 HEAD；其中代码内容与 `a9a6d3f1fc60f910a731fff8dcbd69df4992e898` 相同，其后提交均为文档） |
| 清单内容是否改动 | **零改动**：清单 sha256 仍为 `0cb1dad4…`，`manifest_digest` 仍为 `381d205e…3ccf` |

**结论口径**：回执里的 `code_identity` **不等于**执行代码的提交。**不得**把本回执表述为「由 `2aee211` 代码产生」。

## 10. 契约、API 与默认策略

| 对象 | 状态 |
|---|---|
| 公开 API 字段 / 数据库列 / `history_json` | **零改动** |
| `experiment` / `measurement` / 候选 A artifact schema | **零改动** |
| 阶段 B 回执（补算输入） | **零改动**（sha256 仍 `7ad4318b…`） |
| 清单文件（v6） | **零改动** |
| 新策略身份 / 新清单 | **均未新增**；被测身份仍为 `mixed-local@5` |
| `docs/37` §3.1 | **不触发**（未触碰参考实现、保守判据、`equity` 实现、采样数或固定种子） |
| 默认策略 | **仍为 `heuristic@1`**（未获质量签收必须保持） |
| v1–v5 外部证据 | **零触碰** |

## 11. 未做事项与仍未证

- **未做**：L1–L5 判据判定；质量签收；默认切换；抗针对的 best response；对 D4 区间下界的计算；M2-3；重新冻结清单；任何参数或口径改动。
- **仍未证**：任何质量结论——`docs/53c` 的「质量结论未获支持」**未被本轮改变**；8 族 × 3 风格 × 2 臂的机械对照**不是**可剥削性检验；D4 区间下界；L3 六项门槛（`docs/55` §7.2 明确 `0.15` 阈值在新节点集上**不重标定**，未达标即如实报告为未达标）；跨机器与云端成本。
- **口径提示**：阶段 B 的 `coverage.executed_nodes=125` 是**清单库存**口径；补算的 `hands_compared=16896` 是**同一批对局**的重放，不是新增样本。
- **未消耗**：本轮**未消耗**任何 authorization；仅获**包络级**预算批准（≤1800 s / ≤1 GiB / ≤100 MiB）。
- 证据目录文件数由 `4` 增至 `5`：新增的只有 `runs/stage-b-recheck/mixed-recheck-stage-B.json`；其余四份（含失败阶段 A 回执）**sha256 全部未变**。

## 12. 不得声称

- 不得把补算的 `completed` / `net_chips_exact=true` / `behavior_exact=true` 表述为质量证据、验证通过或独立验证结果。
- 不得把补算当作新样本或新证据，也不得把它与阶段 B 的读数合并计算以扩大样本量。
- 不得把 §7.2 的 `worst_opponents` 表述为 D4 统计量、可剥削性结论或 best response 结果。
- 不得把本篇新增的 VPIP/PFR/aggression_rate 表述为范围强度或均衡频率。
- 不得把 §7.2 的数字表述为「L3/L4 判据已满足/未满足」——该判定不在本篇。
- 不得把本回执表述为「由 `2aee211` 代码产生」（§9）。
- 不得删除或改写 v6 的失败阶段 A 回执，也不得把它说成「未发生过」；四份阶段 A/B 回执**并存**，不得只引用其一。
- 不得据此修改 `docs/20` 至 `docs/55e` 与任何已落盘证据；不得改写 `@1`–`@5` 任一身份的历史含义。

## 13. 本篇唯一下一步

阶段 B 与确定性补算均已落地，且补算证明阶段 B 的逐手读数与行为指标**可确定性复现**。至此，`docs/55` §11 的运行前置与 `docs/55d` §12 的分轮排期已执行完毕，**剩下的只有判据闭环**。

**建议的唯一下一步（需用户裁定，本文件不自行执行）**：**授权按 `docs/55` §7 的 L1–L5 判据出具结论，并据此判定质量签收与否**。该步必须由用户裁定，因为它直接决定：

1. **是否给出质量签收**——`docs/53c` 的「质量结论未获支持」只有在本次按 D2 绑定的判据下被**明确反转**或**再次维持**时才可改变；
2. **是否切换默认策略**——判据很可能不满足（现状锚点：覆盖率 `6.85%`、类型熵 `0.032 bit`；`docs/53c` §4 第 1 条的方向亦不利于新 Bot），而 `docs/53` §13.2 禁止把开发期读数当独立验证；**未获签收必须保持 `heuristic@1`**；
3. **是否在结论中如实记录「范围受限的反转」**——D2 已预承诺该记账方式。

判定所需输入已全部就绪：`docs/55`（口径）+ `docs/55a`（机械明细与机会分母）+ `docs/55e`（阶段 B 读数）+ `docs/55f`（补算读数与新增指标）。
