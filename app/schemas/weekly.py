from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Issue


class GoalStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StageStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class WeeklyPlanStatus(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    AT_RISK = "at_risk"
    INFEASIBLE = "infeasible"
    ARCHIVED = "archived"


class AllocationStatus(StrEnum):
    PROPOSED = "proposed"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class CompletionEventType(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    DELAYED = "delayed"
    NEW_TASK = "new_task"


class WeeklyTriggerType(StrEnum):
    INITIAL = "initial"
    DAILY_ROLLOVER = "daily_rollover"
    TASK_INCOMPLETE = "task_incomplete"
    NEW_TASK = "new_task"
    FIXED_EVENT_CHANGED = "fixed_event_changed"
    WEATHER_CHANGED = "weather_changed"
    MANUAL = "manual"


class EnergyLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GoalStageCreate(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    sequence: int = Field(default=1, ge=1, le=100)
    duration_min: int = Field(ge=5, le=10_080)
    depends_on_stage_ids: list[str] = Field(
        default_factory=list,
        max_length=30,
    )
    splittable: bool = True
    min_chunk_min: int = Field(default=30, ge=5, le=480)
    preferred_location: str | None = Field(default=None, max_length=120)
    completion_criteria: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_chunk(self) -> GoalStageCreate:
        self.min_chunk_min = min(self.min_chunk_min, self.duration_min)
        if not self.splittable:
            self.min_chunk_min = self.duration_min
        if self.id and self.id in self.depends_on_stage_ids:
            raise ValueError("阶段不能依赖自身")
        self.depends_on_stage_ids = list(
            dict.fromkeys(self.depends_on_stage_ids)
        )
        return self


class WeeklyGoalCreate(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    earliest_start: datetime | None = None
    deadline: datetime
    total_duration_min: int = Field(ge=5, le=20_160)
    splittable: bool = True
    min_chunk_min: int = Field(default=30, ge=5, le=480)
    max_chunk_min: int = Field(default=120, ge=5, le=720)
    max_chunks_per_day: int = Field(default=2, ge=1, le=8)
    importance: int = Field(default=3, ge=1, le=5)
    hard_deadline: bool = True
    preferred_periods: list[
        Literal["morning", "afternoon", "evening"]
    ] = Field(default_factory=list)
    avoided_periods: list[
        Literal["morning", "afternoon", "evening"]
    ] = Field(default_factory=list)
    preferred_locations: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    stages: list[GoalStageCreate] = Field(
        default_factory=list,
        max_length=50,
    )

    @model_validator(mode="after")
    def validate_goal(self) -> WeeklyGoalCreate:
        values = [
            value
            for value in (self.earliest_start, self.deadline)
            if value is not None
        ]
        if any(value.tzinfo is None for value in values):
            raise ValueError("周目标时间必须包含时区")
        if self.earliest_start and self.deadline <= self.earliest_start:
            raise ValueError("目标截止时间必须晚于最早开始时间")
        if self.min_chunk_min > self.max_chunk_min:
            raise ValueError("最小时间块不能大于最大时间块")
        self.min_chunk_min = min(self.min_chunk_min, self.total_duration_min)
        self.max_chunk_min = min(self.max_chunk_min, self.total_duration_min)
        if not self.splittable:
            self.min_chunk_min = self.total_duration_min
            self.max_chunk_min = self.total_duration_min
            self.max_chunks_per_day = 1
        if self.stages:
            stage_total = sum(stage.duration_min for stage in self.stages)
            if stage_total != self.total_duration_min:
                raise ValueError("各阶段时长之和必须等于目标总时长")
            stage_ids = [stage.id for stage in self.stages if stage.id]
            if len(stage_ids) != len(set(stage_ids)):
                raise ValueError("同一目标内阶段ID不能重复")
            known = set(stage_ids)
            for stage in self.stages:
                unknown = set(stage.depends_on_stage_ids) - known
                if unknown:
                    raise ValueError(
                        f"阶段依赖不存在：{', '.join(sorted(unknown))}"
                    )
        self.preferred_periods = list(
            dict.fromkeys(self.preferred_periods)
        )
        self.avoided_periods = list(dict.fromkeys(self.avoided_periods))
        if set(self.preferred_periods) & set(self.avoided_periods):
            raise ValueError("同一时段不能同时设为偏好和避开")
        return self


class GoalStage(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    lineage_id: str | None = Field(default=None, max_length=80)
    goal_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    sequence: int = Field(ge=1, le=100)
    duration_min: int = Field(ge=5, le=10_080)
    remaining_duration_min: int = Field(ge=0, le=10_080)
    depends_on_stage_ids: list[str] = Field(default_factory=list)
    splittable: bool = True
    min_chunk_min: int = Field(ge=5, le=480)
    preferred_location: str | None = Field(default=None, max_length=120)
    completion_criteria: str | None = Field(default=None, max_length=500)
    status: StageStatus = StageStatus.PENDING
    created_at: datetime
    updated_at: datetime


class WeeklyGoal(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    lineage_id: str | None = Field(default=None, max_length=80)
    user_id: str = Field(min_length=1, max_length=64)
    campus_id: str = Field(min_length=1, max_length=100)
    week_start: date
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    earliest_start: datetime | None = None
    deadline: datetime
    total_duration_min: int = Field(ge=5, le=20_160)
    remaining_duration_min: int = Field(ge=0, le=20_160)
    splittable: bool
    min_chunk_min: int = Field(ge=5, le=480)
    max_chunk_min: int = Field(ge=5, le=720)
    max_chunks_per_day: int = Field(ge=1, le=8)
    importance: int = Field(ge=1, le=5)
    hard_deadline: bool
    preferred_periods: list[str] = Field(default_factory=list)
    avoided_periods: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    energy_level: EnergyLevel
    status: GoalStatus = GoalStatus.PENDING
    source: str = Field(default="user", max_length=40)
    stages: list[GoalStage] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DailyWindow(BaseModel):
    start_at: datetime
    end_at: datetime
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    location_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_window(self) -> DailyWindow:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("每日容量窗口必须包含时区")
        if self.end_at <= self.start_at:
            raise ValueError("每日容量窗口结束时间必须晚于开始时间")
        if self.start_at.date() != self.end_at.date():
            raise ValueError("首版周规划不支持跨零点容量窗口")
        return self

    @property
    def duration_min(self) -> int:
        return int((self.end_at - self.start_at).total_seconds() // 60)


class DailyCapacity(BaseModel):
    date: date
    windows: list[DailyWindow] = Field(default_factory=list, max_length=30)
    reserved_min: int = Field(default=0, ge=0, le=1440)
    notes: list[str] = Field(default_factory=list)

    @property
    def total_available_min(self) -> int:
        return max(
            0,
            sum(window.duration_min for window in self.windows)
            - self.reserved_min,
        )


class WeeklyClockWindow(BaseModel):
    start: time
    end: time
    energy_level: EnergyLevel = EnergyLevel.MEDIUM
    location_id: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def validate_clock_window(self) -> WeeklyClockWindow:
        if self.end <= self.start:
            raise ValueError("周可用时段结束时间必须晚于开始时间")
        return self


class WeekdayAvailability(BaseModel):
    weekday: int = Field(ge=1, le=7)
    windows: list[WeeklyClockWindow] = Field(
        default_factory=list,
        max_length=12,
    )
    max_focus_min: int | None = Field(default=None, ge=30, le=720)
    notes: list[str] = Field(default_factory=list, max_length=10)


class WeeklyAvailabilityProfile(BaseModel):
    days: list[WeekdayAvailability] = Field(min_length=1, max_length=7)
    use_timetable: bool = True
    use_calendar: bool = True
    use_memories: bool = True

    @model_validator(mode="after")
    def validate_days(self) -> WeeklyAvailabilityProfile:
        weekdays = [item.weekday for item in self.days]
        if len(weekdays) != len(set(weekdays)):
            raise ValueError("同一星期不能重复设置可用时段")
        return self


class WeeklyCapacitySummary(BaseModel):
    source: Literal["manual", "personal_context"] = "manual"
    timetable_applied: bool = False
    excluded_course_count: int = Field(default=0, ge=0)
    calendar_adjusted_dates: list[date] = Field(default_factory=list)
    memory_labels: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DayAllocation(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    lineage_id: str | None = Field(default=None, max_length=80)
    source_allocation_id: str | None = Field(default=None, max_length=80)
    weekly_plan_id: str = Field(min_length=1, max_length=80)
    date: date
    goal_id: str = Field(min_length=1, max_length=80)
    stage_id: str = Field(min_length=1, max_length=80)
    allocated_duration_min: int = Field(ge=5, le=720)
    completed_duration_min: int = Field(default=0, ge=0, le=720)
    earliest_start: datetime
    latest_end: datetime
    window_start_at: datetime | None = None
    window_end_at: datetime | None = None
    preferred_start_at: datetime | None = None
    preferred_end_at: datetime | None = None
    preferred_period: str | None = Field(default=None, max_length=40)
    location_id: str | None = Field(default=None, max_length=120)
    priority_score: float = 0
    risk_score: float = 0
    locked: bool = False
    daily_plan_id: str | None = Field(default=None, max_length=80)
    status: AllocationStatus = AllocationStatus.PROPOSED
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_interval(self) -> DayAllocation:
        if self.completed_duration_min > self.allocated_duration_min:
            raise ValueError("分配块已完成时长不能超过分配时长")
        if self.earliest_start.tzinfo is None or self.latest_end.tzinfo is None:
            raise ValueError("每日分配时间必须包含时区")
        if self.latest_end <= self.earliest_start:
            raise ValueError("分配窗口结束时间必须晚于开始时间")
        if self.earliest_start.date() != self.date:
            raise ValueError("分配日期必须与最早开始日期一致")
        available = int(
            (self.latest_end - self.earliest_start).total_seconds() // 60
        )
        if self.allocated_duration_min > available:
            raise ValueError("分配时长不能超过候选时间窗")
        if (self.window_start_at is None) != (self.window_end_at is None):
            raise ValueError("候选窗口开始和结束时间必须同时提供")
        if self.window_start_at and self.window_end_at:
            if (
                self.window_start_at.tzinfo is None
                or self.window_end_at.tzinfo is None
            ):
                raise ValueError("候选窗口必须包含时区")
            if not (
                self.window_start_at
                <= self.earliest_start
                < self.latest_end
                <= self.window_end_at
            ):
                raise ValueError("建议时间必须位于候选窗口内")
            window_duration = int(
                (
                    self.window_end_at - self.window_start_at
                ).total_seconds()
                // 60
            )
            if self.allocated_duration_min > window_duration:
                raise ValueError("分配时长不能超过候选窗口")
        if (self.preferred_start_at is None) != (
            self.preferred_end_at is None
        ):
            raise ValueError("偏好开始和结束时间必须同时提供")
        if self.preferred_start_at and self.preferred_end_at:
            if (
                self.preferred_start_at.tzinfo is None
                or self.preferred_end_at.tzinfo is None
            ):
                raise ValueError("偏好时间必须包含时区")
            if not (
                (self.window_start_at or self.earliest_start)
                <= self.preferred_start_at
                < self.preferred_end_at
                <= (self.window_end_at or self.latest_end)
            ):
                raise ValueError("偏好时间必须位于候选时间窗内")
            preferred_duration = int(
                (
                    self.preferred_end_at - self.preferred_start_at
                ).total_seconds()
                // 60
            )
            if preferred_duration != self.allocated_duration_min:
                raise ValueError("偏好时间长度必须等于分配时长")
        return self


class WeeklyPlanMetrics(BaseModel):
    requested_duration_min: int = Field(default=0, ge=0)
    allocated_duration_min: int = Field(default=0, ge=0)
    unallocated_duration_min: int = Field(default=0, ge=0)
    hard_violation_count: int = Field(default=0, ge=0)
    at_risk_goal_count: int = Field(default=0, ge=0)
    moved_allocation_count: int = Field(default=0, ge=0)
    workload_balance_score: float = Field(default=1, ge=0, le=1)
    preservation_rate: float | None = Field(default=None, ge=0, le=1)


class WeeklyPlan(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    user_id: str = Field(min_length=1, max_length=64)
    campus_id: str = Field(min_length=1, max_length=100)
    week_start: date
    week_end: date
    timezone: str = Field(min_length=1, max_length=80)
    version: int = Field(default=1, ge=1)
    status: WeeklyPlanStatus
    baseline_plan_id: str | None = Field(default=None, max_length=80)
    trigger_type: WeeklyTriggerType = WeeklyTriggerType.INITIAL
    goals: list[WeeklyGoal] = Field(default_factory=list)
    allocations: list[DayAllocation] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    metrics: WeeklyPlanMetrics = Field(default_factory=WeeklyPlanMetrics)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_week(self) -> WeeklyPlan:
        if self.week_start.isoweekday() != 1:
            raise ValueError("week_start 必须是周一")
        if self.week_end != self.week_start.fromordinal(
            self.week_start.toordinal() + 6
        ):
            raise ValueError("week_end 必须是 week_start 后第6天")
        return self


class CompletionEventCreate(BaseModel):
    event_type: CompletionEventType
    allocation_id: str | None = Field(default=None, max_length=80)
    occurred_at: datetime
    completed_duration_min: int = Field(default=0, ge=0, le=720)
    remaining_duration_min: int | None = Field(default=None, ge=0, le=720)
    reason: str | None = Field(default=None, max_length=500)
    client_event_id: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_event(self) -> CompletionEventCreate:
        if self.occurred_at.tzinfo is None:
            raise ValueError("执行事件时间必须包含时区")
        if self.event_type != CompletionEventType.NEW_TASK and not (
            self.allocation_id
        ):
            raise ValueError("该执行事件必须指定 allocation_id")
        if (
            self.event_type
            in {CompletionEventType.COMPLETED, CompletionEventType.PARTIAL}
            and self.completed_duration_min <= 0
        ):
            raise ValueError("完成或部分完成事件必须提供已完成时长")
        return self


class CompletionEvent(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    user_id: str = Field(min_length=1, max_length=64)
    weekly_plan_id: str = Field(min_length=1, max_length=80)
    allocation_id: str | None = Field(default=None, max_length=80)
    event_type: CompletionEventType
    occurred_at: datetime
    completed_duration_min: int = Field(ge=0, le=720)
    remaining_duration_min: int | None = Field(default=None, ge=0, le=720)
    reason: str | None = Field(default=None, max_length=500)
    client_event_id: str = Field(min_length=1, max_length=120)
    created_at: datetime


class WeeklyPlanCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    campus_id: str = Field(min_length=1, max_length=100)
    week_start: date
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    goals: list[WeeklyGoalCreate] = Field(min_length=1, max_length=30)
    capacities: list[DailyCapacity] = Field(default_factory=list, max_length=7)
    availability: WeeklyAvailabilityProfile | None = None

    @model_validator(mode="after")
    def validate_request(self) -> WeeklyPlanCreateRequest:
        if self.week_start.isoweekday() != 1:
            raise ValueError("week_start 必须是周一")
        allowed_dates = {
            self.week_start.fromordinal(self.week_start.toordinal() + offset)
            for offset in range(7)
        }
        capacity_dates = [item.date for item in self.capacities]
        if len(capacity_dates) != len(set(capacity_dates)):
            raise ValueError("同一天不能重复提供容量")
        if not set(capacity_dates) <= allowed_dates:
            raise ValueError("容量日期必须位于目标周内")
        if not self.capacities and self.availability is None:
            raise ValueError(
                "请提供本周可用时间，或提供可结合个人课表生成容量的"
                " availability 设置"
            )
        return self


class WeeklyReplanRequest(BaseModel):
    trigger_type: WeeklyTriggerType = WeeklyTriggerType.MANUAL
    capacities: list[DailyCapacity] = Field(default_factory=list, max_length=7)
    availability: WeeklyAvailabilityProfile | None = None
    invalidated_allocation_ids: list[str] = Field(
        default_factory=list,
        max_length=100,
    )
    additional_goals: list[WeeklyGoalCreate] = Field(
        default_factory=list,
        max_length=10,
    )

    @model_validator(mode="after")
    def validate_replan(self) -> WeeklyReplanRequest:
        if self.trigger_type == WeeklyTriggerType.INITIAL:
            raise ValueError("滚动重排不能使用 initial 触发类型")
        if self.capacities and self.availability is not None:
            raise ValueError("capacities 和 availability 只能提供一种")
        dates = [item.date for item in self.capacities]
        if len(dates) != len(set(dates)):
            raise ValueError("同一天不能重复提供重排容量")
        self.invalidated_allocation_ids = list(
            dict.fromkeys(self.invalidated_allocation_ids)
        )
        if (
            self.trigger_type == WeeklyTriggerType.NEW_TASK
            and not self.additional_goals
        ):
            raise ValueError("new_task 重排必须提供 additional_goals")
        if (
            self.additional_goals
            and self.trigger_type != WeeklyTriggerType.NEW_TASK
        ):
            raise ValueError("additional_goals 只能用于 new_task 重排")
        return self


class WeeklyTextInterpretation(BaseModel):
    goals: list[WeeklyGoalCreate] = Field(default_factory=list, max_length=30)
    clarifications: list[str] = Field(default_factory=list, max_length=5)
    confidence: float = Field(default=0.0, ge=0, le=1)


class WeeklyTextPlanRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    campus_id: str = Field(default="hdu_xiasha", min_length=1, max_length=100)
    query: str = Field(min_length=2, max_length=5000)
    week_start: date
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)
    availability: WeeklyAvailabilityProfile | None = None

    @model_validator(mode="after")
    def validate_week_start(self) -> WeeklyTextPlanRequest:
        if self.week_start.isoweekday() != 1:
            raise ValueError("week_start 必须是周一")
        return self


class WeeklyPlanResponse(BaseModel):
    status: str
    answer: str
    weekly_plan: WeeklyPlan
    capacity_summary: WeeklyCapacitySummary | None = None
    parser: str | None = None
    interpretation: WeeklyTextInterpretation | None = None


class CompletionEventResponse(BaseModel):
    status: str
    applied: bool
    message: str
    event: CompletionEvent
    weekly_plan: WeeklyPlan


class WeeklyPlanVersionsResponse(BaseModel):
    items: list[WeeklyPlan] = Field(default_factory=list)
