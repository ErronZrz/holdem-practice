# 74ab M8：域 A／域 B ② 推导输入第一层锁定文本（送审稿）

> 日期：2026-10-10。
>
> **战役归属**：`74`（「新身份研发与独立验证」战役）。本文件是该战役的第 `29` 份文档，编号 `74ab`。
>
> **历史关系**：承接已通过内容审查的 `74aa`（域 A/B 前置设计裁定：A-1、B-1 单桶差、P1、S-1、W-b、通用 `V_max^{AB}(v)`；不采用 AB-2z／`V_max^{AB,0}`）、`74b`（分布观测契约冻结规格）、`74i`（A/B 块级上界与 `M_AB(v)`）、`74y`（`seat_rotation` 锁定版本 1；庄位仅引用 SR-B1／SR-P1）、`74f` §9（总顺序）、`74o` §8.2.1（② 侧第一层锁定范畴）。本文件**不修改**任何历史文档正文。
>
> **编号范围**：双后缀 `ab`。本文件不预占 `ac` 及之后编号。
>
> **本文性质**：**域 A／域 B 范围内、② 推导输入的第一层锁定文本（送审稿）**。写定本授权所列**静态规范对象**的锁定候选条款；**不是** `74f` §4.3 的域 A/B ② 结构性推导交付；**不是**设计裁定（裁定以 `74aa` 为准）。
>
> **当前状态**：前两轮阻断已按授权修订；第三轮复审在 `LegalSnap`／`BKT_OTHER`／主要加注边界闭合后**暂不通过**（§6.3 与 `Cand(A-001)` 不一致、`P_ℓ` 规范序与 §4.3 `spot_id` 不符、逐座 `has_acted_since_full_raise` 与引擎重开规则不符）。已依第四轮就地修订授权处理上述三项；**全文复审结论未出**前，§4–§11 仍为锁定候选条款。审查通过前：**不得**称 AB-0、AB-1′、W-1 已建立，**不得**称域 A/B ② 已发生或 A 路径已成立。
>
> **效力限定（写死）**：
>
> - 节点注册表中的条目是**运行前规格的静态登记**，**不是**实际 campaign 已执行节点、随机材料、抽样结果或块报告读数；**禁止**由策略输出、分布观测读数、样本结果、性能读数或历史运行数据生成或筛选表中任一行。
> - **不**生成或冻结随机材料、seed、源码清单、实际 `campaign-configuration-v1` 摘要、`code_identity` 或身份；**不**创建 `mixed-local@9`。
> - **不**改代码、测试、`AGENTS.md`、`docs/README.md` 或既有文档；**不**运行 Ruff、pytest、构建、测量、模拟、补算或质量验证；**不**提交或推送。
> - 通用 `V_max^{AB}(v)` 公式为 `74aa`／`74i` 路线登记；本文件**不**进入解算、**不**主张非退化比较已可执行。
> - **不**采用 AB-2z 或 `V_max^{AB,0}(v)`。

## 1. 授权原文与范围

用户授权原文（摘要）：

```text
新建 docs/phase6/74ab-m8-domain-ab-first-layer-locking-text.md。
性质：域 A／域 B ② 推导输入的第一层锁定文本候选稿，承接 74aa。

写定并冻结候选条款所需的静态规范对象：U_AB、E_AB、节点注册表；域 B 桶表与每节点 b*；
域 A 动作对与 q_c；L*、P1、P_ℓ 枚举、M_ℓ、n_ℓ、规范序；W-b 有理数 v；块模板 T_AB 与 S-1 规范序。

AB-0 仅登记 A-1／B-1 节点级量及逐层支持界；P1、P_ℓ、M_ℓ、n_ℓ、S-1、T_AB 为 AB-1′ 及块级推导前提，不得混为 AB-0 充要条件。
不得新增 H ≤ N；庄位仅引用 74y SR-B1／SR-P1。
动作 type 仅 fold/check/call/bet/raise；BET／RAISE 的 amount 为下注或加注后总额（与 poker.Action 一致）。

不得修改其他文件；不得推进 A/B②、③ 或其后步骤。完成后仅申请全文内容审查。
```

**不属于本文件**：域 A/B ② 结构性推导正文；L-3 扩展 A/B 层材料用途；实现与 SR-J*；③–⑦；索引更新。

## 2. 文件级改动与真实执行情况

| 文件 | 改动性质 |
|---|---|
| `docs/phase6/74ab-m8-domain-ab-first-layer-locking-text.md` | **新增**（本文件） |

| 类别 | 内容 |
|---|---|
| 只读核验 | `git rev-parse HEAD`、`git status -sb`；`backend/app/poker/actions.py`（`ActionType`、`Action` 注释）；`74aa`、`74y` §4.2、`74b` §7.4–§7.5 片段 |
| 测试 / 构建 / Ruff / 测量 | **均未执行** |

事实登记（首版落盘）：`HEAD = d64937bcd44281de6252f4b37387ae2378e83b25`。

**首轮审查后修订（2026-10-10）**：审查裁定暂不通过（阻断 1–3）。修订授权：仅就地修改本文件，消除域 A `marginalized` 口径、域 B 桶表一致性、各节点静态快照不足。未运行 Ruff、pytest、构建或测量；未改其他文件。

| 类别 | 本轮 |
|---|---|
| 只读核验 | `74b` §4.1、§7.3–§7.5；`actions.py` |
| 改动 | 本文件 §4.5–§4.6、§5、§6、§13–§16 |

**复审后修订（2026-10-10）**：复审暂不通过（快照四项阻断）。修订授权：仅就地修改本文件，处理私牌边界、`HandPlan`／`uses_schedule`、`B-002` 候选、`seats[]` 机械字段与 `T_AB` 手序映射。未运行 Ruff、pytest、构建或测量。

