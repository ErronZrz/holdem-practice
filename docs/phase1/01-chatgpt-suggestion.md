# 德州扑克 CFR Bot + DeepSeek API 练习平台

## 起始实现建议报告

## 1. 项目目标

计划实现一套可部署在个人云服务器上的德州扑克练习平台，核心目标是：

* 用户可以与 AI Bot 进行德州扑克练习；
* Bot 的实际牌局决策主要由 CFR 类策略系统完成，而不是依赖 LLM；
* DeepSeek API 主要承担牌局解释、复盘、教学反馈等语言类任务；
* 服务端优先使用 Python；
* 尽量降低持续 CPU、内存和 API 成本；
* 架构保持简单，适合个人维护和逐步迭代；
* 第一阶段优先完成可用的练习闭环，而不是追求完整 GTO Solver 能力。

整体原则：

> **CFR 负责“怎么打”，LLM 负责“为什么这么打”。**

不建议让 DeepSeek API 参与实时动作决策，否则会增加延迟、成本，同时决策稳定性也通常不如结构化策略系统。

---

# 2. 第一阶段建议范围

建议 MVP 先限制为：

* Heads-Up Texas Hold'em；
* No-Limit Hold'em；
* 固定初始筹码深度，例如 100BB；
* 固定盲注；
* 单桌；
* 用户对一个 Bot；
* 不涉及真钱、账户充值等系统；
* 支持完整 Preflop / Flop / Turn / River；
* 支持 Fold / Check / Call / Bet / Raise；
* 支持简单牌局历史；
* 支持牌后分析；
* DeepSeek 只在用户主动请求解释时调用。

暂时不建议第一阶段实现：

* 6-max / 9-max；
* Tournament；
* 多玩家 CFR；
* 实时完整 GTO 求解；
* 任意 bet sizing；
* 大规模用户并发；
* GPU 推理；
* 自训练大型扑克模型；
* 完整 GTO Wizard 类 Range Explorer。

原因很简单：这些功能很容易让项目从一个练习工具演变成 Solver 项目。

---

# 3. 推荐总体架构

可以采用一个相对简单的单体应用：

```text
┌─────────────────────────────┐
│          Web UI             │
│                             │
│  Table / Action / Review    │
└──────────────┬──────────────┘
               │ HTTP / WS
               ▼
┌─────────────────────────────┐
│       Python Backend        │
│                             │
│  FastAPI                    │
│                             │
│  ┌───────────────────────┐  │
│  │    Poker Engine       │  │
│  │                       │  │
│  │ Rules / State / Pot   │  │
│  │ Action Validation     │  │
│  └──────────┬────────────┘  │
│             │               │
│  ┌──────────▼────────────┐  │
│  │   Strategy Engine     │  │
│  │                       │  │
│  │ CFR Policy Lookup     │  │
│  │ Abstraction           │  │
│  │ Action Sampling       │  │
│  └──────────┬────────────┘  │
│             │               │
│  ┌──────────▼────────────┐  │
│  │   Analysis Service    │  │
│  │                       │  │
│  │ Hand Evaluation       │  │
│  │ EV / Mistake Metrics  │  │
│  │ Review Context        │  │
│  └──────────┬────────────┘  │
│             │               │
│  ┌──────────▼────────────┐  │
│  │    LLM Adapter        │  │
│  │                       │  │
│  │ DeepSeek API          │  │
│  └───────────────────────┘  │
│                             │
│ SQLite / PostgreSQL         │
└─────────────────────────────┘
```

第一阶段没有必要拆成微服务。

一个 Python 进程加一个数据库，就足够支撑个人使用甚至少量用户使用。

---

# 4. 推荐技术栈

## 4.1 后端

推荐：

```text
Python 3.12+
FastAPI
Pydantic
SQLAlchemy / SQLModel
SQLite
```

如果未来用户增加，可以自然升级为：

```text
SQLite → PostgreSQL
```

WebSocket 可以用于牌桌实时交互，但 MVP 甚至可以先使用 HTTP API。

