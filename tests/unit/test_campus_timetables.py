from __future__ import annotations

import json
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.config import BASE_DIR
from app.providers.campus_rules import CampusRulesRepository


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


def test_track_is_open_all_day_but_sunshine_credit_has_separate_window():
    rules = CampusRulesRepository(
        BASE_DIR / "data" / "opening_hours.json",
        BASE_DIR / "data" / "campus_rules.json",
        BASE_DIR / "data" / "class_periods.json",
        "Asia/Shanghai",
    )
    target_date = date(2026, 7, 24)
    windows = rules.opening_windows("track", target_date)
    timezone = ZoneInfo("Asia/Shanghai")

    assert windows == [
        (
            datetime(2026, 7, 24, 0, 0, tzinfo=timezone),
            datetime(2026, 7, 25, 0, 0, tzinfo=timezone),
        )
    ]
    track_fact = next(
        fact
        for fact in rules.facts_for_locations({"track"})
        if fact.id == "east_track_sun_run"
    )
    assert "场地全天开放" in track_fact.content
    assert "7:00-21:00" in track_fact.content
    assert "不计入阳光长跑" in track_fact.content
