from __future__ import annotations

import re
from datetime import datetime, time, timedelta

from app.container import AppContainer
from app.nodes.common import append_trace
from app.schemas.common import DataSource, Issue, IssueSeverity
from app.schemas.context import RetrievedFact, TravelEstimate, WeatherContext
from app.schemas.plan import Plan
from app.schemas.task import Task
from app.state import CampusAgentState


def make_respond_node(container: AppContainer):
    async def respond(state: CampusAgentState) -> dict:
        if state.get("clarifications"):
            answer = _clarification_answer(
                query=state.get("query", ""),
                clarifications=state["clarifications"],
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
            direct_operational_answer = _direct_operational_answer(
                state["query"],
                facts,
            )
            direct_policy_answer = _direct_policy_answer(
                state["query"],
                facts,
            )
            direct_calendar_answer = _direct_calendar_answer(
                state["query"],
                facts,
            )
            timetable_fact = next(
                (fact for fact in facts if fact.id == "personal_timetable"),
                None,
            )
            if direct_operational_answer is not None:
                answer = direct_operational_answer
                used_llm = False
            elif direct_policy_answer is not None:
                answer = direct_policy_answer
                used_llm = False
            elif direct_calendar_answer is not None:
                answer = direct_calendar_answer
                used_llm = False
            elif timetable_fact is not None:
                answer = _timetable_answer(timetable_fact.content)
                used_llm = False
            elif not facts:
                answer = (
                    "当前知识库中没有检索到足够依据。"
                    "请提供更具体的制度名称，或以上传的正式文件为准。"
                )
                used_llm = False
            elif container.settings.llm_render_enabled and container.llm.configured:
                try:
                    answer = await container.llm.answer_question(
                        query=state["query"],
                        facts=facts,
                    )
                    answer = _plain_text_answer(answer)
                    used_llm = True
                except Exception:
                    answer = _facts_answer(facts, query=state["query"])
                    used_llm = False
            else:
                answer = _facts_answer(facts, query=state["query"])
                used_llm = False
            answer = _ensure_query_guardrails(
                answer,
                query=state["query"],
                facts=facts,
            )
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
            raw.get("severity") == IssueSeverity.ERROR.value for raw in warnings
        )
        if has_errors:
            draft, suggested_actions = _infeasible_answer(
                plan=plan,
                warnings=warnings,
                tasks=tasks,
                now=datetime.fromisoformat(state["now_iso"]),
                query=state.get("query", ""),
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
                tasks=tasks,
                facts=facts,
                weather=[
                    WeatherContext.model_validate(raw)
                    for raw in state.get("weather_context", [])
                ],
                congestion_windows=container.rules.congestion_windows(plan.date),
            )
            suggested_actions = _congestion_suggested_actions(
                plan,
                already_requested=bool(
                    state.get("preferences", {}).get("avoid_congestion")
                ),
            )

        answer = draft
        used_llm = False
        if container.settings.llm_plan_render_enabled and container.llm.configured:
            try:
                weather_context = state.get("weather_context", [])
                weather_is_relevant = state.get("intent") == "weather_check" or any(
                    raw.get("source") == "user" for raw in weather_context
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


def _clarification_answer(
    *,
    query: str,
    clarifications: list[str],
) -> str:
    details = "；".join(clarifications)
    if any(marker in query for marker in ("事情有点多", "事情很多", "有点忙")) and any(
        "具体任务" in item for item in clarifications
    ):
        return (
            "事情一多，很容易既惦记着这个、又担心漏掉那个。"
            "你不用一次把计划想得很完整，先把现在记得的事情告诉我就好。"
            "我还需要确认："
            f"{details}"
            "可以直接按“任务、最晚完成时间、预计时长、地点”逐条发给我；"
            "不确定的地方也可以留空，我会陪你一起补齐，再排成一份"
            "不会太赶的计划。"
        )
    return (
        "为了不替你做错决定，我还想确认一件事："
        + details
        + "你只要补充已确定的时间、地点或必须保留的安排，"
        "其余部分我会继续帮你梳理。"
    )


def _timetable_answer(summary: str) -> str:
    if "不执行常规课程" in summary:
        return (
            "我把个人课表和校历一起核对过了。\n\n"
            f"{summary}\n\n"
            "假期并不等于这一天不能规划。你可以告诉我想自习、运动、"
            "出行还是休息，我会照常结合开放时间、通勤和天气帮你安排。"
        )
    if "尚未录入学校具体补星期几课程" in summary:
        return (
            "我先把不确定的地方替你拦住了。\n\n"
            f"{summary}\n\n"
            "学校具体补课安排尚未从杭助同步到；在此之前，我不会擅自"
            "把某一天的课搬过来。同步后将以杭助中的实际课程为准。"
        )
    if "没有已启用的课程记录" in summary:
        return (
            "我帮你看过个人课表了。\n\n"
            f"{summary}\n\n"
            "这一天暂时没有课程占用，你可以直接告诉我想安排的"
            "学习、运动或生活任务，我会继续帮你把时间和通勤一起排好。"
        )
    calendar_note = ""
    calendar_match = re.search(r"(学校校历设置为.*?。)$", summary)
    if calendar_match:
        calendar_note = calendar_match.group(1)
        summary = summary[: calendar_match.start()].rstrip()
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
        *([calendar_note, ""] if calendar_note else []),
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
    tasks: list[Task] | None = None,
    facts: list[RetrievedFact],
    weather: list[WeatherContext],
    congestion_windows: list[tuple[datetime, datetime]],
) -> str:
    ordered_items = sorted(plan.items, key=lambda value: value.start_at)
    task_items = [item for item in ordered_items if item.item_type == "task"]
    task_titles = [item.title for item in task_items]
    task_names = "、".join(f"“{title}”" for title in task_titles)
    travel_items = [item for item in ordered_items if item.item_type == "travel"]
    opening_rules_available = not any(
        raw.get("code") == "CAMPUS_KNOWLEDGE_NOT_CONFIGURED" for raw in warnings
    )
    weather_adjustment = _has_precise_weather_risk(
        weather
    ) and _outdoor_tasks_finish_before_weather_risk(plan, weather)
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
        is_removal = any(
            marker in query
            for marker in (
                "取消",
                "删除",
                "去掉",
                "移除",
                "不去了",
                "不用安排",
                "不安排",
                "别安排",
            )
        )
        if is_removal:
            lines = [
                "你要取消的安排我已经移除了，"
                "其他事项仍尽量保持原来的时间，不会顺手把整天推翻。"
            ]
        else:
            lines = [
                "你刚刚强调的变化我记下了。"
                "这次只调整受影响的部分，能保留的安排我都替你留住了。"
            ]
        if task_names:
            lines.append(
                f"安排思路：围绕新的要求重新衔接{task_names}，"
                "没有变化的任务尽量留在原来的时间。"
            )
        else:
            lines.append(
                "这一天原有事项已经全部取消，当前没有需要继续执行的"
                "安排；如果只是想暂缓其中一项，也可以告诉我恢复哪一项。"
            )
    else:
        verified_parts = ["时间顺序"]
        if travel_items:
            verified_parts.append("路上耗时")
        if opening_rules_available:
            verified_parts.append("场所开放时段")
        lines = [
            "这几件事能排开。"
            f"我把{'、'.join(verified_parts)}一起核对过了，"
            "按这个节奏走，不需要卡着分钟一路赶。"
        ]
        if any("自习" in title or "学习" in title for title in task_titles):
            thought = (
                "安排思路：先留出一段完整、连续的学习时间，"
                "再按你说的先后顺序衔接其他事情，避免把专注时间切得"
                "太碎。"
            )
            if travel_items:
                thought += "跨地点之间的通勤时间也已经按你选择的出行方式单独留出。"
            lines.append(thought)
        else:
            lines.append(
                f"安排思路：把{task_names}按时间和地点顺序连起来，尽量减少来回折返。"
            )
    if "后天" in query:
        day_label = "后天"
    elif "明天" in query:
        day_label = "明天"
    elif "今天" in query:
        day_label = "今天"
    else:
        day_label = f"{plan.date.month}月{plan.date.day}日"
    lines.append(
        f"{day_label}可以这样安排："
        if ordered_items
        else f"{day_label}当前没有保留的安排。"
    )
    estimated_tasks = [
        task for task in (tasks or []) if "duration_estimated" in task.tags
    ]
    if estimated_tasks:
        estimates = "、".join(
            f"{task.title}暂按{task.duration_min}分钟"
            for task in estimated_tasks
        )
        lines.append(
            f"你没有说明时长的事项，我先用可调整默认值排入：{estimates}。"
            "直接告诉我实际需要多久，就会只重排受影响的部分。"
        )
    for item in ordered_items:
        label = item.title
        duration_min = int((item.end_at - item.start_at).total_seconds() // 60)
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
                "SCHOOL_CALENDAR_CONFIRMATION_REQUIRED",
            }
        )
    ]
    warning_messages.extend(
        Issue.model_validate(raw).message
        for raw in warnings
        if (
            raw.get("code") == "ROUTE_FALLBACK"
            and "电瓶车实时路线" in str(raw.get("message", ""))
        )
    )
    if warning_messages:
        lines.append("提醒：" + "；".join(dict.fromkeys(warning_messages)))
    elif weather_adjustment and opening_rules_available:
        lines.append(
            "时间、通勤、开放时段和天气风险都已经核对过，"
            "户外任务安排在已知风险时段之前。"
        )
    elif weather_adjustment:
        lines.append(
            "时间、通勤和天气风险已经核对过；这所学校的开放规则"
            "尚未导入，出发前请再确认场所是否开放。"
        )
    else:
        verified_summary = ["时间"]
        if travel_items:
            verified_summary.append("通勤")
        if opening_rules_available:
            verified_summary.append("开放时段")
        lines.append(f"{'、'.join(verified_summary)}已经核对过，可以按这份安排执行。")
    reminder_context = " ".join([query, *task_titles])
    reminders = _knowledge_reminders(facts, query=reminder_context)
    weather_reminder = _weather_reminder(weather, query=query)
    if weather_reminder:
        reminders.insert(0, weather_reminder)
        reminders = reminders[:3]
    elif any(word in query for word in ("天气", "下雨", "降雨", "有雨")) and any(
        raw.get("code") == "API_DEGRADED"
        and raw.get("details", {}).get("provider") == "weather"
        for raw in warnings
    ):
        reminders.insert(
            0,
            "目标日期暂时没有可靠的天气预报；临近当天再查一次会更"
            "准确，如果遇到降雨或高温，我可以只调整跑步等户外安排。",
        )
        reminders = reminders[:3]
    congestion_reminder = _congestion_reminder(
        ordered_items,
        congestion_windows,
    )
    if congestion_reminder:
        reminders.insert(0, congestion_reminder)
        reminders = reminders[:3]
    if reminders:
        count_label = {1: "一点", 2: "两点", 3: "三点"}.get(
            len(reminders),
            "几件事",
        )
        lines.append(f"再替你留意{count_label}：")
        lines.extend(f"• {item}" for item in reminders)
    if ordered_items:
        finish_line = f"整套安排预计在 {ordered_items[-1].end_at:%H:%M} 收尾"
        if plan.metrics.travel_minutes > 0:
            finish_line += f"，其中已经留出 {plan.metrics.travel_minutes} 分钟通勤"
        lines.append(finish_line + "。")
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


