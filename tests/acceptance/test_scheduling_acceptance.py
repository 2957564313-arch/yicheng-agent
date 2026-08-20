"""Product acceptance for the core job: turning a request into a usable day.

These tests are deliberately written against the requirement, not against the
current implementation.  They take extraction as given — the model does that
part correctly — and hold the workflow to what a student would call a correct
answer.  A test here failing means the product is wrong, not that a detail
changed.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.schemas.task import Task, UserPreferences
from app.services.scheduler import Scheduler
from tests.acceptance.conftest import TARGET, at

LIBRARY = "library"
TRACK = "track"
OFFICE = "teaching_building_6"


def _study(index: int, **overrides) -> Task:
    """One self-study sitting as the model reports it: 2h ideal, 1h acceptable."""
    payload = {
        "id": f"study_{index}",
        "title": f"自习（第{index}次）",
        "date": TARGET,
        "duration_min": 120,
        "min_duration_min": 60,
        "location_id": LIBRARY,
        "importance": 4,
    }
    payload.update(overrides)
    return Task(**payload)


def _exercise(**overrides) -> Task:
    payload = {
        "id": "exercise",
        "title": "锻炼",
        "date": TARGET,
        "duration_min": 60,
        "location_id": TRACK,
        "importance": 3,
    }
    payload.update(overrides)
    return Task(**payload)


def _meeting(**overrides) -> Task:
    payload = {
        "id": "advisor",
        "title": "和导师碰头",
        "date": TARGET,
        "duration_min": 60,
        "location_id": OFFICE,
        "importance": 4,
    }
    payload.update(overrides)
    return Task(**payload)


def _schedule(tasks, context, preferences=None):
    return Scheduler().schedule(
        user_id="acceptance",
        thread_id="acceptance",
        tasks=tasks,
        preferences=preferences or UserPreferences(),
        context=context,
    )


def _placed(result) -> dict[str, tuple]:
    return {
        item.task_id: (item.start_at, item.end_at)
        for item in result.plan.items
        if item.item_type == "task" and item.task_id
    }


def _minutes(window) -> int:
    start_at, end_at = window
    return int((end_at - start_at).total_seconds() // 60)


@pytest.mark.asyncio
async def test_1_three_sittings_plus_exercise_and_meeting_all_fit(
    context_factory,
):
    """“今天自习3次，锻炼1小时，和导师碰头” — a whole free day fits all five."""
    context = await context_factory((LIBRARY, TRACK, OFFICE), now_hour=9)
    tasks = [_study(1), _study(2), _study(3), _exercise(), _meeting()]

    result = _schedule(tasks, context)
    placed = _placed(result)

    assert result.unscheduled_task_ids == [], "a free day must fit all five"
    assert len(placed) == 5
    for index in (1, 2, 3):
        assert _minutes(placed[f"study_{index}"]) >= 60


@pytest.mark.asyncio
async def test_2_short_day_shortens_sittings_instead_of_dropping_them(
    context_factory,
):
    """Asked at 16:00 there is no room for full sittings — shrink, don't drop."""
    context = await context_factory((LIBRARY, TRACK, OFFICE), now_hour=16)
    tasks = [_study(1), _study(2), _study(3), _exercise(), _meeting()]

    result = _schedule(tasks, context)
    placed = _placed(result)

    assert result.unscheduled_task_ids == [], (
        "a sitting may be shortened to its minimum, but must not be dropped"
    )
    for index in (1, 2, 3):
        assert _minutes(placed[f"study_{index}"]) >= 60


