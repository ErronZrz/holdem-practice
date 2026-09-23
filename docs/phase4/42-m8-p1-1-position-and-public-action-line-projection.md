# 42 M8：P1-1 位置与公开行动历史的信息集投影（规格冻结）

> 日期：2026-09-18。
>
> 本文件接在 `docs/41` / `docs/41a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/42` 记录本轮**规格与决策冻结**，`docs/42a` 记录与之对应的**实施与验证回执**。`docs/20` 至 `docs/41a` 未被改写。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P1-1** 一项的规格冻结与设计岔路裁定。代码与测试在随后一次提交中落地，回执见 `docs/42a`。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项）

本轮用户明确授权的实施范围**只有一项**，来自 `docs/35` §4.2 的 P1 组：

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P1-1 | 位置与公开行动历史的信息集投影 | **是** |
| P0-1 / P0-2 / P0-3 / P0-4 / P0-5 / P0-6 / P0-7 | 注册表、lookup 预算、抽象映射、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**复用**） |
| P1-2 | 范围模型替代「vs 随机底牌」 | 否 |
| P1-3 | 逐池货币收益（短码 / 边池 / 多人平局） | 否 |
| P1-4 | 真实 Hold'em 的下注尺度与公共牌 | 否 |
| P1-5 | 修复后 6/7（及 2–9）人性能复测 | 否 |
| P2-1 … P2-4 | 2–9 人产品验收、N=9 结论、历史 `pot_results`、稳定性生产者 | 否 |

P1-1 **只是** `docs/35` §4.2 清单中的一项；本文件不改变其余条目的现状、优先级或失效条件，也不构成任何实施授权。按 `docs/35` §4.3 的依赖，P1-1 是 **P1-2 → P1-3** 的先决项，但本轮**不**推进其中任何一项。

### 1.2 用户答复原文（执行确认与四个设计岔路）

本轮采用「**先问用户**」而非「先在文档冻结规格」：在写代码前已就执行确认与四个设计岔路取得用户答复。答复原文照录：

| 项 | 用户答复原文 |
|---|---|
| 执行确认与 `tools/trainer/**` / `backend/app/poker/**` 边界 | 「确认执行；trainer 与 poker 只读」(允许改 `backend/app/strategy/`（新增位置投影模块，不改既有语义）、`backend/tests/`、`docs/42*`、api 最小必要；`tools/trainer/**` 与 `backend/app/poker/**` 零改动、不 import，仅作规范出处只读引用（沿用 P0-3 口径，推荐）) |
| 岔路一：投影载体与命名 | 「新增独立模块 position_projection.py」(新增 `backend/app/strategy/position_projection.py`，不动已冻结的 `projection.py`（P0-4 信息边界）与 `abstraction.py`（P0-3 抽象键）语义；脱敏一律经 `project_for_actor` 复用（推荐）) |
| 岔路二+三：动作线编码口径与相对座位基准 | 「相对按钮 + 只编码动作与相对座位」(以相对按钮为基准（N>2 翻前 UTG=bb+1、翻后 button+1 起；单挑按钮即小盲、翻前按钮先行动，特例保留）；动作线只编码动作 token + 相对座位、按街分段，金额留给 P1-4；加注层级/短码 all-in 等抽象无法表达的一律明确失败（复用 P0-3 失败语义）；绝对 seat 从投影剥离（推荐）) |
| 岔路四：与候选 A 抽象的关系 | 「只交付投影，不判定落入」(本轮只交付投影契约；与候选 A 的落差（单街道、单次开池、无盲注、固定下注、唯一 rank、无公共牌）只在文档中如实写明，不产出任何「已覆盖」结论；覆盖判定唯一入口仍是 P0-3 的 `judge_coverage`（推荐）) |

