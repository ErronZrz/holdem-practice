# 74s M8：第一层锁定的实现方案提案（G-1 至 G-20，待审查）

> 日期：2026-10-09。
>
> **战役归属**：`74`（「新身份研发与独立验证」战役）。本文件是该战役的第 `20` 份文档，编号 `74s`。
>
> **历史关系**：承接已生效的 `74r`（③ 侧四类对象的第一层锁定文本，锁定版本 1；审查方全文内容审查通过后，依 `74r` §3.2 整体生效，通过登记在 `docs/README.md`）。依据 `74r` §9 的实现缺口 G-1 至 G-20、§6.1 的来源与环境定义、§6.6 的审计与承诺、§8.1 U-5 的源码清单，以及 `74p` 登记的包内不可执行边界。本文件**不修改** `74r` 或任何历史文档正文。
>
> **编号范围**：本文件使用根编号 `74` 的后缀 `s`，按创建时的追加顺序确定；不预占任何后续编号。`73` 已关闭、不得续号。
>
> **本文性质**：**§9 实现方案提案**。把 G-1 至 G-20 映射到拟修改或新增的模块与测试，并写定两个包外工具的路径与入口、G-18 的过程审计载体，以及将来实现轮次拟使用的夹具与命令。本文件**不是**实现，**不是**锁定文本的修订或升级，**不**改变 `74r` 版本 1 的任何条款。所写路径、入口与载体是提请审查的方案；审查通过之前**不得**据此改代码。
>
> **效力限定（写死）**：
>
> - 本文件**不**实施 G-1 至 G-20，**不**使 ②–⑦ 发生，**不**建立 C-1′、C-2′、F-0，**不**创建 `mixed-local@9`。
> - **不**生成或冻结材料、seed、清单、节点、摘要或 `code_identity`。五个 ② 侧对象仍未锁定，实际 campaign 摘要仍不可生成。
> - **不**改代码、测试、`74r`、`docs/README.md` 或其他既有文档；**不**运行测试、构建、测量或模拟；**不**提交或推送。
> - 若方案中的某一项无法在 `74r` 版本 1 内实现，只登记为须以新的 `74` 后缀修订，**不**在实现时扩展协议。

## 1. 授权原文与范围

授权原文：

```text
现授权：

- 新建且仅新建 `docs/phase6/74s-m8-first-layer-lock-implementation-plan.md`。
- 性质仅为 §9 实现方案提案，不修改或升级 `74r`。
- 逐项映射 G-1 至 G-20 到拟修改/新增模块及测试。
- 明确包外源码清单工具、材料生成器的具体路径与入口。
- 明确 G-18 过程审计载体；若无法在 `74r` v1 内实现，必须登记为需新后缀修订，不得自行扩展协议。
- 写明非实际夹具、模拟 `os.urandom`、不可执行性检查及拟运行的回归/质量命令。
- 只允许只读核验；不得修改代码、测试、现有文档或索引，不得运行测试/构建，不得生成材料或摘要，不得提交推送或推进②③。

完成后仅申请该提案的内容审查。
```

同段写明：下一步暂不直接授权代码实现。G-11、G-18 的工具路径、入口及过程审计载体仍未确定，直接实施可能静默改变已锁定协议。

**不属于本文件**：对 `74r` 的任何修订；② 侧五个对象的锁定文本；代码与测试的实际修改；③ 的三类核验；④–⑦；索引更新；提交与推送。

## 2. 文件级改动与真实执行情况

| 文件 | 改动性质 |
|---|---|
| `docs/phase6/74s-m8-first-layer-lock-implementation-plan.md` | **新增**（本文件） |

| 类别 | 内容 |
|---|---|
| 只读核验 | `git rev-parse HEAD origin/master`、`git rev-list --left-right --count HEAD...origin/master`、`git status --short`；确认 `docs/phase6/74s*` 尚不存在。阅读 `74r` §6.1、§6.3、§6.5–§6.7、§8.1 U-5、§8.3.4、§9；`74q` 文首。只读代码：`backend/app/verification/` 的模块与函数清单，`deal.py` 人数校验，`config.py` 的 `DomainRunSpec` 与 `schedule_digest`，`protocol.py` 的定位字段比较与 `protocol_digest`，`identity.py` 的种子校验，`instantiation.py` 的常量载荷与 `baseline-effective-seed` 渲染，`execution_identity.py` 的非空校验，`runner.py` 的冻结摘要项与流程名，`backend/tests/test_verification_runner.py` 的导入白名单与禁止调用根，`backend/pyproject.toml` 的依赖与 `ruff` 选择，`backend/tools/` 现有脚本 |
| 开发回归 / 质量验证 / 构建 | 均未执行 |
| 未执行 | 模拟、性能测量、补算、材料生成、清单或摘要计算、提交与推送 |

事实登记（本文件落盘前）：`HEAD = origin/master = eff3fb1abae621e3caa1eacb971bc3d9a0e1627b`，ahead / behind 为 `0 / 0`，工作区清洁。本轮只新增本文件。