如果前端操作只是：

```text
user action
    ↓
server calculate
    ↓
bot action
    ↓
return current game state
```

普通 HTTP 请求完全够用。

---

# 5. 核心模块划分

建议从一开始就保持模块边界清晰。

例如：

```text
app/
├── api/
│   ├── game.py
│   ├── review.py
│   └── health.py
│
├── poker/
│   ├── cards.py
│   ├── deck.py
│   ├── hand.py
│   ├── evaluator.py
│   ├── state.py
│   ├── actions.py
│   └── engine.py
│
├── strategy/
│   ├── interface.py
│   ├── abstraction.py
│   ├── cfr_policy.py
│   ├── random_policy.py
│   └── heuristic_policy.py
│
├── analysis/
│   ├── hand_review.py
│   ├── metrics.py
│   └── mistakes.py
│
├── llm/
│   ├── interface.py
│   ├── deepseek.py
│   └── prompts.py
│
├── storage/
│   ├── models.py
│   └── repository.py
│
└── main.py
```

这里比较重要的一点是：

```text
Poker Engine
Strategy Engine
LLM
```

三者不要互相强耦合。

尤其不要出现：

```python
if bot_turn:
    call_deepseek(...)
```

更推荐：

```python
strategy.choose_action(game_state)
```

至于具体实现是：

```text
CFR
heuristic
random
rule-based
```

Poker Engine 不应该关心。

---

# 6. Poker Engine 设计原则

Poker Engine 是整个项目最值得优先做好的一部分。

核心对象可以抽象为：

```text
GameState
PlayerState
Board
Pot
ActionHistory
LegalActions
```

例如：

```python
GameState(
    street=Street.FLOP,
    board=[...],
    pot=12.0,
    current_player="hero",
    players=...,
    action_history=...,
)
```

Poker Engine 负责：

* 发牌；
* position；
* blind；
* 当前行动玩家；
* pot；
* bet / raise；
* minimum raise；
* all-in；
* fold；
* street transition；
* showdown；
* pot settlement；
* action legality。

Poker Engine 不负责：

* AI 决策；
* LLM；
* UI；
* CFR 算法。

这样后面可以独立测试。

---

# 7. CFR Bot 的现实实现建议

这里建议避免一个常见误区：

> 第一版不需要实现“实时完整 NLHE CFR Solver”。

完整 No-Limit Hold'em 的状态空间非常大。

如果目标是低资源服务器，推荐采用：

```text
Offline Strategy Generation
        ↓
Compact Policy
        ↓
Runtime Lookup
```

也就是：

**训练或计算可以离线进行，线上服务器只做策略查询。**

---

# 8. CFR Runtime 与 CFR Training 分离

建议项目内部明确分成：

```text
CFR Trainer
```

与：

```text
CFR Runtime
```

两部分。

Trainer：

```text
负责：
- CFR iterations
- regret update
- average strategy
- strategy export
```

Runtime：

```text
负责：
- game state abstraction
- infoset lookup
- strategy probability lookup
- action sampling
```

部署服务器只需要 Runtime。

例如：

```text
Bot turn
    ↓
GameState
    ↓
Abstraction
    ↓
InfoSet Key
    ↓
Policy Lookup
    ↓
{
    fold: 0.15,
    call: 0.45,
    raise: 0.40
}
    ↓
sample
```

这样线上一次决策可能只需要几毫秒。

---

# 9. 不建议第一版追求完整 NLHE CFR

第一阶段可以降低问题规模。

一种可行路径是：

### Preflop

使用预生成策略：

```text
position
stack depth
hole cards
previous action
```

例如：

```text
BTN / 100BB / AKs / unopened

raise 0.92
call  0.04
fold  0.04
```

### Postflop

进行状态 abstraction。

例如：

```text
street
position
pot size
effective stack
board texture
hand strength bucket
draw bucket
previous action
```

然后查 CFR policy。

这样系统并不是完美 GTO Solver，但已经非常适合训练。

---

# 10. Action Abstraction

No-Limit Hold'em 最大的问题之一是：

