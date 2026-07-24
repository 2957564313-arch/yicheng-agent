from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    category: Literal["preference", "habit", "context"] = "preference"
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    value: Any
    enabled: bool = True


class MemoryUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    value: Any | None = None
    enabled: bool | None = None


class MemoryItem(BaseModel):
    id: str
    user_id: str
    category: str
    key: str
    label: str
    value: Any
    enabled: bool
    source: str
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryItem] = Field(default_factory=list)
