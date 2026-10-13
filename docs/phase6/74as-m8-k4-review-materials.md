# 74as M8：K-4 审查材料

> 日期：2026-10-13。
>
> **战役归属**：`74`（「新身份研发与独立验证」战役）。本文件是该战役的第 `46` 份文档，编号 `74as`。
>
> **历史关系**：承接已生效且实现复审通过的 `74ar`，以及 `74an` §9.3 只列问题、不给结论的 K-4 清单。本文件**不修改** `74r`、`74am`、`74an`、`74ao`、`74ap`、`74aq`、`74ar` 的正文。
>
> **编号范围**：双后缀 `as`。本文件不预占 `at` 及之后编号。
>
> **本文性质**：**K-4 审查材料**。只登记 a 至 f 的文件路径、函数名、夹具名和判定逻辑。d、e、f 另列缺口与选项。**不是** K-4 结论；**不是** C-2′；**不是** ③ 重跑。
>
> **效力限定（写死）**：
>
> - 审查方尚未对 a 至 f 作出通过或不通过的结论。本文件不代替该结论。
> - `74ar` 的实现复审通过，只表示代码与测试符合 `74ar`。它不重验 L3-J13、L4-J3、L4-J8、L4-J10、L2-J5、G-6。
> - 不建立 C-2′。`74af` 的 ③ 总体不通过持续有效。A 路径未成立。④–⑦ 未发生。
> - 不生成材料、campaign、摘要、seed 或键。不运行生成、测量或模拟。
> - 不改代码。不提交或推送。

## 1. 授权原文与范围

用户在实现复审通过之后授权（要点）：

```text
起草 K-4 审查材料 74as，只新增 docs/phase6/ 一个文件，并更新 docs/README.md。
内容限于 74an §9.3 所对应的 a 至 f：文件路径、函数名、夹具名、判定逻辑。
d、e、f 只写事实、缺口和选项，不写通过或不通过。
不运行任何生成、测量或模拟。
```

**属于本文件**：a 至 f 的只读事实。

**不属于本文件**：K-4 的通过或不通过；参考版本或评估版本是否升版的裁定；③ 的签署。

阅读时的仓库状态：`HEAD = origin/master = 1670e9d`。`74ar` 的实现提交是 `5c58c41`。本文件没有重跑 pytest 或 Ruff。

## 2. 文件级改动

| 文件 | 改动 |
|---|---|
| `docs/phase6/74as-m8-k4-review-materials.md` | **新增** |
| `docs/README.md` | 登记 `74as`；把 `74ar` 的现行状态改为实现复审通过、已落实；编号范围更新到 `74as` |

| 类别 | 内容 |
|---|---|
| 审查材料 | a 至 f 的路径、函数、夹具、缺口与选项 |
| **未执行** | K-4 结论、C-2′、③、生成、测量、模拟、改代码、提交、推送 |

## 3. 问题与 `74an` §9.3 的对应

`74an` §9.3 只列问题。下表是本次要准备的六项。本文件对每一项都不写审查结论。

| 项 | 问题 |
|---|---|
| **a** | 逐 κ 整数 seed 是否进入执行身份 |
| **b** | 协议版本 2 的配置摘要是否进入同一身份 |
| **c** | L-4 原句与逐 κ 来源句如何记载 |
| **d** | 包外源码是否被源码清单与 `code_identity` 覆盖 |
| **e** | 编排器能否覆盖两臂各自的公开投影 |
| **f** | 参考版本、评估版本是否被触及 |

`74an` §9.3 还问到 `samples` 与 `bluff_freq` 是否仍留在实例化口径，以及 `heuristic@1` 是否被写成不必审查。这两点的事实分别写在 §4 与 §9，仍然不是结论。

## 4. a. 逐 κ 整数 seed 与执行身份

判定逻辑在 `verification` 内：

