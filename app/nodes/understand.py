from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from app.container import AppContainer
from app.errors import AppError
from app.nodes.common import append_trace
from app.schemas.calendar import CalendarOverrideCreate
from app.schemas.common import TaskFlexibility
from app.schemas.memory import MemoryCreate, MemoryItem
from app.schemas.plan import Plan
from app.schemas.task import Task, UserPreferences
from app.schemas.timetable import CourseSessionCreate
from app.schemas.understand import UnderstandResult
from app.services.plan_editor import apply_plan_edit
from app.state import CampusAgentState


def make_understand_node(container: AppContainer):
    async def understand(state: CampusAgentState) -> dict:
        memories = _merge_client_memories(
            stored=container.memories.list(
                state["user_id"],
                enabled_only=True,
            ),
            client_items=state.get("client_memories", []),
            user_id=state["user_id"],
            now=datetime.fromisoformat(state["now_iso"]),
        )
        old_plan = (
            Plan.model_validate(state["old_plan"])
            if state.get("old_plan")
            else (
                container.plans.get(state["old_plan_id"])
                if state.get("old_plan_id")
                else None
            )
        )
        warnings = list(state.get("provider_warnings", []))
        rule_result = container.parser.parse(
            query=state["query"],
            now=datetime.fromisoformat(state["now_iso"]),
            old_plan=old_plan,
        )
        # Policy/handbook questions are grounded by the scoped knowledge
        # repository.  They do not need the requirement-extraction model and
        # must not fail merely because a test double only implements answer
        # rendering.  Planning and replanning remain model-required online.
        use_llm = (
            container.llm.configured
            and state.get("mode") != "offline"
            and rule_result.intent.value != "query"
        )
        # Changing an existing day is a conversation, so the model reads it —
        # with the plan and the recent turns in hand. It answers with the
        # change rather than a new day: asked to re-emit the whole plan it
        # drops the arrangements the student did not happen to mention.
        if use_llm and old_plan is not None:
            try:
                edit = await container.llm.parse_plan_edit(
                    query=state["query"],
                    now_iso=state["now_iso"],
                    plan_summary=_describe_plan(old_plan),
                    history=[
                        {
                            "role": str(turn.get("role", "user")),
                            "content": str(turn.get("content", "")),
                        }
                        for turn in state.get("conversation_history", [])
                    ],
                )
                edited, unresolved = apply_plan_edit(
                    tasks=rule_result.tasks,
                    edit=edit,
                    timezone=container.parser.timezone,
                )
                result = rule_result.model_copy(
                    update={
                        "tasks": edited,
                        "clarifications": list(
                            dict.fromkeys([*edit.clarifications, *unresolved])
                        ),
                    }
                )
                parser_name = "llm_plan_edit"
            except Exception as exc:
                raise _required_llm_error(exc) from exc
        elif use_llm:
            try:
                llm_result = await container.llm.parse_requirement(
                    query=state["query"],
                    now_iso=state["now_iso"],
                    history=[
                        {
                            "role": str(turn.get("role", "user")),
                            "content": str(turn.get("content", "")),
                        }
                        for turn in state.get("conversation_history", [])
                    ],
                    memory_context=[
                        {
                            "category": memory.category,
                            "label": memory.label,
                            "key": memory.key,
                            "value": memory.value,
                        }
                        for memory in memories
                    ]
                    + container.external_data.planning_context(state["user_id"]),
                )
                result = _merge_llm_with_rule_constraints(
                    query=state["query"],
                    llm_result=llm_result,
                    rule_result=rule_result,
                )
                if llm_result.clarifications and _can_apply_rule_guard(
                    query=state["query"],
                    llm_result=llm_result,
                    rule_result=rule_result,
                ):
                    result = result.model_copy(
                        update={
                            "clarifications": list(rule_result.clarifications),
                        }
                    )
                parser_name = "llm_with_rule_constraints"
            except Exception as exc:
                raise _required_llm_error(exc) from exc
        else:
            result = rule_result
            parser_name = "deterministic_rules"

        result = _apply_explicit_date_guard(
            query=state["query"],
            result=result,
            rule_result=rule_result,
        )
        # Both readings converge here, so “三次自习” becomes three real tasks
        # whichever path recognised the count.
        result = result.model_copy(
            update={
                "tasks": _split_long_study_blocks(
                    _expand_occurrences(result.tasks)
                )
            }
        )

        planning_now = datetime.fromisoformat(state["now_iso"])
        result, rollover_notice = _roll_over_exhausted_day(
            result=result,
            now=planning_now,
            old_plan=old_plan,
        )

        initial_location_raw = (
            container.parser.journey_origin_from_query(state["query"])
            if result.intent.value == "plan"
            else None
        )
        if initial_location_raw:
            result = result.model_copy(
                update={
                    "tasks": _drop_journey_origin_marker_tasks(
                        result.tasks,
                        initial_location_raw,
                        protected_task_ids={task.id for task in rule_result.tasks},
                    )
                }
            )
        initial_departure_at = (
            container.parser.journey_start_from_query(
                state["query"],
                result.requested_date,
            )
            if result.intent.value == "plan"
            else None
        )
        if initial_departure_at is not None:
            normalized_tasks = [
                _release_destination_from_departure_anchor(
                    task,
                    initial_departure_at,
                )
                for task in result.tasks
            ]
            result = result.model_copy(
                update={
                    "tasks": [
                        task.model_copy(
                            update={
                                "earliest_start": max(
                                    filter(
                                        None,
                                        (
                                            task.earliest_start,
                                            initial_departure_at,
                                        ),
                                    )
                                )
                            }
                        )
                        if task.flexibility == TaskFlexibility.MOVABLE
                        else task
                        for task in normalized_tasks
                    ]
                }
            )

        calendar_context = container.academic_calendar.resolve(
            user_id=state["user_id"],
            target_date=result.requested_date,
            client_overrides=[
                CalendarOverrideCreate.model_validate(raw)
                for raw in state.get("client_calendar_overrides", [])
            ],
        )
        timetable_tasks = container.timetables.tasks_for_date(
            user_id=state["user_id"],
            target_date=result.requested_date,
            class_periods=container.parser.class_periods,
            timezone_name=container.settings.app_timezone,
            effective_weekday=calendar_context.effective_weekday,
        )
        client_timetable_tasks = _client_timetable_tasks(
            raw=state.get("client_timetable"),
            target_date=result.requested_date,
            class_periods=container.parser.class_periods,
            timezone=container.parser.timezone,
            effective_weekday=calendar_context.effective_weekday,
        )
        if client_timetable_tasks:
            timetable_tasks = client_timetable_tasks
        elif hduhelp_tasks := container.external_data.timetable_tasks_for_date(
            user_id=state["user_id"],
            target_date=result.requested_date,
            class_periods=container.parser.class_periods,
            timezone_name=container.settings.app_timezone,
            effective_weekday=calendar_context.effective_weekday,
        ):
            timetable_tasks = hduhelp_tasks
        elif (
            container.external_data.get(state["user_id"], "timetable_terms") is not None
        ):
            # An all-term HDUHelp snapshot is authoritative even when the day
            # contains no class. Do not fall back to a stale legacy timetable.
            timetable_tasks = []
        external_agenda_tasks = container.external_agenda.tasks_for_date(
            state["user_id"],
            result.requested_date,
        )
        fixed_schedule_tasks = [*timetable_tasks, *external_agenda_tasks]
        timetable_summary = (
            _timetable_summary(
                result.requested_date,
                fixed_schedule_tasks,
                calendar_context=calendar_context,
            )
            if _is_timetable_query(state["query"])
            else None
        )
        if (
            old_plan is None
            and result.intent.value != "query"
            and not _explicit_no_class_exception(state["query"])
        ):
            planning_now = datetime.fromisoformat(state["now_iso"])
            active_timetable_tasks = [
                task
                for task in fixed_schedule_tasks
                if not (
                    result.requested_date == planning_now.date()
                    and task.fixed_end is not None
                    and task.fixed_end <= planning_now
                )
            ]
            result = result.model_copy(
                update={
                    "tasks": _apply_timetable_relative_constraints(
                        query=state["query"],
                        timetable_tasks=active_timetable_tasks,
                        tasks=_merge_timetable_tasks(
                            result.tasks,
                            active_timetable_tasks,
                        ),
                    ),
                }
            )
        preferences = _apply_memory_preferences(
            result.preferences,
            memories,
        )
        tasks_with_study_preferences = _apply_study_memory_period(
            result.tasks,
            memories=memories,
        )
        tasks_with_activity_locations = _apply_activity_location_memories(
            tasks_with_study_preferences,
            memories=memories,
            query=state["query"],
        )
        result = result.model_copy(
            update={
                "tasks": _apply_preferred_locations(
                    tasks_with_activity_locations,
                    preferences=preferences,
                    query=state["query"],
                )
            }
        )
        explicit_mode = container.parser.transport_mode_from_query(state["query"])
        explicit_avoid_congestion = container.parser.avoid_congestion_from_query(
            state["query"]
        )
        if (
            explicit_mode.value != "walk"
            or explicit_avoid_congestion
            or any(keyword in state["query"] for keyword in ("步行", "走路", "走过去"))
        ):
            preferences = preferences.model_copy(
                update={
                    "transport_mode": explicit_mode,
                    "avoid_congestion": explicit_avoid_congestion,
                }
            )
        return {
            "intent": result.intent.value,
            "requested_date": result.requested_date.isoformat(),
            "tasks": [task.model_dump(mode="json") for task in result.tasks],
            "preferences": preferences.model_dump(mode="json"),
            "user_memories": [memory.model_dump(mode="json") for memory in memories],
            "timetable_summary": timetable_summary,
            "academic_day_context": calendar_context.model_dump(mode="json"),
            "initial_location_raw": initial_location_raw,
            "initial_departure_at": (
                initial_departure_at.isoformat() if initial_departure_at else None
            ),
            "clarifications": result.clarifications,
            "parse_confidence": result.confidence,
            "rollover_notice": rollover_notice,
            "provider_warnings": warnings,
            "status": (
                "needs_clarification" if result.clarifications else "understood"
            ),
            "node_trace": append_trace(
                state,
                "understand",
                {
                    "parser": parser_name,
                    "intent": result.intent.value,
                    "task_count": len(result.tasks),
                    "memory_count": len(memories),
                    "timetable_task_count": len(fixed_schedule_tasks),
                    "academic_day": calendar_context.course_action,
                    "clarification_count": len(result.clarifications),
                    "rolled_to_next_day": rollover_notice is not None,
                },
            ),
        }

    return understand


