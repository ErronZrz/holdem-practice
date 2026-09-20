# 45 M8：P1-4 真实 Hold'em 的下注尺度与公共牌——抽象映射之外的界与实际规则切片的明确划分（规格冻结）

> 日期：2026-09-20。
>
> 本文件接在 `docs/44` / `docs/44a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/45` 记录本轮**规格与决策冻结**，`docs/45a` 记录与之对应的**实施与验证回执**。`docs/20` 至 `docs/44a` 未被改写。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P1-4** 一项的规格冻结与设计岔路裁定。代码与测试在随后一次提交中落地，回执见 `docs/45a`。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项）

本轮用户明确授权的实施范围**只有一项**，来自 `docs/35` §4.2 的 P1 组：

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P1-4 | 真实 Hold'em 的下注尺度与公共牌 | **是** |
| P0-1 … P0-7 | 注册表、lookup 预算、抽象映射、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**只读引用**其口径） |
| P1-1 | 位置与公开行动历史的信息集投影 | 否（已完成，仅**声明性引用**） |
| P1-2 | 范围模型替代「vs 随机底牌」 | 否（已完成，仅**声明性引用**） |
| P1-3 | 逐池货币收益（短码 / 边池 / 多人平局） | 否（已完成，仅**声明性引用**） |
| P1-5 | 修复后 6/7（及 2–9）人性能复测 | 否 |
| P2-1 … P2-4 | 2–9 人产品验收、N=9 结论、历史 `pot_results`、稳定性生产者 | 否 |

P1-4 **只是** `docs/35` §4.2 清单中的一项；本文件不改变其余条目的现状、优先级或失效条件，也不构成任何实施授权。

### 1.2 用户答复原文（执行确认与四个设计岔路）

本轮采用「**先问用户**」而非「先在文档冻结规格」。答复原文照录：

