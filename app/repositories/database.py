from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    preferences_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'explicit',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    memory_key TEXT NOT NULL,
    label TEXT NOT NULL,
    value_json TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    source TEXT NOT NULL DEFAULT 'explicit',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, memory_key)
);

CREATE INDEX IF NOT EXISTS idx_user_memories_user_enabled
ON user_memories(user_id, enabled);

CREATE TABLE IF NOT EXISTS timetables (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    term_start TEXT,
    term_end TEXT,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS course_sessions (
    id TEXT PRIMARY KEY,
    timetable_id TEXT NOT NULL REFERENCES timetables(id) ON DELETE CASCADE,
    course_name TEXT NOT NULL,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),
    start_period INTEGER NOT NULL CHECK (start_period BETWEEN 1 AND 13),
    end_period INTEGER NOT NULL CHECK (end_period BETWEEN 1 AND 13),
    location_raw TEXT,
    weeks_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'import',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_course_sessions_timetable_day
ON course_sessions(timetable_id, weekday, start_period);

CREATE TABLE IF NOT EXISTS academic_calendar_overrides (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_date TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('no_class', 'normal', 'makeup')),
    replacement_weekday INTEGER CHECK (
        replacement_weekday IS NULL
        OR replacement_weekday BETWEEN 1 AND 7
    ),
    label TEXT NOT NULL,
    source_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, event_date)
);

CREATE INDEX IF NOT EXISTS idx_academic_calendar_user_date
ON academic_calendar_overrides(user_id, event_date);

CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    parent_thread_id TEXT REFERENCES threads(id) ON DELETE SET NULL,
    forked_from_message_id TEXT,
    deleted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_threads_user_updated
