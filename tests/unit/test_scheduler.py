from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.providers.campus_rules import CampusRulesRepository
from app.providers.location_repository import LocationRepository
from app.providers.route_static import StaticRouteProvider
from app.schemas.common import DataSource, TaskFlexibility, TimeWindow
from app.schemas.context import TravelEstimate, WeatherContext
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
async def test_late_free_day_keeps_every_requested_task_by_compacting_soft_gaps(tz):
    """Regression for the real 17:57 request shown in the product UI.

    Two default-length study sittings may shrink to one hour each.  Together
    with a parcel errand, a run and the explicit two-hour adviser meeting they
    fit before midnight after the protected dinner window, but only if the
    generic ten-minute comfort gaps yield.  No requested task may disappear.
    """

    target_date = date(2026, 8, 20)
    now = datetime(2026, 8, 20, 17, 57, tzinfo=tz)
    tasks = [
        Task(
            id="study_1",
            title="自习",
            date=target_date,
            duration_min=120,
            min_duration_min=60,
            duration_source="default",
            min_gap_min=30,
            tags=["study", "elastic_duration", "occurrence_of:study"],
        ),
        Task(
            id="study_2",
            title="自习",
            date=target_date,
            duration_min=120,
            min_duration_min=60,
            duration_source="default",
            min_gap_min=30,
            tags=["study", "elastic_duration", "occurrence_of:study"],
        ),
        Task(
            id="parcel",
            title="取快递",
            date=target_date,
            duration_min=30,
            tags=["courier"],
        ),
        Task(
            id="run",
            title="跑步",
            date=target_date,
            duration_min=30,
        ),
        Task(
            id="mentor",
            title="和导师碰头",
            date=target_date,
            duration_min=120,
            duration_source="explicit",
            constraint_source="user",
            preferred_period="evening",
            tags=["meeting"],
        ),
    ]
    context = await build_context(target_date, now, [])

    result = Scheduler().schedule(
        user_id="late_user",
        thread_id="late_thread",
        tasks=tasks,
        preferences=UserPreferences(buffer_min=10),
        context=context,
    )

    scheduled = [item for item in result.plan.items if item.item_type == "task"]
    assert not result.unscheduled_task_ids
    assert {item.task_id for item in scheduled} == {task.id for task in tasks}
    mentor = next(item for item in scheduled if item.task_id == "mentor")
    assert int((mentor.end_at - mentor.start_at).total_seconds() // 60) == 120
    study_lengths = sorted(
        int((item.end_at - item.start_at).total_seconds() // 60)
        for item in scheduled
        if item.task_id in {"study_1", "study_2"}
    )
    assert all(60 <= minutes <= 120 for minutes in study_lengths)
    assert sum(study_lengths) >= 120
    assert max(item.end_at for item in scheduled) <= datetime.combine(
        target_date + timedelta(days=1),
        time.min,
        tzinfo=tz,
    )
    # This direct scheduler test deliberately starts after dinner has begun.
    # The conversation layer rolls an otherwise unconstrained request this
    # late to tomorrow; the low-level scheduler's remaining responsibility is
    # to keep every requested task visible rather than silently delete one.
    repeated = sorted(
        (item for item in scheduled if item.task_id in {"study_1", "study_2"}),
        key=lambda item: item.start_at,
    )
    assert [item.title for item in repeated] == ["自习（第1次）", "自习（第2次）"]


@pytest.mark.asyncio
async def test_free_day_uses_daytime_and_covers_multi_sitting_request(tz):
    target_date = date(2026, 8, 20)
    now = datetime(2026, 8, 20, 9, 0, tzinfo=tz)
    tasks = [
        Task(
            id=f"study_{index}",
            title="自习",
            date=target_date,
            duration_min=120,
            min_duration_min=60,
            duration_source="default",
        )
        for index in (1, 2)
    ] + [
        Task(
            id="parcel",
            title="取快递",
            date=target_date,
            duration_min=30,
            tags=["courier"],
        ),
        Task(
            id="run",
            title="跑步",
            date=target_date,
            duration_min=30,
        ),
        Task(
            id="mentor",
            title="和导师碰头",
            date=target_date,
            duration_min=120,
            duration_source="explicit",
            constraint_source="user",
            preferred_period="evening",
            tags=["meeting"],
        ),
    ]
    context = await build_context(target_date, now, [])

    result = Scheduler().schedule(
        user_id="day_user",
        thread_id="day_thread",
        tasks=tasks,
        preferences=UserPreferences(buffer_min=10),
        context=context,
    )

    scheduled = [item for item in result.plan.items if item.item_type == "task"]
    assert not result.unscheduled_task_ids
    assert len(scheduled) == len(tasks)
    assert min(item.start_at for item in scheduled).hour < 12
    study_lengths = sorted(
        int((item.end_at - item.start_at).total_seconds() // 60)
        for item in scheduled
        if item.task_id in {"study_1", "study_2"}
    )
    # Compression is an overload strategy, not a generic optimisation knob.
    # A free day must keep the requested/default two-hour study sittings.
    assert study_lengths == [120, 120]
    assert (
        next(item for item in scheduled if item.task_id == "mentor").start_at.hour >= 18
    )


@pytest.mark.asyncio
async def test_scheduler_uses_soft_lunch_hint_for_movable_work(tz):
    target_date = date(2026, 7, 24)
    task = Task(
        id="study_after_class",
        title="复习高数",
        date=target_date,
        duration_min=60,
        earliest_start=datetime(2026, 7, 24, 12, 25, tzinfo=tz),
        latest_end=datetime(2026, 7, 24, 15, 0, tzinfo=tz),
    )
    context = await build_context(
        target_date,
        datetime(2026, 7, 23, 20, 0, tzinfo=tz),
        [],
    )
    context.soft_meal_windows = [TimeWindow(start=time(12, 25), end=time(13, 15))]

    result = Scheduler().schedule(
        user_id="meal_user",
        thread_id="meal_thread",
        tasks=[task],
        preferences=UserPreferences(),
        context=context,
    )

    scheduled = next(item for item in result.plan.items if item.task_id == task.id)
    assert scheduled.start_at == datetime(2026, 7, 24, 13, 15, tzinfo=tz)


@pytest.mark.asyncio
async def test_explicit_meal_can_use_the_protected_meal_window(tz):
    target_date = date(2026, 7, 24)
    task = Task(
        id="lunch",
        title="吃午饭",
        date=target_date,
        duration_min=40,
        earliest_start=datetime(2026, 7, 24, 12, 25, tzinfo=tz),
        latest_end=datetime(2026, 7, 24, 13, 15, tzinfo=tz),
        tags=["meal"],
    )
    context = await build_context(
        target_date,
        datetime(2026, 7, 23, 20, 0, tzinfo=tz),
        [],
    )
    context.soft_meal_windows = [TimeWindow(start=time(12, 25), end=time(13, 15))]

    result = Scheduler().schedule(
        user_id="meal_user",
        thread_id="meal_thread",
        tasks=[task],
        preferences=UserPreferences(),
        context=context,
    )

    scheduled = next(item for item in result.plan.items if item.task_id == task.id)
    assert scheduled.start_at == datetime(2026, 7, 24, 12, 25, tzinfo=tz)


@pytest.mark.asyncio
async def test_very_close_locations_do_not_create_a_travel_block(tz):
    target_date = date(2026, 7, 24)
    tasks = [
        Task(
            id="room_a",
            title="课程一",
            date=target_date,
            duration_min=60,
            location_id="room_a",
            location_raw="第6教研楼北204",
            fixed_start=datetime(2026, 7, 24, 9, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 10, 0, tzinfo=tz),
            flexibility=TaskFlexibility.FIXED,
        ),
        Task(
            id="room_b",
            title="课程二",
            date=target_date,
            duration_min=60,
            location_id="room_b",
            location_raw="第6教研楼北304",
            fixed_start=datetime(2026, 7, 24, 10, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 11, 0, tzinfo=tz),
            flexibility=TaskFlexibility.FIXED,
        ),
    ]
    context = await build_context(
        target_date,
        datetime(2026, 7, 23, 20, 0, tzinfo=tz),
        [],
    )
    context.travel[("room_a", "room_b")] = TravelEstimate(
        origin_id="room_a",
        destination_id="room_b",
        distance_m=45,
        duration_min=2,
        source=DataSource.LIVE_API,
        confidence=1,
    )

    result = Scheduler().schedule(
        user_id="same_building_user",
        thread_id="same_building_thread",
        tasks=tasks,
        preferences=UserPreferences(buffer_min=0),
        context=context,
    )

    assert not [item for item in result.plan.items if item.item_type == "travel"]
    assert [item.location_raw for item in result.plan.items] == [
        "第6教研楼北204",
        "第6教研楼北304",
    ]


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
    travel = next(item for item in result.plan.items if item.item_type == "travel")

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
    item = next(item for item in result.plan.items if item.task_id == "sun_run")

    # The point of this test is the activity window, not one exact minute:
    # the run may start later inside it to keep the dinner gap clear.
    assert datetime(2026, 7, 24, 18, 30, tzinfo=tz) <= item.start_at
    assert item.end_at <= datetime(2026, 7, 24, 21, 0, tzinfo=tz)
    plan, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=[task],
        context=context,
    )
    assert plan.status == "valid"
    assert not [issue for issue in issues if issue.severity == "error"]


def test_free_day_uses_daytime_for_repeated_study_instead_of_scattering_it(tz):
    target_date = date(2026, 8, 20)
    context = PlanningContext(
        target_date=target_date,
        timezone=tz,
        now=datetime(2026, 8, 20, 9, 0, tzinfo=tz),
        soft_meal_windows=list(Scheduler.default_meal_windows),
    )
    tasks = [
        Task(
            id="study_1",
            title="自习（第1次）",
            date=target_date,
            duration_min=120,
            min_duration_min=60,
            preferred_period="day",
            tags=["study", "elastic_duration"],
        ),
        Task(
            id="study_2",
            title="自习（第2次）",
            date=target_date,
            duration_min=120,
            min_duration_min=60,
            preferred_period="day",
            tags=["study", "elastic_duration"],
        ),
        Task(
            id="parcel",
            title="取快递",
            date=target_date,
            duration_min=30,
        ),
        Task(
            id="run",
            title="跑步",
            date=target_date,
            duration_min=30,
        ),
        Task(
            id="mentor",
            title="和导师碰头",
            date=target_date,
            duration_min=120,
            earliest_start=datetime(2026, 8, 20, 18, 0, tzinfo=tz),
            latest_end=datetime(2026, 8, 21, 0, 0, tzinfo=tz),
            preferred_period="evening",
        ),
    ]

    result = Scheduler().schedule(
        user_id="quality_user",
        thread_id="quality_thread",
        tasks=tasks,
        preferences=UserPreferences(buffer_min=10),
        context=context,
    )
    scheduled = {
        item.task_id: item
        for item in result.plan.items
        if item.item_type == "task" and item.task_id
    }

    assert not result.unscheduled_task_ids
    assert set(scheduled) == {task.id for task in tasks}
    assert all(
        int(
            (scheduled[task_id].end_at - scheduled[task_id].start_at).total_seconds()
            // 60
        )
        == 120
        for task_id in ("study_1", "study_2")
    )
    assert min(scheduled["study_1"].start_at, scheduled["study_2"].start_at).hour < 12
    assert max(scheduled["study_1"].end_at, scheduled["study_2"].end_at).hour <= 18
    assert scheduled["mentor"].start_at.hour >= 18


@pytest.mark.asyncio
async def test_default_interval_is_counted_without_locations(tz):
    target_date = date(2026, 8, 21)
    now = datetime(2026, 8, 21, 13, 0, tzinfo=tz)
    context = await build_context(target_date, now, [])
    tasks = [
        Task(
            id="study",
            title="自习",
            date=target_date,
            duration_min=60,
            earliest_start=datetime(2026, 8, 21, 14, 0, tzinfo=tz),
        ),
        Task(
            id="club",
            title="社团活动",
            date=target_date,
            duration_min=120,
            depends_on=["study"],
        ),
    ]

    result = Scheduler().schedule(
        user_id="buffer_user",
        thread_id="buffer_thread",
        tasks=tasks,
        preferences=UserPreferences(),
        context=context,
    )
    validated, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=tasks,
        context=context,
    )

    assert not [issue for issue in issues if issue.severity == "error"]
    assert not [item for item in validated.items if item.item_type == "travel"]
    buffers = [item for item in validated.items if item.item_type == "buffer"]
    assert len(buffers) == 1
    assert int(
        (buffers[0].end_at - buffers[0].start_at).total_seconds() // 60
    ) == 15
    assert validated.metrics.buffer_minutes == 15
    assert validated.metrics.travel_minutes == 0


@pytest.mark.asyncio
async def test_user_reported_heat_moves_outdoor_exercise_after_hottest_hours(tz):
    target_date = date(2026, 8, 21)
    now = datetime(2026, 8, 21, 13, 0, tzinfo=tz)
    context = await build_context(target_date, now, [])
    context.enforce_weather = True
    context.outdoor_location_ids = {"track"}
    context.weather = [
        WeatherContext(
            date=target_date,
            period="day",
            condition="用户提醒天气较热",
            source=DataSource.USER,
        )
    ]
    tasks = [
        Task(
            id="run",
            title="跑步",
            date=target_date,
            duration_min=30,
            location_id="track",
            earliest_start=datetime(2026, 8, 21, 14, 0, tzinfo=tz),
            tags=["outdoor"],
        ),
        Task(
            id="club",
            title="社团活动",
            date=target_date,
            duration_min=120,
            earliest_start=datetime(2026, 8, 21, 14, 0, tzinfo=tz),
        ),
    ]

    result = Scheduler().schedule(
        user_id="hot_user",
        thread_id="hot_thread",
        tasks=tasks,
        preferences=UserPreferences(),
        context=context,
    )
    run = next(item for item in result.plan.items if item.task_id == "run")

    assert run.start_at.time() >= time(17, 0)
