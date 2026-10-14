# 74ay M8：独立 ③ 重验执行记录

> 日期：2026-10-14。
>
> **战役归属**：`74`（「新身份研发与独立验证」战役）。本文件是该战役的第 `52` 份文档，编号 `74ay`。
>
> **历史关系**：执行内容审查通过的 `74ax`。必核范围只有 `74ax` §7.1、§7.2、§7.3、§7.4，以及 §9 登记的版本 3 上 G-20。F-J*、C-1′、F-0、AB-1′、AB-0 不重开，指向 `74af`。本文件**不修改** `74ax` 或任何其他既有正文。
>
> **编号范围**：双后缀 `ay`。本文件不预占 `az` 及之后编号。
>
> **本文性质**：**独立 ③ 重验的执行记录**。逐条登记允许输入下的三态，并分列三层。**不**建立 C-2′。**不**改写 K-4。**不**使 A 路径成立。**不**进入 ④–⑦。总体门槛按 `74ae` §7.4 写成**不通过**。本记录不用「③ 通过」这个口径。
>
> **效力限定（写死）**：
>
> - 签署人为 `weleen`，已于 2026-10-14 在 §2、§8 作出自我声明并签名。签署不改变任何一条的三态，也不把总体门槛改成通过。
> - 通过只覆盖当次输入，以及记录当时引用的锁定版本（`74r` v1、`74am` v2、`74ar`、`74av`）。
> - 夹具产物不是实际材料。回归读数不是本记录的通过证据。
> - **不**生成实际主值、材料、seed、节点、键、清单、campaign 摘要或 `code_identity`。**不**创建 `mixed-local@9`。
> - **不**改代码或测试。**不**运行全量 pytest 或 Ruff。**不**提交或推送。

## 1. 授权原文与范围

用户授权原文（摘要）：

```text
授权十八：执行独立 ③ 重验，并落盘执行记录。
执行依据：74ax（内容审查通过）。
必核范围只有 §7.1 六条、§7.2 的 V12-1 至 V12-10、§7.3 版本 3 各项、
§7.4 保留项，以及 §9 的「版本 3 上 G-20 无读法」。
F-J*、C-1′、F-0、AB-1′、AB-0 不重开，指向 74af。
签署人 weleen。签署栏与自我声明栏暂留空。
载体：新增 74ay。更新 docs/README.md 的登记、编号范围与一条新日志。
夹具只跑授权点名的 12 个测试文件。纸面重算不得落成仓库新文件。
G-20 在版本 3 上只能登记「未可机械执行」。
```

上方授权原文写于执行当时，签署栏当时留空。`weleen` 事后本人填写 §2、§8，不属于代签。

**不属于本文件**：由他人代 `weleen` 签署；建立 C-2′；改写 `74at` 或 `74aw`；④–⑦。

## 2. 签署

| 项 | 登记 |
|---|---|
| 指定签署人 | `weleen` |
| 自我声明 | 已由 `weleen` 填写（2026-10-14），全文见 §8 |
| 签名 | `weleen`（2026-10-14），见 §8 |
| 本文件 | 落盘执行记录。不把推导方或 `74av` 作者写成签署人 |

**签署人 `weleen` 自我声明（写死）**：

```text
本人（weleen）未把推导方或 74av 作者的身份当作自己的签署身份；
未读取任何实际身份输出、实际主值或生产 campaign 作为核验输入；
未撰写 74av、74ax 正文。
本声明为签署人自我声明，不以任何 AI 辅助执行名称替代签署人身份或独立性。
```

用户在索引日志中确认 `weleen` 不属于推导方。该确认不是本栏的自我声明；自我声明以上方文字为准。

## 3. 仓库状态与命令

### 3.1 开头

| 项 | 登记 |
|---|---|
| `HEAD` | `80e5a606288770fdb7f695f3bd930efcfc65c696`（`80e5a60`） |
| 说明 | `docs(phase6): add 74ax independent step-3 reverification specification` |
| 分支 | `master` 与 `origin/master` 同步，ahead / behind 为 `0 / 0` |
| 工作区 | 干净 |
| `74ay` | 执行前未被占用 |

