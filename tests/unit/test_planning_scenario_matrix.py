from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.config import BASE_DIR
from app.schemas.common import TaskFlexibility
from app.services.requirement_parser import RuleBasedRequirementParser


SCENARIOS = json.loads(
    (
        Path(__file__).parents[1]
        / "fixtures"
        / "planning_scenarios.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item["id"])
def test_planning_language_scenario_matrix(scenario):
    parser = RuleBasedRequirementParser(
        "Asia/Shanghai",
        BASE_DIR / "data" / "class_periods.json",
    )
    result = parser.parse(
        query=scenario["query"],
        now=datetime(2026, 7, 24, 7, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    tasks = {task.id: task for task in result.tasks}
    assert set(scenario["expected_ids"]).issubset(tasks)
    for task_id in scenario["fixed_ids"]:
        assert tasks[task_id].flexibility == TaskFlexibility.FIXED
        assert tasks[task_id].fixed_start is not None
        assert tasks[task_id].fixed_end is not None
