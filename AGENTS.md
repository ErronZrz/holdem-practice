# AGENTS.md

本文件是面向 AI 编程助手的项目约束与开发约定，编写代码时必须遵守。

## 架构原则（不可违反）

1. `poker/` 不依赖 `api/`，也不依赖 `llm/`。
2. `strategy/` 只能通过 GameState 与 `poker/` 交互。
3. LLM 永远不参与实时牌局合法性判断。
4. 所有随机过程必须可注入 seed。
5. 筹码/金额使用统一数值规范（单一整数单位，避免浮点误差）。
6. 新增扑克规则必须配套单元测试。
7. 公开 API 一律使用 Pydantic model。
8. 引擎结构按 N 人设计，不得写死「恰好 2 人」。

## 目录约定

- `backend/app/poker/`：规则引擎，纯 Python，无 Web 依赖。
- `backend/app/strategy/`：Bot 策略，插件式接口。
- `backend/app/analysis/`：复盘与错误检测。
- `backend/app/llm/`：LLM 适配，仅解释不决策。
- `backend/app/storage/`：持久化。
- `backend/app/api/`：FastAPI 接口。
- `backend/tests/`：pytest 测试。
- `tools/trainer/`：离线 CFR 训练。

## 开发约定

- 后端用 `uv` 管理依赖；提交前运行 `uv run ruff check .` 与 `uv run pytest -q`。
- 前端用 `npm`；提交前运行 `npm run build`。
- 注释用中文说明目的，不堆砌方法名。
