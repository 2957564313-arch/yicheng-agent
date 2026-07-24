from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from app.container import AppContainer
from app.nodes.common import append_trace
from app.schemas.common import Issue, IssueSeverity
from app.schemas.context import RetrievedFact, TravelEstimate, WeatherContext
from app.schemas.plan import Plan
from app.schemas.task import Task
from app.state import CampusAgentState


def make_respond_node(container: AppContainer):
    async def respond(state: CampusAgentState) -> dict:
        if state.get("clarifications"):
            answer = (
                "为了不替你做错决定，我还想确认一件事："
                + "；".join(state["clarifications"])
            )
            return {
                "final_answer": answer,
                "final_plan": None,
                "response_warnings": state.get("provider_warnings", []),
                "status": "needs_clarification",
                "node_trace": append_trace(
                    state,
                    "respond",
                    {"kind": "clarification"},
                ),
            }

        if state.get("intent") == "query":
            facts = [
                RetrievedFact.model_validate(raw)
                for raw in state.get("retrieved_facts", [])
            ]
            timetable_fact = next(
                (fact for fact in facts if fact.id == "personal_timetable"),
                None,
            )
            if timetable_fact is not None:
                answer = _timetable_answer(timetable_fact.content)
                used_llm = False
            elif not facts:
                answer = (
                    "当前知识库中没有检索到足够依据。"
                    "请提供更具体的制度名称，或以上传的正式文件为准。"
                )
                used_llm = False
            elif (
                container.settings.llm_render_enabled
                and container.llm.configured
            ):
                try:
                    answer = await container.llm.answer_question(
                        query=state["query"],
                        facts=facts,
                    )
                    answer = _plain_text_answer(answer)
                    used_llm = True
                except Exception:
                    answer = _facts_answer(facts)
                    used_llm = False
            else:
                answer = _facts_answer(facts)
                used_llm = False
            return {
                "final_answer": answer,
                "final_plan": None,
                "response_warnings": state.get("provider_warnings", []),
                "status": "completed",
                "node_trace": append_trace(
                    state,
                    "respond",
                    {
                        "kind": "knowledge_query",
                        "llm": used_llm,
                        "fact_count": len(facts),
                    },
                ),
            }

        plan = Plan.model_validate(state["candidate_plan"])
        tasks = [Task.model_validate(raw) for raw in state.get("tasks", [])]
        facts = [
            RetrievedFact.model_validate(raw)
            for raw in state.get("retrieved_facts", [])
        ]
        warnings = [
            *state.get("provider_warnings", []),
            *state.get("validation_issues", []),
        ]
        has_errors = any(
            raw.get("severity") == IssueSeverity.ERROR.value
            for raw in warnings
        )
        if has_errors:
            draft, suggested_actions = _infeasible_answer(
                plan=plan,
                warnings=warnings,
                tasks=tasks,
                now=datetime.fromisoformat(state["now_iso"]),
                routes=[
                    TravelEstimate.model_validate(raw)
                    for raw in state.get("travel_estimates", [])
                ],
            )
        else:
            draft = _success_answer(
                plan,
                warnings,
                intent=state.get("intent", "plan"),
                query=state.get("query", ""),
                facts=facts,
                weather=[
                    WeatherContext.model_validate(raw)
                    for raw in state.get("weather_context", [])
                ],
                congestion_windows=container.rules.congestion_windows(
                    plan.date
                ),
            )
            suggested_actions = _congestion_suggested_actions(
                plan,
                already_requested=bool(
                    state.get("preferences", {}).get("avoid_congestion")
                ),
            )

        answer = draft
        used_llm = False
        if (
            container.settings.llm_render_enabled
            and container.llm.configured
        ):
            try:
                weather_context = state.get("weather_context", [])
                weather_is_relevant = (
                    state.get("intent") == "weather_check"
                    or any(
                        raw.get("source") == "user"
                        for raw in weather_context
                    )
                )
                polished = await container.llm.polish_answer(
                    draft=draft,
                    context={
                        "status": "infeasible" if has_errors else "valid",
                        "user_query": state.get("query", ""),
                        "intent": state.get("intent", "plan"),
                        "requested_tasks": [
                            task.model_dump(mode="json") for task in tasks
                        ],
                        "plan": plan.model_dump(mode="json"),
                        "warnings": warnings,
                        "weather_context": (
                            weather_context if weather_is_relevant else []
                        ),
                        "campus_facts": [
                            {
                                "content": fact.content,
                                "priority": fact.priority,
                                "source": fact.source.value,
                            }
                            for fact in facts[:4]
                        ],
                        "applied_memories": [
                            {
                                "label": raw.get("label"),
                                "value": raw.get("value"),
                            }
                            for raw in state.get("user_memories", [])
                        ],
                    },
                )
                cleaned = _plain_text_answer(polished)
                if _polished_answer_is_grounded(
                    cleaned,
                    tasks=tasks,
                    plan=plan,
                    warnings=warnings,
                ):
                    answer = cleaned
                    used_llm = True
            except Exception:
                pass

        return {
            "final_answer": answer,
            "final_plan": plan.model_dump(mode="json"),
            "response_warnings": warnings,
            "suggested_actions": suggested_actions,
            "status": "partial" if has_errors else "completed",
            "node_trace": append_trace(
                state,
                "respond",
                {
                    "kind": "infeasible" if has_errors else "success",
                    "llm": used_llm,
                },
            ),
        }

    return respond


