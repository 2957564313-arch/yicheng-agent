from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.repositories.database import Database
from app.repositories.weekly import WeeklyPlanRepository
from app.schemas.weekly import (
    AllocationStatus,
    DailyCapacity,
    DailyWindow,
    GoalStageCreate,
    WeeklyGoalCreate,
    WeeklyPlanCreateRequest,
    WeeklyPlanStatus,
    WeeklyTriggerType,
)
from app.services.weekly_allocator import WeeklyAllocator
from app.services.weekly_replanner import WeeklyReplanner

TZ = ZoneInfo("Asia/Shanghai")
WEEK_START = date(2026, 7, 27)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 27 + day, hour, minute, tzinfo=TZ)


def capacity(
    day: int,
    start_hour: int,
    end_hour: int,
    *,
    start_minute: int = 0,
    end_minute: int = 0,
) -> DailyCapacity:
    return DailyCapacity(
        date=WEEK_START.fromordinal(WEEK_START.toordinal() + day),
        windows=[
            DailyWindow(
                start_at=at(day, start_hour, start_minute),
                end_at=at(day, end_hour, end_minute),
            )
        ],
    )


def one_stage_baseline(
    *,
    duration: int,
    capacities: list[DailyCapacity],
    deadline: datetime | None = None,
    min_chunk: int = 60,
    max_chunk: int = 60,
    max_chunks_per_day: int = 1,
):
    request = WeeklyPlanCreateRequest(
        user_id="rolling_user",
        campus_id="hdu_xiasha",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title="课程设计",
                deadline=deadline or at(4, 22),
                total_duration_min=duration,
                min_chunk_min=min_chunk,
                max_chunk_min=max_chunk,
                max_chunks_per_day=max_chunks_per_day,
            )
        ],
        capacities=capacities,
    )
    return WeeklyAllocator().allocate(request, now=at(0, 8))


def exact_interval(allocation) -> tuple[datetime, datetime]:
    start = allocation.preferred_start_at or allocation.earliest_start
    end = allocation.preferred_end_at or (
        start + timedelta(minutes=allocation.allocated_duration_min)
    )
    return start, end


def test_rollover_freezes_completed_and_started_then_moves_only_invalid_block():
    baseline = one_stage_baseline(
        duration=180,
        capacities=[
            capacity(0, 9, 10),
            capacity(1, 9, 10),
            capacity(2, 9, 10),
        ],
    )
    baseline.allocations[0].status = AllocationStatus.COMPLETED
    baseline.goals[0].remaining_duration_min = 120
    baseline.goals[0].stages[0].remaining_duration_min = 120
    original_intervals = {
        allocation.id: exact_interval(allocation)
        for allocation in baseline.allocations
    }

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[
            capacity(0, 9, 10),
            capacity(1, 9, 10),
            capacity(2, 10, 11),
        ],
        trigger=WeeklyTriggerType.DAILY_ROLLOVER,
        now=at(1, 9, 30),
    )

    intervals = [exact_interval(item) for item in plan.allocations]
    assert original_intervals[baseline.allocations[0].id] in intervals
    assert original_intervals[baseline.allocations[1].id] in intervals
    assert original_intervals[baseline.allocations[2].id] not in intervals
    assert (at(2, 10), at(2, 11)) in intervals
    assert plan.version == baseline.version + 1
    assert plan.baseline_plan_id == baseline.id
    assert plan.trigger_type == WeeklyTriggerType.DAILY_ROLLOVER
    assert plan.metrics.moved_allocation_count == 1
    assert plan.metrics.preservation_rate == 0.6667
    assert plan.metrics.requested_duration_min == 120
    assert plan.metrics.unallocated_duration_min == 0
    assert plan.status == WeeklyPlanStatus.VALID