| 步骤 | 位置 |
|---|---|
| 版本 2 载荷 | `backend/app/verification/instantiation.py` 的 `plan_payload`。协议 schema 为版本 2 时返回 `{"schema": "construction-plan-v2", "hands": ...}` |
| 座位材料 | 同文件 `_seat_payload`。版本 2 座位项只有 `materials`。`_material_record` 的字段是 `purpose_label`、`index_key`、`value` |
| 摘要条目 | 同文件 `instantiation_caliber_entries` 把该载荷的摘要写入 `construction-plan-digest` |
| 比对 | 同文件 `require_instantiation_caliber`。重算值与身份条目不同时失败，错误文本带条目名 |
| 主链 | `backend/app/verification/runner.py` 的 `verify_frozen_inputs` 调用 `require_instantiation_caliber` |

`value` 是该键上的整数。没有新增身份条目名。`KappaDecisionPlan` 仍在 `build_kappa_decision_plan` 里带 `samples` 与 `bluff_freq`；`_material_record` 不抄这两个字段。

夹具（均在内存中，不是实际材料）：

| 夹具 | 文件 | 它检查的事 |
|---|---|---|
| `test_version_two_plan_uses_closed_slices_and_integer_order` | `backend/tests/test_verification_coexistence.py` | 版本 2 对象的 `materials` 含整数；`samples`、`bluff_freq` 不在该项里；`"2"` 在 `"10"` 之前 |
| `test_version_two_identity_rejects_unwrapped_plan_digest` | 同上 | 版本 2 身份改记未包 `schema` 的数组摘要时，`require_instantiation_caliber` 失败并点名 `construction-plan-digest` |
| `test_version_one_identity_rejects_wrapped_plan_digest` | 同上 | 版本 1 身份改记 `construction-plan-v2` 包装摘要时，同样失败并点名该条目 |
| `test_version_one_plan_stays_a_single_material_array` | 同上 | 版本 1 仍是每座一个 `material` 的数组 |
| `test_kappa_plan_records_defaults_without_constructing_strategy` | `backend/tests/test_verification_v2_kappa.py` | 内存中的逐 κ 计划记录类默认值，且不构造策略 |
| `test_baseline_execution_caliber_comes_from_strategy_code` | `backend/tests/test_verification_construction.py` | `baseline-effective-samples` 为 `500`，`baseline-effective-bluff-freq` 为 `0.1` |

## 5. b. 协议版本 2 的配置摘要

| 步骤 | 位置 |
|---|---|
| 版本号 | `backend/app/verification/config.py` 的 `randomization_protocol_version`。版本 2 协议返回 `2`，否则返回 `1` |
| 摘要 | 同文件 `campaign_configuration_digest`。`DomainRunSpec` 的校验要求 `campaign` 等于这份摘要 |
| 身份条目 | `backend/app/verification/runner.py` 的 `_require_bound_execution_identity` 把重算结果与 `campaign-configuration-digest` 比对 |
| 版本 2 分支 | 同函数所在的 `verify_frozen_inputs`：版本 2 还要求 `spec.campaign` 等于以协议版本 `2` 算出的摘要 |
| 键上的 campaign | `backend/app/verification/materials.py` 的 `_hand_locations`。索引里的 `campaign` 必须等于规格上的 `campaign` |

夹具：

| 夹具 | 文件 | 它检查的事 |
|---|---|---|
| `test_v2_spec_campaign_matches_protocol_version_two` | `backend/tests/test_verification_v2_kappa.py` | 版本 2 规格的 `campaign` 等于协议版本 2 的配置摘要 |
| `test_v2_frozen_main_chain_binds_protocol_version_two` | 同上 | 冻结主链上，身份中的 `campaign-configuration-digest` 与该 `campaign` 相同，且 `randomization-protocol-schema` 为 `randomization-protocol-v2` |
| `test_v2_frozen_main_chain_rejects_version_one_campaign_digest` | 同上 | 把该条目换成版本 1 摘要时，`verify_frozen_inputs` 失败并点名 `campaign-configuration-digest` |
| `test_version_one_digest_cannot_label_v2_keys` | 同上 | 版本 1 摘要不能充当版本 2 键的 `campaign` |

## 6. c. 两句来源与待处理标记

