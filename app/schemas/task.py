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
    location_raw: str | None = Field(
        default=None,
        max_length=120,
        description="用户说的地点原文，例如“图书馆”“菜鸟驿站”“东操场”。",
    )

    earliest_start: datetime | None = Field(
        default=None,
        description=(
            "最早可以开始的时间。“14点以后”“下课再去”写在这里。"
        ),
    )
    latest_end: datetime | None = Field(
        default=None,
        description="必须结束的时间。“18点前结束”写在这里。",
    )
    fixed_start: datetime | None = None
    fixed_end: datetime | None = None
    deadline: datetime | None = Field(
        default=None,
        description="任务的截止时刻，例如“晚上10点前取到快递”。",
    )

    flexibility: TaskFlexibility = TaskFlexibility.MOVABLE
    importance: int = Field(default=3, ge=1, le=5)
    preferred_period: str | None = Field(
        default=None,
        max_length=40,
        description=(
            "用户指定的时段，只能是 morning（上午/早上）、"
            "afternoon（下午/中午）、evening（晚上/傍晚）、"
            "day（白天/日间，即不要排到晚上）之一；"
            "用户没有说时段就留空。这是硬约束，规划器不会排到该时段之外。"
        ),
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="必须先完成的任务 id，用于“先……再……”这类顺序。",
    )
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
    # User-saved meal times are hard constraints.  Common meal times that the
    # user has not confirmed are injected separately as soft planning hints.
    meal_windows: list[TimeWindow] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    locked_task_ids: list[str] = Field(default_factory=list)
