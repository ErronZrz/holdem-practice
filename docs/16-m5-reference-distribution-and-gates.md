# 16 M5 复盘参考动作：概率分布 + 两处判据门槛

> 本文档记录在 `15-review-open-items.md` 之后，针对其 §2 待办与 §3 两处疑点所做的一轮修复，作为 `15` 之后的实现快照。
>
> **文档权威性**：遵循 `03-execution-plan.md` 第 8 节约定，本文档是 `15` 之后的「实现快照」，与其冲突时以本文档为准。`13-m5-conservative-reference.md` 的跟注侧保守口径**未回退**，本文档在其之上叠加。

---

## 1. 背景与目标

`15` 记录了逐手核对暴露的三个问题：

1. **参考动作带随机性**：唯一随机分支（无人下注的纯空气诈唬）在固定 seed 下表现为一枚硬币的落地结果，同一局面永远给出同一个「随机」动作，不具可解释性；
2. **翻牌前 `bad_call` 对 limp 误报**：跟注额恰好一个大盲的廉价看牌被判 `error`；
3. **价值下注侧缺牌力质量门槛**：顶对弱踢脚在河牌被参考为满池价值下注，真人过牌被标 `value_missed`。

本轮目标：保留随机诈唬，但把参考动作升级为**动作概率分布**；同时为「翻牌前跟注」与「价值下注」补上与跟注侧对称的门槛。仍然**不做**对手范围建模、不引 CFR、不做反事实动作树。

---

## 2. 改动总览

| 层 | 文件 | 改动 |
|---|---|---|
| 策略 | `app/strategy/heuristic.py` | 新增 `action_distribution`（唯一事实源）；`choose_action` 改为从分布采样；原 `_postflop_action` 改为 `_postflop_distribution` |
| 分析 | `app/analysis/hand_review.py` | 新增 `_weak_kicker_top_pair` / `_shift_mass` / `_conservative_distribution` / `_mode_action`，替换原 `_conservative_action`；`_detect_mistakes` 增加 `big_blind` 参数与翻前 limp 豁免；`value_missed` 复用弱踢脚门槛；`_analyze_decision` 输出 `bot_distribution` |
| 接口 | `app/api/schemas.py` | 新增 `ActionProbability`；`DecisionReview` 增加 `bot_distribution`（默认空列表，向后兼容） |
| 工具 | `tools/inspect_hand.py` | 探针改挂 `_conservative_distribution`，打印启发式基线分布 / 参考分布 / 弱踢脚判定 |
| 前端 | `src/cards.js`、`GameTable.vue`、`HistoryView.vue` | 新增 `distributionText`，非退化分布时展示「参考分布」一行 |
| 测试 | `tests/test_review.py`、`tests/test_strategy.py`、`tests/test_games_api.py` | 新增分布 / 门槛 / limp 用例，`_detect_mistakes` 调用同步 `big_blind` |

`reference_strategy` **保持 `"heuristic-conservative"`**：分布字段已自描述，改名只会扩大断言与文案的改动面。

---

## 3. 参考动作改为概率分布

### 3.1 唯一事实源：`HeuristicStrategy.action_distribution`

分布**由策略层计算**，分析层不再重复实现分支判据（沿用 `11 §3.1` 的「复用规则、杜绝漂移」原则）：

```text
action_distribution(state, legal) -> [(Action, weight), ...]   # 权重之和约为 1
```

- 确定性分支只含一个动作，权重 `1.0`（翻牌前分档、面对下注的阈值分支、价值下注、半诈唬）；
- **仅「无人下注 + 胜率 < 0.25」的空气诈唬支是混合分布**：`[(bet, bluff_freq), (check, 1 - bluff_freq)]`；
- `choose_action` 改为从该分布采样，`len(distribution) == 1` 时直接返回、不消耗随机数。

