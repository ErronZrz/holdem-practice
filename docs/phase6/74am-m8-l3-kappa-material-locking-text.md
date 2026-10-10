# 74am M8：L-3 κ 材料锁定文本（版本 2）

> 日期：2026-10-10。
>
> **战役归属**：`74`（「新身份研发与独立验证」战役）。本文件是该战役的第 `40` 份文档，编号 `74am`。
>
> **历史关系**：承接内容复审通过的 `74al`（L-3 κ 材料锁定修订提案）、内容审查通过的 `74ai`（κ 与 `EncodeK2PublicV1`）、内容审查通过的 `74ak`（K-1 为 `heuristic@1`）、已生效的 `74r` L-3 v1 与 `74ae` §9.1。本文件**不修改** `74r` 或其他既有正文。
>
> **编号范围**：双后缀 `am`。本文件不预占 `an` 及之后编号。
>
> **本文性质**：**L-3 随机化协议的第一层锁定修订文本**。L-3 版本递增为 **2**。正式采用 `74al` 复审通过后的指定套餐，写定逐 κ 整数 `seed` 的材料单元、用途、键、域、审计次序、遍历与拒绝规则，以及生成前键集闭合。**不是**实现；**不是**材料生成；**不是** ③ 重跑。
>
> **效力限定（写死）**：
>
> - 用户授权已正式采用下列套餐为 L-3 **v2**。v1 文件保持原样。本文件生效后，§4 所列条款取代 v1 中的对应句子；其中包含 `74r` U-4 里唯一被本修订覆盖的载荷值 `lock_versions.randomization_protocol = 2`。未被 §4 点名的 v1 条款继续有效，不在本文件里重写一遍。
> - **在本文件内容审查通过之前**，不得把 v2 当作已经替换 v1 的 ③ 输入，也不得据此宣布旧核验结论已经失效或重跑 ③。
> - **审查通过之后**，v2 为生效的 L-3 修订。相关旧 L3-J* 与 C-2′ 核验结论**失效**，须在后续**独立** ③ 授权下重验。`74af` 的 ③ 总体不通过在该次重验完成前**持续有效**。
> - **不**生成任何实际键、`σ_public`、seed、材料、digest、清单、身份或 `code_identity`。**不**创建 `mixed-local@9`。
> - **不**改代码、测试、索引或既有文档；**不**运行命令；**不**提交或推送；**不**进入 ④–⑦。

## 1. 授权原文与范围

用户授权原文（摘要）：

```text
裁定：74al 内容复审通过。
两项阻断均已闭合。L3κ-T-append 已排除；键集须生成前闭合。
D-narrow 与原整倍数截断规则可兼容的关系也已更正。

现授权新建且仅新建：
docs/phase6/74am-m8-l3-kappa-material-locking-text.md
性质：L-3 第一层锁定修订文本，版本递增为 v2；不修改 74r v1，
不是实现、材料生成或③重跑。

正式采用：
L3κ-U-be32、L3κ-L-extend、L3κ-K-hand、L3κ-K-hex、
L3κ-D-256、L3κ-A-reorder、L3κ-O-after-deal、L3κ-R-keep-id。
完整 κ 键集必须在材料生成前有限、预注册、可审计地闭合；
运行中只查表，未列键为协议失败，禁止追加读取或补料。

必须明确：每次决策新建 heuristic@1 实例，注入完整 κ 对应的整数 seed；
samples、bluff_freq 是实例化口径。
维持 verification 可配置且不可执行；推进仅在包外。
L-3 v2 生效将使相关 L3-J* 与 C-2′ 旧核验结论失效，须在后续独立③授权下重验；
74af 总体不通过在此之前持续有效。
不生成任何实际键、σ_public、seed、材料、digest、清单、身份或 code_identity。

不得修改其他文件或代码，不运行命令、不更新索引、不提交推送、
不实现或重跑③，不进入④–⑦。完成后仅申请 74am 内容审查。
```

