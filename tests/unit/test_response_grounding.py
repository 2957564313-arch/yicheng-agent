from datetime import datetime
from zoneinfo import ZoneInfo

from app.nodes.respond import (
    _claims_peak_was_avoided,
    _polished_answer_is_grounded,
)
from app.schemas.common import DataSource, PlanStatus
from app.schemas.plan import Plan, PlanItem
from app.schemas.task import Task


TZ = ZoneInfo("Asia/Shanghai")


def _plan() -> Plan:
    return Plan(
        id="plan_grounding",
        user_id="user",
        thread_id="thread",
        date=datetime(2026, 7, 24, tzinfo=TZ).date(),
        status=PlanStatus.VALID,
        items=[
            PlanItem(
                id="study_item",
                task_id="study",
                item_type="task",
                title="图书馆自习",
                start_at=datetime(2026, 7, 24, 14, 0, tzinfo=TZ),
                end_at=datetime(2026, 7, 24, 16, 0, tzinfo=TZ),
                location_id="library",
                source=DataSource.USER,
            ),
            PlanItem(
                id="travel_item",
                item_type="travel",
                title="步行前往取快递地点",
                start_at=datetime(2026, 7, 24, 16, 0, tzinfo=TZ),
                end_at=datetime(2026, 7, 24, 16, 17, tzinfo=TZ),
                location_id="parcel_station",
                source=DataSource.STRUCTURED,
                travel_mode="walk",
                base_duration_min=13,
                congestion_delay_min=4,
            ),
            PlanItem(
                id="parcel_item",
                task_id="parcel",
                item_type="task",
                title="取快递",
                start_at=datetime(2026, 7, 24, 16, 20, tzinfo=TZ),
                end_at=datetime(2026, 7, 24, 16, 50, tzinfo=TZ),
                location_id="parcel_station",
                source=DataSource.USER,
            ),
        ],
        created_at=datetime(2026, 7, 24, 13, 0, tzinfo=TZ),
    )


def _tasks() -> list[Task]:
    return [
        Task(
            id="study",
            title="图书馆自习",
            date=datetime(2026, 7, 24, tzinfo=TZ).date(),
            duration_min=120,
        ),
        Task(
            id="parcel",
            title="取快递",
            date=datetime(2026, 7, 24, tzinfo=TZ).date(),
            duration_min=30,
        ),
    ]


def test_peak_avoidance_claim_is_rejected_when_route_crosses_peak():
    answer = (
        "图书馆自习安排在14:00—16:00，取快递安排在16:20—16:50。"
        "按这个时间点出发刚好能避开最拥挤的人流。"
    )
    assert _claims_peak_was_avoided(answer)
    assert not _polished_answer_is_grounded(
        answer,
        tasks=_tasks(),
        plan=_plan(),
        warnings=[{"code": "PEAK_CONGESTION"}],
    )


def test_truthful_peak_buffer_wording_is_accepted():
    answer = (
        "图书馆自习安排在14:00—16:00，取快递安排在16:20—16:50。"
        "这段路仍会经过集中通行时段，已经额外增加4分钟缓冲；"
        "不用强行错峰。"
    )
    assert not _claims_peak_was_avoided(answer)
    assert _polished_answer_is_grounded(
        answer,
        tasks=_tasks(),
        plan=_plan(),
        warnings=[{"code": "PEAK_CONGESTION"}],
    )


def test_offline_route_cannot_be_described_as_live_amap_result():
    answer = (
        "图书馆自习安排在14:00—16:00，取快递安排在16:20—16:50。"
        "高德实时路线数据已经确认。"
    )
    assert not _polished_answer_is_grounded(
        answer,
        tasks=_tasks(),
        plan=_plan(),
        warnings=[],
    )
