FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# 复制项目全部内容（依赖清单、锁文件与应用源码）
COPY . .

# 仅安装运行时依赖，并安装项目本身
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
