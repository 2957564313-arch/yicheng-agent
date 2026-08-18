from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api import weeks as weekly_api
from app.repositories.exceptions import (
    WeeklyPlanSnapshotChanged,
    WeeklyPlanSuperseded,
)
from tests.integration.test_api_demos import build_test_app


@pytest.fixture(autouse=True)
def freeze_weekly_api_clock(monkeypatch):
    """Keep fixed-date weekly fixtures deterministic as wall-clock time moves."""

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(
                2026,
                7,
                23,
                20,
                0,
                tzinfo=ZoneInfo("Asia/Shanghai"),
            )
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(weekly_api, "datetime", FixedDateTime)


def weekly_payload() -> dict:
    return {
        "user_id": "weekly_api_user",
        "campus_id": "hdu_xiasha",
        "week_start": "2026-07-27",
        "timezone": "Asia/Shanghai",
        "goals": [
            {
                "title": "完成课程设计",
                "deadline": "2026-07-31T22:00:00+08:00",
                "total_duration_min": 240,
                "min_chunk_min": 60,
                "max_chunk_min": 120,
                "importance": 5,
                "stages": [
                    {
                        "id": "coding",
                        "title": "编码",
                        "duration_min": 120,
                        "min_chunk_min": 60,
                    },
                    {
                        "id": "testing",
                        "title": "测试",
                        "sequence": 2,
                        "duration_min": 120,
                        "min_chunk_min": 60,
                        "depends_on_stage_ids": ["coding"],
                    },
                ],
            }
        ],
        "capacities": [
            {
                "date": "2026-07-27",
                "windows": [
                    {
                        "start_at": "2026-07-27T18:00:00+08:00",
                        "end_at": "2026-07-27T21:00:00+08:00",
                    }
                ],
            },
            {
                "date": "2026-07-28",
                "windows": [
                    {
                        "start_at": "2026-07-28T18:00:00+08:00",
                        "end_at": "2026-07-28T21:00:00+08:00",
                    }
                ],
            },
        ],
    }


