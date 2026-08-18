from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.nodes.understand import _merge_llm_with_rule_constraints
from app.services.requirement_parser import RuleBasedRequirementParser


TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 24, 13, 0, tzinfo=TZ)


def test_explicit_start_anchor_beats_model_inferred_evening_preference():
    query = (
        "今天下午没课，14点以后想去图书馆学习2小时，取快递，然后去东操场"
        "跑步30分钟，18点前结束。"
    )
    parsed = RuleBasedRequirementParser("Asia/Shanghai").parse(query=query, now=NOW)
    rule_run = next(task for task in parsed.tasks if task.id == "run")
    model_run = rule_run.model_copy(
        update={
            "earliest_start": datetime(2026, 7, 24, 18, 0, tzinfo=TZ),
            "preferred_period": "evening",
        }
    )
    llm_result = parsed.model_copy(
        update={
            "tasks": [
                model_run if task.id == "run" else task for task in parsed.tasks
            ],
            "preferences": parsed.preferences.model_copy(
                update={"buffer_min": 10}
            ),
        }
    )

    merged = _merge_llm_with_rule_constraints(
        query=query, llm_result=llm_result, rule_result=parsed
    )
    merged_run = next(task for task in merged.tasks if task.id == "run")
    assert merged_run.earliest_start == rule_run.earliest_start
    assert merged_run.latest_end == rule_run.latest_end
    assert merged_run.deadline == rule_run.deadline
    assert merged_run.preferred_period is None
    assert merged.preferences.buffer_min == 0


def test_course_merge_keeps_canonical_course_titles():
    query = "今天第1、3节有课，第四节以后去图书馆自习1小时。"
    parsed = RuleBasedRequirementParser(
        "Asia/Shanghai",
        class_periods_path=Path("data/class_periods.json"),
    ).parse(
        query=query,
        now=NOW,
    )
    model_titles = {
        "course_1_1": "第1节课",
        "course_3_3": "第3节课",
    }
    llm_result = parsed.model_copy(
        update={
            "tasks": [
                task.model_copy(update={"title": model_titles[task.id]})
                if task.id in model_titles
                else task
                for task in parsed.tasks
            ]
        }
    )

    merged = _merge_llm_with_rule_constraints(
        query=query,
        llm_result=llm_result,
        rule_result=parsed,
    )

    course_titles = [
        task.title for task in merged.tasks if "course" in task.tags
    ]
    assert course_titles == ["第1节课程", "第3节课程"]
