# 74t M8：第一层锁定（`74s`）实现落地记录

> 日期：2026-10-09。
>
> **战役归属**：`74`（「新身份研发与独立验证」战役）。本文件是该战役的第 `21` 份文档，编号 `74t`。
>
> **历史关系**：承接已通过内容审查的 `74s`（§9 实现方案提案；SHA-256 `d7fb1a1db4a2a98c7a569fe80f6f9f7142fd747db6eb3f6a98063b6d8a5282a8`，`438` 行）与已生效的 `74r`（③ 侧四类对象第一层锁定文本，锁定版本 1；SHA-256 `27c132801e7cc4da77be1cdf4425c04a52fb41f1fdbb03168558f119fdf33a09`）。本文件登记审查方授权下对 `74s` 所映射的 G-1 至 G-20（**G-7 未实施**）在提交 `e74ef23` 中的代码落地范围、路径、行数，以及开发方在实现轮次中报告并已执行的检查命令及其**非质量结论**边界。本文件**不修改** `74r`、`74q`、`74s` 或任何历史文档正文；**不**更新 `docs/README.md` 索引（索引同步须在本记录内容审查通过后另行授权）。
>
> **编号范围**：本文件使用根编号 `74` 的后缀 `t`；`74a`–`74s` 已占用，本文件不预占任何后续编号。`73` 已关闭、不得续号。
>
> **本文性质**：**实现落地记录**。只记录已入库的实现工件、审查历程与机械量登记，不含新的设计选择，也不作锁定或裁定。
>
> **效力限定（写死）**：
>
> - 本文件**不**使 ②、③、④、⑤、⑥、⑦ 中任一步骤成立或完成；A 路径**仍未成立**；C-1′、C-2′、F-0 **均未建立**；**不**创建 `mixed-local@9`。
> - **不**生成或冻结随机材料、seed、清单、节点、摘要、`code_identity` 或身份；五个 ② 侧对象仍未锁定；⑥ 最终运行冻结未发生。
> - 实现内容与代码审查**通过**只表示 `e74ef23` 相对 `74r` 版本 1 与 `74s` 的映射关系已被审查方接受；**不等于**质量证据，**不等于**可进入 ③。
> - 不改 `poker/**`、`strategy/**`、`analysis/**`、`storage/**`、`frontend/**`、`tools/trainer/**`、数据库、`uv.lock`、`AGENTS.md`；登记截断条款仍截止于 `bb152f1`：本文件是对已形成文档的独立落地记录，**不是**对 `bb152f1` 之后提交的逐次回填；`eff3fb1`、`c79a22e`、`e74ef23` 均不在逐提交登记链内。

## 1. 授权原文与审查历程

### 1.1 实现授权（审查方，摘要）

在 `74s` 内容审查通过后，审查方授权实施 G-1 至 G-20（**G-7 保持不实施**）：允许修改提案点名的 `backend/app/verification/` 模块、新增包内 `source_manifest.py`、新增 `backend/tools/source_manifest.py` 与 `backend/tools/material_generator.py`、以及提案列明的测试；允许运行 `74s` §8 的定向 Ruff、全仓 Ruff、定向 pytest、全量 pytest。**明确禁止**提交、推送实现代码（该禁止在后续轮次解除）。

### 1.2 内容与代码审查（三轮）

| 轮次 | 审查方结论 | 授权范围 |
|---|---|---|
| 第一轮 | **不通过**。五项阻断：相对导入入口无法实际加载；执行身份摘要多数只查 64 位十六进制；`str.isdigit()` 接受非 ASCII 数字；基线默认参数未完全封闭；动态导入别名可绕过且子进程可能写字节码 | 仅修上述五项 |
| 第二轮 | **暂不通过**。不授权提交或推送。两类遗留：① `source-interface-id` / `environment-record` 未绑定当前协议；② `getattr`、容器或下标传播、`exec_module` 等间接加载仍可绕过，且实际加载集合未要求包含全部入口 | 仅修上述两类；允许重跑 `74s` §8 |
| 第三轮 | **通过**。未发现新的阻断项。确认来源/环境绑定、间接加载保守失败、入口须出现在实际加载集合、G-1–G-20（G-7 未实施）按 `74s` 落地、包内仍不可执行 | 授权提交且仅限 22 个后端文件；授权推送至 `master`；**不**授权生成实际材料、推进 ②③ |