def _outdoor_tasks_finish_before_weather_risk(
    plan: Plan,
    weather: list[WeatherContext],
) -> bool:
    """Prove that a timed weather adjustment is reflected in the plan.

    A precise rain boundary alone does not prove that the planner moved an
    outdoor task. This guard prevents a normal demo (or a live plan that still
    crosses the boundary) from claiming that the risk was already avoided.
    """
    risk_times = [
        item.risk_start_at
        for item in weather
        if item.risk_start_at is not None
        and (
            "雨" in (item.condition or "")
            or "雪" in (item.condition or "")
            or "风" in (item.condition or "")
            or (item.rain_probability or 0) >= 0.5
        )
    ]
    if not risk_times:
        return False
    risk_start = min(risk_times)
    outdoor_items = [
        item
        for item in plan.items
        if item.item_type == "task"
        and (
            item.location_id in {"track", "east_track", "northwest_track"}
            or any(
                marker in item.title
                for marker in (
                    "跑步",
                    "长跑",
                    "操场",
                    "骑行",
                    "足球",
                    "篮球",
                    "排球",
                    "网球",
                    "户外",
                )
            )
        )
    ]
    return bool(outdoor_items) and all(
        item.end_at <= risk_start for item in outdoor_items
    )


def _weather_reminder(
    weather: list[WeatherContext],
    *,
    query: str = "",
) -> str | None:
    live_items = [item for item in weather if item.source.value in {"user", "live_api"}]
    if not live_items:
        return None

    def risk_score(item: WeatherContext) -> tuple[int, int, float]:
        condition = item.condition or ""
        severe = int(
            "雨" in condition
            or "雪" in condition
            or "风" in condition
            or (item.rain_probability or 0) >= 0.5
        )
        explicit_boundary = int(item.risk_start_at is not None)
        temperature = item.temperature_c or -100
        return severe, explicit_boundary, temperature

    live = max(
        live_items,
        key=risk_score,
    )
    condition = live.condition or ""
    has_rain = "雨" in condition or (live.rain_probability or 0) >= 0.5
    has_snow = "雪" in condition
    has_wind = "风" in condition
    if has_rain or has_snow or has_wind:
        if has_rain:
            care = "随身带把伞，雨后路面可能湿滑，步行或骑行都慢一点"
        elif has_snow:
            care = "注意保暖和路面湿滑，步行或骑行都慢一点"
        else:
            care = "尽量避开临时搭建物和树下，骑行时注意侧风"
        if live.risk_start_at:
            if live.source.value == "user":
                return (
                    f"你提醒 {live.risk_start_at:%H:%M} 后有雨，户外活动"
                    f"已经按这个时间边界处理；{care}，出发前再看一次"
                    "临近预报会更稳妥。"
                )
            return (
                f"{live.risk_start_at:%H:%M} 后有“{condition or '降雨'}”"
                f"风险，户外活动已按这个时间边界处理；{care}，"
                "出发前再看一次临近预报会更稳妥。"
            )
        period_label = {
            "day": "白天",
            "night": "夜间",
            "morning": "上午",
            "afternoon": "下午",
            "evening": "晚间",
        }.get(live.period, live.period)
        return (
            f"{period_label}天气信息显示“{condition}”，目前只能精确到"
            "日/夜时段；"
            f"{care}。户外活动出发前请再看一次临近预报，变化时"
            "我可以局部调整。"
        )
    if live.temperature_c is not None and live.temperature_c >= 32:
        if any(
            marker in query
            for marker in (
                "跑步",
                "运动",
                "打球",
                "足球",
                "篮球",
                "羽毛球",
                "骑行",
            )
        ):
            return (
                f"当前预报约 {live.temperature_c:g}℃，运动前记得补水，"
                "尽量避开最晒的时段。"
            )
        return (
            f"当前预报约 {live.temperature_c:g}℃，出门记得防晒和补水，"
            "尽量走阴凉处；室内外温差较大时也可以带件薄外套。"
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
                "保持课程、截止时间和任务时长不变，仅在有余地时优先避开集中通行时段。"
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
    query: str,
    limit: int = 3,
) -> list[str]:
    reminders: list[str] = []
    reminder_topics: set[str] = set()
    query_topics = _knowledge_topics(query)
    source_rank = {
        DataSource.USER: 5,
        DataSource.STRUCTURED: 4,
        DataSource.LIVE_API: 3,
        DataSource.RAG: 2,
    }
    ordered = sorted(
        enumerate(facts),
        key=lambda pair: (
            -source_rank.get(pair[1].source, 0),
            -pair[1].priority,
            pair[0],
        ),
    )
    for _, fact in ordered:
        fact_topic = _knowledge_topic(fact.content)
        if (
            fact.source == DataSource.RAG
            and query_topics
            and fact_topic
            and fact_topic not in query_topics
        ):
            continue
        excerpt = (
            " ".join(fact.content.split())
            if fact.source == DataSource.STRUCTURED
            else _knowledge_answer_excerpt(fact.content, query)
        )
        if not excerpt:
            continue
        if len(excerpt) > 180:
            excerpt = excerpt[:180].rstrip() + "…"
        if any(excerpt[:60] == existing[:60] for existing in reminders):
            continue
        topic = fact_topic or _knowledge_topic(excerpt)
        if topic and topic in reminder_topics:
            continue
        reminders.append(excerpt)
        if topic:
            reminder_topics.add(topic)
        if len(reminders) >= limit:
            break
    return reminders