据此，**被授权**：在 `backend/app/strategy/` 新增位置/公开行动线投影模块（不改既有模块语义）、在 `backend/tests/` 新增回归测试、新增 `docs/42*`、以及在**最小必要**范围内改动 `backend/app/api/`。
**被拒绝**（本轮不做）：`tools/trainer/**` 与 `backend/app/poker/**` 任何改动；任何回退动作实现或策略分派路径改动；与候选 A 抽象的落入判定；P1-2 及之后的任何一项。

### 1.3 四项裁定（冻结）

| 岔路 | 裁定 |
|---|---|
| 一 | 新增 `backend/app/strategy/position_projection.py` 作为**纯函数 + Pydantic 模型**入口；**不改动**已冻结的 `projection.py`（P0-4）与 `abstraction.py`（P0-3）的任何语义；从生产快照出发的入口**先调用** P0-4 的 `project_for_actor`，本模块**不重造**第二套脱敏逻辑。 |
| 二 | 公开动作线**只编码动作 token 与相对座位**，按街分段；**金额一律不进入投影**，留给 P1-4。token 词表由本模块的**后端本地冻结常量**定义，不导入 `app.poker.engine` / `app.poker.actions`。加注层级与短码全下加注等**无法用 token 忠实表达**的情形**明确失败**，不静默降级。 |
| 三 | 相对座位**以按钮为基准**（按钮 = 0）；翻前起手为 `bb+1`（N≥3），翻后起手为 `button+1`；**单挑特例保留**（按钮即小盲、翻前按钮先行动）。绝对 `seat`、绝对 `button` 只用于一次相对化换算，**不进入投影**：同向平移全部绝对座位与按钮，投影必须逐字段不变。 |
| 四 | 本轮**只交付投影契约**，**不判定**该投影能否落入候选 A 抽象，也不新增任何覆盖判定或回退实现。覆盖判定的唯一入口仍是 P0-3 的 `judge_coverage`；与候选 A 的落差在 §3.3 如实写明，不产出任何「已覆盖」结论。 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 12]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -5 --oneline
9c684e7 feat: add controlled artifact lookup with budget contract and opt-in measurement
3d3c7d1 docs: freeze p0-2 lookup performance and memory budget specs
d6fa89c feat: add controlled abstraction projection coverage verdict and fallback declaration
09b803c docs: freeze p0-3 abstraction mapping coverage and fallback contract specs
8c6ca64 feat: add read-only multi-seed quality gate verdict without enabling a threshold

$ git rev-parse HEAD
9c684e738511f9c37d9d4b1e21a5cf0e69524621

$ git rev-parse origin/master
ef7e59282015e58f0e7fd153e30cd85ae6e9f56f

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8

$ find /Users/bryanylliu/holdem-campaigns -name strategy.json | wc -l
11          # 实测人数分布：N=6 五份、N=7 六份、N=9 零份

$ ls -1 backend/app/strategy/
__init__.py  abstraction.py  artifact.py  heuristic.py  interface.py
lookup_budget.py  projection.py  random_strategy.py  registry.py
```

与期望基线完全相符（`## master...origin/master [ahead 12]` 不多不少、工作区 0 行、`HEAD` 全哈希逐字符一致、campaigns = 8、11 份 `strategy.json`、`strategy/` 无位置投影模块）；未做任何 `reset` / `clean` / `stash` / `checkout`；**未 push**；未消耗任何本机实验预算。

## 3. 现状事实与必然落差（只读核验）

### 3.1 后端现状

