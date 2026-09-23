# 55b M8：独立质量验证的测试侧改动实施回执（既有清单可复现性已复核）

> 日期：2026-09-22。
>
> 本文件是 `docs/55a` §8 的 C1–C4 实施回执，沿用 `docs/30` §10.1 D6 的编号族约定。`docs/20` 至 `docs/55a` 未被改写，五套外部证据目录未被增删或改写。
>
> 本文件只记录**测试侧能力**的实施与其实测结果。**未生成任何清单文件、未做任何工作树外写入、未运行任何验证阶段、未产生任何质量或强度证据。**

## 1. 授权原文与边界

用户答复原文：

> 「选择 A. 此外，不必 commit 过于频繁，工作树有阶段性改动后再向我请求 commit + push。」

对应选项原文：

> 「A. 授权全部 C1–C4(新增新配方/节点集、新增 4 个探针族、主种子集参数化、补 opt-in 回归；既有常量与既有回归零改动，不合格则停下报告)」

| 项 | 内容 |
|---|---|
| 被授权 | 实施 `docs/55a` §8 的 C1–C4：新增配方与节点集、新增 4 个探针族、主种子集参数化、补 opt-in 回归 |
| 明确排除 | 生成新清单与工作树外写入（C5）；任何阶段实跑；改参数或策略口径；新策略身份；默认切换；M2-3；前端与训练器改动 |
| 提交与推送 | 改为**阶段性改动后**统一请求当轮授权，不再逐小步请求 |

## 2. 只读基线核验（实施前）

```text
$ git status --short --branch
## master...origin/master

$ git rev-parse HEAD
ecdb2a9bd894ff4178982fb147585dbaf8d63a39

$ ls -1 docs/ | wc -l                 -> 99
$ ls -1 backend/tests/*.py | wc -l    -> 43
```

实施前工作区干净。

## 3. 文件级改动

| 文件 | 改动 | 性质 |
|---|---|---|
| `backend/tests/mixed_bot_states.py` | 新增 `MIXED_IQV_RECIPES`（16 组）/ `MIXED_IQV_RECIPE_BY_CATEGORY` / `MIXED_IQV_NODE_ID_SUFFIX` / `MIXED_IQV_RECIPE_CATEGORY_ORDER`；把 `build_node` 的内核抽成 `_build_node_from(recipe, …, node_id_suffix)`，`build_node` 与新增 `build_iqv_node` 各自薄封装；新增 `build_frozen_iqv_nodes()`；`build_frozen_manifest` 增可选 `nodes` 参数 | 新增 |
| `backend/tests/mixed_bot_validation.py` | 新增 `MIXED_IQV_MAIN_SEEDS`（8 个）与 `derive_iqv_main_seeds()`；新增 4 个探针类与其私有辅助；新增 `ADVERSARIAL_OPPONENT_FAMILIES_IQV`、`ADVERSARIAL_FAMILY_SETS`、`adversarial_families()`；新增 `MIXED_IQV_VALIDATION_LIMITATIONS` 与 `validation_limitations()`；新增 `MIXED_IQV_SCENARIO_ORDER`、`MIXED_IQV_STAGE_PLAN`、`ADVERSARIAL_HANDS_IQV`、`STAGE_A_ADVERSARIAL_HANDS_IQV`、`frozen_iqv_manifest()`；对 `adversarial_schedule` / `run_adversarial_batch` / `matches_from_tally` / `run_validation` 增可选参数；`_opponent_mover` 注册 4 个新族；命令行增 `--family-set=` | 新增 + 参数化 |
| `backend/tests/mixed_bot_recheck.py` | `aggregate_matches` 的种子块顺序改为**取自排期自身**（原取模块常量）；新增 `recheck_limitations(块数)` 并在补算报告中按回执实际块数生成块统计措辞 | 缺陷修复 |
| `backend/tests/test_mixed_bot_benchmark.py` | 新增 9 条回归（见 §6） | 新增测试 |

**零改动**：`backend/app/**`（含 `poker/`、`analysis/`、`storage/`、`strategy/`）、`backend/data/holdem.db`、`backend/uv.lock`、`frontend/**`、`tools/trainer/**`、`docs/20`–`docs/55a`、五套外部证据目录。

## 4. 必须如实披露的四处范围扩展

字面授权是 C1–C4；为让 C1–C4 真正可用，做了四处**同源且必要**的扩展，逐项披露：

