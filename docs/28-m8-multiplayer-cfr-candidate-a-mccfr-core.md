# 28 M8：多人 CFR 候选 A——同步 MCCFR 核心与不变量

> 日期：2026-09-17。
>
> 开始时 Git 基线：`36ed1db2b5b9c60818a21fd358578372212e1609`（`feat: add multiplayer candidate A contracts`）。开始时 `master...origin/master` 且工作区干净。
>
> 初始授权：实现同步 external-sampling MCCFR 代码和不变量测试；后续明确追加授权：实现候选 A 的规范策略 JSON 导出器。两项范围均**不执行有预算的 A6/A7 训练、不做质量测量**；本轮不保留策略产物，未 commit 或 push。

## 1. 授权边界与实际变更

本轮只改动独立离线项目 `tools/trainer/` 及本文档。没有修改 `tools/trainer/src/kuhn_cfr/`、其测试、后端、前端、API、LLM、真实 SQLite、锁文件、真实牌局结算或现有 equity/static share/池层投影。

实际新增或修改的文件：

| 文件 | 实际职责 |
|---|---|
| `tools/trainer/src/multiplayer_cfr/randomness.py` | 从显式 `master_seed` 派生彼此隔离、可重放的 chance 与对手动作随机流。 |
| `tools/trainer/src/multiplayer_cfr/mccfr.py` | 候选 A 的同步 external-sampling MCCFR 内存训练态、遍历、批量更新和最小审计摘要。 |
| `tools/trainer/src/multiplayer_cfr/policy.py` | 完整策略验证、确定性概率量化、规范 JSON 导出、严格回读与受控 lookup。 |
| `tools/trainer/src/multiplayer_cfr/__init__.py` | 导出离线 MCCFR 与策略导出的受控公共接口。 |
| `tools/trainer/tests/test_multiplayer_mccfr.py` | 算法结构、同步性、随机流、抽样、平均策略和配置边界的不变量测试。 |
| `tools/trainer/tests/test_multiplayer_policy.py` | 严格读取、概率量化、规范导出、原子失败保护和回读测试。 |
| `docs/28-m8-multiplayer-cfr-candidate-a-mccfr-core.md` | 本轮授权、实现、测试和未做事项记录。 |

未增加运行时依赖；导出测试只写入 pytest 临时目录，并在测试结束后清理。工作区未保留检查点、策略 JSON、训练日志、profile、质量报告或其他长期产物。

## 2. 算法版本与固定语义

实现对应既有候选 A 策略契约中的：

```text
algorithm: synchronous-external-sampling-mccfr-v1
update_mode: synchronous-batched
iteration_definition: one-pass-per-relative-seat
traverser_schedule: ascending-relative-seat
chance_model: uniform-ordered-deals
```

`MCCFRConfig` 不提供隐式人数、迭代数或 seed。调用者必须显式给出 `player_count ∈ {6, 7, 9}`、正整数 `iterations`、整数 `master_seed` 和合法的 `average_strategy_start_iteration`。

每个 iteration 的语义固定如下：

1. 根据所有当前 regret sum 计算 regret-matching 行为策略，并冻结为一份不可回写的内部快照；正 regret 总和为零时严格均匀分布。
2. 按相对座位 `0..N-1` 精确执行 `N` 个 traverser pass。
3. 每个 pass 从独立 chance 流只抽取一份 ordered deal。当前 traverser 节点枚举全部合法动作；其他行动者节点只按冻结策略抽取一个正概率动作。
4. 终局只使用 `terminal_outcome(...).utilities[traverser]`，不把任何其他座位收益取负后替代当前座位收益。
5. traverser 节点收集动作值与节点期望值的差作为 regret delta。对手和 chance 都按其目标分布抽样，因此 regret 的 external-sampling 估计不附加额外的逆概率项。
6. 平均策略只在 traverser 自身节点累积，使用自身到达概率与已采样对手公开路径概率的逆概率权重。该权重仅用于平均策略采样修正。
7. 所有 pass 仅写入本轮临时 delta；全部 `N` 个 pass 完成后，才按预分配信息集和合法动作的固定顺序合并 regret 与平均策略累计量。

训练器不重新实现公开历史、行动顺序、合法动作、终局结算或信息集键。它只调用现有 `game.py` 的规则接口，并用 `information_set_key()` 以行动者自己的 rank 和规范公开历史定位节点。完整 `Deal` 只在遍历期间用于终局结算和当前行动者的 own rank，不进入节点键、平均策略键或结果对象。

## 3. seed、PRNG 与可重放边界

随机语义固定为：

- `CandidateAChance` 和对手动作抽样都使用 Python `random.Random` 的 MT19937，PRNG 标识仍为 `python-random-mt19937`。
- `randomness.py` 的 `derive_seed()` 使用 `sha256-64be-v1`：对版本标识、`master_seed`、人数、iteration、traverser 和 purpose 做 ASCII 编码，再取 SHA-256 前 8 字节的大端无符号整数。
- purpose 仅允许 `chance` 与 `opponent-action`，从而避免递归分支数量改变时使发牌随机流和对手动作随机流互相扰动。
- 相同 Python 版本、配置和 `master_seed` 的有限测试调用会得到相同策略和审计摘要；改变 seed 不会改变候选 A 的规则、公开历史、动作集或信息集数量。

`IterationTrace` 只保留 traverser、两个派生 seed、公开历史上的已采样对手动作，以及 traverser 信息集访问时的 own reach、对手抽样概率和平均策略重要性权重。它不保存完整发牌、其他私牌、赢家、未来历史或生产状态，且不作为长期训练日志或产物写入文件。

## 4. 已验证不变量

新增测试覆盖以下事实：

