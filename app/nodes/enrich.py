from __future__ import annotations

import re
from datetime import date, datetime, time
from itertools import combinations
from zoneinfo import ZoneInfo

from app.container import AppContainer
from app.nodes.common import append_trace
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

        for index, task in enumerate(tasks):
            location = (
                container.locations.get(task.location_id)
                if task.location_id
                else container.locations.resolve(task.location_raw)
            )
            if location:
                tasks[index] = task.model_copy(
                    update={"location_id": location.id}
                )
                normalized_locations[location.id] = location.model_dump(
                    mode="json"
                )
            elif task.location_raw or task.location_id:
                warnings.append(
                    Issue(
                        code="UNKNOWN_LOCATION",
                        severity=IssueSeverity.WARNING,
                        message=(
                            f"“{task.location_raw or task.location_id}”"
                            "暂未匹配到本校地点库；这项固定安排会保留，"
                            "但相关通勤时间建议出发前再确认"
                        ),
                        task_ids=[task.id],
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
        if is_knowledge_query:
            query_text = state["query"]
            for location in container.locations.all():
                names = [location.name, *location.aliases]
                if any(name and name in query_text for name in names):
                    location_ids.append(location.id)
            location_ids = sorted(set(location_ids))

        routes = []
        prefer_live = (
            state.get("mode") in {"auto", "live"}
            and container.settings.live_route_enabled
        )
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
        congestion_windows = container.rules.congestion_contexts(target_date)
        opening_windows = {}
        for location_id in location_ids:
            windows = container.rules.opening_windows(
                location_id,
                target_date,
            )
            opening_windows[location_id] = [
                [start.isoformat(), end.isoformat()]
                for start, end in windows
            ]

        structured_facts = container.rules.facts_for_locations(
            set(location_ids)
        )
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
