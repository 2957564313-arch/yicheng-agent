from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json


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
            expires_at = datetime.now(timezone.utc) + timedelta(
                hours=self.access_hours
            )
            return self._issue("local", expires_at), expires_at
        if not self.configured:
            return None
        if not (
            hmac.compare_digest(username, self.username)
            and hmac.compare_digest(password, self._password)
        ):
            return None
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=self.access_hours
        )
        return self._issue(username, expires_at), expires_at

    def verify(self, token: str) -> str | None:
        if not self.enabled:
            return "local"
        try:
            payload_raw, signature = token.split(".", 1)
            expected = self._signature(payload_raw)
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(_decode(payload_raw))
            expires_at = datetime.fromtimestamp(
                int(payload["exp"]),
                tz=timezone.utc,
            )
            if expires_at <= datetime.now(timezone.utc):
                return None
            username = str(payload["sub"])
            return username if username == self.username else None
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _issue(self, username: str, expires_at: datetime) -> str:
        payload = _encode(
            json.dumps(
                {
                    "sub": username,
                    "exp": int(expires_at.timestamp()),
                },
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