**首轮审查**：**暂不通过**。阻断：`74r` U-4 将 `campaign-configuration-v1.lock_versions.randomization_protocol` 锁定为 `1`，且该配置摘要是全部材料键的 `campaign`。本文件把 L-3 升为 v2 时，没有把该字段承接为 `2`，v2 键空间与 campaign 身份因此没有被同一配置摘要绑定。

**复审轮授权原文（摘要）**：

```text
仅就地修订 74am：
明确承接并覆盖 74r U-4 中唯一受本修订影响的载荷值：
campaign-configuration-v1.lock_versions.randomization_protocol = 2。
写明 campaign-configuration-v1 的 schema、其余封闭字段、禁止项与摘要算法不变；
不新增字段、不生成实际 campaign 摘要。
写明 v2 的每个完整索引键 campaign 字段必须等于以该版本号 2 重算的配置摘要；
版本号为 1 的摘要不得作为 v2 材料键的 campaign。
将此项加入 v2 生效、审计／协议载荷绑定、旧结论失效及后续重核验说明。
不改 74r v1 或其他文件，不选新套餐，不运行命令、不生成材料／seed／摘要／身份，
不实现或重跑③，不进入④–⑦。
修订后仅申请 74am 内容复审。
```

**属于本文件**：L-3 v2 的采用条款、对 v1 的取代范围、配置版本与 `campaign` 的绑定、注入条件、生效与重核验。

**不属于本文件**：对 `74r` 的就地修改；L-2／L-4 修订正文；包外实现；③ 执行记录；`docs/README.md` 索引。

## 2. 文件级改动与执行类别

| 文件 | 改动 |
|---|---|
| `docs/phase6/74am-m8-l3-kappa-material-locking-text.md` | **新增**后经审查 **就地修订**（`randomization_protocol` 承接为 `2`） |

| 类别 | 内容 |
|---|---|
| L-3 锁定修订文本 | 版本 2；指定套餐落成条款 |
| **未执行** | 改 `74r`、代码、测试、索引、命令、实际键／`σ_public`／seed／材料／digest／清单／身份、实现、③ 重跑、④–⑦、提交、推送 |

## 3. 版本与所采用的套餐

| 项 | 锁定 |
|---|---|
| **L-3 版本** | **2**。该整数同时写入 `campaign-configuration-v1.lock_versions.randomization_protocol`（§6.6） |
| **协议载荷 schema** | `randomization-protocol-v2`。它只标记本文件的用途与键定义，**不是**新的承诺字段，本文件也不计算其摘要 |
| **v1 文件** | `74r` 保持不动。其中的 L-3 仍称版本 1，供历史引用 |
| **材料单元** | **L3κ-U-be32**，域为 **L3κ-D-256** |
| **用途** | **L3κ-L-extend** |
| **手序字段** | **L3κ-K-hand** |
| **`σ_public` 键编码** | **L3κ-K-hex** |
| **审计** | **L3κ-A-reorder** |
| **用途级次序** | **L3κ-O-after-deal** |
| **拒绝规则** | **L3κ-R-keep-id** |
| **键集** | 生成前闭合。**L3κ-T-append** 不是本版本的路线 |

## 4. v2 取代 v1 的范围

v2 生效后，只取代 `74r` 里下列读法。其余 v1 句子仍然有效，包括来源接口 `python-os-urandom@1`、环境 `local-single-process-no-parallel@1`、`deal` 与 `arm_m` 的整行、承诺的 14 个字段名、`sha256`、紧凑 JSON、一次性生成、`campaign-configuration-v1` 除下表点名的那一个整数以外的全部封闭字段，以及「协议不证明真实独立性」。

