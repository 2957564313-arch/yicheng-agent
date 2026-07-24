from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.repositories.database import Database


class RunRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def start(
        self,
        *,
        request_id: str,
        trace_id: str,
        thread_id: str,
        input_payload: dict[str, Any],
        created_at: datetime,
        model_name: str | None,
    ) -> str:
        run_id = f"run_{uuid4().hex}"
        with self.database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    id, request_id, trace_id, thread_id, input_json, status,
                    node_trace_json, model_name, created_at
                )
                VALUES (?, ?, ?, ?, ?, 'running', '[]', ?, ?)
                """,
                (
                    run_id,
                    request_id,
                    trace_id,
                    thread_id,
                    json.dumps(input_payload, ensure_ascii=False),
                    model_name,
                    created_at.isoformat(),
                ),
            )
        return run_id

    def finish(
        self,
        *,
        run_id: str,
        output_payload: dict[str, Any] | None,
        status: str,
        node_trace: list[dict[str, Any]],
        completed_at: datetime,
        latency_ms: int,
        route_source: str | None = None,
        weather_source: str | None = None,
        error_code: str | None = None,
        model_name: str | None = None,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE runs
                SET output_json = ?, status = ?, node_trace_json = ?,
                    completed_at = ?, latency_ms = ?, route_source = ?,
                    weather_source = ?, error_code = ?,
                    model_name = COALESCE(?, model_name)
                WHERE id = ?
                """,
                (
                    (
                        json.dumps(output_payload, ensure_ascii=False)
                        if output_payload is not None
                        else None
                    ),
                    status,
                    json.dumps(node_trace, ensure_ascii=False),
                    completed_at.isoformat(),
                    latency_ms,
                    route_source,
                    weather_source,
                    error_code,
                    model_name,
                    run_id,
                ),
            )
