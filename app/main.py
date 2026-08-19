from __future__ import annotations

import re
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.api import (
    academic_calendar,
    agenda,
    auth,
    campuses,
    chat,
    conversations,
    demos,
    hduhelp,
    health,
    memories,
    timetables,
    weeks,
)
from app.config import BASE_DIR, Settings, get_settings
from app.container import build_container
from app.errors import AppError
from app.graph import build_graph
from app.services.access import AccessManager


def create_app(settings_override: Settings | None = None) -> FastAPI:
    active_settings = settings_override or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        container = build_container(active_settings)
        async with AsyncSqliteSaver.from_conn_string(
            str(active_settings.app_checkpoint_database_path)
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
        docs_url="/docs" if active_settings.app_docs_enabled else None,
        redoc_url="/redoc" if active_settings.app_docs_enabled else None,
        openapi_url=(
            "/openapi.json" if active_settings.app_docs_enabled else None
        ),
    )
    application.state.access_manager = AccessManager(
        enabled=active_settings.app_access_enabled,
        username=active_settings.app_test_username,
        password=active_settings.app_test_password,
        secret=active_settings.app_auth_secret,
        access_hours=active_settings.app_access_hours,
    )

    @application.middleware("http")
    async def protect_api(request: Request, call_next):
        manager = request.app.state.access_manager
        path = request.url.path
        public_api = (
            path == "/api/v1/health"
            or path.startswith("/api/v1/auth/")
            or (
                request.method == "GET"
                and path in {
                    "/api/v1/demos",
                    "/api/v1/campuses/current",
                }
            )
        )
        if manager.enabled and path.startswith("/api/v1/") and not public_api:
            authorization = request.headers.get("authorization", "")
            token = (
                authorization.removeprefix("Bearer ").strip()
                if authorization.startswith("Bearer ")
                else ""
            )
            claims = manager.verify_claims(token) if token else None
            if claims is None:
                return JSONResponse(
                    status_code=401,
                    content={
                        "request_id": f"req_{uuid4().hex}",
                        "trace_id": f"trace_{uuid4().hex}",
                        "error": {
                            "code": "AUTH_REQUIRED",
                            "message": "请先登录易程智策账号或使用测试入口",
                            "details": [],
                            "retryable": False,
                        },
                    },
                )
            mode = str(claims.get("mode") or "")
            user_id = str(claims.get("uid") or "")
            user_match = re.match(r"^/api/v1/users/([^/]+)", path)
            if mode not in {"test", "normal"}:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "SESSION_MODE_REQUIRED",
                            "message": "当前登录状态已失效，请重新登录",
                            "details": [],
                            "retryable": False,
                        }
                    },
                )
            if user_match and user_match.group(1) != user_id:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "USER_SCOPE_MISMATCH",
                            "message": "当前登录无权访问这个个人空间",
                            "details": [],
                            "retryable": False,
                        }
                    },
                )
            request.state.access_claims = claims
        return await call_next(request)

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path in {"/", "/index.html", "/app.js", "/styles.css"}:
            response.headers["Cache-Control"] = "no-cache"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), geolocation=(), microphone=(), payment=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self'; "
                "img-src 'self' data:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "object-src 'none'; "
                "base-uri 'self'; "
                "frame-ancestors 'none'; "
                "form-action 'self'"
            ),
        )
        return response

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
    application.include_router(auth.router)
    application.include_router(hduhelp.router)
    application.include_router(chat.router)
    application.include_router(conversations.router)
    application.include_router(demos.router)
    application.include_router(memories.router)
    application.include_router(agenda.router)
    application.include_router(timetables.router)
    application.include_router(academic_calendar.router)
    application.include_router(campuses.router)
    application.include_router(weeks.router)
    application.mount(
        "/",
        StaticFiles(directory=BASE_DIR / "app" / "web", html=True),
        name="web",
    )
    return application


app = create_app()