| v1 位置 | v2 的取代 |
|---|---|
| §6.2 `non_probed`、`arm_b` 的键、定位字段，以及「K-2′：同一 `(campaign, block, hand, seat)` 两臂共享」 | 改为 §6 的完整 κ 键与 §7 的共享规则 |
| §6.3 把 `seat` 只定义为非被测座位集合 | 改为 §6.3：按用途区分座位；并增加 `event_index`、`sigma_public` |
| §6.4 对这两用途「其余字段一律按整数比较」 | `sigma_public` 按字符串比较；整数字段仍按整数比较 |
| 把 `non_probed`／`arm_b` 读成手级一颗种子 | 不再成立。每一完整 κ 一条整数 `seed` |
| U-4 载荷中 `lock_versions.randomization_protocol = 1`，以及「取值为 `1` 的四项依次对应 L-1 至 L-4」里**把 L-3 仍标成 1** 的那一读法 | 改为 §6.6：该字段为 **2**。L-1、L-2、L-4 在 `lock_versions` 中仍为 `1` |

`deal` 的键仍是 `(campaign, block, hand, draw)`。`arm_m` 的键仍是 `(campaign, block, hand)`。二者的输出域、位宽与角色不因本文件改变。

## 5. 注入条件（`heuristic@1`）

本条件来自 `74ak` §4.1，写入 v2 后成为材料的使用规则。

```text
每一次决策，包外新建一个 heuristic@1 实例，
注入与该次完整 κ 对应的整数 seed。
samples 与 bluff_freq 不是这颗 seed 的一部分。
```

| 项 | 锁定 |
|---|---|
| **成员** | 规范标识 `heuristic@1`。无版本别名 `heuristic` 不是该成员 |
| **非被测座位** | 两臂都使用该成员（O-a），并查 `non_probed` |
| **基线臂被测座位** | 继续使用该成员（`74r` L-2 v1），并查 `arm_b` |
| **被测臂被测座位** | 仍用 `arm_m`。本文件不创建、不注册、不选定 `mixed-local@9` |
| **构造** | 受控注册表 `registry-seed`：`create_strategy("heuristic@1", seed=该整数)`。每次决策新实例 |
| **口径** | `samples` 取类默认 `500`，`bluff_freq` 取类默认 `0.10`。二者是实例化口径，不进入 `M(κ)`，不随 κ 改变 |
| **空种子** | `None` 不是材料 |
| **`strategy/`** | 不修改 `HeuristicStrategy` 来完成注入 |

## 6. 用途、键与材料单元

### 6.1 四用途

结构角色沿用 v1 的枚举字面量。用途级次序见 §9。

| 用途标签 | 结构角色 | 完整索引键（顺序即比较顺序） | 整数定位字段 | 输出 |
|---|---|---|---|---|
| `deal` | `deal` | `(campaign, block, hand, draw)` | `block`、`hand`、`draw` | 与 v1 相同，不在本文件改写 |
| `non_probed` | `non-probed-seed` | `(campaign, block, hand, seat, event_index, sigma_public)` | `block`、`hand`、`seat`、`event_index` | `heuristic@1` 的整数 `seed` |
| `arm_m` | `under-test-material` | `(campaign, block, hand)` | `block`、`hand` | 与 v1 相同：被测座位主键材料的整数形式 |
| `arm_b` | `baseline-seed` | `(campaign, block, hand, seat, event_index, sigma_public)` | `block`、`hand`、`seat`、`event_index` | `heuristic@1` 的整数 `seed` |

`non_probed` 与 `arm_b` 的键都覆盖 `74ai` 的 κ。`hand` 承担 `hand_ordinal`。`sigma_public` 是 `σ_public` 的键上编码，不是另一套公开投影。

### 6.2 字段

| 字段 | 规则 |
|---|---|
| `campaign` | `campaign-configuration-v1` 的 SHA-256，小写 64 位十六进制，按字符串比较。v2 的每一条完整索引键上，这个值必须等于 §6.6 以 `randomization_protocol = 2` 重算的摘要。版本号为 `1` 的摘要**不得**充当 v2 材料键的 `campaign`。本文件不生成该摘要 |
| `block` | 与 v1 相同：非负整数，等于运行前规格的块序号 |
| `hand` | 正整数。**等于**同手 `HandPlan.hand_ordinal`，并同时等于同手 `HandMaterials.hand_ordinal` |
| `draw` | 只用于 `deal`，规则与 v1 相同 |
| `seat` | 非负整数。`non_probed` 的取值集合是 `{0…N−1}` 去掉该手被测座位。`arm_b` 的 `seat` 必须等于该手被测座位 |
| `event_index` | 非负整数。对每个 `(seat, hand)`，从 `0` 起，该座每出现一次决策机会加 `1`。定义与 `74ai` §4.2 相同：不回退，不在不同 `σ_public` 下复用同一个序号 |
| `sigma_public` | §6.4。按字符串比较 |

