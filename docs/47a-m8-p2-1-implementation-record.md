# 47a M8：P2-1 2–9 人产品验收（实施与验收回执）

> 日期：2026-09-20。
>
> 本文件是 `docs/47` 的**实施与验收回执**，沿用 `docs/30` D6 的编号族约定。`docs/20` 至 `docs/46a` 未被改写；`docs/47` 未被改写（实施期只有两处**细化**，见 §2）。
>
> 本文件记录已实际落地的代码、测试与**一次本机浏览器实测**。**不产生任何策略、质量或性能证据**；未接入 CFR/查表、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、未推进任何训练。

## 1. 实施基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 7]

$ git status --porcelain=v1 --untracked-files=all | wc -l
0

$ git log -3 --oneline
2ac96dd docs: freeze p2-1 player count product acceptance specs
ead27f2 feat: add controlled decision latency measurement and post-fix remeasurement
b30d71e docs: freeze p1-5 post-fix decision latency remeasurement specs

$ git rev-parse HEAD          -> 2ac96dd（`docs/47` 冻结提交）
$ git rev-parse origin/master -> f9e957bf9f9a1df89bb92957c01e031d5d48723d

$ cd backend && uv run pytest -q
649 passed, 2 skipped, 2 warnings in 9.80s     （实施起点）
```

实施前工作区 0 行；未做任何 `reset` / `clean` / `stash` / `checkout`；本轮**不 push**。

## 2. 实施期规格细化（记录原因，不属修订）

`docs/47` 的四项裁定**未被变更**；实施中只细化了两处规格未写死的细节：

| # | 细化 | 原因 |
|---|---|---|
| 1 | 把「不相交」实现为**「相邻座位盒间距 ≥ 6px」**（新增常量 `MIN_SEAT_GAP`） | 牌桌高度搜索步长为 8px，只要求「不相交」时会落在**相切**的边界上（实测最小间距出现 `0.0px` 的结果），对亚像素取整与字体差异过于脆弱；加入安全间距后最小间距稳定在 `6.2–204px` |
| 2 | 座位定位的具体形态：`.seat` 用**基础盒像素定位 + `transform: scale()`**，并把座位行高、基础盒宽高、缩放全部以 CSS 变量下发 | 规格只要求「渲染盒 = 模型盒」；该形态使 `getBoundingClientRect()` 与模型盒**逐字节一致**（§7.3 实测），且几何模块成为行高的唯一来源 |

另有三处执行细节（不改变判据）：`.seat` 增加 `data-seat` 属性供实测识别；新增 `frontend/scripts/viewport-matrix.mjs` 作为验收视口的唯一来源；`frontend/package.json` 新增两个脚本入口 `check:layout` / `check:layout:browser`（**不新增依赖**）。

## 3. 实际改动（文件级）

| 文件 | 改动 |
|---|---|
| `backend/app/api/schemas.py`（修改，2 行） | `CreateGameRequest.num_players` 的 `le` 由 `10` 改为 `9`；类文档说明「人数上限只在这里落实」 |
| `backend/tests/test_player_count_acceptance.py`（**新增**，约 150 行） | 19 条回归测试，见 §5 |
| `frontend/src/seatLayout.js`（**新增**，约 230 行） | 座位布局纯几何：常量、`computeSeatLayout`、重叠/越界/最小间距判定；**无 DOM 依赖** |
| `frontend/src/components/GameTable.vue`（修改） | 人数表单/快捷项/校验改 2–9；座位定位与行高改由几何模块驱动；`.felt` 高度按人数与宽度计算；状态与下注标记合并为一行；`n ≥ 7` 摊牌明细折叠并在控制面板列出五张；几何不可行时显示明确提示 |
| `frontend/scripts/viewport-matrix.mjs`（**新增**） | 验收视口矩阵与牌桌宽度推导 |
| `frontend/scripts/check-seat-layout.mjs`（**新增**） | 纯几何回归检查（`node` 直跑，**无新依赖**） |
| `frontend/scripts/check-seat-layout-browser.mjs`（**新增**） | 浏览器实测：渲染 2–9 人桌面并读取真实包围盒 |
| `frontend/scripts/run-acceptance.mjs`（**新增**） | 一键编排：起后端（一次性库）与前端开发服务器 → 实测 → 收尾 |
| `frontend/package.json`（修改） | 新增 `check:layout` / `check:layout:browser` 两个脚本入口 |
| `docs/47-m8-p2-1-player-count-product-acceptance.md`（`2ac96dd`） | 规格冻结 |
| `docs/47a-…md`（本文件） | 实施与验收回执 |

**未改动**（`git status` 与 `git diff --stat` 可证）：`backend/app/poker/**`、`backend/app/analysis/**`、`backend/app/strategy/**`、`backend/app/storage/**`（含 `models.py`）、`backend/app/api/**` 的其它文件、`frontend/src/api.js`、`frontend/src/cards.js`、`frontend/src/reviewText.js`、`frontend/src/components/HistoryView.vue`、`frontend/src/components/StatsView.vue`、`frontend/src/components/PlayingCard.vue`、`tools/trainer/**`、`backend/uv.lock`、`frontend/package-lock.json`、`docs/20` 至 `docs/46a`。

**真实数据库未被写入**：实测用后端一律通过 `HOLDEM_DB_PATH` 指向一次性库 `backend/data/acceptance-tmp.db`（实测后已删除）。真实库 `backend/data/holdem.db` 的 mtime 仍为 `Sep 18 18:21`（本轮实测发生在 `Sep 20 16:00`），SHA-256 `b804bc4958543601ea9659090c20eae503a295d0b9494d0dc122f73abe3d0750`。

## 4. 实际形态

### 4.1 人数范围与兼容政策

| 项 | 实际行为 |
|---|---|
| 后端范围 | `2 ≤ num_players ≤ 9`；`0/1/10/11/-1` 一律 `422`；默认仍 `2` |
| 上限来源 | **唯一**来自 `CreateGameRequest`；前端只做同步展示与前置提示 |
| 前端输入 | `min=2 max=9`；快捷项 **2 / 6 / 9** |
| 表单校验 | 「玩家人数需为 2~9 的整数」（数值由 `MIN_PLAYERS`/`MAX_PLAYERS` 派生，不与后端漂移） |
| 旧 10 人配置 | `loadSavedConfig()` 判定非法返回 `null` → 回落设置表单；**不**自动改写、**不**静默降级为 9 |
| 旧 10 人历史 | `GET /games` 与 `GET /games/{id}/stats` 照库中原值只读展示；**不**新增列、**不**迁移 |

### 4.2 座位几何（几何模块为唯一来源）

| 项 | 取值 |
|---|---|
| 缩放档 | `1 / 0.9 / 0.8 / 0.72 / 0.65 / 0.58`（由大到小取第一个可行解） |
| 基础盒（未缩放） | 内联摊牌 `132 × 218`；紧凑摊牌 `110 × 178` |
| 内联摊牌人数 | `n ≤ 6`；`n ≥ 7` 摊牌折叠为一行（五张明细移到控制面板，信息不丢失） |
| 座位行高 | 标记 `18` / 底牌 `54` / 名字 `22` / 筹码 `20` / 状态+下注 `22` / 摊牌 `62` 或 `22`；行距 `4` |
| 牌桌高度 | 确定性搜索：步长 `8px`，范围 `420–900px`，取最小可行值 |
| 安全间距 | 相邻座位盒 ≥ `6px` |
| 不重叠保证 | 搜索失败时返回 `fits=false`，组件显示明确提示（实测 64/64 均未触发） |

## 5. 新增测试与覆盖对应

`backend/tests/test_player_count_acceptance.py`，**19 passed**（`1.16s`）。对应 `docs/47` §4.6：

| 验收项 | 覆盖（用例） |
|---|---|
| D1 人数范围落实 | `test_create_game_accepts_every_supported_player_count`（2–9 参数化，含盲注标记与首个行动者）、`test_create_game_rejects_player_counts_outside_the_product_range`（`0/1/10/11/-1` 参数化 → `422` 且不留记录）、`test_default_player_count_stays_two` |
| D2 上限来源唯一 | 表单校验文案与输入范围由几何模块的 `MIN_PLAYERS`/`MAX_PLAYERS` 派生（前端源码可证），后端为唯一裁决点 |
| D3 旧 10 人兼容 | `test_legacy_ten_player_session_stays_readable`（列表与统计照原值）、`test_new_game_creation_rejects_ten_players_but_keeps_legacy_rows` |
| D4 布局为纯几何 | `frontend/src/seatLayout.js` 无 DOM 依赖；`npm run check:layout` 直接 `node` 运行 |
| D5 6/7/9 不重叠 | 浏览器实测 64/64 通过（§7.1） |
| D6 模型盒 = 渲染盒 | 实测盒高与模型盒高在 64/64 组合中**完全相等**（§7.1 末两列） |
| D7 下注标记合并行 | 状态与 `+下注额` 同一 `.status-row`（行高固定 `22px`） |
| D8 摊牌信息不丢失 | `n ≥ 7` 时控制面板列出每个摊牌座位的牌型与五张牌 |
| D9 不静默降级 | `fits=false` 时 `.layout-warning` 明确提示；实测未触发 |
| D10 无新依赖 | `git diff --stat` 对两个锁文件**无输出**；几何检查只用 `node` |
| D11 层边界 | 见 §3 的未改动清单 |
| D12 既有语义与接口 | 后端完整套件 668 passed（基线 649 + 本轮 19，无既有用例被删改）；API 字段与响应结构未变 |

另含重点人数完整打一手：`test_large_table_can_play_a_hand`（`6/7/9` 参数化，单手净额归零）。

## 6. 实际验证输出

```text
$ cd backend && uv run ruff check .
All checks passed!

$ cd backend && uv run pytest -q
668 passed, 2 skipped, 2 warnings in 10.38s
（实施起点基线 649 passed, 1 skipped；新增 19 条，649 + 19 = 668）

$ cd backend && uv run pytest -q tests/test_player_count_acceptance.py
19 passed, 2 warnings in 1.16s

$ cd frontend && npm run build
vite v6.4.3 building for production...
✓ 24 modules transformed.        （本轮之前为 23，新增 seatLayout.js）
dist/index.html                   0.41 kB │ gzip:  0.31 kB
dist/assets/index-BjINKSI-.css   10.97 kB │ gzip:  2.58 kB    （之前 10.28 kB）
dist/assets/index-2_LUc3Jo.js   105.16 kB │ gzip: 39.41 kB    （之前 100.68 kB）
✓ built in 443ms

$ cd frontend && npm run check:layout
纯几何回归检查通过：64 个（视口 × 人数）组合全部不重叠、留有 ≥6px 间距且不越界。
```

两条 warning 均为既有的 Starlette/httpx 与 AnyIO 弃用提示。`tools/trainer/` **未触碰**，故未运行其 `ruff` / `pytest`。

## 7. 浏览器实测（本机单机型观测）

### 7.1 实测环境与命令

```text
$ cd frontend && npm run check:layout:browser
后端：http://localhost:8000/health（一次性数据库 backend/data/acceptance-tmp.db）
前端：http://localhost:5173/
（实测 8 人数 × 8 视口 = 64 个组合，全部通过）
```

| 项 | 取值 |
|---|---|
| 浏览器 | `agent-browser` 0.17.1 自带的 HeadlessChrome `145.0.7632.6` |
| 系统 | macOS `26.6.2` / `arm64` |
| 页面来源 | `vite` 开发服务器（`:5173`，代理 `/games`、`/hands`、`/health` → `:8000`） |
| 对局来源 | 每个人数通过 `POST /games` 创建一局（`seed = 20260920`），写入 localStorage 后加载页面 |
| 判定 | 座位数正确、两两不相交、全部落在 `.felt` 内、实测盒高 ≤ 模型盒高（容差 `1px`）、牌桌宽等于推导值 |

### 7.2 逐组合实测值（主判据）

| 人数 | 视口 | 视口宽 | 牌桌宽 | 牌桌高 | 座位数 | 最小间距 px | 实测盒高 | 模型盒高 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | desktop-wide | 1440 | 928 | 468 | 2 | 12.0 | 218.0 | 218.0 |
| 2 | desktop | 1280 | 928 | 468 | 2 | 12.0 | 218.0 | 218.0 |
| 2 | laptop | 1024 | 928 | 468 | 2 | 12.0 | 218.0 | 218.0 |
| 2 | narrow-laptop | 900 | 868 | 468 | 2 | 12.0 | 218.0 | 218.0 |
| 2 | tablet | 768 | 736 | 468 | 2 | 12.0 | 218.0 | 218.0 |
| 2 | small-tablet | 600 | 568 | 468 | 2 | 12.0 | 218.0 | 218.0 |
| 2 | large-phone | 480 | 448 | 468 | 2 | 12.0 | 218.0 | 218.0 |
| 2 | phone | 390 | 358 | 468 | 2 | 12.0 | 218.0 | 218.0 |
| 3 | desktop-wide | 1440 | 928 | 420 | 3 | 204.0 | 218.0 | 218.0 |
| 3 | desktop | 1280 | 928 | 420 | 3 | 204.0 | 218.0 | 218.0 |
| 3 | laptop | 1024 | 928 | 420 | 3 | 204.0 | 218.0 | 218.0 |
| 3 | narrow-laptop | 900 | 868 | 420 | 3 | 178.0 | 218.0 | 218.0 |
| 3 | tablet | 768 | 736 | 420 | 3 | 120.9 | 218.0 | 218.0 |
| 3 | small-tablet | 600 | 568 | 420 | 3 | 48.1 | 218.0 | 218.0 |
| 3 | large-phone | 480 | 448 | 540 | 3 | 8.5 | 218.0 | 218.0 |
| 3 | phone | 390 | 358 | 540 | 3 | 8.5 | 218.0 | 218.0 |
| 4 | desktop-wide | 1440 | 928 | 468 | 4 | 12.0 | 218.0 | 218.0 |
| 4 | desktop | 1280 | 928 | 468 | 4 | 12.0 | 218.0 | 218.0 |
| 4 | laptop | 1024 | 928 | 468 | 4 | 12.0 | 218.0 | 218.0 |
| 4 | narrow-laptop | 900 | 868 | 468 | 4 | 12.0 | 218.0 | 218.0 |
| 4 | tablet | 768 | 736 | 468 | 4 | 12.0 | 218.0 | 218.0 |
| 4 | small-tablet | 600 | 568 | 468 | 4 | 12.0 | 218.0 | 218.0 |
| 4 | large-phone | 480 | 448 | 468 | 4 | 12.0 | 218.0 | 218.0 |
| 4 | phone | 390 | 358 | 692 | 4 | 9.0 | 218.0 | 218.0 |
| 5 | desktop-wide | 1440 | 928 | 420 | 5 | 9.0 | 218.0 | 218.0 |
| 5 | desktop | 1280 | 928 | 420 | 5 | 9.0 | 218.0 | 218.0 |
| 5 | laptop | 1024 | 928 | 420 | 5 | 9.0 | 218.0 | 218.0 |
| 5 | narrow-laptop | 900 | 868 | 644 | 5 | 9.0 | 218.0 | 218.0 |
| 5 | tablet | 768 | 736 | 644 | 5 | 9.0 | 218.0 | 218.0 |
| 5 | small-tablet | 600 | 568 | 644 | 5 | 9.0 | 218.0 | 218.0 |
| 5 | large-phone | 480 | 448 | 644 | 5 | 8.8 | 218.0 | 218.0 |
| 5 | phone | 390 | 358 | 732 | 5 | 6.5 | 178.0 | 178.0 |
| 6 | desktop-wide | 1440 | 928 | 692 | 6 | 9.0 | 218.0 | 218.0 |
| 6 | desktop | 1280 | 928 | 692 | 6 | 9.0 | 218.0 | 218.0 |
| 6 | laptop | 1024 | 928 | 692 | 6 | 9.0 | 218.0 | 218.0 |
| 6 | narrow-laptop | 900 | 868 | 692 | 6 | 9.0 | 218.0 | 218.0 |
| 6 | tablet | 768 | 736 | 692 | 6 | 9.0 | 218.0 | 218.0 |
| 6 | small-tablet | 600 | 568 | 692 | 6 | 9.0 | 218.0 | 218.0 |
| 6 | large-phone | 480 | 448 | 572 | 6 | 9.0 | 178.0 | 178.0 |
| 6 | phone | 390 | 358 | 844 | 6 | 7.3 | 160.2 | 160.2 |
| 7 | desktop-wide | 1440 | 928 | 636 | 7 | 7.3 | 178.0 | 178.0 |
| 7 | desktop | 1280 | 928 | 636 | 7 | 7.3 | 178.0 | 178.0 |
| 7 | laptop | 1024 | 928 | 636 | 7 | 7.3 | 178.0 | 178.0 |
| 7 | narrow-laptop | 900 | 868 | 636 | 7 | 7.3 | 178.0 | 178.0 |
| 7 | tablet | 768 | 736 | 636 | 7 | 7.3 | 178.0 | 178.0 |
| 7 | small-tablet | 600 | 568 | 636 | 7 | 7.3 | 178.0 | 178.0 |
| 7 | large-phone | 480 | 448 | 748 | 7 | 8.6 | 178.0 | 178.0 |
| 7 | phone | 390 | 358 | 604 | 7 | 7.4 | 142.4 | 142.4 |
| 8 | desktop-wide | 1440 | 928 | 460 | 8 | 6.9 | 178.0 | 178.0 |
| 8 | desktop | 1280 | 928 | 460 | 8 | 6.9 | 178.0 | 178.0 |
| 8 | laptop | 1024 | 928 | 460 | 8 | 6.9 | 178.0 | 178.0 |
| 8 | narrow-laptop | 900 | 868 | 724 | 8 | 8.0 | 178.0 | 178.0 |
| 8 | tablet | 768 | 736 | 724 | 8 | 8.0 | 178.0 | 178.0 |
| 8 | small-tablet | 600 | 568 | 724 | 8 | 8.0 | 178.0 | 178.0 |
| 8 | large-phone | 480 | 448 | 652 | 8 | 6.6 | 160.2 | 160.2 |
| 8 | phone | 390 | 358 | 532 | 8 | 7.5 | 128.2 | 128.2 |
| 9 | desktop-wide | 1440 | 928 | 748 | 9 | 7.3 | 178.0 | 178.0 |
| 9 | desktop | 1280 | 928 | 748 | 9 | 7.3 | 178.0 | 178.0 |
| 9 | laptop | 1024 | 928 | 748 | 9 | 7.3 | 178.0 | 178.0 |
| 9 | narrow-laptop | 900 | 868 | 748 | 9 | 7.3 | 178.0 | 178.0 |
| 9 | tablet | 768 | 736 | 820 | 9 | 6.2 | 178.0 | 178.0 |
| 9 | small-tablet | 600 | 568 | 748 | 9 | 8.0 | 160.2 | 160.2 |
| 9 | large-phone | 480 | 448 | 844 | 9 | 7.5 | 142.4 | 142.4 |
| 9 | phone | 390 | 358 | 692 | 9 | 6.6 | 115.7 | 115.7 |

**结论**：`2–9 人 × 8 视口 = 64 个组合全部通过**——座位数正确、两两不相交（最小间距 `6.2–204.0px`）、全部落在牌桌内，且**实测盒高与模型盒高逐行完全相等**。

重点人数（`6/7/9`）的实测最小间距分别为 `7.3 / 7.3–8.6 / 6.2–8.0px`；**没有任何组合出现重叠或越界**。

### 7.3 纯几何回归检查（补充证据）

```text
$ cd frontend && npm run check:layout
纯几何回归检查通过：64 个（视口 × 人数）组合全部不重叠、留有 ≥6px 间距且不越界。
```

矩阵（单元格 = `牌桌高度/缩放`，后缀 `c` 表示紧凑摊牌行；列为 `docs/47` §4.4 的 8 个视口）：

| 人数 | desktop-wide | desktop | laptop | narrow-laptop | tablet | small-tablet | large-phone | phone |
|---:|---|---|---|---|---|---|---|---|
| 2 | 468/1 | 468/1 | 468/1 | 468/1 | 468/1 | 468/1 | 468/1 | 468/1 |
| 3 | 420/1 | 420/1 | 420/1 | 420/1 | 420/1 | 420/1 | 540/1 | 540/1 |
| 4 | 468/1 | 468/1 | 468/1 | 468/1 | 468/1 | 468/1 | 468/1 | 692/1 |
| 5 | 420/1 | 420/1 | 420/1 | 644/1 | 644/1 | 644/1 | 644/1 | 732/1c |
| 6 | 692/1 | 692/1 | 692/1 | 692/1 | 692/1 | 692/1 | 572/1c | 844/0.9c |
| 7 | 636/1c | 636/1c | 636/1c | 636/1c | 636/1c | 636/1c | 748/1c | 604/0.8c |
| 8 | 460/1c | 460/1c | 460/1c | 724/1c | 724/1c | 724/1c | 652/0.9c | 532/0.72c |
| 9 | 748/1c | 748/1c | 748/1c | 748/1c | 820/1c | 748/0.9c | 844/0.8c | 692/0.65c |

几何结果与 §7.2 的浏览器实测**逐行一致**（牌桌高度、缩放、摊牌形态、最小间距全部相同），说明「模型盒 = 渲染盒」不是近似而是同一口径。

### 7.4 未覆盖与边界

| 项 | 状态 |
|---|---|
| 视口矩阵之外 | **未测**：未覆盖的宽度（例如 320px 或超宽屏 2560px）未验证；`phone(390px)` 已是最窄覆盖点 |
| 其他浏览器 / 字体 | **未测**：只覆盖了 Agent Browser 自带的 HeadlessChrome `145.0`；不同字体与 `font-size` 设置可能改变行高（模型按固定行高预留，因此理论上仍有 `6px+` 余量，但**未实测**） |
| 页面缩放（浏览器 zoom） | **未测**：非 100% 缩放未验证 |
| 真实设备 / 触屏 | **未测**：未在真实手机或平板设备上验证 |
| 摊牌折叠的视觉验收 | **部分覆盖**：`n ≥ 7` 时折叠为一行、五张明细在控制面板列出（结构已实现并随实测渲染），但**未**做逐人视觉美观验收 |
| 性能 | **本轮不涉及**：`100ms` 是实时 Bot 决策预算，**不是**整手复盘预算；本轮未做任何性能结论 |

## 8. 版本影响与兼容性

| 对象 | 实际行为 |
|---|---|
| 创建接口 | 仅人数上限 `10 → 9`；越界 `422` 且不落库；默认仍 `2`；其余字段与语义不变 |
| 响应模型 | **不新增、不改名字段**；`SessionSummary` / `SessionStats.num_players` 仍为 `int` 原值 |
| 引擎 / 结算 / 策略 / 复盘 | **零改动**（`poker/**`、`strategy/**` 未被触碰）；`history_json` 未被改写 |
| 数据库 | **不加列、不迁移**；真实库未被写入（§3 的 mtime 与 SHA-256 证据） |
| 旧历史 | 只读展示不变；真实库中本无 10 人对局（2 人 3 局、5 人 40 局） |
| 前端对外行为 | 人数表单/快捷项/校验改为 2–9；座位布局改为几何驱动；`n ≥ 7` 摊牌明细位置变化（信息不丢失）；新增几何不可行时的明确提示 |
| 前端依赖 | **不新增依赖**；`frontend/package-lock.json` 与 `backend/uv.lock` 零改动（`git diff --stat` 无输出） |
| `docs/37` §3.1 升版判定 | **不触发**：参考实现、保守判据、`equity` 实现、采样数与固定种子五项全部零改动 |
| 旧 10 人配置的实际处置 | 回落设置表单重新选择；**不**改写、**不**迁移、**不**静默降级 |

## 9. 边界声明与不得声称

- 本轮是**产品可达性（人数范围）与前端布局验收**，**不是**策略质量、收敛或生产可用性证据；**未接入** CFR/查表。
- 「上限 9」是**产品限制**，**不得**表述为引擎能力上限，也**不得**表述为「9 人策略已训练/已验证」；N=9 的任何更强结论仍属 P2-2。
- 实测值只对**本机、该浏览器（HeadlessChrome `145.0.7632.6`）、该 8 视口矩阵、100% 页面缩放**生效；**不外推**其他浏览器、字体、缩放比或真实设备；**有限视口不能证明所有屏幕都不重叠**。
- **不得**把本轮任何结论表述为性能证据；`100ms` 是**实时 Bot 决策**预算，**不是**整手复盘预算。
- 旧 10 人兼容政策**不得**被表述为「已迁移」或「已删除历史」——本轮**没有**迁移，也**没有**改写任何旧数据。
- **单元测试与几何检查都不等于产品验收结论**；它们只证明「在给定视口矩阵下不重叠」。
- 未改写 `docs/20` 至 `docs/46a`；未 push。

## 10. 预算核算

```text
$ cd frontend && S=$SECONDS; node scripts/run-acceptance.mjs >/dev/null; echo $((SECONDS-S))
45
（含两个服务器启动、浏览器冷启动、64 个组合的视口切换与包围盒测量；
 复跑结果与首次逐行一致，几何为确定性搜索）

纯几何回归检查（node 直跑）                                < 1 s
后端完整套件 / ruff / 前端构建                             约 15 s
```

**未消耗任何本机实验预算 / authorization**：本轮是产品验收与前端布局改动，不是受监督训练运行；未新建 campaign、未追加 seed、未重试任何已消耗 authorization；未上云、未转 GPU。

## 11. 未做事项与下一步唯一建议动作

未做：

- 未接入 CFR/查表到运行时；未实现任何回退动作；`strategy/**` 零改动。
- 未改 `poker/**`、`analysis/**`、`storage/**`（含 `models.py`）、锁文件、真实数据库、`tools/trainer/**`、`docs/20` 至 `docs/46a`。
- 未实现 P2-2（N=9 更强结论）、P2-3（历史 `pot_results` 不一致）、P2-4（稳定性生产者）。
- 未启用 `docs/39` 的质量门槛；未恢复已移除的前端策略选择器。
- 未做其他浏览器、真实设备、页面缩放与非 100% 字体设置的验收（§7.4）。
- 未对摊牌折叠做逐人视觉美观验收。
- 未 push（本轮共两次提交，均为本地提交）。

P2-1 的**范围界定、兼容政策与 6/7/9 不重叠**三项口径均已闭环；`docs/35` §4.2 的 P2 组剩余项（P2-2 / P2-3 / P2-4）相互独立，可各自单独排期。

下一步**唯一建议动作**（需用户决定，本轮不自行执行）：**从 P2-2 / P2-3 / P2-4 中选定唯一一项并单独授权**。若需建议，**P2-3（四笔历史 `pot_results` 与当前结算不一致的只读诊断）**风险与服务价值最均衡：它是**只读**诊断、不改任何结算语义，且直接关系到历史复盘的可信度；而 P2-2 需要新的冻结 campaign 与授权，P2-4 属长期工程项。
