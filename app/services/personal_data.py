from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.schemas.agenda import ReminderSettings
from app.schemas.plan import Plan
from app.schemas.profile import (
    PersonalDataRestoreRequest,
    PersonalDataRestoreResponse,
)


def _plan_signature(plan: Plan) -> tuple[Any, ...]:
    """Compare user-visible plan content while ignoring generated identifiers."""

    return (
        plan.date,
        plan.status,
        tuple(
            (
                item.task_id,
                item.item_type,
                item.title,
                item.start_at,
                item.end_at,
                item.location_id,
                item.reason,
                item.travel_mode,
                item.base_duration_min,
                item.congestion_delay_min,
            )
            for item in plan.items
        ),
    )


def _timetable_signature(value: Any) -> tuple[Any, ...] | None:
    timetable = getattr(value, "timetable", None)
    if timetable is None:
        return None
    return (
        timetable.name,
        timetable.term_start,
        timetable.term_end,
        timetable.enabled,
        tuple(
            (
                item.course_name,
                item.weekday,
                item.start_period,
                item.end_period,
                item.location,
                tuple(item.weeks),
            )
            for item in value.entries
        ),
    )


def _timetable_payload_signature(value: Any) -> tuple[Any, ...]:
    return (
        value.name,
        value.term_start,
        value.term_end,
        value.enabled,
        tuple(
            (
                item.course_name,
                item.weekday,
                item.start_period,
                item.end_period,
                item.location,
                tuple(item.weeks),
            )
            for item in value.entries
        ),
    )


def hydrate_personal_data(
    *,
    container: Any,
    user_id: str,
    payload: PersonalDataRestoreRequest,
    now: datetime,
    authoritative: bool = False,
) -> PersonalDataRestoreResponse:
    """Hydrate one execution instance from a browser-owned personal snapshot.

    The public Vercel build can execute two consecutive requests on different
    ephemeral instances. Replaying the small, validated personal snapshot at
    the start of a request makes the result deterministic without treating the
    instance-local SQLite file as durable storage.
    """

    container.plans.ensure_user_and_thread(
        user_id=user_id,
        thread_id=payload.thread_id,
        now=now,
    )

    if authoritative:
        container.memories.delete_except_keys(
            user_id=user_id,
            memory_keys={item.key for item in payload.memories},
        )
    for memory in payload.memories:
        container.memories.upsert(
            user_id=user_id,
            payload=memory,
            now=now,
        )

    timetable_entries = 0
    if payload.timetable is not None:
        current_timetable = container.timetables.get(user_id)
        if (
            _timetable_signature(current_timetable)
            != _timetable_payload_signature(payload.timetable)
        ):
            container.timetables.replace(
                user_id=user_id,
                name=payload.timetable.name,
                term_start=payload.timetable.term_start,
                term_end=payload.timetable.term_end,
                enabled=payload.timetable.enabled,
                entries=payload.timetable.entries,
                now=now,
            )
        timetable_entries = len(payload.timetable.entries)
    elif authoritative:
        container.timetables.clear(user_id)

    if authoritative:
        container.academic_calendar.delete_except_dates(
            user_id=user_id,
            event_dates={
                item.date for item in payload.calendar_overrides
            },
        )
    for override in payload.calendar_overrides:
        container.academic_calendar.upsert_override(
            user_id=user_id,
            payload=override,
            now=now,
        )

    if payload.reminder_settings is not None:
        container.reminders.save(
            user_id=user_id,
            settings=payload.reminder_settings,
            now=now,
        )
    elif authoritative:
        container.reminders.save(
            user_id=user_id,
            settings=ReminderSettings(),
            now=now,
        )

    plan_available = payload.current_plan is not None
    if payload.current_plan is not None:
        latest = container.plans.latest_for_thread(payload.thread_id)
        already_current = (
            latest is not None
            and latest.user_id == user_id
            and _plan_signature(latest)
            == _plan_signature(payload.current_plan)
        )
        if not already_current:
            if authoritative:
                container.plans.clear_thread(
                    user_id=user_id,
                    thread_id=payload.thread_id,
                )
            restored_plan = payload.current_plan.model_copy(
                update={
                    "id": f"plan_{uuid4().hex}",
                    "user_id": user_id,
                    "thread_id": payload.thread_id,
                    "items": [
                        item.model_copy(
                            update={"id": f"item_{uuid4().hex}"}
                        )
                        for item in payload.current_plan.items
                    ],
                    "created_at": now,
                }
            )
            container.plans.save(restored_plan)
    elif authoritative:
        container.plans.clear_thread(
            user_id=user_id,
            thread_id=payload.thread_id,
        )

    return PersonalDataRestoreResponse(
        user_id=user_id,
        thread_id=payload.thread_id,
        memories_restored=len(payload.memories),
        timetable_entries_restored=timetable_entries,
        calendar_overrides_restored=len(payload.calendar_overrides),
        reminder_settings_restored=payload.reminder_settings is not None,
        current_plan_restored=plan_available,
        restored_at=now,
    )
