from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_api_demos import build_test_app

CSV_CONTENT = """课程名称,星期,开始节次,结束节次,地点,周次
高等数学,星期五,1,2,第六教学楼,1-16
大学英语,星期五,3,4,第七教学楼,1-16
"""


def test_saved_plan_becomes_a_personal_agenda(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        generated = client.post("/api/v1/demos/demo_01_normal/run")
        assert generated.status_code == 200, generated.text

        response = client.get(
            "/api/v1/users/demo_user/agenda",
            params={
                "start_date": "2026-07-24",
                "end_date": "2026-07-24",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["summary"]["planned_item_count"] == 3
        assert payload["summary"]["study_minutes"] == 120
        assert payload["summary"]["exercise_minutes"] == 30
        assert {item["title"] for item in payload["items"]} >= {
            "图书馆自习",
            "取快递",
            "跑步",
        }
        assert any(
            reminder["title"] == "准备进入专注时段"
            for reminder in payload["reminders"]
        )


def test_generated_plan_requires_explicit_agenda_publication(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        generated = client.post(
            "/api/v1/chat",
            json={
                "user_id": "publish_user",
                "thread_id": "publish_thread",
                "query": "2026年7月25日14点去图书馆自习2小时。",
                "mode": "offline",
                "publish_to_agenda": False,
                "client_context": {
                    "now": "2026-07-24T20:00:00+08:00",
                },
            },
        )
        assert generated.status_code == 200, generated.text
        assert generated.json()["current_plan_saved"] is True

        before = client.get(
            "/api/v1/users/publish_user/agenda",
            params={"start_date": "2026-07-25", "end_date": "2026-07-25"},
        )
        assert before.status_code == 200, before.text
        assert not any(
            item["source"] == "plan" for item in before.json()["items"]
        )

        context = {
            "schema_version": "1.0",
            "thread_id": "publish_thread",
            "current_plan": generated.json()["plan"],
            "current_plan_published": True,
        }
        published = client.post(
            "/api/v1/users/publish_user/agenda/contextual",
            params={"start_date": "2026-07-25", "end_date": "2026-07-25"},
            json=context,
        )
        assert published.status_code == 200, published.text
        assert any(
            item["title"] == "图书馆自习"
            for item in published.json()["items"]
        )


def test_manual_agenda_item_can_be_added_edited_and_deleted(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        created = client.post(
            "/api/v1/users/manual_user/agenda/items",
            json={
                "title": "小组讨论",
                "start_at": "2026-07-24T14:00:00+08:00",
                "end_at": "2026-07-24T15:00:00+08:00",
                "location_name": "第六教学楼",
                "kind": "meeting",
            },
        )
        assert created.status_code == 201, created.text
        item_id = created.json()["item"]["id"]
        assert created.json()["item"]["source"] == "manual"
        assert created.json()["item"]["locked"] is False

        updated = client.put(
            f"/api/v1/users/manual_user/agenda/items/{item_id}",
            json={
                "title": "项目讨论",
                "start_at": "2026-07-24T15:30:00+08:00",
                "end_at": "2026-07-24T16:30:00+08:00",
                "location_name": "第六教学楼北416",
                "kind": "meeting",
                "original_start_at": "2026-07-24T14:00:00+08:00",
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["item"]["title"] == "项目讨论"
        assert updated.json()["item"]["start_at"] == "2026-07-24T15:30:00+08:00"

        agenda = client.get(
            "/api/v1/users/manual_user/agenda",
            params={"start_date": "2026-07-24", "end_date": "2026-07-24"},
        )
        assert [item["title"] for item in agenda.json()["items"]] == ["项目讨论"]

        deleted = client.delete(
            f"/api/v1/users/manual_user/agenda/items/{item_id}",
            params={"original_start_at": "2026-07-24T15:30:00+08:00"},
        )
        assert deleted.status_code == 200, deleted.text
        agenda = client.get(
            "/api/v1/users/manual_user/agenda",
            params={"start_date": "2026-07-24", "end_date": "2026-07-24"},
        )
        assert agenda.json()["items"] == []


def test_plan_item_override_is_non_destructive_and_can_be_removed(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert client.post("/api/v1/demos/demo_01_normal/run").status_code == 200
        agenda = client.get(
            "/api/v1/users/demo_user/agenda",
            params={"start_date": "2026-07-24", "end_date": "2026-07-24"},
        ).json()
        original = next(item for item in agenda["items"] if item["title"] == "跑步")

        updated = client.put(
            f"/api/v1/users/demo_user/agenda/items/{original['id']}",
            json={
                "title": "东操场跑步",
                "start_at": "2026-07-24T17:00:00+08:00",
                "end_at": "2026-07-24T17:40:00+08:00",
                "location_name": "东操场",
                "kind": "exercise",
                "original_start_at": original["start_at"],
            },
        )
        assert updated.status_code == 200, updated.text
        replacement = updated.json()["item"]
        assert replacement["source"] == "manual"
        assert replacement["notes"] == "手动调整自对话安排"

        changed = client.get(
            "/api/v1/users/demo_user/agenda",
            params={"start_date": "2026-07-24", "end_date": "2026-07-24"},
        ).json()["items"]
        assert not any(item["id"] == original["id"] for item in changed)
        assert any(item["title"] == "东操场跑步" for item in changed)

        deleted = client.delete(
            f"/api/v1/users/demo_user/agenda/items/{replacement['id']}",
            params={"original_start_at": replacement["start_at"]},
        )
        assert deleted.status_code == 200, deleted.text
        after = client.get(
            "/api/v1/users/demo_user/agenda",
            params={"start_date": "2026-07-24", "end_date": "2026-07-24"},
        ).json()["items"]
        assert not any(item["id"] == original["id"] for item in after)
        assert not any(item["id"] == replacement["id"] for item in after)


def test_course_items_are_locked_against_manual_edit_and_delete(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        imported = client.post(
            "/api/v1/users/locked_course_user/timetable/import",
            json={
                "name": "我的课表",
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
                "term_end": "2026-11-30",
            },
        )
        assert imported.status_code == 201, imported.text
        agenda = client.get(
            "/api/v1/users/locked_course_user/agenda",
            params={"start_date": "2026-07-24", "end_date": "2026-07-24"},
        ).json()
        course = next(item for item in agenda["items"] if item["source"] == "course")
        payload = {
            "title": course["title"],
            "start_at": "2026-07-24T09:00:00+08:00",
            "end_at": "2026-07-24T10:00:00+08:00",
            "location_name": course["location_name"],
            "kind": "course",
            "original_start_at": course["start_at"],
        }
        updated = client.put(
            f"/api/v1/users/locked_course_user/agenda/items/{course['id']}",
            json=payload,
        )
        assert updated.status_code == 409, updated.text
        assert updated.json()["error"]["code"] == "AGENDA_ITEM_LOCKED"

        deleted = client.delete(
            f"/api/v1/users/locked_course_user/agenda/items/{course['id']}",
            params={"original_start_at": course["start_at"]},
        )
        assert deleted.status_code == 409, deleted.text
        assert deleted.json()["error"]["code"] == "AGENDA_ITEM_LOCKED"


def test_imported_early_course_gets_wakeup_and_class_reminders(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        imported = client.post(
            "/api/v1/users/agenda_course_user/timetable/import",
            json={
                "name": "我的课表",
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
                "term_end": "2026-11-30",
            },
        )
        assert imported.status_code == 201, imported.text

        response = client.get(
            "/api/v1/users/agenda_course_user/agenda",
            params={
                "start_date": "2026-07-24",
                "end_date": "2026-07-24",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        courses = [
            item for item in payload["items"] if item["kind"] == "course"
        ]
        assert len(courses) == 2
        first_course_reminders = [
            item
            for item in payload["reminders"]
            if item["agenda_item_id"] == courses[0]["id"]
        ]
        assert {item["kind"] for item in first_course_reminders} == {
            "wakeup",
            "prepare",
        }
        assert any(
            item["notify_at"] == "2026-07-24T06:50:00+08:00"
            for item in first_course_reminders
        )
        assert any(
            item["notify_at"] == "2026-07-24T07:45:00+08:00"
            for item in first_course_reminders
        )


def test_contextual_agenda_reminders_and_ical_hydrate_browser_snapshot(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        imported = client.post(
            "/api/v1/users/context_source/timetable/import",
            json={
                "name": "浏览器快照课表",
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
                "term_end": "2026-11-30",
            },
        )
        assert imported.status_code == 201
        saved_memory = client.post(
            "/api/v1/users/context_source/memories",
            json={
                "category": "habit",
                "key": "usual_bedtime",
                "label": "常用就寝时间",
                "value": "23:00",
                "enabled": True,
            },
        )
        assert saved_memory.status_code == 201
        generated = client.post(
            "/api/v1/chat",
            json={
                "user_id": "context_source",
                "thread_id": "context_source_thread",
                "query": "2026年7月25日14点去图书馆自习2小时。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T20:00:00+08:00"
                },
            },
        )
        assert generated.status_code == 200, generated.text
        imported_data = imported.json()
        memory_data = saved_memory.json()
        context = {
            "schema_version": "1.0",
            "thread_id": "context_target_thread",
            "memories": [{
                "category": memory_data["category"],
                "key": memory_data["key"],
                "label": memory_data["label"],
                "value": memory_data["value"],
                "enabled": memory_data["enabled"],
            }],
            "timetable": {
                "name": imported_data["timetable"]["name"],
                "term_start": imported_data["timetable"]["term_start"],
                "term_end": imported_data["timetable"]["term_end"],
                "enabled": imported_data["timetable"]["enabled"],
                "entries": [{
                    "course_name": item["course_name"],
                    "weekday": item["weekday"],
                    "start_period": item["start_period"],
                    "end_period": item["end_period"],
                    "location": item["location"],
                    "weeks": item["weeks"],
                } for item in imported_data["entries"]],
            },
            "current_plan": generated.json()["plan"],
            "current_plan_published": True,
        }

        agenda = client.post(
            "/api/v1/users/context_target/agenda/contextual",
            params={
                "start_date": "2026-07-24",
                "end_date": "2026-07-25",
            },
            json=context,
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

        repeated = client.post(
            "/api/v1/users/context_target/agenda/contextual",
            params={
                "start_date": "2026-07-24",
                "end_date": "2026-07-25",
            },
            json=context,
        )
        assert repeated.status_code == 200, repeated.text
        assert len(repeated.json()["items"]) == len(payload["items"])

        due = client.post(
            "/api/v1/users/context_target/reminders/due/contextual",
            params={
                "now": "2026-07-24T22:30:00+08:00",
                "window_min": 1,
            },
            json=context,
        )
        assert due.status_code == 200, due.text
        assert any(
            item["kind"] == "bedtime"
            for item in due.json()["reminders"]
        )

        exported = client.post(
            "/api/v1/users/context_target/agenda.ics/contextual",
            params={
                "start_date": "2026-07-24",
                "end_date": "2026-07-25",
            },
            json=context,
        )
        assert exported.status_code == 200, exported.text
        assert "text/calendar" in exported.headers["content-type"]
        assert "SUMMARY:高等数学" in exported.text
        assert "SUMMARY:图书馆自习" in exported.text
        assert "SUMMARY:准备休息" in exported.text


def test_reminder_settings_are_user_managed_and_ics_has_alarms(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert client.post(
            "/api/v1/users/reminder_user/timetable/import",
            json={
                "name": "我的课表",
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
            },
        ).status_code == 201
        saved = client.put(
            "/api/v1/users/reminder_user/reminders/settings",
            json={
                "enabled": True,
                "browser_notifications": True,
                "course_lead_min": 30,
                "early_course_wakeup_min": 90,
                "meeting_lead_min": 20,
                "study_lead_min": 15,
                "exercise_lead_min": 15,
                "task_lead_min": 10,
                "quiet_start": "23:00:00",
                "quiet_end": "06:30:00",
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["settings"]["course_lead_min"] == 30

        due = client.get(
            "/api/v1/users/reminder_user/reminders/due",
            params={
                "now": "2026-07-24T06:35:00+08:00",
                "window_min": 1,
            },
        )
        assert due.status_code == 200, due.text
        assert len(due.json()["reminders"]) == 1
        assert due.json()["reminders"][0]["kind"] == "wakeup"

        exported = client.get(
            "/api/v1/users/reminder_user/agenda.ics",
            params={
                "start_date": "2026-07-24",
                "end_date": "2026-07-24",
            },
        )
        assert exported.status_code == 200, exported.text
        assert "text/calendar" in exported.headers["content-type"]
        assert "SUMMARY:高等数学" in exported.text
        assert "TRIGGER:-PT90M" in exported.text
        assert "TRIGGER:-PT30M" in exported.text


def test_heavy_learning_day_gets_optional_care_suggestion(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        generated = client.post(
            "/api/v1/chat",
            json={
                "user_id": "care_user",
                "thread_id": "care_thread",
                "query": "2026年7月25日8点开始在图书馆自习7小时。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T20:00:00+08:00"
                },
            },
        )
        assert generated.status_code == 200, generated.text
        response = client.get(
            "/api/v1/users/care_user/agenda",
            params={
                "start_date": "2026-07-25",
                "end_date": "2026-07-25",
            },
        )
        assert response.status_code == 200, response.text
        suggestions = response.json()["care_suggestions"]
        assert any(
            item["id"] == "balance_heavy_study"
            for item in suggestions
        )
        assert any(
            item["id"].startswith("meal_gap_")
            for item in suggestions
        )


def test_bedtime_reminder_uses_user_routine_and_next_early_course(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert client.post(
            "/api/v1/users/sleep_user/timetable/import",
            json={
                "name": "我的课表",
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
            },
        ).status_code == 201
        for key, label, value in (
            ("usual_bedtime", "常用就寝时间", "23:00"),
            ("usual_wake_time", "常用起床时间", "06:30"),
            ("sleep_goal_hours", "希望睡眠时长", 7.5),
        ):
            saved = client.post(
                "/api/v1/users/sleep_user/memories",
                json={
                    "category": "habit",
                    "key": key,
                    "label": label,
                    "value": value,
                    "enabled": True,
                },
            )
            assert saved.status_code == 201, saved.text

        response = client.get(
            "/api/v1/users/sleep_user/agenda",
            params={
                "start_date": "2026-07-23",
                "end_date": "2026-07-24",
            },
        )
        assert response.status_code == 200, response.text
        reminders = [
            item
            for item in response.json()["reminders"]
            if item["kind"] == "bedtime"
            and item["event_start_at"] == "2026-07-23T23:00:00+08:00"
        ]
        assert len(reminders) == 1
        assert reminders[0]["notify_at"] == "2026-07-23T22:30:00+08:00"
        assert "明天 08:05" in reminders[0]["body"]
        assert "7.5小时" in reminders[0]["body"]

        exported = client.get(
            "/api/v1/users/sleep_user/agenda.ics",
            params={
                "start_date": "2026-07-23",
                "end_date": "2026-07-24",
            },
        )
        assert exported.status_code == 200, exported.text
        assert "SUMMARY:准备休息" in exported.text
        assert "TRIGGER:-PT30M" in exported.text
        assert "明天 08:05" in exported.text


def test_bedtime_reminder_respects_late_arrangement_and_user_switch(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        for key, label, value in (
            ("usual_bedtime", "常用就寝时间", "23:00"),
            ("usual_wake_time", "常用起床时间", "07:00"),
            ("sleep_goal_hours", "希望睡眠时长", 8),
        ):
            saved = client.post(
                "/api/v1/users/night_user/memories",
                json={
                    "category": "habit",
                    "key": key,
                    "label": label,
                    "value": value,
                    "enabled": True,
                },
            )
            assert saved.status_code == 201, saved.text

        generated = client.post(
            "/api/v1/chat",
            json={
                "user_id": "night_user",
                "thread_id": "night_thread",
                "query": "2026年7月25日22:30到23:30开线上会议。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T20:00:00+08:00"
                },
            },
        )
        assert generated.status_code == 200, generated.text

        agenda = client.get(
            "/api/v1/users/night_user/agenda",
            params={
                "start_date": "2026-07-25",
                "end_date": "2026-07-25",
            },
        )
        assert agenda.status_code == 200, agenda.text
        bedtime = [
            item
            for item in agenda.json()["reminders"]
            if item["kind"] == "bedtime"
        ]
        assert len(bedtime) == 1
        assert "线上会议" in bedtime[0]["body"]
        assert "23:30" in bedtime[0]["body"]
        assert "别再给自己加任务" in bedtime[0]["body"]

        current_settings = client.get(
            "/api/v1/users/night_user/reminders/settings"
        ).json()["settings"]
        current_settings["bedtime_enabled"] = False
        disabled = client.put(
            "/api/v1/users/night_user/reminders/settings",
            json=current_settings,
        )
        assert disabled.status_code == 200, disabled.text

        agenda = client.get(
            "/api/v1/users/night_user/agenda",
            params={
                "start_date": "2026-07-25",
                "end_date": "2026-07-25",
            },
        )
        assert agenda.status_code == 200, agenda.text
        assert all(
            item["kind"] != "bedtime"
            for item in agenda.json()["reminders"]
        )


def test_conversational_addition_keeps_existing_daily_agenda(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        first = client.post(
            "/api/v1/chat",
            json={
                "user_id": "ongoing_user",
                "thread_id": "ongoing_thread",
                "query": "2026年7月26日14点去图书馆自习1小时。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:00:00+08:00"
                },
            },
        )
        assert first.status_code == 200, first.text
        second = client.post(
            "/api/v1/chat",
            json={
                "user_id": "ongoing_user",
                "thread_id": "ongoing_thread",
                "query": (
                    "另外在2026年7月26日18:30到19:30固定开会，"
                    "保留已有安排。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:05:00+08:00"
                },
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["previous_plan"] is not None
        assert "热水开放时间" not in second.json()["answer"]
        assert "上课时间第1节" not in second.json()["answer"]
        assert all(
            "热水" not in insight["content"]
            and "上课时间第1节" not in insight["content"]
            for insight in second.json()["insights"]
        )

        agenda = client.get(
            "/api/v1/users/ongoing_user/agenda",
            params={
                "start_date": "2026-07-26",
                "end_date": "2026-07-26",
            },
        )
        assert agenda.status_code == 200, agenda.text
        titles = {
            item["title"]
            for item in agenda.json()["items"]
            if item["kind"] != "travel"
        }
        assert "图书馆自习" in titles
        assert "开会" in titles


def test_conversational_removal_keeps_unaffected_daily_agenda(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        first = client.post(
            "/api/v1/chat",
            json={
                "user_id": "removal_user",
                "thread_id": "removal_thread",
                "query": (
                    "2026年7月28日14点后去图书馆自习1小时，"
                    "再取快递，然后跑步30分钟，20点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:00:00+08:00"
                },
            },
        )
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "completed"

        second = client.post(
            "/api/v1/chat",
            json={
                "user_id": "removal_user",
                "thread_id": "removal_thread",
                "query": "跑步不去了，其他安排保持不变。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:05:00+08:00"
                },
            },
        )
        assert second.status_code == 200, second.text
        payload = second.json()
        assert payload["previous_plan"] is not None
        assert "已经移除" in payload["answer"]
        assert any(
            change["task_id"] == "run"
            and change["change_type"] == "removed"
            for change in payload["plan_diff"]
        )

        agenda = client.get(
            "/api/v1/users/removal_user/agenda",
            params={
                "start_date": "2026-07-28",
                "end_date": "2026-07-28",
            },
        )
        assert agenda.status_code == 200, agenda.text
        titles = {
            item["title"]
            for item in agenda.json()["items"]
            if item["kind"] != "travel"
        }
        assert "图书馆自习" in titles
        assert any("快递" in title for title in titles)
        assert not any("跑步" in title for title in titles)


def test_conversational_clear_all_creates_an_explicit_empty_day(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        first = client.post(
            "/api/v1/chat",
            json={
                "user_id": "clear_user",
                "thread_id": "clear_thread",
                "query": "2026年7月29日14点去图书馆自习1小时。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:00:00+08:00"
                },
            },
        )
        assert first.status_code == 200, first.text

        cleared = client.post(
            "/api/v1/chat",
            json={
                "user_id": "clear_user",
                "thread_id": "clear_thread",
                "query": "把这一天的安排全部取消。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:05:00+08:00"
                },
            },
        )
        assert cleared.status_code == 200, cleared.text
        payload = cleared.json()
        assert payload["status"] == "completed"
        assert payload["plan"]["items"] == []
        assert "当前没有保留的安排" in payload["answer"]
        assert any(
            change["task_id"] == "study"
            and change["change_type"] == "removed"
            for change in payload["plan_diff"]
        )

        agenda = client.get(
            "/api/v1/users/clear_user/agenda",
            params={
                "start_date": "2026-07-29",
                "end_date": "2026-07-29",
            },
        )
        assert agenda.status_code == 200, agenda.text
        assert agenda.json()["items"] == []


def test_conversational_reschedule_moves_only_the_named_task(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        first = client.post(
            "/api/v1/chat",
            json={
                "user_id": "move_user",
                "thread_id": "move_thread",
                "query": (
                    "2026年7月30日14点到15点固定自习，"
                    "18:30到19:30固定开会。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:00:00+08:00"
                },
            },
        )
        assert first.status_code == 200, first.text
        original = {
            item["task_id"]: item
            for item in first.json()["plan"]["items"]
            if item["item_type"] == "task"
        }

        moved = client.post(
            "/api/v1/chat",
            json={
                "user_id": "move_user",
                "thread_id": "move_thread",
                "query": (
                    "把开会改到20:00到21:00，"
                    "自习保持原来的时间。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:05:00+08:00"
                },
            },
        )
        assert moved.status_code == 200, moved.text
        payload = moved.json()
        current = {
            item["task_id"]: item
            for item in payload["plan"]["items"]
            if item["item_type"] == "task"
        }
        meeting_id = next(
            task_id
            for task_id, item in original.items()
            if "开会" in item["title"]
        )
        study_id = next(
            task_id
            for task_id, item in original.items()
            if "自习" in item["title"]
        )
        assert current[meeting_id]["start_at"].endswith("20:00:00+08:00")
        assert current[meeting_id]["end_at"].endswith("21:00:00+08:00")
        assert current[study_id]["start_at"] == original[study_id]["start_at"]
        assert current[study_id]["end_at"] == original[study_id]["end_at"]
        assert any(
            change["task_id"] == meeting_id
            and change["change_type"] == "moved"
            for change in payload["plan_diff"]
        )

        moved_study = client.post(
            "/api/v1/chat",
            json={
                "user_id": "move_user",
                "thread_id": "move_thread",
                "query": "把自习改到16点开始，开会不要动。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:10:00+08:00"
                },
            },
        )
        assert moved_study.status_code == 200, moved_study.text
        after_clock_change = {
            item["task_id"]: item
            for item in moved_study.json()["plan"]["items"]
            if item["item_type"] == "task"
        }
        assert after_clock_change[study_id]["start_at"].endswith(
            "16:00:00+08:00"
        )
        assert after_clock_change[study_id]["end_at"].endswith(
            "17:00:00+08:00"
        )

        earlier = client.post(
            "/api/v1/chat",
            json={
                "user_id": "move_user",
                "thread_id": "move_thread",
                "query": "把自习提前30分钟，开会不要动。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:15:00+08:00"
                },
            },
        )
        assert earlier.status_code == 200, earlier.text
        after_relative = {
            item["task_id"]: item
            for item in earlier.json()["plan"]["items"]
            if item["item_type"] == "task"
        }
        assert after_relative[study_id]["start_at"].endswith(
            "15:30:00+08:00"
        )
        assert after_relative[study_id]["end_at"].endswith(
            "16:30:00+08:00"
        )
        assert after_relative[meeting_id]["start_at"].endswith(
            "20:00:00+08:00"
        )

        extended_meeting = client.post(
            "/api/v1/chat",
            json={
                "user_id": "move_user",
                "thread_id": "move_thread",
                "query": "把开会延长30分钟，自习保持原时间。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:20:00+08:00"
                },
            },
        )
        assert extended_meeting.status_code == 200, extended_meeting.text
        after_duration = {
            item["task_id"]: item
            for item in extended_meeting.json()["plan"]["items"]
            if item["item_type"] == "task"
        }
        assert after_duration[meeting_id]["start_at"].endswith(
            "20:00:00+08:00"
        )
        assert after_duration[meeting_id]["end_at"].endswith(
            "21:30:00+08:00"
        )
        assert after_duration[study_id]["start_at"].endswith(
            "15:30:00+08:00"
        )

        shifted_day = client.post(
            "/api/v1/chat",
            json={
                "user_id": "move_user",
                "thread_id": "move_thread",
                "query": (
                    "把所有安排顺延30分钟，"
                    "但开会保持原来的时间。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T10:25:00+08:00"
                },
            },
        )
        assert shifted_day.status_code == 200, shifted_day.text
        after_global_shift = {
            item["task_id"]: item
            for item in shifted_day.json()["plan"]["items"]
            if item["item_type"] == "task"
        }
        assert after_global_shift[study_id]["start_at"].endswith(
            "16:00:00+08:00"
        )
        assert after_global_shift[study_id]["end_at"].endswith(
            "17:00:00+08:00"
        )
        assert after_global_shift[meeting_id]["start_at"].endswith(
            "20:00:00+08:00"
        )
        assert after_global_shift[meeting_id]["end_at"].endswith(
            "21:30:00+08:00"
        )
