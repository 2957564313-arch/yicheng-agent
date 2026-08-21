from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import TaskFlexibility, TimeWindow, TransportMode


class Task(BaseModel):
    # Reject unknown fields. A misspelled or not-yet-supported constraint used
    # to be dropped in silence, so a request the model had understood
    # correctly reached the planner with the constraint missing.
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    date: date
    # The length to aim for. ``min_duration_min`` says how far it may be cut
    # when the day cannot hold every task at full length; without it a task
    # that does not fit is simply dropped, which is never what a student wants.
    duration_min: int = Field(
        ge=5,
        le=720,
        description="这次任务的理想时长（分钟）。",
    )
    min_duration_min: int | None = Field(
        default=None,
        ge=5,
        le=720,
        description=(
            "排不下时可以压缩到的最短时长；不填表示时长不可压缩。"
            "例如“自习”理想120分钟、最短60分钟。"
        ),
    )
    max_duration_min: int | None = Field(
        default=None,
        ge=5,
        le=720,
        description="时间充裕时可以延长到的最长时长。",
    )
    occurrence_count: int = Field(
        default=1,
        ge=1,
        le=12,
        description=(
            "用户要求这件事今天做几次。“自习3次”写 3，规划器会生成 3 个独立任务。"
        ),
    )
    splittable: bool = Field(
        default=False,
        description="这次任务本身可否再拆成几段完成。",
    )
    min_gap_min: int = Field(
        default=0,
        ge=0,
        le=720,
        description="与同类任务之间至少间隔的分钟数。",
    )
    duration_source: Literal["explicit", "default"] = Field(
        default="default",
        description=(
            "explicit=用户明确说了时长，不可压缩；"
            "default=系统按常识填的默认值，可压缩。"
        ),
    )
    constraint_source: Literal["user", "model", "memory", "rule"] = Field(
        default="model",
        description=(
            "时段等约束的来源。user=用户本轮明确说的，是硬约束；"
            "model/memory=推断出来的，只作为偏好，不能因此丢任务。"
        ),
    )

    location_id: str | None = Field(default=None, max_length=100)
    location_raw: str | None = Field(
        default=None,
        max_length=120,
        description="用户说的地点原文，例如“图书馆”“菜鸟驿站”“东操场”。",
    )

    earliest_start: datetime | None = Field(
        default=None,
        description=("最早可以开始的时间。“14点以后”“下课再去”写在这里。"),
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

    @property
    def preferred_duration_min(self) -> int:
        """The length to aim for. Kept as a name, not a second copy of it."""
        return self.duration_min

    def shortest_acceptable_min(self) -> int:
        """How short this task may be cut before it stops being worth doing."""
        # An explicit study length is an ideal target, not necessarily an
        # indivisible appointment.  Only tasks deliberately tagged elastic
        # may use their shorter useful duration; meetings and classes remain
        # exact even when both have an explicit duration.
        if "elastic_duration" in self.tags and self.min_duration_min:
            return min(self.min_duration_min, self.duration_min)
        if self.duration_source == "explicit":
            return self.duration_min
        return min(self.min_duration_min or self.duration_min, self.duration_min)

    @model_validator(mode="after")
    def validate_duration_band(self) -> Task:
        if self.min_duration_min and self.min_duration_min > self.duration_min:
            raise ValueError("min_duration_min must not exceed duration_min")
        if self.max_duration_min and self.max_duration_min < self.duration_min:
            raise ValueError("max_duration_min must not be below duration_min")
        return self

    @model_validator(mode="after")
    def validate_time_constraints(self) -> Task:
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
