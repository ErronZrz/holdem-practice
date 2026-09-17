# 25 M7：Kuhn CFR 工具链——最小契约与实施确认

> 日期：2026-09-17。开始时代码基线：`e51e144a6e53a15c04064c066e637248c8dacba8`（`feat: add static showdown share estimate`）。
>
> 开始时实际 Git 状态：`master...origin/master`，工作区干净，`origin` 已配置且当前提交与用户给出的基线一致。
>
> 状态：**已完成候选契约、离线训练器、测试与固定配置验证；未获 commit 或 push 授权。** 本轮未修改现有 Hold'em 规则、策略、复盘、API、UI、数据库或静态 share 原语。

## 1. 本轮目标、已确认基线与未确认边界

M7 的唯一目标是用一个严格、可复现、可精确验证的两人零和 Kuhn poker 小博弈，验证以下离线工具链：

1. 有限信息集上的普通 CFR 与 regret matching；
2. 平均策略的累计、导出、读取和合法信息集 lookup；
3. 精确 best response、NashConv 与 exploitability 计算；
4. 小博弈的固定配置回归与收敛证据。

`20` 已确认的路线为“前置核验与通用契约 → M7 工具链 → M8 多人可行性验证 → 分阶段接入”。M7 仅是工具链验证，不能作为 6–9 人 Hold'em 的均衡、GTO、策略质量或生产接入证据。每轮训练累计仍受本机 CPU、2 小时、训练进程合计 8 GiB 峰值内存、1 GiB 保留产物的共同上限约束；达到任一上限、出现隐藏信息泄漏、规则不一致或无有效质量证据即停止汇报。

前置核验中已经完成且本轮不得回退的事实如下：

- `21` 的翻后随机竞争集合包括 Hero 以外全部未弃牌座位，包含全下者、排除弃牌者；这不是逐池货币 EV。
- `22` 的完整欠注差额为 `C`，实际支付为 `A`；逐层资格投影没有副作用，也不改实际结算语义。
- `23` 的旧 `equity()` 对任意平局仍计 `ties / 2`，不是多人逐层份额或边池 EV。
- `24` 已独立实现静态 pooled 竞争集合的 `StaticShowdownShareEstimate`；它不是边池 EV、完整 CALL EV 或 GTO，且尚未接入任何消费者。

本轮明确不做：多人 Hold'em CFR、范围/位置/公开行动历史在生产 `GameState` 的落地、人格、DeepSeek、真实对局 Bot、复盘参考、API、UI、数据库、在线训练、实时求解，以及把静态 share 接入逐层收益。

## 2. 只读核对结果与最小目录边界

开始只读核对时仓库不存在 `tools/`、`tools/trainer/`、Kuhn、CFR、regret matching、best response、策略产物或训练加载器。`AGENTS.md` 已将 `tools/trainer/` 约定为离线 CFR 训练目录；`20` 也明确训练与 runtime lookup 必须独立。

本轮在获得明确授权后创建了下列隔离实现。后端的 `pyproject.toml` 仍只打包 `app`，其测试根目录仍为 `backend/tests`；训练器不向后端运行/开发依赖加入数值训练框架。

| 实际路径 | 职责 | 不做什么 |
|---|---|---|
| `tools/trainer/pyproject.toml`、`uv.lock` | 独立项目、Python `>=3.12`、仅 `pytest` / `ruff` 开发依赖 | 不改后端依赖或 wheel 打包范围 |
| `tools/trainer/src/kuhn_cfr/game.py` | Kuhn 规则、状态、行动历史、收益与信息集 | 不导入 Hold'em 引擎 |
| `tools/trainer/src/kuhn_cfr/cfr.py` | 全 chance 枚举的普通 CFR、regret matching、平均策略 | 不启动在线训练 |
| `tools/trainer/src/kuhn_cfr/policy.py` | 版本化 JSON 导出、安全读取和 lookup | 不接受模块路径、代码或反序列化对象 |
| `tools/trainer/src/kuhn_cfr/quality.py` | 精确策略值、best response、NashConv 与 exploitability | 不把结果外推到 Hold'em |
| `tools/trainer/tests/` | 规则、训练、产物与质量的 42 个 pytest 用例 | 不访问 SQLite、HTTP、API 或真实手牌库 |

