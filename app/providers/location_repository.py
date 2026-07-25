from __future__ import annotations

import json
from pathlib import Path

from app.schemas.context import CampusLocation


def _normalize_name(value: str) -> str:
    return "".join(value.lower().strip().split())


class LocationRepository:
    def __init__(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.schema_version = payload["schema_version"]
        self.campus_id = payload["campus_id"]
        self.data_quality = payload.get("data_quality", "unknown")
        self._locations: dict[str, CampusLocation] = {}
        self._alias_index: dict[str, str] = {}

        for raw in payload.get("locations", []):
            location = CampusLocation.model_validate(raw)
            if location.campus_id is None:
                location = location.model_copy(
                    update={"campus_id": self.campus_id}
                )
            if location.id in self._locations:
                raise ValueError(f"duplicate location id: {location.id}")
            self._locations[location.id] = location

            for alias in {location.name, location.id, *location.aliases}:
                key = _normalize_name(alias)
                index_key = f"{location.campus_id}:{key}"
                existing = self._alias_index.get(index_key)
                if existing and existing != location.id:
                    raise ValueError(
                        f"duplicate location alias {alias!r}: "
                        f"{existing} vs {location.id}"
                    )
                self._alias_index[index_key] = location.id

    def resolve(
        self,
        raw_name: str | None,
        *,
        campus_id: str | None = None,
    ) -> CampusLocation | None:
        if not raw_name:
            return None
        active_campus_id = campus_id or self.campus_id
        location_id = self._alias_index.get(
            f"{active_campus_id}:{_normalize_name(raw_name)}"
        )
        return self._locations.get(location_id) if location_id else None

    def get(
        self,
        location_id: str,
        *,
        campus_id: str | None = None,
    ) -> CampusLocation | None:
        location = self._locations.get(location_id)
        if (
            location is not None
            and campus_id is not None
            and location.campus_id != campus_id
        ):
            return None
        return location

    def all(
        self,
        *,
        campus_id: str | None = None,
    ) -> list[CampusLocation]:
        if campus_id is None:
            return list(self._locations.values())
        return [
            location
            for location in self._locations.values()
            if location.campus_id == campus_id
        ]

    def register_runtime(
        self,
        location: CampusLocation,
    ) -> CampusLocation:
        """Register an API-resolved location for the current process."""
        campus_id = location.campus_id or self.campus_id
        location = location.model_copy(update={"campus_id": campus_id})
        existing = self.resolve(location.name, campus_id=campus_id)
        if existing:
            return existing
        id_collision = self._locations.get(location.id)
        if (
            id_collision is not None
            and id_collision.campus_id != campus_id
        ):
            location = location.model_copy(
                update={"id": f"{campus_id}__{location.id}"}
            )
        self._locations[location.id] = location
        for alias in {location.name, location.id, *location.aliases}:
            key = _normalize_name(alias)
            index_key = f"{campus_id}:{key}"
            if key and index_key not in self._alias_index:
                self._alias_index[index_key] = location.id
        return location
