from __future__ import annotations

import re
from datetime import datetime
from time import perf_counter
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from app.errors import AppError
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConstraintCheck,
    ExecutionStep,
    PlanningInsight,
    PlanningTimeContext,
    SuggestedAction,
    TaskStatus,
)
from app.schemas.common import DataSource, Issue, PlanStatus
from app.schemas.plan import DataFreshness, Plan
from app.services.plan_diff import compare_plans


router = APIRouter(prefix="/api/v1", tags=["chat"])


_CURRENT_PLAN_KEYWORDS = (
    "延长",
    "增加",
    "缩短",
    "调整",
    "重新",
    "保持",
    "不要动",
    "天气",
    "下雨",
    "降雨",
    "当前计划",
)


def _requires_current_plan(query: str) -> bool:
    return any(keyword in query for keyword in _CURRENT_PLAN_KEYWORDS)


def _execution_steps(
    traces: list[dict],
    warnings: list[Issue],
) -> list[ExecutionStep]:
    definitions = [
        ("understand", "理解需求"),
        ("enrich", "补充校园信息"),
        ("plan", "生成可执行计划"),
        ("validate", "检查硬约束"),
        ("respond", "整理规划结果"),
    ]
    latest = {}
    for trace in traces:
        latest[trace.get("node")] = trace.get("summary", {})
    warning_codes = {warning.code for warning in warnings}
    steps = []
    for key, label in definitions:
        summary = latest.get(key)
        if summary is None:
            steps.append(
                ExecutionStep(
                    key=key,
                    label=label,
                    status="waiting",
                    detail="未执行",
                )
            )
            continue
        status = "success"
        if key == "understand" and "LLM_DEGRADED" in warning_codes:
            status = "fallback"
        if key == "enrich" and {
            "API_DEGRADED",
            "UNVERIFIED_CAMPUS_DATA",
        } & warning_codes:
            status = "fallback"
        if key == "validate" and summary.get("error_count", 0):
            status = "failed"
        if key == "understand":
            detail = f"识别 {summary.get('task_count', 0)} 项任务"
        elif key == "enrich":
            detail = (
                f"{summary.get('locations', 0)} 个地点，"
                f"{summary.get('routes', 0)} 条路径"
            )
        elif key == "plan":
            detail = (
                f"已安排 {summary.get('scheduled', 0)}/"
                f"{summary.get('requested', 0)} 项任务"
            )
        elif key == "validate":
            detail = (
                "全部硬约束通过"
                if not summary.get("error_count", 0)
                else f"{summary.get('error_count', 0)} 项约束未通过"
            )
        else:
            detail = "结果已生成"
        steps.append(
            ExecutionStep(
                key=key,
                label=label,
                status=status,
                detail=detail,
            )
        )
    return steps


def _constraint_checks(
    issues: list[Issue],
    *,
    weather_enforced: bool,
) -> list[ConstraintCheck]:
    definitions = [
        (
            "coverage",
            "任务完整性",
            {"TASK_UNSCHEDULED"},
            "用户提出的任务均已安排",
        ),
        (
            "time",
            "时间约束满足",
            {
                "TIME_OVERLAP",
                "FIXED_TIME_CHANGED",
                "EARLIEST_START_VIOLATION",
                "LATEST_END_VIOLATION",
            },
            "固定课程、最早开始、最晚结束和任务时间均满足",
        ),
        (
            "travel",
            "通勤时间充足",
            {"MISSING_TRAVEL_ESTIMATE", "INSUFFICIENT_TRAVEL_TIME"},
            "已按出行方式预留通勤时间，高峰期已额外加时",
        ),
        (
            "deadline",
            "截止时间满足",
            {"DEADLINE_MISSED"},
            "全部任务在截止时间前完成",
        ),
        (
            "opening",
            "场所开放可用",
            {"OUTSIDE_OPENING_HOURS"},
            "任务均位于场所开放时段",
        ),
        (
            "weather",
            "天气风险规避",
            {"WEATHER_RISK"},
            "室外任务未与已知风险时段冲突",
        ),
    ]
    if not weather_enforced:
        definitions = [
            definition
            for definition in definitions
            if definition[0] != "weather"
        ]
    return [
        ConstraintCheck(
            key=key,
            label=label,
            passed=not any(issue.code in codes for issue in issues),
            message=(
                default_message
                if not any(issue.code in codes for issue in issues)
                else "；".join(
                    issue.message for issue in issues if issue.code in codes
                )
            ),
        )
        for key, label, codes, default_message in definitions
    ]


