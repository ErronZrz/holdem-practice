# 52a M8：策略来源调研的工程复核与下一路线建议（待裁定，不实施）

> 日期：2026-09-20。
>
> 本文件接在 `docs/52`（策略来源与技术路线调研）之后，沿用 `docs/30` D6 的编号族约定：`docs/52` 记录外部调研原文，本文件只记录**对它的工程复核、与既有硬约束的冲突清单、以及一条待裁定的下一步路线建议**。
>
> 编号说明：本轮原定用 `52` 作为规格冻结文档；该编号已被调研占用，因此**规格冻结顺延为 `docs/53`（回执为 `53a`）**，本文件作为调研的配套记录占用 `52a`。
>
> 本文**不实施任何代码、不启动任何运行、不消耗任何实验预算、不新建 campaign、不追加 seed**，也不改变任何既有行为。

## 1. 用户答复原文

本文件所依据的两项裁定，答复原文如下：

| 待决项 | 用户答复原文 |
|---|---|
| 是否把 `docs/52` 定位为「调研留档 + 冲突清单」，并把实施路线改为「L1 锚点起步」 | 「Q1: 同意。」 |
| 是否把 L2（本机自产单挑 postflop 查表）现在就列进规格范围 | 「Q2: 先不列。」 |

并附一句范围约束（原文）：「我希望把你的建议也先写入到一份文档中，编号可以是 53 或者 52a，但是先不做任何实际动作。」

## 2. 本轮基线核验（只读）

```text
$ git status --short --branch
## master...origin/master [ahead 12]

$ git status --porcelain=v1 --untracked-files=all | wc -l
1            # 仅 docs/52-chatgpt-survey.md（未入库）

$ git rev-parse HEAD
bced56e415ca5e7f90e8659f32cbb5acdcd35035

$ git rev-parse origin/master
133c99cbf541e9bf49d1f5f2e795ca6585e91d8d

$ ls -1 /Users/bryanylliu/holdem-campaigns/ | wc -l            # 10
$ find /Users/bryanylliu/holdem-campaigns -name strategy.json | wc -l   # 16
$ find /Users/bryanylliu/holdem-campaigns -name measurement.json | wc -l # 19
$ ls -1 backend/app/strategy/*.py | wc -l                      # 14
$ ls -1 backend/tests/test_*.py | wc -l                        # 28
$ ls -1 tools/trainer/src/multiplayer_cfr/*.py | wc -l         # 27
$ ls -1 tools/trainer/tests/test_*.py | wc -l                  # 25
```

测试基线（本轮开始前实测）：

```text
backend:       uv run ruff check .  -> All checks passed!
               uv run pytest -q     -> 668 passed, 2 skipped
tools/trainer: uv run ruff check .  -> All checks passed!
               uv run pytest -q     -> 227 passed
```

工作区干净（除调研文件外）；未做任何 `reset` / `clean` / `stash` / `checkout`；本轮提交与推送由用户明确授权执行。

## 3. 对外部资源的独立核验结论

对 `docs/52` §3 列出的资源做了独立核验（不采信转述），结论如下。