| 类别 | 本轮 |
|---|---|
| 改动 | §4.2–§4.6、§5.3、§11、§13–§16 |

**第三轮复审后修订（2026-10-10）**：复审暂不通过（`LegalSnap`／引擎规则、`BKT_OTHER`）。修订授权：仅就地修改本文件；只读对照 `backend/app/poker/engine.py` 的 `legal_actions`（约第 171–233 行）。未运行测试、Ruff、构建或测量。

| 类别 | 本轮 |
|---|---|
| 改动 | §4.3、§4.5–§4.6、§5.2–§5.3、§6.3、§13–§16 |

**第四轮复审后修订（2026-10-10）**：第三轮复审暂不通过（§6.3 动作对、`P_ℓ` 规范序、`has_acted_since_full_raise` 三项机械不一致）。修订授权：仅就地修改本文件；只读对照 `backend/app/poker/engine.py` 的 `_reopen_after_full_raise`、`_apply` 中 `CHECK`／`CALL`／`FOLD` 与 `_advance_street`。未运行测试、Ruff、构建或测量。

| 类别 | 本轮 |
|---|---|
| 改动 | §4.6.1、§4.6.3–§4.6.5、§6.3、§7.4、§16 |

## 3. 锁定通则

### 3.1 拟锁定对象与版本

| 锁定键 | 拟定版本 | 含义 |
|---|---|---|
| `domain_ab_node_registry` | `1` | `U_AB`、`E_AB`、节点注册表、域 A 动作对与 `q_c`、域 B `b*` |
| `domain_ab_bucket_registry` | `1` | 全局桶表与逐节点合法主动金额及静态完备性 |
| `domain_ab_layer_partition` | `1` | `L*`、谓词、P1、`P_ℓ` 枚举、`M_ℓ`、`n_ℓ`、规范序 |
| `domain_ab_layer_weights` | `1` | W-b 单点类 `{v}` 有理数向量（W-1 候选条款） |
| `domain_ab_block_template` | `1` | `T_AB` 纯结构及与 `HandPlan` 的绑定规则 |
| `domain_ab_support_bounds` | `1` | AB-0：节点级量与逐层 `[a_ℓ,b_ℓ]`、`R_ℓ` |

**审查通过前**，上表全部**未锁定**、**不生效**。

### 3.2 AB-0 与 AB-1′ 的分工（写死）

| 对象 | 归属 | 本文件登记 |
|---|---|---|
| **AB-0** | 节点级量 `y_i` 的定义域与**逐层**支持界 `[a_ℓ,b_ℓ]`、`R_ℓ := b_ℓ − a_ℓ` | §8 |
| **AB-1′** | 层边缘均匀无放回抽样假设 | §9–§11；**前提**为 §6–§7 已写定，**不**纳入 AB-0 的充要条件 |
| **P1、`P_ℓ`、`M_ℓ`、`n_ℓ`** | 静态互斥划分与配额 | §6–§7 |
| **S-1** | 组合数双射所用序 | §7.3、§11.3 |
| **`T_AB`** | 块内层选择与 `HandPlan` 关系 | §11 |
| **W-1** | 层权重单点类 | §10（候选条款；审查前**未建立**） |
| **`V_max^{AB}(v)`** | 块级上界候选 | §12（引用 `74i` §5.3；**未**选用进入解算） |

**AB-0 成立**（在审查意义下「定义完备」）的登记条件**仅**为：§4–§5 与 §8 对**每个**主判层 `ℓ ∈ L*` 的节点级量与支持界已写定，且可由定义或枚举推出 `R_ℓ`。**不要**要求 `P_ℓ`、`n_ℓ` 或 `T_AB` 作为 AB-0 的充要条件。

### 3.3 战役常量（本锁定版本 1）

| 符号 | 取值 | 说明 |
|---|---|---|
| `N` | `6` | 玩家数；用于 `74y` 庄位算术与范围校验 `0 ≤ button, probed_seat < N` |
| `SB`、`BB` | `1`、`2` | 小盲／大盲（整数筹码）；本版全部节点共用 |
| `S` | `200` | 每座**本手开始时**后手筹码（整数）；快照中的 `stack_remaining` 由此与已投入扣减一致 |
| `capability_id` | `distribution-observation@1` | `74b` §7.2 |
| 比较身份 | `candidate`、`baseline` | 域 A：`q_candidate` 为 **candidate** 在 `actor_seat` 的 **marginalized** 质量；域 B：`q_candidate`、`q_baseline` 分别为两身份同桶 **marginalized** 质量 |

**庄位（仅引用 `74y`）**：对块内手序 `h ∈ {1,2,…}`（`h` 为正整数，**无** `H ≤ N` 上界）、`HandPlan` 行满足 **`button = (h − 1) mod N`**（SR-B1，`b₀ = 0`）、**`probed_seat = button`**（SR-P1）。`button` 随 `h` 循环；**本文件不**新增对手数的手数限制。

### 3.4 动作规范表示（与 `poker.Action` 对齐）

记 `ActionRef = (type, amount)`：

| `type` | 取值 | `amount` |
|---|---|---|
| `fold` | 仅此五字 | `0` |
| `check` | | `0` |
| `call` | | `0` |
| `bet` | | 本街下注**后总额**（正整数筹码单位） |
| `raise` | | 加注**后**本街总额（正整数筹码单位） |

**类型全序**（用于固定 `(i,i′)` 方向，禁止仅交换两端改号）：  
`fold` ≺ `check` ≺ `call` ≺ `bet` ≺ `raise`；同类型按 `amount` 升序。

有序对 `(i,i′)` 须满足 `i` 严格小于 `i′` 于上述全序，且 `i,i′ ∈ legal_actions(n)`、`i ≠ i′`。

## 4. 节点母集 `U_AB`、排除集 `E_AB` 与注册表