整数字段在索引键的字符串数组里渲染为无前导零的十进制 ASCII（`0` 为 `"0"`），比较时按整数。这与 v1 的整数渲染相同。

### 6.3 同一 `event_index` 只对应一个 `σ_public`

在已闭合的键集中，对同一用途、同一 `(campaign, block, hand, seat, event_index)`，至多有一条 `sigma_public`。两条不同的十六进制不得共用这个序号。这是 `74ai`「禁止在不同 `σ_public` 下复用 `event_index`」在键集上的写法。

### 6.4 `sigma_public`：小写十六进制

`σ_public` 仍是 `74ai` §4.2 所定义的 UTF-8(`EncodeK2PublicV1(G, L)`) 字节序列。本文件**不**替换该编码，也**不**把它换成哈希。

键字段 `sigma_public` 是这些字节的小写十六进制：

- 每个字节变成两个字符，高半字节在前；
- 字母表只含 `0123456789abcdef`；
- 不加重前缀，不加大写，不加空白，不截断；
- 字符长度恰为字节长度的两倍，因此必须是正偶数；
- 从左到右每两位还原一个字节后，必须得到原来的 `σ_public`。

空串、奇数长度、大写或字母表以外的字符都不是合法键分量。字符串序与底层字节的字典序一致，因为每个字节的两位十六进制保持原顺序。

### 6.5 整数域与八位组身份（L3κ-U-be32，L3κ-D-256）

`non_probed` 与 `arm_b`：

```text
输出域 D = 2^256
位宽 w = 256
接受值 seed 满足 0 ≤ seed < 2^256
```

材料清单中的 `value` 是这个 JSON 整数。`M(κ)` 相等所用的八位组是该整数的 **32 字节无符号大端**表示：整数 `0` 为 32 个零字节，整数 `2^256 − 1` 为 32 个 `0xFF` 字节。同一整数只有一种这样的 32 字节序列。

两臂在同一 `non_probed` 键上必须得到同一个整数，因而得到同一串 32 字节。`arm_b` 在自己的键上同样以这 32 字节识别那颗 `seed`。`samples` 与 `bluff_freq` 不进入这 32 字节。

### 6.6 配置摘要绑定 L-3 版本 2

`74r` U-4 的 `campaign-configuration-v1` 摘要，就是全部材料键的 `campaign` 字段。v1 把 `lock_versions.randomization_protocol` 写成 `1`。L-3 升为 v2 之后，键空间必须和这份配置身份绑在同一个摘要上。本文件因此**只覆盖这一个载荷值**，不改 `74r` 文件：

```text
campaign-configuration-v1.lock_versions.randomization_protocol = 2
```

| 项 | 锁定 |
|---|---|
| **覆盖的值** | 仅 `lock_versions.randomization_protocol`。它对应 L-3，现为 **2** |
| **仍为 1 的三项** | `deal_mapping`、`construction_mapping`、`execution_identity_schema` 保持 U-4 的 `1`，分别仍对应 L-1、L-2、L-4 |
| **schema** | 仍是 `campaign-configuration-v1`。不改名，不升成另一套 schema |
| **其余封闭字段** | `campaign_root`、`game` 的四个正整数、`identities.baseline`、`identities.under_test`，以及 `lock_versions` 里尚未锁定的五个占位正整数，名称与 U-4 相同 |
| **不新增字段** | 封闭结构的字段集合与 U-4 相同，不得增减 |
| **禁止项** | 与 U-4 相同：不得写入自身摘要或完整运行前规格摘要、`block`、逐手计划或具体手序、随机材料、seed、节点、清单、结果、收益、身份输出、观测读数、时间戳、实际 `code_identity`，也不得写入某条 `σ_public` 实例 |
| **摘要算法** | 与 U-4 相同：紧凑 JSON、键排序、`ensure_ascii = true`、UTF-8、SHA-256、小写 64 位十六进制 |