```text
bet size theoretically continuous
```

因此推荐限制 Bot 的动作空间。

例如：

```text
Fold
Check
Call
Bet 33% Pot
Bet 75% Pot
Bet 125% Pot
All-in
```

实际不需要一开始支持这么多。

MVP 可以考虑：

```text
Fold
Check / Call
Small Bet
Large Bet
All-in
```

具体 sizing 可以后续调整。

Poker Engine 本身仍然可以允许用户输入更自由的 sizing，但 Strategy Engine 可以把它映射到最近的 abstraction。

例如：

```text
user bet 58% pot

→ mapped to

50% / 66% bucket
```

---

# 11. Card / Hand Abstraction

完整枚举所有 postflop 状态成本较高。

因此可以使用 bucket。

第一版可以从一些可解释特征开始：

```text
Made Hand:
- high card
- pair
- two pair
- trips
- straight
- flush
- full house+

Draw:
- no draw
- gutshot
- OESD
- flush draw
- combo draw

Strength:
- equity bucket
- percentile bucket
```

例如：

```text
HAND_STRENGTH_BUCKET = 7 / 20
```

board 也可以进行分类：

```text
paired
monotone
two-tone
rainbow
connected
high-card
low-card
```

后续如果需要更高质量，可以逐渐替换为：

```text
equity-based abstraction
potential-aware abstraction
k-means clustering
```

因此抽象逻辑最好独立成模块。

---

# 12. CFR 数据存储形式

运行阶段不建议加载非常复杂的 Python object graph。

简单方案可以是：

```text
dict
msgpack
sqlite
numpy array
```

例如：

```python
policy[infoset_id] = [0.15, 0.45, 0.40]
```

或者：

```text
infoset_id
fold_prob
call_prob
raise_prob
```

如果策略规模不大，可以启动时一次性加载到内存。

例如：

```text
50 MB policy
```

对于现代云服务器通常完全可以接受。

如果策略规模后期扩大，再考虑：

```text
memory mapped file
SQLite lookup
LMDB
```

无需第一阶段过度设计。

---

# 13. Bot 不应该总执行最大概率动作

假设 CFR 输出：

```text
Fold   10%
Call   55%
Raise  35%
```

不要直接：

```text
Call
```

而应该按照策略概率采样：

```python
random.choices(
    ["fold", "call", "raise"],
    weights=[0.1, 0.55, 0.35]
)
```

否则：

```text
mixed strategy
```

会退化为：

```text
deterministic strategy
```

既不符合 CFR 的含义，也会让 Bot 变得容易预测。

---

# 14. 建议支持 Bot Difficulty

练习平台可以很容易做几个难度。

例如：

```text
Easy
Medium
Strong
```

实现方式不一定需要训练三套模型。

可以在 CFR strategy 上加扰动：

```text
Strong
100% CFR policy

Medium
80% CFR
20% heuristic / random

Easy
60% CFR
40% loose heuristic
```

甚至可以人为设置一些 player profile：

```text
Tight
Loose
Aggressive
Passive
Balanced
```

这样训练价值可能比单纯一个 GTO Bot 更高。

---

# 15. DeepSeek 的定位

DeepSeek 推荐只承担：

```text
Review Explanation
```

而不承担：

```text
Poker Decision Engine
```

典型流程：

```text
一手牌结束
    ↓
Analysis Engine
    ↓
生成结构化分析
    ↓
用户点击：
“为什么这里应该 Call？”
    ↓
DeepSeek
    ↓
自然语言解释
```

例如发送给 LLM 的内容不要是：

```text
这是我的牌局，请分析。
```

而应该是结构化信息：

```json
{
  "game": "NLHE",
  "effective_stack_bb": 100,
  "hero_position": "BTN",
  "villain_position": "BB",
  "hero_hand": "AsKh",
  "board": ["Kd", "7s", "2c"],
  "pot_bb": 6.5,
  "action": {
    "hero": "bet 5bb"
  },
  "reference_strategy": {
    "check": 0.62,
    "bet_small": 0.32,
    "bet_large": 0.06
  }
}
```

