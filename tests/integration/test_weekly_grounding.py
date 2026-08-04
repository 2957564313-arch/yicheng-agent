from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.repositories.exceptions import (
    WeeklyPlanSnapshotChanged,
    WeeklyPlanSuperseded,
)
from app.repositories.plans import WeeklyGroundingSnapshotChanged
from app.schemas.common import TaskFlexibility
from app.schemas.task import Task
from app.schemas.weekly import (
    AllocationStatus,
    CompletionEventCreate,
    CompletionEventType,
    DailyCapacity,
    DailyWindow,
    DayAllocation,
    WeeklyGoalCreate,
    WeeklyPlanCreateRequest,
    WeeklyTriggerType,
)
from tests.integration.test_api_demos import build_test_app

TZ = ZoneInfo("Asia/Shanghai")
WEEK_START = date(2026, 7, 27)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 27, hour, minute, tzinfo=TZ)


def weekly_request(
    *,
    user_id: str,
    title: str,
    location_id: str,
    window_start: datetime,
    window_end: datetime,
) -> WeeklyPlanCreateRequest:
    return WeeklyPlanCreateRequest(
        user_id=user_id,
        campus_id="hdu_xiasha",
        week_start=WEEK_START,
        goals=[
            WeeklyGoalCreate(
                title=title,
                deadline=window_end,
                total_duration_min=60,
                min_chunk_min=60,
                max_chunk_min=60,
                splittable=False,
                preferred_locations=[location_id],
                importance=4,
            )
        ],
        capacities=[
            DailyCapacity(
                date=WEEK_START,
                windows=[
                    DailyWindow(
                        start_at=window_start,
                        end_at=window_end,
                    )
                ],
            )
        ],
    )


