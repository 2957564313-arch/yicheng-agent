from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.repositories.database import Database
from app.schemas.conversation import (
    ConversationDetail,
    ConversationMessage,
    ConversationThread,
)
from app.schemas.plan import Plan


class ConversationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_threads(self, *, user_id: str, limit: int = 50) -> list[ConversationThread]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.*,
                       COUNT(m.id) AS message_count,
                       (
                           SELECT content FROM messages last
                           WHERE last.thread_id = t.id
                           ORDER BY last.created_at DESC, last.rowid DESC
                           LIMIT 1
                       ) AS last_message
                FROM threads t
                LEFT JOIN messages m ON m.thread_id = t.id
                WHERE t.user_id = ? AND t.deleted_at IS NULL
                GROUP BY t.id
                HAVING COUNT(m.id) > 0
                ORDER BY t.updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [self._thread(row) for row in rows]

    def get_detail(
        self,
        *,
        user_id: str,
        thread_id: str,
    ) -> ConversationDetail | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT t.*,
                       COUNT(m.id) AS message_count,
                       (
                           SELECT content FROM messages last
                           WHERE last.thread_id = t.id
                           ORDER BY last.created_at DESC, last.rowid DESC
                           LIMIT 1
                       ) AS last_message
                FROM threads t
                LEFT JOIN messages m ON m.thread_id = t.id
                WHERE t.id = ? AND t.user_id = ? AND t.deleted_at IS NULL
                GROUP BY t.id
                """,
                (thread_id, user_id),
            ).fetchone()
            if row is None:
                return None
            messages = connection.execute(
                """
                SELECT id, thread_id, role, content, created_at
                FROM messages WHERE thread_id = ?
                ORDER BY created_at, rowid
                """,
                (thread_id,),
            ).fetchall()
        return ConversationDetail(
            thread=self._thread(row),
            messages=[
                ConversationMessage(
                    id=item["id"],
                    thread_id=item["thread_id"],
                    role=item["role"],
                    content=item["content"],
                    created_at=datetime.fromisoformat(item["created_at"]),
                )
                for item in messages
            ],
        )

    def rename(
        self,
        *,
        user_id: str,
        thread_id: str,
        title: str,
        now: datetime,
    ) -> ConversationThread | None:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                UPDATE threads SET title = ?, updated_at = ?
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                (title, now.isoformat(), thread_id, user_id),
            )
        if cursor.rowcount == 0:
            return None
        detail = self.get_detail(user_id=user_id, thread_id=thread_id)
        return detail.thread if detail else None

    def delete(
        self,
        *,
        user_id: str,
        thread_id: str,
        now: datetime,
    ) -> bool:
        with self.database.transaction() as connection:
            row = connection.execute(
                """
                SELECT id FROM threads
                WHERE id = ? AND user_id = ? AND deleted_at IS NULL
                """,
                (thread_id, user_id),
            ).fetchone()
            if row is None:
                return False
            connection.execute(
                "DELETE FROM messages WHERE thread_id = ?",
                (thread_id,),
            )
            connection.execute(
                """
                UPDATE threads
                SET deleted_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), now.isoformat(), thread_id),
            )
        return True

    def fork(
        self,
        *,
        user_id: str,
        thread_id: str,
        from_message_id: str,
        now: datetime,
    ) -> tuple[ConversationThread, Plan | None]:
        branch_id = f"thread_{uuid4().hex}"
        with self.database.transaction() as connection:
            source = connection.execute(
                """
                SELECT m.rowid AS source_rowid, m.created_at, m.role,
                       t.title, t.user_id
                FROM messages m
                JOIN threads t ON t.id = m.thread_id
                WHERE m.id = ? AND m.thread_id = ?
                  AND t.deleted_at IS NULL
                """,
                (from_message_id, thread_id),
            ).fetchone()
            if source is None or source["user_id"] != user_id:
                raise LookupError("MESSAGE_NOT_FOUND")
            if source["role"] != "user":
                raise ValueError("only user messages can be edited")
            timestamp = now.isoformat()
            title = source["title"] or "对话分支"
            connection.execute(
                """
                INSERT INTO threads(
                    id, user_id, title, parent_thread_id,
                    forked_from_message_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch_id,
                    user_id,
                    f"{title} · 分支",
                    thread_id,
                    from_message_id,
                    timestamp,
                    timestamp,
                ),
            )
            ancestors = connection.execute(
                """
                SELECT role, content, created_at FROM messages
                WHERE thread_id = ? AND rowid < ?
                ORDER BY rowid
                """,
                (thread_id, source["source_rowid"]),
            ).fetchall()
            connection.executemany(
                """
                INSERT INTO messages(id, thread_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        f"msg_{uuid4().hex}",
                        branch_id,
                        item["role"],
                        item["content"],
                        item["created_at"],
                    )
                    for item in ancestors
                ],
            )
            plan_row = connection.execute(
                """
                SELECT p.plan_json FROM plans p
                JOIN messages m ON m.id = p.source_message_id
                WHERE p.thread_id = ? AND m.rowid < ?
                ORDER BY m.rowid DESC, p.version DESC
                LIMIT 1
                """,
                (thread_id, source["source_rowid"]),
            ).fetchone()
            if plan_row is None:
                plan_row = connection.execute(
                    """
                    SELECT plan_json FROM plans
                    WHERE thread_id = ? AND source_message_id IS NULL
                      AND created_at < ?
                    ORDER BY created_at DESC, version DESC
                    LIMIT 1
                    """,
                    (thread_id, source["created_at"]),
                ).fetchone()
        detail = self.get_detail(user_id=user_id, thread_id=branch_id)
        assert detail is not None
        baseline = Plan.model_validate_json(plan_row["plan_json"]) if plan_row else None
        return detail.thread, baseline

    @staticmethod
    def _thread(row) -> ConversationThread:
        return ConversationThread(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            parent_thread_id=row["parent_thread_id"],
            forked_from_message_id=row["forked_from_message_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            message_count=int(row["message_count"]),
            last_message=row["last_message"],
        )
