from datetime import datetime
from zoneinfo import ZoneInfo

from app.nodes.respond import (
    _claims_peak_was_avoided,
    _ensure_query_guardrails,
    _plain_text_answer,
    _polished_answer_is_grounded,
    _success_answer,
    _weather_reminder,
)
from app.schemas.common import DataSource, PlanStatus
from app.schemas.context import RetrievedFact, WeatherContext
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


def test_day_level_weather_adds_reminder_without_claiming_timed_adjustment():
    answer = _success_answer(
        _plan(),
        [],
        intent="plan",
        query="请结合天气安排今天的事情。",
        facts=[],
        weather=[
            WeatherContext(
                date=datetime(2026, 7, 24, tzinfo=TZ).date(),
                period="day",
                condition="晴",
                temperature_c=37,
                source=DataSource.LIVE_API,
            )
        ],
        congestion_windows=[],
    )

    assert "天气有变化时" not in answer
    assert "先避开风险时段" not in answer
    assert "户外任务安排在已知风险时段之前" not in answer
    assert "当前预报约 37℃" in answer


def test_precise_weather_risk_is_not_claimed_when_outdoor_task_crosses_it():
    plan = _plan().model_copy(
        update={
            "items": [
                *_plan().items,
                PlanItem(
                    id="run_item",
                    task_id="run",
                    item_type="task",
                    title="跑步",
                    start_at=datetime(2026, 7, 24, 17, 5, tzinfo=TZ),
                    end_at=datetime(2026, 7, 24, 17, 35, tzinfo=TZ),
                    location_id="track",
                    source=DataSource.USER,
                ),
            ]
        }
    )
    answer = _success_answer(
        plan,
        [],
        intent="plan",
        query="下午去图书馆自习、取快递和跑步",
        facts=[],
        weather=[
            WeatherContext(
                date=datetime(2026, 7, 24, tzinfo=TZ).date(),
                period="17:00以后",
                condition="rain",
                rain_probability=0.85,
                risk_start_at=datetime(2026, 7, 24, 17, 0, tzinfo=TZ),
                source=DataSource.DEMO_FIXTURE,
            )
        ],
        congestion_windows=[],
    )

    assert "天气有变化时" not in answer
    assert "先避开风险时段" not in answer
    assert "户外任务安排在已知风险时段之前" not in answer


def test_precise_weather_adjustment_is_claimed_after_outdoor_task_moves_early():
    plan = _plan().model_copy(
        update={
            "items": [
                PlanItem(
                    id="run_item",
                    task_id="run",
                    item_type="task",
                    title="跑步",
                    start_at=datetime(2026, 7, 24, 14, 0, tzinfo=TZ),
                    end_at=datetime(2026, 7, 24, 14, 30, tzinfo=TZ),
                    location_id="track",
                    source=DataSource.USER,
                ),
                *_plan().items,
            ]
        }
    )
    answer = _success_answer(
        plan,
        [],
        intent="replan",
        query="17点以后有雨，请调整计划",
        facts=[],
        weather=[
            WeatherContext(
                date=datetime(2026, 7, 24, tzinfo=TZ).date(),
                period="17:00以后",
                condition="用户告知有雨",
                rain_probability=1,
                risk_start_at=datetime(2026, 7, 24, 17, 0, tzinfo=TZ),
                source=DataSource.USER,
            )
        ],
        congestion_windows=[],
    )

    assert "天气有变化时" in answer
    assert "先避开风险时段" in answer


def test_missing_requested_weather_is_explained_without_provider_jargon():
    answer = _success_answer(
        _plan(),
        [
            {
                "code": "LLM_DEGRADED",
                "severity": "warning",
                "message": "大模型暂时不可用，已切换为本地规则继续处理",
                "details": {},
            },
            {
                "code": "API_DEGRADED",
                "severity": "warning",
                "message": "未获取到可靠天气，户外安排请出发前复核",
                "details": {"provider": "weather"},
            },
        ],
        intent="plan",
        query="请结合天气安排今天的事情。",
        facts=[],
        weather=[],
        congestion_windows=[],
    )

    assert "大模型暂时不可用" not in answer
    assert "目标日期暂时没有可靠的天气预报" in answer