没有增加 CLI、后台任务或运行时入口。训练器仅使用 Python 标准库；其独立开发依赖仅为 `pytest` 与 `ruff`，不引入 NumPy、PyTorch、数据库或 Web 依赖。

## 3. Kuhn poker 的严格规则契约

### 3.1 牌、chance、ante 与玩家

- 玩家固定为 `P0` 与 `P1`；这是 M7 小博弈专用模型，不能进入 N 人 Hold'em 引擎。
- 牌组固定为三张不同且全序的暗牌：`J < Q < K`。
- chance 从六个等概率有序发牌 `[(P0, P1)]` 中全遍历一次：`(J,Q)`、`(J,K)`、`(Q,J)`、`(Q,K)`、`(K,J)`、`(K,Q)`；每个概率为 `1/6`。
- 两名玩家各先支付 `1` 单位 ante。没有盲注、公共牌、加注、边池、短码、平局或额外下注尺度。
- 无人弃牌时按暗牌大小比较；Kuhn 的两张暗牌必不同，因此没有摊牌平局。

### 3.2 行动与公开历史编码

使用下列唯一字母编码，避免将 check 与 call 混为同一 token：

| token | 含义 |
|---|---|
| `x` | check |
| `b` | bet（固定追加 1 单位） |
| `c` | call（固定追加 1 单位） |
| `f` | fold |

非终局历史、行动者与合法动作严格如下：

| 历史 | 行动者 | 合法动作 |
|---|---|---|
| `""` | `P0` | `("x", "b")` |
| `"x"` | `P1` | `("x", "b")` |
| `"b"` | `P1` | `("f", "c")` |
| `"xb"` | `P0` | `("f", "c")` |

终局历史只有 `"xx"`、`"bf"`、`"bc"`、`"xbf"` 与 `"xbc"`。任何其他历史或行动组合均为无效输入，规则层必须拒绝，不能静默纠正或转入 Hold'em 动作模型。

### 3.3 以 `P0` 为准的净收益

收益从 ante 支付前的筹码变化计算；`P1` 收益始终是其相反数：

| 终局 | `P0` 收益 |
|---|---:|
| `bf` | `+1` |
| `xbf` | `-1` |
| `xx` | 暗牌较大者为 `+1`，较小者为 `-1` |
| `bc`、`xbc` | 暗牌较大者为 `+2`，较小者为 `-2` |

因此对每个终局都有 `u0 + u1 = 0`。这是质量计算使用的唯一收益定义，不以自对局总收益为零代替均衡验证。

### 3.4 信息集与不泄漏约束

信息集键由 `(acting_player, own_card, public_history)` 唯一组成，并序列化为：

```text
p{0|1}:{J|Q|K}:{history-or--}
```

例如 `p0:Q:-`、`p1:J:x`、`p1:K:b`、`p0:Q:xb`。完整有限信息集共 12 个：

- `P0` 的每张暗牌各有根节点和 `xb` 节点，共 6 个；
- `P1` 的每张暗牌各有 `x` 节点和 `b` 节点，共 6 个。

策略索引只能使用行动者自己的暗牌与公开历史。不同对手暗牌但相同 `(acting_player, own_card, public_history)` 必须命中同一个键；内部求解状态可以持有完整 deal，仅用于 chance 和终局收益，绝不能参与键生成、lookup 或策略选择。

## 4. CFR、平均策略与可复现训练契约

### 4.1 算法与一次迭代

候选算法是**普通 full-tree CFR**，不用 CFR+、外部采样或自定义启发式：

1. 在每个信息集由累计 regret 的正部分做 regret matching；
2. 正 regret 之和为零时，对该信息集的全部合法动作使用均匀分布；
3. 每次迭代按 §3.1 列出的固定顺序遍历全部六个有序发牌，再按表中的合法动作顺序遍历完整树；
4. 对每个行动者信息集，按对手 reach probability 累积 counterfactual regret；
5. 从第 `1` 次迭代起，按该行动者 own reach probability 累积当前行为策略，最终归一化得到平均策略。

