# 40a M8：P0-3 抽象映射、覆盖与回退——实施与验证回执

> 日期：2026-09-18。
>
> 本文件接在 `docs/40` 之后，沿用 `docs/30` D6 的编号族约定：`docs/40` 为规格与裁定冻结，本文件为同一轮的**实施与验证回执**。`docs/20` 至 `docs/40` 未被改写。
>
> 本文件只记录已实际落地的代码、测试与实跑输出；**不产生任何策略、质量或资源证据**，也**未实现任何 lookup 与任何回退动作**。

## 1. 本轮提交与授权

| 次序 | commit | 内容 |
|---|---|---|
| 1 | `09b803c` | `docs/40` 规格与四个设计岔路裁定冻结（仅文档） |
| 2 | 本文件同批 | 抽象投影与覆盖判定模块、导出、单元测试、`docs/40a` |

用户答复原文（四项均为推荐口径，照录于 `docs/40` §1.2）：

- 执行确认与 `tools/trainer/**` 边界：「确认执行；trainer 只读」；
- 岔路一：「对齐训练器 m8/ 格式但不依赖」；
- 岔路二：「显式状态判定对象」；
- 岔路三：「只冻结契约与来源标注」。

据此**被授权**并已使用：`backend/app/strategy/` 新增抽象投影模块、`backend/tests/` 新增回归测试、新增 `docs/40*`、以及**最小必要**的 `backend/app/api/` 改动。
**被拒绝**且本轮确实未做：`tools/trainer/**` 任何改动；任何回退动作实现或策略分派路径改动；lookup 运行时与性能基准。

`backend/app/api/` 的授权本轮**未被使用**：判定层自足，无需改动任何请求/响应模型或路由。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 8]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -2 --oneline
8c6ca64 feat: add read-only multi-seed quality gate verdict without enabling a threshold
65cb4b2 docs: freeze p0-6 cfr quality gate definition without enabling a threshold

$ git rev-parse HEAD          -> 8c6ca6464b02e52ed36b092401d17729ddc423fe
$ git rev-parse origin/master -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
```

工作区干净；`ahead 8` 属未 push 的正常形态。未做任何 `reset` / `clean` / `stash` / `checkout`；**未 push**；未消耗任何本机实验预算。

本轮结束前的改动面实测（**无任何多余产物**）：

```text
 M backend/app/strategy/__init__.py
?? backend/app/strategy/abstraction.py
?? backend/tests/test_strategy_abstraction.py
```

## 3. 实际改动清单（文件级）

### 3.1 新增

| 文件 | 内容 |
|---|---|
| `backend/app/strategy/abstraction.py` | 受控抽象投影 `AbstractProjection`、覆盖判定 `CoverageVerdict`、回退声明 `FallbackDeclaration`，以及 `build_abstract_projection` / `judge_coverage` / `build_abstraction_key` / `require_in_abstraction` / `judge_game_state_coverage` / `declared_fallback` |
| `backend/tests/test_strategy_abstraction.py` | 60 个用例：字段齐备、键格式、抽象外/版本不匹配/不完整信息集的独立失败、无最近桶、回退来源标注、信息边界、2–9 人参数化 |
| `docs/40`、`docs/40a` | 规格冻结与实施回执 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/__init__.py` | **仅新增导出**（抽象模块的常量、异常、模型与函数，共 21 个名字）；既有导出名与语义不变，未新增 `known_identifiers` / `spec_for` 等本轮不需要的导出 |

### 3.3 未触碰（边界逐项核验）

- **零改动**：`backend/app/poker/**`（含 `equity` / `estimate_static_showdown_share` / `pot_projection` / `_settle_showdown`）、`backend/app/analysis/**`、`backend/app/storage/**`（含 `models.py`，未加列、未迁移）。
- **零改动**：`backend/app/api/**`、`frontend/**`、`backend/data/holdem.db`、`backend/uv.lock`、`frontend/package-lock.json`。
- **零改动**：`tools/trainer/**`（含 `kuhn_cfr/**`）；训练器只被**只读**引用为其键格式的规范出处，代码中不导入、不读取、不执行其内容。
- `backend/app/strategy/heuristic.py`、`random_strategy.py`、`interface.py`、`projection.py`、`registry.py` 的决策语义与分派语义**零改动**。

## 4. 判定层的实际形态

