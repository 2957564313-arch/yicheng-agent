from pathlib import Path

from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.main import create_app


def protected_app(tmp_path: Path):
    return create_app(
        Settings(
            app_database_path=tmp_path / "app.db",
            app_checkpoint_database_path=tmp_path / "checkpoints.db",
            app_data_dir=BASE_DIR / "data",
            app_demo_dir=BASE_DIR / "fixtures",
            app_access_enabled=True,
            app_test_username="yicheng_test",
            app_test_password="test-password",
            app_auth_secret="test-secret-with-at-least-24-characters",
            llm_enabled=False,
            live_route_enabled=False,
            live_weather_enabled=False,
        )
    )


def product_gate(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "yicheng_test", "password": "test-password"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["session_mode"] == "bootstrap"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_expensive_endpoints_require_short_lived_login(tmp_path):
    with TestClient(protected_app(tmp_path)) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/demos").status_code == 200
        assert client.post("/api/v1/demos/demo_01_normal/run").status_code == 401

        assert client.post("/api/v1/auth/test-session").status_code == 401
        rejected = client.post(
            "/api/v1/auth/login",
            json={"username": "yicheng_test", "password": "wrong-password"},
        )
        assert rejected.status_code == 401

        gate_headers = product_gate(client)
        bootstrap_run = client.post(
            "/api/v1/demos/demo_01_normal/run",
            headers=gate_headers,
        )
        assert bootstrap_run.status_code == 403

        login = client.post(
            "/api/v1/auth/test-session",
            headers=gate_headers,
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        status = client.get("/api/v1/auth/status", headers=headers)
        assert status.json()["authenticated"] is True
        run = client.post(
            "/api/v1/demos/demo_01_normal/run",
            headers=headers,
        )
        assert run.status_code == 200, run.text


def test_tampered_access_token_is_rejected(tmp_path):
    with TestClient(protected_app(tmp_path)) as client:
        login = client.post(
            "/api/v1/auth/test-session",
            headers=product_gate(client),
        )
        token = login.json()["access_token"] + "tampered"
        response = client.post(
            "/api/v1/demos/demo_01_normal/run",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_test_session_is_shared_across_devices_and_can_connect_hduhelp(tmp_path):
    with TestClient(protected_app(tmp_path)) as client:
        login = client.post(
            "/api/v1/auth/test-session",
            headers=product_gate(client),
        )
        assert login.status_code == 200, login.text
        payload = login.json()
        headers = {"Authorization": f"Bearer {payload['access_token']}"}
        user_id = payload["user_id"]

        own = client.get(f"/api/v1/users/{user_id}/memories", headers=headers)
        assert own.status_code == 200, own.text
        saved = client.post(
            f"/api/v1/users/{user_id}/memories",
            headers=headers,
            json={
                "category": "preference",
                "key": "test_shared_memory",
                "label": "共享测试记忆",
                "value": "所有测试设备可见",
            },
        )
        assert saved.status_code == 201, saved.text
        other = client.get("/api/v1/users/someone-else/memories", headers=headers)
        assert other.status_code == 403
        hduhelp = client.get(
            f"/api/v1/users/{user_id}/connections/hduhelp",
            headers=headers,
        )
        assert hduhelp.status_code == 200, hduhelp.text

        second = client.post(
            "/api/v1/auth/test-session",
            headers=product_gate(client),
        ).json()
        assert second["user_id"] == user_id == "test_shared"
        second_headers = {"Authorization": f"Bearer {second['access_token']}"}
        synced = client.get(
            f"/api/v1/users/{user_id}/memories",
            headers=second_headers,
        )
        assert synced.json()["items"][0]["value"] == "所有测试设备可见"


def test_normal_account_is_stable_across_devices_and_user_scoped(tmp_path):
    with TestClient(protected_app(tmp_path)) as client:
        first_gate_headers = product_gate(client)
        created = client.post(
            "/api/v1/auth/register",
            headers=first_gate_headers,
            json={
                "username": "student_2026",
                "password": "safe-password-2026",
                "display_name": "学生用户",
            },
        )
        assert created.status_code == 200, created.text
        first = created.json()
        assert first["session_mode"] == "normal"
        assert first["user_id"].startswith("usr_")

        second_login = client.post(
            "/api/v1/auth/account/login",
            headers=product_gate(client),
            json={
                "username": "STUDENT_2026",
                "password": "safe-password-2026",
            },
        )
        assert second_login.status_code == 200, second_login.text
        second = second_login.json()
        assert second["user_id"] == first["user_id"]

        first_headers = {"Authorization": f"Bearer {first['access_token']}"}
        created_memory = client.post(
            f"/api/v1/users/{first['user_id']}/memories",
            headers=first_headers,
            json={
                "category": "preference",
                "key": "study_place",
                "label": "自习地点",
                "value": "图书馆12层",
            },
        )
        assert created_memory.status_code == 201, created_memory.text

        headers = {"Authorization": f"Bearer {second['access_token']}"}
        own = client.get(
            f"/api/v1/users/{second['user_id']}/memories",
            headers=headers,
        )
        assert own.status_code == 200, own.text
        assert own.json()["items"][0]["value"] == "图书馆12层"
        other = client.get(
            "/api/v1/users/usr_someone_else/memories",
            headers=headers,
        )
        assert other.status_code == 403


def test_account_registration_rejects_duplicates_and_wrong_password(tmp_path):
    with TestClient(protected_app(tmp_path)) as client:
        gate_headers = product_gate(client)
        payload = {
            "username": "student@example.com",
            "password": "safe-password-2026",
        }
        assert client.post(
            "/api/v1/auth/register", headers=gate_headers, json=payload
        ).status_code == 200
        duplicate = client.post(
            "/api/v1/auth/register", headers=product_gate(client), json=payload
        )
        assert duplicate.status_code == 409
        wrong = client.post(
            "/api/v1/auth/account/login",
            headers=product_gate(client),
            json={**payload, "password": "wrong-password"},
        )
        assert wrong.status_code == 401


def test_public_defaults_disable_api_docs_and_add_security_headers(tmp_path):
    with TestClient(protected_app(tmp_path)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "same-origin"
        assert response.headers["permissions-policy"] == (
            "camera=(), geolocation=(), microphone=(), payment=()"
        )
        assert "frame-ancestors 'none'" in response.headers[
            "content-security-policy"
        ]
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404

        script = client.get("/app.js?v=cache-bust")
        assert script.status_code == 200
        assert script.headers["cache-control"] == "no-cache"
