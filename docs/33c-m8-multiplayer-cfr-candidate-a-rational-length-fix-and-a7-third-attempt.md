# 33c M8：多人 CFR 候选 A——有理数长度上限修复与 A7 第三次尝试

> 日期：2026-09-18。
>
> 本文件接在 `docs/33` / `docs/33a` / `docs/33b` 之后，继续沿用 `docs/30` D6 的编号族约定：`docs/33` 记录只读复核、证据边界与决策；`docs/33a` 记录 N9 边界实跑与第一次 A7 加轮；`docs/33b` 记录子进程诊断缺口修复与第二次 A7 加轮；本文件记录**测量记录校验器的有理数长度上限修复**，以及**第三次 A7 加轮**的规格与回执。
>
> 与 `docs/33b` 相同，本文件**分两次提交**：第一次随修复代码提交，只写第 1 至第 7 节；第二次在第三次尝试执行完成后追加第 8 节实际回执。这样写是为了让"冻结提交"早于任何受监督运行。
>
> **第 1 至第 7 节提交时，第三次尝试尚未启动，不声称已生成任何新策略、质量或资源证据。** `docs/20` 至 `docs/32a` 未被改写。

## 1. 本轮授权

用户答复原文：

| 编号 | 问题 | 用户答复 |
|---|---|---|
| Q7 | 是否授权修复有理数长度上限 | 「选 (a) 授权最小修复」 |
| Q8 | 是否授权第三次 A7-1000 重跑 | 「授权」 |
| Q9 | 若第三次仍失败是否预设第四次 | 「暂不预设」 |

由此：授权按最小方案修复（给有理数的分子/分母一个独立上限，标识符字段保持原强度）；授权在新 HEAD 上发起第三次 A7 加轮；**不**预设第四次——每次失败都应先看新落盘的根因再决定。

## 2. 缺口确认（来自 `docs/33b` 第 8.4 / 8.5 节）

第二次 A7 加轮（`a7-seed-7926-i1000-r2`）的失败根因由回执直接给出：

```text
multiplayer_cfr.experiment_record.ExperimentRecordError:
profile.utilities.numerator 必须是长度受限的非空字符串
  experiment_record.py:675 _require_string  ←  :688 _validate_rational
  ←  :509 _validate_profile_payload  ←  :121 build_manifested_measurement_record
```

`_require_string` 的 `len(value) > 128` 上限被复用于**所有**字符串字段，其中包含**精确有理数的分子与分母**。质量阶段（profile 与 probe）已经算完，子进程仅在构造测量记录时被拒。

## 3. 修复内容

改动只涉及一个源文件与一个测试文件：

| 文件 | 改动 |
|---|---|
| `tools/trainer/src/multiplayer_cfr/experiment_record.py` | 有理数文本改用独立上限 |
| `tools/trainer/tests/test_multiplayer_experiment_record.py` | 新增 2 条回归测试 |

### 3.1 具体改动

1. 新增模块级常量 `MAX_RATIONAL_DIGITS = 4_096`，并在其上方写明该值的依据（见第 4 节）；
2. 新增 `_require_rational_text(value, label)`，只在 `len(value) > MAX_RATIONAL_DIGITS` 时拒绝；
3. `_validate_rational` 的分子与分母校验由 `_require_string` 改为 `_require_rational_text`。

**标识符与哈希字段的 128 上限逐字未变**（`_require_string` 原样保留，`_require_hash` 继续经由它）。

### 3.2 未放松的既有校验

`_validate_rational` 的其余判据全部保留：必须恰好是 `numerator` / `denominator` 两个键；必须匹配规范十进制（`0|-?[1-9][0-9]*` 与 `[1-9][0-9]*`）；并且**重新约分后必须与输入字符串逐字一致**（即分子分母必须已是既约规范形式）。因此本次改动只放宽"位数"这一与正确性无关的形式约束，不放宽任何数值语义。

## 4. 为什么 4 096 是安全上界

