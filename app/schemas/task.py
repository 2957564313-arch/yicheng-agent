from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import TaskFlexibility, TimeWindow, TransportMode


class Task(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    date: date
    duration_min: int = Field(ge=5, le=720)

    location_id: str | None = Field(default=None, max_length=100)
    location_raw: str | None = Field(default=None, max_length=120)

    earliest_start: datetime | None = None
    latest_end: datetime | None = None
    fixed_start: datetime | None = None
    fixed_end: datetime | None = None
    deadline: datetime | None = None

    flexibility: TaskFlexibility = TaskFlexibility.MOVABLE
    importance: int = Field(default=3, ge=1, le=5)
    preferred_period: str | None = Field(default=None, max_length=40)
    depends_on: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_time_constraints(self) -> "Task":
        if self.flexibility in {
            TaskFlexibility.FIXED,
            TaskFlexibility.LOCKED,
        }:
            if self.fixed_start is None or self.fixed_end is None:
                raise ValueError(
                    "fixed or locked task requires fixed_start and fixed_end"
                )

        if (self.fixed_start is None) != (self.fixed_end is None):
            raise ValueError("fixed_start and fixed_end must be provided together")

        if self.fixed_start and self.fixed_end:
            if self.fixed_end <= self.fixed_start:
                raise ValueError("fixed_end must be after fixed_start")
            actual_minutes = int(
                (self.fixed_end - self.fixed_start).total_seconds() // 60
            )
            if abs(actual_minutes - self.duration_min) > 1:
                raise ValueError(
                    "duration_min must match fixed_start/fixed_end duration"
                )

        if (
            self.earliest_start is not None
            and self.latest_end is not None
            and self.latest_end <= self.earliest_start
        ):
            raise ValueError("latest_end must be after earliest_start")

        if (
            self.deadline is not None
            and self.earliest_start is not None
            and self.deadline <= self.earliest_start
        ):
            raise ValueError("deadline must be after earliest_start")

        aware_values = [
            value
            for value in (
                self.earliest_start,
                self.latest_end,
                self.fixed_start,
                self.fixed_end,
                self.deadline,
            )
            if value is not None
        ]
        if any(value.tzinfo is None for value in aware_values):
            raise ValueError("all datetimes must include timezone information")
        return self


class UserPreferences(BaseModel):
    buffer_min: int = Field(default=10, ge=0, le=60)
    walking_speed: str = Field(default="normal", pattern="^(slow|normal|fast)$")
    transport_mode: TransportMode = TransportMode.WALK
    avoid_congestion: bool = False
    avoid_rain: bool = True
    avoid_tight_schedule: bool = True
    meal_windows: list[TimeWindow] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    locked_task_ids: list[str] = Field(default_factory=list)