| # | 扩展 | 为什么必要 |
|---|---|---|
| 1 | 族集注册表 `ADVERSARIAL_FAMILY_SETS` + `adversarial_families()` | 清单模型不得新增字段（新增字段会改变已落盘清单的 `manifest_digest`，破坏证据链），因此对手族集只能是**运行参数**；注册表让族集可被显式选择且未注册名称显式失败 |
| 2 | `frozen_iqv_manifest()` | C3 的「参数化」若没有消费方就没有验证对象；该函数**只返回清单对象**，不写文件、不建目录 |
| 3 | 局限说明按种子块数取值（`validation_limitations` / `recheck_limitations`） | 既有常量写死「四个固定主种子块」；8 块清单若沿用该措辞即为不实陈述。该项直接对应 `docs/55` §10.4.2 第 6 条「结论边界必须如实标注」 |
| 4 | `aggregate_matches` 的种子块顺序改取排期自身 | 原实现只认四个既有主种子：对新主种子会得到**空块统计**并随后 `min()`/`max()` 失败。这是新入口暴露出的真实缺陷，属修复而非重构 |

**范围扩展的边界声明**：以上四项均**不改变任何既有路径的取值**；证据见 §5。

## 5. 既有可复现性复核（本轮最强证据）

### 5.1 五个既有身份的清单摘要复算

用 `frozen_manifest` 按各身份的 `code_identity`、`output_dir`（实际为 `<外部目录>/runs`）与 `strategy_id` 重新装配清单并复算 `manifest_digest`：

| 身份 | 复算结果 | 与回执记录 |
|---|---|---|
| `mixed-local@1` | `d36326555fe1ccba515b543e59e055a0c44d9537471f7b6eafee8aeb1eeff751` | **逐字一致** |
| `mixed-local@2` | `dd5ee96647f68062d08a17ae9480cb4cebe599a67c5c91a118b9de175198e2f8` | **逐字一致** |
| `mixed-local@3` | `f8ad8c2e47e35833e315efc6add989a21e091adf1197d520bd70c7eddfb46541` | **逐字一致** |
| `mixed-local@4` | `57906102a79295b51a192d84fd1401041732dabf3d1290dfbd01a5f00cc2d4d6` | **逐字一致** |
| `mixed-local@5` | `d68125e2dfc4600f2e23a80bb18b23f997812f73732812ddf685d38e112124e6` | **逐字一致** |

结论：**5/5 全部逐字复现**。这证明 `build_node` 的抽取与 `nodes` 参数的加入没有改变既有节点的任何字段（底牌、公共牌、动作线、筹码、标识、文本）。

**方法说明（必须如实标注）**：首次复算时五者全部不符，逐字段比对后确认唯一差异是 `output_dir`（实际清单用的是 `<外部目录>/runs`）。按该值重算后全部一致。该差异属复算脚本的参数选择问题，**不是**代码缺陷；此处如实记录该过程，以免后续读者误以为存在过回归。

### 5.2 既有测试套件

`1120 passed, 3 skipped`（实施前为 `1111 passed, 3 skipped`）：**既有 1111 条全部仍然通过**，新增 9 条；skip 数不变。

## 6. 新增回归（C4）

| 测试 | 断言的实质 |
|---|---|
| `test_iqv_main_seeds_follow_the_frozen_derivation_rule` | 8 个新主种子可由冻结派生规则复算；互不重复；与既有四个主种子**无一重合**；非法块数显式失败 |
| `test_iqv_nodes_are_a_full_second_set` | 第二套节点数为 125；标识全部带 `-iqv1` 后缀；与首套**标识不重合**且**内容不重合**（类别/人数/底牌/公共牌/动作线/筹码六元组） |
| `test_iqv_family_set_extends_the_first_batch_untouched` | 默认族集与既有四族逐字一致；`iqv` 集以既有四族开头；共 8 族；未注册族集名显式失败 |
| `test_iqv_schedule_counts_match_the_mechanical_arithmetic` | 默认排期 64 / 4,224 逐字不变；第二套排期 128 / **16,896** 与规格算式一致；空种子集显式失败 |
| `test_iqv_manifest_keeps_the_same_slots_but_new_content` | 第二套清单：8 个新种子、125 个新节点、`config_digest` 取 `mixed-local@5`、与首套清单摘要不同、机械明细齐全 |
| `test_iqv_probes_are_deterministic_and_blind_to_hidden_cards` | 4 个探针 × 125 节点：同局面可复现；**换掉对手暗牌（未脱敏快照 vs 脱敏投影）动作完全相同**；动作类型合法 |
| `test_iqv_adversarial_batch_runs_the_second_family_set` | **真正走 opt-in 路径**：以第二套种子与族集执行对抗批（对局本体被替换为固定结果），逐手行数为 128、种子块与 8 个族名与第二套一致 |
| `test_limit_wording_follows_the_seed_block_count` | 4 块沿用原措辞、8 块用第二套措辞、未登记块数显式失败（验证入口与补算入口各自） |
| `test_aggregate_matches_uses_the_schedule_seed_blocks` | 8 个种子块的排期能给出 8 个块均值（原实现会失败）；首套排期的块统计仍为 `(1.0,)` |

**流程教训的落实**：第 7 条即 `docs/55` §11 要求的「为任何 opt-in 路径新增/修改调用点时，必须补一条真正走该路径的回归」——它走的正是本轮新增的族集与种子参数，而不是只核对常量。

## 7. 配方构造性的实测结果

