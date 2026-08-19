from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.schemas.common import (
    DataSource,
    PlanStatus,
    TaskFlexibility,
    TimeWindow,
)
from app.schemas.context import CongestionWindow, TravelEstimate, WeatherContext
from app.schemas.plan import Plan, PlanItem, PlanMetrics
from app.schemas.task import Task, UserPreferences
from app.services.scoring import candidate_cost, task_priority


@dataclass(slots=True)
class PlanningContext:
    target_date: date
    timezone: ZoneInfo
    now: datetime
    travel: dict[tuple[str, str], TravelEstimate] = field(default_factory=dict)
    congestion_windows: list[CongestionWindow] = field(default_factory=list)
    opening_windows: dict[
        str, list[tuple[datetime, datetime]]
    ] = field(default_factory=dict)
    task_windows: dict[
        str, list[tuple[datetime, datetime]]
    ] = field(default_factory=dict)
    weather: list[WeatherContext] = field(default_factory=list)
    outdoor_location_ids: set[str] = field(default_factory=set)
    enforce_weather: bool = False
    day_start: time = time(8, 0)
    # `00:00` represents the end of the target calendar day.  Venue
    # opening windows and task deadlines remain the real hard constraints;
    # the scheduler must not silently impose an older 22:00 product cutoff.
    day_end: time = time(0, 0)
    old_plan: Plan | None = None
    initial_location_id: str | None = None
    initial_departure_at: datetime | None = None
    soft_meal_windows: list[TimeWindow] = field(default_factory=list)

    def travel_minutes(
        self,
        origin_id: str | None,
        destination_id: str | None,
        departure_at: datetime | None = None,
    ) -> int | None:
        duration, _ = self.travel_details(
            origin_id,
            destination_id,
            departure_at=departure_at,
        )
        return duration

    def travel_details(
        self,
        origin_id: str | None,
        destination_id: str | None,
        *,
        departure_at: datetime | None = None,
    ) -> tuple[int | None, int]:
        if not origin_id or not destination_id or origin_id == destination_id:
            return 0, 0
        estimate = self.travel.get((origin_id, destination_id))
        if estimate is None:
            return None, 0
        base_duration = (
            estimate.base_duration_min
            if estimate.base_duration_min is not None
            else estimate.duration_min
        )
        # A separate timeline block adds noise for another room in the same
        # building or for a destination only a few steps away.  The route is
        # still grounded, but the scheduler treats this as local movement.
        if base_duration <= 1 or (
            estimate.distance_m is not None and estimate.distance_m <= 80
        ):
            return 0, 0
        if departure_at is None or not self.congestion_windows:
            return base_duration, 0
        base_end = departure_at + timedelta(minutes=base_duration)
        delays = [
            max(
                window.minimum_extra_min,
                math.ceil(
                    base_duration * (window.duration_multiplier - 1)
                ),
            )
            for window in self.congestion_windows
            if departure_at < window.end_at and base_end > window.start_at
        ]
        delay = max(delays, default=0)
        return base_duration + delay, delay


@dataclass(slots=True)
class SchedulerResult:
    plan: Plan
    unscheduled_task_ids: list[str]
    missing_route_pairs: list[tuple[str, str]]


@dataclass(slots=True)
class _BeamState:
    task_items: list[PlanItem]
    unscheduled_task_ids: list[str]
    missing_route_pairs: set[tuple[str, str]]
    soft_cost: float = 0


