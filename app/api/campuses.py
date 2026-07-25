from __future__ import annotations

from fastapi import APIRouter, Request

from app.errors import AppError
from app.schemas.campus import (
    CampusDiscoveryRequest,
    CampusDiscoveryResponse,
)


router = APIRouter(prefix="/api/v1/campuses", tags=["campuses"])


@router.get("/current")
def current_campus(request: Request) -> dict:
    container = request.app.state.container
    profile = container.campus_profile
    return {
        "campus_id": (
            profile.get("profile_id")
            or container.locations.campus_id
        ),
        "display_name": (
            profile.get("display_name")
            or container.locations.campus_id
        ),
        "search_city": (
            profile.get("external_services", {})
            .get("amap", {})
            .get("search_city", "")
        ),
        "knowledge_ready": True,
        "location_count": len(
            container.locations.all(
                campus_id=container.locations.campus_id,
            )
        ),
    }


@router.post("/discover", response_model=CampusDiscoveryResponse)
async def discover_campus(
    payload: CampusDiscoveryRequest,
    request: Request,
) -> CampusDiscoveryResponse:
    provider = request.app.state.container.campus_discovery
    if provider is None:
        raise AppError(
            "CAMPUS_DISCOVERY_UNAVAILABLE",
            "当前没有配置高德地点搜索，暂时无法自动建立校园地点目录",
            status_code=503,
            retryable=True,
        )
    try:
        return await provider.discover(
            school_name=payload.school_name,
            city=payload.city,
            radius_m=payload.radius_m,
        )
    except LookupError as exc:
        raise AppError(
            "CAMPUS_NOT_FOUND",
            str(exc),
            status_code=404,
            retryable=False,
        ) from exc
    except Exception as exc:
        raise AppError(
            "CAMPUS_DISCOVERY_FAILED",
            "高德地点检索暂时不可用，请稍后重试",
            status_code=502,
            retryable=True,
        ) from exc