- 候选 A 单条公开历史的动作数至多 `2N − 1`（开池前每座位可 check/bet，开池后至多 N−1 个回应者）：N=6 → 11，N=7 → 13，N=9 → 17。
- 每个动作的概率分母整除 `10^12`，故任一终局到达概率的分母整除 `10^(12 × (2N−1))`：N=9 约为 `10^204`（205 位）；再加上 `N!` 带来的分母与一次约分，量级不变。
- 因此 `4 096` 比 N=9 的理论位数上界高出一个数量级以上，同时仍远小于记录级上限：整条记录受 `MAX_TEXT_BYTES`（4 MiB）与 measurement 槽位上限（1 MiB）独立约束，`4 096` 不会使任何单条记录接近字节上限。
- 参考实测：既有**通过**记录的最大位数是 **110**（`docs/33b` 第 8.5 节）。

## 5. 本轮**未**修复的部分（如实标注）

`tools/trainer/src/multiplayer_cfr/measurement.py` 是另一份独立的测量记录 schema，它对同类字段使用的是 `_MAX_TEXT_LENGTH = 256`（经 `_require_string` → `_parse_rational`）。两份 schema 的口径仍然不一致。

本轮按"最小修复"只改了**阻断 A7 的那一处**（`experiment_record`）。`measurement.py` 的 256 上限**保留原状**，理由与风险如下：

- 该 schema 目前**不在受监督执行路径上**（受监督链只使用 `experiment_record` + `supervised_measurement`），因此它不是本次失败的成因，也不是当前的活跃缺陷；
- 但它对同类字段的上限更紧，属**已知的潜在不一致**，需要用户另行决定是否统一，本轮不擅自改动第二份校验器。

