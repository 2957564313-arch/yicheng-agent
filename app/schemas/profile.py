from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.agenda import ReminderSettings
from app.schemas.calendar import CalendarOverrideCreate
from app.schemas.memory import MemoryCreate
from app.schemas.plan import Plan
from app.schemas.timetable import CourseSessionCreate


class TimetableBackup(BaseModel):
    name: str = Field(default="我的课表", min_length=1, max_length=80)
    term_start: date | None = None
    term_end: date | None = None
    enabled: bool = True
    entries: list[CourseSessionCreate] = Field(
        default_factory=list,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_term(self) -> TimetableBackup:
        if (
            self.term_start is not None
            and self.term_end is not None
            and self.term_end < self.term_start
        ):
            raise ValueError("学期结束日期不能早于开始日期")
        return self


class PersonalDataRestoreRequest(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    thread_id: str = Field(min_length=1, max_length=128)
    memories: list[MemoryCreate] = Field(
        default_factory=list,
        max_length=100,
    )
    timetable: TimetableBackup | None = None
    calendar_overrides: list[CalendarOverrideCreate] = Field(
        default_factory=list,
        max_length=366,
    )
    reminder_settings: ReminderSettings | None = None
    current_plan: Plan | None = None
    current_plan_published: bool = False


class PersonalDataRestoreResponse(BaseModel):
    user_id: str
    thread_id: str
    memories_restored: int = Field(ge=0)
    timetable_entries_restored: int = Field(ge=0)
    calendar_overrides_restored: int = Field(ge=0)
    reminder_settings_restored: bool
    current_plan_restored: bool
    current_plan_published: bool
    restored_at: datetime