def _fact_excerpt(content: str, query: str, limit: int = 180) -> str:
    compact = " ".join(content.split())
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？])", compact)
        if sentence.strip()
    ]
    query_chars = {
        char for char in query if "\u4e00" <= char <= "\u9fff"
    }
    if sentences and query_chars:
        compact = max(
            sentences,
            key=lambda sentence: len(
                query_chars
                & {
                    char
                    for char in sentence
                    if "\u4e00" <= char <= "\u9fff"
                }
            ),
        )
    return compact if len(compact) <= limit else compact[:limit].rstrip() + "…"


def _planning_insights(
    *,
    result: dict,
    query: str,
    time_context: PlanningTimeContext,
) -> list[PlanningInsight]:
    facts = sorted(
        result.get("retrieved_facts", []),
        key=lambda item: (-int(item.get("priority", 0)), item.get("id", "")),
    )
    insights: list[PlanningInsight] = [
        PlanningInsight(
            title="规划时间基准",
            content=(
                (
                    "系统当前按北京时间 "
                    if time_context.source == "server_clock"
                    else "本次指定北京时间为 "
                )
                + f"{time_context.now:%Y年%m月%d日 %H:%M} "
                f"计算；本次任务和天气查询对应"
                f"{time_context.target_date:%Y年%m月%d日}"
                f"（{time_context.weekday}）"
            ),
            source_label=(
                "服务器北京时间"
                if time_context.source == "server_clock"
                else "本次指定时间"
            ),
            importance="required",
        )
    ]
    preferences = result.get("preferences", {})
    transport_mode = preferences.get("transport_mode", "walk")
    mode_label = {
        "walk": "步行",
        "bicycle": "自行车",
        "electrobike": "电瓶车",
    }.get(transport_mode, "步行")
    plan_items = (result.get("final_plan") or {}).get("items", [])
    travel_items = [
        item for item in plan_items if item.get("item_type") == "travel"
    ]
    if travel_items:
        congestion_extra = sum(
            int(item.get("congestion_delay_min") or 0)
            for item in travel_items
        )
        live_route = any(
            item.get("source") == DataSource.LIVE_API.value
            for item in travel_items
        )
        content = f"本次跨地点通勤按{mode_label}计算"
        if congestion_extra:
            content += (
                f"，遇到校园集中通行时段已额外预留 "
                f"{congestion_extra} 分钟"
            )
        else:
            content += "，未触发校园高峰加时"
        insights.append(
            PlanningInsight(
                title="通勤方式与高峰缓冲",
                content=content,
                source_label=(
                    "高德实时路线"
                    if live_route
                    else "校园路线兜底数据"
                ),
                importance="required",
            )
        )
    seen_content: set[str] = set()
    fact_limit = 3 if result.get("intent") == "query" else 2
    for fact in facts:
        content = _fact_excerpt(str(fact.get("content", "")), query)
        fingerprint = content[:80]
        if not content or fingerprint in seen_content:
            continue
        seen_content.add(fingerprint)
        source = fact.get("source")
        source_ref = str(fact.get("source_ref") or "")
        if source == DataSource.STRUCTURED.value:
            title = "已核对校园规则"
            source_label = "校内结构化规则"
            importance = "required"
        elif "学生手册" in source_ref:
            title = "学生手册依据"
            source_label = "2025年学生手册"
            importance = "attention"
        else:
            title = "校园知识参考"
            source_label = "已核验知识库"
            importance = "reference"
        insights.append(
            PlanningInsight(
                title=title,
                content=content,
                source_label=source_label,
                importance=importance,
            )
        )
        if len(insights) >= fact_limit:
            break

    weather = result.get("weather_context", [])
    weather_relevant = (
        result.get("intent") == "weather_check"
        or any(item.get("source") == DataSource.USER.value for item in weather)
        or any(item.get("source") == DataSource.LIVE_API.value for item in weather)
    )
    if weather and weather_relevant:
        item = weather[0]
        weather_date = item.get("date")
        condition = item.get("condition") or "天气情况待复核"
        temperature = item.get("temperature_c")
        details = (
            f"{weather_date}：{condition}"
            if weather_date
            else condition
        )
        is_user_weather = item.get("source") == DataSource.USER.value
        if temperature is not None:
            details += f"，约 {temperature:g}℃"
        if item.get("risk_start_at"):
            risk_time = datetime.fromisoformat(item["risk_start_at"])
            details = (
                f"你提醒 {risk_time:%H:%M} 后有雨，户外任务已按这个"
                "时间边界安排"
                if is_user_weather
                else details + f"，风险时段从 {risk_time:%H:%M} 开始"
            )
        elif item.get("source") == DataSource.LIVE_API.value:
            details += "。当前为日/夜级预报，户外活动出发前请再复核"
        insights.insert(
            0,
            PlanningInsight(
                title="天气与户外安排",
                content=details,
                source_label=(
                    "用户补充"
                    if is_user_weather
                    else "实时天气"
                ),
                importance="attention",
            ),
        )

    memories = result.get("user_memories", [])
    if memories:
        labels = "、".join(
            str(item.get("label", "")) for item in memories[:3]
        )
        insights.append(
            PlanningInsight(
                title="已应用你的长期偏好",
                content=labels,
                source_label="个人记忆库",
                importance="reference",
            )
        )
    return insights[:5]


