# 文档索引与维护说明

> 本索引记录 `docs/` 的当前归档结构与维护约定。归档只改变文件所在目录，不重命名、不重编号、不改写历史文档内容。

## 当前入口

- [phase6/73f `73` 战役关闭记录（未冻结）](phase6/73f-m8-campaign-closure-without-framework-freeze-record.md)：当前入口；在 `73b` 保持未冻结的前提下关闭 `73`，`73` 后缀不得续用；**不等于冻结、运行或质量结论**。
- [phase6/73e R2 保守路径冻结尝试终止与路线处置记录](phase6/73e-m8-r2-freeze-attempt-termination-and-route-disposition-record.md)：登记 `R2 + V_max = M²` 路径不能作为当前 `73b` 的可冻结路线，**不等于冻结、运行或质量结论**。
- [phase6/73d R2 上界、样本量与清单准备计算记录](phase6/73d-m8-r2-bound-sample-and-manifest-preparation-record.md)：记录基于既有裁定的解析计算与准备方案，其 R2 保守路径已由 `73e` 登记为不可冻结；**不等于冻结、运行或质量结论**。
- [phase6/73c 剩余冻结项裁定记录](phase6/73c-m8-remaining-freeze-items-adjudication-record.md)：记录 `73b` 的部分剩余冻结项裁定，**不等于冻结、运行或质量结论**。
- [phase6/73b 长期·分层·配对框架预注册草案（修订版）](phase6/73b-m8-long-term-stratified-paired-framework-preregistration-draft.md)：未冻结的框架预注册草案（统计对象 / 基线池 / 主判层 / 功效依据 / 状态机 / 口径角色）。
- [phase6/73a 长期·分层·配对质量框架规格](phase6/73a-m8-long-term-stratified-paired-quality-framework-spec.md)：框架规格（路线裁定为「丙」之后的产物）。
- [phase6/73 v10 后质量框架与路线决策草案](phase6/73-m8-post-v10-quality-framework-and-route-decision-draft.md)：路线决策草案（含甲/乙/丙三选项与后果），已被 `73a` / `73b` / `73c` / `73d` / `73e` / `73f` 承接；该战役已由 `73f` 在未冻结前提下关闭，根编号 `73` 不再续号。
- [59 当前成果诊断与后续工作边界](59-current-outcome-diagnosis-and-work-boundaries.md)：当前 Bot 路线的判断、证据边界与后续工作护栏。
- [项目总说明](../README.md)：项目运行、开发与产品入口。

## 阶段归档

| 目录 | 编号范围 | 内容 |
| --- | --- | --- |
| [`phase1/`](phase1/) | 01–19 | 项目发现、需求决策、核心牌局、基础 Bot、前端与复盘能力。 |
| [`phase2/`](phase2/) | 20–25 | 对手模拟路线、多人权益与边池前置核验、Kuhn CFR 工具链。 |
| [`phase3/`](phase3/) | 26–35a | M8 多人 CFR Candidate A 的可行性、实现、运行、冻结与收尾。 |
| [`phase4/`](phase4/) | 36–51c | M8 生产接入前置、策略契约、性能、规则边界与 N=9 范围决策。 |
| [`phase5/`](phase5/) | 52–54m | 完整本地 Bot 路线、策略身份与规则标定交付。 |
| [`phase6/`](phase6/) | 55–58n、60–73f | 独立质量验证、可诊断性升级、签收与只读诊断；`73` 起为 v10 后的质量框架与路线决策，该战役已由 `73f` 在未冻结前提下关闭。 |

## 推荐阅读顺序

1. 需要了解项目起点与原始约束时，阅读 [`phase1/02-requirements-decisions.md`](phase1/02-requirements-decisions.md) 与 [`phase1/03-execution-plan.md`](phase1/03-execution-plan.md)。
2. 需要了解对手能力与 CFR 的边界时，阅读 [`phase2/20-opponent-simulation-roadmap.md`](phase2/20-opponent-simulation-roadmap.md)、[`phase2/25-m7-kuhn-cfr-toolchain.md`](phase2/25-m7-kuhn-cfr-toolchain.md) 和 `phase3/` 的收尾记录。
3. 需要了解当前完整 Bot 实现时，阅读 [`phase5/53-m8-full-bot-opponent-route-and-first-delivery-draft.md`](phase5/53-m8-full-bot-opponent-route-and-first-delivery-draft.md) 与 [`phase5/53c-m8-quality-sign-off-record.md`](phase5/53c-m8-quality-sign-off-record.md)。
4. 需要了解当前质量结论与下一步边界时，按 [`phase6/57k-m8-third-verification-criteria-judgment-and-signoff-record.md`](phase6/57k-m8-third-verification-criteria-judgment-and-signoff-record.md)、[`phase6/57m-m8-l4-negative-difference-read-only-diagnostic-record.md`](phase6/57m-m8-l4-negative-difference-read-only-diagnostic-record.md)、[`phase6/58-m8-fourth-independent-quality-verification-preregistration-draft.md`](phase6/58-m8-fourth-independent-quality-verification-preregistration-draft.md)、[59](59-current-outcome-diagnosis-and-work-boundaries.md) 的顺序阅读。

