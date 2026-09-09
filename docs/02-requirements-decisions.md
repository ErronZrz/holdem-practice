# 需求决策记录（Phase 0 确认结果）

> 本文档是需求分析阶段对 `01-chatgpt-suggestion.md` 中悬而未决点的最终拍板，作为后续架构设计与开发范围的输入。编号 `D1`–`D7` 对应上轮向用户确认的七个决策点。

---

## 一、决策点落定

### D1 目标用户：单用户自用

- **结论**：第一阶段仅单用户自用。
- **影响**：
  - 不做注册、登录、多用户隔离。
  - 数据模型以 `Session` 为顶层，`User` 表可省略（或保留为单例占位，不引入鉴权逻辑）。
  - 公网部署仍保留 HTTPS + 一层简单访问保护（如反向代理 Basic Auth 或等价手段），仅用于防止被公网随意访问，不属于账号体系。

### D2 Bot 智能水平底线

- **结论**：MVP 中 Bot 只需「合理、不轻易被 exploit」即可。
- **影响**：
  - 核心交付用 heuristic 策略即可，**CFR 是增强项，不阻塞上线**。
  - 里程碑收敛到 M3（可玩 Web App）即形成闭环；M4/M5（Kuhn 验证、简化 Hold'em CFR）作为 stretch goal 延后。

### D3 策略训练与产物

- **结论**：离线训练在 MacBook 上完成，线上只做 lookup。
- **影响**：
  - 保留 `tools/trainer` 工具链；策略文件（如 `strategy-v*.bin`）以产物形式提交/上传。
  - Backend 只读取策略产物，不在服务器运行 CFR Training。

### D4 会话规则

- **结论**：
  - 一次 Session 打**有限手数**，手数由用户指定。
  - 筹码输光后**自动 rebuy** 至初始深度（100BB）。
  - 需要**结算展示**（单局赢输 BB、Session 累计战绩）。
- **影响**：
  - `Session` 需记录目标手数、已打手数、累计盈亏。
  - `Hand` 需记录结算结果；前端需结算/统计页。

### D5 UI 语言

- **结论**：UI 使用中文；DeepSeek 解释输出中文。

### D6 前端技术栈

- **结论**：Vue 3 + Vite。

### D7 牌桌规模与位置策略（核心决策）

- **结论**：
  - **Poker Engine 按通用 N 人设计**（多 seat、side pot、位置轮转、行动顺序），不从引擎层写死 2 人。
  - **MVP 可玩闭环先用 Heads-Up（1 真人 vs 1 Bot）试玩**，验证引擎正确性；**随后扩展 5 人桌（1 真人 + 4 Bot）**。
  - **Bot 策略初期不做位置感知**，先统一策略，位置感知后续作为增强。
- **影响**：
  - 引擎核心结构（Seat/Player/Pot/SidePot/Position/Button 轮转/Blind 轮转）从第一天就按 N 人建模。
  - side pot 机制在引擎层必须支持；HU 试玩阶段不触发或仅覆盖简单场景。
  - Strategy 接口与位置解耦，先统一 heuristic，后续再注入位置维度。

---

## 二、据此锁定的第一阶段（MVP）范围

- 单用户、中文界面、Vue 3 + Vite 前端。
- Heads-Up No-Limit Hold'em（引擎已按 N 人设计，MVP 只开放 HU 试玩）。
- 固定 100BB 初始筹码、固定盲注、单桌。
- 完整 Preflop / Flop / Turn / River，支持 Fold / Check / Call / Bet / Raise。
- heuristic Bot（合理、不轻易被 exploit、不分位置）。
- 有限手数 Session + 输光自动 rebuy + 结算展示。
- 牌局历史（JSON 为 source of truth）+ 结构化复盘。
- DeepSeek 仅在用户主动请求时做中文解释。

## 三、明确不在第一阶段范围（暂不做）

- 注册 / 登录 / 多用户体系。
- 5 人桌开放试玩（引擎预留，第二阶段开放）。
- 位置感知策略、多人 CFR、完整 GTO Solver。
- 锦标赛、真钱、充值。
- 多桌、大规模并发、GPU 推理。

## 四、从决策推导的关键架构约束

1. **Poker Engine 独立且按 N 人设计，充分测试**（含 side pot、位置轮转，尽管 MVP 只跑 HU）。
2. **Strategy 为插件式接口**（random / heuristic / 后续 CFR），与位置、与具体牌型解耦。
3. **CFR Training 与 Runtime 完全分离**，训练离线进行，产物提交部署。
4. **DeepSeek 只负责解释、不负责决策**，为 optional 依赖，挂了不影响打牌。
5. **单用户模式**：数据模型以 `Session` 为顶层，`Hand` / `Decision` 挂在 `Session` 下。
