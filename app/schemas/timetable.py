from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CourseSessionCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=120)
    weekday: int = Field(ge=1, le=7)
    start_period: int = Field(ge=1, le=13)
    end_period: int = Field(ge=1, le=13)
    location: str | None = Field(default=None, max_length=120)
    weeks: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_periods(self) -> "CourseSessionCreate":
        if self.end_period < self.start_period:
            raise ValueError("结束节次不能早于开始节次")
        if any(week < 1 or week > 30 for week in self.weeks):
            raise ValueError("周次必须在1到30之间")
        self.weeks = sorted(set(self.weeks))
        return self


class CourseSession(CourseSessionCreate):
    id: str
    timetable_id: str
    created_at: datetime


class TimetableImportRequest(BaseModel):
    name: str = Field(default="我的课表", min_length=1, max_length=80)
    format: Literal["csv", "json", "xlsx_base64", "pdf_base64"]
    content: str = Field(min_length=1, max_length=8_000_000)
    term_start: date | None = None
    term_end: date | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_term(self) -> "TimetableImportRequest":
        if (
            self.term_start is not None
            and self.term_end is not None
            and self.term_end < self.term_start
        ):
            raise ValueError("学期结束日期不能早于开始日期")
        return self


class TimetableInfo(BaseModel):
    id: str
    user_id: str
    name: str
    term_start: date | None = None
    term_end: date | None = None
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class TimetableResponse(BaseModel):
    timetable: TimetableInfo | None = None
    entries: list[CourseSession] = Field(default_factory=list)


class TimetableImportResponse(TimetableResponse):
    imported_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    messages: list[str] = Field(default_factory=list)


class TimetablePreviewResponse(BaseModel):
    entries: list[CourseSessionCreate] = Field(default_factory=list)
    imported_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    messages: list[str] = Field(default_factory=list)
    term_start: date | None = None
    term_end: date | None = None
