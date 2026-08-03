from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.integration.test_api_demos import build_test_app


def test_historical_semester_import_keeps_timetable_agenda_and_weather(
    tmp_path,
):
    """Regression path for a prior semester with an explicit demo snapshot."""
    timetable = {
        "entries": [
            {
                "course_name": "2026春季数据结构",
                "weekday": 3,
                "start_period": 3,
                "end_period": 4,
                "location": "第六教学楼",
                "weeks": [8],
            }
        ]
    }
    with TestClient(build_test_app(tmp_path)) as client:
        imported = client.post(
            "/api/v1/users/historical_semester/timetable/import",
            json={
                "name": "2026上半学期课表",
                "format": "json",
                "content": json.dumps(timetable, ensure_ascii=False),
                "term_start": "2026-02-23",
                "term_end": "2026-06-14",
            },
        )
        assert imported.status_code == 201, imported.text
        assert imported.json()["imported_count"] == 1

        agenda = client.get(
            "/api/v1/users/historical_semester/agenda",
            params={"start_date": "2026-04-15", "end_date": "2026-04-15"},
        )
        assert agenda.status_code == 200, agenda.text
        agenda_items = agenda.json()["items"]
        assert any(
            item["title"] == "2026春季数据结构"
            and item["start_at"].startswith("2026-04-15T10:00:00")
            for item in agenda_items
        )

        planned = client.post(
            "/api/v1/chat",
            json={
                "user_id": "historical_semester",
                "thread_id": "historical_semester_plan",
                "query": (
                    "2026年4月15日下课后去图书馆学习30分钟，"
                    "再去操场跑步30分钟，请结合天气安排。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-04-15T08:00:00+08:00"
                },
            },
        )
        assert planned.status_code == 200, planned.text
        payload = planned.json()
        assert payload["data_freshness"]["weather"] == "demo_fixture"
        assert not any(
            warning["code"] == "API_DEGRADED"
            and warning.get("details", {}).get("provider") == "weather"
            for warning in payload["warnings"]
        )
        assert any(
            item["task_id"].startswith("timetable_")
            for item in payload["plan"]["items"]
            if item["item_type"] == "task"
        )
