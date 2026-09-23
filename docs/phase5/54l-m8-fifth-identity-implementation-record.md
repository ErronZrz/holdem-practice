# 54l M8：`mixed-local@5`（跟注型翻后被动偏移）实施与回归回执

> 日期：2026-09-22。
>
> 本文件是 `docs/54k` 的实施回执，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/54k` 未被改写。
>
> 本文件记录已落地的代码与已实跑的常规检查。**不产生任何质量证据**：未运行任何标定或验收运行、未冻结新清单、未切换默认策略。

## 1. 授权原文与边界

用户答复原文：

> 「A.」

对应选项原文：

> 「A. 授权实施 `@5`，跟注型取值 `+100`」

前置裁定（同轮）：**D3 = T1**（三对两两平均 JS 均 ≥ 0.15），口径为同一 4,224 手设计、同一四个主种子、同一清单排布下的 125 节点平均 JS。

| 项 | 内容 |
|---|---|
| 被授权 | 按 `docs/54k` §6.1 的建议取值实施 `@5`；注册累积版身份；配套针对性回归；运行 `ruff` / `pytest` / `npm run build` |
| 明确排除 | 任何标定或验收运行；新清单与新目录；工作树外写入；默认切换；`commit` / `push` |

## 2. 文件级改动

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/mixed_policy.py`（+29/−7） | 新增 `StyleCallBonus`（原 `PreflopCallBonus` 改名，旧名保留为同义名）；口径新增 `postflop_call_bonus` 字段；新增 `MIXED_LOCAL_V5_RULES`；被动评分按街取偏移；新增取翻后偏移的辅助函数 |
| `backend/app/strategy/mixed_strategy.py`（+5/−0） | 新增 `MIXED_STRATEGY_IDENTIFIER_V5`；加入身份元组与身份到口径的映射 |
| `backend/app/strategy/registry.py`（+13/−0） | 注册 `mixed-local@5` 累积版条目；前四个条目逐字不变 |
| `backend/app/strategy/__init__.py`（+6/−0） | 导出新增符号 |
| `backend/tests/mixed_bot_validation.py`（+8/−0） | 摘要登记表新增第五版字段集（含新字段）；导入新身份常量 |
| `backend/tests/test_mixed_style_separation.py`（**新增**，49 条） | 本次针对性回归（§4） |
| `backend/tests/test_mixed_bot_benchmark.py`（+16/−4） | 新增 1 条摘要钉住；「未注册版本」示例由 `mixed-local@5` 改为 `mixed-local@6`（4 处） |
| `backend/tests/test_mixed_shared_board.py`（+5/−5） | 「未注册版本」示例由 `mixed-local@5` 改为 `mixed-local@6`（5 处） |
| `backend/tests/test_strategy_registry.py`（+2/−2） | 同上（2 处） |
| `docs/54k-m8-style-separation-spec.md`（**新增**） | 本轮的规格草案（含 D3 裁定与选参扫描），与实现一并落盘 |

**未改动**：`backend/app/poker/**`、`analysis/**`、`storage/**`、`api/**`、`heuristic.py`、`mixed_features.py`、`mixed_context.py`、`projection.py`、`lookup_budget.py`、`backend/tests/mixed_bot_recheck.py`、`backend/tests/mixed_bot_states.py`、`backend/tests/test_mixed_preflop_caliber.py`、`backend/tests/test_mixed_tight_bonus.py`、`frontend/**`、`tools/trainer/**`、`docs/20` 至 `docs/54j`、工作树外的冻结清单与全部回执。

## 3. 改动内容

`@5` 是**累积版**：翻前取值与 `@4` 逐字一致，唯一差别是新增的**翻后被动跟注偏移**，且只发给跟注型（松散：紧密 0 / 松凶 0 / 跟注 **100**）。

- 该偏移**只进入被动分支**：弃牌与跟注的权重按「评分 + 偏移」计算，价值与非价值主动候选仍按未偏移的评分计算，因此不凭空产生加注。
- 该偏移**只作用于翻后**：翻前一分不动，`docs/54j` 已实测达标的目标带不受影响（由回归锁定）。
- 派生实现：被动评分按街取偏移（翻前取 `preflop_call_bonus`、翻后取 `postflop_call_bonus`），两条街各自独立。

**主动候选的份额效应（如实记账）**：被动质量变大后，归一化分母随之变大，因此主动候选的**单位数**会略微下降。这不是机制改动（主动候选的集合与量化前的相对比例由未偏移的评分决定，完全不受偏移影响），而是同一个分布内份额此消彼长的结果。这一点与 `@3` 的翻前偏移同源。

## 4. 新增与修改的回归

| 测试 | 锁定的契约 |
|---|---|
| `test_fifth_version_postflop_bonus_value_is_recorded` | 第五版偏移取值为 `0 / 0 / 100` |
| `test_fifth_version_only_adds_the_postflop_bonus` | 第五版与第四版只相差这一个字段取值（用替换构造判等） |
| `test_first_four_identities_keep_their_calibers` | 前四个身份的口径取值保持不变 |
| `test_fifth_identity_is_registered_and_cumulative` | 第五版已注册、可构造、继承分池口径 |
| `test_preflop_is_identical_between_fourth_and_fifth`（7 翻前类别 × 3 风格） | 翻前节点上第四版与第五版分布**逐位一致** |
| `test_postflop_bonus_leaves_other_styles_unchanged`（9 翻后类别 × 紧密/松凶） | 偏移只发给跟注型，另两档翻后也逐位一致 |
| `test_postflop_bonus_moves_mass_only_to_the_passive_branch` | 跟注型：跟注变多、弃牌变少 |
| `test_postflop_bonus_keeps_the_active_candidate_set` | 偏移不生成也不删除主动候选；只锁定候选集合与主动份额不上升 |
| `test_postflop_bonus_does_not_touch_the_check_weight` | 没有跟注分支的节点上分布逐项不变 |
| `test_fifth_version_meets_the_separation_target` | 冻结节点回放：三对平均距离均不低于 `0.15` |
| `test_fifth_version_lifts_the_weakest_pair` | 最弱一对被抬到与另两对同量级 |
| `test_identical_node_count_is_recorded` | **记录实测边界**（不是期望值）：最弱一对上仍有 30 个节点分布逐位相同 |
| `test_fifth_version_config_digest_is_pinned` | 第五版配置摘要被钉死 |

