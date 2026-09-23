# 50 M8：P2-4 完整形态——受监督记录接入 + 跨 seed 稳定性记录（规格冻结）

> 日期：2026-09-20。
>
> 本文件接在 `docs/49` / `docs/49a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/50` 记录本轮**规格与决策冻结**，`docs/50a` 记录与之对应的**实施回执**。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P2-4 完整形态**的规格冻结。代码与测试在随后一次提交中落地。
>
> **本文件不产生任何策略、质量或资源证据**；未接入 CFR/查表、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、**未启动任何受监督运行**、未做任何云端操作。

## 1. 授权范围与设计岔路裁定

### 1.1 用户答复原文（逐项照录）

本轮采用「**先问用户**」，共问三项。

| 岔路 | 用户答复原文 |
|---|---|
| 落地形态 | 「C：两者都做（推荐）」——① 受监督 experiment 记录新增 `stability` 段（v1→v2 **双版本读取**，旧封存记录仍可读；单条记录取值通常为 `not-requested`）；② 新增一个**只读**的跨 seed 稳定性记录类型，消费 ≥2 条已封存实验/策略载荷，承载 `measured` |
| artifact v1 是否扩展 | **本轮未作答**。按保守默认取**不扩展**（见裁定二），并在本文显式标注，便于随时更正 |
| 是否授权真实运行 | **本轮未作答**。按保守默认取**不授权**（见裁定三），即不启动任何受监督运行 |

**裁定二、三的两点说明（如与用户本意不符，请指出，本轮可只改文档不落地代码）**：
- 两项默认都取「**不扩大范围**」的方向：不扩展 artifact v1 = 不改任何既有工件与后端读取端；不启动受监督运行 = 不消耗预算、不生成 authorization；
- 因此本轮 `status = "measured"` 只在**单测内**以构造载荷验证，**不产生**任何真实记录。

### 1.2 裁定（冻结）

| 裁定 | 内容 |
|---|---|
| 一 | **落地形态 C**：受监督 experiment 记录新增 `stability` 段（**v1→v2 双版本读取**）；并新增独立、只读的跨 seed 稳定性记录类型承载 `measured`。 |
| 二 | **不扩展策略 artifact v1**：`policy.py` 的 `quality.stability` 仍**只允许** `{status}`；artifact `SCHEMA_VERSION` 保持 `1`；11 份已封存 `strategy.json` 与后端 `strategy/artifact.py` 读取端均不变。 |
| 三 | **不启动任何受监督运行**：不新建 campaign、不追加 seed、不重试 authorization、不消耗预算。 |
| 四 | **版本与兼容策略**：受监督 experiment 记录的 `schema_version` 由 `1` 升至 `2`；读取端**同时接受** v1（无 `stability` 键）与 v2（有 `stability` 键，4 字段必填）。**已封存 v1 子记录必须继续可读**（`holdem-campaigns` 下有 114 份 JSON，最终 measurement 为 supervised v2，其 `child_execution.payload` 即 experiment 记录）。 |
| 五 | **新记录类型**：`multiplayer-cfr-cross-seed-stability`（`schema_version = 1`），只承载「跨 seed 稳定性」这一**集合级**属性，并记录参与比较的**来源身份**（策略产物 sha256 / 字节数 / seed）。 |

### 1.3 与 `docs/37` §3.1 的关系（更正此前表述）

`docs/37` §3.1 冻结的**升版规则**，作用于**后端复盘参考/评估身份**（`backend/app/analysis/reference_identity.py` 的 `REFERENCE_VERSION` / `EVALUATION_VERSION`），其消费者是 `hand_review.py`。

本轮的改动**全部在 `tools/trainer/**`**：既不涉及 `reference_identity.py`，也**不触发** `docs/37` §3.1 的升版。此前把「扩展 artifact v1」与该 §3.1 升版相关联的表述**不准确**，以本文为准。

真正会被策略 artifact 变更牵动的是：**后端 `backend/app/strategy/artifact.py` 的读取端**与 11 份已封存 `strategy.json`——这也是裁定二选择「不扩展」的理由之一。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 4]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -2 --oneline
b32cd4b feat: add code-built cross-seed stability producer for measurement records
fae65bd docs: freeze p2-4 cross-seed stability producer specs

$ git rev-parse HEAD          -> b32cd4b9de42e2f7c679298ac9236b95d3575b0a
$ git rev-parse origin/master -> 133c99cbf541e9bf49d1f5f2e795ca6585e91d8d