**实盘 Bot 行为不变**：生产默认 `bluff_freq = 0.10`，混合分支仍恰好消耗一次 `random()`，且下注先于过牌排列，`roll < p` 的映射与原实现一致；`equity()` 的采样消耗顺序也未变。只有测试用的 `bluff_freq ∈ {0, 1}` 会退化为确定性分布（少一次无用的随机数消耗）。

### 3.2 参考动作取众数 + 新增分布字段

`DecisionReview.bot_action` 语义由「采样结果」改为「收窄后分布的**众数**」，另加 `bot_distribution`：

| 字段 | 含义 |
|---|---|
| `bot_action` | 概率最高的动作（并列取列表靠前者），前端「参考：」仍显示它 |
| `bot_distribution` | `[{action, amount, probability}]`，按概率降序，权重之和为 1 |

效果：`7a88f7…` 河牌（2 人、`equity 0.1710`）的参考动作由 `bet 150` 变为 `check`，分布显示「下注 10% / 过牌 90%」，随机诈唬被保留但不再冒充确定建议。

### 3.3 保守收窄 = 概率质量再分配

`_conservative_distribution` 在基线分布上做转移，不再「改判动作」：

| 场景 | 转移 |
|---|---|
| 翻牌后面对下注，赔率无余量或无可继续牌力 | 跟注质量 → 弃牌（`_shift_mass`） |
| 翻牌后无人下注，弱踢脚顶对（§4） | 下注质量 → 过牌 |
| 翻牌前、加注、弃牌等 | 原样沿用基线 |

确定性基线（权重 1.0）下该操作与旧的「改判动作」完全等价，因此 `13` 的跟注侧保守口径不受影响。

---

## 4. 弱踢脚顶对门槛（价值下注侧）

### 4.1 定义

`_weak_kicker_top_pair(hole_cards, board)` 为真，当且仅当：

1. 最强牌力恰为**一对**；
2. 该对由**底牌**配中公共牌最高点数（排除「仅靠公共牌成对」）；
3. 另一张底牌（踢脚）**低于公共牌去重后第二高的点数**。

| 例子 | 判定 |
|---|---|
| `A6` 在 `Q T A 2 8` 上 | 弱（`6 < Q`） |
| `AK` 在 `Q T A` 上 | 不弱（`K > Q`） |
| 超对、两对、三条、仅公共牌成对 | 不适用 |

### 4.2 作用点与街道范围

- 参考动作：无人下注的价值下注质量转移到**过牌**；
- `value_missed`：命中条件追加 `not _weak_kicker_top_pair(...)`，与参考动作**共用同一门槛**，保证二者自洽。

门槛**对所有翻牌后街道生效**（翻牌/转牌/河牌），而非只限转/河。同一批手牌复核显示翻牌、转牌的 `value_missed` 未因此减少，故未收窄街道范围（见 §7）。

**已知取舍**：门槛不看听牌，因此「弱踢脚顶对 + 组合听牌」的半诈唬下注也会被收成过牌；该情形在本地库未出现，留待后续按需加听牌例外。

---

## 5. 翻牌前 limp 豁免

`_detect_mistakes` 新增 `big_blind` 参数（`_analyze_decision` 传 `engine.big_blind`），`bad_call` 判据追加：

```text
not (翻牌前 且 跟注额 <= 一个大盲)
```

即**补齐盲注 / limp 属廉价看牌，不判跟注赔率不足**；超过一个大盲的翻前跟注仍按赔率判定，翻牌后不受影响。

- 该豁免只作用于 `bad_call`（error），不改变 `bad_fold`；
- 已知取舍：`0aac1a…` 翻前 `A6o` limp 不再报错，但启发式投机档仍给出「参考：弃牌」，复盘会出现「你：跟注 / 参考：弃牌 / 无错误标记」。参考偏紧但规则自洽，本轮只修检测、不重开翻牌前参考口径。

---

## 6. 与 `13` / `15` 的偏差

