# 30 M8：多人 CFR 候选 A——Campaign 执行完整性只读复核

> 日期：2026-09-17。
>
> 实测起点：`git status --short --branch` 输出 `## master...origin/master`（无改动），`git log -8 --oneline` 顶部为 `8601a4b feat: harden supervised campaign execution`，`git rev-parse HEAD` 与 `git rev-parse origin/master` 均为 `8601a4b6248779eb9ce07e0806005869c768acec`。工作区干净，本地与远端一致。
>
> 状态：本轮分两段。**第一段是只读复核**（第 1 至 9 节）：未修改任何代码，未运行 A6/A7/A9 训练、profile/probe、跨 seed 稳定性实验、N9 boundary、supervisor 子进程或资源基准，未写入任何策略/measurement/日志/检查点/ledger 工件，未 commit、未 push，未重新运行测试套件。**第二段获得用户逐项授权后做了 P0/P1 修复并落实阶段截止**（第 10 节）：改动仅限 `tools/trainer/` 与本文档，未启动实际训练，未 commit、未 push。
>
> 本文是 `docs/29` 第 14 节之后的新一轮记录。`docs/20` 至 `docs/29` 未被改写。

## 1. 本轮边界

本轮不构成实际训练授权，也不构成代码修改授权。本文只记录：

1. 与 `8601a4b` 实际一致的工作区与提交状态；
2. 对该提交新增/修改的执行完整性链路（执行快照、父子运行时身份、工件封存、最终 measurement、estimator preflight、campaign 预算与 lease）的只读检查结论；
3. 仍然存在的代码级缺口与验证覆盖缺口；
4. 哪些事项只需用户冻结 canonical campaign，哪些需要先改代码；
5. 是否适合立即启动真实 A6/A7 campaign 的判断。

本文不提供新的质量、资源、策略或收敛证据。上一轮记录的 `159 passed in 117.16s` 仍是最近一次完整离线验证结果；本轮没有重新执行该命令，因此不在此处复述为"本轮验证"。

## 2. 复核范围

只读检查了以下实现（按父子执行顺序）：

| 环节 | 文件 |
|---|---|
| 冻结 experiment/probe manifest 与唯一计划派生 | `manifest.py` |
| 父端执行快照与子端快照重验 | `execution_snapshot.py` |
| 父子双端工作树/提交/解释器身份 | `runtime_identity.py` |
| 无 shell 进程组监督、`ps` 采样与终止 | `supervisor.py` |
| 父端编排入口与 campaign authorization 参数校验 | `supervised_executor.py` |
| 子进程入口 | `manifest_executor.py` |
| 子进程内阶段编排 | `orchestration.py` |
| 子进程测量记录与父端深度复验 | `experiment_record.py` |
| 父端最终 measurement 与回读复验 | `supervised_measurement.py` |
| 独占工件根与封存清单 | `artifact_inventory.py` |
| N6 estimator preflight spec/attestation | `estimator_preflight.py` |
| campaign 共享预算、`flock` lease、终态 ledger | `campaign.py` |
| campaign 授权执行入口 | `campaign_executor.py` |
| 相关测试 | `tests/test_multiplayer_campaign*.py`、`tests/test_multiplayer_supervised_executor.py` 等 |

## 3. 已确认成立的部分

以下为代码事实，不构成结论性质量主张：

