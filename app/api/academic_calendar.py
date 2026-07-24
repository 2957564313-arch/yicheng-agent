from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response, status

from app.errors import AppError
from app.schemas.calendar import (
    CalendarOverride,
    CalendarOverrideCreate,
    CalendarOverrideListResponse,
)


router = APIRouter(prefix="/api/v1/users", tags=["academic-calendar"])


@router.get(
    "/{user_id}/calendar-overrides",
    response_model=CalendarOverrideListResponse,
)
def list_calendar_overrides(
    user_id: str,
    request: Request,
) -> CalendarOverrideListResponse:
    return CalendarOverrideListResponse(
        items=request.app.state.container.academic_calendar.list_overrides(
            user_id
        )
    )


@router.post(
    "/{user_id}/calendar-overrides",
    response_model=CalendarOverride,
    status_code=status.HTTP_201_CREATED,
)
def create_calendar_override(
    user_id: str,
    payload: CalendarOverrideCreate,
    request: Request,
) -> CalendarOverride:
    container = request.app.state.container
    return container.academic_calendar.upsert_override(
        user_id=user_id,
        payload=payload,
        now=datetime.now(ZoneInfo(container.settings.app_timezone)),
    )


@router.delete(
    "/{user_id}/calendar-overrides/{event_date}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_calendar_override(
    user_id: str,
    event_date: date,
    request: Request,
) -> Response:
    deleted = request.app.state.container.academic_calendar.delete_override(
        user_id=user_id,
        event_date=event_date,
    )
    if not deleted:
        raise AppError(
            "CALENDAR_OVERRIDE_NOT_FOUND",
            "没有找到这条校历调整",
            status_code=404,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
