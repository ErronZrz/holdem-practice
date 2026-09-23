# 11 M5 复盘引擎（Review Engine）实现记录

> 本文档记录 M5（复盘：错误检测 + 轻量 EV 分析 + 参考 Bot 对比）完成后落地的实现细节与关键决策，作为后续 M6（DeepSeek Coach）等里程碑的开发依据。
>
> **文档权威性**：遵循 `03-execution-plan.md` 第 8 节约定，本文档是 `10` 之后的「实现快照」，以本文档为准。

---

## 1. 背景与目标

M3 已形成「可玩闭环」，但打完牌只能看动作时间线与结算，无法回答「哪里打得不对、该怎么打」。M5 补齐复盘能力：

- 对真人（`human_seat`）的**每个决策点**做分析，而不是只看结果；
- 给出**轻量 EV 参考量**（摊牌胜率、底池赔率、跟注期望收益）与**明显错误标记**；
- 附上**参考 Bot 在同一局面会怎么做**作为对比，兼顾客观与可解释。

本阶段明确**不做**：反事实动作树模拟、对手范围建模（`10 §4` 的「vs 随机」取舍延续）、GTO 精确判定。

---

## 2. 交付内容总览

| 层 | 文件 | 改动 |
|---|---|---|
| 引擎 | `app/poker/engine.py` | 新增 `start_hand_with` 确定性回放入口；抽取 `_begin_hand` / `_finish_hand_start`；发牌改为 `_draw_board`（支持预置公共牌序列） |
| 牌 | `app/poker/cards.py` | 新增 `card_from_str`（与 `str(Card)` 互逆，用于从历史 JSON 还原牌） |
| 分析 | `app/analysis/hand_review.py` | 新增 `build_review`：确定性重放 + 胜率/赔率/EV + 错误检测 + Bot 对比 |
| 接口 | `app/api/schemas.py` | 新增 `Mistake` / `ActionChoice` / `DecisionReview` / `HandReview` |
| 接口 | `app/api/hands.py` | 新增 `GET /hands/{id}/review` |
| 接口 | `app/api/games.py` / `schemas.py` | `GameView` 新增 `last_hand_id`，每手落库后下发，供牌桌页即时复盘 |
| 前端 | `src/api.js` / `src/components/HistoryView.vue` | 新增 `getReview`；手牌详情内嵌「复盘」区块 |
| 前端 | `src/components/GameTable.vue` | 牌桌页每手结束即时展示复盘 + 「每手复盘」开关 |

测试新增 `tests/test_engine_replay.py`（3 用例）、`tests/test_review.py`（3 用例）、`test_games_api.py` 增加 `test_hand_review_endpoint` 与 `last_hand_id` 下发断言（2 用例）。

---

## 3. 关键设计

### 3.1 确定性重放

复盘只在牌局结束后进行，此时所有底牌与公共牌均已公开，因此可以**确定性重放**（无需随机源）：

- 从 `history_json` 还原庄位、各座位底牌、最终公共牌（顺序即 flop 3 张 + turn 1 张 + river 1 张）；
- 用引擎新增的 `start_hand_with(button, hole_cards, board)` 以已知牌开局；
- 依次重放 `history.actions`（跳过盲注，由 `start_hand_with` 内部处理），在真人决策点调用 `engine.snapshot()` + `legal_actions()` 获取精确局面。

重放复用引擎规则，避免在 analysis 层重复实现下注轮状态机，杜绝漂移。重放时校验 `engine.current_seat` 与历史座位一致，不一致立即抛错（fail fast）。

此外，重放需还原两处与「引擎 Action 语义」不一致的历史记录，否则底池 / 跟注额会算错：

- **各玩家起始筹码**：一手开始时各人筹码可能不同（此前输赢或补码），按 `players[*].starting_stack` 逐人还原，而不是统一用一个值；
- **加注额**：历史记录的是本次加注增量，引擎要求的是加注后总额，重放时换算为「该座位当前已投入 + 记录增量」（仅重放使用，展示仍用历史原值）。

### 3.2 参考标准：EV 为主 + Bot 对比

对每个真人决策点，同时给出两路参考：

1. **独立 EV/胜率**：用 `equity()` 估算「自己底牌面对仍在场对手随机底牌」的摊牌胜率，配合底池赔率得到轻量 EV。**不读取对手真实底牌算胜率**——复盘与打牌保持同一信息边界，避免上帝视角作弊。
2. **Bot 对比**：以 `HeuristicStrategy(seed=0)` 在同一局面 `choose_action` 的结果为基线，并在「翻牌后面对下注」时用保守判据收窄（详见 `13-m5-conservative-reference.md`）。

参考动作**固定为「启发式-保守」**（即使对局当时选用 `random`）：以 heuristic 为基线，翻牌后面对下注额外要求「赔率有余量 + 有可继续的牌力」，避免用高张/仅公共牌成对的牌盲目跟注；随机策略无参考价值。复盘以 `reference_strategy = "heuristic-conservative"` 标注该口径。

### 3.3 轻量 EV 量

每个决策点输出：

- `equity`：胜率（vs 随机，`samples=1000`，seed 固定可复现）；
- `pot_odds`：底池赔率 = `to_call / (pot + to_call)`（仅面对下注时）；
- `call_ev`：跟注期望净收益 = `equity * (pot + to_call) - to_call`（仅面对下注时）。

不做「若采取其他合法动作」的反事实模拟。

### 3.4 错误检测规则

阈值常量集中在 `hand_review.py` 顶部。规则按街区分：

