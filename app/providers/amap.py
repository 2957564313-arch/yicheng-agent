from __future__ import annotations

import asyncio
from hashlib import sha1
import math
from datetime import date, datetime
from time import monotonic
from zoneinfo import ZoneInfo

import httpx

from app.providers.location_repository import LocationRepository
from app.schemas.common import DataSource
from app.schemas.context import (
    CampusLocation,
    SourceMetadata,
    TravelEstimate,
    WeatherContext,
)


class AmapGeocodingProvider:
    """Resolve previously unseen campus building names through AMap."""

    def __init__(
        self,
        *,
        locations: LocationRepository,
        api_key: str,
        campus_query: str,
        search_city: str,
        timeout_seconds: float = 3,
        base_url: str = "https://restapi.amap.com/v3/geocode/geo",
    ) -> None:
        self.locations = locations
        self.api_key = api_key
        self.campus_query = campus_query.strip()
        self.search_city = search_city.strip()
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._cache: dict[str, CampusLocation | None] = {}

    async def resolve(
        self,
        raw_name: str,
    ) -> CampusLocation | None:
        name = raw_name.strip()
        if not name:
            return None
        if name in self._cache:
            cached = self._cache[name]
            return cached.model_copy(deep=True) if cached else None
        address = (
            f"{self.campus_query} {name}"
            if self.campus_query and self.campus_query not in name
            else name
        )
        params = {
            "key": self.api_key,
            "address": address,
            "output": "JSON",
        }
        if self.search_city:
            params["city"] = self.search_city
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
        payload = response.json()
        geocodes = payload.get("geocodes", [])
        if payload.get("status") != "1" or not geocodes:
            self._cache[name] = None
            return None
        raw_location = geocodes[0].get("location", "")
        try:
            longitude_text, latitude_text = raw_location.split(",", 1)
            longitude = float(longitude_text)
            latitude = float(latitude_text)
        except (TypeError, ValueError):
            self._cache[name] = None
            return None
        location = CampusLocation(
            id=(
                "amap_"
                + sha1(
                    f"{address}|{raw_location}".encode("utf-8")
                ).hexdigest()[:14]
            ),
            name=name,
            aliases=[address],
            category="campus_poi",
            longitude=longitude,
            latitude=latitude,
            source=SourceMetadata(
                type="amap_geocode",
                reference=(
                    geocodes[0].get("formatted_address")
                    or address
                ),
            ),
        )
        registered = self.locations.register_runtime(location)
        self._cache[name] = registered
        return registered.model_copy(deep=True)