ON threads(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_thread_created
ON messages(thread_id, created_at);

CREATE TABLE IF NOT EXISTS external_events (
    id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    location_name TEXT,
    kind TEXT NOT NULL DEFAULT 'activity',
    notes TEXT,
    source_url TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'cancelled')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_system, external_event_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_external_events_user_time
ON external_events(user_id, status, start_at, end_at);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    thread_id TEXT NOT NULL REFERENCES threads(id),
    parent_plan_id TEXT REFERENCES plans(id),
    plan_date TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    plan_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    agenda_published INTEGER NOT NULL DEFAULT 0 CHECK (agenda_published IN (0, 1)),
    source_message_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plans_thread_created
ON plans(thread_id, created_at);

CREATE TABLE IF NOT EXISTS plan_items (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    task_id TEXT,
    item_type TEXT NOT NULL,
    title TEXT NOT NULL,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    location_id TEXT,
    item_json TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_items_plan_order
ON plan_items(plan_id, sort_order);

CREATE TABLE IF NOT EXISTS reminder_settings (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    settings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    trace_id TEXT NOT NULL,
    thread_id TEXT NOT NULL REFERENCES threads(id),
    input_json TEXT NOT NULL,
    output_json TEXT,
    status TEXT NOT NULL,
    node_trace_json TEXT NOT NULL,
    model_name TEXT,
    route_source TEXT,
    weather_source TEXT,
    latency_ms INTEGER,
    error_code TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_trace_id ON runs(trace_id);

CREATE TABLE IF NOT EXISTS evaluation_results (
    id TEXT PRIMARY KEY,
    suite_name TEXT NOT NULL,
    case_id TEXT NOT NULL,
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    metrics_json TEXT NOT NULL,
    failure_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_goals (
    id TEXT PRIMARY KEY,
    weekly_plan_id TEXT NOT NULL REFERENCES weekly_plans(id)
        ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    campus_id TEXT NOT NULL,
    week_start TEXT NOT NULL,
    goal_json TEXT NOT NULL,
    status TEXT NOT NULL,
    remaining_duration_min INTEGER NOT NULL CHECK (
        remaining_duration_min >= 0
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_weekly_goals_plan
ON weekly_goals(weekly_plan_id);

CREATE TABLE IF NOT EXISTS goal_stages (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL REFERENCES weekly_goals(id) ON DELETE CASCADE,
    stage_json TEXT NOT NULL,
    status TEXT NOT NULL,
    remaining_duration_min INTEGER NOT NULL CHECK (
        remaining_duration_min >= 0
    ),
    sequence INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goal_stages_goal_sequence
ON goal_stages(goal_id, sequence);

CREATE TABLE IF NOT EXISTS weekly_plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    campus_id TEXT NOT NULL,
    week_start TEXT NOT NULL,
    week_end TEXT NOT NULL,
    timezone TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    status TEXT NOT NULL,
    baseline_plan_id TEXT REFERENCES weekly_plans(id),
    trigger_type TEXT NOT NULL,
    issues_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, campus_id, week_start, version)
);

CREATE INDEX IF NOT EXISTS idx_weekly_plans_user_week_version
ON weekly_plans(user_id, campus_id, week_start, version DESC);

CREATE TABLE IF NOT EXISTS day_allocations (
    id TEXT PRIMARY KEY,
    weekly_plan_id TEXT NOT NULL REFERENCES weekly_plans(id)
        ON DELETE CASCADE,
    goal_id TEXT NOT NULL REFERENCES weekly_goals(id) ON DELETE CASCADE,
    stage_id TEXT NOT NULL REFERENCES goal_stages(id) ON DELETE CASCADE,
    allocation_json TEXT NOT NULL,
    allocation_date TEXT NOT NULL,
    status TEXT NOT NULL,
    allocated_duration_min INTEGER NOT NULL CHECK (
        allocated_duration_min >= 5
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_day_allocations_plan_date
ON day_allocations(weekly_plan_id, allocation_date);

CREATE TABLE IF NOT EXISTS completion_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    weekly_plan_id TEXT NOT NULL REFERENCES weekly_plans(id)
        ON DELETE CASCADE,
    allocation_id TEXT REFERENCES day_allocations(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    event_json TEXT NOT NULL,
    client_event_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(user_id, client_event_id)
);

CREATE INDEX IF NOT EXISTS idx_completion_events_plan_time
ON completion_events(weekly_plan_id, occurred_at);

CREATE TABLE IF NOT EXISTS weekly_plan_versions (
    id TEXT PRIMARY KEY,
    weekly_plan_id TEXT NOT NULL REFERENCES weekly_plans(id)
        ON DELETE CASCADE,
    version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(weekly_plan_id, version)
);
"""


class _ClosingConnection(sqlite3.Connection):
    """Commit or roll back like sqlite3's context manager, then release the file."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=10,
            isolation_level=None,
            factory=_ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(SCHEMA_SQL)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(plans)")
            }
            if "agenda_published" not in columns:
                connection.execute(
                    "ALTER TABLE plans ADD COLUMN agenda_published "
                    "INTEGER NOT NULL DEFAULT 0 "
                    "CHECK (agenda_published IN (0, 1))"
                )
                connection.execute(
                    "UPDATE plans SET agenda_published = 1"
                )
            if "source_message_id" not in columns:
                connection.execute(
                    "ALTER TABLE plans ADD COLUMN source_message_id TEXT"
                )
            thread_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(threads)")
            }
            if "parent_thread_id" not in thread_columns:
                connection.execute(
                    "ALTER TABLE threads ADD COLUMN parent_thread_id TEXT "
                    "REFERENCES threads(id) ON DELETE SET NULL"
                )
            if "forked_from_message_id" not in thread_columns:
                connection.execute(
                    "ALTER TABLE threads ADD COLUMN forked_from_message_id TEXT"
                )
            if "deleted_at" not in thread_columns:
                connection.execute(
                    "ALTER TABLE threads ADD COLUMN deleted_at TEXT"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_threads_parent "
                "ON threads(parent_thread_id)"
            )
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