### 4.1 母集与排除

```text
U_AB := { A-001, A-002, A-003, B-001, B-002 }   // 共 5 项，有限、可逐项列举
E_AB := ∅
U*   := U_AB \ E_AB = U_AB
```

**禁止**：从运行读数、策略输出或块结果扩展 `U_AB`；**禁止**隐式「其他」节点。

### 4.2 外生键字段（索引用，不足以单独构成查询输入）

除 `node_id` 外，注册表索引字段（**不得**含策略输出、观测读数、块盈亏）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `domain` | `A` \| `B` | 域标签 |
| `street` | `preflop` \| `flop` | 与快照一致 |
| `spot_id` | 字符串 | 局面代号（本版字面量） |
| `uses_schedule` | `yes` \| `no` | 本版**全部**为 `yes`；庄位／被测座由 §4.6 的 `hand_ordinal` 与 `74y` 导出 |

**机械规则**：契约查询输入 **必须**使用 §4.5–§4.6 的完整快照三元组（安全状态、合法动作集、**未指定**模式覆盖）；**不得**仅用 `(street, spot_id)` 推断状态。含 `button`／`probed_seat`／`actor_seat` 的节点 **必须**满足 SR-P1：`probed_seat = button = (hand_ordinal − 1) mod N`。

### 4.3 节点注册表（索引）

| node_id | domain | street | spot_id | uses_schedule | `hand_ordinal` | 快照 |
|---|---|---|---|---|---|---|
| A-001 | A | preflop | btn_facing_bb | yes | `1` | §4.6.1 |
| A-002 | A | preflop | btn_facing_open | yes | `1` | §4.6.2 |
| A-003 | A | flop | btn_checked_to | yes | `2` | §4.6.3 |
| B-001 | B | preflop | btn_facing_open_raise | yes | `1` | §4.6.4 |
| B-002 | B | flop | btn_facing_bet | yes | `2` | §4.6.5 |

### 4.4 规范 `node_id` 排序键 `κ_node`

对任意注册节点，`κ_node` 为四元组按字典序比较：

1. `domain`：`A` ≺ `B`（ASCII）  
2. `street`：`flop` ≺ `preflop`（按 UTF-8 字节序）  
3. `spot_id`：UTF-8 字节升序  
4. `node_id`：UTF-8 字节升序（ tie-break）

**禁止**依赖 Python 容器迭代顺序、数据库顺序或文件行顺序。

### 4.5 静态决策快照（模式与 `LegalActions` 记录）

每个 `node_id` 绑定一份**可打印、有限**快照 `Snap(n)`。

**（1）`HandPlan` 绑定（`74y`，本版全部 `uses_schedule=yes`）**

| 字段 | 规则 |
|---|---|
| `hand_ordinal` | 正整数 `h`；登记于 §4.3 |
| `button` | **`(h − 1) mod N`**（SR-B1，`b₀ = 0`） |
| `probed_seat` | **`button`**（SR-P1） |
| `actor_seat` | **等于 `probed_seat`**（本版恒等） |

**（2）安全状态 `GameSnap`**（`74b` §4.1：不含对手私牌；整数筹码；公共牌用 `74r` L-1 牌面串）

| 字段 | 含义 |
|---|---|
| `num_players` | `N = 6` |
| `hand_ordinal` | 见上 |
| `button` / `probed_seat` / `actor_seat` | 见上 |
| `street` | `preflop` \| `flop` |
| `board` | 公共牌列表（preflop 为 `[]`） |
| `hand_over` | 本版均为 `false` |
| `current_seat` | **等于** `actor_seat`（须行动座） |
| `current_bet` | 本街 `street_bet` 的**最大值**（与引擎 `Engine.current_bet` 同义） |
| `current_bet_to_match` | **恒等于** `current_bet`（审查用别名；不得另赋不同值） |
| `min_raise` | 本街当前最小加注**增量**（与引擎 `Engine.min_raise` 同义；盲注街初值为 `BB`） |
| `last_aggressor_seat` | 本街最后一次使 `current_bet` 上升的座位；仅盲注时可为 `null` |
| `actor_hole` | **仅** `actor_seat` 的两张私牌明文；**禁止**为其他座填写私牌、哈希或间接编码 |
| `seats[]` | 长度 `N`；每座 **公开**字段见下表 |
| `pot_main` | 主池总额；**必须**满足 §4.5（3）守恒式 |

**`seats[s]` 公开字段（机械必填）**

| 字段 | 含义 |
|---|---|
| `folded` | 是否已弃牌 |
| `all_in` | 是否已全下（本版均为 `false`） |
| `street_bet` | 本街已投入总额 |
| `total_committed` | 本手累计投入主池（含他街） |
| `stack_remaining` | 后手筹码；**必须**满足 `stack_remaining = S − total_committed` |
| `has_acted_this_street` | 本街是否已行动 |
| `has_acted_since_full_raise` | 与引擎 `PlayerState.has_acted_since_full_raise` 同义（**逐座**） |

**（3）`LegalSnap` 与引擎 `legal_actions()` 的机械对应（`engine.py`）**

记 `actor = actor_seat`，`p` 为 `seats[actor]`，`to_call := current_bet − p.street_bet`，`all_in_total := p.street_bet + p.stack_remaining`。

| 字段 | 规则 |
|---|---|
| `can_fold` | `to_call > 0` |
| `can_check` | `to_call = 0` |
| `can_call` | `to_call > 0` |
| `call_amount` | `to_call`（若 `can_call`） |
| `actual_call_amount` | `min(to_call, p.stack_remaining)` |
| `is_short_all_in_call` | `can_call` 且 `to_call > p.stack_remaining` |
| `can_bet` | `p.stack_remaining > 0` 且 `to_call = 0` 且 `street = flop` |
| `min_bet`／`max_bet` | 若 `can_bet`：`min_bet = min(BB, all_in_total)`，`max_bet = all_in_total`；否则 `0` |
| `can_raise` | `p.stack_remaining > 0` 且 `all_in_total > current_bet` 且（`to_call = 0` 或 `¬p.has_acted_since_full_raise`） |
| `min_raise_to`／`max_raise_to` | 若 `can_raise`：`full_min = current_bet + min_raise`；`min_raise_to = full_min` 若 `all_in_total ≥ full_min`，否则 `all_in_total`；`max_raise_to = all_in_total`；否则 `0` |

