from __future__ import annotations

from datetime import datetime
import json
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


class MisleadingKnowledgeLLM:
    configured = True

    async def answer_question(self, **_kwargs):
        return (
            "普通学生最多只能休学一年，具体规定请自行查看学校文件。"
        )


def test_health_and_demo_catalog(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert '<option value="auto">智能联网</option>' in home.text
        assert '<option value="live">强制实时</option>' in home.text
        assert 'option value="offline"' not in home.text

        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["service"] == "yicheng-agent"
        assert health.json()["display_name"] == "易程智策"
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
        assert "天气有变化时" not in payload["answer"]
        assert "先避开风险时段" not in payload["answer"]

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
        assert "天气有变化时" in payload["answer"]
        assert "先避开风险时段" in payload["answer"]
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


def test_browser_plan_snapshot_supports_replan_after_cold_start(tmp_path):
    first_app = build_test_app(tmp_path / "first_instance")
    with TestClient(first_app) as client:
        first = client.post(
            "/api/v1/chat",
            json={
                "user_id": "snapshot_user",
                "thread_id": "snapshot_thread",
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
        assert first.status_code == 200, first.text
        previous_plan = first.json()["plan"]

    second_app = build_test_app(tmp_path / "second_instance")
    with TestClient(second_app) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "snapshot_user",
                "thread_id": "snapshot_thread",
                "query": (
                    "把图书馆自习延长30分钟，其他任务保持不变，"
                    "还是18点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:05:00+08:00",
                    "previous_plan": previous_plan,
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["previous_plan"]["id"] == previous_plan["id"]
        assert payload["plan"]["version"] == previous_plan["version"] + 1
        assert payload["plan_diff"]
        assert payload["current_plan_saved"] is True


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
        visible_knowledge = [
            item
            for item in payload["insights"]
            if item["title"] != "规划时间基准"
        ]
        assert len(visible_knowledge) == 1
        assert "图书馆" in visible_knowledge[0]["content"]
        assert "上课时间" not in visible_knowledge[0]["content"]
        assert "阳光长跑" not in visible_knowledge[0]["content"]


def test_operational_knowledge_answers_are_exact_and_focused(tmp_path):
    cases = (
        (
            "校医院周末几点可以看病？",
            ("双休日和节假日", "8:00—11:30", "13:30—16:00"),
            ("各餐厅开放时间",),
        ),
        (
            "阳光长跑哪个时间段可以计入？",
            ("东操场 7:00—21:00", "西北田径场 18:30—21:00"),
            ("第1节",),
        ),
        (
            "体育馆周末开放吗？",
            ("工作日 11:30—20:30", "周末不开放"),
            ("各楼层具体开放时间",),
        ),
        (
            "宿舍周五晚上几点关门？",
            ("周五、周六及节假日", "6:20—24:00"),
            ("各快递点开放时间",),
        ),
    )

    with TestClient(build_test_app(tmp_path)) as client:
        for index, (query, expected, forbidden) in enumerate(cases):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_id": "focused_qa",
                    "thread_id": f"focused_qa_{index}",
                    "query": query,
                    "mode": "offline",
                },
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["status"] == "completed"
            assert payload["plan"] is None
            assert all(text in payload["answer"] for text in expected)
            assert all(text not in payload["answer"] for text in forbidden)


def test_handbook_duration_answer_keeps_decisive_quantity(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "policy_qa",
                "thread_id": "policy_suspension_duration",
                "query": "普通学生休学最多可以多久？",
                "mode": "offline",
            },
        )

        assert response.status_code == 200, response.text
        answer = response.json()["answer"]
        assert "累计不得超过两年" in answer
        assert "创业休学" in answer
        assert answer.split("• ", 1)[1].startswith("休学时间一般")
        assert "转学完成后" not in answer


def test_verified_handbook_rule_bypasses_llm_paraphrase(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        client.app.state.container.llm = MisleadingKnowledgeLLM()
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "policy_live_qa",
                "thread_id": "policy_live_suspension_duration",
                "query": "普通学生休学最多可以多久？",
                "mode": "live",
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        answer = payload["answer"]
        assert "累计不得超过两年" in answer
        assert "创业休学" in answer
        assert "最多只能休学一年" not in answer
        assert "依据来源" in answer


def test_open_ended_overload_request_gets_caring_structured_prompt(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "overloaded_user",
                "query": "最近事情有点多，帮我安排一下。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:05:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "needs_clarification"
        assert "你不用一次把计划想得很完整" in payload["answer"]
        assert "最晚完成时间" in payload["answer"]
        assert not payload["answer"].startswith("你好")


def test_late_library_plan_names_the_floor_specific_boundary(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "late_library_user",
                "thread_id": "late_library_thread",
                "query": "今天22点去图书馆自习30分钟，可以吗？",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:05:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        assert "不同楼层开放时间不同" in payload["answer"]
        assert "21:30以后只能选择" in payload["answer"]
        assert "六层或十二层" in payload["answer"]


def test_student_handbook_questions_keep_the_direct_rule_in_answer(tmp_path):
    cases = [
        ("迟到早退按旷课多少学时计算？", ("0.5学时",)),
        ("旷课累计超过课程教学时数多少不能参加考核？", ("三分之一",)),
        ("学生对处分决定不服，申诉期限是多少天？", ("10日",)),
        ("图书馆七层晚上几点关闭？", ("21:30",)),
        ("晚上宿舍什么时候有热水？", ("16:30", "24:00")),
        (
            "不能按期注册又没办请假，旷课每天按几节课计算？",
            ("每天按6节课计",),
        ),
        ("学生最长可以请假多久？", ("不能超过四周",)),
        (
            "普通休学一般按多久办理，累计最多能休学几年？",
            ("一学期或者一学年", "累计不得超过两年"),
        ),
        (
            "休学期满后，应当在什么时候提交复学申请？",
            ("开学两周内",),
        ),
        (
            "创业休学的四年制本科生最长修业年限是几年？",
            ("最长修业年限为8年",),
        ),
        (
            "实际在校超过几个学期就不能申请普通类转专业？",
            ("超过四学期", "不得申请普通类转专业"),
        ),
        (
            "学校收到学生书面申诉后，一般多久作出处理决定？",
            ("15日内",),
        ),
        (
            "对学校申诉处理决定还有异议，多久内可以向浙江省教育厅"
            "提出书面申诉？",
            ("15日内", "浙江省教育厅"),
        ),
        (
            "休学期间还能享受奖学金和助学金吗？",
            ("不享受在校生待遇", "奖学金、助学金和补贴停发"),
        ),
    ]
    with TestClient(build_test_app(tmp_path)) as client:
        for index, (query, expected_markers) in enumerate(cases):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_id": f"handbook_user_{index}",
                    "query": query,
                    "mode": "offline",
                    "client_context": {
                        "now": "2026-07-24T13:05:00+08:00"
                    },
                },
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["status"] == "completed", (
                f"{case['query']=}; answer={payload['answer']}"
            )
            assert payload["plan"] is None
            for expected in expected_markers:
                assert expected in payload["answer"], (
                    f"{query=}; {expected=}; answer={payload['answer']}"
                )
            assert "依据来源" in payload["answer"]


def test_extended_handbook_blind_questions_are_grounded_end_to_end(tmp_path):
    cases = json.loads(
        (
            BASE_DIR
            / "tests"
            / "fixtures"
            / "knowledge_retrieval_cases.json"
        ).read_text(encoding="utf-8")
    )[21:]
    with TestClient(build_test_app(tmp_path)) as client:
        for index, case in enumerate(cases):
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_id": f"extended_handbook_user_{index}",
                    "thread_id": f"extended_handbook_thread_{index}",
                    "query": case["query"],
                    "mode": "offline",
                },
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["status"] == "completed", (
                f"{case['query']=}; answer={payload['answer']}"
            )
            assert payload["plan"] is None
            assert all(
                marker in payload["answer"]
                for marker in case["expected_markers"]
            ), f"{case['query']=}; answer={payload['answer']}"
            assert "依据来源" in payload["answer"]


def test_opt_in_habit_suggestion_never_auto_inserts_task(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "habit_user",
                "thread_id": "habit_thread",
                "query": "今天14点去菜鸟驿站取快递，18点前结束。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00",
                    "personalization": {
                        "enabled": True,
                        "behavior_patterns": [
                            {
                                "key": "hdu|study|20:00|图书馆",
                                "task_title": "自习",
                                "typical_start": "20:00",
                                "duration_min": 60,
                                "location_name": "图书馆",
                                "campus_id": "hdu_xiasha",
                                "occurrences": 4,
                            }
                        ],
                    },
                },
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    habit = next(
        item
        for item in payload["suggested_actions"]
        if item["kind"] == "habit_suggestion"
    )
    assert habit["dismissible"] is True
    assert "近 4 次" in habit["description"]
    assert "只有你确认后" in habit["description"]
    assert "自习" in payload["answer"]
    assert all(
        "自习" not in item["title"]
        for item in payload["plan"]["items"]
        if item["item_type"] == "task"
    )


def test_repeatedly_dismissed_habit_is_suppressed(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "habit_suppressed_user",
                "thread_id": "habit_suppressed_thread",
                "query": "今天14点去菜鸟驿站取快递，18点前结束。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00",
                    "personalization": {
                        "enabled": True,
                        "behavior_patterns": [
                            {
                                "key": "hdu|study|20:00|图书馆",
                                "task_title": "自习",
                                "typical_start": "20:00",
                                "duration_min": 60,
                                "location_name": "图书馆",
                                "campus_id": "hdu_xiasha",
                                "occurrences": 8,
                                "dismissed_count": 2,
                            }
                        ],
                    },
                },
            },
        )

    assert response.status_code == 200, response.text
    assert all(
        item["kind"] != "habit_suggestion"
        for item in response.json()["suggested_actions"]
    )


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


def test_departure_time_and_origin_create_first_travel_leg(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "departure_user",
                "thread_id": "departure_thread",
                "query": (
                    "今天下午4点从第六教学楼出发，"
                    "去图书馆学习90分钟，之后去东操场跑步30分钟，"
                    "校内骑电瓶车。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        items = payload["plan"]["items"]
        first_travel = next(
            item
            for item in items
            if item["item_type"] == "travel"
        )
        study = task_items(payload)["study"]
        assert first_travel["start_at"] == "2026-07-24T16:00:00+08:00"
        assert first_travel["source"] in {
            "structured",
            "estimated",
            "demo_fixture",
        }
        tasks = task_items(payload)
        assert set(tasks) == {"study", "run"}
        assert first_travel["location_id"] == "library"
        assert study["start_at"] >= first_travel["end_at"]
        assert tasks["run"]["start_at"] >= study["end_at"]


def test_specific_courier_closing_time_blocks_late_pickup(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "courier_user",
                "thread_id": "courier_thread",
                "query": "今天19点去顺丰快递取件，帮我看看能不能安排。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "partial"
        assert not task_items(payload)
        assert "08:00—18:00" in payload["answer"]
        assert "不会擅自把顺丰改成京东或菜鸟" in payload["answer"]
        assert any(
            warning["code"] == "TASK_UNSCHEDULED"
            for warning in payload["warnings"]
        )
        assert any(
            warning["code"] == "OUTSIDE_OPENING_HOURS"
            for warning in payload["warnings"]
        )
        assert next(
            item
            for item in payload["constraint_checks"]
            if item["key"] == "opening"
        )["passed"] is False
        assert payload["suggested_actions"][0]["label"] == "改到 18:00 前"


def test_complex_hdu_request_preserves_every_task_and_verified_time_rule(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "complex_hdu_user",
                "thread_id": "complex_hdu_thread",
                "query": (
                    "明天第3到4节有课，下课后去图书馆七楼自习2小时，"
                    "18点前取顺丰，晚上去西北田径场完成40分钟"
                    "阳光长跑，请帮我安排并提醒注意事项。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-23T08:00:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        statuses = {
            status["task_id"]: status
            for status in payload["task_statuses"]
        }
        assert set(statuses) == {"course_3_4", "study", "parcel", "run"}
        assert statuses["parcel"]["title"] == "取顺丰快递"
        assert statuses["run"]["title"] == "阳光长跑"
        assert payload["location_names"]["library_floor_7_11"] == (
            "图书馆七至十一层"
        )
        assert payload["location_names"]["sf_express"] == "顺丰快递点"
        assert payload["location_names"]["northwest_track"] == "西北田径场"

        scheduled = task_items(payload)
        if "run" in scheduled:
            assert scheduled["run"]["start_at"] >= (
                "2026-07-24T18:30:00+08:00"
            )
            assert scheduled["run"]["end_at"] <= (
                "2026-07-24T21:00:00+08:00"
            )
        if "parcel" in scheduled:
            assert scheduled["parcel"]["end_at"] <= (
                "2026-07-24T18:00:00+08:00"
            )
        assert all(
            status["status"] in {"scheduled", "needs_adjustment"}
            for status in statuses.values()
        )
        assert all(status["message"] for status in statuses.values())


def test_hdu_weekend_venue_rule_blocks_indoor_sport_without_hiding_it(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "weekend_rules_user",
                "thread_id": "weekend_rules_thread",
                "query": (
                    "今天下午去校医院就诊30分钟，再打羽毛球1小时，"
                    "晚上回宿舍洗澡30分钟，请把注意事项也告诉我。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-25T08:00:00+08:00"
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        statuses = {
            status["task_id"]: status
            for status in payload["task_statuses"]
        }
        assert set(statuses) == {"clinic", "badminton", "bath"}
        assert statuses["badminton"]["status"] == "needs_adjustment"
        assert "周末" in payload["answer"]
        assert "不开放" in payload["answer"]
        assert "改到宿舍" not in payload["answer"]
        assert any(
            issue["code"] == "TASK_UNSCHEDULED"
            and issue["task_ids"] == ["badminton"]
            for issue in payload["warnings"]
        )


def test_browser_memory_snapshot_survives_without_server_record(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "snapshot_memory_user",
                "thread_id": "snapshot_memory_thread",
                "query": (
                    "今天14点后去图书馆自习1小时，再去取快递，"
                    "18点前结束。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00",
                    "memories": [
                        {
                            "category": "preference",
                            "key": "buffer_min",
                            "label": "日程缓冲时间",
                            "value": 20,
                            "enabled": True,
                        }
                    ],
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        ordered = sorted(
            payload["plan"]["items"],
            key=lambda item: item["start_at"],
        )
        travel = next(item for item in ordered if item["item_type"] == "travel")
        parcel = next(
            item for item in ordered if item.get("task_id") == "parcel"
        )
        assert (
            datetime.fromisoformat(parcel["start_at"])
            - datetime.fromisoformat(travel["end_at"])
        ).total_seconds() >= 20 * 60
        assert any(
            item["source_label"] == "个人记忆库"
            for item in payload["insights"]
        )


def test_saved_walking_pace_personalizes_travel_time(tmp_path):
    def request(client, user_id, memories):
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": user_id,
                "thread_id": f"{user_id}_thread",
                "query": (
                    "今天14点从第六教学楼出发，"
                    "步行去图书馆自习1小时。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00",
                    "memories": memories,
                },
            },
        )
        assert response.status_code == 200, response.text
        return next(
            item
            for item in response.json()["plan"]["items"]
            if item["item_type"] == "travel"
        )

    with TestClient(build_test_app(tmp_path)) as client:
        normal = request(client, "normal_walk_user", [])
        slow = request(
            client,
            "slow_walk_user",
            [
                {
                    "category": "preference",
                    "key": "walking_speed",
                    "label": "步行节奏",
                    "value": "slow",
                    "enabled": True,
                }
            ],
        )

    assert slow["base_duration_min"] > normal["base_duration_min"]
    assert slow["end_at"] > normal["end_at"]


def test_saved_preferred_place_applies_when_request_has_no_place(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "preferred_place_user",
                "thread_id": "preferred_place_thread",
                "query": "今天14点后自习1小时。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00",
                    "memories": [
                        {
                            "category": "preference",
                            "key": "preferred_locations",
                            "label": "常用地点",
                            "value": ["第六教学楼"],
                            "enabled": True,
                        }
                    ],
                },
            },
        )

    assert response.status_code == 200, response.text
    study = next(
        item
        for item in task_items(response.json()).values()
        if "自习" in item["title"]
    )
    assert study["location_id"] == "teaching_building_6"


def test_saved_study_place_applies_to_daily_plan(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "preferred_study_place_user",
                "thread_id": "preferred_study_place_thread",
                "query": "今天14点后自习1小时。",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00",
                    "memories": [
                        {
                            "category": "preference",
                            "key": "preferred_study_location",
                            "label": "常用自习地点",
                            "value": "图书馆六层",
                            "enabled": True,
                        }
                    ],
                },
            },
        )

    assert response.status_code == 200, response.text
    study = next(
        item
        for item in task_items(response.json()).values()
        if "自习" in item["title"]
    )
    assert study["location_id"] == "library_floor_6_12"


def test_saved_study_period_is_soft_daily_preference(tmp_path):
    def request(query: str):
        with TestClient(build_test_app(tmp_path)) as client:
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_id": "preferred_study_period_user",
                    "thread_id": "preferred_study_period_thread",
                    "query": query,
                    "mode": "offline",
                    "client_context": {
                        "now": "2026-07-24T08:00:00+08:00",
                        "memories": [
                            {
                                "category": "habit",
                                "key": "preferred_study_period",
                                "label": "高效学习时段",
                                "value": "evening",
                                "enabled": True,
                            }
                        ],
                    },
                },
            )
        assert response.status_code == 200, response.text
        return next(
            item
            for item in task_items(response.json()).values()
            if "自习" in item["title"]
        )

    preferred = request("今天去图书馆自习1小时。")
    deadline_override = request("今天去图书馆自习1小时，17点前结束。")

    assert datetime.fromisoformat(preferred["start_at"]).hour >= 18
    assert datetime.fromisoformat(deadline_override["end_at"]).hour <= 17


def test_avoid_tight_schedule_memory_can_be_disabled(tmp_path):
    def buffer_after_travel(client, user_id, memory_value):
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": user_id,
                "thread_id": f"{user_id}_thread",
                "query": (
                    "今天14点后去图书馆自习1小时，"
                    "再去菜鸟驿站取快递。"
                ),
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T13:00:00+08:00",
                    "memories": [
                        {
                            "category": "preference",
                            "key": "avoid_tight_schedule",
                            "label": "避免行程太紧",
                            "value": memory_value,
                            "enabled": True,
                        }
                    ],
                },
            },
        )
        assert response.status_code == 200, response.text
        items = sorted(
            response.json()["plan"]["items"],
            key=lambda item: item["start_at"],
        )
        travel = next(item for item in items if item["item_type"] == "travel")
        parcel = next(
            item for item in items if item.get("task_id") == "parcel"
        )
        return int(
            (
                datetime.fromisoformat(parcel["start_at"])
                - datetime.fromisoformat(travel["end_at"])
            ).total_seconds()
            // 60
        )

    with TestClient(build_test_app(tmp_path)) as client:
        relaxed = buffer_after_travel(client, "relaxed_user", False)
        buffered = buffer_after_travel(client, "buffered_user", True)

    assert relaxed == 0
    assert buffered >= 10


def test_browser_timetable_snapshot_is_a_fixed_constraint(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "user_id": "snapshot_timetable_user",
                "thread_id": "snapshot_timetable_thread",
                "query": "今天哪几节有课？",
                "mode": "offline",
                "client_context": {
                    "now": "2026-07-24T07:00:00+08:00",
                    "timetable": {
                        "name": "浏览器课表",
                        "term_start": "2026-07-20",
                        "enabled": True,
                        "entries": [
                            {
                                "course_name": "高等数学",
                                "weekday": 5,
                                "start_period": 1,
                                "end_period": 2,
                                "location": "第六教学楼",
                                "weeks": [1],
                            }
                        ],
                    },
                },
            },
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "completed"
        assert "高等数学" in payload["answer"]
        assert "第1—2节" in payload["answer"]
