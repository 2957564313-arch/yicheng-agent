from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.providers.campus_rules import CampusRulesRepository
from app.providers.location_repository import LocationRepository
from app.providers.route_static import StaticRouteProvider
from app.schemas.common import TaskFlexibility
from app.schemas.task import Task, UserPreferences
from app.services.scheduler import PlanningContext, Scheduler
from app.services.validator import PlanValidator


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


async def build_context(
    target_date: date,
    now: datetime,
    pairs: list[tuple[str, str]],
    *,
    old_plan=None,
) -> PlanningContext:
    locations = LocationRepository(DATA_DIR / "locations.json")
    routes = StaticRouteProvider(DATA_DIR / "travel_times.json", locations)
    rules = CampusRulesRepository(
        DATA_DIR / "opening_hours.json",
        DATA_DIR / "campus_rules.json",
        DATA_DIR / "class_periods.json",
        "Asia/Shanghai",
    )
    travel = {}
    for origin, destination in pairs:
        estimate = await routes.get_route(origin, destination)
        travel[(origin, destination)] = estimate
        reverse = await routes.get_route(destination, origin)
        travel[(destination, origin)] = reverse

    opening = {
        location_id: rules.opening_windows(location_id, target_date)
        for location_id in ("library", "parcel_station")
    }
    return PlanningContext(
        target_date=target_date,
        timezone=ZoneInfo("Asia/Shanghai"),
        now=now,
        travel=travel,
        opening_windows=opening,
        old_plan=old_plan,
    )


@pytest.mark.asyncio
async def test_normal_plan_has_no_hard_violations(tz):
    target_date = date(2026, 7, 24)
    now = datetime(2026, 7, 23, 20, 0, tzinfo=tz)
    tasks = [
        Task(
            id="study",
            title="图书馆自习",
            date=target_date,
            duration_min=120,
            location_id="library",
            earliest_start=datetime(2026, 7, 24, 13, 0, tzinfo=tz),
            latest_end=datetime(2026, 7, 24, 18, 0, tzinfo=tz),
            preferred_period="afternoon",
            importance=4,
        ),
        Task(
            id="parcel",
            title="取快递",
            date=target_date,
            duration_min=15,
            location_id="parcel_station",
            earliest_start=datetime(2026, 7, 24, 13, 0, tzinfo=tz),
            deadline=datetime(2026, 7, 24, 18, 0, tzinfo=tz),
            importance=5,
        ),
        Task(
            id="dinner",
            title="吃晚饭",
            date=target_date,
            duration_min=45,
            location_id="canteen",
            earliest_start=datetime(2026, 7, 24, 17, 0, tzinfo=tz),
            latest_end=datetime(2026, 7, 24, 20, 0, tzinfo=tz),
            importance=3,
        ),
        Task(
            id="run",
            title="跑步",
            date=target_date,
            duration_min=40,
            location_id="track",
            preferred_period="evening",
            importance=3,
        ),
    ]
    pairs = [
        ("library", "parcel_station"),
        ("library", "canteen"),
        ("parcel_station", "canteen"),
        ("canteen", "track"),
        ("library", "track"),
    ]
    context = await build_context(target_date, now, pairs)
    result = Scheduler().schedule(
        user_id="demo_user",
        thread_id="thread_normal",
        tasks=tasks,
        preferences=UserPreferences(buffer_min=10),
        context=context,
    )
    plan, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=tasks,
        context=context,
    )

    assert not result.unscheduled_task_ids
    assert not [issue for issue in issues if issue.severity == "error"]
    assert plan.status == "valid"
    assert plan.metrics.scheduled_task_count == 4
    parcel = next(item for item in plan.items if item.task_id == "parcel")
    run = next(item for item in plan.items if item.task_id == "run")
    assert parcel.end_at <= datetime(2026, 7, 24, 18, 0, tzinfo=tz)
    assert run.start_at.hour >= 18
    assert any(item.item_type == "travel" for item in plan.items)


