# 31 M8：多人 CFR 候选 A——Campaign 冻结就绪性只读复核

> 日期：2026-09-17。
>
> 实测起点：`git status --short --branch` 输出 `## master...origin/master`（无改动），`git log -8 --oneline` 顶部为 `9881050 docs: record execution integrity review and fixes`，`git rev-parse HEAD` 与 `git rev-parse origin/master` 均为 `9881050a53fb6f8e7e74a998153b43910cd5dee6`。工作区干净，本地与远端一致，与期望基线完全相符。
>
> 状态：本轮是**只读复核**。未修改任何代码，未启动 A6/A7 受预算训练，未生成任何真实 campaign manifest、preflight spec、attestation、策略工件、measurement 或 ledger，未 commit、未 push。
>
> 本轮重跑了离线校验（`ruff` 与 `pytest`），结果记在第 5 节；除此之外没有产生任何质量、策略或资源证据。
>
> 本文是 `docs/30` 之后的新一轮记录，编号 31。`docs/20` 至 `docs/30` 未被改写。
>
> **重要操作提示**：本文一经写入工作区即成为未跟踪文件，而 `runtime_identity` 的干净工作区断言使用 `--untracked-files=all`，因此本文的存在本身会阻止真实 A6/A7 启动。详见第 7 节。

## 1. 本轮边界

本文只记录：

1. 与 `9881050` 实际一致的工作区与提交状态；
2. 对 `docs/30` 第 4 节缺口（4.1–4.5）、第 10 节决策与修复、第 11 节 P2 三项遗留的逐条只读复核结论；
3. 本轮只读复核**新发现**的一项实现与声明不一致之处；
4. 真实 A6/A7 启动前必须先解决的操作性前置；
5. 只需用户一次性冻结的 canonical 输入清单；
6. 是否建议启动真实 A6/A7 的判断。

本文不构成实际训练授权，不构成代码修改授权，不提供任何新的质量、资源、策略或收敛证据。

## 2. 复核范围

只读检查了以下实现与测试（按父子执行顺序）：

| 环节 | 文件 |
|---|---|
| campaign 冻结、受控标识、互斥 lease、终态 ledger | `campaign.py` |
| campaign 授权入口、preflight 文件绑定、授权预算校验 | `campaign_executor.py` |
| 父端监督入口、lease 守卫、run 目录归属断言 | `supervised_executor.py` |
| 子进程入口与最小环境身份重验 | `manifest_executor.py`、`runtime_identity.py` |
| 执行快照固化与子端身份比对 | `execution_snapshot.py` |
| 子进程阶段编排与阶段墙钟截止 | `orchestration.py` |
| 父端最终 measurement 与深度复验 | `supervised_measurement.py` |
| 独占工件根与封存清单 | `artifact_inventory.py` |
| 本机 `ps` 采样式进程组监督 | `supervisor.py` |
| estimator preflight spec/attestation 读写与重演 | `estimator_preflight.py` |
| 受控训练阶段限值 | `control.py` |
| 规范 JSON 原子读写 | `safeio.py` |
| 公开 API 面 | `__init__.py` |
| 相关测试 | `tests/test_multiplayer_campaign*.py`、`tests/test_multiplayer_supervised_executor.py` 等 |

## 3. 已闭合项的复核结论

`docs/30` 第 4 节的 4.1–4.5、D2 的阶段截止、第 10.5 节前三项遗留，逐条对照代码复核如下，**均确认已闭合**：

