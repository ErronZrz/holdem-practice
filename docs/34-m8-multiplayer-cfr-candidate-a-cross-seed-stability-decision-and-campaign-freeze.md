# 34 M8：多人 CFR 候选 A——跨 seed 稳定性决策与 campaign-6 冻结

> 日期：2026-09-18。
>
> 本文件接在 `docs/33` / `docs/33a` / `docs/33b` / `docs/33c` 之后，继续沿用 `docs/30` D6 的编号族约定：`docs/33` 记录只读复核、证据边界与决策；`docs/33a` 记录 N9 边界实跑与第一次 A7 加轮；`docs/33b` 记录子进程诊断缺口修复与第二次 A7 加轮；`docs/33c` 记录有理数长度上限修复与第三次 A7 加轮；本文件记录**测量记录上限口径的统一**与**跨 seed 稳定性实验的决策与冻结规格**。
>
> 与 `docs/33b` / `docs/33c` 相同，本文件**分两次提交**：第一次随修复代码提交，只写第 1 至第 9 节；第二次在跨 seed 执行完成后追加第 10 节实际回执。这样写是为了让"冻结提交"早于任何受监督运行，避免文档自身改动打断工作树干净前置。
>
> **第 1 至第 9 节提交时，跨 seed campaign 尚未启动，不声称已生成任何新策略、质量或资源证据。** `docs/20` 至 `docs/33c` 未被改写。

## 1. 本轮授权与用户答复原文

用户答复原文：

| 编号 | 问题 | 用户答复 |
|---|---|---|
| Q10 | 质量判定门槛 | 「(c) 继续补证据」——先执行跨 seed 稳定性，据多 seed 证据再定门槛 |
| Q11 | 跨 seed 稳定性（`docs/31a` D3.3） | 「重开并授权新 campaign」——新建冻结 campaign 并重跑全部输入与 preflight |
| Q12 | `measurement.py` 的 256 上限是否统一 | 「统一到独立上限」——改 `measurement.py`（+ 回归测试），与 `experiment_record` 的 4096 口径一致；若本轮新建 campaign，该改动应在冻结前完成 |
| Q13 | 下一步主线 | 「先完成上述动作再决定」——**暂缓**，本轮不推进候选 B / 生产接入 / M6 |
| Q14 | seed 集合与数量 | 「4 个 seed（含参考 7926）」——7926 + 1215 + 3311 + 20260918 |
| Q15 | 每条 authorization 的预算 envelope | 「20 min/条（推荐）」——可容纳 4 条，预留合计 80 min ≤ 剩余余量 |
| Q16 | commit / push | 「commit + push」 |

由此**被授权**的事项：按第 3 节统一 `measurement.py` 的有理数长度上限并补回归测试；按第 7 节新建冻结 campaign `m8-a-campaign-6`，以 4 个预注册 seed 执行跨 seed 稳定性实验；本轮文档与代码修复定稿后 commit 并 push。

**被拒绝或暂缓**的事项：本轮**不设**任何质量合格线（Q10 = c）；下一步主线**未定**（Q13 暂缓）；不扩预算、不转云、不转 GPU、不追加表中未列出的 seed；不重试任何已消耗 authorization。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git rev-parse HEAD          -> af30918f2004d0237400afd0fa0304333ec7b617
$ git rev-parse origin/master -> af30918f2004d0237400afd0fa0304333ec7b617

$ git log -14 --oneline
af30918 docs: record a7 third attempt completion and quality receipt
bd1483d fix: give exact rationals a dedicated length bound in measurement records
c0ea1e2 docs: record a7 retry receipt and located record-length defect
578a565 fix: capture supervised child diagnostics in supervisor receipt
1e59407 docs: record n9 boundary sample and a7 scale-up execution receipts
634c694 docs: freeze candidate-a evidence boundary and record round decisions
ce35dfb docs: record campaign-2 execution results
4139c3a fix: validate supervised measurement identity per manifest slot
dc79ee9 docs: correct 31/31a naming and finalize campaign freeze checklist
41c9d8a docs: record freeze readiness review and canonical campaign freeze checklist
8f8d8fd feat: enforce campaign preflight and reservation gates at supervised entry
9881050 docs: record execution integrity review and fixes
b9c4554 feat: harden campaign execution integrity
8601a4b feat: harden supervised campaign execution
```

与期望基线完全相符（`## master...origin/master` 不多不少、工作区 0 行、`HEAD == origin/master == af30918`）；未做任何 `reset` / `clean` / `stash` / `checkout`。