**（4）筹码守恒（SNAP-J2）**

```text
Σ_{s=0}^{N-1} (stack_remaining[s] + total_committed[s]) = N · S
Σ_{s=0}^{N-1} total_committed[s] = pot_main
```

**（5）`LegalSnap`**：与 `poker.LegalActions` 同名字段；**必须**与 §4.5（3）由同一 `GameSnap` **唯一**推出。域 A 与域 B 若共用同一 `GameSnap`，则 **`LegalSnap` 必须逐字相同**。

**（6）`Cand(n)`**：有限 `ActionRef` 列表；每个元素须为 §4.5（3）下的合法动作；`BET`／`RAISE` 的 `amount` 落在对应闭区间内。

**（7）主判查询**：模式覆盖**未指定**；`aggregation = marginalized`（§6.1／§5.4）。

**说明性文字**（若有）**不得**作为 SNAP-J1／J2／J5 的机械依据。

### 4.6 各节点冻结快照（完整）

**座位索引约定**：`SB = (button + 1) mod N`，`BB = (button + 2) mod N`；preflop 行动自 `(BB + 1) mod N` 顺时针。

#### 4.6.1 `A-001`（`h=1`；BTN 面对盲注、无人加注）

| 项 | 值 |
|---|---|
| `hand_ordinal` | `1` ⇒ `button = probed_seat = actor_seat = current_seat = 0` |
| `street` / `board` | `preflop` / `[]` |
| `current_bet` / `current_bet_to_match` | `2` |
| `min_raise` | `2` |
| `last_aggressor_seat` | `null` |
| `actor_hole`（座 `0`） | `As Kh` |
| `pot_main` | `3` |

| seat | `folded` | `all_in` | `street_bet` | `total_committed` | `stack_remaining` | `has_acted_this_street` | `has_acted_since_full_raise` |
|---|---|---|---|---|---|---|---|
| 0 | false | false | 0 | 0 | 200 | false | false |
| 1 | false | false | 1 | 1 | 199 | false | false |
| 2 | false | false | 2 | 2 | 198 | false | false |
| 3 | true | false | 0 | 0 | 200 | true | false |
| 4 | true | false | 0 | 0 | 200 | true | false |
| 5 | true | false | 0 | 0 | 200 | true | false |

`LegalSnap`：`can_fold=true`；`can_check=false`；`can_call=true`；`call_amount=2`；`actual_call_amount=2`；`is_short_all_in_call=false`；`can_bet=false`；`min_bet=0`；`max_bet=0`；`can_raise=true`；`min_raise_to=4`；`max_raise_to=200`。

`Cand(A-001)`：`[(fold,0), (call,0)]`。（`FOLD` 不置 `has_acted_since_full_raise`。）

#### 4.6.2 `A-002`（`h=1`；与 §4.6.4 同一 `GameSnap`）

`Cand(A-002)`：`[(fold,0), (call,0)]`。

#### 4.6.3 `A-003`（`h=2` ⇒ `button=probed=actor=1`；flop 被让牌至 BTN）

| 项 | 值 |
|---|---|
| `hand_ordinal` | `2` ⇒ `current_seat = actor_seat = 1` |
| `street` / `board` | `flop` / `[Ah, 7d, 3c]` |
| `current_bet` / `current_bet_to_match` | `0` |
| `min_raise` | `2` |
| `last_aggressor_seat` | `null` |
| `actor_hole`（座 `1`） | `Qs Jd` |
| `pot_main` | `6` |

| seat | `folded` | `all_in` | `street_bet` | `total_committed` | `stack_remaining` | `has_acted_this_street` | `has_acted_since_full_raise` |
|---|---|---|---|---|---|---|---|
| 0 | true | false | 0 | 0 | 200 | true | false |
| 1 | false | false | 0 | 2 | 198 | false | false |
| 2 | false | false | 0 | 2 | 198 | true | true |
| 3 | false | false | 0 | 2 | 198 | true | true |
| 4 | true | false | 0 | 0 | 200 | true | false |
| 5 | true | false | 0 | 0 | 200 | true | false |

`LegalSnap`：`can_fold=false`；`can_check=true`；`can_call=false`；`call_amount=0`；`actual_call_amount=0`；`is_short_all_in_call=false`；`can_bet=true`；`min_bet=2`；`max_bet=198`；`can_raise=false`；`min_raise_to=0`；`max_raise_to=0`。

`Cand(A-003)`：`[(check,0), (bet,4)]`。（翻牌 `_advance_street` 将全体 `has_acted_since_full_raise` 置 `false`；仅本街已 `CHECK` 的座 `2`、`3` 为 `true`。）

#### 4.6.4 `B-001`（`h=1`；与 `A-002` **同一** `GameSnap` 与 **`LegalSnap`**）

| 项 | 值 |
|---|---|
| `hand_ordinal` | `1` ⇒ `button = probed_seat = actor_seat = current_seat = 0` |
| `street` / `board` | `preflop` / `[]` |
| `current_bet` / `current_bet_to_match` | `4` |
| `min_raise` | `2` |
| `last_aggressor_seat` | `5` |
| `actor_hole`（座 `0`） | `As Kh` |
| `pot_main` | `7` |