| 资源 | 核验结论 | 能否直接使用 | 关键前提 / 冲突 |
|---|---|---|---|
| Pokerai API | 真实存在：`github.com/pokerai-bet`、`pokerai.bet/docs`、PyPI 客户端 `pokerai-bet`；自述翻前/翻牌来自预解、转牌/河牌实时求解，**仅 6-max** | 否（最接近） | 在线依赖；「solver-grade」为服务方自述、无独立基准；无 7/9-max；额度、条款与长期存储许可未确认 |
| deepbot-poker | 仓库真实存在且 2024 年仍有提交；依赖两个被修改过的 fork（`PyPokerEngine`、`OMPEval`）作为 submodule；定位 6 人 SNG | 否 | 现代化成本高；6-SNG 目标不等于 100BB cash；不能直接处理 7 人输入；与后端是两套规则 |
| TexasSolver | 真实、活跃；**AGPL-3.0**，官网明确「个人版免费，商用请联系作者」 | 仅可作离线工具 | 商用需单独授权；求解**产物**随产品分发是否触发 AGPL 义务需法务判断；只做两人 postflop |
| PokerKit | 真实、活跃（0.7.x），规则与牌力库质量高 | 部分 | **不应替换线上引擎**：后端 `backend/app/poker/**` 已实现 2–9 人、结算语义、测试与只读边界，引入第二规则引擎会产生双重真理源 |
| OpenSpiel | 真实，含 CFR / Deep CFR / best-response 与 2–10 人通用扑克 | 部分是 | 不附带强权重、不适合线上引擎；但**适合做本机训练与评测底座**——`docs/52` 未覆盖这一用法 |
| PokerData Ranges API | 存在，翻前数据较丰富、postflop 仅单挑；正式方案付费 | 否 | 付费；只覆盖 6-max 口径，不能视为 7-max 策略 |
| PokerTH / Poker GTO Trainer | 存在 | 否 | AGPL / 数据来源粗粒度；仅可借鉴产品形态与接口结构 |
| Pluribus | 论文级成果，**代码与权重从未公开发布**；蓝图约 12,400 CPU-core-hours | 否 | 只能作为基准引用 |

**结论一**：不存在可直接拿来充当「2–9 人、全街、可部署、许可干净」强策略的现成方案；市面上的东西都是**部件**，且各自带许可、兼容或可复现性前提。

## 4. `docs/52` 与本项目既有硬约束的冲突清单

以下 7 处冲突必须先裁定，不能照搬调研结论。

| # | `docs/52` 的主张 | 冲突的既有约束 | 处置建议 |
|---|---|---|---|
| 1 | PokerKit 承载 2–9 人规则与状态 | `backend/app/poker/**` 只读；`AGENTS.md` 架构原则 1、6 | 不替换线上引擎；至多用于训练侧参考，并用测试锁定与引擎的等价性 |
| 2 | 在线 API 参与决策路径 | 「所有随机过程必须可注入 seed」；离线可复现要求 | 仅离线补表与对照，禁止进入运行时路径 |
| 3 | 多级缓存 / 人格统计的持久化 | `backend/app/storage/models.py` 不加列、不迁移 | 缓存与统计只落文件或内存（工作树之外） |
| 4 | 人格参数偏移 base logits | `heuristic.py` 的决策语义是不可回退边界 | 人格层另起实现；不得改 heuristic 的阈值常量 |
| 5 | 难度分层与人格呈现（UI） | 不得恢复已移除的前端策略选择器 | 需要单独裁定新的 UI 入口，或先不做 UI |
| 6 | 阶段二/三含大规模离线求解与外部额度 | 累计本机实测预算 54.72 min，不得扩预算 | 新预算须逐轮按实测锚点配置并如实披露 |
| 7 | AGPL 部件（TexasSolver / PokerTH） | 产品化与许可合规 | 许可前置确认，不得当作「免费部件」 |

## 5. 本机可行路线的建议（L0–L4）

### 5.1 先把目标拆成可度量的子目标

「够强且不易针对」应拆成可检验指标，拆开之后可见**大规模 CFR 并非必需**：

| 子目标 | 可度量指标 | 需要整局 CFR 吗 |
|---|---|---|
| 不可预测 | 条件动作熵、尺度熵、人格间 JS 距离 | 否，只需概率采样 + 人格/每手隐变量 |
| 不易针对 | 本地 best-response / exploit suite 的 bb/100 损失 | 否，只需**对固定对手**求最优反应 |
| 基本合理 | 与关键锚点解的一致性、与外部图表的对照 | 否，只需小规模精确求解 |
| 不退化 | EV 容忍带、概率下限裁剪、多人降诈唬 | 否 |

### 5.2 阶梯

