from __future__ import annotations

import base64
import hashlib
import io
import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import qrcode
from fastapi import APIRouter, Request, Response, status

from app.errors import AppError
from app.providers.hduhelp import available_terms, schedule_to_sessions
from app.schemas.hduhelp import (
    HduHelpConnectionStatus,
    HduHelpConnectRequest,
    HduHelpQRPollRequest,
    HduHelpQRPollResponse,
    HduHelpQRStartResponse,
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
    raw = container.credential_cipher.decrypt(row["credential_ciphertext"])
    try:
        bundle = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw
    token = str(bundle.get("accessToken", "")).strip()
    refresh = str(bundle.get("refreshToken", "")).strip()
    expires_at = int(
        bundle.get("accessExpireAt")
        or bundle.get("accessTokenExpireAt")
        or 0
    )
    if token and (
        not expires_at or expires_at > int(_now(request).timestamp()) + 60
    ):
        return token
    if not refresh:
        raise AppError(
            "HDUHELP_LOGIN_EXPIRED",
            "杭电助手登录已过期，请重新扫码。",
            status_code=401,
        )
    refreshed = container.hduhelp.refresh_login_token(refresh)
    token = str(refreshed.get("accessToken", "")).strip()
    if not token:
        raise AppError(
            "HDUHELP_LOGIN_EXPIRED",
            "杭电助手登录已过期，请重新扫码。",
            status_code=401,
        )
    refreshed.setdefault("refreshToken", refresh)
    container.external_connections.update_credential(
        user_id,
        container.credential_cipher.encrypt(json.dumps(refreshed)),
        _now(request),
    )
    return token


def _status(request: Request, user_id: str) -> HduHelpConnectionStatus:
    container = request.app.state.container
    result = container.external_connections.status(user_id, "hduhelp")
    result.oauth_ready = bool(container.settings.hduhelp_qr_client_id)
    result.synced_counts = container.external_agenda.counts(user_id)
    return result


@router.get(
    "/{user_id}/connections/hduhelp",
    response_model=HduHelpConnectionStatus,
)
def get_connection(user_id: str, request: Request) -> HduHelpConnectionStatus:
    return _status(request, user_id)


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
            "账号可以登录，但没有读取到个人课表。",
            status_code=422,
        )
    container.external_connections.save(
        user_id=user_id,
        external_user_id=str(identity.get("id", "")).strip(),
        display_name=str(identity.get("nickName", "")).strip() or None,
        credential_ciphertext=container.credential_cipher.encrypt(token),
        terms=terms,
        now=_now(request),
    )
    return _status(request, user_id)


@router.post(
    "/{user_id}/connections/hduhelp/wechat/start",
    response_model=HduHelpQRStartResponse,
)
def start_wechat_login(
    user_id: str,
    request: Request,
) -> HduHelpQRStartResponse:
    settings = request.app.state.container.settings
    if not settings.hduhelp_qr_client_id:
        return HduHelpQRStartResponse(
            ready=False,
            message=(
                "微信扫码登录代码已经接好；还需要杭电助手为本项目提供"
                "应用 Client ID 后才能启用。"
            ),
        )
    data = request.app.state.container.hduhelp.create_wechat_qr(
        client_id=settings.hduhelp_qr_client_id,
        redirect_uri=settings.hduhelp_qr_redirect_uri,
    )
    authorize_url = str(data.get("authorizeURL", "")).strip()
    poll_token = str(data.get("pollToken", "")).strip()
    if not authorize_url or not poll_token:
        raise AppError(
            "HDUHELP_QR_INVALID",
            "杭电助手没有返回可用的登录二维码，请稍后重试。",
            status_code=502,
            retryable=True,
        )
    image = qrcode.make(authorize_url)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    qr_data_url = (
        "data:image/png;base64,"
        + base64.b64encode(buffer.getvalue()).decode("ascii")
    )
    return HduHelpQRStartResponse(
        ready=True,
        authorize_url=authorize_url,
        qr_data_url=qr_data_url,
        poll_token=poll_token,
        expires_at=data.get("expiresAt"),
        message="请使用微信打开授权页面，完成杭电助手登录。",
    )


