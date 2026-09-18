# 36 M8：生产接入前置——P0-1 策略标识与受控注册表、P0-4 信息边界与对外投影（规格冻结）

> 日期：2026-09-18。
>
> 本文件接在 `docs/35` / `docs/35a` 之后，沿用 `docs/30` D6 的编号族约定：`docs/36` 记录本轮**规格与决策冻结**，`docs/36a` 记录与之对应的**实施与验证回执**（同一编号族内可多次提交）。`docs/20` 至 `docs/35a` 未被改写。
>
> 本文**不实施任何代码**：只完成两项清单项的规格冻结与设计岔路裁定。代码与测试在随后一次提交中落地，回执见 `docs/36a`。
>
> **本文件不产生任何策略、质量或资源证据**；未新建冻结 campaign、未追加 seed、未重试任何已消耗 authorization、未做任何云端操作。

## 1. 授权范围与设计岔路裁定

### 1.1 本轮授权（仅两项）

本轮用户明确授权的实施范围**只有两项**，均来自 `docs/35` §4.2 的 P0 组：

| 编号 | 前置项 | 本轮是否授权 |
|---|---|---|
| P0-1 | 策略标识与受控注册表 | **是** |
| P0-4 | 信息边界与对外投影 | **是** |
| P0-2 / P0-3 / P0-5 / P0-6 / P0-7 | lookup 性能、抽象映射与回退、评估版本化、质量门槛、参考契约 | 否 |
| P1-1 … P1-5 | 位置与公开行动历史投影、范围模型、逐池 EV、真实尺度、性能复测 | 否 |
| P2-1 … P2-4 | 2–9 人产品验收、N=9 结论、历史 `pot_results`、稳定性生产者 | 否 |

P0-1 与 P0-4 **只是** `docs/35` §4.2 清单中的两项；本文件不改变 `docs/35` §4 中其余条目的现状、优先级或失效条件，也不构成任何实施授权。

### 1.2 三项设计岔路的裁定方式

接手约束要求在写代码前先裁定三个设计岔路，并允许二选一：**先问用户**，或**先在文档冻结规格**。本轮采用**后者**：由本轮在本文档内冻结规格，并在 `docs/36a` 如实标注该裁定方式。

理由与边界：

1. 三项分歧在 `docs/20` §8.4 与 `docs/35` §4.2 中**已有明确依据**（见下表“依据”列），本轮裁定只是把既有约定落成可验证规格，**不引入新的产品决策**；
2. 本文件冻结的是**可被用户修订的规格**：若用户对任一项有不同意见，应按 `docs/35` §4.1 第 5 条“修订本清单并记录原因”的规则处理，**不得静默修改**；
3. **本节不冒充用户答复**：本文不把代理裁定表述为“用户已确认”。

### 1.3 三项裁定（冻结）

| 岔路 | 问题 | 裁定 | 依据 |
|---|---|---|---|
| 岔路一 | 策略标识的表示形式：扩展现有 `Literal` 还是引入带版本的受控注册表？旧值如何兼容？ | **受控注册表 + 版本化标识**。规范标识形如 `name@version`（如 `heuristic@1`）；旧请求值 `heuristic` / `random` 通过**固定别名表**映射到各自的**历史版本**，别名**不随新版本自动前移**。不扩展现有 `Literal` 枚举。 | `docs/20` §8.3「策略工厂用受控注册表」、§8.4「不能只把 runtime 改了，留下 schema/工厂不认识的新名；也不能把新行为偷偷标成旧 heuristic」 |
| 岔路二 | 数据库策略：是否必须避免新增列/迁移？ | **不新增列、不做迁移**。继续使用既有 `sessions.bot_strategy`（`String(32)`），改存版本化标识字符串；旧行原样保留。新策略**不**靠加列区分。 | `docs/20` §8.4「建议避免首轮数据库迁移」「现有 `create_all` 不会给旧表自动补列」 |
| 岔路三 | 前端是否重新暴露策略选择器？ | **不暴露**。前端不传 `bot_strategy`，UI 不出现策略选择器；本轮**不改动**前端。 | `docs/20` §8.4「UI 不必恢复已移除的策略选择器」；`docs/35` §4.2 P0-1 验收「不恢复已移除的前端策略选择器」 |