def _timetable_answer(summary: str) -> str:
    if "没有已启用的课程记录" in summary:
        return (
            "我帮你看过个人课表了。\n\n"
            f"{summary}\n\n"
            "这一天暂时没有课程占用，你可以直接告诉我想安排的"
            "学习、运动或生活任务，我会继续帮你把时间和通勤一起排好。"
        )
    prefix, separator, remainder = summary.partition("为：")
    details = remainder if separator else summary
    details = details.replace("。这些课程属于固定时间约束。", "")
    entries = [item.strip() for item in details.split("；") if item.strip()]
    lines = [
        "我帮你看过个人课表了。",
        "",
        f"{prefix}有以下课程：",
        *[f"• {item}" for item in entries],
        "",
        "这些上课时间已经自动记为固定约束。接下来无论安排自习、"
        "取快递还是运动，我都会先避开课程，再把通勤和开放时间留好。",
    ]
    return "\n".join(lines)


def _success_answer(
    plan: Plan,
    warnings: list[dict],
    *,
    intent: str,
    query: str,
    facts: list[RetrievedFact],
    weather: list[WeatherContext],
    congestion_windows: list[tuple[datetime, datetime]],
) -> str:
    ordered_items = sorted(plan.items, key=lambda value: value.start_at)
    task_items = [
        item for item in ordered_items if item.item_type == "task"
    ]
    task_titles = [item.title for item in task_items]
    task_names = "、".join(f"“{title}”" for title in task_titles)
    weather_adjustment = _has_precise_weather_risk(weather)
    if weather_adjustment:
        lines = [
            "天气有变化时，安全比赶进度更重要。"
            "我把容易受影响的户外安排挪到了更稳妥的时段，"
            "其余事情尽量保持原来的节奏。"
        ]
        lines.append(
            f"安排思路：先避开风险时段完成户外任务，再衔接"
            f"{task_names}；这样既照顾安全，也不需要推翻整天的计划。"
        )
    elif intent == "replan":
        lines = [
            "你刚刚强调的变化我记下了。"
            "这次只调整受影响的部分，能保留的安排我都替你留住了。"
        ]
        lines.append(
            f"安排思路：围绕新的要求重新衔接{task_names}，"
            "没有变化的任务尽量留在原来的时间。"
        )
    else:
        lines = [
            "这几件事能排开。"
            "我把路上的时间和场所开放时段也留意过了，"
            "按这个节奏走，不需要卡着分钟一路赶。"
        ]
        if any("自习" in title or "学习" in title for title in task_titles):
            lines.append(
                "安排思路：先留出一段完整、连续的学习时间，"
                "再按你说的先后顺序衔接其他事情，避免把专注时间切得"
                "太碎；"
                "跨地点之间的通勤时间也已经按你选择的出行方式单独留出。"
            )
        else:
            lines.append(
                f"安排思路：把{task_names}按时间和地点顺序连起来，"
                "尽量减少来回折返。"
            )
    if "后天" in query:
        day_label = "后天"
    elif "明天" in query:
        day_label = "明天"
    elif "今天" in query:
        day_label = "今天"
    else:
        day_label = f"{plan.date.month}月{plan.date.day}日"
    lines.append(f"{day_label}可以这样安排：")
    for item in ordered_items:
        label = item.title
        duration_min = int(
            (item.end_at - item.start_at).total_seconds() // 60
        )
        lines.append(
            f"• {item.start_at:%H:%M}—{item.end_at:%H:%M}　"
            f"{label}（{duration_min}分钟）"
        )
    warning_messages = [
        Issue.model_validate(raw).message
        for raw in warnings
        if (
            raw.get("severity") == IssueSeverity.WARNING.value
            and raw.get("code")
            not in {
                "LLM_DEGRADED",
                "API_DEGRADED",
                "UNVERIFIED_CAMPUS_DATA",
                "PARTIAL_LIVE_ROUTE_COVERAGE",
                "ROUTE_FALLBACK",
                "PEAK_CONGESTION",
            }
        )
    ]
    if warning_messages:
        lines.append("提醒：" + "；".join(dict.fromkeys(warning_messages)))
    elif weather_adjustment:
        lines.append(
            "时间、通勤、开放时段和天气风险都已经核对过，"
            "户外任务安排在已知风险时段之前。"
        )
    else:
        lines.append(
            "时间、通勤和开放时段都已经核对过，可以安心照着执行。"
        )
    reminders = _knowledge_reminders(facts)
    weather_reminder = _weather_reminder(weather)
    if weather_reminder:
        reminders.insert(0, weather_reminder)
        reminders = reminders[:2]
    elif (
        any(word in query for word in ("天气", "下雨", "降雨", "有雨"))
        and any(
            raw.get("code") == "API_DEGRADED"
            and raw.get("details", {}).get("provider") == "weather"
            for raw in warnings
        )
    ):
        reminders.insert(
            0,
            "目标日期暂时没有可靠的天气预报；临近当天再查一次会更"
            "准确，如果遇到降雨或高温，我可以只调整跑步等户外安排。",
        )
        reminders = reminders[:2]
    congestion_reminder = _congestion_reminder(
        ordered_items,
        congestion_windows,
    )
    if congestion_reminder:
        reminders.insert(0, congestion_reminder)
        reminders = reminders[:2]
    if reminders:
        lines.append("再替你留意两点：")
        lines.extend(f"• {item}" for item in reminders)
    if ordered_items:
        lines.append(
            f"整套安排预计在 {ordered_items[-1].end_at:%H:%M} 收尾，"
            f"其中已经留出 {plan.metrics.travel_minutes} 分钟通勤。"
        )
    lines.append(
        "如果临时晚出发、课程拖堂或身体状态有变化，直接告诉我"
        "晚了多久或哪一项想保留，我会只调整受影响的部分。"
    )
    return "\n".join(lines)


