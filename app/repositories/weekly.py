from __future__ import annotations

import json
from datetime import date, datetime
from uuid import uuid4

from app.repositories.database import Database
from app.schemas.weekly import (
    AllocationStatus,
    CompletionEvent,
    CompletionEventCreate,
    CompletionEventType,
    DayAllocation,
    GoalStage,
    GoalStatus,
    StageStatus,
    WeeklyGoal,
    WeeklyPlan,
    WeeklyPlanMetrics,
    WeeklyPlanStatus,
    WeeklyTriggerType,
)


class WeeklyPlanRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, plan: WeeklyPlan) -> None:
        timestamp = plan.updated_at.isoformat()
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO users(id, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at
                """,
                (plan.user_id, timestamp, timestamp),
            )
            connection.execute(
                """
                INSERT INTO weekly_plans(
                    id, user_id, campus_id, week_start, week_end, timezone,
                    version, status, baseline_plan_id, trigger_type,
                    issues_json, metrics_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.id,
                    plan.user_id,
                    plan.campus_id,
                    plan.week_start.isoformat(),
                    plan.week_end.isoformat(),
                    plan.timezone,
                    plan.version,
                    plan.status.value,
                    plan.baseline_plan_id,
                    plan.trigger_type.value,
                    json.dumps(
                        [
                            item.model_dump(mode="json")
                            for item in plan.issues
                        ],
                        ensure_ascii=False,
                    ),
                    plan.metrics.model_dump_json(),
                    plan.created_at.isoformat(),
                    plan.updated_at.isoformat(),
                ),
            )
            for goal in plan.goals:
                connection.execute(
                    """
                    INSERT INTO weekly_goals(
                        id, weekly_plan_id, user_id, campus_id, week_start,
                        goal_json,
                        status, remaining_duration_min, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        goal.id,
                        plan.id,
                        goal.user_id,
                        goal.campus_id,
                        goal.week_start.isoformat(),
                        goal.model_dump_json(exclude={"stages"}),
                        goal.status.value,
                        goal.remaining_duration_min,
                        goal.created_at.isoformat(),
                        goal.updated_at.isoformat(),
                    ),
                )
                for stage in goal.stages:
                    connection.execute(
                        """
                        INSERT INTO goal_stages(
                            id, goal_id, stage_json, status,
                            remaining_duration_min, sequence,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            stage.id,
                            goal.id,
                            stage.model_dump_json(),
                            stage.status.value,
                            stage.remaining_duration_min,
                            stage.sequence,
                            stage.created_at.isoformat(),
                            stage.updated_at.isoformat(),
                        ),
                    )
            for allocation in plan.allocations:
                connection.execute(
                    """
                    INSERT INTO day_allocations(
                        id, weekly_plan_id, goal_id, stage_id,
                        allocation_json, allocation_date, status,
                        allocated_duration_min, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        allocation.id,
                        plan.id,
                        allocation.goal_id,
                        allocation.stage_id,
                        allocation.model_dump_json(),
                        allocation.date.isoformat(),
                        allocation.status.value,
                        allocation.allocated_duration_min,
                        allocation.created_at.isoformat(),
                        allocation.updated_at.isoformat(),
                    ),
                )
            connection.execute(
                """
                INSERT INTO weekly_plan_versions(
                    id, weekly_plan_id, version, snapshot_json, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"weekly_snapshot_{uuid4().hex}",
                    plan.id,
                    plan.version,
                    plan.model_dump_json(),
                    plan.created_at.isoformat(),
                ),
            )

    def get(self, plan_id: str) -> WeeklyPlan | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM weekly_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate(connection, row)

    def latest(
        self,
        *,
        user_id: str,
        campus_id: str,
        week_start: date,
    ) -> WeeklyPlan | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM weekly_plans
                WHERE user_id = ? AND campus_id = ? AND week_start = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (user_id, campus_id, week_start.isoformat()),
            ).fetchone()
            if row is None:
                return None
            return self._hydrate(connection, row)

    def versions(
        self,
        *,
        user_id: str,
        campus_id: str,
        week_start: date,
    ) -> list[WeeklyPlan]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM weekly_plans
                WHERE user_id = ? AND campus_id = ? AND week_start = ?
                ORDER BY version
                """,
                (user_id, campus_id, week_start.isoformat()),
            ).fetchall()
            return [self._hydrate(connection, row) for row in rows]

    def record_event(
        self,
        *,
        user_id: str,
        plan_id: str,
        payload: CompletionEventCreate,
        now: datetime,
    ) -> tuple[CompletionEvent, bool]:
        with self.database.transaction() as connection:
            existing = connection.execute(
                """
                SELECT event_json FROM completion_events
                WHERE user_id = ? AND client_event_id = ?
                """,
                (user_id, payload.client_event_id),
            ).fetchone()
            if existing is not None:
                return (
                    CompletionEvent.model_validate_json(
                        existing["event_json"]
                    ),
                    False,
                )
            plan_row = connection.execute(
                """
                SELECT id FROM weekly_plans
                WHERE id = ? AND user_id = ?
                """,
                (plan_id, user_id),
            ).fetchone()
            if plan_row is None:
                raise LookupError("WEEKLY_PLAN_NOT_FOUND")

            allocation_row = None
            if payload.allocation_id:
                allocation_row = connection.execute(
                    """
                    SELECT * FROM day_allocations
                    WHERE id = ? AND weekly_plan_id = ?
                    """,
                    (payload.allocation_id, plan_id),
                ).fetchone()
                if allocation_row is None:
                    raise LookupError("WEEKLY_ALLOCATION_NOT_FOUND")

            completed_duration = payload.completed_duration_min
            if allocation_row is not None and completed_duration:
                already = connection.execute(
                    """
                    SELECT COALESCE(SUM(
                        CAST(json_extract(
                            event_json,
                            '$.completed_duration_min'
                        ) AS INTEGER)
                    ), 0) AS total
                    FROM completion_events
                    WHERE allocation_id = ?
                      AND event_type IN ('completed', 'partial')
                    """,
                    (payload.allocation_id,),
                ).fetchone()["total"]
                available = max(
                    0,
                    allocation_row["allocated_duration_min"] - int(already),
                )
                completed_duration = min(completed_duration, available)

            event = CompletionEvent(
                id=f"completion_event_{uuid4().hex}",
                user_id=user_id,
                weekly_plan_id=plan_id,
                allocation_id=payload.allocation_id,
                event_type=payload.event_type,
                occurred_at=payload.occurred_at,
                completed_duration_min=completed_duration,
                remaining_duration_min=payload.remaining_duration_min,
                reason=payload.reason,
                client_event_id=payload.client_event_id,
                created_at=now,
            )
            connection.execute(
                """
                INSERT INTO completion_events(
                    id, user_id, weekly_plan_id, allocation_id, event_type,
                    event_json, client_event_id, occurred_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    user_id,
                    plan_id,
                    event.allocation_id,
                    event.event_type.value,
                    event.model_dump_json(),
                    event.client_event_id,
                    event.occurred_at.isoformat(),
                    event.created_at.isoformat(),
                ),
            )
            if allocation_row is not None:
                self._apply_event(
                    connection,
                    allocation_row=allocation_row,
                    event=event,
                    now=now,
                )
            return event, True

    @staticmethod
    def _apply_event(
        connection,
        *,
        allocation_row,
        event: CompletionEvent,
        now: datetime,
    ) -> None:
        allocation = DayAllocation.model_validate_json(
            allocation_row["allocation_json"]
        )
        if event.event_type in {
            CompletionEventType.SKIPPED,
            CompletionEventType.DELAYED,
        }:
            allocation.status = AllocationStatus.DEFERRED
        elif event.completed_duration_min > 0:
            total_row = connection.execute(
                """
                SELECT COALESCE(SUM(
                    CAST(json_extract(
                        event_json,
                        '$.completed_duration_min'
                    ) AS INTEGER)
                ), 0) AS total
                FROM completion_events
                WHERE allocation_id = ?
                  AND event_type IN ('completed', 'partial')
                """,
                (allocation.id,),
            ).fetchone()
            allocation.status = (
                AllocationStatus.COMPLETED
                if int(total_row["total"]) >= allocation.allocated_duration_min
                else AllocationStatus.SCHEDULED
            )
        allocation.updated_at = now
        connection.execute(
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
        if event.completed_duration_min <= 0:
            return

        stage_row = connection.execute(
            "SELECT * FROM goal_stages WHERE id = ?",
            (allocation.stage_id,),
        ).fetchone()
        goal_row = connection.execute(
            "SELECT * FROM weekly_goals WHERE id = ?",
            (allocation.goal_id,),
        ).fetchone()
        if stage_row is None or goal_row is None:
            return

        stage = GoalStage.model_validate_json(stage_row["stage_json"])
        stage.remaining_duration_min = max(
            0,
            stage.remaining_duration_min - event.completed_duration_min,
        )
        stage.status = (
            StageStatus.COMPLETED
            if stage.remaining_duration_min == 0
            else StageStatus.ACTIVE
        )
        stage.updated_at = now
        connection.execute(
            """
            UPDATE goal_stages
            SET stage_json = ?, status = ?, remaining_duration_min = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                stage.model_dump_json(),
                stage.status.value,
                stage.remaining_duration_min,
                now.isoformat(),
                stage.id,
            ),
        )

        goal = WeeklyGoal.model_validate_json(goal_row["goal_json"])
        goal.remaining_duration_min = max(
            0,
            goal.remaining_duration_min - event.completed_duration_min,
        )
        goal.status = (
            GoalStatus.COMPLETED
            if goal.remaining_duration_min == 0
            else GoalStatus.ACTIVE
        )
        goal.updated_at = now
        connection.execute(
            """
            UPDATE weekly_goals
            SET goal_json = ?, status = ?, remaining_duration_min = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                goal.model_dump_json(exclude={"stages"}),
                goal.status.value,
                goal.remaining_duration_min,
                now.isoformat(),
                goal.id,
            ),
        )

    @staticmethod
    def _hydrate(connection, row) -> WeeklyPlan:
        goal_rows = connection.execute(
            """
            SELECT * FROM weekly_goals
            WHERE weekly_plan_id = ?
            ORDER BY created_at, id
            """,
            (row["id"],),
        ).fetchall()
        goals: list[WeeklyGoal] = []
        for goal_row in goal_rows:
            stage_rows = connection.execute(
                """
                SELECT stage_json FROM goal_stages
                WHERE goal_id = ?
                ORDER BY sequence, id
                """,
                (goal_row["id"],),
            ).fetchall()
            payload = json.loads(goal_row["goal_json"])
            payload["stages"] = [
                json.loads(stage_row["stage_json"])
                for stage_row in stage_rows
            ]
            goals.append(WeeklyGoal.model_validate(payload))
        allocation_rows = connection.execute(
            """
            SELECT allocation_json FROM day_allocations
            WHERE weekly_plan_id = ?
            ORDER BY allocation_date, id
            """,
            (row["id"],),
        ).fetchall()
        return WeeklyPlan(
            id=row["id"],
            user_id=row["user_id"],
            campus_id=row["campus_id"],
            week_start=date.fromisoformat(row["week_start"]),
            week_end=date.fromisoformat(row["week_end"]),
            timezone=row["timezone"],
            version=row["version"],
            status=WeeklyPlanStatus(row["status"]),
            baseline_plan_id=row["baseline_plan_id"],
            trigger_type=WeeklyTriggerType(row["trigger_type"]),
            goals=goals,
            allocations=[
                DayAllocation.model_validate_json(
                    allocation_row["allocation_json"]
                )
                for allocation_row in allocation_rows
            ],
            issues=json.loads(row["issues_json"]),
            metrics=WeeklyPlanMetrics.model_validate_json(
                row["metrics_json"]
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
