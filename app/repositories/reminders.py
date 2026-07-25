from __future__ import annotations

import json
from datetime import datetime

from app.repositories.database import Database
from app.schemas.agenda import ReminderSettings


class ReminderSettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(
        self,
        user_id: str,
    ) -> tuple[ReminderSettings, datetime | None]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT settings_json, updated_at
                FROM reminder_settings
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return ReminderSettings(), None
        return (
            ReminderSettings.model_validate_json(row["settings_json"]),
            datetime.fromisoformat(row["updated_at"]),
        )

    def save(
        self,
        *,
        user_id: str,
        settings: ReminderSettings,
        now: datetime,
    ) -> tuple[ReminderSettings, datetime]:
        timestamp = now.isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO users(id, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (user_id, timestamp, timestamp),
            )
            connection.execute(
                """
                INSERT INTO reminder_settings(
                    user_id, settings_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    settings_json = excluded.settings_json,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    json.dumps(
                        settings.model_dump(mode="json"),
                        ensure_ascii=False,
                    ),
                    timestamp,
                    timestamp,
                ),
            )
        return settings, now