`HandDetail.history` 的白名单投影字段集与版本化方式同样在本轮冻结（见 §4.2、§4.3）：**顶层版本字段 + 固定白名单键集**，未知版本按 `unknown` 读取。

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -4 --oneline
ef7e592 docs: record decision addendum and opponent-upgrade preregistration
f9d14d5 docs: record candidate-a closeout decision and production readiness checklist
f055a3c docs: record n6 cross-seed receipts and the seed-dependent verdict reversal
eda4f9c docs: freeze n6 cross-seed campaign and record budget posture change

$ git rev-parse HEAD          -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f
$ git rev-parse origin/master -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f
```

与期望基线完全相符（`## master...origin/master` 不多不少、工作区 0 行、`HEAD == origin/master == ef7e592`）；未做任何 `reset` / `clean` / `stash` / `checkout`。

与本轮两项直接相关的只读事实核对（不构成实验证据）：

```text
backend/app/api/schemas.py:21    bot_strategy: Literal["heuristic", "random"] = "heuristic"
backend/app/storage/models.py:38 bot_strategy: Mapped[str] = mapped_column(String(32), ..., default="heuristic")
backend/app/api/games.py:55-58   _make_bot: strategy_name == "random" ? RandomStrategy : HeuristicStrategy
backend/app/strategy/__init__.py 只导出 Strategy / hero / RandomStrategy / HeuristicStrategy
backend/app/api/schemas.py:153   class HandDetail: history: dict   # 裸 dict，无版本字段、无白名单投影
backend/app/api/hands.py:55      history=json.loads(hand.history_json)  # 直接回传，无裁剪
backend/app/poker/engine.py:74   snapshot() 保留全部玩家 hole_cards（含对手暗牌）
backend/app/poker/engine.py:40   PokerEngine._rng 持有 master seed（仅进程内，未对外序列化）
backend/app/storage/models.py   无评估/参考版本列
backend/app/strategy/           仅 heuristic.py / random_strategy.py / interface.py
frontend/src/components/GameTable.vue:230-234  createGame 只提交 num_players/big_blind/starting_stack
```

两处既有修复仍在位且未被本轮触碰：`tools/trainer/src/multiplayer_cfr/experiment_record.py` 与 `measurement.py` 的 `MAX_RATIONAL_DIGITS = 4_096` 不变；本文件不涉及 `tools/trainer/`。

## 3. P0-1 规格（冻结）：策略标识与受控注册表

### 3.1 标识格式与规范形

1. 规范标识形如 **`<name>@<version>`**：`name` 为小写字母/数字/连字符，`version` 为正整数（如 `heuristic@1`、`random@1`）。
2. **规范标识是唯一权威形态**：进入运行时的策略一律以规范标识命名；`sessions.bot_strategy` 与手牌历史中的策略快照一律记录规范标识。
3. 标识字符串总长度不超过既有列宽 `String(32)`；本轮不存在超宽标识。

### 3.2 受控注册表

新增 `backend/app/strategy/registry.py`，作为策略选择的**唯一入口**：

| 能力 | 语义 |
|---|---|
| `StrategySpec` | 不可变记录：`identifier`（规范标识）、`name`、`version`、`factory(seed) -> Strategy`、`description` |
| `register_strategy(spec, aliases=())` | 注册一个策略；`identifier` 重复即报错；`aliases` 重复即报错（见 §3.3） |
| `resolve_identifier(value) -> str` | 把客户端提交值规范化为注册表中的规范标识；未知标识抛 `UnknownStrategyError` |
| `spec_for(value) -> StrategySpec` | 取注册项（含版本与描述） |
| `create_strategy(value, seed=None) -> Strategy` | 按标识构造策略实例 |
| `known_identifiers() -> tuple[str, ...]` | 供诊断与测试枚举 |

**受控性要求**：注册表只做**精确字符串查表**。客户端提交的类名（如 `HeuristicStrategy`）、模块路径（如 `app.strategy.heuristic.HeuristicStrategy`）、属性链（如 `os.system`）或任何未注册标识都**必须失败**，不得被解析、导入或执行。

内置注册项（本轮）：

| 规范标识 | 工厂 | 说明 |
|---|---|---|
| `heuristic@1` | `HeuristicStrategy(seed=seed)` | 当前生产对手，同时是教学参考基线（`docs/35a` D4 = A） |
| `random@1` | `RandomStrategy(seed=seed)` | 均匀随机基线 |

