# 54e M8：翻前门槛细化（M2a）实施与回归回执

> 日期：2026-09-22。
>
> 本文件是 `docs/54d` 的**实施回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/54d` 未被改写。
>
> 本文件记录已落地的代码与已实跑的常规检查。**不产生任何质量证据**：未运行任何验收或标定运行、未冻结新清单、未切换默认策略。

## 1. 授权原文与边界

用户答复原文：

> 「A. 授权实施 M2a（M2-3 暂不动）（推荐。回归含"非翻前节点逐位不变"；标定运行另轮授权。）」

| 项 | 内容 |
|---|---|
| 被授权 | 实施 M2-1（翻前价格项与人数惩罚口径）与 M2-2（仅作用于跟注分支的翻前风格偏移）；注册累积版 `mixed-local@3`；配套针对性回归；运行 `ruff` / `pytest` / `npm run build` |
| 明确排除 | 任何标定或验收运行；新清单与新目录；M2-3（连张倒置修正）；默认切换；`commit` / `push` |

## 2. 文件级改动

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/mixed_policy.py` | 新增 `PreflopCallBonus`；`MixedPolicyRules` 增加 `preflop_price_weight` / `preflop_contender_penalty` / `preflop_call_bonus` 三项（默认值为首版取值）；新增 `MIXED_LOCAL_V3_RULES`；`_score` 按街取人数惩罚；`build_distribution` 按街取价格权重、并让跟注偏移只作用于被动分支 |
| `backend/app/strategy/mixed_strategy.py` | 新增 `MIXED_STRATEGY_IDENTIFIER_V3` 与映射项 |
| `backend/app/strategy/registry.py` | 新增 `mixed-local@3` 注册项（累积版）；前两版条目不变 |
| `backend/app/strategy/__init__.py` | 导出新增符号 |
| `backend/tests/test_mixed_preflop_caliber.py`（**新增**，81 条） | M2 针对性回归（§5） |
| `backend/tests/test_mixed_shared_board.py` / `test_mixed_bot_benchmark.py` / `test_strategy_registry.py` | 「未注册版本」示例取 `mixed-local@3` 改为 `mixed-local@4`；身份并存断言改为只锁定前两版顺序（§6） |

**未改动**：`backend/app/poker/**`、`analysis/**`、`storage/**`、`api/schemas.py`、`heuristic.py`、翻后节点的任何口径、`frontend/**`、`tools/trainer/**`、`docs/20` 至 `docs/54d`、工作树外的冻结清单与全部回执。

## 3. 改动内容

### 3.1 M2-1 翻前价格项与人数惩罚口径

- 跟注阈值的价格项权重按街取值：翻前由 `preflop_price_weight` 决定（第三版取 150，首版/第二版仍为 450），翻后固定 450。
- 每多一名未弃牌对手的评分惩罚按街取值：翻前由 `preflop_contender_penalty` 决定（第三版取 30，前两版仍为 35），翻后固定 35。

### 3.2 M2-2 仅作用于跟注分支的翻前风格偏移

`preflop_call_bonus` 取 紧密 0 / 松凶 35 / 跟注 110。它只进入被动分支：`fold` 与 `call` 的权重按「评分 + 偏移」计算，而 `value_quality` 与 `non_value_quality` **仍按未偏移的评分**计算。因此该偏移只会把质量从弃牌移向跟注，不会凭空产生加注——这与「跟注型 PFR 应贴近 0」的既有语义一致，并由回归锁定（§5）。

### 3.3 未做

M2-3（连张/缺张加分倒置）按裁定暂不动：翻前基础分公式形态逐字未改。

## 4. 初始参数与来源（**未验证**）

初始参数来自 `docs/54d` §4 的只读算术筛查，目标方向为「三档都抬离 0.045–0.088 的量级，且彼此分开」：

| 参数 | 第三版取值 | 首版/第二版取值 |
|---|---|---|
| 翻前价格项权重 | 150 | 450 |
| 翻前每对手惩罚 | 30 | 35 |
| 翻前跟注偏移（紧/松/跟） | 0 / 35 / 110 | 0 / 0 / 0 |

筛查对第三版的估计落点为 `0.178 / 0.363 / 0.492`，但该模型**系统性高估 30–40%**（`docs/54d` §4）。**这些参数是否命中目标带尚未验证**，必须由授权运行实测确认。

## 5. 冻结节点上的实测读数（实施后只读核对，非验收）

翻前七个节点、各自首个适用人数上「自愿投入单位（跟注 + 主动动作）」的实测值：

| 节点 | 人数 | 紧密 二版 → 三版 | 松凶 二版 → 三版 | 跟注 二版 → 三版 |
|---|---|---|---|---|
| hu-blind-position | 2 | 660,905 → 919,328 | 790,108 → 831,350 | 883,287 → 945,732 |
| unopened-open | 2 | 271,552 → 493,259 | 630,551 → 931,014 | 673,627 → 1,000,000 |
| open-after-limp | 2 | 5,123 → 5,123（未变） | 21,134 → 21,134（未变） | 3,475 → 3,475（未变） |
| facing-first-raise | 2 | 498,237 → 838,681 | 696,399 → 826,774 | 797,191 → 944,799 |
| facing-reraise | 2 | 671,386 → 714,008 | 674,917 → 717,446 | 822,147 → 869,009 |
| short-stack-call | 3 | 1,000,000 → 1,000,000（未变） | 同左 | 同左 |
| incomplete-raise | 3 | 607,143 → 765,464 | 928,499 → 1,000,000 | 913,462 → 1,000,000 |

