from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.providers.amap import AmapRouteProvider, AmapWeatherProvider
from app.providers.location_repository import LocationRepository
from app.schemas.common import DataSource


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeAsyncClient:
    payload: dict = {}
    calls: list[tuple[str, dict]] = []

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, url: str, *, params: dict) -> FakeResponse:
        self.calls.append((url, params))
        return FakeResponse(self.payload)


class SequencedFakeAsyncClient(FakeAsyncClient):
    payloads: list[dict] = []

    async def get(self, url: str, *, params: dict) -> FakeResponse:
        self.calls.append((url, params))
        return FakeResponse(self.payloads.pop(0))


def build_locations(tmp_path: Path, *, with_coordinates: bool = True):
    path = tmp_path / "locations.json"
    coordinates = (
        {
            "a": [120.1234567, 30.1234567],
            "b": [120.2234567, 30.2234567],
        }
        if with_coordinates
        else {"a": [None, None], "b": [None, None]}
    )
    payload = {
        "schema_version": "1.0",
        "campus_id": "test",
        "data_quality": "verified",
        "locations": [
            {
                "id": location_id,
                "name": location_id,
                "aliases": [],
                "category": "test",
                "longitude": values[0],
                "latitude": values[1],
                "source": {
                    "type": "test",
                    "reference": "fixture",
                    "verified_at": "2026-07-23",
                },
            }
            for location_id, values in coordinates.items()
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return LocationRepository(path)


@pytest.mark.asyncio
async def test_amap_route_request_and_response(monkeypatch, tmp_path: Path):
    fake = type("RouteClient", (FakeAsyncClient,), {})
    fake.payload = {
        "status": "1",
        "route": {
            "paths": [
                {
                    "distance": "860",
                    "cost": {"duration": "730"},
                }
            ]
        },
    }
    fake.calls = []
    monkeypatch.setattr("app.providers.amap.httpx.AsyncClient", fake)
    provider = AmapRouteProvider(
        locations=build_locations(tmp_path),
        api_key="test-key",
    )

    result = await provider.get_route("a", "b")

    assert result.source == DataSource.LIVE_API
    assert result.distance_m == 860
    assert result.duration_min == 13
    url, params = fake.calls[0]
    assert url.endswith("/v5/direction/walking")
    assert params == {
        "key": "test-key",
        "origin": "120.123457,30.123457",
        "destination": "120.223457,30.223457",
        "show_fields": "cost",
        "alternative_route": "1",
    }
    second = await provider.get_route("a", "b")
    assert second.duration_min == 13
    assert len(fake.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "endpoint"),
    [
        ("bicycle", "/v5/direction/bicycling"),
        ("electrobike", "/v5/direction/electrobike"),
    ],
)
async def test_amap_route_uses_requested_non_motor_mode(
    monkeypatch,
    tmp_path: Path,
    mode: str,
    endpoint: str,
):
    fake = type(f"RouteClient_{mode}", (FakeAsyncClient,), {})
    fake.payload = {
        "status": "1",
        "route": {
            "paths": [
                {
                    "distance": "860",
                    "cost": {"duration": "240"},
                }
            ]
        },
    }
    fake.calls = []
    monkeypatch.setattr("app.providers.amap.httpx.AsyncClient", fake)
    provider = AmapRouteProvider(
        locations=build_locations(tmp_path),
        api_key="test-key",
    )

    result = await provider.get_route("a", "b", mode=mode)

    assert result.mode == mode
    assert result.duration_min == 4
    assert result.base_duration_min == 4
    url, params = fake.calls[0]
    assert url.endswith(endpoint)
    assert "alternative_route" not in params


@pytest.mark.asyncio
async def test_amap_route_requires_verified_coordinates(tmp_path: Path):
    provider = AmapRouteProvider(
        locations=build_locations(tmp_path, with_coordinates=False),
        api_key="test-key",
    )
    with pytest.raises(LookupError, match="verified coordinates"):
        await provider.get_route("a", "b")


@pytest.mark.asyncio
async def test_amap_route_retries_after_qps_limit(monkeypatch, tmp_path: Path):
    fake = type("RouteRetryClient", (SequencedFakeAsyncClient,), {})
    fake.payloads = [
        {
            "status": "0",
            "info": "CUQPS_HAS_EXCEEDED_THE_LIMIT",
        },
        {
            "status": "1",
            "route": {
                "paths": [
                    {
                        "distance": "500",
                        "cost": {"duration": "300"},
                    }
                ]
            },
        },
    ]
    fake.calls = []

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.providers.amap.httpx.AsyncClient", fake)
    monkeypatch.setattr("app.providers.amap.asyncio.sleep", no_sleep)
    provider = AmapRouteProvider(
        locations=build_locations(tmp_path),
        api_key="test-key",
        min_request_interval_seconds=0,
        qps_retry_count=1,
    )

    result = await provider.get_route("a", "b")

    assert result.duration_min == 5
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_amap_weather_request_and_response(monkeypatch):
    fake = type("WeatherClient", (FakeAsyncClient,), {})
    fake.payload = {
        "status": "1",
        "forecasts": [
            {
                "casts": [
                    {
                        "date": "2026-07-24",
                        "dayweather": "多云",
                        "daytemp": "31",
                        "nightweather": "小雨",
                        "nighttemp": "26",
                    }
                ]
            }
        ],
    }
    fake.calls = []
    monkeypatch.setattr("app.providers.amap.httpx.AsyncClient", fake)
    provider = AmapWeatherProvider(
        api_key="test-key",
        city_adcode="330114",
    )

    result = await provider.get_forecast(
        date(2026, 7, 24),
        "campus_main",
    )

    assert [item.period for item in result] == ["day", "night"]
    assert [item.temperature_c for item in result] == [31.0, 26.0]
    assert all(item.source == DataSource.LIVE_API for item in result)
    url, params = fake.calls[0]
    assert url.endswith("/v3/weather/weatherInfo")
    assert params == {
        "key": "test-key",
        "city": "330114",
        "extensions": "all",
        "output": "JSON",
    }
    second = await provider.get_forecast(
        date(2026, 7, 24),
        "campus_main",
    )
    assert len(second) == 2
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_amap_weather_returns_unknown_for_missing_date(monkeypatch):
    fake = type("WeatherClientMissingDate", (FakeAsyncClient,), {})
    fake.payload = {
        "status": "1",
        "forecasts": [{"casts": [{"date": "2026-07-25"}]}],
    }
    fake.calls = []
    monkeypatch.setattr("app.providers.amap.httpx.AsyncClient", fake)
    provider = AmapWeatherProvider(
        api_key="test-key",
        city_adcode="330114",
    )

    result = await provider.get_forecast(
        date(2026, 7, 24),
        "campus_main",
    )

    assert len(result) == 1
    assert result[0].source == DataSource.UNKNOWN