| 原发现 | 代码事实 |
|---|---|
| 4.1 A6/A7 的 campaign authorization 只是参数存在性检查 | `supervised_executor.run_supervised_manifest_executor` 已移除可自述的 `campaign_authorization_id` / `campaign_experiment_identity`，改为必填 `campaign_lease`；`_require_campaign_authorization` 对非 N9 强制要求 lease，并调用 `verify_active_lease` 复核签发凭证、锁仍持有、ledger 已记录该 lease，同时比对 lease 绑定的 experiment 身份、campaign commit 与 trainer version。`CampaignLease.__post_init__` 以私有哨兵拒绝模块外构造。N9 boundary 是唯一免 lease 路径。 |
| 4.2 受控标识字符集缺失、run 目录可越界 | `campaign._ID_PATTERN = [a-z0-9][a-z0-9-]{0,63}` 统一约束 `campaign_id`、`authorization_id`、`manifest_id`、`record_id`；`CampaignLease.run_root()` 与 `owns_path()` 均经 `_is_within` 做解析后归属断言；`create_run_directories()` 是唯一建目录入口，已存在即拒绝，父端另以 `_require_lease_paths` 断言工件根与快照根都在该 lease 的 run 目录内。 |
| 4.3 campaign `peak_rss_limit_bytes` 未被使用 | `campaign_executor._validate_authorization_budget` 已加入 `plan.manifest.rss_hard_limit_bytes > campaign.peak_rss_limit_bytes` 即拒绝，且有对应测试断言不创建 run 目录。 |
| 4.4 `export` / `measurement` 阶段预算被声明但从未执行 | `orchestration._stage_deadline` 统一构造"仍可继续"检查（同时响应外部取消与 RSS 预警）；`_run_a6_a7` 在导出后校验导出阶段，`_write_record` 在 measurement payload 构造后与写入后各校验一次，超预算即失败且不生成测量记录；测试覆盖导出与 measurement 分别跨预算。 |
| 4.5 异常路径 lease 不落终态、残留工件不清理不记账 | `campaign_executor.run_campaign_authorization` 在 `except BaseException` 中写终态事件：可安全清理声明工件时记 `failed`，`ArtifactInventoryError` 时记 `inventory-failed`，随后重新抛出原异常。 |
| 4.7 preflight 未绑定冻结 spec 文件 | `run_campaign_authorization` 已改为接收 `preflight_spec_path` 与 `preflight_attestation_path`，以 `load_preflight_spec()` / `load_attestation()` 按真实字节重算身份，再依次 `verify_campaign_preflight` 与 `verify_attestation`；原先"从 attestation 反向重建 spec"的私有函数已删除。 |
| 第 11.3 节完成态缺陷 | `experiment_record.strategy_identity_payload()` 为父子共用唯一构造器，两侧形状一致，`supervised_measurement._validate_child_execution` 保留逐字段严格相等。 |

另外确认 `docs/30` 第 4.6 节按 D4 仍保持"只披露"状态（ledger 无哈希链），第 10.5 节第 4、5 项仍作为持续披露项保留。

## 4. 本轮只读复核的新发现

除下列一条外，未发现新的代码级实现缺陷。已重建的执行链骨架（快照 → 父子身份 → lease → 独占工件根 → 父端最终 measurement → 封存清单）在代码层面自洽。

### 4.1 A6/A7 存在第二条公开入口，不经 `run_campaign_authorization` 的 preflight 与预算门禁

`docs/30` 第 10.2 节的修复把 A6/A7 的强制点放在 **`CampaignLease`** 上。但 lease 的签发者 `acquire_campaign_lease` 本身就是公开 API，而 `create_campaign_manifest` 只做结构校验——`preflight_attestation` 在 campaign manifest 里只是一个身份三元组（`record_id` / `sha256` / `byte_length`），**不要求对应文件存在**。

于是存在这样一条完全正常的调用路径：

```text
create_campaign_manifest(<内存构造的 payload>)
  -> acquire_campaign_lease(root, campaign, authorization_id)
  -> run_supervised_manifest_executor(..., campaign_lease=lease)
```

这条路径上：

- `run_supervised_manifest_executor` 只调用 `_require_campaign_authorization`（lease 有效 + experiment 身份 / campaign commit / trainer version 一致）与 `_require_lease_paths`（目录归属），**不读取也不校验 preflight spec/attestation 文件**；
- 它也**不调用** `_validate_authorization_budget`，因此 experiment manifest 的 `cpu_limit_milliseconds`、五阶段墙钟之和、`rss_hard_limit_bytes`、`retained_artifact_limit_bytes` 与其 authorization 预留、与 campaign envelope 之间的绑定（即 4.3 的修复）在此路径上都不生效——supervisor 的硬限直接取自 experiment manifest 自身。

另外，`orchestration.run_manifested_experiment` 也是公开导出函数，只需要一个 `SupervisorSession`，完全不涉及 lease，可作为第三条入口直接运行 A6/A7 的子端编排。

**后果**：用户"执行时的硬前置"中的两句——"A6/A7 只能经 `run_campaign_authorization` 执行"与"必须引用真实的冻结 preflight spec 与 attestation 文件"——在代码上只在**调用方选择全门禁入口**时成立，不是机制强制。campaign 的 CPU / 墙钟 / 峰值 RSS / 工件 envelope 同理。