v2 的每个完整索引键——`deal`、`non_probed`、`arm_m`、`arm_b` 全部包括在内——其 `campaign` 必须等于**按上表重算**的摘要，也就是载荷里 `randomization_protocol` 为 `2` 的那一次 SHA-256。用 `randomization_protocol = 1` 算出的摘要**不得**作为 v2 材料键的 `campaign`。同一条 v2 键集里的各键，这个 `campaign` 必须彼此相同。

U-4 中五个尚未锁定的占位正整数仍然没有第一层锁定值，因此**实际 campaign 摘要仍然不可生成**。本文件只写定版本号这一个整数，不填那些占位，也不算出任何十六进制摘要。

## 7. 谁读取哪一条

| 决策点 | 用途 | 共享 |
|---|---|---|
| 两臂的非被测座位 | `non_probed` | 同一完整 κ **一条**整数。两臂同键同值 |
| 基线臂被测座位 | `arm_b` | 只服务该臂该座。与 `arm_m` **不**共享，也**不**与同手的 `non_probed` 混为同一次抽取 |
| 被测臂被测座位 | `arm_m` | 保持 v1：与 `arm_b` 独立（T-a） |

κ 的四分量按 `74ai` §4.2.5 比较：`seat`、`hand`（即 `hand_ordinal`）、`event_index` 为整数相等；`σ_public` 为字节相等，等价于 `sigma_public` 字符串相等。`M(κ)` 相等即 §6.5 的 32 字节相等。

`σ_public` 字节不同，则键不同，不得复用另一键的 `seed`。

## 8. 键集在生成前闭合

```text
完整键集在任何材料读取之前，以有限、预注册、可审计的清单闭合。
生成只覆盖这份清单。运行中只查表。
未列入清单的决策边界是协议失败：停止。
不得依据行动历史、策略输出或新出现的 σ_public
追加外部随机读取、生成材料或改写已有 M(κ)。
```

| 项 | 锁定 |
|---|---|
| **清单内容** | 有限条完整索引键，覆盖本次允许生成的 `deal`、`non_probed`、`arm_m`、`arm_b`。其中后两类基线种子键必须是 §6.1 的六字段 κ 键 |
| **可审计** | 生成结束后，被接受的材料键集合与这份清单**恰好相等**：不少键、不多键。承诺仍用 v1 的 `manifest_digest` 等 14 个字段承载生成结果；本文件不新增承诺字段，也不计算摘要 |
| **失败** | 运行中装出的 κ 不在清单内，即为协议失败。不得临时补一条键或补一次读取 |
| **排除** | `L3κ-T-append` 不得实现。同一键不得再读、不得改写，并不能把「跑起来才出现的键」变成合法生成 |

`campaign-configuration-v1` 仍不得写入具体材料、seed 或某条 `σ_public` 实例。键集清单是生成前的独立预注册对象，不塞进该载荷。清单里每一键的 `campaign` 仍须满足 §6.6。本文件不给出任何一条实际键，也不生成该摘要。

## 9. 遍历次序（L3κ-O-after-deal）

用途级，与 v1 的用途顺序相同，因为逐 κ 的 `non_probed` 仍在 `deal` 之后、`arm_m` 之前，`arm_b` 仍在 `arm_m` 之后：

```text
deal → non_probed → arm_m → arm_b
```

用途内部按完整键升序：

- `deal`、`arm_m`：比较规则与 v1 相同；
- `non_probed`、`arm_b`：`campaign`（字符串）→ `block` → `hand` → `seat` → `event_index` → `sigma_public`（字符串）。

物理 `read_index` 只走已闭合清单，顺序等于上述规范次序。同一完整键的读取相邻；接受后不得再读该键。不得把运行中新出现的状态插进这个顺序。

