# 37 M8：生产接入前置——P0-5 评估/参考版本化与历史重评隔离（规格冻结）

> 日期：2026-09-18。
>
> 本文件接在 `docs/36` / `docs/36a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/37` 记录本轮**规格与决策冻结**，`docs/37a` 记录**实施与验证回执**。`docs/20` 至 `docs/36a` 未被改写。
>
> 本文**不实施任何代码**。本轮范围仅限 `docs/35` §4.2 的 **P0-5（评估/参考版本化）** 一项；清单其余条目未被授权。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 授权与既定裁定

### 1.1 用户答复原文（逐项照录）

| 编号 | 问题 | 用户答复原文 |
|---|---|---|
| 主线 | 下一步是否就是 P0-5 | 「没问题」 |
| 岔路一 | 版本字段放哪 | 「四个岔路+前端按你建议」 |
| 岔路二 | 是否落库 | 同上 |
| 岔路三 | 是否本轮实现缓存 | 同上 |
| 岔路四 | 版本号怎么定 | 同上 |
| 前端 | 是否允许最小改动显示版本 | 同上 |
| 改动面与边界 | 允许文件/层与验收 | 「改动面和边界你自行决定即可」 |

### 1.2 本轮裁定（承接用户对“按你建议”的批准）

| 岔路 | 本轮建议（已被采纳） | 依据 |
|---|---|---|
| 一、版本字段放哪 | **保持 `reference_strategy` 既有取值不变**，另增独立字段 `reference_version` / `evaluation_version`（外加覆盖范围 `reference_coverage`） | `docs/20` §8.3「保持 `reference_strategy` 兼容，增加独立参考版本/评估版本」 |
| 二、是否落库 | **不落库**：版本为响应级常量，`hands.history_json` 与 `sessions` 均不改动；不新增列、不做迁移 | `docs/20` §8.4「建议避免首轮数据库迁移」；现状无持久化复盘结果 |
| 三、是否本轮实现缓存 | **只冻结键契约，不实现缓存**（`backend/app/llm/` 仍为空，M6 未授权） | `docs/20` §8.3「解释缓存」行；`docs/35` §4.2 P0-5 |
| 四、版本号怎么定 | 从 `1` 起计数；改动参考/评估实现即升版本；**不追溯改写**已产出的历史结论 | `docs/20` §5.2 |
| 前端 | 允许**最小改动**：把写死的参考文案改为按响应字段渲染并显示版本 | `docs/20` §5.2「UI 应如实标注…标明版本」 |

### 1.3 改动面与边界（本轮自行裁定）

**允许修改**：`backend/app/analysis/`、`backend/app/api/`、`frontend/src/`（最小必要）、`backend/tests/`。

**不得修改**：`backend/app/poker/**`（含 `equity`、`pot_projection`、结算）、`backend/app/strategy/heuristic.py`（参考实现语义零改动，`docs/35a` D4 = A 继续有效）、`backend/app/storage/models.py`（不加列、不迁移）、真实数据库 `backend/data/holdem.db`、锁文件、`tools/trainer/**`。

**不得**：改质量判定门槛、改保守保护判据、新增受监督运行或 campaign、追加 seed、重试 authorization、上云/转 GPU/扩预算。

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

工作区干净；`HEAD == bcb6743`（`docs/36` / `docs/36a` 两个提交尚未 push，属上一轮遗留，本轮不改变该状态）。未做任何 `reset` / `clean` / `stash` / `checkout`。

与本轮直接相关的只读事实核对：

```text
backend/app/analysis/hand_review.py:31   _REVIEW_SEED = 0
backend/app/analysis/hand_review.py:424  rng = random.Random(_REVIEW_SEED)
backend/app/analysis/hand_review.py:425  reference_bot = HeuristicStrategy(seed=_REVIEW_SEED)
backend/app/analysis/hand_review.py:434  "reference_strategy": "heuristic-conservative"   # 硬编码字面量
backend/app/api/schemas.py:198-206       class HandReview: 无版本字段
backend/app/api/hands.py:68-75           get_review 按字面量透传，无版本
backend/app/storage/models.py            无任何 version 列
backend/app/llm/                         仅一行包说明，无缓存实现
frontend/src/components/HistoryView.vue:217-219   写死「参考策略：启发式-保守（vs 随机胜率 + 底池赔率 + 牌力门槛）」
frontend/src/components/GameTable.vue:742-746     复盘面板显示参考动作但无参考身份
```

结论：**当前“参考身份”由一组未声明的量共同决定**（参考实现、保守判据、`equity` 版本、`_EQUITY_SAMPLES`、`_REVIEW_SEED`），对外只暴露一个固定字符串。任一量变化，旧手牌都会在同一标签下被静默重评（`docs/21` §6.4、`docs/23` §7 已点名）。

## 3. P0-5 规格（冻结）

### 3.1 版本身份三元组 + 覆盖范围

