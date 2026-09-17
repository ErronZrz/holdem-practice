# 27 M8：多人 CFR 候选 A——离线规则与契约实现

> 日期：2026-09-17。
>
> 开始时 Git 基线：`fb3a54de8ab2bff2a89bb19ee125c38bcd6b4b86`（`docs: add multiplayer CFR feasibility plan`）。开始时 `master...origin/master` 且工作区干净。
>
> 本轮授权：用户已确认 `docs/26` 的候选 A，但只授权离线规则、契约和测试实现，**明确不训练**。本轮未 commit 或 push。

## 1. 本轮范围与只读前置核对

本轮只改动独立训练器项目 `tools/trainer/`，并新增本文档；没有修改 `backend/`、前端、真实数据库、API、LLM、`src/kuhn_cfr/` 或其测试。

只读核对确认：

- M7 的 `kuhn_cfr` 仍是固定两人 Kuhn 规则、full-chance CFR、两人零和质量和独立 JSON schema；这些语义没有被泛化或复用为多人结论。
- `docs/26` 第 4、5、9、10 节是本轮候选 A 的规则、结构、资源和安全产物契约来源。
- 训练器运行时依赖仍为空，开发依赖仍只有 `pytest` 和 `ruff`；没有修改 `tools/trainer/uv.lock`。
- `tools/trainer/pyproject.toml` 仅将新包 `src/multiplayer_cfr` 加入 wheel 打包范围。

## 2. 实际新增文件与包边界

新增包 `tools/trainer/src/multiplayer_cfr/`：

| 文件 | 实际职责 |
|---|---|
| `game.py` | 候选 A 的规则、规范公开历史解析、公开投影、信息集、结构计数与整数终局结算。 |
| `chance.py` | 有显式整数 seed 的 ordered-deal 抽样和完整 chance 空间枚举。 |
| `resources.py` | 从 `docs/26` 预算表固化的静态结构预留，不采样 RSS，不执行基准。 |
| `policy.py` | 严格 JSON 读取、跨字段复核和受控抽象 lookup；不写入、不导出策略。 |
| `__init__.py` | 独立门面；不导入 `kuhn_cfr`、后端或生产状态。 |

新增测试：

- `tools/trainer/tests/test_multiplayer_game.py`
- `tools/trainer/tests/test_multiplayer_chance.py`
- `tools/trainer/tests/test_multiplayer_policy.py`

没有新增数值、Web、数据库或后端依赖，没有锁文件变化，没有生成项目内策略文件。

## 3. 候选 A 实际规则与公开历史

实现限定 `N ∈ {6, 7, 9}`，相对座位恒为 `0..N-1`，其中 `0` 仅表示抽象首个行动者。每位玩家 ante 为整数 `1`，首次开池和 call 的固定额外投入为 `1`；没有盲注、公共牌、all-in、边池、再加注、真实筹码深度或真实范围。

- 未下注时按 `0..N-1` 依次只允许 `x` 或 `b`。
- 首次 `b` 后，开池者之后的所有其他座位按循环顺序各回应一次，只允许 `c` 或 `f`；早先 check 的座位绕回后仍须回应。
- 全员 check 后比较未弃牌者的唯一 rank；响应完成后，若只有开池者存活则其直接获胜，否则比较存活者的唯一 rank。
- 完整 deal 是 `0..N-1` 的一个排列，故没有平局。
- 终局保持整数规则：`u_i = w_i - c_i`，实现逐局检查 `sum(w_i) == P` 和 `sum(u_i) == 0`。折叠者的 ante 保留为死钱。

根历史唯一编码为 `-`。其他历史必须由无空白的 `action@relative-seat` token 以 `|` 拼接，例如：

```text
x@0|x@1|b@2|c@3|f@4
```

`derive_public_state()` 是公开状态的唯一入口，直接从该规范历史派生当前行动者、开池者、弃牌/存活集合、公开投入、待回应循环顺序和终局状态。调用方不能独立传入 `folded`、投入或行动顺序，策略读取器也会将其重复声明的 `public_state` 与派生投影逐字段比对。

## 4. 信息集、chance 与信息泄漏边界

信息集键固定为：

```text
m8/m8-a-v1/n={N}/actor={relative-seat}/rank={own-rank}/history={canonical-public-history}
```

构造键和 lookup 的入参只有游戏版本、人数、相对行动者、自己的唯一 rank 与规范公开历史。实现不接受 `Deal`、其他私牌、未发牌、未来公共牌、终局赢家、生产 `GameState`、真实底池层、数据库记录、对手内部状态或隐藏训练随机状态。

