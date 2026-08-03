from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.repositories.database import Database
from app.repositories.weekly import WeeklyPlanRepository
from app.schemas.weekly import (
    AllocationStatus,
    CompletionEventCreate,
    CompletionEventType,
    DailyCapacity,
    DailyWindow,
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


def capacity(day: int, start_hour: int, end_hour: int) -> DailyCapacity:
    return DailyCapacity(
        date=WEEK_START.fromordinal(WEEK_START.toordinal() + day),
        windows=[
            DailyWindow(
                start_at=at(day, start_hour),
                end_at=at(day, end_hour),
            )
        ],
    )


def test_partial_completion_persists_and_only_replans_remaining_minutes(
    tmp_path,
):
    database = Database(tmp_path / "weekly-partial.db")
    database.initialize()
    repository = WeeklyPlanRepository(database)
    baseline = WeeklyAllocator().allocate(
        WeeklyPlanCreateRequest(
            user_id="partial_user",
            campus_id="hdu_xiasha",
            week_start=WEEK_START,
            goals=[
                WeeklyGoalCreate(
                    title="课程复习",
                    deadline=at(4, 22),
                    total_duration_min=60,
                    min_chunk_min=30,
                    max_chunk_min=60,
                    splittable=True,
                )
            ],
            capacities=[capacity(0, 9, 10)],
        ),
        now=at(0, 8),
    )
    repository.save(baseline)
    original = baseline.allocations[0]

    event, applied = repository.record_event(
        user_id=baseline.user_id,
        plan_id=baseline.id,
        payload=CompletionEventCreate(
            event_type=CompletionEventType.PARTIAL,
            allocation_id=original.id,
            occurred_at=at(0, 9, 30),
            completed_duration_min=30,
            remaining_duration_min=30,
            client_event_id="partial-30-minutes",
        ),
        now=at(0, 10, 5),
    )

    assert applied is True
    assert event.completed_duration_min == 30
    updated = repository.get(baseline.id)
    assert updated is not None
    assert updated.goals[0].remaining_duration_min == 30
    assert updated.goals[0].stages[0].remaining_duration_min == 30
    assert updated.allocations[0].completed_duration_min == 30
    assert updated.allocations[0].status == AllocationStatus.SCHEDULED

    replanned = WeeklyReplanner().replan(
        baseline=updated,
        capacities=[capacity(1, 9, 10)],
        trigger=WeeklyTriggerType.TASK_INCOMPLETE,
        now=at(0, 10, 5),
        invalidated_allocation_ids={original.id},
    )

    assert replanned.status == WeeklyPlanStatus.VALID
    assert replanned.metrics.requested_duration_min == 30
    assert replanned.metrics.allocated_duration_min == 30
    assert replanned.metrics.unallocated_duration_min == 0
    assert sum(
        allocation.allocated_duration_min
        - allocation.completed_duration_min
        for allocation in replanned.allocations
        if allocation.status
        not in {
            AllocationStatus.COMPLETED,
            AllocationStatus.CANCELLED,
            AllocationStatus.DEFERRED,
        }
    ) == 30
    assert len(replanned.allocations) == 1
    moved = replanned.allocations[0]
    assert moved.date == WEEK_START.fromordinal(WEEK_START.toordinal() + 1)
    assert moved.allocated_duration_min == 30
    assert moved.lineage_id == (original.lineage_id or original.id)
    assert moved.source_allocation_id == original.id

    repository.save(replanned)
    persisted = repository.get(replanned.id)
    assert persisted is not None
    assert persisted.allocations[0].model_dump() == moved.model_dump()
