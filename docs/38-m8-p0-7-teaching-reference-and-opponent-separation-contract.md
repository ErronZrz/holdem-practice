# 38 M8：生产接入前置——P0-7 教学参考与对手目标的分离契约（规格冻结）

> 日期：2026-09-18。
>
> 本文件接在 `docs/37` / `docs/37a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/38` 记录本轮**规格与决策冻结**，`docs/38a` 记录**实施与验证回执**。`docs/20` 至 `docs/37a` 未被改写。
>
> 本文**不实施任何代码**。本轮范围仅限 `docs/35` §4.2 的 **P0-7（教学参考与对手目标的分离契约）** 一项；`docs/35` §4 生产接入前置清单中的其余条目（P0-1/P0-4/P0-5 已在前两轮完成，P0-2/P0-3/P0-6 与 P1/P2 组）**未被本轮授权**。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 授权与裁定

### 1.1 用户答复原文（逐项照录）

| 编号 | 问题 | 用户答复原文 |
|---|---|---|
| 执行确认 | 本轮是否只执行 `docs/35` §4.2 的 P0-7 | 「确认执行 P0-7(按提示词的四项产出实施，先冻结 docs/38 规格、再提交实现)」 |
| 岔路一+二 | 适用域/局限的声明形式与「非 GTO」标注落点 | 「加响应字段 + API/UI 一致落位（推荐）(新增 reference_scope / reference_limitations 并与 reference_identity() 同源导出；API 响应与两处 UI 文案都用同一批字段，措辞明确「启发式-保守近似，非 GTO、非均衡解」)」 |
| 岔路三 | 是否为「将来参考换为 CFR」预留契约 | 「只写文档 + 守卫测试（推荐）(用守卫测试锁定「分析层不得另抄一套与策略重复的分支判据」，不引入插件接口，不触碰 strategy/)」 |
| 岔路四 | 「旧保守保护单独评审适用性」的落地方式 | 「清单 + 回归锁定，不改判据（推荐）(逐条列出保护判据及适用域，用测试锁定其不被本轮改动)」 |

**被授权**：按 P0-7 的四项产出实施（参考契约、UI 如实标注、保护判据清单与回归锁定、非众数不判错回归）；改动面为 `backend/app/analysis/`、`backend/app/api/`、`frontend/`（最小必要）、`backend/tests/`，以及**新增** `docs/38` / `docs/38a`；规格与实现分两次提交。

**未被授权（继续有效）**：改质量判定门槛；放宽或删除任何既有教学保护判据；改 `poker/**` 结算与 `equity` 语义；改 `strategy/heuristic.py` 参考实现（`docs/35a` D4 = A 继续有效）；改 `storage/models.py`（不加列、不迁移）；新增受监督运行或 campaign；追加 seed；重试已消耗 authorization；上云、转 GPU、扩预算；恢复已移除的前端策略选择器；引入 `strategy/` 层的 reference 插件接口。

### 1.2 本轮裁定汇总

| 岔路 | 本轮裁定（已被采纳） | 依据 |
|---|---|---|
| 一、适用域/局限声明形式 | **新增响应字段** `reference_scope`（适用域）与 `reference_limitations`（局限），由 `reference_identity()` **同源派生**的 `reference_declaration()` 提供 | `docs/35` §4.2 P0-7「参考契约：版本、适用域、覆盖范围、来源标注」；验收要求「适用域可追溯」——只靠文档无法在 API 层证明可追溯 |
| 二、非 GTO 标注落点 | **API 响应与两处 UI 文案一致落位**；措辞纪律见 §3.3 | `docs/20` §5.2「UI 应如实标注…不仅改成『GTO』标签」；`docs/20` §11.2 |
| 三、CFR 预留 | **只写文档 + 守卫测试**，不引入插件接口，不触碰 `strategy/` | `docs/20` §5.1「唯一事实源是防止重复判据」；`docs/35` §4.2 P0-7「不得在分析层另抄一套判据」 |
| 四、保护判据落地 | **清单 + 回归锁定，不改判据** | `docs/20` §5.2「现有弱踢脚、被压制对子、limp 豁免、听牌余量等回归保留」；`docs/35` §4.2 P0-7「旧保守保护保留并单独评审适用性」 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 4]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -4 --oneline
89a5a15 feat: declare review reference and evaluation versions with a cache-key contract
f325148 docs: freeze p0-5 reference and evaluation versioning specs
bcb6743 feat: add controlled strategy registry and p0-4 information boundary projection
ccf208e docs: freeze p0-1 strategy identity and p0-4 information boundary specs