### 3.3 旧请求值兼容（别名冻结）

1. 固定别名表：`heuristic -> heuristic@1`、`random -> random@1`。
2. **别名不随新版本前移**：将来注册 `heuristic@2`（例如模拟对手升级切片）时，旧值 `heuristic` 仍解析为 `heuristic@1`；把新行为接管旧名称属**禁止项**。该约束由“别名重复注册即报错”的机制保证。
3. 兼容范围仅限既有两个值；不新增任何未注册的旧值。

### 3.4 客户端输入校验

1. `CreateGameRequest.bot_strategy` 的类型由 `Literal["heuristic", "random"]` 改为字符串，并在 Pydantic 校验阶段调用 `resolve_identifier`：
   - 合法（含旧值）→ 字段被**规范化**为规范标识后继续；
   - 未知 → 校验失败，HTTP `422`（明确失败，不静默回退到 `heuristic`）。
2. **禁止静默回退**：任何未知/非法标识都不得被当作 `heuristic` 处理；这正是“新策略不得被偷偷标成旧 `heuristic`”的反向要求（旧名也不得吞掉新值）。
3. `games.py::_make_bot` 改为经注册表构造，删除 `== "random"` 的硬编码分派。

### 3.5 持久化

1. `sessions.bot_strategy` **保持既有列**（`String(32)`），改存规范标识；**不新增列、不做迁移**。
2. `GameRuntime` 记录本局使用的规范标识，并在每手落库的 `history_json` 中写入 `bot_strategy` 快照（见 §4.3），使“实际跑的是哪个策略”可追溯。
3. **不得**把人格/配置 JSON 拼接进 `sessions.bot_strategy` 字符串。

### 3.6 P0-1 验收口径

| # | 验收项 | 判据 |
|---|---|---|
| A1 | 未知标识明确失败 | 创建对局提交未注册标识（含类名/模块路径）返回 `422` |
| A2 | 旧请求不破坏 | 提交 `heuristic` / `random` 仍成功，且落库为 `heuristic@1` / `random@1` |
| A3 | 不恢复前端选择器 | `frontend/` 不被本轮改动；创建请求仍只提交人数/盲注/起始筹码 |
| A4 | 版本可追溯 | 新落库历史的 `bot_strategy` 为规范标识；无标识的旧历史按 `unknown`（见 §4.4） |
| A5 | 不偷偷改写语义 | `HeuristicStrategy` 的决策语义与参考分布**零改动**（仅被注册表引用） |

## 4. P0-4 规格（冻结）：信息边界与对外投影

### 4.1 受控 GameState 投影

新增 `backend/app/strategy/projection.py`，提供**唯一**的策略视角入口 `project_for_actor(state) -> GameState`：

1. 保留：`street`、`board`（当前已发出的公共牌）、`pot`、`current_seat`、`button`、`hand_over`；
2. 每个座位保留：`seat`、`name`、`stack`、`folded`、`all_in`、`street_bet`、`total_committed`；
3. **仅行动者本人**保留 `hole_cards`；**其他座位 `hole_cards` 一律置空**；
4. 投影后的对象仍是 `GameState`，不含 seed、不含牌堆、不含未发出的公共牌、不含对手内部参数；
5. `games.py` 在调用 Bot 时传入投影结果，使策略生产路径**结构上**不可能读到对手暗牌。

既有 `HeuristicStrategy` 与 `RandomStrategy` 的决策分支均不消费对手暗牌（仅消费本人底牌、公共牌、`pot`、公开的 `folded/all_in` 状态）；因此本投影**不改变**既有决策语义与参考分布。

### 4.2 历史 JSON 版本化与白名单投影

在 `backend/app/storage/hand_history.py` 内：

1. 定义版本常量 `HAND_HISTORY_SCHEMA_VERSION = "hand-history.v1"` 与 `UNKNOWN_VERSION = "unknown"`；
2. `build_hand_history(...)` 产出增加顶层 `schema_version` 与 `bot_strategy`（其余字段与取值口径**不变**，仍为 source of truth）；
3. 新增 `project_hand_history(raw: dict) -> dict`：按**固定白名单**裁剪，未在名单内的键（含将来可能出现的敏感键，如 `master_seed`）**一律丢弃**；
4. `api/hands.py` 的 `HandDetail` 与手牌摘要改经 `project_hand_history` 输出；**原始 `history_json` 不被改写**；
5. 复盘接口仍在服务端读取原始历史做确定性重放（分析层需要完整事实）；其对外响应继续由 Pydantic 模型约束，不含对手暗牌。

