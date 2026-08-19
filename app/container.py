from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import time
from pathlib import Path

from app.config import BASE_DIR, Settings
from app.providers.amap import (
    AmapCampusDiscoveryProvider,
    AmapGeocodingProvider,
    AmapRouteProvider,
    AmapWeatherProvider,
)
from app.providers.campus_rules import CampusRulesRepository
from app.providers.fallback import RouteFallbackService, WeatherFallbackService
from app.providers.hduhelp import HduHelpClient
from app.providers.location_repository import LocationRepository
from app.providers.rag import KnowledgeRepository
from app.providers.route_static import StaticRouteProvider
from app.providers.weather_static import StaticWeatherProvider
from app.repositories.academic_calendar import AcademicCalendarRepository
from app.repositories.accounts import AccountRepository
from app.repositories.agenda_edits import AgendaEditRepository
from app.repositories.connections import ExternalConnectionRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.database import Database
from app.repositories.external_agenda import ExternalAgendaRepository
from app.repositories.external_data import ExternalDataRepository
from app.repositories.memories import MemoryRepository
from app.repositories.plans import PlanRepository
from app.repositories.reminders import ReminderSettingsRepository
from app.repositories.runs import RunRepository
from app.repositories.timetables import TimetableRepository
from app.repositories.weekly import WeeklyPlanRepository
from app.services.agenda import AgendaService
from app.services.credentials import CredentialCipher
from app.services.llm import OpenAICompatibleLLM
from app.services.replanner import Replanner
from app.services.requirement_parser import RuleBasedRequirementParser
from app.services.scheduler import Scheduler
from app.services.validator import PlanValidator
from app.services.weekly_allocator import WeeklyAllocator
from app.services.weekly_capacity import WeeklyCapacityBuilder
from app.services.weekly_grounding import WeeklyGroundingService
from app.services.weekly_replanner import WeeklyReplanner


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    campus_profile: dict
    database: Database
    accounts: AccountRepository
    conversations: ConversationRepository
    external_connections: ExternalConnectionRepository
    external_agenda: ExternalAgendaRepository
    agenda_edits: AgendaEditRepository
    external_data: ExternalDataRepository
    credential_cipher: CredentialCipher
    hduhelp: HduHelpClient
    plans: PlanRepository
    reminders: ReminderSettingsRepository
    memories: MemoryRepository
    timetables: TimetableRepository
    academic_calendar: AcademicCalendarRepository
    weekly_plans: WeeklyPlanRepository
    runs: RunRepository
    locations: LocationRepository
    geocoder: AmapGeocodingProvider | None
    campus_discovery: AmapCampusDiscoveryProvider | None
    routes: RouteFallbackService
    weather: WeatherFallbackService
    rules: CampusRulesRepository
    rag: KnowledgeRepository
    scheduler: Scheduler
    replanner: Replanner
    validator: PlanValidator
    weekly_allocator: WeeklyAllocator
    weekly_capacity: WeeklyCapacityBuilder
    weekly_grounding: WeeklyGroundingService
    weekly_replanner: WeeklyReplanner
    agenda: AgendaService
    parser: RuleBasedRequirementParser
    llm: OpenAICompatibleLLM


def _load_campus_profile(data_dir: Path) -> dict:
    profile_path = data_dir / "campus_profile.json"
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _profile_amap_settings(profile: dict) -> dict[str, str]:
    """Read non-secret AMap settings from the active campus profile."""
    raw = profile.get("external_services", {}).get("amap", {})
    return {
        key: str(raw.get(key, "")).strip()
        for key in ("weather_adcode", "search_city", "campus_query")
    }


def _load_class_periods(
    path: Path,
) -> dict[int, tuple[time, time]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        int(item["period"]): (
            time.fromisoformat(item["start"]),
            time.fromisoformat(item["end"]),
        )
        for item in payload.get("class_periods", [])
    }