**审查后修订（2026-10-09）**：首版（`202` 行，SHA-256 `fbe2b834de35d82a82bd9ed2555b8d195189e1d5049283c1aab8bd184cd07210`）经内容审查，审查方裁定**暂不通过**。路径与边界被认定合理，但实现接口尚未机械闭合。五项阻断：生成入口的参数、返回对象与失败语义未封闭；源码清单入口无法核验实际加载的第一方源码；G-2 没有承载五个 ② 侧版本号的模型；若干映射缺少具体 API；验收命令不符合仓库约定，且定向检查漏了预计会改的测试夹具模块。修订授权原文：

```text
现授权仅就地修订 `74s`，逐项闭合上述五点。仍不得修改代码、测试、其他文档或索引，不得运行命令、提交推送、生成材料或推进②③。修订后再次申请内容审查。
```

本次只改本文件：§4 改为两个入口的封闭签名；§5 与 §6 的 G-2、G-11、G-12、G-17、G-18、G-20 改为可调用的模型与函数；§7.1 写明夹具版本号的承载位置；§8 改为必须实际执行全仓质量检查并纳入测试夹具模块。未运行任何命令，未改其他文件。

**第二次审查后修订（2026-10-09）**：上一修订版经审查方核验为 `370` 行、SHA-256 前缀 `4b98e2ed`，审查方裁定**暂不通过**。前次五项接口缺口被认定基本闭合，仍有三项阻断：`DomainRunSpec` 缺少已锁定要求的显式 `campaign` 字段；负零判断会触发除零；`materials_digest` 被写到了错误的模块。审查方同时建议把版本号模型改成不与 ⑥ 第二层冻结混淆的名称。修订授权原文：

```text
现授权仅就地修订 `74s`，处理上述三项并同步相关表述。仍不得修改代码、测试、其他文档或索引，不得运行命令、提交推送、生成材料或推进②③。修订后再次申请内容审查。
```

本次只改本文件中与这三项相关的表述：§4.1 的索引键来源，§6.1 的规格字段、负零判断与材料摘要位置，§6 的 G-2、G-17、G-20 行，以及 §7.1。未运行任何命令，未改其他文件。

**第三次审查后修订（2026-10-09）**：上一修订版经审查方核验为 `386` 行、SHA-256 前缀 `46d78d9e`，审查方裁定**暂不通过**。三项原阻断被认定已正确处理，仍有两处机械闭合问题：campaign 摘要若只接受已构造的 `DomainRunSpec`，调用方无法在构造前得到应写入的 `campaign`；`verify_manifest_binding` 目前没有规格参数，无法做送交材料的次序校验。修订授权原文：

```text
现授权仅就地修订 `74s`，闭合上述两点。仍不得修改代码、测试、其他文档或索引，不得运行命令、提交推送、生成材料或推进②③。修订后再次申请内容审查。
```

本次只改本文件的 §4.1、§6.1、G-2 与 G-20 行、§7.1。未运行任何命令，未改其他文件。不得使用 `model_construct` 绕过规格校验。

## 3. 方案所遵守的已锁定约束

1. `74r` 版本 1 已生效。本方案只规划如何实现其 §9，不改写其条款。`74r` 文首仍留有送审稿字样；通过事实登记在索引中。刷新该文首本身就是修改已生效文本，本方案不提出这种修改。
2. 包内 `backend/app/verification/` 不读取文件、不调用 `os`（`test_verification_runner.py` 将 `os` 列为禁止调用根），也不容纳生成器。源码清单的文件读取与材料生成都在包外。
3. `source-manifest-v1` 的 `dependency_files` 固定为 `backend/pyproject.toml`、`backend/uv.lock`。工具不得改用 `tools/trainer/uv.lock`，也不得改这份清单规格。
4. 承诺字段锁定为 14 项；协议载荷字段集封闭。新增字段会改变摘要，属于协议变更，只能由新的 `74` 后缀承接。
5. 实现轮次的审查只用非实际材料夹具。该轮次不得生成实际材料、实际 campaign 摘要、实际源码清单摘要或 `code_identity`。
6. 实现与测试通过审查之前不得进入 ③。本提案通过审查也不解除该门槛，也不等于取得实现授权。

## 4. 包外工具的路径与入口

两个工具都放在 `backend/tools/`，使用后端环境（`backend/pyproject.toml` 与 `backend/uv.lock`）。该目录已有只读脚本，且不在 `app` 的安装包内，因此不会进入 `app.verification` 的不可执行检查范围，也不会把生成器写进验证包。

### 4.1 材料生成入口

路径 `backend/tools/material_generator.py`。返回类型定义在该文件，不放进验证包，也不给 `AuditedMaterials` 增加字段。

```text
@dataclass(frozen=True)
class GeneratedMaterials:
    bundle: tuple[HandMaterials, ...]
    material_manifest: MaterialManifest
    audit: AuditedMaterials

def generate_materials(
    spec: DomainRunSpec,
    generator_manifest: Mapping[str, object],
) -> GeneratedMaterials:
```

两个参数都必填，没有默认值。`spec` 提供协议、手序、人数、筹码、盲注、`block`，以及 §6.1 的 `CampaignConfiguration`。`generator_manifest` 是已经构造好的 `source-manifest-v1` 对象，不是路径。

