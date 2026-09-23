# 54i M8：`mixed-local@4`（紧密型翻前偏移修订）实施与回归回执

> 日期：2026-09-22。
>
> 本文件是 `docs/54h` 的**实施回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/54h` 未被改写。
>
> 本文件记录已落地的代码与已实跑的常规检查。**不产生任何质量证据**：未运行任何标定或验收运行、未冻结新清单、未切换默认策略。

## 1. 授权原文与边界

用户答复原文：

> 「A. @4 只动紧密型的翻前跟注偏移。」

对应选项原文：

> 「A. 授权实施 `@4`（取值 30、注册累积版身份、配套针对性回归：偏移取值、只影响被动分支、非翻前节点逐位不变、前三个身份逐字不变；跑 `ruff` / `pytest` / `npm run build`；**不实跑标定**）」

| 项 | 内容 |
|---|---|
| 被授权 | 按 `docs/54h` 取值 30 实施 `@4`；注册累积版身份；配套针对性回归；运行 `ruff` / `pytest` / `npm run build` |
| 明确排除 | 任何标定或验收运行；新清单与新目录；工作树外写入；M2-3；M3 / D3；默认切换；`commit` / `push` |

## 2. 文件级改动

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/mixed_policy.py`（+7/−0） | 新增 `MIXED_LOCAL_V4_RULES`：只把紧密型的翻前跟注偏移由 0 改为 30，其余取值与第三版逐字一致 |
| `backend/app/strategy/mixed_strategy.py`（+5/−0） | 新增 `MIXED_STRATEGY_IDENTIFIER_V4`；加入身份元组与身份到口径的映射 |
| `backend/app/strategy/registry.py`（+13/−0） | 注册 `mixed-local@4` 累积版条目；前三个条目逐字不变 |
| `backend/app/strategy/__init__.py`（+4/−0） | 导出新增符号 |
| `backend/tests/mixed_bot_validation.py`（+7/−0） | 摘要登记表新增第四版的字段集；导入新身份常量 |
| `backend/tests/test_mixed_tight_bonus.py`（**新增**，62 条） | 本次针对性回归（§4） |
| `backend/tests/test_mixed_bot_benchmark.py`（+24/−4） | 新增 2 条摘要回归；「未注册版本」示例由 `mixed-local@4` 改为 `mixed-local@5`（4 处） |
| `backend/tests/test_mixed_preflop_caliber.py`（+2/−1） | 身份并存断言由"恰好三版"改为"前三版按序并存" |
| `backend/tests/test_mixed_shared_board.py`（+5/−5） | 「未注册版本」示例由 `mixed-local@4` 改为 `mixed-local@5`（5 处） |
| `backend/tests/test_strategy_registry.py`（+2/−2） | 同上（2 处） |
| `docs/54h-m8-fourth-identity-tight-bonus-spec.md`（**新增**） | 本轮的规格草案（与实现一并落盘） |

**未改动**：`backend/app/poker/**`、`analysis/**`、`storage/**`、`api/**`、`heuristic.py`、`mixed_features.py`、`mixed_context.py`、`projection.py`、`lookup_budget.py`、`backend/tests/mixed_bot_recheck.py`、`backend/tests/mixed_bot_states.py`、`frontend/**`、`tools/trainer/**`、`docs/20` 至 `docs/54g`、工作树外的冻结清单与全部回执。

## 3. 改动内容

`@4` 是**累积版**：含首版 + 分池口径 + 翻前门槛细化，唯一差别是紧密型的翻前跟注偏移由 `0` 改为 `30`。前三个身份的规则对象取值逐字不变。

该偏移仍**只进入被动分支**（弃牌与跟注按"评分 + 偏移"计算，价值与非价值主动候选仍按未偏移的评分计算），因此不会凭空产生加注。

**M2-3（连张/缺张加分倒置）按既有裁定仍不动**：翻前基础分公式形态逐字未改。

## 4. 新增与修改的回归

| 测试 | 锁定的契约 |
|---|---|
| `test_fourth_version_bonus_value_is_recorded` | 第四版偏移取值为 `30 / 35 / 110` |
| `test_fourth_version_only_changes_the_tight_bonus` | 第四版与第三版只相差紧密型这一个取值（用替换构造判等） |
| `test_first_three_identities_keep_their_preflop_values` | 前三个身份的口径取值保持不变 |
| `test_fourth_identity_is_registered_and_cumulative` | 第四版已注册、可构造、继承分池口径 |
| `test_postflop_is_identical_between_third_and_fourth`（9 翻后类别 × 3 风格） | 翻后节点上第四版与第三版分布**逐位一致** |
| `test_tight_bonus_moves_mass_only_to_the_passive_branch`（3 风格） | 偏移只改变弃牌/跟注；主动候选与免费过牌逐项不变；偏移未变的风格必须整份一致 |
| `test_fourth_version_never_reduces_preflop_entry`（7 类别 × 3 风格） | 第四版在任何翻前节点上都不得降低该风格的自愿投入 |
| `test_fourth_version_raises_tight_entry`（5 个未饱和且含跟注分支的类别） | 紧密型的自愿投入必须真的提高 |
| `test_passive_free_node_is_unaffected_by_the_tight_bonus` | **记录实测边界**（不是期望值）：两人可过牌节点没有跟注分支，偏移不生效 |
| `test_tight_bonus_ignores_opponent_hole_cards` | 换掉未公开的对手底牌不改变紧密型的翻前分布 |
| `test_fourth_version_config_digest_is_pinned` | 第四版配置摘要被钉死 |
| `test_every_non_first_identity_has_registered_digest_fields` | 新注册身份若漏登摘要字段，必须在测试阶段失败，而不是等到运行期 |