### 3.2 命令

工作目录除另注外为仓库根。夹具运行的工作目录是 `backend/`，因为 `pyproject` 在该目录。路径写成 `tests/…`，对应授权里的那 12 个 `backend/tests/` 文件。

| 次序 | 命令 | 退出码 | 结果 | 用途 |
|---|---|---|---|---|
| 1 | `git rev-parse HEAD`；`git status -sb`；`git status --porcelain`；`git log -1` | 0 | 见 §3.1 | 开头状态。不是通过证据 |
| 2 | 在仓库根执行 `uv run pytest -q tests/test_verification_v3_derive.py`（及同批其余文件名） | **4** | `ERROR: file or directory not found`；`no tests ran` | 路径写错。**0** 个测试。不作为证据 |
| 3 | 在 `backend/` 执行下面的夹具命令 | **0** | **330 passed**，**0 failed**，**0 skipped**，1.05s | 非实际夹具。失败 id：无。跳过 id：无 |
| 4 | 同一 12 个文件加 `--collect-only` | **0** | `330 tests collected` | 只收集 id，没有再跑夹具 |
| 5 | 在 `backend/` 执行 §3.3 的 `uv run python -c` | **0** | 打印 `match True`、`in_range True`、`digest_len 32` | 固定字节的 HMAC 重算。不是实际材料 |

次序 3 的命令原文：

```text
uv run pytest -q \
  tests/test_verification_v3_derive.py \
  tests/test_verification_v2_kappa.py \
  tests/test_verification_coexistence.py \
  tests/test_verification_construction.py \
  tests/test_verification_lock_caliber.py \
  tests/test_verification_payloads.py \
  tests/test_verification_protocol.py \
  tests/test_verification_runner.py \
  tests/test_kappa_orchestrator.py \
  tests/test_kappa_closed_keyset.py \
  tests/test_material_generator.py \
  tests/test_source_manifest_tool.py
```

输入类型：非实际夹具。通过 id 是这次收集到的 330 个节点；本记录在各条里点名用作证据的 id。没有把开发方报告的 `2000 passed` 或 Ruff 四项当作证据。未运行全量 pytest，未运行 Ruff。

### 3.3 固定字节重算（未写入仓库）

```text
import hmac, hashlib
from app.verification.kappa_derive import derive_kappa_seed
master = b"\x11" * 32
purpose = "non_probed"
key = ("ab" * 32, "0", "1", "0", "0", "ab")
def pref(text):
    raw = text.encode("utf-8")
    return len(raw).to_bytes(4, "big") + raw
message = b"".join([pref("kappa-seed-derive-v1"), pref(purpose), *(pref(field) for field in key)])
value = int.from_bytes(hmac.new(master, message, hashlib.sha256).digest(), "big")
same = value == derive_kappa_seed(master, purpose, key)
print("match", same)
print("in_range", 0 <= value < (1 << 256))
print("digest_len", len(hmac.new(master, message, hashlib.sha256).digest()))
```

主值是固定的 32 个 `0x11`。没有调用 `os.urandom`。同一消息得到同一整数，整数落在 `[0, 2^256)`。这只证明可复核，不证明独立或均匀。

## 4. 不重开的项

| 项 | 本记录 |
|---|---|
| F-J* | 不重开。已有记录见 `74af` |
| C-1′、F-0、AB-1′、AB-0 | 不重开，不改写 `74af` 的三态 |
| C-2′ | 照写**未建立**。本次清单不把它标成已建立 |

## 5. 逐条结论

三态沿 `74ax` §7.5。源码行号是执行时读到的位置。

### 5.1 `74ax` §7.1

