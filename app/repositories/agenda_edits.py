from __future__ import annotations

from datetime import date, datetime, time
from uuid import uuid4

from app.repositories.database import Database
from app.schemas.agenda import AgendaItem, AgendaItemCreate


class AgendaEditRepository:
    """User-owned agenda additions and non-destructive plan overrides."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        *,
        user_id: str,
        payload: AgendaItemCreate,
        now: datetime,
        target_item_id: str | None = None,
    ) -> AgendaItem:
        item_id = f"agenda_manual_{uuid4().hex}"
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
            if target_item_id:
                connection.execute(
                    "DELETE FROM agenda_item_edits WHERE user_id = ? AND target_item_id = ?",
                    (user_id, target_item_id),
                )
            connection.execute(
                """
                INSERT INTO agenda_item_edits(
                    id, user_id, target_item_id, title, start_at, end_at,
                    location_name, kind, deleted, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    item_id,
                    user_id,
                    target_item_id,
                    payload.title.strip(),
                    payload.start_at.isoformat(),
                    payload.end_at.isoformat(),
                    payload.location_name.strip() if payload.location_name else None,
                    payload.kind,
                    timestamp,
                    timestamp,
                ),
            )
        item = self.get(user_id=user_id, item_id=item_id)
        assert item is not None
        return item

    def update(
        self,
        *,
        user_id: str,
        item_id: str,
        payload: AgendaItemCreate,
        now: datetime,
    ) -> AgendaItem | None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE agenda_item_edits
                SET title = ?, start_at = ?, end_at = ?, location_name = ?,
                    kind = ?, deleted = 0, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (
                    payload.title.strip(),
                    payload.start_at.isoformat(),
                    payload.end_at.isoformat(),
                    payload.location_name.strip() if payload.location_name else None,
                    payload.kind,
                    now.isoformat(),
                    item_id,
                    user_id,
                ),
            )
        return self.get(user_id=user_id, item_id=item_id) if cursor.rowcount else None

    def suppress(
        self,
        *,
        user_id: str,
        target: AgendaItem,
        now: datetime,
    ) -> None:
        payload = AgendaItemCreate(
            title=target.title,
            start_at=target.start_at,
            end_at=target.end_at,
            location_name=target.location_name,
            kind=target.kind,
        )
        item = self.create(
            user_id=user_id,
            payload=payload,
            now=now,
            target_item_id=target.id,
        )
        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE agenda_item_edits SET deleted = 1 WHERE id = ?",
                (item.id,),
            )

    def delete_manual(self, *, user_id: str, item_id: str, now: datetime) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE agenda_item_edits SET deleted = 1, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now.isoformat(), item_id, user_id),
            )
        return cursor.rowcount > 0

    def get(self, *, user_id: str, item_id: str) -> AgendaItem | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM agenda_item_edits WHERE id = ? AND user_id = ?",
                (item_id, user_id),
            ).fetchone()
        return self._to_item(row) if row is not None and not row["deleted"] else None

    def list_state(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> tuple[set[str], list[AgendaItem]]:
        start_at = datetime.combine(start_date, time.min).isoformat()
        end_at = datetime.combine(end_date, time.max).isoformat()
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agenda_item_edits
                WHERE user_id = ?
                  AND (target_item_id IS NOT NULL OR (end_at >= ? AND start_at <= ?))
                ORDER BY start_at, end_at, title
                """,
                (user_id, start_at, end_at),
            ).fetchall()
        suppressed = {row["target_item_id"] for row in rows if row["target_item_id"]}
        visible = [
            self._to_item(row)
            for row in rows
            if not row["deleted"] and row["end_at"] >= start_at and row["start_at"] <= end_at
        ]
        return suppressed, visible

    @staticmethod
    def _to_item(row) -> AgendaItem:
        return AgendaItem(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            start_at=datetime.fromisoformat(row["start_at"]),
            end_at=datetime.fromisoformat(row["end_at"]),
            location_name=row["location_name"],
            source="manual",
            kind=row["kind"],
            locked=False,
            notes="手动添加" if row["target_item_id"] is None else "手动调整自对话安排",
        )
