from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.container import AppContainer
from app.nodes.common import append_trace
from app.schemas.context import TravelEstimate, WeatherContext
from app.schemas.plan import Plan
from app.schemas.task import Task
from app.services.scheduler import PlanningContext
from app.state import CampusAgentState


def make_validate_node(container: AppContainer):
    async def validate(state: CampusAgentState) -> dict:
        plan = Plan.model_validate(state["candidate_plan"])
        tasks = [Task.model_validate(raw) for raw in state["tasks"]]
        routes = [
            TravelEstimate.model_validate(raw)
            for raw in state.get("travel_estimates", [])
        ]
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
        context = PlanningContext(
            target_date=plan.date,
            timezone=ZoneInfo(state["timezone"]),
            now=datetime.fromisoformat(state["now_iso"]),
            travel={
                (route.origin_id, route.destination_id): route
                for route in routes
            },
            opening_windows=opening_windows,
            weather=[
                WeatherContext.model_validate(raw)
                for raw in state.get("weather_context", [])
            ],
            outdoor_location_ids={
                location_id
                for location_id, raw in state.get(
                    "normalized_locations", {}
                ).items()
                if raw.get("is_outdoor")
            },
            enforce_weather=(
                state["intent"] == "weather_check"
                or any(
                    raw.get("source") == "user"
                    for raw in state.get("weather_context", [])
                )
            ),
            old_plan=(
                Plan.model_validate(state["old_plan"])
                if state.get("old_plan")
                else (
                    container.plans.get(state["old_plan_id"])
                    if state.get("old_plan_id")
                    else None
                )
            ),
            initial_location_id=state.get("initial_location_id"),
            initial_departure_at=(
                datetime.fromisoformat(state["initial_departure_at"])
                if state.get("initial_departure_at")
                else None
            ),
        )
        validated, issues = container.validator.validate(
            plan=plan,
            tasks=tasks,
            context=context,
        )
        error_count = sum(issue.severity == "error" for issue in issues)
        return {
            "candidate_plan": validated.model_dump(mode="json"),
            "validation_issues": [
                issue.model_dump(mode="json") for issue in issues
            ],
            "status": "valid" if error_count == 0 else "invalid",
            "node_trace": append_trace(
                state,
                "validate",
                {
                    "error_count": error_count,
                    "issue_count": len(issues),
                    "score": validated.metrics.score,
                },
            ),
        }

    return validate
