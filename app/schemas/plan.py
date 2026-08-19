from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import DataSource, Issue, PlanStatus


class PlanItem(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    task_id: str | None = Field(default=None, max_length=64)
    item_type: str = Field(pattern="^(task|travel|buffer|meal)$")
    title: str = Field(min_length=1, max_length=160)
    start_at: datetime
    end_at: datetime
    location_id: str | None = Field(default=None, max_length=100)
    location_raw: str | None = Field(default=None, max_length=120)
    locked: bool = False
    source: DataSource = DataSource.STRUCTURED
    reason: str | None = Field(default=None, max_length=500)
    travel_mode: str | None = Field(
        default=None,
        pattern="^(walk|bicycle|electrobike)$",
    )
    base_duration_min: int | None = Field(default=None, ge=0, le=240)
    congestion_delay_min: int = Field(default=0, ge=0, le=120)

    @model_validator(mode="after")
    def validate_interval(self) -> PlanItem:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("plan item datetimes must include timezone")
        if self.end_at <= self.start_at:
            raise ValueError("plan item end_at must be after start_at")
        return self


class PlanMetrics(BaseModel):
    hard_violation_count: int = Field(default=0, ge=0)
    scheduled_task_count: int = Field(default=0, ge=0)
    requested_task_count: int = Field(default=0, ge=0)
    travel_minutes: int = Field(default=0, ge=0)
    buffer_minutes: int = Field(default=0, ge=0)
    moved_task_count: int = Field(default=0, ge=0)
    total_shift_minutes: int = Field(default=0, ge=0)
    preservation_rate: float | None = Field(default=None, ge=0, le=1)
    score: float = 0


class Plan(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    user_id: str = Field(min_length=1, max_length=64)
    thread_id: str = Field(min_length=1, max_length=128)
    date: date
    status: PlanStatus
    version: int = Field(default=1, ge=1)
    items: list[PlanItem]
    warnings: list[Issue] = Field(default_factory=list)
    metrics: PlanMetrics = Field(default_factory=PlanMetrics)
    created_at: datetime

    @model_validator(mode="after")
    def validate_created_at(self) -> Plan:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must include timezone")
        self.items = sorted(
            self.items,
            key=lambda item: (item.start_at, item.end_at, item.id),
        )
        return self


class DataFreshness(BaseModel):
    route: DataSource = DataSource.UNKNOWN
    weather: DataSource = DataSource.UNKNOWN
    knowledge: DataSource = DataSource.UNKNOWN
