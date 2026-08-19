from __future__ import annotations

from app.schemas.chat import PlanChange
from app.schemas.plan import Plan, PlanItem


def _duration_label(minutes: int) -> str:
    hours, remainder = divmod(abs(minutes), 60)
    parts = []
    if hours:
        parts.append(f"{hours}小时")
    if remainder or not parts:
        parts.append(f"{remainder}分钟")
    return "".join(parts)


def _task_items(plan: Plan) -> dict[str, PlanItem]:
    return {
        item.task_id: item
        for item in plan.items
        if item.item_type == "task" and item.task_id
    }


def compare_plans(previous: Plan | None, current: Plan | None) -> list[PlanChange]:
    """Return an auditable task-level diff between two plans."""

    if previous is None or current is None:
        return []

    before = _task_items(previous)
    after = _task_items(current)
    changes: list[PlanChange] = []
    task_ids = list(dict.fromkeys([*before, *after]))

    for task_id in task_ids:
        old_item = before.get(task_id)
        new_item = after.get(task_id)
        if old_item is None and new_item is not None:
            changes.append(
                PlanChange(
                    task_id=task_id,
                    title=new_item.title,
                    change_type="added",
                    after_start=new_item.start_at,
                    after_end=new_item.end_at,
                    summary="新增任务",
                )
            )
            continue
        if old_item is not None and new_item is None:
            changes.append(
                PlanChange(
                    task_id=task_id,
                    title=old_item.title,
                    change_type="removed",
                    before_start=old_item.start_at,
                    before_end=old_item.end_at,
                    summary="任务未保留",
                )
            )
            continue
        if old_item is None or new_item is None:
            continue

        shift_min = int(
            (new_item.start_at - old_item.start_at).total_seconds() // 60
        )
        old_duration = int(
            (old_item.end_at - old_item.start_at).total_seconds() // 60
        )
        new_duration = int(
            (new_item.end_at - new_item.start_at).total_seconds() // 60
        )
        duration_delta = new_duration - old_duration
        if shift_min == 0 and duration_delta == 0:
            continue

        parts = []
        if duration_delta:
            verb = "延长" if duration_delta > 0 else "缩短"
            parts.append(f"{verb}{_duration_label(duration_delta)}")
        if shift_min:
            verb = "顺延" if shift_min > 0 else "提前"
            parts.append(f"{verb}{_duration_label(shift_min)}")
        changes.append(
            PlanChange(
                task_id=task_id,
                title=new_item.title,
                change_type=(
                    "duration_changed"
                    if duration_delta and shift_min == 0
                    else "moved"
                ),
                before_start=old_item.start_at,
                before_end=old_item.end_at,
                after_start=new_item.start_at,
                after_end=new_item.end_at,
                shift_min=shift_min,
                duration_delta_min=duration_delta,
                summary="，".join(parts),
            )
        )
    return changes