| 步骤 | 位置 |
|---|---|
| 两句 | `backend/app/verification/execution_identity.py` 的 `SEED_SENTENCE_V1`、`SEED_SENTENCE_V2` |
| 按协议选择 | `backend/app/verification/instantiation.py` 的 `_seed_sentence`。版本 2 读 `per-kappa-arm_b-material`，版本 1 读 `per-hand-arm_b-material` |
| 标记 | `execution_identity.py` 的 `ARM_B_SCOPE_CONFLICT`，值为 `settled:v1-per-hand-arm_b-material/v2-per-kappa-arm_b-material`。两种协议的身份都写这一项 |
| 记录校验 | 同文件 `_require_entry_value`。来源句必须是上述两句之一；标记必须是 settled 字符串 |

夹具：

| 夹具 | 文件 | 它检查的事 |
|---|---|---|
| `test_swapped_seed_sentence_fails_for_each_protocol` | `backend/tests/test_verification_coexistence.py` | 版本 1 身份写成逐 κ 句、版本 2 身份写成逐手句，`require_instantiation_caliber` 都失败 |
| `test_pending_scope_marker_is_no_longer_legal` | 同上 | 待处理字符串不能构成合法身份记录 |
| `test_version_one_plan_stays_a_single_material_array` | 同上 | 版本 1 来源句仍是逐手句，标记为 settled 字符串 |
| `test_version_two_plan_uses_closed_slices_and_integer_order` | 同上 | 版本 2 来源句是逐 κ 句，标记与版本 1 相同 |
| `test_baseline_execution_caliber_comes_from_strategy_code` | `backend/tests/test_verification_construction.py` | 版本 1 夹具的来源句与 settled 标记 |
| `test_closed_categories_contain_forty_five_entries` | `backend/tests/test_verification_lock_caliber.py` | 封闭条目仍是 45 项；两句和 settled 字符串在已知普通文本集合里，待处理字符串不在 |

## 7. d. 源码清单与 `code_identity`

### 7.1 事实

执行身份里没有名为 `code_identity` 的条目。`backend/app/verification/` 的源码不出现这个名字。源码覆盖用的是清单摘要：

| 条目 | 类别 | 入口约束 |
|---|---|---|
| `runner-code-manifest-digest` | `runner` | `runner_category_entries` 要求入口为 `backend/app/verification/runner.py` |
| `generator-code-digest` | `randomization-protocol` | `_require_bound_execution_identity` 要求入口为 `backend/tools/material_generator.py` |
| `engine-code-manifest-digest` | `engine-and-strategy-code` | 比对调用方交来的清单，函数不规定入口路径 |
| `baseline-strategy-code-manifest-digest` | 同上 | 同上 |
| `under-test-strategy-code-manifest-digest` | 同上 | 同上 |
| `verification-code-manifest-digest` | 同上 | 同上 |

主链夹具 `fixture_source_manifests`（`backend/tests/verification_helpers.py`）给每份清单只放一个入口文件，再加 `backend/pyproject.toml` 与 `backend/uv.lock`。注释写明这些清单不读取仓库里的真实文件。入口分别是：

| 清单 | 夹具入口 |
|---|---|
| 运行器 | `backend/app/verification/runner.py` |
| 生成器 | `backend/tools/material_generator.py` |
| 引擎 | `backend/fixtures/engine.py` |
| 基线策略 | `backend/fixtures/baseline.py` |
| 被测策略 | `backend/fixtures/under_test.py` |
| 校验包 | `backend/fixtures/verification.py` |

四个包外或投影模块与这些入口的关系：

| 模块 | 谁导入它 | 是否被上述入口约束点名 |
|---|---|---|
| `backend/tools/material_generator.py` | 生成器清单的规定入口 | 是，`generator-code-digest` |
| `backend/tools/kappa_keyset.py` | `material_generator.py` 导入 `ClosedKeyset`、`validate_closed_keyset` | 否。入口校验不要求 `files` 含此路径。夹具的 `files` 只有生成器入口 |
| `backend/tools/kappa_orchestrator.py` | 测试 `test_kappa_orchestrator.py` 按文件路径加载。生成器源码测试断言编排器不导入生成器 | 否。六个清单入口都不是它 |
| `backend/app/poker/k2_public_projection.py` | `kappa_orchestrator.py` 导入 `sigma_public_hex`。`guards.py` 禁止 `verification` 导入该模块 | 否 |

