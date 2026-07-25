from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from app.repositories.academic_calendar import AcademicCalendarRepository
from app.repositories.memories import MemoryRepository
from app.repositories.timetables import TimetableRepository
from app.schemas.memory import MemoryCreate
from app.schemas.timetable import CourseSessionCreate
from app.schemas.weekly import (
    WeekdayAvailability,
    WeeklyAvailabilityProfile,
    WeeklyClockWindow,
)
from app.services.weekly_capacity import WeeklyCapacityBuilder


BASE_DIR = Path(__file__).resolve().parents[2]


def test_personal_timetable_and_memories_shape_weekly_capacity(
    temp_database,
):
    timezone = ZoneInfo("Asia/Shanghai")
    now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone)
    timetables = TimetableRepository(temp_database)
    memories = MemoryRepository(temp_database)
    calendar = AcademicCalendarRepository(
        temp_database,
        BASE_DIR / "data" / "academic_calendar.json",
    )
    timetables.replace(
        user_id="capacity_user",
        name="我的课表",
        term_start=date(2026, 7, 27),
        term_end=date(2026, 8, 2),
        enabled=True,
        entries=[
            CourseSessionCreate(
                course_name="高等数学",
                weekday=1,
                start_period=1,
                end_period=2,
                location="第六教学楼",
                weeks=[1],
            )
        ],
        now=now,
    )
    memories.upsert(
        user_id="capacity_user",
        payload=MemoryCreate(
            category="habit",
            key="preferred_study_period",
            label="上午学习状态更好",
            value="morning",
        ),
        now=now,
    )
    memories.upsert(
        user_id="capacity_user",
        payload=MemoryCreate(
            category="preference",
            key="weekly_daily_focus_limit_min",
            label="每日专注上限",
            value=120,
        ),
        now=now,
    )
    builder = WeeklyCapacityBuilder(
        timetables=timetables,
        memories=memories,
        academic_calendar=calendar,
        class_periods={
            1: (time(8, 5), time(8, 50)),
            2: (time(8, 55), time(9, 40)),
        },
    )

    result = builder.build(
        user_id="capacity_user",
        week_start=date(2026, 7, 27),
        timezone_name="Asia/Shanghai",
        profile=WeeklyAvailabilityProfile(
            days=[
                WeekdayAvailability(
                    weekday=1,
                    windows=[
                        WeeklyClockWindow(
                            start=time(7, 0),
                            end=time(11, 0),
                        )
                    ],
                )
            ]
        ),
    )

    monday = result.capacities[0]
    assert result.summary.timetable_applied is True
    assert result.summary.excluded_course_count == 1
    assert result.summary.memory_labels == [
        "常用学习时段",
        "每日自主安排上限",
    ]
    assert sum(item.duration_min for item in monday.windows) == 120
    assert all(
        not (
            item.start_at < datetime(2026, 7, 27, 9, 40, tzinfo=timezone)
            and item.end_at > datetime(2026, 7, 27, 8, 5, tzinfo=timezone)
        )
        for item in monday.windows
    )
    assert all(item.energy_level == "high" for item in monday.windows)