## 6. 离线复验

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
178 passed in 190.91s (0:03:10)
```

测试数由 `176` 增至 `178`，新增两条都在 `tests/test_multiplayer_experiment_record.py`：

1. 分子为 201 位十进制数（**超过 128**）的精确有理数记录被**接受**，且回读后与输入逐字一致——这正是第二次 A7 加轮被拒的形状；
2. 分子为 `MAX_RATIONAL_DIGITS + 1` 位的记录**仍被拒绝**，说明新上限本身也被强制。

这是**单元测试**：它证明"该形状的记录在代码层面可被写入"，**不等于**任何 A6/A7 实验结果、质量或资源基准。

## 7. 第三次尝试的规格（在提交后的新 HEAD 上重新冻结）

| 项 | 值 |
|---|---|
| campaign 根（工作树之外） | `/Users/bryanylliu/holdem-campaigns/m8-a-campaign-5` |
| `campaign_id` | `m8-a-campaign-5` |
| `authorization_id` / experiment `manifest_id` | `a7-seed-7926-i1000-r3` |
| probe `manifest_id` | `a7-probe-tight-loose-i1000-r3` |
| 参数 | `player_count = 7`、`iterations = 1000`、`average_strategy_start_iteration = 100`、`master_seed = 7926` |
| 阶段预算 | `training / export / profile / probe / measurement = 900 000 / 120 000 / 600 000 / 3 000 000 / 120 000` ms |
| 其余预算 | cpu / wall `4 740 000 ms`、工件预留 16 MiB、策略槽位 12 MiB、measurement 槽位 1 MiB、RSS 6 GiB / 8 GiB |

- 全部输入在**新 HEAD** 上重新生成并重跑 estimator preflight；**不复用** campaign-2 / campaign-3 / campaign-4 的任何输入文件；
- **不重试** campaign-1 的 `a6-seed-6922`、campaign-3 的 `a7-seed-7926-i1000`、campaign-4 的 `a7-seed-7926-i1000-r2`；
- 参数与预算 envelope 与上次逐字相同，**不扩额、不下调**；
- 仍**没有** estimator preflight 证据（preflight 只覆盖 N=6，D4.3），仍是单 seed。

若第三次仍失败，按 `docs/33b` 第 7 节的先例**先看根因再决定**，本轮不预设第四次。

## 8. 第三次尝试的实际回执（第二次提交追加）

### 8.1 结论摘要

**第三次尝试成功完成，并且是 A7 第一次产出可落盘的质量记录。** 三点必须同时记住：

1. 修复是**必需**的：本次记录中精确有理数的最大位数实测为 **134**，**超过**旧上限 128——与第 2 节记录的失败形状完全吻合；
2. 在固定抽象、固定 N=7、固定 1000 轮与固定 seed 7926 下，**两组预注册 probe 在全部座位上的双向 delta 均为负**，`gains` 全为 `0`，因此按 `docs/31a` 第 3.2 节口径为「**未观察到超过 0.05 的阈值偏离**」；
3. 这**仍然不是**收敛、均衡、NashConv、exploitability 或真实 EV 的证据——见第 8.6 节的严格限定。

### 8.2 冻结输入身份（全部在 `bd1483d3324c5866901ed827365aa138e5900236` 上重新生成）

| 文件 | id | sha256 | 字节 |
|---|---|---|---:|
| `campaign.json` | `m8-a-campaign-5` | `da05bb7abd3fb41529549838bdb635c7646168f3e7a769fbb3a3d6dfc3cdbbb1` | 1018 |
| `source/a7-probe.json` | `a7-probe-tight-loose-i1000-r3` | `7845f13908590eb3f17c22c14c09998e26b6859d89966cd92f1c49bd9be70a12` | 461 |
| `source/a7-experiment.json` | `a7-seed-7926-i1000-r3` | `d28ae22fa7bcb17c1bb3682a7728d5431c7de567e7587cbba49b3a2f2431ce17` | 1310 |
| `source/preflight-spec.json` | `n6-estimator-preflight` | `cdfc6346ab3d8a9406073763735e723fdd85df3d5118bc2e302f10685e7fbcd8` | 527 |
| `source/preflight-attestation.json` | `n6-estimator-preflight` | `2c08f9339a680286313557f050e329c5803fe07bf6d80c90e7aac6da5f79cfad` | 1018 |

attestation 由 `run_preflight` 实跑产生，`passed = true`；参数与预算 envelope 与前两次尝试逐字相同。

### 8.3 回执与终态

| 项 | 值 |
|---|---|
| 父监督回执 | `status = completed` / `stop_reason = completed` / `exit_code = 0` / 无信号终止 |
| 墙钟 / CPU | `414 312 ms`（6 min 54 s）/ `408 320 ms`（6 min 48 s） |
| 峰值 RSS | `49 577 984 B`（约 47.3 MiB） |
| 警告触发 | `false`（未触及 CPU、阶段墙钟、RSS 任一阈值） |
| 子进程合并输出 | `child_output_bytes = 0`，`child_output_sha256 = e3b0c442…b855`（空串摘要）→ 成功路径**不产生任何输出**，诊断通道零开销 |
| 终态 ledger | `leased` → `finalized(status = "completed")` |
| `final_measurement_sha256` | `86a0c9e2a6c1fca15f320e600891ce103575a58a1490011aac7d9295c9602184` |
| `supervisor_receipt_sha256` | `931975ba6db77631e81906ebe878bda783bef22915e1ee407936608a3399428c` |
| `final_inventory` | `measurement.json` 15 460 B `86a0c9e2…02184`；`strategy.json` 1 142 972 B `0f0b04cda6e002ed50a4f31c26cc1087018806055bbdab720e36a075fffeb553` |

子端 `resources.supervisor_version = v2`（本次修复引入的新回执 schema）。子端训练阶段 `elapsed_milliseconds = 5 295`（300 轮时为 1 471 ms，约 3.6 倍，与轮次比一致）。

### 8.4 质量结果（预注册口径）

- full-chance profile：ordered deal 5 040，终局叶 **507 482**（300 轮时为 718 988；该计数随策略变化，因为零概率分支会被剪掉）。各座位每手牌平均净效用（BB/hand，相对座位 0–6）：

  ```text
  [-0.089260, -0.067165, -0.030841, +0.035470, +0.025627, +0.094592, +0.031576]
  ```

  以 `fractions.Fraction` 精确求和为 **0**（严格常和）。
- probe（`a7-probe-tight-loose-i1000-r3`，两组与 `docs/31a` C5 同值）：

  ```text
  gains = [0, 0, 0, 0, 0, 0, 0]
  loose-open delta = [-0.3957, -0.5579, -0.4990, -0.5288, -0.4336, -0.5964, -0.6224]
  tight-open delta = [-0.1036, -0.1605, -0.1394, -0.1510, -0.1239, -0.1983, -0.1961]
  ```

  按 `docs/31a` 第 3.2 节冻结口径：**未观察到超过 0.05 的阈值偏离**。
- 精确有理数最大位数：**134**（> 128，本次修复的直接必要性证据）。
- 抽样诊断：每座位信息集总数 3 136；访问覆盖 148–219 个信息集/座位（visits 1 000–1 876）；重要性权重 `maximum_milli` 53 333–512 000、`p95_milli` 6 291–8 471、`non_finite_count` 全为 0。

### 8.5 与 300 轮结果的对照（只作对照，不作因果结论）

| 项 | A7 / 300 轮（`docs/32a`） | A7 / 1000 轮（本次） |
|---|---|---|
| `max_p gains[p]` | `0.361573`（座位 6） | `0.0` |
| `gains` 非零座位 | 座椅 0、4、5、6 | 无 |
| 双向 delta 为正的座位 | `tight-open` 除座位 1 外为正 | 无 |
| profile 值向量 | `[-0.0095, -0.0068, +0.1721, +0.2324, +0.1037, -0.1268, -0.3652]` | `[-0.0893, -0.0672, -0.0308, +0.0355, +0.0256, +0.0946, +0.0316]` |
| 训练阶段耗时 | 1 471 ms | 5 295 ms |
| 访问覆盖（每座位） | 86–176 | 148–219 |

如实说明两点：

1. 差异不只来自轮次：`average_strategy_start_iteration` 也由 30 变为 100（沿用 10% 预热比例），因此这是**两个变量同时变化**的对照，不能把结果单独归因于 iterations。
2. **profile 值向量变化很大**（例如座位 3 由 `+0.2324` 变为 `+0.0355`，座位 6 由 `-0.3652` 变为 `+0.0316`）。这说明平均策略在 300 与 1000 轮之间**仍在显著移动**，因此"1000 轮下未发现 probe 偏离"**不能**被表述为"已收敛"或"已到均衡"。

### 8.6 如何解读（严格限定）

- 结果限于固定抽象 `m8-unique-rank-single-open` / `m8-a-v1`、固定 N=7、固定 1000 轮、固定 seed 7926 的**单 seed**运行；`docs/31a` D3.3 的跨 seed 实验**仍未执行**，**不构成任何稳定性结论**。
- `gains` 全为 0 只说明**这两组预注册阈值策略**在全部座位上都没有发现增益；它**不是** best response、**不是** NashConv、**不是** exploitability，也**不代表不存在其它合法偏离**。
- profile 值是"指定抽象、指定量化策略、指定测量器"下的收益基线，**不是**真实牌局 EV。
- 本次成功**不改变**候选 A 不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实 EV 或生产可用策略这一边界。
- 本次成功也**不**把前两次失败变成"有价值的探索"：那两次各消耗了一条不可重试 authorization 与约 6.6 min CPU，未换回任何质量证据；唯一新增可用物是根因本身。
- 仍无 estimator preflight 证据（只覆盖 N=6，D4.3）；仍无逐阶段耗时（回执只含训练阶段 elapsed 与父端总墙钟）。

### 8.7 预算核算（更新，Q2 = b 口径）

```text
campaign-1 A6（不可核算）          记 0            （记账约定，非"未消耗"）
campaign-2 A6 + A7（实测 CPU）     8.40 min
N9 boundary（实测 CPU 450 ms）     0.01 min
campaign-3 A7-1000（实测 CPU）     6.65 min
campaign-4 A7-1000-r2（实测 CPU）  6.61 min
campaign-5 A7-1000-r3（实测 CPU）  6.81 min
合计实测                           28.48 min ≤ 120 min   （余约 91.5 min）
```

按预留上界口径同样未越限。本轮同样发生了若干次 estimator preflight 核验重演（生成时 1 次 `run_preflight`，加上只读复验、父端门禁与子端门禁的重演），按 `docs/30` D3 **不计入**本机实验预算。

### 8.8 本轮未做事项与下一步

未做：未修改 `kuhn_cfr`、后端、前端、锁文件或真实数据库；未重试任何已消耗 authorization；未追加 seed；未执行跨 seed 稳定性实验；未修订质量判定门槛；未改写 `docs/20` 至 `docs/32a`。

下一步建议（需用户决定）：

1. **质量判定口径**：`docs/33` 第 7 节按 Q1 = (c) 把门槛留到"先补证据"之后。现在已有 A7（300 轮 / 1000 轮）两条可落盘记录，可据此进入 (b) 讨论门槛（须写明作用对象、是否区分 N=6 / N=7、超线后的处置动作）；
2. **跨 seed（D3.3）**：若要让"未观察到偏离"具备稳定性含义，需要重开 D3.3 并预先列入同一 manifest 的 seed 集合，这需要新的授权与新的冻结 campaign；
3. 或维持只报告不判定，把候选 A 收尾。
