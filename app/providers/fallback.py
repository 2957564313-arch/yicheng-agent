from __future__ import annotations

from datetime import date

from app.schemas.context import TravelEstimate, WeatherContext


class RouteFallbackService:
    def __init__(self, *, static, live=None) -> None:
        self.static = static
        self.live = live

    async def get_route(
        self,
        origin_id: str,
        destination_id: str,
        *,
        mode: str = "walk",
        prefer_live: bool,
    ) -> TravelEstimate:
        live_error: Exception | None = None
        if prefer_live and self.live:
            try:
                return await self.live.get_route(
                    origin_id,
                    destination_id,
                    mode=mode,
                )
            except Exception as exc:
                live_error = exc
        estimate = await self.static.get_route(
            origin_id,
            destination_id,
            mode=mode,
        )
        if live_error:
            estimate.warning = (
                "实时路线不可用，已降级为静态或估算路线"
            )
        return estimate


class WeatherFallbackService:
    def __init__(self, *, static, live=None) -> None:
        self.static = static
        self.live = live

    async def get_forecast(
        self,
        target_date: date,
        location_id: str,
        *,
        prefer_live: bool,
    ) -> list[WeatherContext]:
        if prefer_live and self.live:
            try:
                live = await self.live.get_forecast(
                    target_date,
                    location_id,
                )
                if any(item.source.value != "unknown" for item in live):
                    return live
            except Exception:
                pass
        return await self.static.get_forecast(target_date, location_id)
