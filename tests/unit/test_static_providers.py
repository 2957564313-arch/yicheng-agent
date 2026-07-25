from pathlib import Path

import pytest

from app.providers.location_repository import LocationRepository
from app.providers.route_static import StaticRouteProvider
from app.schemas.common import DataSource
from app.schemas.context import CampusLocation, SourceMetadata


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_location_alias_resolution():
    repository = LocationRepository(DATA_DIR / "locations.json")
    assert repository.resolve("六教").id == "teaching_building_6"
    assert repository.resolve(" 菜鸟驿站 ").id == "parcel_station"
    assert repository.resolve("不存在的地点") is None


def test_location_aliases_are_isolated_by_campus():
    repository = LocationRepository(DATA_DIR / "locations.json")
    other_library = repository.register_runtime(
        CampusLocation(
            id="library",
            campus_id="other_university",
            name="图书馆",
            aliases=["本校图书馆"],
            category="study",
            longitude=121.1,
            latitude=31.1,
            source=SourceMetadata(
                type="amap_poi",
                reference="other-library",
            ),
        )
    )

    assert other_library.id != "library"
    assert (
        repository.resolve("图书馆", campus_id="hdu_xiasha").id
        == "library"
    )
    assert (
        repository.resolve(
            "图书馆",
            campus_id="other_university",
        ).id
        == other_library.id
    )
    assert (
        repository.get("library", campus_id="other_university")
        is None
    )


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


@pytest.mark.asyncio
async def test_route_never_crosses_campus_boundaries():
    locations = LocationRepository(DATA_DIR / "locations.json")
    other = locations.register_runtime(
        CampusLocation(
            id="other_gate",
            campus_id="other_university",
            name="另一所学校校门",
            aliases=[],
            category="campus",
            longitude=121.1,
            latitude=31.1,
            source=SourceMetadata(
                type="amap_poi",
                reference="other-gate",
            ),
        )
    )
    routes = StaticRouteProvider(DATA_DIR / "travel_times.json", locations)

    with pytest.raises(LookupError, match="different campuses"):
        await routes.get_route("library", other.id)
