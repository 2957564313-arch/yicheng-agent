from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from app.repositories.database import Database
from app.schemas.calendar import (
    AcademicDayContext,
    CalendarOverride,
    CalendarOverrideCreate,
)
from app.schemas.common import DataSource


class AcademicCalendarRepository:
    def __init__(self, database: Database, national_path: Path) -> None:
        self.database = database
        payload = json.loads(national_path.read_text(encoding="utf-8"))
        self._days = payload.get("days", {})
        self._calendar_year = int(payload.get("calendar_year", 0))
        self._verified_at = (
            date.fromisoformat(payload["verified_at"])
            if payload.get("verified_at")
            else None
        )
        source = payload.get("source", {})
        self._source_ref = source.get("url")

    def list_overrides(self, user_id: str) -> list[CalendarOverride]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM academic_calendar_overrides
                WHERE user_id = ?
                ORDER BY event_date, updated_at
                """,
                (user_id,),
            ).fetchall()
        return [self._to_override(row) for row in rows]

    def upsert_override(
        self,
        *,
        user_id: str,
        payload: CalendarOverrideCreate,
        now: datetime,
    ) -> CalendarOverride:
        timestamp = now.isoformat()
        override_id = f"calendar_{uuid4().hex}"
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
                INSERT INTO academic_calendar_overrides(
                    id, user_id, event_date, action, replacement_weekday,
                    label, source_ref, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, event_date) DO UPDATE SET
                    action = excluded.action,
                    replacement_weekday = excluded.replacement_weekday,
                    label = excluded.label,
                    source_ref = excluded.source_ref,
                    updated_at = excluded.updated_at
                """,
                (
                    override_id,
                    user_id,
                    payload.date.isoformat(),
                    payload.action,
                    payload.replacement_weekday,
                    payload.label,
                    payload.source_ref,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM academic_calendar_overrides
                WHERE user_id = ? AND event_date = ?
                """,
                (user_id, payload.date.isoformat()),
            ).fetchone()
        return self._to_override(row)

    def delete_override(self, *, user_id: str, event_date: date) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM academic_calendar_overrides
                WHERE user_id = ? AND event_date = ?
                """,
                (user_id, event_date.isoformat()),
            )
        return cursor.rowcount > 0

    def resolve(
        self,
        *,
        user_id: str,
        target_date: date,
        client_overrides: list[CalendarOverrideCreate] | None = None,
    ) -> AcademicDayContext:
        overrides = {
            item.date: item
            for item in self.list_overrides(user_id)
        }
        for item in client_overrides or []:
            overrides[item.date] = item
        override = overrides.get(target_date)
        national = self._days.get(target_date.isoformat())
        if override is not None:
            day_type = (
                national.get("type", "normal")
                if national
                else "normal"
            )
            effective_weekday = {
                "no_class": None,
                "normal": target_date.isoweekday(),
                "makeup": override.replacement_weekday,
            }[override.action]
            return AcademicDayContext(
                date=target_date,
                day_type=day_type,
                course_action=override.action,
                label=override.label,
                effective_weekday=effective_weekday,
                source=DataSource.USER,
                source_ref=override.source_ref,
            )
        if national and national.get("type") == "holiday":
            return AcademicDayContext(
                date=target_date,
                day_type="holiday",
                course_action="no_class",
                label=national.get("name"),
                effective_weekday=None,
                source=DataSource.STRUCTURED,
                source_ref=self._source_ref,
                verified_at=self._verified_at,
            )
        if national and national.get("type") == "adjusted_workday":
            return AcademicDayContext(
                date=target_date,
                day_type="adjusted_workday",
                course_action="awaiting_school_notice",
                label=national.get("name"),
                effective_weekday=None,
                source=DataSource.STRUCTURED,
                source_ref=self._source_ref,
                verified_at=self._verified_at,
            )
        if self._calendar_year and target_date.year != self._calendar_year:
            return AcademicDayContext(
                date=target_date,
                day_type="unknown",
                course_action="normal",
                label=f"{target_date.year}年法定节假日数据尚未核验",
                effective_weekday=target_date.isoweekday(),
                source=DataSource.UNKNOWN,
            )
        return AcademicDayContext(
            date=target_date,
            day_type="normal",
            course_action="normal",
            effective_weekday=target_date.isoweekday(),
            source=DataSource.STRUCTURED,
        )

    @staticmethod
    def _to_override(row) -> CalendarOverride:
        return CalendarOverride(
            id=row["id"],
            user_id=row["user_id"],
            date=date.fromisoformat(row["event_date"]),
            action=row["action"],
            replacement_weekday=row["replacement_weekday"],
            label=row["label"],
            source_ref=row["source_ref"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
