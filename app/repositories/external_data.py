from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.repositories.database import Database
from app.schemas.common import TaskFlexibility
from app.schemas.task import Task


class ExternalDataRepository:
    """Store the latest authoritative, non-calendar HDUHelp snapshots."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def replace_source(
        self,
        *,
        user_id: str,
        provider: str,
        source_kind: str,
        payload: Any,
        now: datetime,
    ) -> int:
        count = self._count(payload)
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
                INSERT INTO external_data_snapshots(
                    user_id, provider, source_kind, payload_json,
                    item_count, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, provider, source_kind) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    item_count = excluded.item_count,
                    synced_at = excluded.synced_at
                """,
                (
                    user_id,
                    provider,
                    source_kind,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    count,
                    timestamp,
                ),
            )
        return count

    def get(self, user_id: str, source_kind: str) -> Any | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM external_data_snapshots
                WHERE user_id = ? AND provider = 'hduhelp'
                  AND source_kind = ?
                """,
                (user_id, source_kind),
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["payload_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    def counts(self, user_id: str) -> dict[str, int]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_kind, item_count
                FROM external_data_snapshots
                WHERE user_id = ? AND provider = 'hduhelp'
                """,
                (user_id,),
            ).fetchall()
        return {row["source_kind"]: int(row["item_count"]) for row in rows}

    def planning_context(self, user_id: str) -> list[dict[str, Any]]:
        """Return bounded context records for planning without exposing secrets."""
        labels = {
            "school_time": "杭助当前教学周",
            "course_selection": "杭助选课信息",
            "library_attendance": "图书馆到馆习惯",
            "library_reading": "图书馆阅读记录",
            "library_rooms": "图书馆座位与房间",
            "volunteer": "志愿活动与本人活动",
            "sunrun": "阳光长跑进度",
            "subscriptions": "校园消息订阅",
            "empty_schedule_status": "空课表状态",
            "empty_schedule_favorites": "空课表收藏",
            "empty_schedule_rooms": "空课表协作房间",
            "feed": "杭助信息流",
        }
        records: list[dict[str, Any]] = []
        for source_kind, label in labels.items():
            payload = self.get(user_id, source_kind)
            if payload in (None, [], {}):
                continue
            records.append(
                {
                    "category": "hduhelp",
                    "label": label,
                    "key": f"hduhelp_{source_kind}",
                    "value": self._bounded(payload),
                    "source": "hduhelp_authoritative",
                }
            )
        return records

    def timetable_tasks_for_date(
        self,
        *,
        user_id: str,
        target_date: date,
        class_periods: dict[int, tuple[time, time]],
        timezone_name: str,
        effective_weekday: int | None,
    ) -> list[Task] | None:
        """Return courses from the synced HDUHelp term covering ``target_date``.

        ``None`` means no all-term snapshot exists yet, so callers may fall back
        to the legacy single-timetable store. An empty list is authoritative.
        """
        terms = self.get(user_id, "timetable_terms")
        if not isinstance(terms, list):
            return None
        if effective_weekday is None:
            return []
        selected = next(
            (
                term
                for term in terms
                if isinstance(term, dict)
                and str(term.get("term_start", ""))
                <= target_date.isoformat()
                <= str(term.get("term_end", ""))
            ),
            None,
        )
        if selected is None:
            return []
        try:
            term_start = date.fromisoformat(str(selected["term_start"]))
        except (KeyError, TypeError, ValueError):
            return []
        academic_week = ((target_date - term_start).days // 7) + 1
        timezone = ZoneInfo(timezone_name)
        tasks: list[Task] = []
        for index, entry in enumerate(selected.get("entries", [])):
            if not isinstance(entry, dict):
                continue
            try:
                weekday = int(entry.get("weekday"))
                start_period = int(entry.get("start_period"))
                end_period = int(entry.get("end_period"))
                weeks = [int(value) for value in entry.get("weeks", [])]
            except (TypeError, ValueError):
                continue
            if weekday != effective_weekday or (weeks and academic_week not in weeks):
                continue
            start_value = class_periods.get(start_period)
            end_value = class_periods.get(end_period)
            if not start_value or not end_value:
                continue
            start_at = datetime.combine(target_date, start_value[0], timezone)
            end_at = datetime.combine(target_date, end_value[1], timezone)
            title = str(entry.get("course_name", "")).strip()
            if not title:
                continue
            tasks.append(
                Task(
                    id=(
                        "hduhelp_course_"
                        f"{selected.get('school_year', '')}_{selected.get('semester', '')}_"
                        f"{academic_week}_{weekday}_{start_period}_{index}"
                    ),
                    title=title,
                    date=target_date,
                    duration_min=int((end_at - start_at).total_seconds() // 60),
                    location_raw=str(entry.get("location", "")).strip() or None,
                    fixed_start=start_at,
                    fixed_end=end_at,
                    flexibility=TaskFlexibility.FIXED,
                    importance=5,
                    tags=[
                        "course",
                        "hduhelp",
                        "hard_constraint",
                        f"period:{start_period}-{end_period}",
                    ],
                    notes="来自杭助同步课表，不可被规划器移动",
                )
            )
        return tasks

    def clear_provider(self, user_id: str, provider: str) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                "DELETE FROM external_data_snapshots "
                "WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )

    @staticmethod
    def _count(payload: Any) -> int:
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            for key in ("items", "list", "records", "rooms"):
                if isinstance(payload.get(key), list):
                    return len(payload[key])
            return 1 if payload else 0
        return 1 if payload is not None else 0

    @staticmethod
    def _bounded(payload: Any) -> Any:
        if isinstance(payload, list):
            return payload[:20]
        if isinstance(payload, dict):
            result = dict(payload)
            for key, value in tuple(result.items()):
                if isinstance(value, list) and len(value) > 20:
                    result[key] = value[:20]
            return result
        return payload
