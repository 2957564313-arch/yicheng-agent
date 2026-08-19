from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.repositories.academic_calendar import AcademicCalendarRepository
from app.repositories.memories import MemoryRepository
from app.repositories.timetables import TimetableRepository
from app.schemas.weekly import (
    DailyCapacity,
    DailyWindow,
    EnergyLevel,
    WeeklyAvailabilityProfile,
    WeeklyCapacitySummary,
    WeeklyClockWindow,
)


@dataclass(slots=True)
class WeeklyCapacityResult:
    capacities: list[DailyCapacity]
    summary: WeeklyCapacitySummary


class WeeklyCapacityBuilder:
    """Build weekly free-time capacity from a user's own hard constraints.

    The school knowledge base supplies class-period clock times and the
    academic calendar supplies holiday/makeup-day semantics. The user's
    timetable and explicitly enabled memories remain user-scoped data.
    """

    def __init__(
        self,
        *,
        timetables: TimetableRepository,
        memories: MemoryRepository,
        academic_calendar: AcademicCalendarRepository,
        class_periods: dict[int, tuple],
    ) -> None:
        self.timetables = timetables
        self.memories = memories
        self.academic_calendar = academic_calendar
        self.class_periods = class_periods

    def build(
        self,
        *,
        user_id: str,
        week_start: date,
        timezone_name: str,
        profile: WeeklyAvailabilityProfile,
    ) -> WeeklyCapacityResult:
        timezone = ZoneInfo(timezone_name)
        days = {item.weekday: item for item in profile.days}
        enabled_memories = (
            self.memories.list(user_id, enabled_only=True)
            if profile.use_memories
            else []
        )
        memory_values = {item.key: item.value for item in enabled_memories}
        memory_labels: list[str] = []
        preferred_period = memory_values.get("preferred_study_period")
        preferred_location = memory_values.get("preferred_study_location")
        avoided_weekdays = {
            int(value)
            for value in (
                memory_values.get("avoid_weekdays")
                if isinstance(memory_values.get("avoid_weekdays"), list)
                else []
            )
            if str(value).isdigit() and 1 <= int(value) <= 7
        }
        if preferred_period in {"morning", "afternoon", "evening"}:
            memory_labels.append("常用学习时段")
        if isinstance(preferred_location, str) and preferred_location.strip():
            memory_labels.append("常用学习地点")
        if avoided_weekdays:
            memory_labels.append("避开日期偏好")

        capacities: list[DailyCapacity] = []
        excluded_courses = 0
        calendar_adjusted_dates: list[date] = []
        notes: list[str] = []
        timetable = self.timetables.get(user_id)
        timetable_active = bool(
            profile.use_timetable
            and timetable.timetable
            and timetable.timetable.enabled
        )

        for offset in range(7):
            target_date = week_start + timedelta(days=offset)
            day_profile = days.get(target_date.isoweekday())
            if day_profile is None or target_date.isoweekday() in avoided_weekdays:
                capacities.append(
                    DailyCapacity(
                        date=target_date,
                        notes=["这一天未设置可用时段"],
                    )
                )
                continue

            calendar = self.academic_calendar.resolve(
                user_id=user_id,
                target_date=target_date,
            )
            effective_weekday = (
                calendar.effective_weekday
                if profile.use_calendar
                else target_date.isoweekday()
            )
            if profile.use_calendar and (
                calendar.course_action != "normal"
                or effective_weekday != target_date.isoweekday()
            ):
                calendar_adjusted_dates.append(target_date)

            course_tasks = (
                self.timetables.tasks_for_date(
                    user_id=user_id,
                    target_date=target_date,
                    class_periods=self.class_periods,
                    timezone_name=timezone_name,
                    effective_weekday=effective_weekday,
                )
                if timetable_active
                else []
            )
            excluded_courses += len(course_tasks)
            busy = [
                (task.fixed_start, task.fixed_end)
                for task in course_tasks
                if task.fixed_start and task.fixed_end
            ]
            windows: list[DailyWindow] = []
            for raw_window in day_profile.windows:
                start_at = datetime.combine(
                    target_date,
                    raw_window.start,
                    timezone,
                )
                end_at = datetime.combine(
                    target_date,
                    raw_window.end,
                    timezone,
                )
                for free_start, free_end in self._subtract_busy(
                    start_at,
                    end_at,
                    busy,
                ):
                    windows.append(
                        DailyWindow(
                            start_at=free_start,
                            end_at=free_end,
                            energy_level=self._memory_energy(
                                raw_window,
                                preferred_period,
                            ),
                            location_id=(raw_window.location_id),
                        )
                    )
            limit = day_profile.max_focus_min
            if limit:
                windows = self._limit_windows(windows, limit)
            day_notes = list(day_profile.notes)
            if course_tasks:
                day_notes.append(f"已从可用时段中扣除 {len(course_tasks)} 段固定课程")
            if calendar.label:
                day_notes.append(f"校历：{calendar.label}（{calendar.course_action}）")
            capacities.append(
                DailyCapacity(
                    date=target_date,
                    windows=windows,
                    notes=day_notes,
                )
            )

        if timetable_active:
            notes.append("已按个人启用课表扣除本周固定课程")
        else:
            notes.append("尚未启用个人课表，本周容量未扣除课程")
        if memory_labels:
            notes.append("已应用个性化设置：" + "、".join(memory_labels))
        notes.append("课程与学校调整以杭助为准，法定节假日按国家日历解析")
        return WeeklyCapacityResult(
            capacities=capacities,
            summary=WeeklyCapacitySummary(
                source="personal_context",
                timetable_applied=timetable_active,
                excluded_course_count=excluded_courses,
                calendar_adjusted_dates=calendar_adjusted_dates,
                memory_labels=memory_labels,
                notes=notes,
            ),
        )

    @staticmethod
    def _subtract_busy(
        start_at: datetime,
        end_at: datetime,
        busy: Iterable[tuple[datetime, datetime]],
    ) -> list[tuple[datetime, datetime]]:
        free = [(start_at, end_at)]
        for busy_start, busy_end in sorted(busy):
            next_free: list[tuple[datetime, datetime]] = []
            for free_start, free_end in free:
                if busy_end <= free_start or busy_start >= free_end:
                    next_free.append((free_start, free_end))
                    continue
                if busy_start > free_start:
                    next_free.append((free_start, busy_start))
                if busy_end < free_end:
                    next_free.append((busy_end, free_end))
            free = next_free
        return [
            (free_start, free_end)
            for free_start, free_end in free
            if (free_end - free_start).total_seconds() >= 5 * 60
        ]

    @staticmethod
    def _memory_energy(
        window: WeeklyClockWindow,
        preferred_period: object,
    ) -> EnergyLevel:
        if preferred_period == "morning" and window.start.hour < 12:
            return EnergyLevel.HIGH
        if preferred_period == "afternoon" and 12 <= window.start.hour < 18:
            return EnergyLevel.HIGH
        if preferred_period == "evening" and window.start.hour >= 18:
            return EnergyLevel.HIGH
        return window.energy_level

    @staticmethod
    def _limit_windows(
        windows: list[DailyWindow],
        limit_min: int,
    ) -> list[DailyWindow]:
        remaining = limit_min
        result: list[DailyWindow] = []
        ranked = sorted(
            windows,
            key=lambda item: (
                {
                    EnergyLevel.HIGH: 0,
                    EnergyLevel.MEDIUM: 1,
                    EnergyLevel.LOW: 2,
                }[item.energy_level],
                item.start_at,
            ),
        )
        for window in ranked:
            if remaining < 5:
                break
            duration = min(window.duration_min, remaining)
            result.append(
                window.model_copy(
                    update={"end_at": window.start_at + timedelta(minutes=duration)}
                )
            )
            remaining -= duration
        return sorted(result, key=lambda item: item.start_at)