| code | 触发条件 | 适用范围 | severity |
|---|---|---|---|
| `bad_call` | 面对下注跟注且 `equity < pot_odds - 0.03` | 全街 | error |
| `bad_fold` | 面对下注弃牌且 `equity > pot_odds + margin`（翻牌后 `margin = 0.15 + 0.10 × 跟注占底池比例`，且底牌有可继续的牌力：真实成手牌或强听牌，小注放宽；翻牌前还要求 `equity >= 0.55`） | 全街 | warning |
| `value_missed` | 无人下注过牌且 `equity >= 0.80` | 翻牌后 | warning |
| `underbet` | 无人下注下注额 < 底池一半且 `equity >= 0.80` | 翻牌后 | info |
| `slowplay` | 面对下注只跟不加且 `equity >= 0.90` 且可加注 | 翻牌后 | warning |
| `air_bluff` | 无人下注下注且 `equity < 0.25` | 翻牌后 | info |
| `over_aggressive` | 面对下注加注且 `equity < 0.50` | 翻牌后 | warning |

说明：

- 「纯空气」阈值与 `heuristic.py` 保持一致；「价值下注」阈值复盘取 `0.80`（策略层为 `0.70`），偏保守以减少薄价值过牌的误报。
- 误弃容差随注码放大：跟注占底池比例越大，说明对手范围越强、`vs 随机`胜率越偏乐观，要求更高的胜率优势才判误弃；翻牌前因范围更紧、胜率失真最严重，另加胜率下限。
- 跟注侧加 `0.03` 容差：胜率仅略低于赔率（跟注 EV 约等于 0）不判为错误，避免边缘误报。
- 「该抓诈却弃牌」归入 `bad_fold`（面对下注弃牌但胜率明显支持跟注）。
- 参考动作与误弃判据共用同一套「保守跟注标准」：翻牌后面对下注时，参考「跟注」与 `bad_fold`（该跟却弃）都要求赔率有余量且底牌有可继续的牌力，两者按构造保持一致（详见 `13`）。
- 翻牌前只做赔率类判定（`bad_call` / `bad_fold`），牌型/公共牌相关规则不适用。

### 3.5 每手结束即时复盘

除历史页外，牌桌页也在每手结束时直接展示复盘：

- 后端 `_finalize_hand` 落库后把 `hand_id` 写入 `GameRuntime.last_hand_id`，经 `GameView.last_hand_id` 下发；
- 前端 `GameTable` 在 `hand_over` 且「每手复盘」开关（默认开启）打开时，用 `last_hand_id` 调 `GET /hands/{id}/review` 渲染复盘；
- 采用「按需请求 + 防竞态」：开关关闭不请求；点「下一手」后旧请求回填被丢弃。

---

## 4. 与既有文档的偏差

| 点 | 旧文档表述 | 实际落地 |
|---|---|---|
| 引擎 | 无回放入口 | 新增 `start_hand_with` 确定性回放入口（不新增规则，属发牌注入钩子） |
| 复盘接口 | `03` Phase C 列 `/hands/{id}/review` | 落地为 `GET /hands/{id}/review`，实时计算、不落库 |
| 参考标准 | 未明确 | 落地为「独立 EV 为主 + heuristic Bot 对比」，参考 Bot 固定 heuristic |

---

## 5. 已知取舍

- **仍为「vs 随机」而非「vs 对手范围」**：胜率估算与打牌时的口径一致，面对下注时仍会偏乐观。因此误弃容差不再固定，而是随「跟注占底池比例」放大，翻牌前另加胜率下限；跟注侧加 `0.03` 容差，避免 EV 约等于 0 的边缘误报。范围建模留待后续（方向 B / CFR）。
- **错误是「近似判据」而非 GTO**：阈值为人工拍定，`info` / `warning` 类多为「提示」性质，不构成权威判定。
- **价值丢失阈值与策略层解耦**：复盘取 `0.80`（策略层为 `0.70`），宁缺毋滥，减少薄价值过牌的误报，不再与 `heuristic` 阈值严格一致。
- **复盘结果不落库**：单用户、数据量小，且分析逻辑会迭代，实时计算避免迁移成本；`history_json` 已足够重放。
- **性能**：每个真人决策点约 `equity(1000)` + Bot 对比 `equity(500)`，单挑约 30ms，一手通常 1~6 个决策点，满足读接口延迟要求；采样数可通过 `_EQUITY_SAMPLES` 调节。

---

## 6. 测试与验收

```text
$ uv run ruff check .        # All checks passed
$ uv run pytest -q           # 106 passed, 2 warnings
$ cd frontend && npm run build   # built successfully
```

- `test_engine_replay.py`：注入底牌、公共牌按序发放、`card_from_str` 往返。
- `test_review.py`：价值丢失（强牌过牌）命中、赔率不足跟注命中、每个决策点均含合法参考 Bot 动作；逐人还原起始筹码、加注增量换算（重放底池/跟注额与实际一致）；误弃翻牌前胜率下限与注码容差、价值丢失阈值、跟注容差等判据边界。
- `test_games_api.py::test_hand_review_endpoint`：完整 HU 对局后 review 端点返回正确结构、404 路径。
- 2 条 warning 仍来自 `fastapi.testclient` 依赖（starlette/httpx 弃用提示），与本次实现无关。

---

## 7. 后续注意事项

- 复盘产出的 `DecisionReview`（含 `equity` / `pot_odds` / `call_ev` / `mistakes`）是 M6 DeepSeek Coach 的**结构化输入**：LLM 据此解释「为什么这里打得不对」，而非凭空生成。
- 若后续引入范围建模 / CFR，`equity` 口径可替换为 `equity_vs_range`，`hand_review.py` 的调用点集中，易于升级。
- `start_hand_with` 也可用于确定性规则测试（不依赖随机发牌），为后续 M7/M8 CFR 验证与错误检测单元测试复用。
