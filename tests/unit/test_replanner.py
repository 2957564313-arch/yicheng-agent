from __future__ import annotations

from datetime import date, datetime

import pytest

from app.schemas.common import PlanStatus, TaskFlexibility
from app.schemas.plan import Plan, PlanItem, PlanMetrics
from app.schemas.task import Task, UserPreferences
from app.services.replanner import Replanner
from app.services.validator import PlanValidator
from tests.unit.test_scheduler import build_context


@pytest.mark.asyncio
async def test_replanner_preserves_locked_run(tz):
    target_date = date(2026, 7, 24)
    now = datetime(2026, 7, 24, 12, 0, tzinfo=tz)
    old_plan = Plan(
        id="plan_initial",
        user_id="demo_user",
        thread_id="thread_replan",
        date=target_date,
        status=PlanStatus.VALID,
        version=1,
        items=[
            PlanItem(
                id="old_lab",
                task_id="lab",
                item_type="task",
                title="实验课",
                start_at=datetime(2026, 7, 24, 14, 0, tzinfo=tz),
                end_at=datetime(2026, 7, 24, 16, 0, tzinfo=tz),
                location_id="laboratory",
            ),
            PlanItem(
                id="old_study",
                task_id="study",
                item_type="task",
                title="自习",
                start_at=datetime(2026, 7, 24, 16, 20, tzinfo=tz),
                end_at=datetime(2026, 7, 24, 18, 20, tzinfo=tz),
                location_id="library",
            ),
            PlanItem(
                id="old_run",
                task_id="run",
                item_type="task",
                title="跑步",
                start_at=datetime(2026, 7, 24, 20, 0, tzinfo=tz),
                end_at=datetime(2026, 7, 24, 20, 40, tzinfo=tz),
                location_id="track",
            ),
        ],
        metrics=PlanMetrics(),
        created_at=datetime(2026, 7, 23, 20, 0, tzinfo=tz),
    )
    tasks = [
        Task(
            id="lab",
            title="实验课",
            date=target_date,
            duration_min=120,
            location_id="laboratory",
            fixed_start=datetime(2026, 7, 24, 15, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 17, 0, tzinfo=tz),
            flexibility=TaskFlexibility.FIXED,
        ),
        Task(
            id="study",
            title="自习",
            date=target_date,
            duration_min=120,
            location_id="library",
            earliest_start=datetime(2026, 7, 24, 13, 0, tzinfo=tz),
            latest_end=datetime(2026, 7, 24, 20, 0, tzinfo=tz),
        ),
        Task(
            id="run",
            title="跑步",
            date=target_date,
            duration_min=40,
            location_id="track",
            fixed_start=datetime(2026, 7, 24, 20, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 20, 40, tzinfo=tz),
            flexibility=TaskFlexibility.LOCKED,
        ),
    ]
    context = await build_context(
        target_date,
        now,
        [
            ("laboratory", "library"),
            ("library", "track"),
        ],
        old_plan=old_plan,
    )
    result = Replanner().replan(
        user_id="demo_user",
        thread_id="thread_replan",
        tasks=tasks,
        preferences=UserPreferences(locked_task_ids=["run"]),
        context=context,
        old_plan=old_plan,
    )
    plan, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=tasks,
        context=context,
    )

    run = next(item for item in plan.items if item.task_id == "run")
    study = next(item for item in plan.items if item.task_id == "study")
    assert run.start_at == datetime(2026, 7, 24, 20, 0, tzinfo=tz)
    assert study.start_at >= datetime(2026, 7, 24, 17, 20, tzinfo=tz)
    assert not [issue for issue in issues if issue.severity == "error"]
    assert plan.metrics.preservation_rate is not None
    assert plan.metrics.preservation_rate > 0


@pytest.mark.asyncio
async def test_replanner_minimizes_moved_tasks_globally(tz):
    """A new fixed block must not trigger a greedy two-task cascade."""

    target_date = date(2026, 7, 24)
    now = datetime(2026, 7, 23, 20, 0, tzinfo=tz)
    old_plan = Plan(
        id="plan_before_fixed_block",
        user_id="demo_user",
        thread_id="thread_minimum_disruption",
        date=target_date,
        status=PlanStatus.VALID,
        version=1,
        items=[
            PlanItem(
                id="old_a",
                task_id="a",
                item_type="task",
                title="Task A",
                start_at=datetime(2026, 7, 24, 10, 0, tzinfo=tz),
                end_at=datetime(2026, 7, 24, 11, 0, tzinfo=tz),
            ),
            PlanItem(
                id="old_b",
                task_id="b",
                item_type="task",
                title="Task B",
                start_at=datetime(2026, 7, 24, 11, 0, tzinfo=tz),
                end_at=datetime(2026, 7, 24, 12, 0, tzinfo=tz),
            ),
        ],
        metrics=PlanMetrics(),
        created_at=now,
    )
    tasks = [
        Task(
            id="new_fixed",
            title="New fixed block",
            date=target_date,
            duration_min=60,
            fixed_start=datetime(2026, 7, 24, 10, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 11, 0, tzinfo=tz),
            flexibility=TaskFlexibility.FIXED,
        ),
        Task(
            id="a",
            title="Task A",
            date=target_date,
            duration_min=60,
            earliest_start=datetime(2026, 7, 24, 10, 0, tzinfo=tz),
            latest_end=datetime(2026, 7, 24, 13, 0, tzinfo=tz),
            importance=5,
        ),
        Task(
            id="b",
            title="Task B",
            date=target_date,
            duration_min=60,
            earliest_start=datetime(2026, 7, 24, 10, 0, tzinfo=tz),
            latest_end=datetime(2026, 7, 24, 13, 0, tzinfo=tz),
            importance=4,
        ),
    ]
    context = await build_context(
        target_date,
        now,
        [],
        old_plan=old_plan,
    )
    result = Replanner().replan(
        user_id="demo_user",
        thread_id="thread_minimum_disruption",
        tasks=tasks,
        preferences=UserPreferences(buffer_min=0),
        context=context,
        old_plan=old_plan,
    )
    plan, issues = PlanValidator().validate(
        plan=result.plan,
        tasks=tasks,
        context=context,
    )

    by_task = {
        item.task_id: item
        for item in plan.items
        if item.item_type == "task"
    }
    assert by_task["b"].start_at == datetime(
        2026,
        7,
        24,
        11,
        0,
        tzinfo=tz,
    )
    assert by_task["a"].start_at == datetime(
        2026,
        7,
        24,
        12,
        0,
        tzinfo=tz,
    )
    assert not [issue for issue in issues if issue.severity == "error"]
    assert plan.metrics.moved_task_count == 1
    assert plan.metrics.total_shift_minutes == 120
    assert plan.metrics.preservation_rate == 0.5
