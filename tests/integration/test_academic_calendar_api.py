from fastapi.testclient import TestClient

from tests.integration.test_api_demos import build_test_app


def test_calendar_context_range_exposes_holidays_and_makeup_days(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        response = client.get(
            "/api/v1/users/calendar_api_user/calendar-context",
            params={"start_date": "2026-10-01", "end_date": "2026-10-10"},
        )

    assert response.status_code == 200, response.text
    by_date = {item["date"]: item for item in response.json()["items"]}
    assert by_date["2026-10-01"]["day_type"] == "holiday"
    assert by_date["2026-10-01"]["course_action"] == "no_class"
    assert by_date["2026-10-01"]["label"] == "国庆节"
    assert by_date["2026-10-10"]["day_type"] == "adjusted_workday"
    assert by_date["2026-10-10"]["course_action"] == "awaiting_school_notice"


def test_calendar_context_range_rejects_invalid_ranges(tmp_path):
    with TestClient(build_test_app(tmp_path)) as client:
        reversed_response = client.get(
            "/api/v1/users/calendar_api_user/calendar-context",
            params={"start_date": "2026-10-10", "end_date": "2026-10-01"},
        )
        oversized_response = client.get(
            "/api/v1/users/calendar_api_user/calendar-context",
            params={"start_date": "2026-01-01", "end_date": "2026-05-01"},
        )

    assert reversed_response.status_code == 422
    assert oversized_response.status_code == 422