| seat | `folded` | `all_in` | `street_bet` | `total_committed` | `stack_remaining` | `has_acted_this_street` | `has_acted_since_full_raise` |
|---|---|---|---|---|---|---|---|
| 0 | false | false | 0 | 0 | 200 | false | false |
| 1 | false | false | 1 | 1 | 199 | false | false |
| 2 | false | false | 2 | 2 | 198 | false | false |
| 3 | true | false | 0 | 0 | 200 | true | false |
| 4 | true | false | 0 | 0 | 200 | true | false |
| 5 | false | false | 4 | 4 | 196 | true | true |

`LegalSnap`：`can_fold=true`；`can_check=false`；`can_call=true`；`call_amount=4`；`actual_call_amount=4`；`is_short_all_in_call=false`；`can_bet=false`；`min_bet=0`；`max_bet=0`；`can_raise=true`；`min_raise_to=6`；`max_raise_to=200`。

`Cand(B-001)` 仅 `RAISE`：`[(raise,6), (raise,8), (raise,10)]`。（与 `A-002` 同一 `GameSnap`；座 `5` 完整开池加注后 `_reopen_after_full_raise` 仅令其自身为 `true`。）

#### 4.6.5 `B-002`（`h=2`；flop BTN 面对 SB 下注 `6`）

| 项 | 值 |
|---|---|
| `hand_ordinal` | `2` ⇒ `current_seat = actor_seat = 1` |
| `street` / `board` | `flop` / `[Ah, 7d, 3c]` |
| `current_bet` / `current_bet_to_match` | `6` |
| `min_raise` | `6` |
| `last_aggressor_seat` | `2` |
| `actor_hole`（座 `1`） | `Qs Jd` |
| `pot_main` | `12` |

| seat | `folded` | `all_in` | `street_bet` | `total_committed` | `stack_remaining` | `has_acted_this_street` | `has_acted_since_full_raise` |
|---|---|---|---|---|---|---|---|
| 0 | true | false | 0 | 0 | 200 | true | false |
| 1 | false | false | 0 | 2 | 198 | false | false |
| 2 | false | false | 6 | 8 | 192 | true | true |
| 3 | true | false | 0 | 2 | 198 | true | false |
| 4 | true | false | 0 | 0 | 200 | true | false |
| 5 | true | false | 0 | 0 | 200 | true | false |

`LegalSnap`：`can_fold=true`；`can_check=false`；`can_call=true`；`call_amount=6`；`actual_call_amount=6`；`is_short_all_in_call=false`；`can_bet=false`；`min_bet=0`；`max_bet=0`；`can_raise=true`；`min_raise_to=12`；`max_raise_to=198`。

`Cand(B-002)` 仅 `RAISE`：`[(raise,12), (raise,14), (raise,16)]`。（座 `2` 完整下注后重开；座 `3` 随后 `FOLD` 不改该字段。）

**快照核验**

| 编号 | 判据 |
|---|---|
| SNAP-J1 | `Cand(n)` 与 `LegalSnap` 一致 |
| SNAP-J2 | 守恒式成立；`stack_remaining = S − total_committed` |
| SNAP-J3 | `probed_seat = button = (hand_ordinal−1) mod N`；`actor_seat = probed_seat` |
| SNAP-J4 | 非 `actor_seat` **无**私牌字段；`actor_hole` 仅两张牌 |
| SNAP-J5 | `LegalSnap` 与 §4.5（3）／`engine.py` `legal_actions` 一致 |

## 5. 域 B：桶注册表与每节点 `b*`

### 5.1 桶名称表（有序、有限）

| ordinal | name |
|---|---|
| 0 | `BKT_OPEN` |
| 1 | `BKT_SMALL` |
| 2 | `BKT_MID` |
| 3 | `BKT_LARGE` |
| 4 | `BKT_OTHER` |

### 5.2 模板谓词（仅在与 `A_n` 联用时生效）

对整数 `a`，定义**全局模板**（用于解释命名，**不**单独作为分区）：

| name | 模板 `T_name(a)` |
|---|---|
| `BKT_OPEN` | `a = 2` |
| `BKT_SMALL` | `3 ≤ a ≤ 4` |
| `BKT_MID` | `5 ≤ a ≤ 7` |
| `BKT_LARGE` | `8 ≤ a ≤ 10` |

### 5.3 节点参数化归属 `bucket_n(a)`

对每个域 B 节点 `n`，`A_n` 为 §4.6 中 `Cand(n)` 的 `RAISE`／`BET` 总额集合。

**算法（写死，BKT-J1）**：对 `a ∈ A_n`，

```text
若 T_OPEN(a) 则 bucket_n(a) := BKT_OPEN
否则若 T_SMALL(a) 则 bucket_n(a) := BKT_SMALL
否则若 T_MID(a) 则 bucket_n(a) := BKT_MID
否则若 T_LARGE(a) 则 bucket_n(a) := BKT_LARGE
否则 bucket_n(a) := BKT_OTHER
```

（`T_*` 为 §5.2 模板谓词。）

**逐金额核对表**（必须与上式结果一致；**不是**另一套定义）：

| node_id | `a` | `bucket_n(a)` |
|---|---|---|
| B-001 | `6` | `BKT_MID` |
| B-001 | `8` | `BKT_LARGE` |
| B-001 | `10` | `BKT_LARGE` |
| B-002 | `12` | `BKT_OTHER` |
| B-002 | `14` | `BKT_OTHER` |
| B-002 | `16` | `BKT_OTHER` |

**`BKT_OTHER` 登记（本版）**：在 **`B-001`** 上，所有 `a ∈ A_n` 均命中 `T_MID` 或 `T_LARGE`，故 **`BKT_OTHER` 在 `B-001` 上为空**。在 **`B-002`** 上，`A_n = {12, 14, 16}` 均不满足 `T_OPEN`…`T_LARGE`，故 **三者均为 `BKT_OTHER`**。