本轮为撰写第 3 节而读取的两处只读事实（不构成任何实验证据）：

```text
tools/trainer/src/multiplayer_cfr/measurement.py:23   _MAX_TEXT_LENGTH = 256
tools/trainer/src/multiplayer_cfr/measurement.py:531  _parse_rational → _require_string（分子/分母共用 256）
tools/trainer/src/multiplayer_cfr/experiment_record.py:32  MAX_RATIONAL_DIGITS = 4_096
```

即 `docs/33c` 第 5 节标注的"已知潜在不一致"在提交 `bd1483d` 之后仍然存在，本轮按 Q12 处置。

## 3. `measurement.py` 有理数长度上限的统一（本轮修复）

### 3.1 具体改动

改动只涉及一个源文件与一个测试文件：

| 文件 | 改动 |
|---|---|
| `tools/trainer/src/multiplayer_cfr/measurement.py` | 有理数文本改用独立上限 |
| `tools/trainer/tests/test_multiplayer_measurement.py` | 新增 2 条回归测试 |

1. 新增模块级常量 `MAX_RATIONAL_DIGITS = 4_096`，与 `experiment_record` 同名同值；
2. 新增 `_require_rational_text(value, label)`，只在 `len(value) > MAX_RATIONAL_DIGITS` 时拒绝；
3. `_parse_rational` 的分子与分母校验由 `_require_string` 改为 `_require_rational_text`。

**标识符与哈希字段的 `_MAX_TEXT_LENGTH = 256` 逐字未变**（`_require_string` 原样保留，`_require_hash` 继续经由它）。`4 096` 的取值依据与 `docs/33c` 第 4 节相同：候选 A 单条公开历史的动作数至多 `2N − 1`，每个动作的概率分母整除 `10^12`，故 N=9 的理论位数上界约 205 位，`4 096` 高出一个数量级以上，同时远小于记录级上限（`MAX_MEASUREMENT_BYTES` 4 MiB 独立生效）。

### 3.2 未放松的既有校验

`RationalValue` 的全部语义判据保留：分子必须匹配 `0|-?[1-9][0-9]*`、分母必须匹配 `[1-9][0-9]*`，并且**重新约分后必须与输入字符串逐字一致**（既约规范形式）。本次只放宽"位数"这一与数值正确性无关的形式约束。

### 3.3 兼容性

该改动只**放宽**接受范围，不使任何此前合法的记录变得非法，因此**不是向后不兼容**；既有 measurement / strategy / ledger 文件的字节不受影响（本轮未重写任何历史工件）。

需要如实说明的一点：`measurement.py` **不在受监督执行路径上**（受监督链只使用 `experiment_record` + `supervised_measurement`），因此本次修复**不是**第 7 节 campaign 的前置条件，也不改变任何既有失败与成功的成因判断。它的作用仅是消除 `docs/33c` 第 5 节记录的、两份 schema 之间的已知口径不一致。

