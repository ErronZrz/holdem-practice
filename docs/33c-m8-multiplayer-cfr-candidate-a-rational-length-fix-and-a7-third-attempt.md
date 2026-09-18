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

## 8. 第三次尝试的实际回执

见本文件第二次提交追加的内容。