函数内部按下列顺序取得承诺里的三项，它们都不是额外参数：

1. `generator_code_digest`：先调用包内 `require_source_manifest(generator_manifest)`，再调用 `source_manifest_digest`。入口列表必须恰好是 `("backend/tools/material_generator.py",)`，否则失败。本函数不读盘。
2. `manifest_digest`：接受项全部落到局部的 `MaterialManifest` 之后，调用现有的 `manifest_digest(material_manifest, algorithm=spec.protocol.digest_algorithm)`。
3. 起止时间：不是参数，也不由调用方传入。进入函数、尚未读取随机字节时，取 `datetime.now(timezone.utc)` 并格式化为 U-5 的 `YYYY-MM-DDTHH:MM:SS.ffffffZ`，记入局部变量。全部读取、材料束、清单和两项摘要都成功之后，再取一次时钟作为结束时间。结束时间不得早于这次调用的开始时间。

其余承诺字段来自 `spec.protocol` 与本次读取计数：来源、环境、遍历顺序、算法、记录编码、审计版本 `1`，以及按遍历顺序排列的 `entry_counts` 与 `rejection_counts`。转录摘要是原始字节的 SHA-256，不经 JSON。逐读取记录摘要按物理 `read_index` 计算。索引键里的 `campaign` 使用 `spec.campaign`，`block` 使用 `spec.block`。规格在构造时已经要求 `spec.campaign` 等于按组成字段算出的摘要（§6.1），该计算不需要一份已经构造好的 `DomainRunSpec`。

随机源在源码中写成对 `os.urandom` 的直接调用，不增加可替换随机源参数。

**失败时没有部分结果**：函数不捕获异常，不写文件，不把半份结果放进模块全局或实例属性。`GeneratedMaterials` 只在最后一行构造并返回。任何较早的失败都使该行不执行，调用方只得到异常，拿不到材料束、清单或承诺。测试用会在第二次调用失败的 `os.urandom` 替身断言这一点。

本函数不推进牌局，不创建 `mixed-local@9`，不导入 `app.strategy.registry`，不构造 `HeuristicStrategy`。

### 4.2 源码清单入口

路径 `backend/tools/source_manifest.py`。

```text
def build_source_manifest(
    entrypoints: Sequence[str],
    *,
    workspace_root: Path,
) -> dict:
```

`workspace_root` 必填，必须是绝对路径，且其下必须存在 `backend/pyproject.toml` 与 `backend/uv.lock`。入口是相对该根的 POSIX 路径。没有只接收入口、隐含使用当前目录的重载。

同一次调用内、返回之前，按这个顺序做完，不能拆成可跳过的第二入口：

1. 把每个入口解析为 `workspace_root` 下的真实路径。绝对路径、`.`、`..`、符号链接逃出工作区、重复真实路径，都直接失败。
2. 按静态可解析导入收集闭包，包导入计入相应的 `__init__.py`。非字面动态导入、运行期加载和无法解析的第一方导入直接失败。得到 `files`。
3. **实际加载证据与核验时点**：闭包完成后、计算文件摘要之前，由本函数调用内部的 `_imported_first_party_files(entrypoints, workspace_root)`。该内部函数启动一个只做导入的子进程，避免调用方已经导入的模块污染 `sys.modules`。子进程按文件位置加载每个入口，不调用 `generate_materials`，也不调用 `os.urandom`；然后把它新加载的、真实路径落在工作区内的第一方模块，连同入口自身，写回父进程。父进程核验其中任一路径都不超出 `files`，否则本函数立即失败并且不返回清单。这一步没有单独的公开入口。该子进程只服务于清单核验，不是材料生成，因此不受生成环境「不使用子进程」的约束。
4. 对 `files` 中的文件按原始字节计算 SHA-256，并读入固定的两项依赖文件。`python_version` 取当前解释器的 `major.minor.patch`。然后返回对象。

返回值不写入仓库，也不当作已冻结清单。实现轮次的测试把 `workspace_root` 指到临时目录里的夹具包，不针对真实仓库调用这个函数来保存摘要。

包内对应物只接收已经构造好的对象：

- 新增 `backend/app/verification/source_manifest.py`，函数 `require_source_manifest` 与 `source_manifest_digest`。只做封闭结构、路径规则、字典序、入口包含、依赖文件两项及次序、摘要格式校验，并按规范编码重算内容摘要。模块内不出现 `open`、`pathlib`、`os`。
- 验证包**不**导入 `backend/tools/` 下的任一工具。工具可以调用包内校验函数。

`tools/trainer/` 不作为这两个工具的位置：其锁文件不在版本 1 的依赖文件清单内，改放那里就要更换清单规格。

## 5. G-18 的过程审计载体

版本 1 已经锁定、并且能够作为过程记录使用的载体只有这两件，本方案不增加第三件：

1. 逐读取记录（`protocol.py` 的 `ReadRecord`：`read_index`、`purpose_label`、`index_key`、`bit_width`、`raw_offset`、`raw_value`、`accepted`、`output`），按物理 `read_index` 连续排列。
2. 14 项承诺（`TranscriptCommitment`）。其中 `generation_started_at` 与 `generation_finished_at` 只按 §4.1 在同一次调用的进入处和成功返回前各取一次，格式遵守 U-5。`manifest_digest` 与 `generator_code_digest` 的取得方式也只按 §4.1。