- `backend/app/poker/state.py` 的 `GameState`：字段为 `street` / `board` / `pot` / `current_seat` / `button` / `hand_over` / `players`；`PlayerState` 含 `hole_cards`（**全部座位**）、`stack` / `folded` / `all_in` / `street_bet` / `total_committed`。
- 因此 `GameState` **没有**公开行动历史、**没有**盲注、**没有**跨手统计，也**没有**相对座位；它**不能**直接作为信息集来源。这与 `docs/26` §2.1、`docs/20` §8.3、§11.3 的既有结论一致。
- 真实行动线只存在于引擎的运行时属性 `PokerEngine.history`：条目为 `{street, seat, action, amount}`，由 `PokerEngine._record(seat, action, amount)` 追加。`history` **未**进入 `GameState`，也**未**版本化或白名单投影；`docs/20` §8.3 已把「历史 JSON 也应有版本化校验和白名单投影」列为契约要求（P0-4 已在持久化侧落地，本轮的投影是**策略侧**的）。
- 位置规则（只读引用 `backend/app/poker/engine.py`，**零改动、零 import**）：
  - `_blind_seats()`：`num_players == 2` 时返回 `(button, button+1)`；否则返回 `((button+1) % N, (button+2) % N)`；
  - `_preflop_first()`：`num_players == 2` 时返回 `button`；否则返回 `(bb + 1) % N`；
  - `_advance_street()`：翻后首个行动者为 `_first_active_from((button + 1) % N)`；
  - `_post_blinds()` 先记 `small_blind` 再记 `big_blind`，两者都带 `amount`。
- `docs/26` §10 已给出受控抽象投影 `(game version, N, relative actor, own rank, canonical public history)` 与「抽象外 / 版本不匹配 / 不完整信息集必须明确失败」的口径；`docs/20` §11.3 已明确「用相对按钮/盲位的行动顺序、前后尚待行动的人、公开动作线表达位置；单挑盲位特例保留；绝对座位 ID 不是牌理特征」。**P1-1 的职责正是把这两条口径从「建议」落成受控投影层。**
- P0-4（`projection.py`）与 P0-3（`abstraction.py`）已冻结：前者是唯一脱敏入口，后者的 `judge_game_state_coverage` 明确「不代劳」真实局面到抽象投影的映射——**P1-1 补上的正是这段被显式留白的映射**。

### 3.2 位置与行动顺序的既有事实口径（本模块规范出处）

下表为**只读引用**的引擎事实，本模块以本地常量**逐字对齐**其语义，但**不**导入其代码：

| 事实 | N = 2（单挑特例） | N ≥ 3 |
|---|---|---|
| 小盲相对按钮 | `0`（按钮即小盲） | `1` |
| 大盲相对按钮 | `1` | `2` |
| 翻前首个行动者（相对按钮） | `0`（按钮先行动） | `3`（即大盲后一位） |
| 翻后首个行动者（相对按钮） | `1`（即大盲） | `1`（即小盲） |

绝对 `seat` 与绝对 `button` 只参与一次 `相对座位 = (seat − button) mod N` 的换算；换算之后二者**不再出现**于投影中的任何字段。

### 3.3 真实 Hold'em 局面与受限抽象的落差（必须如实写明）

候选 A 的抽象是**单街道、单次开池、唯一 rank、无公共牌、固定下注 1、`ante = 1`、`bet = 1`、人数限 `{6,7,9}`、且不含盲注**的受限博弈。真实 Hold'em 局面具备相反特征：多街道、有盲注、可变下注尺度、公共牌、多人池/边池、任意人数（引擎按 2–9 人设计）、真实牌面而非 0..N−1 的抽象 rank。

由此产生的**必然结论**（本轮必须如实记录，不得淡化）：

1. 本轮的投影**只是把真实行动线编码成「动作 + 相对座位」的位置描述**；它**不**、也**不得**被表述为「已映射进候选 A 抽象」。候选 A 的公开历史 token 是 `x`/`b`/`c`/`f` 四种，且要求「无下注阶段只允许 check 或固定开池」「固定开池后只允许 call 或 fold」，而真实动作集为 `fold`/`check`/`call`/`bet`/`raise`（外加盲注）；因此**真实行动线与候选 A 抽象几乎必然不匹配**。
2. 一个真实局面经 P0-3 的 `judge_coverage` 判定，通常落在 `incomplete-infoset` 或 `out-of-abstraction`，而**不是** `in-abstraction`。本轮**不**为此提供任何近似、最近桶或插值路径。
3. 本轮**不判定**落入，也**不**新增覆盖入口（见 §1.3 裁定四）；把投影喂给 `judge_coverage` 属后续单独授权的工作。
4. **不得**把本轮交付表述为「位置/行动线已被 CFR 覆盖」「已支持生产 CFR」或「精确解」。

