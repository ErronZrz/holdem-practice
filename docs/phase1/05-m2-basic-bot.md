# 05 M2 Basic Bot 实现记录

> 本文档记录 M2（Basic Bot：Random + Heuristic 策略）完成后落地的实现细节与关键决策，作为后续 M3~M8 的开发依据。
>
> **文档权威性**：遵循 `03-execution-plan.md` 第 8 节约定，本文档是 `04` 之后的「实现快照」。当本文档与 `01`/`02`/`03`/`04` 冲突时，**以本文档为准**。

---

## 1. 交付内容总览

在 `backend/app/strategy/` 下实现插件式 Bot 策略，不修改 `poker/` 领域逻辑。

| 文件 | 职责 |
|---|---|
| `interface.py` | `Strategy` Protocol 统一接口 + `hero()` 视角辅助 + 信息边界约定 |
| `random_strategy.py` | `RandomStrategy`：合法动作内均匀随机，seed 可注入 |
| `heuristic.py` | `HeuristicStrategy`：强牌加注 / 中牌跟注 / 弱牌弃牌 |
| `__init__.py` | 汇总导出 `Strategy` / `hero` / `RandomStrategy` / `HeuristicStrategy` |

测试在 `backend/tests/test_strategy.py`（10 个用例）。

---

## 2. 统一接口与信息边界

```text
class Strategy(Protocol):
    def choose_action(self, state: GameState, legal: LegalActions) -> Action: ...
```

- 策略只通过 `GameState`（`engine.snapshot()`）与 `engine.legal_actions()` 交互，不触碰引擎内部状态，符合 AGENTS 原则 2。
- `hero(state)` 返回 `state.players[state.current_seat]`，即当前行动玩家，作为「策略视角下的自己」。

**信息边界约定**（解决 M1 快照含全部 hole_cards 的问题）：

- 策略只允许读取当前行动玩家自己的 `hole_cards`、公共牌 `board`、底池 `pot`、阶段 `street`、庄位 `button`，以及各玩家的公开状态（stack / folded / all_in / street_bet / total_committed）。
- 严禁读取 `state.players[i].hole_cards`（`i != state.current_seat`）。
- 此约定以接口模块 docstring 明文声明，后续策略实现须遵守。

---

## 3. RandomStrategy

- 从合法动作中均匀随机选择一个动作类型；BET / RAISE 的金额在 `[min, max]` 区间内均匀随机。
- 构造器 `RandomStrategy(seed=None)` 注入 `random.Random(seed)`，可复现（AGENTS 原则 4）。

---

## 4. HeuristicStrategy

### 4.1 牌力分档

统一映射为三档 `Strength`（WEAK / MEDIUM / STRONG）：

**翻牌前**：用 Chen 公式给两手底牌打分，再按阈值分档。

- Chen 分数 ≥ 12 → STRONG（如 AA / KK / QQ / JJ / AKs）
- Chen 分数 ≥ 8 → MEDIUM（如 TT / AKo / KQs / T9s）
- 其余 → WEAK（如 72o / 小对子 / 小连张）

**翻牌后**：用 `evaluate(底牌 + 公共牌)` 得到 `HandRank`，按牌型分档。

- 三条及以上（三条/顺子/同花/葫芦/四条/同花顺）→ STRONG
- 一对 / 两对 → MEDIUM
- 高牌 → WEAK

### 4.2 动作倾向

| 档位 | 能过牌时 | 面对下注时 |
|---|---|---|
| STRONG | 下注（BET） | 加注（RAISE），无法加注则跟注 |
| MEDIUM | 过牌（CHECK） | 跟注（CALL） |
| WEAK | 过牌（CHECK） | 弃牌（FOLD） |

所有分支都从 `LegalActions` 的合法集合内取值，保证返回合法动作。

### 4.3 下注/加注额度

- 下注额 ≈ 一个底池，夹在 `[min_bet, max_bet]` 内。
- 加注后总额 ≈ 「当前跟注额 + 一个底池」，夹在 `[min_raise_to, max_raise_to]` 内；其中「当前跟注额」由 `me.street_bet + legal.call_amount` 推导。

### 4.4 已知取舍

- 本策略为**确定性策略**，不做位置感知、不做诈唬/慢玩混合（对应 `02` D2「合理、不轻易被 exploit」的底线，D7「初期不做位置感知」）。确定性带来的可预测性属已知取舍，后续 CFR（M7/M8）或混入随机可增强。
- Chen 公式与牌型阈值是人工拍定的启发式，非 GTO；后续若需更细牌力可替换 `_preflop_strength` / `_postflop_strength` 实现，接口不变。

---

## 5. 与 04 文档的偏差

| 点 | 04/规划表述 | 实际落地 |
|---|---|---|
| 策略文件名 | 目录约定 `interface / random / heuristic` | `interface.py` / `random_strategy.py` / `heuristic.py`（`random.py` 会与标准库 `random` 同名，故加后缀避免歧义） |
| 视角方案 | 04 仅提示「快照含全部底牌」 | 落地为 `hero()` + 接口 docstring 明文约定「只读自己底牌」，未引入额外的视角快照结构 |

---

## 6. 测试与验收

```text
$ uv run ruff check .        # All checks passed
$ uv run pytest -q           # 44 passed, 2 warnings
```

- 新增 10 个策略用例：随机策略可复现、只返回合法动作；启发式策略翻牌前/后强中弱牌动作倾向、免费看牌不过度弃牌；两个 `HeuristicStrategy` bot 经引擎跑 200 手，无非法动作、无死锁、筹码守恒、盈亏归零。
- 2 条 warning 仍来自 `fastapi.testclient` 依赖（starlette/httpx 弃用提示），与策略无关。
