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
    ) -> list[WeatherContext]:
        if not self._payload:
            return [
                WeatherContext(
                    date=target_date,
                    period="day",
                    source=DataSource.UNKNOWN,
                )
            ]

        fixture_date = date.fromisoformat(self._payload["fixture_date"])
        if fixture_date != target_date:
            return [
                WeatherContext(
                    date=target_date,
                    period="day",
                    source=DataSource.UNKNOWN,
                )
            ]
        return [
            WeatherContext(
                date=target_date,
                source=DataSource.DEMO_FIXTURE,
                **period,
            )
            for period in self._payload.get("periods", [])
        ]

