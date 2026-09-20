# 44 M8：P1-3 逐池货币收益契约（短码 / 边池 / 多人平局）（规格冻结）

> 日期：2026-09-20。
>
> 本文件接在 `docs/43` / `docs/43a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/44` 记录本轮**规格与决策冻结**，`docs/44a` 记录与之对应的**实施与验证回执**。`docs/20` 至 `docs/43a` 未被改写。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P1-3** 一项的规格冻结与设计岔路裁定。代码与测试在随后一次提交中落地，回执见 `docs/44a`。
>
> **实施期修订（原因与回执见 `docs/44a`）**：§4.5 / §4.6 / §4.7 / §4.9 中「范围来源委托范围假设模块校验」改为「**声明常量 + 测试锁定**」。原因是 P1-2 的冻结回归测试把 `app/` 内任何引用 `range_assumption` 的文件判为「生产调用方」，而 P1-2 自身对 P0-5 采用的正是「声明常量 + 测试锁定」这一做法；本轮沿用同一约定，不改动 P1-2 的既有测试与 `docs/43` / `docs/43a`。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项）

本轮用户明确授权的实施范围**只有一项**，来自 `docs/35` §4.2 的 P1 组：

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P1-3 | 逐池货币收益（短码 / 边池 / 多人平局） | **是** |
| P0-1 … P0-7 | 注册表、lookup 预算、抽象映射、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**复用**） |
| P1-1 | 位置与公开行动历史的信息集投影 | 否（已完成，仅**对照**其座位口径） |
| P1-2 | 范围模型替代「vs 随机底牌」 | 否（已完成，仅**引用**其受控 profile 标识） |
| P1-4 | 真实 Hold'em 的下注尺度与公共牌 | 否 |
| P1-5 | 修复后 6/7（及 2–9）人性能复测 | 否 |
| P2-1 … P2-4 | 2–9 人产品验收、N=9 结论、历史 `pot_results`、稳定性生产者 | 否 |

P1-3 **只是** `docs/35` §4.2 清单中的一项；本文件不改变其余条目的现状、优先级或失效条件，也不构成任何实施授权。按 `docs/35` §4.3 的依赖链 `P1-1 → P1-2 → P1-3`，本轮是这条链的末端。

### 1.2 用户答复原文（执行确认与五个设计岔路）

本轮采用「**先问用户**」而非「先在文档冻结规格」。答复原文照录：

| 项 | 用户答复原文 |
|---|---|
| 执行确认与边界 | 「确认执行，边界如上」(沿用 P1-1/P1-2 口径：strategy 新增模块不改既有语义、零生产调用方、poker 与 analysis 零改动不 import 之外的引用) |
| 岔路一：投影载体与命名 | 「新增 pot_ev_contract.py」(新增 `backend/app/strategy/pot_ev_contract.py`；不动 `poker/pot_projection.py` 与 `analysis/`（推荐，与 P1-1/P1-2 平行）) |
| 岔路二：本轮交付范围 | 「只交付契约 + 显式组合」(把既有资格投影、实际支付 `A`、确定回收 `R_h`、平局分配口径与 σ 拼成受控字段；不实现抽样，联合 runout 作为共享口径声明（推荐）) |
| 岔路三 + 四：σ 口径与短码/边池/符号口径 | 「按建议冻结」(σ 为受控闭集（本轮只登记「其余座位全部 CHECK/CALL 到摊牌」单一内置情景，不接受任意注入）；`A` 为唯一现金成本 `-A`，`C` 仅作参照；`caller_recovery` 计入确定回收 `R_h`；`other_uncontested` / `no_eligible_return` 不计入；`contested` 进入 `E[ΣS]` 用名义份额 `1/k`；整数余数与名义份额分别表述（推荐）) |

据此，**被授权**：在 `backend/app/strategy/` 新增逐池收益契约模块（不改既有模块语义）、在 `backend/tests/` 新增回归测试、新增 `docs/44*`。
**被拒绝**（本轮不做）：`tools/trainer/**` 与 `backend/app/poker/**` 任何改动；`backend/app/analysis/**`（含 `hand_review.py` / `reference_identity.py`）任何改动；`backend/app/api/**` 与 `frontend/**` 任何改动；`storage/models.py` 与真实数据库任何改动；任何生产接入（策略 / 复盘 / API / 前端）；抽样实现；真实下注尺度与公共牌；性能复测。

