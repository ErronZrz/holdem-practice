# 43a M8：P1-2 基于公开行动线的范围假设模型——实施与验证回执

> 日期：2026-09-18。
>
> 本文件接在 `docs/43` 之后，沿用 `docs/30` D6 的编号族约定：`docs/43` 为规格与裁定冻结，本文件为同一轮的**实施与验证回执**。`docs/20` 至 `docs/43` 未被改写。
>
> 本文件只记录已实际落地的代码、测试与实跑输出；**不产生任何策略、质量或资源证据**，也**未**实现采样、胜率、share、EV 或任何生产接入。

## 1. 本轮提交与授权

| 次序 | commit | 内容 |
|---|---|---|
| 1 | `3ea91400342396171b19567f67d1d5cb2275a3cf` | `docs/43` 规格与四项设计岔路裁定冻结（仅文档） |
| 2 | 本文件同批 | 范围假设模块、导出、回归测试、`docs/43a` |

用户答复原文（四项均为推荐口径，照录于 `docs/43` §1.2）：

- 执行确认与边界：「确认执行；trainer 与 poker 只读」；
- 岔路一+四：「新增独立模块，零接入」；
- 岔路二：「按公开行动线角色给显式起手牌类权重」；
- 岔路三：「不动 `reference_identity.py`」。

据此**被授权**并已使用：`backend/app/strategy/` 新增范围假设模块、`backend/tests/` 新增回归测试、新增 `docs/43*`。
**被拒绝**且本轮确实未做：`tools/trainer/**` 与 `backend/app/poker/**` 任何改动；`backend/app/analysis/**`（含 `reference_identity.py`）任何改动；`heuristic.py` 决策语义改动；任何生产接入（策略 / 复盘 / API / 前端）。

`backend/app/api/` 与 `docs/43` §1.2 未授权的其余层本轮**未被触碰**。

## 2. 实际基线核验（只读）

第二次提交前的基线（`docs/43` 已落地，工作区仅含本文件与代码改动）：

```text
$ git status --porcelain=v1 --untracked-files=all
 M backend/app/strategy/__init__.py
?? backend/app/strategy/range_assumption.py
?? backend/tests/test_strategy_range_assumption.py
```

`docs/43` 提交前已核验的起点基线与期望完全相符：`## master...origin/master [ahead 14]`、工作区 0 行、`HEAD = 0e5fd52fda69e6420e68c1d197d6b48b174c9946`、`origin/master = ef7e59282015e58f0e7fd153e30cd85ae6e9f56f`、campaigns = 8、11 份 `strategy.json`。未做任何 `reset` / `clean` / `stash` / `checkout`；未 push；未消耗任何本机实验预算。

## 3. 实际改动清单（文件级）

### 3.1 新增