## 4. P1-1 规格（冻结）

### 4.1 位置投影 `PositionProjection`（字段齐备）

`PositionProjection` 是**冻结的 Pydantic model**，字段恰好为下列七项（顺序即契约顺序）：

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `player_count` | `int` | `N`（本手起始参赛人数，2–9） |
| 2 | `street` | `str` | 当前街：`preflop` / `flop` / `turn` / `river` 之一（终局 `showdown` 明确失败，见 §4.5） |
| 3 | `relative_actor` | `int` | 当前行动者的**相对座位**（相对按钮，按钮 = `0`），`0..N-1`；**不是**引擎绝对 seat |
| 4 | `action_order` | `tuple[int, ...]` | 当前街的**位置行动顺序**（相对座位），长度为 `N`；按引擎规则由按钮唯一确定 |
| 5 | `players_to_act_before` | `int` | 当前街位置序中位于行动者**之前**的座位数（行动者的位次） |
| 6 | `players_to_act_after` | `int` | 当前街位置序中位于行动者**之后**的座位数 |
| 7 | `public_action_line` | `tuple[StreetActionLine, ...]` | 按街分段的公开动作线，每段含街名与 token 序列 |

`StreetActionLine` 是**冻结的 Pydantic model**，字段恰好两项：`street: str`、`tokens: tuple[str, ...]`。

**口径澄清（避免与「已行动/未行动」混淆）**：`players_to_act_before` / `players_to_act_after` 是**位置口径**——只回答「当前街的位置序里，行动者前后各有多少个座位」，**不**减去已弃牌与已全下座位。理由：把位置压成「还有几个人要行动」的单一计数会丢掉顺序本身，而顺序才是 `docs/20` §11.3 要求的牌理特征；弃牌与全下事实由 `public_action_line` 与后续筹码层承担。本层**不**重演引擎的筹码机（见 §4.6）。

`PositionProjection` **不得**包含：绝对 `seat`、绝对 `button`、其他座位暗牌、自己的底牌、未发出/未来公共牌、真实牌面、真实 stack、真实底池金额、任何 `amount`、运行中 seed、对手内部参数、未来行动或结算结果。

### 4.2 相对座位基准与单挑特例（冻结）

1. **基准**：相对按钮，`相对座位 = (绝对 seat − 绝对 button) mod N`；按钮恒为 `0`。
2. **翻前位置序**（相对座位，长度为 `N`）：
   - `N == 2`：`(0, 1)`——**按钮即小盲，翻前按钮先行动**（单挑特例，保留）；
   - `N >= 3`：自 `((relative_bb + 1) mod N) = 3` 起顺时针遍历 `N` 个座位，即 `(3, 4, …, N-1, 0, 1, 2)`；`N == 3` 时退化为 `(0, 1, 2)`。
3. **翻后位置序**：自 `(button + 1) mod N = 1` 起顺时针遍历 `N` 个座位，即 `(1, 2, …, N-1, 0)`；`N == 2` 时为 `(1, 0)`。
4. **盲注相对座位**：`N == 2` 时小盲 `0`、大盲 `1`；`N >= 3` 时小盲 `1`、大盲 `2`。
5. **绝对座位剥离**：`seat` 与 `button` 只在换算中出现，**不进入**任何投影字段。判据：把全部绝对 `seat` 与绝对 `button` 同时平移同一常量（模 `N`），投影必须**逐字段完全相等**。

### 4.3 公开动作线 token 与词表（冻结）

token 形式为 `action@relative-seat`，多个 token 以 `|` 连接；$N$ 个座位全部以**相对座位**表达。