def test_valid_future_blocks_are_retained_around_one_changed_capacity():
    baseline = one_stage_baseline(
        duration=180,
        capacities=[
            capacity(0, 9, 10),
            capacity(1, 9, 10),
            capacity(2, 9, 10),
        ],
    )
    changed = baseline.allocations[1]
    preserved = {
        exact_interval(baseline.allocations[0]),
        exact_interval(baseline.allocations[2]),
    }

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[
            capacity(0, 9, 10),
            capacity(1, 10, 11),
            capacity(2, 9, 10),
        ],
        trigger=WeeklyTriggerType.FIXED_EVENT_CHANGED,
        now=at(0, 8),
        invalidated_allocation_ids={changed.id},
    )

    intervals = {exact_interval(item) for item in plan.allocations}
    assert preserved <= intervals
    assert exact_interval(changed) not in intervals
    assert (at(1, 10), at(1, 11)) in intervals
    assert plan.metrics.moved_allocation_count == 1
    assert plan.metrics.preservation_rate == 0.6667
    assert plan.status == WeeklyPlanStatus.VALID
    replacement = next(
        item
        for item in plan.allocations
        if item.source_allocation_id == changed.id
    )
    assert replacement.lineage_id == changed.lineage_id


def test_expired_partial_block_rolls_over_only_its_remaining_duration():
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(0, 9, 10)],
    )
    expired = baseline.allocations[0]
    expired.completed_duration_min = 20
    expired.status = AllocationStatus.SCHEDULED
    baseline.goals[0].remaining_duration_min = 40
    baseline.goals[0].stages[0].remaining_duration_min = 40

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[capacity(1, 9, 10)],
        trigger=WeeklyTriggerType.TASK_INCOMPLETE,
        now=at(0, 11),
        invalidated_allocation_ids={expired.id},
    )

    assert len(plan.allocations) == 1
    replacement = plan.allocations[0]
    assert exact_interval(replacement) == (at(1, 9), at(1, 9, 40))
    assert replacement.allocated_duration_min == 40
    assert replacement.completed_duration_min == 0
    assert replacement.source_allocation_id == expired.id
    assert replacement.lineage_id == expired.lineage_id
    assert plan.metrics.requested_duration_min == 40
    assert plan.metrics.allocated_duration_min == 40
    assert plan.metrics.unallocated_duration_min == 0
    assert plan.metrics.moved_allocation_count == 1
    assert plan.status == WeeklyPlanStatus.VALID


def test_unknown_invalidated_allocation_id_is_rejected():
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(0, 9, 10)],
    )

    with pytest.raises(
        ValueError,
        match="待失效的周计划块不存在：missing-allocation",
    ):
        WeeklyReplanner().replan(
            baseline=baseline,
            capacities=[capacity(0, 9, 10)],
            trigger=WeeklyTriggerType.FIXED_EVENT_CHANGED,
            now=at(0, 8),
            invalidated_allocation_ids={"missing-allocation"},
        )


def test_locked_block_is_never_moved_even_when_capacity_disappears():
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(1, 19, 20)],
    )
    baseline.allocations[0].locked = True
    locked_interval = exact_interval(baseline.allocations[0])

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[],
        trigger=WeeklyTriggerType.MANUAL,
        now=at(0, 8),
        invalidated_ids={baseline.allocations[0].id},
    )

    assert exact_interval(plan.allocations[0]) == locked_interval
    assert plan.allocations[0].locked is True
    assert plan.allocations[0].id != baseline.allocations[0].id
    assert plan.metrics.moved_allocation_count == 0
    assert plan.metrics.preservation_rate == 1
    assert plan.status == WeeklyPlanStatus.INFEASIBLE
    assert {
        issue.code for issue in plan.issues
    } >= {"WEEKLY_FROZEN_CAPACITY_CONFLICT"}


def test_in_progress_partial_block_freezes_only_remaining_workload():
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(0, 9, 10)],
    )
    active = baseline.allocations[0]
    active.completed_duration_min = 20
    active.status = AllocationStatus.SCHEDULED
    baseline.goals[0].remaining_duration_min = 40
    baseline.goals[0].stages[0].remaining_duration_min = 40

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[capacity(0, 9, 10)],
        trigger=WeeklyTriggerType.TASK_INCOMPLETE,
        now=at(0, 9, 30),
    )

    assert len(plan.allocations) == 1
    frozen = plan.allocations[0]
    assert exact_interval(frozen) == (at(0, 9), at(0, 10))
    assert frozen.completed_duration_min == 20
    assert frozen.source_allocation_id == active.id
    assert plan.metrics.requested_duration_min == 40
    assert plan.metrics.allocated_duration_min == 40
    assert plan.metrics.unallocated_duration_min == 0
    assert plan.metrics.moved_allocation_count == 0
    assert plan.status == WeeklyPlanStatus.VALID


