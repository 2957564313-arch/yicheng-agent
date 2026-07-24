from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.main import create_app


def build_test_app(tmp_path: Path):
    settings = Settings(
        app_database_path=tmp_path / "app.db",
        app_checkpoint_database_path=tmp_path / "checkpoints.db",
        app_data_dir=BASE_DIR / "data",
        app_demo_dir=BASE_DIR / "fixtures",
        llm_enabled=False,
        live_route_enabled=False,
        live_weather_enabled=False,
    )
    return create_app(settings)


def task_items(payload: dict) -> dict[str, dict]:
    return {
        item["task_id"]: item
        for item in payload["plan"]["items"]
        if item["item_type"] == "task"
    }


class FailingLLM:
    configured = True

    async def parse_requirement(self, **_kwargs):
        raise TimeoutError("simulated timeout")

    async def render_plan(self, **_kwargs):
        raise TimeoutError("simulated timeout")


def test_health_and_demo_catalog(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["database"] == "ok"
        assert health.json()["knowledge_chunks"] >= 1
        assert health.json()["timezone"] == "Asia/Shanghai"
        assert health.json()["server_time"].endswith("+08:00")

        demos = client.get("/api/v1/demos")
        assert demos.status_code == 200
        assert [item["id"] for item in demos.json()] == [
            "demo_01_normal",
            "demo_02_emergency",
            "demo_03_degraded",
        ]


def test_normal_demo_has_exact_timeline_and_evidence(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post("/api/v1/demos/demo_01_normal/run")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["plan"]["status"] == "valid"
        assert payload["current_plan_saved"] is True
        assert payload["time_context"] == {
            "now": "2026-07-24T13:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "target_date": "2026-07-24",
            "weekday": "星期五",
            "source": "request_context",
        }
        assert payload["insights"][0]["title"] == "规划时间基准"
        assert payload["plan"]["metrics"]["hard_violation_count"] == 0
        assert "安排思路" in payload["answer"]
        assert "今天可以这样安排" in payload["answer"]
        assert "如果临时晚出发" in payload["answer"]

        tasks = task_items(payload)
        assert tasks["study"]["start_at"] == "2026-07-24T14:00:00+08:00"
        assert tasks["study"]["end_at"] == "2026-07-24T16:00:00+08:00"
        assert tasks["parcel"]["start_at"] == "2026-07-24T16:20:00+08:00"
        assert tasks["parcel"]["end_at"] == "2026-07-24T16:50:00+08:00"
        assert tasks["run"]["start_at"] == "2026-07-24T17:05:00+08:00"
        assert tasks["run"]["end_at"] == "2026-07-24T17:35:00+08:00"
        travel = [
            item
            for item in payload["plan"]["items"]
            if item["item_type"] == "travel"
        ][0]
        assert travel["base_duration_min"] == 13
        assert travel["congestion_delay_min"] == 4
        assert any(
            warning["code"] == "PEAK_CONGESTION"
            for warning in payload["warnings"]
        )
        assert payload["suggested_actions"][0]["id"] == "prefer_off_peak"
        assert payload["location_names"]["parcel_station"] == "菜鸟驿站"
        assert payload["location_names"]["library"] == "图书馆"
        assert len(payload["execution_steps"]) == 5
        assert all(check["passed"] for check in payload["constraint_checks"])


def test_client_time_is_normalized_to_campus_timezone(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "timezone_user",
                "thread_id": "timezone_thread",
                "query": "今天17点以后去图书馆学习30分钟。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T16:30:00Z"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["time_context"]["now"] == (
            "2026-07-25T00:30:00+08:00"
        )
        assert payload["time_context"]["target_date"] == "2026-07-25"
        assert payload["time_context"]["weekday"] == "星期六"


def test_requirement_change_uses_current_plan_and_returns_diff(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        first = client.post("/api/v1/demos/demo_01_normal/run")
        assert first.status_code == 200
        response = client.post("/api/v1/demos/demo_02_emergency/run")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["plan"]["version"] == 2
        assert payload["previous_plan"] is not None

        tasks = task_items(payload)
        assert tasks["study"]["end_at"] == "2026-07-24T16:30:00+08:00"
        assert tasks["parcel"]["start_at"] == "2026-07-24T16:45:00+08:00"
        assert tasks["run"]["start_at"] == "2026-07-24T17:30:00+08:00"
        assert tasks["run"]["end_at"] == "2026-07-24T18:00:00+08:00"
        changes = {item["task_id"]: item for item in payload["plan_diff"]}
        assert changes["study"]["duration_delta_min"] == 30
        assert changes["parcel"]["shift_min"] == 30
        assert changes["run"]["shift_min"] == 30
        assert payload["adjustment_reason"]


def test_weather_demo_moves_outdoor_task_before_rain(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post("/api/v1/demos/demo_03_degraded/run")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        tasks = task_items(payload)
        assert tasks["run"]["start_at"] == "2026-07-24T14:00:00+08:00"
        assert tasks["run"]["end_at"] == "2026-07-24T14:30:00+08:00"
        assert tasks["study"]["start_at"] == "2026-07-24T14:40:00+08:00"
        assert tasks["parcel"]["start_at"] == "2026-07-24T16:55:00+08:00"
        assert not any(
            warning["code"] == "WEATHER_RISK"
            for warning in payload["warnings"]
        )
        run_change = next(
            change
            for change in payload["plan_diff"]
            if change["task_id"] == "run"
        )
        assert run_change["shift_min"] == -180
        assert payload["data_freshness"]["weather"] == "user"


def test_reset_makes_each_demo_repeatable(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert client.post("/api/v1/demos/demo_01_normal/run").status_code == 200
        assert client.post("/api/v1/demos/demo_02_emergency/run").status_code == 200
        reset = client.post("/api/v1/demos/reset")
        assert reset.status_code == 200
        assert reset.json()["status"] == "ok"

        second = client.post("/api/v1/demos/demo_02_emergency/run")
        assert second.status_code == 200
        assert (
            task_items(second.json())["study"]["end_at"]
            == "2026-07-24T16:30:00+08:00"
        )


def test_manual_adjustment_resolves_latest_plan_from_thread(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        assert client.post("/api/v1/demos/demo_01_normal/run").status_code == 200
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "demo_user",
                "thread_id": "demo_competition",
                "query": (
                    "把图书馆学习延长30分钟，保持跑步30分钟，"
                    "还是要在18点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:05:00+08:00"
                },
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["previous_plan"] is not None
        assert response.json()["plan_diff"]


def test_invalid_request_has_stable_error_shape(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={"user_id": "demo_user", "query": ""},
        )
        assert response.status_code == 422
        payload = response.json()
        assert payload["error"]["code"] == "INVALID_REQUEST"
        assert payload["request_id"].startswith("req_")


def test_offline_knowledge_query_uses_local_campus_facts(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "knowledge_user",
                "query": "图书馆晚上几点关门？",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:05:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["plan"] is None
        assert "22:30" in payload["answer"]
        assert payload["data_freshness"]["knowledge"] in {
            "structured",
            "rag",
        }


def test_class_periods_are_scheduled_as_immutable_time_blocks(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "course_user",
                "thread_id": "course_thread",
                "query": (
                    "今天第1至4节有课，下课后去图书馆自习2小时，"
                    "再去取快递。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T07:00:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        tasks = task_items(payload)
        assert tasks["course_1_4"]["start_at"] == (
            "2026-07-24T08:05:00+08:00"
        )
        assert tasks["course_1_4"]["end_at"] == (
            "2026-07-24T11:35:00+08:00"
        )
        assert tasks["study"]["start_at"] >= (
            "2026-07-24T11:35:00+08:00"
        )
        assert all(check["passed"] for check in payload["constraint_checks"])
        assert any(
            item["title"] == "已核对校园规则"
            or "校园" in item["source_label"]
            for item in payload["insights"]
        )


def test_memory_can_be_managed_and_applies_across_new_threads(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        created = client.post(
            "/api/v1/users/memory_user/memories",
            json={
                "category": "preference",
                "key": "buffer_min",
                "label": "日程缓冲时间",
                "value": 20,
                "enabled": True,
            },
        )
        assert created.status_code == 201, created.text
        memory = created.json()

        listed = client.get("/api/v1/users/memory_user/memories")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["value"] == 20

        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "memory_user",
                "thread_id": "memory_new_thread",
                "query": (
                    "今天14点后去图书馆自习1小时，再去取快递，"
                    "18点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00"
                },
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        items = sorted(
            payload["plan"]["items"],
            key=lambda item: item["start_at"],
        )
        travel = next(item for item in items if item["item_type"] == "travel")
        parcel = next(
            item for item in items if item.get("task_id") == "parcel"
        )
        travel_end = datetime.fromisoformat(travel["end_at"])
        parcel_start = datetime.fromisoformat(parcel["start_at"])
        assert int((parcel_start - travel_end).total_seconds() // 60) >= 20
        assert any(
            item["source_label"] == "个人记忆库"
            for item in payload["insights"]
        )

        disabled = client.patch(
            f"/api/v1/users/memory_user/memories/{memory['id']}",
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False

        deleted = client.delete(
            f"/api/v1/users/memory_user/memories/{memory['id']}"
        )
        assert deleted.status_code == 204


def test_weather_check_is_only_shown_when_weather_is_enforced(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/demos/demo_01_normal/run"
        )
        assert response.status_code == 200
        keys = {
            check["key"] for check in response.json()["constraint_checks"]
        }
        assert "weather" not in keys


def test_explicit_user_weather_is_a_hard_constraint_on_first_plan(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "weather_first_user",
                "thread_id": "weather_first_thread",
                "query": (
                    "明天14点后先跑步30分钟，再去图书馆自习1小时，"
                    "17点后有雨，最后取快递。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-23T13:00:00+08:00"
                },
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        tasks = task_items(payload)
        assert tasks["run"]["end_at"] <= "2026-07-24T17:00:00+08:00"
        weather_check = next(
            item
            for item in payload["constraint_checks"]
            if item["key"] == "weather"
        )
        assert weather_check["passed"] is True
        assert any(
            item["source_label"] == "用户补充"
            for item in payload["insights"]
        )


def test_llm_failure_falls_back_to_local_parser(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        client.app.state.container.llm = FailingLLM()
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "fallback_user",
                "query": (
                    "今天14点后去图书馆自习2小时，再去菜鸟驿站"
                    "取快递，最后去东操场跑步30分钟，18点前结束。"
                ),
                "mode": "live",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["plan"]["status"] == "valid"
        assert "LLM_DEGRADED" in {
            warning["code"] for warning in payload["warnings"]
        }


def test_infeasible_plan_keeps_every_requested_task_visible(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "late_start_user",
                "thread_id": "late_start_thread",
                "query": (
                    "今天下午没课，14点以后想去图书馆学习2小时，"
                    "取快递，然后去东操场跑步30分钟，18点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T15:35:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "partial"
        assert payload["plan"]["status"] == "infeasible"
        assert payload["current_plan_saved"] is False
        assert "没有替你删掉" in payload["answer"]
        assert "取快递" in payload["answer"]
        assert "跑步" in payload["answer"]
        assert "145 分钟" in payload["answer"]
        assert "208 分钟" in payload["answer"]
        assert "处理方式" in payload["answer"]

        statuses = {
            item["task_id"]: item
            for item in payload["task_statuses"]
        }
        assert set(statuses) == {"study", "parcel", "run"}
        assert statuses["study"]["status"] == "scheduled"
        assert statuses["parcel"]["status"] == "needs_adjustment"
        assert statuses["run"]["status"] == "needs_adjustment"
        assert "未能安排" in statuses["parcel"]["message"]
        assert "未能安排" in statuses["run"]["message"]

        actions = payload["suggested_actions"]
        assert [action["id"] for action in actions] == [
            "option_1",
            "option_2",
        ]
        assert "自习45分钟" in actions[0]["query"]
        assert "18:00前结束" in actions[0]["query"]
        assert "19:15前结束" in actions[1]["query"]


def test_suggested_action_query_generates_complete_plan(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        first = client.post(
            "/api/v1/chat",
            json={
                "user_id": "late_start_user",
                "thread_id": "late_start_thread",
                "query": (
                    "今天下午没课，14点以后想去图书馆学习2小时，"
                    "取快递，然后去东操场跑步30分钟，18点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T15:35:00+08:00"
                },
            },
        )
        action_query = first.json()["suggested_actions"][0]["query"]
        second = client.post(
            "/api/v1/chat",
            json={
                "user_id": "late_start_user",
                "thread_id": "late_start_thread",
                "query": action_query,
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T15:35:00+08:00"
                },
            },
        )

        assert second.status_code == 200, second.text
        payload = second.json()
        assert payload["status"] == "completed"
        assert payload["plan"]["status"] == "valid"
        assert payload["plan"]["metrics"]["scheduled_task_count"] == 3
        assert all(
            task["status"] == "scheduled"
            for task in payload["task_statuses"]
        )


def test_late_plan_is_caring_and_never_shrinks_study_to_token_block(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "very_late_user",
                "thread_id": "very_late_thread",
                "query": (
                    "今天下午没课，14点以后想去图书馆学习2小时，"
                    "取快递，然后去东操场跑步30分钟，18点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T16:00:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "partial"
        assert payload["answer"].startswith("你想把")
        assert not payload["answer"].startswith(
            ("你好", "您好", "没问题", "好的", "可以")
        )
        assert "我不想为了让日程看起来完整" in payload["answer"]
        assert "图书馆自习原本需要 120 分钟" in payload["answer"]
        assert "不会擅自牺牲你明确要求的任务时长" in payload["answer"]

        actions = payload["suggested_actions"]
        assert [action["id"] for action in actions] == ["option_2"]
        assert actions[0]["label"] == "保留完整安排"
        assert "图书馆自习120分钟" in actions[0]["query"]
        assert "自习20分钟" not in actions[0]["query"]


def test_short_study_infeasible_reply_does_not_invent_two_hours(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "short_study_user",
                "thread_id": "short_study_thread",
                "query": (
                    "今天15:05以后骑电瓶车去图书馆学习10分钟，"
                    "再去菜鸟驿站取快递，然后去东操场跑步30分钟，"
                    "17点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T17:05:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "partial"
        assert "图书馆自习原本需要 10 分钟" not in payload["answer"]
        assert "两小时学习" not in payload["answer"]
        assert "十几二十分钟" not in payload["answer"]
        assert "不会擅自牺牲你明确要求的任务时长" in payload["answer"]


def test_user_reported_rain_moves_run_before_risk_and_keeps_all_tasks(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        initial = client.post(
            "/api/v1/chat",
            json={
                "user_id": "weather_care_user",
                "thread_id": "weather_care_thread",
                "query": (
                    "2026-07-24 16:00以后，图书馆自习120分钟，"
                    "然后取快递30分钟，然后跑步30分钟，"
                    "19:40前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T16:00:00+08:00"
                },
            },
        )
        assert initial.status_code == 200, initial.text
        assert initial.json()["status"] == "completed"

        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "weather_care_user",
                "thread_id": "weather_care_thread",
                "query": (
                    "检查当前计划的天气风险。17点以后有雨，"
                    "请调整计划，三项任务都要保留。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T16:00:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["plan"]["status"] == "valid"
        tasks = task_items(payload)
        assert set(tasks) == {"study", "parcel", "run"}
        assert tasks["run"]["end_at"] <= "2026-07-24T17:00:00+08:00"
        assert payload["plan_diff"]
        assert not any(
            warning["code"] == "WEATHER_RISK"
            for warning in payload["warnings"]
        )
        assert "安全" in payload["answer"]