第三轮审查方**未**独立复跑 Ruff、pytest、构建、补算、生成或测量。

### 1.3 本文件落盘授权（用户裁定，2026-10-09）

用户裁定：应新增 `74t` 独立实现落地记录；`docs/README.md` 应在该记录内容审查通过后另行更新索引，但**不应**回填逐提交登记。

唯一下一步授权原文：

```text
仅授权新建 docs/phase6/74t-m8-first-layer-lock-implementation-record.md，如实登记 e74ef23 对 74s G-1–G-20（G-7 未实施）的落地范围、路径、行数和已报告的开发检查结果及其非质量结论边界；完成后仅申请内容审查，不修改索引、不提交、不推送、不运行测试或生成材料，也不推进②③。
```

## 2. 提交事实与文件级改动

### 2.1 Git 事实（只读核验，本文件落盘前）

| 项 | 值 |
|---|---|
| 父提交 | `c79a22e62d180ba401001295c558fb05f54aafb9`（`docs: index the passed first-layer lock implementation plan`） |
| 实现提交 | `e74ef2311fab5160b0c351ab9b399cf155f50e02` |
| 提交说明首行 | `feat(verification): land first-layer lock implementation per 74s` |
| 提交时间（作者/提交者） | 2026-10-09 16:02:33 +0800 |
| 变更规模 | 22 文件，`+3143` / `−174` |
| `HEAD` 与 `origin/master`（落盘前） | 均为 `e74ef2311fab5160b0c351ab9b399cf155f50e02`；ahead / behind `0 / 0`；工作区干净 |
| 提交范围外 | 未触及任何 `docs/**`、`AGENTS.md`、`poker/**`、`strategy/**`、`api/**` 等 |

### 2.2 文件级清单（`e74ef23` 落点；行数为该提交在 `HEAD` 上的 `wc -l` 终态）

**包内 `backend/app/verification/`（12 个文件，其中 1 个新增）**

| 路径 | 改动 | 行数 |
|---|---|---|
| `backend/app/verification/__init__.py` | 修改 | 292 |
| `backend/app/verification/config.py` | 修改 | 288 |
| `backend/app/verification/deal.py` | 修改 | 150 |
| `backend/app/verification/errors.py` | 修改 | 60 |
| `backend/app/verification/execution_identity.py` | 修改 | 316 |
| `backend/app/verification/guards.py` | 修改 | 111 |
| `backend/app/verification/identity.py` | 修改 | 152 |
| `backend/app/verification/instantiation.py` | 修改 | 712 |
| `backend/app/verification/materials.py` | 修改 | 153 |
| `backend/app/verification/protocol.py` | 修改 | 923 |
| `backend/app/verification/runner.py` | 修改 | 563 |
| `backend/app/verification/source_manifest.py` | **新增** | 106 |

**包外工具 `backend/tools/`（2 个新增）**

| 路径 | 改动 | 行数 |
|---|---|---|
| `backend/tools/source_manifest.py` | **新增** | 500 |
| `backend/tools/material_generator.py` | **新增** | 212 |

**测试 `backend/tests/`（8 个文件，其中 4 个新增）**

| 路径 | 改动 | 行数 |
|---|---|---|
| `backend/tests/verification_helpers.py` | 修改 | 839 |
| `backend/tests/test_verification_protocol.py` | 修改 | 986 |
| `backend/tests/test_verification_construction.py` | 修改 | 637 |
| `backend/tests/test_verification_runner.py` | 修改 | 1660 |
| `backend/tests/test_verification_lock_caliber.py` | **新增** | 227 |
| `backend/tests/test_verification_payloads.py` | **新增** | 115 |
| `backend/tests/test_source_manifest_tool.py` | **新增** | 230 |
| `backend/tests/test_material_generator.py` | **新增** | 130 |

