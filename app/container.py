from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from app.config import BASE_DIR, Settings
from app.providers.campus_rules import CampusRulesRepository
from app.providers.amap import (
    AmapGeocodingProvider,
    AmapRouteProvider,
    AmapWeatherProvider,
)
from app.providers.fallback import RouteFallbackService, WeatherFallbackService
from app.providers.location_repository import LocationRepository
from app.providers.rag import KnowledgeRepository
from app.providers.route_static import StaticRouteProvider
from app.providers.weather_static import StaticWeatherProvider
from app.repositories.database import Database
from app.repositories.memories import MemoryRepository
from app.repositories.plans import PlanRepository
from app.repositories.runs import RunRepository
from app.repositories.timetables import TimetableRepository
from app.services.llm import OpenAICompatibleLLM
from app.services.replanner import Replanner
from app.services.requirement_parser import RuleBasedRequirementParser
from app.services.scheduler import Scheduler
from app.services.validator import PlanValidator


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    database: Database
    plans: PlanRepository
    memories: MemoryRepository
    timetables: TimetableRepository
    runs: RunRepository
    locations: LocationRepository
    geocoder: AmapGeocodingProvider | None
    routes: RouteFallbackService
    weather: WeatherFallbackService
    rules: CampusRulesRepository
    rag: KnowledgeRepository
    scheduler: Scheduler
    replanner: Replanner
    validator: PlanValidator
    parser: RuleBasedRequirementParser
    llm: OpenAICompatibleLLM


def _profile_amap_settings(data_dir: Path) -> dict[str, str]:
    """Read non-secret AMap settings from the active campus profile."""
    profile_path = data_dir / "campus_profile.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    raw = (
        profile.get("external_services", {})
        .get("amap", {})
    )
    return {
        key: str(raw.get(key, "")).strip()
        for key in ("weather_adcode", "search_city", "campus_query")
    }


def build_container(settings: Settings) -> AppContainer:
    database = Database(settings.app_database_path)
    database.initialize()
    locations = LocationRepository(settings.app_data_dir / "locations.json")
    amap_profile = _profile_amap_settings(settings.app_data_dir)
    scheduler = Scheduler()
    static_routes = StaticRouteProvider(
        settings.app_data_dir / "travel_times.json",
        locations,
    )
    live_routes = (
        AmapRouteProvider(
            locations=locations,
            api_key=settings.route_api_key,
            timeout_seconds=settings.route_timeout_seconds,
            base_url=(
                settings.route_api_base_url
                or "https://restapi.amap.com/v5/direction/walking"
            ),
        )
        if settings.live_route_enabled and settings.route_api_key
        else None
    )
    static_weather = StaticWeatherProvider(
        settings.app_data_dir / "weather_fallback.json"
    )
    weather_city_adcode = (
        settings.weather_city_adcode
        or amap_profile.get("weather_adcode", "")
    )
    geocoder = (
        AmapGeocodingProvider(
            locations=locations,
            api_key=settings.route_api_key,
            campus_query=amap_profile.get("campus_query", ""),
            search_city=amap_profile.get("search_city", ""),
            timeout_seconds=settings.route_timeout_seconds,
        )
        if settings.live_route_enabled and settings.route_api_key
        else None
    )
    live_weather = (
        AmapWeatherProvider(
            api_key=settings.weather_api_key,
            city_adcode=weather_city_adcode,
            timeout_seconds=settings.weather_timeout_seconds,
            base_url=(
                settings.weather_api_base_url
                or "https://restapi.amap.com/v3/weather/weatherInfo"
            ),
        )
        if (
            settings.live_weather_enabled
            and settings.weather_api_key
            and weather_city_adcode
        )
        else None
    )
    return AppContainer(
        settings=settings,
        database=database,
        plans=PlanRepository(database),
        memories=MemoryRepository(database),
        timetables=TimetableRepository(database),
        runs=RunRepository(database),
        locations=locations,
        geocoder=geocoder,
        routes=RouteFallbackService(
            static=static_routes,
            live=live_routes,
        ),
        weather=WeatherFallbackService(
            static=static_weather,
            live=live_weather,
        ),
        rules=CampusRulesRepository(
            settings.app_data_dir / "opening_hours.json",
            settings.app_data_dir / "campus_rules.json",
            settings.app_data_dir / "class_periods.json",
            settings.app_timezone,
        ),
        rag=KnowledgeRepository(settings.app_data_dir / "knowledge"),
        scheduler=scheduler,
        replanner=Replanner(scheduler),
        validator=PlanValidator(),
        parser=RuleBasedRequirementParser(
            settings.app_timezone,
            settings.app_data_dir / "class_periods.json",
        ),
        llm=OpenAICompatibleLLM(
            enabled=settings.llm_enabled,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            enable_thinking=settings.llm_enable_thinking,
            timeout_seconds=settings.llm_timeout_seconds,
            prompt_dir=BASE_DIR / "prompts",
            campus_context_path=(
                settings.app_data_dir / "class_periods.json"
            ),
        ),
    )
