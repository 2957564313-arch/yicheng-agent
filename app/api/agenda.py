from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request, Response

from app.errors import AppError
from app.schemas.agenda import (
    AgendaClearDayResponse,
    AgendaItemCreate,
    AgendaItemUpdate,
    AgendaMutationResponse,
    AgendaResponse,
    ReminderDueResponse,
    ReminderSettings,
    ReminderSettingsResponse,
)
from app.schemas.profile import PersonalDataRestoreRequest
from app.services.personal_data import hydrate_personal_data

router = APIRouter(prefix="/api/v1/users", tags=["agenda"])


def _resolve_range(
    *,
    start_date: date | None,
    end_date: date | None,
    today: date,
    default_days: int = 6,
    max_days: int = 62,
) -> tuple[date, date]:
    start = start_date or today
    end = end_date or (start + timedelta(days=default_days))
    if end < start:
        raise AppError(
            "INVALID_AGENDA_RANGE",
            "日程结束日期不能早于开始日期。",
            status_code=422,
        )
    if (end - start).days > max_days:
        raise AppError(
            "AGENDA_RANGE_TOO_LARGE",
            f"一次最多查看{max_days + 1}天日程，请缩短日期范围。",
            status_code=422,
        )
    return start, end


def _agenda_response(
    *,
    user_id: str,
    start_date: date,
    end_date: date,
    request: Request,
    now: datetime,
) -> AgendaResponse:
    container = request.app.state.container
    items = container.agenda.list_items(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    reminder_settings, _ = container.reminders.get(user_id)
    return AgendaResponse(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        timezone=container.settings.app_timezone,
        items=items,
        reminders=container.agenda.build_reminders(
            items=items,
            settings=reminder_settings,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        ),
        care_suggestions=container.agenda.care_suggestions(
            items=items,
            start_date=start_date,
            end_date=end_date,
            now=now,
        ),
        summary=container.agenda.summarize(items),
        generated_at=now,
    )


@router.get("/{user_id}/agenda", response_model=AgendaResponse)
def get_agenda(
    user_id: str,
    request: Request,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> AgendaResponse:
    container = request.app.state.container
    timezone = ZoneInfo(container.settings.app_timezone)
    now = datetime.now(timezone)
    start, end = _resolve_range(
        start_date=start_date,
        end_date=end_date,
        today=now.date(),
    )
    return _agenda_response(
        user_id=user_id,
        start_date=start,
        end_date=end,
        request=request,
        now=now,
    )


@router.post(
    "/{user_id}/agenda/items",
    response_model=AgendaMutationResponse,
    status_code=201,
)
def create_agenda_item(
    user_id: str,
    payload: AgendaItemCreate,
    request: Request,
) -> AgendaMutationResponse:
    container = request.app.state.container
    now = datetime.now(ZoneInfo(container.settings.app_timezone))
    item = container.agenda_edits.create(
        user_id=user_id,
        payload=payload,
        now=now,
    )
    return AgendaMutationResponse(status="created", item=item)


@router.put(
    "/{user_id}/agenda/items/{item_id}",
    response_model=AgendaMutationResponse,
)
def update_agenda_item(
    user_id: str,
    item_id: str,
    payload: AgendaItemUpdate,
    request: Request,
) -> AgendaMutationResponse:
    container = request.app.state.container
    now = datetime.now(ZoneInfo(container.settings.app_timezone))
    existing_manual = container.agenda_edits.get(
        user_id=user_id,
        item_id=item_id,
    )
    if existing_manual is not None:
        item = container.agenda_edits.update(
            user_id=user_id,
            item_id=item_id,
            payload=payload,
            now=now,
        )
    else:
        reference_at = payload.original_start_at or payload.start_at
        target = container.agenda.find_item(
            user_id=user_id,
            item_id=item_id,
            reference_at=reference_at,
        )
        if target is None:
            raise AppError(
                "AGENDA_ITEM_NOT_FOUND",
                "没有找到这项日程，请刷新后再试。",
                status_code=404,
            )
        if target.source in {"course", "external"}:
            raise AppError(
                "AGENDA_ITEM_LOCKED",
                "固定课表和杭电助手预约以校方数据为准，不能在这里修改。",
                status_code=409,
            )
        item = container.agenda_edits.create(
            user_id=user_id,
            payload=payload,
            now=now,
            target_item_id=target.id,
        )
    if item is None:
        raise AppError(
            "AGENDA_ITEM_NOT_FOUND",
            "没有找到这项日程，请刷新后再试。",
            status_code=404,
        )
    return AgendaMutationResponse(status="updated", item=item)


@router.delete(
    "/{user_id}/agenda/items/{item_id}",
    response_model=AgendaMutationResponse,
)
def delete_agenda_item(
    user_id: str,
    item_id: str,
    request: Request,
    original_start_at: datetime | None = Query(default=None),
) -> AgendaMutationResponse:
    container = request.app.state.container
    now = datetime.now(ZoneInfo(container.settings.app_timezone))
    manual = container.agenda_edits.get(user_id=user_id, item_id=item_id)
    if manual is not None:
        container.agenda_edits.delete_manual(
            user_id=user_id,
            item_id=item_id,
            now=now,
        )
        return AgendaMutationResponse(status="deleted")
    if original_start_at is None:
        raise AppError(
            "AGENDA_ITEM_REFERENCE_REQUIRED",
            "删除前需要刷新这项日程。",
            status_code=422,
        )
    target = container.agenda.find_item(
        user_id=user_id,
        item_id=item_id,
        reference_at=original_start_at,
    )
    if target is None:
        raise AppError(
            "AGENDA_ITEM_NOT_FOUND",
            "没有找到这项日程，请刷新后再试。",
            status_code=404,
        )
    if target.source in {"course", "external"}:
        raise AppError(
            "AGENDA_ITEM_LOCKED",
            "固定课表和杭电助手预约以校方数据为准，不能在这里删除。",
            status_code=409,
        )
    container.agenda_edits.suppress(user_id=user_id, target=target, now=now)
    return AgendaMutationResponse(status="deleted")


@router.delete(
    "/{user_id}/agenda/day",
    response_model=AgendaClearDayResponse,
)
def clear_agenda_day(
    user_id: str,
    target_date: date,
    request: Request,
) -> AgendaClearDayResponse:
    """Clear user-adjustable items while preserving authoritative HDU data."""

    container = request.app.state.container
    timezone = ZoneInfo(container.settings.app_timezone)
    now = datetime.now(timezone)
    items = [
        item
        for item in container.agenda.list_items(
            user_id=user_id,
            start_date=target_date,
            end_date=target_date,
        )
        if item.start_at.astimezone(timezone).date() == target_date
    ]
    preserved = [item for item in items if item.source in {"course", "external"}]
    adjustable = [item for item in items if item.source not in {"course", "external"}]
    for item in adjustable:
        manual = container.agenda_edits.get(user_id=user_id, item_id=item.id)
        if manual is not None:
            container.agenda_edits.delete_manual(
                user_id=user_id,
                item_id=item.id,
                now=now,
            )
        else:
            container.agenda_edits.suppress(
                user_id=user_id,
                target=item,
                now=now,
            )
    return AgendaClearDayResponse(
        cleared_count=len(adjustable),
        preserved_count=len(preserved),
    )


@router.post(
    "/{user_id}/agenda/contextual",
    response_model=AgendaResponse,
)
def get_contextual_agenda(
    user_id: str,
    payload: PersonalDataRestoreRequest,
    request: Request,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> AgendaResponse:
    """Build an agenda from the browser snapshot on the active instance."""

    container = request.app.state.container
    timezone = ZoneInfo(container.settings.app_timezone)
    now = datetime.now(timezone)
    hydrate_personal_data(
        container=container,
        user_id=user_id,
        payload=payload,
        now=now,
        authoritative=True,
    )
    start, end = _resolve_range(
        start_date=start_date,
        end_date=end_date,
        today=now.date(),
    )
    return _agenda_response(
        user_id=user_id,
        start_date=start,
        end_date=end,
        request=request,
        now=now,
    )


@router.get(
    "/{user_id}/reminders/settings",
    response_model=ReminderSettingsResponse,
)
def get_reminder_settings(
    user_id: str,
    request: Request,
) -> ReminderSettingsResponse:
    settings, updated_at = request.app.state.container.reminders.get(user_id)
    return ReminderSettingsResponse(
        user_id=user_id,
        settings=settings,
        updated_at=updated_at,
    )


@router.put(
    "/{user_id}/reminders/settings",
    response_model=ReminderSettingsResponse,
)
def save_reminder_settings(
    user_id: str,
    payload: ReminderSettings,
    request: Request,
) -> ReminderSettingsResponse:
    container = request.app.state.container
    now = datetime.now(ZoneInfo(container.settings.app_timezone))
    settings, updated_at = container.reminders.save(
        user_id=user_id,
        settings=payload,
        now=now,
    )
    return ReminderSettingsResponse(
        user_id=user_id,
        settings=settings,
        updated_at=updated_at,
    )


@router.get(
    "/{user_id}/reminders/due",
    response_model=ReminderDueResponse,
)
def get_due_reminders(
    user_id: str,
    request: Request,
    now: datetime | None = Query(default=None),
    window_min: int = Query(default=2, ge=1, le=15),
) -> ReminderDueResponse:
    container = request.app.state.container
    timezone = ZoneInfo(container.settings.app_timezone)
    effective_now = now or datetime.now(timezone)
    if effective_now.tzinfo is None:
        raise AppError(
            "INVALID_REMINDER_TIME",
            "提醒查询时间必须包含时区。",
            status_code=422,
        )
    effective_now = effective_now.astimezone(timezone)
    window_end = effective_now + timedelta(minutes=window_min)
    items = container.agenda.list_items(
        user_id=user_id,
        start_date=effective_now.date(),
        end_date=window_end.date(),
    )
    settings, _ = container.reminders.get(user_id)
    reminders = [
        item
        for item in container.agenda.build_reminders(
            items=items,
            settings=settings,
            user_id=user_id,
            start_date=effective_now.date(),
            end_date=window_end.date(),
        )
        if effective_now <= item.notify_at < window_end
    ]
    return ReminderDueResponse(
        now=effective_now,
        window_end=window_end,
        reminders=reminders,
    )


@router.post(
    "/{user_id}/reminders/due/contextual",
    response_model=ReminderDueResponse,
)
def get_contextual_due_reminders(
    user_id: str,
    payload: PersonalDataRestoreRequest,
    request: Request,
    now: datetime | None = Query(default=None),
    window_min: int = Query(default=2, ge=1, le=15),
) -> ReminderDueResponse:
    container = request.app.state.container
    timezone = ZoneInfo(container.settings.app_timezone)
    effective_now = now or datetime.now(timezone)
    if effective_now.tzinfo is None:
        raise AppError(
            "INVALID_REMINDER_TIME",
            "提醒查询时间必须包含时区。",
            status_code=422,
        )
    effective_now = effective_now.astimezone(timezone)
    hydrate_personal_data(
        container=container,
        user_id=user_id,
        payload=payload,
        now=effective_now,
        authoritative=True,
    )
    window_end = effective_now + timedelta(minutes=window_min)
    items = container.agenda.list_items(
        user_id=user_id,
        start_date=effective_now.date(),
        end_date=window_end.date(),
    )
    settings, _ = container.reminders.get(user_id)
    reminders = [
        item
        for item in container.agenda.build_reminders(
            items=items,
            settings=settings,
            user_id=user_id,
            start_date=effective_now.date(),
            end_date=window_end.date(),
        )
        if effective_now <= item.notify_at < window_end
    ]
    return ReminderDueResponse(
        now=effective_now,
        window_end=window_end,
        reminders=reminders,
    )


def _ical_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _ical_datetime(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _ical_response(data: AgendaResponse, *, now: datetime) -> Response:
    reminders_by_item: dict[str, list] = {}
    for reminder in data.reminders:
        reminders_by_item.setdefault(reminder.agenda_item_id, []).append(
            reminder
        )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//易程智策//HDU Personal Agenda//ZH-CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:易程智策个人日程",
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]
    for item in data.items:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_ical_escape(item.id)}@yicheng",
                f"DTSTAMP:{now.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
                (
                    "DTSTART;TZID=Asia/Shanghai:"
                    f"{_ical_datetime(item.start_at)}"
                ),
                (
                    "DTEND;TZID=Asia/Shanghai:"
                    f"{_ical_datetime(item.end_at)}"
                ),
                f"SUMMARY:{_ical_escape(item.title)}",
            ]
        )
        if item.location_name:
            lines.append(
                f"LOCATION:{_ical_escape(item.location_name)}"
            )
        if item.notes:
            lines.append(f"DESCRIPTION:{_ical_escape(item.notes)}")
        for reminder in reminders_by_item.get(item.id, []):
            lead_min = max(
                0,
                int(
                    (
                        item.start_at - reminder.notify_at
                    ).total_seconds()
                    // 60
                ),
            )
            lines.extend(
                [
                    "BEGIN:VALARM",
                    f"TRIGGER:-PT{lead_min}M",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{_ical_escape(reminder.title)}",
                    "END:VALARM",
                ]
            )
        lines.append("END:VEVENT")
    for reminder in (
        item for item in data.reminders if item.kind == "bedtime"
    ):
        lead_min = max(
            0,
            int(
                (
                    reminder.event_start_at - reminder.notify_at
                ).total_seconds()
                // 60
            ),
        )
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_ical_escape(reminder.id)}@yicheng",
                f"DTSTAMP:{now.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ')}",
                (
                    "DTSTART;TZID=Asia/Shanghai:"
                    f"{_ical_datetime(reminder.event_start_at)}"
                ),
                (
                    "DTEND;TZID=Asia/Shanghai:"
                    f"{_ical_datetime(reminder.event_end_at)}"
                ),
                "SUMMARY:准备休息",
                f"DESCRIPTION:{_ical_escape(reminder.body)}",
                "BEGIN:VALARM",
                f"TRIGGER:-PT{lead_min}M",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{_ical_escape(reminder.title)}",
                "END:VALARM",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return Response(
        content="\r\n".join(lines) + "\r\n",
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="yicheng-agenda.ics"'
            )
        },
    )


