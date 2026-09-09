# 德州扑克练习平台

一套可部署在个人云服务器上的中文德州扑克练习平台。CFR/heuristic 负责「怎么打」，DeepSeek 负责「为什么这么打」。

## 文档

- `docs/01-chatgpt-suggestion.md`：技术建议（外部参考）
- `docs/02-requirements-decisions.md`：需求决策
- `docs/03-execution-plan.md`：执行规划总览

## 技术栈

- 后端：Python 3.12+ / FastAPI / Pydantic / SQLAlchemy / SQLite
- 前端：Vue 3 + Vite
- AI：DeepSeek API（仅中文复盘解释）
- 部署：Docker Compose

## 目录结构

```
backend/    # FastAPI 后端（poker / strategy / analysis / llm / storage）
frontend/   # Vue 3 + Vite 前端
tools/      # 离线 CFR 训练工具
docs/       # 需求与规划文档
```

## 快速开始

### 后端

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

### 部署

```bash
docker compose up --build
```

## 质量检查

```bash
# 后端
cd backend && uv run ruff check . && uv run pytest -q

# 前端
cd frontend && npm run build
```