| 层级 | 内容 | 本机成本 | 达成什么 |
|---|---|---|---|
| L0 | equity + 声明式规则 + 概率采样 + 人格 / 每手隐变量 | 约 0 | 不可预测性高、成本极低 |
| **L1 锚点（推荐起步）** | **真实规则下的自终止子博弈精确解**：单挑与多人翻前全下-弃牌；翻后单街「全下或弃牌」 | 分钟级 | 可复算、**可外部交叉验证**的答案表 |
| L2 声明式抽象 CFR | 真实规则 + 牌抽象（169 起手牌类 / 牌面 bucket）+ 下注抽象（少数尺寸）+ SPR 桶 | 单挑全街小时级；3–6 人仅局部「范围 vs 范围」单街 | 两人底池 postflop 查表；**本轮不列入范围** |
| L3 蒸馏 | 把 L1/L2 产物与 L0 约束蒸成小模型或查表，补多人场景 | 天级，可选 | 多人场景一致性 |
| L4 完整 6-max GTO | 全街全下注树的均衡 | **不可行**（Pluribus 约 12,400 CPU-core-hours） | — |

### 5.3 抽象维度的教训（上一轮的根因）

CFR 的成败不在轮数，而在**抽象维度是否选对**：

- 错误抽象：把两张底牌压成单一 `rank`、把多街压成单街——信息被毁，产物对真实决策点无意义（`m8-unique-rank-single-open` 即属此类）；
- 正确抽象：**保留真实信息结构**（真实牌、真实街、真实筹码），只在牌力等价类、下注尺寸、SPR 桶上聚合。信息损失小且可量化。

### 5.4 兼容性说明（易被误读的一点）

「概率采样」与硬约束「所有随机过程必须可注入 seed」**不冲突**：采样取自可注入 seed 的随机源，因此同一 seed 与同一局面必然得到同一动作，确定性纪律不被破坏。

## 6. 推荐结论

1. `docs/52` 降级为**资源与架构调研（已核验）**，不作为实施蓝图；§4 的 7 处冲突在规格中逐条裁定。
2. 不以「训练一个强 6-max bot」为目标，改为「**锚点表 + 人格/混合层 + 本地 exploit 回归**」。
3. 训练侧的起步交付为 **L1 锚点**（示例：单挑翻前全下/弃牌精确解表），它同时提供可复算、可外部验证与可计算的 EV 损失。
4. **L2 本轮不列入范围**（用户裁定「先不列」）；待 L1 闭环并跑通评测后，再按同一口径决定是否引入。
5. 规格冻结使用 `docs/53`（回执 `53a`）。

## 7. 支撑本节的只读观测（现有基线）

为回答「路线落地后相对现有基线有何提升」，本轮做了一次**只读**诊断：按单挑、大盲 10、分别取 1000 / 200 / 150 / 100 起始筹码各 600 手，统计 `HeuristicStrategy` 的翻前决策。结果为（四档筹码的计数**逐项相同**）：

| 起始筹码 | 小盲弃牌 | 小盲跛入 | 小盲加注 | 小盲全下 | 加注到 | 大盲面对加注 | 大盲面对跛入 |
|---|---|---|---|---|---|---|---|
| 1000（100 BB） | 328 | 265 | 13 | 0 | 恒 2.5 BB | 5 跟 / 8 弃 | 253 过牌 / 6 加注 |
| 200（20 BB） | 330 | 263 | 13 | 0 | 恒 2.5 BB | 5 跟 / 8 弃 | 253 过牌 / 6 加注 |
| 150（15 BB） | 330 | 263 | 13 | 0 | 恒 2.5 BB | 5 跟 / 8 弃 | 253 过牌 / 6 加注 |
| 100（10 BB） | 330 | 263 | 13 | 0 | 恒 2.5 BB | 5 跟 / 8 弃 | 253 过牌 / 6 加注 |

三点结构性事实（成因可追溯到 `backend/app/strategy/heuristic.py` 的翻前判据）：

1. **对筹码深度完全不敏感**：10 BB 与 100 BB 的行为逐项相同；
2. **小盲从不全下**：约 55% 弃牌、44% 跛入、2% 加注到固定 2.5 BB；
3. **大盲几乎不惩罚跛入**：面对跛入约 97.7% 只是过牌。

口径声明：这是**本机单次观测、非预注册**，仅用于说明基线的形态，不得作为验收证据或外推依据。诊断脚本为一次性脚本，未入库；为便于复核，其全文见附录 A。