这里“一次迭代”固定指**完整访问六个 ordered deals 各一次**，而不是单个 deal 或随机对局。训练更新中可省去所有 deal 共用的 `1/6` 比例，因为共同的正比例不改变 regret matching 或归一化后的平均策略；精确策略价值与 best response 计算仍必须显式使用 `1/6`。

候选固定训练配置为：

| 字段 | 候选值 |
|---|---|
| `algorithm` | `vanilla-cfr-full-chance-v1` |
| `iterations` | `50_000` |
| `average_strategy_start_iteration` | `1` |
| `chance_model` | `all-six-ordered-deals` |
| `seed` | `0`，记录于配置和导出元数据 |
| action/history order | 本文 §3.2 的表序与 token 顺序 |

全 chance 枚举不消费随机数；因此相同的版本、配置和代码顺序必定给出相同结果，当前 `seed` 仅作为受审计配置字段记录，改变它不会改变该版本的输出。若以后引入抽样 chance，必须先新增明确确认，并且唯一随机源必须由该 seed 派生；不得静默改变 M7 的确定性语义。

### 4.2 平均策略与最小数据模型

训练器保存每个信息集、每个合法动作的累计 regret 和 strategy sum。平均策略定义为每个信息集 strategy sum 的归一化结果；理论上未访问的信息集须以均匀策略表示，但当前完整树遍历应使全部 12 个信息集均被访问。返回的结构化训练结果至少包括：

- `game_id="kuhn-poker"`、`game_version="kuhn-v1"` 与 schema 版本；
- 算法、迭代数、平均策略起始迭代、chance 模型、seed 和“无随机采样”标记；
- 12 个完整信息集的平均策略；
- 训练耗时、信息集数量；
- 从最终**导出后再读取**的平均策略计算出的质量指标。

训练过程的累计 regret 不是策略产物的一部分；首个导出只包含可 lookup 的平均策略和足以审计的元数据，避免把可续训的内部状态误认为可直接部署的策略。

## 5. 策略导出、读取与 lookup 契约

候选产物为一个规范化 UTF-8 JSON 文件，而非 pickle、YAML、任意对象反序列化或动态模块加载。其顶层字段固定为：

```text
schema_version
artifact_type
game
training
probability_units
infosets
quality
```

- `schema_version` 固定为整数 `1`；`artifact_type` 固定为 `kuhn-average-strategy`。
- `game` 必须同时包含固定的 game id 与 game version。
- `training` 必须包含算法、iterations、average strategy 起始轮次、chance 模型、seed 和随机性模式。
- `probability_units` 固定为 `1_000_000_000_000`。每个信息集的动作概率导出为非负整数单位，且合法动作的单位总和必须精确等于该值。
- 导出时使用确定性的最大余数分配把内部浮点概率量化到整数单位；重载后以 `units / probability_units` 恢复 lookup 概率。这样既明确了 `10^-12` 的精度，又避免 JSON 浮点舍入导致的概率和偏差。
- `infosets` 只允许本文 §3.4 的 12 个键；每项必须有准确的行动者、合法动作集合和单位概率。读取时必须同时拒绝缺失项、重复键、未知键、非法动作、负值、总和不等于单位基数、未知顶层字段、非有限 JSON 数值、超大文件和 game/schema 不匹配。
- `quality` 记录导出后重读策略的精确指标，不能记录量化前策略的不同结果。

安全读取只用受限 JSON 解析、大小限制和显式字段校验；不执行文件内容，不解析模块路径，不导入用户指定对象，也不把错误产物作为默认策略。lookup 只接受已经校验的 `(acting_player, own_card, public_history)`，对不在 12 个合法信息集内的请求显式失败。

## 6. 精确质量指标：best response、NashConv 与 exploitability

M7 的主指标是导出后平均策略 \(\bar\sigma=(\bar\sigma_0,\bar\sigma_1)\) 的 **NashConv**，并同时报告惯用的零和 exploitability：

