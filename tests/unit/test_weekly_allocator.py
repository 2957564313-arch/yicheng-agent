from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.schemas.weekly import (
    DailyCapacity,
    DailyWindow,
    GoalStageCreate,
    WeeklyGoalCreate,
    WeeklyPlanCreateRequest,
    WeeklyPlanStatus,
)
from app.services.weekly_allocator import WeeklyAllocator


TZ = ZoneInfo("Asia/Shanghai")
WEEK_START = date(2026, 7, 27)


def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 27, hour, minute, tzinfo=TZ) + timedelta(
        days=day_offset
    )


def capacities(
    *,
    days: int = 5,
    start_hour: int = 18,
    end_hour: int = 21,
) -> list[DailyCapacity]:
    return [
        DailyCapacity(
            date=WEEK_START + timedelta(days=offset),
            windows=[
                DailyWindow(
                    start_at=at(offset, start_hour),
                    end_at=at(offset, end_hour),
                )
            ],
        )
        for offset in range(days)
    ]


def test_complex_week_respects_dependencies_deadlines_and_chunks():
    request = WeeklyPlanCreateRequest(
        user_id="weekly_user",
        campus_id="campus_demo",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title="课程设计",
                deadline=at(4, 22),
                total_duration_min=480,
                min_chunk_min=30,
                max_chunk_min=120,
                importance=5,
                stages=[
                    GoalStageCreate(
                        id="coding",
                        title="编码",
                        sequence=1,
                        duration_min=240,
                        min_chunk_min=60,
                    ),
                    GoalStageCreate(
                        id="testing",
                        title="测试",
                        sequence=2,
                        duration_min=120,
                        min_chunk_min=60,
                        depends_on_stage_ids=["coding"],
                    ),
                    GoalStageCreate(
                        id="report",
                        title="报告",
                        sequence=3,
                        duration_min=120,
                        min_chunk_min=60,
                        depends_on_stage_ids=["testing"],
                    ),
                ],
            ),
            WeeklyGoalCreate(
                title="论文阅读与汇报",
                deadline=at(2, 22),
                total_duration_min=180,
                min_chunk_min=60,
                max_chunk_min=120,
                importance=4,
            ),
            WeeklyGoalCreate(
                title="本周两次跑步",
                deadline=at(6, 21),
                total_duration_min=80,
                min_chunk_min=40,
                max_chunk_min=40,
                max_chunks_per_day=1,
                importance=2,
            ),
        ],
        capacities=capacities(days=7),
    )

    plan = WeeklyAllocator().allocate(
        request,
        now=at(0, 9),
    )

    assert plan.status == WeeklyPlanStatus.VALID
    assert plan.metrics.requested_duration_min == 740
    assert plan.metrics.allocated_duration_min == 740
    assert plan.metrics.unallocated_duration_min == 0
    assert not plan.issues
    assert all(
        item.allocated_duration_min <= 120
        for item in plan.allocations
    )

    course_goal = next(
        goal for goal in plan.goals if goal.title == "课程设计"
    )
    stages = {stage.title: stage for stage in course_goal.stages}
    by_stage = {
        title: [
            item
            for item in plan.allocations
            if item.stage_id == stage.id
        ]
        for title, stage in stages.items()
    }
    assert max(item.latest_end for item in by_stage["编码"]) <= min(
        item.earliest_start for item in by_stage["测试"]
    )
    assert max(item.latest_end for item in by_stage["测试"]) <= min(
        item.earliest_start for item in by_stage["报告"]
    )
    assert all(
        item.latest_end <= course_goal.deadline
        for item in plan.allocations
        if item.goal_id == course_goal.id
    )
    running_goal = next(
        goal for goal in plan.goals if goal.title == "本周两次跑步"
    )
    running_days = {
        item.date
        for item in plan.allocations
        if item.goal_id == running_goal.id
    }
    assert len(running_days) == 2
    assert course_goal.remaining_duration_min == 480


