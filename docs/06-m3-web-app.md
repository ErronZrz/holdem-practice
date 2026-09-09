# 06 M3 可玩 Web App 实现记录

> 本文档记录 M3（可玩 Web App：持久化 + FastAPI + Vue3 中文前端）完成后落地的实现细节与关键决策，作为后续 M3.5~M8 的开发依据。
>
> **文档权威性**：遵循 `03-execution-plan.md` 第 8 节约定，本文档是 `05` 之后的「实现快照」。当本文档与 `01`~`05` 冲突时，**以本文档为准**。

---

## 1. 交付内容总览

| 层 | 文件 | 职责 |
|---|---|---|
| 持久化 | `app/storage/models.py` | `SessionModel` / `HandModel` SQLAlchemy 模型 |
| 持久化 | `app/storage/db.py` | SQLite 引擎、连接与建表（`HOLDEM_DB_PATH` 可覆盖，默认 `backend/data/holdem.db`） |
| 持久化 | `app/storage/repository.py` | Session / Hand 的读写（不自行 commit，事务由 API 层控制） |
| 持久化 | `app/storage/hand_history.py` | 把一手结束后的引擎状态序列化为 Hand History JSON |
| 接口 | `app/api/schemas.py` | 全部对外 Pydantic 请求/响应模型 |
| 接口 | `app/api/games.py` | 创建/获取对局、提交动作、下一手（Bot 惰性逐帧推进） |
| 接口 | `app/api/hands.py` | 手牌历史列表/详情、结算统计 |
| 前端 | `src/App.vue` + `main.js` + `style.css` | 应用壳、三页导航（牌桌/历史/统计）、全局样式 |
| 前端 | `src/components/GameTable.vue` | 中文牌桌页，可对 Bot 打牌（含「本手动作」面板、退出按钮、Bot 逐帧播放） |
| 前端 | `src/components/HistoryView.vue` | 历史对局与手牌详情 |
| 前端 | `src/components/StatsView.vue` | 结算/统计页 |
| 前端 | `src/components/PlayingCard.vue` | 单张牌展示组件 |
| 前端 | `src/api.js` / `src/cards.js` | API 客户端 / 牌与阶段中文展示辅助 |

测试新增 `tests/test_storage.py`（2 用例）、`tests/test_games_api.py`（7 用例）。

---

## 2. 持久化设计

### 2.1 数据模型（单用户，Session 为顶层）

- `SessionModel`：`num_players` / `human_seat` / 盲注 / `starting_stack` / `target_hands` / `hands_played` / `net_chips` / `bot_strategy` / `status`（active|finished）。
- `HandModel`：`session_id`（外键）/ `hand_number` / `net`（真人净盈亏，为统计便利的冗余列）/ `history_json`（完整 Hand History，**source of truth**）。

### 2.2 Hand History JSON

每手结束把引擎公开状态序列化为 JSON 存入 `HandModel.history_json`，字段含：

- `hand_number` / `num_players` / `small_blind` / `big_blind` / `button`
- `players`（座位、名字、是否真人、底牌、起始筹码）
- `board`（公共牌）、`actions`（引擎完整动作日志，含小盲/大盲）
- `street` / `showdown` / `winners` / `net`（各座位净盈亏）

读取侧从 JSON 反序列化还原历史，不做二次归一化，保证 JSON 单一事实来源。`net` 列仅作列表/统计的快速聚合，与 JSON 内 `net` 一致。

### 2.3 运行态 vs 持久化

- **进行中的对局（engine + bot 策略）驻留进程内存**（`app/api/games.py` 的 `_registry`），不落库；重启后需重新创建。
- **已完成的手牌与对局元数据落库**，重启后历史/统计仍可读。

这是单用户本地应用下的取舍：中途恢复对局需完整重建引擎快照，成本高且 MVP 无此诉求，故不实现。

---