token 词表（**后端本地冻结常量**，不导入 `app.poker.engine` / `app.poker.actions`）：

| token | 对应真实动作 | 说明 |
|---|---|---|
| `sb` | `small_blind` | 翻前强制小盲（金额不进投影） |
| `bb` | `big_blind` | 翻前强制大盲（金额不进投影） |
| `f` | `fold` | 弃牌 |
| `x` | `check` | 过牌 |
| `c` | `call` | 跟注（含短码全下跟注，见 §4.6） |
| `b` | `bet` | 下注（本街首次主动投入） |
| `r` | `raise` | 加注 |

约束：

1. **按街分段**：`public_action_line` 为 `StreetActionLine` 的元组，街序必须为 `preflop → flop → turn → river` 单调前进，**必须**自 `preflop` 起（引擎在翻前即记录盲注）；缺街、乱序、回退、重复街均判**不可编码**，明确失败。
2. **金额不进投影**：真实 `amount` 只在本模块内部用于「短码全下加注」判定（§4.5 第 2 条），**不出现**在任何模型字段中。真实下注尺度与公共牌属 **P1-4**，本轮**不**越界实现。
3. **加注层级不编码**：token 只区分 `bet` 与 `raise` 两种动作种类，**不**携带加注倍数、底池比例或档位；「这是第几层加注」这类信息在本轮**不被编码**。
4. **词表外动作明确失败**：出现未登记的动作名（例如引擎未来新增的动作）一律判不可编码，明确失败，不静默跳过、不映射成近似的已登记 token。

### 4.4 构造入口（冻结）

本模块提供两个受控入口，均为纯函数：

| 入口 | 输入 | 输出 |
|---|---|---|
| `build_position_projection(*, player_count, button, current_seat, street, history)` | 人数、绝对按钮、绝对当前座位、街名、引擎风格的历史条目序列 | `PositionProjection` |
| `project_position_for_actor(state, history)` | `GameState` 快照 + 历史条目序列 | `PositionProjection` |

`PublicAction` 是**冻结的 Pydantic model**，字段恰好四项：`street: str`、`seat: int`、`action: str`、`amount: int`（缺省 `0`）。它是**输入侧**的受控记录类型，用于把引擎 `history` 条目规范化；`amount` **只**存在于输入侧，**不**进入投影。

`build_public_actions(history)` 把引擎风格条目（`Mapping`）转换为 `PublicAction` 元组：键名、类型、值域非法一律抛**契约异常**，不做类型转换、不补默认值。

`project_position_for_actor` **必须**先调用 P0-4 的 `project_for_actor(state)`，再以投影结果的人数 / 按钮 / 当前座位 / 街名调用 `build_position_projection`。本模块**不重造**任何脱敏逻辑，也不读取 `hole_cards` / `board` / `pot` / `stack` 的任何内容。

### 4.5 明确失败语义（复用 P0-3 口径）

本模块**没有**「近似投影」「最近位置」「默认顺序」等路径。失败的**分类型**异常如下：

| 异常 | 含义 | 触发条件 |
|---|---|---|
| `PositionContractError` | **契约违规**（结构性非法输入） | 字段类型错误（字符串人数、布尔冒充整数、非字符串动作等）；`history` 条目不是映射或缺少必需键 |
| `PositionEncodingError` | **位置/行动线不完整或不可编码** | 见下列 1–6 |

`PositionContractError` 与 `PositionEncodingError` 都继承 `PositionProjectionError(ValueError)`；二者**不得**合并为同一个「投影失败」状态，与 P0-3 对「契约违规 vs 抽象外」的区分口径一致。

`PositionEncodingError` 的触发条件（逐条列出「缺什么 / 哪里不可编码」，使失败**可追溯**）：

