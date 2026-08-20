"""Regression tests for honouring the time of day the user actually asked for.

These cover the two failures behind “我要白天自习，给我安排晚上，分两段也没法搞”:
a period phrase that the parser did not know, and a request to spread one task
over several sittings that the planner collapsed back into one long block.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.providers.campus_rules import CampusRulesRepository
from app.providers.location_repository import LocationRepository
from app.providers.route_static import StaticRouteProvider
from app.schemas.task import Task, UserPreferences
from app.services.requirement_parser import RuleBasedRequirementParser
from app.services.scheduler import PlanningContext, Scheduler

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TARGET = date(2026, 8, 21)


@pytest.fixture
def parser() -> RuleBasedRequirementParser:
    """Configured the way the container builds it, class periods included."""
    return RuleBasedRequirementParser(
        "Asia/Shanghai",
        DATA_DIR / "class_periods.json",
    )


@pytest.fixture
def now(tz: ZoneInfo) -> datetime:
    return datetime(2026, 8, 20, 20, 0, tzinfo=tz)


def _study_tasks(parser, query: str, now: datetime) -> list[Task]:
    return parser.parse(query=query, now=now, old_plan=None).tasks


def test_daytime_phrase_bounds_the_task_to_the_day(parser, now, tz):
    (study,) = _study_tasks(parser, "明天白天自习3小时", now)
    assert study.preferred_period == "day"
    assert study.duration_min == 180
    # “白天” must rule out an evening slot without picking a half-day.
    assert study.latest_end == datetime(2026, 8, 21, 18, 0, tzinfo=tz)


def test_half_day_phrase_still_wins_over_daytime(parser, now, tz):
    (study,) = _study_tasks(parser, "明天上午自习两小时", now)
    assert study.preferred_period == "morning"
    assert study.latest_end == datetime(2026, 8, 21, 12, 0, tzinfo=tz)


def test_explicit_clock_anchor_outranks_the_period_phrase(parser, now):
    (study,) = _study_tasks(parser, "明天下午2点开始自习两小时", now)
    assert study.preferred_period is None
    assert study.earliest_start.hour == 14


def test_split_request_produces_separate_sittings(parser, now):
    tasks = _study_tasks(parser, "明天自习4小时，分成两段", now)
    assert [task.duration_min for task in tasks] == [120, 120]
    assert [task.id for task in tasks] == ["study_seg1", "study_seg2"]
    assert tasks[1].depends_on == ["study_seg1"]
    assert all("split_segment" in task.tags for task in tasks)


def test_named_periods_are_assigned_to_each_sitting(parser, now):
    tasks = _study_tasks(parser, "明天上午下午各自习两小时", now)
    assert [task.preferred_period for task in tasks] == ["morning", "afternoon"]
    # “各两小时” states the length of one sitting, not the total.
    assert [task.duration_min for task in tasks] == [120, 120]


def test_split_is_refused_when_the_sittings_would_be_too_short(parser, now):
    tasks = _study_tasks(parser, "明天自习40分钟分两段", now)
    assert [task.id for task in tasks] == ["study"]
    assert tasks[0].duration_min == 40


async def _context(tz: ZoneInfo, now: datetime) -> PlanningContext:
    locations = LocationRepository(DATA_DIR / "locations.json")
    routes = StaticRouteProvider(DATA_DIR / "travel_times.json", locations)
    rules = CampusRulesRepository(
        DATA_DIR / "opening_hours.json",
        DATA_DIR / "campus_rules.json",
        DATA_DIR / "class_periods.json",
        "Asia/Shanghai",
    )
    ids = ("library", "teaching_building_6")
    travel = {
        (origin, destination): await routes.get_route(origin, destination)
        for origin in ids
        for destination in ids
        if origin != destination
    }
    return PlanningContext(
        target_date=TARGET,
        timezone=tz,
        now=now,
        travel=travel,
        opening_windows={
            location: rules.opening_windows(location, TARGET)
            for location in ids
        },
    )


def _classes(tz: ZoneInfo) -> list[Task]:
    return [
        Task(
            id="class1",
            title="高等数学",
            date=TARGET,
            duration_min=100,
            location_id="teaching_building_6",
            fixed_start=datetime(2026, 8, 21, 8, 0, tzinfo=tz),
            fixed_end=datetime(2026, 8, 21, 9, 40, tzinfo=tz),
            flexibility="fixed",
        ),
        Task(
            id="class2",
            title="大学物理",
            date=TARGET,
            duration_min=100,
            location_id="teaching_building_6",
            fixed_start=datetime(2026, 8, 21, 13, 30, tzinfo=tz),
            fixed_end=datetime(2026, 8, 21, 15, 10, tzinfo=tz),
            flexibility="fixed",
        ),
    ]


def _placed(result, prefix: str) -> list[tuple[datetime, datetime]]:
    return [
        (item.start_at, item.end_at)
        for item in result.plan.items
        if item.task_id and item.task_id.startswith(prefix)
    ]


@pytest.mark.asyncio
async def test_free_morning_beats_a_shorter_walk_in_the_afternoon(
    parser,
    now,
    tz,
):
    """A movable task must not drift late just to save one leg of a trip."""
    context = await _context(tz, now)
    study = Task(
        id="study",
        title="图书馆自习",
        date=TARGET,
        duration_min=180,
        location_id="library",
        earliest_start=datetime(2026, 8, 21, 8, 0, tzinfo=tz),
        latest_end=datetime(2026, 8, 21, 22, 30, tzinfo=tz),
        importance=5,
    )
    result = Scheduler().schedule(
        user_id="u",
        thread_id="t",
        tasks=[*_classes(tz), study],
        preferences=UserPreferences(),
        context=context,
    )
    ((start_at, _),) = _placed(result, "study")
    assert start_at.hour < 12


@pytest.mark.asyncio
async def test_split_sittings_are_scheduled_apart(parser, now, tz):
    context = await _context(tz, now)
    tasks = [
        task.model_copy(update={"location_id": "library"})
        for task in _study_tasks(parser, "明天白天自习4小时，分成两段", now)
    ]
    result = Scheduler().schedule(
        user_id="u",
        thread_id="t",
        tasks=[*_classes(tz), *tasks],
        preferences=UserPreferences(),
        context=context,
    )
    assert result.unscheduled_task_ids == []
    placed = _placed(result, "study_seg")
    assert len(placed) == 2
    (_, first_end), (second_start, second_end) = placed
    assert second_start - first_end >= timedelta(
        minutes=Scheduler.split_segment_gap_min
    )
    # Both sittings stay inside the daytime window the user asked for.
    assert second_end.hour < 18
