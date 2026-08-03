from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from datetime import date, datetime, timedelta
from itertools import pairwise
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.schemas.common import Issue, IssueSeverity
from app.schemas.weekly import (
    AllocationStatus,
    DailyCapacity,
    DayAllocation,
    GoalStage,
    GoalStatus,
    StageStatus,
    WeeklyGoal,
    WeeklyGoalCreate,
    WeeklyPlan,
    WeeklyPlanMetrics,
    WeeklyPlanStatus,
    WeeklyTriggerType,
)
from app.services.weekly_allocator import WeeklyAllocator, _FreeSegment


class WeeklyReplanner:
    """Repair a weekly plan while changing as little as possible.

    The baseline plan remains immutable. Completed, locked and already-started
    allocations are frozen. Other future allocations are retained only when
    their concrete preferred interval still fits the latest capacity and all
    hard constraints. The allocator is then invoked only for uncovered
    remaining duration.
    """

    def __init__(self, allocator: WeeklyAllocator | None = None) -> None:
        self.allocator = allocator or WeeklyAllocator()

    def replan(
        self,
        *,
        baseline: WeeklyPlan,
        capacities: list[DailyCapacity],
        trigger: WeeklyTriggerType,
        now: datetime,
        invalidated_allocation_ids: Iterable[str] | None = None,
        invalidated_ids: Iterable[str] | None = None,
        additional_goals: Iterable[WeeklyGoalCreate] | None = None,
    ) -> WeeklyPlan:
        timezone = ZoneInfo(baseline.timezone)
        if now.tzinfo is None:
            raise ValueError("周计划重排时间必须包含时区")
        current_time = now.astimezone(timezone)
        self._validate_capacities(baseline, capacities)
        new_goal_payloads = list(additional_goals or ())
        if new_goal_payloads and trigger != WeeklyTriggerType.NEW_TASK:
            raise ValueError("新增目标必须使用 new_task 触发类型")
        if trigger == WeeklyTriggerType.NEW_TASK and not new_goal_payloads:
            raise ValueError("new_task 重排必须提供至少一个新增目标")

        invalidated = set(invalidated_allocation_ids or ())
        invalidated.update(invalidated_ids or ())
        known_allocation_ids = {
            allocation.id for allocation in baseline.allocations
        }
        unknown_allocation_ids = sorted(
            invalidated - known_allocation_ids
        )
        if unknown_allocation_ids:
            raise ValueError(
                "待失效的周计划块不存在："
                + "、".join(unknown_allocation_ids)
            )
        plan_id = f"weekly_plan_{uuid4().hex}"
        goals = [goal.model_copy(deep=True) for goal in baseline.goals]
        new_goal_ids: set[str] = set()
        for goal in goals:
            goal.lineage_id = goal.lineage_id or goal.id
            for stage in goal.stages:
                stage.lineage_id = stage.lineage_id or stage.id
        for payload in new_goal_payloads:
            new_goal = self.allocator._build_goal(
                payload,
                user_id=baseline.user_id,
                campus_id=baseline.campus_id,
                week_start=baseline.week_start,
                now=current_time,
            )
            new_goal.source = "replan_new_task"
            goals.append(new_goal)
            new_goal_ids.add(new_goal.id)
        goal_by_id = {goal.id: goal for goal in goals}
        stage_by_id = {
            stage.id: stage
            for goal in goals
            for stage in goal.stages
        }
        issues: list[Issue] = []
        issue_keys: set[tuple[str, str | None]] = set()

        segments = self.allocator._build_segments(capacities)
        frozen = [
            allocation
            for allocation in baseline.allocations
            if self._is_frozen(allocation, current_time)
        ]
        frozen.sort(key=lambda item: (self._start(item), item.id))
        selected: list[DayAllocation] = []
        selected_ids: set[str] = set()

        for allocation in frozen:
            selected.append(allocation)
            selected_ids.add(allocation.id)
            if allocation.status == AllocationStatus.COMPLETED:
                self._reserve(segments, allocation)
                continue
            goal = goal_by_id.get(allocation.goal_id)
            stage = stage_by_id.get(allocation.stage_id)
            if goal is None or stage is None:
                self._add_issue(
                    issues,
                    issue_keys,
                    code="WEEKLY_FROZEN_REFERENCE_INVALID",
                    severity=IssueSeverity.ERROR,
                    message="冻结时间块引用的目标或阶段不存在，系统没有擅自移动它。",
                    allocation=allocation,
                )
                self._reserve(segments, allocation)
                continue
            if not self._basic_constraints_hold(
                allocation,
                goal=goal,
                stage=stage,
            ):
                self._add_issue(
                    issues,
                    issue_keys,
                    code="WEEKLY_FROZEN_CONSTRAINT_VIOLATION",
                    severity=IssueSeverity.ERROR,
                    message="冻结时间块与当前截止时间或分块约束冲突，需由用户确认。",
                    allocation=allocation,
                    goal=goal,
                )
            if not self._interval_available(
                segments,
                self._start(allocation),
                self._end(allocation),
            ):
                self._add_issue(
                    issues,
                    issue_keys,
                    code="WEEKLY_FROZEN_CAPACITY_CONFLICT",
                    severity=IssueSeverity.ERROR,
                    message="冻结时间块已不在最新可用容量内，系统按约定保持不动。",
                    allocation=allocation,
                    goal=goal,
                )
            self._reserve(segments, allocation)

        candidates_by_stage: dict[str, list[DayAllocation]] = defaultdict(list)
        for allocation in baseline.allocations:
            if allocation.id in selected_ids:
                continue
            if allocation.id in invalidated:
                continue
            if allocation.status not in {
                AllocationStatus.PROPOSED,
                AllocationStatus.SCHEDULED,
            }:
                continue
            if self._start(allocation) <= current_time:
                continue
            if (
                allocation.goal_id not in goal_by_id
                or allocation.stage_id not in stage_by_id
            ):
                continue
            candidates_by_stage[allocation.stage_id].append(allocation)

        frozen_by_stage = self._group_by_stage(frozen)
        selected_by_stage = self._group_by_stage(selected)
        goal_day_chunks = self._chunk_counts(selected)
        retained_complete: dict[str, bool] = {}
        retained_finish: dict[str, datetime] = {}

        for goal in self._ordered_goals(goals):
            for stage in self.allocator._topological_stages(goal.stages):
                dependency_ready = self._dependency_ready(
                    goal,
                    stage,
                    retained_finish,
                    timezone,
                )
                dependencies_retained = all(
                    retained_complete.get(dependency_id, False)
                    for dependency_id in stage.depends_on_stage_ids
                )
                existing = selected_by_stage.get(stage.id, [])
                coverage = self._planned_coverage(existing)
                dependency_valid = all(
                    self._start(item) >= dependency_ready
                    for item in existing
                    if self._counts_towards_remaining(item)
                )

                if dependencies_retained and dependency_valid:
                    for allocation in sorted(
                        candidates_by_stage.get(stage.id, []),
                        key=lambda item: (self._start(item), item.id),
                    ):
                        remaining_room = max(
                            0,
                            stage.remaining_duration_min - coverage,
                        )
                        allocation_remaining = (
                            self._remaining_allocation_duration(allocation)
                        )
                        if allocation_remaining > remaining_room:
                            continue
                        if not self._basic_constraints_hold(
                            allocation,
                            goal=goal,
                            stage=stage,
                        ):
                            continue
                        if self._start(allocation) < dependency_ready:
                            continue
                        key = (goal.id, self._start(allocation).date())
                        if goal_day_chunks[key] >= goal.max_chunks_per_day:
                            continue
                        if not self._interval_available(
                            segments,
                            self._start(allocation),
                            self._end(allocation),
                        ):
                            continue
                        selected.append(allocation)
                        selected_ids.add(allocation.id)
                        selected_by_stage[stage.id].append(allocation)
                        goal_day_chunks[key] += 1
                        coverage += allocation_remaining
                        self._reserve(segments, allocation)

                retained_complete[stage.id] = (
                    dependency_valid
                    and coverage >= stage.remaining_duration_min
                )
                retained_finish[stage.id] = self._stage_finish(
                    selected_by_stage.get(stage.id, []),
                    default=dependency_ready,
                )

        frozen_ids = {item.id for item in frozen}
        selected, priority_allocations, segments = (
            self._prioritize_new_hard_goals(
                plan_id=plan_id,
                goals=goals,
                new_goal_ids=new_goal_ids,
                capacities=capacities,
                selected=selected,
                frozen_ids=frozen_ids,
                now=current_time,
                timezone=timezone,
            )
        )
        selected_ids = {item.id for item in selected}
        retained: list[DayAllocation] = []
        retained_id_map: dict[str, str] = {}
        for allocation in selected:
            copied = self._copy_allocation(
                allocation,
                plan_id=plan_id,
                now=current_time,
            )
            retained.append(copied)
            retained_id_map[allocation.id] = copied.id
        retained_by_stage = self._group_by_stage(retained)
        priority_by_stage = self._group_by_stage(priority_allocations)
        frozen_deadlines = self._frozen_dependency_deadlines(
            goals,
            frozen_by_stage,
        )

        day_load: dict[date, int] = defaultdict(int)
        goal_day_chunks = defaultdict(int)
        for allocation in [*retained, *priority_allocations]:
            if allocation.status == AllocationStatus.CANCELLED:
                continue
            allocation_date = self._start(allocation).date()
            day_load[allocation_date] += (
                self._remaining_allocation_duration(allocation)
            )
            goal_day_chunks[(allocation.goal_id, allocation_date)] += 1

        new_allocations: list[DayAllocation] = list(priority_allocations)
        stage_complete: dict[str, bool] = {}
        stage_finish: dict[str, datetime] = {}

        for goal in self._ordered_goals(goals):
            for stage in self.allocator._topological_stages(goal.stages):
                dependency_ready = self._dependency_ready(
                    goal,
                    stage,
                    stage_finish,
                    timezone,
                )
                dependencies_complete = all(
                    stage_complete.get(dependency_id, False)
                    for dependency_id in stage.depends_on_stage_ids
                )
                existing = [
                    *retained_by_stage.get(stage.id, []),
                    *priority_by_stage.get(stage.id, []),
                ]
                active_existing = [
                    item
                    for item in existing
                    if self._counts_towards_remaining(item)
                ]
                dependency_valid = all(
                    self._start(item) >= dependency_ready
                    for item in active_existing
                )
                if not dependency_valid:
                    for allocation in active_existing:
                        if self._start(allocation) < dependency_ready:
                            self._add_issue(
                                issues,
                                issue_keys,
                                code="WEEKLY_FROZEN_DEPENDENCY_VIOLATION",
                                severity=IssueSeverity.ERROR,
                                message="冻结时间块早于其前置阶段完成时间，系统没有擅自改动。",
                                allocation=allocation,
                                goal=goal,
                            )

                target = (
                    0
                    if goal.status == GoalStatus.CANCELLED
                    or stage.status == StageStatus.CANCELLED
                    else stage.remaining_duration_min
                )
                covered = min(target, self._planned_coverage(existing))
                remaining = max(0, target - covered)
                allocated_for_stage: list[DayAllocation] = []
                missing = remaining

                can_allocate = dependencies_complete and dependency_valid
                if (
                    can_allocate
                    and remaining > 0
                    and remaining >= 5
                    and not (
                        active_existing
                        and (not goal.splittable or not stage.splittable)
                    )
                ):
                    stage_deadline = min(
                        goal.deadline,
                        frozen_deadlines.get(stage.id, goal.deadline),
                    )
                    allocation_goal = goal.model_copy(
                        update={"deadline": stage_deadline}
                    )
                    allocation_stage = stage.model_copy(
                        update={
                            "duration_min": remaining,
                            "remaining_duration_min": remaining,
                        }
                    )
                    allocated_for_stage, missing = (
                        self.allocator._allocate_stage(
                            plan_id=plan_id,
                            goal=allocation_goal,
                            stage=allocation_stage,
                            segments=segments,
                            dependency_ready=dependency_ready,
                            day_load=day_load,
                            goal_day_chunks=goal_day_chunks,
                            now=current_time,
                        )
                    )
                    new_allocations.extend(allocated_for_stage)

                planned = (
                    covered
                    + self._planned_coverage(allocated_for_stage)
                )
                stage_complete[stage.id] = (
                    can_allocate and planned >= target
                )
                stage_finish[stage.id] = self._stage_finish(
                    [*active_existing, *allocated_for_stage],
                    default=dependency_ready,
                )
                if missing > 0:
                    reason = (
                        "前置阶段尚未完整安排"
                        if not dependencies_complete
                        else "剩余容量不足或分块约束无法满足"
                    )
                    self._add_shortage_issue(
                        issues,
                        issue_keys,
                        goal=goal,
                        stage=stage,
                        missing=missing,
                        reason=reason,
                    )

        self._inherit_moved_allocation_lineage(
            baseline_allocations=baseline.allocations,
            selected_ids=selected_ids,
            new_allocations=new_allocations,
        )
        allocations = sorted(
            [*retained, *new_allocations],
            key=lambda item: (
                self._start(item),
                item.goal_id,
                item.stage_id,
            ),
        )
        self._validate_result(
            allocations=allocations,
            goals=goals,
            capacities=capacities,
            frozen_source_ids=frozen_ids,
            issues=issues,
            issue_keys=issue_keys,
        )
        self._update_goal_statuses(
            goals,
            allocations=allocations,
            now=current_time,
        )

        comparable = [
            item
            for item in baseline.allocations
            if item.status != AllocationStatus.CANCELLED
        ]
        preserved_count = sum(
            item.id in selected_ids for item in comparable
        )
        moved_count = len(comparable) - preserved_count
        preservation_rate = (
            round(preserved_count / len(comparable), 4)
            if comparable
            else 1.0
        )

        requested = sum(
            stage.remaining_duration_min
            for goal in goals
            if goal.status != GoalStatus.CANCELLED
            for stage in goal.stages
            if stage.status != StageStatus.CANCELLED
        )
        allocated = 0
        final_by_stage = self._group_by_stage(allocations)
        for goal in goals:
            if goal.status == GoalStatus.CANCELLED:
                continue
            for stage in goal.stages:
                if stage.status == StageStatus.CANCELLED:
                    continue
                allocated += min(
                    stage.remaining_duration_min,
                    self._planned_coverage(
                        final_by_stage.get(stage.id, [])
                    ),
                )

        hard_violations = sum(
            issue.severity == IssueSeverity.ERROR for issue in issues
        )
        at_risk_goals = {
            str(issue.details["goal_id"])
            for issue in issues
            if issue.details.get("goal_id")
        }
        status = WeeklyPlanStatus.VALID
        if hard_violations:
            status = WeeklyPlanStatus.INFEASIBLE
        elif issues:
            status = WeeklyPlanStatus.AT_RISK
        self._remap_version_entities(
            goals=goals,
            allocations=allocations,
            issues=issues,
            retained_id_map=retained_id_map,
        )

        return WeeklyPlan(
            id=plan_id,
            user_id=baseline.user_id,
            campus_id=baseline.campus_id,
            week_start=baseline.week_start,
            week_end=baseline.week_end,
            timezone=baseline.timezone,
            version=baseline.version + 1,
            status=status,
            baseline_plan_id=baseline.id,
            trigger_type=trigger,
            goals=goals,
            allocations=allocations,
            issues=issues,
            metrics=WeeklyPlanMetrics(
                requested_duration_min=requested,
                allocated_duration_min=allocated,
                unallocated_duration_min=max(0, requested - allocated),
                hard_violation_count=hard_violations,
                at_risk_goal_count=len(at_risk_goals),
                moved_allocation_count=moved_count,
                workload_balance_score=self.allocator._balance_score(
                    day_load,
                    capacities,
                ),
                preservation_rate=preservation_rate,
            ),
            created_at=current_time,
            updated_at=current_time,
        )

    @staticmethod
    def _validate_capacities(
        baseline: WeeklyPlan,
        capacities: list[DailyCapacity],
    ) -> None:
        dates = [capacity.date for capacity in capacities]
        if len(dates) != len(set(dates)):
            raise ValueError("同一天不能重复提供周重排容量")
        allowed = {
            baseline.week_start + timedelta(days=offset)
            for offset in range(7)
        }
        if not set(dates) <= allowed:
            raise ValueError("重排容量必须位于基线计划所在周")

    @staticmethod
    def _start(allocation: DayAllocation) -> datetime:
        return (
            allocation.preferred_start_at
            or allocation.earliest_start
        )

    @classmethod
    def _end(cls, allocation: DayAllocation) -> datetime:
        return (
            allocation.preferred_end_at
            or cls._start(allocation)
            + timedelta(minutes=allocation.allocated_duration_min)
        )

    @classmethod
    def _is_frozen(
        cls,
        allocation: DayAllocation,
        now: datetime,
    ) -> bool:
        if allocation.status == AllocationStatus.CANCELLED:
            return False
        return (
            allocation.status == AllocationStatus.COMPLETED
            or allocation.locked
            or (
                allocation.status != AllocationStatus.DEFERRED
                and cls._start(allocation) <= now < cls._end(allocation)
            )
        )

    @staticmethod
    def _counts_towards_remaining(
        allocation: DayAllocation,
    ) -> bool:
        return allocation.status not in {
            AllocationStatus.COMPLETED,
            AllocationStatus.CANCELLED,
            AllocationStatus.DEFERRED,
        }

    @classmethod
    def _planned_coverage(
        cls,
        allocations: Iterable[DayAllocation],
    ) -> int:
        return sum(
            cls._remaining_allocation_duration(item)
            for item in allocations
            if cls._counts_towards_remaining(item)
        )

    @staticmethod
    def _remaining_allocation_duration(
        allocation: DayAllocation,
    ) -> int:
        return max(
            0,
            (
                allocation.allocated_duration_min
                - allocation.completed_duration_min
            ),
        )

    @staticmethod
    def _ordered_goals(
        goals: list[WeeklyGoal],
    ) -> list[WeeklyGoal]:
        return sorted(
            goals,
            key=lambda goal: (
                not goal.hard_deadline,
                goal.deadline,
                -goal.importance,
                goal.total_duration_min,
                goal.id,
            ),
        )

    @staticmethod
    def _group_by_stage(
        allocations: Iterable[DayAllocation],
    ) -> dict[str, list[DayAllocation]]:
        grouped: dict[str, list[DayAllocation]] = defaultdict(list)
        for allocation in allocations:
            grouped[allocation.stage_id].append(allocation)
        return grouped

    @classmethod
    def _basic_constraints_hold(
        cls,
        allocation: DayAllocation,
        *,
        goal: WeeklyGoal,
        stage: GoalStage,
    ) -> bool:
        start = cls._start(allocation)
        end = cls._end(allocation)
        duration = int((end - start).total_seconds() // 60)
        if duration != allocation.allocated_duration_min:
            return False
        if start.date() != allocation.date:
            return False
        if goal.earliest_start and start < goal.earliest_start:
            return False
        if end > goal.deadline:
            return False
        if allocation.allocated_duration_min > goal.max_chunk_min:
            return False
        minimum = min(
            max(goal.min_chunk_min, stage.min_chunk_min),
            max(5, stage.remaining_duration_min),
        )
        if allocation.allocated_duration_min < minimum:
            return False
        return not (
            (not goal.splittable or not stage.splittable)
            and allocation.allocated_duration_min
            < stage.remaining_duration_min
        )

    @staticmethod
    def _interval_available(
        segments: list[_FreeSegment],
        start: datetime,
        end: datetime,
    ) -> bool:
        cursor = start
        for segment in sorted(segments, key=lambda item: item.start_at):
            if segment.end_at <= cursor:
                continue
            if segment.start_at > cursor:
                break
            cursor = min(end, max(cursor, segment.end_at))
            if cursor >= end:
                return True
        return False

    @classmethod
    def _reserve(
        cls,
        segments: list[_FreeSegment],
        allocation: DayAllocation,
    ) -> None:
        start = cls._start(allocation)
        end = cls._end(allocation)
        updated: list[_FreeSegment] = []
        for segment in segments:
            if end <= segment.start_at or start >= segment.end_at:
                updated.append(segment)
                continue
            if segment.start_at < start:
                updated.append(replace(segment, end_at=start))
            if end < segment.end_at:
                updated.append(replace(segment, start_at=end))
        segments[:] = sorted(updated, key=lambda item: item.start_at)

    @classmethod
    def _stage_finish(
        cls,
        allocations: Iterable[DayAllocation],
        *,
        default: datetime,
    ) -> datetime:
        ends = [
            cls._end(item)
            for item in allocations
            if item.status != AllocationStatus.CANCELLED
        ]
        return max(ends, default=default)

    @staticmethod
    def _dependency_ready(
        goal: WeeklyGoal,
        stage: GoalStage,
        stage_finish: dict[str, datetime],
        timezone: ZoneInfo,
    ) -> datetime:
        default = goal.earliest_start or datetime.combine(
            goal.week_start,
            datetime.min.time(),
            timezone,
        )
        return max(
            (
                stage_finish[dependency_id]
                for dependency_id in stage.depends_on_stage_ids
                if dependency_id in stage_finish
            ),
            default=default,
        )

    @classmethod
    def _chunk_counts(
        cls,
        allocations: Iterable[DayAllocation],
    ) -> dict[tuple[str, date], int]:
        counts: dict[tuple[str, date], int] = defaultdict(int)
        for allocation in allocations:
            if allocation.status == AllocationStatus.CANCELLED:
                continue
            counts[
                (allocation.goal_id, cls._start(allocation).date())
            ] += 1
        return counts

    def _prioritize_new_hard_goals(
        self,
        *,
        plan_id: str,
        goals: list[WeeklyGoal],
        new_goal_ids: set[str],
        capacities: list[DailyCapacity],
        selected: list[DayAllocation],
        frozen_ids: set[str],
        now: datetime,
        timezone: ZoneInfo,
    ) -> tuple[
        list[DayAllocation],
        list[DayAllocation],
        list[_FreeSegment],
    ]:
        """Reserve hard new work, evicting the fewest flexible old blocks.

        Existing blocks are tried first. Eviction starts only when a hard new
        goal is otherwise infeasible, so free capacity never causes needless
        movement.
        """

        retained = list(selected)
        priority_allocations: list[DayAllocation] = []
        goal_by_id = {goal.id: goal for goal in goals}
        priority_goals = [
            goal
            for goal in self._ordered_goals(goals)
            if goal.id in new_goal_ids and goal.hard_deadline
        ]

        for goal in priority_goals:
            missing, allocations, trial_segments = (
                self._trial_allocate_new_goal(
                    plan_id=plan_id,
                    goal=goal,
                    capacities=capacities,
                    reservations=[*retained, *priority_allocations],
                    now=now,
                    timezone=timezone,
                )
            )
            if missing == 0:
                priority_allocations.extend(allocations)
                continue

            evictable = [
                allocation
                for allocation in retained
                if allocation.id not in frozen_ids
                and allocation.status
                in {
                    AllocationStatus.PROPOSED,
                    AllocationStatus.SCHEDULED,
                }
                and self._start(allocation) < goal.deadline
                and self._end(allocation) > now
            ]
            evicted_ids: set[str] = set()
            successful: tuple[
                list[DayAllocation],
                list[_FreeSegment],
            ] | None = None

            while evictable:
                best = None
                for candidate in evictable:
                    candidate_ids = {*evicted_ids, candidate.id}
                    candidate_retained = [
                        item
                        for item in retained
                        if item.id not in candidate_ids
                    ]
                    (
                        candidate_missing,
                        candidate_allocations,
                        candidate_segments,
                    ) = self._trial_allocate_new_goal(
                        plan_id=plan_id,
                        goal=goal,
                        capacities=capacities,
                        reservations=[
                            *candidate_retained,
                            *priority_allocations,
                        ],
                        now=now,
                        timezone=timezone,
                    )
                    old_goal = goal_by_id.get(candidate.goal_id)
                    eviction_cost = (
                        bool(old_goal and old_goal.hard_deadline),
                        old_goal.importance if old_goal else 5,
                        candidate.allocated_duration_min,
                        self._start(candidate),
                        candidate.id,
                    )
                    score = (candidate_missing, *eviction_cost)
                    if best is None or score < best[0]:
                        best = (
                            score,
                            candidate,
                            candidate_allocations,
                            candidate_segments,
                        )
                if best is None:
                    break
                _, chosen, trial_allocations, trial_segments = best
                evicted_ids.add(chosen.id)
                evictable = [
                    item for item in evictable if item.id != chosen.id
                ]
                if best[0][0] == 0:
                    successful = (trial_allocations, trial_segments)
                    break

            if successful is not None:
                retained = [
                    item for item in retained if item.id not in evicted_ids
                ]
                allocations, trial_segments = successful
                priority_allocations.extend(allocations)

        final_segments = self.allocator._build_segments(capacities)
        for allocation in [*retained, *priority_allocations]:
            self._reserve(final_segments, allocation)
        return retained, priority_allocations, final_segments

    def _trial_allocate_new_goal(
        self,
        *,
        plan_id: str,
        goal: WeeklyGoal,
        capacities: list[DailyCapacity],
        reservations: list[DayAllocation],
        now: datetime,
        timezone: ZoneInfo,
    ) -> tuple[int, list[DayAllocation], list[_FreeSegment]]:
        segments = self.allocator._build_segments(capacities)
        day_load: dict[date, int] = defaultdict(int)
        goal_day_chunks: dict[tuple[str, date], int] = defaultdict(int)
        for allocation in reservations:
            self._reserve(segments, allocation)
            if allocation.status == AllocationStatus.CANCELLED:
                continue
            allocation_date = self._start(allocation).date()
            day_load[allocation_date] += (
                self._remaining_allocation_duration(allocation)
            )
            goal_day_chunks[(allocation.goal_id, allocation_date)] += 1

        result: list[DayAllocation] = []
        stage_finish: dict[str, datetime] = {}
        stage_complete: dict[str, bool] = {}
        missing_total = 0
        for stage in self.allocator._topological_stages(goal.stages):
            dependency_ready = self._dependency_ready(
                goal,
                stage,
                stage_finish,
                timezone,
            )
            dependencies_complete = all(
                stage_complete.get(dependency_id, False)
                for dependency_id in stage.depends_on_stage_ids
            )
            target = (
                0
                if goal.status == GoalStatus.CANCELLED
                or stage.status == StageStatus.CANCELLED
                else stage.remaining_duration_min
            )
            stage_allocations: list[DayAllocation] = []
            missing = target
            if dependencies_complete and target >= 5:
                allocation_stage = stage.model_copy(
                    update={
                        "duration_min": target,
                        "remaining_duration_min": target,
                    }
                )
                stage_allocations, missing = (
                    self.allocator._allocate_stage(
                        plan_id=plan_id,
                        goal=goal,
                        stage=allocation_stage,
                        segments=segments,
                        dependency_ready=dependency_ready,
                        day_load=day_load,
                        goal_day_chunks=goal_day_chunks,
                        now=now,
                    )
                )
            result.extend(stage_allocations)
            missing_total += missing
            stage_complete[stage.id] = (
                dependencies_complete and missing == 0
            )
            stage_finish[stage.id] = self._stage_finish(
                stage_allocations,
                default=dependency_ready,
            )
        return missing_total, result, segments

    @classmethod
    def _inherit_moved_allocation_lineage(
        cls,
        *,
        baseline_allocations: list[DayAllocation],
        selected_ids: set[str],
        new_allocations: list[DayAllocation],
    ) -> None:
        """Link an unambiguous one-to-one replacement to its direct source."""

        sources = cls._group_by_stage(
            allocation
            for allocation in baseline_allocations
            if allocation.id not in selected_ids
            and allocation.status != AllocationStatus.CANCELLED
        )
        targets = cls._group_by_stage(
            allocation
            for allocation in new_allocations
            if allocation.source_allocation_id is None
        )
        for stage_id, stage_sources in sources.items():
            stage_targets = targets.get(stage_id, [])
            if len(stage_sources) != 1 or len(stage_targets) != 1:
                continue
            source = stage_sources[0]
            target = stage_targets[0]
            if cls._remaining_allocation_duration(
                source
            ) != cls._remaining_allocation_duration(target):
                continue
            target.lineage_id = source.lineage_id or source.id
            target.source_allocation_id = source.id

    @classmethod
    def _copy_allocation(
        cls,
        allocation: DayAllocation,
        *,
        plan_id: str,
        now: datetime,
    ) -> DayAllocation:
        allocation_id = f"day_allocation_{uuid4().hex}"
        return allocation.model_copy(
            deep=True,
            update={
                "id": allocation_id,
                "lineage_id": allocation.lineage_id or allocation.id,
                "source_allocation_id": allocation.id,
                "weekly_plan_id": plan_id,
                "updated_at": now,
            },
        )

    @staticmethod
    def _remap_version_entities(
        *,
        goals: list[WeeklyGoal],
        allocations: list[DayAllocation],
        issues: list[Issue],
        retained_id_map: dict[str, str],
    ) -> None:
        """Give every persisted version its own relational entity IDs."""

        goal_id_map = {
            goal.id: f"weekly_goal_{uuid4().hex}" for goal in goals
        }
        stage_id_map = {
            stage.id: f"goal_stage_{uuid4().hex}"
            for goal in goals
            for stage in goal.stages
        }
        for goal in goals:
            old_goal_id = goal.id
            goal.id = goal_id_map[old_goal_id]
            for stage in goal.stages:
                old_stage_id = stage.id
                stage.id = stage_id_map[old_stage_id]
                stage.goal_id = goal.id
                stage.depends_on_stage_ids = [
                    stage_id_map[dependency_id]
                    for dependency_id in stage.depends_on_stage_ids
                ]
        for allocation in allocations:
            allocation.goal_id = goal_id_map[allocation.goal_id]
            allocation.stage_id = stage_id_map[allocation.stage_id]
        for issue in issues:
            issue.task_ids = [
                goal_id_map.get(
                    item,
                    stage_id_map.get(item, item),
                )
                for item in issue.task_ids
            ]
            goal_id = issue.details.get("goal_id")
            if goal_id in goal_id_map:
                issue.details["goal_id"] = goal_id_map[goal_id]
            stage_id = issue.details.get("stage_id")
            if stage_id in stage_id_map:
                issue.details["stage_id"] = stage_id_map[stage_id]
            allocation_id = issue.details.get("allocation_id")
            if allocation_id in retained_id_map:
                issue.details["allocation_id"] = retained_id_map[
                    allocation_id
                ]

    @classmethod
    def _frozen_dependency_deadlines(
        cls,
        goals: list[WeeklyGoal],
        frozen_by_stage: dict[str, list[DayAllocation]],
    ) -> dict[str, datetime]:
        deadlines: dict[str, datetime] = {}
        for goal in goals:
            dependencies = {
                stage.id: set(stage.depends_on_stage_ids)
                for stage in goal.stages
            }

            for stage in goal.stages:
                starts = [
                    cls._start(item)
                    for item in frozen_by_stage.get(stage.id, [])
                    if cls._counts_towards_remaining(item)
                ]
                if not starts:
                    continue
                frozen_start = min(starts)
                for dependency_id in cls._ancestor_ids(
                    stage.id,
                    dependencies,
                ):
                    deadlines[dependency_id] = min(
                        deadlines.get(dependency_id, frozen_start),
                        frozen_start,
                    )
        return deadlines

    @staticmethod
    def _ancestor_ids(
        stage_id: str,
        dependencies: dict[str, set[str]],
    ) -> set[str]:
        result: set[str] = set()
        pending = list(dependencies.get(stage_id, set()))
        while pending:
            dependency_id = pending.pop()
            if dependency_id in result:
                continue
            result.add(dependency_id)
            pending.extend(dependencies.get(dependency_id, set()))
        return result

    @classmethod
    def _validate_result(
        cls,
        *,
        allocations: list[DayAllocation],
        goals: list[WeeklyGoal],
        capacities: list[DailyCapacity],
        frozen_source_ids: set[str],
        issues: list[Issue],
        issue_keys: set[tuple[str, str | None]],
    ) -> None:
        del capacities, frozen_source_ids
        goal_by_id = {goal.id: goal for goal in goals}
        stage_by_id = {
            stage.id: stage
            for goal in goals
            for stage in goal.stages
        }
        by_stage = cls._group_by_stage(allocations)

        for allocation in allocations:
            if allocation.status == AllocationStatus.COMPLETED:
                continue
            goal = goal_by_id.get(allocation.goal_id)
            stage = stage_by_id.get(allocation.stage_id)
            if goal is None or stage is None:
                continue
            if not cls._basic_constraints_hold(
                allocation,
                goal=goal,
                stage=stage,
            ):
                cls._add_issue(
                    issues,
                    issue_keys,
                    code="WEEKLY_RESULT_CONSTRAINT_VIOLATION",
                    severity=IssueSeverity.ERROR,
                    message="重排结果中存在截止时间或分块硬约束冲突。",
                    allocation=allocation,
                    goal=goal,
                )

        for goal in goals:
            finish_by_stage = {
                stage.id: cls._stage_finish(
                    by_stage.get(stage.id, []),
                    default=goal.earliest_start
                    or datetime.combine(
                        goal.week_start,
                        datetime.min.time(),
                        goal.deadline.tzinfo,
                    ),
                )
                for stage in goal.stages
            }
            for stage in goal.stages:
                dependency_end = max(
                    (
                        finish_by_stage[dependency_id]
                        for dependency_id in stage.depends_on_stage_ids
                    ),
                    default=None,
                )
                if dependency_end is None:
                    continue
                for allocation in by_stage.get(stage.id, []):
                    if (
                        cls._counts_towards_remaining(allocation)
                        and cls._start(allocation) < dependency_end
                    ):
                        cls._add_issue(
                            issues,
                            issue_keys,
                            code="WEEKLY_RESULT_DEPENDENCY_VIOLATION",
                            severity=IssueSeverity.ERROR,
                            message="重排结果中的阶段顺序违反前置依赖。",
                            allocation=allocation,
                            goal=goal,
                        )

            counts: dict[date, int] = defaultdict(int)
            for allocation in allocations:
                if (
                    allocation.goal_id == goal.id
                    and allocation.status != AllocationStatus.CANCELLED
                ):
                    counts[cls._start(allocation).date()] += 1
            for allocation_date, count in counts.items():
                if count <= goal.max_chunks_per_day:
                    continue
                key = (
                    "WEEKLY_RESULT_DAILY_CHUNK_LIMIT",
                    f"{goal.id}:{allocation_date.isoformat()}",
                )
                if key in issue_keys:
                    continue
                issue_keys.add(key)
                issues.append(
                    Issue(
                        code=key[0],
                        severity=IssueSeverity.ERROR,
                        message="重排结果超过目标的每日最大分块数。",
                        task_ids=[goal.id],
                        details={
                            "goal_id": goal.id,
                            "date": allocation_date.isoformat(),
                            "count": count,
                            "limit": goal.max_chunks_per_day,
                        },
                        recoverable=True,
                    )
                )

        active = sorted(
            [
                item
                for item in allocations
                if cls._counts_towards_remaining(item)
            ],
            key=lambda item: (cls._start(item), cls._end(item), item.id),
        )
        for previous, current in pairwise(active):
            if cls._end(previous) <= cls._start(current):
                continue
            cls._add_issue(
                issues,
                issue_keys,
                code="WEEKLY_RESULT_OVERLAP",
                severity=IssueSeverity.ERROR,
                message="重排结果中存在重叠时间块。",
                allocation=current,
                goal=goal_by_id.get(current.goal_id),
            )

    @staticmethod
    def _update_goal_statuses(
        goals: list[WeeklyGoal],
        *,
        allocations: list[DayAllocation],
        now: datetime,
    ) -> None:
        active_by_stage = WeeklyReplanner._group_by_stage(
            item
            for item in allocations
            if WeeklyReplanner._counts_towards_remaining(item)
        )
        for goal in goals:
            for stage in goal.stages:
                if stage.status == StageStatus.CANCELLED:
                    continue
                if stage.remaining_duration_min == 0:
                    stage.status = StageStatus.COMPLETED
                elif active_by_stage.get(stage.id):
                    stage.status = StageStatus.ACTIVE
                else:
                    stage.status = StageStatus.PENDING
                stage.updated_at = now
            if goal.status != GoalStatus.CANCELLED:
                if goal.remaining_duration_min == 0:
                    goal.status = GoalStatus.COMPLETED
                elif any(active_by_stage.get(stage.id) for stage in goal.stages):
                    goal.status = GoalStatus.ACTIVE
                else:
                    goal.status = GoalStatus.PENDING
            goal.updated_at = now

    @staticmethod
    def _add_issue(
        issues: list[Issue],
        issue_keys: set[tuple[str, str | None]],
        *,
        code: str,
        severity: IssueSeverity,
        message: str,
        allocation: DayAllocation,
        goal: WeeklyGoal | None = None,
    ) -> None:
        key = (code, allocation.id)
        if key in issue_keys:
            return
        issue_keys.add(key)
        details = {"allocation_id": allocation.id}
        if goal is not None:
            details["goal_id"] = goal.id
        issues.append(
            Issue(
                code=code,
                severity=severity,
                message=message,
                task_ids=[
                    item
                    for item in (allocation.goal_id, allocation.stage_id)
                    if item
                ],
                details=details,
                recoverable=True,
            )
        )

    @staticmethod
    def _add_shortage_issue(
        issues: list[Issue],
        issue_keys: set[tuple[str, str | None]],
        *,
        goal: WeeklyGoal,
        stage: GoalStage,
        missing: int,
        reason: str,
    ) -> None:
        key = ("WEEKLY_REPLAN_CAPACITY_SHORTAGE", stage.id)
        if key in issue_keys:
            return
        issue_keys.add(key)
        issues.append(
            Issue(
                code=key[0],
                severity=(
                    IssueSeverity.ERROR
                    if goal.hard_deadline
                    else IssueSeverity.WARNING
                ),
                message=(
                    f"“{goal.title} / {stage.title}”仍有 {missing} 分钟"
                    f"未能重排：{reason}。"
                ),
                task_ids=[goal.id, stage.id],
                details={
                    "goal_id": goal.id,
                    "stage_id": stage.id,
                    "missing_min": missing,
                    "deadline": goal.deadline.isoformat(),
                    "reason": reason,
                },
                recoverable=True,
            )
        )
