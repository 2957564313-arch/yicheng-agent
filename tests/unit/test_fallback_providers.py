from __future__ import annotations

from datetime import date

import pytest

from app.providers.fallback import RouteFallbackService, WeatherFallbackService
from app.schemas.common import DataSource
from app.schemas.context import TravelEstimate, WeatherContext


class FailingRoute:
    async def get_route(self, origin_id, destination_id, mode="walk"):
        raise TimeoutError("timeout")


class StaticRoute:
    async def get_route(self, origin_id, destination_id, mode="walk"):
        return TravelEstimate(
            origin_id=origin_id,
            destination_id=destination_id,
            duration_min=8,
            source=DataSource.STRUCTURED,
            confidence=0.9,
        )


class FailingWeather:
    async def get_forecast(self, target_date, location_id):
        raise TimeoutError("timeout")


class StaticWeather:
    async def get_forecast(self, target_date, location_id):
        return [
            WeatherContext(
                date=target_date,
                period="day",
                source=DataSource.UNKNOWN,
            )
        ]


@pytest.mark.asyncio
async def test_route_falls_back_after_live_timeout():
    service = RouteFallbackService(
        static=StaticRoute(),
        live=FailingRoute(),
    )
    result = await service.get_route(
        "a",
        "b",
        prefer_live=True,
    )
    assert result.source == DataSource.STRUCTURED
    assert "已降级" in result.warning


@pytest.mark.asyncio
async def test_weather_falls_back_after_live_timeout():
    service = WeatherFallbackService(
        static=StaticWeather(),
        live=FailingWeather(),
    )
    result = await service.get_forecast(
        date(2026, 7, 24),
        "campus",
        prefer_live=True,
    )
    assert result[0].source == DataSource.UNKNOWN

