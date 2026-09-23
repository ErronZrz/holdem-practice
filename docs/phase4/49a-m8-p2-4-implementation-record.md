# 49a M8：P2-4 跨 seed 稳定性代码内建生产者（实施回执）

> 日期：2026-09-20。
>
> 本文件是 `docs/49` 的**实施回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/48a` 未被改写；`docs/49` 未被改写（五条裁定按原文执行，实施期**无**细化）。
>
> **编号说明**：`48` / `48a` 已由同一轮的 P2-3 只读诊断占用，故本切片取 `49` / `49a`。
>
> 本文件记录已实际落地的代码与测试。**不产生任何策略、质量或资源证据**；未接入 CFR/查表、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、**未启动任何受监督运行**、未做任何云端操作。

## 1. 实施基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 3]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -2 --oneline
fae65bd docs: freeze p2-4 cross-seed stability producer specs
5e94d8a docs: record p2-3 historical pot results read-only diagnosis

$ git rev-parse HEAD          -> fae65bd（`docs/49` 冻结提交）
$ git rev-parse origin/master -> 133c99cbf541e9bf49d1f5f2e795ca6585e91d8d

$ cd tools/trainer && uv run ruff check .   -> All checks passed!
$ cd tools/trainer && uv run pytest -q      -> 197 passed in 185.29s      （实施起点）
$ cd backend && uv run pytest -q            -> 668 passed, 2 skipped      （实施起点）
```

实施前工作区 **0 行**；未做任何 `reset` / `clean` / `stash` / `checkout`；本轮**不 push**。

## 2. 实际改动（文件级）

| 文件 | 改动 |
|---|---|
| `tools/trainer/src/multiplayer_cfr/measurement.py`（修改，+105 / −1） | 新增两个公共函数 `audit_infoset_keys(player_count)`、`build_stability_payload(*, player_count, strategies, probability_units)` 与一个私有校验助手 `_parse_strategy_units(...)`；导入 `collections.abc.Mapping` 与 `.game` 的 `infosets` / `infoset_by_key`（无循环依赖：`game.py` 不依赖本模块） |
| `tools/trainer/tests/test_multiplayer_measurement.py`（修改，+171） | 新增 10 条测试，见 §3 |

**未改动**：`policy.py`、`experiment_record.py`、`supervised_measurement.py`、`kuhn_cfr/**` 以及 `tools/trainer/**` 中其余任何文件；`backend/**`、`frontend/**`、锁文件、真实数据库均未触及。

`git diff --name-only` 实测只有上表两个文件。

## 3. 新增测试（10 条）

| # | 测试 | 断言要点 |
|---|---|---|
| 1 | `test_audit_infosets_cover_every_infoset_of_supported_player_counts`（参数化 N=6/7/9） | 审计集大小 = `structure_counts(N).infosets`（N=6 → 1 152、N=7 → 3 136、N=9 → 20 736）；无重复；等于该人数全部信息集键 |
| 2 | `test_stability_producer_reports_zero_distance_for_identical_strategies` | 同一策略两个 seed → `max_l1 = 0/1`；`status = "measured"`；两个哈希均为 64 位小写 |
| 3 | `test_stability_producer_measures_exact_distance_on_a_single_infoset` | 单个信息集由 500/500 变为 400/600 → **精确** `max_l1 = 1/5` |
| 4 | `test_stability_producer_is_independent_of_seed_insertion_order` | 交换 seed 插入顺序结果逐字段相同；单信息集 250/750 → `max_l1 = 1/2` |
| 5 | `test_stability_producer_rejects_a_single_seed_and_non_integer_seeds` | 单 seed 拒绝；`bool` 型 seed 拒绝 |
| 6 | `test_stability_producer_requires_the_full_audit_set_and_legal_actions` | 缺审计集项、动作名不符、单位和不等、单位取负 → 全部拒绝 |
| 7 | `test_stability_producer_rejects_a_non_positive_probability_unit` | `probability_units = 0` 拒绝 |
| 8 | `test_produced_stability_payload_is_accepted_by_the_measurement_record` | 把产出嵌入既有独立测量记录后 `create_measurement_record` **通过**（等价于通过既有 `stability` 校验） |

## 4. 实际输出

```text
$ cd tools/trainer && uv run ruff check .
All checks passed!

$ cd tools/trainer && uv run pytest tests/test_multiplayer_measurement.py -q
15 passed in 0.90s

$ cd tools/trainer && uv run pytest -q
207 passed in 191.31s (0:03:11)      （实施起点 197 → +10，只增不减）

$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
668 passed, 2 skipped, 2 warnings in 10.83s      （与实施起点逐项一致）
```