def _has_precise_weather_risk(weather: list[WeatherContext]) -> bool:
    """Only claim a timed adjustment when a verified risk boundary exists."""
    return any(
        item.risk_start_at is not None
        and (
            "雨" in (item.condition or "")
            or "雪" in (item.condition or "")
            or "风" in (item.condition or "")
            or (item.rain_probability or 0) >= 0.5
        )
        for item in weather
    )


def _weather_reminder(weather: list[WeatherContext]) -> str | None:
    live = next(
        (
            item
            for item in weather
            if item.source.value in {"user", "live_api"}
        ),
        None,
    )
    if live is None:
        return None
    condition = live.condition or ""
    if (
        "雨" in condition
        or "雪" in condition
        or "风" in condition
        or (live.rain_probability or 0) >= 0.5
    ):
        if live.risk_start_at:
            if live.source.value == "user":
                return (
                    f"你提醒 {live.risk_start_at:%H:%M} 后有雨，户外活动"
                    "已经按这个时间边界处理；出发前再看一次临近预报"
                    "会更稳妥。"
                )
            return (
                f"{live.risk_start_at:%H:%M} 后有“{condition or '降雨'}”"
                "风险，户外活动已按这个时间边界处理；出发前再看一次"
                "临近预报会更稳妥。"
            )
        return (
            f"天气信息显示“{condition}”，目前只能精确到日/夜时段；"
            "户外活动出发前请再看一次临近预报，变化时我可以局部调整。"
        )
    if live.temperature_c is not None and live.temperature_c >= 32:
        return (
            f"当前预报约 {live.temperature_c:g}℃，运动前记得补水，"
            "尽量避开最晒的时段。"
        )
    return None