生成器用代码结构提供 P-10 的约束，供 ③ 做代码审查和非实际夹具核验，而不是用新字段去证明：

- 单函数内按遍历顺序串行读取；
- 每个原始段恰好一次 `os.urandom(bit_width / 8)`；
- 异常或长度不符向上传播，不捕获后重试，不写出承诺，不保留半份结果；
- 源码不导入 `threading`、`subprocess`、`asyncio`、`multiprocessing`。

`74r` §6.1 已经写明：「未按结果筛选、未事后改写、只生成一次」不能仅凭摘要证明。现有 14 项承诺和逐读取记录也没有单独的字段存放这三项过程结论。若要新增承诺字段、协议字段、执行身份条目，或另立一份会进入冻结清单的过程审计载荷，都会改变已锁定的摘要对象。

**登记为须新后缀修订、本方案不实施**：任何超出上述两件现有载体的过程审计对象。实现轮次若发现仅靠这两件载体无法满足审查对 L3-J14 的要求，应停止并申请新的 `74` 后缀，不得在版本 1 内补字段。

## 6. G-1 至 G-20 的模块与测试映射

「拟修改」指将来取得实现授权后要改的现有文件。「拟新增」指那时要新建的文件。本轮一个都不创建、不修改。测试名是建议的落点；G-9、G-4 的补强可以并入既有验证测试，其余集中在第 7 节所列新测试文件，以避免把锁定口径散进与本缺口无关的测试。

### 6.1 本轮补上的包内接口

**G-2 的版本号模型**放在 `config.py`。五个 ② 侧版本号只有这一个承载位置，不散落在调用参数里：

```text
class CampaignLockVersions(BaseModel):
    pairing_and_reset: PositiveInt
    per_hand_bound: PositiveInt
    fragment_template: PositiveInt
    weight_class: PositiveInt
    seat_rotation: PositiveInt

class CampaignConfiguration(BaseModel):
    lock_versions: CampaignLockVersions

class DomainRunSpec(BaseModel):
    ...
    block: NonNegativeInt
    campaign: str
    campaign_configuration: CampaignConfiguration
```

`CampaignLockVersions` 只承载五个尚未锁定的 ② 侧版本号，这个名字不指 ⑥ 的第二层冻结。两个新模型都 `extra="forbid"`、冻结。`campaign` 与 `block` 都是规格上的显式字段，与 `74r` §6.3 一致。`campaign` 必须是小写 64 位十六进制；空串和其他写法在构造时失败。

载荷与摘要的入口**不**接受 `DomainRunSpec`。它们只接受组成字段，因此可以在规格构造之前调用。载荷不包含 `campaign` 自身。四个已锁定对象的版本字面量固定为 `1`；`game` 四项来自人数、筹码和盲注参数；身份与 `campaign_root` 使用锁定常数；五个 ② 侧版本只来自 `lock_versions`。基线与被测标识必须等于身份常数，否则这两个函数失败。

```text
def campaign_configuration_payload(
    *,
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    baseline_identifier: str,
    under_test_identifier: str,
    lock_versions: CampaignLockVersions,
) -> dict: ...

def campaign_configuration_digest(
    *,
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    baseline_identifier: str,
    under_test_identifier: str,
    lock_versions: CampaignLockVersions,
) -> str: ...
```

`DomainRunSpec` 的校验器调用上面的纯函数，把模型上已经赋值的人数、筹码、盲注、两个身份标识和 `campaign_configuration.lock_versions` 传进去，再要求 `campaign` 与返回值相等。不等即拒绝构造。校验器不调用任何以 `DomainRunSpec` 为参数的摘要函数，也不使用 `model_construct`。

另外提供工厂，供调用方不必自己先算摘要：

```text
def build_domain_run_spec(
    *,
    num_players: int,
    starting_stack: int,
    small_blind: int,
    big_blind: int,
    engine_seed: int,
    baseline_identifier: str,
    under_test_identifier: str,
    deal: DealMappingSpec,
    protocol: RandomizationProtocolSpec,
    schedule: tuple[HandPlan, ...],
    block: int,
    campaign_configuration: CampaignConfiguration,
) -> DomainRunSpec: ...
```

工厂先调用 `campaign_configuration_digest`，再调用普通的 `DomainRunSpec(...)` 构造，把得到的摘要填入 `campaign`。它不绕过校验器。直接调用 `DomainRunSpec(...)` 仍然合法，但调用方必须事先用纯函数算出 `campaign`；写错就被校验器拒绝。

索引键的 `campaign` 必须等于 `spec.campaign`，`block` 必须等于 `spec.block`。这个摘要只属于该夹具或该次显式输入，不是五个 ② 侧对象锁定之后的实际 campaign 摘要，实现轮次不得保存它。

**G-12 的运行器类别**不再由 `flow_step_entries()` 产出。该函数今天返回 `step-*` 名称，而且没有清单参数，无法取得代码摘要。覆盖清单改由新函数产出；七个流程名仍来自 `RUN_FLOW_STEPS`，只作为摘要数组的内容：

