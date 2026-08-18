from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Path, Query, Request

from app.errors import AppError
from app.schemas.integration import (
    ExternalEventResponse,
    ExternalEventUpsert,
    IntegrationCapabilities,
)


router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("/capabilities", response_model=IntegrationCapabilities)
def capabilities() -> IntegrationCapabilities:
    return IntegrationCapabilities()


@router.put("/events", response_model=ExternalEventResponse)
def upsert_event(
    payload: ExternalEventUpsert,
    request: Request,
) -> ExternalEventResponse:
    container = request.app.state.container
    timezone = ZoneInfo(container.settings.app_timezone)
    now = datetime.now(timezone)
    normalized = payload.model_copy(
        update={
            "start_at": payload.start_at.astimezone(timezone),
            "end_at": payload.end_at.astimezone(timezone),
        }
    )
    return container.external_events.upsert(normalized, now=now)


@router.delete(
    "/{source_system}/events/{external_event_id}",
    response_model=ExternalEventResponse,
)
def cancel_event(
    request: Request,
    source_system: str = Path(pattern=r"^[A-Za-z0-9_.-]+$", max_length=64),
    external_event_id: str = Path(min_length=1, max_length=128),
    user_id: str = Query(min_length=1, max_length=64),
) -> ExternalEventResponse:
    container = request.app.state.container
    result = container.external_events.cancel(
        source_system=source_system,
        external_event_id=external_event_id,
        user_id=user_id,
        now=datetime.now(ZoneInfo(container.settings.app_timezone)),
    )
    if result is None:
        raise AppError(
            "EXTERNAL_EVENT_NOT_FOUND",
            "未找到对应的外部日程，未执行取消。",
            status_code=404,
        )
    return result