@pytest.mark.asyncio
async def test_3_narrow_window_task_is_not_blocked_by_a_flexible_one(
    context_factory,
):
    """A complete solution exists; task order must not be what decides."""
    context = await context_factory((LIBRARY,), now_hour=7)
    tasks = [
        Task(
            id="flexible",
            title="灵活任务",
            date=TARGET,
            duration_min=120,
            location_id=LIBRARY,
            earliest_start=at(8),
            latest_end=at(12),
            importance=3,
        ),
        Task(
            id="narrow",
            title="狭窄任务",
            date=TARGET,
            duration_min=120,
            location_id=LIBRARY,
            earliest_start=at(8),
            latest_end=at(10),
            importance=3,
        ),
    ]

    # No buffer between the two, otherwise the pair genuinely does not fit:
    # the narrow task can only run 08:00-10:00, and a 10-minute buffer would
    # push the flexible one to 10:10-12:10, past its 12:00 limit.
    result = _schedule(tasks, context, UserPreferences(buffer_min=0))

    assert result.unscheduled_task_ids == [], (
        "narrow 08:00-10:00 then flexible 10:00-12:00 is a complete solution"
    )
    placed = _placed(result)
    assert placed["narrow"][0].hour == 8
    assert placed["flexible"][0].hour == 10


@pytest.mark.asyncio
async def test_4_a_period_the_model_guessed_never_costs_a_task(
    context_factory,
):
    """Three 2h sittings cannot fit one afternoon; an inferred period yields."""
    context = await context_factory((LIBRARY, TRACK, OFFICE), now_hour=9)
    tasks = [
        _study(1, preferred_period="afternoon"),
        _study(2, preferred_period="afternoon"),
        _study(3, preferred_period="afternoon"),
        _exercise(preferred_period="evening"),
        _meeting(preferred_period="morning"),
    ]

    result = _schedule(tasks, context)

    assert result.unscheduled_task_ids == [], (
        "a guessed period is a preference; it must not delete a task"
    )


@pytest.mark.asyncio
async def test_5_a_period_the_user_stated_is_still_honoured(context_factory):
    """The escape hatch above must not weaken what the user actually said."""
    context = await context_factory((LIBRARY,), now_hour=7)
    tasks = [
        _study(
            1,
            preferred_period="evening",
            constraint_source="user",
            duration_min=120,
        )
    ]

    result = _schedule(tasks, context)
    placed = _placed(result)

    assert placed["study_1"][0].hour >= 18


@pytest.mark.asyncio
async def test_6_an_unknown_route_never_costs_a_task(context_factory):
    """A gap in the campus map is not a reason to refuse to plan."""
    context = await context_factory((LIBRARY,), now_hour=9)
    tasks = [
        _study(1),
        _meeting(location_id="unknown_place"),
        _exercise(location_id="another_unknown"),
    ]

    result = _schedule(tasks, context)

    assert result.unscheduled_task_ids == []
    assert result.missing_route_pairs, "the gap must still be reported"


# ---------------------------------------------------------------------------
# What a person would actually do with the day.  The tests above check that
# nothing is lost; these check that what comes back is worth following.
# ---------------------------------------------------------------------------


def _three_sittings_as_requested() -> list[Task]:
    """What the pipeline builds from “自习3次”, via the real expansion."""
    from app.nodes.understand import _expand_occurrences

    return _expand_occurrences(
        [
            Task(
                id="study",
                title="图书馆自习",
                date=TARGET,
                duration_min=120,
                min_duration_min=60,
                occurrence_count=3,
                location_id=LIBRARY,
                importance=4,
            )
        ]
    )


def _spans(result, prefix: str) -> list[tuple]:
    return sorted(
        (item.start_at, item.end_at)
        for item in result.plan.items
        if item.item_type == "task"
        and item.task_id
        and item.task_id.startswith(prefix)
    )


@pytest.mark.asyncio
async def test_7_a_long_day_leaves_room_to_eat(context_factory):
    """Nobody studies straight through lunch; the plan must leave the gap."""
    context = await context_factory((LIBRARY, TRACK, OFFICE), now_hour=9)
    tasks = [*_three_sittings_as_requested(), _exercise(), _meeting()]

    result = _schedule(tasks, context)

    lunch_start = at(12, 0)
    lunch_end = at(12, 45)
    covering = [
        item
        for item in result.plan.items
        if item.item_type == "task"
        and item.start_at < lunch_end
        and item.end_at > lunch_start
    ]
    assert not covering, (
        "12:00-12:45 must stay free to eat, "
        f"but {[item.title for item in covering]} runs through it"
    )