1. 无正 regret 时的均匀 regret matching；正 regret 和平均策略均非负且归一。
2. 6/7/9 人训练器在开始时预分配的节点集，精确等于候选 A 规则信息集及其合法动作。
3. 一个 iteration 恰好有 `N` 个 pass，traverser 固定升序，所有 pass 复用同一个冻结策略快照，且所有节点在最后批量提交前保持未写入状态。
4. 每个 pass 恰好抽取一份 chance deal；traverser 根节点的两个合法动作均继续递归，对手节点才执行单动作抽样。
5. 访问记录中的对手抽样概率为正，平均策略重要性权重等于其倒数；零概率动作不能被抽样。
6. 平均策略严格从配置指定的 iteration 开始累计；结果策略完整覆盖、非负、归一，且相同配置和 seed 的短路径测试可重放。
7. iteration 必须从一顺序执行，不能越过配置上限；非法人数、次数、seed、平均策略起始轮次和 seed 派生参数会显式失败。
8. chance 与对手动作的 seed 派生相同输入稳定、不同 purpose 隔离。

本轮没有把这些不变量测试表述为收敛、均衡、NashConv、exploitability、近似 GTO、真实 Hold'em EV 或生产策略质量。

## 5. 是否运行训练、实际资源与保留产物

**没有执行任何有预算训练、收敛实验、A6/A7 质量测量、A9 长期训练或完整 chance 评估。**

为验证算法路径，pytest 仅调用了 1 或 2 个 iteration 的小型单元测试；这不是授权训练实验，不产生或保留策略工件。实际执行结果：

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer && uv run ruff check .
All checks passed!

cd /Users/bryanylliu/my4/holdem-practice/tools/trainer && uv run pytest -q
117 passed in 4.86s
```

资源记录：

| 项目 | 本轮实际情况 |
|---|---|
| CPU 训练预算 | 未启动训练实验；没有申请或扩展预算。 |
| 峰值 RSS | 未采集。 |
| 训练耗时 | 未测量；`4.40s` 仅为完整离线测试套件墙钟时间。 |
| 保留实验产物 | `0`；无策略 JSON、检查点、日志、profile 或质量文件。 |
| 云/GPU | 未使用。 |

静态资源预留仍仅是上一轮 `resources.py` 的结构契约，并非本轮实测：N=6 为 32 MiB 状态/4 MiB 单产物，N=7 为 96 MiB/12 MiB，N=9 为 512 MiB/64 MiB。

## 6. 质量口径、停止条件与未做事项

本轮没有质量 profile、固定 profile value、probe、best response、NashConv、exploitability、收敛阈值或停止条件。没有任何质量数字可用于认可策略。

当前实现的停止边界是功能性的而非实验性的：配置必须有限、iteration 不能超出显式配置、调用者必须显式提供 seed；本轮没有实现资源守卫、RSS 采集、计时上限或自动停止。后续若授权训练，必须在启动前补齐并记录具体 CPU、内存、工件大小、迭代/时间、质量口径和停止条件，且不得自动扩预算、转云或转 GPU。

仍明确未做：

- 检查点、训练日志、长期策略产物，以及非哨兵的长期工件质量/资源元数据；
- 有预算的 A6/A7 训练和受控产物导出；
- 资源基准、RSS 采集、收敛评估、profile value、probe、best response、NashConv 或 exploitability；
- 9 人长期训练或全 chance 9 人评估；
- 真实 Hold'em 公共牌、范围、边池、平局、短码、下注尺度、真实 EV 以及任何生产接入。

因此，本轮只证明候选 A 的训练核心可在小型测试路径上遵守已声明的同步和信息集契约；不证明策略已经训练完成、能够收敛、接近均衡或可用于生产。

## 7. 范围 1：规范策略 JSON 导出器

导出器只接受已完成的 `MCCFRResult`：`completed_iterations` 必须等于显式配置的 `iterations`，结果信息集计数和策略键集必须精确匹配候选 A 的规则树。它不会调用训练、质量评估、profile、probe、RSS 采集或资源基准。

导出前，`validate_strategy()` 会验证完整信息集覆盖、规则动作集合、有限非负概率和每个信息集概率和。每个动作概率使用 `1_000_000_000_000` 单位进行最大余数法量化：先按规则动作顺序取值，再按小数部分和动作文本进行稳定并列裁决，最终保证每个信息集的整数单位和严格正确。

JSON 按信息集键字典序、对象键排序、紧凑 UTF-8 和末尾换行序列化。`resources.artifact_bytes` 使用受限固定点计算，等于最终文件真实字节数；导出同时遵守全局 64 MiB 上限和 6/7/9 人各自的静态产物预算。写入要求现有非链接父目录，拒绝链接或目录目标，在同目录创建私有临时文件、同步写入后原子替换，并回读 loader 验证最终工件。

导出器从代码常量生成游戏、算法、PRNG 和 seed 派生字段：`python-random-mt19937` 与 `sha256-64be-v1`。调用方只能提供受控 `trainer_version`，不能覆写游戏、算法、人数、seed、信息集、资源计数或概率单位。

当前 schema 仍缺少真实质量与资源测量的完整口径，因此范围 1 只能写入明确的未测量哨兵：质量为 `not-measured`、sample count 为 `0`、常和整数效用为零向量；耗时和 RSS 均为 `0`，仅表示未采集，不能解释为真实测量值。该哨兵不构成收敛、均衡、NashConv、exploitability、真实 EV 或生产可用性证据。

新增测试仅构造完整的内存结果并写入 pytest 临时目录；覆盖导出—回读、字节确定性、稳定量化并列、严格随机性元数据、实际字节数、静态大小预算、临时文件清理，以及未完成或非法结果不覆盖既有目标。没有在工作区保留任何策略 JSON，也没有启动有预算训练。
