from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.api import (
    academic_calendar,
    chat,
    demos,
    health,
    memories,
    timetables,
)
from app.config import BASE_DIR, Settings, get_settings
from app.container import build_container
from app.errors import AppError
from app.graph import build_graph


def create_app(settings_override: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        settings = settings_override or get_settings()
        container = build_container(settings)
        async with AsyncSqliteSaver.from_conn_string(
            str(settings.app_checkpoint_database_path)
        ) as checkpointer:
            await checkpointer.setup()
            application.state.container = container
            application.state.graph = build_graph(
                container,
                checkpointer=checkpointer,
            )
            yield

    application = FastAPI(
        title="易程智策 Campus Agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.exception_handler(AppError)
    async def handle_app_error(
        request: Request,
        exc: AppError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "request_id": f"req_{uuid4().hex}",
                "trace_id": f"trace_{uuid4().hex}",
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "retryable": exc.retryable,
                },
            },
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "request_id": f"req_{uuid4().hex}",
                "trace_id": f"trace_{uuid4().hex}",
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "请求参数不合法",
                    "details": [
                        {
                            "field": ".".join(
                                str(value) for value in error["loc"]
                            ),
                            "reason": error["msg"],
                        }
                        for error in exc.errors()
                    ],
                    "retryable": False,
                },
            },
        )

    application.include_router(health.router)
    application.include_router(chat.router)
    application.include_router(demos.router)
    application.include_router(memories.router)
    application.include_router(timetables.router)
    application.include_router(academic_calendar.router)
    application.mount(
        "/",
        StaticFiles(directory=BASE_DIR / "app" / "web", html=True),
        name="web",
    )
    return application


app = create_app()
