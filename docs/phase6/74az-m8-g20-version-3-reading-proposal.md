# 74az M8：G-20 在版本 3 上的读法锁定与 74ay 机械缺口补齐记录

> 日期：2026-10-14。
>
> **战役归属**：`74`（「新身份研发与独立验证」战役）。本文件是该战役的第 `53` 份文档，编号 `74az`。
>
> **历史关系**：承接已生效的 `74ar`（L3-J13 点名 G-20）、已生效且已落实的 `74av`（版本 3 的送交材料对象、材料清单与决策记录）、内容审查通过的 `74aw`（K-4 重新复审通过（限定））、已签署的 `74ay`（登记版本 3 上的 G-20 与 V12-6 为未可机械执行）。本文件**不修改** `74ar`、`74av`、`74aw`、`74ax`、`74ay` 或任何其他历史正文。
>
> **编号范围**：双后缀 `az`。
>
> **本文性质**：**G-20 版本 3 读法锁定与 `74ay` 机械缺口补齐核验记录**（依简化工作流合并提案修订、读法锁定、补充测试断言与核验记录，不再拆分后续公文后缀）。
>
> **效力与边界（写死）**：
>
> - 正式锁定版本 3 上 G-20 的读法为**候选甲（覆盖仍闭合的 `deal` 与 `arm_m`）与候选乙（覆盖派生用途 `non_probed` 与 `arm_b`）并读**；候选丙维持排除，仅作对照。
> - 封闭条目保持 `45` 项，`execution_identity_schema` 保持 `1`，不改 `74av` 的版本 3 身份取值或摘要载荷，因此**不触发** `74av` §14 的失效传播，**不需要**复核 `74aw` 的 K-4 限定通过。
> - 补齐 `V12-6`（版本 2 送交材料摘要与清单、构造计划切片逐项一致）、版本 3 上 `G-20`、以及 `74as` §8.2 第 5 条（被测臂空表缺键不调用策略）的直接测试断言，使 `74ax`／`74ay` 范围内的全部机械判据均具备直接断言并**通过**（`V12-9` 仍为 `74ay` 已落盘的 `weleen` 自我声明）。
> - `74ag` §4 的 **`R-K2`（K-1、K-2、L-3 v3、K-4、版本 3 上 G-20、V12-6）至此全部闭合**；但战役层 ③ 总体门槛因 `74af` §7.1 的其余非 K-2 项（`V-1–V-4`、`domain_ab_*`、`域 B 分域链`）尚未闭合，仍诚实保持**不通过**，不宣称 A 路径已成立或 ④–⑦ 已发生。

## 1. 范围与工作流合并说明

本文件完成以下三件事并一次落盘：

1. **修正首轮审查指出的候选甲子项三对象含混问题**：将「四字段摘要对象 `supplied-materials-v3` 与 `material-manifest-digest` 的关系」和「材料清单 `MaterialManifest`（去掉 `master`）与手牌材料束 `HandMaterials` 的键和整数逐项一致」分列为两句，明确各自核对的对象与触发边界。
2. **直接选定并锁定版本 3 上 G-20 的读法**：采用「候选甲（覆盖 `deal` 与 `arm_m`）+ 候选乙（覆盖 `non_probed` 与 `arm_b`，由 `74av` §8 决策记录核验替代）」，维持候选丙排除。
3. **补齐直接断言夹具并执行核验**：在测试集中新增对 `V12-6`、版本 3 上 `G-20`、以及被测臂空表缺键停止的直接断言，运行 12 个验证测试文件与 Ruff 检查，闭合 `74ay` 留下的机械缺口。

## 2. 文件级改动与真实执行情况

| 文件 | 改动性质 |
|---|---|
| `docs/phase6/74az-m8-g20-version-3-reading-proposal.md` | **就地修订并定稿**：分列子项三两类对象、锁定甲+乙读法、登记补充测试与核验结果 |
| `docs/README.md` | 更新 `74az` 登记与目录总表括注 |
| `backend/tests/test_verification_coexistence.py` | 新增 `test_version_two_supplied_digest_matches_plan_slices_and_manifest`（直接断言 `V12-6`） |
| `backend/tests/test_verification_v3_derive.py` | 新增 `test_v3_supplied_materials_digest_and_retained_manifest_consistency`（直接断言版本 3 上的 `G-20`） |
| `backend/tests/test_kappa_orchestrator.py` | 新增 `test_missing_key_on_under_test_arm_stops_without_calling_strategy`（补齐 `74as` §8.2 第 5 条） |