@pytest.mark.asyncio
async def test_scheduler_marks_impossible_task_unscheduled(tz):
    target_date = date(2026, 7, 24)
    now = datetime(2026, 7, 23, 20, 0, tzinfo=tz)
    task = Task(
        id="impossible",
        title="无法完成的任务",
        date=target_date,
        duration_min=120,
        earliest_start=datetime(2026, 7, 24, 17, 30, tzinfo=tz),
        deadline=datetime(2026, 7, 24, 18, 0, tzinfo=tz),
    )
    context = await build_context(target_date, now, [])
    result = Scheduler().schedule(
        user_id="demo_user",
        thread_id="thread_impossible",
        tasks=[task],
        preferences=UserPreferences(),
        context=context,
    )
    _, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=[task],
        context=context,
    )

    assert result.unscheduled_task_ids == ["impossible"]
    assert {issue.code for issue in issues} == {"TASK_UNSCHEDULED"}


@pytest.mark.asyncio
async def test_scheduler_uses_venue_closing_time_after_22_not_legacy_cutoff(tz):
    target_date = date(2026, 7, 24)
    now = datetime(2026, 7, 24, 13, 0, tzinfo=tz)
    task = Task(
        id="study",
        title="图书馆自习",
        date=target_date,
        duration_min=30,
        location_id="library",
        earliest_start=datetime(2026, 7, 24, 22, 0, tzinfo=tz),
        latest_end=datetime(2026, 7, 24, 22, 30, tzinfo=tz),
    )
    context = await build_context(target_date, now, [])

    result = Scheduler().schedule(
        user_id="demo_user",
        thread_id="thread_library_boundary",
        tasks=[task],
        preferences=UserPreferences(),
        context=context,
    )
    plan, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=[task],
        context=context,
    )

    study = next(item for item in plan.items if item.task_id == "study")
    assert not result.unscheduled_task_ids
    assert study.start_at == datetime(2026, 7, 24, 22, 0, tzinfo=tz)
    assert study.end_at == datetime(2026, 7, 24, 22, 30, tzinfo=tz)
    assert not [issue for issue in issues if issue.severity == "error"]


