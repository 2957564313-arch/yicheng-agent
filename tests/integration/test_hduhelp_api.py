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
        current_term = [
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
        historical_term = [
            {
                "schoolYear": "2025-2026",
                "semester": 2,
                "week": week,
                "day": 2,
                "courseName": "工程伦理",
                "location": "第6教研楼北214",
                "courseId": "course-2",
                "weeks": [1, 2],
                "sections": [3, 4],
            }
            for week in (1, 2)
        ]
        return [*current_term, *historical_term]

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
        if (school_year, semester) == ("2025-2026", 2):
            return []
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
            },
            {
                "school_year": "2025-2026",
                "semester": 2,
                "raw_entry_count": 2,
            },
        ]
        assert "token" not in connected.text.lower()

        row = app.state.container.external_connections.get_row(
            "visitor-1",
            "hduhelp",
        )
        assert row is not None
        assert TOKEN not in row["credential_ciphertext"]

        synced = sync(client).json()
        assert synced["imported_count"] == 2
        assert synced["entries"][0]["weeks"] == [1, 2]
        assert synced["timetable"]["term_start"] == "2026-09-07"
        assert synced["timetable"]["term_end"] == "2027-01-10"
        expected_counts = {
            "course": 2,
            "library_reservation": 1,
            "second_classroom": 1,
            "exam": 1,
        }
        for key, count in expected_counts.items():
            assert synced["synced_counts"][key] == count
        assert synced["synced_counts"]["timetable_terms"] == 2
        assert len(synced["terms"]) == 2

        timetables = client.get(
            "/api/v1/users/visitor-1/connections/hduhelp/timetables"
        )
        assert timetables.status_code == 200, timetables.text
        terms = timetables.json()["terms"]
        assert [
            (term["school_year"], term["semester"], term["current"])
            for term in terms
        ] == [
            ("2026-2027", 1, True),
            ("2025-2026", 2, False),
        ]
        assert terms[0]["entries"][0]["course_name"] == "高等数学A2"
        assert terms[1]["entries"][0]["course_name"] == "工程伦理"

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
        external = [item for item in agenda_items if item["source"] == "external"]
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

        disconnected = client.delete("/api/v1/users/visitor-1/connections/hduhelp")
        assert disconnected.status_code == 204
        status = client.get("/api/v1/users/visitor-1/connections/hduhelp")
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
        assert "图书馆上游暂时不可用" in "".join(response.json()["warnings"])
        assert (
            app.state.container.external_agenda.counts("visitor-1")[
                "library_reservation"
            ]
            == 1
        )
