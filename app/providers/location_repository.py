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
            if location.id in self._locations:
                raise ValueError(f"duplicate location id: {location.id}")
            self._locations[location.id] = location

            for alias in {location.name, location.id, *location.aliases}:
                key = _normalize_name(alias)
                existing = self._alias_index.get(key)
                if existing and existing != location.id:
                    raise ValueError(
                        f"duplicate location alias {alias!r}: "
                        f"{existing} vs {location.id}"
                    )
                self._alias_index[key] = location.id

    def resolve(self, raw_name: str | None) -> CampusLocation | None:
        if not raw_name:
            return None
        location_id = self._alias_index.get(_normalize_name(raw_name))
        return self._locations.get(location_id) if location_id else None

    def get(self, location_id: str) -> CampusLocation | None:
        return self._locations.get(location_id)

    def all(self) -> list[CampusLocation]:
        return list(self._locations.values())

