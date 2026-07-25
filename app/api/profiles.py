from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request

from app.schemas.calendar import CalendarOverrideCreate
from app.schemas.memory import MemoryCreate
from app.schemas.profile import (
    PersonalDataBackup,
    PersonalDataRestoreRequest,
    PersonalDataRestoreResponse,
    TimetableBackup,
)
from app.schemas.timetable import CourseSessionCreate


router = APIRouter(prefix="/api/v1/users", tags=["personal-data"])


@router.get("/{user_id}/profile", response_model=PersonalDataBackup)
def export_profile(
    user_id: str,
    request: Request,
    thread_id: str = Query(min_length=1, max_length=128),
) -> PersonalDataBackup:
    container = request.app.state.container
    now = datetime.now(ZoneInfo(container.settings.app_timezone))
    timetable = container.timetables.get(user_id)
    reminder_settings, _ = container.reminders.get(user_id)
    plan = container.plans.latest_for_thread(thread_id)
    if plan is not None and plan.user_id != user_id:
        plan = None
    return PersonalDataBackup(
        user_id=user_id,
        thread_id=thread_id,
        exported_at=now,
        memories=[
            MemoryCreate(
                category=item.category,
                key=item.key,
                label=item.label,
                value=item.value,
                enabled=item.enabled,
            )
            for item in container.memories.list(user_id)
        ],
        timetable=(
            TimetableBackup(
                name=timetable.timetable.name,
                term_start=timetable.timetable.term_start,
                term_end=timetable.timetable.term_end,
                enabled=timetable.timetable.enabled,
                entries=[
                    CourseSessionCreate(
                        course_name=item.course_name,
                        weekday=item.weekday,
                        start_period=item.start_period,
                        end_period=item.end_period,
                        location=item.location,
                        weeks=item.weeks,
                    )
                    for item in timetable.entries
                ],
            )
            if timetable.timetable is not None
            else None
        ),
        calendar_overrides=[
            CalendarOverrideCreate(
                date=item.date,
                action=item.action,
                replacement_weekday=item.replacement_weekday,
                label=item.label,
                source_ref=item.source_ref,
            )
            for item in container.academic_calendar.list_overrides(user_id)
        ],
        reminder_settings=reminder_settings,
        current_plan=plan,
    )


@router.post(
    "/{user_id}/profile/restore",
    response_model=PersonalDataRestoreResponse,
)
def restore_profile(
    user_id: str,
    payload: PersonalDataRestoreRequest,
    request: Request,
) -> PersonalDataRestoreResponse:
    container = request.app.state.container
    now = datetime.now(ZoneInfo(container.settings.app_timezone))
    container.plans.ensure_user_and_thread(
        user_id=user_id,
        thread_id=payload.thread_id,
        now=now,
    )

    for memory in payload.memories:
        container.memories.upsert(
            user_id=user_id,
            payload=memory,
            now=now,
        )

    timetable_entries = 0
    if payload.timetable is not None:
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

    plan_restored = False
    if payload.current_plan is not None:
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
        plan_restored = True

    return PersonalDataRestoreResponse(
        user_id=user_id,
        thread_id=payload.thread_id,
        memories_restored=len(payload.memories),
        timetable_entries_restored=timetable_entries,
        calendar_overrides_restored=len(payload.calendar_overrides),
        reminder_settings_restored=payload.reminder_settings is not None,
        current_plan_restored=plan_restored,
        restored_at=now,
    )
