from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from app.api.chat import execute_chat
from app.errors import AppError
from app.schemas.chat import ChatRequest, ChatResponse, ClientContext, DemoFixture
from app.schemas.plan import Plan


router = APIRouter(prefix="/api/v1", tags=["demos"])


def _load_fixtures(directory: Path) -> dict[str, DemoFixture]:
    fixtures = {}
    for path in sorted(directory.glob("demo_*.json")):
        if path.name.endswith(("_initial_plan.json", "_saved_plan.json")):
            continue
        fixture = DemoFixture.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        fixtures[fixture.id] = fixture
    return fixtures


@router.get("/demos")
def list_demos(request: Request) -> list[dict]:
    fixtures = _load_fixtures(
        request.app.state.container.settings.app_demo_dir
    )
    return [
        {
            "id": fixture.id,
            "title": fixture.title,
            "description": fixture.description,
            "query": fixture.query,
        }
        for fixture in fixtures.values()
    ]


@router.post("/demos/{demo_id}/run", response_model=ChatResponse)
async def run_demo(demo_id: str, request: Request) -> ChatResponse:
    container = request.app.state.container
    fixtures = _load_fixtures(container.settings.app_demo_dir)
    fixture = fixtures.get(demo_id)
    if fixture is None:
        raise AppError(
            "DEMO_NOT_FOUND",
            "未找到指定 Demo",
            status_code=404,
        )

    old_plan_id = None
    if fixture.old_plan_fixture:
        path = (
            container.settings.app_demo_dir
            / f"{fixture.old_plan_fixture}.json"
        )
        seed_plan = Plan.model_validate_json(path.read_text(encoding="utf-8"))
        latest = (
            container.plans.latest_for_thread(
                fixture.thread_id or fixture.id
            )
            if fixture.prefer_latest_plan
            else None
        )
        plan = (
            latest
            if latest is not None and _same_baseline(latest, seed_plan)
            else seed_plan
        )
        container.plans.ensure_user_and_thread(
            user_id=plan.user_id,
            thread_id=plan.thread_id,
            now=fixture.now,
        )
        if container.plans.get(plan.id) is None:
            container.plans.save(plan)
        old_plan_id = plan.id

    payload = ChatRequest(
        user_id=fixture.user_id,
        thread_id=fixture.thread_id or fixture.id,
        query=fixture.query,
        old_plan_id=old_plan_id,
        mode="offline",
        client_context=ClientContext(
            current_location_id=fixture.initial_context.get(
                "current_location_id"
            ),
            now=fixture.now,
        ),
    )
    response = await execute_chat(payload, request)
    if response.current_plan_saved and response.plan is not None:
        container.plans.set_agenda_published(
            plan_id=response.plan.id,
            user_id=response.plan.user_id,
            published=True,
        )
    return response


def _same_baseline(plan: Plan, baseline: Plan) -> bool:
    def signature(value: Plan) -> list[tuple]:
        return [
            (
                item.task_id,
                item.start_at,
                item.end_at,
                item.location_id,
            )
            for item in value.items
            if item.item_type == "task"
        ]

    return signature(plan) == signature(baseline)


@router.post("/demos/reset")
def reset_demos(request: Request) -> dict[str, str]:
    request.app.state.container.plans.reset_user("demo_user")
    return {
        "status": "ok",
        "message": "演示状态已复位，可以从案例一重新开始。",
    }