| node_id | `A_n` | `b*` |
|---|---|---|
| B-001 | `{6, 8, 10}` | `BKT_MID` |
| B-002 | `{12, 14, 16}` | `BKT_OTHER` |

### 5.4 域 B 查询口径（主判）

与 §6.1 相同：**未指定**模式覆盖；输出 `aggregation = marginalized`；**禁止** `mode_override` 进入主判。

### 5.5 域 B 节点级量（B-1）

对域 B 节点 `n`、锁定 `b*`：

```text
y_B(n) := Q_candidate(b*, n) − Q_baseline(b*, n)
```

其中 `Q_*(b*, n)` 为：在 §5.4 主判口径下，对身份 `*` 在快照 `Snap(n)` 的 **marginalized** 输出中，将所有 `c ∈ Cand(n)` 且 `bucket_n(amount(c)) = b*` 的候选的 `units` 求和，再除以 `probability_units`（`1_000_000`）得到的**概率单位**质量。

**AB-0（节点支路）**：`Q_candidate, Q_baseline ∈ [0,1]` ⇒ `y_B(n) ∈ [−1, 1]`。

**登记**：桶归属表与 `b*` **未审查通过前**不得对外声称 B-1 支持界已在战役层「成立」；本送审稿为锁定**候选**。

## 6. 域 A：动作对、`q_c` 与合法动作枚举

### 6.1 查询口径（全部域 A 节点共用；`74b` 主判）

| 项 | 锁定值 |
|---|---|
| `capability_id` | `distribution-observation@1` |
| 模式覆盖 | **未指定**（`74b` §7.3） |
| 主判输出 `aggregation` | **`marginalized`**（`74b` §7.5 第 1 条） |
| `overridden_mode` | **不得出现**于主判输出（`74b` §7.4 第 3 条） |
| 查询输入 | `Snap(n)` 的 `GameSnap` + `LegalSnap`（§4.5–§4.6）；`node_id` 为登记键 |

**禁止**在主判路径使用 `mode_override` 或任一单一 `normal`／`cautious`／`pressed` 条件分布替代 `marginalized`（`74b` §4.1 要求 B、§7.5）。

### 6.2 域 A 节点级量（A-1）

```text
y_A(n) := q_candidate(i, n) − q_candidate(i′, n)
```

- `q_candidate(i, n)`：在 §6.1 主判口径下，**candidate** 身份在 `actor_seat` 上对 `ActionRef i ∈ Cand(n)` 的 **marginalized** 概率单位质量（`units / probability_units`）。
- **不**使用动作样本 `0/1` 指示量；域 B 使用两身份桶差（§5.5），与 `74aa` A-1／B-1 分工一致。

### 6.3 域 A 合法动作与有序对（与 `Cand(n)` 一致）

| node_id | `Cand(n)` | 有序对 `(i,i′)` |
|---|---|---|
| A-001 | §4.6.1 | `((fold,0), (call,0))` |
| A-002 | §4.6.2 | `((fold,0), (call,0))` |
| A-003 | §4.6.3 | `((check,0), (bet,4))` |

**AB-0（节点支路）**：在 §6.1 下 `q_candidate(i,n), q_candidate(i′,n) ∈ [0,1]` ⇒ `y_A(n) ∈ [−1, 1]`。

## 7. `L*`、层谓词、P1、`P_ℓ`、`M_ℓ`、`n_ℓ` 与规范序

### 7.1 主判层集合与优先序

```text
L* = { L-A-PF, L-A-FL, L-B }   // 三层
优先序：L-A-PF ≺ L-A-FL ≺ L-B
```

### 7.2 层谓词 `I_ℓ(n)`（仅读 §4 外生字段）

| 层 `ℓ` | `I_ℓ(n)` 为真当且仅当 |
|---|---|
| `L-A-PF` | `domain=A` 且 `street=preflop` |
| `L-A-FL` | `domain=A` 且 `street=flop` |
| `L-B` | `domain=B` |

**无兜底层**：若存在 `n ∈ U*` 使所有 `I_ℓ(n)` 为假 ⇒ 规格自检**失败**（本版构造下不发生）。

### 7.3 P1 构造与 `P_ℓ` 完整枚举

对 `ℓ ∈ L*`：

```text
P_ℓ := { n ∈ U* : I_ℓ(n) ∧ ∀ ℓ′ ≺ ℓ, ¬I_{ℓ′}(n) }
```

| 层 `ℓ` | `P_ℓ` 枚举（`node_id`） | `M_ℓ` | `n_ℓ` | 层类 |
|---|---|---|---|---|
| `L-A-PF` | `A-001`, `A-002` | `2` | `2` | 全枚举（`L_e`） |
| `L-A-FL` | `A-003` | `1` | `1` | 全枚举（`L_e`）；**不**套用 `M_ℓ≥2` 抽样公式 |
| `L-B` | `B-001`, `B-002` | `2` | `2` | 全枚举（`L_e`） |

**并集与互斥**：`⋃_ℓ P_ℓ = U*`；两两不交。

### 7.4 `P_ℓ` 内规范全序（S-1 与组合双射用）

层 `ℓ` 内节点按 **`κ_node`**（§4.4）升序排列，得 `rank_ℓ(n) ∈ {0,…,M_ℓ−1}`。

| 层 | 序（`κ_node` 升序 → `rank_ℓ`） |
|---|---|
| `L-A-PF` | `A-001` → `0`，`A-002` → `1`（`spot_id` UTF-8：`btn_facing_bb` ≺ `btn_facing_open`） |
| `L-A-FL` | `A-003` → `0` |
| `L-B` | `B-002` → `0`，`B-001` → `1`（`street`：`flop` ≺ `preflop`） |