| 编号 | 三态 | 输入 |
|---|---|---|
| **L3-J13**（已有读法） | **通过** | 这一态只覆盖已有直接断言的部分：版本 1 键形（`protocol.py` 约 394–433 行，`arm_b` 为 `(campaign, block, hand)`）；版本 2 的六字段键形（`_V2_FIELDS` 约 971–976 行）与构造计划切片、排序入口（`test_version_two_plan_uses_closed_slices_and_integer_order`、`test_slice_gaps_bad_order_and_illegal_values_fail`）；版本 3 的 `non_probed` 与 `arm_b` 无外部读取（§5.3）；K-5 在这两用途上三方缺席，缺席不是已经核验；用途次序 `V3_TRAVERSAL` 约 1041 行；冲突标记见 L4-J3。**不覆盖**版本 2 送交材料摘要，也不覆盖 G-20 的「送交材料与清单是同一份材料」的一致性。见 V12-6 |
| **版本 3 上的 G-20** | **未可机械执行** | `74av` 未写这一读法。本记录不自造。见 §5.5 |
| **L4-J3** | **通过** | `execution_identity.py` 24–29 行：三句来源句分开；冲突标记逐字为 `settled:v1-per-hand-arm_b-material/v2-per-kappa-arm_b-material/v3-per-kappa-derived-arm_b-material`。夹具 `test_verification_v3_derive.py::test_seed_sentences_are_not_interchangeable`、`test_old_settled_text_fails_on_every_protocol_version`；`test_verification_lock_caliber.py` 中待处理字符串不在 `KNOWN_PLAIN_TEXTS` |
| **L4-J8** | **通过** | 这一态只覆盖：版本 1 与版本 2 的**构造计划**摘要不能互换（`test_v1_digest_is_unchanged_and_differs_from_v2`、`test_version_one_identity_rejects_wrapped_plan_digest`、`test_version_two_identity_rejects_unwrapped_plan_digest`）；版本 3 只按两个 v3 schema（`instantiation.py` `_v3_binding_payload` 217–226 行；`test_version_payloads_do_not_reuse_each_other`）；整数 `1` 或 `2` 的配置摘要不能绑定版本 3（`test_v3_frozen_main_chain_rejects_other_campaign_digests`）。**不覆盖**版本 2 送交材料摘要按 `74ar` §9 重算。见 V12-6 |
| **L4-J10** | **通过** | 这一态只覆盖：来源句与冲突标记（L4-J3）；版本 1、2 的构造计划载荷与版本 3 的四个字段（L4-J8 已覆盖的部分）；上界 `[0, 2^256)`（`kappa_derive.py` 91–92 行与 §3.3）；版本 3 运行前对象不含逐 κ 整数。**不覆盖**版本 2 送交材料摘要，见 V12-6 |
| **L2-J5** | **通过** | 空值与布尔失败：`instantiation.py` `_require_plan_material_value` 821–827 行；`test_verification_construction.py::test_explicit_seed_rejects_empty_and_non_integer`。版本 2 按切片逐条：`test_slice_gaps_bad_order_and_illegal_values_fail`。版本 3 的派生整数在决策记录上逐条核对，见 §5.3 |
| **G-6** | **通过** | 与 L2-J5 同一上界。版本 3 构造计划对象不含逐 κ 整数，上界改在决策记录：`plan_payload` 864–867 行与 `require_derived_decision_records` |

`execution_identity_schema` 的唯一赋值在 `config.py` 34 行，整数仍是 `1`。它不在本次通过范围里。本记录不讨论参考版本或评估版本是否升版。

### 5.2 `74ax` §7.2