然后要求：

```text
解释：
1. Hero 的 range advantage
2. Hero 的 nut advantage
3. 这个 board 的特点
4. 为什么 solver 更偏好 check
5. Hero 当前动作可能有什么问题
```

这样 LLM 的作用是：

```text
structured data → explanation
```

而不是：

```text
raw game state → poker solver
```

准确性会高很多。

---

# 16. API 成本控制

DeepSeek API 成本可以从架构层控制。

建议：

### 只在用户主动请求时调用

不要：

```text
每一个 Action → LLM
```

而是：

```text
每一局 0 次调用
```

默认不分析。

用户点击：

```text
Explain
```

才调用一次。

---

### 缓存

相同或类似问题可以缓存。

例如：

```text
hash(
  position,
  hand_bucket,
  board_bucket,
  action,
  reference_strategy
)
```

命中缓存则直接返回。

---

### 控制 Context

不需要把完整聊天历史发给 DeepSeek。

只发送：

```text
当前 hand
关键 action
CFR result
必要上下文
```

---

### 控制输出长度

例如教学解释：

```text
300～600 字
```

通常已经足够。

---

# 17. 推荐 LLM Adapter

不要直接在业务层调用 DeepSeek SDK。

建议抽象：

```python
class PokerExplanationProvider(Protocol):

    async def explain_hand(
        self,
        context: HandReviewContext,
    ) -> Explanation:
        ...
```

然后：

```text
DeepSeekProvider
MockProvider
```

未来甚至可以替换：

```text
OpenAI
Claude
本地模型
```

而不影响业务逻辑。

---

# 18. Review Engine

相比 CFR Trainer，这部分可能对“训练效果”更重要。

建议每个 Decision 记录：

```text
Game State
Hero Action
Bot Strategy
Reference Strategy
EV Estimate
```

例如：

```json
{
  "street": "turn",
  "hero_action": "fold",
  "strategy": {
    "fold": 0.12,
    "call": 0.73,
    "raise": 0.15
  }
}
```

可以定义一个非常简单的 mistake score。

例如：

```text
Best action probability >= 70%

但玩家选择 probability <= 15%

→ Major Mistake
```

早期甚至不需要真正精确 EV。

先用：

```text
strategy divergence
```

作为训练指标就可以。

---

# 19. 用户训练数据

长期来说最有价值的数据不是：

```text
win rate
```

而是：

```text
decision quality
```

可以统计：

```text
Preflop
- VPIP
- PFR
- 3Bet
- Fold to 3Bet

Flop
- CBet
- Fold to CBet
- Check Raise

Turn
- Barrel
- Fold

River
- Bluff
- Bluff Catch
```

再叠加：

```text
strategy deviation
```

例如：

```text
BTN RFI:
良好

BB vs BTN Open:
Overfold

Turn vs second barrel:
严重 Overfold

River bluff catch:
偏紧
```

这种报告很适合再交给 DeepSeek 转换成：

```text
训练建议
```

---

# 20. 数据模型建议

第一版保持简单即可。

核心可能只有：

```text
User
Session
Hand
Decision
Explanation
```

例如：

```text
Session
├── id
├── user_id
├── started_at
└── settings
```

```text
Hand
├── id
├── session_id
├── hand_no
├── hero_cards
├── board
├── result
└── raw_history
```

```text
Decision
├── hand_id
├── street
├── state
├── hero_action
├── reference_strategy
└── score
```

建议保留：

```text
raw_history
```

即使初期分析能力有限，未来也可以重新跑分析。

---

# 21. Hand History

建议定义自己简单的 JSON 格式。

例如：

```json
{
  "hand_id": "...",
  "players": [
    {
      "id": "hero",
      "position": "BTN",
      "stack": 100
    },
    {
      "id": "bot",
      "position": "BB",
      "stack": 100
    }
  ],
  "actions": [
    {
      "street": "preflop",
      "actor": "hero",
      "action": "raise",
      "amount": 2.5
    }
  ]
}
```

