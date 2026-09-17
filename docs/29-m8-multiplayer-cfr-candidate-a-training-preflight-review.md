# 29 M8：多人 CFR 候选 A——训练前评审与受限实验准备

> 日期：2026-09-17。
>
> 开始时 Git 基线：`78d267c9cd0e13daf477a09ce6469e2477a1c5a2`（`feat: add multiplayer MCCFR exporter`）。实际状态为 `master...origin/master`，工作区干净，`HEAD` 与 `origin/master` 一致。
>
> 状态：先完成训练前代码复核与受限实验设计；后获授权实现训练前验证、受控运行和独立测量记录能力。**没有启动有预算 A6/A7/A9 训练、实际质量实验、长期策略导出或检查点。** 未修改 `kuhn_cfr`、后端、前端、锁文件或生产运行时；未 commit、未 push。

## 1. 本轮授权边界

本轮不构成实际训练授权。候选 A 仍限于独立离线 `tools/trainer/`，不得依赖 `api/`、`llm/`、真实 SQLite、HTTP 生命周期或生产状态。

既有总预算继续有效：同一轮训练相关进程累计 CPU 不超过 2 小时、峰值 RSS 合计不超过 8 GiB、保留实验产物不超过 1 GiB；不得自动扩预算、转云、转 GPU 或无限重跑。本轮新增的受控运行器在 iteration 边界接收显式时钟和 RSS 读取器，记录资源阈值、覆盖、权重与停止原因；它不启动子进程、不能替代进程树监督或硬杀，因此未来实际实验仍须由外层监督实际执行这些限制。

本文先记录审查结论、拟议实验协议和待决 schema 方案；后续追加记录已获授权的离线验证实现。所有数值训练配置、seed、质量通过阈值、保留路径和实际实验 schema 决策均保持待用户明确授权，不能把本文中的上限计划当作已获准执行的命令。

## 2. MCCFR 语义复核

### 2.1 已确认的实现语义

| 审查点 | 代码事实 | 审查结论 |
|---|---|---|
| 迭代与同步性 | 每轮先冻结全部 regret-matching 行为策略，按相对座位 `0..N-1` 收集 pass delta，随后才按固定信息集/动作顺序合并。 | 不会在同一 iteration 内让较早座位看到较晚座位尚未声明的更新。 |
| chance 与对手抽样 | 每个 traverser pass 从独立派生的 chance seed 抽取一份 uniform ordered deal；非 traverser 节点仅从冻结策略的正概率动作抽样。 | 符合当前候选 A 的 external-sampling 定义。 |
| traverser 分支 | traverser 节点枚举其全部合法动作，计算各动作递归效用和冻结策略下的节点期望。 | regret delta 的形状为 `action_utility - node_utility`。 |
| 多人终局效用 | 终局返回 `terminal_outcome(...).utilities[traverser]`。 | 没有把另一座位的效用取负来代替当前玩家效用，避免了两人零和假设。 |
| 平均策略 | 从显式 `average_strategy_start_iteration` 起，在 traverser 节点累计 `own_reach / opponent_sampling_probability * strategy[action]`。 | 这是当前 uniform 一次 chance、对手路径采样下的平均策略采样修正；该累计量本身不是跨信息集可比较的 visit 计数。 |
| 随机流 | `master_seed`、人数、iteration、traverser 和 purpose 经 `sha256-64be-v1` 派生；chance 与对手动作 purpose 分离。 | 完整重跑可重放，并避免 chance 流因对手递归分支消费量而被扰动。 |

当前 uniform 根 chance 对每个固定私有 rank 信息集都带有相同的常数命中比例；该比例在**同一信息集内**归一化平均策略时抵消。因此，当前平均策略读取语义可以成立，但不能把 `strategy_sum` 的绝对大小解释为跨信息集 coverage、有效样本量或未来非均匀/多阶段 chance 的通用累计量。

### 2.2 已有测试覆盖与不足

已有测试覆盖冻结快照、延后批量提交、每个 pass 一次 chance 抽样、traverser 枚举、对手单动作抽样、零概率动作保护、平均策略起始轮次和固定 seed 的短路径重放。规则与信息集结构覆盖 `N=6/7/9`。

仍有以下必须在启动有预算训练前正视的限制：