| 编号 | 三态 | 输入 |
|---|---|---|
| V12-1 | **通过** | 版本 1 来源句 `per-hand-arm_b-material`：`_seed_sentence` 776–783 行；`test_verification_construction.py::test_baseline_execution_caliber_comes_from_strategy_code`。构造计划数组形状：`test_version_one_plan_stays_a_single_material_array`。六字段 `arm_b` 不能进入版本 1：`protocol.py` 425–427 行的版本 1 键是 `(campaign, block, hand)`；`test_v1_schema_rejects_v2_key_shape` |
| V12-2 | **通过** | 版本 2 来源句 `per-kappa-arm_b-material`：`SEED_SENTENCE_V2`。手级 `arm_b` 键不是版本 2 键形：`_V2_FIELDS["arm_b"]` 为六字段；`protocol_declares_v2_keys` 在字段不符时返回假，`protocol.py` 1470–1486 行 |
| V12-3 | **通过** | 版本 1、2、3 都用 §5.1 的新冲突标记。待处理字符串与 `74ar` §5 的旧 settled 字符串都失败：`test_pending_scope_marker_is_no_longer_legal`、`test_old_settled_text_fails_on_every_protocol_version` |
| V12-4 | **通过** | `test_v1_digest_is_unchanged_and_differs_from_v2`；版本 1 与版本 2 的计划摘要不能互换，见 L4-J8 的两则拒绝夹具 |
| V12-5 | **通过** | `test_version_two_plan_uses_closed_slices_and_integer_order`。切片以外失败且不补读：`test_slice_gaps_bad_order_and_illegal_values_fail`；`test_kappa_closed_keyset.py::test_missing_purpose_does_not_read`、`test_duplicate_v2_key_does_not_read` |
| V12-6 | **未可机械执行** | 已有夹具没有直接断言这些子项：版本 2 的 `supplied-materials-digest` 按 `74ar` §9 重算；与材料清单的键和整数逐项一致；与 `74ar` §7.2 同一座位的条目逐项相同。`test_version_two_plan_uses_closed_slices_and_integer_order` 断言的是构造计划切片和排序入口，不是送交材料摘要。`test_manifest_order_and_seed_domain_are_checked` 只断言反序清单被拒绝。授权的 12 个文件里没有看到直接对应的断言。本轮没有为补证再跑测试，也没有新写测试。这些子项在出现直接断言之前不得判通过，所以 V12-6 整体不判通过。排序拒绝与构造计划切片仍分别记在 V12-5，不挪到本行充作通过 |
| V12-7 | **通过** | `test_manifest_order_and_seed_domain_are_checked`；`test_kappa_orchestrator.py::test_material_table_rejects_seed_at_domain_bound`；§3.3 |
| V12-8 | **通过** | `instantiation.py` 810–811 行仍是 `500` 与 `0.1`。派生消息只有域标签、用途和六字段，`kappa_derive.py` 28–35 行，没有这两项 |
| V12-9 | **未可机械执行** | 「签署人不是本战役的推导方」不能在允许输入下机械核对。授权指定了 `weleen`，索引日志里有用户确认。`weleen` 已在 §2、§8 作出自我声明（2026-10-14）。自我声明是签署人自述，不是在允许输入下的机械核对，所以这一态不改成通过，仍记未可机械执行。这一态不影响「核验记录已完整」 |
| V12-10 | **通过** | `test_swapped_seed_sentence_fails_for_each_protocol`；`test_pending_scope_marker_is_no_longer_legal`；`KNOWN_PLAIN_TEXTS` 含三句来源句与新冲突标记，不含待处理字符串 |

### 5.3 `74ax` §7.3

