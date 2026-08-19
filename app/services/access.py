from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta


class AccessManager:
    def __init__(
        self,
        *,
        enabled: bool,
        username: str,
        password: str,
        secret: str,
        access_hours: int,
    ) -> None:
        self.enabled = enabled
        self.username = username
        self._password = password
        self._secret = secret.encode("utf-8")
        self.access_hours = access_hours

    @property
    def configured(self) -> bool:
        return bool(
            not self.enabled
            or (
                self.username
                and self._password
                and len(self._secret) >= 24
            )
        )

    def login(self, username: str, password: str) -> tuple[str, datetime] | None:
        if not self.enabled:
            expires_at = datetime.now(UTC) + timedelta(
                hours=self.access_hours
            )
            return self._issue("local", expires_at, mode="bootstrap"), expires_at
        if not self.configured:
            return None
        if not (
            hmac.compare_digest(username, self.username)
            and hmac.compare_digest(password, self._password)
        ):
            return None
        expires_at = datetime.now(UTC) + timedelta(
            hours=self.access_hours
        )
        return self._issue(username, expires_at, mode="bootstrap"), expires_at

    def issue_session(self, *, mode: str, user_id: str) -> tuple[str, datetime]:
        """Issue a user-scoped application session after mode selection/login."""
        if mode not in {"test", "normal"} or not user_id:
            raise ValueError("invalid access session")
        expires_at = datetime.now(UTC) + timedelta(hours=self.access_hours)
        subject = self.username if self.enabled else "local"
        return (
            self._issue(subject, expires_at, mode=mode, user_id=user_id),
            expires_at,
        )

    def verify_claims(self, token: str) -> dict[str, object] | None:
        if not self.enabled:
            return {"sub": "local", "mode": "local"}
        try:
            payload_raw, signature = token.split(".", 1)
            expected = self._signature(payload_raw)
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(_decode(payload_raw))
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
            if expires_at <= datetime.now(UTC):
                return None
            if str(payload["sub"]) != self.username:
                return None
            return payload
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def verify(self, token: str) -> str | None:
        claims = self.verify_claims(token)
        return str(claims["sub"]) if claims else None

    def _issue(
        self,
        username: str,
        expires_at: datetime,
        *,
        mode: str,
        user_id: str | None = None,
    ) -> str:
        claims: dict[str, object] = {
            "sub": username,
            "exp": int(expires_at.timestamp()),
            "mode": mode,
        }
        if user_id:
            claims["uid"] = user_id
        payload = _encode(
            json.dumps(
                claims,
                separators=(",", ":"),
            )
        )
        return f"{payload}.{self._signature(payload)}"

    def _signature(self, payload: str) -> str:
        digest = hmac.new(
            self._secret,
            payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _encode(value: str) -> str:
    return (
        base64.urlsafe_b64encode(value.encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )


def _decode(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode("utf-8")