新增 `backend/app/analysis/reference_identity.py`，作为**唯一事实源**：

| 常量 | 值 | 含义 |
|---|---|---|
| `REFERENCE_STRATEGY` | `"heuristic-conservative"` | 参考来源标识；**保持既有取值**，不改成版本化字符串 |
| `REFERENCE_VERSION` | `1` | 参考实现版本（参考策略 + 保守收窄判据的实现） |
| `EVALUATION_VERSION` | `1` | 评估口径版本（胜率估计、采样数、固定种子与错误判据的整体） |
| `REFERENCE_COVERAGE` | `"vs-random"` | 覆盖范围标识：只做 vs 随机范围的静态近似，不含位置/范围建模 |
| `CACHE_KEY_VERSION` | `1` | 缓存键格式版本 |

并导出 `reference_identity() -> dict`，返回上述四个对外字段。

**升版规则（冻结）**：改动参考实现、保守判据、`equity` 实现、采样数或固定种子中的任一项，**必须同步升版本并在提交信息与回执中记录原因**；已产出的历史结论不得追溯改写。

### 3.2 对外响应

`HandReview` 新增三个必填字段，`reference_strategy` 语义与取值不变：

```text
reference_strategy: str    # 既有字段，值仍为 "heuristic-conservative"
reference_version: int     # 新增
evaluation_version: int    # 新增
reference_coverage: str    # 新增
```

`api/hands.py::get_review` 从 `build_review` 的返回值透传，不在 API 层另写常量。

### 3.3 决策级缓存键契约（冻结，不实现缓存）

新增纯函数 `decision_cache_key(...)`，冻结 `docs/20` §8.3 与 `docs/35` §4.2 要求的键组成：

```text
v{CACHE_KEY_VERSION} | hand_id | action_index | seat | input_digest
  | ref={REFERENCE_VERSION} | eval={EVALUATION_VERSION}
  | prompt={prompt_schema_version} | provider | model
```

约束：

1. **未来任何解释/评估缓存都必须用本函数产生的键**，不得退化为「仅按手牌 ID」缓存；
2. 参考版本或评估版本变化必须使键变化，从而**旧缓存不会套到新评估**；
3. 本轮**不引入任何缓存存储**，不新增依赖，不触碰 `backend/app/llm/`。

### 3.4 前端最小改动

1. 新增 `frontend/src/reviewText.js`：按响应字段生成参考说明文案（含参考版本、覆盖范围与评估口径版本）；
2. `HistoryView.vue`：删除写死的参考文案，改由该函数渲染；
3. `GameTable.vue`：复盘面板补一行同源文案（原先只显示参考动作却没有参考身份）。

### 3.5 验收口径

| # | 验收项 | 判据 |
|---|---|---|
| C1 | 版本可追溯 | `GET /hands/{id}/review` 返回 `reference_strategy` / `reference_version` / `evaluation_version` / `reference_coverage`，且与 `reference_identity()` 完全一致 |
| C2 | 单一事实源 | `hand_review` 与 API 层均不出现第二份参考/评估版本字面量（grep 可证） |
| C3 | 旧缓存不套到新评估 | 缓存键随 `REFERENCE_VERSION` / `EVALUATION_VERSION` 变化而变化；同输入下键确定 |
| C4 | 键组成完整 | 键必须包含 hand/decision 定位、输入摘要、版本、prompt/schema、provider/model，缺一不可 |
| C5 | UI 区分版本 | 两处复盘界面均显示版本，不再出现写死的参考文案 |
| C6 | 兼容与不可改写 | `reference_strategy` 取值不变；旧历史仍可复盘；`history_json` 不被改写；`sessions` 表无新增列 |
| C7 | 参考语义零改动 | `heuristic.py` 与保守判据零改动；既有 `test_review.py` / `test_games_api.py` 断言不变 |

## 4. 边界声明与不得声称

- 本轮**不接入 CFR**、不引入 lookup、不产生任何策略/质量证据；P0-5 只是“契约与标识”层的前置。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 本轮稳定性的对照仍不存在代码内建生产者；若出现对照结论必须标注为“事后跨工件只读比较”（本轮无该类结论）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 不得因本轮改动而放宽或删除任何既有的教学保护判据（弱踢脚、被压制对子、强听牌余量、limp 豁免）。

## 5. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码/测试/前端/锁文件/真实数据库；未实施 P0-5 的实现；未实施清单其余任何一项；未新建 campaign、未追加 seed、未重试 authorization；未做云端操作。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P0-5，并在 `docs/37a` 给出文件级改动、新增测试与 `ruff` / `pytest` / `npm run build` 的实跑输出。** 实施后，`docs/35` §4.3 的依赖建议指向 **P0-7（教学参考与对手目标的分离契约）**——它与本轮共享同一批参考身份字段，是风险次低、可直接复用本轮成果的下一项。
