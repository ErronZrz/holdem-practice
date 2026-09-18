# 40 M8：P0-3 抽象映射、覆盖与回退（规格冻结）

> 日期：2026-09-18。
>
> 本文件接在 `docs/39` / `docs/39a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/40` 记录本轮**规格与决策冻结**，`docs/40a` 记录与之对应的**实施与验证回执**（同一编号族内可多次提交）。`docs/20` 至 `docs/39a` 未被改写。
>
> 本文**不实施任何代码**：只完成 `docs/35` §4.2 中 **P0-3** 一项的规格冻结与设计岔路裁定。代码与测试在随后一次提交中落地，回执见 `docs/40a`。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅一项）

本轮用户明确授权的实施范围**只有一项**，来自 `docs/35` §4.2 的 P0 组：

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P0-3 | 抽象映射、覆盖与回退 | **是** |
| P0-1 / P0-4 / P0-5 / P0-6 / P0-7 | 注册表、信息边界、评估版本化、质量门槛、参考契约 | 否（已完成，仅**复用**） |
| P0-2 | 实时 lookup 性能与内存预算 | **否** |
| P1-1 … P1-5 | 位置与公开行动历史投影、范围模型、逐池 EV、真实尺度、性能复测 | 否 |
| P2-1 … P2-4 | 2–9 人产品验收、N=9 结论、历史 `pot_results`、稳定性生产者 | 否 |

P0-3 **只是** `docs/35` §4.2 清单中的一项；本文件不改变其余条目的现状、优先级或失效条件，也不构成任何实施授权。按 `docs/35` §4.3 的依赖，P0-3 是 **P0-2** 以及 **P1-1 → P1-2 → P1-3** 的先决项，但本轮**不**推进其中任何一项。

### 1.2 用户答复原文（四个设计岔路）

本轮采用「**先问用户**」而非「先在文档冻结规格」：在写代码前已就四个设计岔路取得用户答复。答复原文照录：

| 岔路 | 用户答复原文 |
|---|---|
| 执行确认与 `tools/trainer/**` 边界 | 「确认执行；trainer 只读」(允许 `backend/app/strategy/` 新增抽象投影模块（不改既有语义）、`backend/tests/`、`docs/40*`、api 最小必要；`tools/trainer/**` 仅只读引用其键格式作为规范出处，零改动、不 import。) |
| 岔路一：抽象键载体与命名 | 「对齐训练器 m8/ 格式但不依赖」(新增 `backend/app/strategy/abstraction.py` 纯函数入口；键字符串逐字对齐训练器 format（便于对账），但键格式以后端本地常量为准，不 import 训练器任何代码，避免把 trainer 变成后端硬依赖。) |
| 岔路二：覆盖判定返回形态 | 「显式状态判定对象」(返回 Pydantic 判定对象，coverage 取值区分 in-abstraction / out-of-abstraction / incomplete-infoset / version-mismatch 四种；构造入口对结构性非法输入仍抛明确异常，抽象外与不完整信息集各自独立取值，绝不静默回退、不用最近桶。) |
| 岔路三：回退定义与落点 | 「只冻结契约与来源标注」(本轮只定义回退契约与来源标注口径（可复现、可追溯、标来源），不实现任何回退动作、不触及策略分派路径；回退明确不等于精确解、不等于已覆盖 CFR。) |

据此，**被授权**：在 `backend/app/strategy/` 新增抽象投影/覆盖判定模块（不改既有模块语义）、在 `backend/tests/` 新增回归测试、新增 `docs/40*`、以及在**最小必要**范围内改动 `backend/app/api/`。**被拒绝**（本轮不做）：`tools/trainer/**` 任何改动；任何回退动作实现或策略分派路径改动；lookup 运行时与性能基准（属 P0-2）。

### 1.3 四项裁定（冻结）

