from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time
from hashlib import sha256
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request, status

from app.errors import AppError
from app.repositories.exceptions import (
    WeeklyGroundingSnapshotChanged,
    WeeklyPlanSnapshotChanged,
    WeeklyPlanSuperseded,
)
from app.schemas.memory import MemoryCreate
from app.schemas.timetable import CourseSessionCreate
from app.schemas.weekly import (
    CompletionEventCreate,
    CompletionEventResponse,
    WeekdayAvailability,
    WeeklyAvailabilityProfile,
    WeeklyCapacitySummary,
    WeeklyClockWindow,
    WeeklyPlanCreateRequest,
    WeeklyPlanResponse,
    WeeklyPlanStatus,
    WeeklyPlanVersionsResponse,
    WeeklyReplanRequest,
    WeeklyTextPlanRequest,
    WeeklyTriggerType,
)
from app.schemas.weekly_grounding import WeeklyDailyGroundingResponse
from app.services.weekly_request_parser import RuleBasedWeeklyRequestParser

router = APIRouter(prefix="/api/v1/weeks", tags=["weekly-planning"])


def _weekly_demo_data(request: Request) -> list[dict]:
    path = (
        request.app.state.container.settings.app_demo_dir
        / "weekly_scenarios.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise AppError(
            "WEEKLY_DEMOS_UNAVAILABLE",
            "周规划演示场景暂时无法读取。",
            status_code=503,
        ) from exc
    return payload if isinstance(payload, list) else []


@router.get("/demos/catalog")
def list_weekly_demos(request: Request) -> list[dict]:
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "description": item["description"],
        }
        for item in _weekly_demo_data(request)
    ]


@router.post(
    "/demos/{demo_id}/run",
    response_model=WeeklyPlanResponse,
)
def run_weekly_demo(
    demo_id: str,
    request: Request,
    user_id: str = Query(min_length=1, max_length=64),
) -> WeeklyPlanResponse:
    fixture = next(
        (
            item
            for item in _weekly_demo_data(request)
            if item.get("id") == demo_id
        ),
        None,
    )
    if fixture is None:
        raise AppError(
            "WEEKLY_DEMO_NOT_FOUND",
            "没有找到这个周规划演示场景。",
            status_code=404,
        )
    demo_user_id = _demo_user_id(user_id=user_id, demo_id=demo_id)
    raw_request = dict(fixture["request"])
    raw_request["user_id"] = demo_user_id
    container = request.app.state.container
    _prepare_demo_personal_context(
        fixture=fixture,
        user_id=demo_user_id,
        container=container,
    )
    payload = WeeklyPlanCreateRequest.model_validate(raw_request)
    payload, capacity_summary = _resolve_capacities(
        payload=payload,
        container=container,
    )
    previous = container.weekly_plans.latest(
        user_id=payload.user_id,
        campus_id=payload.campus_id,
        week_start=payload.week_start,
    )
    plan = container.weekly_allocator.allocate(
        payload,
        version=(previous.version + 1 if previous else 1),
        baseline_plan_id=(previous.id if previous else None),
        trigger_type=(
            WeeklyTriggerType.MANUAL
            if previous
            else WeeklyTriggerType.INITIAL
        ),
        now=datetime.now(ZoneInfo(payload.timezone)),
    )
    container.weekly_plans.save(plan)
    return WeeklyPlanResponse(
        status="completed",
        answer=_plan_answer(plan),
        weekly_plan=plan,
        capacity_summary=capacity_summary,
    )