def _knowledge_topic(content: str) -> str | None:
    topics = _knowledge_topics(content)
    return next(
        (
            topic
            for topic in (
                "sun_run",
                "library",
                "parcel",
                "dormitory",
                "hot_water",
                "clinic",
                "class",
                "congestion",
                "meal",
                "gym",
            )
            if topic in topics
        ),
        None,
    )


def _knowledge_topics(content: str) -> set[str]:
    result: set[str] = set()
    for topic, markers in (
        ("sun_run", ("阳光长跑", "田径场", "操场")),
        ("library", ("图书馆", "阅览室")),
        ("parcel", ("快递", "驿站")),
        ("dormitory", ("门禁", "公寓楼", "熄灯")),
        ("hot_water", ("热水",)),
        ("clinic", ("校医院", "就诊")),
        ("class", ("上课时间", "第1节", "课表")),
        ("congestion", ("拥堵", "集中通行")),
        ("meal", ("餐厅", "食堂", "用餐", "吃饭")),
        ("gym", ("体育馆", "羽毛球", "乒乓球", "综合馆")),
    ):
        if any(marker in content for marker in markers):
            result.add(topic)
    return result


def _infeasible_answer(
    *,
    plan: Plan,
    warnings: list[dict],
    tasks: list[Task],
    now: datetime,
    query: str,
    routes: list[TravelEstimate],
) -> tuple[str, list[dict]]:
    error_messages = [
        Issue.model_validate(raw).message
        for raw in warnings
        if raw.get("severity") == IssueSeverity.ERROR.value
    ]
    scheduled_ids = {
        item.task_id for item in plan.items if item.item_type == "task" and item.task_id
    }
    unscheduled = [task for task in tasks if task.id not in scheduled_ids]
    unscheduled_names = "、".join(f"“{task.title}”" for task in unscheduled)
    all_task_names = "、".join(f"“{task.title}”" for task in tasks)
    has_overall_deadline = bool(
        re.search(
            r"\d{1,2}(?:\s*[:：]\s*\d{1,2})?\s*点?\s*前"
            r"(?:(?:结束|完成|回来|搞定)(?:全部|所有|这些)?"
            r"(?:任务|事情|事项)?|(?=$|[，。；、]))",
            query,
        )
    )
    deadline_values = (
        [task.deadline for task in tasks if task.deadline is not None]
        if has_overall_deadline
        else []
    )
    deadline = min(deadline_values) if deadline_values else None
    starts = [task.earliest_start for task in tasks if task.earliest_start is not None]
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
    required_minutes = sum(task.duration_min for task in active_tasks) + route_minutes
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
    venue_errors = [
        Issue.model_validate(raw).message
        for raw in warnings
        if (
            raw.get("severity") == IssueSeverity.ERROR.value
            and raw.get("code") == "OUTSIDE_OPENING_HOURS"
        )
    ]
    hard_rule_notes = [
        task.notes
        for task in unscheduled
        if task.notes
        and any(marker in task.notes for marker in ("营业时间", "开放时间", "硬约束"))
    ]
    if venue_errors:
        if len(unscheduled) == 1 and not plan.items:
            task = unscheduled[0]
            requested_time = (
                f"{task.earliest_start:%H:%M}以后"
                if task.earliest_start
                else "你指定的时段"
            )
            lines = [
                f"这次不能按原时间直接安排{task.title}。"
                "我先把它保留为“待调整”，没有替你删掉。",
                f"你希望在{requested_time}处理这件事，"
                + "但"
                + "；".join(dict.fromkeys(hard_rule_notes or venue_errors))
                + "。",
            ]
            suggestions = _opening_time_suggestions(
                task=task,
                plan_date=plan.date,
                now=now,
            )
            if "快递" in task.title:
                lines.append(
                    "快递属于哪个站点由包裹决定，我不会擅自把顺丰改成"
                    "京东或菜鸟。更稳妥的做法是把取件提前到本快递点"
                    "营业时间内，或者顺延到下一次开放时段。"
                )
            else:
                lines.append(
                    "可以把任务移到该场所开放时段；如果日期不能改，"
                    "再由你决定是否更换场地，我不会替你强行改动。"
                )
            if suggestions:
                lines.append(
                    "我已经把可直接重排的时间方案放在下方，你确认后我再生成完整日程。"
                )
            return "\n".join(lines), suggestions

        lines = [
            "这一天仍然可以继续规划，但有一项不能按原地点直接排进去。"
            "我先替你拦住，免得到了门口才发现无法使用。",
            "我核对到：" + "；".join(dict.fromkeys(venue_errors)) + "。",
        ]
        if unscheduled_names:
            lines.append(
                f"{unscheduled_names}没有被删除，只是暂时标为“待调整”。"
                "可以换到已经确认开放、且适合这项活动的地点，"
                "也可以改到该场所开放的日期或时段；你选定后，"
                "我会只重排受影响的部分。"
            )
        if plan.items:
            completed_names = "、".join(
                item.title for item in plan.items if item.item_type == "task"
            )
            lines.append(
                f"{completed_names}等不受影响的安排已经保留在下方时间轴，"
                "不需要因为一个场所关闭就推翻整天。"
            )
        return "\n".join(lines), []

    lines = [
        f"你想把{all_task_names}都顾上，我明白。"
        "只是现在时间确实有点赶，我不想为了让日程看起来完整，"
        "就悄悄删掉任何一项。"
    ]
    if unscheduled_names:
        lines.append(
            f"{unscheduled_names}都还在清单里，我没有替你删掉；"
            + (
                "只是按现在的结束时间，还没有足够的空档把它们妥善放进去。"
                if deadline
                else "只是当前的通勤、开放时段或先后约束还没有同时满足。"
            )
        )
    else:
        lines.append("这些任务都已经记下，只是它们和当前结束时间撞在了一起。")

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
    if hard_rule_notes:
        lines.append(
            "需要特别说明的场所规则："
            + "；".join(dict.fromkeys(hard_rule_notes))
            + "。"
        )

    suggestions = _adjustment_suggestions(
        tasks=active_tasks,
        unscheduled=unscheduled,
        plan_date=plan.date,
        planning_start=planning_start,
        deadline=deadline,
        required_minutes=required_minutes,
        deficit=deficit,
    )
    study_task = next(
        (task for task in tasks if "自习" in task.title or "学习" in task.title),
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
                "选一个更符合你今天状态的方案，我再把完整日程排好；"
                "在你确认前，我不会擅自牺牲你明确要求的任务时长。"
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


def _opening_time_suggestions(
    *,
    task: Task,
    plan_date,
    now: datetime,
) -> list[dict]:
    """Offer a safe time change without silently changing the venue."""
    if not task.notes:
        return []
    match = re.search(
        r"(?:营业时间|开放时间)(?:为|：)?"
        r"(\d{1,2}):(\d{2})[—~-](\d{1,2}):(\d{2})",
        task.notes,
    )
    if not match:
        return []
    open_at = time(int(match.group(1)), int(match.group(2)))
    close_at = time(int(match.group(3)), int(match.group(4)))
    candidate_date = plan_date
    close_datetime = datetime.combine(candidate_date, close_at, now.tzinfo)
    if candidate_date == now.date() and now >= close_datetime:
        candidate_date += timedelta(days=1)
        close_datetime = datetime.combine(
            candidate_date,
            close_at,
            now.tzinfo,
        )
    start_datetime = close_datetime - timedelta(minutes=task.duration_min + 10)
    opening_datetime = datetime.combine(
        candidate_date,
        open_at,
        now.tzinfo,
    )
    start_datetime = max(start_datetime, opening_datetime)
    return [
        {
            "id": f"opening_{task.id}",
            "label": f"改到 {close_at:%H:%M} 前",
            "description": (
                f"保留“{task.title}”和原地点，改到"
                f"{candidate_date:%m月%d日} {start_datetime:%H:%M}开始，"
                f"在{close_at:%H:%M}前完成。"
            ),
            "query": (
                f"{candidate_date:%Y-%m-%d} {start_datetime:%H:%M}以后，"
                f"{task.title}{task.duration_min}分钟，"
                f"{close_at:%H:%M}前完成。"
            ),
        }
    ]


def _ordered_route_minutes(
    tasks: list[Task],
    routes: list[TravelEstimate],
) -> int:
    route_map = {
        (route.origin_id, route.destination_id): route.duration_min for route in routes
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
    unscheduled: list[Task],
    plan_date,
    planning_start: datetime,
    deadline: datetime | None,
    required_minutes: int,
    deficit: int,
) -> list[dict]:
    if not deadline or deficit <= 0:
        return []
    action_safety_min = 10
    adjustable = next(
        (task for task in tasks if "自习" in task.title or "学习" in task.title),
        max(tasks, key=lambda task: task.duration_min, default=None),
    )
    suggestions: list[dict] = []
    if adjustable:
        shortened = max(
            5,
            ((adjustable.duration_min - deficit - action_safety_min) // 5) * 5,
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
        planning_start + timedelta(minutes=required_minutes + action_safety_min)
    )
    suggestions.append(
        {
            "id": "option_2",
            "label": "保留完整安排",
            "description": (
                "不牺牲" + "、".join(task.title for task in tasks) + "的完整性，"
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
    movable_unscheduled = [
        task
        for task in unscheduled
        if "course" not in task.tags and "hard_constraint" not in task.tags
    ]
    if movable_unscheduled:
        next_date = plan_date + timedelta(days=1)
        next_start = datetime.combine(next_date, time(8, 0), planning_start.tzinfo)
        next_deadline = datetime.combine(
            next_date,
            time(22, 0),
            planning_start.tzinfo,
        )
        moved_names = "、".join(task.title for task in movable_unscheduled)
        suggestions.append(
            {
                "id": "option_3",
                "label": "改到下一天",
                "description": (
                    f"把暂时排不下的{moved_names}移到"
                    f"{next_date:%m月%d日}并直接生成时间；"
                    "今天能排下的部分保持当前预览。"
                ),
                "query": _standalone_query(
                    tasks=movable_unscheduled,
                    planning_start=next_start,
                    deadline=next_deadline,
                    duration_overrides={},
                ),
            }
        )
        omitted = min(
            movable_unscheduled,
            key=lambda task: (task.importance, -task.duration_min),
        )
        remaining = [task for task in tasks if task.id != omitted.id]
        if remaining:
            suggestions.append(
                {
                    "id": "option_4",
                    "label": f"这次不排{omitted.title}",
                    "description": (
                        f"本次先不安排{omitted.title}，其余任务按"
                        f"{deadline:%H:%M}前结束重新生成；不会静默删除。"
                    ),
                    "query": _standalone_query(
                        tasks=remaining,
                        planning_start=planning_start,
                        deadline=deadline,
                        duration_overrides={},
                    ),
                }
            )
    return suggestions[:4]


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
    return value if remainder == 0 else value + timedelta(minutes=5 - remainder)


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
            marker in task.notes for marker in ("营业时间", "开放时间")
        ):
            continue
        required_times = re.findall(r"\b\d{2}:\d{2}\b", task.notes)
        if any(value not in answer for value in required_times):
            return False

    has_peak_congestion = any(raw.get("code") == "PEAK_CONGESTION" for raw in warnings)
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
    campus_rules_missing = any(
        raw.get("code") == "CAMPUS_KNOWLEDGE_NOT_CONFIGURED" for raw in warnings
    )
    if campus_rules_missing and re.search(
        r"(?:开放时间|开放时段|场所开放)[^。；\n]{0,12}"
        r"(?:已|已经)?(?:核对|确认|留意|检查)",
        answer,
    ):
        return False
    has_travel = any(item.item_type == "travel" for item in plan.items)
    if not has_travel and re.search(r"(?:留出|预留)\s*0\s*分钟通勤", answer):
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
    cleaned = re.sub(r"(?m)^\s*[-*]\s+", "• ", cleaned)
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


def _facts_answer(
    facts: list[RetrievedFact],
    *,
    query: str,
) -> str:
    candidates = [
        (
            _knowledge_answer_excerpt(fact.content, query),
            fact,
        )
        for fact in facts
    ]
    candidates.sort(
        key=lambda item: (
            -_answer_relevance_score(item[0], query),
            -item[1].priority,
            item[1].id,
        )
    )
    primary_source = candidates[0][1].source_ref if candidates else ""
    selected: list[RetrievedFact] = []
    excerpts: list[str] = []
    wants_decisive_quantity = any(
        marker in query for marker in ("最长", "最多", "几年")
    )
    for excerpt, fact in candidates:
        if primary_source and fact.source_ref != primary_source:
            continue
        if not excerpt or excerpt in excerpts:
            continue
        if _answer_relevance_score(excerpt, query) <= 0 and selected:
            continue
        selected.append(fact)
        excerpts.append(excerpt)
        if wants_decisive_quantity and any(
            marker in excerpt for marker in ("不得超过", "最长", "至多", "累计")
        ):
            break
        if len(selected) >= 3:
            break
    if not selected:
        selected = [facts[0]]
        excerpts = [_knowledge_answer_excerpt(facts[0].content, query)]
    lines = [
        "我帮你从已核验的资料里找到了直接相关的依据：",
        "",
        *[f"• {excerpt}" for excerpt in excerpts],
    ]
    seen_sources: list[str] = []
    for fact in selected:
        source_label = _fact_source_label(fact)
        if source_label and source_label not in seen_sources:
            seen_sources.append(source_label)
    if seen_sources:
        lines.extend(["", "依据来源：" + "；".join(seen_sources)])
    lines.extend(
        [
            "",
            "如果你还想把这条规则用于具体某一天的安排，告诉我日期和"
            "要做的事情，我会继续把课程、开放时间和通勤一起核对。",
        ]
    )
    return "\n".join(lines)


def _fact_source_label(fact: RetrievedFact) -> str:
    source = fact.source_ref or ""
    if "gov.cn" in source:
        return f"国务院办公厅（{source}）"
    page = fact.metadata.get("page")
    title = str(fact.metadata.get("title") or "").strip()
    parts = [source] if source else []
    if isinstance(page, int):
        parts.append(f"第{page}页")
    if title:
        parts.append(title)
    return " · ".join(parts)


def _direct_calendar_answer(
    query: str,
    facts: list[RetrievedFact],
) -> str | None:
    """Return verified holiday dates without model-dependent omissions.

    Holiday ranges and adjusted workdays are exact calendar facts. A
    rendering model must not drop an adjusted workday or mix an unrelated
    retrieved section title into the official citation.
    """
    holiday_names = (
        "元旦",
        "春节",
        "清明节",
        "劳动节",
        "端午节",
        "中秋节",
        "国庆节",
    )
    holiday_name = next(
        (name for name in holiday_names if name in query),
        None,
    )
    if holiday_name is None or not any(
        marker in query for marker in ("放假", "调休", "假期")
    ):
        return None

    candidates: list[tuple[int, RetrievedFact, str]] = []
    for fact in facts:
        if holiday_name not in fact.content:
            continue
        excerpt = _knowledge_answer_excerpt(fact.content, query)
        if holiday_name not in excerpt:
            continue
        score = _answer_relevance_score(excerpt, query)
        if "gov.cn" in (fact.source_ref or ""):
            score += 1000
        candidates.append((score, fact, excerpt))
    if not candidates:
        return None

    _, fact, excerpt = max(candidates, key=lambda item: item[0])
    source_label = _fact_source_label(fact)
    lines = [excerpt]
    if source_label:
        lines.extend(["", f"依据来源：{source_label}"])
    return "\n".join(lines)


def _direct_policy_answer(
    query: str,
    facts: list[RetrievedFact],
) -> str | None:
    """Keep verified handbook rules exact instead of model-paraphrased.

    Student-status rules, deadlines and eligibility conditions are
    high-stakes factual answers.  Once the retriever has found the verified
    handbook passage, a rendering model is not allowed to alter its number,
    exception or source label.
    """
    policy_topics = (
        "学生手册",
        "学籍",
        "处分",
        "申诉",
        "请假",
        "休学",
        "复学",
        "转专业",
        "注册",
        "旷课",
        "迟到",
        "早退",
        "奖学金",
        "助学金",
        "修业",
        "退学",
        "毕业",
        "学位",
        "补考",
        "缓考",
        "重修",
        "考试",
        "考核",
        "成绩单",
        "退学警示",
        "试读",
        "结业",
        "肄业",
        "毕业证",
        "学历证书",
        "学位证书",
    )
    if not any(topic in query for topic in policy_topics):
        return None
    handbook_facts = [
        fact
        for fact in facts
        if (
            "学生手册" in fact.source_ref
            or "学生手册" in str(fact.metadata.get("title") or "")
        )
    ]
    if not handbook_facts:
        return None
    return _facts_answer(handbook_facts, query=query)


def _direct_operational_answer(
    query: str,
    facts: list[RetrievedFact],
) -> str | None:
    """Answer strict campus operating-time questions deterministically.

    These facts are hard constraints in planning.  Letting a rendering model
    paraphrase a partially retrieved excerpt can silently drop the exact
    floor or time window, so direct questions use the verified structured
    rule whenever it is present.
    """
    by_id = {fact.id: fact for fact in facts}
    if "图书馆" in query:
        fact = by_id.get("library_floor_hours")
        upper_floor_requested = any(
            marker in query
            for marker in (
                "七层",
                "七楼",
                "八层",
                "八楼",
                "九层",
                "九楼",
                "十层",
                "十楼",
                "十一层",
                "十一楼",
                "7层",
                "7楼",
                "8层",
                "8楼",
                "9层",
                "9楼",
                "10层",
                "10楼",
                "11层",
                "11楼",
            )
        )
        lower_floor_requested = any(
            marker in query
            for marker in (
                "六层",
                "六楼",
                "十二层",
                "十二楼",
                "6层",
                "6楼",
                "12层",
                "12楼",
            )
        )
        if fact is not None and upper_floor_requested:
            return (
                "图书馆七至十一层每天 8:00—21:30 开放"
                "（法定节假日除外），所以七楼晚上 21:30 关闭。"
                "如果临近闭馆去自习，建议把收拾和离馆时间也预留出来；"
                "21:30 以后可改选仍开放到 22:30 的六层或十二层。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
        if fact is not None and lower_floor_requested:
            return (
                "图书馆六层和十二层每天 7:00—22:30 开放"
                "（法定节假日除外）。如果是晚间自习，建议至少提前"
                "十分钟收拾离馆，别把闭馆时间当作最后离开时间。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
        if fact is not None:
            return (
                "图书馆法定节假日外每天开放，但楼层时间不同：六层、"
                "十二层为 7:00—22:30，七至十一层为 8:00—21:30。"
                "如果要排晚间自习，告诉我具体楼层，我会按对应闭馆"
                "时间留出收拾和离馆余量。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
    if "阳光长跑" in query:
        fact = by_id.get("sun_run_locations")
        if fact is not None:
            return (
                "阳光长跑可计入时段是：体育馆副馆南侧塑胶跑道和"
                "东操场 7:00—21:00，西北田径场 18:30—21:00。"
                "这里说的是“可计入成绩的时段”，不等同于场地全天"
                "开放时间；实际跑步还要结合课程、天气和往返通勤。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
    if "校医院" in query or any(
        marker in query for marker in ("医务室", "就诊", "看病")
    ):
        fact = by_id.get("campus_hospital_hours")
        if fact is not None:
            return (
                "校医院工作日 8:00—20:00 就诊；双休日和节假日分为"
                " 8:00—11:30、13:30—16:00 两个时段，中午不接诊。"
                "如果身体明显不舒服，先以就医为主，不必为了原计划"
                "硬撑；需要的话我也可以帮你把当天其他安排顺延。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
    if any(marker in query for marker in ("快递", "驿站", "顺丰", "京东", "菜鸟")):
        fact = by_id.get("express_service_hours")
        if fact is not None:
            if "顺丰" in query:
                detail = "顺丰快递点 8:00—18:00 开放"
            elif "京东" in query:
                detail = "京东快递点 8:00—22:00 开放"
            elif "菜鸟" in query or "驿站" in query:
                detail = "菜鸟驿站 8:30—22:30 开放"
            else:
                detail = "顺丰 8:00—18:00、京东 8:00—22:00、菜鸟驿站 8:30—22:30 开放"
            return (
                f"{detail}。不同快递点闭门时间差异很大，安排取件时"
                "最好说清具体站点，我会把通勤和截止时间一起算进去。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
    if not any(marker in query for marker in ("热水", "供水")) and any(
        marker in query for marker in ("宿舍", "寝室", "公寓", "门禁", "熄灯")
    ):
        fact = by_id.get("dormitory_access_and_lights")
        if fact is not None:
            return (
                "宿舍周日至周四 6:20—23:00 开门，22:50 自主熄灯、"
                "23:00 统一熄灯；周五、周六及节假日 "
                "6:20—24:00 开门，23:50 自主熄灯、24:00 统一"
                "熄灯。晚间安排还要把回宿舍的通勤时间留在门禁之前。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
    if any(marker in query for marker in ("体育馆", "综合馆", "羽毛球", "乒乓球")):
        fact = by_id.get("summer_indoor_sports_hours")
        if fact is not None:
            return (
                "现有已核验的暑期规则记录：7月1日至9月4日，体育馆"
                "主馆二楼乒乓球房和综合馆羽毛球馆仅工作日 "
                "11:30—20:30 开放，周末不开放，并需按要求预约。"
                "室外场地另有开放规则，不能把两者混在一起判断。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
    if any(keyword in query for keyword in ("热水", "供水")):
        fact = by_id.get("hot_water_hours")
        if fact is not None:
            return (
                "宿舍热水每天有两个供应时段：6:00—8:00、"
                "16:30—24:00。晚上从 16:30 开始供应，到 24:00 "
                "结束；如果当天安排较晚，最好在门禁和就寝时间前留出"
                "洗漱余量。\n\n"
                f"依据来源：{fact.source_ref or '杭电时间知识库'}"
            )
    return None


def _answer_relevance_score(content: str, query: str) -> int:
    query_text = "".join(char for char in query if "\u4e00" <= char <= "\u9fff")
    terms = {
        query_text[index : index + width]
        for width in (2, 3, 4)
        for index in range(max(0, len(query_text) - width + 1))
    }
    terms -= {
        "什么",
        "多少",
        "怎么",
        "可以",
        "是否",
        "需要",
        "告诉",
        "一下",
        "是多少",
    }
    score = sum(len(term) ** 2 for term in terms if term in content)
    if any(marker in query for marker in ("最长", "最多", "几年")):
        decisive_topics = (
            "请假",
            "休学",
            "申诉",
            "修业年限",
            "转专业",
            "注册",
            "旷课",
        )
        requested_topics = {topic for topic in decisive_topics if topic in query}
        same_topic = not requested_topics or any(
            topic in content for topic in requested_topics
        )
        if same_topic:
            if any(
                marker in content for marker in ("不得超过", "最长", "至多", "累计")
            ):
                score += 500
            quantities = re.findall(
                r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十百两]+)"
                r"\s*(?:日|天|周|个月|年|学期|小时|分钟)",
                content,
            )
            score += 30 * len(set(quantities))
    return score


def _ensure_query_guardrails(
    answer: str,
    *,
    query: str,
    facts: list[RetrievedFact],
) -> str:
    """Keep mandatory campus caveats stable across model variations."""
    evidence = "\n".join(fact.content for fact in facts)
    additions: list[str] = []
    if (
        "图书馆" in query
        and any(marker in evidence for marker in ("六层", "十二层"))
        and any(marker in evidence for marker in ("七，八，九", "七至十一层"))
        and "不同楼层" not in answer
    ):
        additions.append(
            "还要留意：不同楼层开放时间不同，晚间前往时请按具体楼层的闭馆时间安排。"
        )
    holiday_names = (
        "元旦",
        "春节",
        "清明节",
        "劳动节",
        "端午节",
        "中秋节",
        "国庆节",
        "法定节假日",
    )
    if (
        any(name in query for name in holiday_names)
        and any(marker in evidence for marker in ("放假", "调休", "国务院办公厅"))
        and not any(marker in answer for marker in ("学校校历", "教务通知"))
    ):
        additions.append(
            "国家放假安排不等于学校课程安排；是否停课、补课仍要以"
            "学校校历和教务通知为准。"
        )
    if not additions:
        return answer
    return "\n\n".join([answer.rstrip(), *additions])


def _knowledge_answer_excerpt(content: str, query: str) -> str:
    if (
        "申诉" in query
        and any(marker in query for marker in ("省级", "教育部门"))
        and any(marker in query for marker in ("收到", "处理", "多久"))
    ):
        compact_provincial_content = re.sub(r"\s+", "", content)
        provincial_processing_match = re.search(
            r"(省级教育行政部门应当在接到学生书面申诉之日起"
            r"30个工作日内，对申诉人的问题给予处理并作出决定。)",
            compact_provincial_content,
        )
        if provincial_processing_match:
            return provincial_processing_match.group(1)
    if "申诉" in query and any(
        marker in query for marker in ("没告诉", "未告知", "没有告知")
    ):
        compact_uninformed_content = re.sub(r"\s+", "", content)
        uninformed_deadline_match = re.search(
            r"(处理、处分或者复查决定书未告知学生申诉期限的，"
            r"申诉期限自学生知道或者应当知道处理或者处分决定之日"
            r"起计算，但最长不得超过6个月。)",
            compact_uninformed_content,
        )
        if uninformed_deadline_match:
            return uninformed_deadline_match.group(1)
    if "退学警示" in query and any(
        marker in query for marker in ("什么情况", "哪些情况", "条件", "会收到")
    ):
        compact_warning_content = re.sub(r"\s+", "", content)
        warning_match = re.search(
            r"(第三十九条退学警示。学生一学期.*?"
            r"小于14学分，且.*?小于18学分。)",
            compact_warning_content,
        )
        if warning_match:
            return warning_match.group(1)
    if "试读" in query and any(
        marker in query for marker in ("多久", "什么时候", "何时", "期限")
    ):
        compact_trial_content = re.sub(r"\s+", "", content)
        trial_match = re.search(
            r"(第四十二条因第四十一条第（一）款原因达到退学条件"
            r"的学生，可申请试读。试读期为一学期。"
            r"申请试读应在每学期开学后六周内办理)",
            compact_trial_content,
        )
        if trial_match:
            return trial_match.group(1) + "。"
    if "图书馆" in query:
        compact_library_content = re.sub(r"\s+", "", content)
        upper_floor_requested = any(
            marker in query
            for marker in (
                "七层",
                "八层",
                "九层",
                "十层",
                "十一层",
                "7层",
                "8层",
                "9层",
                "10层",
                "11层",
            )
        )
        lower_floor_requested = any(
            marker in query for marker in ("六层", "十二层", "6层", "12层")
        )
        if upper_floor_requested:
            floor_match = re.search(
                r"(?:七至十一层|七，八，九，十，十一层)"
                r"[:：]?(?:周一至周日)?"
                r"(\d{1,2}:\d{2})[—~-](\d{1,2}:\d{2})",
                compact_library_content,
            )
            if floor_match:
                return (
                    "图书馆七至十一层开放时间为"
                    f"{floor_match.group(1)}—{floor_match.group(2)}。"
                )
        if lower_floor_requested:
            floor_match = re.search(
                r"(?:六层、十二层|十二层，六层)"
                r"[:：]?(?:周一至周日)?"
                r"(\d{1,2}:\d{2})[—~-](\d{1,2}:\d{2})",
                compact_library_content,
            )
            if floor_match:
                return (
                    "图书馆六层、十二层开放时间为"
                    f"{floor_match.group(1)}—{floor_match.group(2)}。"
                )
    if (
        "申诉" in query
        and any(marker in query for marker in ("浙江省教育厅", "省级"))
        and any(marker in query for marker in ("多久", "多少天", "期限", "什么时候"))
    ):
        compact_appeal_content = re.sub(r"\s+", "", content)
        provincial_appeal_match = re.search(
            r"((?:学生对复查决定有异议的，)?"
            r"在接到学校(?:复查|申诉处理)决定书之日起15日内，"
            r"可以向(?:学校所在地省级教育行政部门|浙江省教育厅)"
            r"提出书面申诉。)",
            compact_appeal_content,
        )
        if provincial_appeal_match:
            return provincial_appeal_match.group(1)
    if (
        "申诉" in query
        and "学校" in query
        and any(marker in query for marker in ("处理决定", "复查结论", "作出决定"))
        and any(marker in query for marker in ("多久", "多少天", "期限", "什么时候"))
    ):
        compact_appeal_content = re.sub(r"\s+", "", content)
        school_appeal_match = re.search(
            r"((?:学生申诉处理委员会.*?|申诉委员会.*?)?"
            r"(?:在|自)接到(?:书面申诉|申诉申请书)(?:之日起|后的)"
            r"15日内(?:作出复查结论并告知申诉人|"
            r"产生对申诉的处理决定，并送达申诉人)。?)",
            compact_appeal_content,
        )
        if school_appeal_match:
            return school_appeal_match.group(1)
    if (
        "申诉" in query
        and any(marker in query for marker in ("处分", "处理"))
        and any(marker in query for marker in ("期限", "多少天", "多久"))
        and not any(marker in query for marker in ("教育厅", "省级"))
    ):
        compact_appeal_content = re.sub(r"\s+", "", content)
        appeal_match = re.search(
            r"(学生对学校的处理或者处分决定有异议的.*?"
            r"10\s*日内.*?提出书面申诉。)",
            compact_appeal_content,
        )
        if appeal_match:
            return appeal_match.group(1)
    if (
        "注册" in query
        and "旷课" in query
        and any(marker in query for marker in ("几节", "多少节", "每天"))
    ):
        compact_registration_content = re.sub(r"\s+", "", content)
        registration_match = re.search(
            r"(因故不能按期注册者.*?"
            r"否则以旷课论处（每天按6节课计）[。；]?)",
            compact_registration_content,
        )
        if registration_match:
            return registration_match.group(1)
    if "请假" in query and any(marker in query for marker in ("最长", "多久")):
        compact_leave_content = re.sub(r"\s+", "", content)
        leave_match = re.search(
            r"(最长请假时间不能超过四周。?)",
            compact_leave_content,
        )
        if leave_match:
            return leave_match.group(1)
    if "休学" in query and any(
        marker in query for marker in ("最长", "最多", "多久", "期限", "几年")
    ):
        compact_suspension_content = re.sub(r"\s+", "", content)
        suspension_match = re.search(
            r"(休学时间一般以一学期或者一学年为单位，"
            r"但累计不得超过两年(?:\(创业休学的除外\))?。?)",
            compact_suspension_content,
        )
        if suspension_match:
            return suspension_match.group(1)
    for holiday_name in (
        "元旦",
        "春节",
        "清明节",
        "劳动节",
        "端午节",
        "中秋节",
        "国庆节",
    ):
        if holiday_name not in query:
            continue
        holiday_match = re.search(
            rf"(?:^|\n)[-*]\s*({holiday_name}：.*?)(?=\n[-*]\s|\n##|\Z)",
            content,
            flags=re.DOTALL,
        )
        if holiday_match:
            compact = " ".join(holiday_match.group(1).split())
            return re.sub(r"([，。；：])\s+", r"\1", compact)
    content = re.sub(r"\n[ \t]{2,}", " ", content)
    # PDF text extraction often inserts a hard line break in the middle of a
    # sentence. Join those visual line wraps before ranking answer units.
    content = re.sub(r"(?<![。！？；：])\n(?=[^\n#])", "", content)
    units = [
        re.sub(r"^#+\s*|^[-*]\s*", "", item.strip())
        for item in re.split(r"\n+|(?<=[。！？；])", content)
        if item.strip() and not re.match(r"^#{1,6}\s*", item.strip())
    ]
    known_terms = (
        "元旦",
        "春节",
        "清明节",
        "劳动节",
        "端午节",
        "中秋节",
        "国庆节",
        "放假",
        "调休",
        "上课",
        "补课",
        "门禁",
        "图书馆",
        "快递",
        "处分",
        "作弊",
        "奖学金",
        "请假",
    )
    query_terms = {term for term in known_terms if term in query}
    for chinese_run in re.findall(r"[\u4e00-\u9fff]+", query):
        for width in (2, 3):
            query_terms.update(
                chinese_run[index : index + width]
                for index in range(len(chinese_run) - width + 1)
                if chinese_run[index : index + width]
                not in {"什么", "时候", "怎么", "可以", "是否", "需要"}
            )

    def score(unit: str) -> tuple[int, int]:
        exact = sum(len(term) ** 2 for term in query_terms if term in unit)
        digit_bonus = sum(4 for value in re.findall(r"\d{1,4}", query) if value in unit)
        quantity_bonus = (
            30
            if any(marker in query for marker in ("多少", "几天", "多久"))
            and re.search(
                r"(?:\d+(?:\.\d+)?\s*"
                r"(?:日|天|学时|小时|分钟|周|个月|%))"
                r"|(?:[一二三四五六七八九十百两]+"
                r"(?:日|天|学时|小时|分钟|周|个月|年|学期))"
                r"|(?:[一二三四五六七八九十]+分之"
                r"[一二三四五六七八九十]+)",
                unit,
            )
            else 0
        )
        expected_unit_bonus = 0
        expected_quantity_patterns = (
            (
                ("几节", "多少节", "节课"),
                r"(?:节课|学时)",
            ),
            (
                ("几个学期", "多少个学期"),
                r"学期",
            ),
            (
                ("几年", "多少年"),
                r"(?:年|修业年限)",
            ),
            (
                ("几天", "多少天"),
                r"(?:日|天|工作日)",
            ),
        )
        for query_markers, unit_pattern in expected_quantity_patterns:
            if any(marker in query for marker in query_markers) and re.search(
                unit_pattern, unit
            ):
                expected_unit_bonus += 80
        return (
            exact + digit_bonus + quantity_bonus + expected_unit_bonus,
            -len(unit),
        )

    ranked = sorted(units, key=score, reverse=True)
    selected: list[str] = []
    for unit in ranked:
        if score(unit)[0] <= 0:
            continue
        if any(unit[:50] == existing[:50] for existing in selected):
            continue
        selected.append(unit)
        if len(selected) >= 2 or sum(map(len, selected)) >= 360:
            break
    if not selected and units:
        selected = [units[0]]
    excerpt = " ".join(selected)
    return excerpt if len(excerpt) <= 420 else excerpt[:420].rstrip() + "…"
