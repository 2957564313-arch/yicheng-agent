from __future__ import annotations

from datetime import date, datetime
import re

from app.container import AppContainer
from app.nodes.common import append_trace
from app.schemas.common import Issue, IssueSeverity
from app.schemas.common import TaskFlexibility
from app.schemas.task import UserPreferences
from app.schemas.understand import UnderstandResult
from app.state import CampusAgentState


def make_understand_node(container: AppContainer):
    async def understand(state: CampusAgentState) -> dict:
        memories = container.memories.list(
            state["user_id"],
            enabled_only=True,
        )
        old_plan = (
            container.plans.get(state["old_plan_id"])
            if state.get("old_plan_id")
            else None
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
                if _can_apply_rule_guard(
                    query=state["query"],
                    llm_result=llm_result,
                    rule_result=rule_result,
                ):
                    result = rule_result.model_copy(
                        update={
                            "confidence": max(
                                rule_result.confidence,
                                llm_result.confidence,
                            )
                        }
                    )
                    parser_name = "llm_with_rule_guard"
                else:
                    result = llm_result
                    parser_name = "llm"
            except Exception as exc:
                result = rule_result
                parser_name = "offline_rules_fallback"
                warnings.append(
                    Issue(
                        code="LLM_DEGRADED",
                        severity=IssueSeverity.WARNING,
                        message=(
                            "大模型暂时不可用，已切换为本地规则继续处理"
                        ),
                        details={
                            "error_type": type(exc).__name__,
                            "error_code": getattr(exc, "code", None),
                            "provider_error_type": (
                                exc.details[0].get(
                                    "provider_error_type"
                                )
                                if getattr(exc, "details", None)
                                else None
                            ),
                        },
                        recoverable=True,
                    ).model_dump(mode="json")
                )
        else:
            result = rule_result
            parser_name = "offline_rules"

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

        timetable_tasks = container.timetables.tasks_for_date(
            user_id=state["user_id"],
            target_date=result.requested_date,
            class_periods=container.parser.class_periods,
            timezone_name=container.settings.app_timezone,
        )
        timetable_summary = (
            _timetable_summary(result.requested_date, timetable_tasks)
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
                    "clarification_count": len(result.clarifications),
                },
            ),
        }

    return understand


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
) -> str:
    weekday = "一二三四五六日"[target_date.isoweekday() - 1]
    if not tasks:
        return (
            f"你的个人课表在{target_date:%Y年%m月%d日}（星期{weekday}）"
            "没有已启用的课程记录。"
        )
    details = "；".join(
        _timetable_task_summary(task)
        for task in sorted(tasks, key=lambda item: item.fixed_start)
    )
    return (
        f"你的个人课表在{target_date:%Y年%m月%d日}（星期{weekday}）为："
        f"{details}。这些课程属于固定时间约束。"
    )


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
    }
    for memory in memories:
        if memory.key not in supported:
            continue
        value = memory.value
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
        update[memory.key] = value
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


def _task_kind(title: str, location_raw: str | None) -> str | None:
    text = f"{title} {location_raw or ''}"
    for kind, keywords in (
        ("study", ("自习", "学习", "图书馆")),
        ("parcel", ("快递", "驿站")),
        ("dinner", ("吃饭", "晚饭", "食堂")),
        ("run", ("跑步", "运动", "操场", "田径场")),
    ):
        if any(keyword in text for keyword in keywords):
            return kind
    return None


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
    if (
        llm_result.intent.value != "plan"
        or rule_result.intent.value != "plan"
        or rule_result.clarifications
        or not rule_result.tasks
        or len(llm_result.tasks) != len(rule_result.tasks)
    ):
        return False
    llm_kinds = {
        _task_kind(task.title, task.location_raw)
        for task in llm_result.tasks
    }
    rule_kinds = {
        _task_kind(task.title, task.location_raw)
        for task in rule_result.tasks
    }
    if None in llm_kinds or None in rule_kinds or llm_kinds != rule_kinds:
        return False
    return all(
        task.earliest_start is not None
        and (task.latest_end is not None or task.deadline is not None)
        for task in rule_result.tasks
    )