def _congestion_reminder(
    items,
    windows: list[tuple[datetime, datetime]],
) -> str | None:
    travel_items = [item for item in items if item.item_type == "travel"]
    for item in travel_items:
        if item.congestion_delay_min > 0:
            mode_label = {
                "walk": "步行",
                "bicycle": "自行车骑行",
                "electrobike": "电瓶车骑行",
            }.get(item.travel_mode or "", "通勤")
            base_label = (
                "高德返回时间"
                if item.source.value == "live_api"
                else "校园路线基准时间"
            )
            return (
                f"这段{mode_label}会经过校园集中通行时段，已在"
                f"{base_label}上额外预留 {item.congestion_delay_min} 分钟；"
                "不用强行错峰，如果时间允许，稍晚出发会更从容。"
            )
        for start_at, end_at in windows:
            if item.start_at < end_at and item.end_at > start_at:
                return (
                    f"{start_at:%H:%M}—{end_at:%H:%M} 是校园集中通行"
                    "时段，这段路建议提前几分钟出发，遇到人流也不会"
                    "打乱后面的安排。"
                )
    return None


def _congestion_suggested_actions(
    plan: Plan,
    *,
    already_requested: bool,
) -> list[dict]:
    if already_requested or not any(
        item.item_type == "travel" and item.congestion_delay_min > 0
        for item in plan.items
    ):
        return []
    return [
        {
            "id": "prefer_off_peak",
            "label": "看看错峰方案",
            "description": (
                "保持课程、截止时间和任务时长不变，仅在有余地时"
                "优先避开集中通行时段。"
            ),
            "query": (
                "在不改变固定课程、截止时间、任务时长和原有顺序的"
                "前提下，尽量避开校园拥堵时段，重新安排当前计划。"
            ),
        }
    ]


def _knowledge_reminders(
    facts: list[RetrievedFact],
    *,
    limit: int = 2,
) -> list[str]:
    reminders: list[str] = []
    for fact in sorted(facts, key=lambda item: -item.priority):
        compact = " ".join(fact.content.split())
        first_sentence = re.split(r"(?<=[。！？])", compact)[0].strip()
        if not first_sentence:
            continue
        if len(first_sentence) > 150:
            first_sentence = first_sentence[:150].rstrip() + "…"
        if any(
            first_sentence[:60] == existing[:60]
            for existing in reminders
        ):
            continue
        reminders.append(first_sentence)
        if len(reminders) >= limit:
            break
    return reminders