### 3.4 离线复验

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
180 passed in 185.37s (0:03:05)
```

测试数由 `178` 增至 `180`，新增两条都在 `tests/test_multiplayer_measurement.py`：

1. 首位效用取 301 位分子（**超过 256**）并以其相反数配平的常和 profile 被**接受**，回读后与输入逐字一致；
2. 分子为 `MAX_RATIONAL_DIGITS + 1` 位的记录**仍被拒绝**，说明新上限本身也被强制。

这是**单元测试**：它证明"该形状的测量记录在代码层面可被写入"，**不等于**任何 A6/A7 实验结果、质量或资源基准。

## 4. 候选 A 当前证据边界（本轮冻结，不得扩张）

### 4.1 已被证据支持

1. **固定抽象与身份**：`game.id = m8-unique-rank-single-open`、`game.version = m8-a-v1`。
2. **三条单 seed 受预算运行完成**：A6（N=6, seed 6922, 1 000 轮）、A7（N=7, seed 7926, 300 轮）、A7（N=7, seed 7926, **1 000 轮**，campaign-5，`bd1483d`）。三条的父端回执均为 `completed` / `stop_reason = completed` / `exit_code = 0`。
3. **常和效用精确为零**：三份 full-chance profile 的 `utilities` 以 `fractions.Fraction` 精确求和均为 0。
4. **固定 evaluator 的 full-chance profile 值与终局叶计数**：`candidate-a-full-chance-evaluator` / `v1`，`probability_units = 1e12`；A6 叶 20 672、A7-300 叶 718 988、A7-1000 叶 507 482（叶计数随策略变化，零概率分支被剪掉）。
5. **两组预注册 probe 的 `gains` 与双向 `delta`**：A6 全 `0`；A7-300 `max_p gains = 0.361573`；A7-1000 全 `0` 且双向 `delta` 全为负。
6. **受监督执行链在 6 次执行中真实走通**：快照 → lease → 门禁 → 父子身份核验 → 独占工件根 → 父端最终 measurement → 封存清单。
7. **实测资源与工件字节**：量级为每次 0.4–6.9 min 墙钟、约 44–47 MiB 峰值 RSS、约 1.15 MiB 工件。
8. **N9 单次边界采样**：`boundary_infoset_count = 20 736`，551 ms 墙钟 / 450 ms CPU / 43.8 MiB；该路径免 lease，不产生策略。

### 4.2 未被证据支持（不得声称）

- 任何**收敛、均衡、NashConv、exploitability、best response、真实牌局 EV、生产可用性**结论；
- **跨 seed 稳定性**（`docs/31a` D3.3 此前未执行；本轮第 7 节才首次执行，其结论以 `docs/34a` 的实际回执为准）；
- **N=9 的任何训练或质量结论**（只有一次单 traverser 采样）；
- 真实 Hold'em 的**位置、范围、真实下注尺度、公共牌、all-in/边池、逐层多人平局与整数结算、短码 CALL 收益**；
- **A7-300 与 A7-1000 差异的成因**：两者是 `iterations`（300→1000）与 `average_strategy_start_iteration`（30→100）**同时变化**的对照；且 profile 值向量在两者之间变化很大（座位 3 `+0.2324 → +0.0355`、座位 6 `−0.3652 → +0.0316`），说明平均策略仍在显著移动，因此"A7-1000 未发现 probe 偏离"**不得**表述为收敛或均衡；
- **A6 / A7-300 / A7-1000 之间的横向可比性**：人数与轮次/预热均不同。

### 4.3 与既有质量口径文档的对应

| 本文结论 | 对应条款 |
|---|---|
| 只有守恒、固定 profile 值与有限 probe 集可报告 | `docs/26` §8 指标表 |
| `probe_gain = 0` 或未超 X 只是「这两个特定阈值策略未发现增益」 | `docs/26` §8、`docs/29` §4.2 |
| 严禁把常和、regret、归一化、单 seed 可重放、短路径测试表述为收敛或充分训练 | `docs/29` §4.3 |
| 阈值 probe 的 `T_i` 必须在训练前写入版本化 manifest | `docs/26` §8 |
| X = 0.05 BB/hand 是**解释边界**而非硬门禁 | `docs/31a` §3.2 / D3.4 |
| estimator preflight 只覆盖 N=6；A7 无 preflight 证据 | `docs/31a` D4.3 |
| 跨 seed 稳定性是**经验性**诊断，不是正确性或均衡质量 | `docs/26` §8、`docs/29` §4.1 |

## 5. 质量判定口径的现状（Q10 = c 的落地）

**本轮仍不建立任何质量合格线。** 现状如实记录为：

1. `docs/20` §9.3 把「CFR/教学上线质量门槛」留给实现轮约定，至今**未被约定**；
2. `docs/31a` D3.4 已明确 X = 0.05 BB/hand 只是**解释边界**，不是门禁；
3. `docs/33` 第 7 节按 Q1 = (c) 把门槛留到"先补证据"之后；本轮 Q10 仍选 (c)，因此**动作是补跨 seed 证据，而不是定门槛**；
4. 在门槛被约定并签收之前，`gains` / `delta` 一律只作**解释性指标**报告。

若后续要建立门槛，必须先写明三点：作用对象（`probes.gains` 还是双向 `results[].delta`）、是否区分 N=6 与 N=7、超线后的处置动作。

## 6. 预算口径与累计核算（Q15 = 20 min/条）

沿用 Q2 = b 的**本机累计 2 小时**口径（campaign-1 不可核算部分记 0，见 `docs/33` 第 8 节）。

```text
已落盘实测累计（docs/33c §8.7）              28.48 min
本机累计上限                                 120.00 min
剩余余量                                     91.52 min

