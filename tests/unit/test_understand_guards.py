from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.nodes.understand import (
    _apply_timetable_relative_constraints,
    _can_apply_rule_guard,
    _drop_journey_origin_marker_tasks,
    _merge_llm_with_rule_constraints,
)
from app.schemas.common import Intent, TaskFlexibility
from app.schemas.task import Task
from app.schemas.understand import UnderstandResult
from app.services.requirement_parser import RuleBasedRequirementParser

NOW = datetime(
    2026,
    7,
    24,
    13,
    0,
    tzinfo=ZoneInfo("Asia/Shanghai"),
)


def _parse(query: str) -> UnderstandResult:
    return RuleBasedRequirementParser("Asia/Shanghai").parse(
        query=query,
        now=NOW,
    )


def test_known_venue_boundary_does_not_accept_invented_llm_clarification():
    query = "今天22点去图书馆自习30分钟，可以吗？"
    rule_result = _parse(query)
    llm_result = UnderstandResult(
        intent=Intent.PLAN,
        requested_date=rule_result.requested_date,
        tasks=[],
        clarifications=[
            "图书馆在22:00后的开放情况未知，无法确认是否可以自习。"
        ],
        confidence=0.8,
    )

    assert _can_apply_rule_guard(
        query=query,
        llm_result=llm_result,
        rule_result=rule_result,
    )


def test_journey_origin_is_not_merged_into_first_task_by_llm():
    query = (
        "明天下午4点从第七教学楼出发，去图书馆学习90分钟，"
        "之后到东操场跑步30分钟，校内骑电瓶车。"
    )
    rule_result = _parse(query)
    llm_tasks = [
        rule_result.tasks[0].model_copy(
            update={
                "title": "从第七教学楼出发前往图书馆学习",
                "location_raw": "第七教学楼",
            }
        ),
        rule_result.tasks[1].model_copy(
            update={
                "title": "从图书馆前往东操场跑步",
                "location_raw": "东操场",
            }
        ),
    ]
    llm_result = rule_result.model_copy(
        update={"tasks": llm_tasks, "confidence": 0.9}
    )

    assert _can_apply_rule_guard(
        query=query,
        llm_result=llm_result,
        rule_result=rule_result,
    )


def test_open_ended_request_still_allows_a_real_clarification():
    query = "今天帮我安排学习。"
    rule_result = _parse(query)
    llm_result = UnderstandResult(
        intent=Intent.PLAN,
        requested_date=rule_result.requested_date,
        tasks=[],
        clarifications=["你希望几点开始？"],
        confidence=0.7,
    )

    assert not _can_apply_rule_guard(
        query=query,
        llm_result=llm_result,
        rule_result=rule_result,
    )


def test_departure_point_is_not_kept_as_a_model_task():
    tasks = [
        Task(
            id="origin_marker",
            title="从第七教学楼出发",
            date=NOW.date(),
            duration_min=5,
            location_raw="第七教学楼",
        ),
        Task(
            id="study",
            title="图书馆学习",
            date=NOW.date(),
            duration_min=90,
            location_raw="图书馆",
            depends_on=["origin_marker"],
        ),
    ]

    filtered = _drop_journey_origin_marker_tasks(tasks, "第七教学楼")

    assert [task.id for task in filtered] == ["study"]
    assert filtered[0].depends_on == []


def test_real_origin_task_with_an_action_is_preserved():
    task = Task(
        id="pickup",
        title="从第七教学楼取资料后出发",
        date=NOW.date(),
        duration_min=10,
        location_raw="第七教学楼",
    )

    assert _drop_journey_origin_marker_tasks([task], "第七教学楼") == [
        task
    ]


def test_after_class_constraint_only_applies_to_its_clause():
    class_start = NOW.replace(hour=15, minute=15)
    class_end = NOW.replace(hour=16, minute=50)
    timetable_course = Task(
        id="timetable_math",
        title="数学建模",
        date=NOW.date(),
        duration_min=95,
        fixed_start=class_start,
        fixed_end=class_end,
        flexibility=TaskFlexibility.FIXED,
        tags=["course", "personal_timetable"],
    )
    parcel = Task(
        id="parcel",
        title="取快递",
        date=NOW.date(),
        duration_min=30,
    )
    morning_study = Task(
        id="study",
        title="图书馆自习",
        date=NOW.date(),
        duration_min=60,
        earliest_start=NOW.replace(hour=10, minute=0),
    )

    result = _apply_timetable_relative_constraints(
        query="下午上完课拿快递，上午10点后去图书馆自习",
        timetable_tasks=[timetable_course],
        tasks=[parcel, morning_study],
    )

    assert result[0].earliest_start == class_end
    assert result[1].earliest_start == morning_study.earliest_start


