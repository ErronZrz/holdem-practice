# 44a M8：P1-3 逐池货币收益契约（实施与验证回执）

> 日期：2026-09-20。
>
> 本文件是 `docs/44` 的**实施与验证回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/43a` 未被改写；`docs/44` 只做了一处**实施期规格修订**（见 §2），原因照录于此。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 实施基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 1]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -2 --oneline
01dcb29 docs: freeze p1-3 per-pot monetary payoff contract specs
f9e957b feat: add controlled action-line range assumption contract

$ git rev-parse HEAD -> 01dcb29ddf142c4654005b32efa3f240d2cc7468（短哈希 01dcb29）
```

`ahead 1` 即本轮规格冻结提交（`docs/44`，未 push，符合「规格与实现分两次提交」）；实施前工作区 0 行。未做任何 `reset` / `clean` / `stash` / `checkout` / `push`。

## 2. 实施期规格修订（记录原因）

`docs/44` 的 §4.5 / §4.6 / §4.7 / §4.9 中，范围来源一项由「**委托 P1-2 的 `profile_for()` 校验并复用其 `UnknownRangeProfileError`**」改为「**声明受控常量 + 一条测试锁定**」。

**原因（实测，不是预判）**：按原规格实现后，P1-2 的冻结回归测试 `tests/test_strategy_range_assumption.py::test_module_has_no_production_caller` 失败——它以源码扫描的方式把 `app/` 内**任何**提及 `range_assumption` 的文件判为「生产调用方」，因此 P1-3 契约模块一旦 import 该模块即被判违规。

**裁定依据**：P1-2 自身对 P0-5 采用的正是「**声明常量 + 测试锁定**」这一做法（`docs/43` §4.7：「对 P0-5 当前生产口径的对照只以声明常量形式存在，并由一条测试锁定其与 `reference_identity.REFERENCE_COVERAGE` 不漂移（生产代码不依赖该模块）」）。本轮**沿用同一既有约定**，从而：

1. **不修改** P1-2 的既有测试与 `docs/43` / `docs/43a`（保持「既往冻结断言不变」）；
2. 仍**不另造**范围语义：`POT_EV_RANGE_PROFILE_IDENTIFIER` / `POT_EV_RANGE_SOURCE` 两个常量与 P1-2 的 `DEFAULT_RANGE_PROFILE_IDENTIFIER` / `RANGE_SOURCE_DECLARED_ASSUMPTION` **逐字相等**，并由测试锁定；
3. 代价（如实声明）：本模块**不**对「形式合法但未登记」的标识做运行时拒绝，只校验 `name@version` 形式。该一致性由测试锁定，属**被声明的边界**，不是静默回退。

该修订只涉及**范围来源的引用方式**，不涉及 `docs/44` §1.3 的任何一项裁定（载体、交付范围、σ 受控闭集、符号与座位口径），用户对本轮五个设计岔路的答复**未被变更**。