| 岔路 | 裁定 |
|---|---|
| 一 | 新增 `backend/app/strategy/abstraction.py` 作为**纯函数 + Pydantic 模型**入口；键字符串**逐字对齐**训练器 format，但由**后端本地常量**生成与校验，**不 import** 训练器任何代码，也不把训练器包加入后端依赖。 |
| 二 | 覆盖判定返回**显式状态判定对象**（Pydantic、冻结），`coverage` 取四值之一；抽象外与不完整信息集**各自独立取值**；对结构性非法输入（类型错误）与「要求抽象内但不在抽象内」分别抛**分类型明确异常**；不存在任何静默回退或最近桶近似路径。 |
| 三 | 本轮只冻结**回退契约与来源标注口径**，`FallbackDeclaration` 是**声明**而非动作；**不实现**任何回退动作、**不触及**策略分派路径（`games.py` / `registry` 分派语义零改动）。 |
| 四 | `tools/trainer/**` 保持**只读**：其 `information_set_key` 格式仅作为**规范出处**引用，代码中不读取、不导入、不执行其内容，本轮对其**零改动**。 |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 8]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -5 --oneline
8c6ca64 feat: add read-only multi-seed quality gate verdict without enabling a threshold
65cb4b2 docs: freeze p0-6 cfr quality gate definition without enabling a threshold
175b952 feat: declare teaching reference scope and limitations with a non-mode contract
b6a0bbd docs: freeze p0-7 teaching reference and opponent separation contract specs
89a5a15 feat: declare review reference and evaluation versions with a cache-key contract

$ git rev-parse HEAD          -> 8c6ca6464b02e52ed36b092401d17729ddc423fe
$ git rev-parse origin/master -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l
8

$ ls -1 backend/app/strategy/
__init__.py  heuristic.py  interface.py  projection.py  random_strategy.py  registry.py
```

与期望基线完全相符（`## master...origin/master [ahead 8]` 不多不少、工作区 0 行、`HEAD == 8c6ca64`、campaigns = 8、`strategy/` 无抽象映射/覆盖/回退模块）；未做任何 `reset` / `clean` / `stash` / `checkout` / `push`。

## 3. 现状事实与必然落差（只读核验）

### 3.1 后端现状

- `backend/app/strategy/` 只有注册表（P0-1）、投影（P0-4）、两种策略与接口；**没有**抽象键、覆盖判定或回退定义。
- `backend/app/poker/state.py` 的 `GameState`：`street` / `board` / `pot` / `current_seat` / `button` / `hand_over` / `players`；`PlayerState` 含 `hole_cards`（**全部座位**）、`stack` / `folded` / `all_in` / `street_bet` / `total_committed`。
- 因此 `GameState` **没有**完整公开行动历史，**没有**相对按钮/盲位的行动顺序投影，也**没有**抽象 rank；它**不能**直接作为信息集来源。这与 `docs/26` §2.1、`docs/20` §8.3、§11.3 的既有结论一致。
- `docs/26` §10 已给出受控抽象投影 `(game version, N, relative actor, own rank, canonical public history)` 与「抽象外 / 版本不匹配 / 不完整信息集必须明确失败；本轮不定义任何生产 fallback」的口径，但**尚未落地**。`docs/26` §14 明确把「抽象映射/覆盖/回退」列为**未授予**的工作。

### 3.2 训练器键格式（只读引用，零改动）

只读核对 `tools/trainer/src/multiplayer_cfr/game.py`（未修改、未导入）：

```text
GAME_ID      = "m8-unique-rank-single-open"
GAME_VERSION = "m8-a-v1"
ROOT_HISTORY = "-"
ALLOWED_PLAYER_COUNTS = {6, 7, 9}

information_set_key 实测格式：
m8/{GAME_VERSION}/n={player_count}/actor={actor}/rank={own_rank}/history={canonical_public_history}
```

其中公开历史使用带相对座位的 token（`x` / `b` / `c` / `f` + `@` + 相对座位号，以 `|` 连接；根历史为 `-`），并由 `derive_public_state` 唯一派生行动者、开池者、存活/弃牌集合、投入与待回应顺序。

### 3.3 真实 Hold'em 局面与受限抽象的落差（必须如实写明）

候选 A 的抽象是**单街道、单次开池、唯一 rank、无公共牌、固定下注 1、`ante = 1`、`bet = 1`、人数限 `{6,7,9}`** 的受限博弈。真实 Hold'em 局面具备相反特征：多街道、可变下注尺度、公共牌、多人池/边池、任意人数（引擎按 2–9 人设计）、真实牌面而非 0..N-1 的抽象 rank。

由此产生的**必然结论**（本轮必须如实记录，不得淡化）：