| 名称 | 实际语义 |
|---|---|
| `ABSTRACTION_PROJECTION_FIELDS` | 恰好五项：`game_version` / `player_count` / `relative_actor` / `own_rank` / `canonical_public_history`；字段集即契约，`AbstractProjection` 用 `extra="forbid"` 拒绝未登记字段 |
| `ABSTRACTION_GAME_VERSION` | `m8-a-v1`；`ABSTRACTION_KEY_PREFIX = "m8"`；`ABSTRACTION_ROOT_HISTORY = "-"`；`ABSTRACTION_TRAINED_PLAYER_COUNTS = {6, 7, 9}`——全部为**后端本地常量**，不依赖训练器 |
| 抽象键 | `m8/{game_version}/n={N}/actor={relative_actor}/rank={own_rank}/history={canonical_public_history}`，与训练器既有格式**逐字对齐** |
| `CoverageVerdict` | 冻结模型；`coverage` 取 `in-abstraction` / `out-of-abstraction` / `incomplete-infoset` / `version-mismatch` 四值之一；同时携带规范键（仅抽象内）、投影（仅抽象内）与**判定原因列表** |
| `judge_coverage` | 纯函数；字段缺失 → 不完整信息集；版本不一致 → 版本不匹配；字段齐备但人数不在 `{6,7,9}`、行动者/rank 越界、历史非该抽象的规范公开决策历史、或历史派生行动者与给定行动者不一致 → 抽象外 |
| `judge_game_state_coverage` | 从生产快照出发：先经 `project_for_actor`（P0-4）只读行动者视角；人数不在 `{6,7,9}` 直接判抽象外，人数匹配则**如实**记为不完整信息集并逐项列出缺少什么 |
| `build_abstraction_key` | 只接受判定为抽象内的投影；其余情形抛明确异常，**不返回近似键** |
| `require_in_abstraction` | 把判定结果转成**分类型异常**：`IncompleteInfosetError` / `VersionMismatchError` / `OutOfAbstractionError` |
| `declared_fallback` | 抽象内返回 `None`；其余三种结论产出**回退声明**，来源必须是 P0-1 注册表内的规范标识，声明恒为「非精确解」 |
| `FallbackDeclaration` | 冻结模型；`fallback_identifier` 校验必须在 `known_identifiers()` 内；`triggering_coverage` 校验不得为抽象内；`is_exact_solution` 校验不得为 `True` |

落地口径（与 `docs/40` §4 一致）：

1. **不重造脱敏**：从快照出发的入口先调用 P0-4 的 `project_for_actor`，模块自身不新增第二套信息边界；
2. **不复用训练器代码**：公开历史的规范性与可达性由后端**本地**校验器（`_derive_decision_history`）判定；它不导入训练器、不改写历史、不做补全；
3. **无最近桶**：抽象外一律不产生键；判定对象在抽象外时 `abstraction_key` 与 `projection` 均为 `None`；
4. **回退只是声明**：`declared_fallback` 不执行动作、不改动 `registry` / `games.py` 的任何分派路径；本轮**没有**任何运行时可用的回退行为；
5. **快照入口不代劳映射**：`judge_game_state_coverage` 接受**没有**投影参数——真实局面到抽象投影的映射属 P1-1 / P1-4，本函数不假装能完成它。

## 5. 新增测试（60 个）

```text
$ cd backend && uv run pytest -q --collect-only tests/test_strategy_abstraction.py | tail -1
60 tests collected
```

| 验收项（`docs/40` §4.8） | 对应用例 | 锁定的事实 |
|---|---|---|
| C1 字段齐备 | `test_projection_field_set_is_exactly_the_contract`、`test_projection_rejects_unregistered_fields`、`test_build_projection_returns_the_contract_record` | 字段集恰好五项；未登记字段（如 `board`）被拒；构造入口返回契约记录 |
| C8 键格式对齐 | `test_key_matches_the_declared_format_at_root`、`test_key_matches_the_declared_format_mid_history`、`test_build_abstraction_key_uses_the_same_format` | 根历史与中段历史的键逐字等于冻结格式（含 `-` 与相对行动者） |
| C2 抽象外明确失败 | `test_untrained_player_count_is_out_of_abstraction`、`test_history_outside_abstraction_fails`、`test_actor_or_rank_out_of_range_is_out_of_abstraction`、`test_history_actor_must_match_relative_actor` | 人数、历史形式/可达性、行动者与 rank 越界、行动者不一致均判抽象外且不产生键 |
| C3 版本不匹配明确失败 | `test_version_mismatch_fails` | 非 `m8-a-v1` 的版本一律版本不匹配 |
| C4 不完整信息集明确失败 | `test_missing_field_is_incomplete_infoset`（五项字段各一次） | 任一字段缺失 → 不完整信息集，且**不等于**抽象外 |
| 契约违规 | `test_structural_illegal_input_raises_contract_error` | 类型错误（字符串人数、整数历史、布尔冒充整数）抛 `AbstractionContractError` |
| C9 无最近桶 | `test_out_of_abstraction_never_yields_a_key`、`test_build_abstraction_key_rejects_unresolved_history`、`test_require_in_abstraction_raises_typed_errors` | 抽象外不返回键；生成键与要求抽象内均抛**分类型**异常 |
| C5 回退来源标注 | `test_declared_fallback_is_traceable_and_labeled`、`test_declared_fallback_is_reproducible`、`test_declared_fallback_is_none_in_abstraction`、`test_fallback_source_must_be_registered`、`test_fallback_declaration_cannot_claim_exactness_or_coverage` | 来源在注册表内、携带触发取值与原因、同输入同声明、抽象内不产生声明、未注册来源与「精确解/抽象内」标注均被拒 |
| C6 不读对手暗牌与未来牌 | `test_projection_carries_no_hidden_or_future_fields`、`test_game_state_verdict_ignores_hidden_and_future_cards`、`test_game_state_verdict_reads_only_actor_view` | 模型字段不含底牌/公共牌/seed 等；替换对手暗牌与公共牌后判定完全相等 |
| C7 2–9 人参数化 | `test_coverage_is_parameterized_by_player_count`、`test_game_state_coverage_is_parameterized_by_player_count` | 2–9 人逐人数判定；仅 `{6,7,9}` 可判抽象内，其余为抽象外；**未写死两人** |

