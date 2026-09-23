# 37a M8：P0-5 评估/参考版本化与历史重评隔离——实施与验证回执

> 日期：2026-09-18。
>
> 本文件接在 `docs/37` 之后，沿用 `docs/30` D6 的编号族约定：`docs/37` 为规格与裁定冻结，本文件为同一轮的**实施与验证回执**。`docs/20` 至 `docs/37` 未被改写。
>
> 本文件只记录已实际落地的代码、测试与实跑输出；**不产生任何策略、质量或资源证据**。

## 1. 本轮提交与授权

| 次序 | commit | 内容 |
|---|---|---|
| 1 | `f325148` | `docs/37` 规格与裁定冻结（仅文档） |
| 2 | 本文件同批 | P0-5 实现、回归测试、前端最小改动、`docs/37a` |

用户答复原文（照录）：主线「没问题」；四个岔路与前端「四个岔路+前端按你建议」；改动面与边界「改动面和边界你自行决定即可」。据此本轮**只做 P0-5**，裁定与改动面见 `docs/37` §1.2、§1.3。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 2]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -3 --oneline
bcb6743 feat: add controlled strategy registry and p0-4 information boundary projection
ccf208e docs: freeze p0-1 strategy identity and p0-4 information boundary specs
ef7e592 docs: record decision addendum and opponent-upgrade preregistration
```

工作区干净。`docs/36` / `docs/36a` 两个提交仍未 push（上一轮遗留），本轮不改变该状态。未做任何 `reset` / `clean` / `stash` / `checkout`。

## 3. 实际改动清单（文件级）

### 3.1 新增

| 文件 | 内容 |
|---|---|
| `backend/app/analysis/reference_identity.py` | 参考/评估版本身份的唯一事实源：`REFERENCE_STRATEGY` / `REFERENCE_VERSION` / `EVALUATION_VERSION` / `REFERENCE_COVERAGE` / `CACHE_KEY_VERSION`，以及 `reference_identity()` 与 `decision_cache_key(...)` |
| `backend/tests/test_review_versioning.py` | 版本身份与缓存键契约测试（8 个用例） |
| `frontend/src/reviewText.js` | 按响应字段生成参考说明文案的显示辅助 |
| `docs/37`、`docs/37a` | 规格冻结与实施回执 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `backend/app/analysis/hand_review.py` | `build_review` 的返回值改为展开 `reference_identity()`，删除硬编码 `"heuristic-conservative"` 字面量；**未改动任何参考/错误判据** |
| `backend/app/api/schemas.py` | `HandReview` 新增 `reference_version` / `evaluation_version` / `reference_coverage`；`reference_strategy` 语义与取值不变 |
| `backend/app/api/hands.py` | `get_review` 透传三个新字段，不在 API 层另写常量 |
| `frontend/src/components/HistoryView.vue` | 删除写死的「参考策略：启发式-保守（vs 随机胜率 + 底池赔率 + 牌力门槛）」，改由 `referenceText(review)` 渲染 |
| `frontend/src/components/GameTable.vue` | 复盘面板补一行同源文案，使界面上出现的参考动作带有可追溯的参考身份 |

### 3.3 未触碰

- `backend/app/poker/**`：零改动（`equity` / `pot_projection` / 结算语义不变）。
- `backend/app/strategy/heuristic.py`：零改动，参考实现语义与分布不变（`docs/35a` D4 = A 继续有效）。
- `backend/app/storage/models.py`：零改动，**无新增列、无迁移**；`hands.history_json` 不被改写。
- `backend/app/llm/**`：零改动（未实现任何缓存）。
- 真实数据库 `backend/data/holdem.db`：只读、未写入。
- `tools/trainer/**`、`backend/uv.lock`、`frontend/package-lock.json`：零改动。

## 4. 新增/修改的测试与单一事实源核验

新增 8 个用例（`188 → 196`）：

```text
$ uv run pytest -q --collect-only tests/test_review_versioning.py | tail -1
8 tests collected in 0.60s
```

- 版本身份：常量取值冻结；`build_review` 与 `reference_identity()` 完全一致（单一事实源）；`GET /hands/{id}/review` 返回四个字段且与常量一致。
- 缓存键契约：同输入确定；键的**完整段列表**逐段断言（hand/decision 定位、输入摘要、参考版本、评估版本、prompt/schema、provider、model 缺一不可）；参考版本或评估版本变化即使键变化；决策定位与输入摘要变化也使键变化。

单一事实源核验（证据）——`heuristic-conservative` 在后端 `app/` 中**只出现一次**：

```text
$ grep -rn "heuristic-conservative" backend/app/
backend/app/analysis/reference_identity.py:11:REFERENCE_STRATEGY = "heuristic-conservative"
```

前端 `reviewText.js` 中的同名字符串是**显示映射的查找键**（后端取值 → 中文名），不是第二份版本事实源。

## 5. 实跑验证输出

```text
$ uv run ruff check .
All checks passed!

$ uv run pytest -q
196 passed, 2 warnings in 10.11s
（2 条 warning 来自第三方 starlette/anyio 弃用提示，非本轮引入）

$ npm run build   （frontend/）
vite v6.4.3 building for production...
✓ 23 modules transformed.
dist/index.html                   0.41 kB │ gzip:  0.31 kB
dist/assets/index-DVJEUzb7.css   10.28 kB │ gzip:  2.43 kB
dist/assets/index-DAUXjzsg.js   100.15 kB │ gzip: 37.48 kB
✓ built in 532ms
```

前端新增 1 个模块（`23 modules`，原 `22`）；`dist/` 未进入版本控制。

## 6. 版本影响与兼容性（实测）

| 对象 | 实际行为 |
|---|---|
| 对外响应 | `HandReview` 新增三个必填字段；`reference_strategy` 取值仍为 `"heuristic-conservative"`，既有断言 `test_games_api.py` 未改动即通过 |
| 旧历史 | 复盘仍按当前代码重评，但**响应现在声明了版本**（`heuristic-conservative` + `reference_version=1` + `evaluation_version=1` + `vs-random`），重评可被追溯 |
| 缓存 | 本轮不引入缓存存储；`decision_cache_key` 已使参考/评估版本参与键，将来任何缓存按此键即可避免「旧缓存套到新评估」 |
| 数据库 | 无新增列、无迁移、无回填；`history_json` 未被改写 |
| 前端 | 两处复盘界面改为按响应字段显示版本；未恢复策略选择器 |
| 参考语义 | `HeuristicStrategy` 与全部保守保护判据零改动；`test_review.py` 全部既有断言未改动即通过 |

**升版规则（已冻结，见 `docs/37` §3.1）**：改动参考实现、保守判据、`equity` 实现、采样数或固定种子中的任一项，必须同步升 `REFERENCE_VERSION` / `EVALUATION_VERSION` 并记录原因；已产出的历史结论不得追溯改写。

## 7. 边界声明与不得声称

- 本轮**未**接入 CFR、未引入 lookup、未产生任何策略/质量证据；P0-5 只是“契约与标识”层的前置。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 本轮不存在代码内建的稳定性生产者；若出现对照结论必须标注为“事后跨工件只读比较”（本轮无该类结论）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 未放宽或删除任何既有教学保护判据（弱踢脚、被压制对子、强听牌余量、limp 豁免）。
- 本轮未追加 seed、未新建冻结 campaign、未重试任何已消耗 authorization、未上云、未转 GPU、未扩预算；`/Users/bryanylliu/holdem-campaigns/` 原样保留。

## 8. 未做事项与下一步唯一建议动作

未做：

- 未实施 `docs/35` §4 清单中 P0-5 以外的任何一项；P0-7 / P0-6 / P0-2 / P0-3 与 P1 / P2 组全部未动。
- 未实现任何缓存（含解释缓存）；未新增依赖；未触碰 `backend/app/llm/`。
- 未给 `sessions` / `hands` 增加任何列；未迁移、未回填、未改写历史 JSON。
- 未恢复前端策略选择器；未改动 `frontend/` 的参考/对手语义。
- 未改动 `tools/trainer/`、锁文件与真实数据库；未新建 campaign、未追加 seed、未重试 authorization、未做云端操作。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**实施 `docs/35` §4.2 的 P0-7（教学参考与对手目标的分离契约）**。理由：它与本轮共享同一批参考身份字段（`reference_strategy` / `reference_version` / `reference_coverage`），是 `docs/35` §4.3 依赖链上 `P0-7 → P0-6` 的前置，且同样只涉及契约与标识、不引入新实验；`docs/35` §4.2 P0-7 的验收要求（旧保守保护单独评审、低频动作不因非众数判错、UI 如实标注来源与局限）可直接复用本轮的版本声明。**不建议**先做 P0-6：按 `docs/35` §4.3，门槛必须先有参考契约才有可签收的作用对象与适用域。
