from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request


router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health")
def health(request: Request) -> dict:
    container = request.app.state.container
    timezone_name = container.settings.app_timezone
    server_time = datetime.now(ZoneInfo(timezone_name))
    database_status = "ok"
    try:
        with container.database.connect() as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception:
        database_status = "error"
    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "version": "0.1.0",
        "database": database_status,
        "llm": "configured" if container.llm.configured else "not_configured",
        "live_map_enabled": container.settings.live_route_enabled,
        "live_weather_enabled": container.settings.live_weather_enabled,
        "knowledge_chunks": container.rag.chunk_count,
        "knowledge_retrieval": "enhanced_lexical_rerank",
        "memory_store": "sqlite",
        "server_time": server_time.isoformat(),
        "timezone": timezone_name,
    }
