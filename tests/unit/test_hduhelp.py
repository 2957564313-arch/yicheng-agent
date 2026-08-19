from app.providers.hduhelp import available_terms, schedule_to_sessions
from app.services.credentials import CredentialCipher


def _row(*, week: int, day: int = 1, sections: list[int] | None = None):
    return {
        "schoolYear": "2026-2027",
        "semester": 1,
        "week": week,
        "day": day,
        "period": 1,
        "courseName": "高等数学A2",
        "location": "第6教研楼北204",
        "courseId": "course-1",
        "weeks": [1, 2, 3],
        "sections": sections or [1, 2],
    }


def test_schedule_rows_are_collapsed_into_course_sessions():
    rows = [_row(week=1), _row(week=2), _row(week=3)]
    sessions = schedule_to_sessions(
        rows,
        school_year="2026-2027",
        semester=1,
    )
    assert len(sessions) == 1
    assert sessions[0].course_name == "高等数学A2"
    assert sessions[0].weekday == 1
    assert sessions[0].start_period == 1
    assert sessions[0].end_period == 2
    assert sessions[0].location == "第6教研楼北204"
    assert sessions[0].weeks == [1, 2, 3]


def test_available_terms_are_newest_first():
    rows = [
        _row(week=1),
        {**_row(week=1), "schoolYear": "2025-2026", "semester": 2},
    ]
    terms = available_terms(rows)
    assert [(item.school_year, item.semester) for item in terms] == [
        ("2026-2027", 1),
        ("2025-2026", 2),
    ]


def test_credential_cipher_never_stores_plaintext():
    cipher = CredentialCipher("a-test-secret-that-is-long-enough")
    token = "private-personal-access-token"
    encrypted = cipher.encrypt(token)
    assert token not in encrypted
    assert cipher.decrypt(encrypted) == token