## 5. 实施结果与规格对应

| `docs/49` 裁定 | 落地情况 |
|---|---|
| 一：无 I/O 纯计算生产者 | `build_stability_payload` 不读写文件、不调用训练/评估原语；仅用 `Fraction` / `sha256` / 既有 `_canonical_json_bytes` |
| 二：不动受监督链路 | `experiment_record.py`、`supervised_measurement.py` 未改（`git diff --name-only` 佐证） |
| 三：不动 artifact v1 | `policy.py` 未改；`quality.stability` 仍**只允许** `{status}`；产出走独立测量记录的 `stability` 段 |
| 四：不启动任何运行 | 未启动任何训练/评估/采样；`status="measured"` 仅由**单测内的构造策略**产生，**未**写入任何真实记录 |

实现细节（规格已写死、无偏离）：

- **审计集**：`audit_infoset_keys(N)` = `game.infosets(N)` 的全部键（规范顺序、不抽样）；输入必须**恰好**覆盖该集合。
- **指标**：逐对 seed、逐个审计信息集取 `Σ_a |p_i(a|I) − p_j(a|I)|`，以 `Fraction(单位差之和, probability_units)` 精确计算；`max_l1` 取全局最大值、**不归一化**、以既约 `{numerator, denominator}` 报告。
- **身份哈希**：`seed_set_sha256` 对升序 seed 列表、`audit_infosets_sha256` 对规范顺序信息集键列表取规范 JSON 后的 SHA-256；不同人数因信息集键不同而天然不碰撞。
- **单位**：`probability_units` 由调用方显式给出（**不**内建常量），测试中取 `1000`；与 `policy.PROBABILITY_UNITS`（`1e12`）不构成第二事实源。
- **单 seed 不判定**：参与 seed 少于 2 个即拒绝。
- 按规格**未**引入「有效支持集」「分布相同占比」等额外诊断字段。

## 6. 版本影响与兼容性

| 项 | 结论 |
|---|---|
| 公开 API / Pydantic model | **无变化**（改动全在 `tools/trainer`，后端不 import trainer） |
| 数据模型 / 列 / 迁移 | **无变化** |
| 策略 artifact v1 | **无变化**；`quality.stability` 仍恒为 `{"status": "not-measured"}`；**未触发** `docs/37` §3.1 升版 |
| 独立测量记录 schema | **无变化**；`not-requested` / `not-measured` 分支未动，旧记录照常读取 |
| 既有后端用例 | `668 passed, 2 skipped` 不变 |
| 既有 trainer 用例 | `197 → 207`，**只增不减**，无删改 |
| 生产调用方 | **无**：本生产者当前**没有被任何生产路径调用**（与 P1-1…P1-5 各模块一致）；接入受监督路径需另轮授权 |

## 7. 未做事项与未覆盖面

- **未**接入 `experiment_record.py` / `supervised_measurement.py`；**未**扩展 artifact v1。因此**仍不能**从 v1 artifact 读出稳定性结果（`docs/35` §4.2 验收保持满足）。
- **未**产生任何真实 `measured` 记录：产出只在单测内以构造策略验证；真实跨 seed 稳定性仍须另行授权的受监督运行。
- **未**实现覆盖率、有效支持集、分位数等额外诊断字段；**未**改动质量门槛（`docs/39` 继续不启用）。
- **未**改动 `tools/trainer/**` 中除上述两文件以外的任何文件；**未**触及 `backend/**`、`frontend/**`、锁文件、真实数据库、`docs/20`–`docs/48a`。
- **未**新建 campaign、**未**追加 seed、**未**重试 authorization；**未**推进 P2-2。

## 8. 下一步唯一建议动作（不自行执行）

P2-4 的**最小形态**已闭环为「代码能力」。`docs/35` §4.2 剩余两项都需先解除硬边界，请择一授权：

1. **P2-4 完整形态**：把 `stability` 接入受监督路径（`experiment_record.py` schema 变更），并在需要时讨论 artifact v1 扩展（会触发 `docs/37` §3.1 升版）；若要真实 `measured` 记录，还需**新的受监督运行授权与预算**。
2. **P2-2**：先冻结新的 N=9 campaign 与预算 envelope（设计文档），实际执行另起一轮。