1. MCCFR 实际 traversal、同步更新、平均策略和重放行为测试主要走 `N=6` 的短路径；`N=7/9` 当前主要验证信息集预分配，未获得同等级训练路径实证。
2. 现有测试验证了 estimator 的结构和权重形式，尚未用独立全 chance/full-tree 计算器把 sampled regret 与平均策略累计的样本均值逐项比对。因此不能把单元测试表述为 estimator 数值无偏性的独立证明。
3. `strategy_sum` 未被访问时，平均策略会回退为均匀分布。导出器要求完整信息集覆盖，故“JSON 含全部信息集”不表示这些信息集已被访问或充分训练。
4. `1 / opponent_sampling_probability` 在低概率公开路径上可能产生高方差。现有结果不汇总最大值、分位数、有效样本量或访问信息集数。
5. 随机流隔离保证完整从头重跑的可重放；它不承诺在策略或递归分支改变后，可只凭 iteration 编号随机访问同一条未来对手动作轨迹。

### 2.3 训练前必须补齐的独立核验

在任何长期 A6/A7 训练之前，应先获得单独授权并完成一个有限、离线的 estimator 核验：对固定的非均匀策略剖面，在 `N=6` 全枚举 720 个 ordered deal 与规则树，独立计算选定信息集的 counterfactual regret/平均策略目标；再用预先固定的多组 seed sampled pass 均值对照。该核验必须记录比较对象、样本数、误差口径和结果，不得从训练结果反推或调整对照策略。

该核验只是对当前实现的抽样估计量的工程验证，不是多人抽象的均衡、NashConv、exploitability、GTO、真实 EV 或生产可用性结论。

## 3. 受限实验协议（未授权、不可执行）

### 3.1 训练前不可变 manifest

每一个未来实验必须在运行前写入单独、版本化的 manifest，并在结果产生前冻结。最少字段如下：

| 字段 | A6/A7 必填要求 |
|---|---|
| 代码身份 | Git commit、干净/脏工作区状态、`trainer_version`、Python 完整版本、算法/PRNG/seed 派生标识。 |
| 游戏与训练 | `player_count`、精确 `iterations` **或**精确训练墙钟上限、`average_strategy_start_iteration`、`master_seed` 或固定 seed 集合。 |
| 资源控制 | CPU 总上限、并发进程数、RSS 预警/硬停阈值、墙钟阶段配额、产物总量与单文件上限、外部监控方式和停止信号。 |
| 质量协议 | profile 是否全 chance、固定 probe manifest、coverage 定义、稳定性 seed 集合、计算对象、质量阈值与失败处理。 |
| 保留策略 | 最终策略、测量记录、日志、检查点的精确路径、数量、单项上限和清理规则。 |
| schema 决策 | 是否只导出现有未测量策略 JSON，或是否先获准实现新的策略/测量 schema。 |

本轮没有替用户选择 `iterations`、训练时间、`master_seed`、seed 集合、质量阈值或保留目录。它们均为 `UNSET`；任何未在 manifest 中明确的值不得用隐式默认值补齐。

### 3.2 既有预算内的阶段上限

如未来获得完整执行授权，既有可行性计划的总墙钟上限为 110 分钟，且所有训练、评估、重试和临时导出均计入同一轮：

| 阶段 | 最多累计时间 | 必须停止或降级为未测量的条件 |
|---|---:|---|
| A6 构造、规则和采样预检 | 5 分钟 | 规则、信息集、seed、守恒或独立核验失败即停止。 |
| A6 external-sampling 训练 | 25 分钟 | 到达该阶段时限、RSS 预警或硬停、非有限值、资源/产物限制触发即停止。 |
| A6 全 chance profile 与固定 probe | 15 分钟 | 超时只记录“无精确质量证据”，不得延长或改低口径后宣称通过。 |
| A7 external-sampling 训练 | 30 分钟 | 同 A6。 |
| A7 全 chance profile 与固定 probe | 20 分钟 | 同 A6。 |
| A9 构造与短采样边界路径 | 10 分钟 | 不运行长期训练、完整 chance profile 或长期策略导出。 |
| 导出回读、资源汇总与清理 | 5 分钟 | 超限不再创建新工件。 |

RSS 达到 6 GiB 时触发预警并停止当前阶段；任一训练相关进程或其合计达到 8 GiB 时立即终止实验。保留文件总量达到 1 GiB 前停止创建新实验；当前单个策略 JSON 还必须满足全局 64 MiB 及人数静态产物预算（A6 为 4 MiB、A7 为 12 MiB、A9 为 64 MiB）。这些静态预算不是 RSS 或耗时测量。

