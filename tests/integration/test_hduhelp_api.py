from pathlib import Path

from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.main import create_app


class FakeHduHelp:
    def identity(self, token: str):
        assert token == "test-hduhelp-personal-token"
        return {"id": "hdu-user-1", "nickName": "测试用户"}

    def schedule(self, token: str):
        assert token == "test-hduhelp-personal-token"
        return [
            {
                "schoolYear": "2026-2027",
                "semester": 1,
                "week": week,
                "day": 1,
                "courseName": "高等数学A2",
                "location": "第6教研楼北204",
                "courseId": "course-1",
                "weeks": [1, 2],
                "sections": [1, 2],
            }
            for week in (1, 2)
        ]


def build_hduhelp_app(tmp_path: Path):
    return create_app(
        Settings(
            app_database_path=tmp_path / "app.db",
            app_checkpoint_database_path=tmp_path / "checkpoints.db",
            app_data_dir=BASE_DIR / "data",
            app_demo_dir=BASE_DIR / "fixtures",
            app_credential_secret="test-credential-secret-long-enough",
            llm_enabled=False,
            live_route_enabled=False,
            live_weather_enabled=False,
        )
    )


def test_connect_status_sync_and_disconnect(tmp_path):
    app = build_hduhelp_app(tmp_path)
    with TestClient(app) as client:
        app.state.container.hduhelp = FakeHduHelp()
        connected = client.post(
            "/api/v1/users/visitor-1/connections/hduhelp",
            json={"token": "test-hduhelp-personal-token"},
        )
        assert connected.status_code == 200, connected.text
        payload = connected.json()
        assert payload["connected"] is True
        assert payload["display_name"] == "测试用户"
        assert payload["available_terms"] == [
            {
                "school_year": "2026-2027",
                "semester": 1,
                "raw_entry_count": 2,
            }
        ]
        assert "token" not in connected.text.lower()

        row = app.state.container.external_connections.get_row(
            "visitor-1",
            "hduhelp",
        )
        assert row is not None
        assert "test-hduhelp-personal-token" not in row[
            "credential_ciphertext"
        ]

        synced = client.post(
            "/api/v1/users/visitor-1/connections/hduhelp/sync-timetable",
            json={
                "school_year": "2026-2027",
                "semester": 1,
                "term_start": "2026-09-07",
            },
        )
        assert synced.status_code == 200, synced.text
        assert synced.json()["imported_count"] == 1
        assert synced.json()["entries"][0]["weeks"] == [1, 2]
        assert synced.json()["timetable"]["term_end"] == "2026-09-20"

        disconnected = client.delete(
            "/api/v1/users/visitor-1/connections/hduhelp"
        )
        assert disconnected.status_code == 204
        status = client.get(
            "/api/v1/users/visitor-1/connections/hduhelp"
        )
        assert status.json()["connected"] is False
