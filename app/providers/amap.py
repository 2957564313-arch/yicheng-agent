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
from app.schemas.campus import CampusDiscoveryResponse, CampusSelection
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
        place_url: str = "https://restapi.amap.com/v3/place/text",
    ) -> None:
        self.locations = locations
        self.api_key = api_key
        self.campus_query = campus_query.strip()
        self.search_city = search_city.strip()
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self.place_url = place_url
        self._cache: dict[
            tuple[str, str, str],
            CampusLocation | None,
        ] = {}

    async def resolve(
        self,
        raw_name: str,
        *,
        campus_id: str | None = None,
        campus_query: str | None = None,
        search_city: str | None = None,
    ) -> CampusLocation | None:
        name = raw_name.strip()
        if not name:
            return None
        active_campus_id = campus_id or self.locations.campus_id
        active_campus_query = (
            self.campus_query
            if campus_query is None
            else campus_query.strip()
        )
        active_search_city = (
            self.search_city
            if search_city is None
            else search_city.strip()
        )
        cache_key = (active_campus_id, active_campus_query, name)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return cached.model_copy(deep=True) if cached else None
        address = (
            f"{active_campus_query} {name}"
            if active_campus_query and active_campus_query not in name
            else name
        )
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:
            place_params = {
                "key": self.api_key,
                "keywords": address,
                "citylimit": "true",
                "offset": "10",
                "page": "1",
                "extensions": "base",
                "output": "JSON",
            }
            if active_search_city:
                place_params["city"] = active_search_city
            place_response = await client.get(
                self.place_url,
                params=place_params,
            )
            place_response.raise_for_status()
            place_payload = place_response.json()
            pois = (
                place_payload.get("pois", [])
                if place_payload.get("status") == "1"
                else []
            )

            if pois:
                result = pois[0]
                source_type = "amap_poi"
                reference = " ".join(
                    str(value).strip()
                    for value in (
                        result.get("name"),
                        result.get("address"),
                    )
                    if value
                ) or address
            else:
                geocode_params = {
                    "key": self.api_key,
                    "address": address,
                    "output": "JSON",
                }
                if active_search_city:
                    geocode_params["city"] = active_search_city
                geocode_response = await client.get(
                    self.base_url,
                    params=geocode_params,
                )
                geocode_response.raise_for_status()
                geocode_payload = geocode_response.json()
                geocodes = (
                    geocode_payload.get("geocodes", [])
                    if geocode_payload.get("status") == "1"
                    else []
                )
                if not geocodes:
                    self._cache[cache_key] = None
                    return None
                result = geocodes[0]
                source_type = "amap_geocode"
                reference = (
                    result.get("formatted_address")
                    or address
                )

        raw_location = result.get("location", "")
        try:
            longitude_text, latitude_text = raw_location.split(",", 1)
            longitude = float(longitude_text)
            latitude = float(latitude_text)
        except (TypeError, ValueError):
            self._cache[cache_key] = None
            return None
        location = CampusLocation(
            id=(
                "amap_"
                + sha1(
                    f"{address}|{raw_location}".encode("utf-8")
                ).hexdigest()[:14]
            ),
            campus_id=active_campus_id,
            name=name,
            aliases=list(
                dict.fromkeys(
                    value
                    for value in (
                        address,
                        str(result.get("name", "")).strip(),
                    )
                    if value and value != name
                )
            ),
            category="campus_poi",
            longitude=longitude,
            latitude=latitude,
            source=SourceMetadata(
                type=source_type,
                reference=reference,
            ),
        )
        registered = self.locations.register_runtime(location)
        self._cache[cache_key] = registered
        return registered.model_copy(deep=True)


