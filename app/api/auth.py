from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.errors import AppError


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


@router.get("/status")
def access_status(request: Request) -> dict:
    manager = request.app.state.access_manager
    authorization = request.headers.get("authorization", "")
    token = (
        authorization.removeprefix("Bearer ").strip()
        if authorization.startswith("Bearer ")
        else ""
    )
    return {
        "enabled": manager.enabled,
        "configured": manager.configured,
        "authenticated": bool(token and manager.verify(token)),
        "test_username": manager.username if manager.enabled else None,
    }


@router.post("/login")
def login(payload: LoginRequest, request: Request) -> dict:
    manager = request.app.state.access_manager
    if not manager.configured:
        raise AppError(
            "ACCESS_NOT_CONFIGURED",
            "测试入口尚未完成安全配置，请联系项目负责人",
            status_code=503,
            retryable=False,
        )
    result = manager.login(payload.username, payload.password)
    if result is None:
        raise AppError(
            "INVALID_CREDENTIALS",
            "测试账号或密码不正确",
            status_code=401,
            retryable=False,
        )
    token, expires_at = result
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "username": payload.username,
    }