当 `n_ℓ = M_ℓ` 时，块模板（§11）取**全集**，不调用组合抽样；`S-1` 双射仍由本序定义（单解）。

### 7.5 `L_s` / `L_e`（模板量）

```text
L_e := { ℓ ∈ L* : n_ℓ = M_ℓ } = { L-A-PF, L-A-FL, L-B }
L_s := { ℓ ∈ L* : n_ℓ < M_ℓ } = ∅
```

对本锁定版本 1，块级 `V_max^{AB}(v)` 求和中 **`L_s` 为空** ⇒ 上式求和项为零；**不**主张 `n_s ≥ 2` 严格非退化；仅登记公式来源（§12）。

## 8. AB-0 登记（仅节点级量与逐层支持界）

### 8.1 节点级量汇总

| node_id | 量 | 定义节 |
|---|---|---|
| A-001, A-002, A-003 | `y_A(n)` | §6.2 |
| B-001, B-002 | `y_B(n)` | §5.5 |

### 8.2 逐层支持界

对每个 `ℓ ∈ L*`，令 `N_ℓ := P_ℓ` 上节点集合：

```text
a_ℓ := min_{n ∈ N_ℓ} a_n ，  b_ℓ := max_{n ∈ N_ℓ} b_n ，  R_ℓ := b_ℓ − a_ℓ
```

其中 `[a_n, b_n]` 为节点 `n` 上 **`y` 的合法取值闭区间**（由定义推出，不读样本）：

| 层 `ℓ` | 节点 | `[a_n, b_n]` | 聚合 `[a_ℓ,b_ℓ]` | `R_ℓ` |
|---|---|---|---|---|
| `L-A-PF` | A-001, A-002 | 均为 `[−1, 1]` | `[−1, 1]` | `2` |
| `L-A-FL` | A-003 | `[−1, 1]` | `[−1, 1]` | `2` |
| `L-B` | B-001, B-002 | 均为 `[−1, 1]` | `[−1, 1]` | `2` |

### 8.3 `M_AB(v)`（定义量，非读数）

在 W-1 向量 `v` 写定后（§10）：

```text
M_AB(v)² := ( Σ_{ℓ ∈ L*} v_ℓ · R_ℓ )² / 4
```

本版：`R_ℓ = 2` 恒常，`Σ v_ℓ = 1` ⇒ `M_AB(v) = 1`（**恒等式**，不是实测）。

### 8.4 AB-0 候选条款边界

- §8 **不**断言 AB-1′、块抽样或 `T_AB` 已实现或成立。
- 域 B 桶表未闭合时，**不得**登记对应节点的 `[a_n,b_n]`；本送审稿在 §5 已闭合**候选**表，须审查后方得称为锁定生效。

## 9. AB-1′ 前提：P1 与 `P_ℓ`（非 AB-0）

AB-1′ 陈述（来源 `74i`／`74aa`）：对每个主判层 `ℓ`，块 `j` 的层样本 `S_{j,ℓ}` 为 `P_ℓ` 上 `n_ℓ` 元子集，边缘为均匀无放回。

**本文件角色**：§7 写定 `P_ℓ`、`M_ℓ`、`n_ℓ` 与规范序，使 AB-1′ **有**静态前提；**不**声称 AB-1′ 已由运行器、L-3 协议或材料落盘**建立**。

## 10. W-1 候选条款：W-b 单点类 `{v}`

### 10.1 公式（与 `74aa` 一致）

```text
v_ℓ := M_ℓ / S_M ，  S_M := Σ_{ℓ′ ∈ L*} M_ℓ′
```

### 10.2 逐分量有理数（本版）

`S_M = 2 + 1 + 2 = 5`。

| 层 `ℓ` | `M_ℓ` | `v_ℓ`（既约分数） | 十进制（对照，非规范源） |
|---|---|---|---|
| `L-A-PF` | 2 | `2/5` | `0.4` |
| `L-A-FL` | 1 | `1/5` | `0.2` |
| `L-B` | 2 | `2/5` | `0.4` |

**自检**：`v_ℓ ≥ 0`，`Σ_ℓ v_ℓ = 1`。

### 10.3 边界

- **不得**沿用 `74v` 的 `weight_class`／WC-1；**不得**在 ⑥ 再补写 A/B `v_ℓ` 替代本节。
- 审查通过前：**W-1 未建立**。

## 11. 块模板 `T_AB`（纯结构）

### 11.1 参数

| 项 | 规则 |
|---|---|
| 块索引 | `j = 0, 1, …`（计数用；本锁定**不**冻结块数） |
| 块内手数 `H` | 正整数且 **`H ≥ H_min`**；**无** `H ≤ N` 上界 |
| `H_min` | **`2`**（本版最大 `hand_ordinal`） |
| `HandPlan` | 对每个 `h ∈ {1,…,H}` 一行：`hand_ordinal = h`，`button = (h−1) mod N`，`probed_seat = button`（`74y` SR-B1／SR-P1） |
| 层参与 | 每个块对**全部** `ℓ ∈ L*` 执行一次层选择 |

### 11.2 节点—手序映射与层选择

| `node_id` | `hand_ordinal` | 查询时使用的 `HandPlan` 行 |
|---|---|---|
| A-001, A-002, B-001 | `1` | `h = 1` |
| A-003, B-002 | `2` | `h = 2` |

1. 凡 `uses_schedule = yes` 的节点，构造 `Snap(n)` 时 **必须**取上表 `hand_ordinal` 对应的 `HandPlan` 行，并令 `GameSnap.button`／`probed_seat`／`actor_seat` 与该行一致（**不得**另写冲突庄位）。
2. 块内若 `H > H_min`，则 `h > 2` 的行仅服务于 `74y` 轮换登记；**不**附加本版未登记的节点。
3. 对每个 `(j, ℓ)`：从 `P_ℓ` 按 §7.4 选取 **`n_ℓ` 个** `node_id`（本版为全集）；节点 `n` 的查询绑定 `hand_ordinal(n)`。
4. 块内唯一定位键：`(j, ℓ, node_id, hand_ordinal(n))`。

