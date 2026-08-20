from __future__ import annotations

from datetime import datetime

from app.schemas.task import Task


def task_priority(task: Task, now: datetime) -> float:
    importance = (task.importance - 1) / 4
    fixed_or_locked = 1 if task.flexibility.value in {"fixed", "locked"} else 0

    deadline_urgency = 0.0
    if task.deadline:
        remaining_hours = max(
            (task.deadline - now).total_seconds() / 3600,
            0.1,
        )
        deadline_urgency = min(1.0, 12 / remaining_hours)

    dependency_urgency = min(len(task.depends_on) / 3, 1)
    # Most-constrained-first: a task that may only land inside a period or
    # before a cut-off has the fewest feasible slots, so placing it before the
    # unconstrained ones keeps those slots from being taken.  This is about
    # how tight the task is, not about whether a preference was satisfied —
    # nothing has been placed yet at this point.
    constrainedness = min(
        1.0,
        sum(
            1
            for value in (
                task.preferred_period,
                task.earliest_start,
                task.latest_end,
                task.deadline,
            )
            if value is not None
        )
        / 3,
    )

    return (
        30 * importance
        + 25 * fixed_or_locked
        + 20 * deadline_urgency
        + 15 * dependency_urgency
        + 10 * constrainedness
    )


def candidate_cost(
    *,
    travel_minutes: int,
    preference_penalty: int,
    shift_minutes: int,
    scheduling_delay_minutes: int = 0,
    has_dependents: bool = False,
    shortfall_minutes: int = 0,
) -> float:
    # A task that gates other tasks is pulled forward harder.  The weight for
    # an ordinary task is deliberately mild: one extra minute of walking is
    # worth about twenty minutes of delay, so the planner still prefers a
    # sensible route, but it will no longer skip a free morning to save a
    # single leg of a round trip.  A stated preference (20 per penalty point)
    # outranks both.
    delay_weight = 0.08 if has_dependents else 0.05
    # Cutting a task short is worse than any routing or preference cost, so a
    # full-length slot always wins when one exists.  It stays far cheaper than
    # dropping the task, which the objective rejects outright before cost is
    # even compared.
    return (
        0.5 * travel_minutes
        + 20 * preference_penalty
        + shift_minutes
        + delay_weight * scheduling_delay_minutes
        + 0.6 * shortfall_minutes
    )
