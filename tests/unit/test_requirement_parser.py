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


def test_weekday_and_month_day_target_dates_are_resolved():
    assert parse("下周一去图书馆学习一小时。").requested_date.isoformat() == (
        "2026-07-27"
    )
    assert parse("周三去图书馆学习一小时。").requested_date.isoformat() == (
        "2026-07-29"
    )
    past_weekday = parse("本周三去图书馆学习一小时。")
    assert past_weekday.requested_date.isoformat() == "2026-07-22"
    assert "已经过去" in past_weekday.clarifications[0]
    assert parse("7月31日去图书馆学习一小时。").requested_date.isoformat() == (
        "2026-07-31"
    )


def test_period_used_as_after_anchor_is_not_invented_as_course():
    parser = RuleBasedRequirementParser(
        "Asia/Shanghai",
        BASE_DIR / "data" / "class_periods.json",
    )
    result = parser.parse(
        query="今天第1、3节有课，第四节以后去图书馆自习1小时。",
        now=datetime(
            2026,
            7,
            23,
            8,
            0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ),
    )
    courses = [task for task in result.tasks if "course" in task.tags]
    assert len(courses) == 2
    assert [task.fixed_start.hour for task in courses] == [8, 10]


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


def test_timetable_reference_does_not_turn_planning_request_into_query():
    result = parse(
        "根据我的课表帮我安排明天下午去图书馆自习2小时"
        "和跑步30分钟。"
    )

    assert result.intent == "plan"
    assert {task.id for task in result.tasks} == {"study", "run"}
    assert result.clarifications == []


def test_timetable_question_with_natural_wording_is_a_query():
    result = parse("我明天有哪些课？")

    assert result.intent == "query"
    assert result.tasks == []
    assert result.clarifications == []


def test_operational_questions_do_not_create_fake_tasks():
    for query in (
        "校医院周末几点可以看病？",
        "阳光长跑哪个时间段可以计入？",
        "体育馆周末开放吗？",
        "图书馆七楼今天开吗？",
    ):
        result = parse(query)
        assert result.intent == "query", query
        assert result.tasks == [], query
        assert result.clarifications == [], query


def test_question_word_does_not_hide_explicit_planning_request():
    result = parse(
        "明天下午去图书馆七楼自习2小时，可以帮我安排吗？"
    )

    assert result.intent == "plan"
    assert [task.id for task in result.tasks] == ["study"]


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


def test_departure_time_and_origin_are_hard_start_context():
    parser = RuleBasedRequirementParser("Asia/Shanghai")
    result = parser.parse(
        query=(
            "今天下午4点从第七教学楼出发，"
            "去图书馆学习90分钟，之后去东操场跑步30分钟。"
        ),
        now=datetime(
            2026,
            7,
            24,
            13,
            0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ),
    )
    study = next(task for task in result.tasks if task.id == "study")

    assert study.earliest_start.isoformat() == "2026-07-24T16:00:00+08:00"
    assert study.latest_end.isoformat() == "2026-07-24T22:30:00+08:00"
    assert study.preferred_period is None
    assert (
        parser.journey_origin_from_query(
            "今天下午4点从第七教学楼出发，去图书馆学习。"
        )
        == "第七教学楼"
    )


def test_specific_courier_hours_are_hard_constraints():
    result = parse("今天19点去顺丰快递取件，帮我看看能不能安排。")
    parcel = next(task for task in result.tasks if task.id == "parcel")

    assert parcel.title == "取顺丰快递"
    assert parcel.location_raw == "顺丰快递"
    assert parcel.earliest_start.isoformat() == "2026-07-23T19:00:00+08:00"
    assert parcel.latest_end.isoformat() == "2026-07-23T18:00:00+08:00"
    assert parcel.deadline.isoformat() == "2026-07-23T18:00:00+08:00"
    assert "08:00—18:00" in (parcel.notes or "")
    assert "hard_constraint" in parcel.tags


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


def test_service_hour_questions_are_not_misread_as_planning_tasks():
    for query in (
        "顺丰快递点每天几点关闭？",
        "京东快递点每天几点关闭？",
        "周末下午校医院几点可以就诊？",
        "西北田径场阳光长跑什么时候可以计入？",
    ):
        result = parse(query)
        assert result.intent == "query", query
        assert result.tasks == [], query
        assert result.clarifications == [], query


def test_hot_water_hours_question_is_not_misread_as_a_planning_task():
    result = parse("晚上宿舍什么时候有热水？")

    assert result.intent == "query"
    assert result.tasks == []
    assert result.clarifications == []