不要把牌局历史只存成人类可读文本。

推荐：

```text
JSON = source of truth

Text = rendered representation
```

后续做分析会容易很多。

---

# 22. API 设计

第一版接口数量无需很多。

例如：

```text
POST /games
```

创建游戏。

```text
GET /games/{game_id}
```

获取当前状态。

```text
POST /games/{game_id}/actions
```

玩家行动。

```text
POST /games/{game_id}/next-hand
```

下一手。

```text
GET /hands/{hand_id}
```

获取 Hand History。

```text
GET /hands/{hand_id}/review
```

结构化分析。

```text
POST /hands/{hand_id}/explain
```

DeepSeek 解释。

这种 API 已经足够搭建完整 MVP。

---

# 23. 前端建议

如果目标是个人练习工具，不需要复杂前端框架。

推荐：

```text
React + Vite
```

或者：

```text
Vue
```

取决于个人习惯。

页面可以只有：

```text
/
Poker Table

/history
Hand History

/review/:hand_id
Hand Review

/stats
Training Stats
```

Poker Table 第一版只需要展示：

```text
Opponent
Stack
Board
Pot
Hero Hand
Hero Stack

Fold
Check / Call
Bet / Raise
```

不需要投入太多时间做动画。

---

# 24. 部署建议

因为服务器资源有限，推荐：

```text
Nginx
   ↓
FastAPI
   ↓
SQLite
```

或者：

```text
Caddy
   ↓
FastAPI
```

Docker Compose 可以采用：

```text
frontend
backend
```

数据库初期甚至无需独立容器。

例如：

```text
Docker
├── backend
├── frontend
└── volume
    └── poker.db
```

第一版不需要：

```text
Redis
Kafka
Celery
Kubernetes
Elasticsearch
```

除非后续真的出现需求。

---

# 25. CPU / 内存控制

整个架构最重要的性能原则：

> 不要在服务器实时运行 CFR Training。

服务器只做：

```text
policy lookup
hand evaluation
game state transition
HTTP
```

这些计算量很小。

正常情况下：

```text
1～2 vCPU
1～2 GB RAM
```

就应该能够支撑个人使用。

真正比较耗资源的任务：

```text
CFR Training
```

可以在：

```text
MacBook
开发机
临时高规格机器
```

运行，然后生成：

```text
policy artifact
```

部署到服务器。

---

# 26. CFR Trainer 可以独立成工具

例如：

```text
tools/
└── trainer/
    ├── train.py
    ├── cfr.py
    ├── abstraction.py
    └── export.py
```

执行：

```bash
python train.py --iterations 1000000
```

得到：

```text
strategy-v1.bin
```

然后部署：

```text
backend/data/strategy-v1.bin
```

线上 Backend 只读取。

这种模式非常适合 CodeBuddy 逐模块开发。

---

# 27. 测试策略

这个项目非常适合大量单元测试。

Poker Engine 必须优先测试。

例如：

```text
test_blinds
test_fold
test_call
test_raise
test_min_raise
test_all_in
test_side_pot
test_flop_transition
test_turn_transition
test_river_transition
test_showdown
```

虽然 Heads-Up 第一版 side pot 很简单，但规则引擎仍建议保持严格。

Strategy Engine 测试：

```text
same infoset → valid policy
sum(probabilities) == 1
illegal action probability == 0
```

Simulation Test：

```text
play 10000 random hands
```

验证：

```text
没有非法状态
没有 negative pot
没有 card duplication
没有 action deadlock
```

这类测试非常重要。

---

# 28. 推荐开发顺序

建议不要一开始就写 CFR。

推荐顺序：

## Phase 1：Poker Engine

目标：

```text
两个随机玩家可以完成 10,000 手牌
```

完成：

```text
cards
deck
state
actions
betting
street
showdown
```

---

## Phase 2：Strategy Interface

实现：

```text
RandomBot
```

然后：

```text
HeuristicBot
```

例如：

```text
strong hand → raise
medium → call
weak → fold
```

