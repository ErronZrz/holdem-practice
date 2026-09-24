# 文档索引与维护说明

> 本索引记录 `docs/` 的当前归档结构与维护约定。归档只改变文件所在目录，不重命名、不重编号、不改写历史文档内容。

## 当前入口

- [phase6/73a 长期·分层·配对质量框架规格](phase6/73a-m8-long-term-stratified-paired-quality-framework-spec.md)：当前**待裁定**的框架规格（路线裁定为「丙」之后的产物），是本轮唯一入口。
- [phase6/73 v10 后质量框架与路线决策草案](phase6/73-m8-post-v10-quality-framework-and-route-decision-draft.md)：路线决策草案（含甲/乙/丙三选项与后果），已被 `73a` 承接。
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
| [`phase6/`](phase6/) | 55–58n、60–73a | 独立质量验证、可诊断性升级、签收与只读诊断；`73` 起为 v10 后的质量框架与路线决策。 |

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
