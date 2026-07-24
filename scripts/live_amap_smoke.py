from __future__ import annotations

import asyncio
import json
from datetime import date

from app.config import get_settings
from app.container import _profile_weather_adcode
from app.providers.amap import AmapRouteProvider, AmapWeatherProvider
from app.providers.location_repository import LocationRepository


async def main() -> None:
    settings = get_settings()
    if not settings.route_api_key or not settings.weather_api_key:
        raise RuntimeError("高德 Key 尚未配置")

    locations = LocationRepository(settings.app_data_dir / "locations.json")
    adcode = (
        settings.weather_city_adcode
        or _profile_weather_adcode(settings.app_data_dir)
    )
    if not adcode:
        raise RuntimeError("天气城市编码尚未配置")

    route_provider = AmapRouteProvider(
        locations=locations,
        api_key=settings.route_api_key,
        timeout_seconds=settings.route_timeout_seconds,
        base_url=(
            settings.route_api_base_url
            or "https://restapi.amap.com/v5/direction/walking"
        ),
    )
    weather_provider = AmapWeatherProvider(
        api_key=settings.weather_api_key,
        city_adcode=adcode,
        timeout_seconds=settings.weather_timeout_seconds,
        base_url=(
            settings.weather_api_base_url
            or "https://restapi.amap.com/v3/weather/weatherInfo"
        ),
    )

    route_cases = [
        ("teaching_building_6", "library", "walk"),
        ("library", "parcel_station", "walk"),
        ("library", "canteen", "walk"),
        ("parcel_station", "canteen", "walk"),
        ("canteen", "track", "walk"),
        ("library", "track", "bicycle"),
        ("parcel_station", "track", "electrobike"),
    ]
    routes = [
        await route_provider.get_route(
            origin_id,
            destination_id,
            mode=mode,
        )
        for origin_id, destination_id, mode in route_cases
    ]
    weather = await weather_provider.get_forecast(
        date.today(),
        "campus_main",
    )
    print(
        json.dumps(
            {
                "routes": [
                    {
                        "origin_id": route.origin_id,
                        "destination_id": route.destination_id,
                        "mode": route.mode,
                        "distance_m": route.distance_m,
                        "duration_min": route.duration_min,
                        "source": route.source.value,
                    }
                    for route in routes
                ],
                "weather": [
                    {
                        "date": item.date.isoformat(),
                        "period": item.period,
                        "condition": item.condition,
                        "temperature_c": item.temperature_c,
                        "source": item.source.value,
                    }
                    for item in weather
                ],
                "adcode": adcode,
                "secrets_printed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