```text
def runner_flow_digest(algorithm: str) -> str:
    """对 list(RUN_FLOW_STEPS) 这个 JSON 数组取摘要，不加包装对象。"""

def runner_category_entries(
    runner_manifest: Mapping[str, object],
    *,
    algorithm: str,
) -> tuple[tuple[str, str], ...]:
    """恰好三项：runner-flow-version = "1"；
    runner-flow-digest = runner_flow_digest(algorithm)；
    runner-code-manifest-digest = source_manifest_digest(
        require_source_manifest(runner_manifest), algorithm=algorithm)。"""
```

`runner_manifest` 必填。它由包外 `build_source_manifest(entrypoints=("backend/app/verification/runner.py",), workspace_root=...)` 事先造好再传入。`runner_category_entries` 不读盘。`flow_step_entries` 不再作为覆盖清单的构造函数；既有调用改到 `runner_category_entries`。

**G-12 的注入前类别**同样不再把七个规则名包成 `item-*` 条目。七个规则名留在 `guards.PRECHECK_ITEMS`，只作为摘要数组：

```text
def injection_precheck_rules_digest(algorithm: str) -> str:
    """对 list(PRECHECK_ITEMS) 这个 JSON 数组取摘要。"""

def injection_precheck_category_entries(
    algorithm: str,
) -> tuple[tuple[str, str], ...]:
    """恰好两项：injection-precheck-version = "1"；
    injection-precheck-rules-digest = injection_precheck_rules_digest(algorithm)。"""
```

`precheck_rule_entries()` 不再作为覆盖清单的构造函数。

**G-17 的浮点词法**不经过 `canonical_bytes` / `json.dumps`。入口代码载荷单独编码：

```text
def _require_bluff_freq(value: object) -> None: ...
def encode_baseline_entry_payload(payload: Mapping[str, object]) -> bytes: ...
```

`_require_bluff_freq` 要求 `type(value) is float`，拒绝非有限值、负零以及不等于 `0.1` 的值，也拒绝 `Decimal`、整数和 `float` 的子类。负零用符号位判断：`value == 0.0 and math.copysign(1.0, value) < 0`，不除以该值。`instantiation.py` 因此增加 `import math`。`test_verification_runner.py` 的导入白名单只追加 `"math"`，不放宽 `os` 或其他禁止项。`encode_baseline_entry_payload` 自己按键排序写出紧凑 JSON。走到 `positional_defaults.bluff_freq` 时，先调用上述断言，再把字符 `0.1` 写入输出，不把这个浮点交给通用编码器。树中任何其他浮点直接失败。`baseline-entry-code-digest` 改为 `bytes_digest(encode_baseline_entry_payload(...), algorithm=algorithm)`，不再调用 `content_digest`。

**G-20 的排序校验**增加规格参数。现有 `materials_digest` 位于 `instantiation.py`，不在 `materials.py`。本方案**保留这个位置**，只改签名和全部调用，不把函数迁入 `materials.py`，因此也不改 `__init__.py` 的导出模块。`bundle_payload` 仍在 `materials.py`，继续只负责按给定次序编码。

新增的次序校验放在 `materials.py`，由仍留在 `instantiation.py` 的 `materials_digest` 导入并调用：

```text
def require_supplied_materials_order(
    spec: DomainRunSpec,
    bundle: Sequence[HandMaterials],
) -> None: ...

def materials_digest(
    bundle: Sequence[HandMaterials],
    *,
    spec: DomainRunSpec,
    algorithm: str,
) -> str: ...
```

`require_supplied_materials_order` 使用 `spec.num_players`、`spec.schedule`、`spec.protocol`、`spec.block` 和 `spec.campaign`。它要求手序严格递增并与计划一致，手内先按用途遍历顺序、再按完整索引升序，每手条数等于 `3 * N + 6`，索引中的 `campaign` 与 `block` 等于规格上的显式字段。`materials_digest` 在编码前先调用它。

调用链：

- `instantiation.py`：函数留在原地，签名增加必填的 `spec`，并从 `materials` 导入 `require_supplied_materials_order`。
- `runner.py` 的两处调用都补上 `spec`：`build_frozen_manifest` 里组装冻结清单的那次，以及 `verify_frozen_inputs` 里与 `supplied_materials_digest` 重算比对的那次。
- `runner.verify_frozen_inputs` 在现有 `require_materials(spec, bundle)` 之后调用 `require_supplied_materials_order(spec, bundle)`。
- `protocol.verify_manifest_binding` 增加必填关键字参数 `spec: DomainRunSpec`。进入函数后先要求 `protocol is spec.protocol`，再对同一份 `bundle` 调用 `require_supplied_materials_order(spec, bundle)`，然后才做原有的定位比对。清单侧继续用已有的 `require_manifest_consistent(protocol, manifest)` 检查展平次序。
- 该函数的全部现有调用都补上 `spec`：`runner.verify_frozen_inputs` 传入它已有的 `spec`；`backend/tests/test_verification_protocol.py` 的五处调用分别传入 `fixture.spec` 或 `FIXTURE.spec`（`test_multi_hand_audit_passes_end_to_end`、`test_manifest_binding_passes_for_fixture`、`test_manifest_content_digest_is_recomputed`、`test_commitment_manifest_digest_must_match_manifest_content`、`test_manifest_must_match_supplied_materials`）。`__init__.py` 仍导出同名函数。
- `backend/app/verification/__init__.py` 仍从 `instantiation` 导出 `materials_digest`，不新增同名导出。
- `backend/tests/test_verification_runner.py` 的两处直接调用补上 `spec`。名称仍在模块声明表中，不改表项。
- `backend/tests/verification_helpers.py` 的 `run_spec`、`materials_for_hand` 与 `_ordered_keys` 改为构造 `block`、`campaign` 与 `CampaignConfiguration`，并按上述次序排材料。这是既有夹具的配套修改，不是新的协议字段。

