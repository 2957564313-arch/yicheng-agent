from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.container import AppContainer
from app.nodes.common import append_trace
from app.schemas.common import TaskFlexibility
from app.schemas.context import CongestionWindow, TravelEstimate, WeatherContext
from app.schemas.plan import Plan
from app.schemas.task import Task, UserPreferences
from app.services.scheduler import PlanningContext
from app.state import CampusAgentState


def make_plan_node(container: AppContainer):
    async def plan(state: CampusAgentState) -> dict:
        tasks = [Task.model_validate(raw) for raw in state["tasks"]]
        preferences = UserPreferences.model_validate(state["preferences"])
        routes = [
            TravelEstimate.model_validate(raw)
            for raw in state.get("travel_estimates", [])
        ]
        route_map = {
            (route.origin_id, route.destination_id): route
            for route in routes
        }
        opening_windows = {
            location_id: [
                (
                    datetime.fromisoformat(start),
                    datetime.fromisoformat(end),
                )
                for start, end in windows
            ]
            for location_id, windows in state.get(
                "opening_windows", {}
            ).items()
        }
        old_plan = (
            Plan.model_validate(state["old_plan"])
            if state.get("old_plan")
            else (
                container.plans.get(state["old_plan_id"])
                if state.get("old_plan_id")
                else None
            )
        )
        weather = [
            WeatherContext.model_validate(raw)
            for raw in state.get("weather_context", [])
        ]
        enforce_weather = (
            state["intent"] == "weather_check"
            or any(item.source.value == "user" for item in weather)
        )
        if state["intent"] == "weather_check" and old_plan:
            tasks = _apply_weather_adjustment(
                tasks=tasks,
                weather=weather,
                old_plan=old_plan,
                normalized_locations=state.get(
                    "normalized_locations", {}
                ),
            )
        context = PlanningContext(
            target_date=tasks[0].date,
            timezone=ZoneInfo(state["timezone"]),
            now=datetime.fromisoformat(state["now_iso"]),
            travel=route_map,
            congestion_windows=[
                CongestionWindow.model_validate(raw)
                for raw in state.get("congestion_windows", [])
            ],
            opening_windows=opening_windows,
            weather=weather,
            outdoor_location_ids={
                location_id
                for location_id, raw in state.get(
                    "normalized_locations", {}
                ).items()
                if raw.get("is_outdoor")
            },
            enforce_weather=enforce_weather,
            old_plan=old_plan,
            initial_location_id=state.get("initial_location_id"),
            initial_departure_at=(
                datetime.fromisoformat(state["initial_departure_at"])
                if state.get("initial_departure_at")
                else None
            ),
        )

        if state["intent"] in {"replan", "weather_check"} and old_plan:
            result = container.replanner.replan(
                user_id=state["user_id"],
                thread_id=state["thread_id"],
                tasks=tasks,
                preferences=preferences,
                context=context,
                old_plan=old_plan,
            )
        else:
            result = container.scheduler.schedule(
                user_id=state["user_id"],
                thread_id=state["thread_id"],
                tasks=tasks,
                preferences=preferences,
                context=context,
            )

        replan_count = state.get("replan_count", 0)
        if state.get("validation_issues"):
            replan_count += 1
        diagnostics = {
            "unscheduled_task_ids": result.unscheduled_task_ids,
            "missing_route_pairs": result.missing_route_pairs,
        }
        return {
            "candidate_plan": result.plan.model_dump(mode="json"),
            "replan_count": replan_count,
            "planner_diagnostics": diagnostics,
            "status": "planned",
            "node_trace": append_trace(
                state,
                "plan",
                {
                    "scheduled": result.plan.metrics.scheduled_task_count,
                    "requested": result.plan.metrics.requested_task_count,
                    "replan_count": replan_count,
                    **diagnostics,
                },
            ),
        }

    return plan


def _apply_weather_adjustment(
    *,
    tasks: list[Task],
    weather: list[WeatherContext],
    old_plan: Plan,
    normalized_locations: dict[str, dict],
) -> list[Task]:
    risk_starts = [
        item.risk_start_at
        for item in weather
        if item.risk_start_at
        and (
            (item.rain_probability or 0) >= 0.5
            or "rain" in (item.condition or "").lower()
            or "雨" in (item.condition or "")
        )
    ]
    if not risk_starts:
        return tasks
    risk_start = min(risk_starts)
    old_items = {
        item.task_id: item
        for item in old_plan.items
        if item.item_type == "task" and item.task_id
    }
    affected = []
    for task in tasks:
        old_item = old_items.get(task.id)
        location = normalized_locations.get(task.location_id or "", {})
        is_outdoor = "outdoor" in task.tags or location.get("is_outdoor")
        if old_item and is_outdoor and old_item.end_at > risk_start:
            affected.append(task.id)
    if not affected:
        return tasks

    first_start = min(
        item.start_at
        for item in old_plan.items
        if item.item_type == "task"
    )
    latest_end = max(
        max(
            item.end_at
            for item in old_plan.items
            if item.item_type == "task"
        ),
        risk_start + timedelta(hours=1),
    )

    adjusted = []
    for task in tasks:
        if task.id in affected:
            adjusted.append(
                task.model_copy(
                    update={
                        "flexibility": TaskFlexibility.FIXED,
                        "fixed_start": first_start,
                        "fixed_end": first_start
                        + timedelta(minutes=task.duration_min),
                        "earliest_start": None,
                        "latest_end": None,
                        "deadline": latest_end,
                        "depends_on": [],
                    }
                )
            )
        else:
            adjusted.append(
                task.model_copy(
                    update={
                        "flexibility": TaskFlexibility.MOVABLE,
                        "fixed_start": None,
                        "fixed_end": None,
                        "earliest_start": first_start,
                        "latest_end": latest_end,
                        "deadline": latest_end,
                        "depends_on": [],
                    }
                )
            )
    return adjusted