def build_container(settings: Settings) -> AppContainer:
    database = Database(settings.app_database_path)
    database.initialize()
    accounts = AccountRepository(database)
    conversations = ConversationRepository(database)
    external_connections = ExternalConnectionRepository(database)
    external_agenda = ExternalAgendaRepository(database)
    agenda_edits = AgendaEditRepository(database)
    external_data = ExternalDataRepository(database)
    credential_cipher = CredentialCipher(settings.credential_secret)
    hduhelp = HduHelpClient(
        base_url=settings.hduhelp_api_base_url,
        timeout_seconds=settings.hduhelp_timeout_seconds,
    )
    locations = LocationRepository(settings.app_data_dir / "locations.json")
    campus_profile = _load_campus_profile(settings.app_data_dir)
    amap_profile = _profile_amap_settings(campus_profile)
    scheduler = Scheduler()
    validator = PlanValidator()
    weekly_allocator = WeeklyAllocator()
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
    timetables = TimetableRepository(database)
    academic_calendar = AcademicCalendarRepository(
        database,
        settings.app_data_dir / "academic_calendar.json",
    )
    memories = MemoryRepository(database)
    plans = PlanRepository(database)
    reminders = ReminderSettingsRepository(database)
    class_periods = _load_class_periods(settings.app_data_dir / "class_periods.json")
    weather_city_adcode = settings.weather_city_adcode or amap_profile.get(
        "weather_adcode", ""
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
    agenda = AgendaService(
        plans=plans,
        timetables=timetables,
        external_agenda=external_agenda,
        agenda_edits=agenda_edits,
        academic_calendar=academic_calendar,
        memories=memories,
        locations=locations,
        class_periods=class_periods,
        timezone_name=settings.app_timezone,
    )
    weekly_plans = WeeklyPlanRepository(database)
    weekly_capacity = WeeklyCapacityBuilder(
        timetables=timetables,
        memories=memories,
        academic_calendar=academic_calendar,
        class_periods=class_periods,
    )
    weekly_grounding = WeeklyGroundingService(
        settings=settings,
        campus_profile=campus_profile,
        plans=plans,
        weekly_plans=weekly_plans,
        timetables=timetables,
        academic_calendar=academic_calendar,
        locations=locations,
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
        scheduler=scheduler,
        validator=validator,
        class_periods=class_periods,
    )
    return AppContainer(
        settings=settings,
        campus_profile=campus_profile,
        database=database,
        accounts=accounts,
        conversations=conversations,
        external_connections=external_connections,
        external_agenda=external_agenda,
        agenda_edits=agenda_edits,
        external_data=external_data,
        credential_cipher=credential_cipher,
        hduhelp=hduhelp,
        plans=plans,
        reminders=reminders,
        memories=memories,
        timetables=timetables,
        academic_calendar=academic_calendar,
        weekly_plans=weekly_plans,
        runs=RunRepository(database),
        locations=locations,
        geocoder=geocoder,
        campus_discovery=(
            AmapCampusDiscoveryProvider(
                locations=locations,
                api_key=settings.route_api_key,
                timeout_seconds=max(
                    settings.route_timeout_seconds,
                    6,
                ),
            )
            if settings.live_route_enabled and settings.route_api_key
            else None
        ),
        routes=weekly_grounding.routes,
        weather=weekly_grounding.weather,
        rules=weekly_grounding.rules,
        rag=KnowledgeRepository(settings.app_data_dir / "knowledge"),
        scheduler=scheduler,
        replanner=Replanner(scheduler),
        validator=validator,
        weekly_allocator=weekly_allocator,
        weekly_capacity=weekly_capacity,
        weekly_grounding=weekly_grounding,
        weekly_replanner=WeeklyReplanner(weekly_allocator),
        agenda=agenda,
        parser=RuleBasedRequirementParser(
            settings.app_timezone,
            settings.app_data_dir / "class_periods.json",
        ),
        llm=OpenAICompatibleLLM(
            enabled=settings.llm_enabled,
            model=settings.llm_model,
            fallback_models=settings.llm_models[1:],
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            enable_thinking=settings.llm_enable_thinking,
            timeout_seconds=settings.llm_timeout_seconds,
            prompt_dir=BASE_DIR / "prompts",
            campus_context_path=(settings.app_data_dir / "class_periods.json"),
        ),
    )