`backend/tools/source_manifest.py` 的 `build_source_manifest` 会从入口的导入闭包收文件。当前冻结夹具不调用它来生成上述六份清单。本文件没有运行该工具。

`backend/tests/mixed_bot_states.py` 与 `tools/trainer/` 里另有名为 `code_identity` 的字段。它们不读取这四个模块，也不进入 `verification` 的 45 项。

### 7.2 缺口

- 编排器、键集模块、公开投影模块都没有被任何一条清单入口约束点名。
- 生成器入口被点名，但夹具不要求其导入闭包（含 `kappa_keyset.py`）出现在 `files` 里。
- 执行身份没有 `code_identity` 这一条目名。把「清单摘要」当成该名字，是本文件没有做的换名。

### 7.3 选项（不选定）

| 选项 | 做法 | 代价 |
|---|---|---|
| **入口即覆盖** | 维持现在的入口校验。依赖文件是否列入 `files`，留给以后的真实清单 | 键集、编排器、投影可以不在 45 项所绑定的清单里 |
| **闭包列入生成器清单** | 用 `build_source_manifest` 从生成器入口收闭包，使 `kappa_keyset.py` 进入 `generator-code-digest` 的 `files` | 编排器与投影仍不在这条闭包里，因为生成器不导入它们 |
| **另列入口** | 为编排器、投影各指定清单入口并重算摘要 | 若因此新增身份条目，封闭集合会超过 45 项。本文件不新增条目 |

## 8. e. 编排器与两臂投影

### 8.1 事实

`backend/tools/kappa_orchestrator.py` 的 `play_hand` 推进一手牌。`MaterialTable.require` 在表中找不到恰好一条键时抛出 `KappaMaterialMiss`。`play_hand` 的参数里没有生成器。

`_action_for_decision` 的分支：

| 条件 | 查的键 |
|---|---|
| 臂为 `under-test` 且当前座位是被测座位 | `arm_m`，键为 `(campaign, block, hand)`。动作由调用方给出。不调用 `create_strategy` |
| 其余决策 | 被测座位用 `arm_b`，其他座位用 `non_probed`。键为六字段，其中 `sigma_public` 来自当时的 `sigma_public_hex(state, legal)`。然后 `create_strategy("heuristic@1", seed=该整数)` |

查表发生在 `engine.apply_action` 之前。缺键时函数在提交动作之前返回异常。

夹具（`backend/tests/test_kappa_orchestrator.py`）：

| 夹具 | 它实际做到的事 |
|---|---|
| `test_material_table_rejects_seed_at_domain_bound` | 值等于 `2^256` 时建表失败 |
| `test_orchestrator_source_has_no_generator_callback` | 源码不导入生成器，不含 `os.urandom`，`play_hand` 无生成器参数 |
| `test_missing_key_stops_without_constructing_strategy` | 基线臂、空材料表：抛出 `KappaMaterialMiss`，`create_strategy` 未被调用，历史长度不变，牌局未结束 |
| `test_listed_key_injects_baseline_seed_once` | 基线臂、被测座位为 1、只提供座位 0 的一条 `non_probed`。该夹具里牌局结束，且只以 `heuristic@1` 与种子 `7` 构造一次 |
| `test_under_test_seat_uses_caller_action_not_a_new_identity` | 被测臂、被测座位为 0、只有一条 `arm_m`。调用方弃牌，`create_strategy` 未被调用 |

`play_hand` 不读取闭合集对象。它只查调用方已经放入 `MaterialTable` 的行。

### 8.2 缺口