def _roll_over_exhausted_day(
    *,
    result: UnderstandResult,
    now: datetime,
    old_plan: Plan | None,
) -> tuple[UnderstandResult, str | None]:
    """Move a new full-day workload to tomorrow instead of crushing it at night.

    This deliberately does not move edits, isolated tasks, or anything with an
    exact time/deadline.  It only applies when a multi-task day can no longer
    preserve the user's requested/default durations in today's usable time.
    """

    if (
        old_plan is not None
        or result.intent.value != "plan"
        or result.requested_date != now.date()
        or len(result.tasks) < 3
        or result.clarifications
    ):
        return result, None
    if any(
        task.fixed_start is not None
        or task.fixed_end is not None
        or task.deadline is not None
        for task in result.tasks
    ):
        return result, None

    day_end = datetime.combine(now.date() + timedelta(days=1), time.min, now.tzinfo)
    remaining_minutes = max(0, int((day_end - now).total_seconds() // 60))
    # Default meals are flexible ranges in the scheduler. Capacity only needs
    # to reserve the actual 30-minute break in each range that has not passed,
    # not the entire availability range.
    meal_minutes = sum(
        min(
            30,
            _remaining_overlap_minutes(
                now,
                day_end,
                datetime.combine(now.date(), start, now.tzinfo),
                datetime.combine(now.date(), end, now.tzinfo),
            ),
        )
        for start, end in (
            (time(11, 30), time(13, 30)),
            (time(17, 30), time(19, 30)),
        )
    )
    ideal_minutes = sum(task.duration_min for task in result.tasks)
    ideal_minutes += result.preferences.buffer_min * max(0, len(result.tasks) - 1)
    usable_minutes = max(0, remaining_minutes - meal_minutes)
    if ideal_minutes <= usable_minutes:
        return result, None

    target_date = now.date() + timedelta(days=1)
    shifted_tasks = [
        _shift_task_to_date(task, result.requested_date, target_date).model_copy(
            update={"tags": [*task.tags, "rolled_to_next_day"]}
        )
        for task in result.tasks
    ]
    shifted = result.model_copy(
        update={"requested_date": target_date, "tasks": shifted_tasks}
    )
    return (
        shifted,
        "今天剩余时间不足以完整容纳这些安排，我没有把任务压缩后硬塞到深夜，已按完整时长转到明天。",
    )


def _remaining_overlap_minutes(
    range_start: datetime,
    range_end: datetime,
    window_start: datetime,
    window_end: datetime,
) -> int:
    overlap_start = max(range_start, window_start)
    overlap_end = min(range_end, window_end)
    return max(0, int((overlap_end - overlap_start).total_seconds() // 60))


def _required_llm_error(exc: Exception) -> AppError:
    """Fail visibly instead of silently replacing Qwen with a weaker parser."""

    if isinstance(exc, AppError):
        return exc
    return AppError(
        code="LLM_PROVIDER_ERROR",
        message="千问未能完成本次需求理解，请稍后重试。系统没有用本地规则替你猜测。",
        status_code=503,
        retryable=True,
        details=[_safe_llm_warning_details(exc)],
    )


def _merge_client_memories(
    *,
    stored: list[MemoryItem],
    client_items: list[dict],
    user_id: str,
    now: datetime,
) -> list[MemoryItem]:
    """Let the browser snapshot survive stateless server deployments."""
    by_key = {item.key: item for item in stored}
    for raw in client_items:
        try:
            item = MemoryCreate.model_validate(raw)
        except Exception:
            continue
        if not item.enabled:
            by_key.pop(item.key, None)
            continue
        by_key[item.key] = MemoryItem(
            id=f"client_{item.key}",
            user_id=user_id,
            category=item.category,
            key=item.key,
            label=item.label,
            value=item.value,
            enabled=True,
            source="browser_snapshot",
            created_at=now,
            updated_at=now,
        )
    return sorted(by_key.values(), key=lambda item: (item.label, item.key))


def _client_timetable_tasks(
    *,
    raw: dict | None,
    target_date: date,
    class_periods,
    timezone,
    effective_weekday: int | None,
) -> list[Task]:
    if not raw or not raw.get("enabled", True):
        return []
    if effective_weekday is None:
        return []
    try:
        term_start = (
            date.fromisoformat(raw["term_start"]) if raw.get("term_start") else None
        )
        term_end = date.fromisoformat(raw["term_end"]) if raw.get("term_end") else None
    except (TypeError, ValueError):
        return []
    if term_start and target_date < term_start:
        return []
    if term_end and target_date > term_end:
        return []
    academic_week = ((target_date - term_start).days // 7) + 1 if term_start else None
    tasks: list[Task] = []
    for index, value in enumerate(raw.get("entries", []), start=1):
        try:
            entry = CourseSessionCreate.model_validate(value)
        except Exception:
            continue
        if entry.weekday != effective_weekday:
            continue
        if entry.weeks and (academic_week is None or academic_week not in entry.weeks):
            continue
        start_value = class_periods.get(entry.start_period)
        end_value = class_periods.get(entry.end_period)
        if not start_value or not end_value:
            continue
        start_at = datetime.combine(target_date, start_value[0], timezone)
        end_at = datetime.combine(target_date, end_value[1], timezone)
        tasks.append(
            Task(
                id=f"client_course_{index}_{entry.start_period}_{entry.end_period}",
                title=entry.course_name,
                date=target_date,
                duration_min=int((end_at - start_at).total_seconds() // 60),
                location_raw=entry.location,
                fixed_start=start_at,
                fixed_end=end_at,
                flexibility=TaskFlexibility.FIXED,
                importance=5,
                tags=[
                    "course",
                    "personal_timetable",
                    "browser_snapshot",
                    "hard_constraint",
                    f"period:{entry.start_period}-{entry.end_period}",
                ],
                notes="来自浏览器保存的个人课表，按已核验节次锁定",
            )
        )
    return tasks


def _explicit_no_class_exception(query: str) -> bool:
    """Treat a direct no-class statement as a one-day timetable exception."""
    if any(marker in query for marker in ("吗", "是否", "有没有", "哪几节")):
        return False
    return bool(
        re.search(
            r"(?:今天|明天|后天|当天)?\s*(?:全天)?\s*(?:没课|没有课|无课)",
            query,
        )
    )


def _is_timetable_query(query: str) -> bool:
    return any(
        re.search(pattern, query)
        for pattern in (
            r"课表",
            r"哪几节.*课",
            r"(?:有|没|没有)课吗",
            r"有没有课",
            r"是否有课",
            r"(?:要|需要|应该|是否要)上课吗",
        )
    )


def _merge_timetable_tasks(
    parsed_tasks,
    timetable_tasks,
):
    """Merge personal courses without duplicating explicitly stated classes."""
    verified_course_tags = {
        "verified_timetable",
        "personal_timetable",
        "browser_snapshot",
    }
    merged = [
        task
        for task in parsed_tasks
        if not (
            timetable_tasks
            and "course" in task.tags
            and not verified_course_tags.intersection(task.tags)
        )
    ]
    existing_fixed = [
        task
        for task in merged
        if task.fixed_start is not None and task.fixed_end is not None
    ]
    for task in timetable_tasks:
        overlaps = any(
            existing.fixed_start < task.fixed_end
            and task.fixed_start < existing.fixed_end
            and ("course" in existing.tags or existing.title == task.title)
            for existing in existing_fixed
        )
        if not overlaps:
            merged.append(task)
    return merged


def _apply_timetable_relative_constraints(
    *,
    query: str,
    timetable_tasks,
    tasks,
):
    """Ground “after class” against the imported timetable.

    The rule parser can anchor a task when the user writes explicit periods,
    but imported courses are merged later.  Without this second guard,
    “下午上完课拿快递” can be placed before the actual afternoon class.
    """

    marker = re.search(
        r"(?P<period>上午|下午|晚上)?\s*(?:上完课|下课后|课后)",
        query,
    )
    if marker is None or not timetable_tasks:
        return tasks
    courses = [
        task
        for task in timetable_tasks
        if task.fixed_end is not None
        and (marker.group("period") != "上午" or task.fixed_end.time() <= time(12, 30))
        and (
            marker.group("period") not in {"下午", "晚上"}
            or task.fixed_end.time() > time(12)
        )
    ]
    if not courses:
        return tasks
    class_end = max(task.fixed_end for task in courses if task.fixed_end)
    clause_boundaries = [
        position
        for separator in ("，", "。", "；", ",", ";")
        if (position := query.find(separator, marker.end())) >= 0
    ]
    marker_clause_end = min(clause_boundaries, default=len(query))
    updated = []
    for task in tasks:
        query_position = _task_query_position(query, task)
        if (
            task.flexibility == TaskFlexibility.MOVABLE
            and marker.start() <= query_position <= marker_clause_end
        ):
            earliest_start = (
                max(task.earliest_start, class_end)
                if task.earliest_start is not None
                else class_end
            )
            updated.append(task.model_copy(update={"earliest_start": earliest_start}))
        else:
            updated.append(task)
    return updated


def _timetable_summary(
    target_date: date,
    tasks,
    *,
    calendar_context,
) -> str:
    weekday = "一二三四五六日"[target_date.isoweekday() - 1]
    if calendar_context.course_action == "no_class":
        return (
            f"你的个人课表在{target_date:%Y年%m月%d日}（星期{weekday}）"
            f"因{calendar_context.label or '学校校历安排'}不执行常规课程；"
            "当天仍可以安排学习、运动和生活任务。"
        )
    if calendar_context.course_action == "awaiting_school_notice":
        return (
            f"{target_date:%Y年%m月%d日}（星期{weekday}）是"
            f"{calendar_context.label or '国家调休工作日'}，但尚未录入"
            "学校具体补星期几课程的通知；系统暂不臆测课程，请以教务"
            "通知为准。"
        )
    if not tasks:
        return (
            f"你的个人课表在{target_date:%Y年%m月%d日}（星期{weekday}）"
            "没有已启用的课程记录。"
        )
    details = "；".join(
        _timetable_task_summary(task)
        for task in sorted(tasks, key=lambda item: item.fixed_start)
    )
    summary = (
        f"你的个人课表在{target_date:%Y年%m月%d日}（星期{weekday}）为："
        f"{details}。这些课程属于固定时间约束。"
    )
    if calendar_context.course_action == "makeup":
        effective_weekday = "一二三四五六日"[
            int(calendar_context.effective_weekday) - 1
        ]
        summary += f"学校校历设置为当天按星期{effective_weekday}课表执行。"
    return summary


def _timetable_task_summary(task) -> str:
    period_tag = next(
        (tag.removeprefix("period:") for tag in task.tags if tag.startswith("period:")),
        None,
    )
    period_label = ""
    if period_tag:
        start_period, _, end_period = period_tag.partition("-")
        period_label = (
            f"第{start_period}节"
            if not end_period or end_period == start_period
            else f"第{start_period}—{end_period}节"
        )
    return (
        f"{period_label}（{task.fixed_start:%H:%M}—"
        f"{task.fixed_end:%H:%M}） {task.title}"
        + (f"（{task.location_raw}）" if task.location_raw else "")
    )


def _apply_memory_preferences(
    preferences: UserPreferences,
    memories,
) -> UserPreferences:
    """Apply explicit, enabled memories without changing hard task facts."""
    update = {}
    supported = {
        "buffer_min",
        "walking_speed",
        "transport_mode",
        "avoid_congestion",
        "schedule_pace",
        "preferred_study_location",
        "usual_lunch_time",
        "usual_dinner_time",
    }
    meal_starts: dict[str, time] = {}
    schedule_pace = None
    for memory in memories:
        if memory.key not in supported:
            continue
        value = memory.value
        target_key = memory.key
        if memory.key == "schedule_pace":
            schedule_pace = {
                "宽松": "relaxed",
                "松": "relaxed",
                "relaxed": "relaxed",
                "适中": "balanced",
                "正常": "balanced",
                "balanced": "balanced",
                "紧凑": "compact",
                "紧": "compact",
                "compact": "compact",
            }.get(str(value).strip())
            continue
        if memory.key == "walking_speed":
            value = {
                "慢": "slow",
                "正常": "normal",
                "快": "fast",
            }.get(str(value), value)
        if memory.key == "transport_mode":
            value = {
                "步行": "walk",
                "自行车": "bicycle",
                "骑行": "bicycle",
                "电瓶车": "electrobike",
                "电动车": "electrobike",
            }.get(str(value), value)
        if memory.key == "preferred_locations" and isinstance(value, str):
            value = [item.strip() for item in value.split("、") if item.strip()]
        if memory.key == "preferred_study_location":
            if not isinstance(value, str) or not value.strip():
                continue
            target_key = "preferred_locations"
            existing = update.get(target_key, preferences.preferred_locations)
            value = [
                value.strip(),
                *[item for item in existing if item and item != value.strip()],
            ]
        if memory.key in {"usual_lunch_time", "usual_dinner_time"}:
            try:
                meal_starts[memory.key] = time.fromisoformat(
                    str(value).strip().replace("：", ":")
                )
            except ValueError:
                continue
            continue
        update[target_key] = value
    if meal_starts:
        windows_by_kind = {
            ("lunch" if window.start.hour < 15 else "dinner"): window
            for window in preferences.meal_windows
        }
        meal_windows = []
        for kind, memory_key, fallback, duration_min in (
            ("lunch", "usual_lunch_time", time(12, 25), 50),
            ("dinner", "usual_dinner_time", time(18, 0), 45),
        ):
            existing = windows_by_kind.get(kind)
            start = meal_starts.get(
                memory_key,
                existing.start if existing else fallback,
            )
            end = (
                datetime.combine(date.min, start) + timedelta(minutes=duration_min)
            ).time()
            meal_windows.append({"start": start, "end": end})
        update["meal_windows"] = meal_windows
    if schedule_pace and "buffer_min" not in update:
        pace_updates = {
            "relaxed": (True, max(preferences.buffer_min, 15)),
            "balanced": (True, max(preferences.buffer_min, 15)),
            "compact": (False, 0),
        }
        avoid_tight, buffer_min = pace_updates[schedule_pace]
        update["avoid_tight_schedule"] = avoid_tight
        update["buffer_min"] = buffer_min
    elif update.get("avoid_tight_schedule") is False and "buffer_min" not in update:
        update["buffer_min"] = 0
    elif update.get("avoid_tight_schedule") is True and "buffer_min" not in update:
        update["buffer_min"] = max(preferences.buffer_min, 15)
    if not update:
        return preferences
    try:
        return UserPreferences.model_validate(
            {
                **preferences.model_dump(mode="python"),
                **update,
            }
        )
    except Exception:
        return preferences


def _apply_study_memory_period(
    tasks: list[Task],
    *,
    memories,
) -> list[Task]:
    """Use an explicitly saved study period as a soft daily preference."""
    raw_period = next(
        (memory.value for memory in memories if memory.key == "preferred_study_period"),
        None,
    )
    period = {
        "morning": "morning",
        "上午": "morning",
        "早上": "morning",
        "afternoon": "afternoon",
        "下午": "afternoon",
        "evening": "evening",
        "晚上": "evening",
        "晚间": "evening",
    }.get(str(raw_period))
    if period is None:
        return tasks

    adjusted: list[Task] = []
    for task in tasks:
        if (
            task.flexibility.value != "movable"
            or _task_kind(task.title, task.location_raw) != "study"
            or task.preferred_period is not None
        ):
            adjusted.append(task)
            continue
        adjusted.append(
            task.model_copy(
                update={
                    "preferred_period": period,
                    "tags": list(
                        dict.fromkeys([*task.tags, "memory_period_preference"])
                    ),
                }
            )
        )
    return adjusted


def _apply_preferred_locations(
    tasks: list[Task],
    *,
    preferences: UserPreferences,
    query: str,
) -> list[Task]:
    """Use saved places only when this request did not name another place."""
    preferred = [
        value.strip() for value in preferences.preferred_locations if value.strip()
    ]
    if not preferred:
        return tasks
    keyword_groups = {
        "study": ("图书馆", "自习室", "教室", "宿舍", "教学楼"),
        "run": ("操场", "田径场", "体育馆", "跑道"),
        "dinner": ("食堂", "餐厅"),
        "parcel": ("快递", "驿站"),
    }
    adjusted: list[Task] = []
    for task in tasks:
        if task.flexibility.value != "movable":
            adjusted.append(task)
            continue
        if "memory_activity_location" in task.tags:
            adjusted.append(task)
            continue
        if (
            task.location_raw
            and task.location_raw in query
            and task.location_raw not in {"图书馆", "操场", "快递站"}
        ):
            adjusted.append(task)
            continue
        kind = _task_kind(task.title, task.location_raw)
        keywords = keyword_groups.get(kind or "", ())
        choice = next(
            (
                location
                for location in preferred
                if any(keyword in location for keyword in keywords)
            ),
            None,
        )
        if choice is None:
            adjusted.append(task)
            continue
        adjusted.append(
            task.model_copy(
                update={
                    "location_id": None,
                    "location_raw": choice,
                }
            )
        )
    return adjusted


def _apply_activity_location_memories(
    tasks: list[Task],
    *,
    memories,
    query: str = "",
) -> list[Task]:
    """Apply explicit activity-to-place mappings without overriding facts."""
    raw_value = next(
        (memory.value for memory in memories if memory.key == "activity_location"),
        None,
    )
    mappings: list[tuple[str, str]] = []
    if isinstance(raw_value, dict):
        mappings = [
            (str(activity).strip(), str(location).strip())
            for activity, location in raw_value.items()
        ]
    elif isinstance(raw_value, list):
        for item in raw_value:
            if not isinstance(item, dict):
                continue
            activity = str(item.get("activity", "")).strip()
            location = str(item.get("location", "")).strip()
            if activity and location:
                mappings.append((activity, location))
    mappings = [item for item in mappings if all(item)]
    if not mappings:
        return tasks

    adjusted: list[Task] = []
    for task in tasks:
        if task.flexibility.value != "movable":
            adjusted.append(task)
            continue
        normalized_title = _normalize_task_text(task.title)
        choice = next(
            (
                location
                for activity, location in mappings
                if (
                    _normalize_task_text(activity) in normalized_title
                    or normalized_title in _normalize_task_text(activity)
                )
            ),
            None,
        )
        if choice is None:
            adjusted.append(task)
            continue
        # A detailed location named in the current request wins. Generic
        # parser defaults such as “图书馆” or “操场” may be refined by the
        # user's saved mapping (for example, 图书馆12层 or 东操场).
        if (
            task.location_raw
            and task.location_raw.strip()
            and (
                not query
                or (
                    task.location_raw in query
                    and task.location_raw not in {"图书馆", "操场", "快递站"}
                )
            )
        ):
            adjusted.append(task)
            continue
        # A place explicitly written in the current request always wins; an
        # empty task location means this saved mapping is safe to apply.
        adjusted.append(
            task.model_copy(
                update={
                    "location_id": None,
                    "location_raw": choice,
                    "tags": list(
                        dict.fromkeys([*task.tags, "memory_activity_location"])
                    ),
                }
            )
        )
    return adjusted


def _task_kind(title: str, location_raw: str | None) -> str | None:
    text = f"{title} {location_raw or ''}"
    for kind, keywords in _TASK_KIND_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return kind
    return None


_TASK_KIND_KEYWORDS = (
    ("study", ("自习", "学习", "复习", "图书馆")),
    ("parcel", ("快递", "驿站")),
    ("dinner", ("吃饭", "晚饭", "食堂")),
    ("clinic", ("校医院", "看医生", "就诊", "医务室")),
    ("bath", ("洗澡", "洗漱", "热水", "学生公寓")),
    ("badminton", ("羽毛球", "综合馆")),
    ("table_tennis", ("乒乓球", "体育馆主馆")),
    (
        "run",
        ("阳光长跑", "长跑", "跑步", "运动", "操场", "田径场", "跑道"),
    ),
)


def _describe_plan(plan: Plan) -> str:
    """The current day in the plainest form the model can point back at."""
    lines = [f"日期：{plan.date:%Y-%m-%d}"]
    for item in sorted(plan.items, key=lambda value: value.start_at):
        if item.item_type != "task":
            continue
        lines.append(
            f"- id={item.task_id} 标题={item.title} "
            f"{item.start_at:%H:%M}-{item.end_at:%H:%M}"
            + (f" 地点={item.location_raw}" if item.location_raw else "")
            + (" 【锁定，不可移动】" if item.locked else "")
        )
    if len(lines) == 1:
        lines.append("（当前没有已安排的任务）")
    return chr(10).join(lines)


def _expand_occurrences(tasks: list[Task]) -> list[Task]:
    """Turn “do this N times” into N tasks the planner can actually place.

    A count left on a single task is invisible to the planner: it schedules one
    block and the remaining sittings quietly never happen.  Each sitting gets
    its own id so it can be moved, shortened or dropped on its own, and they
    are kept apart the way split sittings are.
    """

    expanded: list[Task] = []
    for task in tasks:
        count = max(1, task.occurrence_count)
        if count == 1:
            expanded.append(task)
            continue
        for index in range(count):
            expanded.append(
                task.model_copy(
                    update={
                        "id": f"{task.id}_{index + 1}",
                        "title": f"{task.title}（第{index + 1}次）",
                        "occurrence_count": 1,
                        # "自习3次" means three genuinely separate sittings,
                        # not one long block with a short pause.  Keep at least
                        # an hour between them; when today's remaining day is
                        # too short, the request is rolled to tomorrow instead
                        # of weakening what "3次" means.
                        "min_gap_min": max(task.min_gap_min, 60),
                        # Separate sittings, not one block chopped up: they are
                        # deliberately left unchained so the planner can spread
                        # them across whatever gaps the day actually has.
                        "tags": list(
                            dict.fromkeys([*task.tags, f"occurrence_of:{task.id}"])
                        ),
                    }
                )
            )
    if len(expanded) == len(tasks):
        return tasks
    known = {task.id for task in tasks}
    renamed = {task.id: f"{task.id}_1" for task in tasks if task.occurrence_count > 1}
    return [
        task.model_copy(
            update={
                "depends_on": [
                    renamed.get(dependency, dependency)
                    for dependency in task.depends_on
                    if dependency in known or dependency in renamed
                ]
            }
        )
        for task in expanded
    ]


def _split_long_study_blocks(tasks: list[Task]) -> list[Task]:
    """Turn a long study total into usable sittings without losing minutes.

    A seven-hour self-study request cannot cross lunch as one indivisible
    block, so the old scheduler either shortened it drastically or failed to
    publish a full day.  Study is naturally pausable: blocks of at most three
    hours preserve the requested total while allowing meals, classes and
    short recovery gaps between them.  Explicit multi-session requests have
    already been expanded and are left exactly as the user described.
    """

    split: list[Task] = []
    for task in tasks:
        if (
            "study" not in task.tags
            or task.duration_min < 240
            or any(tag.startswith("occurrence_of:") for tag in task.tags)
            or task.flexibility.value != "movable"
        ):
            split.append(task)
            continue

        segment_count = (task.duration_min + 179) // 180
        base = task.duration_min // segment_count
        remainder = task.duration_min % segment_count
        previous_id: str | None = None
        for index in range(segment_count):
            duration = base + (1 if index < remainder else 0)
            segment_id = f"{task.id}_segment_{index + 1}"
            dependencies = list(task.depends_on)
            if previous_id:
                dependencies.append(previous_id)
            split.append(
                task.model_copy(
                    update={
                        "id": segment_id,
                        "title": f"{task.title}（第{index + 1}段）",
                        "duration_min": duration,
                        "min_duration_min": min(60, duration),
                        "splittable": False,
                        "min_gap_min": max(task.min_gap_min, 30),
                        "depends_on": dependencies,
                        "tags": list(
                            dict.fromkeys(
                                [
                                    *task.tags,
                                    "split_segment",
                                    f"split_of:{task.id}",
                                ]
                            )
                        ),
                    }
                )
            )
            previous_id = segment_id
    return split


def _merge_llm_with_rule_constraints(
    *,
    query: str,
    llm_result: UnderstandResult,
    rule_result: UnderstandResult,
) -> UnderstandResult:
    """Keep model semantics while enforcing facts recognized deterministically."""
    if (
        llm_result.intent.value != "plan"
        or rule_result.intent.value != "plan"
        or not rule_result.tasks
    ):
        return llm_result

    merged = list(llm_result.tasks)
    matched_indexes: set[int] = set()
    id_remap: dict[str, str] = {}
    appended_rule_tasks: list[Task] = []

    for rule_task in rule_result.tasks:
        match_index = _best_rule_task_match(
            rule_task=rule_task,
            llm_tasks=merged,
            matched_indexes=matched_indexes,
        )
        if match_index is None:
            # The deterministic parser is also the request ledger for common,
            # explicitly mentioned campus tasks.  An online model may omit one
            # item from a long enumeration (for example "还要取快递").  Never
            # interpret that omission as user intent: append every unmatched
            # ledger item so the scheduler/validator can either place it or
            # report it as unscheduled.
            appended_rule_tasks.append(rule_task)
            continue

        model_task = merged[match_index]
        matched_indexes.add(match_index)
        id_remap[model_task.id] = rule_task.id
        merged[match_index] = _merge_task_constraints(
            query=query,
            model_task=model_task,
            rule_task=rule_task,
        )

    # A count is a property of one conceptual request, not a multiplier for
    # however many objects the model happened to emit.  Qwen may represent
    # “自习2次” as one task with occurrence_count=2 *or* as two separately
    # named tasks.  The deterministic parser already owns the requested
    # count; keeping the model's second representation here and expanding
    # both later silently turns two sittings into three or four.
    redundant_model_indexes = _redundant_model_occurrence_indexes(
        rule_tasks=rule_result.tasks,
        model_tasks=merged,
        matched_indexes=matched_indexes,
    )
    if redundant_model_indexes:
        merged = [
            task
            for index, task in enumerate(merged)
            if index not in redundant_model_indexes
        ]

    merged.extend(appended_rule_tasks)
    merged = [
        task.model_copy(
            update={
                "depends_on": list(
                    dict.fromkeys(
                        id_remap.get(task_id, task_id)
                        for task_id in task.depends_on
                        if id_remap.get(task_id, task_id) != task.id
                    )
                )
            }
        )
        for task in merged
    ]
    merged = [
        task
        for _, task in sorted(
            enumerate(merged),
            key=lambda item: (
                _task_query_position(query, item[1]),
                item[0],
            ),
        )
    ]
    clarifications = list(
        dict.fromkeys(
            [
                *llm_result.clarifications,
                *rule_result.clarifications,
            ]
        )
    )
    return llm_result.model_copy(
        update={
            "requested_date": rule_result.requested_date,
            "tasks": merged,
            # An explicit overall deadline leaves no room for the model's
            # generic anti-rush buffer. Keep any saved/user preference when
            # no deadline was stated, but never make a feasible hard window
            # infeasible by adding an inferred 10-minute buffer.
            "preferences": (
                rule_result.preferences
                if rule_result.preferences.buffer_min == 0
                else llm_result.preferences
            ),
            "clarifications": clarifications,
            "confidence": max(
                llm_result.confidence,
                rule_result.confidence,
            ),
        }
    )


def _redundant_model_occurrence_indexes(
    *,
    rule_tasks: list[Task],
    model_tasks: list[Task],
    matched_indexes: set[int],
) -> set[int]:
    """Remove duplicate model encodings of a rule-owned occurrence count.

    This is deliberately narrow: it applies only when the rule parser found
    an explicit repeated occurrence.  Distinct tasks of the same broad kind
    remain untouched for ordinary requests.
    """

    repeated_kinds = {
        _task_kind(task.title, task.location_raw)
        for task in rule_tasks
        if task.occurrence_count > 1
    }
    repeated_kinds.discard(None)
    if not repeated_kinds:
        return set()
    return {
        index
        for index, task in enumerate(model_tasks)
        if index not in matched_indexes
        and _task_kind(task.title, task.location_raw) in repeated_kinds
    }


def _drop_journey_origin_marker_tasks(
    tasks: list[Task],
    origin: str,
    *,
    protected_task_ids: set[str] | None = None,
) -> list[Task]:
    """Keep a stated departure point as context, never as a fake task."""
    protected = protected_task_ids or set()
    origin_pattern = re.escape(origin.strip())
    marker_pattern = re.compile(
        rf"^\s*(?:从|自)?\s*{origin_pattern}\s*"
        rf"(?:"
        rf"(?:出发|启程)(?:\s*(?:前往|去|到).*)?"
        rf"|(?:前往|去|到).+"
        rf")\s*$"
    )
    removed_ids = {
        task.id
        for task in tasks
        if task.id not in protected and marker_pattern.fullmatch(task.title)
    }
    if not removed_ids:
        return tasks
    return [
        task.model_copy(
            update={
                "depends_on": [
                    task_id for task_id in task.depends_on if task_id not in removed_ids
                ]
            }
        )
        for task in tasks
        if task.id not in removed_ids
    ]


def _release_destination_from_departure_anchor(
    task: Task,
    departure_at: datetime,
) -> Task:
    """Do not confuse the journey start with a destination task start."""
    if (
        task.fixed_start != departure_at
        or task.flexibility not in {TaskFlexibility.FIXED, TaskFlexibility.LOCKED}
        or "hard_constraint" in task.tags
        or "course" in task.tags
    ):
        return task
    return task.model_copy(
        update={
            "fixed_start": None,
            "fixed_end": None,
            "flexibility": TaskFlexibility.MOVABLE,
        }
    )


def _best_rule_task_match(
    *,
    rule_task: Task,
    llm_tasks: list[Task],
    matched_indexes: set[int],
) -> int | None:
    best_index: int | None = None
    best_score = 0
    rule_kind = _task_kind(rule_task.title, rule_task.location_raw)
    rule_title = _normalize_task_text(rule_task.title)
    rule_location = _normalize_task_text(rule_task.location_raw or "")

    for index, model_task in enumerate(llm_tasks):
        if index in matched_indexes:
            continue
        score = 0
        model_kind = _task_kind(model_task.title, model_task.location_raw)
        model_title = _normalize_task_text(model_task.title)
        model_location = _normalize_task_text(model_task.location_raw or "")
        if model_task.id == rule_task.id:
            score += 100
        if rule_kind is not None and model_kind == rule_kind:
            score += 60
        elif (
            rule_kind is not None and model_kind is not None and model_kind != rule_kind
        ):
            continue
        if rule_title and model_title:
            if rule_title == model_title:
                score += 50
            elif rule_title in model_title or model_title in rule_title:
                score += 25
        if rule_location and model_location:
            if rule_location == model_location:
                score += 30
            elif rule_location in model_location or model_location in rule_location:
                score += 15
        if score > best_score:
            best_index = index
            best_score = score
    return best_index


def _merge_task_constraints(
    *,
    query: str,
    model_task: Task,
    rule_task: Task,
) -> Task:
    fixed_by_rule = rule_task.flexibility in {
        TaskFlexibility.FIXED,
        TaskFlexibility.LOCKED,
    }
    use_rule_location = bool(
        rule_task.location_raw
        and ("hard_constraint" in rule_task.tags or rule_task.location_raw in query)
    )
    tags = list(dict.fromkeys([*model_task.tags, *rule_task.tags]))
    notes = model_task.notes
    if "hard_constraint" in rule_task.tags and rule_task.notes:
        notes = (
            rule_task.notes
            if not notes or notes == rule_task.notes
            else f"{notes}；{rule_task.notes}"
        )

    rule_has_explicit_duration = rule_task.duration_source == "explicit"
    rule_has_explicit_period = (
        rule_task.constraint_source == "user" and rule_task.preferred_period is not None
    )
    model_has_explicit_period = (
        model_task.constraint_source == "user"
        and model_task.preferred_period is not None
    )
    update = {
        "id": rule_task.id,
        # Course blocks come from the deterministic period parser. Keep its
        # canonical title (including the ``课程`` marker) so the API and UI
        # can identify course items consistently even when the LLM calls the
        # same block ``第1节课`` or another free-form variant.
        "title": (rule_task.title if "course" in rule_task.tags else model_task.title),
        "date": rule_task.date,
        # Whether a task is fixed is a hard scheduling fact, not a wording
        # choice. The deterministic parser is the final authority here; an
        # LLM must not turn a journey departure time into the fixed start of
        # the first destination task.
        "fixed_start": rule_task.fixed_start,
        "fixed_end": rule_task.fixed_end,
        "flexibility": rule_task.flexibility,
        # A split sitting carries the share of the total the rule parser
        # computed. Taking the model's duration here would give every sitting
        # the length of the whole task and multiply the requested work.
        "duration_min": (
            rule_task.duration_min
            if (
                fixed_by_rule
                or "split_segment" in rule_task.tags
                or rule_has_explicit_duration
            )
            else model_task.duration_min
        ),
        # The deterministic parser knows whether a number was actually
        # attached to this task.  Preserve that provenance and its flexible
        # floor: a default two-hour study block may shrink to one hour, while
        # an explicit “和导师碰头2h” must remain two hours.
        "min_duration_min": (
            rule_task.min_duration_min
            if (not rule_has_explicit_duration or "elastic_duration" in rule_task.tags)
            else None
        ),
        "max_duration_min": (
            rule_task.max_duration_min
            if rule_task.max_duration_min is not None
            else model_task.max_duration_min
        ),
        "duration_source": rule_task.duration_source,
        "occurrence_count": rule_task.occurrence_count,
        "splittable": rule_task.splittable or model_task.splittable,
        "min_gap_min": max(rule_task.min_gap_min, model_task.min_gap_min),
        "location_id": (
            rule_task.location_id if use_rule_location else model_task.location_id
        ),
        "location_raw": (
            rule_task.location_raw if use_rule_location else model_task.location_raw
        ),
        # Explicit time anchors from the deterministic parser are hard user
        # constraints. The model may infer a preference (for example,
        # interpreting “18点前结束” as an 18:00 start), but that inference
        # must not override an explicit “14点以后” boundary.
        "earliest_start": (
            rule_task.earliest_start
            if rule_task.earliest_start is not None
            else model_task.earliest_start
        ),
        "latest_end": (
            rule_task.latest_end
            if rule_task.latest_end is not None
            else model_task.latest_end
        ),
        "deadline": (
            rule_task.deadline
            if rule_task.deadline is not None
            else model_task.deadline
        ),
        # A model-only period is a soft preference at best. When the rule
        # parser found explicit clock anchors but no matching period phrase,
        # drop the model's guessed period (e.g. “evening” for a generic run)
        # so it cannot turn a preference into an impossible hard window.
        "preferred_period": (
            rule_task.preferred_period
            if rule_has_explicit_period
            else (model_task.preferred_period if model_has_explicit_period else None)
        ),
        "constraint_source": (
            "user" if rule_has_explicit_period or model_has_explicit_period else "rule"
        ),
        "importance": max(model_task.importance, rule_task.importance),
        # Dependencies are structural.  The rule parser now creates them only
        # for explicit sequence words (“先…再…”, “然后”), while a language
        # model can easily mistake the enumerating “还要” for an order.
        "depends_on": list(rule_task.depends_on),
        "tags": tags,
        "notes": notes,
    }
    return model_task.model_copy(update=update)


def _task_query_position(query: str, task: Task) -> int:
    candidates = [task.title, task.location_raw or ""]
    kind = _task_kind(task.title, task.location_raw)
    candidates.extend(
        values for candidate, values in _TASK_KIND_KEYWORDS if candidate == kind
    )
    flattened: list[str] = []
    for value in candidates:
        if isinstance(value, tuple):
            flattened.extend(value)
        elif value:
            flattened.append(value)
    positions = [
        query.find(value) for value in flattened if value and query.find(value) >= 0
    ]
    return min(positions, default=len(query) + 1)


def _normalize_task_text(value: str) -> str:
    return re.sub(r"[\s，。；、,:：！？!?（）()\-—_]", "", value)


def _later_datetime(
    first: datetime | None,
    second: datetime | None,
) -> datetime | None:
    values = [value for value in (first, second) if value is not None]
    return max(values, default=None)


def _earlier_datetime(
    first: datetime | None,
    second: datetime | None,
) -> datetime | None:
    values = [value for value in (first, second) if value is not None]
    return min(values, default=None)


def _safe_llm_warning_details(exc: Exception) -> dict:
    details = {
        "error_type": type(exc).__name__,
        "error_code": getattr(exc, "code", None),
    }
    raw_details = getattr(exc, "details", None)
    if not raw_details or not isinstance(raw_details[0], dict):
        return details
    for key in (
        "provider_status_code",
        "provider_error_code",
        "provider_error_type",
        "provider_exception_type",
    ):
        value = raw_details[0].get(key)
        if value is not None:
            details[key] = value
    return details


def _can_apply_rule_guard(
    *,
    query: str,
    llm_result: UnderstandResult,
    rule_result: UnderstandResult,
) -> bool:
    """Use deterministic constraints only for fully recognized common plans."""
    if any("hard_constraint" in task.tags for task in rule_result.tasks):
        return True
    rule_kinds = {
        _task_kind(task.title, task.location_raw) for task in rule_result.tasks
    }
    explicit_common_plan = (
        rule_result.intent.value == "plan"
        and not rule_result.clarifications
        and bool(rule_result.tasks)
        and None not in rule_kinds
        and bool(
            re.search(
                r"(?:[01]?\d|2[0-3])"
                r"(?:\s*[:：]\s*[0-5]?\d|"
                r"\s*点(?:\s*[0-5]?\d\s*分?)?)",
                query,
            )
        )
        and all(
            task.fixed_start is not None or task.earliest_start is not None
            for task in rule_result.tasks
        )
    )
    if explicit_common_plan and llm_result.clarifications:
        # A model occasionally asks whether a venue is open even though the
        # structured campus rule layer can validate that downstream. Once the
        # local parser has a complete common task and explicit time anchor,
        # the model must not invent a blocking clarification.
        return True
    if (
        llm_result.intent.value != "plan"
        or rule_result.intent.value != "plan"
        or rule_result.clarifications
        or not rule_result.tasks
        or len(llm_result.tasks) != len(rule_result.tasks)
    ):
        return False
    if explicit_common_plan and re.search(r"从.{1,40}出发", query):
        # Keep the explicit journey origin separate from task semantics. Some
        # model outputs merge “从某楼出发” into the first task title/location,
        # which can even change the apparent task category.
        return True
    llm_kinds = {_task_kind(task.title, task.location_raw) for task in llm_result.tasks}
    if None in llm_kinds or None in rule_kinds or llm_kinds != rule_kinds:
        return False
    return all(
        task.earliest_start is not None
        and (task.latest_end is not None or task.deadline is not None)
        for task in rule_result.tasks
    )


def _apply_explicit_date_guard(
    *,
    query: str,
    result: UnderstandResult,
    rule_result: UnderstandResult,
) -> UnderstandResult:
    """Keep explicit calendar expressions deterministic.

    A language model may interpret “本周三” as the next Wednesday even when
    the date has already passed. Calendar expressions are hard constraints,
    so the rule parser owns the date while the model may still own task
    semantics.
    """
    if not re.search(
        r"(?:今天|明天|后天|"
        r"(?:本周|这周|本星期|这星期|下周|下星期|周|星期)"
        r"\s*[一二三四五六日天]|"
        r"20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}|"
        r"\d{1,2}月\d{1,2}日)",
        query,
    ):
        return result

    source_date = result.requested_date
    target_date = rule_result.requested_date
    shifted_tasks = [
        _shift_task_to_date(task, source_date, target_date) for task in result.tasks
    ]
    clarifications = list(result.clarifications)
    for clarification in rule_result.clarifications:
        if "已经过去" in clarification and clarification not in clarifications:
            clarifications.append(clarification)
    return result.model_copy(
        update={
            "requested_date": target_date,
            "tasks": shifted_tasks,
            "clarifications": clarifications,
        }
    )


def _shift_task_to_date(
    task: Task,
    source_date: date,
    target_date: date,
) -> Task:
    def shift(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        day_offset = (value.date() - source_date).days
        shifted_date = target_date + timedelta(days=day_offset)
        return datetime.combine(
            shifted_date,
            value.timetz(),
        )

    return task.model_copy(
        update={
            "date": target_date,
            "earliest_start": shift(task.earliest_start),
            "latest_end": shift(task.latest_end),
            "fixed_start": shift(task.fixed_start),
            "fixed_end": shift(task.fixed_end),
            "deadline": shift(task.deadline),
        }
    )
