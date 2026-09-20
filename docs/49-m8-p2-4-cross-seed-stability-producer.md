# 49 M8：P2-4 跨 seed 稳定性代码内建生产者（最小形态规格冻结）

> 日期：2026-09-20。
>
> 本文件接在 `docs/48` / `docs/48a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/49` 记录本轮**规格与口径冻结**，`docs/49a` 记录与之对应的**实施回执**。
>
> **编号说明**：本轮最初约定的权威编号 `48` / `48a` 已由同一轮的 **P2-3 只读诊断**占用（见 `docs/48` / `docs/48a`，均已提交）。P2-4 是同一轮内被单独授权的第二项切片，故按顺序取下一编号 **49 / 49a**；**不**重编号、不改写既有文档。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P2-4** 一项的**最小形态**规格冻结。代码与测试在随后一次提交中落地。
>
> **本文件不产生任何策略、质量或资源证据**；未接入 CFR/查表、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、未启动任何受监督运行、未做任何云端操作。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项，最小形态）

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P2-4 | 跨 seed 稳定性的代码内建生产者 | **是（最小形态）** |
| P0-1 … P0-7 | 注册表、查表预算、抽象映射、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**只读引用**） |
| P1-1 … P1-5 | 位置投影、范围假设、逐池收益、真实规则边界、性能复测 | 否（已完成，仅**只读引用**口径） |
| P2-1 / P2-3 | 2–9 人产品验收 / 历史 `pot_results` 只读诊断 | 否（已完成，仅**只读引用**） |
| P2-2 | N=9 的任何更强结论 | 否 |

### 1.2 用户答复原文

本轮采用「**先问用户**」。答复原文照录：

| 项 | 用户答复原文 |
|---|---|
| 执行确认 | 「P2-4 最小形态（推荐）」：解禁 `tools/trainer/src/multiplayer_cfr/measurement.py`（及该工程的测试），实现一个**无 I/O** 的跨 seed 稳定性纯计算生产者，定义审计信息集集合与指标（沿用 `docs/34b` §5 已冻结口径），并配单测。不改受监督链路、不改 artifact v1、不启动任何受监督运行。 |

据此，**被授权**：修改 `tools/trainer/src/multiplayer_cfr/measurement.py`、在该工程内新增/扩充单元测试、新增 `docs/49*`。

**被拒绝**（本轮不做）：修改 `tools/trainer/**` 中除 `measurement.py` 与该工程测试以外的任何文件（尤其 `experiment_record.py`、`supervised_measurement.py`、`policy.py`、`kuhn_cfr/**`）；修改 `backend/**`、`frontend/**`、锁文件、真实数据库；扩展策略 artifact v1 的 `quality.stability`（**不触发** `docs/37` §3.1 升版）；改质量判定门槛或启用 `docs/39` 门槛；新增受监督运行或 campaign；追加 seed；重试 authorization。

### 1.3 形态裁定（冻结）

| 裁定 | 内容 |
|---|---|
| 一 | **最小形态**：只在 `measurement.py` 增加一个**无 I/O 的纯计算生产者**，把 `docs/34b` §5 已冻结的跨 seed 对照口径提升为代码能力。 |
| 二 | **不动受监督链路**：`experiment_record.py`（`multiplayer-cfr-supervised-measurement` v2）**不变**；`supervised_measurement.py`、`policy.py` **不变**。 |
| 三 | **不动 artifact v1**：`policy.py` 的 `quality.stability` schema 仍**只允许** `{status}`，未测量仍恒为 `{"status": "not-measured"}`；本轮的输出走**独立测量记录**（`multiplayer-cfr-measurement`）的 `stability` 段，**不**写入 v1 artifact。 |
| 四 | **不启动任何运行**：不产生 `status="measured"` 的**真实**记录；本轮只交付可被单测覆盖的**代码能力**。真实 measured 记录仍须另行授权的受监督运行。 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 2]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -2 --oneline
5e94d8a docs: record p2-3 historical pot results read-only diagnosis
4a41951 docs: freeze p2-3 historical pot results diagnosis specs

$ git rev-parse HEAD          -> 5e94d8a7da20e8c7d4f991c7bb47e4e60eded0ec
$ git rev-parse origin/master -> 133c99cbf541e9bf49d1f5f2e795ca6585e91d8d

$ cd tools/trainer && uv run ruff check .   -> All checks passed!
$ cd tools/trainer && uv run pytest -q      -> 197 passed in 185.29s (0:03:05)