1. 真实 Hold'em 局面与候选 A 受限抽象**几乎必然不匹配**；一个真实局面对应的覆盖判定通常是 `incomplete-infoset` 或 `out-of-abstraction`，而**不是** `in-abstraction`。
2. 因此本轮交付**不**代表「真实局面已被覆盖」，更**不**代表「CFR 已支持生产局面」。
3. **不得**用「最近桶」「补零」「掩码」「线性插值」等手段把抽象外局面**冒充**为精确映射；本轮在结构上不提供这类路径。
4. 把真实行动线映射到抽象相对座位与规范历史，是 **P1-1** 的职责；真实下注尺度与公共牌属 **P1-4**。本轮**不**越界实现它们。

## 4. P0-3 规格（冻结）

### 4.1 受控抽象投影 `AbstractProjection`（字段齐备）

`AbstractProjection` 是**冻结的 Pydantic model**，字段恰好为下列五项（顺序即契约顺序）：

| # | 字段 | 类型 | 语义 |
|---|---|---|---|
| 1 | `game_version` | `str` | 抽象博弈版本；当前唯一受支持值为 `m8-a-v1` |
| 2 | `player_count` | `int` | `N`（抽象人数） |
| 3 | `relative_actor` | `int` | 相对行动者；抽象内相对座位 `0..N-1`，**不是**引擎绝对 seat、按钮或盲位 |
| 4 | `own_rank` | `int` | 行动者唯一私有 rank，`0..N-1` |
| 5 | `canonical_public_history` | `str` | 规范公开历史；根历史为 `-`，其余为 `action@relative-seat` 以 `|` 连接 |

`AbstractProjection` **不得**包含：其他座位暗牌、未发出公共牌、真实牌面、引擎绝对 seat、真实 stack、运行中 seed、对手内部参数、未来行动或结算结果。

### 4.2 抽象键格式（对齐但不依赖）

键由后端的受控构造入口生成，格式**逐字对齐**训练器：

```text
m8/{game_version}/n={player_count}/actor={relative_actor}/rank={own_rank}/history={canonical_public_history}
```

约束：

1. 前缀常量 `m8`、受支持版本常量 `m8-a-v1`、根历史常量 `-` 均为**后端本地冻结常量**；
2. 后端**不 import** 训练器任何模块，**不读取**其源码文件，也不把它加入依赖；「对齐」是**字符串格式契约**，不是代码依赖；
3. 历史必须先通过后端本地的**规范公开历史校验**（见 §4.3）才允许进入键；未通过校验的历史一律判为抽象外，**不**截断、**不**修补、**不**映射成最近合法历史；
4. 键**只**由以上五项构成；替换其他座位暗牌、未发出公共牌或未来结果**不得**改变键。

### 4.3 覆盖判定与四种取值

判定输入为「受控抽象投影的五项输入」；判定输出为**冻结的 Pydantic 判定对象**，其 `coverage` 取下列四值之一：

| `coverage` | 含义 | 触发条件 |
|---|---|---|
| `in-abstraction` | 落在训练抽象内 | 版本一致，且 `N ∈ {6,7,9}`，且 `relative_actor` / `own_rank` 在 `0..N-1`，且历史是候选 A 的**规范公开决策历史** |
| `out-of-abstraction` | 结构上合法但不在抽象内 | 版本一致，但 `N ∉ {6,7,9}`；或历史不是候选 A 的规范公开决策历史；或 `relative_actor` / `own_rank` 越界 |
| `incomplete-infoset` | **信息不完整**，无法构造完整信息集键 | 任一必需字段**缺失**（未提供）：`game_version` / `player_count` / `relative_actor` / `own_rank` / `canonical_public_history` 任一为缺省 |
| `version-mismatch` | **版本不匹配** | 提供了版本，但 `game_version != m8-a-v1`（未知版本或历史版本均属此类） |

区分口径（**不得混淆**）：

- `incomplete-infoset` 是「**输入缺项**」：调用方拿不出构造键所需的全部信息（典型情形：只有 `GameState`，而它没有公开行动历史、没有相对行动者、真实牌面也不是抽象 rank）；
- `out-of-abstraction` 是「**输入齐备但落在抽象之外**」：字段齐全、类型合法，只是不在训练覆盖范围内；
- 两者是**不同的独立取值**，不得合并为同一个「不覆盖」状态；`version-mismatch` 亦独立。

判定对象同时携带：规范键（仅 `in-abstraction` 时有值，其余取值为空）、抽象投影（仅构造成功时有值）与**判定原因列表**（逐项说明缺什么 / 越界在哪），使判定**可追溯**。