1. **执行输入不可被事后替换。** 父端从已验证 manifest 的规范 payload 同时写入 `inputs` 快照，并在子端派生前重验 `manifest_id`、`sha256`、`byte_length`；子端不读取用户可变源 manifest 路径（`execution_snapshot.py`、`manifest_executor.py`）。
2. **父子身份双端核验。** 父端用固定 `/usr/bin/git` 读取实际 `HEAD` 与 clean 状态、固定解释器绝对路径；子端再次核验同一工作树与解释器；受控子进程使用最小环境，不继承 `PYTHONPATH`/用户 site（`runtime_identity.py`）。调用方自述 commit、父端实测 commit、冻结 manifest commit 三者一致才继续。
3. **工件根独占且 fail-closed。** 工件根必须为空且非链接；仅接受 manifest 声明的单链接普通文件；出现未知文件、目录或链接即失败；停止/失败时只删除已声明普通文件（`artifact_inventory.py`）。
4. **最终 measurement 由父端写入并深度复验。** 只有真实 supervisor receipt 为 `completed` 时父端才回读子端临时记录，重新 canonicalize 并核验其 schema、SHA-256、字节数、计划参数、策略身份；父端在原子替换后再次生成排序 inventory；停止/失败 receipt 不允许关联策略或质量结果（`supervised_measurement.py`、`experiment_record.py`）。
5. **N9 长期路径被封堵。** `MCCFRConfig`、`run_iteration()`、`train()`、`completed_result()`、`export_strategy()` 拒绝 N9；唯一路径是单 traverser sampled pass，不提交更新、不累计平均策略、不产生策略（`mccfr.py`、`policy.py`、`manifest.py`）。
6. **estimator preflight 具备冻结输入与重演。** spec 冻结 commit、trainer version、显式升序 seed 集、固定目标 infoset、regret/strategy-sum 容差、固定非均匀 fixture 与两种 average 累计模式；attestation 回读时父端重跑固定 oracle/production 审计并逐字节比对（`estimator_preflight.py`）。
7. **campaign 预算与不可重试 lease。** 规范 campaign manifest 固定 authorization 列表、共享 CPU/墙钟/峰值 RSS/保留工件上限且 `max_concurrency == 1`；reservation 总和不得超过 envelope；`flock` 独占；已被 ledger 记录的 authorization 不能再次 lease；每次 authorization 使用新建 run 目录与空工件根（`campaign.py`、`campaign_executor.py`）。

## 4. 代码级发现

### 4.1 需要修复：A6/A7 的 campaign authorization 只是"参数存在性"检查

`supervised_executor.py` 的 `_require_campaign_authorization()` 对 A6/A7 只检查：

- `campaign_authorization_id` 是非空字符串；
- `campaign_experiment_identity == plan.manifest.identity`。

它**不校验该 id 属于某个已冻结 campaign、也不校验当前是否持有该 campaign 的 lease**。因此直接调用公开的 `run_supervised_manifest_executor(..., campaign_authorization_id="任意非空串", campaign_experiment_identity=<experiment identity>)` 就能在完全没有 campaign manifest、没有 `flock` lease、没有 ledger 事件、没有共享预算约束的情况下执行 A6/A7。

这与用户已确认的默认决策"C1 覆盖 A6/A7……authorization 被 lease 后禁止自动重试、预算重置或追加 seed"以及"A6/A7 必须有 campaign authorization"不一致：当前实现的强制性仅停留在调用方自觉使用 `run_campaign_authorization` 的层面。

建议方向（尚未实现）：把 `CampaignLease`（或只能由 `acquire_campaign_lease` 产出的不透明凭证）作为 `run_supervised_manifest_executor` 的必填输入，并同时校验 lease 的 authorization 身份、lock 仍持有、run 根等于 lease 归属的 run 目录。

### 4.2 需要修复：`authorization_id` 未做受控字符集校验，可写出 campaign 根目录之外

`campaign.py` 的 `_require_id()` 只检查"非空字符串且长度不超过 64"，没有字符集限制（对比 `manifest.py` 使用 `[a-z0-9][a-z0-9-]{0,63}`）。

`campaign_executor.py` 直接用该值拼路径：

```text
run_root = root / "runs" / authorization_id
artifact_root = run_root / "artifacts"
artifact_root.mkdir(parents=True)
```

因此形如 `../../../../tmp/x` 的 `authorization_id` 会让 `mkdir(parents=True)` 在 campaign 根目录之外创建目录，破坏"每次 authorization 使用新建、空、独占 artifact root"这一 fail-closed 语义。虽然 manifest 由用户冻结、不构成外部攻击面，但该类输入应在 schema 层被拒绝，而不是依赖 `run_root.exists()` 的偶然拦截。

