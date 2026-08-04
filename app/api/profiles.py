from __future__ import annotations

from datetime import datetime
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
from app.services.personal_data import hydrate_personal_data


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
        current_plan_published=(
            plan is not None
            and container.plans.is_agenda_published(plan.id, user_id)
        ),
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
    return hydrate_personal_data(
        container=container,
        user_id=user_id,
        payload=payload,
        now=now,
    )
