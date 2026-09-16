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
    # 2026-05-09 is a national make-up workday the school has not published a
    # timetable notice for, so the day must stay explicitly unresolved.
    context = repository.resolve(
        user_id="workday_user",
        target_date=date(2026, 5, 9),
    )
    assert context.day_type == "adjusted_workday"
    assert context.course_action == "awaiting_school_notice"
    assert context.effective_weekday is None


def test_calendar_range_resolves_holiday_and_adjusted_workday(temp_database):
    repository = AcademicCalendarRepository(
        temp_database,
        BASE_DIR / "data" / "academic_calendar.json",
    )

    contexts = repository.resolve_range(
        user_id="range_user",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 10),
    )

    assert len(contexts) == 10
    assert contexts[0].day_type == "holiday"
    assert contexts[0].course_action == "no_class"
    assert contexts[-1].day_type == "adjusted_workday"
    assert contexts[-1].course_action == "makeup"
    assert contexts[-1].effective_weekday == 3


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


def test_verified_2025_calendar_only_marks_real_holidays(temp_database):
    repository = AcademicCalendarRepository(
        temp_database,
        BASE_DIR / "data" / "academic_calendar.json",
    )

    ordinary = repository.resolve(
        user_id="calendar_2025",
        target_date=date(2025, 9, 2),
    )
    national_day = repository.resolve(
        user_id="calendar_2025",
        target_date=date(2025, 10, 1),
    )
    makeup_day = repository.resolve(
        user_id="calendar_2025",
        target_date=date(2025, 10, 11),
    )

    assert ordinary.day_type == "normal"
    assert ordinary.course_action == "normal"
    assert ordinary.label is None
    assert national_day.day_type == "holiday"
    assert national_day.label == "国庆节、中秋节"
    assert makeup_day.day_type == "adjusted_workday"
    assert makeup_day.course_action == "awaiting_school_notice"


def test_school_notice_resolves_makeup_without_any_user_override(
    temp_database,
):
    """A campus-wide notice must not depend on per-user data.

    Calendar overrides are owned by the browser copy and are wiped for any
    date the client does not send, so a school-wide make-up day stored as a
    user override would disappear the first time a clean browser syncs.
    """
    repository = AcademicCalendarRepository(
        temp_database,
        BASE_DIR / "data" / "academic_calendar.json",
    )

    context = repository.resolve(
        user_id="user_who_never_entered_anything",
        target_date=date(2026, 9, 20),
    )

    assert context.day_type == "adjusted_workday"
    assert context.course_action == "makeup"
    # 2026-10-06 is a Tuesday: the Sunday follows that day's timetable.
    assert context.effective_weekday == 2
    assert context.source.value == "structured"