@router.post(
    "/{user_id}/connections/hduhelp/wechat/poll",
    response_model=HduHelpQRPollResponse,
)
def poll_wechat_login(
    user_id: str,
    payload: HduHelpQRPollRequest,
    request: Request,
) -> HduHelpQRPollResponse:
    container = request.app.state.container
    result = container.hduhelp.poll_wechat_qr(payload.poll_token)
    scan_status = str(result.get("status", "pending"))
    if scan_status != "authorized":
        return HduHelpQRPollResponse(
            status=scan_status,
            message="等待微信确认。",
        )
    tokens = container.hduhelp.exchange_login_code(
        str(result.get("code", "")).strip()
    )
    access_token = str(tokens.get("accessToken", "")).strip()
    identity = container.hduhelp.identity(access_token)
    external_id = str(identity.get("id", "")).strip()
    stable_user_id = (
        "hdu_" + hashlib.sha256(external_id.encode()).hexdigest()[:24]
    )
    rows = container.hduhelp.schedule(access_token)
    container.external_connections.save(
        user_id=stable_user_id,
        external_user_id=external_id,
        display_name=str(identity.get("nickName", "")).strip() or None,
        credential_ciphertext=container.credential_cipher.encrypt(
            json.dumps(tokens)
        ),
        terms=available_terms(rows),
        now=_now(request),
    )
    app_access_token, expires_at = request.app.state.access_manager.issue_session(
        mode="normal",
        user_id=stable_user_id,
    )
    return HduHelpQRPollResponse(
        status="authorized",
        user_id=stable_user_id,
        display_name=str(identity.get("nickName", "")).strip() or None,
        access_token=app_access_token,
        expires_at=expires_at,
        message="登录成功，正在进入你的个人空间。",
    )


@router.delete(
    "/{user_id}/connections/hduhelp",
    status_code=status.HTTP_204_NO_CONTENT,
)
def disconnect(user_id: str, request: Request) -> Response:
    container = request.app.state.container
    container.external_agenda.clear_provider(user_id, "hduhelp")
    container.external_connections.delete(user_id, "hduhelp")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _inferred_term_dates(
    school_year: str,
    semester: int,
    max_week: int,
) -> tuple[date, date]:
    start_year, end_year = (
        int(value) for value in school_year.split("-", 1)
    )
    anchor = (
        date(start_year, 9, 1)
        if semester == 1
        else date(end_year, 3, 1)
    )
    term_start = anchor - timedelta(days=anchor.weekday())
    term_end = term_start + timedelta(weeks=max(max_week, 18), days=-1)
    return term_start, term_end


def _resolved_term_dates(
    *,
    school_year: str,
    semester: int,
    max_week: int,
    school_time: dict[str, Any],
    timezone: ZoneInfo,
) -> tuple[date, date, bool]:
    """Resolve the current term exactly; explicitly flag a fallback estimate."""
    try:
        same_term = (
            str(school_time.get("schoolYear", "")).strip() == school_year
            and int(school_time.get("semester")) == semester
        )
        week_now = int(school_time.get("weekNow"))
        weekday_now = int(school_time.get("weekDayNow"))
        timestamp = int(school_time.get("timeStamp"))
    except (TypeError, ValueError):
        same_term = False
        week_now = weekday_now = timestamp = 0
    if same_term and week_now > 0 and 0 <= weekday_now <= 7 and timestamp > 0:
        current = datetime.fromtimestamp(timestamp, timezone).date()
        # HDUHelp uses 0 for Sunday and 1-6 for Monday-Saturday.
        days_since_monday = 6 if weekday_now == 0 else weekday_now - 1
        term_start = current - timedelta(
            weeks=week_now - 1,
            days=days_since_monday,
        )
        term_end = term_start + timedelta(weeks=max(max_week, 18), days=-1)
        return term_start, term_end, False
    term_start, term_end = _inferred_term_dates(
        school_year,
        semester,
        max_week,
    )
    return term_start, term_end, True


def _dt(value: Any, timezone: ZoneInfo) -> datetime | None:
    if value in {None, "", 0}:
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value), timezone)
        parsed = datetime.fromisoformat(str(value))
        return (
            parsed.replace(tzinfo=timezone)
            if parsed.tzinfo is None
            else parsed.astimezone(timezone)
        )
    except (TypeError, ValueError, OSError):
        return None


def _event(
    *,
    external_id: str,
    title: str,
    start: Any,
    end: Any,
    timezone: ZoneInfo,
    location: str | None = None,
    status_value: str = "active",
) -> dict | None:
    start_at, end_at = _dt(start, timezone), _dt(end, timezone)
    if (
        not external_id
        or not title
        or not start_at
        or not end_at
        or end_at <= start_at
    ):
        return None
    return {
        "external_id": external_id[:200],
        "title": title[:160],
        "start_at": start_at,
        "end_at": end_at,
        "location_name": (location or "").strip()[:160] or None,
        "status": status_value[:40] or "active",
    }


def _exam_event(row: dict[str, Any], timezone: ZoneInfo) -> dict | None:
    raw = str(row.get("examTime", "")).strip()
    try:
        day, interval = raw.split(" ", 1)
        start_clock, end_clock = interval.split("-", 1)
        start = datetime.fromisoformat(f"{day}T{start_clock}")
        end = datetime.fromisoformat(f"{day}T{end_clock}")
    except (TypeError, ValueError):
        return None
    return _event(
        external_id=(
            str(row.get("selectCode") or row.get("course") or raw)
            + f":{raw}"
        ),
        title=f"{str(row.get('course', '')).strip()}考试",
        start=start,
        end=end,
        timezone=timezone,
        location=str(row.get("classroom", "")),
        status_value="confirmed",
    )


