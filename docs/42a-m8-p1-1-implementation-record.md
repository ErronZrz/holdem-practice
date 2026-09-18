# 42a M8：P1-1 位置与公开行动线投影——实施与验证回执

> 日期：2026-09-18。
>
> 本文件接在 `docs/42` 之后，沿用 `docs/30` D6 的编号族约定：`docs/42` 为规格与裁定冻结，本文件为同一轮的**实施与验证回执**。`docs/20` 至 `docs/42` 未被改写。
>
> 本文件只记录已实际落地的代码、测试与实跑输出；**不产生任何策略、质量或资源证据**，也**未**实现任何覆盖判定、回退动作、范围模型或 CFR 接入。

## 1. 本轮提交与授权

| 次序 | commit | 内容 |
|---|---|---|
| 1 | `bf6794d9cc3bb5c5650287c6124ff11c40acf670` | `docs/42` 规格与四项设计岔路裁定冻结（仅文档） |
| 2 | 本文件同批 | 位置与公开行动线投影模块、导出、回归测试、`docs/42a` |

用户答复原文（四项均为推荐口径，照录于 `docs/42` §1.2）：

- 执行确认与边界：「确认执行；trainer 与 poker 只读」；
- 岔路一：「新增独立模块 position_projection.py」；
- 岔路二+三：「相对按钮 + 只编码动作与相对座位」；
- 岔路四：「只交付投影，不判定落入」。

据此**被授权**并已使用：`backend/app/strategy/` 新增位置投影模块、`backend/tests/` 新增回归测试、新增 `docs/42*`。
**被拒绝**且本轮确实未做：`tools/trainer/**` 与 `backend/app/poker/**` 任何改动；任何回退动作实现或策略分派路径改动；与候选 A 抽象的落入判定；P1-2 及之后的任何一项。

`backend/app/api/` 的授权本轮**未被使用**：投影层自足，无需改动任何请求/响应模型或路由。

## 2. 实际基线核验（只读）

第二次提交前的基线（`docs/42` 已落地，工作区仅含本文件与代码改动）：

```text
$ git log -2 --oneline
bf6794d docs: freeze p1-1 position and public action line projection specs
9c684e7 feat: add controlled artifact lookup with budget contract and opt-in measurement

$ git status --porcelain=v1 --untracked-files=all
 M backend/app/strategy/__init__.py
?? backend/app/strategy/position_projection.py
?? backend/tests/test_strategy_position_projection.py
```

`docs/42` 提交前已核验的起点基线与期望完全相符：`## master...origin/master [ahead 12]`、工作区 0 行、`HEAD = 9c684e738511f9c37d9d4b1e21a5cf0e69524621`、`origin/master = ef7e59282015e58f0e7fd153e30cd85ae6e9f56f`、campaigns = 8、11 份 `strategy.json`（N=6 五份 / N=7 六份 / N=9 零份）。未做任何 `reset` / `clean` / `stash` / `checkout`；未 push；未消耗任何本机实验预算。

## 3. 实际改动清单（文件级）

### 3.1 新增