## 6. 实跑验证输出

```text
$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
268 passed, 2 warnings in 10.27s          （208 → 268，新增 60）

$ cd frontend && npm run build
✓ 23 modules transformed.
dist/assets/index-C7nR2Wox.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 514ms
```

前端产物文件名与体积（`index-Bjv7RHTw.js`，100.68 kB / gzip 37.64 kB）与 `docs/39a` §7 记录**逐字相同**，证明本轮改动未越出后端；后端测试数由 208 增至 268（+60），无既有用例被修改或删除。`tools/trainer/` 未改动，故未运行其 `ruff` / `pytest`。

## 7. 版本影响与兼容性

| 对象 | 实际行为 |
|---|---|
| 既有策略语义 | **零改动**；`heuristic@1` / `random@1` 的决策分布与参考口径不变 |
| 策略分派与 API | **零改动**；未新增运行时回退行为，未改任何请求/响应字段，未恢复已移除的前端策略选择器 |
| 数据库 | **不加列、不迁移**；真实数据库只读，未被写入 |
| 旧历史 / 旧响应 / 旧前端 | 结构不变；`history_json` 未被改写；本轮不产生任何新字段或列 |
| 抽象外局面的实际处置 | 不产生键、不产生动作；判定为 `out-of-abstraction` / `incomplete-infoset` / `version-mismatch`，并可由调用方获取**声明式**回退来源标注 |
| 真实局面的处置 | 人数不在 `{6,7,9}` 直接判抽象外；人数匹配时如实判不完整信息集——**未**被表述为已覆盖 |
| `backend/app/strategy/__init__.py` | 仅新增导出，既有导出名与语义不变 |
| 预算 | 本轮未消耗任何实验预算（无受监督运行；仅单元测试与文档撰写） |

## 8. 边界声明与不得声称

- 本轮改动是**契约与失败语义**，**不是** CFR 接入，也**不构成任何质量证据**；`backend/app/strategy/` 仍无任何 CFR lookup 或产物加载。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- **不得**把回退路径表述为「已覆盖」「已支持 CFR」或「精确解」；本轮的回退**只是声明的来源标注**，没有对应动作实现。
- 真实局面与受限抽象的落差（`docs/40` §3.3）在本轮代码中如实体现：快照入口**不假装**能完成映射，也不给出任何近似结论；**未**使用「最近桶」「补零」「掩码」「插值」。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」；代码中仍**不存在**稳定性生产者。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据**（本轮即属此情况）。
- 未改写 `docs/20` 至 `docs/39a`。
- 未 push（`ahead 10` 由用户决定何时推送）。

## 9. 未做事项与下一步唯一建议动作

未做：

- **未实现** lookup 运行时、产物加载、覆盖率统计与性能/内存基准（属 P0-2，未授权）。
- **未实现**任何回退动作；未改动 `registry` / `games.py` 的策略分派路径；未新增任何运行时兜底行为。
- 未实施 `docs/35` §4 清单中 P0-3 以外的任何一项；P0-2 与 P1 / P2 组全部未动。
- 未改动 `backend/app/api/**`（授权但本轮不需要）、前端、`poker/**`、`analysis/**`、`storage/**`、锁文件与真实数据库。
- 未改动 `tools/trainer/**`；未新增 JSON schema 或依赖。
- 未新增受监督运行或 campaign；未追加 seed；未重试任何已消耗 authorization；未消耗实验预算；未做云端操作。
- 未改质量门槛或启用 `docs/39` 门槛；未放宽或删除任何既有教学保护判据。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**实施 `docs/35` §4.2 的 P0-2（实时 lookup 性能与内存预算）**。理由：按 `docs/35` §4.3 的依赖，P0-3 已完成，P0 组只剩 **P0-3 → P0-2** 这条链路——先有覆盖与回退定义，P0-2 的 lookup 性能基准才有**可比口径**（否则测的是没有覆盖定义的查询）。

给 P0-2 的两点口径提醒：`<100ms` 是**实时 Bot 决策**预算，不是整手复盘预算；P0-2 需单独授权，且应先明确「冷加载 / 常驻内存 / 决策 p95-p99 / 超时数」的测量口径与逐人数（重点 6/7/9）报告格式，再考虑是否存在可测的 CFR 产物。