`CandidateAChance` 只接受显式整数 seed，并以 Python MT19937 (`python-random-mt19937`) 从 `0..N-1` 均匀抽取无重复的有序排列。`iter_ordered_deals()` 则按确定顺序完整枚举该空间，供规则测试使用。它们不调用训练循环。

实际结构计数如下：

| N | ordered deals | 公开决策历史 | 信息集 | 终局历史 |
|---:|---:|---:|---:|---:|
| 6 | 720 | 192 | 1,152 | 193 |
| 7 | 5,040 | 448 | 3,136 | 449 |
| 9 | 362,880 | 2,304 | 20,736 | 2,305 |

`resources.py` 还以静态契约记录了 `docs/26` 的结构预留：6 人状态/产物为 32 MiB/4 MiB，7 人为 96 MiB/12 MiB，9 人为 512 MiB/64 MiB。这些是设计上限，不是本轮 RSS、耗时或训练基准测量。

## 5. 安全策略读取与 lookup 契约

本轮实现了**读取和 lookup**，没有实现策略训练器、策略导出器或任何长期策略产物。

读取器只接受大小不超过 64 MiB 的非链接普通 UTF-8 JSON 文件，拒绝重复键、`NaN`、`Infinity`、未知或缺失字段、错误 schema/type/game/version/N、非法信息集键、错误公开投影、非法动作、负概率单位和错误概率单位和。顶层 schema 固定包含：

```text
schema_version
artifact_type = "multiplayer-cfr-average-strategy"
game
training
probability_units
infosets
quality
resources
```

`game` 固定为候选 A 版本和相对位置语义；`infosets` 必须完整覆盖对应人数的全部可达信息集，并精确重复从规范历史派生的行动者、rank、公开投影与合法动作。`training`、`quality`、`resources` 仅定义未来产物的严格字段形状；它们不代表本轮执行过训练、质量评估或资源采集。

`lookup()` 仅接受受控的抽象投影，遇到版本不匹配、跨人数、非法公开历史或缺失信息集时显式失败，不提供生产 fallback。测试中的 JSON 仅写入 pytest 的临时目录，测试结束后不保留。

## 6. 测试矩阵与实际结果

新增 47 个 pytest case，覆盖：

1. 6/7/9 人的合法顺序、开池后的环形回应、全 check、全 fold、死钱、非法历史/动作和所有终局的整数守恒；
2. 6/7/9 人的固定结构计数，以及每个可达信息集的合法动作；
3. 保持行动者自身 rank 和公开历史时，替换其他私牌并改变未来摊牌赢家不会改变键；改变自身 rank、行动者或公开历史会改变键；
4. `N!` ordered deals 的完整枚举、每次发牌无重复 rank、固定 seed 的可复现抽样；
5. 历史到公开投影的一致性，以及静态资源结构预留；
6. JSON 对重复键、非有限数、未知字段、错 game/version/N、非法键/动作、错误公开投影、负概率和错误概率单位和的拒绝；
7. 受控 lookup 对合法抽象输入的成功路径，以及版本、人数和抽象外历史的显式失败。

实际执行：

```text
cd /Users/bryanylliu/my4/holdem-practice/tools/trainer && uv run ruff check .
All checks passed!

cd /Users/bryanylliu/my4/holdem-practice/tools/trainer && uv run pytest -q
89 passed in 3.93s
```

其中 47 个候选 A case 由 `pytest --collect-only` 确认。上述结果是离线规则与契约回归，不是训练、均衡或生产质量证据。

## 7. 明确未做事项与未生成产物

本轮没有执行或声称执行：

- MCCFR、external-sampling traverser pass、regret 更新、平均策略累积或任何多人训练迭代；
- 资源基准、RSS 采集、收敛评估、固定 profile value、阈值 probe、best response、NashConv 或 exploitability；
- 长期策略 JSON、检查点、训练日志、质量报告或资源报告；
- 9 人长期训练、全 chance 9 人评估，或对真实 Hold'em、边池、平局、短码、真实下注尺度、真实范围和生产 EV 的验证；
- 对后端、策略、分析、API、存储、前端或生产 runtime 的接入。

候选 A 通过的测试仅证明其受限单牌抽象的规则和安全契约自洽，不能称为多人 Hold'em GTO、均衡、NashConv、生产策略质量或真实 CALL EV。

## 8. 确认记录与后续授权边界

用户已确认候选 A 的离线规则/契约实现，并要求本轮不训练；本轮遵守了不自动扩预算、不转云/GPU、不保留实验产物以及不 commit/push 的边界。

后续若要实现同步 external-sampling MCCFR、训练、任何策略导出、质量测量、资源测量或生产接入，均需要新的明确授权。新的授权还必须分别指定训练配置、累计资源预算、保留产物、质量口径和停止条件；不得将本文规则测试直接升级为训练完成或生产可用的结论。
