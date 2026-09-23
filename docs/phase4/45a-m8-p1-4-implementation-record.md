# 45a M8：P1-4 真实规则边界契约（实施与验证回执）

> 日期：2026-09-20。
>
> 本文件是 `docs/45` 的**实施与验证回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/44a` 未被改写；`docs/45` 只做了两处**实施期规格修订**（见 §2），原因照录于此。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 实施基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 3]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -3 --oneline
6388bba docs: freeze p1-4 real rules boundary contract specs
edcc224 feat: add controlled per-pot monetary payoff contract
01dcb29 docs: freeze p1-3 per-pot monetary payoff contract specs

$ git rev-parse HEAD -> 6388bba32fcdf2b81fafab934882723a1bd574ef（短哈希 6388bba）
```

`ahead 3` 即 P1-3 的两次提交与本轮 `docs/45` 冻结提交，全部为**本地**提交，本轮**不 push**；实施前工作区 0 行。未做任何 `reset` / `clean` / `stash` / `checkout`。

## 2. 实施期规格修订（记录原因）

| # | 修订 | 原因（实测） |
|---|---|---|
| 1 | §4.2：抽象版本、训练覆盖人数与动作词表由「本模块声明字面量」改为「**复用**既有抽象契约模块的常量并派生元组」；`ABSTRACTION_ACTION_TOKENS` 的取值随之由 `("x","b","c","f")` 改为派生的 `("b","c","f","x")` | 按原规格实现后 `__init__.py` 出现 `F811` 重定义——P0-3 的抽象契约模块**已经**声明了 `ABSTRACTION_GAME_VERSION = "m8-a-v1"`、`ABSTRACTION_TRAINED_PLAYER_COUNTS = {6,7,9}`、`ABSTRACTION_ACTIONS = {x,b,c,f}`。两处字面量正是「另造一套」；改为复用后**同一事实只有一处来源**，并由测试断言两者相等 |
| 2 | §4.7 / §4.9 C4：模型构造期的目录一致性检查（改写判定或前置、注入未知 / 重复 / 缺漏条目、抽象常量或基准或结构版本不匹配）由「抛 `RealRulesBoundaryContractError`」改为「由 Pydantic 包装为 `ValidationError`」 | 实测 Pydantic v2 会把 `model_post_init` 抛出的 `ValueError` 包装为 `ValidationError`（与 P1-2 已确立的既有情形一致）。分型异常仍由**查询与失败入口**抛出：`boundary_for` / `verdict_for` / `features_with` / `require_in_abstraction_slice` |

两处修订都**不涉及** `docs/45` §1.3 的三项裁定（载体、只交付边界契约、受控闭集三值 + 复用 P0-3 失败语义），用户对本轮四个设计岔路的答复**未被变更**。