- 没有夹具在同一手分别推进基线臂和被测臂。
- 没有夹具核对两臂非被测座位使用同一组六字段键和同一个整数。
- 没有夹具在第一次决策之后，用一个未列入表的新 `sigma_public` 再查一次，并断言 `KappaMaterialMiss`。
- `test_listed_key_injects_baseline_seed_once` 只覆盖基线臂的一个非被测决策。它不能代表分叉后的第二条投影。
- `test_missing_key_stops_without_constructing_strategy` 只覆盖基线臂的空表，不覆盖被测臂。

### 8.3 选项（不选定）

| 选项 | 做法 | 代价 |
|---|---|---|
| **补包外夹具** | 同一手两臂：非被测座位同键同值；基线被测座位查 `arm_b`；被测臂被测座位查 `arm_m`；未登记投影抛 `KappaMaterialMiss` 且不调用生成器 | 夹具仍在包外。不改 `verification` 的不可执行边界 |
| **维持现有夹具** | 把上一节的缺口留在审查记录里 | 审查方不能从现有夹具读出「两臂投影都已覆盖」 |

## 9. f. `poker/`、`strategy/`、`analysis/`

### 9.1 事实

`5c58c41` 的路径只有 `backend/app/verification/` 下五个模块，以及 `backend/tests/` 下四个测试文件。其中没有 `poker/`、`strategy/`、`analysis/`。

自 `8520302` 至 `1670e9d`，这三个目录里新增的文件只有 `backend/app/poker/k2_public_projection.py`，提交为 `ea0a0b9`。同一区间内，`backend/app/strategy/heuristic.py` 与 `backend/app/analysis/reference_identity.py` 没有提交。

基线标识仍是 `heuristic@1`：

| 位置 | 写法 |
|---|---|
| `backend/app/verification/config.py` | `BASELINE_IDENTIFIER = "heuristic@1"` |
| `backend/app/verification/execution_identity.py` | 固定文本 `baseline-identifier` 为 `heuristic@1` |
| `backend/tools/kappa_orchestrator.py` | `_BASELINE = "heuristic@1"`，传给 `create_strategy` |

参考与评估快照仍经 `execution_identity.reference_snapshot` 调用 `reference_identity()`。`reference_identity.py` 里的 `REFERENCE_VERSION` 与 `EVALUATION_VERSION` 在上述区间没有提交改动，源码中两者都写着 `1`，`REFERENCE_STRATEGY` 写着 `heuristic-conservative`。

`heuristic@1` 仍被写成基线成员的标识。本文件不把这个字符串写成「因此不必做 K-4」。

### 9.2 缺口

- `k2_public_projection.py` 在 `ea0a0b9` 进入 `poker/`。它不在 §7 的六个清单入口里。
- 文件未被 `5c58c41` 修改，不等于审查方已经接受「参考版本与评估版本保持不变」。那是 K-4 的问题，不是本文件的判定。

### 9.3 选项（不选定）

| 选项 | 做法 | 代价 |
|---|---|---|
| **按未改文件阅读** | 审查方把 `heuristic.py` 与 `reference_identity.py` 在 `8520302..1670e9d` 无提交，当作这两处源码未改的证据 | 仍要单独决定投影模块算不算触及 `poker/` 的审查范围 |
| **把投影模块纳入 f** | 把 `k2_public_projection.py` 与参考／评估版本是否升版放在同一次 K-4 结论里 | 该模块没有进入 `5c58c41`，结论要写明它来自 `ea0a0b9` |

## 10. 明确不主张

- 本文件不是 K-4 的通过或不通过。
- 不建立 C-2′。`74af` 的 ③ 总体不通过持续有效。
- A 路径未成立。④–⑦ 未发生。
- 不重验 L3-J13、L4-J3、L4-J8、L4-J10、L2-J5、G-6。独立 ③ 的签署人不得是本战役的推导方。
- 不生成材料、campaign、摘要、seed 或键。

## 11. 申请 K-4 复审

请审查方按 §4 至 §9 作出结论。本文件只提供路径、函数、夹具、缺口和选项。

**下一步唯一建议动作**：对 `74as` 作 K-4 复审。复审结论作出之前，不把 a 至 f 写成已经通过，不进入独立 ③，不进入 ④–⑦。