class Scheduler:
    replan_beam_width = 48
    replan_candidates_per_task = 36

    def schedule(
        self,
        *,
        user_id: str,
        thread_id: str,
        tasks: list[Task],
        preferences: UserPreferences,
        context: PlanningContext,
        version: int = 1,
    ) -> SchedulerResult:
        task_items: list[PlanItem] = []
        unscheduled: list[str] = []
        missing_route_pairs: set[tuple[str, str]] = set()

        for task in tasks:
            if task.flexibility not in {
                TaskFlexibility.FIXED,
                TaskFlexibility.LOCKED,
            }:
                continue
            task_items.append(
                self._task_item(
                    task,
                    task.fixed_start,
                    task.fixed_end,
                    reason="固定或用户锁定任务",
                )
            )

        task_items.sort(key=lambda item: item.start_at)
        self._raise_if_fixed_overlap(task_items)

        movable = [
            task
            for task in tasks
            if task.flexibility == TaskFlexibility.MOVABLE
        ]
        movable = self._dependency_order(
            movable,
            scheduled_ids={
                item.task_id for item in task_items if item.task_id
            },
            now=context.now,
            timezone=context.timezone,
        )

        old_starts = self._old_task_starts(context.old_plan)
        if context.old_plan is not None and old_starts:
            beam_result = self._schedule_minimum_disruption(
                initial_items=task_items,
                tasks=movable,
                preferences=preferences,
                context=context,
                old_starts=old_starts,
            )
            task_items = beam_result.task_items
            unscheduled = beam_result.unscheduled_task_ids
            missing_route_pairs = beam_result.missing_route_pairs
        else:
            for task in movable:
                has_dependents = any(
                    task.id in candidate.depends_on
                    for candidate in movable
                )
                candidates = list(
                    self._candidate_intervals(
                        task=task,
                        scheduled=task_items,
                        preferences=preferences,
                        context=context,
                        missing_route_pairs=missing_route_pairs,
                    )
                )
                if not candidates:
                    unscheduled.append(task.id)
                    continue

                scored = [
                    (
                        self._candidate_soft_cost(
                            task=task,
                            start_at=start_at,
                            travel_minutes=travel_minutes,
                            preference_penalty=preference_penalty,
                            old_start=old_starts.get(task.id),
                            has_dependents=has_dependents,
                            context=context,
                        ),
                        start_at,
                        end_at,
                    )
                    for (
                        start_at,
                        end_at,
                        travel_minutes,
                        preference_penalty,
                    ) in candidates
                ]
                _, start_at, end_at = min(
                    scored,
                    key=lambda item: (item[0], item[1]),
                )
                task_items.append(
                    self._task_item(
                        task,
                        start_at,
                        end_at,
                        reason="依据优先级、通勤和可用时间窗安排",
                    )
                )
                task_items.sort(key=lambda item: item.start_at)

        plan_items = self._insert_travel_items(
            task_items,
            context,
            missing_route_pairs,
            preferences,
        )
        metrics = PlanMetrics(
            scheduled_task_count=len(task_items),
            requested_task_count=len(tasks),
            travel_minutes=sum(
                int((item.end_at - item.start_at).total_seconds() // 60)
                for item in plan_items
                if item.item_type == "travel"
            ),
        )
        plan = Plan(
            id=f"plan_{uuid4().hex}",
            user_id=user_id,
            thread_id=thread_id,
            date=context.target_date,
            status=PlanStatus.DRAFT,
            version=version,
            items=plan_items,
            metrics=metrics,
            created_at=context.now,
        )
        return SchedulerResult(
            plan=plan,
            unscheduled_task_ids=unscheduled,
            missing_route_pairs=sorted(missing_route_pairs),
        )

    def _schedule_minimum_disruption(
        self,
        *,
        initial_items: list[PlanItem],
        tasks: list[Task],
        preferences: UserPreferences,
        context: PlanningContext,
        old_starts: dict[str, datetime],
    ) -> _BeamState:
        """Bounded global search with a lexicographic replan objective.

        Hard constraints are enforced while candidates are generated.  Among
        feasible states we first retain task coverage, then minimise the number
        of moved existing tasks, total shift, and finally travel/preference
        cost.  This avoids the cascade where moving one task into another
        task's old slot needlessly moves both.
        """

        beam = [
            _BeamState(
                task_items=list(initial_items),
                unscheduled_task_ids=[],
                missing_route_pairs=set(),
            )
        ]
        for task in tasks:
            expanded: list[_BeamState] = []
            has_dependents = any(
                task.id in candidate.depends_on for candidate in tasks
            )
            for state in beam:
                candidate_missing_pairs = set(state.missing_route_pairs)
                candidates = list(
                    self._candidate_intervals(
                        task=task,
                        scheduled=state.task_items,
                        preferences=preferences,
                        context=context,
                        missing_route_pairs=candidate_missing_pairs,
                    )
                )
                ranked = sorted(
                    candidates,
                    key=lambda item: (
                        self._candidate_soft_cost(
                            task=task,
                            start_at=item[0],
                            travel_minutes=item[2],
                            preference_penalty=item[3],
                            old_start=old_starts.get(task.id),
                            has_dependents=has_dependents,
                            context=context,
                        ),
                        item[0],
                    ),
                )[: self.replan_candidates_per_task]
                if not ranked:
                    expanded.append(
                        _BeamState(
                            task_items=list(state.task_items),
                            unscheduled_task_ids=[
                                *state.unscheduled_task_ids,
                                task.id,
                            ],
                            missing_route_pairs=candidate_missing_pairs,
                            soft_cost=state.soft_cost,
                        )
                    )
                    continue

                for (
                    start_at,
                    end_at,
                    travel_minutes,
                    preference_penalty,
                ) in ranked:
                    item = self._task_item(
                        task,
                        start_at,
                        end_at,
                        reason=(
                            "按全局最小扰动目标保留原计划，并同时满足"
                            "通勤和可用时间窗"
                        ),
                    )
                    child_items = sorted(
                        [*state.task_items, item],
                        key=lambda value: value.start_at,
                    )
                    expanded.append(
                        _BeamState(
                            task_items=child_items,
                            unscheduled_task_ids=list(
                                state.unscheduled_task_ids
                            ),
                            missing_route_pairs=set(
                                candidate_missing_pairs
                            ),
                            soft_cost=(
                                state.soft_cost
                                + self._candidate_soft_cost(
                                    task=task,
                                    start_at=start_at,
                                    travel_minutes=travel_minutes,
                                    preference_penalty=preference_penalty,
                                    old_start=old_starts.get(task.id),
                                    has_dependents=has_dependents,
                                    context=context,
                                )
                            ),
                        )
                    )

            deduplicated: dict[tuple, _BeamState] = {}
            for state in expanded:
                signature = tuple(
                    (
                        item.task_id,
                        item.start_at,
                        item.end_at,
                    )
                    for item in state.task_items
                    if item.item_type == "task"
                )
                current = deduplicated.get(signature)
                if current is None or self._beam_score(
                    state,
                    old_starts,
                ) < self._beam_score(current, old_starts):
                    deduplicated[signature] = state
            beam = sorted(
                deduplicated.values(),
                key=lambda state: self._beam_score(state, old_starts),
            )[: self.replan_beam_width]

        return min(
            beam,
            key=lambda state: self._beam_score(state, old_starts),
        )

    @staticmethod
    def _beam_score(
        state: _BeamState,
        old_starts: dict[str, datetime],
    ) -> tuple:
        shifts = [
            int(
                abs(
                    (
                        item.start_at - old_starts[item.task_id]
                    ).total_seconds()
                )
                // 60
            )
            for item in state.task_items
            if item.task_id in old_starts
        ]
        return (
            len(state.unscheduled_task_ids),
            sum(shift > 0 for shift in shifts),
            sum(shifts),
            round(state.soft_cost, 6),
            tuple(
                (item.task_id or "", item.start_at.isoformat())
                for item in state.task_items
                if item.item_type == "task"
            ),
        )

    @staticmethod
    def _candidate_soft_cost(
        *,
        task: Task,
        start_at: datetime,
        travel_minutes: int,
        preference_penalty: int,
        old_start: datetime | None,
        has_dependents: bool,
        context: PlanningContext,
    ) -> float:
        shift_minutes = (
            int(abs((start_at - old_start).total_seconds()) // 60)
            if old_start
            else 0
        )
        scheduling_delay_minutes = (
            max(
                0,
                int(
                    (
                        start_at
                        - (
                            task.earliest_start
                            or datetime.combine(
                                context.target_date,
                                context.day_start,
                                context.timezone,
                            )
                        )
                    ).total_seconds()
                    // 60
                ),
            )
            if has_dependents
            else 0
        )
        return candidate_cost(
            travel_minutes=travel_minutes,
            preference_penalty=preference_penalty,
            shift_minutes=shift_minutes,
            scheduling_delay_minutes=scheduling_delay_minutes,
        )

    @staticmethod
    def _dependency_order(
        tasks: list[Task],
        *,
        scheduled_ids: set[str],
        now: datetime,
        timezone: ZoneInfo,
    ) -> list[Task]:
        """Honor explicit task order before applying urgency scoring."""
        remaining = list(tasks)
        ordered: list[Task] = []
        known_ids = scheduled_ids | {task.id for task in tasks}

        def priority_key(task: Task):
            return (
                -task_priority(task, now),
                task.deadline or datetime.max.replace(tzinfo=timezone),
                task.id,
            )

        while remaining:
            completed = scheduled_ids | {task.id for task in ordered}
            eligible = [
                task
                for task in remaining
                if {
                    dependency
                    for dependency in task.depends_on
                    if dependency in known_ids
                }
                <= completed
            ]
            if not eligible:
                eligible = remaining
            chosen = min(eligible, key=priority_key)
            ordered.append(chosen)
            remaining.remove(chosen)
        return ordered

    def _candidate_intervals(
        self,
        *,
        task: Task,
        scheduled: list[PlanItem],
        preferences: UserPreferences,
        context: PlanningContext,
        missing_route_pairs: set[tuple[str, str]],
    ) -> Iterable[tuple[datetime, datetime, int, int]]:
        day_start = datetime.combine(
            context.target_date,
            context.day_start,
            context.timezone,
        )
        day_end = datetime.combine(
            context.target_date,
            context.day_end,
            context.timezone,
        )
        if context.day_end <= context.day_start:
            day_end += timedelta(days=1)
        if context.target_date == context.now.date():
            day_start = max(
                day_start,
                self._ceil_five_minutes(context.now),
            )

        search_start = max(day_start, task.earliest_start or day_start)
        search_end = min(
            day_end,
            task.latest_end or day_end,
            task.deadline or day_end,
        )
        period_window = self._preferred_window(
            task.preferred_period,
            context.target_date,
            context.timezone,
        )
        soft_period_preference = (
            "memory_period_preference" in task.tags
        )
        if period_window and not soft_period_preference:
            search_start = max(search_start, period_window[0])
            search_end = min(search_end, period_window[1])

        cursor = self._ceil_five_minutes(search_start)
        duration = timedelta(minutes=task.duration_min)
        while cursor + duration <= search_end:
            end_at = cursor + duration
            if not self._inside_opening_hours(
                task.id,
                task.location_id,
                cursor,
                end_at,
                context,
            ):
                cursor += timedelta(minutes=5)
                continue
            if self._violates_weather(task, cursor, end_at, context):
                cursor += timedelta(minutes=5)
                continue
            if self._overlaps_meal_window(
                task,
                cursor,
                end_at,
                preferences,
                context,
            ):
                cursor += timedelta(minutes=5)
                continue

            meal_penalty = int(
                self._overlaps_windows(
                    task,
                    cursor,
                    end_at,
                    context.soft_meal_windows,
                    context,
                )
            )

            previous, following = self._neighbors(cursor, end_at, scheduled)
            if previous is False or following is False:
                cursor += timedelta(minutes=5)
                continue

            use_initial_origin = bool(
                context.initial_location_id
                and context.initial_departure_at
                and cursor >= context.initial_departure_at
                and (
                    previous is None
                    or previous.end_at <= context.initial_departure_at
                )
            )
            before_origin_id = (
                context.initial_location_id
                if use_initial_origin
                else (previous.location_id if previous else None)
            )
            before_departure_at = (
                context.initial_departure_at
                if use_initial_origin
                else (previous.end_at if previous else None)
            )
            before_travel, before_delay = self._required_travel(
                before_origin_id,
                task.location_id,
                context,
                missing_route_pairs,
                departure_at=before_departure_at,
            )
            after_travel, after_delay = self._required_travel(
                task.location_id,
                following.location_id if following else None,
                context,
                missing_route_pairs,
                departure_at=end_at,
            )
            if before_travel is None or after_travel is None:
                cursor += timedelta(minutes=5)
                continue

            buffer_min = preferences.buffer_min
            if (
                use_initial_origin
                and context.initial_departure_at
                and context.initial_departure_at
                + timedelta(minutes=before_travel + buffer_min)
                > cursor
            ):
                cursor += timedelta(minutes=5)
                continue
            if previous and (
                previous.end_at
                + timedelta(minutes=before_travel + buffer_min)
                > cursor
            ):
                cursor += timedelta(minutes=5)
                continue
            if following and (
                end_at
                + timedelta(minutes=after_travel + buffer_min)
                > following.start_at
            ):
                cursor += timedelta(minutes=5)
                continue

            dependency_end = self._dependency_end(task, scheduled)
            if dependency_end and cursor < dependency_end:
                cursor += timedelta(minutes=5)
                continue

            congestion_penalty = int(
                preferences.avoid_congestion
                and (before_delay > 0 or after_delay > 0)
            )
            period_penalty = int(
                bool(
                    soft_period_preference
                    and period_window
                    and not (
                        period_window[0] <= cursor
                        and end_at <= period_window[1]
                    )
                )
            )
            yield (
                cursor,
                end_at,
                before_travel + after_travel,
                congestion_penalty + period_penalty + meal_penalty,
            )
            cursor += timedelta(minutes=5)

    @staticmethod
    def _overlaps_meal_window(
        task: Task,
        start_at: datetime,
        end_at: datetime,
        preferences: UserPreferences,
        context: PlanningContext,
    ) -> bool:
        return Scheduler._overlaps_windows(
            task,
            start_at,
            end_at,
            preferences.meal_windows,
            context,
        )

    @staticmethod
    def _overlaps_windows(
        task: Task,
        start_at: datetime,
        end_at: datetime,
        windows: list[TimeWindow],
        context: PlanningContext,
    ) -> bool:
        text = f"{task.title} {' '.join(task.tags)}".lower()
        if any(
            marker in text
            for marker in ("吃饭", "用餐", "午餐", "晚餐", "meal")
        ):
            return False
        for window in windows:
            window_start = datetime.combine(
                context.target_date,
                window.start,
                context.timezone,
            )
            window_end = datetime.combine(
                context.target_date,
                window.end,
                context.timezone,
            )
            if start_at < window_end and end_at > window_start:
                return True
        return False

    @staticmethod
    def _violates_weather(
        task: Task,
        start_at: datetime,
        end_at: datetime,
        context: PlanningContext,
    ) -> bool:
        if not context.enforce_weather:
            return False
        is_outdoor = (
            "outdoor" in task.tags
            or task.location_id in context.outdoor_location_ids
        )
        if not is_outdoor:
            return False
        risk_starts = [
            item.risk_start_at
            for item in context.weather
            if item.risk_start_at
            and (
                (item.rain_probability or 0) >= 0.5
                or "rain" in (item.condition or "").lower()
                or "雨" in (item.condition or "")
            )
        ]
        return bool(risk_starts and end_at > min(risk_starts))

    @staticmethod
    def _neighbors(
        start_at: datetime,
        end_at: datetime,
        scheduled: list[PlanItem],
    ) -> tuple[PlanItem | None | bool, PlanItem | None | bool]:
        previous: PlanItem | None = None
        following: PlanItem | None = None
        for item in sorted(scheduled, key=lambda value: value.start_at):
            if item.end_at <= start_at:
                previous = item
                continue
            if item.start_at >= end_at:
                following = item
                break
            return False, False
        return previous, following

    @staticmethod
    def _required_travel(
        origin_id: str | None,
        destination_id: str | None,
        context: PlanningContext,
        missing_route_pairs: set[tuple[str, str]],
        *,
        departure_at: datetime | None,
    ) -> tuple[int | None, int]:
        duration, delay = context.travel_details(
            origin_id,
            destination_id,
            departure_at=departure_at,
        )
        if duration is None and origin_id and destination_id:
            missing_route_pairs.add((origin_id, destination_id))
        return duration, delay

    @staticmethod
    def _inside_opening_hours(
        task_id: str,
        location_id: str | None,
        start_at: datetime,
        end_at: datetime,
        context: PlanningContext,
    ) -> bool:
        venue_windows = (
            context.opening_windows.get(location_id)
            if location_id
            else None
        )
        activity_windows = context.task_windows.get(task_id)
        for windows in (venue_windows, activity_windows):
            if windows is not None and not any(
                window_start <= start_at and end_at <= window_end
                for window_start, window_end in windows
            ):
                return False
        return True

    @staticmethod
    def _preferred_window(
        period: str | None,
        target_date: date,
        timezone: ZoneInfo,
    ) -> tuple[datetime, datetime] | None:
        periods = {
            "morning": (time(8, 0), time(12, 0)),
            "上午": (time(8, 0), time(12, 0)),
            "afternoon": (time(13, 0), time(18, 0)),
            "下午": (time(13, 0), time(18, 0)),
            "evening": (time(18, 0), time(22, 0)),
            "晚上": (time(18, 0), time(22, 0)),
        }
        raw = periods.get(period or "")
        if not raw:
            return None
        return (
            datetime.combine(target_date, raw[0], timezone),
            datetime.combine(target_date, raw[1], timezone),
        )

    @staticmethod
    def _ceil_five_minutes(value: datetime) -> datetime:
        value = value.replace(second=0, microsecond=0)
        remainder = value.minute % 5
        return (
            value
            if remainder == 0
            else value + timedelta(minutes=5 - remainder)
        )

    @staticmethod
    def _dependency_end(
        task: Task,
        scheduled: list[PlanItem],
    ) -> datetime | None:
        ends = [
            item.end_at
            for item in scheduled
            if item.task_id in task.depends_on
        ]
        return max(ends) if ends else None

    @staticmethod
    def _task_item(
        task: Task,
        start_at: datetime | None,
        end_at: datetime | None,
        *,
        reason: str,
    ) -> PlanItem:
        if start_at is None or end_at is None:
            raise ValueError(f"task {task.id} has no concrete interval")
        return PlanItem(
            id=f"item_{uuid4().hex}",
            task_id=task.id,
            item_type="task",
            title=task.title,
            start_at=start_at,
            end_at=end_at,
            location_id=task.location_id,
            location_raw=task.location_raw,
            locked=task.flexibility in {
                TaskFlexibility.FIXED,
                TaskFlexibility.LOCKED,
            },
            source=DataSource.USER,
            reason=reason,
        )

    @staticmethod
    def _raise_if_fixed_overlap(items: list[PlanItem]) -> None:
        for previous, current in pairwise(items):
            if current.start_at < previous.end_at:
                raise ValueError(
                    "fixed tasks overlap: "
                    f"{previous.task_id} and {current.task_id}"
                )

    @staticmethod
    def _old_task_starts(plan: Plan | None) -> dict[str, datetime]:
        if not plan:
            return {}
        return {
            item.task_id: item.start_at
            for item in plan.items
            if item.item_type == "task" and item.task_id
        }

    @staticmethod
    def _insert_travel_items(
        task_items: list[PlanItem],
        context: PlanningContext,
        missing_route_pairs: set[tuple[str, str]],
        preferences: UserPreferences,
    ) -> list[PlanItem]:
        ordered = sorted(task_items, key=lambda item: item.start_at)
        result: list[PlanItem] = []
        if context.initial_location_id and context.initial_departure_at:
            first_after_departure = next(
                (
                    item
                    for item in ordered
                    if item.start_at >= context.initial_departure_at
                ),
                None,
            )
            if (
                first_after_departure
                and first_after_departure.location_id
                and first_after_departure.location_id
                != context.initial_location_id
            ):
                estimate = context.travel.get(
                    (
                        context.initial_location_id,
                        first_after_departure.location_id,
                    )
                )
                if estimate:
                    duration, congestion_delay = context.travel_details(
                        context.initial_location_id,
                        first_after_departure.location_id,
                        departure_at=context.initial_departure_at,
                    )
                    if duration is not None:
                        base_duration = (
                            estimate.base_duration_min
                            if estimate.base_duration_min is not None
                            else estimate.duration_min
                        )
                        mode_label = {
                            "walk": "步行",
                            "bicycle": "骑自行车",
                            "electrobike": "骑电瓶车",
                        }.get(estimate.mode, "通勤")
                        if duration > 0:
                            result.append(
                                PlanItem(
                                    id=f"travel_{uuid4().hex}",
                                    item_type="travel",
                                    title=(
                                        f"{mode_label}前往"
                                        f"{first_after_departure.title}地点"
                                    ),
                                    start_at=context.initial_departure_at,
                                    end_at=context.initial_departure_at
                                    + timedelta(minutes=duration),
                                    location_id=(
                                        first_after_departure.location_id
                                    ),
                                    source=estimate.source,
                                    reason=(
                                        f"{mode_label}基础时间 "
                                        f"{base_duration} 分钟"
                                        + (
                                            "，校园通行高峰额外预留 "
                                            f"{congestion_delay} 分钟"
                                            if congestion_delay
                                            else ""
                                        )
                                    ),
                                    travel_mode=estimate.mode,
                                    base_duration_min=base_duration,
                                    congestion_delay_min=congestion_delay,
                                )
                            )
                else:
                    missing_route_pairs.add(
                        (
                            context.initial_location_id,
                            first_after_departure.location_id,
                        )
                    )
        for index, item in enumerate(ordered):
            result.append(item)
            if index == len(ordered) - 1:
                continue
            following = ordered[index + 1]
            if not item.location_id or not following.location_id:
                continue
            if item.location_id == following.location_id:
                continue
            estimate = context.travel.get(
                (item.location_id, following.location_id)
            )
            if not estimate:
                missing_route_pairs.add(
                    (item.location_id, following.location_id)
                )
                continue
            base_duration = (
                estimate.base_duration_min
                if estimate.base_duration_min is not None
                else estimate.duration_min
            )
            desired_end = following.start_at - timedelta(
                minutes=preferences.buffer_min
            )
            provisional_start = desired_end - timedelta(
                minutes=base_duration
            )
            adjusted_duration, congestion_delay = context.travel_details(
                item.location_id,
                following.location_id,
                departure_at=provisional_start,
            )
            if adjusted_duration is None:
                continue
            if adjusted_duration <= 0:
                continue
            travel_end = desired_end
            travel_start = travel_end - timedelta(
                minutes=adjusted_duration
            )
            if travel_start < item.end_at:
                travel_start = item.end_at
                adjusted_duration, congestion_delay = context.travel_details(
                    item.location_id,
                    following.location_id,
                    departure_at=travel_start,
                )
                if adjusted_duration is None:
                    continue
                travel_end = travel_start + timedelta(
                    minutes=adjusted_duration
                )
            mode_labels = {
                "walk": "步行",
                "bicycle": "骑自行车",
                "electrobike": "骑电瓶车",
            }
            mode_label = mode_labels.get(estimate.mode, "通勤")
            reason = (
                f"{mode_label}基础时间 {base_duration} 分钟"
                + (
                    f"，校园通行高峰额外预留 {congestion_delay} 分钟"
                    if congestion_delay
                    else ""
                )
            )
            result.append(
                PlanItem(
                    id=f"travel_{uuid4().hex}",
                    item_type="travel",
                    title=f"{mode_label}前往{following.title}地点",
                    start_at=travel_start,
                    end_at=travel_end,
                    location_id=following.location_id,
                    source=estimate.source,
                    reason=reason,
                    travel_mode=estimate.mode,
                    base_duration_min=base_duration,
                    congestion_delay_min=congestion_delay,
                )
            )
        return sorted(result, key=lambda item: item.start_at)
