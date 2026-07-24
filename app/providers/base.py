from __future__ import annotations

from datetime import date
from typing import Protocol

from app.schemas.context import (
    CampusLocation,
    RetrievedFact,
    TravelEstimate,
    WeatherContext,
)


class LocationProvider(Protocol):
    def resolve(self, raw_name: str | None) -> CampusLocation | None: ...


class RouteProvider(Protocol):
    async def get_route(
        self,
        origin_id: str,
        destination_id: str,
        mode: str = "walk",
    ) -> TravelEstimate: ...


class WeatherProvider(Protocol):
    async def get_forecast(
        self,
        target_date: date,
        location_id: str,
    ) -> list[WeatherContext]: ...


class RagProvider(Protocol):
    async def retrieve(
        self,
        queries: list[str],
        *,
        top_k: int = 3,
    ) -> list[RetrievedFact]: ...

