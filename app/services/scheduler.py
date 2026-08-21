from __future__ import annotations

import math
import re
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
    opening_windows: dict[str, list[tuple[datetime, datetime]]] = field(
        default_factory=dict
    )
    task_windows: dict[str, list[tuple[datetime, datetime]]] = field(
        default_factory=dict
    )
    weather: list[WeatherContext] = field(default_factory=list)
    outdoor_location_ids: set[str] = field(default_factory=set)
    enforce_weather: bool = False
    day_start: time = time(8, 0)
    # `00:00` represents the end of the target calendar day.  Venue
    # opening windows and task deadlines remain the real hard constraints;
    # the scheduler must not silently impose an older 22:00 product cutoff.
    day_end: time = time(0, 0)
    old_plan: Plan | None = None
    # Quick-adjustment buttons steer the objective from here. They must never
    # reach into the task list: rewriting depends_on and importance invented
    # an order the student never asked for and destroyed the one they did.
    objective_bias: str | None = None
    avoid_starts: dict[str, datetime] = field(default_factory=dict)
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
                math.ceil(base_duration * (window.duration_multiplier - 1)),
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
class _Candidate:
    """One placement a task could take, with what it would cost to take it."""

    start_at: datetime
    end_at: datetime
    travel_minutes: int
    preference_penalty: int
    shortfall_minutes: int
    breaks_weather: bool


@dataclass(slots=True)
class _BeamState:
    task_items: list[PlanItem]
    unscheduled_task_ids: list[str]
    missing_route_pairs: set[tuple[str, str]]
    unscheduled_cost: float = 0
    # Loss against the duration the user asked for.  Coverage comes first,
    # but once the same tasks fit we must keep their requested lengths.  This
    # prevents an otherwise empty day from shortening a two-hour study block
    # merely to save a few minutes of walking or finish a little earlier.
    shortfall_minutes: int = 0
    # Time between the first and last arrangement that is neither occupied by
    # a task nor intentionally reserved for a meal.  A plan that leaves a
    # two-hour hole in the middle of an otherwise free day is technically
    # feasible but is not a good student schedule.
    avoidable_idle_minutes: int = 0
    soft_cost: float = 0
    weather_breaches: int = 0