### 1.3 四项裁定（冻结）

| 岔路 | 裁定 |
|---|---|
| 一 | 新增 `backend/app/strategy/pot_ev_contract.py` 作为**纯函数 + 冻结 Pydantic 模型**入口；**不改动**已冻结的 `poker/pot_projection.py`（资格投影）与 `analysis/`（参考与评估身份）的任何语义；本模块**只读引用**既有资格投影的模型类型，**不重造**第二套分层或脱敏逻辑。 |
| 二 | 本轮**只交付契约与显式组合**：把「逐层 eligible 集合 + 实际支付 `A` + 确定回收 `R_h` + 平局分配口径 + 名义份额与整数派彩的区分 + 后续行动情景 σ」定义成受控字段；**不实现**联合 runout 或份额抽样，`E[Σ S_{h,ℓ} \| σ]` 在本轮是**未求值的占位**，只由字段与声明承载。 |
| 三 | 后续行动情景 σ 是**受控闭集**：本轮只登记一个内置情景 `others-check-call-to-showdown@1`（其余座位自本街起全部 CHECK/CALL 到摊牌，不再有新的下注或加注），**不接受**调用方注入任意情景；未知标识明确失败。σ **不得**被表述为完整 CALL EV 或 GTO。 |
| 四 | 符号与座位口径：`actual_call_amount`（`A`）是**唯一**现金成本项（符号 `-A`），`call_amount`（`C`）只作差额参照、**不进入**任何收益口径；`caller_recovery` 层计入**确定回收** `R_h`（正项、确定而非期望）；`other_uncontested` 与 `no_eligible_return` 层**不计入**；`contested` 层进入期望项 `E[Σ S_{h,ℓ}]`，其**名义份额**按该层同级赢家人数 `k` 取 `1/k`；**整数派彩**（`amount // k` 加余数按座位升序）与名义份额**分别**表述，不得相互冒充。座位口径沿用 `CandidateCallProjection` 的**绝对 seat**（见 §4.7）。 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -6 --oneline
f9e957b feat: add controlled action-line range assumption contract
3ea9140 docs: freeze p1-2 action-line range assumption contract specs
0e5fd52 feat: add controlled position and public action line projection
bf6794d docs: freeze p1-1 position and public action line projection specs
9c684e7 feat: add controlled artifact lookup with budget contract and opt-in measurement
3d3c7d1 docs: freeze p0-2 lookup performance and memory budget specs

$ git rev-parse HEAD          -> f9e957bf9f9a1df89bb92957c01e031d5d48723d
$ git rev-parse origin/master -> f9e957bf9f9a1df89bb92957c01e031d5d48723d

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8
$ find /Users/bryanylliu/holdem-campaigns -name strategy.json | wc -l
11

$ ls -1 backend/app/strategy/
__init__.py  abstraction.py  artifact.py  heuristic.py  interface.py  lookup_budget.py
position_projection.py  projection.py  random_strategy.py  range_assumption.py  registry.py

$ ls -1 backend/app/analysis/
__init__.py  hand_review.py  reference_identity.py

$ ls -1 backend/app/poker/
__init__.py  actions.py  cards.py  deck.py  engine.py  equity.py  evaluator.py
hand.py  pot_projection.py  state.py
```

与期望基线完全相符（`## master...origin/master` 不多不少、工作区 0 行、`HEAD == origin/master` 且全哈希逐字符一致、campaigns = 8、11 份 `strategy.json`、`strategy/` 无逐池收益模块）；未做任何 `reset` / `clean` / `stash` / `checkout`；**未 push**；未消耗任何本机实验预算。

## 3. 现状事实与必然落差（只读核验）

### 3.1 现有能力（本轮直接复用，不重造）

只读核验 `backend/app/poker/pot_projection.py`：

