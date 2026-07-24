from __future__ import annotations

import json
from datetime import date, datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.repositories.database import Database
from app.schemas.common import TaskFlexibility
from app.schemas.task import Task
from app.schemas.timetable import (
    CourseSession,
    CourseSessionCreate,
    TimetableInfo,
    TimetableResponse,
)


class TimetableRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, user_id: str) -> TimetableResponse:
        with self.database.connect() as connection:
            timetable_row = connection.execute(
                "SELECT * FROM timetables WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if timetable_row is None:
                return TimetableResponse()
            rows = connection.execute(
                """
                SELECT * FROM course_sessions
                WHERE timetable_id = ?
                ORDER BY weekday, start_period, course_name
                """,
                (timetable_row["id"],),
            ).fetchall()
        return TimetableResponse(
            timetable=self._to_timetable(timetable_row),
            entries=[self._to_session(row) for row in rows],
        )

    def replace(
        self,
        *,
        user_id: str,
        name: str,
        term_start: date | None,
        term_end: date | None,
        enabled: bool,
        entries: list[CourseSessionCreate],
        now: datetime,
    ) -> TimetableResponse:
        current = self.get(user_id)
        timetable_id = (
            current.timetable.id
            if current.timetable
            else f"timetable_{uuid4().hex}"
        )
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
                INSERT INTO timetables(
                    id, user_id, name, term_start, term_end, enabled,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name = excluded.name,
                    term_start = excluded.term_start,
                    term_end = excluded.term_end,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    timetable_id,
                    user_id,
                    name,
                    term_start.isoformat() if term_start else None,
                    term_end.isoformat() if term_end else None,
                    int(enabled),
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "DELETE FROM course_sessions WHERE timetable_id = ?",
                (timetable_id,),
            )
            for entry in entries:
                connection.execute(
                    """
                    INSERT INTO course_sessions(
                        id, timetable_id, course_name, weekday,
                        start_period, end_period, location_raw, weeks_json,
                        source, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'import', ?)
                    """,
                    (
                        f"course_session_{uuid4().hex}",
                        timetable_id,
                        entry.course_name,
                        entry.weekday,
                        entry.start_period,
                        entry.end_period,
                        entry.location,
                        json.dumps(entry.weeks, ensure_ascii=False),
                        timestamp,
                    ),
                )
        return self.get(user_id)

    def clear(self, user_id: str) -> bool:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM timetables WHERE user_id = ?",
                (user_id,),
            )
        return cursor.rowcount > 0

    def tasks_for_date(
        self,
        *,
        user_id: str,
        target_date: date,
        class_periods: dict[int, tuple[time, time]],
        timezone_name: str,
        effective_weekday: int | None = None,
    ) -> list[Task]:
        response = self.get(user_id)
        timetable = response.timetable
        if not timetable or not timetable.enabled:
            return []
        if timetable.term_start and target_date < timetable.term_start:
            return []
        if timetable.term_end and target_date > timetable.term_end:
            return []
        if effective_weekday is None:
            return []
        academic_week = (
            ((target_date - timetable.term_start).days // 7) + 1
            if timetable.term_start
            else None
        )
        timezone = ZoneInfo(timezone_name)
        tasks: list[Task] = []
        for entry in response.entries:
            if entry.weekday != effective_weekday:
                continue
            if entry.weeks and (
                academic_week is None or academic_week not in entry.weeks
            ):
                continue
            start_value = class_periods.get(entry.start_period)
            end_value = class_periods.get(entry.end_period)
            if not start_value or not end_value:
                continue
            start_at = datetime.combine(target_date, start_value[0], timezone)
            end_at = datetime.combine(target_date, end_value[1], timezone)
            tasks.append(
                Task(
                    id=f"timetable_{entry.id[-12:]}",
                    title=entry.course_name,
                    date=target_date,
                    duration_min=int((end_at - start_at).total_seconds() // 60),
                    location_raw=entry.location,
                    fixed_start=start_at,
                    fixed_end=end_at,
                    flexibility=TaskFlexibility.FIXED,
                    importance=5,
                    tags=[
                        "course",
                        "personal_timetable",
                        "hard_constraint",
                        (
                            f"period:{entry.start_period}"
                            f"-{entry.end_period}"
                        ),
                    ],
                    notes="来自你导入并启用的个人课表，不可被规划器移动",
                )
            )
        return tasks

    @staticmethod
    def _to_timetable(row) -> TimetableInfo:
        return TimetableInfo(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            term_start=(
                date.fromisoformat(row["term_start"])
                if row["term_start"]
                else None
            ),
            term_end=(
                date.fromisoformat(row["term_end"])
                if row["term_end"]
                else None
            ),
            enabled=bool(row["enabled"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _to_session(row) -> CourseSession:
        return CourseSession(
            id=row["id"],
            timetable_id=row["timetable_id"],
            course_name=row["course_name"],
            weekday=row["weekday"],
            start_period=row["start_period"],
            end_period=row["end_period"],
            location=row["location_raw"],
            weeks=json.loads(row["weeks_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