不允许通过增加线程、并行 worker、云主机、GPU、重新开始同一配置或追加 seed 来绕过任一上限。若要进行跨 seed 对比，所有 seed 必须预先列入同一 manifest，并从上述总预算中分配；只有一个 seed 时，只能报告单 seed 结果，不能宣称稳定性。

### 3.3 N=9 的明确边界

`N=9` 只允许构造信息集、规则路径和极短 sampled boundary pass，用于记录实际单轮耗时、RSS、访问覆盖、重要性权重摘要和停止原因。不得执行长期 A9 训练、导出长期策略或默认全 chance 质量测量。

候选 A 在 `N=9` 有 362,880 个 ordered deal、2,305 个终局历史；朴素固定策略全 chance 评估上界为 836,438,400 叶。因此，一次能完成构造或短采样，不可解释为 A9 长期训练可行、质量通过或可用于生产。

## 4. 质量口径与解释边界

### 4.1 应记录的诊断

| 项目 | 定义 | 可说明的事实 | 不可说明的事实 |
|---|---|---|---|
| 规则守恒 | 所有检查的终局满足整数投入、派彩和 `sum(utilities)=0`。 | 受限规则未发现自相矛盾。 | 策略质量。 |
| coverage | 在平均策略累计区间内，至少一次出现在 traverser visit 的不同信息集数 / 该人数完整信息集数；另记录 `strategy_sum` 全零信息集数。 | 哪些信息集获得过采样访问，均匀回退是否广泛存在。 | 有效样本量、收敛或均衡质量。 |
| 权重摘要 | 每位 traverser 的 visit 数、最大/分位 `1/q_opponents`、非有限值次数。 | 抽样路径与高方差风险。 | 无偏性或策略优劣。 |
| 固定 profile value | 对**导出后回读的量化策略**，在预先声明的 chance/策略树口径下计算各相对座位期望净效用。A6/A7 仅在时间 gate 内做全 chance；A9 不做。 | 指定抽象、指定策略、指定测量器的收益基线。 | 真实 EV、均衡或 GTO。 |
| 阈值 probe | 每位座位仅用预注册的合法阈值策略，对冻结其余玩家后的收益增量取最大值。 | 是否发现该有限 probe 集的可见漏洞。 | best response、NashConv 或 exploitability。 |
| 跨 seed 稳定性 | 在固定审计信息集集合上比较不同预注册 seed 产物的策略 L1 距离，并记录 profile/probe 差异。 | 对采样轨迹的经验敏感性。 | 正确性、收敛或均衡。 |

coverage 必须由训练期间的 visit 事件累计，而不能从导出 JSON 是否完整、`strategy_sum` 绝对大小或平均策略是否归一化推导。当前 `MCCFRResult` 和策略 JSON 不保留该总计；未获新授权前不实现采集或写入。

### 4.2 固定 probe 规则

未来的 A6/A7 manifest 可使用既有的两组阈值，但必须在训练前冻结：

```text
(ceil(N / 2), ceil(N / 2))
(ceil(3N / 4), ceil(N / 2))
```

第一项是无下注阶段的开池 rank 阈值，第二项是面对开池时的 call rank 阈值。对 A6 分别为 `(3, 3)`、`(5, 3)`；对 A7 分别为 `(4, 4)`、`(6, 4)`。策略只读取自身 rank 和公开阶段，因而不读取对手私牌。

probe 的 manifest 必须包含完整策略定义、版本/hash、评估器版本、评估策略 artifact 的 SHA-256 和阈值。`probe_gain=0` 或未发现增益，只表示这两个预先限定策略没有发现增益；不得称为不存在其他信息集合法偏离，更不得称为 NashConv、exploitability 或近似 GTO。

### 4.3 严禁作出的结论

无论后续 coverage、probe 或 profile 的数值如何，候选 A 都不得被表述为：多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV、真实范围/公共牌/边池/短码结果、模拟对手成品策略或生产可用策略。

尤其不能将常和性质、regret 数值、策略归一化、自对局收益、单 seed 可重放、短路径测试或所有信息集已写入 JSON，改写为收敛或充分训练证据。

## 5. 现有策略 artifact 的 schema 缺口

### 5.1 已确认缺口

当前策略 JSON 的 `quality.utilities` 只能接受整数且必须求和为零；终局效用确为整数，但完整 chance 与混合策略 profile 的期望效用通常为分数。当前导出器也固定写入 `not-measured` 哨兵，因此不能诚实承载真实的 profile 结果。