**没有**「最近桶」「默认桶」「近似命中」等取值：抽象外一律**不产生键**。

### 4.4 明确失败语义

1. `build_abstraction_key(...)`：仅接受**已判定为 `in-abstraction`** 的输入；其余情形抛分类型异常，**不**返回近似键。
2. `require_in_abstraction(verdict)`：把判定结果转为**明确失败**——`out-of-abstraction` / `version-mismatch` / `incomplete-infoset` 各自抛独立的异常类型，便于调用方区分处置。
3. `AbstractProjection` 的构造对**结构性非法输入**（类型错误、非字符串历史、布尔值冒充整数等）抛 `AbstractionContractError`；这是**契约违规**，与「抽象外」是两回事。
4. **禁止静默回退**：任何未知、缺失或越界的输入都不得被当作抽象内处理，也不得回落到默认策略后仍声称「抽象内」。

### 4.5 回退契约与来源标注（只声明，不动作）

`FallbackDeclaration` 是**冻结的 Pydantic model**，字段：

| 字段 | 语义 |
|---|---|
| `fallback_identifier` | 回退来源的**受控策略标识**；必须是 P0-1 注册表（`registry.known_identifiers()`）内的规范标识，**复用 P0-1，不另起命名体系** |
| `triggering_coverage` | 触发回退的覆盖取值（三选一，`in-abstraction` 不产生回退） |
| `abstraction_key` | 触发时所用的抽象键（仅抽象内之外可空）；使回退**可追溯** |
| `reasons` | 触发原因列表（与判定对象一致），使回退**可复现** |
| `source` | 来源标注常量（本轮固定为「契约声明」），表明回退**来源可标注** |
| `is_exact_solution` | 恒为 `False`，且**不接受**设为 `True`；明确回退**不是精确解** |

约束：

1. **本轮不实现任何回退动作**：`FallbackDeclaration` 只表达「如果在未覆盖场景按契约回退，来源是谁、如何标注、如何复现」；
2. **不触及策略分派路径**：`registry` / `games.py` / API 的策略选择语义**零改动**；本轮没有新增运行时可用的回退行为；
3. 默认声明来源常量指向注册表内既有的 `heuristic@1`（当前生产对手与教学基线）；该常量是**契约默认**，不是新增策略、也不改变任何既有策略语义；
4. 回退**不得**被表述为「已覆盖」「已支持 CFR」或「精确解」；`docs/20` §11.3「未覆盖上下文应明确回退，不能只为了不中断牌局就标记为 CFR 已支持」在本轮以**声明**形式落实，动作留给后续单独授权。

### 4.6 信息边界复用（P0-4）与不读对手暗牌 / 未来牌

1. 从**生产快照**出发的判定入口，必须先把快照交给 **P0-4** 的 `project_for_actor`，只从投影结果读取行动者本人信息；本模块**不重造**第二套脱敏逻辑。
2. 本模块**不读取**、也不在键或判定对象中出现：其他座位暗牌、未发出/未来公共牌、运行中 master seed、对手内部参数、结算结果。
3. 键与判定对象的字段集合在结构上**不包含**上述任何一项（见 §4.1、§4.5 的字段表）。

### 4.7 与 P1-1 / P1-4 的职责边界

本轮 P0-3 只交付「**键投影 + 覆盖判定 + 回退声明**」这一层契约；下列**不在**本轮范围：

| 职责 | 归属 | 本轮处置 |
|---|---|---|
| 把真实行动线映射到相对座位与规范公开历史（位置/行动顺序投影） | P1-1 | **不实现**；从生产快照出发的判定对缺失项**如实**给出 `incomplete-infoset` |
| 真实下注尺度、公共牌、多人池/边池 | P1-4 | **不实现**；抽象外如实给出 `out-of-abstraction` |
| lookup 运行时、产物加载、性能与内存基准 | P0-2 | **不实现**；本轮无任何 lookup 路径 |

### 4.8 P0-3 验收口径

对照 `docs/35` §4.2 P0-3 原文口径（受控抽象投影字段齐备；抽象外/版本不匹配/不完整信息集明确失败；回退可复现、可追溯且标注来源，不得用最近桶冒充精确）：

