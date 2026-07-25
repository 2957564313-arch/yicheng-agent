from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import sqrt
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.schemas.common import Issue, IssueSeverity
from app.schemas.weekly import (
    AllocationStatus,
    DailyCapacity,
    DayAllocation,
    EnergyLevel,
    GoalStage,
    GoalStageCreate,
    GoalStatus,
    StageStatus,
    WeeklyGoal,
    WeeklyGoalCreate,
    WeeklyPlan,
    WeeklyPlanCreateRequest,
    WeeklyPlanMetrics,
    WeeklyPlanStatus,
    WeeklyTriggerType,
)


@dataclass(slots=True)
class _FreeSegment:
    start_at: datetime
    end_at: datetime
    energy_level: EnergyLevel
    location_id: str | None

    @property
    def duration_min(self) -> int:
        return max(
            0,
            int((self.end_at - self.start_at).total_seconds() // 60),
        )


class WeeklyAllocator:
    """Deterministic cross-day allocator.

    Weekly planning decides which day owns each goal chunk. Exact travel,
    opening-hour and weather checks remain the responsibility of the daily
    planner when an allocation is materialised.
    """

    def allocate(
        self,
        request: WeeklyPlanCreateRequest,
        *,
        version: int = 1,
        baseline_plan_id: str | None = None,
        trigger_type: WeeklyTriggerType = WeeklyTriggerType.INITIAL,
        now: datetime | None = None,
    ) -> WeeklyPlan:
        timezone = ZoneInfo(request.timezone)
        current_time = now or datetime.now(timezone)
        if current_time.tzinfo is None:
            raise ValueError("周规划生成时间必须包含时区")
        current_time = current_time.astimezone(timezone)
        plan_id = f"weekly_plan_{uuid4().hex}"
        week_end = request.week_start + timedelta(days=6)

        goals = [
            self._build_goal(
                payload,
                user_id=request.user_id,
                campus_id=request.campus_id,
                week_start=request.week_start,
                now=current_time,
            )
            for payload in request.goals
        ]
        segments = self._build_segments(request.capacities)
        allocations: list[DayAllocation] = []
        issues: list[Issue] = []
        day_load: dict[date, int] = defaultdict(int)
        goal_day_chunks: dict[tuple[str, date], int] = defaultdict(int)

        ordered_goals = sorted(
            goals,
            key=lambda goal: (
                not goal.hard_deadline,
                goal.deadline,
                -goal.importance,
                goal.total_duration_min,
                goal.id,
            ),
        )
        for goal in ordered_goals:
            stage_finish: dict[str, datetime] = {}
            ordered_stages = self._topological_stages(goal.stages)
            for stage in ordered_stages:
                dependency_ready = max(
                    (
                        stage_finish[dependency_id]
                        for dependency_id in stage.depends_on_stage_ids
                    ),
                    default=goal.earliest_start
                    or datetime.combine(
                        request.week_start,
                        datetime.min.time(),
                        timezone,
                    ),
                )
                stage_allocations, missing = self._allocate_stage(
                    plan_id=plan_id,
                    goal=goal,
                    stage=stage,
                    segments=segments,
                    dependency_ready=dependency_ready,
                    day_load=day_load,
                    goal_day_chunks=goal_day_chunks,
                    now=current_time,
                )
                allocations.extend(stage_allocations)
                stage.remaining_duration_min = stage.duration_min
                stage.status = (
                    StageStatus.ACTIVE
                    if stage_allocations
                    else StageStatus.PENDING
                )
                if stage_allocations:
                    stage_finish[stage.id] = max(
                        item.latest_end for item in stage_allocations
                    )
                else:
                    stage_finish[stage.id] = dependency_ready
                if missing:
                    subject = (
                        goal.title
                        if stage.title == goal.title
                        else f"{goal.title} / {stage.title}"
                    )
                    issues.append(
                        Issue(
                            code="WEEKLY_CAPACITY_SHORTAGE",
                            severity=(
                                IssueSeverity.ERROR
                                if goal.hard_deadline
                                else IssueSeverity.WARNING
                            ),
                            message=(
                                f"“{subject}”"
                                f"仍有 {missing} 分钟未能在本周可用时间内安排"
                            ),
                            task_ids=[goal.id, stage.id],
                            details={
                                "goal_id": goal.id,
                                "stage_id": stage.id,
                                "missing_min": missing,
                                "deadline": goal.deadline.isoformat(),
                            },
                            recoverable=True,
                        )
                    )
            goal.remaining_duration_min = goal.total_duration_min
            goal.status = (
                GoalStatus.ACTIVE
                if any(
                    item.goal_id == goal.id for item in allocations
                )
                else GoalStatus.PENDING
            )

        requested = sum(goal.total_duration_min for goal in goals)
        allocated = sum(
            item.allocated_duration_min for item in allocations
        )
        hard_violations = sum(
            issue.severity == IssueSeverity.ERROR for issue in issues
        )
        at_risk_goals = len(
            {
                issue.details.get("goal_id")
                for issue in issues
                if issue.details.get("goal_id")
            }
        )
        status = WeeklyPlanStatus.VALID
        if hard_violations:
            status = WeeklyPlanStatus.INFEASIBLE
        elif issues:
            status = WeeklyPlanStatus.AT_RISK
        metrics = WeeklyPlanMetrics(
            requested_duration_min=requested,
            allocated_duration_min=allocated,
            unallocated_duration_min=max(0, requested - allocated),
            hard_violation_count=hard_violations,
            at_risk_goal_count=at_risk_goals,
            workload_balance_score=self._balance_score(
                day_load,
                request.capacities,
            ),
        )
        return WeeklyPlan(
            id=plan_id,
            user_id=request.user_id,
            campus_id=request.campus_id,
            week_start=request.week_start,
            week_end=week_end,
            timezone=request.timezone,
            version=version,
            status=status,
            baseline_plan_id=baseline_plan_id,
            trigger_type=trigger_type,
            goals=goals,
            allocations=sorted(
                allocations,
                key=lambda item: (
                    item.date,
                    item.earliest_start,
                    item.goal_id,
                ),
            ),
            issues=issues,
            metrics=metrics,
            created_at=current_time,
            updated_at=current_time,
        )

    @staticmethod
    def _build_goal(
        payload: WeeklyGoalCreate,
        *,
        user_id: str,
        campus_id: str,
        week_start: date,
        now: datetime,
    ) -> WeeklyGoal:
        goal_id = f"weekly_goal_{uuid4().hex}"
        stage_payloads = payload.stages or [
            GoalStageCreate(
                id="default",
                title=payload.title,
                duration_min=payload.total_duration_min,
                splittable=payload.splittable,
                min_chunk_min=payload.min_chunk_min,
                preferred_location=(
                    payload.preferred_locations[0]
                    if payload.preferred_locations
                    else None
                ),
            )
        ]
        aliases: dict[str, str] = {}
        for index, stage in enumerate(stage_payloads, start=1):
            alias = stage.id or f"stage_{index}"
            aliases[alias] = f"goal_stage_{uuid4().hex}"
        stages = []
        for index, stage in enumerate(stage_payloads, start=1):
            alias = stage.id or f"stage_{index}"
            stages.append(
                GoalStage(
                    id=aliases[alias],
                    goal_id=goal_id,
                    title=stage.title,
                    sequence=stage.sequence or index,
                    duration_min=stage.duration_min,
                    remaining_duration_min=stage.duration_min,
                    depends_on_stage_ids=[
                        aliases[item]
                        for item in stage.depends_on_stage_ids
                    ],
                    splittable=stage.splittable,
                    min_chunk_min=stage.min_chunk_min,
                    preferred_location=stage.preferred_location,
                    completion_criteria=stage.completion_criteria,
                    status=StageStatus.PENDING,
                    created_at=now,
                    updated_at=now,
                )
            )
        return WeeklyGoal(
            id=goal_id,
            user_id=user_id,
            campus_id=campus_id,
            week_start=week_start,
            title=payload.title,
            description=payload.description,
            earliest_start=payload.earliest_start,
            deadline=payload.deadline,
            total_duration_min=payload.total_duration_min,
            remaining_duration_min=payload.total_duration_min,
            splittable=payload.splittable,
            min_chunk_min=payload.min_chunk_min,
            max_chunk_min=payload.max_chunk_min,
            max_chunks_per_day=payload.max_chunks_per_day,
            importance=payload.importance,
            hard_deadline=payload.hard_deadline,
            preferred_periods=list(payload.preferred_periods),
            avoided_periods=list(payload.avoided_periods),
            preferred_locations=list(payload.preferred_locations),
            energy_level=payload.energy_level,
            status=GoalStatus.PENDING,
            stages=stages,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _topological_stages(stages: list[GoalStage]) -> list[GoalStage]:
        by_id = {stage.id: stage for stage in stages}
        pending = set(by_id)
        resolved: set[str] = set()
        ordered: list[GoalStage] = []
        while pending:
            ready = sorted(
                (
                    by_id[stage_id]
                    for stage_id in pending
                    if set(
                        by_id[stage_id].depends_on_stage_ids
                    ) <= resolved
                ),
                key=lambda stage: (stage.sequence, stage.id),
            )
            if not ready:
                raise ValueError("目标阶段依赖存在循环，无法生成周计划")
            for stage in ready:
                ordered.append(stage)
                resolved.add(stage.id)
                pending.remove(stage.id)
        return ordered

    @staticmethod
    def _build_segments(
        capacities: list[DailyCapacity],
    ) -> list[_FreeSegment]:
        segments: list[_FreeSegment] = []
        for capacity in sorted(capacities, key=lambda item: item.date):
            reserved = capacity.reserved_min
            for window in sorted(
                capacity.windows,
                key=lambda item: item.start_at,
            ):
                start_at = window.start_at
                end_at = window.end_at
                if reserved:
                    deduction = min(
                        reserved,
                        int(
                            (end_at - start_at).total_seconds() // 60
                        ),
                    )
                    start_at += timedelta(minutes=deduction)
                    reserved -= deduction
                if end_at > start_at:
                    for slice_start, slice_end in (
                        WeeklyAllocator._period_slices(start_at, end_at)
                    ):
                        segments.append(
                            _FreeSegment(
                                start_at=slice_start,
                                end_at=slice_end,
                                energy_level=window.energy_level,
                                location_id=window.location_id,
                            )
                        )
        return segments

    @staticmethod
    def _period_slices(
        start_at: datetime,
        end_at: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """Split broad windows where morning/afternoon/evening change.

        Without these boundaries a 07:00—22:30 window is classified only by
        its 07:00 start, so an explicit “尽量晚上” preference can never win.
        """
        boundaries = [
            start_at.replace(hour=12, minute=0, second=0, microsecond=0),
            start_at.replace(hour=18, minute=0, second=0, microsecond=0),
        ]
        points = [
            start_at,
            *[
                boundary
                for boundary in boundaries
                if start_at < boundary < end_at
            ],
            end_at,
        ]
        return list(zip(points, points[1:]))

    def _allocate_stage(
        self,
        *,
        plan_id: str,
        goal: WeeklyGoal,
        stage: GoalStage,
        segments: list[_FreeSegment],
        dependency_ready: datetime,
        day_load: dict[date, int],
        goal_day_chunks: dict[tuple[str, date], int],
        now: datetime,
    ) -> tuple[list[DayAllocation], int]:
        remaining = stage.duration_min
        result: list[DayAllocation] = []
        min_chunk = max(stage.min_chunk_min, goal.min_chunk_min)
        if not stage.splittable or not goal.splittable:
            min_chunk = remaining

        while remaining > 0:
            candidates = []
            for segment_index, segment in enumerate(segments):
                start_at = max(segment.start_at, dependency_ready, now)
                if goal.earliest_start:
                    start_at = max(start_at, goal.earliest_start)
                end_at = min(segment.end_at, goal.deadline)
                available = max(
                    0,
                    int((end_at - start_at).total_seconds() // 60),
                )
                if available < min(min_chunk, remaining):
                    continue
                key = (goal.id, start_at.date())
                if goal_day_chunks[key] >= goal.max_chunks_per_day:
                    continue
                period = self._period_for(start_at)
                if period in goal.avoided_periods:
                    period_penalty = 2
                elif period in goal.preferred_periods:
                    period_penalty = 0
                else:
                    period_penalty = 1
                energy_penalty = (
                    0
                    if segment.energy_level == goal.energy_level
                    else 1
                )
                ranking = (
                    (
                        start_at.date(),
                        period_penalty,
                        energy_penalty,
                        day_load[start_at.date()],
                        start_at,
                    )
                    if len(goal.stages) > 1
                    else (
                        period_penalty,
                        energy_penalty,
                        day_load[start_at.date()],
                        start_at.date(),
                        start_at,
                    )
                )
                candidates.append(
                    (
                        ranking,
                        start_at,
                        end_at,
                        segment_index,
                        segment,
                    )
                )
            if not candidates:
                break
            (
                _ranking,
                start_at,
                end_at,
                _segment_index,
                segment,
            ) = min(candidates)
            available = int((end_at - start_at).total_seconds() // 60)
            if not stage.splittable or not goal.splittable:
                chunk = remaining
            else:
                chunk = min(remaining, goal.max_chunk_min, available)
                leftover = remaining - chunk
                if 0 < leftover < min_chunk:
                    adjusted = chunk - (min_chunk - leftover)
                    if adjusted >= min_chunk:
                        chunk = adjusted
                    elif remaining <= available:
                        chunk = remaining
            if chunk < min(min_chunk, remaining):
                break

            allocation_end = start_at + timedelta(minutes=chunk)
            urgency_hours = max(
                1.0,
                (goal.deadline - start_at).total_seconds() / 3600,
            )
            allocation = DayAllocation(
                id=f"day_allocation_{uuid4().hex}",
                weekly_plan_id=plan_id,
                date=start_at.date(),
                goal_id=goal.id,
                stage_id=stage.id,
                allocated_duration_min=chunk,
                earliest_start=start_at,
                latest_end=allocation_end,
                preferred_period=self._period_for(start_at),
                location_id=(
                    stage.preferred_location
                    or (
                        goal.preferred_locations[0]
                        if goal.preferred_locations
                        else segment.location_id
                    )
                ),
                priority_score=float(
                    goal.importance * 20
                    + (30 if goal.hard_deadline else 0)
                ),
                risk_score=round(
                    min(100.0, 100.0 / urgency_hours),
                    2,
                ),
                status=AllocationStatus.PROPOSED,
                created_at=now,
                updated_at=now,
            )
            result.append(allocation)
            remaining -= chunk
            day_load[start_at.date()] += chunk
            goal_day_chunks[(goal.id, start_at.date())] += 1
            segment.start_at = allocation_end
            dependency_ready = allocation_end
        return result, remaining

    @staticmethod
    def _period_for(value: datetime) -> str:
        if value.hour < 12:
            return "morning"
        if value.hour < 18:
            return "afternoon"
        return "evening"

    @staticmethod
    def _balance_score(
        day_load: dict[date, int],
        capacities: list[DailyCapacity],
    ) -> float:
        active_dates = [
            capacity.date
            for capacity in capacities
            if capacity.total_available_min > 0
        ]
        if len(active_dates) <= 1:
            return 1.0
        loads = [day_load.get(item, 0) for item in active_dates]
        mean = sum(loads) / len(loads)
        if mean <= 0:
            return 1.0
        variance = sum((value - mean) ** 2 for value in loads) / len(loads)
        coefficient = sqrt(variance) / mean
        return round(max(0.0, min(1.0, 1.0 - coefficient)), 4)