def test_weekly_plan_persists_versions_and_events_are_idempotent(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        created = client.post("/api/v1/weeks/plan", json=weekly_payload())
        assert created.status_code == 201, created.text
        plan = created.json()["weekly_plan"]
        assert plan["status"] == "valid"
        assert plan["version"] == 1
        assert sum(
            item["allocated_duration_min"]
            for item in plan["allocations"]
        ) == 240
        assert all(
            60 <= item["allocated_duration_min"] <= 120
            for item in plan["allocations"]
        )
        assert "每天真正执行前" in created.json()["answer"]

        fetched = client.get(
            "/api/v1/weeks/2026-07-27",
            params={
                "user_id": "weekly_api_user",
                "campus_id": "hdu_xiasha",
            },
        )
        assert fetched.status_code == 200
        assert fetched.json()["weekly_plan"]["id"] == plan["id"]

        allocation = plan["allocations"][0]
        event_payload = {
            "event_type": "partial",
            "allocation_id": allocation["id"],
            "occurred_at": "2026-07-27T19:00:00+08:00",
            "completed_duration_min": 60,
            "client_event_id": "device-event-001",
        }
        first_event = client.post(
            f"/api/v1/weeks/{plan['id']}/events",
            params={"user_id": "weekly_api_user"},
            json=event_payload,
        )
        assert first_event.status_code == 200, first_event.text
        assert first_event.json()["applied"] is True
        assert (
            first_event.json()["weekly_plan"]["goals"][0][
                "remaining_duration_min"
            ]
            == 180
        )

        duplicate = client.post(
            f"/api/v1/weeks/{plan['id']}/events",
            params={"user_id": "weekly_api_user"},
            json=event_payload,
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["applied"] is False
        assert (
            duplicate.json()["weekly_plan"]["goals"][0][
                "remaining_duration_min"
            ]
            == 180
        )

        second = client.post("/api/v1/weeks/plan", json=weekly_payload())
        assert second.status_code == 201, second.text
        assert second.json()["weekly_plan"]["version"] == 2
        assert second.json()["weekly_plan"]["baseline_plan_id"] == plan["id"]

        versions = client.get(
            "/api/v1/weeks/2026-07-27/versions",
            params={
                "user_id": "weekly_api_user",
                "campus_id": "hdu_xiasha",
            },
        )
        assert versions.status_code == 200
        assert [item["version"] for item in versions.json()["items"]] == [
            1,
            2,
        ]


def test_weekly_replan_adds_task_preserves_lineage_and_rejects_stale_base(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        created = client.post("/api/v1/weeks/plan", json=weekly_payload())
        assert created.status_code == 201, created.text
        baseline = created.json()["weekly_plan"]

        response = client.post(
            f"/api/v1/weeks/{baseline['id']}/replan",
            params={"user_id": "weekly_api_user"},
            json={
                "trigger_type": "new_task",
                "capacities": weekly_payload()["capacities"],
                "additional_goals": [
                    {
                        "title": "新增答辩提纲",
                        "deadline": "2026-07-28T21:00:00+08:00",
                        "total_duration_min": 60,
                        "min_chunk_min": 60,
                        "max_chunk_min": 60,
                        "splittable": False,
                    }
                ],
            },
        )

        assert response.status_code == 201, response.text
        data = response.json()
        plan = data["weekly_plan"]
        assert plan["version"] == 2
        assert plan["baseline_plan_id"] == baseline["id"]
        assert plan["trigger_type"] == "new_task"
        assert plan["metrics"]["preservation_rate"] == 1
        assert plan["metrics"]["moved_allocation_count"] == 0
        assert any(
            goal["title"] == "新增答辩提纲"
            and goal["source"] == "replan_new_task"
            for goal in plan["goals"]
        )
        assert {
            allocation["id"] for allocation in baseline["allocations"]
        } <= {
            allocation["source_allocation_id"]
            for allocation in plan["allocations"]
            if allocation["source_allocation_id"]
        }
        assert "保留率 100%" in data["answer"]

        versions = client.get(
            "/api/v1/weeks/2026-07-27/versions",
            params={
                "user_id": "weekly_api_user",
                "campus_id": "hdu_xiasha",
            },
        )
        assert versions.status_code == 200
        assert [item["version"] for item in versions.json()["items"]] == [
            1,
            2,
        ]

        stale_retry = client.post(
            f"/api/v1/weeks/{baseline['id']}/replan",
            params={"user_id": "weekly_api_user"},
            json={
                "trigger_type": "manual",
                "capacities": weekly_payload()["capacities"],
            },
        )
        assert stale_retry.status_code == 409
        assert (
            stale_retry.json()["error"]["code"]
            == "WEEKLY_PLAN_SUPERSEDED"
        )

        stale_event = client.post(
            f"/api/v1/weeks/{baseline['id']}/events",
            params={"user_id": "weekly_api_user"},
            json={
                "event_type": "completed",
                "allocation_id": baseline["allocations"][0]["id"],
                "occurred_at": "2026-07-27T20:00:00+08:00",
                "completed_duration_min": (
                    baseline["allocations"][0]["allocated_duration_min"]
                ),
                "client_event_id": "stale-version-event",
            },
        )
        assert stale_event.status_code == 409
        assert (
            stale_event.json()["error"]["code"]
            == "WEEKLY_PLAN_SUPERSEDED"
        )

        stale_materialization = client.post(
            (
                f"/api/v1/weeks/{baseline['id']}/days/"
                "2026-07-27/materialize"
            ),
            params={
                "user_id": "weekly_api_user",
                "prefer_live": False,
            },
        )
        assert stale_materialization.status_code == 409
        assert (
            stale_materialization.json()["error"]["code"]
            == "WEEKLY_PLAN_SUPERSEDED"
        )


def test_weekly_replan_rejects_unknown_invalidated_allocation_id(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        created = client.post("/api/v1/weeks/plan", json=weekly_payload())
        assert created.status_code == 201, created.text
        baseline = created.json()["weekly_plan"]

        response = client.post(
            f"/api/v1/weeks/{baseline['id']}/replan",
            params={"user_id": "weekly_api_user"},
            json={
                "trigger_type": "fixed_event_changed",
                "capacities": weekly_payload()["capacities"],
                "invalidated_allocation_ids": [
                    "missing-allocation",
                ],
            },
        )

        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "WEEKLY_ALLOCATION_NOT_FOUND"
        assert error["details"] == [
            {
                "allocation_ids": ["missing-allocation"],
            }
        ]


def test_three_weekly_demos_cover_valid_shortage_and_personalization(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        catalog = client.get("/api/v1/weeks/demos/catalog")
        assert catalog.status_code == 200
        assert [item["id"] for item in catalog.json()] == [
            "weekly_demo_01_sprint",
            "weekly_demo_02_overload",
            "weekly_demo_03_portable",
        ]

        results = {}
        summaries = {}
        for item in catalog.json():
            response = client.post(
                f"/api/v1/weeks/demos/{item['id']}/run",
                params={"user_id": f"fixture_{item['id']}"},
            )
            assert response.status_code == 200, response.text
            results[item["id"]] = response.json()["weekly_plan"]
            summaries[item["id"]] = response.json()["capacity_summary"]

        assert results["weekly_demo_01_sprint"]["status"] == "valid"
        assert (
            results["weekly_demo_01_sprint"]["metrics"][
                "allocated_duration_min"
            ]
            == 740
        )
        overload = results["weekly_demo_02_overload"]
        assert overload["status"] == "infeasible"
        assert overload["metrics"]["unallocated_duration_min"] == 240
        assert overload["issues"][0]["details"]["missing_min"] == 240
        portable = results["weekly_demo_03_portable"]
        assert portable["status"] == "valid"
        assert portable["campus_id"] == "hdu_xiasha"
        assert portable["metrics"]["allocated_duration_min"] == 630
        assert summaries["weekly_demo_03_portable"]["timetable_applied"] is True
        assert (
            summaries["weekly_demo_03_portable"]["excluded_course_count"]
            == 4
        )
        assert summaries["weekly_demo_03_portable"]["memory_labels"] == [
            "常用学习时段",
            "常用学习地点",
        ]
        exercise_goal = next(
            goal
            for goal in portable["goals"]
            if goal["title"] == "本周运动两次"
        )
        exercise_allocations = [
            item
            for item in portable["allocations"]
            if item["goal_id"] == exercise_goal["id"]
        ]
        assert {
            item["location_id"] for item in exercise_allocations
        } == {"东操场"}
        visitor_memories = client.get(
            "/api/v1/users/fixture_weekly_demo_03_portable/memories"
        )
        assert visitor_memories.status_code == 200
        assert visitor_memories.json()["items"] == []


def test_weekly_demo_remains_replayable_after_fixture_week(
    tmp_path,
    monkeypatch,
):
    class LateDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(
                2026,
                8,
                17,
                12,
                0,
                tzinfo=ZoneInfo("Asia/Shanghai"),
            )
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(weekly_api, "datetime", LateDateTime)
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/weeks/demos/weekly_demo_01_sprint/run",
            params={"user_id": "late_fixture_user"},
        )

    assert response.status_code == 200, response.text
    plan = response.json()["weekly_plan"]
    assert plan["status"] == "valid"
    assert plan["metrics"]["allocated_duration_min"] == 740


def test_user_can_create_a_real_weekly_plan_from_natural_language(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/weeks/plan/from-text",
            json={
                "user_id": "weekly_text_user",
                "campus_id": "hdu_xiasha",
                "week_start": "2026-07-27",
                "timezone": "Asia/Shanghai",
                "query": (
                    "周五22:00前完成课程设计，共8小时，"
                    "其中编码4小时、测试2小时、报告2小时；"
                    "周三20:00前完成论文阅读，共2小时；"
                    "本周跑步2次，每次40分钟，尽量晚上去东操场。"
                ),
            },
        )

        assert response.status_code == 201, response.text
        data = response.json()
        plan = data["weekly_plan"]
        assert data["parser"] == "structured_rules"
        assert plan["status"] == "valid"
        assert len(plan["goals"]) == 3
        assert plan["metrics"]["requested_duration_min"] == 680
        assert plan["metrics"]["allocated_duration_min"] == 680
        running = next(
            goal for goal in plan["goals"] if goal["title"] == "跑步"
        )
        running_days = {
            item["date"]
            for item in plan["allocations"]
            if item["goal_id"] == running["id"]
        }
        assert len(running_days) == 2
        assert data["capacity_summary"]["source"] == "personal_context"
        assert "尚未启用个人课表" in " ".join(
            data["capacity_summary"]["notes"]
        )


def test_weekly_text_returns_a_clear_question_for_missing_duration(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/weeks/plan/from-text",
            json={
                "user_id": "weekly_clarify_user",
                "campus_id": "hdu_xiasha",
                "week_start": "2026-07-27",
                "query": "周五前完善创新项目方案。",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "WEEKLY_CLARIFICATION_REQUIRED"
        assert "投入多长时间" in data["error"]["details"][0]["question"]


def test_weekly_concurrency_errors_have_stable_409_mappings(
    tmp_path,
    monkeypatch,
):
    with TestClient(build_test_app(tmp_path)) as client:
        created = client.post("/api/v1/weeks/plan", json=weekly_payload())
        assert created.status_code == 201, created.text
        baseline = created.json()["weekly_plan"]
        container = client.app.state.container

        async def raise_superseded(**_kwargs):
            raise WeeklyPlanSuperseded("new weekly version exists")

        monkeypatch.setattr(
            container.weekly_grounding,
            "materialize_day",
            raise_superseded,
        )
        materialize = client.post(
            (
                f"/api/v1/weeks/{baseline['id']}/days/"
                "2026-07-27/materialize"
            ),
            params={
                "user_id": "weekly_api_user",
                "prefer_live": False,
            },
        )
        assert materialize.status_code == 409
        assert (
            materialize.json()["error"]["code"]
            == "WEEKLY_PLAN_SUPERSEDED"
        )
        assert materialize.json()["error"]["retryable"] is False

        def raise_snapshot_changed(*_args, **_kwargs):
            raise WeeklyPlanSnapshotChanged("completion progress changed")

        monkeypatch.setattr(
            container.weekly_plans,
            "save_replan",
            raise_snapshot_changed,
        )
        replan = client.post(
            f"/api/v1/weeks/{baseline['id']}/replan",
            params={"user_id": "weekly_api_user"},
            json={
                "trigger_type": "manual",
                "capacities": weekly_payload()["capacities"],
            },
        )
        assert replan.status_code == 409
        assert (
            replan.json()["error"]["code"]
            == "WEEKLY_REPLAN_SNAPSHOT_CHANGED"
        )
        assert replan.json()["error"]["retryable"] is True
