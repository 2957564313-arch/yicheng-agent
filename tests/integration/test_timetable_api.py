from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_api_demos import build_test_app, task_items


CSV_CONTENT = """课程名称,星期,开始节次,结束节次,地点,周次
高等数学,星期五,1,2,第六教学楼,1-16
大学英语,星期五,3,4,第六教学楼,1-16
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
        assert tasks["study"]["start_at"] >= "2026-07-24T11:35:00+08:00"
        assert all(check["passed"] for check in payload["constraint_checks"])


def test_explicit_no_class_statement_is_a_one_day_exception(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert client.post(
            "/api/v1/users/no_class_user/timetable/import",
            json={
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
            },
        ).status_code == 201
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
        assert client.post(
            "/api/v1/users/question_user/timetable/import",
            json={
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
            },
        ).status_code == 201
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
        assert payload["data_freshness"]["knowledge"] == "user"


def test_imported_courses_fixed_event_and_deadline_are_jointly_feasible(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        assert client.post(
            "/api/v1/users/joint_user/timetable/import",
            json={
                "format": "csv",
                "content": CSV_CONTENT,
                "term_start": "2026-07-20",
            },
        ).status_code == 201
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