campaign-6 预留合计（4 × 20 min）            80.00 min  ≤ 91.52 min   ✓
campaign-6 预计实测（4 × 约 6.8 min）        27.2 min
预计累计（实测口径）                         55.7 min  ≤ 120 min      ✓
```

其余资源：单条 experiment 工件预留 16 MiB，campaign 工件预留 4 × 16 MiB = 64 MiB，远低于本机 1 GiB 保留上限；单条 experiment RSS 硬停 8 GiB，campaign 峰值 RSS 上限同口径。

estimator preflight 的**核验重演**（生成时 1 次 `run_preflight` 实跑，加上只读复验、父端门禁与子端门禁的重演，量级约每次 1 分钟）按 `docs/30` D3 **不计入**本机实验预算。

## 7. 跨 seed campaign-6 的冻结规格

### 7.1 目的与形式（必须先说清的限制）

本轮要回答的问题只有一个：**在候选 A 固定抽象、固定 N=7、固定 1 000 轮与固定预热下，把 `master_seed` 换成 4 个预注册值，产出的策略与质量指标是否稳定。**

必须在结果之前说明两条限制：

1. **代码中没有跨 seed 稳定性的生产者。** `measurement.py` 只定义了 `stability` 字段的**校验**（`{status, seed_set_sha256, audit_infosets_sha256, max_l1}`），受监督路径使用的 `experiment_record.py` 连该字段都没有；策略 artifact v1 的 `quality.stability` 恒为 `{"status": "not-measured"}`。因此本轮跨 seed 稳定性**只能是事后跨工件比较**（对已封存的 measurement / strategy 文件做只读计算），**不是**代码内建的稳定性指标，也**不得**把 v1 artifact 的 `stability` 字段读成稳定性结果。
2. **本 campaign 的 4 条 authorization 除 `master_seed` 外参数逐字相同**，且全部在同一 `code_identity` 下生成。这正是相对 `docs/33c` 第 8.5 节那个"两个变量同时变化"的对照的关键改进：本轮若出现差异，**不能**再归因于人数、轮次或预热。

### 7.2 seed 集合与 authorization（预注册，不得追加）

| authorization_id / experiment `manifest_id` | probe `manifest_id` | `master_seed` |
|---|---|---|
| `a7-seed-1215-i1000` | `a7-probe-tight-loose-c6-1215` | `1215` |
| `a7-seed-20260918-i1000` | `a7-probe-tight-loose-c6-20260918` | `20260918` |
| `a7-seed-3311-i1000` | `a7-probe-tight-loose-c6-3311` | `3311` |
| `a7-seed-7926-i1000-r4` | `a7-probe-tight-loose-c6-7926-r4` | `7926`（参考，在新 HEAD 上重跑） |

- 表中 4 个 seed **就是全部**：实验开始后不得追加、不得替换、不得因某个 seed 结果不理想而重跑；
- authorization 已按 id 升序排列（`campaign.py` 的硬校验）；
- `7926` 在新冻结提交上重跑，可与 campaign-5（`bd1483d`）的 `strategy.json` sha256 `0f0b04cd…eb553` 逐字对照，用于检验**同一 seed 在同一参数下的可重放性**；若不一致，那是一条必须如实记录的新发现，而不是可以忽略的噪声。

### 7.3 参数与预算 envelope（Q15 = 20 min/条）

参数（4 条逐字相同）：`player_count = 7`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`execution.kind = a6-a7-training`、`quality.profile_mode = full-chance`、probe 两组沿用 `tight-open`（4/3）与 `loose-open`（1/0）。

| 项 | 值 |
|---|---|
| 阶段预算（ms） | `training 240_000` / `export 60_000` / `profile 360_000` / `probe 420_000` / `measurement 120_000` |
| stages 之和 = 父端墙钟硬限（ms） | `1_200_000`（20 min） |
| `budget.cpu_limit_milliseconds` | `1_200_000` |
| 工件预留 | `16_777_216`（16 MiB）；strategy 槽位 12 MiB、measurement 槽位 1 MiB |
| RSS | 预警 6 GiB、硬停 8 GiB |
| `max_concurrency` | `1` |
| campaign `limits` | cpu / wall `4_800_000`（80 min）、工件 `67_108_864`（64 MiB）、峰值 RSS 8 GiB |

约束自检（与 `docs/31a` §5.2 同口径）：

- `2 × measurement.maximum_bytes + strategy.maximum_bytes = 2×1_048_576 + 12_582_912 = 14_680_064 ≤ 16_777_216` ✓；
- `strategy.maximum_bytes = 12 MiB ≤ min(64 MiB, A7 静态预算 12 MiB)` ✓；
- stages **恰好**按 `training, export, profile, probe, measurement` 顺序 ✓；
- 预留总和 `4 × 1_200_000 = 4_800_000 ≤ limits` ✓。

**必须如实披露的风险**：本 envelope 相对 A7-1000 原值（`4_740_000` ms / 79 min）是**收紧**，不是扩额。收紧的理由是共享预算内要容纳 4 个 seed（4 × 79 min = 316 min 远超剩余余量）。收紧后的余量口径：

- `training` 240 s，对实测训练阶段 5.30 s 是约 45 倍；
- `profile + probe` 合计 780 s，对 A7-300 实测整条墙钟 492 s（其中训练 1.5 s）与 A7-1000 实测整条墙钟 414 s（其中训练 5.3 s）约为 1.6–1.9 倍。

因此若某个 seed 的评估显著更慢，该条 authorization 会因阶段墙钟/父端墙钟触发而失败，**并已永久消耗**。这是本轮为换取 4 个 seed 的对照能力而明确接受的代价，不得在事后表述为"预算充足"。

### 7.4 目录与驱动脚本（全部在工作树之外）

| 项 | 值 |
|---|---|
| campaign 根 | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-6/` |
| 目录内约定 | `generate_frozen_inputs.py`、`run_campaign.py`、`source/`、`runs/<authorization_id>/{artifacts,inputs}`、`campaign.json`、`campaign-ledger.json` |
| Python 解释器 | `/Users/bryanylliu/my4/holdem-practice/tools/trainer/.venv/bin/python` |