建议方向（尚未实现）：对 `campaign_id`、`authorization_id` 采用与 manifest 相同的受控标识正则，并在拼接后断言解析路径仍位于 campaign 根目录之内。

### 4.3 需要绑定：campaign 的 `peak_rss_limit_bytes` 未被任何环节使用

`peak_rss_limit_bytes` 仅在 `campaign.py` 内部解析、保存、回写（`campaign.py:69`、`:233`、`:252`、`:329`），运行期没有任何使用点。

`campaign_executor.py` 的 `_validate_authorization_budget()` 只比较三项：experiment 的 `cpu_limit_milliseconds ≤` authorization CPU 预留、阶段墙钟总和 `≤` 墙钟预留、`retained_artifact_limit_bytes ≤` 工件预留。**RSS 不在比较之列。**

后果：一个 authorization 可以绑定一份把 `rss_hard_limit_bytes` 声明得远高于 campaign envelope 的 experiment manifest，campaign 校验仍然通过，实际 supervisor 用的是 experiment 的 RSS 阈值。用户冻结的"训练相关进程峰值 RSS 合计：8 GiB"因此没有被 campaign 层机械约束。

建议方向（尚未实现）：在 `_validate_authorization_budget` 中加入 `experiment.rss_hard_limit_bytes ≤ campaign.peak_rss_limit_bytes`（单并发下二者应同口径绑定），或引入显式 RSS reservation。

### 4.4 语义未闭合：`export` 与 `measurement` 阶段预算被声明但从未执行

`manifest.py` 要求 A6/A7 必须按固定顺序声明 `training, export, profile, probe, measurement` 五个阶段预算；`campaign_executor._validate_authorization_budget` 也把五个阶段墙钟之和作为墙钟预留口径。

但实际执行中：

- `training` / `boundary` 通过 `orchestration._run_limits()` 生效；
- `profile` / `probe` 通过 `orchestration._evaluation_checkpoint()` 生效；
- **`export` 与 `measurement` 没有任何读取点**（`stage_budgets` 只在这两处被消费）。

即：这两个阶段的墙钟数值参与预算核算，却不产生任何阶段级停止行为。总墙钟仍由父 supervisor 硬限（其 `wall_time_limit_milliseconds` 取五阶段之和），所以不存在"超出预留总量"的风险，但"逐阶段降级"的语义并未实现。需要明确二选一：要么实现 export/measurement 阶段截止，要么在 manifest/schema 层说明它们只是预留而非独立门限。

### 4.5 异常路径：campaign lease 不落终态，失败工件不被记录或清理

`campaign_executor.run_campaign_authorization()` 在 `with acquire_campaign_lease(...)` 内直接调用 `run_supervised_manifest_executor(...)`，然后 `lease.finalize(...)`。若后者抛出异常（例如 `supervised_executor.py:196-203` 的"最终 measurement 替换后的工件清单不符合计划"，或 `:180-181` 的"子进程退出后的工件清单不符合计划"），则：

- `finalize()` 不执行，ledger 只留下 `leased` 事件，没有终态、没有 supervisor receipt hash、没有 final measurement hash、没有 inventory；
- 该 run 目录中可能已经存在子进程写入的已声明策略与 measurement 文件，不会再被清理，也不会被任何账本记录。

该行为在 `CampaignLease.close()` 的文档里被描述为"未终结 lease 保持 ledger 中的 fail-closed 状态"，属于有意设计；但它同时意味着"停止/失败时仅清理已声明普通文件"这条要求在异常（非 supervisor 回执）路径上不成立。建议在不改变"不可重试"语义的前提下，为异常路径补一次明确的终态写入与已声明工件清理。

### 4.6 audit 残差：campaign ledger 无完整性链，事件字段未校验

`campaign.py:_load_ledger()` 只校验 `schema_version`、`record_type`、`campaign` 身份与 `events` 是列表；单条 event 的字段没有 schema 校验（`acquire_campaign_lease` 直接索引 `event["authorization_id"]`，缺字段会抛 `KeyError` 而不是 `CampaignError`）。