**性质界定**：这不是对抗性绕过，也不构成外部攻击面（需要调用方主动编写代码选择低层入口，且仍然会经过真实 lease、ledger 记录、run 目录归属、父子身份与工件封存）。它与 `docs/30` 第 10.5 节第 5 项披露的"lease 守卫是 Python 级 API 约束"同源，但比该表述更具体：**即使持有合法 campaign，也可以跳过 preflight 与资源绑定**。

**需要用户决策（二选一，本轮未改代码）**：

1. **接受为流程约束**：由唯一驱动脚本只调用 `run_campaign_authorization`，并在冻结清单与执行记录中明确写出"只能经该入口"是流程约定而非代码强制；
2. **要求加固**：把 preflight 校验与授权预算校验下沉——例如在 `acquire_campaign_lease` 内校验 campaign 引用的 attestation 身份，或在 `run_supervised_manifest_executor` 的非 N9 路径上、用 `lease.campaign` 与 `lease.authorization` 补齐 `_validate_authorization_budget` 的同一组比较。

### 4.2 已确认成立、但值得随本轮一并披露的实现细节

以下不是缺陷，仅作为执行前的事实备忘：

1. `manifest_executor` 构造的 `SupervisorSession` 使用 `rss_reader=lambda: 0`，因此子端阶段限值只能自主执行**墙钟**；RSS 硬停完全依赖父端 `ps` 采样。这与 `docs/30` 第 8 节的披露一致，但意味着子端记录中的 `peak_rss_bytes` 不是真实 RSS。
2. 策略 artifact v1 的 `quality` 块由 `_not_measured_quality()` 填充、`resources` 块为静态零值与静态字节数，导出只依赖 `MCCFRResult`；`orchestration._run_a6_a7` 在评估之前即完成导出，因此 profile/probe 结果、真实资源与 campaign 回执**不会**写回 v1 artifact，边界 7 成立。
3. `run_campaign_authorization` 成功路径上的 `lease.finalize(...)` 位于 `try` 之外；若 `finalize` 自身失败，ledger 只会留下 `leased` 事件（与 4.5 已修路径不同的残余形态）。
4. 父端 `run_supervised_manifest_executor` 与 `campaign_executor` 各自读取一次 experiment manifest（`docs/30` 第 4.8 节已记录）。由于两处都要求 identity 与 lease 中冻结的 authorization 一致，无法通过替换文件构造可比对的 TOCTOU，仍仅为设计备注。

## 5. 本轮离线校验