| 缺口 | 拟修改 | 拟新增 | 拟测试 | 与版本 1 的关系 |
|---|---|---|---|---|
| G-1 | `deal.py` 的 `_require_player_count`；`config.py` 的 `DomainRunSpec` 人数校验。两处都增加 `N ≤ 23` 的硬失败，并拒绝布尔值 | 无 | 人数 `1`、`23`、`24` 与布尔值 | 实现 L1-J5，不改发牌规则 |
| G-2 | `config.py`：按 §6.1 增加 `CampaignLockVersions`、`CampaignConfiguration`、显式 `campaign: str`、`block`、纯摘要函数与 `build_domain_run_spec`。校验器只调用纯函数 | 无 | 缺 `campaign`、摘要不符、缺五个版本号、多字段、身份不符、`game` 四项与规格不一致即失败 | 摘要不依赖已构造的规格，也不使用 `model_construct`。夹具摘要不是实际 campaign 摘要 |
| G-3 | `protocol.py`：索引比较按载荷中的 `integer_fields` 解析 `block`、`hand` 以及该用途已有的 `draw` 或 `seat`；不再只把抽取次序和座位号当整数 | 无 | `block`、`hand` 的无前导零整数比较；非法渲染失败 | 落实 §8.3.4 已有字段，不新增协议字段 |
| G-4 | `protocol.py`、`instantiation.py`：补上 K-1、K-2，以及索引键 `hand` 与两处 `hand_ordinal` 的一致校验。K-4、K-5 已有路径只做对照审查和夹具补强，不另写一套规则 | 无 | K-1–K-3 的失败夹具；K-4、K-5 用非实际材料确认现有路径仍满足锁定 | 不把「已有路径」写成「已经满足锁定」 |
| G-5 | `protocol.py`：整数字段必须是无前导零十进制，`0` 渲染为 `0` | 无 | `00`、`+1`、空白、前导零失败；`0` 与 `10` 通过 | 实现 §6.3 已写的渲染 |
| G-6 | `identity.py` 的 `require_explicit_seed` 增加 `[0, 2^256)` 上界；`instantiation.py` 核对构造计划里每个 `material.value` 为该范围内的整数，基线 seed 不得为空、布尔或非整数 | 无 | 上界、空值、布尔、负值 | 实现 R3-4 的取值范围 |
| G-7 | **不修改** | 无 | 无 | 裁定未要求把对照类判据内置。内置会把锁定值写进包内，须另行裁定，本方案不采用 |
| G-8 | `execution_identity.py`：摘要须为小写 64 位十六进制；普通文本按 U-2 的可见 ASCII 与七个固定文本逐字比较；浮点文本只接受 `0.1`。`instantiation.py`：参数布局改为 JSON 数组 `["self","seed","samples","bluff_freq"]` | 无 | 七个固定文本、非法字符、`0.10` / `1e-1` / `.1`、逗号布局 | 实现 U-2、U-3 与参数布局锁定值 |
| G-9 | 无生产代码改动（当前两条路径已与 U-1 一致） | 无 | 在既有协议与身份测试中补大端、32 字节、越界与布尔拒绝 | 只补测试，不改字节序 |
| G-10 | `protocol.py`：两个生成时刻必须匹配 U-5 的格式、有效公历、仅 `Z` 后缀，且起不晚于止 | 无 | 偏移时区、五位微秒、非法日期、止早于起 | 实现 U-5，不改 14 项字段集 |
| G-11 | 无包内文件读取 | `backend/tools/source_manifest.py` 的 `build_source_manifest(entrypoints, *, workspace_root)`；包内 `require_source_manifest`、`source_manifest_digest` | 包内测试只接收手造对象。包外测试用临时工作区；多加载一个闭包外模块必须失败且不返回清单 | 签名与核验时点见 §4.2；不改 `source-manifest-v1` |
| G-12 | `execution_identity.py` 校验类别内次序与封闭名称；`runner.py` 新增 `runner_flow_digest` 与 `runner_category_entries`；`guards.py` 新增 `injection_precheck_rules_digest` 与 `injection_precheck_category_entries`。`flow_step_entries` 与 `precheck_rule_entries` 不再构造覆盖清单 | 无 | 缺清单参数、入口不是 `runner.py`、旧名 `step-*` / `item-*`、版本值不为 `1`、六类不是 41 项 | 接口见 §6.1。运行器代码清单的入口固定为 `backend/app/verification/runner.py` |
| G-13 | `protocol.py`：协议模型增加已锁定的 `rejection_rule` 与 `integer_fields`；`protocol_digest` 改为按 `randomization-protocol-v1` 的封闭载荷计算，不再对模型全部字段取摘要；`purposes` 次序必须等于遍历顺序；`rejection_rule` 必须等于 `rejection-whole-multiple-truncation-v1` | 无 | 标识不符、次序不符、字段超出封闭集合 | 摘要算法从「模型全字段」改为锁定载荷。这是实现缺口，不是协议改版；既有摘要夹具要随之改为锁定载荷 |
| G-14 | `config.py` 的 `schedule_digest` 改为 `schedule-v1`（含 `schema` 与 `block`，不含 `campaign`）；`runner.py` 冻结清单中的同名项调用同一函数 | 无 | 缺 `block`、含 `campaign`、手序不递增即失败 | 两处必须使用同一载荷 |
| G-15 | `deal.py`、`protocol.py`、`instantiation.py`、`runner.py`、`guards.py` 分别构造 `deal-mapping-v1`、`purpose-index-mapping-v1`、`public-summary-mapping-v1` 与两个有序名称数组，并按 U-4 重算摘要 | 无 | 与 §8.3.1–§8.3.3、§8.3.6 的字段和次序逐项比对 | 不计算一份供 ⑥ 冻结的实际摘要 |
| G-16 | `protocol.py`：逐读取记录摘要必须按调用时的物理 `read_index` 编码，不得先排序再摘要；`entry_counts`、`rejection_counts` 必须按 `traversal_order` 排列 | 无 | 乱序记录被拒绝；计数次序与遍历次序不符被拒绝 | 材料束排序见 G-20 |
| G-17 | `instantiation.py`：`import math`，`_require_bluff_freq` 用 `math.copysign` 判断负零，以及 `encode_baseline_entry_payload`。入口摘要改走后者。`_constant_payload` 对浮点和未列明类型硬失败。测试白名单只追加 `math` | 无 | `Decimal`、整数、`float` 子类、负零、非有限值、复数、省略号；并断言输出字节里该字段是词法 `0.1` 而不是 `json.dumps` 的结果 | 见 §6.1。不把浮点交给 `canonical_bytes`，也不用除法判断负零 |
| G-18 | 无包内生成器 | `backend/tools/material_generator.py` 的 `GeneratedMaterials` 与 `generate_materials(spec, generator_manifest)` | 见 §4.1 与第 7 节：返回三件对象；失败时调用方拿不到返回值；第二次读取失败后不再调用 | 过程载体见第 5 节。不新增审计字段 |
| G-19 | `instantiation.py`：`baseline-effective-seed` 固定写 `per-hand-arm_b-material`，不再渲染入口默认值 `none`；实际 seed 只出现在构造计划的逐座位 `material.value` | 无 | 条目文本被改即失败；计划中的空 seed 失败 | 条目文本不描述 `non_probed`；该类 seed 仍由计划逐座位承载 |
| G-20 | `materials_digest` **留在** `instantiation.py`，签名增加必填 `spec`。`materials.py` 只新增 `require_supplied_materials_order`。`verify_manifest_binding` 增加必填 `spec`。调用点：`runner.py` 两处摘要、`verify_frozen_inputs`、`test_verification_protocol.py` 五处、`test_verification_runner.py` 两处。`__init__.py` 的导出模块不变 | 无 | 缺 `spec`、`protocol` 不是 `spec.protocol`、错序、条数不是 `3N + 6`、两份编码不一致即失败 | 见 §6.1。不迁移函数。夹具材料由测试给定 |

