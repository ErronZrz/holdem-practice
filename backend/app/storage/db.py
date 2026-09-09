"""SQLite 连接与会话管理。

数据库路径可由环境变量 ``HOLDEM_DB_PATH`` 覆盖，默认落在 ``backend/data/holdem.db``。
"""

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def _default_db_path() -> str:
    env = os.environ.get("HOLDEM_DB_PATH")
    if env:
        return env
    return str(Path(__file__).resolve().parents[2] / "data" / "holdem.db")


def init_db(path: str | None = None) -> None:
    """初始化引擎并建表；重复调用会重建连接（供测试切换临时库）。"""
    global _engine, _session_factory
    db_path = path or _default_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：提供请求级数据库会话。"""
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    db = _session_factory()
    try:
        yield db
    finally:
        db.close()
