from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.providers.campus_rules import CampusRulesRepository
from app.providers.location_repository import LocationRepository
from app.providers.route_static import StaticRouteProvider
from app.services.scheduler import PlanningContext

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
TARGET = date(2026, 8, 21)
TZ = ZoneInfo("Asia/Shanghai")


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 21, hour, minute, tzinfo=TZ)


@pytest.fixture
def target_date() -> date:
    return TARGET


@pytest.fixture
def shanghai() -> ZoneInfo:
    return TZ


@pytest.fixture
async def context_factory():
    """Build a planning context with the real campus data behind it."""

    locations = LocationRepository(DATA_DIR / "locations.json")
    routes = StaticRouteProvider(DATA_DIR / "travel_times.json", locations)
    rules = CampusRulesRepository(
        DATA_DIR / "opening_hours.json",
        DATA_DIR / "campus_rules.json",
        DATA_DIR / "class_periods.json",
        "Asia/Shanghai",
    )

    async def build(location_ids: tuple[str, ...], *, now_hour: int = 9):
        travel = {}
        for origin in location_ids:
            for destination in location_ids:
                if origin == destination:
                    continue
                try:
                    travel[(origin, destination)] = await routes.get_route(
                        origin,
                        destination,
                    )
                except LookupError:
                    continue
        # Only venues with a real rule constrain the day; this mirrors what
        # the enrich node passes in production.
        opening = {
            location_id: rules.opening_windows(location_id, TARGET)
            for location_id in location_ids
            if rules.has_applicable_opening_rule(location_id, TARGET)
        }
        return PlanningContext(
            target_date=TARGET,
            timezone=TZ,
            now=at(now_hour),
            travel=travel,
            opening_windows=opening,
        )

    return build
