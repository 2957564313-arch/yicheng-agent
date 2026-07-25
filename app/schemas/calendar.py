from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import DataSource


CalendarOverrideAction = Literal["no_class", "normal", "makeup"]


class CalendarOverrideCreate(BaseModel):
    date: date
    action: CalendarOverrideAction
    replacement_weekday: int | None = Field(default=None, ge=1, le=7)
    label: str = Field(default="学校校历调整", min_length=1, max_length=100)
    source_ref: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_replacement_weekday(self) -> "CalendarOverrideCreate":
        if self.action == "makeup" and self.replacement_weekday is None:
            raise ValueError("补课日期需要指定按星期几的课表执行")
        if self.action != "makeup":
            self.replacement_weekday = None
        return self


class CalendarOverride(CalendarOverrideCreate):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class CalendarOverrideListResponse(BaseModel):
    items: list[CalendarOverride] = Field(default_factory=list)


class AcademicDayContext(BaseModel):
    date: date
    day_type: Literal["normal", "holiday", "adjusted_workday", "unknown"]
    course_action: Literal[
        "normal",
        "no_class",
        "makeup",
        "awaiting_school_notice",
    ]
    label: str | None = None
    effective_weekday: int | None = Field(default=None, ge=1, le=7)
    source: DataSource
    source_ref: str | None = None
    verified_at: date | None = None

    @property
    def has_course_schedule(self) -> bool:
        return self.effective_weekday is not None