def test_replanned_stages_still_obey_dependency_order():
    request = WeeklyPlanCreateRequest(
        user_id="dependency_user",
        campus_id="hdu_xiasha",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title="实验报告",
                deadline=at(4, 22),
                total_duration_min=120,
                min_chunk_min=60,
                max_chunk_min=60,
                max_chunks_per_day=1,
                stages=[
                    GoalStageCreate(
                        id="analysis",
                        title="数据分析",
                        sequence=1,
                        duration_min=60,
                        min_chunk_min=60,
                    ),
                    GoalStageCreate(
                        id="writing",
                        title="撰写报告",
                        sequence=2,
                        duration_min=60,
                        min_chunk_min=60,
                        depends_on_stage_ids=["analysis"],
                    ),
                ],
            )
        ],
        capacities=[
            capacity(0, 9, 10),
            capacity(1, 9, 10),
        ],
    )
    baseline = WeeklyAllocator().allocate(request, now=at(0, 8))
    first_stage_id = baseline.goals[0].stages[0].id
    first_allocation = next(
        item
        for item in baseline.allocations
        if item.stage_id == first_stage_id
    )

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[
            capacity(1, 10, 11),
            capacity(2, 9, 10),
        ],
        trigger=WeeklyTriggerType.FIXED_EVENT_CHANGED,
        now=at(0, 8),
        invalidated_allocation_ids={first_allocation.id},
    )

    stages = {stage.title: stage.id for stage in plan.goals[0].stages}
    analysis = [
        item
        for item in plan.allocations
        if item.stage_id == stages["数据分析"]
    ]
    writing = [
        item
        for item in plan.allocations
        if item.stage_id == stages["撰写报告"]
    ]
    assert max(exact_interval(item)[1] for item in analysis) <= min(
        exact_interval(item)[0] for item in writing
    )
    assert plan.status == WeeklyPlanStatus.VALID
    assert plan.metrics.unallocated_duration_min == 0


def test_deadline_and_minimum_chunk_are_not_broken_to_fake_completion():
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(1, 9, 10)],
        deadline=at(1, 10),
        min_chunk=60,
        max_chunk=60,
    )

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[
            capacity(
                1,
                9,
                9,
                end_minute=30,
            )
        ],
        trigger=WeeklyTriggerType.FIXED_EVENT_CHANGED,
        now=at(0, 8),
        invalidated_allocation_ids={baseline.allocations[0].id},
    )

    assert plan.allocations == []
    assert plan.status == WeeklyPlanStatus.INFEASIBLE
    assert plan.metrics.allocated_duration_min == 0
    assert plan.metrics.unallocated_duration_min == 60
    assert plan.metrics.moved_allocation_count == 1
    assert any(
        issue.code == "WEEKLY_REPLAN_CAPACITY_SHORTAGE"
        and issue.details["missing_min"] == 60
        for issue in plan.issues
    )


def test_preservation_uses_preferred_interval_not_broad_candidate_window():
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(1, 9, 10)],
    )
    allocation = baseline.allocations[0]
    baseline.allocations[0] = allocation.model_copy(
        update={
            "earliest_start": at(1, 8),
            "latest_end": at(1, 12),
            "window_start_at": at(1, 8),
            "window_end_at": at(1, 12),
            "preferred_start_at": at(1, 9),
            "preferred_end_at": at(1, 10),
        }
    )

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[capacity(1, 9, 10)],
        trigger=WeeklyTriggerType.WEATHER_CHANGED,
        now=at(0, 8),
    )

    assert len(plan.allocations) == 1
    assert plan.allocations[0].earliest_start == at(1, 8)
    assert plan.allocations[0].latest_end == at(1, 12)
    assert exact_interval(plan.allocations[0]) == (at(1, 9), at(1, 10))
    assert plan.metrics.moved_allocation_count == 0
    assert plan.metrics.preservation_rate == 1


