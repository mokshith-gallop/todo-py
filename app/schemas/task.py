import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.base import CamelBase
from app.schemas.enums import Priority


class TaskCreate(CamelBase):
    list_id: uuid.UUID
    title: str = Field(min_length=1, max_length=500)
    notes: str | None = Field(default=None, max_length=10_000)
    due_at: datetime | None = None
    priority: Priority = Priority.NONE
    position: float | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title must not be blank")
        return v

    @field_validator("due_at")
    @classmethod
    def due_at_must_be_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("Datetime must include timezone information")
        return v


class TaskResponse(CamelBase):
    id: uuid.UUID
    list_id: uuid.UUID
    title: str
    notes: str | None
    due_at: datetime | None
    priority: Priority
    position: float
    completed_at: datetime | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int
