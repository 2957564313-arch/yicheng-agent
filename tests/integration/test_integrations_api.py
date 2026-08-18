from pathlib import Path

from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.main import create_app


def integration_app(tmp_path: Path):
    return create_app(
        Settings(
            app_database_path=tmp_path / "app.db",
            app_checkpoint_database_path=tmp_path / "checkpoints.db",
            app_data_dir=BASE_DIR / "data",
            app_demo_dir=BASE_DIR / "fixtures",
            app_integration_api_key="integration-test-key",
            llm_enabled=False,
            live_route_enabled=False,
            live_weather_enabled=False,
        )
    )


def test_external_event_is_authenticated_idempotent_and_visible_in_agenda(
    tmp_path,
):
    with TestClient(integration_app(tmp_path)) as client:
        payload = {
            "source_system": "second-classroom",
            "external_event_id": "activity-2026-001",
            "user_id": "campus_student_001",
            "title": "创新创业讲座",
            "start_at": "2026-09-10T18:30:00+08:00",
            "end_at": "2026-09-10T20:00:00+08:00",
            "location_name": "学生活动中心报告厅",
            "kind": "activity",
            "notes": "二课系统同步",
        }
        assert client.put("/api/v1/integrations/events", json=payload).status_code == 401
        headers = {"X-Yicheng-Integration-Key": "integration-test-key"}

        created = client.put(
            "/api/v1/integrations/events",
            json=payload,
            headers=headers,
        )
        assert created.status_code == 200, created.text
        assert created.json()["operation"] == "created"
        event_id = created.json()["id"]

        repeated = client.put(
            "/api/v1/integrations/events",
            json=payload,
            headers=headers,
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["id"] == event_id
        assert repeated.json()["operation"] == "unchanged"

        payload["location_name"] = "科技馆一楼"
        updated = client.put(
            "/api/v1/integrations/events",
            json=payload,
            headers=headers,
        )
        assert updated.json()["operation"] == "updated"
        assert updated.json()["id"] == event_id

        agenda = client.get(
            "/api/v1/users/campus_student_001/agenda",
            params={"start_date": "2026-09-10", "end_date": "2026-09-10"},
        )
        assert agenda.status_code == 200, agenda.text
        external = [
            item for item in agenda.json()["items"]
            if item["source"] == "external"
        ]
        assert len(external) == 1
        assert external[0]["title"] == "创新创业讲座"
        assert external[0]["location_name"] == "科技馆一楼"
        assert external[0]["locked"] is True

        planned = client.post(
            "/api/v1/chat",
            json={
                "user_id": "campus_student_001",
                "thread_id": "external_constraint_thread",
                "query": "今天18点以后学习1小时，21点前结束。",
                "mode": "offline",
                "publish_to_agenda": True,
                "client_context": {"now": "2026-09-10T16:00:00+08:00"},
            },
        )
        assert planned.status_code == 200, planned.text
        plan = planned.json()["plan"]
        assert plan is not None
        fixed_external = [
            item for item in plan["items"]
            if (item.get("task_id") or "").startswith("external_")
        ]
        assert len(fixed_external) == 1
        assert fixed_external[0]["title"] == "创新创业讲座"
        study = next(
            item for item in plan["items"]
            if item["item_type"] == "task" and item not in fixed_external
        )
        assert (
            study["end_at"] <= fixed_external[0]["start_at"]
            or study["start_at"] >= fixed_external[0]["end_at"]
        )

        agenda_after_plan = client.get(
            "/api/v1/users/campus_student_001/agenda",
            params={"start_date": "2026-09-10", "end_date": "2026-09-10"},
        ).json()["items"]
        assert sum(
            item["title"] == "创新创业讲座"
            for item in agenda_after_plan
        ) == 1

        cancelled = client.delete(
            "/api/v1/integrations/second-classroom/events/activity-2026-001",
            params={"user_id": "campus_student_001"},
            headers=headers,
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["operation"] == "cancelled"
        after = client.get(
            "/api/v1/users/campus_student_001/agenda",
            params={"start_date": "2026-09-10", "end_date": "2026-09-10"},
        )
        assert not [
            item for item in after.json()["items"]
            if item["source"] == "external"
        ]


def test_integration_endpoint_is_disabled_without_a_configured_key(tmp_path):
    app = create_app(
        Settings(
            app_database_path=tmp_path / "disabled.db",
            app_checkpoint_database_path=tmp_path / "disabled-checkpoints.db",
            app_data_dir=BASE_DIR / "data",
            app_demo_dir=BASE_DIR / "fixtures",
        )
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/integrations/capabilities")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INTEGRATION_DISABLED"