$ cd backend && uv run pytest -q            -> 668 passed, 2 skipped, 2 warnings
```

本轮开始前工作区 **0 行**；未做任何 `reset` / `clean` / `stash` / `checkout`；本轮**不 push**。

## 3. 规格冻结（实施前的唯一依据）

### 3.1 现状缺口（已只读核对）

| 位置 | 事实 |
|---|---|
| `measurement.py` | `stability` 字段 schema 为 `{status, seed_set_sha256, audit_infosets_sha256, max_l1}`，`status ∈ {not-requested, not-measured, measured}`；**只有** `_validate_stability()` **校验**，**无生产者** |
| `experiment_record.py` | 受监督路径的记录**完全没有** `stability` 段 |
| `policy.py` | artifact v1 的 `quality.stability` **只允许** `{status}` 一个键 |
| 现有稳定性对照 | 全部是**工作树之外的事后只读脚本** |

### 3.2 审计信息集集合（冻结）

- 审计集 = **该人数的全部候选 A 信息集**，按 `game.infosets(player_count)` 的既有规范顺序，取每个 `InfoSetSpec.key`；**不抽样**（与 `docs/34b` §5「在全部信息集上、不抽样」一致）。
- 审计集只依赖人数，是纯函数；N=6 → 1 152 个、N=7 → 3 136 个、N=9 → 20 736 个。
- 生产者的输入**必须完整覆盖**审计集：缺项、多项、或键不属于该人数一律拒绝。

### 3.3 指标定义（冻结，沿用 `docs/34b` §5）

对参与比较的每一对 seed \((i, j)\) 与审计集中每个信息集 \(I\)：

\[
\mathrm{L1}_{ij}(I) = \sum_{a \in A(I)} \left| p_i(a \mid I) - p_j(a \mid I) \right|
\]

- 概率以整数单位表示（单位由调用方显式给出），距离以 `fractions.Fraction` **精确**计算。
- 输出的 `max_l1` = 上述值对**所有 seed 对**与**所有审计信息集**取的最大值（原始 L1，**不归一化**），以既约 `{numerator, denominator}` 报告。
- 本轮**只**产出 schema 已有的四个字段；`docs/26` §8 提到的「有效支持集大小」「两两分布完全相同的信息集占比」属**额外诊断**，本轮**不**写入 schema（避免为报告细节扩大契约）。

### 3.4 身份哈希定义（冻结）

| 字段 | 定义 |
|---|---|
| `seed_set_sha256` | 对**升序去重**的参与 seed 列表做规范 JSON（`{"seeds": [...]}`）后取 SHA-256 |
| `audit_infosets_sha256` | 对**规范顺序**的审计信息集键列表做规范 JSON（`{"infosets": [...]}`）后取 SHA-256 |

两者共同唯一确定「哪一组 seed、在哪一个审计集上比较」；不同人数因信息集键不同而**天然不碰撞**（人数隔离）。

### 3.5 输入契约与校验（冻结）

生产者签名（概念）：`build_stability_payload(*, player_count, strategies, probability_units)`。

- `player_count` 经 `game.validate_player_count` 校验；
- `probability_units` 必须是不小于 1 的整数（**不由本模块内建常量**，避免与 `policy.PROBABILITY_UNITS` 形成第二事实源）；
- `strategies` 是 `Mapping[seed, Mapping[infoset_key, Mapping[action, units]]]`：**seed 用映射键天然唯一**；参与数**少于 2 个**即拒绝（**单 seed 不判定**）；
- 每个策略的键集合必须**恰好等于**审计集；每个信息集的动作集合必须**恰好等于**该信息集的合法动作集合；每个单位为 `[0, probability_units]` 的整数且每个信息集之和**恰好等于** `probability_units`。

任何违反一律抛 `MeasurementRecordError`（复用既有异常类型）。

### 3.6 输出契约（冻结）

输出为可直接嵌入独立测量记录的 `stability` 段：

```text
{"status": "measured",
 "seed_set_sha256": <64 位小写 SHA-256>,
 "audit_infosets_sha256": <64 位小写 SHA-256>,
 "max_l1": {"numerator": <规范十进制>, "denominator": <规范十进制>}}
```

该输出**必须**能通过与既有 `_validate_stability()` 等价的全部校验（非负既约有理数、两个小写 SHA-256、字段恰为四项）。

### 3.7 不得声称

- 不得从 artifact v1 的 `quality.stability` 读出稳定性结果（`docs/35` §4.2 验收原文）。
- 不得把本生产者产出的数字表述为收敛、均衡、NashConv、exploitability 或真实 EV；窄区间不构成「稳定」，宽区间不构成「不稳定」。
- 不得跨人数比较或归因；不得把单 seed 结果纳入判定。
- 不得把本轮的代码能力表述为「已完成跨 seed 稳定性实验」。

## 4. 边界（沿用不可回退边界）

- **只读**：`backend/**`、`frontend/**`、`tools/trainer/**` 中未被授权的文件（含 `kuhn_cfr/**`、`experiment_record.py`、`policy.py`、`supervised_measurement.py`）。
- **不得修改**：`backend/app/storage/models.py`（不加列、不迁移）、锁文件、真实数据库、`docs/20` 至 `docs/48a`；`history_json` 原始事实；公开 API 的 Pydantic model；结算语义与 `equity()`；`lookup_budget.py` 既有常量；质量判定门槛。
- **必须保持**：统一支持 2–9 人；所有随机过程可注入 seed；注释用中文说明目的，且**不在代码注释中引用仅文档出现的编号/概念**。

## 5. 不在本轮范围

- 不接入受监督路径（`experiment_record.py` / `supervised_measurement.py` 不变）、不扩展 artifact v1、不触发 artifact 升版。
- 不运行任何训练/评估/采样；不产生真实 `measured` 记录；不新建 campaign、不追加 seed、不重试 authorization。
- 不实现覆盖率、有效支持集、分位数等额外诊断字段；不改变现有质量门槛（`docs/39` 继续不启用）。
- 不推进 P2-2，也不改变 `docs/35` §4.2 中其余条目的状态。
