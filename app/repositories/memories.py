from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.repositories.database import Database
from app.schemas.memory import MemoryCreate, MemoryItem, MemoryUpdate


class MemoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list(
        self,
        user_id: str,
        *,
        enabled_only: bool = False,
    ) -> list[MemoryItem]:
        condition = "AND enabled = 1" if enabled_only else ""
        with self.database.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM user_memories
                WHERE user_id = ? {condition}
                ORDER BY updated_at DESC, label ASC
                """,
                (user_id,),
            ).fetchall()
        return [self._to_item(row) for row in rows]

    def upsert(
        self,
        *,
        user_id: str,
        payload: MemoryCreate,
        now: datetime,
    ) -> MemoryItem:
        timestamp = now.isoformat()
        memory_id = f"memory_{uuid4().hex}"
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
                INSERT INTO user_memories(
                    id, user_id, category, memory_key, label, value_json,
                    enabled, source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'explicit', ?, ?)
                ON CONFLICT(user_id, memory_key) DO UPDATE SET
                    category = excluded.category,
                    label = excluded.label,
                    value_json = excluded.value_json,
                    enabled = excluded.enabled,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    memory_id,
                    user_id,
                    payload.category,
                    payload.key,
                    payload.label,
                    json.dumps(payload.value, ensure_ascii=False),
                    int(payload.enabled),
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM user_memories
                WHERE user_id = ? AND memory_key = ?
                """,
                (user_id, payload.key),
            ).fetchone()
        return self._to_item(row)

    def update(
        self,
        *,
        user_id: str,
        memory_id: str,
        payload: MemoryUpdate,
        now: datetime,
    ) -> MemoryItem | None:
        fields: list[str] = []
        values: list[Any] = []
        if payload.label is not None:
            fields.append("label = ?")
            values.append(payload.label)
        if payload.value is not None:
            fields.append("value_json = ?")
            values.append(json.dumps(payload.value, ensure_ascii=False))
        if payload.enabled is not None:
            fields.append("enabled = ?")
            values.append(int(payload.enabled))
        if not fields:
            return self.get(user_id=user_id, memory_id=memory_id)
        fields.append("updated_at = ?")
        values.append(now.isoformat())
        values.extend([user_id, memory_id])
        with self.database.transaction() as connection:
            connection.execute(
                f"""
                UPDATE user_memories
                SET {", ".join(fields)}
                WHERE user_id = ? AND id = ?
                """,
                values,
            )
        return self.get(user_id=user_id, memory_id=memory_id)

    def get(
        self,
        *,
        user_id: str,
        memory_id: str,
    ) -> MemoryItem | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM user_memories
                WHERE user_id = ? AND id = ?
                """,
                (user_id, memory_id),
            ).fetchone()
        return self._to_item(row) if row else None

    def delete(self, *, user_id: str, memory_id: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM user_memories
                WHERE user_id = ? AND id = ?
                """,
                (user_id, memory_id),
            )
        return cursor.rowcount > 0

    @staticmethod
    def _to_item(row) -> MemoryItem:
        return MemoryItem(
            id=row["id"],
            user_id=row["user_id"],
            category=row["category"],
            key=row["memory_key"],
            label=row["label"],
            value=json.loads(row["value_json"]),
            enabled=bool(row["enabled"]),
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
