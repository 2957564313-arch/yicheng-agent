from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response, status

from app.errors import AppError
from app.schemas.timetable import (
    TimetableImportRequest,
    TimetableImportResponse,
    TimetableResponse,
)
from app.services.timetable_importer import parse_timetable


router = APIRouter(prefix="/api/v1/users", tags=["timetables"])


@router.get("/{user_id}/timetable", response_model=TimetableResponse)
def get_timetable(user_id: str, request: Request) -> TimetableResponse:
    return request.app.state.container.timetables.get(user_id)


@router.post(
    "/{user_id}/timetable/import",
    response_model=TimetableImportResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_timetable(
    user_id: str,
    payload: TimetableImportRequest,
    request: Request,
) -> TimetableImportResponse:
    try:
        entries, skipped, messages = parse_timetable(
            content=payload.content,
            format_name=payload.format,
        )
    except Exception as exc:
        raise AppError(
            "TIMETABLE_IMPORT_FAILED",
            f"课表没有导入成功：{exc}",
            status_code=422,
        ) from exc
    container = request.app.state.container
    result = container.timetables.replace(
        user_id=user_id,
        name=payload.name,
        term_start=payload.term_start,
        term_end=payload.term_end,
        enabled=payload.enabled,
        entries=entries,
        now=datetime.now(ZoneInfo(container.settings.app_timezone)),
    )
    return TimetableImportResponse(
        **result.model_dump(mode="python"),
        imported_count=len(entries),
        skipped_count=skipped,
        messages=messages,
    )


@router.delete(
    "/{user_id}/timetable",
    status_code=status.HTTP_204_NO_CONTENT,
)
def clear_timetable(user_id: str, request: Request) -> Response:
    request.app.state.container.timetables.clear(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
