from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.nodes.understand import (
    _apply_activity_location_memories,
    _apply_memory_preferences,
    _apply_timetable_relative_constraints,
    _can_apply_rule_guard,
    _drop_journey_origin_marker_tasks,
    _expand_occurrences,
    _merge_llm_with_rule_constraints,
    _release_destination_from_departure_anchor,
    _roll_over_exhausted_day,
)
from app.schemas.common import Intent, TaskFlexibility
from app.schemas.memory import MemoryCreate
from app.schemas.task import Task, UserPreferences
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


def test_saved_meal_times_replace_default_meal_windows():
    preferences = _apply_memory_preferences(
        UserPreferences(),
        [
            MemoryCreate(
                category="habit",
                key="usual_lunch_time",
                label="常用午餐时间",
                value="12:40",
            ),
            MemoryCreate(
                category="habit",
                key="usual_dinner_time",
                label="常用晚餐时间",
                value="18:10",
            ),
        ],
    )

    actual = [
        (window.start.isoformat(), window.end.isoformat())
        for window in preferences.meal_windows
    ]
    assert actual == [
        ("12:40:00", "13:30:00"),
        ("18:10:00", "18:55:00"),
    ]


def test_schedule_pace_uses_natural_three_level_setting():
    compact = _apply_memory_preferences(
        UserPreferences(),
        [
            MemoryCreate(
                category="preference",
                key="schedule_pace",
                label="日程节奏",
                value="compact",
            )
        ],
    )
    relaxed = _apply_memory_preferences(
        UserPreferences(buffer_min=5),
        [
            MemoryCreate(
                category="preference",
                key="schedule_pace",
                label="日程节奏",
                value="relaxed",
            )
        ],
    )

    assert compact.avoid_tight_schedule is False
    assert compact.buffer_min == 0
    assert relaxed.avoid_tight_schedule is True
    assert relaxed.buffer_min == 15


def test_activity_location_memory_only_fills_matching_missing_place():
    tasks = [
        Task(
            id="rehearsal",
            title="乐团排练",
            date=NOW.date(),
            duration_min=60,
        ),
        Task(
            id="meeting",
            title="和导师碰头",
            date=NOW.date(),
            duration_min=30,
            location_raw="导师办公室",
        ),
        Task(
            id="parcel",
            title="取快递",
            date=NOW.date(),
            duration_min=20,
        ),
    ]
    memories = [
        MemoryCreate(
            category="preference",
            key="activity_location",
            label="事情对应地点",
            value=[
                {"activity": "乐团排练", "location": "学活A区"},
                {"activity": "导师碰头", "location": "10教408"},
            ],
        )
    ]

    adjusted = _apply_activity_location_memories(
        tasks,
        memories=memories,
    )

    assert adjusted[0].location_raw == "学活A区"
    assert "memory_activity_location" in adjusted[0].tags
    assert adjusted[1].location_raw == "导师办公室"
    assert adjusted[2].location_raw is None


def test_activity_location_memory_refines_generic_parser_location():
    tasks = [
        Task(
            id="study",
            title="图书馆自习",
            date=NOW.date(),
            duration_min=120,
            location_raw="图书馆",
        ),
        Task(
            id="run",
            title="跑步",
            date=NOW.date(),
            duration_min=30,
            location_raw="操场",
        ),
    ]
    memories = [
        MemoryCreate(
            category="preference",
            key="activity_location",
            label="事项地点偏好",
            value=[
                {"activity": "自习", "location": "图书馆12层"},
                {"activity": "跑步", "location": "东操场"},
            ],
        )
    ]

    adjusted = _apply_activity_location_memories(
        tasks,
        memories=memories,
        query="今天去图书馆自习2小时，然后跑步30分钟。",
    )

    assert adjusted[0].location_raw == "图书馆12层"
    assert adjusted[1].location_raw == "东操场"


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


def test_departure_leg_to_first_destination_is_not_a_separate_task():
    tasks = [
        Task(
            id="travel_like_task",
            title="从第七教学楼出发前往图书馆",
            date=NOW.date(),
            duration_min=30,
            location_raw="图书馆",
        ),
        Task(
            id="study",
            title="在图书馆学习",
            date=NOW.date(),
            duration_min=90,
            location_raw="图书馆",
        ),
    ]

    filtered = _drop_journey_origin_marker_tasks(tasks, "第七教学楼")

    assert [task.id for task in filtered] == ["study"]


def test_matched_explicit_task_is_not_removed_by_journey_cleanup():
    study = Task(
        id="study",
        title="从第七教学楼出发前往图书馆学习",
        date=NOW.date(),
        duration_min=90,
        location_raw="图书馆",
    )

    filtered = _drop_journey_origin_marker_tasks(
        [study],
        "第七教学楼",
        protected_task_ids={"study"},
    )

    assert filtered == [study]


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


def test_departure_time_is_not_a_fixed_start_for_destination_task():
    departure_at = NOW.replace(hour=16, minute=0)
    task = Task(
        id="study",
        title="图书馆学习",
        date=NOW.date(),
        duration_min=90,
        location_raw="图书馆",
        fixed_start=departure_at,
        fixed_end=departure_at + timedelta(minutes=90),
        flexibility=TaskFlexibility.FIXED,
        tags=["model_interpreted"],
    )

    normalized = _release_destination_from_departure_anchor(
        task,
        departure_at,
    )

    assert normalized.fixed_start is None
    assert normalized.fixed_end is None
    assert normalized.flexibility == TaskFlexibility.MOVABLE