ledger 是 campaign 根目录下的普通文件，没有哈希链或签名。因此"不可重试"只对代码自动流程成立：手工删掉某条 `leased` 事件并同时删除对应 `runs/<id>` 目录后，同一条 authorization 可以再次 lease。这属于需要在文档中如实披露的残差，而不是未实现的功能；若要闭合，需要 append-only 哈希链或在 run 目录写入不可撤销标记。

### 4.7 preflight 证据链：attestation 未绑定冻结 spec 文件，且重演在预算之外

`campaign_executor.py` 接收的是已构造的 `EstimatorAttestation` 对象，并用 `_preflight_spec_from_attestation()` 从 attestation payload **反向重建** spec，再交给 `verify_attestation()`。

这意味着重演确实能发现 attestation 内容被篡改（payload 与重跑结果必须逐字节一致），但用户冻结的 canonical preflight spec 文件本身既不需要存在、也不被读取，`spec.identity` 与文件字节的唯一关联只来自 attestation 内嵌的身份字段。用户决策要求"真实 campaign 必须使用真实 canonical preflight spec/attestation"，当前代码只强制了后半句。

另外，`verify_attestation()` 的完整重演发生在 `acquire_campaign_lease()` 之前、且不在 supervisor 监督范围内，因此每次 authorization 都会重复消耗这部分 CPU，且不计入 campaign 预算。

建议方向（尚未实现）：`run_campaign_authorization` 改为接收 preflight spec 路径，用 `load_preflight_spec()` 读取并把该 spec 与 attestation 一起验证；同时明确该重演是否计入总 CPU 预算。

### 4.8 双重读取依赖身份复核（低风险，记录备查）

`run_campaign_authorization` 先读取 experiment manifest 用于预算校验，`run_supervised_manifest_executor` 再读取同一路径用于生成快照。两者之间源文件被替换时，第二次读取的 identity 会与 lease 中记录的 authorization identity 不符而失败，因此当前不存在可利用的 TOCTOU。仅记为设计备注：更直接的写法是把第一次读取的 `LoadedManifest` 传下去，避免依赖"第二次读取必然失败"来保证一致。

## 5. 验证覆盖缺口

1. **campaign 路径下的 preflight 门禁未被端到端验证。** `tests/test_multiplayer_campaign_executor.py:156` 用 `monkeypatch.setattr(campaign_executor, "verify_attestation", lambda *_: None)` 把该门禁替换为空操作，且其 fixture attestation 的 `target_infosets` 为空、identity 为构造值，在真实 `verify_attestation` 下不会通过。也就是说，唯一一条 campaign 执行测试并没有覆盖"必须携带通过的 preflight attestation"这一强制链路。
2. **`_validate_authorization_budget` 无测试。** 全局搜索确认该函数只有定义与调用点，没有任何测试用例触发"资源上限超过预留"分支。
3. **A6/A7 受监督路径未被真正执行。** `tests/test_multiplayer_supervised_executor.py` 只有 N9 boundary 成功路径，以及 "A6 缺少 campaign authorization 被拒" 与 "运行时身份不符在启动子进程前失败" 两个拒绝路径；A6/A7 的策略槽位、预算对齐、profile/probe 阶段均未在受监督协议中被执行过。
4. **`authorization_id` 路径安全、ledger 篡改、异常路径终态** 均无测试。

以上缺口都是"未覆盖"，不等于"已失败"；但 4.1 与 4.2 属于有明确绕过面的实现问题，3 与 4 若要作为实际实验的证据链，应在启动真实 campaign 前补上。

## 6. 只需用户冻结、无需再改代码的事项

以下事项当前代码已能承接，只缺用户一次性冻结的 canonical 输入：

