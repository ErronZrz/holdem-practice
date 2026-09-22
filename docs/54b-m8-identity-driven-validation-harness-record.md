# 54b M8：验证入口的身份驱动适配实施回执（D5 前置）

> 日期：2026-09-22。
>
> 本文件是 `docs/54` 决策 D5 的**前置实施回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/54a` 未被改写。
>
> 本文件记录已落地的测试侧改动与已实跑的常规检查。**不产生任何质量或强度证据**：未运行任何阶段实跑、未冻结任何新清单、未创建任何新目录或报告。

## 1. 授权原文与边界

用户答复原文：

> 「A. 授权测试侧适配 + 提交推送（推荐。适配 config_digest 与运行器身份驱动，跑三项检查，然后 feat:/docs: 提交并推送；下轮冻结新清单并请你签收预算。）」

| 项 | 内容 |
|---|---|
| 被授权 | 测试侧适配（配置摘要覆盖新口径、运行器按清单身份驱动）、配套回归、`ruff` / `pytest` / `npm run build`、`feat:` 与 `docs:` 提交并推送 |
| 明确排除 | 任何阶段实跑；冻结新清单或新建输出目录；默认策略切换；改写既有外部清单与回执；前端源码与训练器改动；云端操作 |

## 2. 为什么需要这次适配（三个前置中的两个）

实施 M1 / M1b 后，`mixed-local@2` 的分布已与首版不同，但验证入口仍有两处会破坏证据完整性：

1. **配置摘要不覆盖新口径**：`config_digest()` 原先只摘要风格参数表、量化单位与手模式分区，`mixed-local@1` 与 `@2` 会算出**同一个**配置摘要——两套不同分布共用同一身份。
2. **运行器会把第二版静默按首版驱动**：计时、行为矩阵与对抗对照三处构造子策略时不传身份，而报告却写死首版标识。若直接跑第二版清单，会得到「报告标 `mixed-local@2`、实际按 `mixed-local@1` 决策」的静默错标——这是 `docs/53` §10.5 禁止的静默回退。

第三个前置（`code_identity` 需指向实现提交）由本轮提交解决，见 §7。

## 3. 文件级改动

| 文件 | 改动 |
|---|---|
| `backend/tests/mixed_bot_validation.py` | `config_digest(identifier=…)` 按身份出摘要；新增 `strategy_rules(manifest)`；`frozen_manifest(…, strategy_id=…)`；`time_decision(…, identifier=…)`；`collect_behavior` 与对抗对照按清单身份取口径；`_focus_mover` / `play_adversarial_hand` 显式接收口径；`run_adversarial_batch(…, identifier=…)`；`run_validation` 在任何计算之前校验身份，报告写入清单声明的身份 |
| `backend/tests/mixed_bot_states.py` | `build_frozen_manifest(…, strategy_id=…)`，缺省仍为首版标识 |
| `backend/tests/test_mixed_bot_benchmark.py` | `_manifest(…, strategy_id=…)`；新增 8 条身份驱动回归（§5） |

## 4. 兼容设计（关键：已签收证据不得改写）

`config_digest()` 采用**只增不改**的兼容口径：首版身份的载荷**不追加任何字段**，其余身份额外写入自身的规则口径。因此：

| 校验项 | 实测 |
|---|---|
| `config_digest()`（缺省，即首版） | `bfe231419ecc31e54e9b73aaa16421026cc2392a21516ddb44e6a629936d1484`，与外部冻结清单逐字一致 |
| 用已签收的 `code_identity` 与输出目录重算整份清单摘要 | `d36326555fe1ccba515b543e59e055a0c44d9537471f7b6eafee8aeb1eeff751`，与已签收摘要逐字一致 |
| `config_digest("mixed-local@2")` | `338a4863a68ca10eda44dcfdfdf26e510a4560cf8f7bbd1f97f048bc6ff6e794`（与首版不同） |

即：本次适配**在代码层面可复核地未动摇**已签收的首版清单与配置摘要。

未注册身份在所有入口都显式失败，不静默回退：`config_digest` / `strategy_rules` / `frozen_manifest` / `run_adversarial_batch` / `MixedLocalStrategy` / 两个派生函数。

## 5. 新增回归

| 测试 | 锁定的契约 |
|---|---|
| `test_first_version_config_digest_is_pinned` | 首版配置摘要被钉死在已签收取值上，任何改写立即失败 |
| `test_second_version_gets_its_own_config_digest` | 第二版配置摘要与首版不同 |
| `test_config_digest_refuses_an_unregistered_identity` | 未注册身份取摘要即失败 |
| `test_frozen_manifest_carries_the_requested_identity` | 清单身份随参数写入、摘要随之变化、节点集不变 |
| `test_frozen_manifest_refuses_an_unregistered_identity` | 未注册身份不得装配清单 |
| `test_strategy_rules_follow_the_manifest_identity` | 口径由清单身份决定，未注册身份失败 |
| `test_behavior_collection_follows_the_manifest_identity` | 行为矩阵确实按清单身份计算：第二版在共享牌面上的跟注质量高于首版 |
| `test_adversarial_batch_refuses_an_unregistered_identity` | 对抗对照在未注册身份下开跑前即失败 |

## 6. 本次常规检查实跑结果（2026-09-22）

| 命令 | 实际结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `910 passed, 3 skipped, 2 warnings in 13.74s` |
| `cd frontend && npm run build` | Vite 6.4.3；`24 modules transformed`；`built in 695ms`（同状态下另一次为 514ms） |

本轮基线为 `815 passed, 3 skipped`。加入 §11 的修复回归后，全量回归为 `911 passed, 3 skipped`（累计新增 96 条通过用例）。

## 7. 提交与 `code_identity`

- `feat:` 提交：`backend/app/**` 的 M1 + M1b 实现与全部回归（`test_mixed_shared_board.py`、`test_mixed_games.py`、`test_strategy_registry.py`、`test_mixed_bot_benchmark.py`、`mixed_bot_validation.py`、`mixed_bot_states.py`）。
- `docs:` 提交：`docs/54`、`docs/54a`、`docs/54b`。
- 第二版清单的 `code_identity` 应取该 `feat:` 提交的全哈希，与首版「取被测策略实现提交、不取测试侧提交」的口径一致。

## 8. 契约与兼容影响

| 对象 | 影响 |
|---|---|
| 公开 API | 零改动（本轮只动测试侧） |
| 新建默认策略 | 仍为 `heuristic@1` |
| 数据库 / `history_json` / 复盘参考 | 零改动 |
| 测试侧内部契约 | `config_digest` / `frozen_manifest` / `time_decision` / `run_adversarial_batch` 各新增**带默认值**的身份参数，缺省行为与首版一致；`_focus_mover` / `play_adversarial_hand` 的口径参数为必填（无默认，避免漏传） |
| 报告 schema | 未改字段；`strategy_id` 改为写入清单声明值 |
| `docs/37` §3.1 | **不触发** |

## 9. 未做事项与仍未证

- 未运行任何阶段实跑；未冻结新清单；未创建新输出目录。
- 未做 `mixed-local@2` 的收益/退化对照，也未做任何独立质量验证。
- §4 的摘要是配置身份校验，**不是**质量或强度读数。
- 仍未证：第二版的实际质量、抗针对程度、性能矩阵。

## 10. 不得声称

- 不得把本轮表述为已获质量签收、已授权默认切换或已产生任何运行证据。
- 不得把 `910 passed` 或摘要校验表述为对手质量证据。
- 不得把「运行器已支持第二版身份」表述为第二版已被评测。
- 不得据此修改 `docs/20` 至 `docs/54a`。

## 11. 实施后暴露的缺陷与修复（补算首次运行，2026-09-22）

本节记录的缺陷**由本次适配引入**，且**未被 §6 的三项常规检查发现**。如实记账如下。

**现象**：对第二版阶段 B 回执首次运行补算时立即中止，抛出 `TypeError: play_adversarial_hand() missing 1 required keyword-only argument: 'rules'`，**未写任何报告**（`stage-b-recheck/` 只留下一个空目录；补算入口在回放前中止，未产生部分报告）。

**根因**：§3 把对照回放的口径参数改成**必填**（刻意不给默认值，避免漏传静默沿用首版口径），但补算模块的同一个调用点未同步。

**为什么没被测试发现**：补算的对照回放只在显式 opt-in 时才执行；默认套件只覆盖补算的**拒绝分支**，从未走到回放循环。§5 新增的 8 条回归也没有一条真正驱动「阶段 A 回执 + 补算回放」这条链路。

**处置**：

1. 同步补算模块的调用点，并把口径由**回执与清单共同的策略身份**取出；
2. 顺带补上一条硬约束：**回执身份与清单身份不一致时拒绝补算**（原先没有这项检查，会出现「用 A 身份重算 B 身份回执」的错配）；
3. 新增一条真正走回放路径的回归：用单节点清单实际跑一次阶段 A 与补算，断言回放收到的口径就是回执身份对应的口径，并断言身份不一致时被拒。

**修复后**：补算一次通过（读数见 `docs/54c` §5.5）；全量回归为 `911 passed, 3 skipped, 2 warnings`。

**影响范围**：缺陷与修复均在测试侧，不触及被测策略实现，也不改变任何已落盘证据；第二版清单的 `code_identity` 指向策略实现提交，**无需重取**。

## 12. 唯一下一步

清单冻结与开发性对照已由用户另行授权并已完成（读数与边界见 `docs/54c`）。**建议下一步只裁定一件事：提交并推送本轮修复与回执**，随后 `docs/54` 的下一步回到 D2 / D3 的目标带裁定。
