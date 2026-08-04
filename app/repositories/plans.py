from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from hashlib import sha256
from uuid import uuid4

from app.repositories.database import Database
from app.repositories.exceptions import (
    WeeklyGroundingSnapshotChanged,
    WeeklyPlanSuperseded,
)
from app.schemas.common import PlanStatus
from app.schemas.plan import Plan
from app.schemas.weekly import AllocationStatus, DayAllocation


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
        with self.database.transaction() as connection:
            self._ensure_user_and_thread_on_connection(
                connection,
                user_id=user_id,
                thread_id=thread_id,
                now=now,
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

    def save(
        self,
        plan: Plan,
        parent_plan_id: str | None = None,
        *,
        agenda_published: bool = False,
    ) -> None:
        with self.database.transaction() as connection:
            self._insert_on_connection(
                connection,
                plan=plan,
                parent_plan_id=parent_plan_id,
                agenda_published=agenda_published,
            )

    def set_agenda_published(
        self,
        *,
        plan_id: str,
        user_id: str,
        published: bool,
    ) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE plans SET agenda_published = ? "
                "WHERE id = ? AND user_id = ? AND status = 'valid'",
                (int(published), plan_id, user_id),
            )
        return cursor.rowcount > 0

    def is_agenda_published(self, plan_id: str, user_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT agenda_published FROM plans "
                "WHERE id = ? AND user_id = ?",
                (plan_id, user_id),
            ).fetchone()
        return bool(row and row["agenda_published"])

    def publish_weekly_day(
        self,
        *,
        weekly_plan_id: str,
        user_id: str,
        target_date: date,
        allocation_ids: list[str],
        allocation_fingerprints: dict[str, str],
        expected_task_ids: set[str],
        plan: Plan,
        now: datetime,
    ) -> tuple[Plan, bool]:
        """Atomically publish and bind one validated weekly day.

        Scheduling remains outside the transaction.  ``BEGIN IMMEDIATE`` in
        ``Database.transaction`` serializes the short publication step, so a
        concurrent loser observes and returns the winner instead of inserting
        another agenda-visible plan.
        """

        requested_ids = set(allocation_ids)
        if not requested_ids or len(requested_ids) != len(allocation_ids):
            raise ValueError("weekly grounding allocation ids must be unique")
        if set(allocation_fingerprints) != requested_ids:
            raise ValueError("weekly grounding fingerprints are incomplete")
        self._validate_weekly_candidate(
            plan=plan,
            user_id=user_id,
            target_date=target_date,
            expected_task_ids=expected_task_ids,
        )

        with self.database.transaction() as connection:
            owner = connection.execute(
                """
                SELECT id, campus_id, week_start FROM weekly_plans
                WHERE id = ? AND user_id = ?
                """,
                (weekly_plan_id, user_id),
            ).fetchone()
            if owner is None:
                raise LookupError("WEEKLY_PLAN_NOT_FOUND")
            latest = connection.execute(
                """
                SELECT id FROM weekly_plans
                WHERE user_id = ? AND campus_id = ? AND week_start = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (user_id, owner["campus_id"], owner["week_start"]),
            ).fetchone()
            if latest is None or latest["id"] != weekly_plan_id:
                raise WeeklyPlanSuperseded(
                    "weekly plan was superseded during daily grounding"
                )

            rows = connection.execute(
                """
                SELECT id, status, allocation_json
                FROM day_allocations
                WHERE weekly_plan_id = ? AND allocation_date = ?
                ORDER BY id
                """,
                (weekly_plan_id, target_date.isoformat()),
            ).fetchall()
            current = {
                row["id"]: DayAllocation.model_validate_json(
                    row["allocation_json"]
                )
                for row in rows
                if row["status"]
                not in {
                    AllocationStatus.COMPLETED.value,
                    AllocationStatus.CANCELLED.value,
                    AllocationStatus.DEFERRED.value,
                }
            }
            if set(current) != requested_ids:
                raise WeeklyGroundingSnapshotChanged(
                    "active weekly allocations changed during daily grounding"
                )

            bound_plan_ids = {
                allocation.daily_plan_id
                for allocation in current.values()
                if allocation.daily_plan_id
            }
            existing = self._matching_weekly_plan_on_connection(
                connection,
                plan_ids=bound_plan_ids,
                thread_id=None,
                user_id=user_id,
                target_date=target_date,
                expected_task_ids=expected_task_ids,
            )
            if existing is not None:
                self._bind_allocations_on_connection(
                    connection,
                    allocations=current,
                    daily_plan_id=existing.id,
                    now=now,
                )
                return existing, False

            current_fingerprints = {
                allocation_id: self.weekly_allocation_fingerprint(allocation)
                for allocation_id, allocation in current.items()
            }
            if current_fingerprints != allocation_fingerprints:
                raise WeeklyGroundingSnapshotChanged(
                    "weekly allocation details changed during daily grounding"
                )

            legacy = self._matching_weekly_plan_on_connection(
                connection,
                plan_ids=set(),
                thread_id=plan.thread_id,
                user_id=user_id,
                target_date=target_date,
                expected_task_ids=expected_task_ids,
            )
            if legacy is not None:
                self._bind_allocations_on_connection(
                    connection,
                    allocations=current,
                    daily_plan_id=legacy.id,
                    now=now,
                )
                return legacy, False

            self._ensure_user_and_thread_on_connection(
                connection,
                user_id=user_id,
                thread_id=plan.thread_id,
                now=now,
            )
            self._insert_on_connection(
                connection,
                plan=plan,
                agenda_published=True,
            )
            self._bind_allocations_on_connection(
                connection,
                allocations=current,
                daily_plan_id=plan.id,
                now=now,
            )
        return plan, True

    @staticmethod
    def weekly_allocation_fingerprint(allocation: DayAllocation) -> str:
        """Stable fingerprint for stale-snapshot detection at publication."""

        return sha256(
            allocation.model_dump_json().encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _ensure_user_and_thread_on_connection(
        connection: sqlite3.Connection,
        *,
        user_id: str,
        thread_id: str,
        now: datetime,
    ) -> None:
        timestamp = now.isoformat()
        connection.execute(
            """
            INSERT INTO users(id, created_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (user_id, timestamp, timestamp),
        )
        thread = connection.execute(
            "SELECT user_id FROM threads WHERE id = ?",
            (thread_id,),
        ).fetchone()
        if thread is not None and thread["user_id"] != user_id:
            raise ValueError("thread belongs to another user")
        connection.execute(
            """
            INSERT INTO threads(id, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (thread_id, user_id, timestamp, timestamp),
        )

    @staticmethod
    def _insert_on_connection(
        connection: sqlite3.Connection,
        *,
        plan: Plan,
        parent_plan_id: str | None = None,
        agenda_published: bool = False,
    ) -> None:
        connection.execute(
            """
            INSERT INTO plans(
                id, user_id, thread_id, parent_plan_id, plan_date,
                status, version, plan_json, metrics_json,
                agenda_published, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.id,
                plan.user_id,
                plan.thread_id,
                parent_plan_id,
                plan.date.isoformat(),
                plan.status.value,
                plan.version,
                plan.model_dump_json(),
                plan.metrics.model_dump_json(),
                int(agenda_published),
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

    @classmethod
    def _matching_weekly_plan_on_connection(
        cls,
        connection: sqlite3.Connection,
        *,
        plan_ids: set[str],
        thread_id: str | None,
        user_id: str,
        target_date: date,
        expected_task_ids: set[str],
    ) -> Plan | None:
        candidates: list[Plan] = []
        if len(plan_ids) == 1:
            row = connection.execute(
                """
                SELECT plan_json FROM plans
                WHERE id = ? AND user_id = ? AND plan_date = ?
                  AND status = 'valid'
                """,
                (next(iter(plan_ids)), user_id, target_date.isoformat()),
            ).fetchone()
            if row is not None:
                candidates.append(
                    Plan.model_validate_json(row["plan_json"])
                )

        # Also repairs a legacy plan written before binding was made atomic.
        if thread_id is not None:
            row = connection.execute(
                """
                SELECT plan_json FROM plans
                WHERE thread_id = ? AND user_id = ? AND plan_date = ?
                  AND status = 'valid'
                ORDER BY created_at DESC, version DESC
                LIMIT 1
                """,
                (thread_id, user_id, target_date.isoformat()),
            ).fetchone()
            if row is not None:
                candidate = Plan.model_validate_json(row["plan_json"])
                if all(item.id != candidate.id for item in candidates):
                    candidates.append(candidate)

        return next(
            (
                candidate
                for candidate in candidates
                if cls._weekly_task_ids(candidate) == expected_task_ids
            ),
            None,
        )

    @staticmethod
    def _bind_allocations_on_connection(
        connection: sqlite3.Connection,
        *,
        allocations: dict[str, DayAllocation],
        daily_plan_id: str,
        now: datetime,
    ) -> None:
        for allocation in allocations.values():
            allocation.daily_plan_id = daily_plan_id
            allocation.status = AllocationStatus.SCHEDULED
            allocation.updated_at = now
            cursor = connection.execute(
                """
                UPDATE day_allocations
                SET allocation_json = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    allocation.model_dump_json(),
                    allocation.status.value,
                    now.isoformat(),
                    allocation.id,
                ),
            )
            if cursor.rowcount != 1:
                raise WeeklyGroundingSnapshotChanged(
                    "weekly allocation disappeared during daily grounding"
                )

    @classmethod
    def _validate_weekly_candidate(
        cls,
        *,
        plan: Plan,
        user_id: str,
        target_date: date,
        expected_task_ids: set[str],
    ) -> None:
        if (
            plan.status != PlanStatus.VALID
            or plan.user_id != user_id
            or plan.date != target_date
            or cls._weekly_task_ids(plan) != expected_task_ids
        ):
            raise ValueError("invalid weekly daily plan publication")

    @staticmethod
    def _weekly_task_ids(plan: Plan) -> set[str]:
        return {
            item.task_id
            for item in plan.items
            if item.item_type == "task"
            and item.task_id
            and item.task_id.startswith("weekly_")
        }

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

    def latest_for_user_range(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[Plan]:
        """Return the newest valid daily plan for every date in a range."""

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT plan_json
                FROM (
                    SELECT
                        plan_json,
                        plan_date,
                        ROW_NUMBER() OVER (
                            PARTITION BY plan_date
                            ORDER BY created_at DESC, version DESC
                        ) AS rank_in_date
                    FROM plans
                    WHERE user_id = ?
                      AND plan_date BETWEEN ? AND ?
                      AND status = 'valid'
                      AND agenda_published = 1
                )
                WHERE rank_in_date = 1
                ORDER BY plan_date
                """,
                (
                    user_id,
                    start_date.isoformat(),
                    end_date.isoformat(),
                ),
            ).fetchall()
        return [
            Plan.model_validate(json.loads(row["plan_json"]))
            for row in rows
        ]

    def clear_thread(self, *, user_id: str, thread_id: str) -> int:
        with self.database.transaction() as connection:
            plan_rows = connection.execute(
                """
                SELECT id FROM plans
                WHERE user_id = ? AND thread_id = ?
                """,
                (user_id, thread_id),
            ).fetchall()
            plan_ids = [row["id"] for row in plan_rows]
            if plan_ids:
                placeholders = ",".join("?" for _ in plan_ids)
                connection.execute(
                    "DELETE FROM plan_items "
                    f"WHERE plan_id IN ({placeholders})",
                    plan_ids,
                )
            cursor = connection.execute(
                """
                DELETE FROM plans
                WHERE user_id = ? AND thread_id = ?
                """,
                (user_id, thread_id),
            )
        return cursor.rowcount

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
