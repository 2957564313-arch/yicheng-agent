from __future__ import annotations

import re
from datetime import date, datetime, time
from itertools import combinations
from zoneinfo import ZoneInfo

from app.container import AppContainer
from app.nodes.common import append_trace
from app.schemas.calendar import AcademicDayContext
from app.schemas.common import DataSource, Issue, IssueSeverity
from app.schemas.context import RetrievedFact, WeatherContext
from app.schemas.task import Task, UserPreferences
from app.state import CampusAgentState


def make_enrich_node(container: AppContainer):
    async def enrich(state: CampusAgentState) -> dict:
        tasks = [Task.model_validate(raw) for raw in state["tasks"]]
        is_knowledge_query = state.get("intent") == "query"
        warnings = [
            Issue.model_validate(raw)
            for raw in state.get("provider_warnings", [])
        ]
        preferences = UserPreferences.model_validate(state["preferences"])
        transport_mode = preferences.transport_mode.value
        normalized_locations = {}
        prefer_live = (
            state.get("mode") in {"auto", "live"}
            and container.settings.live_route_enabled
        )

        for index, task in enumerate(tasks):
            raw_location = task.location_raw or task.location_id
            location = (
                container.locations.get(task.location_id)
                if task.location_id
                else container.locations.resolve(task.location_raw)
            )
            if (
                location is None
                and raw_location
                and prefer_live
                and container.geocoder is not None
            ):
                try:
                    location = await container.geocoder.resolve(raw_location)
                except Exception:
                    location = None
            if location:
                tasks[index] = task.model_copy(
                    update={"location_id": location.id}
                )
                normalized_locations[location.id] = location.model_dump(
                    mode="json"
                )
            elif raw_location:
                warnings.append(
                    Issue(
                        code="UNKNOWN_LOCATION",
                        severity=IssueSeverity.WARNING,
                        message=(
                            f"“{raw_location}”"
                            "暂未匹配到本校地点库；这项固定安排会保留，"
                            "但相关通勤时间建议出发前再确认"
                        ),
                        task_ids=[task.id],
                        recoverable=True,
                    )
                )

        initial_location_id = None
        initial_location_raw = state.get("initial_location_raw")
        if initial_location_raw:
            initial_location = container.locations.resolve(
                initial_location_raw
            )
            if (
                initial_location is None
                and prefer_live
                and container.geocoder is not None
            ):
                try:
                    initial_location = await container.geocoder.resolve(
                        initial_location_raw
                    )
                except Exception:
                    initial_location = None
            if initial_location:
                initial_location_id = initial_location.id
                normalized_locations[initial_location.id] = (
                    initial_location.model_dump(mode="json")
                )
            elif not any(
                warning.code == "UNKNOWN_LOCATION"
                and initial_location_raw in warning.message
                for warning in warnings
            ):
                warnings.append(
                    Issue(
                        code="UNKNOWN_LOCATION",
                        severity=IssueSeverity.WARNING,
                        message=(
                            f"“{initial_location_raw}”暂未匹配到高德或"
                            "本校地点库；首段通勤时间请出发前再确认"
                        ),
                        recoverable=True,
                    )
                )

        location_ids = sorted(
            {
                task.location_id
                for task in tasks
                if task.location_id
            }
        )
        if initial_location_id:
            location_ids.append(initial_location_id)
            location_ids = sorted(set(location_ids))
        if is_knowledge_query:
            query_text = state["query"]
            for location in container.locations.all():
                names = [location.name, *location.aliases]
                if any(name and name in query_text for name in names):
                    location_ids.append(location.id)
            location_ids = sorted(set(location_ids))

        routes = []
        for origin, destination in combinations(location_ids, 2):
            for start, end in (
                (origin, destination),
                (destination, origin),
            ):
                try:
                    estimate = await container.routes.get_route(
                        start,
                        end,
                        mode=transport_mode,
                        prefer_live=prefer_live,
                    )
                    routes.append(estimate)
                except LookupError:
                    continue
        route_warning_messages = list(
            dict.fromkeys(
                route.warning for route in routes if route.warning
            )
        )
        for message in route_warning_messages:
            warnings.append(
                Issue(
                    code="ROUTE_FALLBACK",
                    severity=IssueSeverity.WARNING,
                    message=message,
                    details={"transport_mode": transport_mode},
                    recoverable=True,
                )
            )

        location_data_quality = container.locations.data_quality.lower()
        if any(
            marker in location_data_quality
            for marker in (
                "demo_fixture",
                "not_verified",
                "unverified",
                "coordinates_pending",
            )
        ):
            warnings.append(
                Issue(
                    code="UNVERIFIED_CAMPUS_DATA",
                    severity=IssueSeverity.WARNING,
                    message="当前校园地点和通勤数据为待核验演示数据",
                    recoverable=True,
                )
            )
        elif prefer_live:
            missing_live_location_ids = [
                location_id
                for location_id in location_ids
                if (
                    (location := container.locations.get(location_id))
                    and (
                        location.longitude is None
                        or location.latitude is None
                    )
                )
            ]
            if missing_live_location_ids:
                warnings.append(
                    Issue(
                        code="PARTIAL_LIVE_ROUTE_COVERAGE",
                        severity=IssueSeverity.WARNING,
                        message=(
                            "部分泛化地点未绑定唯一坐标，相关路线将使用"
                            "本地通勤数据"
                        ),
                        details={
                            "location_ids": missing_live_location_ids
                        },
                        recoverable=True,
                    )
                )
        if state.get("mode") == "offline" and not is_knowledge_query:
            warnings.append(
                Issue(
                    code="API_DEGRADED",
                    severity=IssueSeverity.WARNING,
                    message=(
                        "当前为离线演示模式，路线和天气不会调用实时接口"
                    ),
                    details={"mode": "offline"},
                )
            )

        target_date = date.fromisoformat(state["requested_date"])
        academic_day = (
            AcademicDayContext.model_validate(state["academic_day_context"])
            if state.get("academic_day_context")
            else None
        )
        congestion_windows = container.rules.congestion_contexts(target_date)
        opening_windows = {}
        for location_id in location_ids:
            if not container.rules.has_opening_rule(location_id):
                continue
            windows = container.rules.opening_windows(
                location_id,
                target_date,
                is_national_holiday=bool(
                    academic_day and academic_day.day_type == "holiday"
                ),
            )
            opening_windows[location_id] = [
                [start.isoformat(), end.isoformat()]
                for start, end in windows
            ]
            if (
                not windows
                and academic_day
                and academic_day.day_type == "holiday"
                and container.rules.closes_on_national_holidays(location_id)
            ):
                affected = [
                    task.id
                    for task in tasks
                    if task.location_id == location_id
                ]
                if affected:
                    location_name = (
                        container.locations.get(location_id).name
                        if container.locations.get(location_id)
                        else location_id
                    )
                    warnings.append(
                        Issue(
                            code="OUTSIDE_OPENING_HOURS",
                            severity=IssueSeverity.ERROR,
                            message=(
                                f"{location_name}的常规开放规则不适用于"
                                f"{academic_day.label or '法定节假日'}，"
                                "在没有专门开放通知前不能把任务安排进去"
                            ),
                            task_ids=affected,
                            recoverable=True,
                        )
                    )

        structured_facts = container.rules.facts_for_locations(
            set(location_ids)
        )
        if academic_day and (
            academic_day.course_action != "normal"
            or academic_day.day_type == "unknown"
        ):
            if academic_day.day_type == "unknown":
                content = (
                    f"{target_date.year}年国家法定节假日安排尚未录入"
                    "已核验数据；当前仍按普通星期课表规划，但临近日期时"
                    "需要再核对国务院通知和学校校历。"
                )
                warnings.append(
                    Issue(
                        code="ANNUAL_CALENDAR_NOT_VERIFIED",
                        severity=IssueSeverity.WARNING,
                        message=content,
                        recoverable=True,
                    )
                )
            elif academic_day.course_action == "no_class":
                content = (
                    f"{target_date:%Y年%m月%d日}为"
                    f"{academic_day.label or '校历休息日'}，"
                    "个人课表中的常规课程不占用当天；学习、运动和生活"
                    "任务仍可照常规划。如学校另有临时通知，以学校通知"
                    "为准。"
                )
            elif academic_day.course_action == "makeup":
                weekday = "一二三四五六日"[
                    int(academic_day.effective_weekday or 1) - 1
                ]
                content = (
                    f"{target_date:%Y年%m月%d日}按学校校历执行"
                    f"星期{weekday}的课表；这些补课课程已作为固定约束。"
                )
            else:
                content = (
                    f"{target_date:%Y年%m月%d日}为"
                    f"{academic_day.label or '国家调休工作日'}。"
                    "国家通知只说明当天上班，不能据此推断学校补星期几"
                    "的课程；在未录入学校教务通知前，系统不会臆造课程。"
                )
                warnings.append(
                    Issue(
                        code="SCHOOL_CALENDAR_CONFIRMATION_REQUIRED",
                        severity=IssueSeverity.WARNING,
                        message=(
                            "这一天属于国家调休工作日，但学校具体补课"
                            "安排尚未录入，请以教务通知为准"
                        ),
                        recoverable=True,
                    )
                )
            structured_facts = [
                RetrievedFact(
                    id=f"academic_calendar_{target_date.isoformat()}",
                    content=content,
                    priority=120,
                    source=academic_day.source,
                    source_ref=academic_day.source_ref or "个人校历设置",
                    verified_at=academic_day.verified_at,
                    metadata={
                        "day_type": academic_day.day_type,
                        "course_action": academic_day.course_action,
                    },
                ),
                *structured_facts,
            ]
        if is_knowledge_query and state.get("timetable_summary"):
            structured_facts = [
                RetrievedFact(
                    id="personal_timetable",
                    content=state["timetable_summary"],
                    priority=100,
                    source=DataSource.USER,
                    source_ref="个人课表",
                ),
                *structured_facts,
            ]
        rag_facts = []
        if not (is_knowledge_query and state.get("timetable_summary")):
            rag_facts = await container.rag.retrieve(
                [
                    state["query"],
                    *[task.title for task in tasks],
                    *location_ids,
                ],
                top_k=5 if is_knowledge_query else 3,
            )
        weather = []
        if not is_knowledge_query:
            weather = await container.weather.get_forecast(
                target_date,
                "campus_main",
                prefer_live=(
                    state.get("mode") in {"auto", "live"}
                    and container.settings.live_weather_enabled
                ),
            )
            user_weather = _explicit_user_weather(
                query=state["query"],
                target_date=target_date,
                timezone_name=container.settings.app_timezone,
            )
            if user_weather:
                weather = [user_weather, *weather]
        if (
            not is_knowledge_query
            and all(item.source == DataSource.UNKNOWN for item in weather)
        ):
            warnings.append(
                Issue(
                    code="API_DEGRADED",
                    severity=IssueSeverity.WARNING,
                    message="未获取到可靠天气，户外安排请出发前复核",
                    details={"provider": "weather"},
                )
            )

        return {
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "initial_location_id": initial_location_id,
            "normalized_locations": normalized_locations,
            "travel_estimates": [
                route.model_dump(mode="json") for route in routes
            ],
            "congestion_windows": [
                item.model_dump(mode="json")
                for item in congestion_windows
            ],
            "weather_context": [
                item.model_dump(mode="json") for item in weather
            ],
            "retrieved_facts": [
                fact.model_dump(mode="json")
                for fact in [*structured_facts, *rag_facts]
            ],
            "opening_windows": opening_windows,
            "provider_warnings": [
                warning.model_dump(mode="json") for warning in warnings
            ],
            "status": "enriched",
            "node_trace": append_trace(
                state,
                "enrich",
                {
                    "locations": len(normalized_locations),
                    "routes": len(routes),
                    "transport_mode": transport_mode,
                    "congestion_windows": len(congestion_windows),
                    "facts": len(structured_facts) + len(rag_facts),
                    "warnings": len(warnings),
                },
            ),
        }

    return enrich


def _explicit_user_weather(
    *,
    query: str,
    target_date: date,
    timezone_name: str,
) -> WeatherContext | None:
    """Turn an explicit user weather update into a hard planning input."""
    if not any(word in query for word in ("有雨", "下雨", "降雨")):
        return None
    matches = list(
        re.finditer(
            r"(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?\s*点?\s*"
            r"(?:以后|之后|后|开始)[^，。；]{0,8}"
            r"(?:有雨|下雨|降雨)",
            query,
        )
    )
    if not matches:
        return None
    match = matches[-1]
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    risk_start = datetime.combine(
        target_date,
        time(hour, minute),
        ZoneInfo(timezone_name),
    )
    return WeatherContext(
        date=target_date,
        period=f"{hour:02d}:{minute:02d}以后",
        condition="用户告知有雨",
        rain_probability=1,
        risk_start_at=risk_start,
        source=DataSource.USER,
    )