@pytest.mark.asyncio
async def test_peak_window_extends_travel_and_keeps_user_time_choice(tz):
    target_date = date(2026, 7, 24)
    now = datetime(2026, 7, 23, 20, 0, tzinfo=tz)
    context = await build_context(
        target_date,
        now,
        [("library", "parcel_station")],
    )
    rules = CampusRulesRepository(
        DATA_DIR / "opening_hours.json",
        DATA_DIR / "campus_rules.json",
        DATA_DIR / "class_periods.json",
        "Asia/Shanghai",
    )
    context.congestion_windows = rules.congestion_contexts(target_date)
    tasks = [
        Task(
            id="study",
            title="图书馆自习",
            date=target_date,
            duration_min=40,
            location_id="library",
            fixed_start=datetime(2026, 7, 24, 9, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 9, 40, tzinfo=tz),
            flexibility=TaskFlexibility.FIXED,
        ),
        Task(
            id="parcel",
            title="取快递",
            date=target_date,
            duration_min=20,
            location_id="parcel_station",
            fixed_start=datetime(2026, 7, 24, 10, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 10, 20, tzinfo=tz),
            flexibility=TaskFlexibility.FIXED,
        ),
    ]

    result = Scheduler().schedule(
        user_id="demo_user",
        thread_id="thread_peak",
        tasks=tasks,
        preferences=UserPreferences(),
        context=context,
    )
    plan, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=tasks,
        context=context,
    )
    travel = next(item for item in plan.items if item.item_type == "travel")

    assert travel.base_duration_min == 13
    assert travel.congestion_delay_min == 4
    assert int((travel.end_at - travel.start_at).total_seconds() // 60) == 17
    assert plan.status == "valid"
    assert "PEAK_CONGESTION" in {issue.code for issue in issues}
    assert not [issue for issue in issues if issue.severity == "error"]


@pytest.mark.asyncio
async def test_travel_is_placed_close_to_following_task_when_gap_is_long(tz):
    target_date = date(2026, 7, 24)
    now = datetime(2026, 7, 23, 20, 0, tzinfo=tz)
    context = await build_context(
        target_date,
        now,
        [("parcel_station", "track")],
    )
    tasks = [
        Task(
            id="parcel",
            title="取快递",
            date=target_date,
            duration_min=30,
            location_id="parcel_station",
            fixed_start=datetime(2026, 7, 24, 13, 30, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 14, 0, tzinfo=tz),
            flexibility=TaskFlexibility.FIXED,
        ),
        Task(
            id="run",
            title="跑步",
            date=target_date,
            duration_min=30,
            location_id="track",
            fixed_start=datetime(2026, 7, 24, 18, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 18, 30, tzinfo=tz),
            flexibility=TaskFlexibility.FIXED,
        ),
    ]

    result = Scheduler().schedule(
        user_id="demo_user",
        thread_id="thread_late_travel",
        tasks=tasks,
        preferences=UserPreferences(buffer_min=10),
        context=context,
    )
    travel = next(
        item for item in result.plan.items if item.item_type == "travel"
    )

    assert travel.start_at > tasks[0].fixed_end
    assert travel.end_at == tasks[1].fixed_start - timedelta(minutes=10)


@pytest.mark.asyncio
async def test_validator_rejects_any_change_to_fixed_course_time(tz):
    target_date = date(2026, 7, 24)
    now = datetime(2026, 7, 23, 20, 0, tzinfo=tz)
    task = Task(
        id="course_1_2",
        title="第1—2节课程",
        date=target_date,
        duration_min=95,
        fixed_start=datetime(2026, 7, 24, 8, 5, tzinfo=tz),
        fixed_end=datetime(2026, 7, 24, 9, 40, tzinfo=tz),
        flexibility=TaskFlexibility.FIXED,
        tags=["course", "hard_constraint"],
    )
    context = await build_context(target_date, now, [])
    result = Scheduler().schedule(
        user_id="demo_user",
        thread_id="thread_fixed_course",
        tasks=[task],
        preferences=UserPreferences(),
        context=context,
    )
    result.plan.items[0] = result.plan.items[0].model_copy(
        update={
            "start_at": result.plan.items[0].start_at + timedelta(minutes=5),
            "end_at": result.plan.items[0].end_at + timedelta(minutes=5),
        }
    )

    plan, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=[task],
        context=context,
    )

    assert plan.status == "infeasible"
    assert "FIXED_TIME_CHANGED" in {issue.code for issue in issues}


def test_scheduler_uses_activity_specific_window_for_sunshine_run(tz):
    target_date = date(2026, 7, 24)
    task = Task(
        id="sun_run",
        title="完成一次阳光长跑",
        date=target_date,
        duration_min=40,
        location_id="northwest_track",
    )
    context = PlanningContext(
        target_date=target_date,
        timezone=tz,
        now=datetime(2026, 7, 23, 20, 0, tzinfo=tz),
        opening_windows={
            "northwest_track": [
                (
                    datetime(2026, 7, 24, 0, 0, tzinfo=tz),
                    datetime(2026, 7, 25, 0, 0, tzinfo=tz),
                )
            ]
        },
        task_windows={
            "sun_run": [
                (
                    datetime(2026, 7, 24, 18, 30, tzinfo=tz),
                    datetime(2026, 7, 24, 21, 0, tzinfo=tz),
                )
            ]
        },
    )

    result = Scheduler().schedule(
        user_id="demo_user",
        thread_id="thread_sun_run",
        tasks=[task],
        preferences=UserPreferences(),
        context=context,
    )
    item = next(
        item for item in result.plan.items if item.task_id == "sun_run"
    )

    assert item.start_at == datetime(2026, 7, 24, 18, 30, tzinfo=tz)
    plan, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=[task],
        context=context,
    )
    assert plan.status == "valid"
    assert not [issue for issue in issues if issue.severity == "error"]