上述 22 文件在 `HEAD` 合计 `9362` 行（含本表所列路径的全部行，含空行；**不**含未改动的同包其他文件如 `digests.py`）。

### 2.3 本文件落盘时的执行类别

| 类别 | 内容 |
|---|---|
| 只读核验 | `git rev-parse HEAD origin/master`、`git status -sb`、`git show --stat e74ef23`、`git log -1 e74ef23`；对 22 个路径 `wc -l`；确认 `docs/phase6/74t*` 落盘前不存在；确认 `74r`、`74s` 工作区无改动 |
| 开发回归 / 质量验证 / 构建 | **均未执行**（本文件授权禁止） |
| 未执行 | 索引更新、提交、推送、材料生成、②③ |

## 3. G-1 至 G-20 落地对照（相对 `74s` §6；G-7 未实施）

下列为 `e74ef23` 中的**实现落点摘要**，规范依据仍为 `74r` 版本 1；与 `74s` 映射表不一致时以 `74r` 为准。

| 缺口 | 生产 / 包内 | 包外 | 落地要点（登记用语） |
|---|---|---|---|
| G-1 | `deal._require_player_count`、`DomainRunSpec` | — | 人数 `2`–`23` 整数，拒绝布尔 |
| G-2 | `config.py`：`CampaignLockVersions`、`CampaignConfiguration`、显式 `campaign`/`block`、纯摘要函数与 `build_domain_run_spec` | — | 摘要不接受已构造 `DomainRunSpec`；未用 `model_construct` 绕过校验 |
| G-3 / G-5 | `protocol.py`：`integer_fields`；`block`/`hand`/`draw`/`seat` 无前导零 ASCII 十进制 | — | `0` 合法；`00`、`+1`、全角/印度/上标数字等非法 |
| G-4 / G-20 | `materials.require_supplied_materials_order`；`instantiation.materials_digest(..., spec)`；`verify_manifest_binding(..., spec)` | — | 手序、`3N+6`、索引 `campaign`/`block`/`hand` 与规格及两处手序核对 |
| G-6 / G-19 | `identity.require_explicit_seed` 上界；`instantiation` 构造计划 `material.value`；`baseline-effective-seed` 固定 `per-hand-arm_b-material` | — | seed ∈ `[0, 2^256)` |
| G-7 | — | — | **未修改**（裁定不实施） |
| G-8 / G-12 | `execution_identity.py` 六类 41 项；`runner.py` 的 `runner_category_entries` / `runner_flow_digest`；`guards.py` 的 `injection_precheck_category_entries` / `injection_precheck_rules_digest` | — | `flow_step_entries` / `precheck_rule_entries` 保留旧名，不再构造覆盖清单 |
| G-9 | — | — | 测试补强（大端、32 字节、越界、布尔） |
| G-10 | `protocol.py` 两生成时刻 | — | `YYYY-MM-DDTHH:MM:SS.ffffffZ`、有效公历、仅 `Z`、起不晚于止 |
| G-11 | `source_manifest.py`：只校验显式对象并重算摘要，不读盘 | `tools/source_manifest.py`：`build_source_manifest(entrypoints, *, workspace_root)` | 闭包外模块、间接加载（含 `getattr`/容器传播/`exec_module`）、入口未在实际加载集合则失败；子进程 `-B`、`PYTHONDONTWRITEBYTECODE`、`dont_write_bytecode` |
| G-13 | `protocol.py`：`rejection_rule`、`protocol_digest` 为 `randomization-protocol-v1` 封闭载荷 | — | `purposes` 次序等于 `traversal_order` |
| G-14 / G-15 | `schedule_digest` 等为 `schedule-v1` 等锁定载荷；`deal`/`protocol`/`instantiation`/`runner`/`guards` 各映射摘要 | — | 不计算供 ⑥ 冻结的实际 campaign 摘要 |
| G-16 | `read_record_digest` 按物理 `read_index`；`entry_counts`/`rejection_counts` 按 `traversal_order` | — | 不先排序再摘要 |
| G-17 | `instantiation.py`：`import math`、负零 `copysign`、`encode_baseline_entry_payload` 词法 `0.1`、位置默认值封闭、递归常量禁浮点 | — | 白名单追加 `math`、`datetime` |
| G-18 | — | `tools/material_generator.py`：`GeneratedMaterials`、`generate_materials`；源码内直接 `os.urandom` | 失败不返回对象；测试可替换 `os.urandom` |
| 主链 | `runner.verify_frozen_inputs` 六份显式源码清单参数 | — | 重算并核对协议、来源接口、环境记录、材料、审计、campaign、schedule、生成器及运行器/四项代码清单；来源与环境须等于 `spec.protocol` 对应字段 |