1. Campaign ID、实际 Git commit、trainer version、实际 worktree 与解释器语义；
2. A6/A7 每条 authorization 的 player count、iterations、`average_strategy_start_iteration`、单一显式 seed、strategy/measurement 槽位名与上限、单次 CPU、阶段墙钟、RSS、artifact reservation；
3. Campaign 总 CPU、总墙钟、峰值 RSS、总 artifact 上限；
4. 是否执行 full-chance profile、预注册 probe、跨 seed 稳定性实验，以及各自通过/停止/保留/失败阈值；
5. 新建独占 artifact root 的位置与保留策略；
6. 真实 estimator preflight spec 文件与由其实跑得到的、`passed == true` 的 attestation 文件；
7. 一次性实际执行授权；
8. 是否允许 commit/push 实验文档或 ledger（默认不允许）。

不得以当前单元测试 fixture、示例 manifest、测试 attestation 或 N9 boundary 测试替代上述任一输入。

## 7. 结论：当前不建议直接启动真实 A6/A7 campaign

- **执行链路的骨架已经成形**：快照、父子身份、独占工件封存、父端最终 measurement、N9 封堵、preflight 重演、campaign lease 与共享预留均已实现并通过此前的单元测试。
- **但仍存在未闭合的实现缺口**，且这些缺口直接对应"必须有 campaign authorization""artifact root 独占""峰值 RSS 合计上限"这三条用户已确认的边界：见 4.1、4.2、4.3。此外 4.4、4.5 会影响"停止即降级、失败即清理"的可审计性。
- 因此判断是：**应先修复 4.1–4.3（并补齐第 5 节列出的覆盖），再做一次只读就绪复核；在此之前不应消耗一次性预算启动真实 A6/A7。**
- 4.6、4.7 属于需要持续披露的证据链边界；即使修复，也只能表述为"按用户接受的本机采样式进程组监督 + 规范化指纹记账"，不能表述为不可绕过的系统级执法。

上述修复不涉及 `kuhn_cfr`、后端、前端、锁文件或真实数据库，也不需要运行任何实际训练；它们可以在纯单元测试路径内完成。

## 8. 持续披露与解释边界

- 当前 macOS supervisor 是本机 `ps` 采样式进程组监督：它在阈值命中时终止已知进程组与已观察后代，**不是不可逃逸的内核级 containment**，不能被表述为此类能力。
- 即使在真实 campaign 完成后，候选 A 也不得被表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 单元测试、N9 boundary、有限 estimator preflight、短路径回归、采样累计量、常和性质或策略稳定性，都不等于 A6/A7 训练结果、质量证据或资源基准。
- 在未启动实际 A6/A7 之前，不得声称已生成任何策略、质量或资源证据。本文没有产生任何此类证据。

## 9. 只读复核阶段的未做事项

该阶段未修改任何代码文件；未运行 A6/A7/A9 训练、profile/probe、稳定性实验、N9 boundary、supervisor 子进程或资源基准；未重新运行完整测试套件；未在工作区生成策略 JSON、measurement、ledger、日志或检查点；未 commit、未 push。

## 10. 获授权修复（P0/P1 与阶段截止）及复验结果

第 4 节的只读发现经用户逐项决策后，本轮完成了 P0、P1 以及 D2 的阶段截止。改动范围仅 `tools/trainer/src/multiplayer_cfr/` 的四个文件与对应测试，未触碰 `kuhn_cfr`、后端、前端、锁文件或真实数据库，未启动任何实际训练或 supervisor 子进程。

### 10.1 用户决策记录

| 决策 | 内容 |
|---|---|
| D1 | 授权本轮做 P0 与 P1 修复；P2 另起一轮 |
| D2 | `export` / `measurement` 阶段预算**实现截止**，不做纯预留说明 |
| D3 | estimator preflight 重演的 CPU **不计入**本机 2 小时总预算（前置 evidence，非实验执行） |
| D4 | ledger 残缺按 D4 建议**只做披露**，不改动账本为哈希链 |
| D5 | `docs/30` 保留在工作区、不提交 |
| D6 | 本轮记录全部落在 `docs/30`；如需拆分才使用 `30a` 编号 |

### 10.2 修复对照

