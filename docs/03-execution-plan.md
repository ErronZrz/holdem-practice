# 03 执行规划总览

> **文档权威性声明**：本文档是需求分析阶段的执行规划总览，用于让后续开发不跑偏。**本文档并非一直权威**：随着实现推进，实际做法可能与本文档出现出入。当发生冲突时，**一律以编号较新的文档为准**（如 `04-...`、`05-...`），并建议在出现偏差时补充新编号文档说明缘由，而不是回头改旧文档。

---

## 0. 文档定位

| 文档 | 角色 |
|---|---|
| `01-chatgpt-suggestion.md` | 技术建议（外部参考） |
| `02-requirements-decisions.md` | 需求决策（已拍板） |
| `03-execution-plan.md`（本文档） | 执行总览（里程碑 / 顺序 / 目录 / 约束 / 验收） |

本文档将 `02` 的决策落地为可执行的路线，不引入新的需求决策。

---

## 1. 目标与核心原则

**一句话目标**：一套可部署在个人云服务器上的中文德州扑克练习平台——CFR/heuristic 负责「怎么打」，DeepSeek 负责「为什么这么打」。

**四条贯穿始终的架构原则**（不可因实现而妥协）：

1. Poker Engine 独立且充分测试（按 N 人设计）。
2. Strategy 是插件式接口，不写死 CFR / heuristic。
3. CFR Training 与 Runtime 完全分离（训练离线，线上只 lookup）。
4. DeepSeek 只解释、不决策，且为 optional 依赖。

---

## 2. 技术栈（已锁定）

- **后端**：Python 3.12+ / FastAPI / Pydantic / SQLAlchemy（或 SQLModel）/ SQLite（可升级 PostgreSQL）。
- **前端**：Vue 3 + Vite。
- **AI**：DeepSeek API（仅中文复盘解释）。
- **部署**：Docker Compose，初期 Nginx/Caddy → FastAPI → SQLite；**先在 Mac 本地部署验收，功能稳定后再上云服务器公网**。
- **语言**：UI 与解释输出均为中文。

---

## 3. 里程碑总览

> 阶段标注：`MVP` = 第一阶段必须；`二期` = 紧随其后；`Stretch` = 增强，不阻塞上线。

| 里程碑 | 内容 | 阶段 | 关联决策 |
|---|---|---|---|
| M0 | 仓库骨架：Python 项目 / lint / test / Docker / CI | MVP | — |
| M1 | Poker Engine：**N 人设计**，HU 试玩跑通 10,000 手随机对局 | MVP | D7 |
| M2 | Basic Bot：Random + Heuristic 策略（合理、不轻易被 exploit） | MVP | D2 |
| M3 | 可玩 Web App：FastAPI + Vue3 中文界面 + Hand History + 结算展示 | MVP | D4/D5/D6 |
| M3.5 | Mac 本地部署验收：Docker Compose 起临时服务供用户验收 | MVP | — |
| M3.6 | 云服务器公网部署：HTTPS + 简单访问保护 | MVP | D1 |
| M4 | 开放 5 人桌（1 真人 + 4 Bot），启用 side pot / 位置轮转 | 二期 | D7 |
| M5 | Review Engine：策略对比、错误检测、训练统计 | 二期 | — |
| M6 | DeepSeek Coach：中文解释 + cache + usage 跟踪 | 二期 | D3 |
| M7 | CFR Framework：Kuhn Poker 收敛验证 | Stretch | D2 |
| M8 | 简化 Hold'em CFR：abstraction + 离线训练 + runtime lookup | Stretch | D2/D3 |

**要点**：
- **M3 完成即形成完整练习闭环**，先在 Mac 本地部署验收，再上云公网；M4–M6 为后续增强。
- **M7/M8 不阻塞上线**：Bot 用 heuristic 也能满足 D2 底线，CFR 是水平升级而非前提。
- 引擎从 M1 起按 N 人建模，避免 M4 扩 5 人桌时返工。

### 3.1 部署路径（本地优先）

> 原则：**云服务器是终点，不是开发期调试场。** 实际操作云服务器之前，必须先在本机完成部署验收。

三阶段：

