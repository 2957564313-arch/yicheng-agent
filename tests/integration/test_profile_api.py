from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_api_demos import build_test_app


CSV_CONTENT = """课程名称,星期,开始节次,结束节次,地点,周次
高等数学,星期五,1,2,第六教学楼,1-16
大学英语,星期五,3,4,第七教学楼,1-16
"""


def _create_source_profile(client: TestClient) -> None:
    assert client.post(
        "/api/v1/users/backup_source/memories",
        json={
            "category": "habit",
            "key": "usual_bedtime",
            "label": "常用就寝时间",
            "value": "23:00",
            "enabled": True,
        },
    ).status_code == 201
    assert client.post(
        "/api/v1/users/backup_source/timetable/import",
        json={
            "name": "备份测试课表",
            "format": "csv",
            "content": CSV_CONTENT,
            "term_start": "2026-07-20",
            "term_end": "2026-11-30",
        },
    ).status_code == 201
    assert client.post(
        "/api/v1/users/backup_source/calendar-overrides",
        json={
            "date": "2026-07-31",
            "action": "no_class",
            "label": "学校临时停课",
            "source_ref": "测试通知",
        },
    ).status_code == 201
    assert client.put(
        "/api/v1/users/backup_source/reminders/settings",
        json={
            "enabled": True,
            "browser_notifications": False,
            "bedtime_enabled": True,
            "course_lead_min": 35,
            "early_course_wakeup_min": 95,
            "meeting_lead_min": 20,
            "study_lead_min": 15,
            "exercise_lead_min": 15,
            "task_lead_min": 10,
            "bedtime_lead_min": 30,
            "quiet_start": "23:00:00",
            "quiet_end": "06:30:00",
        },
    ).status_code == 200
    generated = client.post(
        "/api/v1/chat",
        json={
            "user_id": "backup_source",
            "thread_id": "backup_source_thread",
            "query": "2026年7月25日14点去图书馆自习2小时。",
            "mode": "offline",
            "client_context": {
                "now": "2026-07-24T20:00:00+08:00",
            },
        },
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["current_plan_saved"] is True


def test_profile_backup_restores_long_term_personal_data(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        _create_source_profile(client)

        exported = client.get(
            "/api/v1/users/backup_source/profile",
            params={"thread_id": "backup_source_thread"},
        )
        assert exported.status_code == 200, exported.text
        backup = exported.json()
        assert backup["product"] == "yicheng-agent"
        assert backup["schema_version"] == "1.0"
        assert len(backup["memories"]) == 1
        assert len(backup["timetable"]["entries"]) == 2
        assert len(backup["calendar_overrides"]) == 1
        assert backup["reminder_settings"]["course_lead_min"] == 35
        assert backup["current_plan"]["date"] == "2026-07-25"
        assert backup["current_plan_published"] is True

        backup["thread_id"] = "backup_target_thread"
        restored = client.post(
            "/api/v1/users/backup_target/profile/restore",
            json=backup,
        )
        assert restored.status_code == 200, restored.text
        result = restored.json()
        assert result["memories_restored"] == 1
        assert result["timetable_entries_restored"] == 2
        assert result["calendar_overrides_restored"] == 1
        assert result["reminder_settings_restored"] is True
        assert result["current_plan_restored"] is True
        assert result["current_plan_published"] is True

        target = client.get(
            "/api/v1/users/backup_target/profile",
            params={"thread_id": "backup_target_thread"},
        )
        assert target.status_code == 200, target.text
        restored_profile = target.json()
        assert restored_profile["user_id"] == "backup_target"
        assert restored_profile["thread_id"] == "backup_target_thread"
        assert restored_profile["memories"][0]["value"] == "23:00"
        assert len(restored_profile["timetable"]["entries"]) == 2
        assert restored_profile["calendar_overrides"][0]["action"] == (
            "no_class"
        )
        assert (
            restored_profile["reminder_settings"]["early_course_wakeup_min"]
            == 95
        )
        assert restored_profile["current_plan"]["user_id"] == "backup_target"
        assert restored_profile["current_plan"]["thread_id"] == (
            "backup_target_thread"
        )
        assert restored_profile["current_plan_published"] is True

        agenda = client.get(
            "/api/v1/users/backup_target/agenda",
            params={
                "start_date": "2026-07-24",
                "end_date": "2026-07-25",
            },
        )
        assert agenda.status_code == 200, agenda.text
        payload = agenda.json()
        assert payload["summary"]["course_count"] == 2
        assert any(
            item["title"] == "图书馆自习"
            for item in payload["items"]
        )
        assert any(
            reminder["kind"] == "bedtime"
            for reminder in payload["reminders"]
        )


def test_profile_restore_rejects_invalid_or_oversized_backup(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        wrong_version = client.post(
            "/api/v1/users/invalid_backup/profile/restore",
            json={
                "schema_version": "2.0",
                "thread_id": "invalid_backup_thread",
            },
        )
        assert wrong_version.status_code == 422
        assert wrong_version.json()["error"]["code"] == "INVALID_REQUEST"

        oversized = client.post(
            "/api/v1/users/invalid_backup/profile/restore",
            json={
                "schema_version": "1.0",
                "thread_id": "invalid_backup_thread",
                "memories": [
                    {
                        "category": "preference",
                        "key": f"preference_{index}",
                        "label": f"偏好{index}",
                        "value": index,
                        "enabled": True,
                    }
                    for index in range(101)
                ],
            },
        )
        assert oversized.status_code == 422
        assert oversized.json()["error"]["code"] == "INVALID_REQUEST"