| 只读发现 | 修复 |
|---|---|
| 4.1 A6/A7 的 campaign authorization 只是参数存在性检查 | A6/A7 必须携带 `CampaignLease`；lease 只能由 `acquire_campaign_lease` 签发（构造凭证校验），并重验其仍有效、与冻结 experiment 身份/代码版本一致、且 ledger 已记录该 lease；工件与快照目录必须落在该 lease 的 run 目录内。原 `campaign_authorization_id` / `campaign_experiment_identity` 两个可自述参数被移除 |
| 4.2 `authorization_id` 未做字符集校验可越出 campaign 根 | `campaign_id`、`authorization_id`、manifest/preflight 引用标识统一要求受控标识 `[a-z0-9][a-z0-9-]{0,63}`；run 目录拼接后再断言解析路径仍在 campaign 根内，并新增 `create_run_directories()` 作为唯一建目录入口 |
| 4.3 campaign `peak_rss_limit_bytes` 未被任何环节使用 | 授权预算校验新增 `experiment.rss_hard_limit_bytes ≤ campaign.peak_rss_limit_bytes`（单并发下同口径绑定） |
| 4.4 `export` / `measurement` 阶段预算被声明但从未执行 | 新增统一的阶段墙钟检查（同时响应外部取消与 RSS 预警）；导出完成后校验导出阶段，measurement 记录构造与写入前后各校验一次；超预算即失败且不生成测量记录 |
| 4.5 异常路径 lease 不落终态、残留工件不清理不记账 | `run_campaign_authorization` 在异常路径写入终态事件：能安全清理声明工件时记 `failed`，无法安全清理时记 `inventory-failed` |
| 4.6 ledger 事件字段未校验 | 读取 ledger 时逐条校验事件字段集合，避免缺字段抛 `KeyError`；哈希链按 D4 结论不做 |

### 10.3 新增测试

1. campaign：越界 authorization 标识被拒、lease 无法在互斥入口之外构造、run 目录只创建一次且不越界、lease 需与 ledger 实时记录一致（释放后校验失败）、ledger 事件字段异常被拒。
2. campaign executor：experiment RSS 硬停阈值高于 campaign envelope 时被拒，且不创建 run 目录。
3. supervised executor：lease 绑定的 experiment 身份与待执行 manifest 不一致时被拒，且不生成快照、工件目录保持为空。
4. orchestration：导出阶段与 measurement 阶段分别跨过各自墙钟预算时失败，且不生成 measurement。