\[
V(\bar\sigma)=u_0(\bar\sigma_0,\bar\sigma_1)
\]

\[
BR_0(\bar\sigma_1)=\max_{\sigma_0}u_0(\sigma_0,\bar\sigma_1),\qquad
BR_1(\bar\sigma_0)=\max_{\sigma_1}u_1(\bar\sigma_0,\sigma_1)
\]

\[
\operatorname{NashConv}(\bar\sigma)=
[BR_0(\bar\sigma_1)-V(\bar\sigma)] +
[BR_1(\bar\sigma_0)+V(\bar\sigma)]
=BR_0(\bar\sigma_1)+BR_1(\bar\sigma_0)
\]

\[
\operatorname{exploitability}(\bar\sigma)=
\frac{\operatorname{NashConv}(\bar\sigma)}{2}
\]

为避免 best response 错误读取对手暗牌，候选实现不在每个 deal 上贪心选行动。它枚举目标玩家 6 个信息集上全部 \(2^6=64\) 个合法纯策略，针对固定对手混合策略精确计算六个 chance deal 的期望收益，再取最大值。有限混合策略的最优响应必存在于此纯策略集合，故这个枚举在 Kuhn 上是精确的，并天然遵守信息集边界。

质量阈值候选为：使用 §4.1 的 `50_000` 次完整迭代，导出后重读策略必须满足 `NashConv <= 0.05`（等价 `exploitability <= 0.025`），且全部概率、收益与质量值为有限数。阈值的作用只是锁定 M7 小博弈工具链回归，不是 Hold'em、多人、人格策略或生产质量门槛。实施后必须记录实际结果；若确定性实现未达到该阈值，不以增加到多人实验、扩大预算或修改指标名称掩盖失败，而是先定位 CFR、平均策略、信息集或 BR 计算问题。

自对局总收益为零只说明此零和游戏的筹码守恒，不能替代上述任一 best-response 指标。

## 7. 最小测试、资源预算与停止条件

已实现并通过以下覆盖：

1. 三张牌、六个无重复 ordered deals、四个非终局节点、五种终局历史和动作非法输入；
2. 相同自己暗牌与公开历史在不同对手暗牌下得到相同信息集键，错误行动者或终局历史被拒绝；
3. 全部终局收益正确且对每个终局 `u0 + u1 == 0`；
4. regret matching 概率非负且归一，所有正 regret 为零时回退均匀策略；
5. 每个平均策略信息集概率非负且归一；
6. 同一版本、seed、迭代数和配置重复训练得到相同平均策略与质量指标，并导出逐字节相同的规范 JSON；
7. 导出后读取的 12 个合法信息集 lookup 正确，未知顶层字段、概率单位和 game version 被拒绝；
8. 独立 BR 小样本：双方均采用“先 check、面对 bet fold”的固定策略时，策略值为 `0`、`BR0=1`、`BR1=1`、`NashConv=2`、`exploitability=1`；
9. `50_000` 次固定配置训练的导出后 `NashConv` 达到 §6 阈值；
10. 临时产物测量并删除，不创建检查点或保留训练产物；
11. 完整后端与前端回归证明没有触及现有 Hold'em engine、策略、复盘、API 或 UI。

实际检查结果：

| 检查 | 结果 |
|---|---|
| `cd tools/trainer && uv run ruff check .` | 通过 |
| `cd tools/trainer && uv run pytest -q` | `42 passed`，3.17s |
| 固定 `50_000` 次训练、导出后重读 | `NashConv=0.0020155181203666064`，`exploitability=0.0010077590601833032`，低于 `0.05` / `0.025` 门槛 |
| 同次质量明细 | `V=-0.05555536126392966`，`BR0=-0.05449918594116668`，`BR1=0.056514704061533284` |
| 资源测量 | 在启用 `tracemalloc` 的单次固定训练中耗时 18.254s，Python 分配峰值 281,632 bytes，临时 JSON 产物 1,709 bytes；均远低于 2 小时 / 8 GiB / 1 GiB 上限 |
| `cd backend && uv run ruff check .` | 通过 |
| `cd backend && uv run pytest -q` | `160 passed, 2 warnings`，9.73s；warning 为既有 Starlette/httpx 与 AnyIO 弃用提示 |
| `cd frontend && npm run build` | 通过，Vite 6.4.3，22 modules transformed，623ms |
| `git diff --check` | 通过 |

