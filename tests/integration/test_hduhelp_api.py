from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.errors import AppError
from app.main import create_app

TOKEN = "test-hduhelp-personal-token"
TIMEZONE = ZoneInfo("Asia/Shanghai")


def timestamp(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=TIMEZONE).timestamp())


class FakeHduHelp:
    def __init__(self) -> None:
        self.cancelled = False
        self.library_unavailable = False

    def identity(self, token: str):
        assert token == TOKEN
        return {"id": "hdu-user-1", "nickName": "测试用户"}

    def schedule(self, token: str):
        assert token == TOKEN
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

    def school_time(self, token: str):
        assert token == TOKEN
        return {
            "schoolYear": "2026-2027",
            "semester": "1",
            "weekNow": 1,
            "weekDayNow": 1,
            "timeStamp": timestamp("2026-09-07T09:00:00"),
        }

    def library_reservations(self, token: str):
        assert token == TOKEN
        if self.library_unavailable:
            raise AppError(
                "HDUHELP_PROVIDER_ERROR",
                "图书馆上游暂时不可用",
                status_code=502,
                retryable=True,
            )
        if self.cancelled:
            return []
        return [
            {
                "staffId": "student-1",
                "startTime": timestamp("2026-09-07T13:00:00"),
                "endTime": timestamp("2026-09-07T15:00:00"),
                "room": "图书馆12层",
                "seatNo": "1208",
                "finalState": "confirmed",
            }
        ]

    def my_activities(self, token: str):
        assert token == TOKEN
        if self.cancelled:
            return []
        return [
            {
                "activityID": "activity-1",
                "activityName": "二课讲座",
                "activityStartTime": "2026-09-08T18:30:00+08:00",
                "activityEndTime": "2026-09-08T20:00:00+08:00",
                "position": "科技馆报告厅",
                "activityStatusName": "已报名",
            }
        ]

    def exams(self, token: str, school_year: str, semester: int):
        assert token == TOKEN
        assert (school_year, semester) == ("2026-2027", 1)
        if self.cancelled:
            return []
        return [
            {
                "selectCode": "exam-1",
                "course": "高等数学A2",
                "examTime": "2026-12-28 09:00-11:00",
                "classroom": "第6教研楼北204",
            }
        ]

    def create_wechat_qr(self, *, client_id: str, redirect_uri: str):
        assert client_id == "official-client-id"
        assert redirect_uri == "https://yichengapp.top/"
        return {
            "authorizeURL": "https://api.hduhelp.com/mock-authorize",
            "pollToken": "private-poll-token-123456",
            "expiresAt": 1_800_000_000,
        }

    def poll_wechat_qr(self, poll_token: str):
        assert poll_token == "private-poll-token-123456"
        return {"status": "authorized", "code": "one-time-code"}

    def exchange_login_code(self, code: str):
        assert code == "one-time-code"
        return {
            "accessToken": TOKEN,
            "refreshToken": "refresh-token",
            "accessExpireAt": 1_900_000_000,
        }


def build_hduhelp_app(tmp_path: Path, *, access_enabled: bool = False):
    return create_app(
        Settings(
            app_database_path=tmp_path / "app.db",
            app_checkpoint_database_path=tmp_path / "checkpoints.db",
            app_data_dir=BASE_DIR / "data",
            app_demo_dir=BASE_DIR / "fixtures",
            app_credential_secret="test-credential-secret-long-enough",
            app_access_enabled=access_enabled,
            app_test_username="yicheng_test",
            app_test_password="test-password",
            app_auth_secret="test-secret-with-at-least-24-characters",
            hduhelp_qr_client_id=(
                "official-client-id" if access_enabled else ""
            ),
            hduhelp_qr_redirect_uri="https://yichengapp.top/",
            llm_enabled=False,
            live_route_enabled=False,
            live_weather_enabled=False,
        )
    )


def connect(client: TestClient):
    response = client.post(
        "/api/v1/users/visitor-1/connections/hduhelp",
        json={"token": TOKEN},
    )
    assert response.status_code == 200, response.text
    return response


def sync(client: TestClient):
    response = client.post(
        "/api/v1/users/visitor-1/connections/hduhelp/sync",
        json={"school_year": "2026-2027", "semester": 1},
    )
    assert response.status_code == 200, response.text
    return response


