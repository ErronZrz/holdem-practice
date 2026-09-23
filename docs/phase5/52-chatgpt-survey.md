# 德州扑克 Bot 练习平台：策略来源与技术路线调研

> 调研日期：2026-09-20  
> 目标：构建以 6–7 人桌为主、可进一步扩展至 9 人桌、全部对手均为 Bot 的德州扑克练习平台。  
> 本报告只讨论自有练习环境，不涉及真钱牌桌实时辅助（RTA）。

## 1. 执行摘要

按本项目的取舍顺序：

1. **不可预测性**：最不希望牺牲；
2. **运行时成本**：轻量服务器可承载，外部服务费用可控；
3. **不可剥削性**：希望尽量保留，但可以为前两项让步。

最合适的路线不是寻找一个“免费、完整、多人、职业级”的万能策略库——目前没有可信的现成方案同时满足这些条件——而是采用**混合策略路由架构**：

- 使用 PokerKit 一类开源库承载 2–9 人规则和牌局状态；
- 翻牌前使用本地范围表，运行时只做查询；
- 两人底池 postflop 优先使用预计算策略缓存；
- 多人底池使用范围估计、Monte Carlo equity 和可参数化规则；
- 以 GTO/近 GTO 策略作为基线，再通过“对手人格参数 + 每手牌隐变量 + 概率采样”产生多样打法；
- 仅把收费 API 用作冷启动、离线补表和质量标杆，不作为所有 Bot 每一步决策的在线依赖；
- 引入少量已训练模型或独立规则族，避免所有 Bot 只是同一张策略表的轻微变体。

推荐的第一版组合是：

> **PokerKit 规则引擎 + 本地 6-max 翻前表 + 两人 postflop 缓存 + 多人 equity/规则 fallback + 多风格概率变换器；Pokerai API 只承担离线补表和抽样校验。**

这条路线最符合优先级：不可预测性高、运行时便宜，策略强度虽不等同于 Pluribus，但可通过离线回归和 exploit 测试逐步提升。

---

## 2. 需求三角的工程化定义

### 2.1 不可预测性

“不可预测”不应等同于随意随机。纯随机 Bot 很难预测，但也很弱、缺乏人格。这里将不可预测性拆成三个可检验维度。

#### A. 同一对手、不同 hand 的动作多样性

同一个 Bot 在相似牌面和历史下，不应永远选择相同动作。基准策略应输出概率分布，例如：

```text
Fold 10% / Call 55% / Raise 35%
```

运行时再按概率采样，而不是执行 `argmax`。同时，每手牌为 Bot 抽取一个低维“状态”——例如谨慎、正常、施压——使这一手内部打法保持连贯，而不是每一步独立掷骰。

#### B. 相同动作下的下注尺度多样性

当 Bot 选择 bet/raise 时，不能固定使用一个筹码尺度。下注尺度也应是一层条件概率分布，例如：

```text
33% pot: 20%
50% pot: 35%
75% pot: 30%
125% pot: 10%
All-in: 5%
```

实际候选尺度需要结合 street、SPR、牌面结构、位置和人格过滤。不可为了“多样”在明显不合理的节点随机使用任意数额。

#### C. 不同对手的打法差异

不同 Bot 不能只是更换头像和昵称后查询同一套策略。至少应有三层差异：

- **范围差异**：VPIP、PFR、3-bet、冷跟范围；
- **行动差异**：价值下注、诈唬、check-raise、barrel、hero call 倾向；
- **尺寸差异**：偏好小注、多尺度、超池、极化或全下。

理想情况下，部分 Bot 还应来自不同的决策族，例如 lookup 型、神经网络型和规则/对手建模型，而不只是同一概率表的参数偏移。

### 2.2 运行时成本

运行时目标应是：

- 单个普通 CPU 实例可运行多个牌桌；
- 大部分行动在 10–50 ms 内完成；
- 不要求 GPU；
- 不在每个行动节点启动求解器；
- 外部 API 故障或额度耗尽时，牌局仍可继续；
- 付费查询通过本地缓存、请求去重和离线批量生成控制。

### 2.3 不可剥削性

本项目不以“求出多人 Nash equilibrium”为必须条件，但应避免明显可机械利用的漏洞，例如：