## 3. 接口设计

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/games` | 创建对局并开始第一手 |
| GET | `/games` | 对局列表（摘要） |
| GET | `/games/{id}` | 当前对局视图；轮到 Bot 时惰性推进一个 Bot 动作 |
| POST | `/games/{id}/actions` | 提交真人动作（不立即跑 Bot，后续由 GET 逐帧推进） |
| POST | `/games/{id}/next-hand` | 开始下一手 |
| GET | `/games/{id}/hands` | 手牌历史列表 |
| GET | `/hands/{id}` | 单手完整历史 |
| GET | `/games/{id}/stats` | 结算/统计（胜/负/平、净筹码） |

关键约定：

- **真人不写死座位**：真人固定 `human_seat=0`，其余座位全部由 Bot 驱动，支持 `num_players >= 2`（MVP 界面默认 2）。
- **Bot 惰性逐帧推进**：`GET /games/{id}` 在轮到 Bot 且距上次动作 ≥ `BOT_DELAY`（默认 1s）时仅推进**一个** Bot 动作；前端轮询该接口逐步拉取，从而逐个播放 Bot 动作，而非一次性跑到终局。推进导致本手结束时才落库结算。
- **当前手动作**：`GameView.hand_actions` 返回本手已发生的动作序列（含盲注），供牌桌内实时展示；`small_blind`/`big_blind` 一并下发。
- **底牌遮蔽**：视图仅在「真人自己」或「本手已结束（摊牌）」时返回 `hole_cards`，其余玩家返回空并置 `cards_revealed=false`，从接口层杜绝 Bot 底牌泄露。
- **非法动作 400**：引擎抛 `IllegalActionError` 时转为 `400` 返回中文原因；非真人回合、本手已结束、金额缺失等也返回 `400`。
- 创建时若 `small_blind > big_blind` 返回 `400`。

---

## 4. 前端设计

- Vue 3 + Vite，三页切换（牌桌/历史/统计），无路由库，用 `App.vue` 的 `view` 状态切换；三页以 `<KeepAlive>` 包裹，切到历史/统计再切回牌桌时进行中的对局不丢失。
- 开发时经 Vite 代理 `/games`、`/hands`、`/health` 转发到本地后端（uvicorn）；生产可由 `VITE_API_BASE` 覆盖后端地址。
- 牌桌页：创建表单（人数/手数/Bot 策略/盲注/初始筹码）→ 桌面（对手在顶、真人在底、公共牌与底池居中）→ 行动条（弃牌/过牌/跟注/下注/加注，下注加注带金额输入与最小/底池/全下快捷键）→ 结果横幅与「下一手」/「再开一局」；顶部提供「退出对局」按钮（确认后回到创建表单）。
- 牌桌内「本手动作」面板：按街分组、中文展示当前手已发生的动作，随 Bot 逐帧推进实时追加。
- Bot 播放节奏：轮到 Bot 时前端以约 400ms 轮询 `GET /games/{id}`，配合后端 `BOT_DELAY` 实现「每 1s 一个 Bot 动作」；切到其它 tab 暂停轮询（`onDeactivated`），切回自动恢复（`onActivated`）。
- 历史页：选择对局 → 手牌列表（第 N 手 / 净盈亏 / 阶段）→ 单手详情（公共牌、各玩家底牌与盈亏、按街分组的动作时间线）。
- 统计页：选择对局 → 已打手数、累计净筹码（含 BB 换算）、胜/负/平。

---

## 5. 与 03 / 04 / 05 的偏差

| 点 | 旧文档表述 | 实际落地 |
|---|---|---|
| 复盘/解释接口 | `03` Phase C 列 `/hands/{id}/review`、`/hands/{id}/explain` | M3 不实现，推迟到 M5/M6；不引入 llm 依赖 |
| storage 目录 | `03` 目录约定 `models / repository` | 落地为 `models.py` / `db.py` / `repository.py` / `hand_history.py` |
| rebuy 承载 | `04` §3.9 注「Session 层在 M3 再落实」 | 输光自动补码仍由引擎 `start_hand` 承担（每手重置时补码），Session 层只累计战绩，未另起补码逻辑 |
| 进行中对局持久化 | `03` §5 仅列 `storage` | 进行中对局驻内存、仅已完成手牌落库（见 §2.3） |
| 多人桌 | `02` D7 MVP 仅开放 HU | 引擎与接口均按 N 人设计，接口支持 `num_players>2`，前端牌桌当前按「真人底部 + Bot 顶部」渲染（多人时 Bot 横向排列） |
| Bot 行动方式 | `05` 未涉及（策略独立于 API） | M3 落地为「惰性逐帧推进 + 前端轮询」，使 Bot 动作逐个播放 |

---

## 6. 测试与验收

```text
$ uv run ruff check .        # All checks passed
$ uv run pytest -q           # 53 passed, 2 warnings
$ cd frontend && npm run build   # built successfully
```

新增覆盖：

- 持久化：Session/Hand 落库往返、Hand History JSON 还原、多对局列表。
- 接口：创建/获取对局、首手庄位与真人先行动、底牌遮蔽、动作金额校验（缺金额/低于最小加注 400）、弃牌立即结束、HU 连续 5 手打完无非法动作无死锁（测试内 `BOT_DELAY=0` 模拟逐帧轮询推进）、历史与统计落库正确、随机 Bot 对局跑通、404/400 错误路径。

端到端冒烟（真实默认库路径）验证：创建 → 连续打满 3 手 → 统计与手牌历史读取均正常；另以真实 `BOT_DELAY=1s` 验证 Bot 动作在提交后约 1s 才逐个推进。

2 条 warning 仍来自 `fastapi.testclient` 依赖（starlette/httpx 弃用提示），与本次实现无关。

---

## 7. 后续注意事项

- **尚未 commit**：M3 完成后按用户要求暂未提交，待确认后统一提交。
- `analysis/`、`llm/` 仍为空壳，接口未暴露 review/explain，符合「LLM 不参与实时牌局」约束。
- 进行中对局不落库：若后续需要服务重启不中断牌局，需补充引擎快照的序列化/恢复（M4 开放多人桌时一并评估）。
- 本地开发端口：已归位为默认 8000（`uvicorn` 默认端口 + `vite.config.js` 代理均指向 8000）。
- 下一里程碑 **M3.5（Mac 本地体验验收）**：受「Mac 办公机不安装 Docker Desktop」限制，本地验证仅做产品体验（`uvicorn` + `vite dev` 直接起服务），不做部署层；Docker Compose 部署预演推迟到云服务器（M3.6）阶段再验证。