`generate_frozen_inputs.py`：核对工作树干净与实际 HEAD，在内存中构造 4 份 probe manifest、4 份 experiment manifest、preflight spec、preflight attestation 与 campaign manifest，**实跑一次 `run_preflight`** 并确认 `passed = true`，随后原子写入并**回读逐项比对身份**；拒绝覆盖既有文件。

`run_campaign.py`：**默认只读复验**（加载全部冻结输入、复验 preflight 证据、复算资源预留、核对工作树身份与运行目录、确认该 authorization 尚未被 lease），不获取 lease、不创建任何运行目录；只有 `--execute <authorization_id>` 才消费一条 lease，且一次只允许一条。日志按 authorization 分开且已存在不覆盖。

沿用 `docs/33a` 第 1 节与 `docs/33b` 第 8.7 节记录的两次驱动缺陷教训：只读模式不得写执行日志；打印回执不得把 `SupervisedExecutionResult` 当作 `CampaignExecutionResult` 使用。

### 7.5 执行顺序与冻结前置

```text
1. 提交第 3 节的代码修复与本文第 1–9 节 -> 记录新 HEAD（= 冻结提交）
2. 确认工作区重新完全干净（--untracked-files=all 为 0 行）
3. 在工作树之外建 campaign-6 根与 source/，生成并回读全部冻结输入（含实跑 preflight）
4. 只读复验 campaign-6（不获取 lease）
5. 逐条执行 4 条 authorization（每条 lease 一次，成功后不重跑）
6. 只按实际回执写 docs/34a
```

