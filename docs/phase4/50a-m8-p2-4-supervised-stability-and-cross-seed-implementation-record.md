# 50a M8：P2-4 完整形态（实施回执）

> 日期：2026-09-20。
>
> 本文件是 `docs/50` 的**实施回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/49a` 未被改写；`docs/50` 未被改写（五条裁定按原文执行，实施期**无**细化）。
>
> 本文件记录已实际落地的代码与测试。**不产生任何策略、质量或资源证据**；未接入 CFR/查表、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、**未启动任何受监督运行**。

## 1. 实施基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 5]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -2 --oneline
0f3924f docs: freeze p2-4 supervised stability and cross-seed record specs
b32cd4b feat: add code-built cross-seed stability producer for measurement records

$ git rev-parse HEAD          -> 0f3924f（`docs/50` 冻结提交）
$ git rev-parse origin/master -> 133c99cbf541e9bf49d1f5f2e795ca6585e91d8d

$ cd tools/trainer && uv run ruff check .   -> All checks passed!
$ cd tools/trainer && uv run pytest -q      -> 207 passed      （实施起点）
$ cd backend && uv run pytest -q            -> 668 passed, 2 skipped
```

实施前工作区 **0 行**；未做任何 `reset` / `clean` / `stash` / `checkout`；本轮**不 push**。

## 2. 实际改动（文件级）

| 文件 | 改动 |
|---|---|
| `tools/trainer/src/multiplayer_cfr/measurement.py`（修改，+32 / −6） | 新增公开常量 `STABILITY_FIELDS`、公开函数 `audit_infosets_sha256(player_count)`、`seed_set_sha256(seeds)`、`validate_stability(value)`；`build_stability_payload` 改用后两者；`_validate_stability` 改用 `set(STABILITY_FIELDS)`。**稳定性 schema 自此只有一个校验入口与一份身份哈希公式** |
| `tools/trainer/src/multiplayer_cfr/experiment_record.py`（修改，+50 / −18） | `EXPERIMENT_RECORD_SCHEMA_VERSION` `1` → `2`；新增 `LEGACY_EXPERIMENT_RECORD_SCHEMA_VERSION = 1` 与两套顶层字段集合；构造器新增 `stability` 段（`not-requested`）；`_validate_payload` 改为**按版本分派**（v1 无 `stability`、v2 必含且经 `validate_stability` 校验） |
| `tools/trainer/src/multiplayer_cfr/cross_seed_stability.py`（**新增**，251 行） | 集合级记录类型 `multiplayer-cfr-cross-seed-stability` v1：`StabilitySource` / `SealedStrategySample` / `CrossSeedStabilityRecord`；`read_sealed_strategy`（只读）、`build_cross_seed_stability_record`、`parse_/load_/write_` 规范 JSON 读写；并**交叉核对** `seed_set_sha256` 与 `audit_infosets_sha256` |
| `tools/trainer/tests/test_multiplayer_cross_seed_stability.py`（**新增**，207 行） | 10 条测试，见 §3 |
| `tools/trainer/tests/test_multiplayer_experiment_record.py`（修改，+45） | 既有夹具补齐 `stability` 段；新增 4 条测试，见 §3。**未删除或弱化任何既有断言** |

**未改动**：`policy.py`（artifact v1 与其 `SCHEMA_VERSION` / `PROBABILITY_UNITS` **原样**）、`control.py`、`mccfr.py`、`evaluation.py`、`campaign.py`、`campaign_executor.py`、`supervised_measurement.py`、`safeio.py`、`kuhn_cfr/**`；`backend/**`、`frontend/**`、锁文件、真实数据库均未触及。

## 3. 新增测试（14 条）

| 文件 | 测试 | 断言要点 |
|---|---|---|
| `test_multiplayer_cross_seed_stability.py` | `test_cross_seed_record_identity_follows_the_audit_set`（参数化 N=6/7/9） | 记录类型与版本；`status = "measured"`；相同策略 `max_l1 = 0/1`；两个身份哈希等于 `seed_set_sha256` / `audit_infosets_sha256`；`sources` 按 seed 升序 |
| 同上 | `test_cross_seed_record_aggregates_sealed_strategies` | **端到端**：导出两份不同 seed 的策略产物 → `read_sealed_strategy` → 聚合，`max_l1` **精确** `1/5`；来源 sha256 与读取身份一致 |
| 同上 | `test_cross_seed_record_round_trips_through_canonical_json` | 规范 JSON 写入/回读身份一致 |
| 同上 | `test_cross_seed_record_rejects_fewer_than_two_samples_or_duplicate_seeds` | 单样本拒绝；重复 seed 拒绝 |
| 同上 | `test_cross_seed_record_rejects_an_incomplete_audit_coverage` | 审计集缺项拒绝 |
| 同上 | `test_cross_seed_record_rejects_a_tampered_seed_identity` | 篡改 `seed_set_sha256` / `audit_infosets_sha256` 均拒绝（交叉核对生效） |
| 同上 | `test_cross_seed_record_rejects_a_non_measured_stability_section` | 非 `measured` 拒绝 |
| 同上 | `test_cross_seed_record_rejects_a_mismatched_game_version` | 游戏版本不符拒绝 |
| `test_multiplayer_experiment_record.py` | `test_current_version_declares_unrequested_stability` | 当前版本 = 2 且 `stability` 为 `not-requested` |
| 同上 | `test_legacy_payload_without_stability_section_is_still_accepted` | **v1 载荷（无 `stability`）仍可解析** |
| 同上 | `test_record_rejects_an_incompatible_stability_section` | v2 下非法 `stability` 拒绝 |
| 同上 | `test_record_rejects_a_stability_section_on_the_legacy_version` | v1 下**不得**携带 `stability` |