- `project_pot_layers(participants)` 只按**公开累计投入**与**弃牌状态**切层，输出 `PotLayer(lower_commitment, upper_commitment, amount, contributor_seats, eligible_seats, refunds)`；**无牌力、无赢家、无金额分配**；
- `project_candidate_call(participants, caller_seat, actual_call_amount)` 只在当前行动者的累计投入上增加**实际支付 `A`**，并把每层标为 `PotLayerKind` 四值之一：`contested` / `caller_recovery` / `other_uncontested` / `no_eligible_return`；返回 `CandidateCallProjection(caller_seat, actual_call_amount, participants, layers)`；
- 引擎侧只读入口为 `PokerEngine.candidate_call_pot_projection()`，**不修改** `stack` / `street_bet` / `total_committed` / `all_in` / 行动顺序 / 历史 / 公共牌 / 结算结果。

只读核验 `backend/app/poker/equity.py`：

- 旧 `equity()` 的精确语义是 \(E[\mathbf 1_{严格独赢}+\tfrac12\mathbf 1_{并列最强}]\)，平局**一律折半**，`num_opponents <= 0 -> 1.0`；
- `estimate_static_showdown_share(...)` 只表示**固定 pooled 竞争集合**的静态名义 share（逐样本按 `1` / `1/(k+1)` / `0` 累加），**目前无生产调用方**。

只读核验 `backend/app/poker/actions.py` 与 `engine.py`：

- `LegalActions.call_amount` = 完整差额 `C`，`actual_call_amount` = 实际支付 `A`，并有 `is_short_all_in_call`；`A = min(C, stack)`，故 `C > A` 与 `is_short_all_in_call` 同义（在 `can_call` 成立时）；
- `_settle_showdown()` 已按**每层 eligible 实际牌力**选赢家、`amount // winners` 均分、余数按赢家座位**升序**分配（**结算语义冻结，本轮不得改**）。

只读核验 `backend/app/strategy/`：`position_projection.py`（P1-1）与 `range_assumption.py`（P1-2）已按「独立模块 + 冻结模型 + 分型异常 + 本地冻结常量 + 无生产调用方」落地。

### 3.2 后端不存在的能力（本轮要补的缺口）

经只读核验：后端**不存在**任何把「逐层资格」与「实际支付 / 确定回收 / 平局分配口径 / 后续行动情景」组合成受控字段的契约。`project_pot_layers()` / `project_candidate_call()` 只回答**资格**（哪些层、谁有资格、是否回收）；`estimate_static_showdown_share()` 只回答**单一 pooled 静态 share**；`equity()` 固定 `ties/2`。三者都**不是**逐池货币收益，也没有任何字段承载 \(R_h\)、\(A\)、σ 与「名义份额 vs 整数派彩」的区分。

### 3.3 必然落差（必须如实写明）

1. 候选 A 的 probe 与既有启发式**都是 vs 随机范围**（`docs/35` §4.2）。本轮交付的是**逐池收益的口径契约**，它**不**是求解器输出、**不**来自 CFR 训练，也**不**声称接近均衡。
2. 本轮**不实现抽样**：\(E[\sum_\ell S_{h,\ell}\mid\sigma]\) 在本轮**没有数值**，只是一个**由字段与声明承载的未求值占位**。因此本轮**不产出**任何 CALL EV 数值，也**不得**把契约当作「已算出逐池 EV」。
3. 真实下注尺度与公共牌属 **P1-4**（未授权）。本轮接收的是**已经公开的资格投影**，因此**不接收** `board` / 真实牌面 / runout 实体；「联合 runout」在本轮只作为**跨层共享口径的声明**（所有 contested 层必须在**同一次** runout 下评估，层间结果相关、不可独立抽样），而非可执行的采样。
4. 范围由 **P1-2** 提供（声明式、不随公共牌收窄、不读取真实底牌）。本模块只**引用**其受控 profile 标识以声明范围来源，**不**展开权重、**不**做组合数步骤。
5. 由此：**不得**把资格投影或静态 pooled share 表述为逐池 EV / 完整 CALL EV / GTO；**不得**用 `1/k` 直接替换既有 `call_ev`。

## 4. P1-3 规格（冻结）

### 4.1 契约结构版本与基准标识

```text
POT_EV_CONTRACT_SCHEMA_VERSION = "pot-ev-contract.v1"
POT_EV_BASIS = "per-layer-eligible-shared-runout"
```

`POT_EV_BASIS` 声明本契约的口径基准：**逐层 eligible 集合 + 跨层共享的联合 runout**。

### 4.2 逐池收益层 `PotEvLayer`（冻结，字段齐备）