目标：

```text
用户可以完整和 Bot 打牌
```

---

## Phase 3：Web API

实现：

```text
create game
action
state
history
```

---

## Phase 4：Web UI

做到：

```text
真正可以连续练习
```

---

## Phase 5：CFR Prototype

先在一个非常小的游戏上验证 CFR。

例如：

```text
Kuhn Poker
```

这一步很推荐。

因为 Kuhn Poker 可以验证：

```text
regret update
average strategy
infoset
convergence
```

如果 CFR 实现正确，再迁移到简化 Hold'em。

---

# 29. 为什么建议先实现 Kuhn Poker

CFR 算法本身很容易写出：

```text
能跑
```

但：

```text
不正确
```

的实现。

Kuhn Poker 很小，而且已知 Nash equilibrium。

因此可以用它验证：

```text
CFR framework
```

例如：

```text
trainer/
├── core.py
├── kuhn.py
└── holdem.py
```

其中：

```text
core.py
```

尽量保持 game-independent。

这样后面迁移到 Hold'em 更稳。

---

# 30. Hold'em CFR 第一版建议

不要立即实现：

```text
100BB unrestricted NLHE
```

可以先实现一个简化版本：

```text
Heads-Up
20BB / 50BB
有限 bet sizing
有限 raise depth
card abstraction
```

例如：

```text
Actions:

CHECK
CALL
BET_50
BET_100
RAISE_3X
ALL_IN
FOLD
```

再逐步增加复杂度。

---

# 31. CFR 核心接口建议

可以抽象类似：

```python
class CFRGame(Protocol):

    def current_player(self, state):
        ...

    def legal_actions(self, state):
        ...

    def apply_action(self, state, action):
        ...

    def is_terminal(self, state):
        ...

    def utility(self, state, player):
        ...

    def infoset_key(self, state, player):
        ...
```

CFR algorithm 不应该知道：

```text
Texas Hold'em
```

是什么。

它只理解：

```text
state
action
player
utility
infoset
```

这样后面可以方便测试。

---

# 32. Strategy Versioning

建议从一开始就记录：

```text
strategy_version
```

例如：

```text
cfr-hu-v1
cfr-hu-v2
```

Hand History 中保存：

```json
{
  "strategy_version": "cfr-hu-v3"
}
```

否则未来策略升级后：

```text
为什么同一手牌以前的 Review 和现在不一样？
```

会很难排查。

---

# 33. DeepSeek Prompt 设计

Prompt 推荐拆成：

```text
System Instruction
+
Structured Hand Context
+
Review Data
+
Question
```

System Prompt 大致约束：

```text
你是一名德州扑克训练教练。

所有建议应基于给定 reference strategy。
不要自行声称某个动作是 GTO，除非 reference data 支持。
重点解释：
- range
- board texture
- position
- stack
- sizing
- frequencies

避免给出不存在的精确 EV。
```

这一条非常重要：

> LLM 不应该凭空生成 solver 数字。

如果系统没有：

```text
EV = +2.31
```

就不要让模型说：

```text
这个动作损失 0.42BB。
```

---

# 34. LLM 输入输出建议结构化

可以要求 DeepSeek 返回 JSON：

```json
{
  "summary": "...",
  "why": [
    "...",
    "..."
  ],
  "mistake": "...",
  "better_plan": "...",
  "practice_tip": "..."
}
```

Backend 做 Pydantic validation：

```python
class Explanation(BaseModel):
    summary: str
    why: list[str]
    mistake: str | None
    better_plan: str
    practice_tip: str
```

这样：

```text
API 输出
UI 展示
历史存储
```

都会更稳定。

---

# 35. 错误处理

DeepSeek API 不应该成为牌局依赖。

如果 DeepSeek：

```text
timeout
rate limit
API unavailable
```

系统仍然必须可以继续打牌。

例如：

```text
Poker
✅ available

Review
✅ available

Natural Language Explanation
⚠ temporarily unavailable
```

因此 LLM 模块最好是完全 optional dependency。

