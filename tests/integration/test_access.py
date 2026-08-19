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


def test_expensive_endpoints_require_short_lived_login(tmp_path):
    with TestClient(protected_app(tmp_path)) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/demos").status_code == 200
        assert client.post("/api/v1/demos/demo_01_normal/run").status_code == 401

        rejected = client.post(
            "/api/v1/auth/login",
            json={
                "username": "yicheng_test",
                "password": "wrong-password",
            },
        )
        assert rejected.status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={
                "username": "yicheng_test",
                "password": "test-password",
            },
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
            "/api/v1/auth/login",
            json={
                "username": "yicheng_test",
                "password": "test-password",
            },
        )
        token = login.json()["access_token"] + "tampered"
        response = client.post(
            "/api/v1/demos/demo_01_normal/run",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_test_session_is_user_scoped_and_cannot_connect_hduhelp(tmp_path):
    with TestClient(protected_app(tmp_path)) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "yicheng_test", "password": "test-password"},
        )
        bootstrap = login.json()["access_token"]
        session = client.post(
            "/api/v1/auth/session",
            headers={"Authorization": f"Bearer {bootstrap}"},
            json={"mode": "test"},
        )
        assert session.status_code == 200, session.text
        payload = session.json()
        headers = {"Authorization": f"Bearer {payload['access_token']}"}
        user_id = payload["user_id"]

        own = client.get(f"/api/v1/users/{user_id}/memories", headers=headers)
        assert own.status_code == 200, own.text
        other = client.get("/api/v1/users/someone-else/memories", headers=headers)
        assert other.status_code == 403
        hduhelp = client.get(
            f"/api/v1/users/{user_id}/connections/hduhelp",
            headers=headers,
        )
        assert hduhelp.status_code == 403
        assert hduhelp.json()["error"]["code"] == "TEST_HDUHELP_DISABLED"


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