| 项 | 三态 | 输入 |
|---|---|---|
| 主值 | **通过** | 这一态只覆盖：32 字节、`read_index = 0`、`entry_counts["master"] == 1`（`material_generator.py` 347–348、394–409 行；`test_fixture_generation_keeps_baseline_counts_at_zero`，主值 `b"\x02" * 32`）；实际路径传入主值则失败（333–335 行；`test_actual_path_rejects_injected_master`）；夹具用固定 `entropy`，不调用 `os.urandom`（338–361 行）；八个读取字段（394–404 行）；`campaign` 按整数 `3` 重算（`verification_helpers.py` `v3_run_spec` 1184–1192 行）。**不覆盖**「注入值不得记成该来源标识」。该分句见下一行，本记录不判通过，也不判不通过 |
| 主值来源标识的已登记观察 | **不裁定** | 夹具承诺仍抄协议上的 `python-os-urandom@1`（`material_generator.py` 439–440 行）。`74ax` §7.3 写明这一观察不裁定通过或不通过。夹具产物不是实际材料 |
| `deal` 与 `arm_m` | **通过** | 生成前闭合：`_generate_v3` 373 行先 `validate_closed_keyset`。逐键读取与 `deal` 的拒绝重读：`_read_supplied` 475–499 行。版本 3 夹具闭合集只有 `deal` 与 `arm_m`：`test_verification_v3_derive.py` `_closed` |
| `non_probed` 与 `arm_b` | **通过** | 不进入上述闭合集，接受与拒绝条数都是 0：`test_fixture_generation_keeps_baseline_counts_at_zero`。两标签仍在 `V3_TRAVERSAL`。次序是 `master`、`deal`、`non_probed`、`arm_m`、`arm_b` |
| 决策记录的包内核对 | **通过** | 字段恰好三项，非法键在整数比较之前失败：`kappa_derive.py` 67–98 行。键不合法且 HMAC 已相等仍失败：`test_decision_record_accepts_a_legal_key_and_rejects_bad_ones` 里 `arm_b` 座位与被测座位不符的那一条。同一完整键重复失败、整数不符失败：同一测试。编排器调用 `derive_kappa_seed` 是注入，不是核验：`kappa_orchestrator.py` 145–153 行。`kappa_derive.py` 不调用 `EncodeK2PublicV1`，不创建引擎，不提交行动，不推进牌局。包内看不到漏记：该函数说明写明看不见对局过程。⑦ 对账没有做 |
| 三份清单的路径 | **通过** | `source_manifest.py` `require_v3_manifest_files` 109–126 行。缺派生模块、缺投影、缺编排器、或编排器出现在引擎 `entrypoints` 即失败：`test_manifest_files_must_name_derive_projection_and_orchestrator`、`test_v3_frozen_main_chain_rejects_incomplete_manifests`。生成器入口只有 `backend/tools/material_generator.py`：`material_generator.py` 37、375 行 |
| 摘要 | **通过** | 四个字段与两个 schema：`_v3_binding_payload`。交叉重算失败：`test_version_payloads_do_not_reuse_each_other` 与 L4-J8 的版本拒绝夹具。整数 `3`：`test_v3_frozen_main_chain_rejects_other_campaign_digests` |
| 条目与版本 1、2 | **通过** | 这一态只覆盖条目数与 schema：`execution_identity.py` 47–110 行是 `17 + 3 + 13 + 2 + 6 + 4 = 45`，没有名为 `code_identity` 的条目，`execution_identity_schema` 仍是 `1`。不覆盖 V12-6。该条是未可机械执行，见 §5.2 |
| 两个基线常数 | **通过** | 同 V12-8 |

校验包不导入可执行牌局路径：`test_verification_v2_kappa.py::test_verification_package_does_not_import_execution_paths`；`test_derive_module_does_not_import_execution_boundaries`。

### 5.4 `74ax` §7.4 保留项

| 保留项 | 三态 | 输入 |
|---|---|---|
| `deal` 与 `arm_m` 的键、外部读取、闭合与拒绝重读 | **通过** | 见 §5.3。`74am` §6.3 对仍闭合用途继续有效：`test_kappa_closed_keyset.py::test_two_projections_cannot_share_an_event_index` |
| 六字段键形与同键同值 | **通过** | `kappa_derive.py` 26–27、97–98 行；`test_same_key_matches_and_distinct_projection_differs`；§3.3 |
| 十六进制 | **通过** | `kappa_derive.py` 141–146 行；决策记录测试里的大写 `AB` 被拒绝 |
| `[0, 2^256)` 与 32 字节大端 | **通过** | `int.from_bytes(..., "big")`：`material_generator.py` 393 行与 `kappa_derive.py` 38 行；§3.3 |
| 拒绝标识 | **通过** | `protocol.py` `REJECTION_RULE_ID`；`test_verification_v2_kappa.py::test_protocol_v2_keeps_rejection_id_and_commitment_fields`；`test_verification_payloads.py::test_payloads_keep_closed_fields` |
| 14 个承诺字段 | **通过** | `protocol.py` `_COMMITMENT_FIELD_NAMES` 979–994 行，共 14 个。决策记录不在其中 |
| 来源标识 | **通过** | 实际路径的标识仍是 `python-os-urandom@1`：`protocol.py` `LOCKED_SOURCE_INTERFACE`。夹具承诺抄写同一标识的观察见 §5.3，不另裁定 |
| 版本 1、2 的来源句与载荷 | **未可机械执行** | 来源句与冲突标记有直接断言，见 V12-1、V12-2、V12-3、V12-10 与 L4-J3，那些行仍是通过。送交材料按 `74ar` §9 重算没有直接断言，与 V12-6 是同一缺口。整行因此不判通过，避免用来源句的通过盖住载荷 |

