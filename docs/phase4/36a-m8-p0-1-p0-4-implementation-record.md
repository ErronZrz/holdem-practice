# 36a M8：P0-1 策略标识与受控注册表、P0-4 信息边界与对外投影——实施与验证回执

> 日期：2026-09-18。
>
> 本文件接在 `docs/36` 之后，沿用 `docs/30` D6 的编号族约定：`docs/36` 为规格与设计岔路冻结，本文件为同一轮的**实施与验证回执**（同一编号族内可多次提交）。
>
> 本文件只记录已实际落地的代码、测试与实跑输出；**不产生任何策略、质量或资源证据**。`docs/20` 至 `docs/36` 未被改写。

## 1. 本轮提交与设计岔路的裁定方式

本轮按 `docs/36` §1.2 采用的裁定方式为**“先在文档冻结规格”**（`docs/36` §1.3）。因此：

- 三个设计岔路的裁定为**代理在文档内冻结**，**不是**用户答复原文；
- 本文**不冒充**用户答复：若用户对任一项有不同意见，应按 `docs/36` §1.2 第 2 条先修订 `docs/36` 再改代码；
- 用户**未**逐项回复；本轮实际执行的授权范围就是接手约束里写明的两项（P0-1、P0-4）。

本轮提交（两次，符合“规格与实现分两次提交”）：

| 次序 | commit | 内容 |
|---|---|---|
| 1 | `ccf208e` | `docs/36` 规格与设计岔路冻结（仅文档） |
| 2 | 本文件同批 | P0-1 与 P0-4 的实现、回归测试、`docs/36a` |

## 2. 实际基线核验（只读）

```text
$ git status --short --branch
## master...origin/master

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git rev-parse HEAD          -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f
$ git rev-parse origin/master -> ef7e59282015e58f0e7fd153e30cd85ae6e9f56f

$ git log -4 --oneline
ef7e592 docs: record decision addendum and opponent-upgrade preregistration
f9d14d5 docs: record candidate-a closeout decision and production readiness checklist
f055a3c docs: record n6 cross-seed receipts and the seed-dependent verdict reversal
eda4f9c docs: freeze n6 cross-seed campaign and record budget posture change
```

与期望基线完全相符；未做任何 `reset` / `clean` / `stash` / `checkout`。

## 3. 实际改动清单（文件级）

### 3.1 新增

| 文件 | 内容 |
|---|---|
| `backend/app/strategy/registry.py` | 受控策略注册表：`StrategySpec`、`register_strategy`、`resolve_identifier`、`spec_for`、`create_strategy`、`known_identifiers`、`UnknownStrategyError`；内置 `heuristic@1` / `random@1`，旧别名 `heuristic` / `random` 固定指向 v1 |
| `backend/app/strategy/projection.py` | `project_for_actor(state)`：仅保留公开信息与行动者本人底牌，其他座位 `hole_cards` 置空 |
| `backend/tests/test_strategy_registry.py` | 注册表与接口层回归测试（21 个用例，含参数化） |
| `backend/tests/test_info_boundary.py` | 信息边界、历史投影与 seed 外发回归测试（7 个用例） |
| `docs/36`、`docs/36a` | 规格冻结与实施回执 |

### 3.2 修改

| 文件 | 改动 |
|---|---|
| `backend/app/api/schemas.py` | `CreateGameRequest.bot_strategy` 由 `Literal["heuristic","random"]` 改为 `str`（默认 `heuristic@1`、`validate_default=True`），并加 `field_validator` 调用 `resolve_identifier`；未知标识 → `422` |
| `backend/app/api/games.py` | `_make_bot` 改经 `create_strategy`；`GameRuntime` 新增 `bot_strategy` 字段；`_advance_if_bot_turn` 传入 `project_for_actor(...)`；`_finalize_hand` 把策略标识写入历史 |
| `backend/app/api/hands.py` | `HandDetail` 与手牌摘要改经 `project_hand_history(...)` 输出 |
| `backend/app/storage/hand_history.py` | 新增 `HAND_HISTORY_SCHEMA_VERSION` / `UNKNOWN_VERSION` 与 `project_hand_history`；`build_hand_history` 增加顶层 `schema_version`、`bot_strategy`（新增关键字参数，旧调用不受影响） |
| `backend/app/storage/__init__.py` | 导出 `project_hand_history` 与版本常量 |
| `backend/app/storage/models.py` | `sessions.bot_strategy` **列定义不变**（`String(32)`），仅把 Python 侧默认值改为规范形态 `heuristic@1`；**无迁移、无新列** |
| `backend/app/strategy/__init__.py` | 导出 `create_strategy`、`resolve_identifier`、`StrategySpec`、`UnknownStrategyError`、`project_for_actor` |

### 3.3 未触碰

- `backend/app/poker/**`：零改动。`equity` / `estimate_static_showdown_share` / `pot_projection` / `_settle_showdown` / 任何结算语义不变。
- `backend/app/strategy/heuristic.py`：零改动（仅被注册表引用），决策语义与参考分布不变（`docs/35a` D4 = A 继续有效）。
- `frontend/**`：零改动（不恢复策略选择器）。
- `tools/trainer/**`、锁文件 `backend/uv.lock` / `frontend/package-lock.json`：零改动。
- 真实数据库 `backend/data/holdem.db`：只读，未迁移、未写入（`mtime` 仍为 `Sep 17 11:32`）。

## 4. 新增/修改的测试