## 3. 实际改动（文件级）

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/real_rules_boundary.py`（**新增**，443 行） | 边界契约：`RuleSliceBoundary` / `RuleBoundaryContract` 两个冻结模型、`BoundaryVerdict` 三值闭集、20 条冻结目录、受控前置标识闭集、分型异常 `RealRulesBoundaryError` / `RealRulesBoundaryContractError` / `UnknownBoundaryFeatureError`，以及纯函数入口 `boundary_catalogue` / `boundary_features` / `boundary_for` / `verdict_for` / `features_with` / `require_in_abstraction_slice` / `build_rule_boundary_contract`。**无生产调用方**。 |
| `backend/app/strategy/__init__.py`（修改，+61 行） | 导出新模块的公开符号；既有导出与顺序语义不变。 |
| `backend/tests/test_strategy_real_rules_boundary.py`（**新增**，378 行） | 32 条回归测试，见 §4。 |
| `docs/45-m8-p1-4-real-rules-boundary-contract.md`（修改） | 规格冻结（`6388bba`）+ 两处实施期修订（见 §2）。 |
| `docs/45a-…md`（本文件） | 实施与验证回执。 |

**未改动**（`git status` 可证）：`backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/api/**`、`backend/app/storage/models.py`、`frontend/**`、`tools/trainer/**`、`backend/uv.lock`、`frontend/package-lock.json`、真实数据库 `backend/data/holdem.db`、`docs/20` 至 `docs/44a`。

### 3.1 抽象事实（复用 + 补充）

| 常量 | 值 | 来源 |
|---|---|---|
| `ABSTRACTION_GAME_VERSION` | `"m8-a-v1"` | 复用 P0-3 抽象契约模块 |
| `ABSTRACTION_PLAYER_COUNTS` | `(6, 7, 9)` | 由抽象契约模块的人数集合派生 |
| `ABSTRACTION_ACTION_TOKENS` | `("b", "c", "f", "x")` | 由抽象契约模块的动作集合派生 |
| `ABSTRACTION_GAME_ID` | `"m8-unique-rank-single-open"` | 本模块补充声明 |
| `ABSTRACTION_ANTE` / `ABSTRACTION_BET` | `1` / `1` | 本模块补充声明 |

后四项与训练器候选切片描述的一致性由**一条测试读取训练器源文件**锁定（不 import 该独立工程）。

### 3.2 冻结目录（20 条）

| 判定 | 条数 | 切片 |
|---|---:|---|
| `in-abstraction-slice` | 6 | `relative-seat-order`、`public-action-history`、`fold-and-alive-state`、`fixed-integer-contributions`、`constant-sum-utility`、`private-information-key` |
| `out-of-abstraction` | 7 | `blinds-and-forced-bets`、`multi-street-betting`、`public-board`、`variable-bet-sizing`、`re-raise-multi-level`、`real-card-evaluation`、`opponent-real-hole-cards` |
| `contracted-not-wired` | 7 | `all-in-and-short-stack`、`side-pots`、`multiway-tie-share`、`per-pot-monetary-payoff`、`position-and-action-line-projection`、`action-line-range-assumption`、`abstraction-mapping-and-coverage` |

受控前置标识闭集：`abstraction-coverage` / `candidate-call-pot-projection` / `position-projection` / `range-assumption` / `pot-ev-contract`（外加 `none`）；**真实下注尺度**与**公共牌**被明确划到 `out-of-abstraction`。

## 4. 新增测试与覆盖对应

`backend/tests/test_strategy_real_rules_boundary.py`，**32 passed**（`0.11s`）。对应 `docs/45` §4.9：

| 验收项 | 覆盖 |
|---|---|
| C1 抽象事实齐备且对齐训练器 | `test_abstraction_descriptor_is_declared`、`test_abstraction_facts_reuse_the_abstraction_contract`、`test_abstraction_descriptor_matches_the_trainer_slice` |
| C2 逐条划分、不重不漏 | `test_catalogue_partitions_every_feature_into_three_verdicts` |
| C3 判定为闭集三值 | 同上（三值并集等于全部切片） |
| C4 判定不可改写 | `test_contract_rejects_a_rewritten_verdict`、`test_contract_rejects_missing_duplicate_or_reordered_entries`、`test_contract_rejects_a_foreign_version_or_basis_or_abstraction` |
| C5 前置标识为闭集且真实存在 | `test_prerequisites_follow_the_verdict`、`test_prerequisite_identifiers_resolve_to_real_entry_points` |
| C6 下注尺度与公共牌在界外 | `test_bet_sizing_and_board_are_out_of_abstraction` |
| C7 明确失败 | `test_unknown_feature_or_verdict_fails`、`test_require_in_abstraction_slice_fails_outside_the_slice`、`test_contracted_slice_must_declare_a_known_prerequisite`、`test_in_slice_entry_must_not_declare_a_prerequisite` |
| C8 不替代 `judge_coverage` | `test_entry_has_no_real_state_input`、`test_module_only_reuses_the_abstraction_contract` |
| C9 不实现真实牌堆 / 公共牌 / 尺度 | `test_contract_fields_carry_no_real_state` |
| C10 只复用抽象契约 | `test_module_only_reuses_the_abstraction_contract` |
| C11 无生产调用方 | `test_module_has_no_production_caller` |
| C12 既有语义零改动 | 后端完整套件 599 passed（基线 567 + 本轮 32，无既有用例被删改） |

另含契约纪律测试：字段集恰为冻结集合（5 / 9 项）、`extra="forbid"`、模型冻结、切片标识字符集（拒绝大写、下划线、路径与点号）、结构版本、局限声明必须齐备、JSON 往返。

## 5. 实际验证输出

```text
$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
599 passed, 1 skipped, 2 warnings in 9.70s
（本轮起点基线 567 passed, 1 skipped；新增 32 条，567 + 32 = 599，无既有用例被删改）

$ cd backend && uv run pytest tests/test_strategy_real_rules_boundary.py -q
32 passed in 0.11s

$ cd frontend && npm run build
vite v6.4.3 building for production...
✓ 23 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.31 kB
dist/assets/index-C7nR2Wox.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 450ms

$ git diff --check
（无输出）
```

两条 warning 均为既有的 Starlette/httpx 与 AnyIO 弃用提示。本轮**未改变前端任何文件**（`git status` 可证），前端构建只用于确认无回归。`tools/trainer/` **未被触碰**，因此未运行其 `ruff` / `pytest`（只在后端测试中**只读**其 `game.py` 以锁定常量）。

## 6. 版本影响与兼容性

| 对象 | 影响 |
|---|---|
| 既有策略语义 | **零改动**：`heuristic.py`、注册表与分派路径不受影响 |
| 复盘与参考身份 | **零改动**：`hand_review.py` 与 `reference_identity.py` 未被触碰；四个版本字段与 `call_ev` 展示口径不变 |
| 抽象契约（P0-3） | **零改动**：只被**只读复用**三个常量；`judge_coverage` 与覆盖判定语义不变，也**未被**替代 |
| P1-1 / P1-2 / P1-3 模块 | **零改动**：只以受控前置**标识**引用，并由测试锁定其入口存在；生产代码不互相 import |
| API 与前端 | **零改动**：不新增或改名字段；缓存键不变 |
| 数据库 | **不加列、不迁移**；真实数据库只读 |
| 引擎 / 结算 | 零改动；`equity` / `pot_projection` / `_settle_showdown` 语义不变 |
| 训练器 | **零改动**：不被 import，只被后端测试读取源文件 |
| 锁文件 | 零改动（不新增依赖） |
| 新模块 | 新增独立模块与导出；**无生产调用方**，不改变运行时路径与对外响应 |
| `docs/37` §3.1 升版判定 | **不触发**：参考实现、保守判据、`equity` 实现、采样数与固定种子五项全部零改动 |
| 抽象外切片的实际处置 | **不产生映射、不产生动作**；`require_in_abstraction_slice` 抛 `RealRulesBoundaryContractError`，未知标识抛 `UnknownBoundaryFeatureError`；无最近桶、无补零、无默认尺度、无插值 |

## 7. 边界声明与不得声称

- 本轮改动是**边界契约层**，**不是** CFR 接入，也**不构成任何质量证据**。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论；**未启动任何实际运行**。
- 本轮**没有实现**真实牌堆、公共牌、可变下注尺度、真实牌力评估，也**没有实现** P1-3 遗留的期望项抽样；真实下注尺度与公共牌被**划到抽象之外的界**。
- **不得**把候选 A 的受限抽象结果表述为真实牌局 EV、GTO、均衡、NashConv、exploitability、best response 或生产可用策略。
- **不得**把本轮的边界表表述为「已支持真实 Hold'em」「已实现真实下注尺度/公共牌」或「已接入生产」。
- **不得**用「最近桶」「补零」「掩码」「插值」「默认尺度」把抽象外的切片冒充为已映射。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者；本轮无该类结论）。
- 本轮不追加 seed、不新建冻结 campaign、不重试任何已消耗 authorization、不上云、不转 GPU、不扩预算。

## 8. 未做事项与下一步唯一建议动作

未做：

- 未改 `backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/api/**`、`frontend/**`、`backend/app/storage/models.py`、锁文件、真实数据库、`tools/trainer/**`、`docs/20` 至 `docs/44a`。
- 未实现真实牌堆 / 公共牌 / 下注尺度 / 牌力评估；未实现联合 runout 或份额抽样；未产出任何行动价值数值。
- 未接入任何生产路径（策略 / 复盘 / API / 前端）；未启用 `docs/39` 的质量门槛。
- 未实施 `docs/35` §4.2 清单中 P1-4 以外的任何一项（P1-5 与 P2 组全部未授权）。
- 未 push（本轮共两次提交，均为本地提交）。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**单独授权 P1-5（修复后 6/7（及 2–9）人性能复测）**——它是 `docs/35` §4.2 的 P1 组中唯一尚未授权的一项，与 P0-2 共享性能口径。若用户更关心把逐池收益从口径推进到数值，则应另行单独授权「真实牌堆与跨层联合 runout 的只读抽样原语」，并说明其跨 `poker/` 的边界——该实现**不**由本轮或 P1-5 自动覆盖。P2 组（2–9 人产品验收、N=9 结论、历史 `pot_results` 不一致、稳定性生产者）相互独立，可各自单独排期。