| 命令（工作目录 `backend/`） | 退出码 | 结果 |
|---|---|---|
| `uv run ruff check tests/test_verification_coexistence.py tests/test_verification_v3_derive.py tests/test_kappa_orchestrator.py` | `0` | `All checks passed!` |
| `uv run pytest -q tests/test_verification_v3_derive.py tests/test_verification_v2_kappa.py tests/test_verification_coexistence.py tests/test_verification_construction.py tests/test_verification_lock_caliber.py tests/test_verification_payloads.py tests/test_verification_protocol.py tests/test_verification_runner.py tests/test_kappa_orchestrator.py tests/test_kappa_closed_keyset.py tests/test_material_generator.py tests/test_source_manifest_tool.py` | `0` | **`333 passed in 1.23s`**（`0 failed`，`0 skipped`） |

## 3. 引用的已有句子

### 3.1 `74ar` 对 G-20 的点名

`74ar` §11 的 L3-J13 行点名 G-20 与 K-5，其中 G-20 原文为：

> 送交材料载荷的构造、手间与手内排序的硬失败校验，以及 `supplied-materials-digest` 与 `material-manifest-digest` 同一份材料的一致性夹具

三个子项固定称为：

| 子项 | 原文所指 |
|---|---|
| **子项一** | 送交材料载荷的构造 |
| **子项二** | 手间与手内排序的硬失败校验 |
| **子项三** | `supplied-materials-digest` 与 `material-manifest-digest` 同一份材料的一致性夹具 |

### 3.2 `74av` §7、§8、§11

- **§7 送交材料对象**：采用「规则与主值」，不把送交材料改到运行后绑定，也不把 45 项增为 46 项。版本 3 的送交材料摘要对象 `supplied-materials-v3` 恰好含四个字段：`schema = "supplied-materials-v3"`、`protocol_schema = "randomization-protocol-v3"`、`master_read_index = 0`、`derivation_algorithm = "hmac-sha256-domain-separated-v1"`。`deal` 与 `arm_m` 的逐键整数不进入该四字段对象，仍在材料清单与逐读取记录里。
- **§8 材料清单与决策记录**：派生用途（`non_probed` 与 `arm_b`）不进入材料清单；清单只有 `master`（`read_index = 0`）以及仍走外部读取的 `deal` 与 `arm_m`。派生用途的核验落在另行提交的决策记录（`purpose_label`、`index_key`、`value`）上，决策记录不属于冻结身份的 45 项。
- **§11 条目计数**：六类仍是 `17 + 3 + 13 + 2 + 6 + 4 = 45`，`execution_identity_schema` 仍是 `1`。

### 3.3 `74ay` §5.2、§5.4、§5.5 的待补缺口

- **`74ay` §5.2 V12-6（及 §5.4 版本 1、2 的来源句与载荷）**：此前 12 个测试文件缺少对版本 2 `supplied-materials-digest` 按 `74ar` §9 重算、与材料清单键和整数逐项一致、以及与 `74ar` §7.2 同座 `materials` 条目逐项相同的直接断言。
- **`74ay` §5.5 版本 3 上的 G-20**：`74av` 未写出版本 3 上 G-20 的读法，故在 `74ay` 中记为未可机械执行。

## 4. 候选读法分析与正式锁定

### 4.1 候选甲：缩并读法（覆盖仍闭合的 `deal` 与 `arm_m`）

针对首轮审查指出的问题，`74ar` 点名的子项三涉及两个不同层面的对象：**一是运行前摘要对象 `supplied-materials-v3`（四字段）与 `material-manifest-digest`（含 `master`、`deal`、`arm_m`）之间的绑定关系**；**二是材料清单 `MaterialManifest`（去掉 `master`）与送交手牌材料束 `HandMaterials` 之间的键和整数逐项比对**。两句并列写清如下：

