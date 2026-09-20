# 48 M8：P2-3 历史 `pot_results` 差异只读诊断（规格冻结）

> 日期：2026-09-20。
>
> 本文件接在 `docs/47` / `docs/47a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/48` 记录本轮**规格与口径冻结**，`docs/48a` 记录与之对应的**只读诊断回执**。`docs/20` 至 `docs/47a` 未被改写。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P2-3** 一项的规格冻结与口径裁定。诊断本身是只读的，其回执在随后一次提交中落地。
>
> **本文件不产生任何策略、质量或资源证据**；未接入 CFR/查表、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、未上云、未改动真实数据库。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项）

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P2-3 | 四笔历史 `pot_results` 与当前结算不一致 | **是** |
| P0-1 … P0-7 | 注册表、查表预算、抽象映射、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**只读引用**） |
| P1-1 … P1-5 | 位置投影、范围假设、逐池收益、真实规则边界、性能复测 | 否（已完成，仅**只读引用**口径） |
| P2-1 | 2–9 人产品验收 | 否（已完成，仅**只读引用**） |
| P2-2 | N=9 的任何更强结论 | 否 |
| P2-4 | 跨 seed 稳定性的代码内建生产者 | 否 |

P2-3 **只是** `docs/35` §4.2 清单中的一项；本文件不改变其余条目的现状、优先级或失效条件。

### 1.2 用户答复原文

本轮采用「**先问用户**」。答复原文照录：

| 项 | 用户答复原文 |
|---|---|
| 执行确认 | 「P2-3 只读诊断（推荐）」(仅只读复放四手，复现差异、给出预期值与受影响样本；不改结算规则、不写库、不训练。) |

据此，**被授权**：以只读方式复放 `docs/23` §6.1 记录的四手历史（`fe2a542f…`、`db0948fc…`、`5356c818…`、`37810a1d…`），复现差异、给出预期值与受影响样本，并新增 `docs/48*`。

**被拒绝**（本轮不做）：修改 `backend/app/poker/**`（含 `_settle_showdown` 与任何结算语义）、`backend/app/analysis/**`、`backend/app/storage/**`（含 `models.py`：**不加列、不迁移**）、`backend/app/api/**`、`backend/app/strategy/**`、`frontend/**`、锁文件、真实数据库、`tools/trainer/**`；新增受监督运行或 campaign；追加 seed；重试 authorization；把 P0-2 查询路径数字表述为端到端决策延迟；恢复已移除的前端策略选择器。

### 1.3 口径冻结（诊断协议，实施前的唯一依据）

| 裁定 | 内容 |
|---|---|
| 一 | **先判字段存在性，再谈差异**：任何一手，必须先在**原始** `history_json` 中确认 `pot_results` 是否存在。若不存在，该手的差异只能判定为「**历史记录缺项**」；**不得**与「历史值为一个与当前结算不同的具体值」混为一谈。 |
| 二 | **重放复用既有实现**：不另造一套重放。复用 `backend/app/analysis/hand_review.py` 的 `_history_action()` / `_replay_action()` 与 `PokerEngine.start_hand_with()`，按各座位 `starting_stack` 逐人还原、跳过历史盲注动作。 |
| 三 | **只读不改结算**：本诊断**不调用**会派彩并推进的接口、**不**在决策期调用 `_settle_showdown()`、**不**修改任何结算规则或常量。 |
| 四 | **比较项固定**：逐手比较最终公共牌、`winners`、各座位 `net`，以及（仅当原始记录存在时）`pot_results` 的 `amount` / `winners` / `shares` 与 `showdown_hands`。 |
| 五 | **受影响样本分类**：分三类分别计数与陈述——(a) 摊牌但原始记录**缺** `pot_results` 的手；(b) 非摊牌手（按 `build_hand_history` 设计天然不带 `pot_results`，**不计**为受影响）；(c) 动作与当前合法性不兼容、无法完整重放的手。 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 8]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -3 --oneline
133c99c feat: enforce 2-9 player product range and geometry-driven seat layout
2ac96dd docs: freeze p2-1 player count product acceptance specs
ead27f2 feat: add controlled decision latency measurement and post-fix remeasurement

$ git rev-parse HEAD          -> 133c99cbf541e9bf49d1f5f2e795ca6585e91d8d
                            （短 133c99c，`feat: enforce 2-9 player product range and geometry-driven seat layout`）
$ git rev-parse origin/master -> f9e957bf9f9a1df89bb92957c01e031d5d48723d

