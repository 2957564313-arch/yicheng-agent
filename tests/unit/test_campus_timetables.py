from __future__ import annotations

import json
from datetime import time

from app.config import BASE_DIR


def test_class_periods_are_complete_ordered_and_non_overlapping():
    payload = json.loads(
        (BASE_DIR / "data" / "class_periods.json").read_text(
            encoding="utf-8"
        )
    )
    periods = payload["class_periods"]

    assert [item["period"] for item in periods] == list(range(1, 14))
    for previous, current in zip(periods, periods[1:]):
        assert time.fromisoformat(previous["end"]) <= time.fromisoformat(
            current["start"]
        )


def test_campus_timetables_keep_unknown_summer_year_explicit():
    payload = json.loads(
        (BASE_DIR / "data" / "campus_timetables.json").read_text(
            encoding="utf-8"
        )
    )

    assert payload["summer_sports"]["effective_year"] is None
    assert payload["summer_sports"]["requires_year_verification"] is True
    assert payload["couriers"][2] == {
        "name": "菜鸟驿站",
        "windows": [["08:30", "22:30"]],
    }


def test_congestion_windows_define_required_time_buffer_without_forced_avoidance():
    payload = json.loads(
        (BASE_DIR / "data" / "class_periods.json").read_text(
            encoding="utf-8"
        )
    )

    assert len(payload["congestion_windows"]) == 6
    assert all(
        item["duration_multiplier"] >= 1
        and item["minimum_extra_min"] >= 0
        for item in payload["congestion_windows"]
    )
    assert (
        payload["congestion_policy"]["constraint_level"]
        == "soft_with_required_time_buffer"
    )
