# 54a M8：共享牌面细化（M1 + M1b）实施与回归回执

> 日期：2026-09-22。
>
> 本文件是 `docs/54` 草案下决策 D1 与 M1b 的**实施回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/54` 未被改写（`54` 仅为被引用的草案）。
>
> 本文件记录已落地的代码与已实跑的常规检查。**不产生任何质量或强度证据**：未运行任何阶段实跑、未对抗对局、未切换默认策略、未改写任何外部清单或封存工件。

## 1. 授权原文与边界

第一次实施授权（M1）用户答复原文：

> 「A. 授权实施 M1（推荐。按草案 §4 方案 (b) 实现锁定判定与分池口径；不改旧身份与证据；回归锁定非锁定共享牌面仍保持保守。）」

第二次授权（M1b）用户答复原文：

> 「A. 裁定 M1b：锁定局面免除人数惩罚（推荐。配套回归，仍不含实跑；直接修 7-9 人档缺口。）」

| 项 | 内容 |
|---|---|
| 被授权 | 实现 M1（锁定判定 + 分池价格口径）与 M1b（锁定局面免除人数惩罚）；注册 `mixed-local@2` 并保留 `mixed-local@1`；配套针对性回归；运行 `ruff` / `pytest` / `npm run build` |
| 明确排除 | 任何阶段实跑；默认策略切换；外部冻结清单改写；`docs/53` 及既有回执改写；前端源码改动；训练器改动；`commit` / `push`（需另行当轮授权）；云端操作 |

### 1.1 版本身份的处置（必须披露）

M1b 在 `mixed-local@2` 落地之前到达。`mixed-local@2` **只存在于工作区，尚未提交，也未被任何回执、报告或证据引用**。因此 M1b 作为同一「分池口径」的一部分**并入 `mixed-local@2`**，不新开第三版。

若第二版已提交或被证据引用，则必须另立新身份；本轮不构成对该纪律的例外。

## 2. 基线与结束状态（只读核验）

| 项 | 值 |
|---|---|
| 起始 HEAD / `origin/master` | `a52c4a626ec9a8c4d5d2edfb4f978ff110ee789b`（两者相同） |
| 起始工作区 | 仅 `?? docs/54-m8-full-bot-rule-refinement-draft.md` 一项 |
| 结束 HEAD | 未变（本轮未提交、未推送） |
| 结束工作区 | 见 §3；既有跟踪文件无「删除/改名」，仅新增与定点修改 |

## 3. 文件级改动

| 文件 | 改动 |
|---|---|
| `backend/app/strategy/mixed_features.py`（修改，+65） | 新增锁定判定（`_board_hand_is_untouchable`、`_highest_straight_window`）与特征字段 `shared_board_locked`；既有封顶 `_SHARED_BOARD_CAP=450` **不变** |
| `backend/app/strategy/mixed_policy.py`（修改，+30/−4） | 新增口径对象 `MixedPolicyRules` 与两个口径常量；`build_distribution` 增加**带默认值**的 `rules` 参数；`_score` 在分池口径下免除锁定局面的人数惩罚；`build_distribution` 的跟注价格按分池人数折减 |
| `backend/app/strategy/mixed_strategy.py`（修改，+65/−13） | 新增 `mixed-local@2` 身份常量、身份→口径映射、`rules_for_identifier`、未注册身份显式失败；`MixedLocalStrategy` 增加 `identifier` 参数与属性；`derive_deck_seed` / `derive_bots_key` 增加**带默认值**的身份参数 |
| `backend/app/strategy/registry.py`（修改，+14） | 新增 `mixed-local@2` 注册项；`mixed-local@1` 条目、别名与工厂**逐字不变** |
| `backend/app/strategy/__init__.py`（修改，+14） | 导出新增符号；既有导出与顺序不变 |
| `backend/app/api/games.py`（修改，+5/−5） | 新策略分支改为按身份集合判定，并**按身份**派生牌堆种子；旧策略路径不变 |
| `backend/tests/test_mixed_shared_board.py`（**新增**，273 行） | 86 条针对性回归（§5） |
| `backend/tests/test_mixed_games.py`（修改，+21） | 新增 1 条：第二版身份可显式选择、可打完一手 |
| `backend/tests/test_strategy_registry.py`（修改，+3/−2） | **两处取值就地更新**（§6） |
| `docs/54a-…md`（本文件） | 实施回执 |

**未改动**（`git status` 可证）：`backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/storage/**`、`backend/app/api/schemas.py` 及其余 API 模块、`backend/app/strategy/heuristic.py` / `random_strategy.py` / `interface.py` / `projection.py` / `lookup_budget.py` / `mixed_context.py`、`backend/data/holdem.db`、`backend/uv.lock`、`frontend/**`、`tools/trainer/**`、`docs/20` 至 `docs/53`（含 `53a`/`53b`/`53c`）、工作树外的冻结清单与四份回执。实施期间未创建任何临时脚本或临时文件。

## 4. 规则改动（M1 + M1b）

### 4.1 锁定判定（M1，新增，只读公共五张）

新增 `shared_board_locked`：河牌时自身最佳牌型等同于公共五张，**且该牌型已不可能被任何两张底牌超越**。判定按牌型分类给出，只在能证明时才为真：

- 公共同花顺：检查同花色能否用至多两张补牌凑出更高的同花顺窗口；不能则锁定。
- 公共至少三张同花：直接判否（两张同花底牌即可成同花或抬高已有同花）。
- 公共四条：在排除同花顺可能后判是（四张同点牌已用尽，底牌既凑不出更高四条也凑不出葫芦）。
- 公共三条：判否（任一底牌配上即成四条）。
- 公共顺子：公共有对子则判否（葫芦可能）；否则比较「可用至多两张补牌凑出的最高五连窗口」与公共顺子高度。
- 其余牌型（两对及以下）：判否。

判定只读公共五张，不枚举对手底牌、不读未发牌、不新增 Monte Carlo；河牌单次决策的 `evaluate_fast` 调用次数仍为至多两次（由回归锁定）。

### 4.2 分池口径（仅 `mixed-local@2` 生效）

锁定平分局面上施加两项改动，二者同属一个口径：

1. **免除人数惩罚**（M1b）：原先每多一名未弃牌对手减 `_CONTENDER_PENALTY=35` 分；锁定局面下英雄不会输，人数不降低其权益，故不再减分。
2. **折减跟注价格**（M1）：跟注价格按共同分割底池的人数折减，即 `price // (contenders + 1)`，理由是该局面下英雄不是要独占底池。

首版 `mixed-local@1` 的口径**逐字不变**，仍按普通跟注加人数惩罚处理。

**未做**：本次不改 `_SHARED_BOARD_CAP=450`，不改阈值基数、价值阈值、风格参数、尺度生成、危险尺度保护与量化规则，也不在锁定局面引入任何主动动作。

## 5. 新增与修改的回归

| 测试 | 锁定的契约 |
|---|---|
| `test_untouchable_board_detection`（9 例） | 锁定判定的正反例：百老汇顺子、中段顺子、三张同花、公共三条、公共两对、公共四条、皇家同花顺、九高同花顺、公共五张同花 |
| `test_shared_board_nodes_are_locked`（2–9 人） | 冻结的共享牌面节点全部判为锁定，且基础分仍被封顶在 450 |
| `test_plain_river_shape_is_not_locked` | 普通一对牌面不得被误判为锁定 |
| `test_chop_caliber_only_moves_mass_from_fold_to_call`（8 人数 × 3 风格） | 分池口径只把质量从弃牌移向跟注，不得反向；单位总和恒为一百万 |
| `test_heads_up_locked_board_recovers_call_mass` | 两人桌三风格均得到高于首版的跟注质量 |
| `test_non_locked_nodes_are_unchanged` | 非锁定节点两版分布**完全一致**，细化不外溢 |
| `test_lock_covers_every_player_count` | **全部 2–9 人档**在锁定局面都给出非零跟注质量（M1b 后的覆盖断言） |
| `test_locked_board_keeps_no_active_aggression`（8 人数 × 3 风格） | 锁定局面只分摊弃牌与跟注，不得凭空产生下注或加注质量 |
| `test_locked_decision_ignores_opponent_hole_cards` | 换掉未公开的对手底牌不改变锁定判定与特征 |
| `test_river_decision_still_uses_at_most_two_evaluations` | 锁定判定不增加牌型评估次数 |
| `test_second_version_replays_deterministically` | 第二版仍可确定性重放；分布查询不消耗行动随机流；两版分布不同 |
| `test_second_identity_is_registered_alongside_the_first` | 两版身份并存，第二版版本号为 2 |
| `test_unregistered_mixed_identifiers_still_fail` | `mixed-local`（无版本）与 `mixed-local@3` 仍被拒 |
| `test_factory_keeps_each_version_on_its_own_caliber` | 工厂按身份给出对应口径 |
| `test_unregistered_identity_never_falls_back_to_the_first_version` | 未注册身份不静默回退（口径、实例、派生均显式失败） |
| `test_omitted_identifier_stays_on_the_first_version` | 省略身份等价于首版 |
| `test_versions_do_not_share_random_streams` | 两版牌堆与 Bot 派生流互不相同 |
| `test_second_mixed_version_is_selectable_and_plays_a_hand`（`test_mixed_games.py`） | 接口层可选第二版、可打完一手、派生流与首版分离 |

## 6. 既有断言的就地更新（如实披露）

`backend/tests/test_strategy_registry.py` 原有两条断言**显式要求 `mixed-local@2` 不存在**：一条在 `test_mixed_identity_has_no_unversioned_alias`，一条在 `test_create_game_rejects_unknown_identifier` 的取值表里。注册第二版后这两条必然失效。

处理方式：**只把「代表未注册版本」的取值从 `mixed-local@2` 换成 `mixed-local@3`**，两条断言所验证的性质（未知版本必须被拒、无版本别名必须被拒）逐条保留。未删除任何用例，未放宽任何无关断言。

另有一条**本轮内新增又替换**的断言：M1 阶段为记录缺口写了 `test_nine_handed_locked_board_is_not_yet_covered`（断言九人档两版一致）；M1b 授权后该缺口被修，按该断言自带的说明替换为 `test_lock_covers_every_player_count`。此替换发生在同一未提交轮次内，不涉及任何已提交或已引用的证据。

## 7. 开发期定点核对读数（**不是**新样本、不进报告、不构成质量证据）

实施后对冻结的共享牌面节点做了一次只读定点核对（`python -c` 内联执行，未落任何文件），用于确认机制与设定测试断言。实测（正常手模式，`price=250`、`r=1`、`base=450`、锁定判定在 2–9 人全部为真）：

| 人数（未弃牌对手数） | 跟注单位 首版 → 第二版（紧密 / 松凶 / 跟注） |
|---|---|
| 2（1） | 247,332 → 406,073 ｜ 603,648 → 765,072 ｜ 648,364 → 790,289 |
| 3（2） | 62,253 → 344,235 ｜ 363,575 → 706,173 ｜ 387,748 → 741,091 |
| 4（3） | 8,687 → 406,073 ｜ 280,207 → 765,072 ｜ 279,255 → 790,289 |
| 5（4） | 0 → 403,061 ｜ 129,527 → 762,310 ｜ 52,083 → 788,043 |
| 6（5） | 0 → 403,061 ｜ 0 → 762,310 ｜ 0 → 788,043 |
| 7（6） | 0 → 403,061 ｜ 0 → 762,310 ｜ 0 → 788,043 |
| 8（7） | 0 → 403,061 ｜ 0 → 762,310 ｜ 0 → 788,043 |
| 9（8） | 0 → 403,061 ｜ 0 → 762,310 ｜ 0 → 788,043 |

补充实测：**全部 24 个组合（8 人数 × 3 风格）在下注与加注上的质量均为 0**，即第二版只改变弃牌与跟注之间的分摊，未产生主动动作。

读数含义仅为「跟注质量从零变为非零」这一分布层面的变化，**不是**质量改善的证明。六人以上档位在第二版下数值相同，是因为人数惩罚被免除后评分不再随人数变化、而折减后的价格项也趋于同一量级；这不代表这些档位已被充分校准。

## 8. 本次常规检查实跑结果（2026-09-22）

| 命令 | 实际结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `902 passed, 3 skipped, 2 warnings in 12.74s` |
| `cd frontend && npm run build` | Vite 6.4.3；`24 modules transformed`；`built in 514ms` |

对照：本轮基线为 `815 passed, 3 skipped`。新增 87 条通过用例，既有 815 条**全部保持通过**；两条 skip 仍是既有显式 opt-in 基准，第三条是本轮之前已存在的混合验证 opt-in 入口。前端源码未改动，仅构建。

## 9. 契约与兼容影响

| 对象 | 影响 |
|---|---|
| 公开 API 字段 | **无新增/改名/删除**；但 `bot_strategy` 的**可接受取值新增 `mixed-local@2`**——这是显式的接口行为变化，如实记录 |
| 新建默认策略 | **仍为 `heuristic@1`**，未切换；`schemas.py` 未改动 |
| 数据库 | 不加列、不迁移；真实库未被写入 |
| 内部契约 | 新增：`MixedPolicyRules` 与两个口径常量、身份集合与映射、`rules_for_identifier`、`MixedFeatures.shared_board_locked`；`build_distribution` / `_score` / `derive_deck_seed` / `derive_bots_key` / `MixedLocalStrategy` / `MixedSeatPolicy` 各增加**带默认值**的参数，缺省行为等同首版 |
| 旧身份语义 | `mixed-local@1` 的口径、派生消息与分布**逐字不变**；旧策略路径（`heuristic@1` / `random@1`）零改动 |
| `history_json` / 复盘参考 | 不改写；复盘仍用独立保守参考 |
| `docs/37` §3.1 | **不触发**（参考实现、保守判据、`equity` 实现、采样数、固定种子五项零改动） |
| 训练器 / artifact schema | 零改动；未 import 训练器 |

## 10. 未做事项与仍未证

- 未运行任何阶段实跑：§7 的读数是开发期定点核对，**不是**成本矩阵、对抗对局或分布矩阵，不能当作新一轮样本。
- 未做 `mixed-local@2` 的再测量：外部冻结清单绑定 `strategy_id=mixed-local@1` 与既有 `config_digest`，且不得改写，因此第二版需要一个**新的清单与摘要**——属 `docs/54` 决策 D5，本次未获授权。
- 未做任何 best-response 或剥削性检验；「锁定平分局面下弃牌严格劣于跟注」是规则层面的支配关系，**不等于**该弱点已被对手利用。
- 仍未证：`mixed-local@2` 的实际质量、抗针对程度、长矩阵下的决策延迟（本轮未跑任何性能矩阵）、2–9 人之外的外推。
- 仍未处理 `docs/54` 的其余反向读数：翻前过紧（R2，需决策 D2 的目标带）与松凶–跟注人格区分不足（R3，需决策 D3）。

## 11. 不得声称

- 不得把本轮表述为质量通过、强度认证、抗针对程度或生产可用性。
- 不得把 §7 的读数表述为新的测量样本或质量证据；它只是规则层的定点核对。
- 不得把 902 条测试通过或前端构建成功表述为对手质量证据。
- 不得把共享牌面上跟注质量从零变为非零表述为「已修复已知弱点」。
- 不得把注册第二版表述为已授权默认切换。
- 不得据此修改 `docs/20` 至 `docs/53` 及 `docs/53a`/`53b`/`53c`。

## 12. 唯一下一步

M1 与 M1b 均已落地并通过常规检查，`docs/54` 中 D4 已按建议取值落实。**建议下一步只裁定一件事：D5——为 `mixed-local@2` 立新的清单与摘要并授权再测量**（含开发性对照，以及是否需要独立质量验证的预注册）。该裁定必须同时给出运行范围与预算口径：既有冻结清单不得改写，已消耗的授权不得重试，A9 相关授权绝不可重试。
