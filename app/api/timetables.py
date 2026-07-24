from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response, status

from app.errors import AppError
from app.schemas.timetable import (
    TimetableImportRequest,
    TimetableImportResponse,
    TimetablePreviewResponse,
    TimetableResponse,
)
from app.services.timetable_importer import parse_timetable


router = APIRouter(prefix="/api/v1/users", tags=["timetables"])


def _prepare_import(payload: TimetableImportRequest):
    try:
        entries, skipped, messages = parse_timetable(
            content=payload.content,
            format_name=payload.format,
        )
    except Exception as exc:
        raise AppError(
            "TIMETABLE_IMPORT_FAILED",
            f"课表没有识别成功：{exc}",
            status_code=422,
        ) from exc
    if len(entries) > 500:
        raise AppError(
            "TIMETABLE_TOO_LARGE",
            "单次最多导入500个课程时段，请只保留当前学期课表",
            status_code=422,
        )
    if any(entry.weeks for entry in entries) and payload.term_start is None:
        raise AppError(
            "TIMETABLE_TERM_START_REQUIRED",
            (
                "这份课表包含教学周次，请先填写“第一教学周周一”。"
                "系统需要用它把第1周、第2周和单双周换算成真实日期。"
            ),
            status_code=422,
        )
    term_end = payload.term_end
    if payload.term_start and term_end is None:
        max_week = max(
            (max(entry.weeks) for entry in entries if entry.weeks),
            default=0,
        )
        if max_week:
            term_end = (
                payload.term_start
                + timedelta(weeks=max_week, days=-1)
            )
    return entries, skipped, messages, term_end


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
    entries, skipped, messages, term_end = _prepare_import(payload)
    container = request.app.state.container
    result = container.timetables.replace(
        user_id=user_id,
        name=payload.name,
        term_start=payload.term_start,
        term_end=term_end,
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


@router.post(
    "/{user_id}/timetable/preview",
    response_model=TimetablePreviewResponse,
)
def preview_timetable(
    user_id: str,
    payload: TimetableImportRequest,
) -> TimetablePreviewResponse:
    entries, skipped, messages, term_end = _prepare_import(payload)
    return TimetablePreviewResponse(
        entries=entries,
        imported_count=len(entries),
        skipped_count=skipped,
        messages=messages,
        term_start=payload.term_start,
        term_end=term_end,
    )


@router.delete(
    "/{user_id}/timetable",
    status_code=status.HTTP_204_NO_CONTENT,
)
def clear_timetable(user_id: str, request: Request) -> Response:
    request.app.state.container.timetables.clear(user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