由这些读数得到三项**必须如实记账的边界**：

1. **「跟注型进池最松」不成立，且不应作为要求**：在可过牌的节点上，唯一自愿动作是主动投入，而被动的跟注型本就应当更少加注（`open-after-limp` 上 跟注 3,475 < 紧密 5,123 < 松凶 21,134）。这与 D2 的裁定一致——D2 只要求「三档两两相差 ≥0.05」，未规定排序。因此本批**不锁定三档的排序**，只锁定「三档可分辨」。
2. **部分节点饱和，不含风格信息**：`short-stack-call` 上三档都达到全量；`incomplete-raise` 上松凶与跟注型已饱和，仅紧密型仍有区分空间。这类节点对 VPIP 目标带没有贡献。
3. **两人可过牌节点上 M2 零效果**：`open-after-limp` 上三档两版完全一致——该节点既无跟注（偏移不适用），人数惩罚也为零（只有一名对手），因此三项改动都不生效。这说明 M2 的作用面集中在「面对下注」与「多人桌」。

**超额风险（如实披露）**：`unopened-open` 上跟注型已达到全量自愿投入；配合筛查的高估特性，第三版跟注型的**聚合 VPIP 有可能超过 0.35 上限**。首次标定运行若出现该情况，应下调跟注型的偏移（该值集中在 `MIXED_LOCAL_V3_RULES` 一处，便于调整）。

## 6. 新增与修改的回归

| 测试 | 锁定的契约 |
|---|---|
| `test_preflop_caliber_does_not_leak_postflop`（9 翻后类别 × 3 风格） | 翻后节点上第三版与第二版分布**逐位一致** |
| `test_second_version_preflop_is_unchanged`（7 翻前类别 × 3 风格） | 第二版的翻前分布仍与首版一致 |
| `test_preflop_bonus_moves_mass_only_to_the_passive_branch`（3 风格） | 跟注偏移只改变弃牌/跟注；主动候选与免费过牌逐项不变；偏移为零的风格必须逐项一致 |
| `test_third_version_never_reduces_preflop_entry`（7 类别 × 3 风格） | 第三版在任何翻前节点上都不得降低该风格的自愿投入 |
| `test_third_version_separates_the_styles`（3 个未饱和节点） | 三档自愿投入两两相差 ≥1% |
| `test_short_stack_node_saturates_every_style` / `test_incomplete_raise_node_saturates_two_styles` | **记录实测边界**（不是期望值），参数变动时必须重新审视 |
| `test_preflop_caliber_ignores_opponent_hole_cards` | 换掉未公开的对手底牌不改变翻前特征 |
| `test_old_identities_keep_the_original_preflop_caliber` | 前两版口径对象的翻前字段保持原值 |
| `test_third_identity_is_registered_and_cumulative` | 第三版已注册且继承第二版的分池口径 |
| `test_preflop_bonus_fields_match_the_style_values` | 偏移字段名与风格取值一一对应，取值为 0 / 35 / 110 且严格递增 |

既有断言的**就地更新**（如实披露）：三处把「未注册版本」示例由 `mixed-local@3` 改为 `mixed-local@4`（性质保留：未知版本必须被拒）；一处身份并存断言由「恰好两版」改为「前两版按序并存」，因为后续版本会继续追加。未删除任何用例。

## 7. 本次常规检查实跑结果（2026-09-22）

| 命令 | 实际结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `992 passed, 3 skipped, 2 warnings in 14.23s` |
| `cd frontend && npm run build` | Vite 6.4.3；`24 modules transformed`；`built in 564ms` |

本轮基线为 `911 passed, 3 skipped`（新增 81 条）。

## 8. 契约与兼容影响

| 对象 | 影响 |
|---|---|
| 公开 API | `bot_strategy` 的**可接受取值新增 `mixed-local@3`**（显式接口行为变化） |
| 新建默认策略 | **仍为 `heuristic@1`** |
| 数据库 / `history_json` / 复盘参考 | 零改动 |
| 内部契约 | `MixedPolicyRules` 增加三个字段（默认值为首版取值）；新增 `PreflopCallBonus`、`MIXED_LOCAL_V3_RULES`、`MIXED_STRATEGY_IDENTIFIER_V3` |
| 旧身份 | `mixed-local@1` / `@2` 的口径、摘要与全部已落盘证据零改动（由回归锁定） |
| `docs/37` §3.1 | **不触发**（参考实现、保守判据、`equity` 实现、采样数、固定种子五项零改动） |

## 9. 未做事项与仍未证

- 未运行任何标定或验收运行：§5 的读数是**冻结节点的只读核对**，不是对抗对照上的 VPIP，**不能**用来判断是否命中目标带。
- 未冻结第三版的清单与目录；M2-3 未做。
- 仍未证：第三版三档的聚合 VPIP、是否命中 `[0.12, 0.35]` 与两两 ≥0.05、PFR/主动率是否保持既有分工、决策延迟与耗时。

## 10. 不得声称

- 不得把本文件表述为 M2 已达标或已获质量签收。
- 不得把 §5 的节点读数表述为聚合 VPIP 或验收结果。
- 不得把 `992 passed` 表述为对手质量证据。
- 不得据此修改 `docs/20` 至 `docs/54d`。

## 11. 唯一下一步

**建议先裁定一件事：提交并推送本轮 M2a 实现与回归**（标定运行的授权在提交之后另行提出，届时你会看到实际参数取值与 §5 的边界读数）。提交后的下一步是 `docs/54d` §7 的 M2b 标定运行授权。