既有断言的**就地更新**（如实披露）：三个测试文件里把"未注册版本"示例由 `mixed-local@4` 改为 `mixed-local@5`（共 11 处，性质保留：未知版本必须被拒）；一处身份并存断言由"恰好三版"改为"前三版按序并存"，因为后续版本会继续追加。未删除任何用例。

## 5. 冻结节点上的实测读数（实施后只读核对，非验收）

七个翻前节点、各自首个适用人数上"自愿投入单位（跟注 + 主动动作）"的实测值：

| 节点 | 人数 | 紧密 三版 → 四版 | 松凶 | 跟注 |
|---|---|---|---|---|
| hu-blind-position | 2 | 919,328 → 925,581 | 831,350（未变） | 945,732（未变） |
| unopened-open | 2 | 493,259 → 593,256 | 931,014（未变） | 1,000,000（饱和，未变） |
| open-after-limp | 2 | 5,123 → 5,123（未变） | 21,134（未变） | 3,475（未变） |
| facing-first-raise | 2 | 838,681 → 926,891 | 826,774（未变） | 944,799（未变） |
| facing-reraise | 2 | 714,008 → 724,719 | 717,446（未变） | 869,009（未变） |
| short-stack-call | 3 | 1,000,000（饱和，未变） | 1,000,000（饱和） | 1,000,000（饱和） |
| incomplete-raise | 3 | 765,464 → 886,729 | 1,000,000（饱和） | 1,000,000（饱和） |

由这些读数得到三项**必须如实记账的边界**：

1. **松凶与跟注型逐位不变**：本次修订只落在紧密型上。
2. **两人可过牌节点上零效果**：`open-after-limp` 上紧密型未变——该节点唯一自愿动作是主动投入，没有跟注分支，偏移无从生效。
3. **饱和节点不提供区分空间**：`short-stack-call` 上三档都是全量；`incomplete-raise` 上松凶与跟注型仍饱和，只有紧密型仍有空间。

**这些是冻结节点上的读数，不是聚合 VPIP，也不能用来判断是否命中目标带。** 目标带（`docs/54d` §2）只能由授权标定运行给出。

## 6. 本次常规检查实跑结果（2026-09-22）

| 命令 | 实际结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `1061 passed, 3 skipped, 2 warnings in 15.19s` |
| `cd frontend && npm run build` | `24 modules transformed`；`built in 517ms` |

上一轮基线为 `997 passed, 3 skipped`（本轮新增 64 条）。

另做的只读核对（非测试）：`config_digest` 逐身份取值为 `bfe2314…d1484`（首版）、`338a4863…e794`（第二版）、`5ed7992b…643f`（第三版）——三者与已落盘记录**逐字一致**；第四版为 `52b03d5d…b481d`（与三者都不同）。

## 7. 契约与兼容影响

| 对象 | 影响 |
|---|---|
| 公开 API | `bot_strategy` 的**可接受取值新增 `mixed-local@4`**（显式接口行为变化）；字段名与结构零改动 |
| 数据库 / `history_json` / 复盘参考 / artifact schema | 零改动 |
| 内部契约 | 新增 `MIXED_LOCAL_V4_RULES`、`MIXED_STRATEGY_IDENTIFIER_V4`；`MixedPolicyRules` 的字段集与形态不变 |
| 新建默认策略 | **仍为 `heuristic@1`** |
| 旧身份 | `mixed-local@1` / `@2` / `@3` 的口径、摘要与全部已落盘证据零改动（由回归锁定） |
| `docs/37` §3.1 | **不触发**（参考实现、保守判据、`equity` 实现、采样数、固定种子五项零改动） |

## 8. 未做事项与仍未证

- 未运行任何标定或验收运行：§5 的读数是**冻结节点的只读核对**，不是对抗对照上的 VPIP。
- 未冻结第四版的清单与目录；M2-3 未做；M3 / D3 未裁定。
- 仍未证：第四版三档的聚合 VPIP、是否命中目标带（紧密型需落在 `[0.1200, 0.1872]`）、PFR 与主动率分工、决策延迟与耗时。
- `docs/54h` §3 / §4 的只读估算是**估计**，不是读数；第四版的实际落点完全未测。

## 9. 不得声称

- 不得把本文件或 `1061 passed` 表述为对手质量证据或验收结果。
- 不得把 §5 的节点读数表述为聚合 VPIP、达标或已获质量签收。
- 不得把取值 30 表述为"已验证"或"最优"。
- 不得据此修改 `docs/20` 至 `docs/54h` 与任何已落盘证据。

## 10. 唯一下一步

**建议先裁定一件事：提交并推送本轮实现与回归**（代码与回归一条 `feat:` 提交、规格与本回执一条 `docs:` 提交）。标定运行的授权在提交之后单独提出，届时会以新的提交全哈希作为 `code_identity`。
