import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Task(Base):
    __tablename__ = "task"
    __table_args__ = (
        ForeignKeyConstraint(
            ["list_id", "user_id"],
            ["task_list.id", "task_list.user_id"],
            name="fk_task_list_same_owner",
        ),
        CheckConstraint(
            "char_length(trim(title)) > 0",
            name="ck_task_title_not_blank",
        ),
        CheckConstraint(
            "priority IN ('none', 'low', 'med', 'high')",
            name="ck_task_priority",
        ),
        Index(
            "ix_task_list_position",
            "list_id",
            "position",
            postgresql_where="deleted_at IS NULL",
        ),
        Index("ix_task_user", "user_id"),
        Index(
            "ix_task_purge",
            "deleted_at",
            postgresql_where="deleted_at IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=func.gen_random_uuid()
    )
    list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_list.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        String(4), nullable=False, server_default="none"
    )
    position: Mapped[float] = mapped_column(Float, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )

    # Relationships with lazy="raise" to prevent accidental lazy loading in async
    task_list = relationship(
        "TaskList", foreign_keys=[list_id], lazy="raise"
    )
    user = relationship("User", foreign_keys=[user_id], lazy="raise")
