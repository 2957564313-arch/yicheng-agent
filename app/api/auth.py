from __future__ import annotations

from secrets import token_hex
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.errors import AppError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class SessionRequest(BaseModel):
    mode: Literal["test"]


@router.get("/status")
def access_status(request: Request) -> dict:
    manager = request.app.state.access_manager
    authorization = request.headers.get("authorization", "")
    token = (
        authorization.removeprefix("Bearer ").strip()
        if authorization.startswith("Bearer ")
        else ""
    )
    claims = manager.verify_claims(token) if token else None
    return {
        "enabled": manager.enabled,
        "configured": manager.configured,
        "authenticated": bool(token and manager.verify(token)),
        "test_username": manager.username if manager.enabled else None,
        "session_mode": claims.get("mode") if claims else None,
        "user_id": claims.get("uid") if claims else None,
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


@router.post("/session")
def create_session(payload: SessionRequest, request: Request) -> dict:
    """Create an isolated demonstration workspace; it never carries HDUHelp data."""
    manager = request.app.state.access_manager
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ").strip()
    claims = manager.verify_claims(token)
    if claims is None:
        raise AppError(
            "AUTH_REQUIRED",
            "请先使用比赛测试账号登录",
            status_code=401,
            retryable=False,
        )
    user_id = f"test_{token_hex(12)}"
    access_token, expires_at = manager.issue_session(
        mode=payload.mode,
        user_id=user_id,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "session_mode": payload.mode,
        "user_id": user_id,
    }
