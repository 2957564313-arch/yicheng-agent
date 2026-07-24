from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from app.repositories.database import Database
from app.schemas.plan import Plan


class PlanRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def ensure_user_and_thread(
        self,
        *,
        user_id: str,
        thread_id: str,
        now: datetime,
    ) -> None:
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
                INSERT INTO threads(id, user_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (thread_id, user_id, timestamp, timestamp),
            )

    def add_message(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        created_at: datetime,
    ) -> str:
        message_id = f"msg_{uuid4().hex}"
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO messages(id, thread_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    thread_id,
                    role,
                    content,
                    created_at.isoformat(),
                ),
            )
        return message_id

    def save(self, plan: Plan, parent_plan_id: str | None = None) -> None:
        plan_json = plan.model_dump_json()
        metrics_json = plan.metrics.model_dump_json()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO plans(
                    id, user_id, thread_id, parent_plan_id, plan_date,
                    status, version, plan_json, metrics_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.id,
                    plan.user_id,
                    plan.thread_id,
                    parent_plan_id,
                    plan.date.isoformat(),
                    plan.status.value,
                    plan.version,
                    plan_json,
                    metrics_json,
                    plan.created_at.isoformat(),
                ),
            )
            connection.executemany(
                """
                INSERT INTO plan_items(
                    id, plan_id, task_id, item_type, title, start_at, end_at,
                    location_id, item_json, sort_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item.id,
                        plan.id,
                        item.task_id,
                        item.item_type,
                        item.title,
                        item.start_at.isoformat(),
                        item.end_at.isoformat(),
                        item.location_id,
                        item.model_dump_json(),
                        index,
                    )
                    for index, item in enumerate(plan.items)
                ],
            )

    def get(self, plan_id: str) -> Plan | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT plan_json FROM plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        if row is None:
            return None
        return Plan.model_validate(json.loads(row["plan_json"]))

    def latest_for_thread(self, thread_id: str) -> Plan | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT plan_json
                FROM plans
                WHERE thread_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        return Plan.model_validate(json.loads(row["plan_json"]))

    def reset_user(self, user_id: str) -> None:
        """Reset demo conversations while preserving long-term user memories."""

        with self.database.transaction() as connection:
            thread_rows = connection.execute(
                "SELECT id FROM threads WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            thread_ids = [row["id"] for row in thread_rows]
            if thread_ids:
                placeholders = ",".join("?" for _ in thread_ids)
                plan_rows = connection.execute(
                    f"SELECT id FROM plans WHERE thread_id IN ({placeholders})",
                    thread_ids,
                ).fetchall()
                plan_ids = [row["id"] for row in plan_rows]
                if plan_ids:
                    plan_placeholders = ",".join("?" for _ in plan_ids)
                    connection.execute(
                        "DELETE FROM plan_items "
                        f"WHERE plan_id IN ({plan_placeholders})",
                        plan_ids,
                    )
                connection.execute(
                    f"DELETE FROM runs WHERE thread_id IN ({placeholders})",
                    thread_ids,
                )
                connection.execute(
                    f"DELETE FROM plans WHERE thread_id IN ({placeholders})",
                    thread_ids,
                )
                connection.execute(
                    f"DELETE FROM messages WHERE thread_id IN ({placeholders})",
                    thread_ids,
                )
                connection.execute(
                    f"DELETE FROM threads WHERE id IN ({placeholders})",
                    thread_ids,
                )