$ git rev-parse HEAD          -> 89a5a158cc3dfc79e480fe9ef93f68aac586f76c
$ git rev-parse origin/master -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
```

与期望基线完全相符（工作区 0 行、`HEAD` 短哈希 `89a5a15`、`ahead 4` 属未 push 的正常形态、campaign 目录 8 个）；未做任何 `reset` / `clean` / `stash` / `checkout` / `push`。

与本轮直接相关的只读事实核对：

```text
backend/app/analysis/reference_identity.py     REFERENCE_STRATEGY / REFERENCE_VERSION / EVALUATION_VERSION
                                               / REFERENCE_COVERAGE / CACHE_KEY_VERSION + reference_identity()
backend/app/analysis/hand_review.py:436        "**reference_identity()" 展开，已无硬编码字面量
backend/app/analysis/hand_review.py:232-324    _detect_mistakes(...)：签名不含任何分布/众数参数
backend/app/analysis/hand_review.py:327-384    _analyze_decision：bot_distribution 与 mistakes 分列产出
backend/app/api/schemas.py:211-226             HandReview：已含四个参考身份字段，无适用域/局限字段
backend/app/api/hands.py:60-79                 get_review 按字段透传
frontend/src/reviewText.js                     referenceText(review) 仅渲染来源/版本/覆盖
frontend/src/components/HistoryView.vue:219    复用 referenceText
frontend/src/components/GameTable.vue:747      复用 referenceText
```

`GTO` / `均衡` / `最优` 字样在当前后端 `app/` 与前端 `src/` 中**零命中**（现有基线已无 GTO 标签，本轮要做的是「不得引入」的可验证守卫）。

## 3. P0-7 规格（冻结）

### 3.1 参考契约的组成与同源关系

参考契约由**六个对外字段**组成，全部来自 `backend/app/analysis/reference_identity.py` 这唯一事实源：

| 字段 | 类别 | 取值来源 | 语义 |
|---|---|---|---|
| `reference_strategy` | 来源标注 | 既有常量（取值不变） | 参考实现标识，UI 据此映射中文名 |
| `reference_version` | 版本 | 既有常量 | 参考实现与保守判据的实现版本 |
| `evaluation_version` | 版本 | 既有常量 | 胜率估计、采样数、固定种子与错误判据的整体版本 |
| `reference_coverage` | 覆盖范围 | 既有常量 | 只做 vs 随机范围的静态近似 |
| `reference_scope` | **新增·适用域** | 新增常量 | 参考动作在哪些局面经过保守收窄、哪些局面沿用基线 |
| `reference_limitations` | **新增·局限** | 新增常量（字符串列表） | 模型假设与不可推断事项的如实声明 |

同源约束：

1. `reference_identity()` **保持现状**（仍返回上表前四项），既有断言与调用点不受影响；
2. 新增 `reference_declaration()`，实现为 `{**reference_identity(), "reference_scope": ..., "reference_limitations": [...]}`，即**在版本身份之上叠加**，不复制任何既有取值；
3. `build_review` 改为展开 `reference_declaration()`；API 层（`schemas.HandReview` / `hands.get_review`）只按字段透传，**不得另写常量**。

### 3.2 参考语义零改动与版本不升版的理由

本轮只新增**声明性字段**与**显示文案**，不触碰：

- `REFERENCE_STRATEGY` / `REFERENCE_VERSION` / `EVALUATION_VERSION` / `REFERENCE_COVERAGE` 的取值；
- `HeuristicStrategy` 的实现与分布；
- `_conservative_distribution` 与 `_detect_mistakes` 的任何判据、阈值或分支；
- `_EQUITY_SAMPLES`、`_REVIEW_SEED`。

因此按 `docs/37` §3.1 的升版规则（只对「参考实现、保守判据、`equity` 实现、采样数或固定种子」的改动生效），**本轮不升版本**，`reference_version` / `evaluation_version` 仍为 `1`。新增字段属契约扩张而非参考语义变化，`docs/38a` 必须逐条说明这一判断，并在测试中冻结四个既有常量的取值。

### 3.3 非 GTO 标注的落点与措辞纪律

落点（两处一致）：

1. **API 响应**：`reference_scope` 与 `reference_limitations` 随 `HandReview` 返回，限制项为**明文否定式声明**；
2. **UI 文案**：`frontend/src/reviewText.js` 新增按字段渲染的适用域/局限文案，`HistoryView.vue` 与 `GameTable.vue` 复用同一批函数。

措辞纪律（冻结，且由 §3.5 的守卫测试锁定）：

- **不得**出现 `GTO`、`NashConv`、`exploitability`、`最优` 等把参考表述为求解器/均衡/最佳打法的字样；
- 涉及「均衡」一词时**只允许出现在否定语境**（如「非均衡近似」），不得作为参考的属性标签；
- 约束 1–2 同时作用于后端常量（`REFERENCE_LIMITATIONS`）与前端展示层（`reviewText.js` 及引用它的组件）。

**必须显式声明的三条局限**（不得省略）：

1. 胜率口径为 vs 随机范围的静态近似，未做对手范围与位置建模；
2. 参考由启发式规则加保守收窄构成，属非均衡近似，不构成求解器或训练产物的质量结论；
3. **与参考动作或其分布众数不同，本身不构成错误；错误只来自既有判据。**

### 3.4 旧保守保护的适用域清单（单独评审，只锁定不改动）

下表逐条列出 `hand_review.py` 既有的教学保护判据、其**适用域**与本轮处置。**本轮全部「保留原值、保留行为」，不做任何调整**；由 §3.5 的回归测试冻结取值与命中行为。

| # | 保护判据（常量 / 函数） | 现值 | 适用域 | 本轮处置 |
|---|---|---|---|---|
| G1 | `_FOLD_EV_MARGIN` / `_FOLD_BET_SCALE`（`_fold_margin`） | `0.15` / `0.10` | 翻牌后「该跟却弃」的胜率余量；随跟注占底池比例放大 | 保留 |
| G2 | `_FOLD_MIN_EQ_PREFLOP` | `0.55` | 翻牌前误弃的胜率下限（vs 随机胜率无法反映加注范围） | 保留 |
| G3 | `_BAD_CALL_EQ_MARGIN` | `0.03` | 跟注赔率不足判定的容差（EV 约 0 的边缘不误报） | 保留 |
| G4 | limp 豁免（`cheap_preflop = 翻牌前且跟注额 ≤ 一个大盲`） | 判据内 | 仅翻牌前的 `bad_call`；不作用于 `bad_fold`，不作用于翻牌后 | 保留 |
| G5 | `_is_made_hand` + `_dominated_pair` + `_has_playable_strength`（被压制对子不算可继续牌力） | 判据内 | 翻牌后「面对下注」的跟注侧牌力质量门槛（参考动作与 `bad_fold` 共用） | 保留 |
| G6 | `_STRONG_DRAW_OUTS` / `_DRAW_MARGIN_SCALE`（强听牌余量折半） | `8` / `0.5` | 翻牌后（`3 ≤ 公共牌 < 5`）的强听牌宽限 | 保留 |
| G7 | `_SMALL_BET_NUM` / `_SMALL_BET_DEN`（小注例外） | `1 / 3` | 翻牌后跟注额 ≤ 底池 1/3 时放宽牌力要求 | 保留 |
| G8 | `_weak_kicker_top_pair`（价值下注侧质量门槛） | 判据内 | 翻牌后无人下注的价值下注收窄；对全部翻牌后街道生效 | 保留 |
| G9 | `_VALUE_BET_EQ`（`value_missed` 阈值） | `0.80` | 翻牌后无人下注时「强牌过牌」的价值丢失判据（复盘口径，宽于策略层） | 保留 |
| G10 | `_UNDERBET_EQ` / `_UNDERBET_DEN` | `0.80` / `2` | 翻牌后强牌下注额 < 底池 1/2 的 `underbet`（`info`） | 保留 |
| G11 | `_SLOWPLAY_EQ` | `0.90` | 翻牌后面对下注时「强牌只跟不加」的 `slowplay`（`warning`） | 保留 |
| G12 | `_OVER_AGGRESSIVE_EQ` | `0.50` | 翻牌后面对下注时「低胜率加注」的 `over_aggressive`（`warning`） | 保留 |
| G13 | `_AIR_EQ` | `0.25` | 无人下注时低胜率下注的 `air_bluff`（`info`） | 保留 |
| G14 | `_EQUITY_SAMPLES` / `_REVIEW_SEED` | `1000` / `0` | 复盘胜率采样数与固定种子（可复现性） | 保留 |

适用域的**边界声明**：以上判据全部是「在 vs 随机静态近似下、面向复盘解释」的**保守收窄**，其结论不构成行动价值比较，也不构成任何均衡或最优性判断；判定只作用于真人实际动作对**该判据**的命中，不作用于「动作是否等于参考分布众数」。

### 3.5 非众数不判错的契约

**契约（冻结）**：`bot_action`（参考分布众数）与 `bot_distribution` 是**展示用参考信息**；错误检测 `_detect_mistakes` **不接收、不读取**参考分布或众数。因此：

1. 「真人动作 ≠ 参考分布众数」**本身不构成任何错误**；
2. 错误的**唯一来源**是既有判据集合 `{bad_call, bad_fold, slowplay, over_aggressive, value_missed, underbet, air_bluff}`；
3. 参考分布中的低频动作只能说明参考在该节点的动作配比，不能推断概率低即为失误（`docs/20` §11.2）。

该契约由三类测试锁定（见 §3.6 验收 C4）。

### 3.6 将来参考换为 CFR 的预留方式

**仅**做两件事，不引入插件接口、不触碰 `strategy/`：

1. **文档**：本文件与 `docs/38a` 记录「唯一事实源只保证不重复判据，不等于把参考永久锁死在启发式」；若将来以 CFR 参考替代，必须同步变更实现契约、更新测试与版本，且旧保守收窄层须**重新审查**而非原样套用（`docs/20` §5.1、§11.2 第 6 条）；
2. **守卫测试**：锁定「分析层不得另抄一套与策略重复的分支判据」——即参考分布仍由 `HeuristicStrategy.action_distribution` 生产，分析层只做收窄与展示，不新增独立判据实现。

### 3.7 验收口径

| # | 验收项 | 判据 |
|---|---|---|
| C1 | 来源/版本/适用域/覆盖范围可追溯 | `GET /hands/{id}/review` 返回六个契约字段，且逐字段等于唯一事实源的声明 |
| C2 | 单一事实源 | `reference_identity()` / `reference_declaration()` 之外无第二份来源/版本/适用域字面量（grep + 测试可证） |
| C3 | UI 如实标注且非 GTO 标签 | 两处复盘界面渲染适用域与局限；后端常量与前端展示层均不含 `GTO`/`NashConv`/`exploitability`/`最优`，「均衡」仅出现在否定语境 |
| C4 | 非众数不判错 | 存在「动作 ≠ 众数且无任何既有判据命中 → `mistakes` 为空」的真实手牌用例；判据函数签名与实现不引用分布/众数；产出错误码 ⊆ 既有判据集合 |
| C5 | 保护判据未被改动 | G1–G14 常量取值被测试逐条冻结；`test_review.py` 既有断言不改动即通过 |
| C6 | 兼容与不可改写 | `reference_strategy` 取值不变；旧历史仍可复盘；`history_json` 不被改写；`sessions` / `hands` 无新增列、无迁移 |
| C7 | 参考语义零改动 | `heuristic.py` 与保守判据零改动；`REFERENCE_VERSION` / `EVALUATION_VERSION` 保持 `1`；缓存键格式不变 |

## 4. 边界声明与不得声称

- 本轮改动是**契约与标注**，**不是 CFR 接入**，也不构成任何质量证据；P0-7 只是 `docs/35` §4.3 依赖链上 `P0-7 → P0-6` 的前置。
- `docs/35` §4 生产接入前置清单中，**只有 P0-7 在本轮被授权**；P0-2 / P0-3 / P0-6 与 P1 / P2 组未被本轮授权。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实 EV 或生产可用策略。
- 本轮稳定性的对照仍不存在代码内建生产者；若出现对照结论必须标注为「事后跨工件只读比较」（本轮无该类结论）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 不得因本轮改动而放宽或删除任何既有的教学保护判据（G1–G14 全部保留）。
- 不得改写 `docs/20` 至 `docs/37a`。

## 5. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码、测试、前端、锁文件或真实数据库；未实施 P0-7 的实现；未实施 `docs/35` §4 清单中的其余任何一项；未新建 campaign、未追加 seed、未重试 authorization；未做云端操作。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P0-7，并在 `docs/38a` 给出文件级改动、新增测试与 `ruff` / `pytest` / `npm run build` 的实跑输出。** 实施后，`docs/35` §4.3 的依赖建议指向 **P0-6（CFR/教学上线质量门槛）**——按依赖链它必须先有参考契约才有可签收的作用对象与适用域；但 P0-6 涉及门槛签收与「单 seed 不判定」，**需单独授权并遵守更强的表述纪律**（`docs/34b` §9.7）。