`resources.elapsed_seconds`、`peak_rss_bytes` 若直接写入确定性策略 JSON，会使相同训练配置在不同机器或不同运行时无法保持字节相同。当前写入的零仅表示未采集，不能被解释为实测资源值。

`training` 只有声明的 `iterations`；内存 `MCCFRResult` 虽有 `completed_iterations`，但 JSON 没有相应字段。即使未来增加字段，loader 也只能检验声明的内在一致性，不能单独证明策略确实由未篡改训练过程生成。

### 5.2 建议的后续方案（未实现）

默认建议保持现有 v1 策略 artifact 为可复现的纯策略文件，不把运行测量混入其中；如需要真实实验记录，新增独立、版本化的测量记录，而不是修改 v1 的固定字段。

| 需求 | 建议表示 | 原因 |
|---|---|---|
| 分数期望效用 | 测量记录中每位效用使用显式有理数 `numerator`/`denominator`，并声明统一缩放/归一规则。 | 避免浮点舍入和“整数终局效用”等同“整数期望效用”的错误。 |
| 耗时与 RSS | 测量记录保存采集工具/平台、开始结束时间、累计秒数、RSS 口径、预警/停止原因。 | 让策略文件的字节确定性与机器相关测量解耦。 |
| 策略关联 | 测量记录保存策略 artifact 的 SHA-256、实际字节数和完整训练 manifest hash。 | 质量结论可明确指向被测量的量化后策略。 |
| 完成声明 | 后续 schema 主版本升级时，可添加 `completed_iterations` 并要求等于 `iterations`；测量记录另保存运行日志 hash。 | 允许 loader 检查内部一致性，但不伪造来源证明。 |
| coverage、权重和稳定性 | 测量记录保存定义、计数、seed 集合、审计信息集集合/hash 和 evaluator 版本。 | 避免把有限采样诊断伪装成策略固有事实。 |

若未来选择把任何真实测量写入策略 artifact，必须新建 schema 主版本并同时修改严格 loader、导出器和测试；不能在 v1 添加未知字段或复用 `not-measured` 字段表达不同语义。无论采用策略 artifact v2 或独立测量记录，实际训练来源仍需要冻结 manifest、干净代码身份、受控运行日志和可重放复核共同支撑，不能只依赖 JSON 自述。

## 6. 下次执行前的最小授权清单

进入范围 3 的实际 A6/A7 训练前，用户必须一次性明确：

1. A6 与 A7 各自的精确 iteration 数或训练墙钟上限，以及 `average_strategy_start_iteration`；
2. 每个配置的 `master_seed` 或固定 seed 集合，以及是否允许跨 seed 对比；
3. CPU、并发、RSS、总墙钟、单/总产物大小和每一项停止条件；
4. 是否执行 profile/probe，具体 evaluator、全 chance 或 sampled 口径、sample seed/count、probe/stability/coverage 阈值和失败后的处理；
5. 是否保留策略、测量记录、日志和检查点，以及精确路径、数量与清理策略；
6. 已实现的 estimator 对照、受控运行、量化 profile/probe、独立测量记录是否按当前接口使用，还是需要新的范围调整；
7. 是否维持策略 artifact v1 不变并使用独立测量记录；若要修改策略 artifact schema，仍需单独授权。

在上述实际实验授权缺失时，不得开始有预算训练、实际质量实验、长期策略导出、资源基准、保留工件、commit 或 push。

## 7. 本轮获授权的训练前实现与验证

本轮在独立 `tools/trainer/` 中新增以下离线能力，未触碰 `kuhn_cfr`、后端、前端、锁文件、数据库或生产运行时：

| 能力 | 实现边界 |
|---|---|
| N6 estimator 对照 | `estimator_oracle.py` 独立枚举 full chance 和对手动作分布，且不导入 MCCFR 私有遍历；测试用固定非均匀策略、根和回应信息集、固定 seed 样本均值比对 regret 与 average-strategy delta。 |
| MCCFR 更新审计 | `IterationTrace` 增加固定排序的稀疏 `IterationUpdate` 快照；只有在 iteration 已收集全部 pass 后才建立，训练核心仍按原同步批量提交。 |
| N7 与 N9 受控路径 | `control.py` 的合作式运行器在 iteration 边界调用外部时钟/RSS 读取器，汇总 coverage、权重分位数、资源阈值和停止原因；N7 短路径回归实际执行一轮，N9 在采样前以 `nine-player-boundary` 停止且没有可导出结果。它不启动或终止外部进程。 |
| A6/A7 量化评估 | `evaluation.py` 仅接受单次安全读取的量化策略单位，完整枚举 A6/A7 chance/profile；阈值 probe 只读取自身 rank 和公开阶段；N9 完整 chance 显式失败，检查器只能在 deal 边界停止。 |
| 独立测量记录 | `measurement.py` 以严格、规范、原子 JSON 表示策略 SHA-256/字节数、manifest 引用、精确既约有理效用、profile/probe 状态、coverage/权重、稳定性和资源阈值。策略 artifact v1 未写入真实资源或质量数据。 |