def test_new_task_is_inserted_without_moving_valid_existing_blocks():
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(0, 9, 12)],
    )
    original_interval = exact_interval(baseline.allocations[0])

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[capacity(0, 9, 12)],
        trigger=WeeklyTriggerType.NEW_TASK,
        additional_goals=[
            WeeklyGoalCreate(
                title="新增答辩提纲",
                deadline=at(0, 12),
                total_duration_min=60,
                min_chunk_min=60,
                max_chunk_min=60,
                splittable=False,
            )
        ],
        now=at(0, 8),
    )

    assert len(plan.goals) == 2
    assert any(goal.title == "新增答辩提纲" for goal in plan.goals)
    assert original_interval in {
        exact_interval(allocation) for allocation in plan.allocations
    }
    assert plan.metrics.preservation_rate == 1
    assert plan.metrics.moved_allocation_count == 0
    assert plan.metrics.unallocated_duration_min == 0
    assert plan.status == WeeklyPlanStatus.VALID


def test_hard_new_task_evicts_one_flexible_block_then_rehomes_it():
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(0, 9, 11)],
    )
    old_allocation = baseline.allocations[0]

    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[capacity(0, 9, 11)],
        trigger=WeeklyTriggerType.NEW_TASK,
        additional_goals=[
            WeeklyGoalCreate(
                title="紧急答辩材料",
                deadline=at(0, 10),
                total_duration_min=60,
                min_chunk_min=60,
                max_chunk_min=60,
                splittable=False,
                hard_deadline=True,
            )
        ],
        now=at(0, 8),
    )

    goals = {goal.id: goal.title for goal in plan.goals}
    by_title = {
        goals[allocation.goal_id]: exact_interval(allocation)
        for allocation in plan.allocations
    }
    assert by_title["紧急答辩材料"] == (at(0, 9), at(0, 10))
    assert by_title["课程设计"] == (at(0, 10), at(0, 11))
    moved = next(
        item
        for item in plan.allocations
        if goals[item.goal_id] == "课程设计"
    )
    assert moved.source_allocation_id == old_allocation.id
    assert moved.lineage_id == old_allocation.lineage_id
    assert plan.metrics.moved_allocation_count == 1
    assert plan.metrics.preservation_rate == 0
    assert plan.metrics.unallocated_duration_min == 0
    assert plan.status == WeeklyPlanStatus.VALID


def test_replanned_version_can_be_saved_beside_baseline(
    tmp_path: Path,
):
    baseline = one_stage_baseline(
        duration=60,
        capacities=[capacity(1, 9, 10)],
    )
    plan = WeeklyReplanner().replan(
        baseline=baseline,
        capacities=[capacity(1, 9, 10)],
        trigger=WeeklyTriggerType.MANUAL,
        now=at(0, 8),
    )
    database = Database(tmp_path / "weekly-replan.sqlite3")
    database.initialize()
    repository = WeeklyPlanRepository(database)

    repository.save(baseline)
    repository.save(plan)

    latest = repository.latest(
        user_id=baseline.user_id,
        campus_id=baseline.campus_id,
        week_start=baseline.week_start,
    )
    assert latest is not None
    assert latest.id == plan.id
    assert latest.version == 2
    assert latest.baseline_plan_id == baseline.id
    assert {goal.id for goal in baseline.goals}.isdisjoint(
        goal.id for goal in plan.goals
    )
    assert [goal.lineage_id for goal in plan.goals] == [
        goal.lineage_id for goal in baseline.goals
    ]
    assert {
        stage.id
        for goal in baseline.goals
        for stage in goal.stages
    }.isdisjoint(
        stage.id
        for goal in plan.goals
        for stage in goal.stages
    )
    assert {
        stage.lineage_id
        for goal in plan.goals
        for stage in goal.stages
    } == {
        stage.lineage_id
        for goal in baseline.goals
        for stage in goal.stages
    }
    assert plan.allocations[0].source_allocation_id == (
        baseline.allocations[0].id
    )
    assert plan.allocations[0].lineage_id == (
        baseline.allocations[0].lineage_id
    )