def test_markdown_bullets_are_normalized_for_plain_text_frontend():
    answer = _plain_text_answer(
        "好的，安排如下：\n* 第一项提醒\n- 第二项提醒"
    )

    assert answer.startswith("安排如下：")
    assert "* " not in answer
    assert "- " not in answer
    assert "• 第一项提醒" in answer
    assert "• 第二项提醒" in answer


def test_rain_reminder_includes_umbrella_and_wet_surface_care():
    reminder = _weather_reminder(
        [
            WeatherContext(
                date=datetime(2026, 7, 24, tzinfo=TZ).date(),
                period="afternoon",
                condition="用户告知有雨",
                risk_start_at=datetime(2026, 7, 24, 17, 0, tzinfo=TZ),
                source=DataSource.USER,
            )
        ],
        query="17点后去操场跑步",
    )

    assert reminder is not None
    assert "带把伞" in reminder
    assert "湿滑" in reminder
    assert "17:00" in reminder


def test_hot_weather_reminder_matches_non_sport_task():
    reminder = _weather_reminder(
        [
            WeatherContext(
                date=datetime(2026, 7, 24, tzinfo=TZ).date(),
                period="day",
                condition="晴",
                temperature_c=38,
                source=DataSource.LIVE_API,
            )
        ],
        query="去图书馆学习",
    )

    assert reminder is not None
    assert "防晒和补水" in reminder
    assert "运动前" not in reminder


def test_custom_campus_without_rules_never_claims_opening_hours_checked():
    single_task_plan = Plan(
        id="custom_campus_plan",
        user_id="user",
        thread_id="thread",
        date=datetime(2026, 7, 25, tzinfo=TZ).date(),
        status=PlanStatus.VALID,
        items=[
            PlanItem(
                id="study_item",
                task_id="study",
                item_type="task",
                title="图书馆自习",
                start_at=datetime(2026, 7, 25, 14, 0, tzinfo=TZ),
                end_at=datetime(2026, 7, 25, 15, 0, tzinfo=TZ),
                location_id="custom_library",
                source=DataSource.USER,
            )
        ],
        created_at=datetime(2026, 7, 24, 13, 0, tzinfo=TZ),
    )
    answer = _success_answer(
        single_task_plan,
        [
            {
                "code": "CAMPUS_KNOWLEDGE_NOT_CONFIGURED",
                "severity": "warning",
                "message": "本校知识包尚未导入",
                "details": {},
            }
        ],
        intent="plan",
        query="明天14点去图书馆学习1小时",
        facts=[],
        weather=[],
        congestion_windows=[],
    )

    assert "开放时段也留意过" not in answer
    assert "开放时段都已经核对过" not in answer
    assert "留出 0 分钟通勤" not in answer
    assert "本校知识包尚未导入" in answer

    assert not _polished_answer_is_grounded(
        (
            "图书馆自习安排在14:00—15:00，"
            "场所开放时段已经核对过。"
        ),
        tasks=[
            Task(
                id="study",
                title="图书馆自习",
                date=single_task_plan.date,
                duration_min=60,
            )
        ],
        plan=single_task_plan,
        warnings=[
            {
                "code": "CAMPUS_KNOWLEDGE_NOT_CONFIGURED",
                "severity": "warning",
            }
        ],
    )


def test_library_query_keeps_floor_specific_caveat():
    answer = _ensure_query_guardrails(
        "图书馆整体开放到22:30，六层和十二层可以使用。",
        query="今天22点去图书馆自习30分钟可以吗",
        facts=[
            RetrievedFact(
                id="library_hours",
                content=(
                    "六层、十二层7:00—22:30；"
                    "七至十一层8:00—21:30。"
                ),
                source=DataSource.RAG,
                source_ref="杭电时间知识库.docx",
            )
        ],
    )

    assert "不同楼层开放时间不同" in answer


def test_holiday_query_keeps_school_calendar_caveat():
    answer = _ensure_query_guardrails(
        "2026年国庆节10月1日至7日放假，共7天。",
        query="2026年国庆节怎么放假",
        facts=[
            RetrievedFact(
                id="holiday",
                content="国务院办公厅通知：国庆节放假调休。",
                source=DataSource.RAG,
                source_ref="gov.cn",
            )
        ],
    )

    assert "学校校历" in answer
    assert "教务通知" in answer