`build_frozen_iqv_nodes()` 与 `build_frozen_nodes()` 的实测：

```text
old nodes: 125   new nodes: 125
id overlap: 0     content overlap: 0
all ids suffixed: True
```

16 组候选配方**全部构造成功**。既有构造器内含两遍一致性校验（占位执行与主题牌面执行的决策座位、决策街、动作线必须完全一致），因此构造成功同时意味着这 16 组配方通过了该机械校验。

**边界（不得越过）**：构造成功只证明**机制可构造**，不证明这些节点的覆盖面足够、不代表质量，也不构成任何强度或验收证据。

## 8. 与文档口径的对照

| `docs/55a` 的规格 | 实施结果 |
|---|---|
| §5.2 的 16 组候选配方 | 逐组落地，未替换任何一组 |
| §5.3 标识加 `-iqv1`、适用人数沿用门槛规则 | 已落地；125 个节点 |
| §6.2 的 4 个增补族 | 逐族落地；既有 4 族实现零改动 |
| §6.4 手数算式 264 / 2,112 / 8,448 / **16,896** | `ADVERSARIAL_HANDS_IQV == 16896`、阶段 A `128`，与算式一致 |
| §7 机会分母与评估方式 | 未实施改动（评估口径沿用既有实现）；§7.5 的两个预先指定机会域仍待写入清单文本 |
| §8 的 C5（生成清单并写入工作树外） | **未做**，需单独授权 |

**一处如实记账**：`docs/55a` §7.5 要求「两个**预先指定**的机会域」出现在清单机械明细中，而清单模型的文本字段（`scenario_order` 等）是本轮未改的常量。该口径的落位属于 C5 的范围，**本轮未完成**，不得当作已冻结。

## 9. 契约、API 与默认策略

| 对象 | 状态 |
|---|---|
| 公开 API 字段 / 数据库列 / `history_json` | **零改动** |
| `experiment` / `measurement` / 候选 A artifact schema | **零改动** |
| 清单模型 `MixedFixtureManifest` | **零改动**（未加字段；加字段会改变已落盘清单摘要） |
| 新策略身份 | **未新增**（本轮只加样本集与测试侧能力） |
| `docs/37` §3.1 | **不触发**：参考实现、保守判据、`equity` 实现、采样数、固定种子五项零改动 |
| 新建默认策略 | **仍为 `heuristic@1`** |

## 10. 实测输出（提交前）

| 命令 | 实测结果 |
|---|---|
| `cd backend && UV_FROZEN=1 uv run ruff check .` | `All checks passed!` |
| `cd backend && HOLDEM_DB_PATH=:memory: HOLDEM_LOOKUP_BENCHMARK=0 HOLDEM_DECISION_LATENCY_BENCHMARK=0 UV_FROZEN=1 uv run pytest -q` | `1120 passed, 3 skipped, 2 warnings in 15.10s` |
| `cd frontend && npm run build` | `24 modules transformed`；`built in 536ms` |

## 11. 未做事项与仍未证

- **未做**：C5（生成清单、工作区外写入）；任何阶段实跑（A0/A/B）；确定性补算实跑；参数或策略口径改动；默认切换；M2-3。
- **仍未证**：任何质量结论；抗针对与剥削性检验；新节点集的覆盖面是否充分；两个预先指定机会域的清单落位；**耗时**（本文件不含任何耗时承诺）。
- **未消耗**：任何 authorization、任何实验预算、任何工作树外目录。
- 本轮只改 `backend/tests/**` 四个文件；默认整轮测试**不覆盖** opt-in 实跑路径，本轮新增的第 7 条回归只覆盖到对局本体被替换后的排期与汇总。

## 12. 不得声称

- 不得把本文件表述为质量验证、质量签收、强度认证或生产可用性。
- 不得把「16 组配方构造成功」「125 个节点零重合」表述为覆盖面充分或质量证据——它只证明机制可构造。
- 不得把新增的 9 条测试通过表述为独立质量验证。
- 不得把第二套清单的存在表述为已冻结清单或已授权运行；清单文件**尚未生成**。
- 不得把本轮的排期手数算式（16,896）表述为耗时预测或成本实测。
- 不得据此修改 `docs/20` 至 `docs/55a` 与任何已落盘证据；不得改写 `@1`–`@5` 任一身份的历史含义。

## 13. 本篇唯一下一步

C1–C4 已实施并实测通过，既有清单可复现性已用 5/5 摘要复算复核。

**建议的唯一下一步（需用户决定，本文件不自行执行）**：**单独裁定 C5**——生成第二套冻结清单并写入**工作树外的空目录**。理由：

1. 它是「运行授权」的最后一项前置：没有落盘清单，阶段门禁不会放行任何运行；
2. 它同时需要两项当轮批准：清单生成（会调用本轮新增的装配函数）与工作树外写入（新目录）；
3. 完成后才能谈「耗时估时」与「运行授权」，不得先跑再补。