def test_hard_fixed_task_at_departure_time_is_preserved():
    departure_at = NOW.replace(hour=16, minute=0)
    task = Task(
        id="meeting",
        title="固定会议",
        date=NOW.date(),
        duration_min=60,
        fixed_start=departure_at,
        fixed_end=departure_at + timedelta(minutes=60),
        flexibility=TaskFlexibility.FIXED,
        tags=["hard_constraint"],
    )

    assert _release_destination_from_departure_anchor(
        task,
        departure_at,
    ) == task


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


def test_enumerated_request_keeps_every_explicit_task_and_occurrence():
    query = (
        "今天很空，能帮我安排一下吗？自习2次，还要取快递、跑步，"
        "还要晚上和导师碰头2h。"
    )

    parsed = _parse(query)
    expanded = _expand_occurrences(parsed.tasks)

    assert len(expanded) == 5
    assert sum("自习" in task.title for task in expanded) == 2
    assert sum("快递" in task.title for task in expanded) == 1
    assert sum("跑步" in task.title for task in expanded) == 1
    assert sum("导师" in task.title for task in expanded) == 1
    studies = [task for task in expanded if "自习" in task.title]
    assert all(task.duration_source == "default" for task in studies)
    assert all(task.duration_min == 120 for task in studies)
    assert all(task.min_duration_min == 60 for task in studies)
    advisor = next(task for task in expanded if "导师" in task.title)
    assert advisor.duration_min == 120
    assert advisor.duration_source == "explicit"
    assert advisor.preferred_period == "evening"


def test_online_merge_cannot_drop_enumerated_tasks_or_double_occurrences():
    query = (
        "今天很空，能帮我安排一下吗？自习2次，还要取快递、跑步，"
        "还要晚上和导师碰头2h。"
    )
    rule_result = _parse(query)
    target_date = rule_result.requested_date
    assert target_date is not None

    # A realistic imperfect model response: it represents the two sittings
    # as two objects, but accidentally omits parcel pickup.  The merge layer
    # must neither turn two sittings into four nor silently delete parcel.
    llm_result = UnderstandResult(
        intent=Intent.PLAN,
        requested_date=target_date,
        tasks=[
            Task(
                id="study_a",
                title="自习（第一次）",
                date=target_date,
                duration_min=120,
                min_duration_min=60,
            ),
            Task(
                id="study_b",
                title="自习（第二次）",
                date=target_date,
                duration_min=120,
                min_duration_min=60,
            ),
            Task(
                id="run",
                title="跑步",
                date=target_date,
                duration_min=30,
            ),
            Task(
                id="advisor",
                title="晚上和导师碰头",
                date=target_date,
                duration_min=120,
                preferred_period="evening",
            ),
        ],
        confidence=0.95,
    )

    merged = _merge_llm_with_rule_constraints(
        query=query,
        llm_result=llm_result,
        rule_result=rule_result,
    )
    expanded = _expand_occurrences(merged.tasks)

    assert len(expanded) == 5
    assert sum("自习" in task.title for task in expanded) == 2
    assert sum("快递" in task.title for task in expanded) == 1
    assert sum("跑步" in task.title for task in expanded) == 1
    assert sum("导师" in task.title for task in expanded) == 1


def test_late_full_day_workload_rolls_to_tomorrow_without_shrinking_tasks():
    late_now = datetime(
        2026,
        8,
        20,
        17,
        57,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    parsed = RuleBasedRequirementParser("Asia/Shanghai").parse(
        query=(
            "今天很空，能帮我安排一下吗？自习2次，还要取快递、跑步，"
            "还要晚上和导师碰头2h。"
        ),
        now=late_now,
    )
    parsed = parsed.model_copy(update={"tasks": _expand_occurrences(parsed.tasks)})

    shifted, notice = _roll_over_exhausted_day(
        result=parsed,
        now=late_now,
        old_plan=None,
    )

    assert shifted.requested_date == late_now.date() + timedelta(days=1)
    assert len(shifted.tasks) == 5
    assert [task.duration_min for task in shifted.tasks] == [
        task.duration_min for task in parsed.tasks
    ]
    assert all(task.date == shifted.requested_date for task in shifted.tasks)
    assert notice is not None


def test_morning_full_day_workload_stays_today():
    morning_now = datetime(
        2026,
        8,
        20,
        9,
        0,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    parsed = RuleBasedRequirementParser("Asia/Shanghai").parse(
        query=(
            "今天很空，能帮我安排一下吗？自习2次，还要取快递、跑步，"
            "还要晚上和导师碰头2h。"
        ),
        now=morning_now,
    )
    parsed = parsed.model_copy(update={"tasks": _expand_occurrences(parsed.tasks)})

    unchanged, notice = _roll_over_exhausted_day(
        result=parsed,
        now=morning_now,
        old_plan=None,
    )

    assert unchanged.requested_date == morning_now.date()
    assert notice is None


def test_hard_deadline_is_never_silently_rolled_to_tomorrow():
    late_now = datetime(
        2026,
        8,
        20,
        20,
        0,
        tzinfo=ZoneInfo("Asia/Shanghai"),
    )
    target = late_now.date()
    result = UnderstandResult(
        intent=Intent.PLAN,
        requested_date=target,
        tasks=[
            Task(
                id=f"task_{index}",
                title=f"任务{index}",
                date=target,
                duration_min=120,
                deadline=late_now.replace(hour=23, minute=0),
            )
            for index in range(3)
        ],
    )

    unchanged, notice = _roll_over_exhausted_day(
        result=result,
        now=late_now,
        old_plan=None,
    )

    assert unchanged.requested_date == target
    assert notice is None
