from __future__ import annotations

from datetime import date

from app.schemas.common import DataSource
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
                "实时路线暂不可用，已降级为根据当前学校已缓存的地点坐标"
                "进行保守估算；不会采用校园范围外的同名地点"
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
        city_adcode: str | None = None,
        allow_static: bool = True,
    ) -> list[WeatherContext]:
        if prefer_live and self.live:
            try:
                live = await self.live.get_forecast(
                    target_date,
                    location_id,
                    city_adcode=city_adcode,
                )
                if any(item.source.value != "unknown" for item in live):
                    return live
            except Exception:
                pass
            return [
                WeatherContext(
                    date=target_date,
                    period="day",
                    source=DataSource.UNKNOWN,
                )
            ]
        if allow_static:
            return await self.static.get_forecast(
                target_date,
                location_id,
                city_adcode=city_adcode,
            )
        return [
            WeatherContext(
                date=target_date,
                period="day",
                source=DataSource.UNKNOWN,
            )
        ]