class Scheduler:
    replan_beam_width = 48
    replan_candidates_per_task = 36
    split_segment_gap_min = 30
    # Priced so that any dry slot beats every wet one, while a day with no dry
    # slot left still produces a plan the student can act on.
    wet_slot_penalty = 5
    # Default meals are flexible availability ranges: keep at least thirty
    # minutes somewhere in each range instead of forcing everybody to eat at
    # exactly 12:00/18:00. User-configured meal windows remain exact, hard
    # constraints through ``preferences.meal_windows``.
    default_meal_windows = (
        TimeWindow(start=time(11, 30), end=time(13, 30)),
        TimeWindow(start=time(17, 30), end=time(19, 30)),
    )
    # Conservative campus crossing used when no route is known for a pair.
    # Larger than the real walk between any two points on the Xiasha campus,
    # so a plan built on it stays executable.
    unknown_route_minutes = 20

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

        # Keeping the usual eating times clear is planning policy, not
        # something each caller should remember to pass in. Without it a day
        # of movable tasks is packed straight through lunch and dinner.
        if not context.soft_meal_windows and not preferences.meal_windows:
            context.soft_meal_windows = list(self.default_meal_windows)

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
            task for task in tasks if task.flexibility == TaskFlexibility.MOVABLE
        ]
        movable = self._dependency_order(
            movable,
            scheduled_ids={item.task_id for item in task_items if item.task_id},
            now=context.now,
            timezone=context.timezone,
            context=context,
        )

        old_starts = self._old_task_starts(context.old_plan)
        # A first plan gets the same global search as a replan.  Placing tasks
        # one at a time in priority order means the order decides the outcome:
        # a flexible task would take the only slot a narrow one could use, and
        # the narrow task was then reported as impossible even though a
        # complete solution existed.  With no old plan the shift terms of the
        # objective are zero, so it reduces to coverage first, then cost.
        if movable:
            beam_result = self._solve_with_escalating_compression(
                initial_items=task_items,
                tasks=movable,
                preferences=preferences,
                context=context,
                old_starts=old_starts,
            )
            effective_preferences = preferences
            # The default fifteen-minute breathing room is a comfort preference,
            # not a reason to make an explicitly requested task disappear.
            # Only retry without it when the normal search still leaves work
            # out; meal windows, fixed events, venue hours and travel remain
            # intact.  This makes a late but still mathematically feasible day
            # compact instead of silently sacrificing the appointment.
            if preferences.buffer_min and beam_result.unscheduled_task_ids:
                compact_preferences = preferences.model_copy(update={"buffer_min": 0})
                compact_result = self._solve_with_escalating_compression(
                    initial_items=task_items,
                    tasks=movable,
                    preferences=compact_preferences,
                    context=context,
                    old_starts=old_starts,
                )
                if self._beam_score(
                    compact_result,
                    old_starts,
                ) < self._beam_score(beam_result, old_starts):
                    beam_result = compact_result
                    effective_preferences = compact_preferences
            # The built-in lunch/dinner windows are comfort defaults, not a
            # licence to delete a requested task.  If a day is genuinely too
            # tight even after removing optional buffers, prove whether all
            # tasks fit without only the *soft* meal reservation.  Explicit
            # user meal windows remain hard through ``preferences``.
            if beam_result.unscheduled_task_ids and context.soft_meal_windows:
                saved_soft_meals = context.soft_meal_windows
                context.soft_meal_windows = []
                try:
                    tight_result = self._solve_with_escalating_compression(
                        initial_items=task_items,
                        tasks=movable,
                        preferences=effective_preferences,
                        context=context,
                        old_starts=old_starts,
                    )
                finally:
                    context.soft_meal_windows = saved_soft_meals
                if self._beam_score(
                    tight_result,
                    old_starts,
                ) < self._beam_score(beam_result, old_starts):
                    beam_result = tight_result
            task_items = beam_result.task_items
            unscheduled = beam_result.unscheduled_task_ids
            missing_route_pairs = beam_result.missing_route_pairs
        else:
            effective_preferences = preferences
        task_items = self._chronological_occurrence_labels(task_items, tasks)
        plan_items = self._insert_travel_items(
            task_items,
            context,
            missing_route_pairs,
            effective_preferences,
        )
        metrics = PlanMetrics(
            scheduled_task_count=len(task_items),
            requested_task_count=len(tasks),
            travel_minutes=sum(
                int((item.end_at - item.start_at).total_seconds() // 60)
                for item in plan_items
                if item.item_type == "travel"
            ),
            buffer_minutes=sum(
                int((item.end_at - item.start_at).total_seconds() // 60)
                for item in plan_items
                if item.item_type == "buffer"
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

    @staticmethod
    def _uses_soft_meal_window(
        items: list[PlanItem],
        context: PlanningContext,
    ) -> bool:
        """Whether movable work has consumed a default eating window.

        A complete plan can still be a bad plan.  In particular, the normal
        comfort buffer used to make the solver accept a five-task evening by
        placing work across dinner, even though dropping the optional gaps
        could preserve both the tasks and time to eat.  This predicate asks
        the compact pass to compete whenever that happens.
        """

        for item in items:
            if item.item_type != "task":
                continue
            for window in context.soft_meal_windows:
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
                if item.start_at < window_end and item.end_at > window_start:
                    return True
        return False

    @staticmethod
    def _chronological_occurrence_labels(
        items: list[PlanItem],
        tasks: list[Task],
    ) -> list[PlanItem]:
        """Number repeated sittings in the order the student will do them.

        Search deliberately places the most constrained occurrence first.
        That implementation detail must not leak into the UI as a later
        ``第二次`` appearing before ``第一次`` on the time line.
        """

        task_by_id = {task.id: task for task in tasks}
        grouped: dict[str, list[PlanItem]] = {}
        for item in items:
            task = task_by_id.get(item.task_id or "")
            if task is None:
                continue
            group = Scheduler._occurrence_group(task)
            if group:
                grouped.setdefault(group, []).append(item)

        replacements: dict[str, PlanItem] = {}
        for group_items in grouped.values():
            ordered = sorted(group_items, key=lambda item: item.start_at)
            base = re.sub(r"（第[一二三四五六七八九十\d]+次）$", "", ordered[0].title)
            for index, item in enumerate(ordered, start=1):
                replacements[item.id] = item.model_copy(
                    update={"title": f"{base}（第{index}次）"}
                )
        return [replacements.get(item.id, item) for item in items]

    # Fractions of the way from a task's shortest acceptable length to its
    # ideal one.  The first pass asks for everything; later passes ask for
    # less, so a crowded day ends with shorter tasks rather than missing ones.
    compression_levels = (1.0, 0.6, 0.0)
    complete_search_task_limit = 8
    complete_search_node_limit = 6000
    complete_search_candidates_per_task = 24

    def _solve_with_escalating_compression(
        self,
        *,
        initial_items: list[PlanItem],
        tasks: list[Task],
        preferences: UserPreferences,
        context: PlanningContext,
        old_starts: dict[str, datetime],
    ) -> _BeamState:
        """Solve, and if anything is left over, ask for less and solve again.

        The search keeps only its most promising states, and a full-length
        placement always scores better than a shortened one.  So the states
        that would have left room for the last task are pruned long before the
        search discovers that the day does not fit — three two-hour sittings
        are placed as two, and the third is reported impossible.  Re-solving
        with a lower ceiling gives every task the shorter form up front.
        """

        best: _BeamState | None = None
        requested_duration = {task.id: task.duration_min for task in tasks}
        for level in self.compression_levels:
            compressed_tasks = [self._compressed(task, level) for task in tasks]
            attempt = self._schedule_minimum_disruption(
                initial_items=initial_items,
                tasks=compressed_tasks,
                preferences=preferences,
                context=context,
                old_starts=old_starts,
            )
            # Beam search is fast, but it is still an approximation: its
            # fixed processing order can consume the only useful gaps and
            # prune the state that would have fitted every task.  When a
            # small student-day plan is reported partial, prove that result
            # with a bounded backtracking search before telling the user a
            # task is impossible.  This is the correctness path of the
            # online scheduler, not a provider fallback.
            if (
                (attempt.unscheduled_task_ids or attempt.weather_breaches)
                and len(compressed_tasks) <= self.complete_search_task_limit
            ):
                complete = self._search_complete_schedule(
                    initial_items=initial_items,
                    tasks=compressed_tasks,
                    preferences=preferences,
                    context=context,
                    old_starts=old_starts,
                )
                if complete is not None:
                    attempt = complete
            attempt.shortfall_minutes = sum(
                max(
                    0,
                    requested_duration.get(item.task_id or "", 0)
                    - int((item.end_at - item.start_at).total_seconds() // 60),
                )
                for item in attempt.task_items
                if item.item_type == "task" and item.task_id in requested_duration
            )
            # ``compressed_tasks`` carry the shortened duration as their own
            # target, so candidate-level cost cannot see the gap to the
            # user's original ideal duration.  Price that gap again at the
            # completed-plan level.  Without this, a free day chose two
            # one-hour study blocks over two requested two-hour blocks simply
            # because the shorter timeline had less travel and delay cost.
            attempt.soft_cost += 20.0 * attempt.shortfall_minutes
            if best is None or self._beam_score(
                attempt,
                old_starts,
            ) < self._beam_score(best, old_starts):
                best = attempt
            # Do not stop merely because the ideal-length pass managed to
            # squeeze everything in.  It may have done so by consuming the
            # meal window or pushing every flexible task to the end of the
            # day.  The shorter passes are still scored against it and win
            # only when the overall plan is genuinely better.
        assert best is not None
        return best

    def _search_complete_schedule(
        self,
        *,
        initial_items: list[PlanItem],
        tasks: list[Task],
        preferences: UserPreferences,
        context: PlanningContext,
        old_starts: dict[str, datetime],
    ) -> _BeamState | None:
        """Find a complete placement for a small plan or return ``None``.

        The next task is selected by minimum remaining values (fewest legal
        slots), so a two-hour evening appointment or a closing parcel station
        is considered before a study block that can use most of the day.  A
        depth-first search then backtracks when a locally attractive early
        slot blocks a later request.  The node budget keeps latency bounded;
        larger days continue to use the beam solver.
        """

        known_ids = {task.id for task in tasks} | {
            item.task_id for item in initial_items if item.task_id
        }
        nodes = 0
        best_complete: _BeamState | None = None

        def candidate_rank(task: Task, candidate: _Candidate) -> tuple:
            has_dependents = any(task.id in other.depends_on for other in tasks)
            return (
                self._candidate_soft_cost(
                    task=task,
                    start_at=candidate.start_at,
                    travel_minutes=candidate.travel_minutes,
                    preference_penalty=candidate.preference_penalty,
                    shortfall_minutes=candidate.shortfall_minutes,
                    old_start=old_starts.get(task.id),
                    has_dependents=has_dependents,
                    context=context,
                ),
                candidate.start_at,
                candidate.end_at,
            )

        def visit(
            scheduled: list[PlanItem],
            remaining: tuple[Task, ...],
            missing_pairs: set[tuple[str, str]],
            soft_cost: float,
            weather_breaches: int,
            shortfall_minutes: int,
        ) -> None:
            nonlocal nodes, best_complete
            if not remaining:
                result = _BeamState(
                    task_items=sorted(
                        scheduled,
                        key=lambda item: item.start_at,
                    ),
                    unscheduled_task_ids=[],
                    missing_route_pairs=missing_pairs,
                    avoidable_idle_minutes=self._avoidable_idle_minutes(
                        scheduled,
                        context,
                    ),
                    soft_cost=soft_cost,
                    weather_breaches=weather_breaches,
                    shortfall_minutes=shortfall_minutes,
                )
                if best_complete is None or self._beam_score(
                    result,
                    old_starts,
                ) < self._beam_score(best_complete, old_starts):
                    best_complete = result
                return
            if nodes >= self.complete_search_node_limit:
                return

            completed = {item.task_id for item in scheduled if item.task_id}
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
                return

            choices: list[tuple[int, Task, list[_Candidate], set[tuple[str, str]]]] = []
            for task in eligible:
                task_missing = set(missing_pairs)
                candidates = list(
                    self._candidate_intervals(
                        task=task,
                        scheduled=scheduled,
                        preferences=preferences,
                        context=context,
                        missing_route_pairs=task_missing,
                    )
                )
                # A duplicate interval can appear through more than one
                # flexible-duration path.  Keep the cheaper representation.
                unique: dict[tuple[datetime, datetime], _Candidate] = {}
                for candidate in candidates:
                    key = (candidate.start_at, candidate.end_at)
                    current = unique.get(key)
                    if current is None or candidate_rank(
                        task, candidate
                    ) < candidate_rank(task, current):
                        unique[key] = candidate
                ranked_all = sorted(
                    unique.values(),
                    key=lambda candidate: candidate_rank(task, candidate),
                )
                # Five-minute enumeration can create hundreds of equivalent
                # starts.  Feeding all of them into every recursive level made
                # one ordinary five-task day take more than a minute.  Keep a
                # diverse set instead: the cheapest choices for every allowed
                # duration plus the earliest/latest boundary of that duration.
                # Those boundaries are the placements that make room for the
                # neighbours; the middle copies add latency, not completeness.
                ranked = self._best_per_length(
                    ranked_all,
                    key=lambda candidate: candidate_rank(task, candidate),
                    limit=self.complete_search_candidates_per_task,
                )
                by_shortfall: dict[int, list[_Candidate]] = {}
                for candidate in ranked_all:
                    by_shortfall.setdefault(
                        candidate.shortfall_minutes,
                        [],
                    ).append(candidate)
                boundary_candidates = [
                    boundary
                    for group in by_shortfall.values()
                    for boundary in (
                        min(group, key=lambda value: value.start_at),
                        max(group, key=lambda value: value.start_at),
                    )
                ]
                ranked_by_interval = {
                    (candidate.start_at, candidate.end_at): candidate
                    for candidate in [*ranked, *boundary_candidates]
                }
                ranked = sorted(
                    ranked_by_interval.values(),
                    key=lambda candidate: candidate_rank(task, candidate),
                )
                if not ranked:
                    return
                choices.append((len(ranked), task, ranked, task_missing))

            _, task, candidates, task_missing = min(
                choices,
                key=lambda entry: (
                    entry[0],
                    entry[1].latest_end
                    or datetime.max.replace(tzinfo=context.timezone),
                    -entry[1].importance,
                    entry[1].id,
                ),
            )
            next_remaining = tuple(other for other in remaining if other.id != task.id)
            has_dependents = any(task.id in other.depends_on for other in tasks)
            for candidate in candidates:
                nodes += 1
                if nodes > self.complete_search_node_limit:
                    break
                item = self._task_item(
                    task,
                    candidate.start_at,
                    candidate.end_at,
                    reason=("按全局完整性回溯排程，保留全部明确任务"),
                )
                visit(
                    [*scheduled, item],
                    next_remaining,
                    set(task_missing),
                    soft_cost
                    + self._candidate_soft_cost(
                        task=task,
                        start_at=candidate.start_at,
                        travel_minutes=candidate.travel_minutes,
                        preference_penalty=candidate.preference_penalty,
                        shortfall_minutes=candidate.shortfall_minutes,
                        old_start=old_starts.get(task.id),
                        has_dependents=has_dependents,
                        context=context,
                    ),
                    weather_breaches + int(candidate.breaks_weather),
                    shortfall_minutes + candidate.shortfall_minutes,
                )
            return

        visit(
            list(initial_items),
            tuple(tasks),
            set(),
            0.0,
            0,
            0,
        )
        return best_complete

    @staticmethod
    def _compressed(task: Task, level: float) -> Task:
        """The same task asked for at ``level`` of its flexible length."""
        shortest = task.shortest_acceptable_min()
        if shortest >= task.duration_min or level >= 1:
            return task
        target = shortest + (task.duration_min - shortest) * level
        minutes = max(shortest, int(target) - int(target) % 5)
        if minutes == task.duration_min:
            return task
        return task.model_copy(update={"duration_min": minutes})

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
                avoidable_idle_minutes=self._avoidable_idle_minutes(
                    initial_items,
                    context,
                ),
            )
        ]
        for task in tasks:
            expanded: list[_BeamState] = []
            has_dependents = any(task.id in candidate.depends_on for candidate in tasks)
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

                def rank_key(
                    candidate: _Candidate,
                    task: Task = task,
                    has_dependents: bool = has_dependents,
                ):
                    return (
                        self._candidate_soft_cost(
                            task=task,
                            start_at=candidate.start_at,
                            travel_minutes=candidate.travel_minutes,
                            preference_penalty=candidate.preference_penalty,
                            shortfall_minutes=candidate.shortfall_minutes,
                            old_start=old_starts.get(task.id),
                            has_dependents=has_dependents,
                            context=context,
                        ),
                        candidate.start_at,
                    )

                ranked = self._best_per_length(
                    candidates,
                    key=rank_key,
                    limit=self.replan_candidates_per_task,
                )
                # Skipping must remain a branch even when this task has a
                # feasible slot.  Otherwise the first flexible study block
                # eagerly consumes the only evening slot and a later explicit
                # two-hour adviser meeting has no state left in which it can
                # be scheduled.  The weighted penalty below decides which
                # wish to shorten/defer if all of them genuinely do not fit.
                expanded.append(
                    _BeamState(
                        task_items=list(state.task_items),
                        unscheduled_task_ids=[
                            *state.unscheduled_task_ids,
                            task.id,
                        ],
                        missing_route_pairs=candidate_missing_pairs,
                        unscheduled_cost=(
                            state.unscheduled_cost + self._unscheduled_penalty(task)
                        ),
                        shortfall_minutes=state.shortfall_minutes,
                        avoidable_idle_minutes=state.avoidable_idle_minutes,
                        soft_cost=state.soft_cost,
                        weather_breaches=state.weather_breaches,
                    )
                )

                for candidate in ranked:
                    item = self._task_item(
                        task,
                        candidate.start_at,
                        candidate.end_at,
                        reason=(
                            "按全局最小扰动目标保留原计划，并同时满足通勤和可用时间窗"
                            if old_starts
                            else "按全局目标安排：先尽量排下更多任务，再优化通勤与偏好"
                        ),
                    )
                    child_items = sorted(
                        [*state.task_items, item],
                        key=lambda value: value.start_at,
                    )
                    expanded.append(
                        _BeamState(
                            task_items=child_items,
                            unscheduled_task_ids=list(state.unscheduled_task_ids),
                            missing_route_pairs=set(candidate_missing_pairs),
                            unscheduled_cost=state.unscheduled_cost,
                            shortfall_minutes=(
                                state.shortfall_minutes + candidate.shortfall_minutes
                            ),
                            avoidable_idle_minutes=self._avoidable_idle_minutes(
                                child_items,
                                context,
                            ),
                            soft_cost=(
                                state.soft_cost
                                + self._candidate_soft_cost(
                                    task=task,
                                    start_at=candidate.start_at,
                                    travel_minutes=candidate.travel_minutes,
                                    preference_penalty=(candidate.preference_penalty),
                                    shortfall_minutes=(candidate.shortfall_minutes),
                                    old_start=old_starts.get(task.id),
                                    has_dependents=has_dependents,
                                    context=context,
                                )
                            ),
                            weather_breaches=(
                                state.weather_breaches + int(candidate.breaks_weather)
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
            int(abs((item.start_at - old_starts[item.task_id]).total_seconds()) // 60)
            for item in state.task_items
            if item.task_id in old_starts
        ]
        # The order these are compared in is the product's priority order:
        # cover the tasks, then keep the plan safe to follow, then disturb the
        # existing day as little as possible, then optimise comfort and
        # travel. Weather sits above disruption deliberately — ranking it
        # below meant a replan left a run in the rain because moving it
        # counted as more expensive than getting wet.
        coverage = (
            round(state.unscheduled_cost, 6),
            len(state.unscheduled_task_ids),
        )
        safety = (state.weather_breaches,)
        tie_breaker = (
            round(state.soft_cost, 6),
            tuple(
                (item.task_id or "", item.start_at.isoformat())
                for item in state.task_items
                if item.item_type == "task"
            ),
        )
        if old_starts:
            # During an edit, unchanged tasks are structural promises.  Keep
            # them before optimising comfort, while still allowing a named
            # task to move when the new requirement makes that necessary.
            return (
                *coverage,
                *safety,
                sum(shift > 0 for shift in shifts),
                sum(shifts),
                state.shortfall_minutes,
                state.avoidable_idle_minutes,
                *tie_breaker,
            )
        # On a new day, full requested duration and the user's temporal intent
        # outrank compactness.  Putting every task back-to-back at night has
        # little internal idle time, but is still much worse than using a free
        # morning/afternoon.  Per-candidate soft cost contains scheduling delay,
        # travel and stated-period preference; compare it before the final
        # compactness tie-break so saving a few walking minutes cannot abandon
        # an otherwise useful daytime window.
        return (
            *coverage,
            *safety,
            state.shortfall_minutes,
            round(state.soft_cost, 6),
            state.avoidable_idle_minutes,
            tie_breaker[1],
        )

    @staticmethod
    def _avoidable_idle_minutes(
        items: list[PlanItem],
        context: PlanningContext,
    ) -> int:
        """Return idle time inside the active schedule, excluding meals.

        This is deliberately a plan-level quality measure.  Per-task costs
        cannot distinguish a compact, useful day from the same tasks scattered
        across large empty gaps.  Fixed commitments participate as anchors, so
        movable work is naturally pulled into the usable spaces around class.
        """

        ordered = sorted(
            (item for item in items if item.item_type == "task"),
            key=lambda item: item.start_at,
        )
        if len(ordered) < 2:
            return 0

        idle = 0
        for previous, current in pairwise(ordered):
            gap_start = previous.end_at
            gap_end = current.start_at
            if gap_end <= gap_start:
                continue
            gap_minutes = int((gap_end - gap_start).total_seconds() // 60)
            reserved = 0
            for window in context.soft_meal_windows:
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
                overlap_start = max(gap_start, window_start)
                overlap_end = min(gap_end, window_end)
                if overlap_end > overlap_start:
                    reserved += int((overlap_end - overlap_start).total_seconds() // 60)
            idle += max(0, gap_minutes - reserved)
        return idle

    @staticmethod
    def _unscheduled_penalty(task: Task) -> float:
        """Cost of omitting one request from the produced plan.

        Coverage is not a useful binary metric when the day is overfull: five
        wishes may not all fit, and dropping an explicit evening appointment
        is much worse than deferring one default-length study sitting.  This
        score encodes that product truth without asking the language model to
        rewrite or silently delete tasks.
        """

        penalty = 80.0 + task.importance * 25.0
        if task.duration_source == "explicit":
            penalty += 220.0
        if task.constraint_source == "user":
            penalty += 140.0
        if task.deadline is not None:
            penalty += 120.0
        if any(
            tag in task.tags
            for tag in (
                "meeting",
                "courier",
                "service_hours",
                "hard_constraint",
            )
        ):
            penalty += 100.0
        # A system-default study duration is deliberately elastic.  Omitting
        # one sitting is still visible to the user, but it must not displace a
        # named appointment or time-limited errand.
        if (
            task.duration_source == "default"
            and task.min_duration_min is not None
            and task.min_duration_min < task.duration_min
        ):
            penalty -= 90.0
        return max(20.0, penalty)

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
        shortfall_minutes: int = 0,
    ) -> float:
        shift_minutes = (
            int(abs((start_at - old_start).total_seconds()) // 60) if old_start else 0
        )
        # Every movable task pays for being pushed back, not just the ones
        # that block another task.  Without this a task drifts to whatever
        # slot happens to save a few minutes of walking: a three-hour study
        # block would skip a free morning to save one leg of a round trip.
        # The baseline is the earliest moment the task was ever allowed to
        # start, so a task the user deliberately anchored late (dinner at
        # 17:00, an evening run) is not penalised for honouring that anchor.
        baseline = task.earliest_start or datetime.combine(
            context.target_date,
            context.day_start,
            context.timezone,
        )
        period_window = Scheduler._preferred_window(
            task.preferred_period,
            context.target_date,
            context.timezone,
        )
        if period_window:
            baseline = max(baseline, period_window[0])
        scheduling_delay_minutes = max(
            0,
            int((start_at - baseline).total_seconds() // 60),
        )
        bias_penalty = 0.0
        if context.objective_bias == "alternative":
            # Ask for a genuinely different arrangement by making the slots the
            # previous plan used unattractive — without forbidding them, so a
            # task with only one feasible slot keeps it.
            if context.avoid_starts.get(task.id) == start_at:
                bias_penalty += 45.0
        elif context.objective_bias == "reverse_order":
            # Turn "sooner is better" around instead of chaining the tasks up.
            scheduling_delay_minutes = -scheduling_delay_minutes
        activity_delay_penalty = 0.0
        activity_shortfall_penalty = 0.0
        title_is_study = any(
            keyword in task.title for keyword in ("自习", "学习", "复习")
        )
        is_study = "study" in task.tags or title_is_study
        if (
            is_study
            and task.preferred_period != "evening"
        ):
            # A free morning or afternoon is worth more than saving a few
            # walking minutes and moving self-study to late evening. Explicit
            # evening requests are excluded, so the user's current wording
            # continues to outrank this default quality preference.
            # For study, using the earlier useful daytime window outranks a
            # marginally shorter walk later in the day.  A minute-for-minute
            # delay weight is intentional: the generic route cost is much
            # smaller and must not push a free morning into late afternoon.
            activity_delay_penalty = 6.0 * scheduling_delay_minutes
            if start_at.time() >= time(18, 0):
                # Crossing into an unrequested evening is a large quality
                # regression. A shorter useful daytime sitting should win.
                activity_delay_penalty += 10_000.0
            # On a genuinely free day, keep the full ideal duration instead
            # of shrinking every elastic sitting merely to compact the plan.
            activity_shortfall_penalty = 20.0 * shortfall_minutes
        return (
            bias_penalty
            + activity_delay_penalty
            + activity_shortfall_penalty
            + candidate_cost(
                travel_minutes=travel_minutes,
                preference_penalty=preference_penalty,
                shift_minutes=shift_minutes,
                scheduling_delay_minutes=scheduling_delay_minutes,
                has_dependents=has_dependents,
                shortfall_minutes=shortfall_minutes,
            )
        )

    @staticmethod
    def _dependency_order(
        tasks: list[Task],
        *,
        scheduled_ids: set[str],
        now: datetime,
        timezone: ZoneInfo,
        context: PlanningContext,
    ) -> list[Task]:
        """Honor dependencies, then protect the scarcest real-world windows.

        A generic priority score is not enough for a campus day.  A study
        block can usually move throughout the day, while a running track,
        parcel station or explicit evening appointment has a closing edge.
        Scheduling the unconstrained block first can consume the only slot of
        the constrained task even though a complete plan exists.
        """
        remaining = list(tasks)
        ordered: list[Task] = []
        known_ids = scheduled_ids | {task.id for task in tasks}

        day_end = datetime.combine(
            context.target_date + timedelta(days=1),
            time.min,
            timezone,
        )

        def effective_latest(task: Task) -> datetime:
            boundaries = [
                boundary for boundary in (task.latest_end, task.deadline) if boundary
            ]
            preferred = Scheduler._preferred_window(
                task.preferred_period,
                context.target_date,
                timezone,
            )
            if preferred and task.constraint_source == "user":
                boundaries.append(preferred[1])
            activity_windows = context.task_windows.get(task.id, [])
            if activity_windows:
                boundaries.append(max(end for _, end in activity_windows))
            if task.location_id:
                venue_windows = context.opening_windows.get(task.location_id, [])
                if venue_windows:
                    boundaries.append(max(end for _, end in venue_windows))
            return min(boundaries, default=day_end)

        def priority_key(task: Task):
            return (
                effective_latest(task),
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

    @staticmethod
    def _best_per_length(candidates, *, key, limit: int) -> list:
        """Keep the best slots for every length, not just the best overall.

        Full-length slots always score better, so a plain cut at ``limit``
        threw away every shortened option before the search could see it — and
        a day that only fits three shorter sittings then lost one of them.
        """

        by_length: dict[int, list] = {}
        for candidate in candidates:
            by_length.setdefault(candidate.shortfall_minutes, []).append(candidate)
        if not by_length:
            return []
        share = max(1, limit // len(by_length))
        ranked: list = []
        for shortfall in sorted(by_length):
            ranked.extend(sorted(by_length[shortfall], key=key)[:share])
        return sorted(ranked, key=key)[:limit]

    @staticmethod
    def _duration_options(task: Task) -> list[int]:
        """Lengths to try for one task, longest first.

        A task the student did not put a length on is a wish, not a
        measurement: two hours of self-study is the aim, one hour still counts.
        Offering the shorter lengths lets a crowded day keep the task instead
        of reporting it as impossible.
        """

        shortest = task.shortest_acceptable_min()
        if shortest >= task.duration_min:
            return [task.duration_min]
        options = [task.duration_min]
        step = max(15, (task.duration_min - shortest) // 3)
        value = task.duration_min - step
        while value > shortest:
            options.append(value - value % 5)
            value -= step
        options.append(shortest)
        return list(dict.fromkeys(options))

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
        # A period only narrows the day when the user actually said it.
        # Inferred periods — the model's guess, a saved habit — are preferences:
        # enforcing them as hard windows deleted tasks that had a perfectly good
        # slot an hour later, which is how “three sittings” became “two”.
        soft_period_preference = (
            task.constraint_source != "user" or "memory_period_preference" in task.tags
        )
        if period_window and not soft_period_preference:
            search_start = max(search_start, period_window[0])
            search_end = min(search_end, period_window[1])

        for option_minutes in self._duration_options(task):
            yield from self._intervals_for_duration(
                task=task,
                minutes=option_minutes,
                search_start=search_start,
                search_end=search_end,
                period_window=period_window,
                soft_period_preference=soft_period_preference,
                scheduled=scheduled,
                preferences=preferences,
                context=context,
                missing_route_pairs=missing_route_pairs,
            )

    def _intervals_for_duration(
        self,
        *,
        task: Task,
        minutes: int,
        search_start: datetime,
        search_end: datetime,
        period_window: tuple[datetime, datetime] | None,
        soft_period_preference: bool,
        scheduled: list[PlanItem],
        preferences: UserPreferences,
        context: PlanningContext,
        missing_route_pairs: set[tuple[str, str]],
    ) -> Iterable[_Candidate]:
        shortfall = task.duration_min - minutes
        cursor = self._ceil_five_minutes(search_start)
        duration = timedelta(minutes=minutes)
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
            # Rain is a strong reason to go earlier, not a reason to give up
            # exercising. Refusing every wet slot deleted the task outright
            # whenever the forecast was bad all day, which is exactly when the
            # student most needs to be told about it.
            weather_penalty = (
                self.wet_slot_penalty
                if self._violates_weather(task, cursor, end_at, context)
                else 0
            )
            if self._overlaps_meal_window(
                task,
                cursor,
                end_at,
                preferences,
                context,
            ):
                cursor += timedelta(minutes=5)
                continue

            # The default lunch/dinner windows are not timeline events, but
            # the student still needs a usable break.  A mere soft score is
            # insufficient: the first complete packing found by the exact
            # search used to occupy 30 of a 45 minute dinner window and then
            # report the plan as fully valid.  Protect at least 30 minutes of
            # the still-available window whenever the existing fixed plan has
            # not already made that impossible.  Explicit meal tasks remain
            # allowed inside the window.
            if self._would_consume_required_meal_break(
                task,
                cursor,
                end_at,
                scheduled,
                context,
            ):
                cursor += timedelta(minutes=5)
                continue

            # Default meal windows are soft because a genuinely immovable
            # appointment may have to cross them.  Price the *actual minutes*
            # consumed, though: the previous boolean cost treated a five-
            # minute edge overlap exactly like losing the whole dinner break,
            # so the first complete packing could leave only fifteen minutes
            # to eat while claiming the day was comfortable.
            meal_penalty = self._window_overlap_minutes(
                task,
                cursor,
                end_at,
                context.soft_meal_windows,
                context,
            )
            if self._matches_old_interval(task, cursor, end_at, context):
                meal_penalty = 0

            previous, following = self._neighbors(cursor, end_at, scheduled)
            if previous is False or following is False:
                cursor += timedelta(minutes=5)
                continue

            use_initial_origin = bool(
                context.initial_location_id
                and context.initial_departure_at
                and cursor >= context.initial_departure_at
                and (
                    previous is None or previous.end_at <= context.initial_departure_at
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
                previous.end_at + timedelta(minutes=before_travel + buffer_min) > cursor
            ):
                cursor += timedelta(minutes=5)
                continue
            if following and (
                end_at + timedelta(minutes=after_travel + buffer_min)
                > following.start_at
            ):
                cursor += timedelta(minutes=5)
                continue

            if self._too_close_to_a_sibling(task, cursor, end_at, scheduled):
                cursor += timedelta(minutes=5)
                continue

            dependency_end = self._dependency_end(task, scheduled)
            if dependency_end and cursor < dependency_end + timedelta(
                minutes=self._required_dependency_gap(task)
            ):
                cursor += timedelta(minutes=5)
                continue

            congestion_penalty = int(
                preferences.avoid_congestion and (before_delay > 0 or after_delay > 0)
            )
            period_penalty = int(
                bool(
                    soft_period_preference
                    and period_window
                    and not (period_window[0] <= cursor and end_at <= period_window[1])
                )
            )
            yield _Candidate(
                start_at=cursor,
                end_at=end_at,
                travel_minutes=before_travel + after_travel,
                preference_penalty=(
                    congestion_penalty + period_penalty + meal_penalty + weather_penalty
                ),
                shortfall_minutes=shortfall,
                breaks_weather=bool(weather_penalty),
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
        if any(marker in text for marker in ("吃饭", "用餐", "午餐", "晚餐", "meal")):
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
    def _window_overlap_minutes(
        task: Task,
        start_at: datetime,
        end_at: datetime,
        windows: list[TimeWindow],
        context: PlanningContext,
    ) -> int:
        """Return how many protected meal minutes a task consumes."""

        text = f"{task.title} {' '.join(task.tags)}".lower()
        if any(marker in text for marker in ("吃饭", "用餐", "午餐", "晚餐", "meal")):
            return 0
        overlap = 0
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
            overlap_start = max(start_at, window_start)
            overlap_end = min(end_at, window_end)
            if overlap_start < overlap_end:
                overlap += int((overlap_end - overlap_start).total_seconds() // 60)
        return overlap

    @staticmethod
    def _would_consume_required_meal_break(
        task: Task,
        start_at: datetime,
        end_at: datetime,
        scheduled: list[PlanItem],
        context: PlanningContext,
    ) -> bool:
        """Keep a real meal break without displaying a fake meal event.

        Only the part of a meal window that has not passed can be protected.
        If locked courses already consume more than the preferred allowance,
        movable work may not make the situation worse, but the solver is not
        allowed to reject the whole day for something it cannot change.
        """

        text = f"{task.title} {' '.join(task.tags)}".lower()
        if any(marker in text for marker in ("吃饭", "用餐", "午餐", "晚餐", "meal")):
            return False

        # The built-in meal window is a default comfort policy, not authority
        # to rewrite an existing plan.  If this exact task was already at this
        # time, keep it during an unrelated replan.  A user-supplied hard meal
        # window is checked earlier by ``_overlaps_meal_window`` and still
        # wins.  Without this exemption every edit moved an independent 18:00
        # task to 18:45, even when the student changed something at noon.
        if Scheduler._matches_old_interval(
            task,
            start_at,
            end_at,
            context,
        ):
            return False

        for window in context.soft_meal_windows:
            full_start = datetime.combine(
                context.target_date,
                window.start,
                context.timezone,
            )
            full_end = datetime.combine(
                context.target_date,
                window.end,
                context.timezone,
            )
            available_start = max(full_start, context.now)
            if available_start >= full_end:
                continue
            remaining_minutes = int((full_end - available_start).total_seconds() // 60)
            required_free = min(30, remaining_minutes)
            maximum_occupied = remaining_minutes - required_free

            def overlap_minutes(
                item_start: datetime,
                item_end: datetime,
                window_start: datetime = available_start,
                window_end: datetime = full_end,
            ) -> int:
                overlap_start = max(item_start, window_start)
                overlap_end = min(item_end, window_end)
                if overlap_start >= overlap_end:
                    return 0
                return int((overlap_end - overlap_start).total_seconds() // 60)

            occupied_before = sum(
                overlap_minutes(item.start_at, item.end_at)
                for item in scheduled
                if item.item_type == "task"
            )
            occupied_after = occupied_before + overlap_minutes(start_at, end_at)
            permitted = max(maximum_occupied, occupied_before)
            if occupied_after > permitted:
                return True
        return False

    @staticmethod
    def _matches_old_interval(
        task: Task,
        start_at: datetime,
        end_at: datetime,
        context: PlanningContext,
    ) -> bool:
        """Whether this candidate exactly preserves a published task slot.

        Soft defaults may guide a new plan, but an unrelated edit must not
        move accepted work merely to improve a default meal suggestion.
        Explicit user meal windows are checked separately as hard constraints.
        """

        return context.old_plan is not None and any(
            item.item_type == "task"
            and item.task_id == task.id
            and item.start_at == start_at
            and item.end_at == end_at
            for item in context.old_plan.items
        )

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
            "outdoor" in task.tags or task.location_id in context.outdoor_location_ids
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
        if risk_starts and end_at > min(risk_starts):
            return True

        # A user saying that it is hot is planning input, not small talk.
        # For outdoor exercise, strongly prefer slots outside the most exposed
        # 11:00-17:00 window. It remains a soft safety preference so an
        # otherwise impossible day still returns the requested activity with
        # a clear care reminder instead of silently deleting it.
        hot_weather = any(
            (item.temperature_c is not None and item.temperature_c >= 32)
            or any(
                marker in (item.condition or "")
                for marker in ("热", "高温", "炎热", "闷热")
            )
            for item in context.weather
        )
        if not hot_weather:
            return False
        hottest_start = datetime.combine(
            context.target_date,
            time(11, 0),
            context.timezone,
        )
        hottest_end = datetime.combine(
            context.target_date,
            time(17, 0),
            context.timezone,
        )
        return start_at < hottest_end and end_at > hottest_start

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
            # An unknown route is a gap in the map, not a reason to refuse to
            # plan.  Returning None here rejected every candidate slot and the
            # task then vanished from the day with nothing said about it — the
            # single largest source of "5 tasks requested, 2 scheduled".  Book
            # a deliberately generous crossing instead; the pair is recorded
            # above so the answer can say the estimate is unverified.
            return Scheduler.unknown_route_minutes, 0
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
            context.opening_windows.get(location_id) if location_id else None
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
            "早上": (time(8, 0), time(12, 0)),
            "早晨": (time(8, 0), time(12, 0)),
            "上午": (time(8, 0), time(12, 0)),
            "noon": (time(11, 30), time(13, 30)),
            "中午": (time(11, 30), time(13, 30)),
            "afternoon": (time(13, 0), time(18, 0)),
            "下午": (time(13, 0), time(18, 0)),
            "evening": (time(18, 0), time(22, 0)),
            "傍晚": (time(17, 0), time(20, 0)),
            "晚上": (time(18, 0), time(22, 0)),
            "夜间": (time(18, 0), time(22, 0)),
            # “白天” spans the whole non-evening day rather than a single
            # half-day: it rules out an evening slot without forcing the
            # planner to pick morning or afternoon on the user's behalf.
            "day": (time(8, 0), time(18, 0)),
            "白天": (time(8, 0), time(18, 0)),
            "日间": (time(8, 0), time(18, 0)),
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
        return value if remainder == 0 else value + timedelta(minutes=5 - remainder)

    @staticmethod
    def _occurrence_group(task: Task) -> str | None:
        return next(
            (
                tag.removeprefix("occurrence_of:")
                for tag in task.tags
                if tag.startswith("occurrence_of:")
            ),
            None,
        )

    @staticmethod
    def _too_close_to_a_sibling(
        task: Task,
        start_at: datetime,
        end_at: datetime,
        scheduled: list[PlanItem],
    ) -> bool:
        """Keep separate sittings of one request genuinely apart.

        Without this the planner satisfies “自习3次” by running three blocks
        end to end, which is the six-hour session the student was breaking up
        in the first place.
        """

        if task.min_gap_min <= 0:
            return False
        group = Scheduler._occurrence_group(task)
        if group is None:
            return False
        gap = timedelta(minutes=task.min_gap_min)
        prefix = f"{group}_"
        for item in scheduled:
            if not item.task_id or item.task_id == task.id:
                continue
            if not item.task_id.startswith(prefix):
                continue
            if start_at < item.end_at + gap and item.start_at < end_at + gap:
                return True
        return False

    @staticmethod
    def _required_dependency_gap(task: Task) -> int:
        """Minutes a task must leave after the task it depends on.

        Sittings of a split task depend on the previous sitting, so without a
        gap the planner puts them back to back and rebuilds the single long
        block the user asked to break up.  The gap belongs between two
        sittings only: when the user named something to do in between, that
        task already separates them and a further gap would just add dead time.
        """

        group = next(
            (
                tag.removeprefix("split_of:")
                for tag in task.tags
                if tag.startswith("split_of:")
            ),
            None,
        )
        if group is None:
            return 0
        sibling_prefix = f"{group}_seg"
        return (
            Scheduler.split_segment_gap_min
            if any(
                dependency.startswith(sibling_prefix) for dependency in task.depends_on
            )
            else 0
        )

    @staticmethod
    def _dependency_end(
        task: Task,
        scheduled: list[PlanItem],
    ) -> datetime | None:
        ends = [item.end_at for item in scheduled if item.task_id in task.depends_on]
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
            locked=task.flexibility
            in {
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
                    f"fixed tasks overlap: {previous.task_id} and {current.task_id}"
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
                and first_after_departure.location_id != context.initial_location_id
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
                                    location_id=(first_after_departure.location_id),
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
            travel_end_at = item.end_at
            if (
                item.location_id
                and following.location_id
                and item.location_id != following.location_id
            ):
                estimate = context.travel.get(
                    (item.location_id, following.location_id)
                )
                if not estimate:
                    missing_route_pairs.add(
                        (item.location_id, following.location_id)
                    )
                else:
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
                    if adjusted_duration and adjusted_duration > 0:
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
                            if adjusted_duration is not None:
                                travel_end = travel_start + timedelta(
                                    minutes=adjusted_duration
                                )
                        if adjusted_duration is not None and travel_end <= following.start_at:
                            mode_labels = {
                                "walk": "步行",
                                "bicycle": "骑自行车",
                                "electrobike": "骑电瓶车",
                            }
                            mode_label = mode_labels.get(estimate.mode, "通勤")
                            reason = f"{mode_label}基础时间 {base_duration} 分钟" + (
                                f"，校园通行高峰额外预留 {congestion_delay} 分钟"
                                if congestion_delay
                                else ""
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
                            travel_end_at = travel_end

            # Protect the requested breathing room even when neither task has
            # a location. Travel and buffer are separate concepts: AMap owns
            # the former, while this default interval gives the student time
            # to wrap up, rest briefly, and absorb small delays.
            if preferences.buffer_min > 0:
                buffer_end = following.start_at
                buffer_start = buffer_end - timedelta(
                    minutes=preferences.buffer_min
                )
                buffer_start = max(buffer_start, item.end_at, travel_end_at)
                if buffer_start < buffer_end:
                    result.append(
                        PlanItem(
                            id=f"buffer_{uuid4().hex}",
                            item_type="buffer",
                            title="衔接缓冲",
                            start_at=buffer_start,
                            end_at=buffer_end,
                            source=DataSource.STRUCTURED,
                            reason=(
                                "相邻安排之间默认预留时间，用于收尾、休息和临时变化"
                            ),
                        )
                    )
        return sorted(result, key=lambda item: item.start_at)
