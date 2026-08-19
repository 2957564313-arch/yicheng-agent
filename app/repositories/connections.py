from __future__ import annotations

import json
from datetime import datetime

from app.repositories.database import Database
from app.schemas.hduhelp import HduHelpConnectionStatus, HduHelpTerm


class ExternalConnectionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_row(self, user_id: str, provider: str):
        with self.database.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM external_account_connections
                WHERE user_id = ? AND provider = ?
                """,
                (user_id, provider),
            ).fetchone()

    def status(self, user_id: str, provider: str) -> HduHelpConnectionStatus:
        row = self.get_row(user_id, provider)
        if row is None:
            return HduHelpConnectionStatus()
        try:
            terms = [
                HduHelpTerm.model_validate(value)
                for value in json.loads(row["terms_json"] or "[]")
            ]
        except (TypeError, ValueError, json.JSONDecodeError):
            terms = []
        return HduHelpConnectionStatus(
            connected=row["status"] == "active",
            display_name=row["display_name"],
            available_terms=terms,
            last_synced_at=(
                datetime.fromisoformat(row["last_synced_at"])
                if row["last_synced_at"]
                else None
            ),
            last_error=row["last_error"],
        )

    def save(
        self,
        *,
        user_id: str,
        external_user_id: str,
        display_name: str | None,
        credential_ciphertext: str,
        terms: list[HduHelpTerm],
        now: datetime,
    ) -> HduHelpConnectionStatus:
        timestamp = now.isoformat()
        terms_json = json.dumps(
            [term.model_dump(mode="json") for term in terms],
            ensure_ascii=False,
        )
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO users(id, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, users.display_name),
                    updated_at = excluded.updated_at
                """,
                (user_id, display_name, timestamp, timestamp),
            )
            connection.execute(
                """
                INSERT INTO external_account_connections(
                    user_id, provider, external_user_id, display_name,
                    credential_ciphertext, terms_json, status,
                    last_synced_at, last_error, created_at, updated_at
                ) VALUES (?, 'hduhelp', ?, ?, ?, ?, 'active', NULL, NULL, ?, ?)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    external_user_id = excluded.external_user_id,
                    display_name = excluded.display_name,
                    credential_ciphertext = excluded.credential_ciphertext,
                    terms_json = excluded.terms_json,
                    status = 'active',
                    last_error = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    external_user_id,
                    display_name,
                    credential_ciphertext,
                    terms_json,
                    timestamp,
                    timestamp,
                ),
            )
        return self.status(user_id, "hduhelp")

    def mark_synced(self, user_id: str, now: datetime) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE external_account_connections
                SET last_synced_at = ?, last_error = NULL, updated_at = ?
                WHERE user_id = ? AND provider = 'hduhelp'
                """,
                (now.isoformat(), now.isoformat(), user_id),
            )

    def update_credential(
        self,
        user_id: str,
        credential_ciphertext: str,
        now: datetime,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE external_account_connections
                SET credential_ciphertext = ?, updated_at = ?
                WHERE user_id = ? AND provider = 'hduhelp'
                """,
                (credential_ciphertext, now.isoformat(), user_id),
            )

    def mark_error(self, user_id: str, message: str, now: datetime) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE external_account_connections
                SET last_error = ?, updated_at = ?
                WHERE user_id = ? AND provider = 'hduhelp'
                """,
                (message[:240], now.isoformat(), user_id),
            )

    def delete(self, user_id: str, provider: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM external_account_connections
                WHERE user_id = ? AND provider = ?
                """,
                (user_id, provider),
            )
        return cursor.rowcount > 0