**字面写法（已采用并锁定，用于 `deal` 与 `arm_m`）：**

```text
版本 3 上，G-20 对仍闭合的用途 deal 与 arm_m 按以下三项核对：
1. 子项一（送交材料摘要对象的构造）：supplied-materials-digest 只按四字段对象重算
   （schema 为 supplied-materials-v3，protocol_schema 为 randomization-protocol-v3，
   master_read_index 为 0，derivation_algorithm 为 hmac-sha256-domain-separated-v1），
   不得增减字段，且与 construction-plan-v3 摘要不可互换；deal 与 arm_m 的逐键整数不进入该四字段对象。
2. 子项二（手间与手内排序的硬失败校验）：送交手牌材料束（HandMaterials）只保留 deal 与 arm_m，
   拒绝列入 non_probed、arm_b 与 master；核对手间 hand_ordinal 与手序计划严格对应，
   手内按用途次序与完整键升序排列且 deal 抽取序号从 0 起连续，不合则硬失败。
3. 子项三（摘要绑定与同一份材料一致性，分列两句）：
   (a) 四字段摘要对象与清单摘要之间：supplied-materials-digest 按上述四字段重算（不含逐键整数），
       其 master_read_index = 0 与材料清单首行及逐读取记录序号 0 的 master 定位对应；
   (b) 材料清单与手牌材料束之间：材料清单（MaterialManifest）去掉首行 master 后，
       其余全部条目（deal 与 arm_m）与手牌材料束（HandMaterials）中的键和整数必须逐项一致，
       并与闭合集及已接受读取记录逐键相等，缺键、多键或整数不符即硬失败。
```

| 维度 | 结论 |
|---|---|
| **45 项与执行身份** | 不增名，不加第 46 项，`execution_identity_schema` 保持 `1`，四字段对象与 `74av` §7 完全一致 |
| **是否触发 `74av` §14** | 子项三 (a) 与 (b) 均保持 `supplied-materials-v3` 为四字段对象、不把逐键整数写进该摘要载荷，因此**不改变**版本 3 的身份取值或摘要载荷，**不触发** `74av` §14 失效传播（反之，若把 `deal`/`arm_m` 逐键整数塞入 `supplied-materials-v3` 摘要对象，则会改变载荷并触发 §14，故不采用那种做法） |
| **`74aw` 是否需要复核** | **不需要**。`74aw` a–f 所依据的身份绑定与编排器实现未发生任何载荷或取值改变 |

### 4.2 候选乙：派生用途明确不适用，以决策记录核验替代（覆盖 `non_probed` 与 `arm_b`）

**字面写法（已采用并锁定，用于 `non_probed` 与 `arm_b`）：**

```text
版本 3 上，G-20 的子项一、子项二、子项三在运行前送交材料束与材料清单上对 non_probed 与 arm_b 不适用：
送交手牌材料束与材料清单均不列入这两用途的逐键整数，不为这两用途做手内材料束排序校验，
也不要求这两用途出现在材料清单与手牌材料束的逐键比对里。
这两用途的核验由 74av §8 的已提交决策记录核验替代：
每条决策记录字段恰好为 purpose_label、index_key、value；purpose_label 只许 non_probed 或 arm_b；
index_key 满足六字段合法性规则且同一完整键不重复；value 必须等于用已提交主值重算的 HMAC 输出，
键不合法或整数不等即硬失败。
决策记录不进入冻结身份的 45 项与 14 个承诺字段；这一替代不覆盖 deal 与 arm_m（后者由 §4.1 覆盖）。
```

| 维度 | 结论 |
|---|---|
| **45 项与执行身份** | 决策记录留在冻结身份之外，不增名，不改两份运行前摘要载荷 |
| **是否触发 `74av` §14** | **不触发** |
| **`74aw` 是否需要复核** | **不需要** |

### 4.3 候选丙：新绑定对象或第 46 项（维持排除，仅作对照）

`74av` §7 已明确排除「新增摘要条目／把 45 项增为 46 项」。若重新打开将改变版本 3 身份取值并触发 `74av` §14 失效传播与 K-4 复核。本记录**维持排除**，不重新打开。

### 4.4 正式锁定的合并规则

