from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(title="德州扑克练习平台 API", version="0.1.0")
app.include_router(health_router)
