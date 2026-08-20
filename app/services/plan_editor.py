from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.schemas.plan_edit import PlanEdit, PlanEditOperation
from app.schemas.task import Task

# Periods a move may name, kept in step with the scheduler's own vocabulary.
_PERIOD_STARTS = {
    "morning": (8, 0),
    "day": (8, 0),
    "afternoon": (13, 0),
    "evening": (18, 0),
}
_PERIOD_ENDS = {
    "morning": (12, 0),
    "day": (18, 0),
    "afternoon": (18, 0),
    "evening": (22, 0),
}


def _normalise(value: str) -> str:
    return "".join(value.split()).lower()


def match_task(reference: str | None, tasks: list[Task]) -> Task | None:
    """Find the task the student pointed at, by id or by what it is called."""
    if not reference:
        return None
    wanted = _normalise(reference)
    if not wanted:
        return None
    for task in tasks:
        if _normalise(task.id) == wanted:
            return task
    for task in tasks:
        if _normalise(task.title) == wanted:
            return task
    contained = [
        task
        for task in tasks
        if wanted in _normalise(task.title) or _normalise(task.title) in wanted
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def apply_plan_edit(
    *,
    tasks: list[Task],
    edit: PlanEdit,
    timezone: ZoneInfo,
) -> tuple[list[Task], list[str]]:
    """Apply the requested changes, leaving everything else exactly as it was.

    Every task in ``tasks`` survives unless an operation removes it by name.
    This is the whole point of the edit contract: the model decides what the
    student meant, and this decides what happens to the rest of the day, so a
    follow-up can never quietly drop the arrangements nobody mentioned.
    """

    edited = {task.id: task for task in tasks}
    order = [task.id for task in tasks]
    unresolved: list[str] = []

    for operation in edit.operations:
        if operation.action == "add":
            task = _new_task(operation, tasks, timezone)
            if task is None:
                unresolved.append(
                    f"没听懂要新增的安排：{operation.title or operation.task_ref}"
                )
                continue
            edited[task.id] = task
            order.append(task.id)
            continue

        target = match_task(operation.task_ref, list(edited.values()))
        if target is None:
            unresolved.append(
                f"计划里没有找到「{operation.task_ref}」这项安排"
            )
            continue
        if operation.action == "remove":
            edited.pop(target.id, None)
            order = [task_id for task_id in order if task_id != target.id]
            continue
        edited[target.id] = _retimed(operation, target, timezone)

    remaining = [edited[task_id] for task_id in order if task_id in edited]
    # A dependency on a task that was just removed would make the day
    # unschedulable for a reason the student never asked for.
    surviving = {task.id for task in remaining}
    return (
        [
            task.model_copy(
                update={
                    "depends_on": [
                        dependency
                        for dependency in task.depends_on
                        if dependency in surviving
                    ]
                }
            )
            for task in remaining
        ],
        unresolved,
    )


def _retimed(
    operation: PlanEditOperation,
    task: Task,
    timezone: ZoneInfo,
) -> Task:
    update: dict = {}
    if operation.action in {"shorten", "lengthen"} and operation.duration_min:
        update["duration_min"] = operation.duration_min
        # A length the student just named is a measurement, not a default.
        update["duration_source"] = "explicit"
        update["min_duration_min"] = None

    target_date = operation.target_date or (
        operation.target_start.date() if operation.target_start else None
    )
    if target_date and target_date != task.date:
        update["date"] = target_date
        # Old absolute anchors belong to the day the task is leaving.
        update.update(
            earliest_start=None,
            latest_end=None,
            deadline=None,
            fixed_start=None,
            fixed_end=None,
        )
        if task.flexibility.value in {"fixed", "locked"}:
            update["flexibility"] = "movable"

    if operation.target_start:
        update["earliest_start"] = operation.target_start
        update["latest_end"] = operation.target_start + timedelta(
            minutes=update.get("duration_min", task.duration_min)
        )
        update["preferred_period"] = None
    elif operation.target_period in _PERIOD_STARTS:
        day = update.get("date", task.date)
        start_hour, start_minute = _PERIOD_STARTS[operation.target_period]
        end_hour, end_minute = _PERIOD_ENDS[operation.target_period]
        update["earliest_start"] = datetime(
            day.year, day.month, day.day, start_hour, start_minute, tzinfo=timezone
        )
        update["latest_end"] = datetime(
            day.year, day.month, day.day, end_hour, end_minute, tzinfo=timezone
        )
        update["preferred_period"] = operation.target_period
        # The student asked for this period out loud, so it is a hard window.
        update["constraint_source"] = "user"

    if operation.location_raw:
        update["location_raw"] = operation.location_raw
        update["location_id"] = None
    return task.model_copy(update=update) if update else task


def _new_task(
    operation: PlanEditOperation,
    tasks: list[Task],
    timezone: ZoneInfo,
) -> Task | None:
    title = operation.title or operation.task_ref
    if not title:
        return None
    reference_date = operation.target_date or (
        operation.target_start.date()
        if operation.target_start
        else (tasks[0].date if tasks else None)
    )
    if reference_date is None:
        return None
    task = Task(
        id=f"added_{uuid4().hex[:8]}",
        title=title,
        date=reference_date,
        duration_min=operation.duration_min or 60,
        location_raw=operation.location_raw,
        min_duration_min=None if operation.duration_min else 30,
        duration_source="explicit" if operation.duration_min else "default",
        importance=3,
    )
    return _retimed(operation, task, timezone)
