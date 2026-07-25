from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from tests.integration.test_api_demos import build_test_app


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
