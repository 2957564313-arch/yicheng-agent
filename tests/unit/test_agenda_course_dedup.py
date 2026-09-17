from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.schemas.common import DataSource, PlanStatus
from app.schemas.plan import Plan, PlanItem
from app.services.agenda import AgendaService

TZ = ZoneInfo("Asia/Shanghai")
DAY = date(2026, 9, 17)


class _Plans:
    def __init__(self, plan: Plan) -> None:
        self._plan = plan

    def latest_for_user_range(self, **_: object) -> list[Plan]:
        return [self._plan]


class _Locations:
    def get(self, _location_id: str) -> None:
        return None


def _service(plan: Plan) -> AgendaService:
    service = AgendaService.__new__(AgendaService)
    service.plans = _Plans(plan)
    service.locations = _Locations()
    return service


def _course_plan(task_id: str) -> Plan:
    return Plan(
        id="plan_dup",
        user_id="student",
        thread_id="thread",
        date=DAY,
        status=PlanStatus.VALID,
        created_at=datetime(2026, 9, 17, 8, 0, tzinfo=TZ),
        items=[
            PlanItem(
                id="item_course",
                task_id=task_id,
                item_type="task",
                title="大学物理B2",
                start_at=datetime(2026, 9, 17, 10, 0, tzinfo=TZ),
                end_at=datetime(2026, 9, 17, 12, 25, tzinfo=TZ),
                location_raw="第6教研楼北410",
                locked=True,
                source=DataSource.STRUCTURED,
            ),
        ],
    )


def test_planned_course_is_not_listed_next_to_the_imported_class():
    """The class must appear once, from the timetable, and stay locked.

    Courses are handed to the planner as fixed tasks so nothing is scheduled
    on top of them, so the saved plan echoes every class back. Listing that
    echo alongside the imported class showed each course twice — once locked,
    once editable.
    """
    service = _service(_course_plan("hduhelp_course_2026-2027_1_1_4_3_8"))

    items = service._plan_items(
        user_id="student",
        start_date=DAY,
        end_date=DAY,
        imported_course_keys=set(),
    )

    assert items == []


def test_planned_course_is_dropped_even_under_an_unrecognised_task_id():
    """`classify` reads the title, and real course names carry no keyword.

    "大学物理B2" contains none of 课程/上课/实验课, so it classifies as a plain
    task; keying the de-duplication on kind == "course" let every genuinely
    named class through.
    """
    service = _service(_course_plan("task_from_some_other_source"))

    items = service._plan_items(
        user_id="student",
        start_date=DAY,
        end_date=DAY,
        imported_course_keys={
            (
                "大学物理B2",
                datetime(2026, 9, 17, 10, 0, tzinfo=TZ),
                datetime(2026, 9, 17, 12, 25, tzinfo=TZ),
                "第6教研楼北410",
            )
        },
    )

    assert items == []


def test_an_ordinary_task_is_still_listed():
    plan = Plan(
        id="plan_ok",
        user_id="student",
        thread_id="thread",
        date=DAY,
        status=PlanStatus.VALID,
        created_at=datetime(2026, 9, 17, 8, 0, tzinfo=TZ),
        items=[
            PlanItem(
                id="item_study",
                task_id="study",
                item_type="task",
                title="自习",
                start_at=datetime(2026, 9, 17, 15, 30, tzinfo=TZ),
                end_at=datetime(2026, 9, 17, 17, 30, tzinfo=TZ),
                location_raw="图书馆",
                source=DataSource.USER,
            ),
        ],
    )

    items = _service(plan)._plan_items(
        user_id="student",
        start_date=DAY,
        end_date=DAY,
        imported_course_keys=set(),
    )

    assert [item.title for item in items] == ["自习"]
