from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response, status

from app.errors import AppError
from app.providers.hduhelp import available_terms, schedule_to_sessions
from app.schemas.hduhelp import (
    HduHelpConnectionStatus,
    HduHelpConnectRequest,
    HduHelpSyncRequest,
    HduHelpSyncResponse,
    HduHelpTimetablesResponse,
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
    if not token:
        raise AppError(
            "HDUHELP_LOGIN_EXPIRED",
            "杭电助手个人访问令牌已失效，请重新连接。",
            status_code=401,
        )
    return token


def _status(request: Request, user_id: str) -> HduHelpConnectionStatus:
    container = request.app.state.container
    result = container.external_connections.status(user_id, "hduhelp")
    result.synced_counts = {
        **container.external_data.counts(user_id),
        **container.external_agenda.counts(user_id),
    }
    return result


@router.get(
    "/{user_id}/connections/hduhelp",
    response_model=HduHelpConnectionStatus,
)
def get_connection(user_id: str, request: Request) -> HduHelpConnectionStatus:
    return _status(request, user_id)


@router.get(
    "/{user_id}/connections/hduhelp/timetables",
    response_model=HduHelpTimetablesResponse,
)
def get_synced_timetables(
    user_id: str,
    request: Request,
) -> HduHelpTimetablesResponse:
    payload = request.app.state.container.external_data.get(
        user_id,
        "timetable_terms",
    )
    return HduHelpTimetablesResponse(
        terms=payload if isinstance(payload, list) else [],
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


@router.delete(
    "/{user_id}/connections/hduhelp",
    status_code=status.HTTP_204_NO_CONTENT,
)
def disconnect(user_id: str, request: Request) -> Response:
    container = request.app.state.container
    container.external_agenda.clear_provider(user_id, "hduhelp")
    container.external_data.clear_provider(user_id, "hduhelp")
    container.external_connections.delete(user_id, "hduhelp")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _inferred_term_dates(
    school_year: str,
    semester: int,
    max_week: int,
) -> tuple[date, date]:
    start_year, end_year = (int(value) for value in school_year.split("-", 1))
    anchor = date(start_year, 9, 1) if semester == 1 else date(end_year, 3, 1)
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
    if not external_id or not title or not start_at or not end_at or end_at <= start_at:
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
            str(row.get("selectCode") or row.get("course") or raw) + f":{raw}"
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
        converted = [event for row in fetch() if (event := convert(row)) is not None]
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


def _safe_snapshot(
    *,
    source_kind: str,
    fetch: Callable[[], Any],
    user_id: str,
    request: Request,
    now: datetime,
    warnings: list[str],
) -> int:
    """Refresh one optional source and preserve the last good snapshot on failure."""
    container = request.app.state.container
    try:
        payload = fetch()
    except AppError as exc:
        warnings.append(f"{source_kind}：{exc.message}")
        return container.external_data.counts(user_id).get(source_kind, 0)
    except AttributeError:
        # Allows older provider adapters and test doubles to keep core sync
        # working while optional read-only capabilities are unavailable.
        warnings.append(f"{source_kind}：当前连接暂不支持此项数据")
        return container.external_data.counts(user_id).get(source_kind, 0)
    return container.external_data.replace_source(
        user_id=user_id,
        provider="hduhelp",
        source_kind=source_kind,
        payload=payload,
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
        terms = available_terms(rows)
        school_time = container.hduhelp.school_time(token)
    except AppError as exc:
        container.external_connections.mark_error(user_id, exc.message, now)
        raise
    if not terms:
        raise AppError(
            "HDUHELP_SCHEDULE_EMPTY",
            "杭助没有返回可同步的课表。",
            status_code=422,
        )
    warnings: list[str] = []
    current_key = (
        str(school_time.get("schoolYear", "")).strip(),
        str(school_time.get("semester", "")).strip(),
    )
    term_payloads: list[dict[str, Any]] = []
    for term in terms:
        entries = schedule_to_sessions(
            rows,
            school_year=term.school_year,
            semester=term.semester,
        )
        max_week = max(
            (max(entry.weeks) for entry in entries if entry.weeks),
            default=18,
        )
        term_start, term_end, dates_inferred = _resolved_term_dates(
            school_year=term.school_year,
            semester=term.semester,
            max_week=max_week,
            school_time=school_time,
            timezone=timezone,
        )
        term_payloads.append(
            {
                "school_year": term.school_year,
                "semester": term.semester,
                "name": f"{term.school_year} · 第{term.semester}学期",
                "term_start": term_start.isoformat(),
                "term_end": term_end.isoformat(),
                "current": current_key == (term.school_year, str(term.semester)),
                "dates_inferred": dates_inferred,
                "entries": [entry.model_dump(mode="json") for entry in entries],
            }
        )
    active = next(
        (term for term in term_payloads if term["current"]),
        None,
    )
    if active is None and payload.school_year and payload.semester:
        active = next(
            (
                term
                for term in term_payloads
                if term["school_year"] == payload.school_year
                and term["semester"] == payload.semester
            ),
            None,
        )
    active = active or term_payloads[0]
    if any(term["dates_inferred"] for term in term_payloads):
        warnings.append("非当前学期的教学周日期由杭助学年学期与周次推算。")
    container.external_data.replace_source(
        user_id=user_id,
        provider="hduhelp",
        source_kind="timetable_terms",
        payload=term_payloads,
        now=now,
    )
    container.external_data.replace_source(
        user_id=user_id,
        provider="hduhelp",
        source_kind="school_time",
        payload=school_time,
        now=now,
    )
    timetable = container.timetables.replace(
        user_id=user_id,
        name=str(active["name"]),
        term_start=date.fromisoformat(str(active["term_start"])),
        term_end=date.fromisoformat(str(active["term_end"])),
        enabled=True,
        entries=schedule_to_sessions(
            rows,
            school_year=str(active["school_year"]),
            semester=int(active["semester"]),
        ),
        now=now,
    )
    total_course_count = sum(len(term["entries"]) for term in term_payloads)
    counts: dict[str, int] = {
        "course": total_course_count,
        "timetable_terms": len(term_payloads),
    }
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
            status_value=str(row.get("status") or row.get("finalState", "active")),
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
        fetch=lambda: [
            row
            for term in terms
            for row in container.hduhelp.exams(
                token,
                term.school_year,
                term.semester,
            )
        ],
        convert=lambda row: _exam_event(row, timezone),
        user_id=user_id,
        request=request,
        now=now,
        warnings=warnings,
    )
    snapshot_fetchers: dict[str, Callable[[], Any]] = {
        "identity_bindings": lambda: container.hduhelp.identity_bindings(token),
        "semester_list": lambda: container.hduhelp.semester_list(
            token,
            start_date=min(term["term_start"] for term in term_payloads),
            end_date=max(term["term_end"] for term in term_payloads),
        ),
        "course_selection": lambda: [
            {
                "school_year": term.school_year,
                "semester": term.semester,
                "items": container.hduhelp.course_selection(
                    token,
                    school_year=term.school_year,
                    semester=term.semester,
                ),
            }
            for term in terms
        ],
        "library_attendance": lambda: container.hduhelp.library_attendance(token),
        "library_reading": lambda: container.hduhelp.library_reading(token),
        "library_rooms": lambda: container.hduhelp.library_rooms(token),
        "volunteer": lambda: container.hduhelp.volunteer_activities(token),
        "sunrun": lambda: container.hduhelp.sunrun_overview(token),
        "subscriptions": lambda: container.hduhelp.subscriptions(token),
        "empty_schedule_status": lambda: container.hduhelp.empty_schedule_status(token),
        "empty_schedule_favorites": lambda: container.hduhelp.empty_schedule_favorites(
            token
        ),
        "empty_schedule_rooms": lambda: container.hduhelp.empty_schedule_rooms(token),
        "feed": lambda: container.hduhelp.feed(token),
    }
    for source_kind, fetch in snapshot_fetchers.items():
        counts[source_kind] = _safe_snapshot(
            source_kind=source_kind,
            fetch=fetch,
            user_id=user_id,
            request=request,
            now=now,
            warnings=warnings,
        )
    container.external_connections.mark_synced(user_id, now)
    return HduHelpSyncResponse(
        **timetable.model_dump(mode="python"),
        imported_count=total_course_count,
        skipped_count=0,
        messages=[
            (
                "已同步杭助当前授权范围内的全部学期课程、考试、图书馆、"
                "活动、空课表、信息流与校园习惯数据。"
            )
        ],
        school_year=str(active["school_year"]),
        semester=int(active["semester"]),
        synced_counts=counts,
        warnings=warnings,
        terms=term_payloads,
    )
