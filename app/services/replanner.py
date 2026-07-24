from __future__ import annotations

from datetime import datetime

from app.schemas.common import TaskFlexibility
from app.schemas.plan import Plan
from app.schemas.task import Task, UserPreferences
from app.services.scheduler import PlanningContext, Scheduler, SchedulerResult


class Replanner:
    def __init__(self, scheduler: Scheduler | None = None) -> None:
        self.scheduler = scheduler or Scheduler()

    def replan(
        self,
        *,
        user_id: str,
        thread_id: str,
        tasks: list[Task],
        preferences: UserPreferences,
        context: PlanningContext,
        old_plan: Plan,
    ) -> SchedulerResult:
        old_by_task = {
            item.task_id: item
            for item in old_plan.items
            if item.item_type == "task" and item.task_id
        }
        normalized: list[Task] = []
        for task in tasks:
            if (
                task.id in preferences.locked_task_ids
                and task.id in old_by_task
            ):
                old_item = old_by_task[task.id]
                task = task.model_copy(
                    update={
                        "flexibility": TaskFlexibility.LOCKED,
                        "fixed_start": old_item.start_at,
                        "fixed_end": old_item.end_at,
                        "duration_min": int(
                            (
                                old_item.end_at - old_item.start_at
                            ).total_seconds()
                            // 60
                        ),
                    }
                )
            normalized.append(task)

        context.old_plan = old_plan
        return self.scheduler.schedule(
            user_id=user_id,
            thread_id=thread_id,
            tasks=normalized,
            preferences=preferences,
            context=context,
            version=old_plan.version + 1,
        )

