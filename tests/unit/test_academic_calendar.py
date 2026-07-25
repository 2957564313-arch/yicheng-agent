from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import BASE_DIR
from app.repositories.academic_calendar import AcademicCalendarRepository
from app.schemas.calendar import CalendarOverrideCreate


def test_national_holiday_suppresses_regular_course_table(temp_database):
    repository = AcademicCalendarRepository(
        temp_database,
        BASE_DIR / "data" / "academic_calendar.json",
    )
    context = repository.resolve(
        user_id="holiday_user",
        target_date=date(2026, 10, 2),
    )
    assert context.day_type == "holiday"
    assert context.course_action == "no_class"
    assert context.effective_weekday is None
    assert context.label == "国庆节"


def test_adjusted_workday_waits_for_school_notice(temp_database):
    repository = AcademicCalendarRepository(
        temp_database,
        BASE_DIR / "data" / "academic_calendar.json",
    )
    context = repository.resolve(
        user_id="workday_user",
        target_date=date(2026, 10, 10),
    )
    assert context.day_type == "adjusted_workday"
    assert context.course_action == "awaiting_school_notice"
    assert context.effective_weekday is None


def test_school_makeup_override_has_priority_over_national_calendar(
    temp_database,
):
    repository = AcademicCalendarRepository(
        temp_database,
        BASE_DIR / "data" / "academic_calendar.json",
    )
    repository.upsert_override(
        user_id="makeup_user",
        payload=CalendarOverrideCreate(
            date=date(2026, 10, 10),
            action="makeup",
            replacement_weekday=5,
            label="学校通知：补星期五课程",
        ),
        now=datetime(2026, 9, 30, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    context = repository.resolve(
        user_id="makeup_user",
        target_date=date(2026, 10, 10),
    )
    assert context.day_type == "adjusted_workday"
    assert context.course_action == "makeup"
    assert context.effective_weekday == 5
    assert context.source.value == "user"


def test_unverified_future_year_keeps_weekday_but_does_not_guess_holidays(
    temp_database,
):
    repository = AcademicCalendarRepository(
        temp_database,
        BASE_DIR / "data" / "academic_calendar.json",
    )
    context = repository.resolve(
        user_id="future_user",
        target_date=date(2027, 1, 1),
    )
    assert context.day_type == "unknown"
    assert context.course_action == "normal"
    assert context.effective_weekday == 5
    assert context.source.value == "unknown"
