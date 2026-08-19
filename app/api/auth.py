from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from app.errors import AppError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class AccountLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=200)


class RegisterRequest(AccountLoginRequest):
    display_name: str | None = Field(default=None, max_length=40)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or any(
            not (character.isalnum() or character in "._@+-")
            for character in cleaned
        ):
            raise ValueError("账号只能包含文字、数字及 . _ @ + -")
        return cleaned


def _session_payload(
    request: Request,
    *,
    mode: str,
    user_id: str,
    account_name: str | None = None,
) -> dict:
    token, expires_at = request.app.state.access_manager.issue_session(
        mode=mode,
        user_id=user_id,
        account_name=account_name,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "session_mode": mode,
        "user_id": user_id,
        "account_name": account_name,
    }


def _require_bootstrap(request: Request) -> None:
    manager = request.app.state.access_manager
    if not manager.enabled:
        return
    authorization = request.headers.get("authorization", "")
    token = (
        authorization.removeprefix("Bearer ").strip()
        if authorization.startswith("Bearer ")
        else ""
    )
    claims = manager.verify_claims(token) if token else None
    if not claims or claims.get("mode") != "bootstrap":
        raise AppError(
            "PRODUCT_ACCESS_REQUIRED",
            "请先输入产品统一入口账号和密码。",
            status_code=401,
            retryable=False,
        )


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
        "account_name": claims.get("account") if claims else None,
    }


@router.post("/register")
def register(payload: RegisterRequest, request: Request) -> dict:
    _require_bootstrap(request)
    account = request.app.state.container.accounts.create(
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
        now=datetime.now(UTC),
    )
    if account is None:
        raise AppError(
            "ACCOUNT_EXISTS",
            "这个账号已经存在，请直接登录。",
            status_code=409,
            retryable=False,
        )
    return _session_payload(
        request,
        mode="normal",
        user_id=account.user_id,
        account_name=account.username,
    )


@router.post("/account/login")
def account_login(payload: AccountLoginRequest, request: Request) -> dict:
    _require_bootstrap(request)
    account = request.app.state.container.accounts.authenticate(
        username=payload.username,
        password=payload.password,
        now=datetime.now(UTC),
    )
    if account is None:
        raise AppError(
            "INVALID_ACCOUNT_CREDENTIALS",
            "账号或密码不正确。",
            status_code=401,
            retryable=False,
        )
    return _session_payload(
        request,
        mode="normal",
        user_id=account.user_id,
        account_name=account.username,
    )


@router.post("/login")
def product_login(payload: LoginRequest, request: Request) -> dict:
    """Pass the shared product gate before choosing a personal/test space."""
    manager = request.app.state.access_manager
    login = manager.login(payload.username, payload.password)
    if login is None:
        raise AppError(
            "INVALID_CREDENTIALS",
            "产品入口账号或密码不正确。",
            status_code=401,
            retryable=False,
        )
    token, expires_at = login
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "session_mode": "bootstrap",
        "user_id": None,
        "account_name": None,
    }


@router.post("/test-session")
def test_session(request: Request) -> dict:
    """Enter the stable shared workspace used for debugging and judging."""
    _require_bootstrap(request)
    return _session_payload(
        request,
        mode="test",
        user_id="test_shared",
        account_name="共享测试空间",
    )