---

# 36. 日志与可观测性

个人项目不需要复杂 observability。

最少记录：

```text
request id
game id
hand id
decision id
strategy version
LLM request latency
LLM token usage
```

尤其建议记录：

```text
DeepSeek usage
```

用于成本监控。

例如：

```text
daily_requests
input_tokens
output_tokens
estimated_cost
```

后续可以在简单 admin 页面查看。

---

# 37. API Budget

可以在 Backend 实现简单配额。

例如：

```text
每天最多：
50 次解释
```

或者：

```text
每手最多：
3 次解释
```

避免前端 bug 导致：

```text
重复请求 API
```

还可以对：

```text
(hand_id, question_type)
```

进行 cache。

---

# 38. 安全

如果服务部署在公网，至少考虑：

```text
HTTPS
Authentication
Rate Limit
Secret Management
```

DeepSeek API Key：

不要放：

```text
frontend
git repository
docker image
```

只通过环境变量：

```text
DEEPSEEK_API_KEY
```

读取。

---

# 39. CodeBuddy 项目开发方式

不建议直接给 Coding Agent 一个任务：

```text
实现整个扑克平台。
```

建议拆成一系列独立目标。

例如：

```text
Task 1

实现纯 Python Texas Hold'em game engine。

要求：
- 无 Web 框架依赖
- Heads-Up
- 支持 betting round
- 完整 unit tests
```

然后：

```text
Task 2

在 poker engine 上定义 Strategy protocol，
实现 RandomStrategy。
```

然后：

```text
Task 3

建立 FastAPI API，
不要修改 poker engine 的领域逻辑。
```

这种方式比一次生成整个系统的代码质量会高很多。

---

# 40. 建议给 CodeBuddy 的 Repository Guide

可以在项目中维护：

```text
AGENTS.md
```

或者类似项目规则文件。

内容建议包括：

```text
Architecture Principles

1. poker/ 不依赖 api/
2. poker/ 不依赖 llm/
3. strategy/ 只能通过 GameState 与 poker 交互
4. LLM 永远不参与实时牌局 legality
5. 所有随机过程必须可注入 seed
6. monetary / chip value 使用统一数值规范
7. 新 poker rule 必须有 unit test
8. public API 使用 Pydantic model
```

对于 Coding Agent 来说，这类约束往往非常有用。

---

# 41. 推荐 Repository 初始结构

可以考虑：

```text
poker-trainer/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── poker/
│   │   ├── strategy/
│   │   ├── analysis/
│   │   ├── llm/
│   │   └── storage/
│   │
│   ├── tests/
│   ├── data/
│   ├── pyproject.toml
│   └── Dockerfile
│
├── frontend/
│
├── tools/
│   └── trainer/
│
├── docker-compose.yml
├── AGENTS.md
└── README.md
```

这种 monorepo 对个人项目比较方便。

---

# 42. 最重要的几个技术风险

## 风险一：高估 CFR 第一版可以达到的水平

最容易失控的部分就是：

```text
Poker Solver
```

第一阶段目标应该是：

```text
合理、稳定、不可轻易 exploit 的训练 Bot
```

而不是：

```text
完整 GTO Solver
```

---

## 风险二：过度依赖 LLM

如果：

```text
Bot action → LLM
Review → LLM
Stats → LLM
```

最终所有功能都会变成 API 调用。

应保持：

```text
Game
Strategy
Analysis
```

都可以完全离线运行。

LLM 只是 presentation / coaching layer。

---

## 风险三：过度抽象

第一版不需要：

```text
microservices
event sourcing
DDD framework
CQRS
message queue
distributed cache
```

保持模块清晰比引入复杂架构更重要。

---

## 风险四：CFR 正确性

CFR 很容易因为：

```text
utility sign
reach probability
counterfactual probability
average strategy weighting
infoset construction
```

出现错误。

因此：

```text
Kuhn Poker validation
```

值得作为正式 milestone。

---

# 43. 建议 MVP Milestones

可以把项目拆成：

### M0 — Repository

