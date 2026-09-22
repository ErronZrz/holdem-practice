# 54f M8：配置摘要按身份隔离（缺陷修复）实施与回归回执

> 日期：2026-09-22。
>
> 本文件是一次**测试侧**缺陷修复的实施回执，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/54e` 未被改写。
>
> 本文件记录已落地的代码与已实跑的常规检查。**不产生任何质量证据**：未运行任何验收或标定运行、未冻结新清单与新目录、未切换默认策略、未改动任何已落盘证据。

## 1. 授权原文与边界

用户答复原文：

> 「A.」

对应选项原文：

> 「A. 先修摘要隔离，再单独提 M2b 授权（推荐。…给非首版身份规定"只摘要该身份自身引入的口径字段"（`@2` → 仅 `shared_board_chop_caliber`，已实测可逐字恢复 `338a4863…`；`@3` → 四项，摘要 `5ed7992b…` 不变），并补一条钉住 `@2` 摘要的回归。修完 `@2` 恢复可复算、v3 不再继承同缺陷；本轮不涉任何实跑）」

| 项 | 内容 |
|---|---|
| 被授权 | 修复配置摘要的身份隔离；补针对性回归；运行 `ruff` / `pytest` / `npm run build` |
| 明确排除 | 任何标定或验收运行；新清单与新目录；M2b；M2 参数调整；默认切换；`commit` / `push`；改写 `docs/20` 至 `docs/54e` |

## 2. 缺陷描述与证据

### 2.1 发现方式（只读核算，不实跑）

在核验第三版身份常量时发现：当前代码取出的第二版配置摘要，与 v2 冻结清单及三份 v2 回执记录的取值不同。

| 取值来源 | `mixed-local@2` 配置摘要 |
|---|---|
| v2 冻结清单与三份 v2 回执记录 | `338a4863a68ca10eda44dcfdfdf26e510a4560cf8f7bbd1f97f048bc6ff6e794` |
| 修复前，当前代码 | `c75e1bcca26fcf52551e7f7eeeeeacdcda207415c3badeb286e33c251e28c620` |
| 修复前，把翻前三项从载荷剔除后再算 | `338a4863…e794`（逐字复现） |

### 2.2 成因

配置摘要对非首版身份写入的是**整份规则对象**。M2a 给共享的规则对象增加了三个翻前字段（翻前价格项权重、翻前每对手惩罚、翻前跟注偏移），第二版的规则对象也随之带上这三项（取值为首版默认 `450 / 35 / 0`），载荷键集变化，因而摘要变化。首版身份不受影响，因为它的载荷不含规则字段（由既有回归钉住）。

### 2.3 影响边界（逐项查证）

- **已落盘证据未被改写**：重载 v1 / v2 清单文件复算摘要，仍为 `d3632655…ff751` / `dd5ee966…e2f8`，与记录逐字相符。
- **第二版证据仍可确定性重放**：补算模块不重算配置摘要，只校验身份标识，并从回执原样带过摘要字段。
- **但摘要不再可从代码复算**：既有断言只要求"第二版与首版不同"，未钉住取值，因此该漂移未被任何回归发现。
- **第三版会继承同一脆弱性**：`mixed-local@3` 的摘要修复前后均为 `5ed7992b…643f`；若先冻结 v3 证据、日后又有新身份增加字段，v3 摘要将同样漂移。

### 2.4 对既有文档表述的更正（不改写旧文档）

`docs/54e` §8 表述为「旧身份 `mixed-local@1` / `@2` 的口径、**摘要**与全部已落盘证据零改动」。按本次查证：**就已落盘文件而言该表述成立**（文件与回执未被改写）；**就"用当前代码复算摘要"而言，该表述在修复前不成立**。`docs/54e` 按纪律未被改写，本文件即为该表述的更正记录。修复后，该表述在两种意义下都成立。

## 3. 文件级改动

| 文件 | 改动 |
|---|---|
| `backend/tests/mixed_bot_validation.py`（修改，+24/−3） | 新增"身份 → 参与摘要的规则字段"登记表；`config_digest` 改为只写入该身份登记过的字段；已注册但未登记字段的身份显式失败；新增 `MixedStrategyError` 与两个身份常量的导入 |
| `backend/tests/test_mixed_bot_benchmark.py`（修改，+63/−0） | 新增 5 条回归（§5） |

**未改动**：`backend/app/**`（含 `mixed_policy.py`、`mixed_strategy.py`、`registry.py`）、`backend/tests/mixed_bot_recheck.py`、`backend/tests/mixed_bot_states.py`、`backend/tests/test_mixed_preflop_caliber.py`、`backend/tests/test_mixed_shared_board.py`、`backend/tests/test_strategy_registry.py`、`frontend/**`、`tools/trainer/**`、`docs/20` 至 `docs/54e`、工作树外的冻结清单与全部回执。

## 4. 修复内容

- 登记表只列各身份**自身引入**的口径字段：第二版为分池口径一项；第三版为分池口径加翻前三项。
- 配置摘要对非首版身份只写入登记过的字段，因此后续身份新增字段不会改动旧身份的摘要。
- 首版身份的载荷仍不追加任何字段（逐字不变）。
- 未注册身份仍由取口径处失败；已注册但未登记字段的身份在取摘要处**显式失败**，不静默改用整份规则对象。

## 5. 新增回归

| 测试 | 锁定的契约 |
|---|---|
| `test_second_version_config_digest_is_pinned` | 第二版摘要逐字等于已签收取值 |
| `test_third_version_config_digest_is_pinned` | 第三版摘要被钉住，且与第二版不同 |
| `test_digest_fields_are_registered_per_identity` | 登记的字段属于已注册身份、且是该身份规则对象里的真实字段；首版不在登记表内；第二版只登记分池口径 |
| `test_extra_rule_fields_do_not_move_earlier_digests` | 模拟规则对象将来多出字段：已登记身份的摘要必须逐字不变 |
| `test_config_digest_refuses_an_identity_without_registered_fields` | 已注册身份漏登摘要字段时必须显式失败 |

未删除任何既有用例：`test_second_version_gets_its_own_config_digest` 等原有断言保持原样。

## 6. 本次常规检查实跑结果（2026-09-22）

| 命令 | 实际结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `997 passed, 3 skipped, 2 warnings in 14.67s` |
| `cd frontend && npm run build` | `24 modules transformed`；`built in 543ms` |

上一轮基线为 `992 passed, 3 skipped`（本轮新增 5 条）。

另做三项**只读核对**（非测试，不落盘）：

| 项 | 实测 |
|---|---|
| `config_digest("mixed-local@1")` | `bfe2314…d1484`，与已签收值逐字一致 |
| `config_digest("mixed-local@2")` | `338a4863…e794`，恢复为已签收值 |
| `config_digest("mixed-local@3")` | `5ed7992b…643f`，与修复前一致 |
| 用 v2 已签收的 `code_identity` 与输出目录重算整份 v2 清单 | `dd5ee966…e2f8`，与已签收摘要逐字一致 |
| 重载 v1 / v2 清单文件复算摘要 | `d3632655…ff751` / `dd5ee966…e2f8`，未被改写 |

## 7. 契约与兼容影响

| 对象 | 影响 |
|---|---|
| 公开 API 字段 | 零改动；`bot_strategy` 的可接受取值不变 |
| 数据库列 / `history_json` / 复盘参考 / artifact schema | 零改动 |
| 内部契约 | 配置摘要的非首版载荷语义收紧：由"整份规则对象"改为"该身份登记的字段"。首版取值不变；第二版取值恢复为已签收值；第三版取值不变 |
| 新建默认策略 | **仍为 `heuristic@1`** |
| `docs/37` §3.1 | **不触发**（参考实现、保守判据、`equity` 实现、采样数、固定种子五项零改动） |

## 8. 未做事项与仍未证

- 未运行任何标定或验收运行；M2b 未获授权、未启动。
- 未冻结第三版的清单与目录；M2-3 未做；M3 / D3 未裁定。
- 仍未证：第三版三档的聚合 VPIP、是否命中 `[0.12, 0.35]` 与两两 ≥0.05、PFR 与主动率分工、决策延迟与耗时。
- 第二版摘要恢复可复算，**不等于**第二版分布或质量获得任何新证据。

## 9. 不得声称

- 不得把本文件或 `997 passed` 表述为对手质量证据。
- 不得把"摘要可复算"表述为分布正确、达标或已获质量签收。
- 不得把本次修复表述为 M2 已达标。
- 不得据此改写 `docs/20` 至 `docs/54e` 与任何已落盘证据。

## 10. 唯一下一步

**建议先裁定一件事：提交并推送本次摘要隔离修复**（代码与回归一条 `fix:` 提交、本回执一条 `docs:` 提交）。

理由：M2b 清单的 `code_identity` 必须指向**运行时**的代码，而本轮已改动测试侧代码，`docs/54e` 之后原定的 `cbdf051…` 已不再代表运行时代码。要给出准确、可核验的 M2b 授权包（含 `code_identity` 与第三版 `config_digest`），需先落定提交。M2b 的授权在提交之后单独提出。