@router.post(
    "/plan",
    response_model=WeeklyPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_weekly_plan(
    payload: WeeklyPlanCreateRequest,
    request: Request,
) -> WeeklyPlanResponse:
    container = request.app.state.container
    payload, capacity_summary = _resolve_capacities(
        payload=payload,
        container=container,
    )
    now = datetime.now(ZoneInfo(payload.timezone))
    previous = container.weekly_plans.latest(
        user_id=payload.user_id,
        campus_id=payload.campus_id,
        week_start=payload.week_start,
    )
    plan = container.weekly_allocator.allocate(
        payload,
        version=(previous.version + 1 if previous else 1),
        baseline_plan_id=(previous.id if previous else None),
        trigger_type=(
            WeeklyTriggerType.MANUAL
            if previous
            else WeeklyTriggerType.INITIAL
        ),
        now=now,
    )
    container.weekly_plans.save(plan)
    return WeeklyPlanResponse(
        status="completed",
        answer=_plan_answer(plan),
        weekly_plan=plan,
        capacity_summary=capacity_summary,
    )


@router.post(
    "/plan/from-text",
    response_model=WeeklyPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_weekly_plan_from_text(
    payload: WeeklyTextPlanRequest,
    request: Request,
) -> WeeklyPlanResponse:
    container = request.app.state.container
    now = datetime.now(ZoneInfo(payload.timezone))
    rules = RuleBasedWeeklyRequestParser(payload.timezone).parse(
        query=payload.query,
        week_start=payload.week_start,
    )
    interpretation = rules
    parser_name = "structured_rules"
    if (rules.clarifications or not rules.goals) and container.llm.configured:
        try:
            container.llm.reset_usage()
            memories = container.memories.list(
                payload.user_id,
                enabled_only=True,
            )
            model_result = await container.llm.parse_weekly_requirement(
                query=payload.query,
                week_start=payload.week_start.isoformat(),
                now_iso=now.isoformat(),
                memory_context=[
                    {
                        "category": item.category,
                        "label": item.label,
                        "key": item.key,
                        "value": item.value,
                    }
                    for item in memories
                ],
            )
            if model_result.goals and not model_result.clarifications:
                interpretation = model_result
                parser_name = "llm"
        except Exception:  # noqa: BLE001
            # A weekly plan must remain usable when a model's free quota,
            # rate limit, or temporary availability changes.
            parser_name = "structured_rules_fallback"
    if interpretation.clarifications or not interpretation.goals:
        questions = interpretation.clarifications or [
            "请至少告诉我一个本周目标、预计投入时长和截止时间。"
        ]
        raise AppError(
            "WEEKLY_CLARIFICATION_REQUIRED",
            "我还差一项关键信息，先确认后才能稳妥安排这一周。",
            status_code=422,
            details=[
                {"question": question}
                for question in questions[:3]
            ],
        )

    availability = payload.availability or _default_weekly_availability()
    plan_request = WeeklyPlanCreateRequest(
        user_id=payload.user_id,
        campus_id=payload.campus_id,
        week_start=payload.week_start,
        timezone=payload.timezone,
        goals=interpretation.goals,
        availability=availability,
    )
    plan_request, capacity_summary = _resolve_capacities(
        payload=plan_request,
        container=container,
    )
    previous = container.weekly_plans.latest(
        user_id=payload.user_id,
        campus_id=payload.campus_id,
        week_start=payload.week_start,
    )
    plan = container.weekly_allocator.allocate(
        plan_request,
        version=(previous.version + 1 if previous else 1),
        baseline_plan_id=(previous.id if previous else None),
        trigger_type=(
            WeeklyTriggerType.MANUAL
            if previous
            else WeeklyTriggerType.INITIAL
        ),
        now=now,
    )
    container.weekly_plans.save(plan)
    return WeeklyPlanResponse(
        status="completed",
        answer=_plan_answer(plan),
        weekly_plan=plan,
        capacity_summary=capacity_summary,
        parser=parser_name,
        interpretation=interpretation,
    )


@router.get(
    "/{week_start}",
    response_model=WeeklyPlanResponse,
)
def get_weekly_plan(
    week_start: date,
    request: Request,
    user_id: str = Query(min_length=1, max_length=64),
    campus_id: str = Query(min_length=1, max_length=100),
) -> WeeklyPlanResponse:
    plan = request.app.state.container.weekly_plans.latest(
        user_id=user_id,
        campus_id=campus_id,
        week_start=week_start,
    )
    if plan is None:
        raise AppError(
            "WEEKLY_PLAN_NOT_FOUND",
            "还没有找到这一周的计划，可以先告诉我本周目标和可用时间。",
            status_code=404,
        )
    return WeeklyPlanResponse(
        status="completed",
        answer=_plan_answer(plan),
        weekly_plan=plan,
    )


@router.get(
    "/{week_start}/versions",
    response_model=WeeklyPlanVersionsResponse,
)
def list_weekly_plan_versions(
    week_start: date,
    request: Request,
    user_id: str = Query(min_length=1, max_length=64),
    campus_id: str = Query(min_length=1, max_length=100),
) -> WeeklyPlanVersionsResponse:
    return WeeklyPlanVersionsResponse(
        items=request.app.state.container.weekly_plans.versions(
            user_id=user_id,
            campus_id=campus_id,
            week_start=week_start,
        )
    )


@router.post(
    "/{plan_id}/days/{target_date}/materialize",
    response_model=WeeklyDailyGroundingResponse,
)
async def materialize_weekly_day(
    plan_id: str,
    target_date: date,
    request: Request,
    user_id: str = Query(min_length=1, max_length=64),
    prefer_live: bool = Query(default=True),
) -> WeeklyDailyGroundingResponse:
    container = request.app.state.container
    _current_weekly_plan(
        container=container,
        plan_id=plan_id,
        user_id=user_id,
    )
    try:
        return await container.weekly_grounding.materialize_day(
            plan_id=plan_id,
            user_id=user_id,
            target_date=target_date,
            prefer_live=prefer_live,
        )
    except WeeklyPlanSuperseded as exc:
        raise _weekly_plan_superseded_error(container, plan_id) from exc
    except WeeklyGroundingSnapshotChanged as exc:
        raise AppError(
            "WEEKLY_GROUNDING_SNAPSHOT_CHANGED",
            "周计划在生成日程期间发生了变化，请重试。",
            status_code=409,
            retryable=True,
            details=[{"reason": str(exc)}],
        ) from exc
    except LookupError as exc:
        raise AppError(
            "WEEKLY_PLAN_NOT_FOUND",
            "没有找到对应的周计划。",
            status_code=404,
        ) from exc
    except ValueError as exc:
        raise AppError(
            "WEEKLY_DAY_OUTSIDE_PLAN",
            "要落地的日期必须位于这份周计划内。",
            status_code=422,
            details=[{"reason": str(exc)}],
        ) from exc


@router.post(
    "/{plan_id}/replan",
    response_model=WeeklyPlanResponse,
    status_code=status.HTTP_201_CREATED,
)
def replan_weekly_plan(
    plan_id: str,
    payload: WeeklyReplanRequest,
    request: Request,
    user_id: str = Query(min_length=1, max_length=64),
) -> WeeklyPlanResponse:
    container = request.app.state.container
    baseline = _current_weekly_plan(
        container=container,
        plan_id=plan_id,
        user_id=user_id,
    )
    baseline_fingerprint = (
        container.weekly_plans.weekly_plan_fingerprint(baseline)
    )

    known_allocation_ids = {
        allocation.id for allocation in baseline.allocations
    }
    unknown_allocation_ids = sorted(
        set(payload.invalidated_allocation_ids)
        - known_allocation_ids
    )
    if unknown_allocation_ids:
        raise AppError(
            "WEEKLY_ALLOCATION_NOT_FOUND",
            "要失效的周计划块不存在，请刷新后重试。",
            status_code=404,
            details=[
                {
                    "allocation_ids": unknown_allocation_ids,
                }
            ],
        )

    capacities, capacity_summary = _resolve_replan_capacities(
        payload=payload,
        baseline=baseline,
        container=container,
    )
    now = datetime.now(ZoneInfo(baseline.timezone))
    try:
        plan = container.weekly_replanner.replan(
            baseline=baseline,
            capacities=capacities,
            trigger=payload.trigger_type,
            now=now,
            invalidated_allocation_ids=(
                payload.invalidated_allocation_ids
            ),
            additional_goals=payload.additional_goals,
        )
        container.weekly_plans.save_replan(
            plan,
            baseline_plan_id=baseline.id,
            baseline_fingerprint=baseline_fingerprint,
        )
    except WeeklyPlanSuperseded as exc:
        raise _weekly_plan_superseded_error(container, plan_id) from exc
    except WeeklyPlanSnapshotChanged as exc:
        raise AppError(
            "WEEKLY_REPLAN_SNAPSHOT_CHANGED",
            "周计划在重排期间发生了变化，请基于最新进度重试。",
            status_code=409,
            retryable=True,
            details=[{"reason": str(exc)}],
        ) from exc
    except ValueError as exc:
        raise AppError(
            "WEEKLY_REPLAN_INVALID",
            "当前变化信息不足以生成可靠的周计划新版本。",
            status_code=422,
            details=[{"reason": str(exc)}],
        ) from exc
    except sqlite3.IntegrityError as exc:
        raise AppError(
            "WEEKLY_REPLAN_CONFLICT",
            "周计划刚刚被另一项操作更新，请读取最新版本后重试。",
            status_code=409,
        ) from exc

    return WeeklyPlanResponse(
        status="completed",
        answer=_replan_answer(plan),
        weekly_plan=plan,
        capacity_summary=capacity_summary,
    )


@router.post(
    "/{plan_id}/events",
    response_model=CompletionEventResponse,
)
def record_weekly_event(
    plan_id: str,
    payload: CompletionEventCreate,
    request: Request,
    user_id: str = Query(min_length=1, max_length=64),
) -> CompletionEventResponse:
    container = request.app.state.container
    _current_weekly_plan(
        container=container,
        plan_id=plan_id,
        user_id=user_id,
    )
    now = datetime.now(ZoneInfo(container.settings.app_timezone))
    try:
        event, applied = container.weekly_plans.record_event(
            user_id=user_id,
            plan_id=plan_id,
            payload=payload,
            now=now,
        )
    except WeeklyPlanSuperseded as exc:
        raise _weekly_plan_superseded_error(container, plan_id) from exc
    except LookupError as exc:
        if str(exc) == "WEEKLY_ALLOCATION_NOT_FOUND":
            raise AppError(
                "WEEKLY_ALLOCATION_NOT_FOUND",
                "没有找到这段安排，可能已经被新的周计划替换。",
                status_code=404,
            ) from exc
        raise AppError(
            "WEEKLY_PLAN_NOT_FOUND",
            "没有找到对应的周计划。",
            status_code=404,
        ) from exc
    plan = container.weekly_plans.get(plan_id)
    if plan is None:
        raise AppError(
            "WEEKLY_PLAN_NOT_FOUND",
            "没有找到对应的周计划。",
            status_code=404,
        )
    return CompletionEventResponse(
        status="completed",
        applied=applied,
        message=(
            "完成情况已经记下，剩余目标时长也同步更新了。"
            if applied
            else "这条完成记录已经处理过，不会重复扣减任务时长。"
        ),
        event=event,
        weekly_plan=plan,
    )


def _current_weekly_plan(
    *,
    container,
    plan_id: str,
    user_id: str,
):
    plan = container.weekly_plans.get(plan_id)
    if plan is None or plan.user_id != user_id:
        raise AppError(
            "WEEKLY_PLAN_NOT_FOUND",
            "没有找到对应的周计划。",
            status_code=404,
        )
    latest = container.weekly_plans.latest(
        user_id=user_id,
        campus_id=plan.campus_id,
        week_start=plan.week_start,
    )
    if latest is None or latest.id != plan.id:
        raise AppError(
            "WEEKLY_PLAN_SUPERSEDED",
            "这份周计划已有更新版本，请基于最新版本继续操作。",
            status_code=409,
            details=[
                {
                    "latest_plan_id": latest.id if latest else None,
                    "latest_version": latest.version if latest else None,
                }
            ],
        )
    return plan


def _weekly_plan_superseded_error(container, plan_id: str) -> AppError:
    plan = container.weekly_plans.get(plan_id)
    latest = (
        container.weekly_plans.latest(
            user_id=plan.user_id,
            campus_id=plan.campus_id,
            week_start=plan.week_start,
        )
        if plan is not None
        else None
    )
    return AppError(
        "WEEKLY_PLAN_SUPERSEDED",
        "这份周计划已有更新版本，请基于最新版本继续操作。",
        status_code=409,
        details=[
            {
                "latest_plan_id": latest.id if latest else None,
                "latest_version": latest.version if latest else None,
            }
        ],
    )


def _plan_answer(plan) -> str:
    allocated = plan.metrics.allocated_duration_min
    requested = plan.metrics.requested_duration_min
    days = len({item.date for item in plan.allocations})
    if plan.status == WeeklyPlanStatus.VALID:
        return (
            f"我已经把这周的 {len(plan.goals)} 个目标拆成"
            f" {len(plan.allocations)} 个可执行时间块，"
            f"共安排 {allocated} 分钟，分布在 {days} 天。"
            "阶段先后、截止时间和每天的承载上限都已保留；"
            "每天真正执行前，还会再结合课表、地点通勤、"
            "场馆开放时间和天气做一次细化校验。"
        )
    missing = max(0, requested - allocated)
    if plan.status == WeeklyPlanStatus.AT_RISK:
        return (
            f"本周大部分目标已经安排好，但还有 {missing} 分钟"
            "存在挤压风险。我保留了原始任务时长，没有为了让计划"
            "看起来完整而擅自缩短；你可以增加可用时间，或调整"
            "非硬性目标的截止时间。"
        )
    return (
        f"我先把当前条件下能安全执行的部分排好了，但本周仍缺少"
        f" {missing} 分钟，硬性截止目标暂时无法全部完成。"
        "我没有隐藏或删除任何任务。建议先增加一个可用时段，"
        "或明确哪项任务可以延期，我再做最小幅度的调整。"
    )


def _replan_answer(plan) -> str:
    preservation = plan.metrics.preservation_rate
    preservation_text = (
        f"{preservation:.0%}" if preservation is not None else "无可比较旧块"
    )
    summary = (
        f"已生成第 {plan.version} 版周计划：保留率 {preservation_text}，"
        f"移动 {plan.metrics.moved_allocation_count} 个原时间块。"
    )
    if plan.status == WeeklyPlanStatus.VALID:
        return summary + "所有剩余目标均已在当前硬约束内重新落位。"
    return (
        summary
        + f"仍有 {plan.metrics.unallocated_duration_min} 分钟无法安全安排；"
        "系统保留了冻结时间块，并在 issues 中给出具体冲突。"
    )


def _resolve_replan_capacities(
    *,
    payload: WeeklyReplanRequest,
    baseline,
    container,
):
    if payload.capacities:
        return payload.capacities, WeeklyCapacitySummary(
            source="manual",
            notes=["按本次事件提供的最新可用时段执行最小扰动重排"],
        )
    profile = payload.availability or _default_weekly_availability()
    result = container.weekly_capacity.build(
        user_id=baseline.user_id,
        week_start=baseline.week_start,
        timezone_name=baseline.timezone,
        profile=profile,
    )
    return result.capacities, result.summary


def _resolve_capacities(
    *,
    payload: WeeklyPlanCreateRequest,
    container,
) -> tuple[WeeklyPlanCreateRequest, WeeklyCapacitySummary]:
    payload = _apply_weekly_goal_memories(
        payload=payload,
        container=container,
    )
    if payload.capacities:
        return payload, WeeklyCapacitySummary(
            source="manual",
            notes=["按用户明确提供的本周可用时段分配"],
        )
    if payload.availability is None:
        raise AppError(
            "WEEKLY_AVAILABILITY_REQUIRED",
            "请先设置一周中通常可安排任务的时段。",
            status_code=422,
        )
    result = container.weekly_capacity.build(
        user_id=payload.user_id,
        week_start=payload.week_start,
        timezone_name=payload.timezone,
        profile=payload.availability,
    )
    return (
        payload.model_copy(update={"capacities": result.capacities}),
        result.summary,
    )


def _default_weekly_availability() -> WeeklyAvailabilityProfile:
    """A broad candidate window; personal hard constraints are subtracted.

    This is not an instruction to fill the whole day. Goal chunk limits,
    imported courses, calendar overrides, and enabled memory settings still
    control the actual weekly load.
    """
    return WeeklyAvailabilityProfile(
        days=[
            WeekdayAvailability(
                weekday=weekday,
                windows=[
                    WeeklyClockWindow(
                        start=time(7, 0),
                        end=time(22, 30),
                    )
                ],
                notes=["由系统结合个人课表与校历计算可用时间"],
            )
            for weekday in range(1, 8)
        ],
        use_timetable=True,
        use_calendar=True,
        use_memories=True,
    )


def _apply_weekly_goal_memories(
    *,
    payload: WeeklyPlanCreateRequest,
    container,
) -> WeeklyPlanCreateRequest:
    if payload.availability and not payload.availability.use_memories:
        return payload
    memories = {
        item.key: item.value
        for item in container.memories.list(
            payload.user_id,
            enabled_only=True,
        )
    }
    preferred_period = memories.get("preferred_study_period")
    preferred_location = memories.get("preferred_study_location")
    if not preferred_location:
        locations = memories.get("preferred_locations")
        if isinstance(locations, list) and locations:
            preferred_location = locations[0]
    if (
        preferred_period not in {"morning", "afternoon", "evening"}
        and not (
            isinstance(preferred_location, str)
            and preferred_location.strip()
        )
    ):
        return payload
    study_keywords = (
        "学习",
        "自习",
        "复习",
        "备考",
        "考试",
        "作业",
        "论文",
        "报告",
        "阅读",
        "课程设计",
        "实验数据",
    )
    goals = []
    for goal in payload.goals:
        if not any(keyword in goal.title for keyword in study_keywords):
            goals.append(goal)
            continue
        update = {}
        if not goal.preferred_periods and preferred_period in {
            "morning",
            "afternoon",
            "evening",
        }:
            update["preferred_periods"] = [preferred_period]
        if (
            not goal.preferred_locations
            and isinstance(preferred_location, str)
            and preferred_location.strip()
        ):
            update["preferred_locations"] = [
                preferred_location.strip()
            ]
        goals.append(goal.model_copy(update=update) if update else goal)
    return payload.model_copy(update={"goals": goals})


def _prepare_demo_personal_context(
    *,
    fixture: dict,
    user_id: str,
    container,
) -> None:
    setup = fixture.get("setup")
    if not isinstance(setup, dict):
        return
    now = datetime.now(ZoneInfo(container.settings.app_timezone))
    timetable = setup.get("timetable")
    if isinstance(timetable, dict):
        entries = [
            CourseSessionCreate.model_validate(item)
            for item in timetable.get("entries", [])
        ]
        container.timetables.replace(
            user_id=user_id,
            name=str(timetable.get("name") or "演示课表"),
            term_start=(
                date.fromisoformat(timetable["term_start"])
                if timetable.get("term_start")
                else None
            ),
            term_end=(
                date.fromisoformat(timetable["term_end"])
                if timetable.get("term_end")
                else None
            ),
            enabled=True,
            entries=entries,
            now=now,
        )
    for raw_memory in setup.get("memories", []):
        container.memories.upsert(
            user_id=user_id,
            payload=MemoryCreate.model_validate(raw_memory),
            now=now,
        )


def _demo_user_id(*, user_id: str, demo_id: str) -> str:
    digest = sha256(f"{user_id}:{demo_id}".encode()).hexdigest()[:24]
    return f"weekly_demo_{digest}"
