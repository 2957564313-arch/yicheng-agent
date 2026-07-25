from datetime import date

from app.services.weekly_request_parser import RuleBasedWeeklyRequestParser


def test_complex_weekly_text_preserves_stages_deadlines_and_repetition():
    result = RuleBasedWeeklyRequestParser().parse(
        query=(
            "周五22:00前完成课程设计，共8小时，"
            "其中编码4小时、测试2小时、报告2小时；"
            "周三20:00前完成论文阅读，共2小时；"
            "本周跑步2次，每次40分钟，尽量晚上去东操场。"
        ),
        week_start=date(2026, 7, 27),
    )

    assert result.clarifications == []
    assert len(result.goals) == 3
    design, paper, running = result.goals
    assert design.title == "课程设计"
    assert design.total_duration_min == 480
    assert design.deadline.isoformat() == "2026-07-31T22:00:00+08:00"
    assert [item.title for item in design.stages] == [
        "编码",
        "测试",
        "报告",
    ]
    assert design.stages[1].depends_on_stage_ids == ["stage_1"]
    assert design.stages[2].depends_on_stage_ids == ["stage_2"]
    assert paper.deadline.isoformat() == "2026-07-29T20:00:00+08:00"
    assert running.total_duration_min == 80
    assert running.min_chunk_min == 40
    assert running.max_chunk_min == 40
    assert running.max_chunks_per_day == 1
    assert running.preferred_periods == ["evening"]
    assert running.preferred_locations == ["东操场"]
    assert running.hard_deadline is True


def test_weekly_text_uses_safe_defaults_only_for_common_tasks():
    result = RuleBasedWeeklyRequestParser().parse(
        query=(
            "周二前取快递；周四晚上跑步；"
            "周日前完善一个还没定义范围的创新方案。"
        ),
        week_start=date(2026, 7, 27),
    )

    assert [item.title for item in result.goals] == ["取快递", "跑步"]
    assert [item.total_duration_min for item in result.goals] == [30, 30]
    assert result.clarifications == [
        "“完善一个还没定义范围的创新方案”预计需要投入多长时间？"
        "可以写成“共3小时”或“2次，每次40分钟”。"
    ]


def test_weekly_text_without_any_goal_asks_one_actionable_question():
    result = RuleBasedWeeklyRequestParser().parse(
        query="请帮我看看这一周。",
        week_start=date(2026, 7, 27),
    )

    assert result.goals == []
    assert result.clarifications
    assert "预计需要投入多长时间" in result.clarifications[0]