## 3. 实际改动（文件级）

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/pot_ev_contract.py`（**新增**，468 行） | 逐池收益契约：`PotEvContract` / `PotEvLayer` 两个冻结模型、`PotEvDisposition` 四值闭集、σ 受控闭集、四类资格处置映射、分型异常 `PotEvError` / `PotEvContractError` / `PotEvEncodingError` / `UnknownScenarioError`，以及纯函数入口 `build_pot_ev_contract` / `disposition_for_kind` / `known_scenario_identifiers` / `scenario_description_for`。**无生产调用方**。 |
| `backend/app/strategy/__init__.py`（修改，+58 行） | 导出新模块的公开符号；既有导出与顺序语义不变。 |
| `backend/tests/test_strategy_pot_ev_contract.py`（**新增**，703 行） | 51 条回归测试，见 §4。 |
| `docs/44-m8-p1-3-per-pot-monetary-payoff-contract.md`（修改，+14 / −6 行） | 仅修订范围来源相关的四条规格条款并加实施期修订说明（见 §2）。 |
| `docs/44a-…md`（本文件） | 实施与验证回执。 |

**未改动**（`git status` 可证）：`backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/api/**`、`backend/app/storage/models.py`、`frontend/**`、`tools/trainer/**`、`backend/uv.lock`、`frontend/package-lock.json`、真实数据库 `backend/data/holdem.db`、`docs/20` 至 `docs/43a`。

### 3.1 契约字段（与 `docs/44` §4.2 / §4.5 逐项一致）

`PotEvLayer` 恰为 10 字段：`lower_commitment` / `upper_commitment` / `amount` / `contributor_seats` / `eligible_seats` / `kind` / `disposition` / `caller_eligible` / `enters_expected_share` / `certain_recovery`。

`PotEvContract` 恰为 17 字段：`schema_version` / `basis` / `scenario_identifier` / `scenario_description` / `range_profile_identifier` / `range_source` / `player_count` / `caller_seat` / `call_amount` / `actual_call_amount` / `is_short_all_in_call` / `runout_scope` / `nominal_share_rule` / `integer_payout_rule` / `layers` / `certain_recovery_total` / `limitations`。

### 3.2 符号口径（与 `docs/44` §1.3 裁定四一致）

| 资格 `kind` | 处置 `disposition` | 口径 | 符号 |
|---|---|---|---|
| `contested` | `contested` | 进入期望项 `E[Σ S_{h,ℓ} | σ]`，名义份额按同级赢家人数 `k` 取 `1/k` | 期望项（本轮**未求值**） |
| `caller_recovery` | `certain_recovery` | 计入确定回收 `R_h`（`certain_recovery_total`） | `+`（确定） |
| `other_uncontested` | `not_eligible` | 不计入（当前行动者无资格） | `0` |
| `no_eligible_return` | `refund` | 不计入（与当前行动者结构上无关） | `0` |

`A`（`actual_call_amount`）是唯一现金成本项；`C`（`call_amount`）只作参照字段。整数派彩规则与名义份额规则以 `integer_payout_rule` / `nominal_share_rule` **两个独立声明字段**承载，不相互冒充。

## 4. 新增测试与覆盖对应

`backend/tests/test_strategy_pot_ev_contract.py`，**51 passed**（`0.11s`）。逐项对应 `docs/44` §4.9 的验收口径：

| 验收项 | 覆盖 |
|---|---|
| C1 逐层 eligible 与实际支付 `A` 组合正确 | `test_layers_follow_actual_call_amount_and_dispositions`、`test_other_uncontested_layer_is_excluded`、`test_contract_uses_actual_short_payment_from_the_engine` |
| C2 四类资格处置正确 | `test_disposition_covers_all_four_layer_kinds`、`test_other_uncontested_layer_is_excluded`、`test_no_eligible_return_layer_is_excluded_from_payoff`、`test_layers_follow_actual_call_amount_and_dispositions` |
| C3 短码全下覆盖层 | `test_short_all_in_call_covers_only_the_layers_it_reaches`、`test_contract_uses_actual_short_payment_from_the_engine` |
| C4 联合 runout 为共享口径 | `test_main_three_way_and_side_two_way_share_one_runout`、`test_contract_declares_version_basis_scenario_and_rules` |
| C5 平局分配与整数余数分别表述 | `test_nominal_share_and_integer_payout_are_declared_separately` |
| C6 σ 为受控闭集 | `test_known_scenarios_are_a_closed_set`、`test_unknown_scenario_stops_the_construction` |
| C7 明确失败（分型、互不继承） | `test_error_types_are_distinct`、`test_non_projection_input_is_a_contract_violation`、`test_call_amount_must_be_a_positive_integer`、`test_call_amount_below_the_actual_payment_fails`、`test_eligible_seats_must_be_contributors`、`test_folded_caller_cannot_build_a_payoff_contract`、`test_caller_without_eligibility_is_incomplete`、`test_non_contiguous_layers_fail`、`test_unknown_layer_kind_fails`、`test_layer_rejects_mismatched_disposition`、`test_layer_rejects_recovery_without_eligibility` |
| C8 2–9 人参数化 | `test_contract_is_parameterized_over_player_counts`（`N = 2..9`） |
| C9 不读对手暗牌与未来牌 | `test_contract_fields_carry_no_cards_board_or_seed`、`test_contract_ignores_hidden_cards_board_and_seed` |
| C10 不读运行中 seed | 同上（两个不同 `seed` 的引擎得到**相等**契约） |
| C11 不写回 `history_json` | `test_module_has_no_production_caller`、`test_build_does_not_mutate_the_projection`、`test_contract_round_trips_through_json` |
| C12 既有 `call_ev` / `equity()` 语义未变 | `test_module_never_imports_engine_equity_analysis_or_storage`（源码中不含 `call_ev` / `ties` / 相关工作模块）、`test_production_reference_identity_is_unchanged` |
| C13 与 P1-2 版本化对齐 | `test_range_reference_mirrors_the_controlled_catalogue`、`test_range_profile_identifier_must_be_versioned` |
| C14 无生产调用方 | `test_module_has_no_production_caller`、`test_entry_accepts_only_public_projection_and_declarations` |

另含契约纪律测试：字段集恰为冻结集合（10 / 17 项）、`extra="forbid"`、模型冻结、结构版本不匹配、来源标注拒绝求解器口径、局限声明必须齐备。

## 5. 实际验证输出

```text
$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
567 passed, 1 skipped, 2 warnings in 9.72s
（基线为 516 passed, 1 skipped；本轮新增 51 条，516 + 51 = 567，无既有用例被删改）

$ cd backend && uv run pytest tests/test_strategy_pot_ev_contract.py -q
51 passed in 0.11s

$ cd frontend && npm run build
vite v6.4.3 building for production...
✓ 23 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.31 kB
dist/assets/index-C7nR2Wox.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 454ms

$ git diff --check
（无输出）
```

两条 warning 均为既有的 Starlette/httpx 与 AnyIO 弃用提示。本轮**未改变前端任何文件**（`git status` 可证），前端构建只用于确认无回归。

`tools/trainer/` 本轮**未被触碰**，因此未运行其 `ruff` / `pytest`。

## 6. 版本影响与兼容性

| 对象 | 影响 |
|---|---|
| 既有策略语义 | **零改动**：`heuristic.py` 的阈值、分支与 `equity()` 调用完全不变 |
| 复盘与参考身份 | **零改动**：`hand_review.py` 与 `reference_identity.py` 未被触碰；`reference_strategy` / `reference_version` / `evaluation_version` / `reference_coverage` 取值不变；`call_ev` 展示口径（含短码时 `None`）不变 |
| `equity()` 与静态 share | **零改动**：固定 `ties/2` 不变；`estimate_static_showdown_share()` 不变，仍无生产调用方 |
| 引擎 / 结算 | **零改动**：`pot_projection.py` / `actions.py` / `engine.py` 未被触碰；`_settle_showdown()` 的整数派彩语义不变 |
| 生产池层资格投影 | **零改动**：`project_pot_layers()` / `project_candidate_call()` 只被**只读引用**其模型类型与枚举 |
| API 与前端 | **零改动**：不新增或改名字段；缓存键不变；未恢复前端策略选择器 |
| 数据库 | **不加列、不迁移**；真实数据库只读 |
| 旧响应 / 旧历史 / 旧前端 | 结构不变；`history_json` 未被改写；旧手牌仍可复盘 |
| 锁文件 | 零改动（不新增依赖） |
| 新模块 | 新增独立模块与导出；**目前无生产调用方**，不改变任何运行时路径与对外响应 |
| `docs/37` §3.1 升版判定 | **不触发**：参考实现、保守判据、`equity` 实现、采样数与固定种子**五项全部零改动**（明确声明） |
| 不可编码局面的实际处置 | **不产生契约、不产生动作**；抛分型明确异常；无默认情景、无补零、无插值、无最近桶 |

## 7. 边界声明与不得声称

- 本轮改动是**契约与收益口径层**，**不是** CFR 接入，也**不构成任何质量证据**；`backend/app/strategy/` 仍无任何 CFR lookup 或产物接线的新语义。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论；**未启动任何实际运行**。
- 本轮**不产出任何 CALL EV 数值**：`E[Σ S_{h,ℓ} | σ]` 是未求值的占位，跑抽样与联合 runout 属未授权的后续工作。
- **不得**把本轮交付表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实牌局 EV 或生产可用策略；**不得**把资格投影或静态 pooled share 表述为逐池 EV / 完整 CALL EV。
- **不得**用 `1/k` 直接替换既有 `call_ev`；**不得**跨人数插值，**不得**用「最近桶」「补零」「掩码」冒充精确。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者；本轮无该类结论）。
- 本轮不追加 seed、不新建冻结 campaign、不重试任何已消耗 authorization、不上云、不转 GPU、不扩预算。

## 8. 未做事项与下一步唯一建议动作

未做：

- 未改 `backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/api/**`、`frontend/**`、`backend/app/storage/models.py`、锁文件、真实数据库、`tools/trainer/**`、`docs/20` 至 `docs/43a`。
- 未实现抽样：无联合 runout 采样、无逐层份额抽样、无任何行动价值数值。
- 未接入任何生产路径（策略 / 复盘 / API / 前端）；未启用 `docs/39` 的质量门槛；未构建或修改任务正文以外的自动化。
- 未实施 `docs/35` §4.2 清单中 P1-3 以外的任何一项（P1-4 / P1-5 与 P2 组全部未授权）。
- 未 push（本轮共两次提交，均为本地提交）。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**在 `docs/35` §4.2 的 P1 组中单独授权 P1-4（真实 Hold'em 的下注尺度与公共牌）或 P1-5（修复后 6/7（及 2–9）人性能复测）中的一项。** 其中 P1-4 是本契约真正产出具数值期望的前置（真实牌堆、公共牌与联合 runout 的抽样实现都依赖它）；P1-5 与 P0-2 共享性能口径。P2 组（2–9 人产品验收、N=9 结论、历史 `pot_results` 不一致、稳定性生产者）相互独立，可各自单独排期。
