# 13 M5 复盘「参考动作」保守化（修复跟注建议偏松）

> 本文档记录在 `12-m5-review-quality-tuning.md` 之后，针对「复盘参考动作偏松」问题所做的一轮修复，作为 `12` 之后的实现快照。
>
> **文档权威性**：遵循 `03-execution-plan.md` 第 8 节约定，本文档是 `12` 之后的「实现快照」，与其冲突时以本文档为准。

---

## 1. 背景与目标

复盘会显示「参考：跟注」，但该跟注并不合理：用**高张**或**仅靠公共牌成对**的牌去跟注下注。根因是三因素叠加：

1. **口径**：`equity` 是「vs 随机」摊牌胜率，面对下注时被系统性高估；
2. **判据缺牌力要求**：`heuristic.py` 翻牌后面对下注只要 `equity >= pot_odds` 就跟注，唯一门槛 `_AIR_EQ = 0.25` 太低，高张轻松越过；
3. **反向隐含赔率（RIO）**：高张「看着能赢随机牌」，成对后（弱踢脚）仍常输给对手更强成牌。

本轮目标：**只收紧复盘的参考动作**，保持简单——不引对手范围建模、不引 CFR，也**不改变实盘 Bot 行为**。

---

## 2. 诊断（本地 159 手）

把「参考=跟注」的翻牌后决策点按实际牌力分组，B 组为不合理建议：

| 组 | 公共牌 | 底牌 | 牌力 | 胜率 | 赔率 |
|---|---|---|---|---|---|
| A | Th 3d 6c | T9o | 顶对 | 74.9% | 33.3% |
| A | Ad Ks 7c 6h | A2o | 顶对 A | 73.6% | 25.0% |
| A | Kd Td 6c 9d | KAh | 顶对 K | 52.4% | 25.0% |
| B | 7d Ac Ks | Q8o | Q 高，无听牌 | 48.8% | 33.3% |
| B | 8h Th 4d | AQo | A 高，无听牌 | 54.8% | 33.3% |
| B | 5c 3h 5h | AJo | A 高（对子是公共牌的 5） | 59.1% | 33.3% |
| B | 5s 5d 7c | A9o | A 高（对子是公共牌的 5） | 54.9% | 33.3% |
| B | Ah 7s 7d | KQo | K 高（对子是公共牌的 7） | 59.6% | 33.3% |
| B | Qd 5c 4h 4d | A6o | A 高（对子是公共牌的 4） | 48.9% | 33.3% |
| B | 2s Ts 2c | K3o | K 高（对子是公共牌的 2） | 50.1% | 33.3% |

B 组胜率均高于赔率（33.3%），故**不会被 `bad_call` 命中**，唯一表现就是 `bot_action` 显示成「参考：跟注」。这说明问题定位在**参考动作口径**，而非错误检测。

---

## 3. 改动

只动复盘层，**不改实盘 Bot**（`strategy/heuristic.py` 仅把补牌统计 `_draw_outs` 提升为公开 `draw_outs` 供复盘复用，行为不变）。

| 文件 | 改动 |
|---|---|
| `app/analysis/hand_review.py` | 新增保守参考动作 `_conservative_action` 与牌力判据 `_is_made_hand` / `_has_playable_strength`；`bad_fold` 复用同一牌力门槛；`reference_strategy` 由 `heuristic` 改为 `heuristic-conservative` |
| `app/strategy/heuristic.py` | `_draw_outs` → 公开 `draw_outs`（无行为变化） |
| `tests/test_review.py` | 同步 `_detect_mistakes` 新签名，新增 6 个用例 |
| `tests/test_games_api.py` | `reference_strategy` 断言改为 `heuristic-conservative` |
| `frontend/src/components/GameTable.vue`、`HistoryView.vue` | 参考策略文案改为「启发式-保守」；复盘区展示可一键复制的手牌 ID |
| `frontend/src/clipboard.js` | 新增 `copyText`：优先 Clipboard API，非安全上下文回退到临时输入框 |

### 保守参考动作判据

以 heuristic 的 `choose_action` 为基线，**仅在「翻牌后且面对下注」且基线建议跟注时介入**，改为「跟注需同时满足」：

1. **赔率有余量**：`equity > pot_odds + margin`，`margin = 0.15 + 0.10 × 跟注占底池比例`（与 `bad_fold` 同一套，保持对称）；
2. **有可继续的牌力**（满足其一）：
   - 真实成手牌：底牌参与成牌（口袋对 / 与公共牌配对），或公共牌本身构成三条及以上；**排除「仅靠公共牌成对」**；
   - 强听牌：补牌数 ≥ 8（开放式顺子 / 同花听牌）；
   - 例外：跟注额很小（`to_call × 3 ≤ pot`）时放宽，高张也可便宜看牌。