class AmapCampusDiscoveryProvider:
    """Build a campus-scoped POI directory from AMap search results."""

    CATEGORY_KEYWORDS = {
        "teaching": "教学楼|实验楼|实训楼",
        "study": "图书馆|自习室",
        "food": "食堂|餐厅",
        "residential": "宿舍|学生公寓",
        "sports": "操场|田径场|体育馆",
        "service": "快递|驿站|校医院|学生活动中心",
    }

    def __init__(
        self,
        *,
        locations: LocationRepository,
        api_key: str,
        timeout_seconds: float = 6,
        text_url: str = "https://restapi.amap.com/v5/place/text",
        around_url: str = "https://restapi.amap.com/v5/place/around",
    ) -> None:
        self.locations = locations
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.text_url = text_url
        self.around_url = around_url

    async def discover(
        self,
        *,
        school_name: str,
        city: str = "",
        radius_m: int = 1800,
    ) -> CampusDiscoveryResponse:
        school_payload = await self._get(
            self.text_url,
            {
                "key": self.api_key,
                "keywords": school_name,
                "region": city,
                "city_limit": "true" if city else "false",
                "show_fields": "navi",
                "page_size": "10",
                "page_num": "1",
            },
        )
        school_pois = school_payload.get("pois", [])
        if school_payload.get("status") != "1" or not school_pois:
            raise LookupError("未在高德找到这所学校或校区")
        school_poi = max(
            school_pois,
            key=lambda poi: self._school_match_score(
                school_name,
                str(poi.get("name", "")),
            ),
        )
        longitude, latitude = self._poi_coordinates(school_poi)
        campus_id = (
            "amap_campus_"
            + sha1(
                f"{school_name}|{longitude:.6f}|{latitude:.6f}".encode(
                    "utf-8"
                )
            ).hexdigest()[:14]
        )
        weather_adcode = str(school_poi.get("adcode", "")).strip()
        discovered: dict[str, CampusLocation] = {}
        failed_categories: list[str] = []
        campus_location = self._campus_location(
            campus_id=campus_id,
            school_name=school_name,
            poi=school_poi,
            longitude=longitude,
            latitude=latitude,
        )
        discovered[campus_location.id] = campus_location

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            try:
                payload = await self._get(
                    self.around_url,
                    {
                        "key": self.api_key,
                        "location": f"{longitude:.6f},{latitude:.6f}",
                        "keywords": keywords,
                        "radius": str(radius_m),
                        "sortrule": "distance",
                        "region": city,
                        "city_limit": "true" if city else "false",
                        "show_fields": "navi",
                        "page_size": "25",
                        "page_num": "1",
                    },
                )
            except (httpx.HTTPError, RuntimeError, ValueError):
                failed_categories.append(category)
                continue
            if payload.get("status") != "1":
                failed_categories.append(category)
                continue
            for poi in payload.get("pois", []):
                try:
                    location = self._poi_location(
                        campus_id=campus_id,
                        poi=poi,
                        category=category,
                        center=(longitude, latitude),
                        radius_m=radius_m,
                    )
                except (TypeError, ValueError):
                    continue
                if location is not None:
                    discovered[location.id] = location

        registered = [
            self.locations.register_runtime(location)
            for location in discovered.values()
        ]
        return CampusDiscoveryResponse(
            campus=CampusSelection(
                campus_id=campus_id,
                display_name=school_name,
                search_city=city,
                weather_adcode=weather_adcode,
                longitude=longitude,
                latitude=latitude,
                locations=registered,
            ),
            searched_categories=list(self.CATEGORY_KEYWORDS),
            coverage_note=(
                "已按教学、学习、餐饮、住宿、运动和生活服务分类检索"
                "首批高德地点。"
                + (
                    "本次有部分分类暂时未返回，用户实际提及地点时会"
                    "继续实时补查。"
                    if failed_categories
                    else ""
                )
                + "高德没有“校内全部建筑”单一接口；"
                "未收录地点会在用户实际提及时继续实时搜索。"
            ),
        )

    async def _get(self, url: str, params: dict[str, str]) -> dict:
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds
        ) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
        payload = response.json()
        if payload.get("status") != "1":
            raise RuntimeError(
                f"AMap place error: {payload.get('info', 'unknown')}"
            )
        return payload

    @staticmethod
    def _school_match_score(expected: str, actual: str) -> tuple[int, int]:
        compact_expected = "".join(expected.split())
        compact_actual = "".join(actual.split())
        return (
            int(compact_expected == compact_actual) * 4
            + int(
                compact_expected in compact_actual
                or compact_actual in compact_expected
            )
            * 2,
            -abs(len(compact_expected) - len(compact_actual)),
        )

    @staticmethod
    def _poi_coordinates(poi: dict) -> tuple[float, float]:
        raw = (
            poi.get("navi", {}).get("entr_location")
            if isinstance(poi.get("navi"), dict)
            else None
        ) or poi.get("location", "")
        longitude_text, latitude_text = str(raw).split(",", 1)
        return float(longitude_text), float(latitude_text)

    @classmethod
    def _campus_location(
        cls,
        *,
        campus_id: str,
        school_name: str,
        poi: dict,
        longitude: float,
        latitude: float,
    ) -> CampusLocation:
        poi_id = str(poi.get("id", "")).strip()
        return CampusLocation(
            id=(
                f"amap_{poi_id}"
                if poi_id
                else f"{campus_id}_center"
            ),
            campus_id=campus_id,
            name=str(poi.get("name") or school_name).strip(),
            aliases=list(
                dict.fromkeys(
                    value
                    for value in (
                        school_name,
                        "学校",
                        "校门",
                    )
                    if value
                )
            ),
            category="campus",
            longitude=longitude,
            latitude=latitude,
            source=SourceMetadata(
                type="amap_poi",
                reference=poi_id or school_name,
            ),
        )

    @classmethod
    def _poi_location(
        cls,
        *,
        campus_id: str,
        poi: dict,
        category: str,
        center: tuple[float, float],
        radius_m: int,
    ) -> CampusLocation | None:
        longitude, latitude = cls._poi_coordinates(poi)
        if (
            cls._distance_m(center, (longitude, latitude))
            > radius_m * 1.15
        ):
            return None
        name = str(poi.get("name", "")).strip()
        if not name:
            return None
        poi_id = str(poi.get("id", "")).strip()
        location_id = (
            f"amap_{poi_id}"
            if poi_id
            else (
                "amap_"
                + sha1(
                    f"{campus_id}|{name}|{longitude}|{latitude}".encode(
                        "utf-8"
                    )
                ).hexdigest()[:14]
            )
        )
        return CampusLocation(
            id=location_id,
            campus_id=campus_id,
            name=name,
            aliases=[],
            category=category,
            longitude=longitude,
            latitude=latitude,
            is_outdoor=(
                category == "sports"
                and any(
                    word in name
                    for word in ("操场", "田径场", "球场", "跑道")
                )
            ),
            source=SourceMetadata(
                type="amap_poi",
                reference=poi_id or name,
            ),
        )

    @staticmethod
    def _distance_m(
        left: tuple[float, float],
        right: tuple[float, float],
    ) -> float:
        longitude_delta = math.radians(right[0] - left[0])
        latitude_delta = math.radians(right[1] - left[1])
        latitude_mean = math.radians((left[1] + right[1]) / 2)
        x = longitude_delta * math.cos(latitude_mean)
        return math.hypot(x, latitude_delta) * 6_371_000


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
        if origin.campus_id != destination.campus_id:
            raise LookupError("route endpoints belong to different campuses")
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
        *,
        city_adcode: str | None = None,
    ) -> list[WeatherContext]:
        active_adcode = (city_adcode or self.city_adcode).strip()
        if not active_adcode:
            return [
                WeatherContext(
                    date=target_date,
                    period="day",
                    source=DataSource.UNKNOWN,
                )
            ]
        cache_key = (target_date, f"{location_id}:{active_adcode}")
        cached = self._cache.get(cache_key)
        if cached:
            return [item.model_copy(deep=True) for item in cached]

        params = {
            "key": self.api_key,
            "city": active_adcode,
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
