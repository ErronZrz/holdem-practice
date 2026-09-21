# 53a M8：完整 Bot 对手首期实施与常规回归回执

> 日期：2026-09-21。
>
> 本文件是 `docs/53` 的**实施与验证回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/53` 未被改写；`docs/53` 的冻结规格未做任何修订。
>
> 本文件记录已落地的代码、新增回归与一次常规检查实跑。**不产生任何策略、质量或资源证据**：未运行任何成本矩阵或对抗对局、未切换新建默认策略、未消耗任何 authorization、未新建 campaign、未追加 seed、未改写任何封存工件。
>
> 提交说明：本记录起草于实施授权之下，该授权本身**不含**提交与推送；用户随后就本轮实现**另行单独授权** `commit` + `push`，实际执行的提交全哈希与推送结果在交付消息中实报，本文件不自引用哈希。

## 1. 本轮授权原文与边界

用户答复原文：

> 授权完整实施(新增 mixed_context/mixed_features/mixed_policy/mixed_strategy 与对应测试，改 registry/__init__/games.py 接线，跑 ruff + pytest + build；默认仍 heuristic@1，不实跑 §11 实验、不改 schemas 默认、不 commit/push)

| 项 | 内容 |
|---|---|
| 被授权 | 按 `docs/53` §12.1 清单实现首期新 Bot 与其回归；运行 `ruff` / `pytest` / `npm run build` 三项常规检查 |
| 未被授权（该次实施授权范围内） | `docs/53` §11 的任何实跑（成本矩阵、分布矩阵、对抗对照、阶段 A/B）；新建默认策略切换；`backend/app/api/schemas.py` 默认值改动；`docs/53` 规格修改；`commit` / `push`；前端改动；训练器改动；任何预算或云端操作 |
| 随后单独授权 | 本轮实现的 `commit` + `push`（另一次明确的对话授权；不含 `docs/53` §11 实跑、不含默认切换） |

## 2. 实施前基线核验（只读）

```text
$ git status --short --branch
## master...origin/master
$ git status --porcelain=v1 --untracked-files=all | wc -l
0
$ git rev-parse HEAD
f7cd98a23d3a3b6aa06d3d11d4936162fcdbf621
$ git rev-parse origin/master
f7cd98a23d3a3b6aa06d3d11d4936162fcdbf621
$ ls -1 backend/app/strategy/*.py | wc -l        # 14
$ ls -1 backend/tests/test_*.py | wc -l          # 28
$ ls -1 docs/ | wc -l                            # 80
```

与 `docs/53` 交接基线逐项一致；工作区 0 行、无暂存改动；未做任何 `reset` / `clean` / `stash` / `checkout` / `rebase` / `push`。

## 3. 实际改动（文件级）

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/mixed_context.py`（**新增**，428 行） | `MixedContext` / `MixedStreetSummary`（`frozen=True, extra="forbid"`）、`MixedGameState`（`GameState` 的冻结子类，唯一新增属性 `context`）、`MixedSummaryTracker`（四街固定数组的增量维护）、`require_mixed_input`（输入一致性与信息边界校验）、`mixed_state`。不持有引擎、不做牌力判断 |
| `backend/app/strategy/mixed_features.py`（**新增**，434 行） | 翻前/翻后基础分、听牌补牌、位置、牌面风险、价格与有效投入；只读复用 `evaluate_fast` 与 `project_candidate_call` |
| `backend/app/strategy/mixed_policy.py`（**新增**，354 行） | 三种风格参数表、三种手模式分区、整数尺寸候选生成与合并、危险尺度保护、百万单位联合分布 `MixedDistribution` 与抽样 |
| `backend/app/strategy/mixed_strategy.py`（**新增**，211 行） | 主键与域分离派生（`derive_root_key` / `derive_deck_seed` / `derive_bots_key`）、座位分派器 `MixedLocalStrategy`、无状态子策略 `MixedSeatPolicy` |
| `backend/app/strategy/registry.py`（修改，+11 行） | 新增 `mixed-local@1` 注册项；**不设**无版本别名；旧条目、别名、工厂不变 |
| `backend/app/strategy/__init__.py`（修改，+80 行） | 导出新模块公开符号；既有导出与顺序语义不变 |
| `backend/app/api/games.py`（修改，+113 / −17 行） | 仅新策略分支：`derive_root_key` → `derive_deck_seed` / `MixedLocalStrategy(root_key=...)`、逐手公开摘要的生命周期接线、行动成功后的增量消费、固定措辞的失败转换；旧策略路径语义不变 |
| `backend/tests/mixed_bot_states.py`（**新增**，332 行） | 16 类节点、2–9 人适用性矩阵、计划槽遍历、逐张牌清单 schema（`MixedNodeFixture` / `MixedFixtureManifest`）与确定性回放入口 `apply_node` |
| `backend/tests/mixed_bot_validation.py`（**新增**，983 行） | `mixed-validation.v1` 报告模型、计时口径、成本矩阵与补充矩阵、对抗对照排期与探针、阶段门禁与 opt-in 入口 |
| `backend/tests/test_mixed_context.py`（**新增**，400 行） | 39 条常驻回归 |
| `backend/tests/test_mixed_policy.py`（**新增**，371 行） | 26 条常驻回归 |
| `backend/tests/test_mixed_strategy.py`（**新增**，246 行） | 17 条常驻回归 |
| `backend/tests/test_mixed_games.py`（**新增**，250 行） | 20 条常驻回归 |
| `backend/tests/test_mixed_bot_benchmark.py`（**新增**，265 行） | 15 条常驻设计/门禁回归 + 1 条默认跳过的显式 opt-in 入口 |
| `backend/tests/test_strategy_registry.py`（修改，+37 / −1 行） | 新增新身份与工厂断言、两个应被拒的无版本/错版本标识；既有断言改为在集合包含关系中追加新标识，**未删除或放宽任何既有断言** |
| `docs/53a-…md`（本文件） | 实施与验证回执 |

**未改动**（`git status` 可证）：`backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/storage/**`、`backend/app/api/schemas.py` 及其余 API 模块、`backend/app/strategy/interface.py`、`heuristic.py`、`random_strategy.py`、`projection.py`、`lookup_budget.py`、`abstraction.py`、`artifact.py`、`position_projection.py`、`range_assumption.py`、`pot_ev_contract.py`、`real_rules_boundary.py`、`decision_latency.py`、`frontend/**`、`tools/trainer/**`、`backend/uv.lock`、`frontend/package-lock.json`、真实数据库 `backend/data/holdem.db`（mtime 仍为 2026-09-18）、`docs/20` 至 `docs/53`。

实施过程中的一次性联调脚本置于工作树之外并已删除；未在仓库留下任何临时文件。

## 4. 与冻结规格的对应

| `docs/53` | 落点 |
|---|---|
| §9.1 身份与兼容分派 | `registry.py` 的 `mixed-local@1`（无别名）；`MixedLocalStrategy` 仅为座位分派器，座位升序循环分配 `tight / aggressive / calling`；`GameRuntime.bot` 保留，旧策略仍走原单实例路径 |
| §9.2 安全上下文与 `GameState` 关系 | `MixedGameState` / `MixedContext` / `require_mixed_input`；先 `project_for_actor` 再附加摘要 |
| §9.3 摘要维护与原子性 | `MixedSummaryTracker`：`begin_hand` 消费恰好两条盲注，`consume_after_action` 消费恰好一条；`games.py` 中先校验求值、再 apply、最后消费 |
| §9.4 随机源与可重放范围 | `derive_root_key`（显式 seed 的十进制字符串 → SHA-256；`None` 时取一次 32 字节系统熵）、HMAC-SHA256 + 紧凑 JSON 消息、`deck` / `bots` / `seat` / `hand…mode` / `hand…action` 五级派生；主种子只在 API/工厂边界 |
| §10.1 计算路线 | 不调用 `HeuristicStrategy`，不新增 Monte Carlo；每次决策至多两次 `evaluate_fast` |
| §10.2 特征定义 | `mixed_features.py` 的全部公式与阈值 |
| §10.3 人格/模式与被动权重 | `STYLE_PARAMETERS`、`HAND_MODE_ROLL_BOUNDS`、`Tc` / `Tv` / 质量与倍率 |
| §10.4 尺度生成、风险排除与量化 | `_active_candidates` 与 `_quantize`；危险尺度恒禁用非价值质量 |
| §10.5 工作量与失败策略 | 固定扫描上界；失败在 apply 之前抛出，不静默回退 |
| §11.1–11.7 评测设计 | `mixed_bot_states.py` 的节点/适用性；`mixed_bot_validation.py` 的矩阵、报告 schema 与门禁 |
| §12.1 建议允许文件清单 | 与本文件 §3 逐条对应，未超出清单 |

未发现冻结规格的矛盾或不可实现点，因此没有提出裁定事项，也没有改动任何公式、测试口径或验收口径。

## 5. 新增回归锁定的契约

| 测试文件 | 锁定的契约 |
|---|---|
| `test_mixed_context.py` | 摘要模型闭集与冻结；跨字段一致性；摘要逐项失败（未知动作、负额、非可行动街、动作数与游标不匹配、被动动作带金额）；盲注只计入支付；加注前跟注者集合；计数饱和与支付累加；缺上下文 / 终局 / 已弃牌 / 公共牌数不符 / 对手底牌泄漏 / 支付与快照不一致 / 已知牌重复的显式失败；真实整手的摘要与引擎投入逐座位一致 |
| `test_mixed_policy.py` | 三种风格参数表逐项冻结；`[0,100)` 三模式分区与越界失败；开池名义目标；`ceil(P/3)` / `ceil(3P/4)` / `ceil(5P/4)` 目标；夹紧与偏好合并；主动总质量不随候选数增长；全下只在可完整匹配时生成；无 live 对手不生成主动候选；危险尺度在无价值时删除、保留时禁用非价值质量；自相矛盾合法动作失败；零质量显式失败；抽样可复现且不抽零单位项；同节点风格差异；候选顺序与金额规范 |
| `test_mixed_strategy.py` | 标识版本化；根键确定性与 seed 依赖；牌堆种子非负且与 Bot 键分离；跨实例重放；根键注入与 seed 等价；分布查询不消耗行动随机流；座位风格循环；座位集合变更被拒；未知座位被拒；未附加上下文 / 泄漏快照被拒；每手模式稳定；座位派生键互不相同；行动线推进只改变事件标识 |
| `test_mixed_games.py` | 请求默认仍为 `heuristic@1`；旧策略会话 `summary` 为 `None`；显式新策略可选中且不泄露种子与对手底牌；`mixed-local` 无版本标识 422；2–9 人会话均可完成；历史记录新策略身份且复盘仍用独立保守参考；跨手摘要重置；非法真人动作不污染摘要；同 seed 重放同一行动线；摊牌前不泄露对手底牌 |
| `test_mixed_bot_benchmark.py` | 计划槽 128（125 可行动 + 3 结构性不适用）；36 格与 278/277 配额合计 10000；补充 240 次；对抗 4224 手与 256 动作上限；阶段 A 排期 64 手且固定单一 seed / 单一风格 / 单一轮换；两 arm 使用同一牌堆派生流；缺清单 / 缺允许阶段 / 缺机械明细 / 阶段 B 缺前置回执均被拒；输出目录不得覆盖；节点拒绝结构性不适用人数与未知类别；节点确定性回放；行为收集有界；**配方生成与不变量**（见 §8.1） |
| `test_strategy_registry.py` | 新身份与工厂；无版本与错版本标识被拒；接口层接受新标识并落库规范化身份 |

## 6. 本次常规检查实跑结果（2026-09-21）

| 命令 | 实际结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `790 passed, 3 skipped, 2 warnings in 12.15s` |
| `cd frontend && npm run build` | Vite 6.4.3；`24 modules transformed`；`built in 509ms` |

对照：既有基线为 `668 passed, 2 skipped`。新增用例合计 123 条（122 passed + 1 条默认跳过的 opt-in）。剔除本轮新增的五个测试文件与注册表增量后，**既有 668 条断言全部保持通过，没有删除整条用例、也没有放宽无关断言**；唯一的既有文件改动是把集合包含关系断言从两个标识扩为三个。

两条 skip 仍是既有的显式 opt-in 基准；第三条 skip 是本轮新增的混合验证 opt-in 入口。两条 warning 仍是依赖弃用提示，未升级依赖。训练器未改动，本次未执行其独立检查或测试。前端源码未改动，仅构建，未运行布局验收（未获授权触及前端）。

### 6.1 逐张牌清单冻结后的复测（同日追加）

| 命令 | 实际结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `801 passed, 3 skipped, 2 warnings in 12.11s` |
| `cd frontend && npm run build` | Vite 6.4.3；`24 modules transformed`；`built in 494ms` |

相对 §6 的 `790 passed` 增加 11 条通过用例与 1 条新增 opt-in 跳过；既有断言仍全部通过，未删除或放宽任何一条。

## 7. 行为与兼容影响

| 对象 | 影响 |
|---|---|
| 公开 API 字段 | **零变化**：无新增、无改名、无删除；`bot_strategy` 新建默认仍为 `heuristic@1` |
| 数据库 | **不加列、不迁移**；继续复用既有 `bot_strategy` 字段；真实库未被写入 |
| 历史记录 | `history_json` 不改写、不迁移；旧记录缺身份仍读作 `unknown` |
| 既有策略语义 | **零改动**：`heuristic.py` 的阈值与分支、`random_strategy.py`、`projection.py`、`lookup_budget.py` 常量、`equity()` 的语义与采样数均未触碰 |
| 复盘与参考身份 | **零改动**：仍使用 `heuristic-conservative` 与既有保护判据；新对手不参与真人错误判定 |
| 内部契约 | 只新增：`mixed-context.v1` / `mixed-distribution.v1` / `mixed-bot-fixtures.v1` / `mixed-validation.v1` 均为新策略或测试自身口径，不进入旧公开响应或旧历史 JSON |
| 训练记录 / artifact schema | **零改动**：未改 `experiment` / `measurement` / 候选工件 schema 与 `PROBABILITY_UNITS`；训练器未被 import |
| `docs/37` §3.1 | **不触发**：参考实现、保守判据、`equity` 实现、采样数与固定种子五项全部零改动 |
| 前端 | 零改动；未恢复策略选择器 |

## 8. 未做事项与仍未证的结论

- 未运行 `docs/53` §11 的任何实跑：分布矩阵（1125 份直接分布）、成本矩阵（逐人数 10000 次）、补充矩阵（240 次）、对抗对照（4224 手）与阶段 A/B 均**未执行**。
- 阶段 A/B 的 runner 已实现但**尚未被执行过**，因此其端到端可运行性仍未经实测；首次执行仍须单独获得运行许可。
- 逐张牌清单已按 §8.1 冻结并通过用户签收；清单只定义节点，不产生任何运行读数。
- 未获得任何预算；阶段 A 的 120 秒与 A+B 的 1800 秒仍只是待批准提案。
- 未切换新建默认策略；未修改 `schemas.py`。
- 未做 N=9 采样式质量评估，未重开 `docs/51c` 拒绝的范围。
- 提交与推送：起草本记录时尚未发生；随后按用户的**单独授权**执行，提交分两次（实现一次、本记录一次），全哈希与推送结果在交付消息中实报。前端与训练器不在这两次提交范围内。
- **仍未证**：新 Bot 的合法性之外的实际质量、混合机制在真实对局中的表现、多风格间差异的稳定性、抗针对程度、单次决策是否稳定满足 100ms 硬预算、2–9 人的延迟分布、共享公共大牌是否构成已知弱点。

## 8.1 逐张牌清单的冻结（2026-09-21，用户签收）

签收方式：由用户先认可「规则化生成」，再由本文件与清单公开**构造规则与槽位清单**供只读核对，不逐张人工审阅 125 组牌。

| 项 | 值 |
|---|---|
| 清单文件 | `/Users/bryanylliu/holdem-mixed-bot-validation/input/frozen-fixture-manifest.json` |
| 报告输出目录 | `/Users/bryanylliu/holdem-mixed-bot-validation/runs/`（当前为空） |
| `manifest_digest` | `d36326555fe1ccba515b543e59e055a0c44d9537471f7b6eafee8aeb1eeff751` |
| `config_digest` | `bfe231419ecc31e54e9b73aaa16421026cc2392a21516ddb44e6a629936d1484` |
| `code_identity` | `566b0dd95da78de45851f017778d4db127abb4e4`（被测策略实现提交；不取测试侧提交以避免自引用） |
| 节点数 / 街分布 | 125 个；翻前 54 / 翻牌 16 / 转牌 23 / 河牌 32 |
| 覆盖 | 每个 2–9 人数都覆盖全部四街；每个（类别，人数）槽恰好一个节点 |
| 主种子 | 1215 / 20260918 / 3311 / 7926（数值沿用，未新增） |

构造规则（冻结，与运行结果无关）：

1. **决策街**：每类节点的街写死在类别表中，不由运行结果选择。
2. **翻前形状**：无自愿加注 / 1 家跛入 / 加注到 30 / 连续两次加注 / 加注到 80 / 「加注 30 → 全员跟注 → 大盲短码全下 45」/「先行者全下 150 → 一家跟注」。
3. **驱动**：只用跟注与过牌推进到目标街，不越过目标街行动；目标街之后就位的是声明中的决策者。
4. **价格**：除免费过牌节点外，到达目标街后先让首位玩家下注 `max(min_bet, min(max_bet, 底池/2))`，决策者即面对该下注的一位。
5. **牌面主题**：焦点座位拿到与类别对应的牌面（顶对弱踢脚、同花听牌、组合听牌、错失听牌、公共共享大牌等），其余座位按固定顺序填牌，保证与已用牌不重复。
6. **短码角色**：三个类别使用固定短码（`short-stack-call`、`incomplete-raise`、`one-side-all-in`），由「开局前筹码」表达，因此**不参与深度缩放**；其余节点按 15/100/1000BB 等比缩放。
7. **两遍执行**：先用占位底牌把短码角色迭代稳定并确定决策座位，再放主题牌面重跑；两次的决策座位、决策街与动作线必须完全一致，否则显式失败。

清单**直接由测试逐条核对**，而不是靠人工阅牌：125 槽无重无漏、每个人数覆盖四街、逐节点回放成功且落在声明决策街、牌面不重复、以及按类别的语义不变量（短码跟注必须 `is_short_all_in_call`、不足额加注必须已失去加注权、单方全下必须恰好一名对手全下、免费过牌必须无可跟注额、共享牌面必须自身牌力等于公共五张牌力）。

清单冻结**不等于**获得运行许可：阶段 A/B 仍需另行授权，`runs/` 目前为空。

## 9. 实现取舍披露

| # | 取舍 | 理由与边界 |
|---|---|---|
| 1 | 子策略做成**无状态纯函数**：手模式与动作随机流都由 `(座位键, 手号, 事件数)` 确定性派生，不保存「本手模式缓存」 | 与 `docs/53` §9.4 的「相同手号、事件数、输入和版本重复查询/采样得到相同结果」直接一致；避免引入跨手可变状态。一手内模式天然固定 |
| 2 | 离线行为统计直接用 `MixedSeatPolicy` 逐风格构造，而非走座位升序循环分配 | `docs/53` §11.3 明确「模式由内部测试接口显式指定，生产无此参数」；逐风格覆盖需要绕过生产分配规则，属测试侧能力，不改生产分配 |
| 3 | 分布保留零单位候选 | `docs/53` §10.4 明确「非负整数 units」与「零单位项不抽到」；抽样只在正单位项上累计，报告侧因此能如实区分「结构性单尺寸」与「无主动概率」 |
| 4 | 归一化允许 ≤1 个单位的取整差 | 先按精确有理数归一、再由小数余数补齐差额；两个候选集合不同但精确质量相同时，取整次序可能相差 1 个单位 |
| 5 | 新策略的牌堆种子由主键派生，旧策略仍直接用请求 seed | `docs/53` §9.4 明确「相同显式 seed 的新旧策略不保证得到相同发牌」；旧随机消费语义零改动 |
| 6 | 补充场景耗时单列而不并入主路径 | `docs/53` §11.4 要求补充测试与主矩阵分开报告 |
| 7 | 逐张牌清单**按固定规则生成**，签收对象是规则与槽位清单，而不是 125 组牌面 | 生成不参考任何运行结果；规则与不变量由测试逐条核对，签收面从 125 组牌降到 1 份规则 |
| 8 | 三道**默认拒绝门禁**：完整分布矩阵、对抗对照、缺机械明细的清单 | 避免「写好 opt-in 入口就等于获得运行许可」；只有 `run_validation` 的阶段许可路径能开启 |
| 9 | 三个短码节点不参与深度缩放，只在其自身筹码上使用 | 短码语义依赖固定筹码额；把它们放进其它深度格会与该类别的定义冲突，成本矩阵按可缩放性筛选节点 |

## 10. 边界声明与不得声称

- 本轮改动是**首期实现、常规回归与清单冻结**，不是质量验证，也不构成任何强度、均衡或生产可用证据。
- 不得把通过的 801 条测试或 125 个节点的顺利回放表述为对手质量、不可预测性或抗针对程度的证明。
- 不得把 `mixed-local@1` 的规则评分表述为概率、EV、GTO 或均衡结论。
- 不得把「未运行」表述为「已通过」，也不得把未测人数外推为已覆盖。
- 不得把清单冻结表述为已获得运行许可或已消耗任何预算。
- 不得据此修改 `docs/20` 至 `docs/53`；`docs/53a` 只是实施回执。

## 11. 下一步唯一建议动作

清单已冻结并签收，**唯一建议的下一步是单独授权阶段 A 的运行**：建议先跑 A0（单人数 × 单风格 × 单深度 × 四街各一次的极小前哨，用于验证 runner 端到端可用），确认后再执行 A1（成本矩阵逐人数 36 格首样本 288 次 + 补充首样本 24 次 + 对抗 64 手）。阶段 A 实测披露之后，再另行裁定阶段 B 预算可行性与质量签收；默认切换必须晚于质量签收并单独授权。
