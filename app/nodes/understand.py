from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.container import AppContainer
from app.nodes.common import append_trace
from app.schemas.calendar import CalendarOverrideCreate
from app.schemas.common import Issue, IssueSeverity, TaskFlexibility
from app.schemas.memory import MemoryCreate, MemoryItem
from app.schemas.plan import Plan
from app.schemas.task import Task, UserPreferences
from app.schemas.timetable import CourseSessionCreate
from app.schemas.understand import UnderstandResult
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
        should_use_llm = (
            container.llm.configured
            and old_plan is None
            and state.get("mode") != "offline"
        )
        if should_use_llm:
            try:
                llm_result = await container.llm.parse_requirement(
                    query=state["query"],
                    now_iso=state["now_iso"],
                    memory_context=[
                        {
                            "category": memory.category,
                            "label": memory.label,
                            "key": memory.key,
                            "value": memory.value,
                        }
                        for memory in memories
                    ],
                )
                result = _merge_llm_with_rule_constraints(
                    query=state["query"],
                    llm_result=llm_result,
                    rule_result=rule_result,
                )
                if (
                    llm_result.clarifications
                    and _can_apply_rule_guard(
                        query=state["query"],
                        llm_result=llm_result,
                        rule_result=rule_result,
                    )
                ):
                    result = result.model_copy(
                        update={
                            "clarifications": list(
                                rule_result.clarifications
                            ),
                        }
                    )
                parser_name = "llm_with_rule_constraints"
            except Exception as exc:
                result = rule_result
                parser_name = "deterministic_rules_fallback"
                warnings.append(
                    Issue(
                        code="LLM_DEGRADED",
                        severity=IssueSeverity.WARNING,
                        message=(
                            "大模型暂时不可用，已使用确定性约束层继续完成规划"
                        ),
                        details=_safe_llm_warning_details(exc),
                        recoverable=True,
                    ).model_dump(mode="json")
                )
        else:
            result = rule_result
            parser_name = "deterministic_rules"

        result = _apply_explicit_date_guard(
            query=state["query"],
            result=result,
            rule_result=rule_result,
        )

        initial_location_raw = (
            container.parser.journey_origin_from_query(state["query"])
            if result.intent.value == "plan"
            else None
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
                        for task in result.tasks
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
        timetable_summary = (
            _timetable_summary(
                result.requested_date,
                timetable_tasks,
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
            result = result.model_copy(
                update={
                    "tasks": _merge_timetable_tasks(
                        result.tasks,
                        timetable_tasks,
                    )
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
        result = result.model_copy(
            update={
                "tasks": _apply_preferred_locations(
                    tasks_with_study_preferences,
                    preferences=preferences,
                    query=state["query"],
                )
            }
        )
        explicit_mode = container.parser.transport_mode_from_query(state["query"])
        explicit_avoid_congestion = (
            container.parser.avoid_congestion_from_query(state["query"])
        )
        if (
            explicit_mode.value != "walk"
            or explicit_avoid_congestion
            or any(
                keyword in state["query"]
                for keyword in ("步行", "走路", "走过去")
            )
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
            "tasks": [
                task.model_dump(mode="json")
                for task in result.tasks
            ],
            "preferences": preferences.model_dump(mode="json"),
            "user_memories": [
                memory.model_dump(mode="json") for memory in memories
            ],
            "timetable_summary": timetable_summary,
            "academic_day_context": calendar_context.model_dump(mode="json"),
            "initial_location_raw": initial_location_raw,
            "initial_departure_at": (
                initial_departure_at.isoformat()
                if initial_departure_at
                else None
            ),
            "clarifications": result.clarifications,
            "parse_confidence": result.confidence,
            "provider_warnings": warnings,
            "status": (
                "needs_clarification"
                if result.clarifications
                else "understood"
            ),
            "node_trace": append_trace(
                state,
                "understand",
                {
                    "parser": parser_name,
                    "intent": result.intent.value,
                    "task_count": len(result.tasks),
                    "memory_count": len(memories),
                    "timetable_task_count": len(timetable_tasks),
                    "academic_day": calendar_context.course_action,
                    "clarification_count": len(result.clarifications),
                },
            ),
        }

    return understand


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
            date.fromisoformat(raw["term_start"])
            if raw.get("term_start")
            else None
        )
        term_end = (
            date.fromisoformat(raw["term_end"])
            if raw.get("term_end")
            else None
        )
    except (TypeError, ValueError):
        return []
    if term_start and target_date < term_start:
        return []
    if term_end and target_date > term_end:
        return []
    academic_week = (
        ((target_date - term_start).days // 7) + 1
        if term_start
        else None
    )
    tasks: list[Task] = []
    for index, value in enumerate(raw.get("entries", []), start=1):
        try:
            entry = CourseSessionCreate.model_validate(value)
        except Exception:
            continue
        if entry.weekday != effective_weekday:
            continue
        if entry.weeks and (
            academic_week is None or academic_week not in entry.weeks
        ):
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
    merged = list(parsed_tasks)
    existing_fixed = [
        task
        for task in parsed_tasks
        if task.fixed_start is not None and task.fixed_end is not None
    ]
    for task in timetable_tasks:
        overlaps = any(
            existing.fixed_start < task.fixed_end
            and task.fixed_start < existing.fixed_end
            and (
                "course" in existing.tags
                or existing.title == task.title
            )
            for existing in existing_fixed
        )
        if not overlaps:
            merged.append(task)
    return merged


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
        summary += (
            f"学校校历设置为当天按星期{effective_weekday}课表执行。"
        )
    return summary


def _timetable_task_summary(task) -> str:
    period_tag = next(
        (
            tag.removeprefix("period:")
            for tag in task.tags
            if tag.startswith("period:")
        ),
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
        "avoid_rain",
        "avoid_tight_schedule",
        "preferred_locations",
        "preferred_study_location",
    }
    for memory in memories:
        if memory.key not in supported:
            continue
        value = memory.value
        target_key = memory.key
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
                *[
                    item
                    for item in existing
                    if item and item != value.strip()
                ],
            ]
        update[target_key] = value
    if (
        update.get("avoid_tight_schedule") is False
        and "buffer_min" not in update
    ):
        update["buffer_min"] = 0
    elif (
        update.get("avoid_tight_schedule") is True
        and "buffer_min" not in update
    ):
        update["buffer_min"] = max(preferences.buffer_min, 10)
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
        (
            memory.value
            for memory in memories
            if memory.key == "preferred_study_period"
        ),
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
                        dict.fromkeys(
                            [*task.tags, "memory_period_preference"]
                        )
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
        value.strip()
        for value in preferences.preferred_locations
        if value.strip()
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
        if task.location_raw and task.location_raw in query:
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
            if (
                "common_task_fallback" not in rule_task.tags
                or not llm_result.tasks
            ):
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
            "clarifications": clarifications,
            "confidence": max(
                llm_result.confidence,
                rule_result.confidence,
            ),
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
            rule_kind is not None
            and model_kind is not None
            and model_kind != rule_kind
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
        and (
            "hard_constraint" in rule_task.tags
            or rule_task.location_raw in query
        )
    )
    tags = list(dict.fromkeys([*model_task.tags, *rule_task.tags]))
    notes = model_task.notes
    if "hard_constraint" in rule_task.tags and rule_task.notes:
        notes = (
            rule_task.notes
            if not notes or notes == rule_task.notes
            else f"{notes}；{rule_task.notes}"
        )

    update = {
        "id": rule_task.id,
        "date": rule_task.date,
        "duration_min": (
            rule_task.duration_min
            if fixed_by_rule
            else model_task.duration_min
        ),
        "location_id": (
            rule_task.location_id
            if use_rule_location
            else model_task.location_id
        ),
        "location_raw": (
            rule_task.location_raw
            if use_rule_location
            else model_task.location_raw
        ),
        "earliest_start": _later_datetime(
            model_task.earliest_start,
            rule_task.earliest_start,
        ),
        "latest_end": _earlier_datetime(
            model_task.latest_end,
            rule_task.latest_end,
        ),
        "deadline": _earlier_datetime(
            model_task.deadline,
            rule_task.deadline,
        ),
        "importance": max(model_task.importance, rule_task.importance),
        "depends_on": list(
            dict.fromkeys(
                [*model_task.depends_on, *rule_task.depends_on]
            )
        ),
        "tags": tags,
        "notes": notes,
    }
    if fixed_by_rule:
        update.update(
            {
                "fixed_start": rule_task.fixed_start,
                "fixed_end": rule_task.fixed_end,
                "flexibility": rule_task.flexibility,
            }
        )
    return model_task.model_copy(update=update)


def _task_query_position(query: str, task: Task) -> int:
    candidates = [task.title, task.location_raw or ""]
    kind = _task_kind(task.title, task.location_raw)
    candidates.extend(
        values
        for candidate, values in _TASK_KIND_KEYWORDS
        if candidate == kind
    )
    flattened: list[str] = []
    for value in candidates:
        if isinstance(value, tuple):
            flattened.extend(value)
        elif value:
            flattened.append(value)
    positions = [
        query.find(value)
        for value in flattened
        if value and query.find(value) >= 0
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
    if any(
        "hard_constraint" in task.tags
        for task in rule_result.tasks
    ):
        return True
    rule_kinds = {
        _task_kind(task.title, task.location_raw)
        for task in rule_result.tasks
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
            task.fixed_start is not None
            or task.earliest_start is not None
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
    llm_kinds = {
        _task_kind(task.title, task.location_raw)
        for task in llm_result.tasks
    }
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
        _shift_task_to_date(task, source_date, target_date)
        for task in result.tasks
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