def test_shortage_is_reported_without_shrinking_or_hiding_goal():
    request = WeeklyPlanCreateRequest(
        user_id="shortage_user",
        campus_id="campus_demo",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title="完成报告",
                deadline=at(0, 20),
                total_duration_min=300,
                min_chunk_min=30,
                max_chunk_min=120,
                importance=5,
                hard_deadline=True,
            )
        ],
        capacities=capacities(days=1, start_hour=18, end_hour=20),
    )

    plan = WeeklyAllocator().allocate(request, now=at(0, 9))

    assert plan.status == WeeklyPlanStatus.INFEASIBLE
    assert plan.metrics.allocated_duration_min == 120
    assert plan.metrics.unallocated_duration_min == 180
    assert plan.goals[0].total_duration_min == 300
    assert plan.goals[0].remaining_duration_min == 300
    assert plan.issues[0].details["missing_min"] == 180


def test_non_splittable_goal_is_not_illegally_split():
    request = WeeklyPlanCreateRequest(
        user_id="single_block_user",
        campus_id="campus_demo",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title="完整模拟考试",
                deadline=at(1, 22),
                total_duration_min=90,
                splittable=False,
                importance=5,
            )
        ],
        capacities=[
            DailyCapacity(
                date=WEEK_START,
                windows=[
                    DailyWindow(
                        start_at=at(0, 18),
                        end_at=at(0, 19),
                    )
                ],
            ),
            DailyCapacity(
                date=WEEK_START + timedelta(days=1),
                windows=[
                    DailyWindow(
                        start_at=at(1, 18),
                        end_at=at(1, 19),
                    )
                ],
            ),
        ],
    )

    plan = WeeklyAllocator().allocate(request, now=at(0, 9))

    assert plan.status == WeeklyPlanStatus.INFEASIBLE
    assert plan.allocations == []
    assert plan.metrics.unallocated_duration_min == 90


def test_single_stage_goal_balances_across_available_days():
    request = WeeklyPlanCreateRequest(
        user_id="balanced_user",
        campus_id="campus_demo",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title="一周复习计划",
                deadline=at(4, 22),
                total_duration_min=360,
                min_chunk_min=60,
                max_chunk_min=120,
                max_chunks_per_day=2,
                importance=4,
            )
        ],
        capacities=capacities(days=5),
    )

    plan = WeeklyAllocator().allocate(request, now=at(0, 9))

    assert plan.status == WeeklyPlanStatus.VALID
    assert len({item.date for item in plan.allocations}) >= 3
    assert max(
        sum(
            item.allocated_duration_min
            for item in plan.allocations
            if item.date == target_date
        )
        for target_date in {item.date for item in plan.allocations}
    ) <= 120


def test_allocator_never_uses_time_before_now():
    request = WeeklyPlanCreateRequest(
        user_id="current_week_user",
        campus_id="campus_demo",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title="当天完成作业",
                deadline=at(0, 21),
                total_duration_min=60,
                min_chunk_min=60,
                importance=5,
            )
        ],
        capacities=[
            DailyCapacity(
                date=WEEK_START,
                windows=[
                    DailyWindow(
                        start_at=at(0, 8),
                        end_at=at(0, 10),
                    ),
                    DailyWindow(
                        start_at=at(0, 18),
                        end_at=at(0, 20),
                    ),
                ],
            )
        ],
    )

    plan = WeeklyAllocator().allocate(request, now=at(0, 16))

    assert plan.status == WeeklyPlanStatus.VALID
    assert plan.allocations[0].earliest_start == at(0, 18)


def test_cycle_in_stage_dependencies_is_rejected():
    request = WeeklyPlanCreateRequest(
        user_id="cycle_user",
        campus_id="campus_demo",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title="循环依赖任务",
                deadline=at(4, 22),
                total_duration_min=120,
                stages=[
                    GoalStageCreate(
                        id="a",
                        title="A",
                        duration_min=60,
                        depends_on_stage_ids=["b"],
                    ),
                    GoalStageCreate(
                        id="b",
                        title="B",
                        duration_min=60,
                        depends_on_stage_ids=["a"],
                    ),
                ],
            )
        ],
        capacities=capacities(),
    )

    with pytest.raises(ValueError, match="依赖存在循环"):
        WeeklyAllocator().allocate(request, now=at(0, 9))