### 5.5 G-20

`74ar` 点名的 G-20 包含送交材料的构造、手间与手内排序，以及送交材料摘要与材料清单是同一份材料。版本 2 与版本 3 分开记。

**版本 2。** 排序拒绝有夹具，见 V12-5。G-20 在版本 2 上的「送交材料摘要与清单一致性」没有直接断言，不判通过，见 V12-6。V12-5 不代替这一项。

**版本 3。** `74av` 没有写下 G-20 在版本 3 上的读法。本记录不自造读法。三态：**未可机械执行**。不得写成通过。这与上一款不是同一件事。

## 6. 三层结论

| 层级 | 结论 |
|---|---|
| **核验记录已完整** | **是**。§5.1 至 §5.4 每条都有编号、输入类型和三态。未可机械执行的有：版本 3 上的 G-20、V12-6、V12-9，以及 §5.4 的「版本 1、2 的来源句与载荷」（送交材料载荷与 V12-6 同一缺口）。L3-J13、L4-J8、L4-J10 的通过不覆盖版本 2 送交材料摘要。该缺口仍记在 V12-6。三态之一即可，不要求全部通过。F-J* 与未重开的前提指向 `74af`，没有改写成新结论 |
| **单项前提已建立** | C-2′：**未建立**。C-1′、F-0、AB-1′、AB-0 不在本次必核名单，三态仍以 `74af` 为准 |
| **③ 总体门槛** | **不通过** |

总体门槛写成不通过，是因为 C-2′ 未建立，并且版本 3 上的 G-20 为未可机械执行。V12-6、V12-9，以及「版本 1、2 的来源句与载荷」也是未可机械执行，同样不能把总体门槛写成通过。依据是 `74ae` §7.4 与 `74ax` §9 的写法规则。本记录已由 `weleen` 于 2026-10-14 签署，构成已落盘的 ③ 重验结论，结论为不通过。它也不替换 `74af` 的已落盘不通过。

**不构成**：C-2′ 已建立；K-4 被改写；A 路径成立；进入 ④–⑦；`heuristic@1` 或 `mixed-local` 的质量结论；Nash、NashConv 或 exploitability。

## 7. 结尾工作区

写完本文件并更新索引之后，`git status --porcelain` 只有两项：`docs/README.md` 被修改，本文件未跟踪。夹具运行、`--collect-only` 与 §3.3 的重算没有再改其他被跟踪文件，也没有往仓库写入脚本。实际路径的 `os.urandom(32)` 没有被调用。

## 8. 签署栏

```text
签署人 ID：weleen

自我声明：
本人（weleen）确认已按 74ax 规格与本次授权审阅本记录正文。
本人未把推导方或 74av 作者的身份当作自己的签署身份；
未读取任何实际身份输出、实际主值或生产 campaign 作为核验输入；
未撰写 74av、74ax 正文。
本声明为本人自我声明，不以 AI 辅助落盘名义替代本人身份或独立性。

核验记录已完整：是。
C-2′：未建立。
③ 总体门槛通过：否（不通过）。
V12-9：本声明是自我声明，不是机械核对；V12-9 仍按 §5.2 登记为未可机械执行。

日期：2026-10-14
签名：weleen
```
