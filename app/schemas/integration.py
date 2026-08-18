from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from app.schemas.agenda import AgendaKind


class ExternalEventUpsert(BaseModel):
    source_system: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=64)
    external_event_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    start_at: datetime
    end_at: datetime
    location_name: str | None = Field(default=None, max_length=160)
    kind: AgendaKind = "activity"
    notes: str | None = Field(default=None, max_length=500)
    source_url: HttpUrl | None = None

    @field_validator("source_system")
    @classmethod
    def normalize_source_system(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_interval(self) -> "ExternalEventUpsert":
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("外部日程时间必须包含时区")
        if self.end_at <= self.start_at:
            raise ValueError("外部日程结束时间必须晚于开始时间")
        if (self.end_at - self.start_at).total_seconds() > 60 * 60 * 12:
            raise ValueError("单个外部日程不能持续超过12小时")
        return self


class ExternalEventResponse(BaseModel):
    id: str
    source_system: str
    external_event_id: str
    user_id: str
    title: str
    start_at: datetime
    end_at: datetime
    location_name: str | None = None
    kind: AgendaKind
    notes: str | None = None
    source_url: str | None = None
    status: Literal["active", "cancelled"]
    created_at: datetime
    updated_at: datetime
    operation: Literal["created", "updated", "unchanged", "cancelled"]


class IntegrationCapabilities(BaseModel):
    api_version: str = "2026-08-18"
    authentication: str = "X-Yicheng-Integration-Key"
    operations: list[str] = Field(
        default_factory=lambda: ["upsert_event", "cancel_event"]
    )
    idempotency: str = "source_system + external_event_id + user_id"