材料清单与送交材料束：用途按上面的次序，用途内按完整键升序。送交材料束的手与手之间仍按 `hand_ordinal` 升序，手内再按该次序。`entry_counts` 与 `rejection_counts` 严格按这四个标签的次序排列。

## 10. 拒绝规则（L3κ-R-keep-id）

继续引用 v1 标识 `rejection-whole-multiple-truncation-v1`。接受公式、拒绝处理、同键相邻与接受后不得再读都不变：

```text
B = D · ⌊2^w / D⌋
raw_value < B 时接受，输出 raw_value % D
仅 [B, 2^w) 被拒绝
拒绝后以同一用途、同一完整键、同一位宽继续读取
```

`non_probed`、`arm_m`、`arm_b` 的 `D = 2^w = 2^256`，故 `B = 2^256`，这三用途的拒绝区间为空。这是原公式的推论，不是另一条规则，因此**不**更换标识。`deal` 的收缩域与 v1 相同，仍可能拒绝。

标识的指称仍是 v1 §6.5 的那一套语义。本文件没有改那些句子，也没有改 `74r` 里的标识字符串。

## 11. 审计与承诺（L3κ-A-reorder）

下列各项保持 v1，不另起名字：`commitment_form = transcript-commitment-v1`、`audit_format_version = 1`、`read_record_encoding = compact-json-v1`、`digest_algorithm = sha256`、逐读取记录的八个字段、承诺的 14 个字段名。

v2 只改这些字段**所排列的键**：

| 对象 | v2 要求 |
|---|---|
| `traversal_order` | `deal`、`non_probed`、`arm_m`、`arm_b` |
| `entry_counts`、`rejection_counts` | 按该次序 |
| 逐读取记录的 `index_key` | 字符串数组，顺序与 §6.1 该用途的字段顺序相同。`sigma_public` 用 §6.4 的小写十六进制 |
| 材料清单 | `purpose_label`、`index_key`、`value`。`value` 为 JSON 整数。次序见 §9 |
| 协议载荷 | schema 为 `randomization-protocol-v2`；`rejection_rule` 仍为 `rejection-whole-multiple-truncation-v1`；`purposes` 按 §9 排列，并写明 §6.1 的键 |
| **`campaign` 绑定** | 全部索引键的 `campaign`，以及承诺／执行身份中的 `campaign-configuration-digest`，都等于 §6.6 以 `randomization_protocol = 2` 重算的 `campaign-configuration-v1` 摘要。版本号为 `1` 的摘要不得绑定到 v2 材料键 |

不新增承诺字段，不把摘要算法改成 `sha256` 以外的算法，也不改 `campaign-configuration-v1` 的摘要算法。本文件不产生任何一个摘要字节。

## 12. 执行边界

| 边界 | 锁定 |
|---|---|
| **`verification/`** | 可配置且不可执行。不推进牌局，不在决策边界调用策略，不生成材料 |
| **推进** | 只在包外。包外编排在决策前固定 `74ai` 的 `(G, L)`，算出 `EncodeK2PublicV1` 与 κ，再查已经生成的整数 `seed` |
| **查表失败** | κ 不在生成前的键集中：协议失败，不补料 |
| **`poker/`** | 不依赖 `api/`、`llm/` |
| **`strategy/`** | 只经 `GameState` 与 `poker/` 交互 |

实现、包外编排的代码，以及 K-4（执行身份／`code_identity`、参考／评估版本化）都是后续单列授权。标识保持 `heuristic@1` 不豁免 K-4。本文件不预定是否升版。

`74r` L-4 里 `baseline-effective-seed` 的固定文本仍是 `per-hand-arm_b-material`。那是 L-4 的句子，本文件不改它。v2 生效后，该句与逐 κ 的 `arm_b` 是否还相符，留待 K-4 或另行的锁定授权，不在这里裁定。

## 13. 生效、失效与 `74af`