`PotEvLayer` 是**冻结的 Pydantic model**，字段恰好为下列十项（顺序即契约顺序）：

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `lower_commitment` | `int` | 该层下界累计投入（含） |
| 2 | `upper_commitment` | `int` | 该层上界累计投入（含） |
| 3 | `amount` | `int` | 该层金额（含弃牌死钱） |
| 4 | `contributor_seats` | `tuple[int, ...]` | 该层贡献者（**绝对 seat**，升序） |
| 5 | `eligible_seats` | `tuple[int, ...]` | 该层未弃牌资格者（**绝对 seat**，升序） |
| 6 | `kind` | `str` | 沿用 `PotLayerKind` 的四值之一 |
| 7 | `disposition` | `str` | 本模块的收益处置（见 §4.3） |
| 8 | `caller_eligible` | `bool` | 当前行动者是否在该层有资格 |
| 9 | `enters_expected_share` | `bool` | 该层是否进入期望项 \(E[\sum_\ell S_{h,\ell}]\) |
| 10 | `certain_recovery` | `int` | 若为确定回收层，则等于 `amount`；否则 `0` |

`PotEvLayer` **不得**包含：其他座位暗牌、自己的底牌、公共牌、真实牌面、runout 实体、运行中 seed、对手内部参数、未来行动或结算结果、赢家或同级赢家人数。

### 4.3 处置枚举 `PotEvDisposition` 与四类资格的对应（冻结）

`PotEvDisposition` 是受控闭集，取值恰为下列四个：

| disposition | 对应 `PotLayerKind` | 收益口径处置 | 符号 |
|---|---|---|---|
| `contested` | `contested` | 进入期望项 \(E[\sum_\ell S_{h,\ell}\mid\sigma]\)，名义份额按该层同级赢家人数 \(k\) 取 \(1/k\) | 期望项（未求值） |
| `certain_recovery` | `caller_recovery` | 计入**确定回收** \(R_h\)，是**确定**项而非期望项 | `+`（确定） |
| `not_eligible` | `other_uncontested` | **不计入**：当前行动者无资格 | `0` |
| `refund` | `no_eligible_return` | **不计入**：该层无人有资格、按投入退回贡献者，与当前行动者**结构上无关**（当前行动者未弃牌，不可能只与弃牌者同层） | `0` |

约束：

1. `disposition` 与 `kind` 必须**一一对应**（四值映射表即契约）；未知 `kind` 不得构造；
2. `enters_expected_share` 当且仅当 `disposition == "contested"`；
3. `certain_recovery > 0` 当且仅当 `disposition == "certain_recovery"`，且此时必须等于 `amount`；
4. `caller_eligible` 必须与层内 `caller_seat` 是否在 `eligible_seats` 一致；
5. 层序必须按 `lower_commitment` 升序且**连续**（后层下界等于前层上界）。

### 4.4 后续行动情景 σ（冻结，受控闭集）

`POT_EV_SCENARIOS` 是受控闭集，本轮只登记一个内置情景：

```text
POT_EV_SCENARIO_CHECK_CALL = "others-check-call-to-showdown@1"
POT_EV_DEFAULT_SCENARIO = POT_EV_SCENARIO_CHECK_CALL
```

其描述声明为：**其余座位自本街起全部 CHECK/CALL 到摊牌；不再有新的下注或加注。**

约束：

1. 情景标识必须形如 `name@version`；未登记标识抛 `UnknownScenarioError`，**不回落**默认情景；
2. 调用方**只能**在闭集内选择，不能注入任意情景对象或自由文本；
3. σ **不是**完整 CALL EV、**不是** GTO、**不是**对真实后续行动的预测；它是**被显式声明的**假设情景。

### 4.5 逐池收益契约 `PotEvContract`（冻结，字段齐备）