$ cd tools/trainer && uv run ruff check .   -> All checks passed!
$ cd tools/trainer && uv run pytest -q      -> 207 passed
$ cd backend && uv run pytest -q            -> 668 passed, 2 skipped
```

只读核对的事实：

| 项 | 实测 |
|---|---|
| `experiment_record.py` 顶层键 | 11 个（无 `stability`）；`EXPERIMENT_RECORD_SCHEMA_VERSION = 1`，校验为**严格等值** |
| 已封存记录 | `holdem-campaigns` 下 114 份 JSON；最终 `measurement.json` 为 `multiplayer-cfr-supervised-measurement` v2，其 `child_execution.payload` 即 experiment 记录 |
| 后端消费 | **0 处**引用 trainer 任何 measurement / supervised 记录类型 |
| `policy.py` 读取 API | `load_strategy(path)` / `load_quantized_strategy(path)`；后者给出 `action_units`（`dict[key, dict[Action, int]]`）与字节身份；`training.master_seed` 为整数 |
| `safeio.load_canonical_json` | **已强制**规范编码（原始字节必须等于规范编码） |

## 3. 规格冻结（实施前的唯一依据）

### 3.1 受监督 experiment 记录的版本与读取规则（冻结）

| 版本 | 顶层键 | 读取端行为 |
|---|---|---|
| `1`（既有、已封存） | 11 键，**不含** `stability` | **继续接受**；不得因缺 `stability` 而失败 |
| `2`（本轮起由构造器产出） | 12 键，**必含** `stability` | 必须通过 §3.2 的同一套校验 |

- 构造器 `build_manifested_measurement_record(...)` 一律产出 **v2**，其 `stability` 取值为 `{"status": "not-requested", ... 其余三字段为 null}`。
- **单条 experiment 只有一个 seed，因此单条记录的 `stability` 在语义上不可能取 `measured`**；`measured` 只能来自 §3.3 的集合级记录。这一点必须在代码与文档中如实体现，不得让单条记录看起来像「已测得稳定性」。

### 3.2 `stability` 段的唯一 schema（冻结）

复用 `measurement.py` 既有 schema，**不另立第二套**：字段恰为 `{status, seed_set_sha256, audit_infosets_sha256, max_l1}`；`status ∈ {not-requested, not-measured, measured}`；非 `measured` 时其余三字段必须为 `null`；`measured` 时 `seed_set_sha256` / `audit_infosets_sha256` 为小写 SHA-256、`max_l1` 为非负既约有理数 `{numerator, denominator}`。

实施方式：在 `measurement.py` 暴露**唯一**的公开校验入口，供 `experiment_record.py` 与 §3.3 复用；不得在两个模块各写一份校验。

### 3.3 跨 seed 稳定性记录（新记录类型，冻结）

| 项 | 定义 |
|---|---|
| `record_type` | `multiplayer-cfr-cross-seed-stability` |
| `schema_version` | `1` |
| 顶层字段 | `schema_version`、`record_type`、`game`（`{id, version, player_count}`）、`stability`（§3.2 schema，**必须**为 `measured`）、`sources`（≥2 条来源身份） |
| `sources[]` | `{seed, strategy_sha256, strategy_bytes}` 三条；`seed` 为整数且**互不相同**；`strategy_sha256` 为小写 SHA-256；`strategy_bytes ≥ 1` |
| 交叉校验 | `stability.seed_set_sha256` **必须**等于对 `sources[].seed` 升序列表取规范 JSON 后的 SHA-256；`stability.audit_infosets_sha256` **必须**等于该人数审计集的同一哈希；参与比较的 seed 集合**必须**与 `sources[].seed` 集合一致 |
| 指标与审计集 | 沿用 `docs/34b` §5 与 `docs/49` §3.2–3.3：审计集 = 该人数**全部**信息集、不抽样；`max_l1` = 逐对 seed 与逐审计信息集的最大 L1 距离（原始、不归一化） |
| 只读消费 | 提供从**已封存策略产物**读取参与样本的**只读**入口（`policy.load_quantized_strategy`），不写回、不改写任何既有工件 |
| 写入 | 以既有 `safeio` 的规范 JSON 原子写入（新建、不覆盖） |

**为什么单列一个记录类型**：稳定性是「策略集合」的属性。把它塞进单条 experiment 记录或单条策略 artifact 都会语义不自洽（后者即裁定二拒绝扩展 artifact v1 的原因）。

### 3.4 不得声称

- 不得从策略 artifact v1 的 `quality.stability` 读出稳定性结果（`docs/35` §4.2 验收原文仍须满足）。
- 不得把单条受监督 experiment 记录的 `stability` 表述为已测得跨 seed 稳定性。
- 不得把本记录的数字表述为收敛、均衡、NashConv、exploitability 或真实 EV；窄区间不构成「稳定」、宽区间不构成「不稳定」。
- 不得跨人数比较或归因；不得把单 seed 纳入判定。
- 不得把本轮的实现表述为「已完成跨 seed 稳定性实验」。

## 4. 边界（沿用不可回退边界）

- **只读**：`backend/**`、`frontend/**`、真实数据库、`docs/20` 至 `docs/49a`；`tools/trainer/**` 中未被授权的文件（含 `kuhn_cfr/**`、`policy.py`、`control.py`、`mccfr.py`、`campaign*.py`、`supervised_measurement.py`）。
- **不得修改**：`policy.py`（artifact schema 与 `PROBABILITY_UNITS` 不动）、`backend/app/storage/models.py`（不加列、不迁移）、锁文件；`heuristic.py` 决策语义；`equity()`；`lookup_budget.py` 常量；质量判定门槛。
- **必须保持**：已封存 v1 子记录的**再读取能力**（`holdem-campaigns` 114 份 JSON）；统一支持 2–9 人；所有随机过程可注入 seed；注释用中文说明目的且**不引用仅文档出现的编号/概念**。

## 5. 不在本轮范围

- 不扩展策略 artifact v1、不触发任何后端身份升版（`docs/37` §3.1 与本轮无关，见 §1.3）。
- 不启动训练/评估/采样；不产生真实 `measured` 记录；不新建 campaign、不追加 seed、不重试 authorization。
- 不改质量门槛（`docs/39` 继续不启用）；不实现覆盖率、有效支持集、分位数等额外诊断字段。
- 不把新记录类型接入 `campaign.py` 的账本或 lease 路径（账本是 append-only 事件流，不适合承载该记录）。
- 不推进 P2-2。
