# 04 M1 Poker Engine 实现记录

> 本文档记录 M0（仓库骨架）与 M1（Poker Engine）完成后落地的实现细节与关键决策，作为后续 M2~M8 的开发依据。
>
> **文档权威性**：遵循 `03-execution-plan.md` 第 8 节的约定——本文档是 `03` 之后的「实现快照」。当本文档与 `01`/`02`/`03` 冲突时，**以本文档为准**；后续实现若再偏离，应新增编号更大的文档（如 `05-...`），而非改写本文档。

---

## 1. M0 仓库骨架（回顾）

M0 已交付，目录与工具链如下：

- **backend/**：FastAPI + Pydantic + SQLAlchemy，`uv` 管理依赖（`pyproject.toml` + `uv.lock`），`uv run ruff check .` 与 `uv run pytest -q` 通过。
- **backend/app/api/health.py**：`GET /health` 接口，已有 `tests/test_health.py`。
- **frontend/**：Vue 3 + Vite（`package.json` / `vite.config.js`），`npm run build` 通过。
- **docker-compose.yml**、**backend/Dockerfile**：本地/云部署预留。
- **.github/workflows/ci.yml**：GitHub Actions CI。
- **AGENTS.md / README.md / .gitignore**：项目约束与说明。
- **尚未 `git commit`**（仓库为 no commits yet 状态）。

---

## 2. M1 交付内容总览

在 `backend/app/poker/` 下实现纯 Python、无 Web 依赖的德州扑克规则引擎，全部按 N 人设计。

### 2.1 模块清单

| 模块 | 职责 |
|---|---|
| `cards.py` | `Suit`/`Rank` 枚举、不可变可哈希 `Card`（含 `"As"` 式可读 `__str__`） |
| `deck.py` | 52 张牌堆；洗牌随机源可注入 `seed`，顺序发牌天然避免重复 |
| `hand.py` | `HandCategory`（高牌~同花顺）+ 可比较的 `HandRank` |
| `evaluator.py` | 5~7 张牌求最强 5 张（`combinations` 7 选 5；含 A-2-3-4-5 轮子顺子） |
| `state.py` | `Street` / `PlayerState` / `GameState`（只读快照） |
| `actions.py` | `Action` / `LegalActions` / `IllegalActionError` |
| `engine.py` | `PokerEngine`（发牌、下注轮、街流转、摊牌、结算） |

### 2.2 `PokerEngine` 生命周期与对外接口

```text
engine = PokerEngine(num_players, small_blind, big_blind, starting_stack, seed=None)
engine.start_hand()               # 轮转庄位、发底牌、下盲注、定位首个行动者
while not engine.hand_over:
    legal = engine.legal_actions()  # 返回 LegalActions
    engine.apply_action(action)      # 非法动作抛 IllegalActionError
# 结束后可读 engine.winners / engine.last_net / engine.history / engine.snapshot()
```

`legal_actions()` 返回的 `LegalActions` 完整描述当前玩家可选动作与额度区间（`can_fold/can_check/can_call/call_amount/can_bet/min_bet/max_bet/can_raise/min_raise_to/max_raise_to`），供后续 strategy 采样，引擎不关心策略如何选择。

---

## 3. 关键设计决策

### 3.1 筹码单位与随机性（对应 AGENTS 原则 4/5）

- 筹码统一为**整数单位**，全程无浮点。约定 `small_blind=5 / big_blind=10 / starting_stack=1000`（即 100BB）。
- 所有随机过程（洗牌）通过构造器 `seed` 注入 `random.Random`，可复现。

### 3.2 N 人设计与单挑特例（原则 8）

- 引擎以「座位 0..N-1 + 庄位 `button`」建模，未写死 2 人。
- 盲注与行动顺序对单挑做特例处理：

| 场景 | 规则 |
|---|---|
| 单挑（N=2） | 庄位即小盲（SB = button），大盲为另一玩家 |
| N≥3 | SB = 庄位左侧，BB = SB 左侧 |

### 3.3 行动顺序（位置轮转）

- 每手开始庄位顺时针轮转：`button = (button + 1) % N`，首手庄位为最后一个座位。
- preflop 首个行动者：单挑为庄位（小盲）；N≥3 为 BB 左侧（枪口位）。
- postflop 首个行动者：庄位左侧（单挑即大盲，多人即小盲）。
- 任何阶段均跳过已弃牌/已全下玩家。

### 3.4 下注 / 加注 / 最小加注 / 全下

- 每街 `current_bet` 为当前需跟注总额，`min_raise` 为最小加注幅度（每街初始 = 大盲）。
- **BET**：仅当 `current_bet == 0`，下注额 ∈ `[min(big_blind, all_in_total), all_in_total]`。
- **RAISE**：仅当 `current_bet > 0` 且行动未被锁定，加注后总额 ∈ `[min_raise_to, all_in_total]`；`min_raise_to = current_bet + min_raise`，若余额不足以完整加注则只能全下（短码加注）。
- **完整加注**（增量 ≥ `min_raise`）更新 `min_raise` 为本次增量；**短码全下加注**（增量 < `min_raise`）不更新 `min_raise`。
- **CALL** 在余额不足时自动转为全下跟注。

### 3.5 行动重开（reopen）机制

用每个玩家 `has_acted_since_full_raise` 标志实现「短码全下加注不重开行动」：

- 完整加注：重置所有玩家标志为 `False`，加注者置 `True`（其他人可再行动/再加注）。
- 短码全下加注：不重置标志（已行动过的玩家只能跟注或弃牌，不能再加注）。
- 下注轮结束条件：所有未弃牌未全下玩家 `street_bet == current_bet` 且 `has_acted_since_full_raise == True`。

### 3.6 边池切分与未跟注退还

摊牌结算按「所有玩家投入层级」切分边池，覆盖任意 N 人的部分全下：

1. 取所有玩家（含弃牌者）`total_committed` 的不同正数层级 `levels`，逐层处理。
2. 每层 `contributors` = 投入 ≥ 该层的玩家；`eligible` = 其中未弃牌者；层金额 = `(level - prev) × |contributors|`。
3. `eligible` 非空 → 该层为边池，按牌力在 eligible 内争夺。
4. `eligible` 为空（该层全部由弃牌玩家投入，无人可争夺）→ 整层退还 `contributors` 本人（每人 `level - prev`）。

> 该算法由构造保证筹码守恒。M1 自测期间曾发现并修复一个边池 bug：多个弃牌玩家并列最高投入、且高于所有未弃牌玩家时，原「只退还单个最高者」的逻辑会丢弃无人争夺的层级，已改为上述空层退还方案。

### 3.7 街流转与自动跑完

- 下注轮结束 → 若在 river 则摊牌；否则 `_advance_street` 发公共牌（flop 3 张、turn/river 各 1 张），重置 `current_bet=0 / min_raise=big_blind / street_bet=0 / 标志=False`，首个行动者 = 庄位左侧。
- 若新街无可下注玩家（未弃牌未全下 ≤ 1 人）→ `_run_out` 直接发完余牌进入摊牌。
- 仅剩 1 名未弃牌玩家 → 不经摊牌，直接由其赢得全部底池。

### 3.8 摊牌、并列与结算

- 摊牌时用 `evaluate(hole_cards + board)` 逐池比较，最强牌力者赢池。
- 并列平分：`share = 池额 // 赢家人数`，余数按座位号升序依次每人 1 筹码（确定性规则）。
- `last_net` 记录每手各座位净盈亏（相对本手起始筹码），用于校验守恒与后续统计。

### 3.9 自动补码（rebuy）

- `start_hand` 的 `_reset_players` 中，筹码 ≤ 0 的玩家自动补码至 `starting_stack`，对应 `02` 文档 D4「输光自动 rebuy」。

### 3.10 `GameState` 快照（为 M2 预留）

- `engine.snapshot()` 返回冻结的 `GameState`（street / board / pot / current_seat / button / hand_over / players 副本），供 strategy 按 `02` 约束「只能通过 GameState 与 poker 交互」。正式 strategy 接口在 M2 落地。

---

## 4. 与需求 / 规划文档的偏差

| 点 | 旧文档表述 | 实际落地 |
|---|---|---|
| 引擎人数 | `01` Phase 1 写「Heads-Up」 | 按 `02` D7「N 人设计」，仿真覆盖 2/3/5 人 |
| side pot | `01` 建议 HU 第一版简单处理 | 按 N 人完整实现边池切分 + 未跟注退还 |
| rebuy | `02` D4 描述为 Session 规则 | M1 暂以引擎 `start_hand` 内自动补码承载，Session 层在 M3 再落实 |
| GameState | `03` 目录约定 strategy 经 GameState 交互 | M1 先提供 `snapshot()` 快照，strategy 接口延后到 M2 |

---

## 5. 测试与验收

### 5.1 测试文件

| 文件 | 覆盖 |
|---|---|
| `tests/test_cards.py` | 52 张唯一、seed 复现、发牌越界 |
| `tests/test_evaluator.py` | 全部牌型、轮子顺子、7 选 5、大小比较 |
| `tests/test_engine.py` | 盲注/位置、弃牌、过牌到底、bet/raise、min-raise、all-in 跑完、边池切分+未跟注退还、弃牌玩家未跟注退还、位置轮转、筹码守恒、快照 |
| `tests/test_simulation.py` | 2 人 10,000 手 + 3 人 3,000 手 + 5 人 2,000 手随机对局，校验无非法动作/无重复发牌/无死锁/筹码守恒/盈亏归零 |
| `tests/helpers.py` | 字符串牌转 `Card` 的测试辅助 |

### 5.2 运行结果

```text
$ uv run ruff check .        # All checks passed
$ uv run pytest -q           # 34 passed, 2 warnings
```

- 2 条 warning 来自 `fastapi.testclient` 依赖（starlette/httpx 弃用提示），与 poker 引擎无关。
- 仿真校验的不变量：每手无重复发牌、任意时刻无负筹码/负投入、未全下玩家 `street_bet ≤ current_bet`、单手动作数 < 1000（防死锁）、结束筹码守恒、`last_net` 求和为 0。

---

## 6. 后续注意事项

- **尚未 commit**：M1 完成后按用户要求暂未提交，待确认后统一提交。
- `strategy/`、`api/`（除 health）、`llm/`、`storage/`、`analysis/`、`tools/trainer/` 仍为空壳/未接入，引擎未依赖其中任何模块，符合 AGENTS.md 边界。
- 下一里程碑 **M2（Basic Bot）**：在 `strategy/` 定义 Strategy 接口，实现 Random + Heuristic，通过 `engine.legal_actions()` + `engine.snapshot()` 与引擎交互。