def _safe_sync(
    *,
    source_kind: str,
    fetch: Callable[[], list[dict[str, Any]]],
    convert: Callable[[dict[str, Any]], dict | None],
    user_id: str,
    request: Request,
    now: datetime,
    warnings: list[str],
) -> int:
    container = request.app.state.container
    try:
        converted = [
            event
            for row in fetch()
            if (event := convert(row)) is not None
        ]
    except AppError as exc:
        warnings.append(f"{source_kind}：{exc.message}")
        return container.external_agenda.counts(user_id).get(source_kind, 0)
    return container.external_agenda.replace_source(
        user_id=user_id,
        provider="hduhelp",
        source_kind=source_kind,
        items=converted,
        now=now,
    )


@router.post(
    "/{user_id}/connections/hduhelp/sync",
    response_model=HduHelpSyncResponse,
)
@router.post(
    "/{user_id}/connections/hduhelp/sync-timetable",
    response_model=HduHelpSyncResponse,
)
def sync_all(
    user_id: str,
    payload: HduHelpSyncRequest,
    request: Request,
) -> HduHelpSyncResponse:
    container = request.app.state.container
    token = _credential(request, user_id)
    now = _now(request)
    timezone = ZoneInfo(container.settings.app_timezone)
    try:
        rows = container.hduhelp.schedule(token)
        entries = schedule_to_sessions(
            rows,
            school_year=payload.school_year,
            semester=payload.semester,
        )
    except AppError as exc:
        container.external_connections.mark_error(user_id, exc.message, now)
        raise
    if not entries:
        raise AppError(
            "HDUHELP_TERM_EMPTY",
            "所选学期没有可同步的课程。",
            status_code=422,
        )
    max_week = max(
        (max(entry.weeks) for entry in entries if entry.weeks),
        default=18,
    )
    warnings: list[str] = []
    try:
        school_time = container.hduhelp.school_time(token)
    except AppError as exc:
        school_time = {}
        warnings.append(f"校历：{exc.message}")
    term_start, term_end, dates_inferred = _resolved_term_dates(
        school_year=payload.school_year,
        semester=payload.semester,
        max_week=max_week,
        school_time=school_time,
        timezone=timezone,
    )
    if dates_inferred:
        warnings.append(
            "所选不是杭助当前学期，教学周日期暂按学期规则估算；"
            "正式使用前请以学校校历为准。"
        )
    timetable = container.timetables.replace(
        user_id=user_id,
        name=payload.name,
        term_start=term_start,
        term_end=term_end,
        enabled=True,
        entries=entries,
        now=now,
    )
    counts: dict[str, int] = {"course": len(entries)}
    counts["library_reservation"] = _safe_sync(
        source_kind="library_reservation",
        fetch=lambda: (
            container.hduhelp.library_agenda(token)
            if hasattr(container.hduhelp, "library_agenda")
            else container.hduhelp.library_reservations(token)
        ),
        convert=lambda row: _event(
            external_id=str(
                row.get("externalId")
                or f"{row.get('staffId', '')}:{row.get('startTime', '')}:"
                f"{row.get('seatNo', '')}"
            ),
            title="图书馆自习预约",
            start=row.get("start") or row.get("startTime"),
            end=row.get("end") or row.get("endTime"),
            timezone=timezone,
            location=" ".join(
                filter(
                    None,
                    [
                        str(row.get("room", "")).strip(),
                        str(row.get("seat") or row.get("seatNo", "")).strip(),
                    ],
                )
            ),
            status_value=str(
                row.get("status") or row.get("finalState", "active")
            ),
        ),
        user_id=user_id,
        request=request,
        now=now,
        warnings=warnings,
    )
    counts["second_classroom"] = _safe_sync(
        source_kind="second_classroom",
        fetch=lambda: container.hduhelp.my_activities(token),
        convert=lambda row: _event(
            external_id=str(row.get("activityID", "")),
            title=str(row.get("activityName", "")),
            start=row.get("activityStartTime"),
            end=row.get("activityEndTime"),
            timezone=timezone,
            location=str(row.get("position", "")),
            status_value=str(row.get("activityStatusName", "active")),
        ),
        user_id=user_id,
        request=request,
        now=now,
        warnings=warnings,
    )
    counts["exam"] = _safe_sync(
        source_kind="exam",
        fetch=lambda: container.hduhelp.exams(
            token,
            payload.school_year,
            payload.semester,
        ),
        convert=lambda row: _exam_event(row, timezone),
        user_id=user_id,
        request=request,
        now=now,
        warnings=warnings,
    )
    container.external_connections.mark_synced(user_id, now)
    return HduHelpSyncResponse(
        **timetable.model_dump(mode="python"),
        imported_count=len(entries),
        skipped_count=0,
        messages=[
            "已同步课表，并尝试刷新图书馆预约、二课与考试数据。"
        ],
        school_year=payload.school_year,
        semester=payload.semester,
        synced_counts=counts,
        warnings=warnings,
    )
