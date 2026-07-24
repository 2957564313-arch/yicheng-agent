import json
import re

from app.config import get_settings
from app.providers.rag import KnowledgeRepository
from app.providers.campus_rules import CampusRulesRepository
from app.providers.location_repository import LocationRepository
from app.providers.route_static import StaticRouteProvider


def main() -> None:
    settings = get_settings()
    profile_path = settings.app_data_dir / "campus_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    weather_adcode = str(
        profile.get("external_services", {})
        .get("amap", {})
        .get("weather_adcode", "")
    )
    if weather_adcode and not re.fullmatch(r"\d{6}", weather_adcode):
        raise ValueError("campus profile weather_adcode must be 6 digits")
    missing = [
        required
        for required in profile.get("required_files", [])
        if not (settings.app_data_dir / required).exists()
    ]
    if missing:
        raise ValueError(
            "campus profile is missing required entries: "
            + ", ".join(missing)
        )
    locations = LocationRepository(settings.app_data_dir / "locations.json")
    StaticRouteProvider(
        settings.app_data_dir / "travel_times.json",
        locations,
    )
    CampusRulesRepository(
        settings.app_data_dir / "opening_hours.json",
        settings.app_data_dir / "campus_rules.json",
        settings.app_data_dir / "class_periods.json",
        settings.app_timezone,
    )
    class_periods = json.loads(
        (settings.app_data_dir / "class_periods.json").read_text(
            encoding="utf-8"
        )
    )
    periods = class_periods.get("class_periods", [])
    if [item.get("period") for item in periods] != list(range(1, 14)):
        raise ValueError("class periods must contain ordered periods 1-13")
    knowledge = KnowledgeRepository(settings.app_data_dir / "knowledge")
    if knowledge.chunk_count == 0:
        raise ValueError("campus profile knowledge base is empty")
    print(
        f"validated profile={profile['profile_id']}; "
        f"locations={len(locations.all())}; "
        f"knowledge_chunks={knowledge.chunk_count}; "
        f"data_quality={locations.data_quality}"
    )


if __name__ == "__main__":
    main()
