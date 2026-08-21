from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_api_demos import build_test_app, task_items

CSV_CONTENT = """课程名称,星期,开始节次,结束节次,地点,周次
高等数学,星期五,1,2,第六教学楼,1-16
大学英语,星期五,3,4,第七教学楼,1-16
"""

MONDAY_REALISTIC_CONTENT = """课程名称,星期,开始节次,结束节次,地点,周次
高等数学A2,星期一,1,2,第6教研楼北204,1-17
中国建筑设计赏析,星期一,6,7,第6教研楼北304,1-17
数学建模,星期一,8,9,第6教研楼北304,2-16
"""


def test_imported_timetable_becomes_hard_planning_constraint(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        imported = client.post(
            "/api/v1/users/timetable_user/timetable/import",
            json={
                "name": "2026测试课表",
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
                "term_end": "2026-11-30",
            },
        )
        assert imported.status_code == 201, imported.text
        assert imported.json()["imported_count"] == 2

        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "timetable_user",
                "thread_id": "timetable_plan",
                "query": "今天下课后去图书馆自习1小时，再去取快递。",
                "mode": "offline",
                "client_context": {"now": "2026-07-24T07:00:00+08:00"},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        tasks = task_items(payload)
        imported_courses = [
            item
            for task_id, item in tasks.items()
            if task_id.startswith("timetable_")
        ]
        assert len(imported_courses) == 2
        assert imported_courses[0]["start_at"] == "2026-07-24T08:05:00+08:00"
        assert imported_courses[-1]["end_at"] == "2026-07-24T11:35:00+08:00"
        assert {item["location_raw"] for item in imported_courses} == {
            "第六教学楼",
            "第七教学楼",
        }
        assert all(item["locked"] for item in imported_courses)
        assert tasks["study"]["start_at"] >= "2026-07-24T11:35:00+08:00"
        assert all(check["passed"] for check in payload["constraint_checks"])
        assert payload["status"] == "completed"
        assert any(
            warning["code"] == "UNKNOWN_LOCATION"
            and warning["severity"] == "warning"
            for warning in payload["warnings"]
        )


def test_week_based_timetable_requires_first_teaching_monday(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/users/missing_term/timetable/import",
            json={
                "format": "csv",
                "content": CSV_CONTENT,
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == (
            "TIMETABLE_TERM_START_REQUIRED"
        )
        assert "第一教学周周一" in response.json()["error"]["message"]


def test_term_end_is_derived_from_maximum_imported_week(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/users/derived_term/timetable/import",
            json={
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-02-23",
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["timetable"]["term_end"] == "2026-06-14"


def test_timetable_preview_does_not_replace_saved_timetable(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        preview = client.post(
            "/api/v1/users/preview_user/timetable/preview",
            json={
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-02-23",
            },
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["imported_count"] == 2
        assert preview.json()["term_end"] == "2026-06-14"
        saved = client.get("/api/v1/users/preview_user/timetable")
        assert saved.status_code == 200
        assert saved.json()["timetable"] is None
        assert saved.json()["entries"] == []


def test_explicit_no_class_statement_is_a_one_day_exception(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert (
            client.post(
                "/api/v1/users/no_class_user/timetable/import",
                json={
                    "format": "csv",
                    "content": CSV_CONTENT,
                    "term_start": "2026-07-20",
                },
            ).status_code
            == 201
        )
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "no_class_user",
                "query": "今天没课，14点以后去图书馆自习1小时。",
                "mode": "offline",
                "client_context": {"now": "2026-07-24T10:00:00+08:00"},
            },
        )
        assert response.status_code == 200, response.text
        assert not any(
            task_id.startswith("timetable_")
            for task_id in task_items(response.json())
        )


def test_timetable_question_uses_personal_schedule(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert (
            client.post(
                "/api/v1/users/question_user/timetable/import",
                json={
                    "format": "csv",
                    "content": CSV_CONTENT,
                    "term_start": "2026-07-20",
                },
            ).status_code
            == 201
        )
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "question_user",
                "query": "今天哪几节有课？",
                "mode": "offline",
                "client_context": {"now": "2026-07-24T07:00:00+08:00"},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["plan"] is None
        assert "高等数学" in payload["answer"]
        assert "大学英语" in payload["answer"]
        assert "第1—2节" in payload["answer"]
        assert "第3—4节" in payload["answer"]
        assert "第1节和第2节" not in payload["answer"]
        assert not any(
            insight["source_label"] == "2025年学生手册"
            for insight in payload["insights"]
        )
        assert payload["data_freshness"]["knowledge"] == "user"


def test_imported_courses_fixed_event_and_deadline_are_jointly_feasible(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        assert (
            client.post(
                "/api/v1/users/joint_user/timetable/import",
                json={
                    "format": "csv",
                    "content": CSV_CONTENT,
                    "term_start": "2026-07-20",
                },
            ).status_code
            == 201
        )
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "joint_user",
                "query": (
                    "2026年7月31日下课后去图书馆自习90分钟，"
                    "15:00到16:00在图书馆固定参加社团会议，"
                    "18点前去菜鸟驿站取快递，晚上去东操场跑步30分钟，"
                    "校内骑电瓶车。"
                ),
                "mode": "offline",
                "client_context": {"now": "2026-07-24T19:00:00+08:00"},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        tasks = task_items(payload)
        assert len(tasks) == 6
        assert tasks["parcel"]["end_at"] <= "2026-07-31T18:00:00+08:00"
        assert tasks["parcel"]["start_at"] >= "2026-07-31T16:00:00+08:00"
        assert tasks["fixed_1500_1600_1"]["start_at"] == (
            "2026-07-31T15:00:00+08:00"
        )
        assert "7月31日可以这样安排" in payload["answer"]
        assert "实时骑行路线不可用" not in payload["answer"]
        assert all(check["passed"] for check in payload["constraint_checks"])
        assert payload["status"] == "completed"


def test_realistic_monday_plan_uses_timetable_and_orders_fixed_point_events(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        imported = client.post(
            "/api/v1/users/realistic_user/timetable/import",
            json={
                "name": "2025-2026-2课表",
                "format": "csv",
                "content": MONDAY_REALISTIC_CONTENT,
                "term_start": "2026-02-23",
            },
        )
        assert imported.status_code == 201, imported.text

        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "realistic_user",
                "thread_id": "realistic_monday",
                "query": (
                    "根据我的课表安排今天：下午上完课拿快递，"
                    "晚上21:00要乐团排练，中午12:40有一个20分钟的视频会议。"
                ),
                "mode": "offline",
                "client_context": {"now": "2026-03-02T12:00:00+08:00"},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        items = payload["plan"]["items"]
        task_by_id = {
            item["task_id"]: item
            for item in items
            if item["item_type"] == "task"
        }

        assert [item["start_at"] for item in items] == sorted(
            item["start_at"] for item in items
        )
        assert "高等数学A2" not in {item["title"] for item in items}
        assert "中国建筑设计赏析" in {item["title"] for item in items}
        assert "数学建模" in {item["title"] for item in items}
        assert "下午课程" not in {item["title"] for item in items}
        assert task_by_id["fixed_point_video_meeting_1240"]["start_at"] == (
            "2026-03-02T12:40:00+08:00"
        )
        assert task_by_id["fixed_point_video_meeting_1240"]["end_at"] == (
            "2026-03-02T13:00:00+08:00"
        )
        assert task_by_id["parcel"]["start_at"] >= (
            "2026-03-02T16:50:00+08:00"
        )
        assert task_by_id["fixed_point_rehearsal_2100"]["start_at"] == (
            "2026-03-02T21:00:00+08:00"
        )
        assert payload["plan"]["metrics"]["buffer_minutes"] >= 15
        assert all(check["passed"] for check in payload["constraint_checks"])


def test_complete_new_request_with_weather_does_not_reuse_old_plan(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        first = client.post(
            "/api/v1/chat",
            json={
                "user_id": "fresh_request_user",
                "thread_id": "same_thread",
                "query": "今天14点后去图书馆学习30分钟。",
                "mode": "offline",
                "client_context": {"now": "2026-07-24T13:00:00+08:00"},
            },
        )
        assert first.status_code == 200
        second = client.post(
            "/api/v1/chat",
            json={
                "user_id": "fresh_request_user",
                "thread_id": "same_thread",
                "query": (
                    "明天15:00到16:00固定参加社团会议，"
                    "之后取快递，请结合天气和开放时间安排。"
                ),
                "mode": "offline",
                "client_context": {"now": "2026-07-24T19:00:00+08:00"},
            },
        )
        assert second.status_code == 200, second.text
        payload = second.json()
        assert payload["previous_plan"] is None
        tasks = task_items(payload)
        assert "fixed_1500_1600_1" in tasks
        assert "parcel" in tasks
        assert "study" not in tasks


def test_holiday_allows_personal_plan_but_does_not_add_regular_courses(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        assert (
            client.post(
                "/api/v1/users/holiday_plan/timetable/import",
                json={
                    "format": "csv",
                    "content": CSV_CONTENT,
                    "term_start": "2026-09-28",
                },
            ).status_code
            == 201
        )
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "holiday_plan",
                "query": (
                    "2026年10月2日14点以后去图书馆自习1小时，再去东操场跑步30分钟。"
                ),
                "mode": "offline",
                "client_context": {"now": "2026-09-30T12:00:00+08:00"},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        tasks = task_items(payload)
        assert "study" not in tasks
        assert "run" in tasks
        assert not any(key.startswith("timetable_") for key in tasks)
        assert payload["status"] == "partial"
        assert "国庆节" in payload["answer"]
        assert "到了门口才发现无法使用" in payload["answer"]
        assert any(
            insight["source_label"] == "校内结构化规则"
            and "国庆节" in insight["content"]
            for insight in payload["insights"]
        )


def test_school_makeup_override_uses_replacement_weekday_courses(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert (
            client.post(
                "/api/v1/users/makeup_plan/timetable/import",
                json={
                    "format": "csv",
                    "content": CSV_CONTENT,
                    "term_start": "2026-09-28",
                },
            ).status_code
            == 201
        )
        override = client.post(
            "/api/v1/users/makeup_plan/calendar-overrides",
            json={
                "date": "2026-10-10",
                "action": "makeup",
                "replacement_weekday": 5,
                "label": "学校通知：补星期五课程",
            },
        )
        assert override.status_code == 201, override.text
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "makeup_plan",
                "query": "2026年10月10日哪几节有课？",
                "mode": "offline",
                "client_context": {"now": "2026-09-30T12:00:00+08:00"},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert "高等数学" in payload["answer"]
        assert "大学英语" in payload["answer"]
        assert any(
            "按学校校历执行星期五的课表" in insight["content"]
            for insight in payload["insights"]
        )


def test_browser_snapshots_preserve_timetable_and_makeup_rule(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "snapshot_only_user",
                "query": "2026年10月10日哪几节有课？",
                "mode": "offline",
                "client_context": {
                    "now": "2026-09-30T12:00:00+08:00",
                    "timetable": {
                        "name": "浏览器课表",
                        "term_start": "2026-09-28",
                        "enabled": True,
                        "entries": [
                            {
                                "course_name": "数据结构",
                                "weekday": 5,
                                "start_period": 3,
                                "end_period": 5,
                                "location": "第六教学楼",
                                "weeks": [1, 2, 3],
                            }
                        ],
                    },
                    "calendar_overrides": [
                        {
                            "date": "2026-10-10",
                            "action": "makeup",
                            "replacement_weekday": 5,
                            "label": "学校通知：补周五课程",
                        }
                    ],
                },
            },
        )
        assert response.status_code == 200, response.text
        assert "数据结构" in response.json()["answer"]
        assert "第3—5节" in response.json()["answer"]
        assert "按星期五课表执行" in response.json()["answer"]


def test_holiday_question_returns_concise_official_answer(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "holiday_question",
                "query": "2026年国庆节什么时候放假？",
                "mode": "offline",
                "client_context": {"now": "2026-04-01T10:00:00+08:00"},
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert "10月1日" in payload["answer"]
        assert "10月7日" in payload["answer"]
        assert "10月10日" in payload["answer"]
        assert "国家奖学金" not in payload["answer"]
        assert len(payload["answer"]) < 500
        assert any(
            insight["source_label"] == "国务院办公厅"
            for insight in payload["insights"]
        )