def _task_statuses(
    task_values: list[dict],
    plan: Plan | None,
    issues: list[Issue],
) -> list[TaskStatus]:
    scheduled = {
        item.task_id: item
        for item in (plan.items if plan else [])
        if item.item_type == "task" and item.task_id
    }
    issues_by_task: dict[str, list[str]] = {}
    for issue in issues:
        for task_id in issue.task_ids:
            issues_by_task.setdefault(task_id, []).append(issue.message)

    statuses = []
    for raw in task_values:
        task_id = raw["id"]
        item = scheduled.get(task_id)
        if item:
            statuses.append(
                TaskStatus(
                    task_id=task_id,
                    title=raw["title"],
                    duration_min=raw["duration_min"],
                    location_id=raw.get("location_id"),
                    status="scheduled",
                    start_at=item.start_at,
                    end_at=item.end_at,
                    message="已纳入当前时间轴",
                )
            )
            continue
        messages = list(dict.fromkeys(issues_by_task.get(task_id, [])))
        statuses.append(
            TaskStatus(
                task_id=task_id,
                title=raw["title"],
                duration_min=raw["duration_min"],
                location_id=raw.get("location_id"),
                status="needs_adjustment",
                message=(
                    "；".join(messages)
                    if messages
                    else "当前时间与约束下暂未找到可行时段"
                ),
            )
        )
    return statuses


def _adjustment_reason(
    intent: str,
    query: str,
    has_previous_plan: bool,
) -> str | None:
    if not has_previous_plan:
        return None
    if intent == "weather_check":
        return (
            "检测到17:00后降雨风险，已将室外跑步提前，并依据通勤时间"
            "对其余任务进行局部重排。"
        )
    if intent == "replan":
        if "延长" in query or "增加" in query:
            return (
                "已按新的任务时长更新计划，仅顺延受影响任务，"
                "并继续满足通勤与截止时间约束。"
            )
        return "已基于当前计划进行局部调整，尽量减少对原安排的改动。"
    return None


def _dominant_source(
    values: list[dict],
    *,
    default: DataSource = DataSource.UNKNOWN,
) -> DataSource:
    priority = [
        DataSource.USER,
        DataSource.LIVE_API,
        DataSource.STRUCTURED,
        DataSource.DEMO_FIXTURE,
        DataSource.CACHE,
        DataSource.ESTIMATED,
        DataSource.RAG,
        DataSource.UNKNOWN,
    ]
    found = {
        DataSource(value["source"])
        for value in values
        if value.get("source")
    }
    return next((source for source in priority if source in found), default)


