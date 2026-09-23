# 65 M8：第五套样本集（`-iqv4`）实施记录

> 日期：2026-09-23。
>
> 本文件接在 `docs/phase6/64-m8-seventh-identity-implementation-record.md` 之后，沿用 `docs/30` §10.1 D6 的编号族约定。归档路径按 `docs/README.md` 的维护约定：本文件属第四次验证族，归档于 `phase6/`。
>
> 本文件记录 `J1b` 的实际结果：按 `docs/phase6/62` §12 的顺序，在 `J1` 之后实施**第五套样本集**（配方、节点、种子盐、主种子、清单装配与回归）。
>
> **本文件不构成冻结或运行授权**：样本集**未冻结**、**未落盘**到任何外部证据目录、**未运行**任何标定或验证。`J2` / `J3` 与 `X2` 仍**未授权**。

## 1. 授权原文与边界

用户裁定（选项照录）：

> 「A. 授权 `J1b` 完整实施（规模沿用第四套）」

该选项随附理由由助手在选项中提出、随选项被选定，此处照录以免与用户原话混淆：

> 「按 `docs/phase6/62` §12 的冻结顺序，新样本集是「已看过的读数」与「未来独立验证」分开的前置条件；沿用 `125` 节点 / `16` 类别 / `16` 主种子可保持已登记的局限文本与成本包络不变。包含配方、节点、新盐与新种子、清单装配、正交性回归；不冻结、不落盘外部、不运行。」

| 项 | 内容 |
|---|---|
| 被授权 | 实施第五套样本集：`16` 条配方与主题牌面、节点构造器、新种子盐与 `16` 个新主种子、场景顺序与阶段计划文本、清单装配函数、深度重建派发、同构回归 |
| 明确排除 | 冻结清单；创建外部证据目录；运行标定 / 阶段 `A` / `B` / 补算；改判据 / 门槛 / 机会分母 / 估值块 / 区间方法；默认策略切换；推送 |
| 未授权 | `J2`（清单冻结）、`J3`（运行）、`X2`；工作树外写入 |
| 未消耗 | **未消耗**任何 authorization；`docs/37` §3.1 **未触发** |

## 2. 只读基线核验（实施前）

```text
$ git status --short --branch
## master...origin/master [ahead 3]

$ git rev-parse HEAD
ba3566aff074466fdbfa1c91d038f9d030c9d714

$ git rev-parse origin/master
06e9ecb2e50781a8c71d02bb6195f5e2453139fb
```

实施前实测：`ruff check .` → `All checks passed!`；`pytest -q` → `1225 passed, 3 skipped`；`npm run build` → `24 modules transformed`。八套外部证据目录未被触碰，v8 七份工件 sha256 未变。

## 3. 落点清单（与第四套逐项同构）

| 侧 | 文件 | 新增 |
|---|---|---|
| 节点与配方 | `backend/tests/mixed_bot_states.py` | `MIXED_IQV4_NODE_ID_SUFFIX = "-iqv4"`；`MIXED_IQV4_RECIPES`（`16` 条）；`MIXED_IQV4_RECIPE_BY_CATEGORY`；`MIXED_IQV4_RECIPE_CATEGORY_ORDER`；`build_iqv4_node`；`build_frozen_iqv4_nodes` |
| 种子与清单 | `backend/tests/mixed_bot_validation.py` | `MIXED_IQV4_SEED_PREFIX = "mixed-local-iqv-v4:seed:"`；`MIXED_IQV4_MAIN_SEED_COUNT = 16`；`derive_iqv4_main_seeds`；`MIXED_IQV4_MAIN_SEEDS`；`MIXED_IQV4_SCENARIO_ORDER`；`MIXED_IQV4_STAGE_PLAN`；`frozen_iqv4_manifest`；`_rebuild_fixture` 增加第五套分支 |
| 回归 | `backend/tests/test_mixed_iqv4_sample_set.py` | **新增**：尺寸与后缀、槽位覆盖、与**全部四套**既有样本集的正交性、牌面不重复与确定性、回放合法性与类别语义、主题语义、深度重建、种子派生与正交、清单身份与局限沿用、opt-in 入口链 |

**未改动**：四套既有样本集的配方、种子、清单装配与全部常量；`@1`–`@7` 的身份与摘要；判据模块与行为诊断模块；`backend/app/**` 全部产品代码（本轮**零产品代码改动**）；`frontend/**`；`tools/trainer/**`。

## 4. 主题牌面（第五套）

规模与第四套逐项相同：`16` 个类别、`125` 个可行动节点、形状 / 角色 / 是否开注与第四套一致，**只换主题牌面**。下表是记录，**代码是唯一来源**。

| 类别 | 底牌 | 公共牌 |
|---|---|---|
| `hu-blind-position` | `Ks/Qs` | — |
| `unopened-open` | `Ah/Th` | — |
| `open-after-limp` | `Ac/Jc` | — |
| `facing-first-raise` | `Qs/Ts` | — |
| `facing-reraise` | `Th/Td` | — |
| `short-stack-call` | `6s/6d` | — |
| `incomplete-raise` | `Ah/Kh` | — |
| `free-check` | `Jc/Td` | `Kd/Qs/2h` |
| `flop-draw` | `Ah/Kh` | `Qh/8h/3s` |
| `top-pair-weak-kicker` | `Ah/5c` | `As/7d/2h/4c` |
| `turn-combo-draw` | `Kd/Qd` | `Jd/Td/4s/2h` |
| `one-side-all-in` | `Ks/Qh` | `Jh/7c/4d/2s` |
| `overpair-on-high-board` | `7h/7c` | `Ad/Ks/Qc/6h/2d` |
| `missed-draw-river` | `Qc/Jc` | `Kc/8c/4d/2s/9h` |
| `shared-board` | `2c/3s` | `Ah/Kh/Qh/Jh/Th` |
| `sizes-merged` | `Jd/4c` | `Jh/8s/6d/3c/2h` |