| # | 验收项 | 判据 |
|---|---|---|
| C1 | 抽象投影字段齐备 | `AbstractProjection` 字段集**恰好**为 §4.1 五项；多一项或漏一项即失败 |
| C2 | 抽象外明确失败 | `N ∉ {6,7,9}` 或历史非候选 A 规范历史 → `out-of-abstraction`，且不产生键 |
| C3 | 版本不匹配明确失败 | `game_version != m8-a-v1` → `version-mismatch` |
| C4 | 不完整信息集明确失败 | 任一必需字段缺失 → `incomplete-infoset`，且与 `out-of-abstraction` 取值**不同** |
| C5 | 回退可追溯且带来源标注 | `FallbackDeclaration` 的来源标识**在注册表内**，携带触发取值、键与原因；`is_exact_solution` 恒 `False` |
| C6 | 不读取对手暗牌与未来牌 | 替换其他座位暗牌 / 未公开公共牌不改变判定与键；键与判定对象字段中不存在相关字段 |
| C7 | 2–9 人参数化，不写死两人 | 判定按 `N` 参数化；仅 `{6,7,9}` 可判为 `in-abstraction`，其余人数为 `out-of-abstraction` |
| C8 | 键格式对齐 | 生成键逐字等于 §4.2 格式（含前缀、版本、`-` 根历史） |
| C9 | 无最近桶近似 | 抽象外不返回键；`build_abstraction_key` 对抽象外输入抛明确异常 |

## 5. 版本影响与兼容性（预期）

| 对象 | 影响 |
|---|---|
| 既有策略语义 | **零改动**：`heuristic.py` / `random_strategy.py` / `interface.py` / `projection.py` / `registry.py` 语义不变 |
| 策略分派 | **零改动**：注册表与 `games.py` 的分派路径不受影响；本轮**不新增**运行时回退行为 |
| API 与前端 | 除非最小必要，不做改动；不改任何请求/响应字段；**不恢复**已移除的前端策略选择器 |
| 数据库 | **不加列、不迁移**；`storage/models.py` 零改动；真实数据库只读 |
| 旧历史 | 原样保留；`history_json` 不被改写；旧响应结构不变 |
| 引擎 / 结算 | 零改动；`equity` / `estimate_static_showdown_share` / `pot_projection` / `_settle_showdown` 语义不变 |
| 锁文件 | `backend/uv.lock` 与 `frontend/package-lock.json` 零改动（不新增依赖） |
| 抽象外局面的实际处置 | **不产生键、不产生动作**；判定为 `out-of-abstraction` / `incomplete-infoset` / `version-mismatch`，并可由调用方请求**声明式**回退来源标注 |

## 6. 边界声明与不得声称

- 本轮改动是**契约与失败语义**，**不是** CFR 接入，也**不构成任何质量证据**；`backend/app/strategy/` 仍无任何 CFR lookup 或产物加载。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、best response、真实 EV 或生产可用策略。
- **不得**把回退路径表述为「已覆盖」「已支持 CFR」或「精确解」；回退只是**声明的来源标注**。
- 真实局面与受限抽象的落差已在 §3.3 如实写明；**不得**用「最近桶」「补零」「掩码」「插值」冒充精确映射。
- 稳定性结论若出现，必须标注为「事后跨工件只读比较」（代码中没有稳定性生产者）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 本轮不追加 seed、不新建冻结 campaign、不重试任何已消耗 authorization、不上云、不转 GPU、不扩预算。
- 不得修改 `backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/storage/models.py`、真实数据库 `backend/data/holdem.db`、锁文件、`tools/trainer/**`、`docs/20` 至 `docs/39a`。

## 7. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码/测试/前端/锁文件/真实数据库；未实施 P0-3 的实现；未实施清单其余任何一项；未改质量门槛或启用 `docs/39` 门槛；未新增受监督运行或 campaign；未追加 seed；未重试 authorization；未 push。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P0-3，并在实施回执（`docs/40a`）中给出文件级改动、新增/修改测试与 `ruff` / `pytest` / `npm run build` 的实跑输出。** 若用户对 §1.3 的任一项裁定有不同意见，应在实施前先修订本文件并记录原因。

P0-3 完成之后的下一个清单项是 **P0-2（实时 lookup 性能与内存预算）**；它需要 P0-3 的覆盖与回退定义才具备可比口径，须**单独授权**；并注意 `<100ms` 是**实时 Bot 决策**预算，不是整手复盘预算。