1. **街序不完整或乱序**：`public_action_line` 非自 `preflop` 起、街序回退、重复街，或当前 `street` 早于最后一段动作所在的街；
2. **短码全下加注**：`raise` 的增量小于当时的最小加注额（该加注**未重开行动**）。token 线只有 `r@seat`，**无法**表达「这一次加注没有重开行动」，因此如实判**不可编码**，明确失败；这是「不得用近似冒充精确」在本层的直接落实；
3. **盲注结构不符**：`preflop` 段的前两个 token 不是 `sb@<相对小盲>`、`bb@<相对大盲>`（顺序或相对座位与该人数的规则不符）；
4. **词表外动作**：动作名不在 §4.3 词表内；
5. **座位越界或已弃牌座位再次行动**：绝对 `seat` 不在 `[0, N)`；某座位已 `fold` 之后又出现动作；
6. **同街重复行动缺少解释**：同一街内某座位第二次出现，但其两次出现之间**没有**任何 `bet` 或 `raise`。

终局（`street == "showdown"`）**没有**当前行动者，一律判**不可编码**，明确失败。

**禁止静默回退**：任何未知、缺失或不可编码的输入都不得被当作「已编码」处理，也不得回落到默认位置或默认顺序后仍声称投影成功。

### 4.6 明确不在本层的口径（边界，防越界）

为避免与 P1-4 及引擎语义混淆，本层**明确不**实现、也**不**断言：

1. **不重演引擎下注机**：不完整重演 `current_bet` / `street_bet` / `has_acted_since_full_raise` / `min_raise` 的逐动作状态机（`docs/20` §12.2 已警告「禁止复制状态机/判据造成漂移」），只做 §4.5 列出的**结构性**校验；
2. **不判定全下状态**：历史条目不含 `all_in` 标记，因此本层**不**断言「某街首个行动者是否因全下被跳过」；短码全下**跟注**与短码全下**下注**按其动作种类编码（`c@` / `b@`），其金额后果属 P1-4；
3. **不判定下注轮闭合**：本层不判断某街何时结束，只校验已记录 token 的结构自洽；
4. **不判定能否落入候选 A 抽象**：见 §1.3 裁定四与 §3.3。

### 4.7 信息边界复用（P0-4）与不读对手暗牌 / 未来牌

1. 从**生产快照**出发的入口，**必须**先把快照交给 P0-4 的 `project_for_actor`；本模块不新增第二条脱敏通道。
2. 本模块**不读取**、也不在投影中出现：其他座位暗牌、自己的底牌、未发出/未来公共牌、真实牌面、运行中 master seed、对手内部参数、结算结果。
3. 投影的字段集合在结构上**不包含**上述任何一项（见 §4.1 字段表）；公开动作线只来自引擎已记录的**公开**行动。

### 4.8 P1-1 验收口径

对照 `docs/35` §4.2 P1-1 原文口径（相对座位/行动顺序/前位待行动人数/公开动作线的受控投影；单挑盲位特例保留；绝对 seat 不作为牌理特征；人数相同但筹码/行动线不匹配不得冒充精确解）：

| # | 验收项 | 判据 |
|---|---|---|
| C1 | 相对座位正确 | `relative_actor` 恒为 `(current_seat − button) mod N` |
| C2 | 行动顺序正确 | 翻前 `N≥3` 从相对 `3` 起、单挑从 `0` 起；翻后从相对 `1` 起；长度恒为 `N` |
| C3 | 前位待行动人数正确 | `players_to_act_before` + `players_to_act_after` = `N − 1`；且等于行动者在 `action_order` 中的位次口径 |
| C4 | 公开动作线可编码且按街分段 | 同输入必得同 token 序列；街序单调自 `preflop` 起；金额不出现在任何字段 |
| C5 | 单挑盲位特例保留 | `N == 2` 时相对小盲 = `0`（按钮）、相对大盲 = `1`，翻前 `action_order[0] == 0`，且 `sb@0`/`bb@1` 可编码通过 |
| C6 | 绝对 seat 不作为牌理特征 | 同向平移全部绝对 `seat` 与绝对 `button` 后，投影**逐字段完全相等** |
| C7 | 2–9 人参数化，不写死两人 | `N = 2..9` 逐人数构造成功且顺序/位次符合规则 |
| C8 | 不读对手暗牌与未来牌 | 替换其他座位暗牌与公共牌后，投影完全相等；投影字段中不存在相关字段 |
| C9 | 不可编码 / 不完整明确失败 | §4.5 六类触发条件各自抛出 `PositionEncodingError`；类型错误抛 `PositionContractError`；两者类型不同 |
| C10 | 不写回 `history_json` | 本模块只读历史条目，不持有引擎引用、不写任何存储；投影为纯值对象 |