加注、翻牌前与无人下注的动作**原样沿用** heuristic，避免扩大影响面。

阈值常量集中于 `hand_review.py` 顶部：

| 项 | 值 | 含义 |
|---|---|---|
| `_STRONG_DRAW_OUTS` | `8` | 强听牌补牌数下限 |
| `_SMALL_BET_NUM / _SMALL_BET_DEN` | `1 / 3` | 小注例外：跟注额 ≤ 底池的 1/3 |

### 与 `bad_fold` 的一致性

本地 4 处残留 `bad_fold` 恰好就是 B 组那批「高张/仅公共牌成对」的牌（`A9o/5s5d7c`、`AQo/8hTh4d`、`KQs/Ah7s7d3h`、`AJo/5c3h5h`，补牌数全为 0）。若只收紧参考动作，会出现「`bad_fold` 说该跟、参考却说弃」的自相矛盾。因此 `bad_fold` 复用同一牌力门槛（属**进一步收窄**，未回退 `12` 的容差与翻牌前胜率下限）。

---

## 4. 与 `11` / `12` 的偏差

| 点 | 旧表述 | 本轮落地 |
|---|---|---|
| 参考标准 | 参考 Bot 固定为 `heuristic` | 改为「启发式-保守」，`reference_strategy = "heuristic-conservative"` |
| 参考动作判据 | 直接取 `HeuristicStrategy` 结果 | 翻牌后面对下注额外要求「赔率余量 + 可继续牌力」，小注放宽 |
| `bad_fold` 判据 | `equity > pot_odds + margin`（+ 翻牌前胜率下限） | 追加「底牌有可继续的牌力」（仅翻牌后） |
| 实盘 Bot | — | **未改变**，`12` 之前的对局行为与既有策略测试不变 |

---

## 5. 效果（同一批 159 手，155 手可重放）

「参考=跟注」的翻牌后决策点按牌力分组：

| 牌力 | 调整前 | 调整后 |
|---|---|---|
| air | 3 | 0 |
| 仅公共牌成对 | 8 | 0 |
| 真实成手牌 | 8 | 6 |
| 公共牌三条及以上 | 2 | 0 |
| **合计** | **21** | **6** |

错误标记总数 **49 → 45**：

| code | 调整前 | 调整后 |
|---|---|---|
| `bad_fold` | 4 | 0 |
| `bad_call` | 35 | 35 |
| `value_missed` | 3 | 3 |
| `slowplay` | 3 | 3 |
| `underbet` | 4 | 4 |

被收紧为弃牌的 15 个决策点均为**合理收紧**：无听牌高张、仅公共牌成对、弱对子（低于公共牌的对子）或低胜率公共牌三条；A 组顶对（胜率 52%~75%）全部保留为跟注。

---

## 6. 遗留与后续

- **仍为「vs 随机」口径**：保守判据只压低了「面对下注」的乐观度，未做对手范围建模；`equity` 数字本身仍偏乐观。
- **参考 ≠ 实盘 Bot**：本轮刻意让「教练标准」严于「对手打法」，两者解耦；若后续要把该门槛下沉到实盘 Bot，需另用独立的 EV 阈值，**不可直接复用 `bad_fold` 的 `margin`**（否则会弃掉三条等强牌）。
- **公共牌三条被 margin 收紧**：面对接近底池的下注，公共牌三条（弱踢脚，胜率约 0.66）会被判为弃牌，属「保守」取向，留待按需微调。
- **`bad_call` 未同步**：跟注侧仍按 `equity < pot_odds - 0.03` 判定，未与保守参考动作对齐，避免扩大改动面。

---

## 7. 测试与验收

```text
$ uv run ruff check .        # All checks passed
$ uv run pytest -q           # 112 passed, 2 warnings
```

- `test_review.py` 新增：`_detect_mistakes` 牌力门槛（高张不判误弃 / 成手牌判）、保守参考动作的高张收紧、顶对跟注、强听牌跟注、小注例外、加注/弃牌原样沿用。
- `test_games_api.py`：`reference_strategy` 断言更新为 `heuristic-conservative`。
- 2 条 warning 仍来自 `fastapi.testclient` 依赖（starlette/httpx 弃用提示），与本轮改动无关。