def test_deadline_after_task_clause_only_constrains_that_task():
    result = parse(
        "明天15:00到16:30固定参加社团会议，之后去取快递，"
        "18点前完成，再去图书馆自习1小时。"
    )

    parcel = next(task for task in result.tasks if task.id == "parcel")
    study = next(task for task in result.tasks if task.id == "study")
    assert parcel.deadline.isoformat() == "2026-07-24T18:00:00+08:00"
    assert study.deadline is None


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


def test_named_subject_periods_are_still_hard_class_constraints():
    parser = RuleBasedRequirementParser(
        "Asia/Shanghai",
        Path(BASE_DIR / "data" / "class_periods.json"),
    )
    result = parser.parse(
        query=(
            "今天第1至2节有高等数学课，第3至4节有大学英语课。"
            "下课后去图书馆自习90分钟。"
        ),
        now=datetime(
            2026,
            7,
            24,
            7,
            0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ),
    )

    courses = [task for task in result.tasks if "course" in task.tags]
    study = next(task for task in result.tasks if task.id == "study")
    assert [(task.id, task.title) for task in courses] == [
        ("course_1_2", "高等数学课"),
        ("course_3_4", "大学英语课"),
    ]
    assert courses[0].fixed_start.isoformat() == "2026-07-24T08:05:00+08:00"
    assert courses[0].fixed_end.isoformat() == "2026-07-24T09:40:00+08:00"
    assert courses[1].fixed_start.isoformat() == "2026-07-24T10:00:00+08:00"
    assert courses[1].fixed_end.isoformat() == "2026-07-24T11:35:00+08:00"
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


def test_complex_hdu_plan_keeps_courier_floor_and_sunshine_run_constraints():
    parser = RuleBasedRequirementParser(
        "Asia/Shanghai",
        BASE_DIR / "data" / "class_periods.json",
    )
    result = parser.parse(
        query=(
            "明天第3到4节有课，下课后去图书馆七楼自习2小时，"
            "18点前取顺丰，晚上去西北田径场完成40分钟阳光长跑，"
            "请帮我安排并提醒注意事项。"
        ),
        now=datetime(
            2026,
            7,
            23,
            8,
            0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        ),
    )

    tasks = {task.id: task for task in result.tasks}
    assert set(tasks) == {"course_3_4", "study", "parcel", "run"}
    assert tasks["course_3_4"].fixed_start.isoformat() == (
        "2026-07-24T10:00:00+08:00"
    )
    assert tasks["course_3_4"].fixed_end.isoformat() == (
        "2026-07-24T11:35:00+08:00"
    )
    assert tasks["study"].duration_min == 120
    assert tasks["study"].location_raw == "图书馆七层"
    assert tasks["parcel"].title == "取顺丰快递"
    assert tasks["parcel"].location_raw == "顺丰快递"
    assert tasks["parcel"].deadline.isoformat() == (
        "2026-07-24T18:00:00+08:00"
    )
    assert tasks["run"].title == "阳光长跑"
    assert tasks["run"].duration_min == 40
    assert tasks["run"].location_raw == "西北田径场"
    assert "sunshine_run" in tasks["run"].tags
    assert tasks["run"].depends_on == ["parcel"]


def test_hdu_health_hot_water_and_indoor_sports_are_plannable_tasks():
    result = parse(
        "明天下午去校医院就诊30分钟，之后打羽毛球1小时，"
        "晚上回宿舍洗澡30分钟。"
    )

    tasks = {task.id: task for task in result.tasks}
    assert set(tasks) == {"clinic", "badminton", "bath"}
    assert tasks["clinic"].location_raw == "校医院"
    assert tasks["clinic"].duration_min == 30
    assert "hard_constraint" in tasks["clinic"].tags
    assert tasks["badminton"].location_raw == "综合馆"
    assert tasks["badminton"].duration_min == 60
    assert "reservation_required" in tasks["badminton"].tags
    assert tasks["bath"].location_raw == "学生公寓"
    assert tasks["bath"].duration_min == 30
    assert "hot_water" in tasks["bath"].tags
    assert tasks["badminton"].depends_on == ["clinic"]
    assert tasks["bath"].depends_on == ["badminton"]


def test_explicit_calendar_date_does_not_hide_following_clock_time():
    parser = RuleBasedRequirementParser("Asia/Shanghai")

    assert str(parser._overall_start("7月24日21点后去顺丰取快递")) == "21:00:00"
    assert str(parser._overall_start("7月24日19点去西北田径场长跑")) == "19:00:00"
    assert str(parser._overall_start("7月26日晚上23点30分回宿舍")) == "23:30:00"
    assert str(parser._overall_start("7月25日15点45分去综合馆打羽毛球")) == "15:45:00"
