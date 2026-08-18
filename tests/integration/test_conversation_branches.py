from pathlib import Path

from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.main import create_app


def branch_app(tmp_path: Path):
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


def chat_payload(query: str) -> dict:
    return {
        "user_id": "branch_user",
        "thread_id": "branch_source",
        "query": query,
        "mode": "offline",
        "publish_to_agenda": False,
        "client_context": {"now": "2026-08-18T09:00:00+08:00"},
    }


def test_editing_an_old_question_creates_a_branch_and_preserves_original(tmp_path):
    with TestClient(branch_app(tmp_path)) as client:
        first = client.post(
            "/api/v1/chat",
            json=chat_payload("今天14点到15点在图书馆复习高数。"),
        )
        assert first.status_code == 200, first.text
        first_user_message_id = first.json()["user_message_id"]
        assert first_user_message_id

        second = client.post(
            "/api/v1/chat",
            json=chat_payload("再加一个16点到16点30分取快递。"),
        )
        assert second.status_code == 200, second.text

        original_before = client.get(
            "/api/v1/users/branch_user/threads/branch_source"
        ).json()
        assert len(original_before["messages"]) == 4

        fork = client.post(
            "/api/v1/users/branch_user/threads/branch_source/fork",
            json={
                "from_message_id": first_user_message_id,
                "query": "今天15点到16点在图书馆复习线性代数。",
                "mode": "offline",
                "publish_to_agenda": False,
                "client_context": {"now": "2026-08-18T09:00:00+08:00"},
            },
        )
        assert fork.status_code == 200, fork.text
        branch_id = fork.json()["branch"]["id"]
        assert branch_id != "branch_source"
        assert fork.json()["branch"]["parent_thread_id"] == "branch_source"
        assert fork.json()["branch"]["forked_from_message_id"] == first_user_message_id

        original_after = client.get(
            "/api/v1/users/branch_user/threads/branch_source"
        ).json()
        assert original_after == original_before

        branch = client.get(
            f"/api/v1/users/branch_user/threads/{branch_id}"
        ).json()
        contents = [item["content"] for item in branch["messages"]]
        assert "今天15点到16点在图书馆复习线性代数。" in contents
        assert "再加一个16点到16点30分取快递。" not in contents
        assert len(branch["messages"]) == 2

        threads = client.get("/api/v1/users/branch_user/threads").json()
        assert {item["id"] for item in threads} == {"branch_source", branch_id}


def test_branch_cannot_edit_an_assistant_message(tmp_path):
    with TestClient(branch_app(tmp_path)) as client:
        response = client.post(
            "/api/v1/chat",
            json=chat_payload("今天下午学习一小时。"),
        )
        assistant_id = response.json()["assistant_message_id"]
        rejected = client.post(
            "/api/v1/users/branch_user/threads/branch_source/fork",
            json={
                "from_message_id": assistant_id,
                "query": "修改一下",
                "mode": "offline",
            },
        )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "MESSAGE_NOT_EDITABLE"


def test_branch_uses_plan_state_before_edited_message(tmp_path):
    with TestClient(branch_app(tmp_path)) as client:
        first = client.post(
            "/api/v1/chat",
            json=chat_payload("今天14点到15点在图书馆复习高数。"),
        ).json()
        second = client.post(
            "/api/v1/chat",
            json=chat_payload("再加一个16点到16点30分取快递。"),
        ).json()
        third = client.post(
            "/api/v1/chat",
            json=chat_payload("再加一个18点到18点30分跑步。"),
        ).json()

        fork = client.post(
            "/api/v1/users/branch_user/threads/branch_source/fork",
            json={
                "from_message_id": second["user_message_id"],
                "query": "改成16点到17点去健身。",
                "mode": "offline",
                "publish_to_agenda": False,
                "client_context": {"now": "2026-08-18T09:00:00+08:00"},
            },
        )
        assert fork.status_code == 200, fork.text
        payload = fork.json()
        assert payload["response"]["previous_plan"]["id"] == first["plan"]["id"]
        assert payload["response"]["previous_plan"]["id"] not in {
            second["plan"]["id"],
            third["plan"]["id"],
        }
        branch = client.get(
            f"/api/v1/users/branch_user/threads/{payload['branch']['id']}"
        ).json()
        branch_contents = [item["content"] for item in branch["messages"]]
        assert "今天14点到15点在图书馆复习高数。" in branch_contents
        assert "改成16点到17点去健身。" in branch_contents
        assert "再加一个16点到16点30分取快递。" not in branch_contents
        assert "再加一个18点到18点30分跑步。" not in branch_contents
