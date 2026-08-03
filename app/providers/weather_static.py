from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from app.schemas.common import DataSource
from app.schemas.context import WeatherContext


class StaticWeatherProvider:
    def __init__(self, path: Path | None = None) -> None:
        self._payload: dict | None = None
        if path and path.exists():
            self._payload = json.loads(path.read_text(encoding="utf-8"))

    async def get_forecast(
        self,
        target_date: date,
        location_id: str,
        *,
        city_adcode: str | None = None,
    ) -> list[WeatherContext]:
        if not self._payload:
            return [
                WeatherContext(
                    date=target_date,
                    period="day",
                    source=DataSource.UNKNOWN,
                )
            ]

        # Keep the original single-fixture format compatible, while allowing
        # an explicitly labelled set of historical regression snapshots.
        fixtures = self._payload.get("fixtures")
        if not isinstance(fixtures, list):
            fixtures = [self._payload]
        for fixture in fixtures:
            if not isinstance(fixture, dict):
                continue
            try:
                fixture_date = date.fromisoformat(fixture["fixture_date"])
            except (KeyError, TypeError, ValueError):
                continue
            fixture_location = str(fixture.get("location_id") or "").strip()
            if fixture_date != target_date or (
                fixture_location and fixture_location != location_id
            ):
                continue
            return [
                WeatherContext(
                    date=target_date,
                    source=DataSource.DEMO_FIXTURE,
                    **period,
                )
                for period in fixture.get("periods", [])
            ]
        return [
            WeatherContext(
                date=target_date,
                period="day",
                source=DataSource.UNKNOWN,
            )
        ]
