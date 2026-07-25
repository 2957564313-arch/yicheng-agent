from __future__ import annotations

from typing import Any, TypedDict


class CampusAgentState(TypedDict, total=False):
    trace_id: str
    user_id: str
    thread_id: str
    request_id: str
    now_iso: str
    timezone: str
    mode: str

    query: str
    intent: str
    requested_date: str | None
    old_plan_id: str | None
    old_plan: dict[str, Any] | None

    tasks: list[dict[str, Any]]
    preferences: dict[str, Any]
    client_memories: list[dict[str, Any]]
    client_timetable: dict[str, Any] | None
    client_calendar_overrides: list[dict[str, Any]]
    active_campus: dict[str, Any] | None
    user_memories: list[dict[str, Any]]
    timetable_summary: str | None
    academic_day_context: dict[str, Any] | None
    initial_location_raw: str | None
    initial_location_id: str | None
    initial_departure_at: str | None
    clarifications: list[str]
    parse_confidence: float

    normalized_locations: dict[str, dict[str, Any]]
    travel_estimates: list[dict[str, Any]]
    congestion_windows: list[dict[str, Any]]
    weather_context: list[dict[str, Any]]
    retrieved_facts: list[dict[str, Any]]
    opening_windows: dict[str, list[list[str]]]
    task_windows: dict[str, list[list[str]]]
    provider_warnings: list[dict[str, Any]]

    candidate_plan: dict[str, Any] | None
    validation_issues: list[dict[str, Any]]
    replan_count: int
    max_replans: int
    planner_diagnostics: dict[str, Any]

    final_answer: str
    final_plan: dict[str, Any] | None
    response_warnings: list[dict[str, Any]]
    suggested_actions: list[dict[str, Any]]

    node_trace: list[dict[str, Any]]
    status: str