async def execute_chat(
    payload: ChatRequest,
    request: Request,
) -> ChatResponse:
    container = request.app.state.container
    graph = request.app.state.graph
    timezone = ZoneInfo(container.settings.app_timezone)
    now = (
        payload.client_context.now.astimezone(timezone)
        if payload.client_context and payload.client_context.now
        else datetime.now(timezone)
    )
    time_source = (
        "request_context"
        if payload.client_context and payload.client_context.now
        else "server_clock"
    )
    thread_id = payload.thread_id or f"thread_{uuid4().hex}"
    request_id = f"req_{uuid4().hex}"
    trace_id = f"trace_{uuid4().hex}"

    effective_old_plan_id = payload.old_plan_id
    if effective_old_plan_id is None and _requires_current_plan(payload.query):
        latest_plan = container.plans.latest_for_thread(thread_id)
        effective_old_plan_id = latest_plan.id if latest_plan else None
    previous_plan = (
        container.plans.get(effective_old_plan_id)
        if effective_old_plan_id
        else None
    )

    container.plans.ensure_user_and_thread(
        user_id=payload.user_id,
        thread_id=thread_id,
        now=now,
    )
    container.plans.add_message(
        thread_id=thread_id,
        role="user",
        content=payload.query,
        created_at=now,
    )
    run_id = container.runs.start(
        request_id=request_id,
        trace_id=trace_id,
        thread_id=thread_id,
        input_payload=payload.model_dump(mode="json"),
        created_at=now,
        model_name=(
            container.settings.llm_model if container.llm.configured else None
        ),
    )
    started = perf_counter()
    initial_state = {
        "trace_id": trace_id,
        "user_id": payload.user_id,
        "thread_id": thread_id,
        "request_id": request_id,
        "now_iso": now.isoformat(),
        "timezone": container.settings.app_timezone,
        "mode": payload.mode,
        "query": payload.query,
        "intent": "",
        "requested_date": None,
        "old_plan_id": effective_old_plan_id,
        "tasks": [],
        "preferences": {},
        "user_memories": [],
        "clarifications": [],
        "parse_confidence": 0,
        "normalized_locations": {},
        "travel_estimates": [],
        "congestion_windows": [],
        "weather_context": [],
        "retrieved_facts": [],
        "opening_windows": {},
        "provider_warnings": [],
        "candidate_plan": None,
        "validation_issues": [],
        "replan_count": 0,
        "max_replans": 2,
        "planner_diagnostics": {},
        "final_answer": "",
        "final_plan": None,
        "response_warnings": [],
        "suggested_actions": [],
        "node_trace": [],
        "status": "started",
    }
    try:
        result = await graph.ainvoke(
            initial_state,
            config={
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 12,
            },
        )
        plan = (
            Plan.model_validate(result["final_plan"])
            if result.get("final_plan")
            else None
        )
        current_plan_saved = bool(
            plan and plan.status == PlanStatus.VALID
        )
        if current_plan_saved and plan:
            container.plans.save(
                plan,
                parent_plan_id=effective_old_plan_id,
            )
        container.plans.add_message(
            thread_id=thread_id,
            role="assistant",
            content=result["final_answer"],
            created_at=datetime.now(timezone),
        )
        warnings = [
            Issue.model_validate(raw)
            for raw in result.get("response_warnings", [])
        ]
        freshness = DataFreshness(
            route=_dominant_source(result.get("travel_estimates", [])),
            weather=_dominant_source(result.get("weather_context", [])),
            knowledge=_dominant_source(
                result.get("retrieved_facts", []),
            ),
        )
        traces = result.get("node_trace", [])
        weather_enforced = (
            result.get("intent") == "weather_check"
            or any(
                raw.get("source") == DataSource.USER.value
                for raw in result.get("weather_context", [])
            )
        )
        target_date = (
            plan.date
            if plan
            else (
                datetime.fromisoformat(result["requested_date"]).date()
                if result.get("requested_date")
                else now.date()
            )
        )
        weekdays = (
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日",
        )
        time_context = PlanningTimeContext(
            now=now,
            timezone=container.settings.app_timezone,
            target_date=target_date,
            weekday=weekdays[target_date.weekday()],
            source=time_source,
        )
        response = ChatResponse(
            request_id=request_id,
            trace_id=trace_id,
            thread_id=thread_id,
            status=result["status"],
            answer=result["final_answer"],
            plan=plan,
            clarifications=result.get("clarifications", []),
            warnings=warnings,
            data_freshness=freshness,
            location_names={
                location_id: raw.get("name", location_id)
                for location_id, raw in result.get(
                    "normalized_locations", {}
                ).items()
            },
            previous_plan=previous_plan,
            plan_diff=compare_plans(previous_plan, plan),
            adjustment_reason=_adjustment_reason(
                result.get("intent", ""),
                payload.query,
                previous_plan is not None,
            ),
            constraint_checks=_constraint_checks(
                warnings,
                weather_enforced=weather_enforced,
            ),
            execution_steps=_execution_steps(traces, warnings),
            task_statuses=_task_statuses(
                result.get("tasks", []),
                plan,
                warnings,
            ),
            suggested_actions=[
                SuggestedAction.model_validate(raw)
                for raw in result.get("suggested_actions", [])
            ],
            insights=_planning_insights(
                result=result,
                query=payload.query,
                time_context=time_context,
            ),
            time_context=time_context,
            current_plan_saved=current_plan_saved,
        )
        container.runs.finish(
            run_id=run_id,
            output_payload=response.model_dump(mode="json"),
            status=result["status"],
            node_trace=traces,
            completed_at=datetime.now(timezone),
            latency_ms=round((perf_counter() - started) * 1000),
            route_source=freshness.route.value,
            weather_source=freshness.weather.value,
        )
        return response
    except Exception as exc:
        error_code = exc.code if isinstance(exc, AppError) else "INTERNAL_ERROR"
        container.runs.finish(
            run_id=run_id,
            output_payload=None,
            status="failed",
            node_trace=[],
            completed_at=datetime.now(timezone),
            latency_ms=round((perf_counter() - started) * 1000),
            error_code=error_code,
        )
        raise


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    return await execute_chat(payload, request)


@router.get("/plans/{plan_id}", response_model=Plan)
def get_plan(plan_id: str, request: Request) -> Plan:
    plan = request.app.state.container.plans.get(plan_id)
    if plan is None:
        raise AppError(
            "PLAN_NOT_FOUND",
            "未找到指定计划",
            status_code=404,
        )
    return plan
