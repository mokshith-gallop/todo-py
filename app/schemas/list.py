import uuid
from datetime import datetime

from pydantic import Field, field_validator, model_validator

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


class ListUpdate(CamelBase):
    name: str | None = Field(None, min_length=1, max_length=120)
    position: float | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Name must not be blank")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "ListUpdate":
        if self.name is None and self.position is None:
            raise ValueError(
                "At least one of name or position must be provided"
            )
        return self


class ListResponse(CamelBase):
    id: uuid.UUID
    name: str
    position: float
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
