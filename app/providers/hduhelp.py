from __future__ import annotations

from collections import defaultdict
from typing import Any

import httpx

from app.errors import AppError
from app.schemas.hduhelp import HduHelpTerm
from app.schemas.timetable import CourseSessionCreate


class HduHelpClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _get(self, path: str, token: str) -> Any:
        return self._request("GET", path, token=token)

    def _request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                headers=headers,
            ) as client:
                response = client.request(
                    method,
                    path,
                    json=json_body,
                    params=params,
                )
        except httpx.TimeoutException as exc:
            raise AppError(
                "HDUHELP_TIMEOUT",
                "杭电助手连接超时，请稍后重试。",
                status_code=504,
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "HDUHELP_UNAVAILABLE",
                "暂时无法连接杭电助手，请检查网络后重试。",
                status_code=502,
                retryable=True,
            ) from exc
        if response.status_code in {401, 403}:
            raise AppError(
                "HDUHELP_TOKEN_INVALID",
                "个人访问令牌无效、已过期或缺少所需权限。",
                status_code=401,
            )
        if response.status_code >= 400:
            raise AppError(
                "HDUHELP_PROVIDER_ERROR",
                "杭电助手暂时没有返回可用数据。",
                status_code=502,
                retryable=response.status_code >= 500,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError(
                "HDUHELP_INVALID_RESPONSE",
                "杭电助手返回了无法识别的数据。",
                status_code=502,
            ) from exc
        if not isinstance(payload, dict):
            raise AppError(
                "HDUHELP_INVALID_RESPONSE",
                "杭电助手返回的数据结构不完整。",
                status_code=502,
            )
        provider_code = payload.get("code", 0)
        if provider_code not in {0, 200, None} or "data" not in payload:
            message = str(payload.get("msg") or "杭电助手暂时没有返回可用数据。")
            raise AppError(
                "HDUHELP_PROVIDER_ERROR",
                message[:240],
                status_code=502,
                retryable=True,
            )
        return payload["data"]

    def identity(self, token: str) -> dict[str, Any]:
        data = self._get("/hduhelp-neo/identity/me", token)
        if not isinstance(data, dict) or not str(data.get("id", "")).strip():
            raise AppError(
                "HDUHELP_IDENTITY_MISSING",
                "杭电助手没有返回当前用户身份。",
                status_code=502,
            )
        return data

    def schedule(self, token: str) -> list[dict[str, Any]]:
        data = self._get("/hduhelp-neo/academic/schedule", token)
        if not isinstance(data, list):
            raise AppError(
                "HDUHELP_SCHEDULE_INVALID",
                "杭电助手返回的课表格式不正确。",
                status_code=502,
            )
        return [item for item in data if isinstance(item, dict)]

    def school_time(self, token: str) -> dict[str, Any]:
        data = self._get("/hduhelp-neo/academic/schooltime/time", token)
        return data if isinstance(data, dict) else {}

    def exams(self, token: str, school_year: str, semester: int) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            "/hduhelp-neo/academic/exam",
            token=token,
            params={"schoolYear": school_year, "semester": semester},
        )
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def library_reservations(self, token: str) -> list[dict[str, Any]]:
        data = self._get("/hduhelp-neo/academic/library/seat/reservations", token)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def library_bookings(self, token: str) -> list[dict[str, Any]]:
        data = self._get("/hduhelp-neo/library-booking/bookings", token)
        if not isinstance(data, dict):
            return []
        rows = data.get("bookings")
        return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []

    def my_activities(self, token: str) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            "/hduhelp-neo/campuslife/activities/mine",
            token=token,
            params={"status": 0, "page": 1, "pageSize": 100},
        )
        if not isinstance(data, dict):
            return []
        rows = data.get("items")
        return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []

    def create_wechat_qr(
        self,
        *,
        client_id: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/hduhelp-neo/identity/login/wechat/qr",
            json_body={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "return_to": "/",
                "flow": "login",
            },
        )
        return data if isinstance(data, dict) else {}

    def poll_wechat_qr(self, poll_token: str) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/hduhelp-neo/identity/login/wechat/qr/status",
            json_body={"poll_token": poll_token},
        )
        return data if isinstance(data, dict) else {}

    def exchange_login_code(self, code: str) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/hduhelp-neo/identity/login/exchange",
            json_body={"code": code},
        )
        return data if isinstance(data, dict) else {}

    def refresh_login_token(self, refresh_token: str) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/hduhelp-neo/identity/auth/token/refresh",
            json_body={"refreshToken": refresh_token},
        )
        return data if isinstance(data, dict) else {}


def available_terms(rows: list[dict[str, Any]]) -> list[HduHelpTerm]:
    counts: dict[tuple[str, int], int] = defaultdict(int)
    for row in rows:
        school_year = str(row.get("schoolYear", "")).strip()
        try:
            semester = int(row.get("semester"))
        except (TypeError, ValueError):
            continue
        if school_year and 1 <= semester <= 3:
            counts[(school_year, semester)] += 1
    return [
        HduHelpTerm(
            school_year=school_year,
            semester=semester,
            raw_entry_count=count,
        )
        for (school_year, semester), count in sorted(
            counts.items(), reverse=True
        )
    ]


def schedule_to_sessions(
    rows: list[dict[str, Any]],
    *,
    school_year: str,
    semester: int,
) -> list[CourseSessionCreate]:
    grouped: dict[tuple[Any, ...], set[int]] = defaultdict(set)
    for row in rows:
        if str(row.get("schoolYear", "")).strip() != school_year:
            continue
        try:
            row_semester = int(row.get("semester"))
            weekday = int(row.get("day"))
        except (TypeError, ValueError):
            continue
        if row_semester != semester or not 1 <= weekday <= 7:
            continue
        sections = _positive_ints(row.get("sections"))
        if not sections:
            period = _positive_int(row.get("period"))
            sections = [period] if period is not None else []
        if not sections:
            continue
        course_name = str(row.get("courseName", "")).strip()
        if not course_name:
            continue
        location = _location(row)
        course_identity = str(
            row.get("courseId")
            or row.get("courseCode")
            or row.get("selectCode")
            or course_name
        ).strip()
        key = (
            course_identity,
            course_name,
            weekday,
            min(sections),
            max(sections),
            location,
        )
        grouped[key].update(_positive_ints(row.get("weeks")))
        week = _positive_int(row.get("week"))
        if week is not None:
            grouped[key].add(week)
    sessions = [
        CourseSessionCreate(
            course_name=key[1],
            weekday=key[2],
            start_period=key[3],
            end_period=key[4],
            location=key[5] or None,
            weeks=sorted(week for week in weeks if 1 <= week <= 30),
        )
        for key, weeks in grouped.items()
    ]
    return sorted(
        sessions,
        key=lambda item: (
            item.weekday,
            item.start_period,
            item.course_name,
            item.location or "",
        ),
    )


def _positive_int(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _positive_ints(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        parsed = _positive_int(item)
        if parsed is not None:
            result.append(parsed)
    return sorted(set(result))


def _location(row: dict[str, Any]) -> str:
    direct = str(row.get("location", "")).strip()
    if direct:
        return direct[:120]
    building = str(row.get("buildingName", "")).strip()
    room = str(row.get("locationName", "")).strip()
    if building and room and room not in building:
        return f"{building}{room}"[:120]
    return (room or building)[:120]