### 4.3 v1 白名单键集（冻结）

```text
schema_version, bot_strategy,
hand_number, num_players, small_blind, big_blind, button, board,
players, actions, street, showdown, winners, net,
showdown_hands, pot_results
```

该集合覆盖当前前端历史视图与摘要接口的全部消费字段；**新增字段必须同时更新本清单并配套测试**，不得静默扩表。

### 4.4 旧数据与未知版本

1. 缺少 `schema_version` 或 `bot_strategy` 的历史，投影输出对应字段为 `unknown`；
2. **不得**把未知版本补成当前版本（不假设旧数据等价于 `hand-history.v1`）；
3. 旧数据的其余已知键仍按白名单原样透出，保证历史视图与摘要继续可用。

### 4.5 运行中 seed 不外发

1. API 响应（对局视图、手牌详情、摘要、复盘）**任何层级都不得出现** master seed、牌堆状态或随机源对象；
2. `project_for_actor` 与 `project_hand_history` 的结果均不含 seed；`PokerEngine._rng` 仅存进程内，不进入任何对外模型。

### 4.6 P0-4 验收口径

| # | 验收项 | 判据 |
|---|---|---|
| B1 | 隐藏底牌不改变策略分布 | 仅替换其他座位底牌 / 未公开公共牌后，投影后的 `GameState` 相等，且同 seed 下 `HeuristicStrategy.action_distribution` **逐项相等** |
| B2 | 运行中 seed 不外发 | 对局视图与手牌详情的 JSON 中递归不存在 `seed` / `_rng` 等键 |
| B3 | 旧数据按 unknown 读取 | 无版本字段的旧历史，投影 `schema_version == "unknown"` 且 `bot_strategy == "unknown"` |
| B4 | 白名单确实裁剪 | 人为注入未登记敏感键的历史，投影后该键不存在 |
| B5 | 历史未被改写 | 投影只作用于响应；`hands.history_json` 原样保留 |

## 5. 版本影响与兼容性（预期）

| 对象 | 影响 |
|---|---|
| 旧请求 | `heuristic` / `random` 继续可用；请求体被规范化为 `heuristic@1` / `random@1`，语义不变 |
| 旧对局行 | `sessions.bot_strategy` 旧值原样保留，不迁移、不回填；不读取该列做行为判断 |
| 旧历史 | 无版本字段 → 按 `unknown` 读取；白名单内的已知键原样透出；原始 JSON 不被改写 |
| 前端 | 无改动（不发送策略字段、不恢复选择器）；历史视图消费的字段集不变 |
| 引擎 / 结算 | 零改动；`equity` / `estimate_static_showdown_share` / `pot_projection` / `_settle_showdown` 语义不变 |
| 参考基线 | `HeuristicStrategy` 语义与 `heuristic-conservative` 参考口径不变（`docs/35a` D4 = A） |

## 6. 边界声明与不得声称

- 本轮**不**接入 CFR，`backend/app/strategy/` 仍无任何 CFR lookup 或产物加载；本文件不构成 `docs/35` §4 中 P0-2 / P0-3 的任何进展。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 若涉及稳定性/对照，必须标注为“事后跨工件只读比较”——本轮不存在任何稳定性生产者，也**不产生**该类结论。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 本轮不追加 seed、不新建冻结 campaign、不重试任何已消耗 authorization、不上云、不转 GPU、不扩预算。
- 不得修改 `tools/trainer/src/kuhn_cfr/` 及其测试、`tools/trainer/` 其它部分、锁文件与真实数据库 `backend/data/holdem.db`。

## 7. 未做事项与下一步唯一建议动作

本轮（规格冻结）未做：未改任何代码/测试/前端/锁文件/真实数据库；未实施 P0-1 与 P0-4 的实现；未实施清单其余任何一项；未新建 campaign、未追加 seed、未重试 authorization；未做云端操作。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**按本文冻结的规格实施 P0-1 与 P0-4，并在实施回执（`docs/36a`）中给出文件级改动、新增/修改测试与 `ruff` / `pytest` / `npm run build` 的实跑输出。** 若用户对 §1.3 的任一项裁定有不同意见，应在实施前先修订本文件并记录原因。