def test_online_merge_keeps_model_tasks_and_adds_verified_constraints():
    query = (
        "明天去打印店打印材料，再去菜鸟驿站取快递，"
        "最后给辅导员发邮件，18点前结束。"
    )
    parsed = _parse(query)
    rule_parcel = next(task for task in parsed.tasks if task.id == "parcel")
    rule_result = parsed.model_copy(
        update={
            "tasks": [
                rule_parcel.model_copy(update={"depends_on": []})
            ]
        }
    )
    target_date = parsed.requested_date
    timezone = NOW.tzinfo
    llm_result = UnderstandResult(
        intent=Intent.PLAN,
        requested_date=target_date,
        tasks=[
            Task(
                id="print_materials",
                title="打印课程材料",
                date=target_date,
                duration_min=20,
                location_raw="打印店",
                earliest_start=datetime(
                    2026, 7, 25, 8, 0, tzinfo=timezone
                ),
                latest_end=datetime(
                    2026, 7, 25, 18, 0, tzinfo=timezone
                ),
            ),
            Task(
                id="model_parcel",
                title="领取快递",
                date=target_date,
                duration_min=12,
                location_raw="菜鸟驿站",
                earliest_start=datetime(
                    2026, 7, 25, 7, 0, tzinfo=timezone
                ),
                latest_end=datetime(
                    2026, 7, 25, 20, 0, tzinfo=timezone
                ),
                depends_on=["print_materials"],
                tags=["model_interpreted"],
            ),
            Task(
                id="email_adviser",
                title="给辅导员发邮件",
                date=target_date,
                duration_min=10,
                depends_on=["model_parcel"],
            ),
        ],
        confidence=0.92,
    )

    result = _merge_llm_with_rule_constraints(
        query=query,
        llm_result=llm_result,
        rule_result=rule_result,
    )

    assert [task.id for task in result.tasks] == [
        "print_materials",
        "parcel",
        "email_adviser",
    ]
    parcel = result.tasks[1]
    assert parcel.duration_min == 12
    assert parcel.earliest_start == rule_parcel.earliest_start
    assert parcel.latest_end == rule_parcel.latest_end
    assert parcel.deadline == rule_parcel.deadline
    assert "model_interpreted" in parcel.tags
    assert "hard_constraint" in parcel.tags
    assert result.tasks[2].depends_on == ["parcel"]


def test_online_merge_adds_fixed_task_omitted_by_model():
    target_date = NOW.date() + timedelta(days=1)
    fixed_start = datetime(
        2026, 7, 25, 10, 0, tzinfo=NOW.tzinfo
    )
    fixed_task = Task(
        id="project_review",
        title="项目评审",
        date=target_date,
        duration_min=60,
        fixed_start=fixed_start,
        fixed_end=fixed_start + timedelta(hours=1),
        flexibility=TaskFlexibility.FIXED,
        tags=["hard_constraint"],
    )
    rule_result = UnderstandResult(
        intent=Intent.PLAN,
        requested_date=target_date,
        tasks=[fixed_task],
    )
    llm_result = UnderstandResult(
        intent=Intent.PLAN,
        requested_date=target_date,
        tasks=[
            Task(
                id="meeting_notes",
                title="整理会议纪要",
                date=target_date,
                duration_min=45,
            )
        ],
        confidence=0.9,
    )

    result = _merge_llm_with_rule_constraints(
        query="明天10点参加项目评审，再整理会议纪要",
        llm_result=llm_result,
        rule_result=rule_result,
    )

    assert [task.id for task in result.tasks] == [
        "project_review",
        "meeting_notes",
    ]
    assert result.tasks[0].fixed_start == fixed_start
    assert result.tasks[0].flexibility == TaskFlexibility.FIXED


def test_online_merge_does_not_force_rule_defaults_over_model_semantics():
    query = "今天帮我安排在宿舍学习45分钟。"
    rule_result = _parse(query)
    rule_task = rule_result.tasks[0]
    model_task = rule_task.model_copy(
        update={
            "id": "focused_study",
            "title": "在宿舍复习专业课",
            "duration_min": 45,
            "location_raw": "宿舍",
        }
    )
    llm_result = rule_result.model_copy(
        update={"tasks": [model_task], "confidence": 0.95}
    )

    result = _merge_llm_with_rule_constraints(
        query=query,
        llm_result=llm_result,
        rule_result=rule_result,
    )

    assert result.tasks[0].id == "study"
    assert result.tasks[0].title == "在宿舍复习专业课"
    assert result.tasks[0].duration_min == 45
    assert result.tasks[0].location_raw == "宿舍"