| 文件 | 内容 |
|---|---|
| `backend/app/strategy/range_assumption.py` | 受控 profile `RangeProfile`、逐座位假设 `OpponentRange`、整体假设 `RangeAssumption`，以及 `HAND_CLASS_ORDER` / `weights_for_class_count` / `profile_for` / `known_profile_identifiers` / `register_range_profile` / `assign_opponent_roles` / `build_range_assumption` |
| `backend/tests/test_strategy_range_assumption.py` | 64 个用例：字段契约、169 顺序、档位与权重、受控目录、角色派生、整体覆盖、超范围明确失败、信息边界、版本化、无生产调用方、纯度 |
| `docs/43`、`docs/43a` | 规格冻结与实施回执 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/__init__.py` | **仅新增导出**（范围假设模块的常量、异常、模型与函数，共 23 个名字）；既有导出名与语义不变 |

### 3.3 未触碰（边界逐项核验）

- **零改动**：`backend/app/poker/**`（含 `engine.py`、`equity.py`、`estimate_static_showdown_share`、`pot_projection`、`_settle_showdown`）、`backend/app/analysis/**`（含 `reference_identity.py` 与 `hand_review.py`）、`backend/app/storage/**`。
- **零改动**：`backend/app/strategy/heuristic.py` 的决策语义、阈值与 `equity()` 调用；`random_strategy.py` / `interface.py` / `projection.py` / `abstraction.py` / `registry.py` / `artifact.py` / `lookup_budget.py` / `position_projection.py`。
- **零改动**：`backend/app/api/**`、`frontend/**`、`backend/data/holdem.db`、`backend/uv.lock`、`frontend/package-lock.json`。
- **零改动**：`tools/trainer/**`（含 `kuhn_cfr/**`）；本轮未引用其任何内容。

## 4. 范围假设层的实际形态

| 名称 | 实际语义 |
|---|---|
| `HAND_CLASS_ORDER` | 长度恰为 **169** 的元组，由**显式本地规则**生成（对子按 rank 降序 13 个；非对子按高牌降序、同低牌降序、同花先于非同花 156 个）；`AA` 居首、`32o` 居末。**是显式约定，不是牌力排序** |
| `RANGE_ROLES` | 闭集五值：`aggressor` / `caller` / `blind` / `unacted` / `folded` |
| `RANGE_ROLE_CLASS_COUNT_FIELDS` | 角色 -> profile 档位字段的**唯一映射**；测试锁定 `set(mapping) == set(RANGE_ROLES)` 且取值都在 `RANGE_PROFILE_FIELDS` 内 |
| `RangeProfile` | 冻结模型，恰好 9 字段；标识必须是 `name@version`；来源必须是「声明的模型假设」；档位必须 `0..169`；`folded_class_count` 必须为 `0`；单街主动下注/加注上限至少为 1 |
| `OpponentRange` | 冻结模型，恰好 5 字段；`weights` 长度恒为 169；`folded` 恒不争池且档位为 0；争池角色档位至少为 1；**权重必须与档位逐项一致**（禁止另行注入），使假设可审计 |
| `RangeAssumption` | 冻结模型，恰好 8 字段；结构版本必须为 `range-assumption.v1`；来源必须是声明的模型假设；`limitations` 必须含「非求解器输出」与「不随公共牌收窄」两条；`opponents` **恰好**覆盖除行动者外的全部相对座位、按升序、不重不漏 |
| `assign_opponent_roles` | 由 `public_action_line` 唯一派生：弃牌**跨街持久**；过牌归 `unacted`；仅盲注且无自愿动作者为 `blind`；行动者自身**不赋范围** |
| `weights_for_class_count` | 把档位换算成 169 项 `1.0`/`0.0` 前缀指示；越界或类型非法抛 `RangeContractError`，不夹紧 |
| `profile_for` / `known_profile_identifiers` | 受控目录查询；未知标识抛 `UnknownRangeProfileError`；目录只读（`MappingProxyType`） |
| `build_range_assumption` | 唯一构造入口：先校验投影、再取 profile、再校验未超建模范围、最后按角色装配；**不接收**公共牌、底池、筹码与任何真实底牌 |

内置目录登记一个 profile `action-line-roles@1`（来源＝声明的模型假设），档位：`aggressor 40` / `caller 80` / `blind 110` / `unacted 130` / `folded 0`，单街主动下注/加注上限 `1`。

### 4.1 两点如实标注的口径（不冒充精确）

1. **失败语义的分层**：**纯函数入口**（`weights_for_class_count` / `profile_for` / `assign_opponent_roles` / `build_range_assumption`）抛**分类型**契约异常（`RangeContractError` / `UnknownRangeProfileError` / `OutOfProfileError`，三者互不继承）；而由 **Pydantic 模型层**自洽校验拒绝的输入（来源标注、档位一致性、权重与档位不一致、`opponents` 覆盖不全、结构版本不符等）按 Pydantic 语义抛 `ValidationError`——这与 P0-3 的既有先例（`AbstractProjection` 用 `extra="forbid"` 拒绝未登记字段）一致。`docs/43` C9 的「明确失败且分型」由**入口**层面满足，模型层面由 `ValidationError` 兜底，两者都不静默回退。
2. **档位的性质**：`40 / 80 / 110 / 130` 四个数字**没有任何数据或求解器来源**，仅是为使假设可复现而**显式冻结**的取值；`HAND_CLASS_ORDER` 的排序同样只是**显式约定**。两者都不得被表述为「正确范围」「GTO 范围」或任何质量结论。

## 5. 新增测试（64 个）

```text
$ cd backend && uv run pytest -q --collect-only tests/test_strategy_range_assumption.py | tail -1
64 tests collected
```

| 验收项（`docs/43` §4.8） | 对应用例（节选） | 锁定的事实 |
|---|---|---|
| C1 基于公开行动线 | `test_roles_follow_the_public_action_line`、`test_roles_come_from_the_last_segment_only` | 角色只由 `public_action_line` 派生；翻前加注者在翻牌过牌后不再带收紧信息 |
| C2 明确是模型推断 | `test_assumption_declares_model_inference_and_limitations`、`test_assumption_rejects_a_solver_style_source`、`test_source_must_be_a_declared_assumption` | 来源恒为声明的模型假设；求解器口径被拒；两条必需局限齐备 |
| C3 不读取对手暗牌 | `test_assumption_ignores_hidden_cards_and_board`、`test_assumption_fields_carry_no_cards_or_amounts` | 替换对手暗牌后假设完全相等；字段集中无 `hole_cards` |
| C4 不读取未来牌 | `test_entry_accepts_only_the_public_projection`、`test_assumption_fields_carry_no_cards_or_amounts` | 入口只接受 `projection` 与 `profile_identifier`；字段集中无 `board` / `runout` |
| C5 与参考来源一起版本化 | `test_assumption_declares_model_inference_and_limitations`、`test_unknown_profile_identifier_fails`、`test_assumption_rejects_a_foreign_schema_version` | profile 标识 + 结构版本 + 来源三者齐备；未知标识与外版结构明确失败 |
| C6 角色派生正确 | `test_blind_role_requires_no_voluntary_action`、`test_check_does_not_narrow_the_assumed_range`、`test_fold_is_persistent_across_streets`、`test_folded_seat_is_not_an_aggressor`、`test_actor_is_not_given_a_range` | 五个角色逐条锁定；弃牌持久；过牌归 `unacted`；行动者不赋范围 |
| C7 起手牌类顺序确定 | `test_hand_class_order_is_169_unique_and_bounded` | 169 项、唯一、`AA` 首、`32o` 末、`AKs/AKo` 紧邻 |
| C8 权重与档位一致 | `test_weights_are_an_indicative_prefix`、`test_default_profile_declares_the_frozen_class_counts`、`test_opponent_range_rejects_inconsistent_weights` | 前缀指示正确；内置档位逐角色锁定；不一致权重被拒 |
| C9 明确失败且分型 | `test_second_aggressive_action_per_street_is_out_of_profile`、`test_malformed_token_is_out_of_profile`、`test_non_projection_input_is_a_contract_violation`、`test_error_types_are_distinct`、`test_weights_reject_out_of_range_or_illegal_input`、`test_contending_role_cannot_carry_an_empty_range`、`test_folded_role_cannot_contest_the_pot` | 三类异常互不继承；超建模范围、坏 token、类型错误各自失败；争池角色不得空范围 |
| C10 不接入任何生产路径 | `test_module_has_no_production_caller`、`test_module_never_imports_lookup_equity_analysis_or_storage`、`test_production_reference_identity_is_unchanged`、`test_contrast_coverage_mirrors_the_frozen_reference_identity` | 应用内除自身与包导出外无引用；不 import equity / engine / analysis / storage / llm / heuristic；参考身份取值不变；对照常量与 P0-5 事实源不漂移 |
| C11 2–9 人参数化 | `test_assumption_covers_every_other_seat`（2–9 人逐一） | `opponents` 恒为 `N − 1` 项且座位集合正确 |
| C12 不写回历史 | `test_build_does_not_mutate_the_projection`、`test_assumption_round_trips_through_json`、`test_assumption_is_frozen` | 输入不被改写；结果为可序列化的冻结值对象 |

## 6. 实跑验证输出

```text
$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
516 passed, 1 skipped, 2 warnings in 10.81s      （452 → 516，新增 64；1 skipped 为实测入口）

$ cd frontend && npm run build
vite v6.4.3 building for production...
✓ 23 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.31 kB
dist/assets/index-C7nR2Wox.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 508ms
```

前端产物文件名与体积（`index-Bjv7RHTw.js`，100.68 kB / gzip 37.64 kB）与 `docs/39a` §7、`docs/40a` §6、`docs/42a` §6 记录**逐字相同**，证明本轮改动未越出后端。`tools/trainer/` 未改动，故未运行其 `ruff` / `pytest`。

## 7. 版本影响与兼容性

| 对象 | 实际行为 |
|---|---|
| 既有策略语义 | **零改动**；`heuristic@1` 的阈值、分支与 `equity()` 调用完全不变 |
| 复盘与参考身份 | **零改动**；`hand_review.py` 与 `reference_identity.py` 未被触碰，`REFERENCE_VERSION` / `EVALUATION_VERSION` / `REFERENCE_COVERAGE` 取值不变 |
| API 与前端 | **零改动**；不新增或改名字段；缓存键不变 |
| 数据库 | **不加列、不迁移**；真实数据库只读，未被写入 |
| 旧历史 / 旧响应 / 旧前端 | 结构不变；`history_json` 未被改写；本轮不产生任何新字段或列 |
| 新模块 | 新增独立模块，仅新增导出；**目前无生产调用方**，不改变任何运行时路径 |
| 超建模范围局面的实际处置 | **不产生假设、不产生动作**；抛 `OutOfProfileError` 等分类型异常，无最近档 / 默认档 / 插值 |
| 预算 | 本轮未消耗任何实验预算（无受监督运行；仅单元测试与文档撰写） |

## 8. 边界声明与不得声称

- 本轮改动是**契约与假设模型层**，**不是** CFR 接入，也**不构成任何质量证据**。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- **不得**把范围假设表述为「正确范围」「GTO 范围」「已替代 vs 随机」「已实现范围化 EV」或「已覆盖真实局面」；它只是一份**显式声明的人为假设**，档位数字与排序约定均无数据或求解器来源。
- **不得**用「最近档」「补零」「掩码」「线性插值」把未覆盖局面冒充为已假设；本轮在结构上不提供这类路径，`folded` 的全零权重是「该对手已弃牌」的显式事实声明，不是近似。
- `equity()` 固定 `ties/2` 的边界（`docs/23` §2.1）与 `docs/23` §7 的禁止事项继续有效；本轮未触碰 `equity()`，也未把资格投影说成收益。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」；代码中仍**不存在**稳定性生产者。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据**（本轮即属此情况）。
- 未改写 `docs/20` 至 `docs/43`；未 push（`ahead` 数由用户决定何时推送）。

## 9. 未做事项与下一步唯一建议动作

未做：

- **未实现**采样、胜率、静态 share 或行动价值；把起手牌类权重组合成具体组合概率的步骤**未实现**（属后续单独授权）。
- **未接入**任何生产路径：`heuristic.py`、`hand_review.py`、API 与前端零改动；未新增或改名任何请求/响应字段。
- **未改动** `reference_identity.py`；未新增 coverage 取值；未升 `REFERENCE_VERSION` / `EVALUATION_VERSION`。
- **未实施**逐池货币收益、真实下注尺度与公共牌、性能复测（P1-3 / P1-4 / P1-5 全部未授权）。
- 未实施 `docs/35` §4 清单中 P1-2 以外的任何一项；P0 组与 P2 组全部未动。
- 未改动 `backend/app/poker/**`、`backend/app/analysis/**`、`storage/**`、锁文件与真实数据库；未改动 `tools/trainer/**`。
- 未新增受监督运行或 campaign；未追加 seed；未重试任何已消耗 authorization；未消耗实验预算；未做云端操作。
- 未改质量门槛或启用 `docs/39` 门槛；未放宽或删除任何既有教学保护判据。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按 `docs/35` §4.3 单独授权 P1-3（逐池货币收益：短码 / 边池 / 多人平局）**，并在实施前先冻结三点口径：一是**不得**把 `project_pot_layers()` / `project_candidate_call()` 的资格投影或 `estimate_static_showdown_share()` 的静态 pooled share 表述为逐池 EV；二是 `1/k` **不得**直接替换既有 `call_ev`，`equity()` 的固定 `ties/2` 边界不在本轮改动范围；三是逐层 eligible 集合、联合 runout、平局分配、实际支付与**明确的后续行动情景**必须逐项定义并配回归测试。
