from __future__ import annotations

import json
from datetime import date, datetime, time
from uuid import uuid4

from app.repositories.database import Database
from app.schemas.agenda import AgendaItem
from app.schemas.common import TaskFlexibility
from app.schemas.task import Task


class ExternalAgendaRepository:
    """Authoritative agenda records mirrored from a connected campus account."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def replace_source(
        self,
        *,
        user_id: str,
        provider: str,
        source_kind: str,
        items: list[dict],
        now: datetime,
    ) -> int:
        """Replace one fully-fetched source so remote cancellations disappear."""
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
                DELETE FROM external_agenda_items
                WHERE user_id = ? AND provider = ? AND source_kind = ?
                """,
                (user_id, provider, source_kind),
            )
            for item in items:
                connection.execute(
                    """
                    INSERT INTO external_agenda_items(
                        id, user_id, provider, source_kind, external_id,
                        title, start_at, end_at, location_name, status,
                        payload_json, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"external_agenda_{uuid4().hex}",
                        user_id,
                        provider,
                        source_kind,
                        item["external_id"],
                        item["title"],
                        item["start_at"].isoformat(),
                        item["end_at"].isoformat(),
                        item.get("location_name"),
                        item.get("status", "active"),
                        json.dumps(item.get("payload", {}), ensure_ascii=False),
                        timestamp,
                    ),
                )
        return len(items)

    def list_range(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[AgendaItem]:
        start_at = datetime.combine(start_date, time.min).isoformat()
        end_at = datetime.combine(end_date, time.max).isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM external_agenda_items
                WHERE user_id = ? AND end_at >= ? AND start_at <= ?
                ORDER BY start_at, end_at, title
                """,
                (user_id, start_at, end_at),
            ).fetchall()
        return [
            AgendaItem(
                id=row["id"],
                user_id=user_id,
                title=row["title"],
                start_at=datetime.fromisoformat(row["start_at"]),
                end_at=datetime.fromisoformat(row["end_at"]),
                location_name=row["location_name"],
                source="external",
                kind=self._kind(row["source_kind"]),
                locked=True,
                task_id=f"external_{row['source_kind']}_{row['external_id']}",
                notes="来自杭电助手，以校园系统记录为准",
            )
            for row in rows
        ]

    def counts(self, user_id: str) -> dict[str, int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_kind, COUNT(*) AS count
                FROM external_agenda_items
                WHERE user_id = ? AND provider = 'hduhelp'
                GROUP BY source_kind
                """,
                (user_id,),
            ).fetchall()
        return {row["source_kind"]: int(row["count"]) for row in rows}

    def tasks_for_date(self, user_id: str, target_date: date) -> list[Task]:
        return [
            Task(
                id=f"external_{item.id[-20:]}",
                title=item.title,
                date=target_date,
                duration_min=int(
                    (item.end_at - item.start_at).total_seconds() // 60
                ),
                location_raw=item.location_name,
                fixed_start=item.start_at,
                fixed_end=item.end_at,
                flexibility=TaskFlexibility.FIXED,
                importance=5,
                tags=["hduhelp", "authoritative", item.kind],
                notes="来自杭电助手，以校园系统记录为准",
            )
            for item in self.list_range(
                user_id=user_id,
                start_date=target_date,
                end_date=target_date,
            )
        ]

    def clear_provider(self, user_id: str, provider: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM external_agenda_items WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )

    @staticmethod
    def _kind(source_kind: str) -> str:
        return {
            "library_reservation": "study",
            "second_classroom": "activity",
            "exam": "course",
            "volunteer": "activity",
        }.get(source_kind, "activity")
