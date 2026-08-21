from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Issue
from app.schemas.calendar import CalendarOverrideCreate
from app.schemas.campus import CampusSelection
from app.schemas.memory import MemoryCreate
from app.schemas.plan import DataFreshness, Plan
from app.schemas.timetable import CourseSessionCreate


class ClientTimetableSnapshot(BaseModel):
    name: str = Field(default="我的课表", min_length=1, max_length=80)
    term_start: date | None = None
    term_end: date | None = None
    enabled: bool = True
    entries: list[CourseSessionCreate] = Field(
        default_factory=list,
        max_length=200,
    )


class ClientBehaviorPattern(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    task_title: str = Field(min_length=1, max_length=100)
    typical_start: time
    duration_min: int = Field(ge=5, le=480)
    location_name: str | None = Field(default=None, max_length=120)
    campus_id: str | None = Field(default=None, max_length=100)
    occurrences: int = Field(ge=3, le=1000)
    dismissed_count: int = Field(default=0, ge=0, le=1000)
    last_dismissed_at: datetime | None = None
    last_suggested_at: datetime | None = None


class ClientPersonalization(BaseModel):
    enabled: bool = False
    behavior_patterns: list[ClientBehaviorPattern] = Field(
        default_factory=list,
        max_length=20,
    )


class ClientContext(BaseModel):
    current_location_id: str | None = Field(default=None, max_length=100)
    now: datetime | None = None
    memories: list[MemoryCreate] = Field(default_factory=list, max_length=30)
    timetable: ClientTimetableSnapshot | None = None
    calendar_overrides: list[CalendarOverrideCreate] = Field(
        default_factory=list,
        max_length=60,
    )
    previous_plan: Plan | None = None
    campus: CampusSelection | None = None
    personalization: ClientPersonalization = Field(
        default_factory=ClientPersonalization,
    )

    @model_validator(mode="after")
    def validate_now(self) -> "ClientContext":
        if self.now is not None and self.now.tzinfo is None:
            raise ValueError("client_context.now must include timezone")
        return self


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    thread_id: str | None = Field(default=None, max_length=128)
    query: str = Field(min_length=1, max_length=2000)
    old_plan_id: str | None = Field(default=None, max_length=80)
    mode: Literal["auto", "offline", "live"] = "live"
    publish_to_agenda: bool = True
    preview_only: bool = False
    client_context: ClientContext | None = None


class ChatResponse(BaseModel):
    request_id: str
    trace_id: str
    thread_id: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    status: str
    answer: str
    plan: Plan | None = None
    clarifications: list[str] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    data_freshness: DataFreshness = Field(default_factory=DataFreshness)
    location_names: dict[str, str] = Field(default_factory=dict)
    previous_plan: Plan | None = None
    plan_diff: list["PlanChange"] = Field(default_factory=list)
    adjustment_reason: str | None = None
    constraint_checks: list["ConstraintCheck"] = Field(default_factory=list)
    execution_steps: list["ExecutionStep"] = Field(default_factory=list)
    task_statuses: list["TaskStatus"] = Field(default_factory=list)
    suggested_actions: list["SuggestedAction"] = Field(default_factory=list)
    insights: list["PlanningInsight"] = Field(default_factory=list)
    time_context: "PlanningTimeContext"
    current_plan_saved: bool = False


class ExecutionStep(BaseModel):
    key: str
    label: str
    status: Literal["waiting", "success", "fallback", "failed"]
    detail: str = ""


class ConstraintCheck(BaseModel):
    key: str
    label: str
    passed: bool
    message: str


class TaskStatus(BaseModel):
    task_id: str
    title: str
    duration_min: int = Field(ge=5)
    location_id: str | None = None
    status: Literal["scheduled", "needs_adjustment"]
    start_at: datetime | None = None
    end_at: datetime | None = None
    message: str


class SuggestedAction(BaseModel):
    id: str
    label: str
    description: str
    query: str
    kind: Literal["plan_adjustment", "habit_suggestion"] = "plan_adjustment"
    dismissible: bool = False


class PlanningInsight(BaseModel):
    title: str
    content: str
    source_label: str
    importance: Literal["required", "attention", "reference"] = "reference"


class PlanningTimeContext(BaseModel):
    now: datetime
    timezone: str
    target_date: date
    weekday: str
    source: Literal["server_clock", "request_context"]


class PlanChange(BaseModel):
    task_id: str
    title: str
    change_type: Literal[
        "added",
        "removed",
        "moved",
        "duration_changed",
    ]
    before_start: datetime | None = None
    before_end: datetime | None = None
    after_start: datetime | None = None
    after_end: datetime | None = None
    shift_min: int = 0
    duration_delta_min: int = 0
    summary: str


class DemoInfo(BaseModel):
    id: str
    title: str
    description: str
    query: str


class ErrorDetail(BaseModel):
    field: str | None = None
    reason: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    retryable: bool = False


class ErrorResponse(BaseModel):
    request_id: str
    trace_id: str
    error: ErrorBody


class DemoFixture(BaseModel):
    id: str
    title: str
    description: str
    now: datetime
    query: str
    mode: Literal["offline"] = "offline"
    user_id: str = "demo_user"
    thread_id: str | None = None
    old_plan_fixture: str | None = None
    prefer_latest_plan: bool = False
    initial_context: dict[str, Any] = Field(default_factory=dict)
    faults: dict[str, str] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