### 11.3 S-1 组合索引（当 `n_ℓ < M_ℓ` 时适用）

对固定 `(ℓ, M_ℓ, n_ℓ)`：

1. 均匀整数 `u ∈ {0, …, C(M_ℓ, n_ℓ) − 1}`（外部随机化协议；**本文件不**生成 `u`）。
2. 将 `u` 映射为 `rank_ℓ` 上大小为 `n_ℓ` 的子集：采用 **colexicographic** 组合序（标准组合数排名与 `P_ℓ` 上 `rank_ℓ` 升序配合）；映射须为双射。
3. 本版 `n_ℓ = M_ℓ` 的层：唯一子集为全集，**不**消耗随机材料亦可登记为确定性选择。

**L-3 边界**：现行 L-3 随机化协议**未**包含 A/B 层抽样材料用途；**不得**称 AB-1′ 已由 L-3 **建立**；新材料用途、键与实现须**后续单独授权**。

## 12. `V_max^{AB}(v)`（通用候选；不采用 AB-2z）

在 **AB-0**、**AB-1′**、**W-1** 均成立且审查选用本候选时（`74i` §5.3、`74aa` §8.1）：

```text
V_max^{AB}(v) := ( Σ_{ℓ ∈ L_s} v_ℓ · √c_ℓ · R_ℓ / (2 √n_ℓ) )²
c_ℓ := (M_ℓ − n_ℓ) / (M_ℓ − 1)   （仅 ℓ ∈ L_s）
```

本版 `L_s = ∅` ⇒ 右式为 `0`（空和）。**不**采用 `V_max^{AB,0}`；**不**采用 AB-2z。

## 13. 可执行判据（候选）

| 编号 | 判据 | 类型 |
|---|---|---|
| SNAP-J1 | `Cand(n)` 与 `LegalSnap`、§4.6 一致 | 机械 |
| SNAP-J2 | §4.5（3）筹码守恒；`stack_remaining = S − total_committed` | 机械 |
| SNAP-J3 | `hand_ordinal` 与 `74y`；`actor_seat = probed_seat = button` | 机械 |
| SNAP-J4 | 仅 `actor_hole`；`seats[]` 无私牌 | 机械 |
| SNAP-J5 | `LegalSnap` 与 §4.5（3）／`engine.py` `legal_actions` 一致 | 机械 |
| AB0-J1 | 节点表与 §6、§5 动作／桶一致；`y` 区间由定义推出 | 对照／形式 |
| AB0-J2 | 每层 `R_ℓ = b_ℓ − a_ℓ` 与 §8.2 表一致 | 机械 |
| P1-J1 | 机械复算 `P_ℓ` 满足互斥且 `⋃ P_ℓ = U*` | 机械 |
| P1-J2 | 无节点命中多层 | 机械 |
| BKT-J1 | `bucket_n(a)` 与 §5.2–§5.3 算法及核对表一致 | 机械 |
| W-J1 | `Σ v_ℓ = 1`，与 §10.2 分数一致 | 机械 |
| T-J1 | `HandPlan` 行满足 SR-B1／SR-P1（**不**要求 `H ≤ N`） | 对照 |
| T-J2 | 块内层选择键 `(j,ℓ,node_id)` 唯一 | 机械 |

**③ 未授权**；判据**不**构成质量证据。

## 14. 实现缺口（只读登记）

| 项 | 缺口 |
|---|---|
| `CampaignLockVersions` | **无** `domain_ab_*` 字段 |
| 节点／桶校验 | 包内**无** A/B 注册表硬校验 |
| `distribution_observation` | 域 B 分域链／金额分区**未**按 §5 闭合实现 |
| L-3 | **无** A/B 层抽样材料键 |
| SR-J4/J5 等 | 仍属 `74y` 实现另案 |

## 15. 前提状态（审查前）

| 对象 | 状态 |
|---|---|
| AB-0 | **候选条款**；审查前**未建立** |
| AB-1′ | **未建立** |
| W-1 | **未建立** |
| 域 A/B ② 交付 | **未发生** |
| A 路径 | **未成立** |
| ③–⑦ | **均未发生** |

## 16. 申请全文内容复审（第四轮）

请审查方核验第四轮三项机械修订是否已消除阻断，并复验第三轮已闭合项仍成立：

1. **域 A 动作对一致**：§6.3 `A-001` 有序对是否与 §4.6.1 `Cand(A-001)` 及 `LegalSnap`（`can_call`、无 `can_bet`）一致；
2. **`P_ℓ` 规范序**：§7.4 `L-A-PF` 的 `rank_ℓ` 是否由 §4.3 登记 `spot_id` 与 §4.4 `κ_node`（含 UTF-8 `spot_id` 序）机械推出；
3. **`has_acted_since_full_raise`**：§4.6.1／§4.6.3–§4.6.5 逐座取值是否与 `engine.py` 的 `_reopen_after_full_raise`、`CHECK`／`CALL`／`FOLD`、`_advance_street` 一致（**不得**以 `has_acted_this_street` 替代）；
4. **第三轮保留项**：§4.5（3）与 `legal_actions`；`A-002`／`B-001` 共享 `LegalSnap`；`B-002` `min_raise_to=12` 与 `Cand`；§5.3 `BKT_OTHER` 与 `b*`；`marginalized`、私牌边界、`74y`／`HandPlan`、SNAP-J2、AB-0／AB-1′ 分工；**无** `H ≤ N`；**未**越权改仓库或推进 ②／③。

**下一步唯一建议动作（须另行授权）**：对本文件作**全文内容复审**；复审通过前全部条款仅为锁定候选。