| 时点 | 状态 |
|---|---|
| **本文件审查通过之前** | v2 文本已写定，但还不是 ③ 的输入。不重跑，不改 `74af` |
| **审查通过、v2 生效** | §4 的取代生效，包括 `randomization_protocol = 2`。依赖 v1 键空间或依赖「`campaign` 来自版本号 `1` 的配置摘要」的相关 **L3-J\***（含 L3-J9）与 **C-2′** 旧核验结论**失效**（`74ae` §9.1） |
| **失效之后** | 须另一次独立 ③ 授权重验。推导方不得签署。重验至少包括：六字段 κ 键、生成前键集与清单一致、运行中未列键即失败、两臂 `non_probed` 同键同 seed、32 字节大端、`event_index` 不跨 `σ_public` 复用、拒绝标识仍为原标识、用途次序、每次决策新建 `heuristic@1`，以及每个完整索引键的 `campaign` 等于 `randomization_protocol = 2` 的配置摘要、且不等于版本号为 `1` 的摘要 |
| **重验完成之前** | `74af` ③ 总体不通过**持续有效**。C-2′ **不得**标为已建立 |
| **重验即使通过** | 也不由本文件进入 ④–⑦ |

A 路径在本文件中**未成立**。

## 14. 本文件不生成

不生成、不冻结、不举例写出：

- 任何完整键、`sigma_public` 字符串或 `σ_public` 字节；
- 任何 seed、raw 值或 32 字节实例；
- 任何 digest，包括 campaign 摘要、材料清单、逐读取记录、承诺对象或 `code_identity`；
- 任何身份，包括 `mixed-local@9`。

§6 的字段名是协议字段，不是一条已经填好的键。

## 15. 后续顺序（建议，不授权执行）

```text
1. 对本文件作内容复审（本回合仅申请此项）。
2. 审查通过后，v2 生效，包括 randomization_protocol = 2；
   相关旧 L3-J* 与 C-2′ 结论失效。失效本身不是③重跑。
3. 另行授权：实现与包外编排，并在该次授权中落盘 K-4。
4. 另行授权：独立③核验与重跑。74af 总体不通过在重跑完成前仍然有效。
5. ④–⑦：仍须单列授权。
```

## 16. 状态与不主张

- 本文件是 L-3 **锁定修订文本**，不是质量证据，不构成 exploitability、NashConv 或 best-response 上界。
- 它不证明操作系统熵的独立性或均匀性。
- 默认策略与基线成员仍是 `heuristic@1`。`mixed-local@8`／`-v10` 仍为质量未获支持。`mixed-local@9` **未**创建。
- 本文件修订轮次**未**运行命令。

## 17. 申请 `74am` 内容复审

请审查方核验首轮阻断是否闭合：

1. **配置版本**：§6.6 是否写明唯一被覆盖的 U-4 载荷值是 `campaign-configuration-v1.lock_versions.randomization_protocol = 2`；schema、其余封闭字段、禁止项与 SHA-256 摘要算法是否保持不变；是否没有新增字段，也没有生成实际 campaign 摘要；
2. **键上的 campaign**：是否写明 v2 每个完整索引键的 `campaign` 必须等于以版本号 `2` 重算的配置摘要，版本号为 `1` 的摘要不得作为 v2 材料键的 `campaign`；
3. **生效与重核验**：§11、§13、§15 是否把这项绑定写进协议／审计、v2 生效、旧 L3-J*（含 L3-J9）与 C-2′ 失效，以及后续独立 ③ 重验；此前 `74af` 总体不通过是否仍然有效；
4. **套餐未改**：是否仍是原先采用的那一套，没有另选材料单元、用途、键编码、域、审计、遍历或拒绝规则；
5. **边界**：是否仅就地修订本文件，未改 `74r` v1、代码或其他文件，未运行命令，未生成材料、seed、摘要或身份，未实现或重跑 ③，未进入 ④–⑦。

**下一步唯一建议动作（须另行授权）**：审查方对本文件 **复审版** 作 **内容复审**。复审通过**不**自动实现，**不**自动重跑 ③，**不**进入 ④–⑦。