| 文件 | 内容 |
|---|---|
| `backend/app/strategy/position_projection.py` | 受控位置投影 `PositionProjection`、按街分段的 `StreetActionLine`、输入侧受控记录 `PublicAction`，以及 `relative_seat` / `blind_relative_seats` / `street_action_order` / `build_public_actions` / `build_position_projection` / `project_position_for_actor` |
| `backend/tests/test_strategy_position_projection.py` | 119 个用例：字段契约、相对座位与行动顺序、前位人数、动作线分段与金额剥离、单挑盲位特例、绝对座位剥离、信息边界、不可编码/不完整明确失败、契约违规、纯度与不写回 |
| `docs/42`、`docs/42a` | 规格冻结与实施回执 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/__init__.py` | **仅新增导出**（`position_projection` 的常量、异常、模型与函数，共 17 个名字）；既有导出名与语义不变 |

### 3.3 未触碰（边界逐项核验）

- **零改动**：`backend/app/poker/**`（含 `engine.py`、`equity`、`estimate_static_showdown_share`、`pot_projection`、`_settle_showdown`）、`backend/app/analysis/**`、`backend/app/storage/**`（含 `models.py`，未加列、未迁移）。
- **零改动**：`backend/app/api/**`、`frontend/**`、`backend/data/holdem.db`、`backend/uv.lock`、`frontend/package-lock.json`。
- **零改动**：`tools/trainer/**`（含 `kuhn_cfr/**`）；训练器只被**只读**引用为其键格式的规范出处，代码中不导入、不读取、不执行其内容。
- `backend/app/strategy/heuristic.py`、`random_strategy.py`、`interface.py`、`projection.py`、`abstraction.py`、`registry.py`、`artifact.py`、`lookup_budget.py` 的决策语义与分派语义**零改动**。

## 4. 投影层的实际形态

| 名称 | 实际语义 |
|---|---|
| `POSITION_PROJECTION_FIELDS` | 恰好七项：`player_count` / `street` / `relative_actor` / `action_order` / `players_to_act_before` / `players_to_act_after` / `public_action_line`；字段集即契约，`PositionProjection` 用 `extra="forbid"` 拒绝未登记字段，并冻结为不可变 |
| 常量 | `POSITION_PROJECTION_VERSION = "position-line.v1"`、`POSITION_BASIS = "relative-button"`、`POSITION_STREETS = ("preflop","flop","turn","river")`、`POSITION_ACTION_TOKENS`（`small_blind→sb`、`big_blind→bb`、`fold→f`、`check→x`、`call→c`、`bet→b`、`raise→r`）——全部为**后端本地常量**，不依赖 `app.poker.engine` / `app.poker.actions` |
| `relative_seat` / `blind_relative_seats` | 相对按钮换算与盲注相对座位：`N == 2` 时为 `(0, 1)`（按钮即小盲），`N >= 3` 时为 `(1, 2)` |
| `street_action_order` | 翻前：`N == 2` 自 `0` 起（按钮先行动），`N >= 3` 自 `3` 起顺时针；翻后：自 `1` 起顺时针；长度恒为 `N` |
| `build_public_actions` | 把引擎风格条目规范化为 `PublicAction` 元组；缺键、类型错误、非映射一律抛 `PositionContractError`，不做类型转换 |
| `build_position_projection` | 纯函数；接受受控记录或引擎风格条目；绝对座位/按钮只参与一次相对化换算；不可编码时抛 `PositionEncodingError` |
| `project_position_for_actor` | 从生产快照出发：**先**经 P0-4 的 `project_for_actor` 只保留行动者视角，再以投影结果的人数/按钮/当前座位/街名构造 |
| 不可编码判定 | 街序不完整或回退、重复街、盲注结构与规则不符、词表外动作、座位越界、已弃牌座位再次行动、同街重复行动缺少 `bet`/`raise` 解释、**短码全下加注**、终局街、当前街早于最后一段动作所在的街 |

落地口径（与 `docs/42` §4 一致）：

1. **不重造脱敏**：快照入口先调用 P0-4 的 `project_for_actor`，本模块自身不新增第二条信息边界；投影字段中不存在底牌、公共牌、底池、筹码与随机源；
2. **不复用训练器代码**：动作词表与位置顺序由后端**本地**常量与本地规则生成；不导入、不读取、不执行训练器内容；
3. **金额不进投影**：`amount` 只存在于输入侧 `PublicAction`，仅用于判定「短码全下加注」，不出现于任何投影字段；
4. **无条件静默回退**：抽象外、不完整或不可编码一律抛**分类型**异常（`PositionContractError` / `PositionEncodingError`），二者取值不同且互不继承；没有最近位置、默认顺序或插值路径；
5. **绝对座位剥离**：同向平移全部绝对 `seat` 与绝对 `button` 后，投影逐字段完全相等；
6. **单挑特例结构性保留**：`N == 2` 时按钮即小盲、翻前按钮先行动，由位置序与盲注相对座位共同表达，并被专门用例锁定。

### 4.1 两点如实标注的已知局限（不冒充精确）

1. **最小加注额基准**：`docs/42` §4.4 已写明「最小加注额以本手大盲的实际记录金额为基准」。若大盲因短码未能足额投入，引擎内部的最小加注额（配置大盲）会大于该记录金额，此时「短码全下加注」可能**未被检出**。本层**不**重演筹码机（`docs/42` §4.6），故不作近似修补；该情形属后续「真实下注尺度与筹码层」的范围。
2. **入口参数越界的归类**：动作记录中的绝对座位越界判为**不可编码**（`PositionEncodingError`）；而入口参数 `button` / `current_seat` 越界判为**契约违规**（`PositionContractError`）——前者是历史内容的问题，后者是调用方参数的问题。两类分型在测试中被分别锁定。

## 5. 新增测试（119 个）

```text
$ cd backend && uv run pytest -q --collect-only tests/test_strategy_position_projection.py | tail -1
119 tests collected
```

| 验收项（`docs/42` §4.8） | 对应用例（节选） | 锁定的事实 |
|---|---|---|
| C1 相对座位正确 | `test_relative_actor_is_measured_from_the_button`（2–9 人 × 3 种按钮偏移） | 行动者相对座位恒为 `(seat − button) mod N` |
| C2 行动顺序正确 | `test_action_order_matches_the_blind_rules`、`test_action_order_starts_at_the_engine_first_actor` | 翻前/翻后顺序按人数与街唯一确定；首行动者与**真实引擎实测**一致 |
| C3 前位待行动人数正确 | `test_players_to_act_counts_are_positional`（2–9 人 × 4 街 × 全座位） | 位次口径正确，前后之和恒为 `N − 1` |
| C4 公开动作线可编码且按街分段 | `test_action_line_is_segmented_by_street`、`test_action_line_is_deterministic_and_amount_free`、`test_bet_and_raise_keep_their_action_kind`、`test_big_blind_may_act_after_posting` | 同输入同 token；街序自 `preflop` 起；金额不出现在投影；大盲投注后仍可行动 |
| C5 单挑盲位特例保留 | `test_heads_up_button_posts_the_small_blind`、`test_heads_up_real_hand_matches_the_engine` | 相对小盲 `0`、相对大盲 `1`、翻前 `(0, 1)`、翻后 `(1, 0)`；真实单挑牌局实测 |
| C6 绝对 seat 不作为牌理特征 | `test_shifting_every_absolute_seat_leaves_the_projection_unchanged`（5 种平移）、`test_projection_never_exposes_absolute_seats` | 同向平移后投影逐字段相等；投影字段集不含 `seat` / `button` |
| C7 2–9 人参数化，不写死两人 | 上述 2–9 人参数化用例、`test_real_six_player_hand_projects_relative_seats` | 2–9 人逐一构造成功；**未写死两人** |
| C8 不读对手暗牌与未来牌 | `test_projection_ignores_opponent_hole_cards_and_board`、`test_projection_carries_no_seat_amount_or_hidden_fields` | 替换对手暗牌与公共牌后投影完全相等；字段集中不存在相关字段 |
| C9 不可编码 / 不完整明确失败 | `test_empty_action_line_fails`、`test_action_line_must_start_at_preflop`、`test_duplicated_street_fails`、`test_street_regression_fails`、`test_current_street_earlier_than_last_action_fails`、`test_missing_blinds_fails`、`test_blind_structure_must_match_the_rules`、`test_unknown_action_fails`、`test_forced_blind_must_not_repeat_mid_street`、`test_out_of_range_seat_fails`、`test_folded_seat_cannot_act_again`、`test_repeat_action_without_reopen_fails`、`test_short_all_in_raise_is_not_encodable`、`test_terminal_street_has_no_actor`、`test_position_error_types_are_distinct`、`test_structural_illegal_arguments_raise_contract_error`、`test_malformed_history_entries_raise_contract_error` | 六类触发条件各自失败；契约违规与不可编码分型独立；**不存在**静默回退路径 |
| C10 不写回 `history_json` | `test_projection_does_not_mutate_the_input_history`、`test_projection_round_trips_through_json`、`test_module_never_imports_storage_or_engine`、`test_projection_is_frozen` | 输入不被改写；投影为纯值对象；模块不导入存储与引擎实现 |
| 反例：重开后才允许重复行动 | `test_repeat_action_after_a_raise_is_allowed` | 有 `raise` 解释的重复行动**不**被误判为失败 |

## 6. 实跑验证输出

```text
$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
452 passed, 1 skipped, 2 warnings in 10.72s      （333 → 452，新增 119；1 skipped 为实测入口）

$ cd frontend && npm run build
vite v6.4.3 building for production...
✓ 23 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.31 kB
dist/assets/index-C7nR2Wox.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 526ms
```

前端产物文件名与体积（`index-Bjv7RHTw.js`，100.68 kB / gzip 37.64 kB）与 `docs/39a` §7、`docs/40a` §6 记录**逐字相同**，证明本轮改动未越出后端。`tools/trainer/` 未改动，故未运行其 `ruff` / `pytest`。

## 7. 版本影响与兼容性

| 对象 | 实际行为 |
|---|---|
| 既有策略语义 | **零改动**；`heuristic@1` / `random@1` 的决策分布与参考口径不变 |
| 策略分派与 API | **零改动**；未新增运行时行为，未改任何请求/响应字段，未恢复已移除的前端策略选择器 |
| 数据库 | **不加列、不迁移**；真实数据库只读，未被写入 |
| 旧历史 / 旧响应 / 旧前端 | 结构不变；`history_json` 未被改写；本轮不产生任何新字段或列 |
| 投影模块的落点 | 新增独立模块，仅新增导出；本模块**目前无生产调用方**，不改变任何运行时路径 |
| 不可编码局面的实际处置 | **不产生投影、不产生动作**；抛 `PositionEncodingError`，无最近位置/默认顺序/插值 |
| 与候选 A 的关系 | 投影**未**被判定为落入或覆盖；真实局面能否落入受限抽象属后续单独授权的工作 |
| 预算 | 本轮未消耗任何实验预算（无受监督运行；仅单元测试与文档撰写） |

## 8. 边界声明与不得声称

- 本轮改动是**契约与投影层**，**不是** CFR 接入，也**不构成任何质量证据**；`backend/app/strategy/` 仍无任何 CFR lookup 或产物接线的**新**语义。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- **不得**把投影结果表述为「已覆盖」「已支持 CFR」或「精确解」；也**不得**因为投影可成功构造就声称真实局面已被训练抽象覆盖。真实局面与受限抽象的落差（`docs/42` §3.3）在本轮代码中如实体现：投影只描述位置与公开动作线，不给出任何覆盖或近似结论。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」；代码中仍**不存在**稳定性生产者。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据**（本轮即属此情况）。
- 未改写 `docs/20` 至 `docs/42`；未 push（`ahead` 数由用户决定何时推送）。

## 9. 未做事项与下一步唯一建议动作

未做：

- **未实现**与候选 A 抽象的落入判定、任何覆盖判定入口或任何回退动作（属后续单独授权）。
- **未实现**范围模型、逐池货币收益、真实下注尺度与公共牌、性能复测（P1-2 / P1-3 / P1-4 / P1-5 全部未授权）。
- **未实现**任何回退动作；未改动 `registry` / `games.py` 的策略分派路径；未新增任何运行时兜底行为。
- 未实施 `docs/35` §4 清单中 P1-1 以外的任何一项；P0 组与 P2 组全部未动。
- 未改动 `backend/app/api/**`（授权但本轮不需要）、前端、`poker/**`、`analysis/**`、`storage/**`、锁文件与真实数据库。
- 未改动 `tools/trainer/**`；未新增依赖或 JSON schema。
- 未新增受监督运行或 campaign；未追加 seed；未重试任何已消耗 authorization；未消耗实验预算；未做云端操作。
- 未改质量门槛或启用 `docs/39` 门槛；未放宽或删除任何既有教学保护判据。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按 `docs/35` §4.3 推进 P1-2（用基于公开行动线的范围模型替代「vs 随机底牌」）**，并在实施前先明确两点口径：范围假设必须**与参考来源一起版本化**、且**不得读取对手暗牌与未来牌**。
两项提醒：一是 P1-2 与 `equity()` 固定 `ties/2` 的既有边界、以及 P1-3 逐池 EV 相互耦合，须一并考虑验收口径；二是本轮的投影层是 P1-2 的位置与行动线前提，但**它本身不构成任何范围或质量证据**。