@pytest.mark.asyncio
async def test_weekly_day_is_grounded_saved_bound_and_idempotent(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="grounding_user",
            title="课程复习",
            location_id="library",
            window_start=at(18),
            window_end=at(21),
        )
        weekly_plan = container.weekly_allocator.allocate(
            request,
            now=at(9),
        )
        weekly_plan.allocations[0] = weekly_plan.allocations[0].model_copy(
            update={
                "preferred_start_at": at(20),
                "preferred_end_at": at(21),
            }
        )
        container.weekly_plans.save(weekly_plan)

        result = await container.weekly_grounding.materialize_day(
            plan_id=weekly_plan.id,
            user_id=request.user_id,
            target_date=WEEK_START,
            prefer_live=False,
            now=at(9),
        )

        assert result.status == "grounded"
        assert result.plan is not None
        assert result.plan.status.value == "valid"
        assert result.plan.metrics.hard_violation_count == 0
        assert result.evidence.opening_rule_location_ids == ["library"]
        assert result.evidence.timetable_task_count == 0
        weekly_task_id = container.weekly_grounding.task_id_for_allocation(
            weekly_plan.allocations[0].id
        )
        grounded_item = next(
            item
            for item in result.plan.items
            if item.task_id == weekly_task_id
        )
        assert grounded_item.start_at == at(20)

        persisted_week = container.weekly_plans.get(weekly_plan.id)
        assert persisted_week is not None
        allocation = persisted_week.allocations[0]
        assert allocation.status.value == "scheduled"
        assert allocation.daily_plan_id == result.plan.id

        agenda_items = container.agenda.list_items(
            user_id=request.user_id,
            start_date=WEEK_START,
            end_date=WEEK_START,
        )
        assert any(item.title == "课程复习" for item in agenda_items)

        repeated = client.post(
            (
                f"/api/v1/weeks/{weekly_plan.id}/days/"
                f"{WEEK_START.isoformat()}/materialize"
            ),
            params={
                "user_id": request.user_id,
                "prefer_live": False,
            },
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["status"] == "already_grounded"
        assert repeated.json()["plan"]["id"] == result.plan.id


@pytest.mark.asyncio
async def test_weekly_day_rejects_closed_venue_without_persisting(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="closed_venue_user",
            title="取顺丰快递",
            location_id="sf_express",
            window_start=at(19),
            window_end=at(21),
        )
        weekly_plan = container.weekly_allocator.allocate(
            request,
            now=at(9),
        )
        container.weekly_plans.save(weekly_plan)

        result = await container.weekly_grounding.materialize_day(
            plan_id=weekly_plan.id,
            user_id=request.user_id,
            target_date=WEEK_START,
            prefer_live=False,
            now=at(9),
        )

        assert result.status == "infeasible"
        assert result.plan is not None
        assert result.plan.status.value == "infeasible"
        assert any(
            issue.code in {"TASK_UNSCHEDULED", "OUTSIDE_OPENING_HOURS"}
            for issue in result.issues
        )
        persisted_week = container.weekly_plans.get(weekly_plan.id)
        assert persisted_week is not None
        allocation = persisted_week.allocations[0]
        assert allocation.status.value == "proposed"
        assert allocation.daily_plan_id is None
        assert (
            container.plans.latest_for_thread(
                container.weekly_grounding._thread_id(
                    plan_id=weekly_plan.id,
                    target_date=WEEK_START,
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_new_week_version_regrounds_mixed_day_with_stable_task_lineage(
    tmp_path,
):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="version_grounding_user",
            title="原有学习任务",
            location_id="library",
            window_start=at(18),
            window_end=at(21),
        )
        baseline = container.weekly_allocator.allocate(request, now=at(9))
        container.weekly_plans.save(baseline)
        first = await container.weekly_grounding.materialize_day(
            plan_id=baseline.id,
            user_id=request.user_id,
            target_date=WEEK_START,
            prefer_live=False,
            now=at(9),
        )
        assert first.status == "grounded"
        assert first.plan is not None

        grounded_baseline = container.weekly_plans.get(baseline.id)
        assert grounded_baseline is not None
        replanned = container.weekly_replanner.replan(
            baseline=grounded_baseline,
            capacities=request.capacities,
            trigger=WeeklyTriggerType.NEW_TASK,
            additional_goals=[
                WeeklyGoalCreate(
                    title="新增复盘任务",
                    deadline=at(21),
                    total_duration_min=60,
                    min_chunk_min=60,
                    max_chunk_min=60,
                    splittable=False,
                    preferred_locations=["library"],
                )
            ],
            now=at(9),
        )
        container.weekly_plans.save(replanned)

        second = await container.weekly_grounding.materialize_day(
            plan_id=replanned.id,
            user_id=request.user_id,
            target_date=WEEK_START,
            prefer_live=False,
            now=at(9),
        )

        assert second.status == "grounded"
        assert second.plan is not None
        assert second.plan.id != first.plan.id
        expected_task_ids = {
            container.weekly_grounding.task_id_for_allocation(
                allocation.lineage_id or allocation.id
            )
            for allocation in replanned.allocations
        }
        assert expected_task_ids == {
            item.task_id
            for item in second.plan.items
            if item.task_id in expected_task_ids
        }
        persisted = container.weekly_plans.get(replanned.id)
        assert persisted is not None
        assert {
            allocation.daily_plan_id for allocation in persisted.allocations
        } == {second.plan.id}


@pytest.mark.asyncio
async def test_weekly_period_preference_moves_when_course_occupies_morning(
    tmp_path,
    monkeypatch,
):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="soft_period_user",
            title="课程复习",
            location_id="library",
            window_start=at(9),
            window_end=at(17),
        )
        weekly_plan = container.weekly_allocator.allocate(
            request,
            now=at(8),
        )
        allocation = weekly_plan.allocations[0]
        weekly_plan.allocations[0] = allocation.model_copy(
            update={
                "window_start_at": at(9),
                "window_end_at": at(17),
                "preferred_start_at": at(9),
                "preferred_end_at": at(10),
                "preferred_period": "morning",
            }
        )
        container.weekly_plans.save(weekly_plan)

        morning_course = Task(
            id="timetable_morning_course",
            title="上午固定课程",
            date=WEEK_START,
            duration_min=180,
            fixed_start=at(9),
            fixed_end=at(12),
            flexibility=TaskFlexibility.FIXED,
            tags=["course", "hard_constraint"],
        )
        monkeypatch.setattr(
            container.timetables,
            "tasks_for_date",
            lambda **_kwargs: [morning_course],
        )

        result = await container.weekly_grounding.materialize_day(
            plan_id=weekly_plan.id,
            user_id=request.user_id,
            target_date=WEEK_START,
            prefer_live=False,
            now=at(8),
        )

        assert result.status == "grounded"
        assert result.plan is not None
        assert result.evidence.timetable_task_count == 1
        weekly_task_id = container.weekly_grounding.task_id_for_allocation(
            allocation.id
        )
        grounded = next(
            item
            for item in result.plan.items
            if item.task_id == weekly_task_id
        )
        # The default ten-minute buffer remains a hard execution safeguard.
        assert grounded.start_at == at(12, 10)
        assert grounded.end_at == at(13, 10)


@pytest.mark.asyncio
async def test_weekly_grounding_publication_rolls_back_without_orphan_plan(
    tmp_path,
    monkeypatch,
):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="grounding_rollback_user",
            title="原子发布回滚",
            location_id="library",
            window_start=at(18),
            window_end=at(21),
        )
        weekly_plan = container.weekly_allocator.allocate(request, now=at(9))
        container.weekly_plans.save(weekly_plan)
        original_insert = container.plans._insert_on_connection

        def fail_after_insert(
            connection,
            *,
            plan,
            parent_plan_id=None,
            agenda_published=False,
        ):
            original_insert(
                connection,
                plan=plan,
                parent_plan_id=parent_plan_id,
                agenda_published=agenda_published,
            )
            raise RuntimeError("injected publication failure")

        monkeypatch.setattr(
            container.plans,
            "_insert_on_connection",
            fail_after_insert,
        )

        with pytest.raises(
            RuntimeError,
            match="injected publication failure",
        ):
            await container.weekly_grounding.materialize_day(
                plan_id=weekly_plan.id,
                user_id=request.user_id,
                target_date=WEEK_START,
                prefer_live=False,
                now=at(9),
            )

        thread_id = container.weekly_grounding._thread_id(
            plan_id=weekly_plan.id,
            target_date=WEEK_START,
        )
        with container.plans.database.connect() as connection:
            plan_count = connection.execute(
                "SELECT COUNT(*) FROM plans WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()[0]
            item_count = connection.execute(
                """
                SELECT COUNT(*) FROM plan_items
                WHERE plan_id IN (
                    SELECT id FROM plans WHERE thread_id = ?
                )
                """,
                (thread_id,),
            ).fetchone()[0]
            thread_count = connection.execute(
                "SELECT COUNT(*) FROM threads WHERE id = ?",
                (thread_id,),
            ).fetchone()[0]
        assert (plan_count, item_count, thread_count) == (0, 0, 0)

        persisted = container.weekly_plans.get(weekly_plan.id)
        assert persisted is not None
        assert persisted.allocations[0].daily_plan_id is None
        assert persisted.allocations[0].status.value == "proposed"
        assert all(
            item.title != "原子发布回滚"
            for item in container.agenda.list_items(
                user_id=request.user_id,
                start_date=WEEK_START,
                end_date=WEEK_START,
            )
        )


@pytest.mark.asyncio
async def test_weekly_grounding_rejects_changed_allocation_fingerprint(
    tmp_path,
    monkeypatch,
):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="grounding_snapshot_user",
            title="进行中进度保护",
            location_id="library",
            window_start=at(18),
            window_end=at(21),
        )
        weekly_plan = container.weekly_allocator.allocate(request, now=at(9))
        weekly_plan.allocations[0] = weekly_plan.allocations[0].model_copy(
            update={"status": AllocationStatus.SCHEDULED}
        )
        container.weekly_plans.save(weekly_plan)
        allocation_id = weekly_plan.allocations[0].id
        original_publish = container.plans.publish_weekly_day

        def change_progress_before_publish(**kwargs):
            with container.plans.database.transaction() as connection:
                row = connection.execute(
                    """
                    SELECT allocation_json FROM day_allocations
                    WHERE id = ?
                    """,
                    (allocation_id,),
                ).fetchone()
                allocation = DayAllocation.model_validate_json(
                    row["allocation_json"]
                )
                allocation.completed_duration_min = 15
                allocation.updated_at = at(10)
                connection.execute(
                    """
                    UPDATE day_allocations
                    SET allocation_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        allocation.model_dump_json(),
                        allocation.updated_at.isoformat(),
                        allocation.id,
                    ),
                )
            return original_publish(**kwargs)

        monkeypatch.setattr(
            container.plans,
            "publish_weekly_day",
            change_progress_before_publish,
        )

        with pytest.raises(WeeklyGroundingSnapshotChanged):
            await container.weekly_grounding.materialize_day(
                plan_id=weekly_plan.id,
                user_id=request.user_id,
                target_date=WEEK_START,
                prefer_live=False,
                now=at(9),
            )

        thread_id = container.weekly_grounding._thread_id(
            plan_id=weekly_plan.id,
            target_date=WEEK_START,
        )
        assert container.plans.latest_for_thread(thread_id) is None
        persisted = container.weekly_plans.get(weekly_plan.id)
        assert persisted is not None
        assert persisted.allocations[0].completed_duration_min == 15
        assert persisted.allocations[0].daily_plan_id is None


def test_weekly_grounding_snapshot_conflict_has_retryable_409(
    tmp_path,
    monkeypatch,
):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="grounding_conflict_api_user",
            title="冲突响应",
            location_id="library",
            window_start=at(18),
            window_end=at(21),
        )
        weekly_plan = container.weekly_allocator.allocate(request, now=at(9))
        container.weekly_plans.save(weekly_plan)

        async def raise_snapshot_changed(**_kwargs):
            raise WeeklyGroundingSnapshotChanged("allocation changed")

        monkeypatch.setattr(
            container.weekly_grounding,
            "materialize_day",
            raise_snapshot_changed,
        )
        response = client.post(
            (
                f"/api/v1/weeks/{weekly_plan.id}/days/"
                f"{WEEK_START.isoformat()}/materialize"
            ),
            params={"user_id": request.user_id, "prefer_live": False},
        )

        assert response.status_code == 409
        assert (
            response.json()["error"]["code"]
            == "WEEKLY_GROUNDING_SNAPSHOT_CHANGED"
        )
        assert response.json()["error"]["retryable"] is True


def test_concurrent_weekly_grounding_publishes_one_plan(tmp_path, monkeypatch):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="grounding_concurrent_user",
            title="并发原子发布",
            location_id="library",
            window_start=at(18),
            window_end=at(21),
        )
        weekly_plan = container.weekly_allocator.allocate(request, now=at(9))
        container.weekly_plans.save(weekly_plan)
        original_publish = container.plans.publish_weekly_day
        ready = Barrier(2, timeout=10)

        def publish_together(**kwargs):
            ready.wait()
            return original_publish(**kwargs)

        monkeypatch.setattr(
            container.plans,
            "publish_weekly_day",
            publish_together,
        )

        async def materialize():
            return await container.weekly_grounding.materialize_day(
                plan_id=weekly_plan.id,
                user_id=request.user_id,
                target_date=WEEK_START,
                prefer_live=False,
                now=at(9),
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(asyncio.run, materialize())
                for _ in range(2)
            ]
            results = [future.result(timeout=20) for future in futures]

        assert {result.status for result in results} == {
            "grounded",
            "already_grounded",
        }
        assert len({result.plan.id for result in results}) == 1
        thread_id = container.weekly_grounding._thread_id(
            plan_id=weekly_plan.id,
            target_date=WEEK_START,
        )
        with container.plans.database.connect() as connection:
            plan_count = connection.execute(
                "SELECT COUNT(*) FROM plans WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()[0]
        assert plan_count == 1
        persisted = container.weekly_plans.get(weekly_plan.id)
        assert persisted is not None
        assert {
            item.daily_plan_id for item in persisted.allocations
        } == {results[0].plan.id}


def test_event_and_replan_cas_never_silently_lose_progress(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="event_replan_cas_user",
            title="并发进度保护",
            location_id="library",
            window_start=at(18),
            window_end=at(21),
        )
        baseline = container.weekly_allocator.allocate(request, now=at(9))
        container.weekly_plans.save(baseline)
        snapshot = container.weekly_plans.get(baseline.id)
        assert snapshot is not None
        fingerprint = container.weekly_plans.weekly_plan_fingerprint(snapshot)
        replanned = container.weekly_replanner.replan(
            baseline=snapshot,
            capacities=request.capacities,
            trigger=WeeklyTriggerType.MANUAL,
            now=at(9),
        )
        allocation = snapshot.allocations[0]
        ready = Barrier(2, timeout=10)

        def save_replan():
            ready.wait()
            try:
                container.weekly_plans.save_replan(
                    replanned,
                    baseline_plan_id=snapshot.id,
                    baseline_fingerprint=fingerprint,
                )
            except (WeeklyPlanSnapshotChanged, WeeklyPlanSuperseded) as exc:
                return ("conflict", type(exc))
            return ("saved", None)

        def record_event():
            ready.wait()
            try:
                container.weekly_plans.record_event(
                    user_id=snapshot.user_id,
                    plan_id=snapshot.id,
                    payload=CompletionEventCreate(
                        event_type=CompletionEventType.PARTIAL,
                        allocation_id=allocation.id,
                        occurred_at=at(18, 30),
                        completed_duration_min=30,
                        remaining_duration_min=30,
                        client_event_id="event-vs-replan",
                    ),
                    now=at(18, 30),
                )
            except (WeeklyPlanSnapshotChanged, WeeklyPlanSuperseded) as exc:
                return ("conflict", type(exc))
            return ("event", None)

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                future.result(timeout=20)
                for future in (
                    executor.submit(save_replan),
                    executor.submit(record_event),
                )
            ]

        assert sorted(item[0] for item in outcomes) in [
            ["conflict", "event"],
            ["conflict", "saved"],
        ]
        latest = container.weekly_plans.latest(
            user_id=snapshot.user_id,
            campus_id=snapshot.campus_id,
            week_start=snapshot.week_start,
        )
        assert latest is not None
        with container.weekly_plans.database.connect() as connection:
            event_count = connection.execute(
                """
                SELECT COUNT(*) FROM completion_events
                WHERE client_event_id = ?
                """,
                ("event-vs-replan",),
            ).fetchone()[0]
        if event_count:
            assert latest.id == snapshot.id
            assert latest.goals[0].remaining_duration_min == 30
            assert any(
                item[1] is WeeklyPlanSnapshotChanged
                for item in outcomes
                if item[0] == "conflict"
            )
        else:
            assert latest.id == replanned.id
            assert latest.version == 2
            assert any(
                item[1] is WeeklyPlanSuperseded
                for item in outcomes
                if item[0] == "conflict"
            )


def test_materialize_and_replan_cas_never_publish_an_old_version(
    tmp_path,
    monkeypatch,
):
    with TestClient(build_test_app(tmp_path)) as client:
        container = client.app.state.container
        request = weekly_request(
            user_id="materialize_replan_cas_user",
            title="并发日落地保护",
            location_id="library",
            window_start=at(18),
            window_end=at(21),
        )
        baseline = container.weekly_allocator.allocate(request, now=at(9))
        container.weekly_plans.save(baseline)
        snapshot = container.weekly_plans.get(baseline.id)
        assert snapshot is not None
        fingerprint = container.weekly_plans.weekly_plan_fingerprint(snapshot)
        replanned = container.weekly_replanner.replan(
            baseline=snapshot,
            capacities=request.capacities,
            trigger=WeeklyTriggerType.MANUAL,
            now=at(9),
        )
        original_publish = container.plans.publish_weekly_day
        ready = Barrier(2, timeout=10)

        def publish_after_replan_is_ready(**kwargs):
            ready.wait()
            return original_publish(**kwargs)

        monkeypatch.setattr(
            container.plans,
            "publish_weekly_day",
            publish_after_replan_is_ready,
        )

        def materialize():
            try:
                result = asyncio.run(
                    container.weekly_grounding.materialize_day(
                        plan_id=snapshot.id,
                        user_id=snapshot.user_id,
                        target_date=WEEK_START,
                        prefer_live=False,
                        now=at(9),
                    )
                )
            except (WeeklyPlanSnapshotChanged, WeeklyPlanSuperseded) as exc:
                return ("conflict", type(exc))
            return ("grounded", result.plan.id)

        def save_replan():
            ready.wait()
            try:
                container.weekly_plans.save_replan(
                    replanned,
                    baseline_plan_id=snapshot.id,
                    baseline_fingerprint=fingerprint,
                )
            except (WeeklyPlanSnapshotChanged, WeeklyPlanSuperseded) as exc:
                return ("conflict", type(exc))
            return ("saved", replanned.id)

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [
                future.result(timeout=20)
                for future in (
                    executor.submit(materialize),
                    executor.submit(save_replan),
                )
            ]

        assert sorted(item[0] for item in outcomes) in [
            ["conflict", "grounded"],
            ["conflict", "saved"],
        ]
        latest = container.weekly_plans.latest(
            user_id=snapshot.user_id,
            campus_id=snapshot.campus_id,
            week_start=snapshot.week_start,
        )
        assert latest is not None
        persisted_baseline = container.weekly_plans.get(snapshot.id)
        assert persisted_baseline is not None
        old_thread_id = container.weekly_grounding._thread_id(
            plan_id=snapshot.id,
            target_date=WEEK_START,
        )
        if latest.id == replanned.id:
            assert container.plans.latest_for_thread(old_thread_id) is None
            assert all(
                item.daily_plan_id is None
                for item in persisted_baseline.allocations
            )
            assert any(
                item[1] is WeeklyPlanSuperseded
                for item in outcomes
                if item[0] == "conflict"
            )
        else:
            assert latest.id == snapshot.id
            assert container.plans.latest_for_thread(old_thread_id) is not None
            assert any(
                item[1] is WeeklyPlanSnapshotChanged
                for item in outcomes
                if item[0] == "conflict"
            )