策略读取扩展为在同一次安全读取中返回量化动作单位及 SHA-256/字节身份，供评估器和测量记录关联；v1 JSON 的字段、未测量哨兵和 lookup 语义未改变。

仅运行了短路径单元测试与完整离线测试套件，没有启动有预算训练或保留实验工件。实际结果：

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
128 passed in 42.02s
```

## 8. 本轮未做事项与结论

没有执行 A6/A7 的有预算训练、实际 profile/probe 实验、跨 seed 稳定性实验、RSS 基准、长期策略导出、检查点或真实实验 manifest；没有在工作区保留策略 JSON、profile、probe、日志或测量文件。因此，除短路径测试外没有新的 A6/A7 CPU、RSS、耗时、coverage、稳定性、profile、probe 或策略质量数字。

本轮结论更新为：候选 A 现在具备训练前 estimator 对照、受控停止回执、量化后 A6/A7 profile/probe evaluator 及独立测量记录的离线实现和测试覆盖；实际训练前仍需要用户冻结具体实验 manifest，并由外层进程监督执行资源限制。该实现与测试不构成多人 Hold'em、均衡、NashConv、exploitability、GTO、真实 EV 或生产可用性结论。

## 9. 提交后实际实验就绪复核

在提交 `19b7426209331e764467d1303edd5320c38ae993` 后，进行了只读实验就绪复核；未运行训练、profile/probe、资源基准或长期工件导出。结论是：**当前不可直接进入实际 A6/A7 受预算实验。** 新增训练前能力已通过测试，但还缺少将冻结 manifest、外部硬监督、训练/评估/导出和测量记录机械绑定为不可绕过链路的实现。

### 已满足

1. 合作式运行器要求显式阶段、墙钟、RSS 和产物限制，在 iteration 边界记录 coverage、权重、停止原因和资源阈值；它明确不启动或管理外部进程。
2. 策略读取在一次安全读取中保留量化单位及实际文件 SHA-256/字节数；A6/A7 evaluator 从这些单位而非内存浮点概率计算。
3. N6 estimator oracle 独立于 MCCFR 私有遍历，采用 full chance 与对手分布枚举；短路径测试覆盖根和回应信息集的 regret/average-strategy 样本均值对照。
4. 受控训练入口对 N9 在采样前停止，完整 chance evaluator 只接受 N6/N7，measurement schema 不能把 N9 写成完成的 full-chance profile。
5. 策略 artifact v1 保持确定性纯策略文件；独立测量记录可承载精确有理效用、资源、诊断与身份引用。

### 进入实际实验前的代码级阻塞项

1. **N9 仍可绕过受控入口。** `MCCFRConfig`、核心 `train()` 和 `export_strategy()` 仍直接接受 N9；因此调用公开基础 API 可进行长期 N9 训练或导出，与只允许 N9 边界路径的约束不一致。实际实验入口必须限制或隔离这些直接路径。
2. **当前资源控制不是端到端硬限制。** 合作式检查在训练器构造后、iteration 边界发生，不能中断单次 iteration；最终结果复制、策略导出、profile/probe、测量写入和总保留产物账本都不在同一个受控阶段链内。实际执行需要从进程启动前计时、采集目标进程树 RSS、覆盖全部阶段并能实施硬杀的外层监督器。
3. **measurement 关联仍由调用方自述。** profile/probe 结果不自带策略 SHA-256、评估器版本或 probe manifest identity；measurement record 也未机械校验其与真实 artifact/evaluator 输出匹配。需要受控 record builder 从已验证 artifact、冻结 manifest、实际评估结果和受控运行回执自动生成引用。
4. **尚无严格实验 manifest。** 当前只有文档约定和 manifest hash 引用；没有 schema、安全读取、规范 hash 或从 manifest 唯一派生 `MCCFRConfig`、`RunLimits`、probe、路径和阶段控制的入口。`average_strategy_start_iteration` 仍存在代码默认值，不能作为实际实验中的隐式补齐。
5. **estimator gate 覆盖不足。** 当前核验只覆盖两个 N6 信息集、固定 128 个连续 seed 和 average 累计开启路径；还应覆盖不同 actor/公开历史、零概率动作、average 累计关闭路径，并将固定 seed、误差口径和比较结果写入 preflight 记录。

因此，下一项建议工作是：在不启动实际训练的前提下，实现严格 experiment/probe manifest、受控实验编排与 record builder，并在边界层禁止直接 N9 长训/导出。完成并复核后，才由用户冻结 A6/A7 实验参数、实际外层进程监督方式及产物保留方案。

## 10. Manifest 强约束链路实现（未运行实际实验）

在上述就绪复核后，本轮实现了训练前的强约束链路，仍未启动有预算 A6/A7/A9 训练、实际 profile/probe、资源基准或长期工件导出：

| 能力 | 实现约束 |
|---|---|
| 冻结 manifest | `manifest.py` 新增严格 experiment/probe manifest schema。读取只接受规范 JSON；manifest 身份由安全读取的原始规范字节计算 SHA-256 与字节数。A6/A7 必须显式提供 `iterations`、`average_strategy_start_iteration` 和 `master_seed`；不再由训练配置默认补值。 |
| 唯一计划派生 | `derive_experiment_plan()` 只从已验证 manifest 生成训练配置、阶段预算、质量计划、probe 引用和工件槽位。训练、RSS、CPU、并发、保留额度、策略与 measurement 槽位均不得在运行调用中自由传入。 |
| 运行时代码身份 | 受控编排会话必须携带完整 Git commit、干净工作区和训练器版本，并在预留工件或构造训练器前与 manifest `code_identity` 比对。身份不一致时直接失败。 |
| 工件账本与编排 | `orchestration.py` 只允许 manifest 预声明的策略/measurement 相对文件名和槽位；阶段顺序固定为训练→导出→量化回读→可选 profile/probe→measurement。已有目标、超槽位或未声明工件均失败。 |
| 机械测量绑定 | `experiment_record.py` 的 builder 只接收已验证计划、训练/N9 回执、量化策略和评估结果。profile/probe 结果携带策略 SHA-256、字节数、固定 evaluator 身份和 probe manifest 身份；记录不接收调用方手填的这些关联。 |
| N9 边界 | `MCCFRConfig`、`run_iteration()`、`train()`、`completed_result()` 和 `export_strategy()` 都拒绝 N9 长期训练或策略导出。唯一允许路径是 `sample_n9_boundary()` / `run_n9_boundary_sample()` 的单 traverser sampled pass：不提交 delta、不累计平均策略、不返回 `MCCFRResult`、不产生策略/profile/probe。 |
| estimator gate 补充 | 除既有根/回应信息集对照外，测试覆盖了 `average_strategy_start_iteration` 尚未到达时，production pass 与 oracle 均不产生 average-strategy delta，且冻结策略可有零概率动作。 |

受控编排仅使用外部 supervisor 会话提供的时钟、RSS 读取和取消信号，并要求其声明 `process-tree` 与 `external-hard-limit` 监督语义；Python 包本身不创建进程、不能实施 OS 级硬杀，也不能证明该外部监督器实际执行了 CPU、进程树 RSS、并发或墙钟限制。因此，实际实验前仍须由用户指定并运行可验证的外部 supervisor，而不能将会话身份字段误读为已完成系统级资源执法。

本轮新增的 manifest、编排、N9 防绕过、受控记录和估计器回归均只走单元测试路径。它们没有生成或保留任何策略、profile、probe、日志、检查点或测量工件；也不构成多人 Hold'em、均衡、NashConv、exploitability、GTO、真实 EV 或生产可用性结论。实际验证结果为：

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer
uv run ruff check .
All checks passed!

uv run pytest -q
141 passed in 54.10s
```

在实际 A6/A7 实验前仍需用户冻结：具体训练 iteration、seed/seed 集、各阶段与总 CPU/RSS/墙钟/产物上限、外部 supervisor 的实际实现与回执口径、profile/probe/stability 阈值及失败处理、预声明工件路径与保留数量。只有该 manifest 被写入规范文件、运行时代码身份与其一致且外部 supervisor 已就绪后，才可获得另一次明确授权进入受预算实验。