@router.get("/{user_id}/agenda.ics")
def export_agenda_ics(
    user_id: str,
    request: Request,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> Response:
    container = request.app.state.container
    timezone = ZoneInfo(container.settings.app_timezone)
    now = datetime.now(timezone)
    start, end = _resolve_range(
        start_date=start_date,
        end_date=end_date,
        today=now.date(),
        default_days=90,
        max_days=183,
    )
    data = _agenda_response(
        user_id=user_id,
        start_date=start,
        end_date=end,
        request=request,
        now=now,
    )
    return _ical_response(data, now=now)


@router.post("/{user_id}/agenda.ics/contextual")
def export_contextual_agenda_ics(
    user_id: str,
    payload: PersonalDataRestoreRequest,
    request: Request,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> Response:
    container = request.app.state.container
    timezone = ZoneInfo(container.settings.app_timezone)
    now = datetime.now(timezone)
    hydrate_personal_data(
        container=container,
        user_id=user_id,
        payload=payload,
        now=now,
        authoritative=True,
    )
    start, end = _resolve_range(
        start_date=start_date,
        end_date=end_date,
        today=now.date(),
        default_days=90,
        max_days=183,
    )
    data = _agenda_response(
        user_id=user_id,
        start_date=start,
        end_date=end,
        request=request,
        now=now,
    )
    return _ical_response(data, now=now)
