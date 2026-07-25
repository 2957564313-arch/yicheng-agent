from __future__ import annotations

import json
import math
from pathlib import Path

from app.providers.location_repository import LocationRepository
from app.schemas.common import DataSource
from app.schemas.context import TravelEstimate


class StaticRouteProvider:
    def __init__(
        self,
        path: Path,
        locations: LocationRepository,
    ) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.mode = payload.get("mode", "walk")
        self.data_quality = payload.get("data_quality", "unknown")
        self.locations = locations
        self._pairs: dict[tuple[str, str], dict] = {}
        for pair in payload.get("pairs", []):
            origin = pair["origin_id"]
            destination = pair["destination_id"]
            if locations.get(origin) is None or locations.get(destination) is None:
                raise ValueError(
                    f"route references unknown location: {origin}->{destination}"
                )
            self._pairs[(origin, destination)] = pair
            if pair.get("bidirectional", False):
                reverse = dict(pair)
                reverse["origin_id"] = destination
                reverse["destination_id"] = origin
                self._pairs[(destination, origin)] = reverse

    async def get_route(
        self,
        origin_id: str,
        destination_id: str,
        mode: str = "walk",
    ) -> TravelEstimate:
        if mode not in {"walk", "bicycle", "electrobike"}:
            raise ValueError(f"unsupported route mode: {mode}")
        if origin_id == destination_id:
            return TravelEstimate(
                origin_id=origin_id,
                destination_id=destination_id,
                mode=mode,
                distance_m=0,
                duration_min=0,
                base_duration_min=0,
                source=DataSource.STRUCTURED,
                confidence=1,
            )

        origin_location = self.locations.get(origin_id)
        destination_location = self.locations.get(destination_id)
        if (
            origin_location is None
            or destination_location is None
            or origin_location.campus_id != destination_location.campus_id
        ):
            raise LookupError(
                "route endpoints are unknown or belong to different campuses"
            )

        pair = self._pairs.get((origin_id, destination_id))
        if pair:
            duration_min = self._duration_for_mode(
                mode=mode,
                walking_duration_min=int(pair["duration_min"]),
                distance_m=pair.get("distance_m"),
            )
            source = (
                DataSource.DEMO_FIXTURE
                if "demo_fixture" in pair.get("source", "")
                else DataSource.STRUCTURED
            )
            warning = (
                "当前通勤数据为未核验演示数据"
                if source == DataSource.DEMO_FIXTURE
                else None
            )
            if mode != "walk":
                source = DataSource.ESTIMATED
                warning = (
                    "实时骑行路线不可用，已按本地距离保守估算；"
                    "联网时将优先使用高德对应出行方式"
                )
            return TravelEstimate(
                origin_id=origin_id,
                destination_id=destination_id,
                mode=mode,
                distance_m=pair.get("distance_m"),
                duration_min=duration_min,
                base_duration_min=duration_min,
                source=source,
                confidence=(
                    min(float(pair.get("confidence", 0.8)), 0.6)
                    if mode != "walk"
                    else pair.get("confidence", 0.8)
                ),
                warning=warning,
            )

        estimated = self._estimate_from_coordinates(
            origin_id,
            destination_id,
            mode=mode,
        )
        if estimated is not None:
            distance_m, duration_min = estimated
            return TravelEstimate(
                origin_id=origin_id,
                destination_id=destination_id,
                mode=mode,
                distance_m=distance_m,
                duration_min=duration_min,
                base_duration_min=duration_min,
                source=DataSource.ESTIMATED,
                confidence=0.45,
                warning="未找到静态路线，当前结果由坐标直线距离估算",
            )
        raise LookupError(f"route unavailable: {origin_id}->{destination_id}")

    def _estimate_from_coordinates(
        self,
        origin_id: str,
        destination_id: str,
        *,
        mode: str,
    ) -> tuple[int, int] | None:
        origin = self.locations.get(origin_id)
        destination = self.locations.get(destination_id)
        if not origin or not destination:
            return None
        if None in (
            origin.longitude,
            origin.latitude,
            destination.longitude,
            destination.latitude,
        ):
            return None

        lat1 = math.radians(float(origin.latitude))
        lon1 = math.radians(float(origin.longitude))
        lat2 = math.radians(float(destination.latitude))
        lon2 = math.radians(float(destination.longitude))
        delta_lat = lat2 - lat1
        delta_lon = lon2 - lon1
        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        )
        straight_m = 6_371_000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        walking_m = max(1, round(straight_m * 1.25))
        duration_min = self._duration_for_mode(
            mode=mode,
            walking_duration_min=max(1, math.ceil(walking_m / 80)),
            distance_m=walking_m,
        )
        return walking_m, duration_min

    @staticmethod
    def _duration_for_mode(
        *,
        mode: str,
        walking_duration_min: int,
        distance_m: int | None,
    ) -> int:
        if mode == "walk":
            return walking_duration_min
        if distance_m is None:
            factor = 0.55 if mode == "bicycle" else 0.4
            return max(2, math.ceil(walking_duration_min * factor))
        speed_m_per_min = 200 if mode == "bicycle" else 300
        return max(2, math.ceil(int(distance_m) / speed_m_per_min) + 1)