`PotEvContract` 是**冻结的 Pydantic model**，字段恰好为下列十七项（顺序即契约顺序）：

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `schema_version` | `str` | 本契约的结构版本（当前唯一受支持值 `pot-ev-contract.v1`） |
| 2 | `basis` | `str` | 口径基准（`per-layer-eligible-shared-runout`） |
| 3 | `scenario_identifier` | `str` | 生效的受控情景标识（σ） |
| 4 | `scenario_description` | `str` | 该情景的显式描述 |
| 5 | `range_profile_identifier` | `str` | 范围来源标识（`name@version` 形式；取值与 P1-2 的受控 profile 标识一致，由测试锁定） |
| 6 | `range_source` | `str` | 范围来源标注（受控常量：只允许「声明的模型假设」） |
| 7 | `player_count` | `int` | `N`（2–9，透传自资格投影） |
| 8 | `caller_seat` | `int` | 当前行动者的**绝对 seat**（透传自资格投影） |
| 9 | `call_amount` | `int` | 完整差额 `C`：**仅作参照**，不进入任何收益口径 |
| 10 | `actual_call_amount` | `int` | 实际支付 `A`：**唯一**现金成本项 |
| 11 | `is_short_all_in_call` | `bool` | 是否短码全下跟注（`C > A`） |
| 12 | `runout_scope` | `str` | 联合 runout 的共享口径声明（`shared-across-layers`） |
| 13 | `nominal_share_rule` | `str` | 名义份额规则声明：每层按同级赢家人数 `k` 取 `1/k` |
| 14 | `integer_payout_rule` | `str` | 整数派彩规则声明：每层先取 `amount // k`，余数按赢家座位升序分配 |
| 15 | `layers` | `tuple[PotEvLayer, ...]` | 逐层收益处置（按层序升序） |
| 16 | `certain_recovery_total` | `int` | \(R_h\)：所有 `certain_recovery` 层金额之和 |
| 17 | `limitations` | `tuple[str, ...]` | 局限声明（见 §4.8） |

`PotEvContract` **不得**包含：公共牌、真实牌面、runout 实体、底池金额以外的筹码事实、真实底牌、运行中 seed、对手内部参数、未来行动、结算结果、任何 EV 数值字段。

`certain_recovery_total` 必须等于所有 `disposition == "certain_recovery"` 层的 `amount` 之和（结构自洽校验）。

### 4.6 构造入口与明确失败语义（冻结）

入口（纯函数）：

| 入口 | 输入 | 输出 |
|---|---|---|
| `build_pot_ev_contract(*, projection, call_amount, scenario_identifier=POT_EV_DEFAULT_SCENARIO, range_profile_identifier=DEFAULT_RANGE_PROFILE_IDENTIFIER)` | 既有资格投影 + 完整差额 `C` + σ 标识 + 范围 profile 标识 | `PotEvContract` |
| `disposition_for_kind(kind)` | `PotLayerKind` 四值之一 | 对应的 `PotEvDisposition` |
| `known_scenario_identifiers()` | — | 已登记情景标识的升序元组 |
| `scenario_description_for(identifier)` | 情景标识 | 该情景的显式描述 |

失败的**分类型**异常（与 P0-3 / P1-1 / P1-2 的区分口径一致）：

| 异常 | 含义 | 触发条件 |
|---|---|---|
| `PotEvContractError` | **契约违规**（结构性非法输入） | `projection` 不是 `CandidateCallProjection`；`call_amount <= 0`；`call_amount < actual_call_amount`；`player_count < 2`；`caller_seat` 越界；`layers` 为空；层序不连续或层金额与投入不一致；`range_profile_identifier` 不是 `name@version` 形式 |
| `PotEvEncodingError` | **投影不完整或不可编码** | 层内 `eligible_seats ⊄ contributor_seats`；`kind` 不在四值内；`disposition` 与 `kind` 不一致；`certain_recovery` 与 `disposition` 不一致；`caller_seat` 不在任何层 |
| `UnknownScenarioError` | **情景标识未知或版本不受支持** | `scenario_identifier` 不在受控闭集内（含未知版本与历史版本） |

基类为 `PotEvError(ValueError)`；三个子类**互不继承**。

**范围来源只作声明性引用**：`range_profile_identifier` 只校验 `name@version` **形式**，其取值与 P1-2 的受控 profile 标识一致，由**一条测试锁定**；本模块**不 import** `range_assumption`（避免与其「无生产调用方」的冻结约定冲突，沿用 P1-2 对 P0-5 的同一做法），也**不复制**范围目录。因此本模块**不**对「形式合法但未登记」的标识做运行时拒绝——该一致性由测试锁定，是本轮**被声明的边界**，不是静默回退。