- 相同信息集永远选择相同动作；
- 某个下注尺度只对应强牌；
- 面对大注按固定牌力阈值弃牌；
- 多人底池无条件过度诈唬；
- 不根据位置、SPR、人数和历史调整范围。

不可剥削性的现实目标可定义为：**普通到较强的人类玩家不能在短时间内发现一个稳定、重复、收益显著的机械打法。**

---

## 3. 互联网可用资源

### 3.1 Pokerai API：最接近现成 lookup 的服务

项目地址：[Pokerai API](https://github.com/pokerai-bet)

其公开说明称，API 提供 6-max NLHE 全街混合频率策略：翻前和 flop 来自预解结果，turn/river 由实时求解池处理。免费层为每月 1,000 次预解查询和 25 次实时求解，不要求信用卡。用途条款允许训练、教学、复盘和研究，禁止真钱桌 RTA。

**与需求三角的匹配：**

- 不可预测性：高。返回动作频率，适合概率采样；若响应包含多种下注动作，也可生成尺度多样性。
- 运行时成本：原型期低，规模化后取决于定价与缓存命中率。
- 不可剥削性：理论上是候选中最强的一类，但“solver-grade”目前主要是服务方自述，缺少公开独立基准。

**建议用途：**

- 用免费层验证状态编码和响应质量；
- 离线收集常见节点并建立本地缓存；
- 定期抽样对比自有 Bot；
- 不将其设为所有 Bot 的强制实时依赖。

**待确认事项：**

- 响应长期存储和批量缓存是否被条款允许；
- 商业产品能否向终端用户间接提供策略结果；
- 超出免费层后的单次成本、速率限制和 SLA；
- 7-max/9-max 与多人 postflop 是否有产品计划。

### 3.2 deepbot-poker：附带权重的 6 人研究 Bot

项目地址：[deepbot-poker](https://github.com/tamlhp/deepbot-poker)

该项目使用神经网络和 LSTM 跟踪牌局及不同对手，提供 `6max_full`、`6max_single` 和 heads-up 等预训练权重。`6max_full` 的目标是 6 人 SNG，并在多种规则型对手桌上训练。许可证为 Apache-2.0。

**优势：**

- 真正附带可运行的 6 人预训练模型；
- 具备跨 hand 的记忆与对手建模特征；
- 可以和 lookup Bot 构成不同决策族，提高对手间差异。

**限制：**

- 工程基于 Python 3.5 和修改版 PyPokerEngine，现代化成本较高；
- 训练目标为 6 人 SNG，不等于 100BB cash；
- 不能未经修改直接处理 7 人输入；
- 原模型输出可能仍需增加温度采样或策略 wrapper，才能获得足够的尺度多样性。

**结论：**适合作为 Bot 池中的一个独立人格族，不适合作为全平台唯一策略。

### 3.3 PokerTH：成熟的多人产品与风格参考

项目地址：[PokerTH](https://www.pokerth.net/)；[项目说明](https://sourceforge.net/projects/pokerth/)

PokerTH 支持最多九个电脑对手，覆盖 Windows、macOS、Linux 等平台。其客户端生态提供不同难度及 Calling Station、Maniac 等风格。

**适用价值：**

- 直接体验多人桌对 Bot 产品；
- 研究交互、节奏、难度分层和人格呈现；
- 参考规则型 Bot 如何以极低成本运行。

**不足：**Bot 更偏产品型规则 AI，不是 solver 级策略。项目采用 AGPL，若复用代码构建网络服务，需要专门审查开源义务。

### 3.4 PokerData API：翻前数据较丰富，但不属于免费主路线

项目地址：[PokerData Ranges API](https://pokerdata.io/api)

公开页面提供 6-max NLHE 多筹码深度翻前范围、动作路径和手牌 EV；postflop 部分为已经求解的单挑底池。发现/目录接口免费，正式数据方案从约 100 美元/月起。

**评价：**

- 适合作为翻前数据补充或质量对照；
- 不能覆盖完整多人 postflop；
- 固定月费是否可控取决于产品预算；
- 页面列出的 NLHE 重点是 6-max，不能直接视为 7-max 策略。

### 3.5 TexasSolver：适合离线生成单挑 postflop 缓存

项目地址：[TexasSolver](https://github.com/bupticybee/TexasSolver)

TexasSolver 是开源 Texas Hold’em/短牌 postflop 求解器，可导出 JSON 策略。其主要能力是两人 postflop，并不能求出完整 6–7 人桌策略。

**最佳使用方式：**

- 在开发机或批处理节点离线求解常见 SRP、3-bet pot 和典型牌面；
- 将结果归一化后保存为只读 lookup 文件；
- 线上服务器仅加载和查询，不运行 CFR。

项目使用 AGPL，并在 README 中对集成代码和互联网服务另外提示商业许可要求。因此，在产品集成前必须完成许可证确认，不能只依据“个人用户免费”推断商业可用。

### 3.6 PokerKit：推荐的规则与状态底座

项目地址：[PokerKit](https://github.com/uoftcprg/pokerkit)

PokerKit 是 Python 扑克状态机和牌型计算库，支持多人 NLHE 及多种扑克变体。它不提供强 Bot，但适合统一处理：

- 发牌、盲注、ante、straddle；
- 合法动作与最小加注；
- side pot、all-in、摊牌；
- 2–9 人桌状态；
- hand history 与重放。

使用独立规则引擎的好处是让“牌局是否合法”和“Bot 是否聪明”解耦，后续可以自由替换策略提供者。

### 3.7 OpenSpiel：适合研究和评测，不是现成产品 Bot

项目地址：[OpenSpiel](https://github.com/google-deepmind/open_spiel)

OpenSpiel 的 Universal Poker 支持 2–10 人、limit/no-limit 和多种实验配置，也包含 CFR、Deep CFR、策略评测等研究工具。

它适合：

- 构建缩小版扑克进行算法实验；
- 运行 best-response、self-play 和策略族评测；
- 验证动作抽象或训练流程。

它并未附送一个可直接部署的强 6-max NLHE 权重，Universal Poker 的部分完整下注抽象也有历史限制，因此不建议把它直接作为线上牌局引擎。

### 3.8 Poker GTO Trainer：仅作为原型参考

项目地址：[Poker GTO Trainer](https://github.com/haowenzheng-art/poker-gto-trainer/)

该项目宣称支持 6/9-max、预计算策略、混合频率、EV 提示和五个 Bot，许可证为 MIT。但其公开策略文档又显示，许多翻前与 postflop 决策来自粗粒度范围和 `basic_*_rules()` fallback；postflop 示例按强牌、中等牌、弱牌给出固定频率。

因此，它适合借鉴：

- 桌面 UI；
- session 统计；
- hint 和复盘交互；
- 策略接口结构。

不应在缺少逐节点验证的情况下，将其数据直接宣传为可靠 GTO lookup。

### 3.9 Pluribus：重要基准，但没有可下载策略

CMU 和 Facebook 的 Pluribus 在六人 NLHE 中击败顶尖职业玩家。其方法是离线 self-play blueprint 加线上有限深度 subgame search。公开资料还指出，生成 blueprint 使用了约 12,400 CPU core-hours，实时对局使用约 28 个 CPU core。[CMU 官方介绍](https://www.cs.cmu.edu/news/2019/carnegie-mellon-and-facebook-ai-beats-professionals-six-player-poker)

但 Pluribus 的完整代码、权重和 lookup 表并未作为可直接使用的公共资源发布。因此，GitHub 上自称“Pluribus-style”或“Pluribus-quality”的项目，应视为独立复现尝试，而不是官方 Pluribus。

---

## 4. 基于需求三角的候选评分

评分为相对判断：5 最符合，1 最不符合。“不可剥削性”只评价公开信息能够支持的程度，不代表经过严格认证。

| 方案 | hand 动作多样 | 下注尺度多样 | 对手间差异 | 运行成本 | 不可剥削性 | 建议角色 |
|---|---:|---:|---:|---:|---:|---|
| Pokerai API 直接查询 | 5 | 4–5 | 2，需自行加人格层 | 2–4，视额度 | 4，待独立验证 | 标杆、冷启动、补表 |
| Pokerai + 本地缓存 | 5 | 4–5 | 4，配合人格层 | 5 | 4 | 首选 lookup 路线 |
| deepbot-poker | 3–4 | 2–3 | 4 | 5 | 2–3 | 独立模型型对手 |
| PokerTH 规则 Bot | 3 | 3 | 4 | 5 | 1–2 | 产品和人格参考 |
| PokerData API | 4 | 3 | 2 | 2–3 | 4，限覆盖区 | 翻前数据补充 |
| TexasSolver 线上实时求解 | 5 | 5 | 2 | 1 | 4，限 HU | 不推荐线上运行 |
| TexasSolver 离线表 | 5 | 5 | 4，配合人格层 | 5 | 4，限 HU | 两人 postflop 缓存 |
| equity + 参数化规则 | 4 | 5 | 5 | 5 | 1–2 | 多人底池 fallback |
| Poker GTO Trainer 原表 | 3 | 3 | 2 | 5 | 1–2 | 仅原型参考 |

从这一矩阵看，最符合需求优先级的不是单一资源，而是：

> **高质量基准 lookup + 本地缓存 + 人格变换器 + 概率采样 + 独立策略族 + 低成本多人 fallback。**

---

## 5. 推荐系统架构

```text
牌局状态 / Hand History
          │
          ▼
状态规范化与合法动作层（PokerKit）
          │
          ▼
策略路由器
 ├─ 翻前：本地 6-max / full-ring 范围表
 ├─ 两人 postflop：本地 solver/API 缓存
 ├─ 缓存缺失：受控外部 API 或近邻节点
 ├─ 多人 postflop：range + equity + 规则模型
 └─ 独立模型族：DeepBot / opponent model
          │
          ▼
Bot 人格变换器
 ├─ 范围松紧
 ├─ 主动性 / 诈唬率
 ├─ 跟注与弃牌倾向
 ├─ 下注尺度偏好
 └─ 对玩家的有限适应
          │
          ▼
每手牌隐变量 + 混合策略采样
          │
          ▼
合法性校验、风险限制、执行动作
```

### 5.1 状态规范化

lookup key 不应直接使用完整原始状态，否则缓存几乎无法命中。建议将状态归一为：

- 游戏模式：6-max / 7-max / 9-max；
- 有效筹码桶：20、40、60、100、150、200BB；
- 位置和参与人数；
- preflop action line；
- street、SPR 桶和 pot 类型；
- 牌面 texture；
- hero hand class / combo；
- 历史下注映射到标准尺寸桶。

标准尺寸可先采用：`25% / 33% / 50% / 75% / 100% / 125% / all-in`，再根据节点缩减。

### 5.2 人格变换器

不要为每个人格复制一整套表。可以对基准 logits 做参数化偏移：

```text
profile_logits = base_logits
               + range_bias
               + aggression_bias
               + sizing_bias
               + opponent_adjustment
               + hand_mode_bias
```

再经 softmax 得到合法动作概率。这种方法能保持基准策略的结构，同时制造真实且稳定的风格差异。

建议初始提供六种人格：

| 人格 | 核心差异 | 主要弱点 |
|---|---|---|
| Balanced Reg | 接近基准混合策略，多尺度 | 不明显，作为最高难度 |
| Tight Passive | 入池窄、主动性低、面对压力多弃牌 | 可被频繁偷盲和小注压迫 |
| Calling Station | 入池较宽、跟注多、诈唬少 | 价值下注容易获利 |
| Loose Aggressive | 宽范围、高 3-bet、高 barrel | 容易过度诈唬 |
| Polarized Maniac | 大尺寸和超池多、极化明显 | 中等牌范围保护不足 |
| Adaptive Hunter | 记录玩家统计并有限调整 | 初期样本不足时不稳定 |

允许人格有可利用弱点是合理的，因为本项目将不可剥削性放在第三位；关键是弱点不能退化成一个过于简单、每局都奏效的固定公式。

### 5.3 每手牌隐变量

为每个 Bot 每手牌抽取一次 `hand_mode`，例如：

- 65% 正常；
- 15% 谨慎；
- 15% 施压；
- 5% 非常规。

`hand_mode` 在这一手内持续影响 aggression、bluff 和 sizing，但幅度受人格约束。例如 Tight Passive 的“施压”仍不应比 Maniac 更激进。

这比逐动作加入独立噪声更自然：玩家能感受到对手偶尔换挡，却不会看到同一手牌中毫无逻辑的性格跳变。

### 5.4 随机性的安全边界

为了避免不可预测性严重损害实力，应设置：

- 概率下限裁剪：极差动作若基准频率近零，不因人格噪声突然高频出现；
- EV 容忍带：只在 EV 差距低于阈值的动作之间增加混合；
- 尺度合法集：不允许任意随机筹码数；
- 河牌诈唬预算：按 value/bluff 结构控制；
- 多人底池降诈唬：人数越多，随机进攻幅度越小；
- session 级参数固定：一场内人格稳定，仅允许缓慢适应。

---

## 6. 6-max、7-max 与多人 postflop 的处理

### 6.1 建议把 6-max 设为标准模式

公开数据、训练项目和 API 主要集中在 6-max。首发版本以 6-max 为正式竞技/训练模式，可以显著降低策略映射歧义。

### 6.2 7-max 使用 full-ring 裁剪映射

7-max 可采用从 9-max 删除两个最早位置后的映射，或将位置转换为“距离 BTN 的座位数”。但报告和产品 UI 应注明：

- 翻前属于 full-ring/6-max 的近似映射；
- 不是严格求解的 7-max GTO；
- 玩家离桌后要重新计算位置语义和有效人数。

### 6.3 多人 postflop 不强求 lookup 完整覆盖

三人及以上底池的状态组合远超单挑公开解。建议使用：

1. 根据翻前行动生成各方范围；
2. Monte Carlo 计算对多范围 equity；
3. 加入位置、人数、SPR、牌面湿度和 nut advantage 特征；
4. 通过人格决定下注阈值、尺度和诈唬预算；
5. 只在底池缩减为 heads-up 后切回 lookup，但保留此前范围约束。

这会牺牲一部分不可剥削性，却能以极低成本覆盖完整游戏，并很好地服务于人格多样性。

---

## 7. 成本控制设计

### 7.1 API 不按“每个动作”调用

一桌 6-max 每手可能产生多次 Bot 决策。如果所有行动都走外部 API，免费 1,000 次查询只能支撑很短的练习量。应改为：

- 优先读内存 LRU；
- 未命中读本地持久缓存；
- 仍未命中时查询外部服务；
- 结果经许可后写回缓存；
- 相同规范化节点合并并发请求；
- turn/river 实时求解设置每日或每桌预算；
- 额度耗尽自动降级，不中断牌局。

### 7.2 缓存分层

```text
L1：进程内热点节点，微秒到亚毫秒级
L2：本地 SQLite / LMDB / RocksDB，毫秒级
L3：对象存储中的版本化策略包
L4：外部 API，仅处理未覆盖节点
```

### 7.3 离线优先

最常见的翻前线路、SRP、3-bet pot 和代表性 flop texture 应在发布前预装。线上服务器只进行：

- 查表；
- 少量 equity 模拟；
- 概率变换与采样；
- 对手统计更新。

这些工作不需要 GPU。Monte Carlo 还可以通过较小样本数、向量化 evaluator、结果缓存和决策时间预算控制。

---

## 8. 评测方法

### 8.1 不可预测性指标

不能只凭肉眼判断，建议持续记录以下指标。

#### 条件动作熵

对相同或规范化后的 information set，计算动作分布熵：

```text
H(Action | State, Bot Profile)
```

熵过低说明行为固定；熵过高且集中在低 EV 动作，说明随机性失控。

#### 尺度熵

只对 bet/raise 样本计算尺寸分布和有效尺度数。应按 street、SPR 和人格分别观察，防止全局平均掩盖某个节点永远固定下注。

#### 对手间策略距离

在一组固定测试节点上，用 Jensen–Shannon divergence 比较不同 Bot 的动作分布。距离过低说明“不同人格”只是名称不同。

#### 跨 hand 稳定性

同一人格在长期统计上应保持预设 VPIP、PFR、3-bet、AF 和尺寸偏好；单手有变化，长期仍能被识别为同一种风格。

### 8.2 成本指标

- p50 / p95 / p99 决策延迟；
- 每百手外部 API 请求数；
- L1/L2 缓存命中率；
- 每桌每小时 CPU 时间；
- 每 10,000 手的外部服务成本；
- API 故障下的降级成功率。

### 8.3 不可剥削性指标

- Bot 之间循环联赛的 bb/100；
- 对固定 exploit suite 的最大损失；
- 规则型 best response 的收益；
- 同一策略不同随机种子的置信区间；
- 对松凶、紧弱、跟注站等基准玩家的表现；
- 是否存在只凭下注尺寸即可高精度推断牌力的泄漏。

多人游戏没有简单、廉价、严格的 exploitability 数值，因此应以对抗测试、ablation 和长期模拟共同评估。

---

## 9. 分阶段实施建议

### 阶段一：可玩 MVP

- 6-max cash，固定 100BB；
- PokerKit 或等价规则状态机；
- 本地翻前范围；
- postflop equity + 六种人格规则；
- 动作和尺度概率采样；
- 完整 hand history 与统计埋点；
- 外部 API 仅用于开发期对照。

验收重点：不同 Bot 能被玩家感知为不同风格；相同 Bot 不会在同类节点机械重复。

### 阶段二：策略 lookup 与缓存

- 接入 Pokerai 免费层做小规模验证；
- 建立规范化 key 和多级缓存；
- 预装常见翻前、SRP 和 3-bet 节点；
- 增加 EV 容忍带和安全随机化；
- 引入 deepbot-poker 或自行移植的模型型对手。

验收重点：API 断开后仍可完整对局；常规节点外部请求接近零。

### 阶段三：7–9 人和适应型 Bot

- 增加 full-ring 翻前表与 7-max 位置映射；
- 改进多人范围和 equity；
- Bot 读取玩家 VPIP、PFR、fold-to-cbet、WTSD 等统计；
- 使用有上限的 exploit adjustment，避免短样本剧烈震荡；
- 建立自动联赛与回归评测。

验收重点：扩桌后没有明显位置错误；适应型 Bot 的变化可解释且不会破坏人格一致性。

---

## 10. 风险与待办

1. **数据许可风险**：公开可查看的范围图不代表可以批量抓取、缓存并随产品分发。
2. **“GTO”营销风险**：未提供树配置、范围、下注尺度、收敛误差和验证方法的数据，不应直接标注为 GTO。
3. **6-max 到 7-max 的外推风险**：应明确标注近似策略，避免虚假精确。
4. **多人底池强度风险**：equity 不等于策略价值，必须加入范围、位置和后续行动建模。
5. **随机性泄漏风险**：若先选动作再随意选尺寸，容易产生不平衡的 value/bluff 对应关系。
6. **人格趋同风险**：仅修改 VPIP 不足以产生不同打法，需要同时修改范围、行动和尺寸。
7. **对手建模过拟合**：小样本统计应做贝叶斯平滑或最小样本门槛。
8. **API 单点风险**：所有外部服务都必须有超时、熔断和本地 fallback。

在开始商业开发前，应优先向候选 API 服务确认缓存和产品集成权利，并对所有进入产品的数据保留来源、版本、许可和生成参数记录。

---

## 11. 最终建议

按照“不可预测性 > 运行时成本 > 不可剥削性”的排序，推荐把核心竞争力放在**策略组合系统**，而不是追求单一最强模型：

- 基准 lookup 保证基本合理性；
- 混合频率和多尺寸保证同一对手跨 hand 的变化；
- 人格参数和独立决策族保证不同对手不趋同；
- 每手牌隐变量使随机性有连贯性；
- 离线预计算和本地缓存将运行成本降到普通服务器可承担；
- exploit suite 和回归联赛负责阻止明显漏洞，而不追求昂贵的多人严格均衡。

换言之，本项目最值得构建的并不是“一个 Pluribus”，而是一个能将多种不完美策略组织成**有个性、难以机械预测、成本可控**的 Bot 生态。

## 参考链接

- [Pokerai API](https://github.com/pokerai-bet)
- [PokerData Ranges API](https://pokerdata.io/api)
- [deepbot-poker](https://github.com/tamlhp/deepbot-poker)
- [PokerTH](https://www.pokerth.net/)
- [PokerKit](https://github.com/uoftcprg/pokerkit)
- [OpenSpiel](https://github.com/google-deepmind/open_spiel)
- [TexasSolver](https://github.com/bupticybee/TexasSolver)
- [Poker GTO Trainer](https://github.com/haowenzheng-art/poker-gto-trainer/)
- [CMU：Pluribus 官方介绍](https://www.cs.cmu.edu/news/2019/carnegie-mellon-and-facebook-ai-beats-professionals-six-player-poker)