| 点 | 旧表述 | 本轮落地 |
|---|---|---|
| 参考动作形态 | 单一确定动作 | 动作概率分布，`bot_action` 取众数 |
| 参考实现 | `_conservative_action` 改判动作 | `_conservative_distribution` 概率质量再分配 |
| 价值下注门槛 | 只看 vs 随机胜率阈值 | 追加弱踢脚顶对门槛，参考与 `value_missed` 共用 |
| `bad_call`（翻前） | `equity < pot_odds - 0.03` | 追加「跟注额 ≤ 一个大盲」豁免（`13 §6` 的遗留项） |
| 实盘 Bot | — | **未改变**（分布重构保持 RNG 消耗与动作映射一致） |

---

## 7. 效果（同一批本地手牌，180/184 可重放）

改动前后对**同一批**手牌逐决策点计数（`bad_call` 分街单列以确认改动面）：

| code | 改动前 | 改动后 |
|---|---|---|
| `bad_call`（翻前） | 33 | 1 |
| `bad_call`（转） | 3 | 3 |
| `bad_call`（河） | 3 | 3 |
| `value_missed`（翻牌/转/河） | 1 / 2 / 1 | 1 / 2 / 0 |
| `slowplay` | 3 | 3 |
| `underbet` | 4 | 4 |
| **合计** | **50** | **17** |

- `bad_call` 的降幅**全部来自翻前**（33 → 1），转/河判据未受影响，说明豁免面被限定在 limp；
- `value_missed` 仅河牌那 1 处（`0aac1a…`）被抑制，翻牌/转牌未减少，支持「门槛全街生效」；
- 有 **53 个决策点**的参考动作现在带非退化分布（改动前均表现为单一采样结果）。

---

## 8. 遗留与后续

- **弱踢脚顶对不看听牌**：组合听牌 + 弱踢脚顶对也会被收成过牌（§4.2）。
- **翻前参考仍偏紧**：limp 不报错，但参考动作仍为弃牌（§5）。
- **参考 ≠ 实盘 Bot**：价值下注门槛只在复盘层，实盘启发式仍按 `0.70` 阈值下注（延续 `13` 的取舍）。
- **仍为「vs 随机」口径**：`bot_distribution` 的混合只覆盖策略里已有的随机分支，未做阈值软化；「50% / 40% / 10%」这类宽分布需先有对应的策略依据。
- **`underbet` 未同步**：弱踢脚顶对下小注仍可能命中 `underbet`（`info` 级），本轮未动。

---

## 9. 测试与验收

```text
$ uv run ruff check .        # All checks passed
$ uv run pytest -q           # 121 passed, 2 warnings
$ cd frontend && npm run build   # built successfully
```

- `test_strategy.py`：空气诈唬支的混合分布权重（`0.25 / 0.75`）、面对下注的确定性分布只含一个动作。
- `test_review.py`：参考分布权重和为 1 且 `bot_action` 为众数；翻前 limp 豁免（`to_call = big_blind` 不判、超过则判）与「豁免仅限翻前」；弱踢脚顶对判定（弱 / 强 / 两对 / 三条 / 超对 / 仅公共牌成对 / 翻牌）；`value_missed` 跳过弱踢脚；收窄只转移跟注质量；弱踢脚顶对价值下注转过牌、强踢脚保留；加注/弃牌原样沿用。
- `test_games_api.py`：每个决策点含合法参考分布，权重和为 1，`bot_action` 与分布众数一致。
- 2 条 warning 仍来自 `fastapi.testclient` 依赖（starlette/httpx 弃用提示），与本轮改动无关。

---

## 10. 关联

- `docs/13-m5-conservative-reference.md`：跟注侧保守口径（赔率余量 + 牌力门槛），本轮在其之上叠加。
- `docs/15-review-open-items.md`：本轮修复的待办与疑点来源。
- `backend/tools/inspect_hand.py`：逐手核对工具，已同步分布展示。