新增包内模块 `source_manifest.py` 后，`test_verification_runner.py` 里按递归枚举比对的模块声明表必须同时登记该模块。这是不可执行检查的配套更新，不是放宽检查。

`DomainRunSpec` 增加显式 `campaign`、`block` 与 `campaign_configuration` 后，`backend/tests/verification_helpers.py` 的 `run_spec` 改为调用 `build_domain_run_spec`，由工厂填入 `campaign`。需要断言「摘要不符即失败」的测试直接构造 `DomainRunSpec` 并传入写错的 `campaign`，不使用 `model_construct`。这只触及验证测试夹具，不改公开 API、数据库或报告 schema。

## 7. 非实际夹具、模拟随机源与不可执行检查

### 7.1 非实际夹具

夹具全部由测试代码直接写出，并在断言结束后丢弃：

- 五个 ② 侧版本号只写在 `CampaignConfiguration.lock_versions`。夹具通过 `build_domain_run_spec` 得到与组成字段一致的 `campaign`。这个结果只属于该夹具，不保存为实际 campaign 摘要。
- `block`、`hand`、座位号与材料整数使用小的手造值。人数取 `2` 与边界 `23`。
- 源码清单对象的路径和摘要使用临时目录中的夹具文件，或测试内嵌的字典。不读取真实业务源码来形成一份可冻结清单。
- 生成时刻使用测试给定的合法与非法字符串，不取墙上时钟作为将要冻结的时间。
- 夹具不得写入仓库，不得装入 `FrozenRunManifest` 后当作 ⑥ 的冻结结果。