## 4. 包边界、夹具与内部契约

- **不可执行**：延续 `74p` 登记；`e74ef23` 未向 `runner.py` 增加可推进牌局的路径。材料生成与源码清单的读盘、闭包收集、子进程加载核验均在 `backend/tools/`，验证包不导入 `backend/tools/`。
- **`verify_frozen_inputs`**：较 `74p` 增加六份必填显式源码清单参数；若干公开函数签名增加必填 `spec`；冻结摘要项与协议载荷按 `74r`/`74s` 封闭。
- **夹具（非实际）**：测试使用锁定常数 `mixed-local@9` 字符串、夹具 campaign/块 `0`/手号、六位微秒生成时刻、手造生成器清单摘要等；**不是**身份创建、注册或实际生成产物。承诺中的 `generator_code_digest` 来自手造清单重算，不是仓库真实源码清单摘要。
- **公开 API、数据库、报告 schema、包络数值**：未改。`73b` 必要冻结项 28 项未变。未触发 `docs/phase4/37` §3.1。默认策略仍为 `heuristic@1`。

## 5. 开发方报告的检查命令（机械登记，非质量结论）

下列命令在实现轮次中由开发方执行并报告结果；审查方在第三轮**未**独立复验。本表**不构成**质量证据，**不构成**进入 ③ 的依据，**不**替代内容与代码审查结论。

| 命令（工作目录 `backend/`） | 开发方报告结果 |
|---|---|
| 定向 `uv run ruff check`（`74s` §8 所列验证相关路径） | 通过 |
| `uv run ruff check .`（全仓） | 仅有 **4** 项既有诊断，全部位于**未改动**的 `backend/tests/test_distribution_observation_consistency.py`（`I001`、`UP035`、两处 `E501`）；本轮未修该文件 |
| 定向 `uv run pytest`（`74s` §8 所列） | **249** 通过 |
| `uv run pytest -q`（全量） | **1914** 通过，**3** 跳过（既有跳过） |
| `npm run build` | 未执行 |

## 6. 步骤状态与未授权事项

| 项 | 状态 |
|---|---|
| `74s` 方案 | 已通过内容审查；`e74ef23` 为实现落地，非方案修订 |
| 实现内容与代码审查 | 审查方第三轮**通过**并已授权提交推送 |
| 本文件 `74t` | 首版落盘；**待**内容审查 |
| `docs/README.md` 索引 | **未**更新（须本文件审查通过后另行授权） |
| ②–⑦、`mixed-local@9`、实际材料/seed/清单/`code_identity` | **未**发生 |

## 7. 申请内容审查

请审查方对 `docs/phase6/74t-m8-first-layer-lock-implementation-record.md`（本文件）做**内容审查**，核验：

1. 提交 `e74ef23` 的 22 文件清单、行数与 `+3143/−174` 是否与仓库一致；
2. G-1–G-20（G-7 未实施）对照是否与 `74s`/`74r` 一致且无夸大；
3. 审查历程、授权边界与「检查命令非质量结论」表述是否准确；
4. 效力限定是否未暗示 ②③ 或锁定已成立。

审查通过之前：不修改索引、不提交、不推送、不运行测试或构建、不生成材料、不推进 ②③。
