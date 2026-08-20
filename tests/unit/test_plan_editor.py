"""A follow-up must change what was asked and nothing else.

“把自习换到下午，其他照旧” has to leave the rest of the day standing. These
tests pin that guarantee to the deterministic applier, so it holds whatever
the model happens to return.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.schemas.plan_edit import PlanEdit, PlanEditOperation
from app.schemas.task import Task
from app.services.plan_editor import apply_plan_edit, match_task

TZ = ZoneInfo("Asia/Shanghai")
TODAY = date(2026, 8, 21)


def _day() -> list[Task]:
    return [
        Task(
            id="course",
            title="数据结构",
            date=TODAY,
            duration_min=120,
            fixed_start=datetime(2026, 8, 21, 8, 0, tzinfo=TZ),
            fixed_end=datetime(2026, 8, 21, 10, 0, tzinfo=TZ),
            flexibility="locked",
        ),
        Task(id="study", title="图书馆自习", date=TODAY, duration_min=120),
        Task(id="parcel", title="取快递", date=TODAY, duration_min=30),
        Task(id="run", title="跑步", date=TODAY, duration_min=45),
    ]


def _apply(edit: PlanEdit, tasks=None):
    return apply_plan_edit(tasks=tasks or _day(), edit=edit, timezone=TZ)


def test_moving_one_task_keeps_every_other_arrangement():
    edit = PlanEdit(
        operations=[
            PlanEditOperation(
                action="move",
                task_ref="图书馆自习",
                target_period="afternoon",
            )
        ]
    )
    tasks, unresolved = _apply(edit)

    assert [task.id for task in tasks] == ["course", "study", "parcel", "run"]
    assert not unresolved
    study = next(task for task in tasks if task.id == "study")
    assert study.preferred_period == "afternoon"
    assert study.earliest_start.hour == 13
    # Said out loud by the student, so the planner must honour it.
    assert study.constraint_source == "user"


def test_a_locked_class_is_untouched_by_an_edit_to_something_else():
    tasks, _ = _apply(
        PlanEdit(
            operations=[
                PlanEditOperation(
                    action="move", task_ref="跑步", target_period="evening"
                )
            ]
        )
    )
    course = next(task for task in tasks if task.id == "course")
    assert course.flexibility.value == "locked"
    assert course.fixed_start == datetime(2026, 8, 21, 8, 0, tzinfo=TZ)


def test_moving_a_task_to_another_day_really_changes_the_date():
    tasks, _ = _apply(
        PlanEdit(
            operations=[
                PlanEditOperation(
                    action="move",
                    task_ref="跑步",
                    target_date=date(2026, 8, 22),
                )
            ]
        )
    )
    run = next(task for task in tasks if task.id == "run")
    assert run.date == date(2026, 8, 22)
    # Yesterday's anchors must not follow it across the day boundary.
    assert run.earliest_start is None or run.earliest_start.date() == run.date


def test_shortening_states_a_length_that_may_not_be_compressed_again():
    tasks, _ = _apply(
        PlanEdit(
            operations=[
                PlanEditOperation(
                    action="shorten", task_ref="图书馆自习", duration_min=60
                )
            ]
        )
    )
    study = next(task for task in tasks if task.id == "study")
    assert study.duration_min == 60
    assert study.duration_source == "explicit"
    assert study.shortest_acceptable_min() == 60


def test_removing_a_task_also_clears_what_depended_on_it():
    day = _day()
    day[2] = day[2].model_copy(update={"depends_on": ["study"]})
    tasks, _ = _apply(
        PlanEdit(
            operations=[
                PlanEditOperation(action="remove", task_ref="图书馆自习")
            ]
        ),
        day,
    )
    assert [task.id for task in tasks] == ["course", "parcel", "run"]
    parcel = next(task for task in tasks if task.id == "parcel")
    assert parcel.depends_on == []


def test_an_unrecognised_reference_is_reported_not_guessed():
    tasks, unresolved = _apply(
        PlanEdit(
            operations=[
                PlanEditOperation(
                    action="move", task_ref="打篮球", target_period="evening"
                )
            ]
        )
    )
    assert len(tasks) == 4, "nothing may be dropped over a reference we missed"
    assert unresolved and "打篮球" in unresolved[0]


def test_adding_a_task_leaves_the_existing_ones_alone():
    tasks, _ = _apply(
        PlanEdit(
            operations=[
                PlanEditOperation(
                    action="add",
                    title="和导师碰头",
                    duration_min=60,
                    target_period="morning",
                )
            ]
        )
    )
    assert len(tasks) == 5
    added = tasks[-1]
    assert added.title == "和导师碰头"
    assert added.date == TODAY
    assert added.earliest_start.hour == 8


@pytest.mark.parametrize(
    "reference,expected",
    [("study", "study"), ("图书馆自习", "study"), ("自习", "study"), ("取快递", "parcel")],
)
def test_tasks_can_be_named_the_way_a_student_would(reference, expected):
    assert match_task(reference, _day()).id == expected


def test_an_ambiguous_name_is_not_resolved_by_guessing():
    day = [
        Task(id="a", title="自习一", date=TODAY, duration_min=60),
        Task(id="b", title="自习二", date=TODAY, duration_min=60),
    ]
    assert match_task("自习", day) is None