新增 28 个用例（`160 → 188`）：

```text
$ uv run pytest -q --collect-only | tail -1
188 tests collected in 0.58s

$ uv run pytest -q --collect-only tests/test_strategy_registry.py tests/test_info_boundary.py | tail -1
28 tests collected in 0.45s
```

`test_strategy_registry.py`（21）：

- 旧值规范化：`heuristic → heuristic@1`、`random → random@1`；规范标识原样解析；
- 未知标识失败：`cfr` / `heuristic@2` / 类名 / 模块路径 / 属性链 / 空串 / 带尾随空格（参数化）；
- 注册约束：标识重复报错；**旧别名不得被新版本接管**且失败注册不留痕；
- 接口层：旧值入库为规范标识、缺省入库为 `heuristic@1`、`random@1` 构造 `RandomStrategy`、未知标识返回 `422`（参数化）。

`test_info_boundary.py`（7）：

- 投影只保留行动者底牌，公开字段原样；
- 投影结果不含 `seed`（`dataclasses.asdict` 递归）；
- **仅替换其他座位底牌后投影相等，且同 seed 下 `action_distribution` 逐项相等**（P0-4 核心验收）；
- 白名单丢弃未登记键（`master_seed` / `rng_state`）；
- 旧历史按 `unknown` 读取，已知旧字段仍透出；旧历史摘要接口仍可用；
- 新历史带 `schema_version = hand-history.v1` 与 `bot_strategy = heuristic@1`；对局视图 / 手牌详情 / 复盘 JSON **递归不存在** `seed` 键。

## 5. 实跑验证输出

```text
$ uv run ruff check .
All checks passed!

$ uv run pytest -q
188 passed, 2 warnings in 9.57s
（2 条 warning 来自第三方 starlette/anyio 弃用提示，非本轮引入）

$ npm run build   （frontend/）
vite v6.4.3 building for production...
✓ 22 modules transformed.
dist/index.html                  0.41 kB │ gzip:  0.31 kB
dist/assets/index-BmvYNXUR.css  10.28 kB │ gzip:  2.42 kB
dist/assets/index-vteOA14Z.js   99.85 kB │ gzip: 37.36 kB
✓ built in 535ms
```

前端本次未改动源码，`build` 为按提交前检查要求执行；`dist/` 未进入版本控制。

## 6. 版本影响与兼容性（实测）

| 对象 | 实际行为 |
|---|---|
| 旧请求值 | `heuristic` / `random` 仍然成功，并被规范化落库为 `heuristic@1` / `random@1`（实测） |
| 未知标识 | 返回 `422`，**不静默回退**到 `heuristic`（实测） |
| 旧对局行 | 不迁移、不回填；`bot_strategy` 列定义与旧值原样保留 |
| 旧历史 | 无版本字段 → `schema_version` / `bot_strategy` 均读出 `unknown`；白名单内旧字段继续可用（实测） |
| 新历史 | 记录 `hand-history.v1` 与规范策略标识；原始 `history_json` 不被改写，投影只作用于响应 |
| 前端 | 无改动；历史视图消费的字段全部在白名单内（`players` / `actions` / `board` / `net` / `showdown_hands` / `pot_results` / `winners` / `showdown` / 基础元数据） |
| 对局行为 | Bot 决策分支与 `HeuristicStrategy` 语义未变；投影只移除策略本就不消费的对手暗牌 |

## 7. 边界声明与不得声称

- 本轮**未**接入 CFR：`backend/app/strategy/` 仍无 lookup、无产物加载；不构成 `docs/35` §4 中 P0-2 / P0-3 / P0-5 / P0-6 / P0-7 的任何进展。
- **单元测试不等于 A6/A7 实验结果**；本轮不新增任何质量、收敛或稳定性结论。
- 不得把本轮改动表述为多人 Hold'em GTO、均衡、NashConv、exploitability、真实牌局 EV 或生产可用策略。
- 本轮不存在任何稳定性生产者；若出现对照结论，必须标注为“事后跨工件只读比较”（本轮无该类结论）。
- **未启动实际运行前，不得伪称已生成策略、质量或资源证据。**
- 本轮未追加 seed、未新建冻结 campaign、未重试任何已消耗 authorization、未上云、未转 GPU、未扩预算；`/Users/bryanylliu/holdem-campaigns/` 原样保留。

## 8. 未做事项与下一步唯一建议动作

未做：

- 未实施 `docs/35` §4 清单中 P0-1、P0-4 以外的任何一项（P0-2 / P0-3 / P0-5 / P0-6 / P0-7、P1 组、P2 组全部未动）。
- 未给 `sessions` 增加任何列、未做迁移、未回填旧数据；未改写任何历史 JSON。
- 未恢复前端策略选择器；未改动 `frontend/` 任何源码。
- 未改动 `tools/trainer/`、锁文件与真实数据库；未触碰 `equity` / static share / 池层投影 / 生产结算。
- 未新建 campaign、未追加 seed、未重试 authorization、未做云端操作。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**先按 `docs/36` §1.3 确认或修订三项设计岔路裁定**；确认后，从 `docs/35` §4 的 P0 组剩余项中选定**唯一一项**并单独授权实施。若需建议，按 `docs/36` §1.3 与 `docs/35` §4.3 的依赖，**P0-5（评估/参考版本化）** 与 P0-1/P0-4 同属“契约与标识”层、不引入新实验，是风险最低、共识最高的下一项。
