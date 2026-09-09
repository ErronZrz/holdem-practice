from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.games import router as games_router
from app.api.hands import router as hands_router
from app.api.health import router as health_router
from app.storage.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="德州扑克练习平台 API", version="0.1.0", lifespan=lifespan)

# 本地单用户应用，允许跨域以支持前端直连调试。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(games_router)
app.include_router(hands_router)
