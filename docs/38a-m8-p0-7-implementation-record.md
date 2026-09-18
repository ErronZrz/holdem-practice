# 38a M8：P0-7 教学参考与对手目标的分离契约——实施与验证回执

> 日期：2026-09-18。
>
> 本文件接在 `docs/38` 之后，沿用 `docs/30` D6 的编号族约定：`docs/38` 为规格与裁定冻结，本文件为同一轮的**实施与验证回执**。`docs/20` 至 `docs/38` 未被改写。
>
> 本文件只记录已实际落地的代码、测试与实跑输出；**不产生任何策略、质量或资源证据**。

## 1. 本轮提交与授权

| 次序 | commit | 内容 |
|---|---|---|
| 1 | `b6a0bbd` | `docs/38` 规格与裁定冻结（仅文档） |
| 2 | 本文件同批 | P0-7 实现、回归测试、前端最小改动、`docs/38a` |

用户答复原文（照录，四项均为推荐口径）：

- 执行确认：「确认执行 P0-7(按提示词的四项产出实施，先冻结 docs/38 规格、再提交实现)」
- 岔路一+二：「加响应字段 + API/UI 一致落位（推荐）(新增 reference_scope / reference_limitations 并与 reference_identity() 同源导出；API 响应与两处 UI 文案都用同一批字段，措辞明确「启发式-保守近似，非 GTO、非均衡解」)」
- 岔路三：「只写文档 + 守卫测试（推荐）(用守卫测试锁定「分析层不得另抄一套与策略重复的分支判据」，不引入插件接口，不触碰 strategy/)」
- 岔路四：「清单 + 回归锁定，不改判据（推荐）(逐条列出保护判据及适用域，用测试锁定其不被本轮改动)」

