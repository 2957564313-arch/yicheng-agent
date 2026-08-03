from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from itertools import permutations
from typing import Any
from zoneinfo import ZoneInfo

from app.schemas.common import (
    DataSource,
    Issue,
    IssueSeverity,
    PlanStatus,
    TaskFlexibility,
)
from app.schemas.plan import Plan, PlanItem, PlanMetrics
from app.schemas.task import Task, UserPreferences
from app.schemas.weekly import AllocationStatus, DayAllocation, WeeklyPlan
from app.schemas.weekly_grounding import (
    WeeklyDailyGroundingEvidence,
    WeeklyDailyGroundingResponse,
)
from app.services.scheduler import PlanningContext


class WeeklyGroundingService:
    """Turn cross-day allocations into a validated, persistent daily plan.

    The weekly layer owns goals, stages, and daily capacity.  This service is
    the missing lower layer: it resolves locations, courses, campus opening
    rules, travel, congestion, and weather before a day is considered
    executable.  Invalid days are returned with issues and are never silently
    persisted as successful plans.
    """

    def __init__(
        self,
        *,
        settings,
        campus_profile: dict[str, Any],
        plans,
        weekly_plans,
        timetables,
        academic_calendar,
        locations,
        routes,
        weather,
        rules,
        scheduler,
        validator,
        class_periods,
    ) -> None:
        self.settings = settings
        self.campus_profile = campus_profile
        self.plans = plans
        self.weekly_plans = weekly_plans
        self.timetables = timetables
        self.academic_calendar = academic_calendar
        self.locations = locations
        self.routes = routes
        self.weather = weather
        self.rules = rules
        self.scheduler = scheduler
        self.validator = validator
        self.class_periods = class_periods

    async def materialize_day(
        self,
        *,
        plan_id: str,
        user_id: str,
        target_date: date,
        prefer_live: bool = True,
        now: datetime | None = None,
    ) -> WeeklyDailyGroundingResponse:
        weekly_plan = self.weekly_plans.get(plan_id)
        if weekly_plan is None or weekly_plan.user_id != user_id:
            raise LookupError("WEEKLY_PLAN_NOT_FOUND")
        if not weekly_plan.week_start <= target_date <= weekly_plan.week_end:
            raise ValueError("target date is outside the weekly plan")

        allocations = self._active_allocations(weekly_plan, target_date)
        allocation_ids = [item.id for item in allocations]
        if not allocations:
            return WeeklyDailyGroundingResponse(
                status="empty",
                weekly_plan_id=plan_id,
                date=target_date,
            )

        existing = self._existing_grounded_plan(
            weekly_plan=weekly_plan,
            allocations=allocations,
            target_date=target_date,
        )
        if existing is not None:
            return WeeklyDailyGroundingResponse(
                status="already_grounded",
                weekly_plan_id=plan_id,
                date=target_date,
                allocation_ids=allocation_ids,
                plan=existing,
            )

        timezone = ZoneInfo(weekly_plan.timezone)
        effective_now = now or datetime.now(timezone)
        if effective_now.tzinfo is None:
            raise ValueError("grounding time must include timezone")
        effective_now = effective_now.astimezone(timezone)

        academic_day = self.academic_calendar.resolve(
            user_id=user_id,
            target_date=target_date,
        )
        course_tasks = self.timetables.tasks_for_date(
            user_id=user_id,
            target_date=target_date,
            class_periods=self.class_periods,
            timezone_name=weekly_plan.timezone,
            effective_weekday=academic_day.effective_weekday,
        )

        allocation_by_task_id: dict[str, DayAllocation] = {}
        tasks = self._allocation_tasks(
            weekly_plan=weekly_plan,
            allocations=allocations,
            allocation_by_task_id=allocation_by_task_id,
        )
        tasks.extend(course_tasks)
        tasks, unknown_location_issues = self._resolve_task_locations(tasks)

        context, evidence = await self._build_context(
            weekly_plan=weekly_plan,
            tasks=tasks,
            target_date=target_date,
            academic_day=academic_day,
            effective_now=effective_now,
            prefer_live=prefer_live,
            course_task_count=len(course_tasks),
        )
        preferences = self._preferences(user_id)

        thread_id = self._thread_id(plan_id=plan_id, target_date=target_date)
        context.old_plan = self._preferred_day_plan(
            weekly_plan=weekly_plan,
            allocations=allocations,
            allocation_by_task_id=allocation_by_task_id,
            thread_id=thread_id,
            created_at=effective_now,
        )
        try:
            result = self.scheduler.schedule(
                user_id=user_id,
                thread_id=thread_id,
                tasks=tasks,
                preferences=preferences,
                context=context,
            )
            validated, issues = self.validator.validate(
                plan=result.plan,
                tasks=tasks,
                context=context,
            )
        except ValueError as exc:
            issues = [
                Issue(
                    code="DAILY_GROUNDING_CONFLICT",
                    severity=IssueSeverity.ERROR,
                    message="当天存在互相冲突的固定安排，无法生成可执行日计划。",
                    details={"reason": str(exc)},
                    recoverable=True,
                )
            ]
            validated = None

        issues = [*unknown_location_issues, *issues]
        hard_errors = [
            issue for issue in issues if issue.severity == IssueSeverity.ERROR
        ]
        if validated is None or hard_errors:
            return WeeklyDailyGroundingResponse(
                status="infeasible",
                weekly_plan_id=plan_id,
                date=target_date,
                allocation_ids=allocation_ids,
                plan=validated,
                issues=issues,
                evidence=evidence,
            )

        expected_task_ids = {
            self._task_id_for_allocation(item) for item in allocations
        }
        allocation_fingerprints = {
            item.id: self.plans.weekly_allocation_fingerprint(item)
            for item in allocations
        }
        published, created = self.plans.publish_weekly_day(
            weekly_plan_id=plan_id,
            user_id=user_id,
            target_date=target_date,
            allocation_ids=allocation_ids,
            allocation_fingerprints=allocation_fingerprints,
            expected_task_ids=expected_task_ids,
            plan=validated,
            now=effective_now,
        )
        return WeeklyDailyGroundingResponse(
            status="grounded" if created else "already_grounded",
            weekly_plan_id=plan_id,
            date=target_date,
            allocation_ids=allocation_ids,
            plan=published,
            issues=issues,
            evidence=evidence,
        )

    @staticmethod
    def _active_allocations(
        weekly_plan: WeeklyPlan,
        target_date: date,
    ) -> list[DayAllocation]:
        return [
            item
            for item in weekly_plan.allocations
            if item.date == target_date
            and item.status
            not in {
                AllocationStatus.COMPLETED,
                AllocationStatus.CANCELLED,
                AllocationStatus.DEFERRED,
            }
        ]

    def _existing_grounded_plan(
        self,
        *,
        weekly_plan: WeeklyPlan,
        allocations: list[DayAllocation],
        target_date: date,
    ):
        expected_task_ids = {
            self._task_id_for_allocation(item) for item in allocations
        }
        plan_ids = {
            item.daily_plan_id for item in allocations if item.daily_plan_id
        }
        if len(plan_ids) == 1:
            existing = self.plans.get(next(iter(plan_ids)))
            if existing is not None and self._covers_weekly_tasks(
                existing,
                expected_task_ids,
            ):
                return existing

        # Legacy unbound plans are recovered inside the atomic publication
        # transaction, never by a separate bind that could race a new writer.
        return None

    def _allocation_tasks(
        self,
        *,
        weekly_plan: WeeklyPlan,
        allocations: list[DayAllocation],
        allocation_by_task_id: dict[str, DayAllocation],
    ) -> list[Task]:
        goals = {goal.id: goal for goal in weekly_plan.goals}
        stages = {
            stage.id: stage
            for goal in weekly_plan.goals
            for stage in goal.stages
        }
        tasks: list[Task] = []
        for allocation in allocations:
            goal = goals[allocation.goal_id]
            stage = stages[allocation.stage_id]
            task_id = self._task_id_for_allocation(allocation)
            allocation_by_task_id[task_id] = allocation
            tasks.append(
                Task(
                    id=task_id,
                    title=(
                        goal.title
                        if stage.title == goal.title
                        else f"{goal.title} · {stage.title}"
                    ),
                    date=allocation.date,
                    duration_min=allocation.allocated_duration_min,
                    location_id=allocation.location_id,
                    location_raw=allocation.location_id,
                    earliest_start=(
                        allocation.window_start_at
                        or allocation.earliest_start
                    ),
                    latest_end=allocation.window_end_at or allocation.latest_end,
                    deadline=min(
                        goal.deadline,
                        allocation.window_end_at or allocation.latest_end,
                    ),
                    flexibility=TaskFlexibility.MOVABLE,
                    importance=goal.importance,
                    preferred_period=allocation.preferred_period,
                    tags=[
                        "weekly_allocation",
                        # The weekly layer proposes a period; daily grounding
                        # may leave it when courses or campus constraints make
                        # another interval on the same day more executable.
                        "memory_period_preference",
                        f"weekly_goal:{goal.id}",
                    ],
                    notes=(
                        "由周目标分层分配生成；日规划必须继续校验课表、"
                        "场馆开放、通勤与天气。"
                    ),
                )
            )
        return tasks

    @staticmethod
    def _preferred_day_plan(
        *,
        weekly_plan: WeeklyPlan,
        allocations: list[DayAllocation],
        allocation_by_task_id: dict[str, DayAllocation],
        thread_id: str,
        created_at: datetime,
    ) -> Plan:
        """Represent weekly proposals as history for minimum-disruption search.

        The weekly layer's exact proposal is a preference, not a hard lock. By
        passing it as the old plan, daily grounding first tries to retain it,
        but can move it when courses, travel, opening rules, or weather require
        a different feasible interval.
        """

        task_id_by_allocation_id = {
            allocation.id: task_id
            for task_id, allocation in allocation_by_task_id.items()
        }
        items: list[PlanItem] = []
        for allocation in allocations:
            start_at = (
                allocation.preferred_start_at
                or allocation.earliest_start
            )
            end_at = allocation.preferred_end_at or (
                start_at
                + (
                    allocation.latest_end
                    - allocation.earliest_start
                )
            )
            task_id = task_id_by_allocation_id[allocation.id]
            items.append(
                PlanItem(
                    id=f"weekly_preference_{task_id}",
                    task_id=task_id,
                    item_type="task",
                    title=task_id,
                    start_at=start_at,
                    end_at=end_at,
                    location_id=allocation.location_id,
                    source=DataSource.STRUCTURED,
                    reason="周计划建议时段，日落地时作为可移动软偏好",
                )
            )
        return Plan(
            id=(
                "weekly_preference_"
                + sha256(weekly_plan.id.encode()).hexdigest()[:24]
            ),
            user_id=weekly_plan.user_id,
            thread_id=thread_id,
            date=allocations[0].date,
            status=PlanStatus.DRAFT,
            version=1,
            items=items,
            metrics=PlanMetrics(
                scheduled_task_count=len(items),
                requested_task_count=len(items),
            ),
            created_at=created_at,
        )

    def _resolve_task_locations(
        self,
        tasks: list[Task],
    ) -> tuple[list[Task], list[Issue]]:
        resolved_tasks: list[Task] = []
        issues: list[Issue] = []
        for task in tasks:
            raw = task.location_raw or task.location_id
            if not raw:
                resolved_tasks.append(task)
                continue
            location = self.locations.get(task.location_id) if task.location_id else None
            location = location or self.locations.resolve(raw)
            if location is None:
                issues.append(
                    Issue(
                        code="UNKNOWN_LOCATION",
                        severity=IssueSeverity.WARNING,
                        message=f"“{raw}”暂未匹配到校园地点库，相关通勤需人工复核。",
                        task_ids=[task.id],
                        details={"location": raw},
                        recoverable=True,
                    )
                )
                resolved_tasks.append(
                    task.model_copy(
                        update={"location_id": None, "location_raw": raw}
                    )
                )
                continue
            tags = list(task.tags)
            if location.is_outdoor and "outdoor" not in tags:
                tags.append("outdoor")
            resolved_tasks.append(
                task.model_copy(
                    update={
                        "location_id": location.id,
                        "location_raw": raw,
                        "tags": tags,
                    }
                )
            )
        return resolved_tasks, issues

    async def _build_context(
        self,
        *,
        weekly_plan: WeeklyPlan,
        tasks: list[Task],
        target_date: date,
        academic_day,
        effective_now: datetime,
        prefer_live: bool,
        course_task_count: int,
    ) -> tuple[PlanningContext, WeeklyDailyGroundingEvidence]:
        location_ids = sorted(
            {task.location_id for task in tasks if task.location_id}
        )
        routes = []
        for origin_id, destination_id in permutations(location_ids, 2):
            try:
                routes.append(
                    await self.routes.get_route(
                        origin_id,
                        destination_id,
                        mode="walk",
                        prefer_live=(
                            prefer_live and self.settings.live_route_enabled
                        ),
                    )
                )
            except LookupError:
                continue

        opening_windows = {}
        for location_id in location_ids:
            if not self.rules.has_applicable_opening_rule(
                location_id,
                target_date,
            ):
                continue
            opening_windows[location_id] = self.rules.opening_windows(
                location_id,
                target_date,
                is_national_holiday=academic_day.day_type == "holiday",
            )

        task_windows = {}
        for task in tasks:
            windows = self.rules.task_windows(
                task_title=task.title,
                location_id=task.location_id,
                target_date=target_date,
            )
            if windows:
                task_windows[task.id] = windows

        weather_adcode = (
            self.settings.weather_city_adcode
            or self.campus_profile.get("external_services", {})
            .get("amap", {})
            .get("weather_adcode")
        )
        weather = await self.weather.get_forecast(
            target_date,
            "campus_main",
            prefer_live=(
                prefer_live and self.settings.live_weather_enabled
            ),
            city_adcode=weather_adcode,
            allow_static=True,
        )
        outdoor_location_ids = {
            location_id
            for location_id in location_ids
            if (
                (location := self.locations.get(location_id))
                and location.is_outdoor
            )
        }
        preferences = self._preferences(weekly_plan.user_id)
        weather_enforced = bool(
            preferences.avoid_rain
            and outdoor_location_ids
            and any(item.source != DataSource.UNKNOWN for item in weather)
        )
        context = PlanningContext(
            target_date=target_date,
            timezone=ZoneInfo(weekly_plan.timezone),
            now=effective_now,
            travel={
                (item.origin_id, item.destination_id): item for item in routes
            },
            congestion_windows=self.rules.congestion_contexts(target_date),
            opening_windows=opening_windows,
            task_windows=task_windows,
            weather=weather,
            outdoor_location_ids=outdoor_location_ids,
            enforce_weather=weather_enforced,
        )
        evidence = WeeklyDailyGroundingEvidence(
            route_sources=sorted(
                {item.source for item in routes},
                key=lambda item: item.value,
            ),
            weather_sources=sorted(
                {item.source for item in weather},
                key=lambda item: item.value,
            ),
            opening_rule_location_ids=sorted(opening_windows),
            timetable_task_count=course_task_count,
            route_pair_count=len(routes),
            weather_enforced=weather_enforced,
        )
        return context, evidence

    def _preferences(self, user_id: str) -> UserPreferences:
        # The weekly capacity builder already consumes enabled memories.  Daily
        # grounding intentionally keeps a conservative deterministic default;
        # explicit per-day preferences remain available through the chat flow.
        return UserPreferences()

    @staticmethod
    def task_id_for_allocation(allocation_id: str) -> str:
        digest = sha256(allocation_id.encode("utf-8")).hexdigest()[:24]
        return f"weekly_{digest}"

    @classmethod
    def _task_id_for_allocation(cls, allocation: DayAllocation) -> str:
        return cls.task_id_for_allocation(
            allocation.lineage_id or allocation.id
        )

    @staticmethod
    def _covers_weekly_tasks(plan: Plan, expected_task_ids: set[str]) -> bool:
        actual_task_ids = {
            item.task_id
            for item in plan.items
            if item.item_type == "task"
            and item.task_id
            and item.task_id.startswith("weekly_")
        }
        return actual_task_ids == expected_task_ids

    @staticmethod
    def _thread_id(*, plan_id: str, target_date: date) -> str:
        digest = sha256(
            f"{plan_id}:{target_date.isoformat()}".encode()
        ).hexdigest()[:24]
        return f"weekly_day_{digest}"
