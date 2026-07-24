from datetime import date, datetime

import pytest
from pydantic import ValidationError

from app.schemas.common import TaskFlexibility
from app.schemas.task import Task


def test_fixed_task_requires_interval(tz):
    with pytest.raises(ValidationError):
        Task(
            id="task_1",
            title="实验课",
            date=date(2026, 7, 24),
            duration_min=120,
            flexibility=TaskFlexibility.FIXED,
        )


def test_fixed_task_duration_must_match(tz):
    with pytest.raises(ValidationError):
        Task(
            id="task_1",
            title="实验课",
            date=date(2026, 7, 24),
            duration_min=60,
            flexibility=TaskFlexibility.FIXED,
            fixed_start=datetime(2026, 7, 24, 14, 0, tzinfo=tz),
            fixed_end=datetime(2026, 7, 24, 16, 0, tzinfo=tz),
        )


def test_datetimes_must_be_timezone_aware():
    with pytest.raises(ValidationError):
        Task(
            id="task_1",
            title="自习",
            date=date(2026, 7, 24),
            duration_min=120,
            earliest_start=datetime(2026, 7, 24, 14, 0),
        )