def _infeasible_answer(
    *,
    plan: Plan,
    warnings: list[dict],
    tasks: list[Task],
    now: datetime,
    routes: list[TravelEstimate],
) -> tuple[str, list[dict]]:
    error_messages = [
        Issue.model_validate(raw).message
        for raw in warnings
        if raw.get("severity") == IssueSeverity.ERROR.value
    ]
    scheduled_ids = {
        item.task_id
        for item in plan.items
        if item.item_type == "task" and item.task_id
    }
    unscheduled = [task for task in tasks if task.id not in scheduled_ids]
    unscheduled_names = "、".join(
        f"“{task.title}”" for task in unscheduled
    )
    all_task_names = "、".join(f"“{task.title}”" for task in tasks)
    deadline_values = [
        task.deadline for task in tasks if task.deadline is not None
    ]
    deadline = min(deadline_values) if deadline_values else None
    starts = [
        task.earliest_start
        for task in tasks
        if task.earliest_start is not None
    ]
    target_start = (
        now
        if now.date() == plan.date
        else datetime.combine(plan.date, time(8, 0), now.tzinfo)
    )
    planning_start = max(
        target_start,
        min(starts) if starts else target_start,
    )
    planning_start = _ceil_five_minutes(planning_start)
    active_tasks = [
        task
        for task in tasks
        if task.fixed_end is None or task.fixed_end > planning_start
    ]
    route_minutes = _ordered_route_minutes(active_tasks, routes)
    required_minutes = (
        sum(task.duration_min for task in active_tasks) + route_minutes
    )
    available_minutes = (
        max(0, int((deadline - planning_start).total_seconds() // 60))
        if deadline
        else None
    )
    deficit = (
        max(0, required_minutes - available_minutes)
        if available_minutes is not None
        else 0
    )

    lines = [
        f"你想把{all_task_names}都顾上，我明白。"
        "只是现在时间确实有点赶，我不想为了让日程看起来完整，"
        "就悄悄删掉任何一项。"
    ]
    if unscheduled_names:
        lines.append(
            f"{unscheduled_names}都还在清单里，我没有替你删掉；"
            "只是按现在的结束时间，还没有足够的空档把它们妥善放进去。"
        )
    else:
        lines.append(
            "这些任务都已经记下，只是它们和当前结束时间撞在了一起。"
        )

    if deadline and available_minutes is not None:
        lines.append(
            f"我先说结论：如果一定要在 {deadline:%H:%M} 前结束，"
            "这几件事目前无法全部按原时长完成。"
        )
        lines.append(
            "原因很具体："
            f"从 {planning_start:%H:%M} 到 {deadline:%H:%M}，"
            f"能用的时间只有 {available_minutes} 分钟；"
            f"把原任务时长和约 {route_minutes} 分钟通勤都算进去，"
            f"至少需要 {required_minutes} 分钟"
            + (f"，还差约 {deficit} 分钟。" if deficit else "。")
        )
    elif error_messages:
        lines.append("冲突原因：" + "；".join(dict.fromkeys(error_messages)))
    hard_rule_notes = [
        task.notes
        for task in unscheduled
        if task.notes
        and any(
            marker in task.notes
            for marker in ("营业时间", "开放时间", "硬约束")
        )
    ]
    if hard_rule_notes:
        lines.append(
            "需要特别说明的场所规则："
            + "；".join(dict.fromkeys(hard_rule_notes))
            + "。"
        )

    suggestions = _adjustment_suggestions(
        tasks=active_tasks,
        planning_start=planning_start,
        deadline=deadline,
        required_minutes=required_minutes,
        deficit=deficit,
    )
    study_task = next(
        (
            task
            for task in tasks
            if "自习" in task.title or "学习" in task.title
        ),
        None,
    )
    if (
        study_task
        and study_task.duration_min >= 60
        and study_task.duration_min - deficit - 10 < 30
        and deadline
    ):
        lines.append(
            f"{study_task.title}原本需要 {study_task.duration_min} 分钟。"
            "如果只为了守住结束时间而把它压成十几二十分钟，"
            "看起来是排进去了，实际上很难形成有效学习，"
            "所以我没有把这种“凑时间”的结果当成可行方案。"
        )
    if suggestions:
        lines.append("更合适的处理方式是：")
        lines.extend(
            f"{index}. {action['description']}"
            for index, action in enumerate(suggestions, start=1)
        )
        lines.append(
            (
                "选一个更符合你今天状态的方案，我再把完整日程排好。"
            )
            if len(suggestions) >= 2
            else (
                "如果这个结束时间可以接受，点一下我就重新排好；"
                f"如果 {deadline:%H:%M} 必须守住，请告诉我哪一项可以"
                "顺延，"
                "我不会擅自牺牲你明确要求的任务时长。"
            )
        )
    elif error_messages:
        lines.append("需要处理：" + "；".join(dict.fromkeys(error_messages)))
    if plan.items:
        lines.append(
            "下方时间轴先保留能稳妥完成的部分；"
            "还没排进去的任务会明确标成“待调整”，不会被藏起来。"
        )
    return "\n".join(lines), suggestions


def _ordered_route_minutes(
    tasks: list[Task],
    routes: list[TravelEstimate],
) -> int:
    route_map = {
        (route.origin_id, route.destination_id): route.duration_min
        for route in routes
    }
    total = 0
    for previous, current in zip(tasks, tasks[1:]):
        if (
            previous.location_id
            and current.location_id
            and previous.location_id != current.location_id
        ):
            total += route_map.get(
                (previous.location_id, current.location_id),
                0,
            )
    return total


def _adjustment_suggestions(
    *,
    tasks: list[Task],
    planning_start: datetime,
    deadline: datetime | None,
    required_minutes: int,
    deficit: int,
) -> list[dict]:
    if not deadline or deficit <= 0:
        return []
    action_safety_min = 10
    adjustable = next(
        (
            task
            for task in tasks
            if "自习" in task.title or "学习" in task.title
        ),
        max(tasks, key=lambda task: task.duration_min, default=None),
    )
    suggestions: list[dict] = []
    if adjustable:
        shortened = max(
            5,
            (
                (
                    adjustable.duration_min
                    - deficit
                    - action_safety_min
                )
                // 5
            )
            * 5,
        )
        if shortened >= 30:
            description = (
                f"守住 {deadline:%H:%M}：把{adjustable.title}从"
                f"{adjustable.duration_min}分钟缩短到约{shortened}分钟，"
                "其余任务和通勤保留。"
            )
            suggestions.append(
                {
                    "id": "option_1",
                    "label": f"守住 {deadline:%H:%M}",
                    "description": description,
                    "query": _standalone_query(
                        tasks=tasks,
                        planning_start=planning_start,
                        deadline=deadline,
                        duration_overrides={adjustable.id: shortened},
                    ),
                }
            )
    earliest_finish = _ceil_five_minutes(
        planning_start
        + timedelta(minutes=required_minutes + action_safety_min)
    )
    suggestions.append(
        {
            "id": "option_2",
            "label": "保留完整安排",
            "description": (
                "不牺牲"
                + "、".join(task.title for task in tasks)
                + "的完整性，"
                f"把最晚结束时间放宽到约 {earliest_finish:%H:%M}。"
            ),
            "query": _standalone_query(
                tasks=tasks,
                planning_start=planning_start,
                deadline=earliest_finish,
                duration_overrides={},
            ),
        }
    )
    return suggestions[:2]


def _standalone_query(
    *,
    tasks: list[Task],
    planning_start: datetime,
    deadline: datetime,
    duration_overrides: dict[str, int],
) -> str:
    task_parts = []
    for task in tasks:
        duration = duration_overrides.get(task.id, task.duration_min)
        task_parts.append(f"{task.title}{duration}分钟")
    joined = "，然后".join(task_parts)
    return (
        f"{planning_start:%Y-%m-%d} {planning_start:%H:%M}以后，"
        f"{joined}，{deadline:%H:%M}前结束。"
    )


def _ceil_five_minutes(value: datetime) -> datetime:
    value = value.replace(second=0, microsecond=0)
    remainder = value.minute % 5
    return (
        value
        if remainder == 0
        else value + timedelta(minutes=5 - remainder)
    )


def _covers_all_tasks(answer: str, tasks: list[Task]) -> bool:
    return all(task.title in answer for task in tasks)


def _polished_answer_is_grounded(
    answer: str,
    *,
    tasks: list[Task],
    plan: Plan,
    warnings: list[dict],
) -> bool:
    """Fail closed when language polishing changes verified planning facts."""
    if not _covers_all_tasks(answer, tasks):
        return False

    for item in plan.items:
        if item.item_type != "task":
            continue
        if (
            f"{item.start_at:%H:%M}" not in answer
            or f"{item.end_at:%H:%M}" not in answer
        ):
            return False

    for task in tasks:
        if not task.notes or not any(
            marker in task.notes
            for marker in ("营业时间", "开放时间")
        ):
            continue
        required_times = re.findall(r"\b\d{2}:\d{2}\b", task.notes)
        if any(value not in answer for value in required_times):
            return False

    has_peak_congestion = any(
        raw.get("code") == "PEAK_CONGESTION" for raw in warnings
    )
    if has_peak_congestion and _claims_peak_was_avoided(answer):
        return False

    has_only_non_live_routes = all(
        item.source.value != "live_api"
        for item in plan.items
        if item.item_type == "travel"
    )
    if has_only_non_live_routes and re.search(
        r"高德(?:实时|返回).{0,8}(?:路线|时间|数据)",
        answer,
    ):
        return False
    return True


def _claims_peak_was_avoided(answer: str) -> bool:
    patterns = (
        r"(?:已经|已|刚好|正好|能够|能|可以)?[^。；\n]{0,10}"
        r"(?:避开|错开)[^。；\n]{0,12}(?:高峰|拥堵|最拥挤|人流)",
        r"(?:高峰|拥堵|最拥挤|人流)[^。；\n]{0,10}"
        r"(?:已经|已)?(?:避开|错开)",
        r"(?:不在|没有经过|未经过)[^。；\n]{0,8}"
        r"(?:高峰|拥堵|最拥挤|集中通行时段)",
    )
    return any(re.search(pattern, answer) for pattern in patterns)


def _plain_text_answer(answer: str) -> str:
    cleaned = (
        answer.replace("**", "")
        .replace("### ", "")
        .replace("## ", "")
        .replace("# ", "")
        .strip()
    )
    cleaned = re.sub(
        (
            r"^(?:(?:你好|您好|没问题|好的|当然可以|可以(?:的)?)"
            r"[！!，,。.\s]*)+"
        ),
        "",
        cleaned,
    ).lstrip()
    return re.sub(
        (
            r"^(\d{1,2}点(?:以后|之后|后).{0,12}"
            r"(?:有雨|下雨|降雨))[，,]\s*把"
        ),
        r"\1。考虑到安全，我已经把",
        cleaned,
        count=1,
    )


def _facts_answer(facts: list[RetrievedFact]) -> str:
    lines = ["根据当前校园知识库："]
    seen_sources: list[str] = []
    for fact in facts[:3]:
        lines.append(f"- {fact.content}")
        if fact.source_ref and fact.source_ref not in seen_sources:
            seen_sources.append(fact.source_ref)
    if seen_sources:
        lines.append("来源：" + "；".join(seen_sources))
    return "\n".join(lines)