@pytest.mark.asyncio
async def test_8_repeated_sittings_are_spread_across_the_day(context_factory):
    """Three sittings asked for separately are not one six-hour block."""
    context = await context_factory((LIBRARY, TRACK, OFFICE), now_hour=9)
    tasks = [*_three_sittings_as_requested(), _exercise(), _meeting()]

    result = _schedule(tasks, context)
    sittings = _spans(result, "study_")

    assert len(sittings) == 3
    for (_, earlier_end), (later_start, _) in pairwise(sittings):
        gap = int((later_start - earlier_end).total_seconds() // 60)
        assert gap >= 60, (
            f"only {gap} minutes between sittings — that is one long block"
        )


# ---------------------------------------------------------------------------
# Constraints in combination: a synced timetable, the weather and saved
# preferences all pulling at once.  The order they must resolve in is
# locked commitments, then what the user asked for now, then coverage,
# then preferences, then travel.
# ---------------------------------------------------------------------------


def _locked_course() -> Task:
    """A class synced from 杭电助手: the one thing that may never move."""
    return Task(
        id="course_hduhelp",
        title="数据结构",
        date=TARGET,
        duration_min=120,
        location_id=OFFICE,
        fixed_start=at(14),
        fixed_end=at(16),
        flexibility="locked",
        importance=5,
        constraint_source="user",
        tags=["course", "verified_timetable"],
    )


def _rain_from(hour: int):
    from app.schemas.common import DataSource
    from app.schemas.context import WeatherContext

    return WeatherContext(
        date=TARGET,
        period="afternoon",
        condition="小雨",
        rain_probability=0.8,
        risk_start_at=at(hour),
        source=DataSource.ESTIMATED,
    )


@pytest.mark.asyncio
async def test_9_a_synced_class_is_never_moved_or_overlapped(context_factory):
    context = await context_factory((LIBRARY, TRACK, OFFICE), now_hour=9)
    course = _locked_course()
    tasks = [course, *_three_sittings_as_requested(), _exercise()]

    result = _schedule(tasks, context)
    placed = _placed(result)

    assert placed["course_hduhelp"] == (at(14), at(16))
    for task_id, (start_at, end_at) in placed.items():
        if task_id == "course_hduhelp":
            continue
        assert end_at <= at(14) or start_at >= at(16), (
            f"{task_id} overlaps the synced class"
        )


@pytest.mark.asyncio
async def test_10_rain_moves_outdoor_work_but_never_deletes_it(
    context_factory,
):
    """Rain all afternoon is a reason to go early, not to skip exercising."""
    context = await context_factory((LIBRARY, TRACK, OFFICE), now_hour=9)
    context.enforce_weather = True
    context.outdoor_location_ids = {TRACK}
    context.weather = [_rain_from(13)]

    tasks = [*_three_sittings_as_requested(), _exercise()]
    result = _schedule(tasks, context)
    placed = _placed(result)

    assert "exercise" in placed, "exercise must not vanish because of rain"
    assert placed["exercise"][1] <= at(13), "and it should land before the rain"


@pytest.mark.asyncio
async def test_11_all_day_rain_still_produces_a_plan(context_factory):
    """When every slot is wet, say so — do not hand back an empty day."""
    context = await context_factory((LIBRARY, TRACK, OFFICE), now_hour=9)
    context.enforce_weather = True
    context.outdoor_location_ids = {TRACK}
    context.weather = [_rain_from(8)]

    tasks = [*_three_sittings_as_requested(), _exercise()]
    result = _schedule(tasks, context)

    assert "exercise" in _placed(result), (
        "an unavoidable forecast must not silently delete the task"
    )