硬前置（代码已强制，违反即 fail-closed）：工作区完全干净；manifest 的 `code_identity.git_commit` 等于**启动时刻实际 HEAD**；全部输入与运行目录都在工作树之外；每条 authorization 只 lease 一次。

### 7.6 预注册的跨 seed 对照口径（在任何结果产生之前冻结）

对 4 条成功记录做**只读**比较，全部指标在见结果前定义如下，不得事后增减：

1. **策略概率的 L1 距离**：对每一对 (seed i, seed j)，在**全部**信息集上（不抽样；候选 A 的信息集全集可由规则树确定性枚举，N=7 每座位 3 136 个）计算 `Σ_a |p_i(a) − p_j(a)|`，报告**每信息集的最大值**与**全部信息集的平均/分位**；概率以整数单位 `1e12` 表示，故该值可用 `fractions.Fraction` 精确计算。同时报告跨 seed 出现非零概率的**有效支持集**大小与两两支持集的交并规模。
2. **profile 值区间**：逐座位报告 4 个 seed 的 `profile.utilities`（BB/hand）的 min–max 区间（精确有理数）。
3. **probe 结果区间**：逐座位报告 `probes.gains` 与双向 `results[].delta` 的 min–max 区间，以及按 `docs/31a` §3.2 口径（X = 0.05，作用于 `probes.gains`）的"是否观察到超过 0.05 的阈值偏离"。
4. **终局叶计数与抽样诊断**：逐 seed 报告终局叶计数、每座位访问覆盖与重要性权重分位。
5. **可重放性**：seed 7926 本轮 `strategy.json` 的 sha256/字节数与 campaign-5 的对照。

**本口径不设任何合格线**：区间窄不构成"稳定"结论，区间宽也不构成"不稳定"结论；两者都只是"4 个特定 seed 下两个经验量级的观察"。不得据此声称收敛、均衡、NashConv、exploitability 或真实 EV。

## 8. 持续披露与不得声称

- macOS supervisor 是本机 `ps` **采样式进程组监督**，**不是不可逃逸的内核级 containment**；`docs/33b` 新增的子进程输出捕获是**父端合作式观察**，只保留受限尾部（8 KiB 字节 / 2 048 字符），不是安全边界。
- campaign ledger **无哈希链**；"不可重试"依赖代码流程，不是账本自身的完整性证明。
- 门禁（lease 守卫、preflight 复验、预算预留校验）均为 **Python 级 API 约束**，不是对抗性安全边界；训练原语（`run_manifested_experiment`、`manifest_executor`、`mccfr.train`、`evaluate_profile` 等）**直接调用属流程违规**。
- **单元测试 / N9 boundary / estimator preflight 不等于 A6/A7 实验结果**。
- 必须如实延续三次 A7 加轮失败的代价记录（campaign-1 / campaign-3 / campaign-4 各消耗一条不可重试 authorization；其中 campaign-4 的评估结果算出来了却因校验器拒绝而无法落盘），不得写成"验证了链路"或"有价值的探索"。
- 本轮仍是固定抽象、固定人数与固定轮次；**4 个 seed 仍不构成均衡质量结论**。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**

## 9. 本轮未做事项（截至本文提交）

- 未修改 `kuhn_cfr`、后端、前端、锁文件或真实数据库；本轮代码改动只有第 3 节的 `measurement.py` 与其测试。
- 未执行跨 seed campaign（在第 5 步才启动）；未重试 campaign-1 / campaign-3 / campaign-4 / campaign-5 的任何 authorization。
- 未追加预注册 seed 集合之外的 seed；未扩预算、未转云、未转 GPU。
- 未修订质量判定门槛（Q10 = c）；未定下一步主线（Q13 暂缓）。
- 未改写 `docs/20` 至 `docs/33c`；既有 campaign 记录与工件原样保留。
