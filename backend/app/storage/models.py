"""SQLAlchemy 数据模型：Session 与 Hand。

Session 为顶层实体（单用户模式），Hand 挂在 Session 下；每手完整的 Hand History
以 JSON 文本形式存入 ``Hand.history_json``，作为 source of truth。
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """返回当前 UTC 时间的 naive datetime（与 SQLite 存储保持一致）。"""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    """所有模型的声明式基类。"""


class SessionModel(Base):
    """一次练习对局（有限手数 + 输光自动补码）。"""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    num_players: Mapped[int] = mapped_column(Integer, nullable=False)
    human_seat: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    small_blind: Mapped[int] = mapped_column(Integer, nullable=False)
    big_blind: Mapped[int] = mapped_column(Integer, nullable=False)
    starting_stack: Mapped[int] = mapped_column(Integer, nullable=False)
    # 0 表示不限手数（对局不会自动结束）。
    target_hands: Mapped[int] = mapped_column(Integer, nullable=False)
    hands_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_chips: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 版本化策略标识（受控注册表的规范形态）；旧行保留其历史取值，不做回填。
    bot_strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="heuristic@1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    hands: Mapped[list["HandModel"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class HandModel(Base):
    """一手牌的持久化记录；完整历史见 ``history_json``。"""

    __tablename__ = "hands"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id"), index=True, nullable=False
    )
    hand_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    net: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    history_json: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped[SessionModel] = relationship(back_populates="hands")
