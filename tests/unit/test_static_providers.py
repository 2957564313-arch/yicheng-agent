from pathlib import Path

import pytest

from app.providers.location_repository import LocationRepository
from app.providers.route_static import StaticRouteProvider
from app.schemas.common import DataSource


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_location_alias_resolution():
    repository = LocationRepository(DATA_DIR / "locations.json")
    assert repository.resolve("六教").id == "teaching_building_6"
    assert repository.resolve(" 菜鸟驿站 ").id == "parcel_station"
    assert repository.resolve("不存在的地点") is None


@pytest.mark.asyncio
async def test_static_route_is_bidirectional():
    locations = LocationRepository(DATA_DIR / "locations.json")
    routes = StaticRouteProvider(DATA_DIR / "travel_times.json", locations)

    forward = await routes.get_route("library", "parcel_station")
    reverse = await routes.get_route("parcel_station", "library")

    assert forward.duration_min == 13
    assert reverse.duration_min == 13
    assert forward.source == DataSource.STRUCTURED


@pytest.mark.asyncio
async def test_static_route_estimates_requested_non_motor_mode_as_fallback():
    locations = LocationRepository(DATA_DIR / "locations.json")
    routes = StaticRouteProvider(DATA_DIR / "travel_times.json", locations)

    bicycle = await routes.get_route(
        "library",
        "parcel_station",
        mode="bicycle",
    )
    electrobike = await routes.get_route(
        "library",
        "parcel_station",
        mode="electrobike",
    )

    assert bicycle.mode == "bicycle"
    assert electrobike.mode == "electrobike"
    assert bicycle.source == DataSource.ESTIMATED
    assert electrobike.duration_min <= bicycle.duration_min


@pytest.mark.asyncio
async def test_unknown_route_with_coordinates_is_estimated():
    locations = LocationRepository(DATA_DIR / "locations.json")
    routes = StaticRouteProvider(DATA_DIR / "travel_times.json", locations)

    result = await routes.get_route("teaching_building_6", "track")

    assert result.source == DataSource.ESTIMATED
    assert result.duration_min > 0


@pytest.mark.asyncio
async def test_unknown_route_without_coordinates_fails():
    locations = LocationRepository(DATA_DIR / "locations.json")
    routes = StaticRouteProvider(DATA_DIR / "travel_times.json", locations)

    with pytest.raises(LookupError):
        await routes.get_route("laboratory", "track")
