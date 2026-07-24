from __future__ import annotations

from datetime import datetime

from app.schemas.common import (
    Issue,
    IssueSeverity,
    PlanStatus,
    TaskFlexibility,
)
from app.schemas.plan import Plan, PlanItem, PlanMetrics
from app.schemas.task import Task
from app.services.scheduler import PlanningContext


class PlanValidator:
    def validate(
        self,
        *,
        plan: Plan,
        tasks: list[Task],
        context: PlanningContext,
    ) -> tuple[Plan, list[Issue]]:
        issues: list[Issue] = []
        issues.extend(self._check_overlaps(plan.items))
        issues.extend(self._check_task_coverage(plan.items, tasks))
        issues.extend(self._check_task_time_windows(plan.items, tasks))
        issues.extend(self._check_deadlines(plan.items, tasks))
        issues.extend(self._check_opening_hours(plan.items, context))
        issues.extend(self._check_travel(plan.items, context))
        issues.extend(self._check_congestion(plan.items))
        issues.extend(self._check_weather(plan.items, tasks, context))
        issues.extend(
            self._check_locked_tasks(
                plan.items,
                tasks,
                context.old_plan.items if context.old_plan else [],
            )
        )

        metrics = self._calculate_metrics(
            plan=plan,
            tasks=tasks,
            issues=issues,
            context=context,
            old_plan=context.old_plan,
        )
        plan.status = (
            PlanStatus.INFEASIBLE
            if any(issue.severity == IssueSeverity.ERROR for issue in issues)
            else PlanStatus.VALID
        )
        plan.warnings = issues
        plan.metrics = metrics
        return plan, issues

    @staticmethod
    def _task_items(items: list[PlanItem]) -> list[PlanItem]:
        return sorted(
            [item for item in items if item.item_type == "task"],
            key=lambda item: item.start_at,
        )

    def _check_overlaps(self, items: list[PlanItem]) -> list[Issue]:
        ordered = sorted(items, key=lambda item: item.start_at)
        issues = []
        for previous, current in zip(ordered, ordered[1:]):
            if current.start_at < previous.end_at:
                issues.append(
                    Issue(
                        code="TIME_OVERLAP",
                        severity=IssueSeverity.ERROR,
                        message=(
                            f"{previous.title}与{current.title}时间重叠"
                        ),
                        task_ids=[
                            value
                            for value in (
                                previous.task_id,
                                current.task_id,
                            )
                            if value
                        ],
                        details={
                            "previous_end": previous.end_at.isoformat(),
                            "current_start": current.start_at.isoformat(),
                        },
                    )
                )
        return issues

    def _check_weather(
        self,
        items: list[PlanItem],
        tasks: list[Task],
        context: PlanningContext,
    ) -> list[Issue]:
        if not context.enforce_weather:
            return []
        risk_starts = [
            item.risk_start_at
            for item in context.weather
            if item.risk_start_at
            and (
                (item.rain_probability or 0) >= 0.5
                or "rain" in (item.condition or "").lower()
                or "雨" in (item.condition or "")
            )
        ]
        if not risk_starts:
            return []
        risk_start = min(risk_starts)
        task_by_id = {task.id: task for task in tasks}
        issues = []
        for item in self._task_items(items):
            task = task_by_id.get(item.task_id or "")
            is_outdoor = (
                item.location_id in context.outdoor_location_ids
                or (task is not None and "outdoor" in task.tags)
            )
            if is_outdoor and item.end_at > risk_start:
                issues.append(
                    Issue(
                        code="WEATHER_RISK",
                        severity=IssueSeverity.ERROR,
                        message=(
                            f"室外任务“{item.title}”与降雨风险时段重叠"
                        ),
                        task_ids=[item.task_id] if item.task_id else [],
                        details={
                            "risk_start_at": risk_start.isoformat(),
                        },
                    )
                )
        return issues

    def _check_task_coverage(
        self,
        items: list[PlanItem],
        tasks: list[Task],
    ) -> list[Issue]:
        scheduled = {
            item.task_id
            for item in items
            if item.item_type == "task" and item.task_id
        }
        return [
            Issue(
                code="TASK_UNSCHEDULED",
                severity=IssueSeverity.ERROR,
                message=f"任务“{task.title}”未能安排",
                task_ids=[task.id],
                recoverable=True,
            )
            for task in tasks
            if task.id not in scheduled
        ]

    def _check_deadlines(
        self,
        items: list[PlanItem],
        tasks: list[Task],
    ) -> list[Issue]:
        item_by_task = {
            item.task_id: item
            for item in items
            if item.item_type == "task" and item.task_id
        }
        issues = []
        for task in tasks:
            item = item_by_task.get(task.id)
            if item and task.deadline and item.end_at > task.deadline:
                issues.append(
                    Issue(
                        code="DEADLINE_MISSED",
                        severity=IssueSeverity.ERROR,
                        message=f"任务“{task.title}”超过截止时间",
                        task_ids=[task.id],
                        details={
                            "deadline": task.deadline.isoformat(),
                            "actual_end": item.end_at.isoformat(),
                        },
                    )
                )
        return issues

    def _check_task_time_windows(
        self,
        items: list[PlanItem],
        tasks: list[Task],
    ) -> list[Issue]:
        item_by_task = {
            item.task_id: item
            for item in items
            if item.item_type == "task" and item.task_id
        }
        issues: list[Issue] = []
        for task in tasks:
            item = item_by_task.get(task.id)
            if item is None:
                continue
            if (
                task.fixed_start is not None
                and task.fixed_end is not None
                and (
                    item.start_at != task.fixed_start
                    or item.end_at != task.fixed_end
                )
            ):
                issues.append(
                    Issue(
                        code="FIXED_TIME_CHANGED",
                        severity=IssueSeverity.ERROR,
                        message=f"固定任务“{task.title}”的时间被改变",
                        task_ids=[task.id],
                        recoverable=False,
                    )
                )
            if (
                task.earliest_start is not None
                and item.start_at < task.earliest_start
            ):
                issues.append(
                    Issue(
                        code="EARLIEST_START_VIOLATION",
                        severity=IssueSeverity.ERROR,
                        message=f"任务“{task.title}”早于允许开始时间",
                        task_ids=[task.id],
                    )
                )
            if task.latest_end is not None and item.end_at > task.latest_end:
                issues.append(
                    Issue(
                        code="LATEST_END_VIOLATION",
                        severity=IssueSeverity.ERROR,
                        message=f"任务“{task.title}”晚于允许结束时间",
                        task_ids=[task.id],
                    )
                )
        return issues

    def _check_opening_hours(
        self,
        items: list[PlanItem],
        context: PlanningContext,
    ) -> list[Issue]:
        issues = []
        for item in self._task_items(items):
            if not item.location_id:
                continue
            if item.location_id not in context.opening_windows:
                continue
            windows = context.opening_windows[item.location_id]
            if not any(
                start <= item.start_at and item.end_at <= end
                for start, end in windows
            ):
                issues.append(
                    Issue(
                        code="OUTSIDE_OPENING_HOURS",
                        severity=IssueSeverity.ERROR,
                        message=f"“{item.title}”不在场所开放时段内",
                        task_ids=[item.task_id] if item.task_id else [],
                    )
                )
        return issues

    def _check_travel(
        self,
        items: list[PlanItem],
        context: PlanningContext,
    ) -> list[Issue]:
        tasks = self._task_items(items)
        issues = []
        for previous, current in zip(tasks, tasks[1:]):
            if (
                not previous.location_id
                or not current.location_id
                or previous.location_id == current.location_id
            ):
                continue
            estimate = context.travel.get(
                (previous.location_id, current.location_id)
            )
            if not estimate:
                issues.append(
                    Issue(
                        code="MISSING_TRAVEL_ESTIMATE",
                        severity=IssueSeverity.ERROR,
                        message=(
                            f"缺少{previous.location_id}到"
                            f"{current.location_id}的通勤数据"
                        ),
                        task_ids=[
                            value
                            for value in (
                                previous.task_id,
                                current.task_id,
                            )
                            if value
                        ],
                    )
                )
                continue
            available = int(
                (current.start_at - previous.end_at).total_seconds() // 60
            )
            required, congestion_delay = context.travel_details(
                previous.location_id,
                current.location_id,
                departure_at=previous.end_at,
            )
            if required is None:
                continue
            if available < required:
                issues.append(
                    Issue(
                        code="INSUFFICIENT_TRAVEL_TIME",
                        severity=IssueSeverity.ERROR,
                        message=(
                            f"{previous.title}到{current.title}"
                            "之间通勤时间不足"
                        ),
                        task_ids=[
                            value
                            for value in (
                                previous.task_id,
                                current.task_id,
                            )
                            if value
                        ],
                        details={
                            "required_min": required,
                            "available_min": available,
                            "base_min": (
                                estimate.base_duration_min
                                if estimate.base_duration_min is not None
                                else estimate.duration_min
                            ),
                            "congestion_delay_min": congestion_delay,
                        },
                    )
                )
        return issues

    @staticmethod
    def _check_congestion(items: list[PlanItem]) -> list[Issue]:
        affected = [
            item
            for item in items
            if (
                item.item_type == "travel"
                and item.congestion_delay_min > 0
            )
        ]
        if not affected:
            return []
        total_delay = sum(item.congestion_delay_min for item in affected)
        return [
            Issue(
                code="PEAK_CONGESTION",
                severity=IssueSeverity.WARNING,
                message=(
                    f"有 {len(affected)} 段通勤经过校园集中通行时段，"
                    f"已额外预留 {total_delay} 分钟；如时间允许可选择错峰"
                ),
                details={
                    "affected_travel_count": len(affected),
                    "extra_minutes": total_delay,
                },
            )
        ]

    def _check_locked_tasks(
        self,
        items: list[PlanItem],
        tasks: list[Task],
        old_items: list[PlanItem],
    ) -> list[Issue]:
        current = {
            item.task_id: item
            for item in self._task_items(items)
            if item.task_id
        }
        old = {
            item.task_id: item
            for item in self._task_items(old_items)
            if item.task_id
        }
        issues = []
        for task in tasks:
            if task.flexibility != TaskFlexibility.LOCKED:
                continue
            old_item = old.get(task.id)
            current_item = current.get(task.id)
            if (
                old_item
                and current_item
                and (
                    old_item.start_at != current_item.start_at
                    or old_item.end_at != current_item.end_at
                )
            ):
                issues.append(
                    Issue(
                        code="LOCKED_TASK_MOVED",
                        severity=IssueSeverity.ERROR,
                        message=f"锁定任务“{task.title}”被移动",
                        task_ids=[task.id],
                        recoverable=False,
                    )
                )
        return issues

    def _calculate_metrics(
        self,
        *,
        plan: Plan,
        tasks: list[Task],
        issues: list[Issue],
        context: PlanningContext,
        old_plan: Plan | None,
    ) -> PlanMetrics:
        task_items = self._task_items(plan.items)
        travel_minutes = sum(
            int((item.end_at - item.start_at).total_seconds() // 60)
            for item in plan.items
            if item.item_type == "travel"
        )
        buffer_minutes = 0
        for previous, current in zip(task_items, task_items[1:]):
            required = 0
            if previous.location_id and current.location_id:
                required = (
                    context.travel_minutes(
                        previous.location_id,
                        current.location_id,
                        departure_at=previous.end_at,
                    )
                    or 0
                )
            gap = max(
                0,
                int(
                    (current.start_at - previous.end_at).total_seconds() // 60
                ),
            )
            buffer_minutes += max(0, gap - required)

        moved_task_count = 0
        total_shift_minutes = 0
        preservation_rate = None
        if old_plan:
            old_by_task = {
                item.task_id: item
                for item in self._task_items(old_plan.items)
                if item.task_id
            }
            comparable = 0
            preserved = 0
            for item in task_items:
                if not item.task_id or item.task_id not in old_by_task:
                    continue
                comparable += 1
                old_item = old_by_task[item.task_id]
                shift = int(
                    abs((item.start_at - old_item.start_at).total_seconds())
                    // 60
                )
                total_shift_minutes += shift
                if shift:
                    moved_task_count += 1
                else:
                    preserved += 1
            if comparable:
                preservation_rate = preserved / comparable

        return PlanMetrics(
            hard_violation_count=sum(
                issue.severity == IssueSeverity.ERROR for issue in issues
            ),
            scheduled_task_count=len(task_items),
            requested_task_count=len(tasks),
            travel_minutes=travel_minutes,
            buffer_minutes=buffer_minutes,
            moved_task_count=moved_task_count,
            total_shift_minutes=total_shift_minutes,
            preservation_rate=preservation_rate,
            score=(
                100
                - 100
                * sum(
                    issue.severity == IssueSeverity.ERROR for issue in issues
                )
                - moved_task_count * 2
                - travel_minutes * 0.1
            ),
        )
