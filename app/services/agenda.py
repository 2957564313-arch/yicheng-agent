from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.providers.location_repository import LocationRepository
from app.repositories.academic_calendar import AcademicCalendarRepository
from app.repositories.external_events import ExternalEventRepository
from app.repositories.memories import MemoryRepository
from app.repositories.plans import PlanRepository
from app.repositories.timetables import TimetableRepository
from app.schemas.agenda import (
    AgendaItem,
    AgendaSummary,
    CareSuggestion,
    ReminderCandidate,
    ReminderSettings,
)


class AgendaService:
    """Merge personal timetable and saved plans into one long-lived agenda."""

    def __init__(
        self,
        *,
        plans: PlanRepository,
        external_events: ExternalEventRepository,
        timetables: TimetableRepository,
        academic_calendar: AcademicCalendarRepository,
        memories: MemoryRepository,
        locations: LocationRepository,
        class_periods: dict[int, tuple[time, time]],
        timezone_name: str,
    ) -> None:
        self.plans = plans
        self.external_events = external_events
        self.timetables = timetables
        self.academic_calendar = academic_calendar
        self.memories = memories
        self.locations = locations
        self.class_periods = class_periods
        self.timezone_name = timezone_name

    def list_items(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[AgendaItem]:
        if end_date < start_date:
            return []
        if (end_date - start_date).days > 183:
            raise ValueError("日程查询范围不能超过184天")

        course_items = self._course_items(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        plan_items = self._plan_items(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            imported_course_keys={
                self._course_identity(item) for item in course_items
            },
        )
        external_items = self._external_items(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        return sorted(
            [*course_items, *plan_items, *external_items],
            key=lambda item: (
                item.start_at,
                item.end_at,
                item.source,
                item.title,
            ),
        )

    def _external_items(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[AgendaItem]:
        return [
            AgendaItem(
                id=f"agenda_external_{event.id}",
                user_id=user_id,
                title=event.title,
                start_at=event.start_at,
                end_at=event.end_at,
                location_name=event.location_name,
                source="external",
                kind=event.kind,
                locked=True,
                task_id=event.external_event_id,
                notes=(
                    f"来自 {event.source_system}"
                    + (f"；{event.notes}" if event.notes else "")
                ),
            )
            for event in self.external_events.active_for_range(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
            )
        ]

    def _course_items(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> list[AgendaItem]:
        result: list[AgendaItem] = []
        target_date = start_date
        while target_date <= end_date:
            academic_day = self.academic_calendar.resolve(
                user_id=user_id,
                target_date=target_date,
            )
            tasks = self.timetables.tasks_for_date(
                user_id=user_id,
                target_date=target_date,
                class_periods=self.class_periods,
                timezone_name=self.timezone_name,
                effective_weekday=academic_day.effective_weekday,
            )
            for task in tasks:
                if task.fixed_start is None or task.fixed_end is None:
                    continue
                result.append(
                    AgendaItem(
                        id=f"agenda_course_{target_date}_{task.id}",
                        user_id=user_id,
                        title=task.title,
                        start_at=task.fixed_start,
                        end_at=task.fixed_end,
                        location_name=task.location_raw,
                        source="course",
                        kind="course",
                        locked=True,
                        task_id=task.id,
                        notes=(
                            "来自已启用的个人课表"
                            + (
                                f"；{academic_day.label}"
                                if academic_day.label
                                else ""
                            )
                        ),
                    )
                )
            target_date += timedelta(days=1)
        return result

    def _plan_items(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
        imported_course_keys: set[tuple],
    ) -> list[AgendaItem]:
        result: list[AgendaItem] = []
        plans = self.plans.latest_for_user_range(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
        for plan in plans:
            for item in plan.items:
                if (
                    item.task_id
                    and item.task_id.startswith(("timetable_", "external_"))
                ):
                    continue
                location = (
                    self.locations.get(item.location_id)
                    if item.location_id
                    else None
                )
                agenda_item = AgendaItem(
                    id=f"agenda_plan_{plan.id}_{item.id}",
                    user_id=user_id,
                    title=item.title,
                    start_at=item.start_at,
                    end_at=item.end_at,
                    location_name=location.name if location else None,
                    source="plan",
                    kind=self.classify(
                        title=item.title,
                        item_type=item.item_type,
                    ),
                    locked=(
                        item.reason == "固定或用户锁定任务"
                    ),
                    plan_id=plan.id,
                    task_id=item.task_id,
                    notes=item.reason,
                )
                if (
                    agenda_item.kind == "course"
                    and self._course_identity(agenda_item)
                    in imported_course_keys
                ):
                    continue
                result.append(agenda_item)
        return result

    @staticmethod
    def _course_identity(item: AgendaItem) -> tuple:
        return (
            item.title,
            item.start_at,
            item.end_at,
            item.location_name or "",
        )

    @staticmethod
    def classify(*, title: str, item_type: str = "task") -> str:
        if item_type == "travel":
            return "travel"
        if item_type == "meal":
            return "meal"
        lowered = title.lower()
        if any(word in lowered for word in ("课程", "上课", "实验课")):
            return "course"
        if any(
            word in lowered
            for word in (
                "二课",
                "第二课堂",
                "志愿活动",
                "社团活动",
                "素质拓展",
                "讲座",
            )
        ):
            return "activity"
        if any(word in lowered for word in ("会议", "开会", "例会", "答辩")):
            return "meeting"
        if any(
            word in lowered
            for word in ("自习", "学习", "复习", "阅读", "作业", "报告")
        ):
            return "study"
        if any(
            word in lowered
            for word in ("跑步", "运动", "健身", "锻炼", "球")
        ):
            return "exercise"
        if any(word in lowered for word in ("吃饭", "用餐", "早餐", "午餐", "晚餐")):
            return "meal"
        return "task"

    def build_reminders(
        self,
        *,
        items: list[AgendaItem],
        settings: ReminderSettings,
        user_id: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[ReminderCandidate]:
        if not settings.enabled:
            return []
        result: list[ReminderCandidate] = []
        for item in items:
            if item.kind == "travel":
                continue
            lead_min = {
                "course": settings.course_lead_min,
                "meeting": settings.meeting_lead_min,
                "activity": settings.activity_lead_min,
                "study": settings.study_lead_min,
                "exercise": settings.exercise_lead_min,
                "meal": settings.task_lead_min,
                "task": settings.task_lead_min,
            }[item.kind]
            if lead_min > 0:
                notify_at = item.start_at - timedelta(minutes=lead_min)
                if not self._in_quiet_hours(notify_at, settings):
                    result.append(
                        ReminderCandidate(
                            id=f"{item.id}:upcoming:{lead_min}",
                            agenda_item_id=item.id,
                            kind=(
                                "prepare"
                                if item.kind in {"course", "meeting", "activity"}
                                else "upcoming"
                            ),
                            notify_at=notify_at,
                            title=self._reminder_title(item),
                            body=self._reminder_body(item, lead_min),
                            event_start_at=item.start_at,
                            event_end_at=item.end_at,
                        )
                    )
            if (
                item.kind == "course"
                and item.start_at.time() < time(9, 0)
            ):
                notify_at = item.start_at - timedelta(
                    minutes=settings.early_course_wakeup_min
                )
                result.append(
                    ReminderCandidate(
                        id=(
                            f"{item.id}:wakeup:"
                            f"{settings.early_course_wakeup_min}"
                        ),
                        agenda_item_id=item.id,
                        kind="wakeup",
                        notify_at=notify_at,
                        title="早课起床提醒",
                        body=(
                            f"今天第一项是 {item.start_at:%H:%M} 的"
                            f"“{item.title}”"
                            + (
                                f"，地点在{item.location_name}"
                                if item.location_name
                                else ""
                            )
                            + "。给自己留一点洗漱、早餐和通勤时间。"
                        ),
                        event_start_at=item.start_at,
                        event_end_at=item.end_at,
                    )
                )
        if user_id and start_date and end_date:
            result.extend(
                self._bedtime_reminders(
                    user_id=user_id,
                    start_date=start_date,
                    end_date=end_date,
                    settings=settings,
                    agenda_items=items,
                )
            )
        return sorted(result, key=lambda item: (item.notify_at, item.id))

    def _bedtime_reminders(
        self,
        *,
        user_id: str,
        start_date: date,
        end_date: date,
        settings: ReminderSettings,
        agenda_items: list[AgendaItem],
    ) -> list[ReminderCandidate]:
        if not settings.bedtime_enabled:
            return []
        memories = {
            item.key: item.value
            for item in self.memories.list(user_id, enabled_only=True)
        }
        bedtime = self._memory_time(memories.get("usual_bedtime"))
        if bedtime is None:
            return []
        wake_time = self._memory_time(memories.get("usual_wake_time"))
        sleep_goal = self._sleep_goal(memories.get("sleep_goal_hours"))
        timezone = ZoneInfo(self.timezone_name)
        result: list[ReminderCandidate] = []
        current_date = start_date
        while current_date <= end_date:
            bedtime_date = (
                current_date + timedelta(days=1)
                if bedtime < time(5, 0)
                else current_date
            )
            bedtime_at = datetime.combine(
                bedtime_date,
                bedtime,
                timezone,
            )
            tomorrow = current_date + timedelta(days=1)
            early_course = min(
                (
                    item
                    for item in agenda_items
                    if item.kind == "course"
                    and item.start_at.date() == tomorrow
                    and item.start_at.time() < time(9, 0)
                ),
                key=lambda item: item.start_at,
                default=None,
            )
            last_evening_item = max(
                (
                    item
                    for item in agenda_items
                    if item.kind != "travel"
                    and item.end_at.date() == bedtime_at.date()
                    and item.end_at > bedtime_at
                ),
                key=lambda item: item.end_at,
                default=None,
            )
            body_parts = [
                f"你平时希望在 {bedtime:%H:%M} 左右休息，"
                "可以开始收尾、洗漱，给大脑一点慢下来的时间。"
            ]
            if last_evening_item:
                body_parts.append(
                    f"不过今晚“{last_evening_item.title}”安排到"
                    f" {last_evening_item.end_at:%H:%M}，"
                    "会比平时睡得晚一些；如果这项必须保留，"
                    "结束后就别再给自己加任务了。"
                )
            if wake_time and sleep_goal:
                body_parts.append(
                    f"按 {wake_time:%H:%M} 起床和约"
                    f"{sleep_goal:g}小时睡眠目标，今晚尽量不要再向后拖。"
                )
            if early_course:
                body_parts.append(
                    f"明天 {early_course.start_at:%H:%M} 还有"
                    f"“{early_course.title}”，早点休息会更从容。"
                )
            result.append(
                ReminderCandidate(
                    id=f"bedtime:{user_id}:{current_date}",
                    agenda_item_id=f"bedtime_habit:{current_date}",
                    kind="bedtime",
                    notify_at=bedtime_at - timedelta(
                        minutes=settings.bedtime_lead_min
                    ),
                    title="该慢慢收一收今天了",
                    body="".join(body_parts),
                    event_start_at=bedtime_at,
                    event_end_at=bedtime_at + timedelta(minutes=15),
                )
            )
            current_date += timedelta(days=1)
        return result

    @staticmethod
    def _memory_time(value: object) -> time | None:
        if not isinstance(value, str):
            return None
        try:
            return time.fromisoformat(value.strip())
        except ValueError:
            return None

    @staticmethod
    def _sleep_goal(value: object) -> float | None:
        if isinstance(value, bool):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if 4 <= result <= 12 else None

    @staticmethod
    def _in_quiet_hours(
        value: datetime,
        settings: ReminderSettings,
    ) -> bool:
        current = value.timetz().replace(tzinfo=None)
        start = settings.quiet_start
        end = settings.quiet_end
        if start == end:
            return False
        if start < end:
            return start <= current < end
        return current >= start or current < end

    @staticmethod
    def _reminder_title(item: AgendaItem) -> str:
        return {
            "course": "快到上课时间了",
            "meeting": "别忘了接下来的会议",
            "activity": (
                "二课报名任务即将开始"
                if "报名" in item.title
                else (
                    "二课活动即将开始"
                    if any(word in item.title for word in ("二课", "第二课堂"))
                    else "活动即将开始"
                )
            ),
            "study": "准备进入专注时段",
            "exercise": "给身体留出的时间要到了",
            "meal": "记得按时吃饭",
            "task": "下一项安排快开始了",
        }[item.kind]

    @staticmethod
    def _reminder_body(item: AgendaItem, lead_min: int) -> str:
        location = (
            f"，地点：{item.location_name}"
            if item.location_name
            else ""
        )
        return (
            f"{lead_min}分钟后开始“{item.title}”"
            f"（{item.start_at:%H:%M}—{item.end_at:%H:%M}）"
            f"{location}。"
        )

    @staticmethod
    def summarize(items: list[AgendaItem]) -> AgendaSummary:
        def minutes(item: AgendaItem) -> int:
            return int((item.end_at - item.start_at).total_seconds() // 60)

        busy_items = [item for item in items if item.kind != "travel"]
        return AgendaSummary(
            course_count=sum(item.kind == "course" for item in items),
            planned_item_count=len(busy_items),
            study_minutes=sum(
                minutes(item)
                for item in items
                if item.kind in {"course", "study"}
            ),
            exercise_minutes=sum(
                minutes(item) for item in items if item.kind == "exercise"
            ),
            meeting_minutes=sum(
                minutes(item) for item in items if item.kind == "meeting"
            ),
            busy_minutes=sum(minutes(item) for item in busy_items),
            earliest_start=(
                min((item.start_at for item in items), default=None)
            ),
            latest_end=max((item.end_at for item in items), default=None),
        )

    def care_suggestions(
        self,
        *,
        items: list[AgendaItem],
        start_date: date,
        end_date: date,
        now: datetime,
    ) -> list[CareSuggestion]:
        if not items:
            return [
                CareSuggestion(
                    id="gentle_empty_agenda",
                    title="今天还留有很多自由空间",
                    content=(
                        "如果你愿意，可以告诉我这段时间最想推进的事；"
                        "也可以什么都不加，给自己留一点真正的休息。"
                    ),
                    level="positive",
                )
            ]
        grouped: dict[date, list[AgendaItem]] = defaultdict(list)
        for item in items:
            grouped[item.start_at.date()].append(item)

        suggestions: list[CareSuggestion] = []
        daily_loads = {
            item_date: self.summarize(day_items)
            for item_date, day_items in grouped.items()
        }
        heavy_dates = [
            item_date
            for item_date, summary in daily_loads.items()
            if summary.study_minutes >= 360
            or summary.busy_minutes >= 540
        ]
        exercise_minutes = sum(
            summary.exercise_minutes for summary in daily_loads.values()
        )
        if heavy_dates and exercise_minutes < 60:
            range_text = (
                "这几天"
                if end_date > start_date
                else "今天"
            )
            suggestions.append(
                CareSuggestion(
                    id="balance_heavy_study",
                    title="给高负荷学习留一点恢复空间",
                    content=(
                        f"{range_text}的课程和学习安排偏密，"
                        "但还没有明显的运动或放松时间。可以考虑加入"
                        "20—30分钟散步、慢跑或拉伸；是否加入由你决定。"
                    ),
                    level="attention",
                    action_query=(
                        "在不移动课程、会议和已有固定安排的前提下，"
                        "为我找一个合适的20到30分钟轻松运动时段；"
                        "如果时间不合适，只给建议，不要强行加入。"
                    ),
                )
            )

        tomorrow = now.date() + timedelta(days=1)
        early_courses = [
            item
            for item in items
            if item.kind == "course"
            and item.start_at.date() == tomorrow
            and item.start_at.time() < time(9, 0)
        ]
        if early_courses:
            first = min(early_courses, key=lambda item: item.start_at)
            suggestions.append(
                CareSuggestion(
                    id=f"early_course_{tomorrow}",
                    title="明天有早课，今晚别把自己拖得太晚",
                    content=(
                        f"明天 {first.start_at:%H:%M} 有“{first.title}”"
                        + (
                            f"，地点在{first.location_name}"
                            if first.location_name
                            else ""
                        )
                        + "。系统会按你的提醒设置提前叫你，今晚也可以"
                        "预留洗漱和入睡缓冲。"
                    ),
                    level="gentle",
                )
            )

        for item_date, day_items in sorted(grouped.items()):
            occupied_lunch = [
                item
                for item in day_items
                if item.kind != "meal"
                and item.start_at.time() < time(12, 40)
                and item.end_at.time() > time(11, 20)
            ]
            has_meal = any(item.kind == "meal" for item in day_items)
            if occupied_lunch and not has_meal:
                suggestions.append(
                    CareSuggestion(
                        id=f"meal_gap_{item_date}",
                        title="午餐时间别被任务悄悄挤掉",
                        content=(
                            f"{item_date:%m月%d日}中午已有安排经过常用"
                            "用餐时段。建议至少留出一段吃饭和短暂休息时间，"
                            "我不会未经确认自动移动你的任务。"
                        ),
                        level="gentle",
                        action_query=(
                            f"请检查{item_date:%Y年%m月%d日}的计划，"
                            "在不移动课程和会议的前提下留出午餐时间；"
                            "如需调整其他任务，先告诉我变化。"
                        ),
                    )
                )
                break
        return suggestions[:3]