def test_connect_sync_authoritative_cancellation_and_disconnect(tmp_path):
    app = build_hduhelp_app(tmp_path)
    fake = FakeHduHelp()
    with TestClient(app) as client:
        app.state.container.hduhelp = fake
        connected = connect(client)
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
        assert TOKEN not in row["credential_ciphertext"]

        synced = sync(client).json()
        assert synced["imported_count"] == 1
        assert synced["entries"][0]["weeks"] == [1, 2]
        assert synced["timetable"]["term_start"] == "2026-09-07"
        assert synced["timetable"]["term_end"] == "2027-01-10"
        assert synced["synced_counts"] == {
            "course": 1,
            "library_reservation": 1,
            "second_classroom": 1,
            "exam": 1,
        }

        agenda_items = []
        for start_date, end_date in (
            ("2026-09-07", "2026-09-08"),
            ("2026-12-28", "2026-12-28"),
        ):
            agenda = client.get(
                "/api/v1/users/visitor-1/agenda",
                params={"start_date": start_date, "end_date": end_date},
            )
            assert agenda.status_code == 200, agenda.text
            agenda_items.extend(agenda.json()["items"])
        external = [
            item for item in agenda_items if item["source"] == "external"
        ]
        assert {item["title"] for item in external} == {
            "图书馆自习预约",
            "二课讲座",
            "高等数学A2考试",
        }
        assert all(item["locked"] for item in external)

        fake.cancelled = True
        resynced = sync(client).json()
        assert resynced["synced_counts"]["library_reservation"] == 0
        assert resynced["synced_counts"]["second_classroom"] == 0
        assert resynced["synced_counts"]["exam"] == 0
        assert app.state.container.external_agenda.counts("visitor-1") == {}

        qr = client.post(
            "/api/v1/users/visitor-1/connections/hduhelp/wechat/start"
        )
        assert qr.status_code == 200
        assert qr.json()["ready"] is False
        assert "Client ID" in qr.json()["message"]

        disconnected = client.delete(
            "/api/v1/users/visitor-1/connections/hduhelp"
        )
        assert disconnected.status_code == 204
        status = client.get(
            "/api/v1/users/visitor-1/connections/hduhelp"
        )
        assert status.json()["connected"] is False


def test_provider_failure_preserves_last_successful_source(tmp_path):
    app = build_hduhelp_app(tmp_path)
    fake = FakeHduHelp()
    with TestClient(app) as client:
        app.state.container.hduhelp = fake
        connect(client)
        sync(client)
        fake.library_unavailable = True
        response = sync(client)
        assert response.json()["synced_counts"]["library_reservation"] == 1
        assert "图书馆上游暂时不可用" in "".join(
            response.json()["warnings"]
        )
        assert app.state.container.external_agenda.counts("visitor-1")[
            "library_reservation"
        ] == 1


def test_wechat_qr_creates_a_user_scoped_normal_session(tmp_path):
    app = build_hduhelp_app(tmp_path, access_enabled=True)
    fake = FakeHduHelp()
    with TestClient(app) as client:
        app.state.container.hduhelp = fake
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "yicheng_test", "password": "test-password"},
        )
        bootstrap_headers = {
            "Authorization": f"Bearer {login.json()['access_token']}"
        }
        started = client.post(
            "/api/v1/users/onboarding-client/connections/hduhelp/wechat/start",
            headers=bootstrap_headers,
        )
        assert started.status_code == 200, started.text
        assert started.json()["ready"] is True
        assert started.json()["poll_token"] == "private-poll-token-123456"

        completed = client.post(
            "/api/v1/users/onboarding-client/connections/hduhelp/wechat/poll",
            headers=bootstrap_headers,
            json={"poll_token": "private-poll-token-123456"},
        )
        assert completed.status_code == 200, completed.text
        payload = completed.json()
        assert payload["status"] == "authorized"
        assert payload["user_id"].startswith("hdu_")
        normal_headers = {
            "Authorization": f"Bearer {payload['access_token']}"
        }
        own = client.get(
            f"/api/v1/users/{payload['user_id']}/connections/hduhelp",
            headers=normal_headers,
        )
        assert own.status_code == 200, own.text
        assert own.json()["connected"] is True
        other = client.get(
            "/api/v1/users/someone-else/connections/hduhelp",
            headers=normal_headers,
        )
        assert other.status_code == 403