`tracemalloc` 仅反映 Python 分配观测，不替代进程 RSS；本次固定状态空间为 6 个 deal、12 个信息集和每侧 64 个 BR 纯策略，实际数据已远低于总预算。测试不以脆弱的微秒门槛替代全轮预算；若将来出现超预算、检查点写入、未声明依赖、数据库/HTTP 访问或隐藏信息泄漏，必须停止并重新确认。

训练器测试保持在独立目录，未为测试发现而改写后端 `testpaths` 或生产打包范围。

## 8. 用户确认记录

### 已确认

- `20` 的阶段路线、离线训练/运行时 lookup 分离、M7 仅验证 Kuhn 工具链，以及本机 CPU 的 2 小时 / 8 GiB / 1 GiB 上限。
- 训练前置中的多人全下竞争集合、多人平局份额、短码跟注价格已经按各自确认边界处理；本轮不回退或接入它们。
- 新模块不能接入实时决策路径，不能把 Kuhn 结果称为 6–9 人 Hold'em GTO 证据。
- 本轮开始前必须先核对实际 Git 状态，且不覆盖用户新增改动。
- 用户已在本轮明确回复“确认按 docs/25 的 M7 候选方案实施”，据此创建隔离训练器、执行训练和完整验证。

### 尚未确认

- commit 或 push；
- 将 Kuhn 产物或 lookup 接入 `backend/app/strategy/`、`analysis/`、`api/`、前端或任何实时路径；
- M8 多人 Hold'em 的抽象、训练或生产接入。

## 9. 实际实现、测试、收敛证据与版本影响

实际新增的离线模块为 `game.py`、`cfr.py`、`policy.py`、`quality.py` 和对应测试；训练器独立锁定依赖，未修改 `backend/app/`、`backend/tests/`、`frontend/`、现有文档 20–24 或真实数据库。

实现遵循本文契约：普通 full-tree CFR 对六个 ordered deals 按固定顺序遍历，regret matching 使用累计正 regret 和均匀回退，平均策略从第 1 次完整迭代开始累计。`seed` 作为元数据记录；该版本无 chance 抽样，训练过程不消费随机数。质量模块枚举每侧 64 个信息集合法纯策略来计算精确 best response，绝不按单一 deal 观察对手暗牌。

策略产物是 schema `1` 的受限 UTF-8 JSON：含 game/version、训练配置、12 个信息集、`10^-12` 整数概率单位和导出后重读的 quality。读取器限制文件为 1 MiB，拒绝重复键、非有限数、未知字段、非法信息集/动作、错误概率和与 game/schema 不匹配；不执行内容或加载动态对象。测量只使用临时 JSON，已删除，不保留策略、检查点或其他训练产物。

固定配置的实际收敛结果见 §7：`NashConv=0.0020155181203666064`，比 `0.05` 阈值低约 24.8 倍；`exploitability=0.0010077590601833032`。这证明的是该实现对 Kuhn 小博弈的 CFR、平均策略、导出/读取和精确 BR 工具链可以复现并通过预定门槛，不是多人 Hold'em 的均衡或 GTO 证据。

版本影响仅限仓库根目录新增的离线 `tools/trainer/` 项目。后端包仍只打包 `app`，没有新的生产依赖、API、数据库格式、策略工厂、运行时 lookup 或用户可见行为。

## 10. 遗留与 M8 前的下一小步

M7 完成且通过小博弈质量门槛后，下一步仍不是生产接入。应单独提出 M8 的多人可行性切片：明确 6/7 人主目标和 9 人早期边界、状态/位置/公开历史、抽象、行动尺度、范围、多人收益、资源测量、产物版本和抽象外回退。M7 不提供这些模型，也不改变 `StaticShowdownShareEstimate`、`equity()`、池层投影、实际结算或任何用户可见行为。
