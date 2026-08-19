from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime

from app.repositories.database import Database


@dataclass(frozen=True, slots=True)
class Account:
    user_id: str
    username: str
    display_name: str | None


def normalize_username(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


def _password_digest(password: str, salt: bytes) -> str:
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
        maxmem=64 * 1024 * 1024,
    )
    return digest.hex()


class AccountRepository:
    """Server-side accounts that map every device to one user data scope."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        username: str,
        password: str,
        display_name: str | None,
        now: datetime,
    ) -> Account | None:
        normalized = normalize_username(username)
        salt = secrets.token_bytes(16)
        user_id = f"usr_{secrets.token_hex(12)}"
        account_id = f"acct_{secrets.token_hex(12)}"
        timestamp = now.isoformat()
        clean_display_name = (display_name or "").strip() or None
        try:
            with self.database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO users(id, display_name, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, clean_display_name, timestamp, timestamp),
                )
                connection.execute(
                    """
                    INSERT INTO app_accounts(
                        id, user_id, username, username_normalized,
                        password_hash, password_salt, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account_id,
                        user_id,
                        username.strip(),
                        normalized,
                        _password_digest(password, salt),
                        salt.hex(),
                        timestamp,
                        timestamp,
                    ),
                )
        except sqlite3.IntegrityError:
            return None
        return Account(
            user_id=user_id,
            username=username.strip(),
            display_name=clean_display_name,
        )

    def authenticate(
        self,
        *,
        username: str,
        password: str,
        now: datetime,
    ) -> Account | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT a.user_id, a.username, a.password_hash,
                       a.password_salt, a.disabled, u.display_name
                FROM app_accounts AS a
                JOIN users AS u ON u.id = a.user_id
                WHERE a.username_normalized = ?
                """,
                (normalize_username(username),),
            ).fetchone()
        if row is None or row["disabled"]:
            return None
        try:
            actual = _password_digest(password, bytes.fromhex(row["password_salt"]))
        except (ValueError, TypeError):
            return None
        if not hmac.compare_digest(actual, row["password_hash"]):
            return None
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE app_accounts
                SET last_login_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (now.isoformat(), now.isoformat(), row["user_id"]),
            )
        return Account(
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
        )