据此本轮**只做 P0-7**；裁定与改动面见 `docs/38` §1.2、§2、§3。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 4]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git rev-parse HEAD          -> 89a5a158cc3dfc79e480fe9ef93f68aac586f76c
$ git rev-parse origin/master -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
```

工作区干净、`HEAD` 短哈希 `89a5a15`（实测全哈希见上）、`ahead 4` 属未 push 的正常形态。未做任何 `reset` / `clean` / `stash` / `checkout`；**未 push**。`/Users/bryanylliu/holdem-campaigns/` 原样保留（8 个目录、14 条 authorization）。

## 3. 实际改动清单（文件级）

### 3.1 新增

| 文件 | 内容 |
|---|---|
| `backend/tests/test_review_reference_contract.py` | 参考契约回归测试（12 个用例）：可追溯、非 GTO 标注守卫、非众数不判错、保护判据冻结 |
| `docs/38`、`docs/38a` | 规格冻结与实施回执 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `backend/app/analysis/reference_identity.py` | 新增 `REFERENCE_SCOPE`（适用域）与 `REFERENCE_LIMITATIONS`（局限），新增 `reference_declaration()` 在 `reference_identity()` 之上叠加；**四个既有常量取值未变** |
| `backend/app/analysis/hand_review.py` | `build_review` 改展开 `reference_declaration()`；模块文档补一句「参考契约而非对手目标、参考分布由策略层唯一事实源生产」；**未改动任何参考/错误判据** |
| `backend/app/api/schemas.py` | `HandReview` 新增 `reference_scope: str` 与 `reference_limitations: list[str]`；既有四个参考字段语义与取值不变 |
| `backend/app/api/hands.py` | `get_review` 透传两个新字段，不在 API 层另写常量 |
| `frontend/src/reviewText.js` | 新增 `referenceScopeText(review)` 与 `referenceLimitationText(review)`，按响应字段渲染适用域与局限 |
| `frontend/src/components/HistoryView.vue` | 复盘头部补两行同源文案（适用域 / 局限） |
| `frontend/src/components/GameTable.vue` | 本手复盘面板补同样两行同源文案 |

### 3.3 未触碰（不可回退边界逐项核验）

- `backend/app/poker/**`：零改动（`equity` / `estimate_static_showdown_share` / `pot_projection` / 结算语义不变）。
- `backend/app/strategy/heuristic.py`：零改动；`HeuristicStrategy` 继续同时承担「当前生产对手」与「教学参考基线」，参考分布与决策语义零改动。
- `backend/app/storage/models.py`：零改动，**无新增列、无迁移**；`hands.history_json` 未被改写；真实数据库 `backend/data/holdem.db` 只读。
- `backend/uv.lock`、`frontend/package-lock.json`、`tools/trainer/**`：零改动。
- 未引入 `strategy/` 层的 reference 插件接口（岔路三按「只写文档 + 守卫测试」执行）。
- 未恢复前端策略选择器；未改质量判定门槛。

`git status` 实测改动面（无任何多余产物）：

```text
 M backend/app/analysis/hand_review.py
 M backend/app/analysis/reference_identity.py
 M backend/app/api/hands.py
 M backend/app/api/schemas.py
 M frontend/src/components/GameTable.vue
 M frontend/src/components/HistoryView.vue
 M frontend/src/reviewText.js
?? backend/tests/test_review_reference_contract.py
```

## 4. 参考契约的实际对外形态（实测抓取）

`GET /hands/{id}/review` 实际返回（截去 `decisions`）：

```json
{
  "hand_id": "a466425be60949ed85ca72bfefb3745e",
  "hand_number": 1,
  "human_seat": 0,
  "reference_strategy": "heuristic-conservative",
  "reference_version": 1,
  "evaluation_version": 1,
  "reference_coverage": "vs-random",
  "reference_scope": "翻牌后面对下注与无人下注的局面经过保守收窄；翻牌前与加注沿用启发式基线。",
  "reference_limitations": [
    "胜率口径为 vs 随机范围的静态近似，未做对手范围与位置建模。",
    "参考由启发式规则加保守收窄构成，属非均衡近似；不构成求解器或训练产物的质量结论。",
    "与参考动作或其分布众数不同，本身不构成错误；错误只来自既有判据。"
  ],
  "mistake_count": 0
}
```

来源（`reference_strategy`）、版本（`reference_version` / `evaluation_version`）、覆盖范围（`reference_coverage`）、适用域（`reference_scope`）与局限（`reference_limitations`）五项均可从响应直接追溯。

## 5. 新增测试与核验

新增 12 个用例（`196 → 208`）：

```text
$ uv run pytest -q --collect-only tests/test_review_reference_contract.py | tail -1
12 tests collected
```

| 验收项 | 对应用例 | 锁定的事实 |
|---|---|---|
| C1 可追溯 | `test_reference_declaration_extends_identity`、`test_review_uses_the_single_source_declaration`、`test_review_endpoint_declares_the_contract` | 六个契约字段逐字段等于唯一事实源的声明 |
| C2 单一事实源 | `test_reference_source_literal_is_single` | `heuristic-conservative` 在 `analysis/` + `api/` 中只出现一次（`reference_identity.py`） |
| C3 非 GTO 标注 | `test_limitations_disclose_scope_and_non_mode_rule`、`test_frontend_reference_text_has_no_solver_labels`、`test_both_review_views_render_scope_and_limitations` | 后端常量与前端展示层均无 `gto` / `nashconv` / `exploitab` / `最优`；「均衡」只出现在否定语境；两处视图均渲染适用域与局限 |
| C4 非众数不判错 | `test_mistake_detection_does_not_read_reference_distribution`、`test_non_mode_action_without_existing_rule_is_not_flagged`、`test_mistake_codes_come_only_from_existing_rules` | 判据函数签名与实现均不引用分布/众数；真实手牌中「动作 ≠ 众数且无既有判据命中 → `mistakes` 为空」；产出错误码 ⊆ 既有判据集合 |
| C5 保护判据未被改动 | `test_conservative_protection_constants_are_frozen`、`test_reference_semantics_versions_unchanged` | G1–G14 常量逐条冻结；`_fold_margin(100, 200) == 0.20`；三个版本号仍为 `1` |

**非众数用例的具体构造**（可复现）：2 人桌、真人为小盲（`button=0`）、底牌 `7c 2d`（垃圾牌）、公共牌 `Kc Qd 9h Ts 3c`；真人翻前补齐盲注（跟注 5）。该决策点的参考众数为**弃牌**（`HeuristicStrategy` 翻前对垃圾牌直接弃），真人动作是**跟注**——两者不同；而跟注额 ≤ 一个大盲触发既有的 limp 豁免，未命中任何既有判据，故 `mistakes == []`。这直接锁定「动作 != 众数本身不构成错误」。

**单一事实源核验（证据）**：

```text
$ grep -rn "heuristic-conservative" backend/app/
backend/app/analysis/reference_identity.py:11:REFERENCE_STRATEGY = "heuristic-conservative"
```

前端 `reviewText.js` 中的同名字符串是**显示映射的查找键**（后端取值 → 中文名），不是第二份来源事实源。

## 6. 实跑验证输出

```text
$ uv run ruff check .
All checks passed!

$ uv run pytest -q
208 passed, 2 warnings in 12.87s
（2 条 warning 来自第三方 starlette/anyio 弃用提示，非本轮引入）

$ cd frontend && npm run build
vite v6.4.3 building for production...
✓ 23 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.31 kB
dist/assets/index-C7nR2Wox.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-Bjv7RHTw.js   100.68 kB │ gzip: 37.64 kB
✓ built in 792ms
```

前端模块数仍为 `23`（本轮只改既有模块，未新增模块）；`dist/` 未进入版本控制。

## 7. 保护判据评审结论（只评审、不改动）

保护判据清单与适用域见 `docs/38` §3.4（G1–G14），本轮**全部保留原值、保留行为**，无一被放宽或删除：

- 跟注侧：`_FOLD_EV_MARGIN` / `_FOLD_BET_SCALE` / `_FOLD_MIN_EQ_PREFLOP` / `_BAD_CALL_EQ_MARGIN`、limp 豁免、`_is_made_hand` / `_dominated_pair` / `_has_playable_strength`（被压制对子不算可继续牌力）、`_STRONG_DRAW_OUTS` / `_DRAW_MARGIN_SCALE`（强听牌余量折半）、`_SMALL_BET_*`（小注例外）；
- 价值下注侧：`_weak_kicker_top_pair`、`_VALUE_BET_EQ`、`_UNDERBET_EQ` / `_UNDERBET_DEN`；
- 其它：`_SLOWPLAY_EQ`、`_OVER_AGGRESSIVE_EQ`、`_AIR_EQ`、`_EQUITY_SAMPLES`、`_REVIEW_SEED`。

`test_review.py` 的全部既有断言**未改动即通过**，与新增的常量冻结用例共同锁定「本轮未动判据」。适用域的边界声明同见 `docs/38` §3.4：以上判据均为 vs 随机静态近似下的复盘保守收窄，不构成行动价值比较或任何最优性判断。

## 8. 版本影响与兼容性（实测）

| 对象 | 实际行为 |
|---|---|
| 对外响应 | `HandReview` 新增两个字段（`reference_scope`、`reference_limitations`）；既有四个参考字段取值与语义不变，`test_games_api.py` / `test_review_versioning.py` 未改动即通过 |
| 版本号 | `reference_version` / `evaluation_version` / `cache_key_version` 仍为 `1`——本轮只新增声明性字段，未触及参考实现、保守判据、`equity` 实现、采样数与固定种子，按升版规则**不升版** |
| 缓存键 | 键格式与组成未变；`decision_cache_key` 不引入新段。局限/适用域属声明性信息，不参与决策定位，故不进键 |
| 旧历史 | 复盘仍按当前代码重评，但响应现在同时声明来源、版本、覆盖、适用域与局限，重评可被追溯且不再可能被当作求解器结论 |
| 旧前端 | 新字段对未知字段的旧客户端无影响（JSON 增字段）；`reference_strategy` 仍为 `"heuristic-conservative"` |
| 数据库 | 无新增列、无迁移、无回填；`history_json` 未被改写；`sessions` / `hands` 表结构未变 |
| 前端 | 两处复盘界面改为按响应字段渲染适用域与局限；未恢复策略选择器；未新增模块 |
| 参考语义 | `HeuristicStrategy` 与全部保守保护判据零改动 |

## 9. 边界声明与不得声称

- 本轮改动是**契约与标注**，**不是 CFR 接入**，也不构成任何质量证据；`docs/35` §4 清单中只有 P0-7 被授权。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实 EV 或生产可用策略。
- 本轮不存在代码内建的稳定性生产者；若有对照结论必须标注为「事后跨工件只读比较」（本轮无该类结论）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 未放宽或删除任何既有教学保护判据（G1–G14 全部保留）。
- 本轮未追加 seed、未新建冻结 campaign、未重试任何已消耗 authorization、未上云、未转 GPU、未扩预算；`/Users/bryanylliu/holdem-campaigns/` 原样保留。

## 10. 未做事项与下一步唯一建议动作

未做：

- 未实施 `docs/35` §4 清单中 P0-7 以外的任何一项；P0-2 / P0-3 / P0-6 与 P1 / P2 组全部未动。
- 未引入 `strategy/` 层的 reference 插件接口；未把参考实现抽象化或替换。
- 未改任何保护判据、质量判定门槛、`equity` / 池层投影 / 结算语义。
- 未给 `sessions` / `hands` 增加任何列；未迁移、未回填、未改写历史 JSON。
- 未实现缓存；未新增依赖；未恢复前端策略选择器。
- 未改动 `tools/trainer/`、锁文件与真实数据库；未新建 campaign、未追加 seed、未重试 authorization、未做云端操作。
- 未 push（`ahead 6` 由用户决定何时推送）。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**实施 `docs/35` §4.2 的 P0-6（CFR/教学上线质量门槛）**。理由：按 `docs/35` §4.3 的依赖链，`P0-7 → P0-6`，本轮已提供参考契约（来源/版本/覆盖/适用域/局限），门槛因此才有可签收的**作用对象与适用域**。但 P0-6 涉及门槛签收与超线处置，**必须单独授权并遵守更强的表述纪律**：若作用对象是 `probes.gains`，须先写入「以多 seed 结论为准、单 seed 不判定」（`docs/34b` §9.7），并说明是否区分 N=6 / N=7。**不建议**跳过该前提直接设阈值。