class AmapRouteProvider:
    """高德路径规划 2.0 步行、骑行和电动车适配器。"""

    MODE_PATHS = {
        "walk": "walking",
        "bicycle": "bicycling",
        "electrobike": "electrobike",
    }

    def __init__(
        self,
        *,
        locations: LocationRepository,
        api_key: str,
        timeout_seconds: float = 3,
        base_url: str = "https://restapi.amap.com/v5/direction/walking",
        min_request_interval_seconds: float = 0.38,
        qps_retry_count: int = 2,
    ) -> None:
        self.locations = locations
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self.min_request_interval_seconds = min_request_interval_seconds
        self.qps_retry_count = qps_retry_count
        self._cache: dict[tuple[str, str, str], TravelEstimate] = {}
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

    def _route_url(self, mode: str) -> str:
        path = self.MODE_PATHS.get(mode)
        if path is None:
            raise ValueError(f"unsupported AMap route mode: {mode}")
        for existing in self.MODE_PATHS.values():
            suffix = f"/{existing}"
            if self.base_url.rstrip("/").endswith(suffix):
                return (
                    self.base_url.rstrip("/")[: -len(suffix)]
                    + f"/{path}"
                )
        return f"https://restapi.amap.com/v5/direction/{path}"

    async def _request(
        self,
        url: str,
        params: dict[str, str],
    ) -> dict:
        payload: dict = {}
        for attempt in range(self.qps_retry_count + 1):
            async with self._request_lock:
                elapsed = monotonic() - self._last_request_at
                wait_seconds = self.min_request_interval_seconds - elapsed
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds
                ) as client:
                    response = await client.get(
                        url,
                        params=params,
                    )
                    self._last_request_at = monotonic()
                    response.raise_for_status()
                payload = response.json()
            if payload.get("info") != "CUQPS_HAS_EXCEEDED_THE_LIMIT":
                return payload
            if attempt < self.qps_retry_count:
                await asyncio.sleep(0.75 * (attempt + 1))
        return payload

    async def get_route(
        self,
        origin_id: str,
        destination_id: str,
        mode: str = "walk",
    ) -> TravelEstimate:
        cache_key = (origin_id, destination_id, mode)
        cached = self._cache.get(cache_key)
        if cached:
            return cached.model_copy(deep=True)

        origin = self.locations.get(origin_id)
        destination = self.locations.get(destination_id)
        if not origin or not destination:
            raise LookupError("unknown route endpoint")
        if None in (
            origin.longitude,
            origin.latitude,
            destination.longitude,
            destination.latitude,
        ):
            raise LookupError("route endpoint has no verified coordinates")
        params = {
            "key": self.api_key,
            "origin": f"{origin.longitude:.6f},{origin.latitude:.6f}",
            "destination": (
                f"{destination.longitude:.6f},{destination.latitude:.6f}"
            ),
            "show_fields": "cost",
        }
        if mode == "walk":
            params["alternative_route"] = "1"
        payload = await self._request(self._route_url(mode), params)
        if payload.get("status") != "1":
            raise RuntimeError(
                f"AMap route error: {payload.get('info', 'unknown')}"
            )
        paths = payload.get("route", {}).get("paths", [])
        if not paths:
            raise RuntimeError(f"AMap returned no {mode} path")
        path = paths[0]
        duration_seconds = int(
            path.get("cost", {}).get("duration")
            or path.get("duration")
            or 0
        )
        if duration_seconds <= 0:
            raise RuntimeError("AMap route has no duration")
        estimate = TravelEstimate(
            origin_id=origin_id,
            destination_id=destination_id,
            mode=mode,
            distance_m=int(path["distance"]),
            duration_min=max(1, math.ceil(duration_seconds / 60)),
            base_duration_min=max(1, math.ceil(duration_seconds / 60)),
            source=DataSource.LIVE_API,
            confidence=0.9,
            fetched_at=datetime.now(ZoneInfo("Asia/Shanghai")),
        )
        self._cache[cache_key] = estimate
        return estimate.model_copy(deep=True)

class AmapWeatherProvider:
    """高德天气预报适配器。"""

    def __init__(
        self,
        *,
        api_key: str,
        city_adcode: str,
        timeout_seconds: float = 3,
        base_url: str = "https://restapi.amap.com/v3/weather/weatherInfo",
    ) -> None:
        self.api_key = api_key
        self.city_adcode = city_adcode
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._cache: dict[
            tuple[date, str], list[WeatherContext]
        ] = {}

    async def get_forecast(
        self,
        target_date: date,
        location_id: str,
    ) -> list[WeatherContext]:
        cache_key = (target_date, location_id)
        cached = self._cache.get(cache_key)
        if cached:
            return [item.model_copy(deep=True) for item in cached]

        params = {
            "key": self.api_key,
            "city": self.city_adcode,
            "extensions": "all",
            "output": "JSON",
        }
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "1":
            raise RuntimeError(
                f"AMap weather error: {payload.get('info', 'unknown')}"
            )
        forecasts = payload.get("forecasts", [])
        casts = forecasts[0].get("casts", []) if forecasts else []
        for cast in casts:
            if cast.get("date") != target_date.isoformat():
                continue
            contexts = []
            for period, weather_key, temp_key in (
                ("day", "dayweather", "daytemp"),
                ("night", "nightweather", "nighttemp"),
            ):
                raw_temp = cast.get(temp_key)
                contexts.append(
                    WeatherContext(
                        date=target_date,
                        period=period,
                        condition=cast.get(weather_key),
                        temperature_c=(
                            float(raw_temp)
                            if raw_temp not in (None, "")
                            else None
                        ),
                        rain_probability=None,
                        source=DataSource.LIVE_API,
                        fetched_at=datetime.now(ZoneInfo("Asia/Shanghai")),
                    )
                )
            self._cache[cache_key] = contexts
            return [item.model_copy(deep=True) for item in contexts]
        unknown = [
            WeatherContext(
                date=target_date,
                period="day",
                source=DataSource.UNKNOWN,
            )
        ]
        self._cache[cache_key] = unknown
        return [item.model_copy(deep=True) for item in unknown]