```text
Python project
lint
test
Docker
CI
```

### M1 — Poker Engine

```text
Heads-Up NLHE
10,000 random simulations
```

### M2 — Basic Bot

```text
Random / Heuristic strategy
```

### M3 — Playable Web App

```text
FastAPI
Web UI
Hand History
```

### M4 — CFR Framework

```text
Kuhn Poker convergence
```

### M5 — Simplified Hold'em CFR

```text
abstraction
offline training
policy export
runtime lookup
```

### M6 — Review Engine

```text
strategy comparison
mistake detection
stats
```

### M7 — DeepSeek Coach

```text
explain hand
cache
usage tracking
```

### M8 — Deployment

```text
Docker Compose
HTTPS
backup
monitoring
```

---

# 44. 第一版“完成”的判断标准

比起功能数量，更建议使用下面这些标准：

```text
能够稳定连续打 1,000 手
```

没有：

```text
illegal action
invalid pot
duplicate card
state deadlock
```

Bot：

```text
响应 < 100ms
```

不调用 LLM。

服务器：

```text
正常 idle memory < 几百 MB
```

牌局结束后：

```text
可以查看完整 history
可以看到 reference strategy
可以看到主要错误
```

用户点击解释后：

```text
DeepSeek 给出结构化训练建议
```

这样已经是一套完整的练习平台。

---

# 45. 推荐的总体技术路线

综合开发成本、运行成本和训练价值，推荐采用：

```text
                Offline
                   │
            CFR Training
                   │
             Policy File
                   │
                   ▼

User ────── Poker Engine ────── CFR Runtime
  │
  │
  └──── Hand History
             │
             ▼
       Analysis Engine
             │
             ├── Strategy Review
             │
             ├── Mistake Detection
             │
             └── Stats
                     │
                     ▼
                DeepSeek
                     │
                     ▼
                AI Coach
```

核心思想可以归纳成一句：

> **运行时尽可能 deterministic、structured、local；只有语言解释部分使用远程 LLM。**

这种设计比较符合：

* 低服务器资源；
* 低长期成本；
* Python 开发效率；
* 个人部署；
* CodeBuddy 辅助开发；
* 后续逐步升级 CFR 水平；

这些目标。

---

# 46. 建议第一批 CodeBuddy 任务

项目启动后，可以优先让 CodeBuddy 依次完成：

```text
1. 初始化 Python/FastAPI 项目结构与测试框架

2. 实现与 Web 层无关的 Heads-Up Texas Hold'em Poker Engine

3. 为 Poker Engine 补充 exhaustive / randomized tests

4. 定义 Strategy Protocol，接入 RandomStrategy

5. 增加 HeuristicStrategy，使整个系统可实际试玩

6. 提供 FastAPI Game API

7. 实现 Hand History JSON 格式

8. 实现最小 Web Poker Table

9. 独立实现 Kuhn Poker CFR

10. 使用测试验证 CFR 收敛

11. 设计 Hold'em abstraction

12. 实现 offline policy export / runtime policy lookup

13. 实现 Hand Review 数据模型

14. 接入 DeepSeek Explanation Provider

15. 增加 LLM cache / usage budget

16. Docker Compose 部署
```

推荐在第 8 步之后先暂停 CFR 开发，实际试玩系统。

因为这个阶段往往会暴露：

```text
GameState
Action model
Hand History
API
```

中真正需要调整的地方。

等核心牌局系统稳定之后，再进入 CFR，整体返工量会明显更小。

---

# 47. 最后的架构取舍

初期最值得坚持的只有四条：

1. **Poker Engine 独立且经过充分测试。**
2. **Strategy 是插件式接口，而不是写死 CFR。**
3. **CFR Training 与 Runtime 完全分离。**
4. **DeepSeek 只负责解释，不负责决定实际扑克动作。**

除此之外，包括：

```text
数据库
前端框架
policy 文件格式
abstraction 算法
bet sizing
CFR variant
```

都可以根据实现过程逐步调整，不必在项目开始阶段锁死。