**禁止静默回退**：任何未知、缺失或不可编码的输入都不得被当作「已组合」处理，也不得回落到默认情景、默认层序或补零后仍声称构造成功。

### 4.7 座位口径与信息边界

1. **座位口径沿用绝对 seat**：本模块的输入是 `CandidateCallProjection`，其 `caller_seat` / `participants` / 各层座位均为**引擎绝对 seat**。P1-1 / P1-2 的相对座位口径**不进入**本模块；本模块**不提供**第二套相对化换算，也不与 P1-1 / P1-2 的座位字段混用（避免两处各写一份换算）。
2. **不得把绝对 seat 当作牌理特征输出**：本契约的产物是**收益口径**，不进入任何 CFR 信息集键；文档与代码都必须如此表述。若后续要与 P1-1 / P1-2 联动，由调用方在两套口径之间自行换算，本模块不承担该职责。
3. 本模块**不接收** `board` / `pot` / `stack` / `hole_cards` / 任何真实底牌 / 运行中 seed，因此**在结构上**无法读取对手暗牌与未来公共牌。
4. 本模块**不 import** `app.poker.equity` / `app.poker.engine` / `app.analysis` / `app.storage` / `app.llm` / `heuristic`；只 import `app.poker.pot_projection` 的**模型类型与枚举**（只读引用）。对 P1-2 的范围来源只作**声明性引用**（受控常量 + 测试锁定），**不** import 该模块。

### 4.8 局限声明（冻结，必须齐备）

`PotEvContract.limitations` 必须同时包含下列四条（缺一即构造失败）：

| 常量 | 内容 |
|---|---|
| `POT_EV_LIMITATION_NOT_FULL_EV` | 本契约只定义逐池收益口径，不产出 CALL EV 数值，也不是 GTO。 |
| `POT_EV_LIMITATION_NO_SAMPLING` | 本轮不实现联合 runout 或份额抽样；期望项是未求值的占位。 |
| `POT_EV_LIMITATION_RANGE_DECLARED` | 范围由 P1-2 的声明式假设提供，不随公共牌收窄，也不读取真实底牌。 |
| `POT_EV_LIMITATION_NOT_QUALIFICATION_PROJECTION` | 资格投影与静态 share 不等于逐池 EV。 |

### 4.9 P1-3 验收口径

对照 `docs/35` §4.2 P1-3 原文口径（逐层 eligible 集合 + 联合 runout + 平局分配 + 实际支付 + 确定回收 + 明确后续行动情景；验收：不得把资格投影或静态 share 表述为逐池 EV / 完整 CALL EV / GTO；`1/k` 不得直接替换现有 `call_ev`）：

| # | 验收项 | 判据 |
|---|---|---|
| C1 | 逐层 eligible 与实际支付 `A`（而非 `C`）组合正确 | 契约各层与 `CandidateCallProjection` 一致；现金成本项恒为 `A`；`C` 只出现在参照字段 |
| C2 | 四类资格处置正确 | `contested` → 期望项；`caller_recovery` → 确定回收 `R_h`；`other_uncontested` / `no_eligible_return` → 不计入 |
| C3 | 短码全下覆盖层 | `is_short_all_in_call` 为真时 `C > A`；`A` 覆盖的层进入资格，超出 `A` 的层按 §4.3 处置 |
| C4 | 联合 runout 为共享口径 | `runout_scope` 声明所有 contested 层共享同一 runout；契约不含 runout 实体 |
| C5 | 平局分配与整数余数分别表述 | `nominal_share_rule` 为 `1/k`；`integer_payout_rule` 为 `amount // k` + 余数按座位升序；两者是**不同**声明字段 |
| C6 | σ 为受控闭集 | 未知情景抛 `UnknownScenarioError`；默认情景唯一；不接受任意注入 |
| C7 | 明确失败 | §4.6 三类触发条件各自抛出对应异常；三者类型互不继承；范围标识未知复用 P1-2 的 `UnknownRangeProfileError` |
| C8 | 2–9 人参数化，不写死两人 | `N = 2..9` 逐人数构造成功 |
| C9 | 不读对手暗牌与未来牌 | 模块不接受 `board` / `hole_cards`；字段集中不存在相关字段；替换暗牌后结果不变 |
| C10 | 不读运行中 seed | 入口无 `seed` 参数；字段集中不存在 `seed` |
| C11 | 不写回 `history_json` | 模块不持有引擎引用、不写任何存储；结果为纯值对象，输入不被改写 |
| C12 | 不改动既有 `call_ev` 与 `equity()` 语义 | `analysis/` 与 `poker/equity.py` 零改动；`heuristic.py` 决策语义零改动 |
| C13 | 与 P1-2 的版本化对齐 | `range_profile_identifier` 与 P1-2 的受控 profile 标识一致并由测试锁定；`range_source` 只允许声明式假设；非法形式明确失败 |
| C14 | 无生产调用方 | 模块不 import `heuristic` / `equity` / `analysis` / `storage` / `api` / `frontend`；对外响应与缓存键不变 |

