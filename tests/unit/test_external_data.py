from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.repositories.external_data import ExternalDataRepository


def test_all_term_snapshot_selects_course_for_requested_semester(temp_database):
    repository = ExternalDataRepository(temp_database)
    repository.replace_source(
        user_id="multi_term_user",
        provider="hduhelp",
        source_kind="timetable_terms",
        payload=[
            {
                "school_year": "2025-2026",
                "semester": 2,
                "term_start": "2026-03-02",
                "term_end": "2026-07-05",
                "entries": [
                    {
                        "course_name": "高等数学A2",
                        "weekday": 1,
                        "start_period": 1,
                        "end_period": 2,
                        "location": "第6教研楼北204",
                        "weeks": [1],
                    }
                ],
            },
            {
                "school_year": "2026-2027",
                "semester": 1,
                "term_start": "2026-09-07",
                "term_end": "2027-01-10",
                "entries": [
                    {
                        "course_name": "工程伦理",
                        "weekday": 1,
                        "start_period": 1,
                        "end_period": 2,
                        "location": "第6教研楼北214",
                        "weeks": [1],
                    }
                ],
            },
        ],
        now=datetime(2026, 8, 19, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    tasks = repository.timetable_tasks_for_date(
        user_id="multi_term_user",
        target_date=date(2026, 9, 7),
        class_periods={
            1: (time(8, 5), time(8, 50)),
            2: (time(8, 55), time(9, 40)),
        },
        timezone_name="Asia/Shanghai",
        effective_weekday=1,
    )

    assert tasks is not None
    assert len(tasks) == 1
    assert tasks[0].title == "工程伦理"
    assert tasks[0].location_raw == "第6教研楼北214"
    assert tasks[0].fixed_start is not None
    assert tasks[0].fixed_start.strftime("%H:%M") == "08:05"
    assert tasks[0].fixed_end is not None
    assert tasks[0].fixed_end.strftime("%H:%M") == "09:40"


def test_all_term_snapshot_is_authoritative_when_date_has_no_course(temp_database):
    repository = ExternalDataRepository(temp_database)
    repository.replace_source(
        user_id="empty_day_user",
        provider="hduhelp",
        source_kind="timetable_terms",
        payload=[
            {
                "school_year": "2026-2027",
                "semester": 1,
                "term_start": "2026-09-07",
                "term_end": "2027-01-10",
                "entries": [],
            }
        ],
        now=datetime(2026, 8, 19, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    tasks = repository.timetable_tasks_for_date(
        user_id="empty_day_user",
        target_date=date(2026, 9, 8),
        class_periods={},
        timezone_name="Asia/Shanghai",
        effective_weekday=2,
    )

    assert tasks == []
