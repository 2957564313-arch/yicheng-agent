from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


AgendaSource = Literal["course", "plan", "weekly", "manual"]
AgendaKind = Literal[
    "course",
    "meeting",
    "activity",
    "study",
    "exercise",
    "meal",
    "travel",
    "task",
]
ReminderKind = Literal["wakeup", "bedtime", "prepare", "upcoming"]


class AgendaItem(BaseModel):
    id: str = Field(min_length=1, max_length=160)
    user_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    start_at: datetime
    end_at: datetime
    location_name: str | None = Field(default=None, max_length=160)
    source: AgendaSource
    kind: AgendaKind
    locked: bool = False
    plan_id: str | None = Field(default=None, max_length=80)
    task_id: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_interval(self) -> "AgendaItem":
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("日程时间必须包含时区")
        if self.end_at <= self.start_at:
            raise ValueError("日程结束时间必须晚于开始时间")
        return self


class ReminderSettings(BaseModel):
    enabled: bool = True
    browser_notifications: bool = False
    bedtime_enabled: bool = True
    course_lead_min: int = Field(default=20, ge=5, le=180)
    early_course_wakeup_min: int = Field(default=75, ge=20, le=240)
    meeting_lead_min: int = Field(default=15, ge=5, le=180)
    activity_lead_min: int = Field(default=30, ge=5, le=240)
    study_lead_min: int = Field(default=10, ge=0, le=120)
    exercise_lead_min: int = Field(default=15, ge=0, le=120)
    task_lead_min: int = Field(default=10, ge=0, le=120)
    bedtime_lead_min: int = Field(default=30, ge=0, le=120)
    quiet_start: time = time(23, 0)
    quiet_end: time = time(6, 30)


class ReminderCandidate(BaseModel):
    id: str = Field(min_length=1, max_length=220)
    agenda_item_id: str = Field(min_length=1, max_length=160)
    kind: ReminderKind
    notify_at: datetime
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=300)
    event_start_at: datetime
    event_end_at: datetime


class CareSuggestion(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=400)
    level: Literal["gentle", "attention", "positive"] = "gentle"
    action_query: str | None = Field(default=None, max_length=500)


class AgendaSummary(BaseModel):
    course_count: int = Field(default=0, ge=0)
    planned_item_count: int = Field(default=0, ge=0)
    study_minutes: int = Field(default=0, ge=0)
    exercise_minutes: int = Field(default=0, ge=0)
    meeting_minutes: int = Field(default=0, ge=0)
    busy_minutes: int = Field(default=0, ge=0)
    earliest_start: datetime | None = None
    latest_end: datetime | None = None


class AgendaResponse(BaseModel):
    user_id: str
    start_date: date
    end_date: date
    timezone: str
    items: list[AgendaItem] = Field(default_factory=list)
    reminders: list[ReminderCandidate] = Field(default_factory=list)
    care_suggestions: list[CareSuggestion] = Field(default_factory=list)
    summary: AgendaSummary = Field(default_factory=AgendaSummary)
    generated_at: datetime


class ReminderSettingsResponse(BaseModel):
    user_id: str
    settings: ReminderSettings
    updated_at: datetime | None = None


class ReminderDueResponse(BaseModel):
    now: datetime
    window_end: datetime
    reminders: list[ReminderCandidate] = Field(default_factory=list)
