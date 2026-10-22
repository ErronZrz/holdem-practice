"""SQLAlchemy 数据模型：Session、Hand，以及独立的教练解读与追问。

Session 为顶层实体（单用户模式），Hand 挂在 Session 下；每手完整的 Hand History
以 JSON 文本形式存入 ``Hand.history_json``，作为 source of truth。
教练解读和追问另表保存，不改动手牌历史。
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
    # 新建行未写入身份时的产品默认；已落库的旧行保留原值，不做回填。
    bot_strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="mixed-local@14")
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


class CoachExplanationModel(Base):
    """一条决策级教练解读。主键是决策缓存键，同一手的不同决策各自一行。"""

    __tablename__ = "coach_explanations"

    cache_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    hand_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    action_index: Mapped[int] = mapped_column(Integer, nullable=False)
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CoachMessageModel(Base):
    """决策点上的一轮追问。按缓存键挂在初始解读下面，按写入顺序回放。"""

    __tablename__ = "coach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(512), index=True, nullable=False)
    hand_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    action_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