## 4. 实际输出

```text
$ cd tools/trainer && uv run ruff check .
All checks passed!

$ cd tools/trainer && uv run pytest tests/test_multiplayer_cross_seed_stability.py tests/test_multiplayer_experiment_record.py tests/test_multiplayer_measurement.py -q
34 passed in 3.45s

$ cd tools/trainer && uv run pytest -q
221 passed in 187.74s (0:03:07)      （实施起点 207 → +14，只增不减）

$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
668 passed, 2 skipped, 2 warnings in 11.50s      （与实施起点逐项一致）
```

**实测数字**：跨 seed 记录对 N=6/7/9 的参数化测试全部通过；端到端用例中，两份真实导出的策略（量化单位 `1e12`）在单个偏离信息集上给出**精确** `max_l1 = 1/5`。

## 5. 规格对应

| `docs/50` 裁定 | 落地情况 |
|---|---|
| 一：形态 C | 受监督记录新增 `stability` 段（构造器产出 v2）；新增 `cross_seed_stability.py` 承载集合级 `measured` |
| 二：不扩展 artifact v1 | `policy.py` **未改**（`git diff --name-only` 佐证）；`quality.stability` 仍只允许 `{status}`；`SCHEMA_VERSION` 仍为 `1` |
| 三：不启动受监督运行 | 未执行任何训练/评估/采样；`measured` 只由单测构造与真实导出策略（`iterations=1` 的合成结果）产生，**未**写入任何真实记录 |
| 四：v1/v2 双版本读取 | `_validate_payload` 按 `schema_version` 分派；`test_legacy_payload_without_stability_section_is_still_accepted` 直接验证旧载荷可读 |
| 五：新记录类型 | `multiplayer-cfr-cross-seed-stability` v1；含来源身份与两项交叉核对 |

## 6. 版本影响与兼容性

| 项 | 结论 |
|---|---|
| 受监督 experiment 记录 | `schema_version` **1 → 2**；**旧 v1 记录继续可读**（`holdem-campaigns` 下已封存的 `child_execution.payload` 不受影响）；**唯一被改动的既有测试夹具**已随 schema 补齐新字段，未删除或弱化断言 |
| 独立测量记录（`measurement.py`） | **schema 无变化**；仅将既有私有校验提升为公开入口、并把两处哈希公式提取为公开函数；`not-requested` / `not-measured` 行为不变 |
| 策略 artifact v1 | **无变化**（裁定二）；后端 `strategy/artifact.py` 读取端与 11 份已封存 `strategy.json` 不受影响 |
| 后端复盘参考/评估身份 | **无变化**；`docs/37` §3.1 与本轮无关（见 `docs/50` §1.3 的更正） |
| 公开 API / 数据模型 / 列 / 迁移 | **无变化** |
| 既有用例 | trainer `207 → 221`（只增）、backend `668 passed, 2 skipped`（不变） |
| 生产调用方 | 跨 seed 记录的 `build_/read_` 入口当前**无生产调用方**（未接入 campaign 账本/lease，见 `docs/50` §5）；接入需另轮授权 |

## 7. 未做事项与未覆盖面

- **两项未作答的问题按保守默认执行**（`docs/50` §1.1）：**不扩展** artifact v1；**不授权**真实受监督运行。若与本意不符，请指出：其中「不启动受监督运行」不受本轮代码影响；但「不扩展 artifact v1」若改为「扩展」，需**追加**代码改动、artifact `SCHEMA_VERSION` 升级与**后端读取端**的兼容处理（属另一轮范围）。
- **未**产生任何真实 `measured` 记录；未启动任何训练/评估/采样；未新建 campaign、未追加 seed、未重试 authorization、未消耗任何预算。
- **未**把新记录类型接入 `campaign.py` 的账本或 lease 路径；**未**提供 campaign 级的自动聚合驱动（记录类型与只读聚合入口已就绪，驱动需另轮授权）。
- **未**改动质量门槛（`docs/39` 继续不启用）；**未**实现覆盖率、有效支持集、分位数等额外字段。
- **未**推进 P2-2；**未**触及 `backend/**`、`frontend/**`、锁文件、真实数据库、`docs/20`–`docs/49a`。

## 8. 下一步唯一建议动作（不自行执行）

`docs/35` §4.2 至此**仅剩 P2-2**（N=9 的任何更强结论）。它须先裁定新的冻结 N=9 campaign 与预算 envelope（含 seed 集合、轮次/预热/停止条件、N9 estimator preflight 方案、需放开的代码闸门清单），且实际执行必须启动受监督运行——**请先给出该项的单独授权**，我再开轮。

（本轮改动仍在本地，`ahead 5`；按惯例**不自行 push**。）
