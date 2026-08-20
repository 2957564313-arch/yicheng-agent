"""Regression tests for reading what the student actually asked for.

Each case here produced a wrong plan against the real app: a task dropped
without a word, a meal moved eight hours away from the task it was supposed to
follow, a request that yielded no tasks at all, and an invented class block
built out of a time reference.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from app.services.requirement_parser import RuleBasedRequirementParser

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TARGET = date(2026, 8, 21)


@pytest.fixture
def parser() -> RuleBasedRequirementParser:
    """Configured the way the container builds it, so class periods resolve."""
    return RuleBasedRequirementParser(
        "Asia/Shanghai",
        DATA_DIR / "class_periods.json",
    )


@pytest.fixture
def now(tz) -> datetime:
    return datetime(2026, 8, 20, 7, 30, tzinfo=tz)


def _tasks(parser, query: str, now: datetime):
    return parser.parse(query=query, now=now, old_plan=None).tasks


def _by_id(tasks) -> dict:
    return {task.id: task for task in tasks}


@pytest.mark.parametrize(
    "query",
    [
        "明天下午3点前把快递取了",
        "明天把快递拿一下",
        "明天领个包裹",
        "明天去驿站",
        "明天去快递站",
        "明天去快递点",
        "明天取件",
    ],
)
def test_parcel_pickup_survives_ordinary_phrasing(parser, now, query):
    """A pickup used to vanish unless it was worded “取快递”."""
    assert "parcel" in _by_id(_tasks(parser, query, now))


def test_parcel_deadline_is_kept(parser, now):
    parcel = _by_id(_tasks(parser, "明天下午3点前把快递取了", now))["parcel"]
    assert parcel.deadline is not None
    assert parcel.deadline.hour == 15


def test_midday_meal_is_not_moved_to_the_evening(parser, now):
    tasks = _by_id(_tasks(parser, "明天白天安排自习，但是中午要留时间吃饭", now))
    assert "lunch" in tasks
    assert tasks["lunch"].earliest_start.hour == 11
    assert tasks["lunch"].latest_end.hour == 14


def test_unqualified_meal_keeps_a_wide_window(parser, now):
    """“然后去食堂吃饭” must be able to follow a morning task."""
    tasks = _by_id(_tasks(parser, "明天自习两小时，然后去食堂吃饭", now))
    meal = tasks["meal"]
    assert meal.preferred_period is None
    assert meal.earliest_start.hour == 11
    assert meal.depends_on == ["study"]


def test_explicit_dinner_still_means_the_evening(parser, now):
    dinner = _by_id(_tasks(parser, "明天晚上吃饭", now))["dinner"]
    assert dinner.preferred_period == "evening"
    assert dinner.earliest_start.hour == 17


@pytest.mark.parametrize(
    "query",
    ["明天白天把作业写完", "明天把作业做完", "明天要写作业"],
)
def test_assignment_is_recognised_either_way_round(parser, now, query):
    assert "assignment" in _by_id(_tasks(parser, query, now))


def test_class_period_reference_anchors_without_inventing_a_class(parser, now):
    """“第三节课后去自习” says when to start, not that a class needs planning."""
    tasks = _tasks(parser, "明天上午第三节课后去图书馆自习两小时", now)
    assert not [task for task in tasks if task.id.startswith("course_")]
    study = _by_id(tasks)["study"]
    # The third period ends at 10:45.
    assert study.earliest_start.hour == 10
    assert study.earliest_start.minute == 45


def test_a_stated_class_is_still_planned_with_a_sane_title(parser, now):
    tasks = _tasks(parser, "明天第三节课在六教", now)
    (course,) = [task for task in tasks if task.id.startswith("course_")]
    assert course.title == "第3节课程"
    assert course.flexibility.value == "fixed"


def test_a_named_course_keeps_its_name(parser, now):
    tasks = _tasks(parser, "明天第1-2节有高等数学", now)
    (course,) = [task for task in tasks if task.id.startswith("course_")]
    assert course.title == "高等数学"


def test_named_task_is_scheduled_between_the_sittings(parser, now):
    """“分两段，中间吃个午饭” puts the meal between, not after, the sittings."""
    tasks = _by_id(_tasks(parser, "明天自习4小时分两段，中间吃个午饭", now))
    assert tasks["lunch"].depends_on == ["study_seg1"]
    assert tasks["study_seg2"].depends_on == ["lunch"]


def test_middle_task_removes_the_sitting_gap(parser, now):
    """The meal already separates the sittings, so no extra dead time."""
    from app.services.scheduler import Scheduler

    tasks = _by_id(_tasks(parser, "明天自习4小时分两段，中间吃个午饭", now))
    assert Scheduler._required_dependency_gap(tasks["study_seg2"]) == 0
    plain = _by_id(_tasks(parser, "明天自习4小时分两段", now))
    assert (
        Scheduler._required_dependency_gap(plain["study_seg2"])
        == Scheduler.split_segment_gap_min
    )


def test_returning_to_the_dormitory_is_a_task(parser, now):
    tasks = _by_id(_tasks(parser, "明天自习两小时，最后回宿舍", now))
    assert tasks["return_dorm"].location_raw == "学生公寓"
    assert tasks["return_dorm"].depends_on == ["study"]


def test_narrated_order_is_kept_for_every_task_kind(parser, now):
    """A task id missing from TASK_KEYWORDS used to sort silently to the end."""
    tasks = _tasks(parser, "明天自习两小时，然后去食堂吃饭，最后回宿舍", now)
    assert [task.id for task in tasks] == ["study", "meal", "return_dorm"]


@pytest.mark.parametrize(
    "query,expected_id",
    [
        ("明天回宿舍洗澡", "bath"),
        ("明天回宿舍洗衣服", "laundry"),
        ("明天下午回宿舍休息", "rest"),
    ],
)
def test_going_back_to_the_dorm_to_do_something_is_one_task(
    parser,
    now,
    query,
    expected_id,
):
    tasks = _by_id(_tasks(parser, query, now))
    assert "return_dorm" not in tasks
    assert expected_id in tasks


def test_every_built_task_id_is_known_to_the_ordering_map():
    """Ordering scores an unknown id as “not mentioned”; keep the map complete."""
    from app.services.requirement_parser import COMMON_TASK_SPECS, TASK_KEYWORDS

    assert {spec.id for spec in COMMON_TASK_SPECS} <= set(TASK_KEYWORDS)