$ ls -1 backend/app/strategy/*.py | wc -l      -> 14
$ ls -1 backend/tests/test_*.py | wc -l        -> 28
$ cd backend && uv run pytest -q               -> 668 passed, 2 skipped, 2 warnings
```

本轮开始前工作区 **0 行**；未做任何 `reset` / `clean` / `stash` / `checkout`；本轮**不 push**。

真实库只读指纹（诊断时实测）：

```text
$ shasum -a 256 backend/data/holdem.db
b804bc4958543601ea9659090c20eae503a295d0b9494d0dc122f73abe3d0750
```

> 与 `docs/23` §6.1 记录的 `75aaa9f3…3ce` **不同**，差异可由「该记录之后新增手数（`docs/23` 时 315 手 → 当前 343 手）」解释；`backend/app/storage` 无对 `hands` 的 `UPDATE` 路径，历史行以追加方式保留。该差异只作事实披露，**不作为**任何结论的依据。

## 3. 诊断口径（预注册）

### 3.1 样本与只读约束

- 样本为真实库 `backend/data/holdem.db` 中 **全部** 手（当前 343 手），并以连接级约束保证只读：SQLite URI `mode=ro`、`PRAGMA query_only=ON`、显式 `BEGIN` / `ROLLBACK`、按值参数绑定。
- 重点关注 `docs/23` §6.1 记录的四手：`fe2a542feb08481eae97d6aa677ebcc5`、`db0948fc24ed409fbcd9710cecd5a45c`、`5356c818812a47739d1093b8eca1ca18`、`37810a1d646e4c149c3acfddafa61e32`。

### 3.2 复算方法

- 对每手：按 `players[].starting_stack` 逐人还原筹码，用 `start_hand_with(button, hole_cards, board)` 起手（跳过随机洗牌与发牌），跳过历史中的 `small_blind` / `big_blind` 记录，其余动作经 `_history_action()` → `_replay_action()` 后 `apply_action()` 重放至终局。
- 重放过程中若出现座位不一致或非法动作，记为该手**无法完整重放**（第 (c) 类），不保留成功前缀。

### 3.3 比较项与差异分类

| 比较项 | 差值判定 |
|---|---|
| 最终公共牌 `board` | 重放结果与原始记录逐张对比 |
| `winners` | 集合对比 |
| 各座位 `net` | 逐座位整数对比 |
| `pot_results`（仅原始记录存在时） | `amount` / `winners` / `shares` 逐项对比 |
| `showdown_hands`（仅原始记录存在时） | 存在性与内容对比 |

差异**只**允许归入两类之一，并分别计数：

1. **缺项类**：原始记录不含 `pot_results`（可能连带不含 `showdown_hands`），无可比之值；
2. **不同值类**：原始记录含 `pot_results`，但其值与当前引擎重放结果不同。

### 3.4 「预期值」的定义

「预期值」指**当前引擎对同一手重放后**产出的终局结算明细（`pot_results` 的 `amount` / `winners` / `shares`）与各座位 `net`。它只描述「当前结算会给出什么」，**不是**对历史记录正确性的判决，也**不**主张历史记录错误。

### 3.5 不得声称

- 不得由本诊断**修改**任何结算规则或常量；成因未定前不改结算（本轮口径即为「只读」）。
- 不得把「历史记录缺字段」表述为「结算错误」「结算不一致（不同值）」或「规则回归」。
- 不得把单库、单版本、343 手的观察外推为对全部历史、对其它人数（N=2–9）或对未来版本的结论。
- 不得把本诊断与 `docs/23` 的平局份额问题、`docs/22` 的短码叫价问题或任何策略/质量结论混为一谈。

## 4. 边界（沿用不可回退边界）

- **只读**：`backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/api/**`、`backend/app/storage/**`、`backend/app/strategy/**`、`frontend/**`、`tools/trainer/**`。
- **不得修改**：`backend/app/storage/models.py`（不加列、不迁移）、`backend/uv.lock`、`frontend/package-lock.json`、真实数据库 `backend/data/holdem.db`、`docs/20` 至 `docs/47a`；`heuristic.py` 的决策语义；`equity()` 的 `ties/2` 与采样数；`lookup_budget.py` 的既有常量。
- **必须保持**：`history_json` 原始事实不被改写；公开 API 一律 Pydantic model；统一支持 2–9 人；所有随机过程可注入 seed。

## 5. 不在本轮范围

- 不修改结算规则、不新增/变更任何列或迁移、不写真实库。
- 不实现任何可复用的「纯查询入口」或生产代码（若将来需要，须单独授权并在 `poker/` 中以无副作用投影实现）。
- 不启动受监督运行或 campaign、不追加 seed、不重试 authorization。
- 不推进 P2-2 / P2-4，也不改变 `docs/35` §4.2 中其余条目的状态。