## 维护约定

- 编号分两层：`phase` 只表示**宏观归档阶段**，不表示单次验证战役编号；文档编号由**战役根编号 + 小写字母后缀**构成。
- 每个新的路线决策、策略身份研发或独立验证战役使用**未占用的下一个整数根编号**；该战役内部的规格、实施、清单、运行、签收、勘误与只读补记才使用同一根编号的字母后缀（如 `73`、`73a`、`73b`）。
- 根编号**专属一个战役**；已关闭战役的根编号**不得复用，也不得续号**。
- 每份新根文档头部固定写明三项：**战役归属**、**历史关系**、**编号范围**。
- 本索引随编号范围变化同步更新；存量历史文档的正文与历史路径**不改写、不重编号、不移动**。
- 早期「新文档沿用连续编号」的约定，自 2026-09-24 起由上面的「根编号 = 一个战役」约定取代；`55`–`72` 等存量编号即该早期约定的产物，**不重编号**。
- 新文档按其**首次形成时的工作阶段**归档；当前状态总结、跨阶段索引和未来路线诊断可保留在 `docs/` 顶层。
- 同一编号族的规格、实施记录、运行回执、判定与补记必须放在同一阶段目录，不按文档类型拆分。
- 已归档文档是历史记录。除明确要求纠错外，不为修复过期路径、改写历史命令输出或追溯更新当时结论而修改其正文。
- 新文档应链接到当前归档路径；旧文档中的历史路径保留原样。本索引是旧路径迁移后的导航入口。
- 形成新的质量结论前，应先区分开发证据、独立验证证据与只读诊断，避免互相替代。

## 归档记录

- 2026-09-23：将原本平铺在 `docs/` 顶层的 01–58 号文档按六个阶段归档；文件名、编号、正文和历史引用均保持不变。
- 2026-09-23：新增 59 号当前成果诊断文档，作为后续策略研发与质量验证的工作边界参考。
- 2026-09-24：第五次独立验证战役（根编号 `58`）闭环于「质量未获支持」，其根编号**关闭**，不再续号。
- 2026-09-24：新增 `phase6/73` 号「v10 后质量框架与路线决策草案」，并据此把 `phase6/` 的编号范围更新为 `55–58n、60–73`；同时把「根编号 = 一个战役」的编号约定写入本索引。存量文档正文与历史路径未改动。
- 2026-09-24：路线裁定为「丙」，新增 `phase6/73a` 号「长期·分层·配对质量框架规格」；`phase6/` 编号范围相应更新为 `55–58n、60–73a`。
- 2026-09-24：新增 `phase6/73b` 号「长期·分层·配对框架预注册草案」；`phase6/` 编号范围更新为 `55–58n、60–73b`。同时确立：`73` 战役在框架冻结后关闭，**新身份改造与新验证另开根编号 `74`**，不使用 `73c`。
- 2026-09-24：`73b` 首次审查未通过（三项阻断性问题 + 两项必写清项），**就地修订同编号 `73b`**（未新建文档、未创建 `73c`）：更正方差依据、基线池选择偏差与成本状态映射，补充归一化与截断规则及风险预算 / MDE 的独立定义。`phase6/` 编号范围不变（`55–58n、60–73b`）。
- 2026-09-24：在 `73` 未关闭期间，经单独裁定新增 `phase6/73c` 号「剩余冻结项裁定记录」，只记录 `73b` 的部分冻结项取值与边界，不构成冻结、运行、实现或新开 `74` 的授权；`phase6/` 编号范围更新为 `55–58n、60–73c`。
- 2026-09-24：在 `73` 未关闭期间，经单独授权新增 `phase6/73d` 号「R2 上界、样本量与清单准备计算记录」，仅基于既有裁定与 `73b` 公式作解析代入、准备方案和可达性 / 包络登记；未生成或冻结清单、seed、节点、`code_identity`，不构成运行、实现、关闭 `73` 或新开 `74` 的授权；`phase6/` 编号范围更新为 `55–58n、60–73d`。
- 2026-09-24：在 `73` 未关闭期间，经单独裁定新增 `phase6/73e` 号「R2 保守路径冻结尝试终止与路线处置记录」，只登记 `R2 + V_max = M²` 路径不能作为当前 `73b` 的可冻结路线，并终止该路径上的 `73` 冻结尝试；不否决 `73b` 的框架性内容、不主张关闭 `73`、不开启 `74`，也不构成运行、实现、清单冻结或提交推送的授权；`phase6/` 编号范围更新为 `55–58n、60–73e`。
- 2026-09-24：经单独裁定新增 `phase6/73f` 号「未冻结前提下的 `73` 战役关闭记录」，在 `73b` 保持未冻结（其 §11.1 必要冻结项仍为 `28` 项、未齐备）的前提下关闭 `73`，并明确 `73` 后缀不得续用；原「框架冻结后关闭」条件未满足，其索引字面不改写、由 `73f` 声明取代。新身份改造与新验证另开根编号 `74`（未授权、未开启）；`phase6/` 编号范围更新为 `55–58n、60–73f`。