## 5. 版本影响与兼容性（预期）

| 对象 | 影响 |
|---|---|
| 既有策略语义 | **零改动**：`heuristic.py` 的阈值、分支与 `equity()` 调用完全不变 |
| 复盘与参考身份 | **零改动**：`hand_review.py` 与 `reference_identity.py` 不触碰；`REFERENCE_VERSION` / `EVALUATION_VERSION` / `REFERENCE_COVERAGE` 取值不变；`call_ev` 展示口径不变 |
| API 与前端 | **零改动**：不新增或改名字段；缓存键不变 |
| 数据库 | **不加列、不迁移**；真实数据库只读 |
| 引擎 / 结算 | 零改动；`equity` / `estimate_static_showdown_share` / `pot_projection` / `_settle_showdown` 语义不变 |
| 锁文件 | 零改动（不新增依赖） |
| 新模块 | 新增独立模块与导出；**目前无生产调用方**，不改变任何运行时路径 |
| 不可编码局面的实际处置 | **不产生契约、不产生动作**；抛分类型明确异常；无默认情景、无补零、无插值 |

按 `docs/37` §3.1 的升版规则：本轮**不改动**参考实现、保守判据、`equity` 实现、采样数或固定种子中的任一项，因此**不触发升版**，并在此明确声明上述各项**零改动**。

## 6. 边界声明与不得声称

- 本轮改动是**契约与收益口径层**，**不是** CFR 接入，也**不构成任何质量证据**；`backend/app/strategy/` 仍无任何 CFR lookup 或产物接线的新语义。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实牌局 EV 或生产可用策略。
- **不得**把资格投影（`project_pot_layers()` / `project_candidate_call()`）或静态 pooled share（`estimate_static_showdown_share()`）表述为逐池 EV / 完整 CALL EV。
- **不得**用 `1/k` 直接替换既有 `call_ev`；`docs/23` §7「不把新 share 静默塞入既有字段、不把资格投影说成收益」继续有效。
- **不得**跨人数插值，**不得**用「最近桶」「补零」「掩码」冒充精确。
- 现有 `equity()` 固定 `ties/2` 的边界**不变**；生产结算**不变**；`docs/39` 的质量门槛**未被**启用。
- 稳定性结论若出现，必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 本轮不追加 seed、不新建冻结 campaign、不重试任何已消耗 authorization、不上云、不转 GPU、不扩预算。
- 不得修改 `backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/api/**`、`frontend/**`、`backend/app/storage/models.py`、真实数据库 `backend/data/holdem.db`、锁文件、`tools/trainer/**`、`docs/20` 至 `docs/43a`。

## 7. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码/测试/前端/锁文件/真实数据库；未实施 P1-3 的实现；未实施清单其余任何一项；未改质量门槛或启用 `docs/39` 门槛；未新增受监督运行或 campaign；未追加 seed；未重试 authorization；未 push。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P1-3，并在实施回执（`docs/44a`）中给出文件级改动、新增/修改测试与 `ruff` / `pytest` / `npm run build` 的实跑输出。** 若用户对 §1.3 的任一项裁定有不同意见，应在实施前先修订本文件并记录原因。

P1-3 完成之后，按 `docs/35` §4.3 的依赖建议，清单尚未授权的下一项是 **P1-4（真实 Hold'em 的下注尺度与公共牌）** 与 **P1-5（修复后 6/7（及 2–9）人性能复测）**，两者须**各自单独授权**；P2 组（2–9 人产品验收、N=9 结论、历史 `pot_results` 不一致、稳定性生产者）相互独立，可各自单独排期。
