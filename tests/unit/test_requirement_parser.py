from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import BASE_DIR
from app.services.requirement_parser import RuleBasedRequirementParser


def parse(query: str):
    parser = RuleBasedRequirementParser("Asia/Shanghai")
    return parser.parse(
        query=query,
        now=datetime(
            2026,
            7,
            23,
            8,
            0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ),
    )


def test_learning_duration_uses_actual_keyword():
    result = parse("明天去图书馆学习一个小时。")
    assert result.tasks[0].duration_min == 60


def test_chinese_duration_and_deadline_are_parsed():
    result = parse("明天下午自习两个小时，再取快递，18点前完成。")
    study = next(task for task in result.tasks if task.id == "study")
    parcel = next(task for task in result.tasks if task.id == "parcel")
    assert study.duration_min == 120
    assert study.deadline.hour == 18
    assert parcel.deadline.hour == 18
    assert parcel.deadline.tzinfo is not None


def test_task_scoped_deadline_does_not_leak_to_evening_run():
    result = parse(
        "明天下课后去图书馆学习90分钟，"
        "18点前到菜鸟驿站取快递，晚上去东操场跑步30分钟。"
    )
    study = next(task for task in result.tasks if task.id == "study")
    parcel = next(task for task in result.tasks if task.id == "parcel")
    run = next(task for task in result.tasks if task.id == "run")

    assert study.deadline is None
    assert parcel.deadline.isoformat() == "2026-07-24T18:00:00+08:00"
    assert run.deadline is None
    assert run.earliest_start.isoformat() == "2026-07-24T18:00:00+08:00"
    assert run.latest_end.isoformat() == "2026-07-24T22:00:00+08:00"
    assert result.preferences.buffer_min == 10


def test_empty_task_request_requires_clarification():
    result = parse("请帮我安排一下。")
    assert result.tasks == []
    assert result.clarifications == ["请告诉我需要安排的具体任务。"]


def test_competition_demo_parses_minutes_without_cross_task_capture():
    result = parse(
        "今天14点以后去图书馆学习2小时，取快递，"
        "再去东操场跑步30分钟，18点前结束。"
    )
    run = next(task for task in result.tasks if task.id == "run")
    study = next(task for task in result.tasks if task.id == "study")
    parcel = next(task for task in result.tasks if task.id == "parcel")
    assert run.duration_min == 30
    assert run.depends_on == ["parcel"]
    assert run.deadline.hour == 18
    assert study.earliest_start.hour == 14
    assert parcel.earliest_start.hour == 14


def test_short_after_expression_and_minutes_are_parsed():
    result = parse("今天下午2:30后去图书馆学习1小时。")
    study = next(task for task in result.tasks if task.id == "study")

    assert study.earliest_start.hour == 14
    assert study.earliest_start.minute == 30


def test_adjustment_without_current_plan_requires_baseline():
    result = parse("把学习延长30分钟，其他任务保持不变。")
    assert result.tasks == []
    assert result.intent == "replan"
    assert result.clarifications == [
        "当前没有可调整的计划，请先生成一份计划或提供原计划。"
    ]


def test_campus_rule_question_is_a_query_without_task_clarification():
    result = parse("图书馆晚上几点关门？")

    assert result.intent == "query"
    assert result.tasks == []
    assert result.clarifications == []


def test_verified_class_periods_become_fixed_hard_constraints():
    parser = RuleBasedRequirementParser(
        "Asia/Shanghai",
        Path(BASE_DIR / "data" / "class_periods.json"),
    )
    result = parser.parse(
        query="今天第1至4节有课，下课后去图书馆自习2小时。",
        now=datetime(
            2026,
            7,
            24,
            7,
            0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ),
    )

    course = next(task for task in result.tasks if task.id == "course_1_4")
    study = next(task for task in result.tasks if task.id == "study")
    assert course.fixed_start.isoformat() == "2026-07-24T08:05:00+08:00"
    assert course.fixed_end.isoformat() == "2026-07-24T11:35:00+08:00"
    assert course.duration_min == 210
    assert "hard_constraint" in course.tags
    assert study.earliest_start.isoformat() == "2026-07-24T11:35:00+08:00"


def test_parcel_without_user_deadline_uses_opening_hours_not_fake_18_deadline():
    result = parse("明天下课后去图书馆自习2小时，再去取快递。")
    parcel = next(task for task in result.tasks if task.id == "parcel")

    assert parcel.deadline is None
    assert parcel.latest_end.isoformat() == "2026-07-24T22:30:00+08:00"


def test_transport_mode_defaults_to_walk_and_honors_non_motor_request():
    assert parse("明天去图书馆学习一小时。").preferences.transport_mode == "walk"
    assert (
        parse("明天骑自行车去图书馆学习一小时。")
        .preferences.transport_mode
        == "bicycle"
    )
    assert (
        parse("明天骑电瓶车去图书馆学习一小时。")
        .preferences.transport_mode
        == "electrobike"
    )


def test_avoid_congestion_is_soft_preference_only_when_requested():
    normal = parse("明天去图书馆学习一小时。")
    off_peak = parse("明天去图书馆学习一小时，尽量错峰。")

    assert normal.preferences.avoid_congestion is False
    assert off_peak.preferences.avoid_congestion is True