### 7.2 模拟 `os.urandom`

生成器源码保持对 `os.urandom` 的直接调用，不增加随机源参数，以免把测试替身写成协议的一部分。测试只在加载 `backend/tools/material_generator.py` 之后替换该模块所使用的 `os.urandom`：

- 替身按预定字节序列返回，并记录每次调用的长度与次数；
- 另有一组替身抛出异常或返回错误长度，断言生成函数失败且不再调用；
- 预定字节不是一次真实生成的产物，测试结束即丢弃返回的材料对象。

生产入口在未被测试替换时仍调用 `os.urandom`。实现轮次不得为了方便测试而运行一次真实生成并保存输出。

### 7.3 不可执行性检查

既有检查保持为测试侧对 `app.verification` 的逐文件语法树断言，规则不放宽：

- 导入白名单、禁止调用根（含 `os`、`subprocess`、`threading`、`asyncio`、`multiprocessing`）、禁止推进牌局的符号，继续覆盖包内全部模块，包括新的 `source_manifest.py`。
- 包内不得出现对两个包外工具的导入。
- 对 `backend/tools/material_generator.py` 另做一份测试侧语法树断言：必须能见到对 `os.urandom` 的调用；不得导入上述并发与子进程模块；不得出现牌局推进符号、`create_strategy` 或 `HeuristicStrategy(`。这份检查只约束该工具文件，不把 `os` 放进验证包的允许列表。
- 结构检查仍然只约束被扫描到的源码。包外若另写调用方，现有检查本来就不封堵；本方案不把这一点改写成「仓库中不存在其他调用」。

## 8. 将来实现轮次拟运行的命令

下列命令**本轮不运行**。它们只在另行取得实现与测试授权、并且本提案已经通过内容审查之后才执行。工作目录均为 `backend/`。命令的通过只说明这些检查被执行过，不是质量结论，也不是进入 ③ 的依据。

提交前必须实际执行全仓质量检查，与仓库约定一致，不得用定向检查代替：

```text
uv run ruff check .
```

该命令的输出按两类分开登记，两类都要出现在实现轮次的记录里：

- 既有错误：未改动的 `backend/tests/test_distribution_observation_consistency.py` 中已有的 4 项。本轮不修复该文件；不得因为这 4 项而跳过这条命令。
- 本轮发现：上述 4 项以外的每条诊断，按文件登记。其中预计会修改的 `tests/verification_helpers.py` 若出现诊断，算本轮发现，不并入既有 4 项。

定向检查可以额外执行，但不能取代上一条。它必须包含该夹具模块：

```text
uv run ruff check app/verification tools/source_manifest.py tools/material_generator.py tests/verification_helpers.py tests/test_verification_protocol.py tests/test_verification_construction.py tests/test_verification_runner.py tests/test_verification_lock_caliber.py tests/test_verification_payloads.py tests/test_source_manifest_tool.py tests/test_material_generator.py
```

与本方案直接相关的测试：

```text
uv run pytest -q tests/test_verification_protocol.py tests/test_verification_construction.py tests/test_verification_runner.py tests/test_verification_lock_caliber.py tests/test_verification_payloads.py tests/test_source_manifest_tool.py tests/test_material_generator.py
```

全量回归：

```text
uv run pytest -q
```

其中三个 `test_verification_*.py` 为既有文件，四个新名称对应该轮次要新增的测试。不运行 `npm run build`。

## 9. 本提案明确不做的事

- 不修改 `74r`，不把版本 1 升为版本 2。
- 不新增承诺字段、协议字段、执行身份条目或独立的过程审计载荷（第 5 节）。这项若被审查要求，须新的 `74` 后缀，而不是在实现时补上。
- 不计算实际 campaign 摘要、实际源码清单摘要、实际材料或 `code_identity`。
- 不创建、注册或实现 `mixed-local@9`。
- 不修改 `AGENTS.md`、`docs/README.md`、`poker/`、`strategy/`、`api/`、`analysis/`、`storage/`、`frontend/`、`tools/trainer/` 或数据库。
- 不把 G-7 的对照判据改成包内常量。
- 不把测试通过、`ruff` 通过或提交成功表述为质量证据。

## 10. 状态与下一步

- A 路径仍未成立；「非退化」要求仍未满足；域 A / 域 B 仍不可判定；C-1′、C-2′、F-0 仍未建立；②–⑦ 仍未发生；⑥ 的最终运行冻结仍未发生。
- `74r` 的 L-1 至 L-4 已是锁定版本 1。本文件不改变该事实，也不开始 §9 的实现。
- `docs/README.md` 尚未索引 `74s`。索引须另行授权。
- 默认策略仍为 `heuristic@1`。`73b` 的必要冻结项仍为 28 项且未齐备。

**下一步唯一建议动作**：请审查方再次对本提案作内容审查。审查通过之前不修改代码或测试，不运行第 8 节的命令，不生成材料或摘要，不推进 ②、③。
