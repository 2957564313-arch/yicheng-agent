from __future__ import annotations

import json
from datetime import date, datetime
from uuid import uuid4

from app.repositories.database import Database
from app.schemas.integration import ExternalEventResponse, ExternalEventUpsert


class ExternalEventRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def upsert(
        self,
        payload: ExternalEventUpsert,
        *,
        now: datetime,
    ) -> ExternalEventResponse:
        canonical = payload.model_dump(mode="json")
        payload_json = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
        with self.database.transaction() as connection:
            timestamp = now.isoformat()
            connection.execute(
                """
                INSERT INTO users(id, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (payload.user_id, timestamp, timestamp),
            )
            existing = connection.execute(
                """
                SELECT * FROM external_events
                WHERE source_system = ? AND external_event_id = ?
                  AND user_id = ?
                """,
                (
                    payload.source_system,
                    payload.external_event_id,
                    payload.user_id,
                ),
            ).fetchone()
            event_id = existing["id"] if existing else f"ext_{uuid4().hex}"
            created_at = existing["created_at"] if existing else timestamp
            unchanged = bool(
                existing
                and existing["payload_json"] == payload_json
                and existing["status"] == "active"
            )
            if not unchanged:
                connection.execute(
                    """
                    INSERT INTO external_events(
                        id, source_system, external_event_id, user_id, title,
                        start_at, end_at, location_name, kind, notes,
                        source_url, status, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                    ON CONFLICT(source_system, external_event_id, user_id)
                    DO UPDATE SET
                        title = excluded.title,
                        start_at = excluded.start_at,
                        end_at = excluded.end_at,
                        location_name = excluded.location_name,
                        kind = excluded.kind,
                        notes = excluded.notes,
                        source_url = excluded.source_url,
                        status = 'active',
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        event_id,
                        payload.source_system,
                        payload.external_event_id,
                        payload.user_id,
                        payload.title,
                        payload.start_at.isoformat(),
                        payload.end_at.isoformat(),
                        payload.location_name,
                        payload.kind,
                        payload.notes,
                        str(payload.source_url) if payload.source_url else None,
                        payload_json,
                        created_at,
                        timestamp,
                    ),
                )
            row = connection.execute(
                "SELECT * FROM external_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        return self._response(
            row,
            operation="unchanged" if unchanged else ("updated" if existing else "created"),
        )

    def cancel(
        self,
        *,
        source_system: str,
        external_event_id: str,
        user_id: str,
        now: datetime,
    ) -> ExternalEventResponse | None:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT * FROM external_events
                WHERE source_system = ? AND external_event_id = ?
                  AND user_id = ?
                """,
                (source_system.lower(), external_event_id, user_id),
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE external_events SET status = 'cancelled', updated_at = ? "
                "WHERE id = ?",
                (now.isoformat(), row["id"]),
            )
            updated = connection.execute(
                "SELECT * FROM external_events WHERE id = ?",
                (row["id"],),
            ).fetchone()
        return self._response(updated, operation="cancelled")

    def active_for_range(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[ExternalEventResponse]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM external_events
                WHERE user_id = ? AND status = 'active'
                  AND substr(start_at, 1, 10) <= ?
                  AND substr(end_at, 1, 10) >= ?
                ORDER BY start_at, end_at, title
                """,
                (user_id, end_date.isoformat(), start_date.isoformat()),
            ).fetchall()
        return [self._response(row, operation="unchanged") for row in rows]

    @staticmethod
    def _response(row, *, operation: str) -> ExternalEventResponse:
        return ExternalEventResponse(
            id=row["id"],
            source_system=row["source_system"],
            external_event_id=row["external_event_id"],
            user_id=row["user_id"],
            title=row["title"],
            start_at=datetime.fromisoformat(row["start_at"]),
            end_at=datetime.fromisoformat(row["end_at"]),
            location_name=row["location_name"],
            kind=row["kind"],
            notes=row["notes"],
            source_url=row["source_url"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            operation=operation,
        )