正交性由回归逐（类别 × 人数）断言：底牌与公共牌都与**全部四套**既有样本集不同；节点标识、牌面、行动线三者组合亦不重合。`125` 个节点全部可回放，且每个类别的结构语义（短码全下跟注、不完整加注、单侧全下、免费过牌、共享牌面）逐节点成立。

**本轮新增了一条主题语义回归**（第四套没有）：逐节点断言 `flop-draw` 与 `turn-combo-draw` 的听牌分量为正、`top-pair-weak-kicker` 与 `sizes-merged` 为顶对、`overpair-on-high-board` 为口袋对、`missed-draw-river` 为高牌。它只断言性质，不写任何门槛数值。

## 5. 主种子（第五套）

| 项 | 内容 |
|---|---|
| 派生盐 | `mixed-local-iqv-v4:seed:` |
| 派生规则 | `sha256(盐 + 序号)` 的前 `4` 字节按大端解释为无符号整数，序号 `1..16` |
| 个数 | `16`（与既有四套一致） |
| 与前四套的关系 | **无交集**（回归断言） |
| 自身 | `16` 个互不相同（回归断言） |

清单中的种子序按上表派生顺序排列；**不得**按数值排序改写。

## 6. 清单装配

`frozen_iqv4_manifest(strategy_id=…)` 只返回清单对象，**不写文件、不建目录**；节点集、主种子、场景顺序与阶段计划文本均为第五套自身取值，其余机械明细（种子派生说明、资源包络、停止条件、报告版本）沿用既有取值。

回归断言：清单携带 `mixed-local@7` 时，`config_digest` 等于该身份的摘要（`fd7433e3…`）；块数为 `16` 时**沿用已登记的局限文本**（与前一版同一条），未新增局限条目。

## 7. 深度重建

节点标识是配方归属的唯一标记，`_rebuild_fixture` 增加第五套分支后，`fixture_at_depth` 可在其余深度上按第五套配方重建；回归断言可缩放节点在全部深度上重建后仍落在声明的决策街，固定短码节点原样返回。

## 8. 回归与实测输出

新增 `14` 条用例（尺寸与后缀、槽位覆盖、四套正交、牌面不重复与确定性、回放与类别语义、主题语义、深度重建、种子派生与正交、清单身份、局限沿用、入口链）。

```text
$ uv run ruff check .
All checks passed!

$ uv run pytest -q
1239 passed, 3 skipped, 2 warnings in 38.23s

$ npm run build
✓ 24 modules transformed.
✓ built in 555ms
```

`pytest` 用例数由 `1225` 增至 `1239`。

## 9. 未做事项、读数纪律与仍未证

- **未做**：清单冻结（`J2`）；任何外部目录创建；任何标定或验证运行（`J3`）；任何判据 / 门槛 / 分母 / 区间改动；任何产品代码改动；默认策略切换；推送；`X2` 的裁定。
- **读数纪律（本轮的要点）**：本轮**没有**在第五套样本集上计算或记录任何质量读数（不存在三档主动率、熵、JS 距离、跨人数净值之类的数字），以保持它作为**未来独立验证样本**的可用性。唯一触及节点行为的是 opt-in 入口链回归：它在**临时目录**对第五套的**一个**节点跑一次阶段 `A` 与一次补算，并且只断言结构与身份一致性、**不读取也不记录任何质量指标值**（沿用第四套同款回归的既有做法）。
- **仍未证**：第七版在第五套样本集上的任何表现；第五套样本集的成本与耗时；判据与口径尚未在读数之前冻结（按 `docs/phase6/62` §12，这一步必须早于任何读数）；`A-i` 对 L3 / L4 的实际影响；`X6` 的方向是否正确。

## 10. 契约、API 与默认策略

- **未改**API 字段、数据库列、内部契约、报告与观测 schema、artifact schema；`MixedFixtureManifest` **未加字段**；**未新增策略身份**（第七版身份已在 `J1` 落地）。
- 本轮**零产品代码改动**：全部改动落在 `backend/tests/` 的三个文件内。
- 默认策略仍为 **`heuristic@1`**。
- `docs/37` §3.1 **未触发**。

## 11. 不得声称

- 不得把本轮说成样本集已冻结、已落盘或已可用于验证；冻结与运行**各自需要单独授权**。
- 不得声称第七版在第五套样本集上表现如何——**该样本集上没有任何读数**。
- 不得把 `pytest` 用例数、正交性、确定性回放、毫秒级构建耗时说成质量证据。
- 不得把第五套样本集的节点与第四套的读数并列比较，也不得据此改动任何取值或配方。
- 不得改写四套既有样本集的任何常量、种子或清单文本；不得改写 `docs/phase6/62` 与 `docs/phase6/64` 的原文。
- 不得把本记录说成对 `docs/53c` / `55g` / `56h` / `57k` 任一签收结论的反转、修正或追认。

## 12. 本篇唯一下一步

据 `docs/phase6/62` §12 的冻结顺序，`J1` 与 `J1b` 已完成，仍未做的是：

- **冻结判据与口径**（照抄 `docs/phase6/60` §10 与 §14 的 `S1`）——必须**在任何读数之前**完成；
- **`J2`**：清单冻结（生成并落盘第五套清单到新外部证据目录）；
- **`J3`**：运行（`A` / `B` + 确定性补算，各自单独一轮）。

**建议先落「判据与口径冻结」**：它是 `J2` 的前置，且不消耗任何运行授权；冻结完成后再单独裁定 `J2` 与 `J3`。