版本 3 上的 G-20 正式锁定为 **§4.1（候选甲，覆盖 `deal` 与 `arm_m`）与 §4.2（候选乙，覆盖 `non_probed` 与 `arm_b`）并读**。由此，四种用途在版本 3 上均有封闭、可机械执行的核验落点，且与 `74av` 已落盘代码完全自洽。

## 5. `74ay` 待补缺口的直接断言与核验结论

本轮在允许的非实际夹具下补充了 3 个直接测试函数，逐项闭合 `74ay` 留下的机械缺口：

| 缺口项 | 新增／对应直接断言夹具 | 核验内容 | 现行三态 |
|---|---|---|---|
| **版本 3 上的 G-20**（`74ay` §5.1、§5.5） | `test_verification_v3_derive.py::test_v3_supplied_materials_digest_and_retained_manifest_consistency` | 核对 `supplied-materials-v3` 四字段摘要重算、与 `construction-plan-v3` 及 `material-manifest-digest` 区分；核对 `require_supplied_materials_order` 对 `deal`/`arm_m` 反序及混入 `arm_b` 的硬失败拒绝；核对 `manifest` 首行为 `master`（`read_index = 0`），且去掉 `master` 后与 `bundle` 的 `deal`/`arm_m` 键和整数逐项一致，篡改任一整数即触发 `verify_manifest_binding` 失败；派生用途由 `test_decision_record_accepts_a_legal_key_and_rejects_bad_ones` 核对 | **通过** |
| **V12-6** 与 **§5.4 版本 1、2 的来源句与载荷**（`74ay` §5.2、§5.4） | `test_verification_coexistence.py::test_version_two_supplied_digest_matches_plan_slices_and_manifest` | 核对版本 2 `materials_digest` 按 `74ar` §9 的无 `schema` 数组重算；核对 `material_manifest` 与 `bundle` 的全部 `(purpose_label, index_key, value)` 集合与条数逐项相等，篡改整数即触发 `verify_manifest_binding` 失败；核对 `plan_payload`（`74ar` §7.2）各手各臂各座位的 `materials` 与 `bundle` 对应切片逐项相等 | **通过** |
| **`74as` §8.2 第 5 条**（`74ax` §9 登记的被测臂空表缺键测试） | `test_kappa_orchestrator.py::test_missing_key_on_under_test_arm_stops_without_calling_strategy` | 核对 `arm="under-test"` 在空材料表下缺 `arm_m` 时立即抛出 `KappaMaterialMiss`，不调用 `under_test_choose` 回调，也不构造基线策略或推进牌局 | **通过** |
| **`C-2′`（手间零协方差前提，`74w` §11.2 / `74j` §6.3）** | `test_kappa_orchestrator.py`、`test_verification_v3_derive.py`、`protocol.py` | `K-1`（`74ak`）、`K-2`（`74ai`）、`L-3 v3`（`74av`）、`K-4`（`74aw`）已全部落盘；每手每臂新建引擎与每次决策新建策略实例（`play_hand`）、随机输入仅来自 `Z_h`、无跨手可变状态、`L3-J*` 与版本 3 `G-20`／`V12-6` 全部机械通过 | **`R-K2` 链已完整闭合**（C-2′ 的 K-2／L-3 阻断已消除） |

## 6. 当前战役状态汇总

| 对象 | 状态 |
|---|---|
| `74ax`／`74ay` 独立 ③ 重验范围 | 经本记录补齐后，范围内全部机械判据（`L3-J13`、`L4-J3`、`L4-J8`、`L4-J10`、`L2-J5`、`G-6`、`V12-1`–`V12-8`、`V12-10`、版本 3 各项、保留项、版本 3 上 `G-20`）均为**通过**；`V12-9` 保持 `weleen` 在 `74ay` 的已签署自我声明 |
| `74ag` §4 `R-K2` 整改项 | **已全部闭合** |
| 战役层 ③ 总体门槛（`74af` §7.1） | 除 `R-K2` 外的其余项（`V-1–V-4`、`domain_ab_*`、`域 B 分域链`）待下一批处理，故战役层 ③ 总体门槛仍记为**不通过**；A 路径**未**成立；④–⑦ **未**发生 |
