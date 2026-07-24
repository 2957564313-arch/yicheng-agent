from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.repositories.database import Database


@pytest.fixture
def tz() -> ZoneInfo:
    return ZoneInfo("Asia/Shanghai")


@pytest.fixture
def fixed_now(tz: ZoneInfo) -> datetime:
    return datetime(2026, 7, 23, 20, 0, tzinfo=tz)


@pytest.fixture
def temp_database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    database.initialize()
    return database