在冻结提交 `9881050`（工作区干净）上重跑：

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
169 passed in 147.25s (0:02:27)
```

这与 `docs/30` 第 11.4 节记录的 `169 passed` 一致；本轮只新增了只读复核，代码未变，因此结果相同属预期。该命令只覆盖规则、有限 estimator preflight、N9 boundary、父子协议、快照、封存清单、campaign 预算/lease、阶段截止与 A6 受监督**单元**成功路径；它**不是** A6/A7 训练、profile/probe、跨 seed 稳定性或资源基准证据。

## 6. 需要用户一次性冻结的内容（除第 4.1 节决策外，无需再改代码）

1. Campaign ID、实际 Git commit（须含 `b9c4554`，即 `9881050` 或其后，且所有代码改动已提交）、trainer version、实际 worktree 与解释器语义；
2. A6/A7 每条 authorization：player count、iterations、`average_strategy_start_iteration`、单一显式 seed、strategy/measurement 槽位名与上限、单次 CPU、各阶段墙钟、RSS 硬停与预警、artifact reservation；
3. Campaign 总 CPU、总墙钟、峰值 RSS、总 artifact 上限（以及 `max_concurrency = 1`）；
4. 是否执行 A6/A7 full-chance profile、预注册 probe、跨 seed 稳定性实验，以及各自的通过 / 停止 / 保留 / 失败阈值；
5. 新建、空、独占的 artifact root 位置与保留策略；
6. 真实 estimator preflight spec 文件与由其实跑得到且 `passed == true` 的 attestation 文件（注意 attestation 内嵌的 `code_identity` 必须等于 campaign 的 commit 与 trainer version，`verify_campaign_preflight` 会强制比对）；
7. 一次性实际执行授权；
8. 是否允许 commit/push 实验文档或 ledger（默认不允许）。

不得以单元测试 fixture、示例 manifest、测试 attestation 或 N9 boundary 测试替代上述任一输入。

## 7. 启动真实 A6/A7 前必须先解决的操作性前置

`runtime_identity.inspect_runtime_identity` 使用固定 `/usr/bin/git` 执行：

```text
git status --porcelain=v1 --untracked-files=all
```

并**要求输出为空**，否则拒绝启动。本轮实测该命令在当前工作区输出 0 行（`__pycache__/`、`.venv/`、`.pytest_cache/`、`.ruff_cache/` 均被 `.gitignore` 覆盖）。

因此：**本文写入后工作区立即变为脏**。在默认"不允许 commit"的授权下，只要 `docs/31-*.md` 停留在工作区，真实 A6/A7 就无法通过父端与子端的身份核验。用户需要明确选择其一：

1. 授权先提交文档，再以提交后的新 HEAD 作为冻结 commit（推荐，且与 `docs/30` 的处理方式一致——`9881050` 正是提交后的 `docs/30`）；
2. 在启动实验前把本文移出工作区（或删除），并把复核记录保存在工作区之外；
3. 先不启动实验，仅保留本文作为本轮的只读记录。

无论哪种选择，**冻结的 commit 必须等于启动时刻的实际 `HEAD`**，且必须同时等于 campaign manifest 与 experiment manifest 中的 `code_identity.git_commit`。

同一断言还带来一条容易被忽略的布置约束：`git status --untracked-files=all` 覆盖工作树内的**全部**未忽略文件，因此下面这些执行期输入都**不能放在工作树内**（否则它们自身就会让工作区变脏并使实验 fail-closed）：

- campaign 根目录与 `campaign-ledger.json`、`.campaign.lock`；
- 每条 authorization 的 `runs/<authorization_id>/` 及其 `artifacts/`、`inputs/`；
- 源 experiment / probe manifest 文件；
- estimator preflight spec 与 attestation 文件。

建议把它们统一放在工作树之外的独立目录（例如用户主目录下的专用 campaign 目录），并在冻结清单中写明该绝对路径。唯一 `working_directory` 必须指向工作树本身。

## 8. 结论

- 已确认 `docs/30` 第 4.1–4.5、D2 阶段截止、第 11 节三项遗留全部闭合；离线校验与上一轮一致（169 passed）。
- 本轮新发现 **1 项实现与声明不一致**（第 4.1 节）：A6/A7 存在一条持有合法 lease 但不经 preflight 与授权预算门禁的公开入口。它不影响"按唯一脚本调用 `run_campaign_authorization`"的执行正确性，但使"只能经该入口"这句话在代码层面不成立。
- 因此给出如下判断：**在第 4.1 节决策完成、第 7 节操作性前置解决、第 6 节冻结清单全部齐备之前，不建议启动真实 A6/A7。** 若用户选择第 4.1 节的方案 1（接受为流程约束），其余条件满足后即可启动；若选择方案 2（要求加固），则需要一轮小范围的 `tools/trainer/` 代码改动与单元测试，再重复一次只读就绪复核。
- 除上述两点外，未发现其余代码级阻塞项。

> 上述第 4.1 节的判断已由用户在随后以"先做 D1 方案 B"授权加固；加固与复验结果见第 11 节，第 4.1 节的两个后果已闭合。

## 9. 持续披露与解释边界

- 当前 macOS supervisor 是本机 `ps` 采样式进程组监督：在阈值命中时终止已知进程组与已观察后代，**不是不可逃逸的内核级 containment**，不能表述为此类能力。
- campaign ledger 无哈希链（`docs/30` D4），"不可重试"依赖代码流程而非账本自身的完整性证明；lease 守卫是 Python 级 API 约束，不是对抗性安全边界。
- 即使真实 campaign 完成，候选 A 也不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 单元测试、N9 boundary、有限 estimator preflight、短路径回归、采样累计量、常和性质或策略稳定性，都不等于 A6/A7 训练结果、质量证据或资源基准。
- 本轮未启动任何实际 A6/A7 训练、profile/probe、稳定性实验或资源基准，未产生任何策略、质量或资源证据；本文不对未执行的事项作任何声称。

## 10. 本轮未做事项

除第 11 节所述、经用户授权的加固外，未运行 A6/A7 受预算训练、profile/probe、跨 seed 稳定性实验、N9 boundary 或资源基准；未生成真实 campaign manifest、preflight spec、attestation、策略 JSON、measurement、ledger、日志或检查点；未 commit、未 push；未改写 `docs/20` 至 `docs/30`。

## 11. 获授权加固（D1 方案 B）与复验结果

第 4.1 节的两个后果经用户授权后本轮闭合。改动只涉及 `tools/trainer/src/multiplayer_cfr/` 的四个文件与两个测试文件，未触碰 `kuhn_cfr`、后端、前端、锁文件或真实数据库，未启动任何实际训练或受预算运行。

### 11.1 改动内容

1. **门禁收敛为唯一实现。** 新增 `campaign.require_campaign_preflight_files()` 与 `campaign.require_authorization_within_reservation()`，前者按真实文件字节读取冻结 spec 与 attestation、校验 campaign 引用身份与代码版本、并重演固定 oracle/production 核验；后者为原先只存在于授权入口内的资源预留比较（CPU、阶段墙钟之和、保留工件、以及 experiment RSS 硬停阈值与 campaign 峰值 RSS 上限的同口径绑定）。两者均可从包根导入。
2. **父端监督入口强制 preflight 与预留。** `run_supervised_manifest_executor()` 新增 `preflight_spec_path` / `preflight_attestation_path`；`_require_campaign_authorization()` 在创建快照与工件之前依次校验：lease 仍有效 → experiment 身份 / campaign commit / trainer version 一致 → 不超授权预留 → preflight 证据复验通过。A6/A7 缺少任一 preflight 路径即拒绝；N9 boundary 不持有 lease，因此也不接受 preflight 证据（避免把独立采样伪装成授权实验）。
3. **授权入口改为复用同一实现。** `campaign_executor._validate_authorization_budget()` 被删除，由共用的 `require_authorization_within_reservation()` 取代；preflight 校验改为调用 `require_campaign_preflight_files()`。授权入口仍**在获取 lease 之前**完成这两项校验，因此门禁失败不会消耗一次性 authorization（该性质未被本次加固改变）。

### 11.2 加固后的不变式

- 取得 lease 只有 `acquire_campaign_lease` 一条途径，而**任何** A6/A7 受监督执行都必须同时提供有效 lease 与真实冻结 preflight 证据，且 experiment 资源上限必须落在该 authorization 的预留与 campaign envelope 之内；两条入口不再有强弱之分。
- 仍然存在的 Python 级残留：`orchestration.run_manifested_experiment()`、`manifest_executor` 子进程入口与 `mccfr.train()` 属于**训练原语**。直接调用它们运行 A6/A7 属于流程违规，不由任何 Python 级检查拦截——这与"直接调用训练函数"同属一类，需要在文档与执行纪律上约束，不能表述为机制强制。

### 11.3 新增测试

1. 持有真实 lease 但省略 preflight 证据时，父端在启动子进程前失败，且工件根与快照根保持为空。
2. 绕过授权入口、直接使用 lease 执行时，父端仍拒绝超出授权 CPU 预留的 experiment，工件根与快照根保持为空。
3. N9 boundary 传入 preflight 证据时被拒绝。
4. 既有 A6 受监督成功路径改为携带真实冻结 spec 与由其实跑得到的 attestation；既有的"lease 绑定到另一 experiment 被拒"路径同样改为提供真实证据，使其仍因身份不一致而失败。

### 11.4 复验结果

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
172 passed in 154.42s (0:02:34)
```

`169` 增至 `172` 即第 11.3 节的 3 条新测试。这些仍是**单元测试**：使用临时 Git 工作树、显式 1 iteration 与本地 supervisor 原语，不是受预算实验，也不能作为 A6/A7 训练质量、策略质量、RSS 或耗时的实测证据。

另记录一次测量事实：本机单次 estimator preflight 的首次重演约 65 秒（oracle 首次构建），同进程内后续重演约 0.2 秒（oracle 命中进程内缓存）。因此"授权入口 + 父端入口各校验一次"的额外代价约 0.2 秒，不影响 D3 的"preflight 重演不计入本机实验预算"结论。

### 11.5 仍未闭合

1. ledger 仍无哈希链（沿用 `docs/30` D4），"不可重试"依赖代码流程。
2. lease 守卫与本次新增门禁同属 Python 级 API 约束，不是对抗性安全边界。
3. 第 7 节的工作区干净前置、第 6 节的冻结清单，以及第 4.1 节以外的持续性披露项，均未因本次加固而改变。