## 5. 版本影响与兼容性（预期）

| 对象 | 影响 |
|---|---|
| 既有策略语义 | **零改动**：`heuristic.py` / `random_strategy.py` / `interface.py` / `projection.py` / `abstraction.py` / `registry.py` / `artifact.py` / `lookup_budget.py` 语义不变 |
| 策略分派 | **零改动**：注册表与 `games.py` 的分派路径不受影响；本轮**不新增**任何运行时行为，也**不**新增回退动作 |
| API 与前端 | 除非最小必要，不做改动；不改任何请求/响应字段；**不恢复**已移除的前端策略选择器 |
| 数据库 | **不加列、不迁移**；`storage/models.py` 零改动；真实数据库只读 |
| 旧历史 | 原样保留；`history_json` 不被改写；旧响应结构不变 |
| 引擎 / 结算 | 零改动；`equity` / `estimate_static_showdown_share` / `pot_projection` / `_settle_showdown` 语义不变 |
| 锁文件 | `backend/uv.lock` 与 `frontend/package-lock.json` 零改动（不新增依赖） |
| 不可编码局面的实际处置 | **不产生投影、不产生动作**；抛出分类型明确异常；无最近桶、无默认顺序、无插值 |
| 与候选 A 的关系 | 投影**不**被判定为落入或覆盖；真实局面落入受限抽象属后续单独授权的工作 |

## 6. 边界声明与不得声称

- 本轮改动是**契约与投影层**，**不是** CFR 接入，也**不构成任何质量证据**；`backend/app/strategy/` 仍无任何 CFR lookup 或产物接线的**新**语义（P0-2 的加载层保持原样）。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- **不得**把投影结果表述为「已覆盖」「已支持 CFR」或「精确解」；也**不得**因为投影可成功构造就声称真实局面已被训练抽象覆盖。
- 真实局面与受限抽象的落差已在 §3.3 如实写明；**不得**用「最近桶」「补零」「掩码」「插值」冒充精确映射。
- 稳定性结论若出现，必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 本轮不追加 seed、不新建冻结 campaign、不重试任何已消耗 authorization、不上云、不转 GPU、不扩预算。
- 不得修改 `backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/storage/models.py`、真实数据库 `backend/data/holdem.db`、锁文件、`tools/trainer/**`、`docs/20` 至 `docs/41a`。

## 7. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码/测试/前端/锁文件/真实数据库；未实施 P1-1 的实现；未实施清单其余任何一项；未改质量门槛或启用 `docs/39` 门槛；未新增受监督运行或 campaign；未追加 seed；未重试 authorization；未 push。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P1-1，并在实施回执（`docs/42a`）中给出文件级改动、新增/修改测试与 `ruff` / `pytest` / `npm run build` 的实跑输出。** 若用户对 §1.3 的任一项裁定有不同意见，应在实施前先修订本文件并记录原因。

P1-1 完成之后的下一个清单项是 **P1-2（用基于公开行动线的范围模型替代「vs 随机底牌」）**；按 `docs/35` §4.3 的依赖，它是 P1-3 的先决项，须**单独授权**，并注意其验收要求「不得读取对手暗牌/未来牌」「范围假设与参考来源一起版本化」，以及与 `equity()` 固定 `ties/2`、P1-3 逐池 EV 的耦合。