既有断言的**就地更新**（如实披露）：三个测试文件里把"未注册版本"示例由 `mixed-local@5` 改为 `mixed-local@6`（共 11 处，性质保留：未知版本必须被拒）。未删除任何用例。

## 5. 冻结节点上的实测读数（实施后只读核对，非验收）

### 5.1 风格间平均距离（125 节点口径，与运行报告同源）

| 风格对 | `@4` | `@5` |
|---|---|---|
| 紧密–松凶 | 0.2136 | 0.2136（按构造不变） |
| 紧密–跟注 | 0.2444 | 0.3132 |
| **松凶–跟注** | **0.1102** | **0.1765** |
| 最小对 | 0.1102（不满足 T1） | **0.1765（满足 T1）** |
| 逐位相同的节点数（松凶–跟注） | 31 | 30 |

### 5.2 跟注型的被动分支变化（各翻后类别首个适用人数）

| 类别 | 人数 | 弃牌 四版 → 五版 | 跟注 四版 → 五版 |
|---|---|---|---|
| overpair-on-high-board | 2 | 179,217 → **2,926** | 820,783 → **997,074** |
| shared-board | 2 | 209,711 → **23,973** | 790,289 → **976,027** |
| flop-draw | 2 | 970,124 → **546,000** | 0 → **430,000** |
| top-pair-weak-kicker | 2 | 0 → 0 | 897,683 → 917,574 |
| turn-combo-draw | 2 | 0 → 0 | 840,553 → 863,190 |
| sizes-merged | 2 | 0 → 0 | 966,667 → 973,913 |
| free-check | 2 | 0 → 0（无跟注分支，逐项未变） | 0 → 0 |

**这些是冻结节点上的读数**：§5.1 与运行报告的口径同源（同一 125 节点与手模式权重），因此**预期标定运行会复现它**；但在获得授权的运行读数之前，**不得表述为已达标**。

## 6. 本次常规检查实跑结果（2026-09-22）

| 命令 | 实际结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `1111 passed, 3 skipped, 2 warnings in 15.56s` |
| `cd frontend && npm run build` | `24 modules transformed`；`built in 543ms` |

上一轮基线为 `1061 passed, 3 skipped`（本轮新增 50 条）。

另做的只读核对（非测试）：`config_digest` 逐身份取值为 `bfe2314…d1484`（首版）、`338a4863…e794`（第二版）、`5ed7992b…643f`（第三版）、`52b03d5d…b481d`（第四版）——四者与已落盘记录**逐字一致**；第五版为 `8896013b…82f2`。

## 7. 契约与兼容影响

| 对象 | 影响 |
|---|---|
| 公开 API | `bot_strategy` 的**可接受取值新增 `mixed-local@5`**（显式接口行为变化）；字段名与结构零改动 |
| 数据库 / `history_json` / 复盘参考 / artifact schema | 零改动 |
| 内部契约 | 新增 `MIXED_LOCAL_V5_RULES`、`MIXED_STRATEGY_IDENTIFIER_V5`、`StyleCallBonus`（`PreflopCallBonus` 保留为同义名，既有引用不受影响）；`MixedPolicyRules` 新增 `postflop_call_bonus` 字段，默认零偏移 |
| 新建默认策略 | **仍为 `heuristic@1`** |
| 旧身份 | `mixed-local@1`–`@4` 的口径、摘要与全部已落盘证据零改动（由回归与摘要登记表共同锁定） |
| `docs/37` §3.1 | **不触发**（参考实现、保守判据、`equity` 实现、采样数、固定种子五项零改动） |

## 8. 未做事项与仍未证

- 未运行任何标定或验收运行：§5 的读数是**冻结节点回放**，不是授权运行的回执。
- 未冻结第五版的清单与目录；M2-3 未做；抗针对与剥削性检验仍未做。
- 仍未证：`@5` 在对抗对照上的三档 VPIP（目标带是否不回落）、三对 JS 是否与冻结节点读数一致、PFR 与主动率分工、决策延迟与耗时。
- 跟注型动作熵在冻结节点上由 `0.376` 降到 `0.303`：这是**副作用**，按 `docs/53` §13.2 不得表述为改进目标。
- `docs/53c` 的质量签收结论未被本轮回执覆盖。

## 9. 不得声称

- 不得把本文件或 `1111 passed` 表述为对手质量证据或验收结果。
- 不得把 §5 的冻结节点读数表述为已达标、已获质量签收或运行读数。
- 不得把动作熵下降表述为改进目标。
- 不得据此修改 `docs/20` 至 `docs/54k` 与任何已落盘证据。

## 10. 唯一下一步

**建议先裁定一件事：提交并推送本轮实现与回归**（代码与回归一条 `feat:` 提交、规格与本回执一条 `docs:` 提交）。标定运行的授权在提交之后单独提出，届时会以新的提交全哈希作为 `code_identity`，并以 **T1** 与 `@4` 已达标的目标带（三档 VPIP 与两两差）同时作为判定口径。
