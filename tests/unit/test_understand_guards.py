from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.nodes.understand import _can_apply_rule_guard
from app.schemas.common import Intent
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
