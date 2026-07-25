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
    preference_match = 1 if task.preferred_period else 0

    return (
        30 * importance
        + 25 * fixed_or_locked
        + 20 * deadline_urgency
        + 15 * dependency_urgency
        + 10 * preference_match
    )


def candidate_cost(
    *,
    travel_minutes: int,
    preference_penalty: int,
    shift_minutes: int,
    scheduling_delay_minutes: int = 0,
) -> float:
    return (
        0.5 * travel_minutes
        + 20 * preference_penalty
        + shift_minutes
        + 0.08 * scheduling_delay_minutes
    )
