import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.base import CamelBase


class ListCreate(CamelBase):
    name: str = Field(min_length=1, max_length=120)
    position: float | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name must not be blank")
        return v


class ListResponse(CamelBase):
    id: uuid.UUID
    name: str
    position: float
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