1. **本地开发（dev）**：前后端本地起服务（如 `uvicorn` + `vite dev`），快速迭代，不依赖 Docker。
2. **本地部署验收（staging）**：在 Mac 上用 Docker Compose 起完整临时服务（前端构建产物 + Nginx/Caddy + 后端 + SQLite 卷），供用户验收；**每次功能相对稳定时都重复这一步**，作为云部署的预演。
3. **云服务器公网部署（prod）**：功能稳定、验收通过后，再将同一套 Docker Compose 配置应用到云服务器，补上 HTTPS、访问保护、备份。

约定：

- 云部署与本地验收尽量共用同一份配置，减少环境差异。
- 本地验收未通过，不进云部署。

---

## 4. 推荐开发顺序

沿用 `01` 的分层思路，强调「先跑通牌局、后上策略、最后接 LLM」：

1. **Phase A（引擎）**：cards / deck / hand / evaluator / state / actions / engine，含 blinds、bet/raise、min-raise、all-in、side pot、street 流转、showdown、结算——全部按 N 人实现。
2. **Phase B（策略接口）**：定义 Strategy Protocol，接入 RandomStrategy，再实现 HeuristicStrategy（强牌 raise / 中牌 call / 弱牌 fold）。
3. **Phase C（Web API）**：`POST /games`、`GET /games/{id}`、`POST /games/{id}/actions`、`/next-hand`、`/hands/{id}`、`/hands/{id}/review`、`/hands/{id}/explain`。
4. **Phase D（Web UI）**：中文牌桌页 + 历史页 + 复盘页 + 统计/结算页，做到可连续练习。
5. **Phase E（暂停试玩）**：先实际打一打，暴露 GameState / Action / Hand History / API 的调整点，**此阶段暂不写 CFR**。
6. **Phase F（二期）**：开放 5 人桌 → Review Engine → DeepSeek Coach。
7. **Phase G（Stretch）**：Kuhn CFR 验证 → 简化 Hold'em CFR → 离线导出策略 → runtime lookup。

> 明确约定：**在 Phase E 之前不进入 CFR 开发**，把返工成本压到最低。

---

## 5. 目录结构（monorepo）

```
holdem-practice/
├── backend/
│   ├── app/
│   │   ├── api/          # game.py / review.py / health.py
│   │   ├── poker/        # N 人引擎（cards/deck/hand/evaluator/state/actions/engine）
│   │   ├── strategy/     # interface / random / heuristic（后续 cfr_policy）
│   │   ├── analysis/     # hand_review / metrics / mistakes
│   │   ├── llm/          # interface / deepseek / prompts
│   │   └── storage/      # models / repository
│   ├── tests/
│   ├── data/             # 策略产物 + SQLite
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/             # Vue 3 + Vite
├── tools/
│   └── trainer/          # 离线 CFR 训练（MacBook 运行）
├── docker-compose.yml
├── AGENTS.md
└── README.md
```

---

## 6. 架构约束（供 AGENTS.md 落地）

1. `poker/` 不依赖 `api/`，也不依赖 `llm/`。
2. `strategy/` 只能通过 GameState 与 `poker/` 交互。
3. LLM 永远不参与实时牌局合法性判断。
4. 所有随机过程必须可注入 seed（便于复现与测试）。
5. 筹码/金额使用统一数值规范（单一单位，避免浮点误差）。
6. 新增扑克规则必须配套单元测试。
7. 公开 API 一律使用 Pydantic model。
8. 引擎结构按 N 人设计，不得写死「恰好 2 人」。

---

## 7. 验收标准

**M3（MVP 闭环）完成判据**：

- 能稳定连续打 1,000 手，无非法动作 / 非法 pot / 重复发牌 / 状态死锁。
- Bot 决策 < 100ms，且不调用 LLM。
- 服务器 idle 内存 < 数百 MB。
- 牌局结束可查看完整历史、reference strategy、主要错误。
- 点击解释后 DeepSeek 返回结构化中文建议；DeepSeek 不可用时打牌不受影响。

**D7（引擎 N 人）设计判据**：M1 阶段即通过多人 side pot / 位置轮转相关的单元测试（即使 MVP 只跑 HU）。

---

## 8. 文档演进方式

- 本文档为「阶段起点快照」，后续里程碑之间如发生方案变化，**新增编号文档**（如 `04-...`）记录变更，而非改写本文档。
- 若未来实现与本文档冲突，以编号更大的文档为准；必要时在本文件头部标注「已被 XX 文档更新」的指向。