| 项 | 用户答复原文 |
|---|---|
| 执行确认与边界 | 「确认执行，边界如上」(backend/app/poker/**、analysis/**、api/**、frontend/**、storage/models.py、tools/trainer/**（含 multiplayer_cfr）、锁文件、真实数据库一律零改动且只读，仅作规范出处引用) |
| 岔路一：载体与命名 | 「新增 real_rules_boundary.py」(backend/app/strategy/real_rules_boundary.py；零生产调用方，与 P1-1/P1-2/P1-3 平行（推荐）) |
| 岔路二：本轮交付范围 | 「只交付边界划分契约」(受限抽象切片事实 + 真实规则切片 + 逐条边界判定 + 明确失败 + 局限声明；不实现真实牌堆/公共牌/下注尺度，也不实现 P1-3 遗留的期望项抽样（推荐）) |
| 岔路三：边界取值与既有契约关系 | 「按建议冻结」(受控闭集三值：in-abstraction-slice / out-of-abstraction / contracted-not-wired；复用 P0-3 的失败与回退语义（明确失败、不得最近桶/补零/插值），不替代 judge_coverage；对 P1-1/P1-2/P1-3 与 tools/trainer 只作声明性引用（常量 + 测试锁定，不 import）（推荐）) |

据此，**被授权**：在 `backend/app/strategy/` 新增边界契约模块（不改既有模块语义）、在 `backend/tests/` 新增回归测试、新增 `docs/45*`。
**被拒绝**（本轮不做）：`tools/trainer/**` 与 `backend/app/poker/**` 任何改动或不 import 之外的引用；`backend/app/analysis/**`、`backend/app/api/**`、`frontend/**`、`backend/app/storage/models.py` 任何改动；真实牌堆/公共牌/下注尺度的实现；P1-3 遗留期望项的抽样实现；任何生产接入。

### 1.3 三项裁定（冻结）

| 岔路 | 裁定 |
|---|---|
| 一 | 新增 `backend/app/strategy/real_rules_boundary.py` 作为**纯函数 + 冻结 Pydantic 模型**入口；**不改动** `poker/`、`analysis/`、`trainer` 的任何文件；本模块**零生产调用方**，不改变任何运行时路径与对外响应。 |
| 二 | 本轮**只交付边界划分契约**：受限抽象切片事实 + 真实规则切片 + 逐条边界判定 + 明确失败 + 局限声明。**不实现**真实牌堆、公共牌、可变下注尺度、真实牌力评估，也**不实现** P1-3 遗留的期望项抽样；「真实下注尺度」与「公共牌」在本轮被**划到抽象之外的界**，而不是被实现。 |
| 三 | 边界判定取值是**受控闭集三值** `in-abstraction-slice` / `out-of-abstraction` / `contracted-not-wired`（见 §4.3）；**复用** P0-3 的失败与回退语义（抽象外必须明确失败、不得用最近桶/补零/插值冒充精确），但**不替代** `judge_coverage`——本模块**不**接收 `GameState`、**不**判定任何真实局面是否落入抽象。对 P1-1 / P1-2 / P1-3 与 `tools/trainer` 只作**声明性引用**（受控常量 + 测试锁定，**不** import），判定不可由调用方改写。 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 2]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -4 --oneline
edcc224 feat: add controlled per-pot monetary payoff contract
01dcb29 docs: freeze p1-3 per-pot monetary payoff contract specs
f9e957b feat: add controlled action-line range assumption contract
3ea9140 docs: freeze p1-2 action-line range assumption contract specs

$ git rev-parse HEAD          -> edcc2242433610a39718f5db79e904105063b0f5
$ git rev-parse origin/master -> f9e957bf9f9a1df89bb92957c01e031d5d48723d

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
$ find /Users/bryanylliu/holdem-campaigns -name strategy.json | wc -l
11
```

`ahead 2` 即 `docs/44` 冻结（`01dcb29`）与 P1-3 实现（`edcc224`）两个**本地**提交，本轮不改变该状态、**不 push**；工作区 0 行。未做任何 `reset` / `clean` / `stash` / `checkout`。

只读核对（不构成任何实验证据）：

```text
tools/trainer/src/multiplayer_cfr/game.py
  GAME_ID      = "m8-unique-rank-single-open"
  GAME_VERSION = "m8-a-v1"
  ALLOWED_PLAYER_COUNTS = frozenset({6, 7, 9})
  ANTE = 1
  BET  = 1
```

## 3. 现状事实与必然落差（只读核验）

### 3.1 受限抽象（候选 A）的公开事实

只读引用 `docs/26` §4.1 / §5.1 与 `tools/trainer/src/multiplayer_cfr/game.py`（**零改动、零 import**）：

| 事实 | 取值 |
|---|---|
| `game id` / `version` | `m8-unique-rank-single-open` / `m8-a-v1` |
| 人数 | `{6, 7, 9}`（只支持这三档，不是 2–9 连续） |
| 强制投入 | `ante = 1`，**无盲注** |
| 下注 | **固定** `bet = 1`；单街道、单次开池，第一名 `b` 之后不允许开池或加注 |
| 行动集 | `x` / `b` / `c` / `f` 四种 |
| 牌 | 恰好 `N` 张**全序唯一 rank**，全部发出，每人一张；**无公共牌**；**同级平局不可能发生** |
| 收益 | 整数常和 `u_i = w_i - c_i`，`Σ w_i = P`、`Σ u_i = 0` |
| 不建模 | 盲注、多街道、公共牌、可变下注尺度、再加注、all-in、可变筹码深度、边池、多人平局、真实牌力、真实范围 |

`docs/26` §5.1 已明确：候选 A「**不**验证多人平局、整数余数、公共牌、范围、边池、短码或真实 Hold'em 牌力」。

### 3.2 已完成的受控契约（本轮只作声明性引用）

| 产物 | 模块 | 承载的口径 |
|---|---|---|
| P0-3 抽象映射与覆盖 | `abstraction.py` | `AbstractProjection` / `CoverageVerdict` / `declared_fallback` / `judge_coverage` |
| P0-2 逐层资格投影 | `poker/pot_projection.py` | `project_pot_layers()` / `project_candidate_call()`（只做资格，无收益） |
| P1-1 位置与公开行动线 | `position_projection.py` | 相对座位 / 行动顺序 / 按街分段的公开动作线 |
| P1-2 范围假设 | `range_assumption.py` | 角色 → 起手牌类权重的**声明式**假设（不随公共牌收窄） |
| P1-3 逐池货币收益口径 | `pot_ev_contract.py` | 逐层处置 / 确定回收 `R_h` / 实际支付 `A` / σ；期望项**未求值** |

这些产物**都未接入生产**，也**都不构成**真实牌局 EV 或质量证据。

### 3.3 必然落差（必须如实写明）

1. 候选 A 的结果是**受限抽象上的常和整数效用**，**不是**真实 NLHE 的行动价值、EV 或 GTO 结论；`docs/26` §7 已把「6–9 人完整 Hold'em GTO / 真实范围或真实下注尺度的质量 / 边池、短码、逐层资格或 CALL EV 的正确性」列为该推荐**证明不了**的结论。
2. 真实下注尺度与公共牌在本轮**被划到抽象之外的界**：它们既无抽象实现，也无受控契约承载，因此任何「按最近桶 / 补零 / 插值 / 默认尺度」把它们映射进抽象的做法都必须**明确失败**。
3. P1-3 的期望项 \(E[\sum_\ell S_{h,\ell}\mid\sigma]\) 在本轮**仍未被求值**：真实牌堆与联合 runout 的抽样不在 P1-4 的授权内（§1.3 裁定二）。
4. 由此：**不得**把候选 A 的受限结果表述为真实牌局 EV；**不得**把本轮的边界表表述为「已支持真实 Hold'em」或「已接入生产」。

## 4. P1-4 规格（冻结）

### 4.1 契约结构版本与基准标识

```text
REAL_RULES_BOUNDARY_SCHEMA_VERSION = "real-rules-boundary.v1"
REAL_RULES_BOUNDARY_BASIS = "abstraction-slice-vs-real-rule-slices"
```

### 4.2 受限抽象切片事实（冻结，声明常量 + 测试锁定）

以下常量与本轮**只读引用**的受限抽象描述逐字对齐，并由**一条测试**读取训练器源文件锁定其不漂移；本模块**不 import** 训练器（后端与训练器是两个独立 `uv` 工程）：

| 常量 | 值 |
|---|---|
| `ABSTRACTION_GAME_ID` | `"m8-unique-rank-single-open"` |
| `ABSTRACTION_GAME_VERSION` | `"m8-a-v1"` |
| `ABSTRACTION_PLAYER_COUNTS` | `(6, 7, 9)` |
| `ABSTRACTION_ANTE` | `1` |
| `ABSTRACTION_BET` | `1` |
| `ABSTRACTION_ACTION_TOKENS` | `("x", "b", "c", "f")` |

### 4.3 边界判定取值 `BoundaryVerdict`（冻结，闭集三值）

| 取值 | 语义（互斥） |
|---|---|
| `in-abstraction-slice` | 受限抽象**实际实现并结算**的真实规则元素 |
| `out-of-abstraction` | 真实规则中**既无抽象实现、也无受控契约承载**的元素；必须明确失败 |
| `contracted-not-wired` | **已有受控契约承载其口径**、但**未接入生产**且**不构成真实 EV** 的元素 |

约束：

1. 取值是**闭集**，不得新增第四值；
2. `in-abstraction-slice` 与 `out-of-abstraction` 的 `prerequisite` **必须**为 `"none"`；
3. `contracted-not-wired` 的 `prerequisite` **必须**是 §4.5 受控前置标识之一；
4. **判定不可由调用方改写**：任何条目的 `verdict` / `prerequisite` 必须与冻结目录**逐字相等**，否则构造失败。

### 4.4 真实规则切片 `RuleSliceBoundary`（冻结，字段齐备）

`RuleSliceBoundary` 是**冻结的 Pydantic model**，字段恰好五项：

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `feature` | `str` | 受控切片标识（连字符形式，不含模块路径） |
| 2 | `description` | `str` | 中文说明 |
| 3 | `verdict` | `str` | §4.3 三值之一 |
| 4 | `prerequisite` | `str` | 受控前置标识；无则为 `"none"` |
| 5 | `declaration` | `str` | 该切片的**边界声明**：提供什么 / 明确不提供什么 |

冻结目录（20 条，顺序即契约顺序）：

**`in-abstraction-slice`（6 条，`prerequisite = none`）**

| feature | declaration 要点 |
|---|---|
| `relative-seat-order` | 相对座位 `0..N-1` 与行动次序由公开历史唯一派生 |
| `public-action-history` | 规范 `action@relative-seat` token 历史，可复核 |
| `fold-and-alive-state` | 弃牌跨行动持久；弃牌者投入是死钱 |
| `fixed-integer-contributions` | `ante = 1` 与固定 `bet = 1`，全部为整数筹码单位 |
| `constant-sum-utility` | 每个终局 `Σ w_i = P` 且 `Σ u_i = 0` |
| `private-information-key` | 信息集键只含行动者自己的 rank 与规范公开历史 |

**`out-of-abstraction`（7 条，`prerequisite = none`）**

| feature | declaration 要点 |
|---|---|
| `blinds-and-forced-bets` | 抽象无盲注；真实盲注结构不映射 |
| `multi-street-betting` | 抽象单街道；翻牌/转牌/河牌的下注轮不映射 |
| `public-board` | 抽象无公共牌；真实公共牌发出与牌面不映射 |
| `variable-bet-sizing` | 抽象固定 `bet = 1`；真实尺度、最小加注与底池比例不映射 |
| `re-raise-multi-level` | 抽象单次开池；再加注与多层加注不映射 |
| `real-card-evaluation` | 抽象为唯一 rank 比较；真实 52 张牌力评估不映射 |
| `opponent-real-hole-cards` | 对手真实底牌不进入任何投影、假设或收益口径 |

**`contracted-not-wired`（7 条，`prerequisite ≠ none`）**

| feature | prerequisite | declaration 要点 |
|---|---|---|
| `all-in-and-short-stack` | `candidate-call-pot-projection` | 只有实际支付 `A` 与逐层资格投影；未接入策略或复盘 EV |
| `side-pots` | `candidate-call-pot-projection` | 只有公开投入的逐层资格；真实边池结算与逐层货币收益未建模 |
| `multiway-tie-share` | `pot-ev-contract` | 只有名义份额 `1/k` 与整数派彩的**分开声明**；期望项未求值 |
| `per-pot-monetary-payoff` | `pot-ev-contract` | 只有逐层处置与确定回收口径；不产出 CALL EV 数值 |
| `position-and-action-line-projection` | `position-projection` | 只有相对座位与公开动作线投影；未接入生产 |
| `action-line-range-assumption` | `range-assumption` | 只有声明式范围假设；不随公共牌收窄，不是求解器输出 |
| `abstraction-mapping-and-coverage` | `abstraction-coverage` | 只有受控抽象键与覆盖判定；不代劳真实局面到抽象的映射 |

### 4.5 受控前置标识 `prerequisites`（冻结，闭集）

```text
PREREQUISITE_NONE = "none"
PREREQUISITES = (
    "abstraction-coverage",
    "candidate-call-pot-projection",
    "position-projection",
    "range-assumption",
    "pot-ev-contract",
)
```

标识一律为**语义化的连字符形式**，**不含**模块路径或文档编号；每个标识对应的实际模块/入口由**一条测试**逐一导入并断言存在，从而在不 import 的前提下锁定「前置确实存在」。

### 4.6 边界契约 `RuleBoundaryContract`（冻结，字段齐备）

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `schema_version` | `str` | 唯一受支持值 `real-rules-boundary.v1` |
| 2 | `basis` | `str` | `abstraction-slice-vs-real-rule-slices` |
| 3 | `abstraction_game_id` | `str` | 受限抽象标识 |
| 4 | `abstraction_game_version` | `str` | 受限抽象版本 |
| 5 | `abstraction_player_counts` | `tuple[int, ...]` | `(6, 7, 9)` |
| 6 | `abstraction_ante` | `int` | `1` |
| 7 | `abstraction_bet` | `int` | `1` |
| 8 | `entries` | `tuple[RuleSliceBoundary, ...]` | 逐条边界（按冻结目录顺序，不重不漏） |
| 9 | `limitations` | `tuple[str, ...]` | 局限声明（§4.8） |

约束：

1. `entries` 的 `feature` **唯一**且**恰好覆盖**冻结目录，顺序一致；
2. 每条 `entries[i]` 必须与冻结目录中的同名条目**逐字相等**（判定不可改写）；
3. 契约**不得**包含：`GameState`、真实底牌、公共牌、真实尺度、运行中 seed、对手内部参数、任何 EV 数值字段。

### 4.7 构造入口与明确失败语义（复用 P0-3 口径）

入口（纯函数）：

| 入口 | 输入 | 输出 |
|---|---|---|
| `build_rule_boundary_contract()` | — | `RuleBoundaryContract` |
| `boundary_catalogue()` | — | 冻结目录（21 条，元组） |
| `boundary_features()` | — | 全部切片标识（升序元组） |
| `boundary_for(feature)` | 切片标识 | 对应的 `RuleSliceBoundary` |
| `verdict_for(feature)` | 切片标识 | 该切片的 `BoundaryVerdict` |
| `features_with(verdict)` | 判定取值 | 该取值下的切片标识（按目录顺序） |
| `require_in_abstraction_slice(feature)` | 切片标识 | 仅当判定为 `in-abstraction-slice` 时返回该条目 |

失败的**分类型**异常：

| 异常 | 含义 | 触发条件 |
|---|---|---|
| `RealRulesBoundaryError` | 基类 | —— |
| `RealRulesBoundaryContractError` | **契约违规**（结构性非法或越界主张） | 条目与冻结目录不一致（改写判定 / 未知 feature / 重复 feature / 缺漏）；`verdict`、`prerequisite`、抽象常量、`schema_version` 不匹配；`require_in_abstraction_slice` 收到非界内切片 |
| `UnknownBoundaryFeatureError` | **切片标识未知** | `boundary_for` / `verdict_for` 收到冻结目录外的标识 |

**禁止静默回退**：未知、缺漏或抽象外的切片**一律不得**被当作界内处理，也**不得**用最近桶、补零、默认尺度或插值冒充映射。本模块**不替代** `judge_coverage`：它**不**接收 `GameState`，**不**判定真实局面是否落入抽象。

### 4.8 局限声明（冻结，必须齐备）

| 常量 | 内容 |
|---|---|
| `REAL_RULES_LIMITATION_NOT_REAL_EV` | 受限抽象的结果不是真实牌局 EV，也不构成生产可用策略。 |
| `REAL_RULES_LIMITATION_NO_IMPLEMENTATION` | 真实下注尺度与公共牌被划到抽象之外的界，本轮不实现真实牌堆或公共牌。 |
| `REAL_RULES_LIMITATION_CONTRACTED_NOT_WIRED` | 已有受控契约承载的切片仍未接入生产，也不构成任何质量证据。 |
| `REAL_RULES_LIMITATION_NO_SILENT_FALLBACK` | 抽象之外的切片必须明确失败，不得用最近桶、补零或插值冒充精确。 |

### 4.9 P1-4 验收口径

对照 `docs/35` §4.2 P1-4 原文口径（需要产出：抽象映射之外的界与实际规则切片的明确划分；验收：不得把受限抽象结果表述为真实牌局 EV 或生产可用策略）：

| # | 验收项 | 判据 |
|---|---|---|
| C1 | 受限抽象切片事实齐备 | §4.2 六个常量与训练器描述逐字一致（由测试读取训练器源文件锁定） |
| C2 | 真实规则切片逐条划分 | 冻结目录 20 条，`feature` 唯一且不重不漏 |
| C3 | 判定为受控闭集三值 | §4.3 三值；`features_with` 三个取值并集等于全部切片 |
| C4 | 判定不可由调用方改写 | 改写 `verdict` / `prerequisite` 或注入未知 / 重复 / 缺漏 feature 一律抛 `RealRulesBoundaryContractError` |
| C5 | 前置标识为闭集且真实存在 | §4.5 闭集；每个标识对应的模块入口由测试导入并断言存在 |
| C6 | 真实下注尺度与公共牌被明确划到界外 | `variable-bet-sizing` 与 `public-board` 的判定恒为 `out-of-abstraction` |
| C7 | 明确失败 | 未知切片抛 `UnknownBoundaryFeatureError`；非界内切片经 `require_in_abstraction_slice` 抛 `RealRulesBoundaryContractError` |
| C8 | 不替代 `judge_coverage` | 模块不接收 `GameState`、不 import `abstraction`；字段中不存在真实局面 |
| C9 | 不实现真实牌堆 / 公共牌 / 尺度 | 模块不含牌面、公共牌、尺度或抽样字段与入口 |
| C10 | 不 import 既有策略模块与训练器 | 源码中不出现既有策略模块名、`app.poker.*`、`tools.*` |
| C11 | 无生产调用方 | `app/**` 内除自身与包导出外无引用；对外响应与缓存键不变 |
| C12 | 既有语义零改动 | `equity()`、`call_ev`、结算、参考身份、P1-1 / P1-2 / P1-3 模块均不被触碰 |

## 5. 版本影响与兼容性（预期）

| 对象 | 影响 |
|---|---|
| 既有策略语义 | **零改动**：`heuristic.py` 与注册表不受影响 |
| 复盘与参考身份 | **零改动**：`hand_review.py` 与 `reference_identity.py` 不触碰；`call_ev` 与版本字段取值不变 |
| API 与前端 | **零改动**：不新增或改名字段；缓存键不变 |
| 数据库 | **不加列、不迁移**；真实数据库只读 |
| 引擎 / 结算 | 零改动；`equity` / `pot_projection` / `_settle_showdown` 语义不变 |
| 训练器 | **零改动**：只被测试**读取源文件**以锁定常量，不被 import |
| 锁文件 | 零改动（不新增依赖） |
| 新模块 | 新增独立模块与导出；**无生产调用方** |
| `docs/37` §3.1 升版判定 | **不触发**：参考实现、保守判据、`equity` 实现、采样数与固定种子五项全部零改动（明确声明） |

## 6. 边界声明与不得声称

- 本轮改动是**边界契约层**，**不是** CFR 接入，也**不构成任何质量证据**。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- **不得**把候选 A 的受限抽象结果表述为真实牌局 EV、GTO、均衡、NashConv、exploitability、best response 或生产可用策略。
- **不得**把本轮的边界表表述为「已支持真实 Hold'em」「已实现真实下注尺度/公共牌」或「已接入生产」。
- **不得**把资格投影、静态 share 或逐池收益口径表述为逐池 EV / 完整 CALL EV。
- **不得**用「最近桶」「补零」「掩码」「插值」「默认尺度」把抽象外的切片冒充为已映射。
- 稳定性结论若出现必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 本轮不追加 seed、不新建冻结 campaign、不重试任何已消耗 authorization、不上云、不转 GPU、不扩预算。
- 不得修改 `backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/api/**`、`frontend/**`、`backend/app/storage/models.py`、真实数据库 `backend/data/holdem.db`、锁文件、`tools/trainer/**`、`docs/20` 至 `docs/44a`。

## 7. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码/测试/前端/锁文件/真实数据库；未实施 P1-4 的实现；未实施清单其余任何一项；未改质量门槛或启用 `docs/39` 门槛；未新增受监督运行或 campaign；未追加 seed；未重试 authorization；未 push。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P1-4，并在实施回执（`docs/45a`）中给出文件级改动、新增/修改测试与 `ruff` / `pytest` / `npm run build` 的实跑输出。** 若用户对 §1.3 的任一项裁定有不同意见，应在实施前先修订本文件并记录原因。

P1-4 完成之后，`docs/35` §4.2 的 P1 组仅剩 **P1-5（修复后 6/7（及 2–9）人性能复测）** 未授权；它与 P0-2 共享性能口径。P2 组（2–9 人产品验收、N=9 结论、历史 `pot_results` 不一致、稳定性生产者）相互独立，可各自单独排期。**本轮不因 P1-4 而实现真实牌堆与联合 runout 的抽样**；该实现属 P1-3 遗留期望项，须另行单独授权并说明其跨 `poker/` 的边界。
