"""Follow-up edits go through the model, and may only change what was named.

The model is stubbed here — the point is not what Qwen answers but that
whatever it answers is applied to the day the student already has, instead of
replacing it.  Before this path existed the model was skipped entirely on a
follow-up, so “把自习换到下午，其他照旧” was read by pattern matching alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.main import create_app
from app.schemas.plan_edit import PlanEdit, PlanEditOperation

NOW = "2026-08-21T09:00:00+08:00"


def _app(tmp_path: Path):
    return create_app(
        Settings(
            app_database_path=tmp_path / "app.db",
            app_checkpoint_database_path=tmp_path / "checkpoints.db",
            app_data_dir=BASE_DIR / "data",
            app_demo_dir=BASE_DIR / "fixtures",
            llm_enabled=False,
            live_route_enabled=False,
            live_weather_enabled=False,
        )
    )


def _payload(query: str, *, mode: str = "auto") -> dict:
    return {
        "user_id": "edit_user",
        "thread_id": "edit_thread",
        "query": query,
        "mode": mode,
        "publish_to_agenda": False,
        "client_context": {"now": NOW},
    }


class _StubLLM:
    """Stands in for Qwen: records what it was given, returns a fixed edit."""

    configured = True

    def __init__(self, edit: PlanEdit) -> None:
        self.edit = edit
        self.plan_summary: str | None = None
        self.history: list[dict] | None = None
        self.query: str | None = None

    async def parse_plan_edit(self, *, query, now_iso, plan_summary, history=None):
        self.query = query
        self.plan_summary = plan_summary
        self.history = list(history or [])
        return self.edit


def _titles(body: dict) -> set[str]:
    return {
        item["title"]
        for item in (body.get("plan") or {}).get("items", [])
        if item["item_type"] == "task"
    }


@pytest.fixture
def planned(tmp_path):
    """A day with several arrangements, ready to be edited."""
    application = _app(tmp_path)
    with TestClient(application) as client:
        first = client.post(
            "/api/v1/chat",
            json=_payload(
                "今天上午自习两小时，下午取快递，晚上跑步。",
                mode="offline",
            ),
        )
        assert first.status_code == 200, first.text
        yield application, client, first.json()


def test_the_model_is_given_the_plan_and_the_conversation(planned):
    application, client, first = planned
    assert len(_titles(first)) >= 3

    stub = _StubLLM(
        PlanEdit(
            operations=[
                PlanEditOperation(
                    action="move",
                    task_ref="图书馆自习",
                    target_period="afternoon",
                )
            ]
        )
    )
    application.state.container.llm = stub

    response = client.post(
        "/api/v1/chat",
        json=_payload("把自习换到下午，其他照旧"),
    )
    assert response.status_code == 200, response.text

    assert stub.plan_summary is not None, "the model must be shown the day"
    assert "取快递" in stub.plan_summary
    assert stub.history, "the model must be shown the conversation"
    assert any("自习" in turn["content"] for turn in stub.history)


def test_an_edit_never_drops_the_arrangements_nobody_mentioned(planned):
    application, client, first = planned
    before = _titles(first)

    application.state.container.llm = _StubLLM(
        PlanEdit(
            operations=[
                PlanEditOperation(
                    action="move",
                    task_ref="图书馆自习",
                    target_period="afternoon",
                )
            ]
        )
    )
    response = client.post(
        "/api/v1/chat",
        json=_payload("把自习换到下午，其他照旧"),
    )
    body = response.json()
    after = _titles(body)

    assert before <= after, f"lost {before - after} after a one-task edit"
    study = next(
        item
        for item in body["plan"]["items"]
        if item["item_type"] == "task" and "自习" in item["title"]
    )
    assert 13 <= int(study["start_at"][11:13]) < 18


def test_a_reference_the_model_got_wrong_is_reported_not_silently_applied(
    planned,
):
    application, client, first = planned
    before = _titles(first)

    application.state.container.llm = _StubLLM(
        PlanEdit(
            operations=[
                PlanEditOperation(
                    action="remove", task_ref="并不存在的安排"
                )
            ]
        )
    )
    body = client.post(
        "/api/v1/chat",
        json=_payload("把那个删掉"),
    ).json()

    assert before <= _titles(body), "nothing may vanish over a bad reference"
    assert body.get("clarifications"), "the student must be told we missed it"