### 10.4 复验结果

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
168 passed in 118.43s
```

该复验只覆盖规则、有限 estimator preflight、N9 boundary、父子协议、快照、封存清单、campaign 预算/lease 与短路径阶段截止。A6/A7 训练、profile/probe、稳定性实验、资源基准、真实 campaign 与任何保留工件仍**没有**执行。

### 10.5 仍未闭合的事项

1. ~~`4.7` 的 preflight spec 文件绑定仍未实现~~ 已在第 11 节闭合。
2. ~~campaign 路径的 preflight 门禁在测试中仍由 monkeypatch 绕过~~ 已在第 11 节闭合。
3. ~~A6/A7 的受监督成功路径仍无测试~~ 已在第 11 节闭合；该测试同时暴露了一个此前未发现的完成态缺陷，见第 11 节。
4. ledger 仍无哈希链（按 D4 决定不改），因此"不可重试"依赖代码流程而非账本自身的完整性证明。
5. lease 守卫是 **Python 级 API 约束**：它阻止调用方在无 campaign 的情况下误用 A6/A7 入口，但不构成对任意代码执行的对抗性安全边界；需要接触模块内部标识并伪造 ledger 才可能绕过。

### 10.6 持续披露

- macOS supervisor 仍是本机采样式进程组监督，不是不可逃逸的内核级 containment，不能表述为此类能力。
- 第 10 节的全部改动只经过单元测试与短路径验证，不构成多人 Hold'em GTO、均衡、NashConv、exploitability、真实 EV 或生产可用性结论。
- 本轮未产生任何策略、质量或资源证据；未启动实际 A6/A7 之前不得声称已生成此类证据。

## 11. P2：preflight 文件绑定、真实 attestation 与 A6 受监督成功路径

用户以"按你建议继续推进"授权第 10.5 节列出的三项后续工作。改动仍限于 `tools/trainer/` 与本文档，未启动任何受预算训练，未 commit、未 push。

### 11.1 冻结 preflight 文件绑定

`run_campaign_authorization` 不再接收调用方自述的 attestation 对象，改为接收冻结文件路径：

- `preflight_spec_path`：用 `load_preflight_spec()` 安全读取并重算 spec 身份；
- `preflight_attestation_path`：用 `load_attestation()` 安全读取并按真实字节重算 attestation 身份；
- 先 `verify_campaign_preflight(campaign, attestation)`（campaign 引用的 attestation 身份与代码版本必须一致），再 `verify_attestation(spec, attestation)`（冻结 spec 必须重演出与 attestation 完全相同的 payload）。

原先"从 attestation payload 反向重建 spec"的私有函数已删除，因此证据链现在是：campaign 文件 → attestation 文件字节 → 内嵌 preflight manifest 身份 → spec 文件字节 → 重演的 oracle/production 结果。任一环节被替换都会在启动子进程前失败。D3 的"重演不计入本机预算"结论不变，该重演仍发生在获取 lease 之前。

### 11.2 真实 attestation 的端到端测试

campaign executor 测试不再 monkeypatch `verify_attestation`：测试改为在临时目录写入真实的冻结 spec 与由它实跑得到的 attestation，campaign 引用其真实身份，再走完整授权路径。这同时闭合了"campaign 路径 preflight 门禁未被端到端验证"的覆盖缺口。

### 11.3 A6 受监督成功路径与新发现的完成态缺陷

新增一条 A6 受监督成功路径测试：真实子进程 + 冻结 A6 manifest + 持有 campaign lease，断言父 supervisor 回执为 `completed`、策略文件存在、最终 measurement 关联策略与子执行记录、最终封存清单为 `measurement.json` 与 `strategy.json`。

**该测试首次暴露出一个此前未发现的完成态缺陷**：父端最终 measurement 中的策略身份块只写 `sha256` 与 `artifact_bytes` 两个字段，而子端测量记录写 `sha256`、`artifact_bytes`、`artifact_type`、`artifact_schema_version` 四个字段；`supervised_measurement` 内层的严格相等校验因此必然失败。后果是：**任何完成的 A6/A7 受监督运行都无法产出最终 measurement**，而此前受监督路径只有 N9 测试（无策略），所以该缺陷一直不可见。

修复方式是消除重复实现：把策略身份块抽出为唯一共用构造器 `strategy_identity_payload()`，父端与子端共用同一形状，并保留严格逐字段相等校验（不放松为只比较部分字段）。这样两侧一旦再次分叉就会立即失败，而不是静默产生不可比对的结果。

### 11.4 复验结果

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
169 passed in 123.88s
```

第 11.3 节的 A6 测试是**单元测试**：它使用显式 1 iteration、固定 seed、临时 Git 工作树与本地 supervisor 原语，不是受预算实验，也不能作为 A6/A7 训练质量、策略质量、RSS 或耗时的实测证据。

### 11.5 当前遗留

1. ledger 仍无哈希链（D4 决定），"不可授权重试"依赖代码流程。
2. lease 守卫仍是 Python 级 API 约束，不是对抗性安全边界。
3. 第 10.4 与 11.4 节的验证仍只覆盖单元测试路径；实际 A6/A7 campaign、profile/probe、跨 seed 稳定性、资源基准与保留工件均未执行。

至此，第 4 节列出的代码级缺口（4.1–4.5）、D2 的阶段截止、以及第 10.5 节的前三项遗留都已闭合。下一步仍应由用户冻结 canonical campaign（第 6 节清单）并给出一次性实际执行授权；在此之前不得启动真实 A6/A7。
