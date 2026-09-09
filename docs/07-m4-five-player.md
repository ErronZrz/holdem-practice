# 07 M4 五人桌实现记录

> 本文档记录 M4（开放 5 人桌：1 真人 + 4 Bot，启用 side pot / 位置轮转）以及其后的体验增强（摊牌牌型与底池归属展示）落地的实现细节与关键决策，作为后续 M5~M8 的开发依据。
>
> **文档权威性**：遵循 `03-execution-plan.md` 第 8 节约定，本文档是 `06` 之后的「实现快照」。当本文档与 `01`~`06` 冲突时，**以本文档为准**。

---

## 1. 交付内容总览

| 层 | 文件 | 变更 |
|---|---|---|
| 前端 | `src/components/GameTable.vue` | 通用 N 人环形座位布局（替换 HU 顶部/底部布局）；创建表单支持 2 人 / 5 人快捷选择；摊牌牌型与底池归属展示 |
| 前端 | `src/components/HistoryView.vue` / `src/cards.js` | 手牌详情摊牌展示；新增 `cardText` / `HAND_CATEGORY_CN` |
| 后端 | `app/poker/evaluator.py` | 新增 `best_five`（从 5~7 张返回最佳 5 张） |
| 后端 | `app/poker/engine.py` | 摊牌结算时记录 `showdown_hands` / `pot_results`（只读明细，不改结算逻辑） |
| 后端 | `app/api/games.py` / `schemas.py` / `storage/hand_history.py` | 对外暴露摊牌牌型与边池归属 |
| 测试 | `tests/test_multiplayer_api.py` 等 | 5 人桌位置轮转 / 连续打满 / side pot 守恒；`best_five` 与摊牌字段 |

---

## 2. 关键设计决策

### 2.1 环形座位布局（前端）

- 座位 0（真人）固定在底部中央，其余座位按座位号顺时针均匀分布在椭圆上。
- 定位公式：`角度 = 90° + seat × (360°/N)`，映射到椭圆横向/纵向半径，适配 2~10 人（N=2 时自然退化为上下对坐）。
- 当前行动座位（`GameView.current_seat`）高亮，便于在多人逐帧推进时看清轮到谁。

### 2.2 多人桌复用 M3 的惰性推进

- 后端 `_advance_if_bot_turn` 以 `bot_seats` 列表判断，对任意多个 Bot 通用；每次 `GET /games/{id}` 推进**一个** Bot 动作，多个 Bot 轮流行动时逐个播放。
- 位置轮转、盲注位置、side pot 切分与未跟注退还均由引擎承担（M1 已按 N 人实现并通过 `test_simulation` 多人压力测试）。

### 2.3 位置策略（暂缓）

- 依 `02` D7「Bot 初期不做位置感知」，M4 继续使用统一 `HeuristicStrategy`，未注入位置维度。
- 位置感知作为后续增强（M5 错误检测或 M8 CFR 抽象时一并评估）。

### 2.4 摊牌牌型与底池归属展示

- 摊牌时，引擎在 `_settle_showdown` 中额外记录两处只读明细，**不改变既有结算逻辑**：
  - `showdown_hands`：每个未弃牌玩家的最佳 5 张牌（`evaluator.best_five` 从底牌 + 公共牌 7 选 5）。
  - `pot_results`：每个边池的金额、赢家与每人份额（含余数按座位号升序分配）。
- 序列化层（`hand_history`）与接口层（`build_game_view`）据此暴露 `showdown_hands` / `pot_results`，牌型名由前端 `HAND_CATEGORY_CN` 映射为中文。
- 排序：`evaluator.sort_five` 按牌型语义排序——对子/三条/葫芦先排相同点数、踢脚从大到小；顺子/同花顺从小到大（轮子 `A-2-3-4-5` 的 A 记低排最前）。
- 前端展示：牌桌座位旁与历史详情里用小尺寸卡片（`PlayingCard` 的 `small` 属性，复用底牌样式）显示牌型 + 排序后的 5 张牌，控制区/详情显示「底池金额 → 赢家（并列时列每人份额）」。

---

## 3. 与 06 的偏差

| 点 | 06 表述 | 实际落地 |
|---|---|---|
| 前端布局 | 06 按「真人底部 + Bot 顶部」渲染 | 改为通用 N 人环形/椭圆布局，HU 只是 N=2 的特例 |
| 后端接口 | 06 已支持 `num_players>2` | 多人桌路径复用不改动；另为摊牌展示新增 `best_five` / 引擎只读明细 / 接口字段 |

---

## 4. 测试与验收

```text
$ uv run ruff check .        # All checks passed
$ uv run pytest -q           # 58 passed, 2 warnings（五人桌 + best_five + 摊牌字段）
$ cd frontend && npm run build   # built successfully
```

新增覆盖：

- 5 人桌首手位置：庄位 0（真人）、小盲 1、大盲 2，preflop 首个行动者 = 大盲左侧（seat 3），开局即由 Bot 先行动。
- 5 人桌连续打满 3 手：无非法动作、无死锁，对局正常结束，统计正确。
- 5 人桌 side pot 守恒：每手 Hand History 的 `net` 求和为 0（覆盖边池与未跟注退还）。
- 摊牌字段：`best_five` 7 选 5 后牌力与全 7 张一致；摊牌时 `showdown_hands` 含未弃牌玩家各 5 张牌、`pot_results` 边池分配守恒。

端到端冒烟（真实 `BOT_DELAY=1s`）：5 人桌开局后 Bot 逐个行动（seat3 弃牌 → 1s 后 seat4 弃牌 → 轮到真人），验证多 Bot 逐帧播放节奏正确。

---

## 5. 后续注意事项

- **尚未 commit**：M4 完成后按用户要求暂未提交，待确认后统一提交。
- 多人桌 UI 可进一步打磨：下注筹码动画、边池可视化、座位高亮样式等（体验优化，非阻塞）。
- 下一阶段候选：M5（Review Engine）或 M6（DeepSeek Coach）或 M3.6（云部署，需云服务器 + Docker）。