## 8. 不得声称

- 不得把 `docs/52` 的资源清单表述为「已验证可用的现成方案」；其中多数只经过**存在性与许可**层面的核验，策略强度一律未经独立验证；
- 不得把第 7 节的观测表述为预注册实验、质量证据或既成结论；
- 不得把本文的建议表述为已授权实施；本文**零代码改动**；
- 不得把 L1 锚点解的适用范围外推到全局面；不得把受限子博弈的结论表述为真实牌局 EV、GTO、均衡或生产可用策略；
- 不得把「本机自产」表述为「已达到商用级强度」。

## 9. 未做事项与下一步

未做：

- 未写任何代码、未改任何测试、未改锁文件、未碰真实数据库；
- 未启动任何受监督运行、未新建 campaign、未追加 seed、未重试任何已消耗 authorization、未消耗实验预算；
- 未引入任何外部依赖；未上云、未转 GPU、未扩预算；
- 未修改 `docs/20` 至 `docs/52`。

下一步唯一建议动作：**在新对话中继续确认路线**（以本文件与 `docs/52` 为输入），确认后再冻结 `docs/53` 规格、再实施；规格与实现分两次提交。

## 附录 A：第 7 节所用的一次性只读诊断脚本

脚本为一次性诊断，按既有惯例置于工作树之外、未入库；以下为其全文，供复核。

```python
"""只读诊断：量化 heuristic@1 在单挑翻前的实际行为（不写库、不改代码）。"""

import sys
from collections import Counter

sys.path.insert(0, ".")

from app.poker.actions import ActionType
from app.poker.engine import PokerEngine
from app.strategy.heuristic import _chen_score, HeuristicStrategy
from app.strategy.projection import project_for_actor

HANDS = 600


def run(stack, big_blind=10):
    """按单挑跑若干手，统计翻前各类决策。"""
    sb = big_blind // 2
    sb_action = Counter()
    sb_jam = 0
    sb_raise_to = Counter()
    bb_facing_raise = Counter()
    bb_limp_response = Counter()
    for seed in range(HANDS):
        engine = PokerEngine(2, sb, big_blind, stack, seed=seed)
        engine.start_hand()
        bot = HeuristicStrategy(seed=seed)
        guard = 0
        while not engine.hand_over and guard < 30:
            guard += 1
            state = project_for_actor(engine.snapshot())
            if state.street.name.lower() != "preflop":
                break
            legal = engine.legal_actions()
            rel = (engine.current_seat - engine.button) % 2
            facing = legal.call_amount > 0
            me = state.players[state.current_seat]
            action = bot.choose_action(state, legal)
            if rel == 0:
                sb_action[action.type.name] += 1
                if action.type in (ActionType.BET, ActionType.RAISE):
                    sb_raise_to[action.amount] += 1
                    if action.amount >= me.stack + me.street_bet:
                        sb_jam += 1
            elif facing:
                bb_facing_raise[action.type.name] += 1
            else:
                bb_limp_response[action.type.name] += 1
            engine.apply_action(action)
    return dict(
        sb_action=dict(sb_action),
        sb_jam=sb_jam,
        sb_raise_to=sb_raise_to,
        bb_facing=dict(bb_facing_raise),
        bb_limp=dict(bb_limp_response),
    )
```

## 附录 B：`docs/52` 的可采信部分

调研中判断正确、可直接沿用的部分（本节为唯一保留意见）：

- §2 的需求三角工程化定义，特别是把「不可预测性」拆成「跨手动作多样性 / 下注尺度多样性 / 对手间差异」三维；
- §5.2 人格变换器与 §5.3 每手隐变量的设计思路（在项目中的落点需按 §4 冲突 4、5 另行裁定）；
- §5.4 随机性的安全边界（概率下限裁剪、EV 容忍带、尺度合法集、多人降诈唬）；
- §8 的评测指标族（条件动作熵、尺度熵、人格间 JS 距离、跨手稳定性、exploit suite 损失）。

上述内容与本文 §5.1 的子目标拆分一致，可作为 `docs/53` 规格的输入。
