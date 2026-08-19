from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response, status

from app.errors import AppError
from app.providers.hduhelp import available_terms, schedule_to_sessions
from app.schemas.hduhelp import (
    HduHelpConnectionStatus,
    HduHelpConnectRequest,
    HduHelpSyncRequest,
    HduHelpSyncResponse,
)

router = APIRouter(prefix="/api/v1/users", tags=["hduhelp"])


def _now(request: Request) -> datetime:
    settings = request.app.state.container.settings
    return datetime.now(ZoneInfo(settings.app_timezone))


def _credential(request: Request, user_id: str) -> str:
    container = request.app.state.container
    row = container.external_connections.get_row(user_id, "hduhelp")
    if row is None or row["status"] != "active":
        raise AppError(
            "HDUHELP_NOT_CONNECTED",
            "请先连接自己的杭电助手账号。",
            status_code=409,
        )
    return container.credential_cipher.decrypt(row["credential_ciphertext"])


@router.get(
    "/{user_id}/connections/hduhelp",
    response_model=HduHelpConnectionStatus,
)
def get_connection(user_id: str, request: Request) -> HduHelpConnectionStatus:
    return request.app.state.container.external_connections.status(
        user_id,
        "hduhelp",
    )


@router.post(
    "/{user_id}/connections/hduhelp",
    response_model=HduHelpConnectionStatus,
)
def connect(
    user_id: str,
    payload: HduHelpConnectRequest,
    request: Request,
) -> HduHelpConnectionStatus:
    container = request.app.state.container
    token = payload.token.get_secret_value().strip()
    identity = container.hduhelp.identity(token)
    rows = container.hduhelp.schedule(token)
    terms = available_terms(rows)
    if not terms:
        raise AppError(
            "HDUHELP_SCHEDULE_EMPTY",
            "令牌可以登录，但没有读取到课表；请检查课表权限。",
            status_code=422,
        )
    return container.external_connections.save(
        user_id=user_id,
        external_user_id=str(identity.get("id", "")).strip(),
        display_name=(
            str(identity.get("nickName", "")).strip() or None
        ),
        credential_ciphertext=container.credential_cipher.encrypt(token),
        terms=terms,
        now=_now(request),
    )


@router.delete(
    "/{user_id}/connections/hduhelp",
    status_code=status.HTTP_204_NO_CONTENT,
)
def disconnect(user_id: str, request: Request) -> Response:
    request.app.state.container.external_connections.delete(
        user_id,
        "hduhelp",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{user_id}/connections/hduhelp/sync-timetable",
    response_model=HduHelpSyncResponse,
)
def sync_timetable(
    user_id: str,
    payload: HduHelpSyncRequest,
    request: Request,
) -> HduHelpSyncResponse:
    container = request.app.state.container
    token = _credential(request, user_id)
    now = _now(request)
    try:
        rows = container.hduhelp.schedule(token)
        entries = schedule_to_sessions(
            rows,
            school_year=payload.school_year,
            semester=payload.semester,
        )
    except AppError as exc:
        container.external_connections.mark_error(
            user_id,
            exc.message,
            now,
        )
        raise
    if not entries:
        raise AppError(
            "HDUHELP_TERM_EMPTY",
            "所选学期没有可同步的课程，请换一个学期。",
            status_code=422,
        )
    max_week = max(
        (max(entry.weeks) for entry in entries if entry.weeks),
        default=0,
    )
    term_end = payload.term_end
    if term_end is None and max_week:
        term_end = payload.term_start + timedelta(weeks=max_week, days=-1)
    result = container.timetables.replace(
        user_id=user_id,
        name=payload.name,
        term_start=payload.term_start,
        term_end=term_end,
        enabled=True,
        entries=entries,
        now=now,
    )
    container.external_connections.mark_synced(user_id, now)
    return HduHelpSyncResponse(
        **result.model_dump(mode="python"),
        imported_count=len(entries),
        skipped_count=0,
        messages=[
            "已按课程、星期、节次和教室合并重复周次。",
            "同步会覆盖当前启用的个人课表。",
        ],
        school_year=payload.school_year,
        semester=payload.semester,
    )
