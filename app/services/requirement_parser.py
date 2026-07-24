from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.schemas.common import Intent, TaskFlexibility, TransportMode
from app.schemas.plan import Plan
from app.schemas.task import Task, UserPreferences
from app.schemas.understand import UnderstandResult


CHINESE_NUMBER_HOURS = {
    "半": 0.5,
    "一": 1,
    "一个": 1,
    "两": 2,
    "两个": 2,
    "三": 3,
    "三个": 3,
    "四": 4,
    "四个": 4,
}

CHINESE_PERIOD_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
    "十三": 13,
}


class RuleBasedRequirementParser:
    """离线解析器。

    它保证三个比赛 Demo 在不配置模型时可运行，不替代在线模型对复杂
    口语的理解。无法可靠确认的信息会保留为默认值或澄清问题。
    """

    def __init__(
        self,
        timezone_name: str = "Asia/Shanghai",
        class_periods_path: Path | None = None,
    ) -> None:
        self.timezone = ZoneInfo(timezone_name)
        self.class_periods = self._load_class_periods(class_periods_path)

    def parse(
        self,
        *,
        query: str,
        now: datetime,
        old_plan: Plan | None = None,
    ) -> UnderstandResult:
        target_date = self._target_date(query, now, old_plan)
        if (
            old_plan is None
            and self._is_knowledge_query(query)
        ):
            intent = Intent.QUERY
        elif old_plan and any(
            keyword in query
            for keyword in ("天气", "下雨", "降雨", "受天气影响")
        ):
            intent = Intent.WEATHER_CHECK
        elif old_plan or any(
            keyword in query
            for keyword in (
                "重新安排",
                "重新规划",
                "延迟",
                "延长",
                "不要动",
                "保持",
                "调整",
            )
        ):
            intent = Intent.REPLAN
        else:
            intent = Intent.PLAN

        if intent in {Intent.REPLAN, Intent.WEATHER_CHECK} and old_plan is None:
            return UnderstandResult(
                intent=intent,
                requested_date=target_date,
                tasks=[],
                preferences=UserPreferences(),
                clarifications=[
                    "当前没有可调整的计划，请先生成一份计划或提供原计划。"
                ],
                confidence=0.95,
            )

        if intent == Intent.QUERY:
            tasks, preferences = [], UserPreferences()
        elif intent in {Intent.REPLAN, Intent.WEATHER_CHECK} and old_plan:
            tasks, preferences = self._tasks_from_old_plan(
                query=query,
                old_plan=old_plan,
                intent=intent,
            )
        else:
            tasks, preferences = self._extract_plan_tasks(
                query=query,
                target_date=target_date,
            )

        clarifications = []
        if not tasks and intent != Intent.QUERY:
            clarifications.append("请告诉我需要安排的具体任务。")
        return UnderstandResult(
            intent=intent,
            requested_date=target_date,
            tasks=tasks,
            preferences=preferences,
            clarifications=clarifications,
            confidence=(
                0.9
                if intent == Intent.QUERY
                else (0.92 if tasks else 0.2)
            ),
        )

    @staticmethod
    def _is_knowledge_query(query: str) -> bool:
        if any(
            re.search(pattern, query)
            for pattern in (
                r"课表",
                r"哪几节.*课",
                r"(?:有|没|没有)课吗",
                r"有没有课",
                r"是否有课",
            )
        ):
            return True
        planning_keywords = (
            "安排",
            "规划",
            "自习",
            "学习",
            "取快递",
            "拿快递",
            "跑步",
            "运动",
            "吃饭",
        )
        if any(keyword in query for keyword in planning_keywords):
            return False
        return any(
            keyword in query
            for keyword in (
                "几点",
                "什么时候",
                "开放时间",
                "关门",
                "门禁",
                "规定",
                "制度",
                "学生手册",
                "处分",
                "作弊",
                "奖学金",
                "推免",
                "学分",
                "请假",
            )
        )

    def _target_date(
        self,
        query: str,
        now: datetime,
        old_plan: Plan | None,
    ) -> date:
        if old_plan:
            return old_plan.date
        explicit = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", query)
        if explicit:
            return date(
                int(explicit.group(1)),
                int(explicit.group(2)),
                int(explicit.group(3)),
            )
        if "后天" in query:
            return now.date() + timedelta(days=2)
        if "明天" in query:
            return now.date() + timedelta(days=1)
        return now.date()

    def _extract_plan_tasks(
        self,
        *,
        query: str,
        target_date: date,
    ) -> tuple[list[Task], UserPreferences]:
        course_tasks = self._course_tasks(query, target_date)
        fixed_tasks = self._fixed_arrangement_tasks(query, target_date)
        fixed_text = " ".join(task.title for task in fixed_tasks)
        tasks: list[Task] = []
        overall_start = self._overall_start(query)
        if (
            course_tasks
            and any(keyword in query for keyword in ("下课后", "课后"))
        ):
            last_course_end = max(
                task.fixed_end for task in course_tasks if task.fixed_end
            )
            overall_start = last_course_end.time()
        overall_deadline = self._overall_deadline(query, target_date)
        if (
            ("自习" in query or "学习" in query)
            and not any(word in fixed_text for word in ("自习", "学习"))
        ):
            study_keyword = "自习" if "自习" in query else "学习"
            study_deadline = self._task_deadline(
                query,
                target_date,
                ("自习", "学习"),
            )
            study_limit = study_deadline or overall_deadline
            duration = self._duration_near(
                query,
                study_keyword,
                default=120,
            )
            tasks.append(
                self._movable_task(
                    task_id="study",
                    title="图书馆自习",
                    target_date=target_date,
                    duration=duration,
                    location_raw="图书馆",
                    earliest=(
                        overall_start
                        or (time(13, 0) if "下午" in query else time(8, 0))
                    ),
                    latest=(
                        study_limit.time()
                        if study_limit
                        else time(22, 30)
                    ),
                    deadline=(
                        study_limit.time()
                        if study_limit
                        else None
                    ),
                    preferred_period=(
                        "afternoon"
                        if "下午" in query and overall_start is None
                        else None
                    ),
                    importance=5,
                )
            )
        if (
            not any(word in fixed_text for word in ("快递", "驿站"))
            and any(
            keyword in query
            for keyword in ("取快递", "拿快递", "去快递站", "取件")
            )
        ):
            (
                parcel_title,
                parcel_location,
                service_open,
                service_close,
            ) = self._courier_profile(query)
            stated_closing_hour = self._closing_hour(query)
            scoped_parcel_deadline = self._task_deadline(
                query,
                target_date,
                ("取快递", "拿快递", "快递", "取件"),
            )
            parcel_limit = scoped_parcel_deadline or overall_deadline
            parcel_latest = (
                parcel_limit.time()
                if parcel_limit
                else (
                    time(stated_closing_hour, 0)
                    if stated_closing_hour is not None
                    else service_close
                )
            )
            parcel_deadline = (
                parcel_limit.time()
                if parcel_limit
                else (
                    time(stated_closing_hour, 0)
                    if stated_closing_hour is not None
                    else (
                        service_close
                        if parcel_location != "快递站"
                        else None
                    )
                )
            )
            tasks.append(
                self._movable_task(
                    task_id="parcel",
                    title=parcel_title,
                    target_date=target_date,
                    duration=30,
                    location_raw=parcel_location,
                    earliest=(
                        overall_start
                        or (
                            time(13, 0)
                            if "下午" in query
                            else service_open
                        )
                    ),
                    latest=parcel_latest,
                    deadline=parcel_deadline,
                    importance=4,
                )
            )
            tasks[-1] = tasks[-1].model_copy(
                update={
                    "tags": ["courier", "service_hours", "hard_constraint"],
                    "notes": (
                        f"{parcel_location}营业时间为"
                        f"{service_open:%H:%M}—{service_close:%H:%M}，"
                        "属于已核验的场所开放硬约束"
                    ),
                }
            )
        if (
            not any(word in fixed_text for word in ("晚饭", "吃饭", "食堂"))
            and any(keyword in query for keyword in ("吃晚饭", "晚饭", "吃饭"))
        ):
            tasks.append(
                self._movable_task(
                    task_id="dinner",
                    title="吃晚饭",
                    target_date=target_date,
                    duration=45,
                    location_raw="食堂",
                    earliest=time(17, 0),
                    latest=time(20, 0),
                    preferred_period="evening",
                    importance=3,
                )
            )
        if (
            not any(word in fixed_text for word in ("跑步", "运动"))
            and any(keyword in query for keyword in ("跑步", "运动"))
        ):
            run_deadline = self._task_deadline(
                query,
                target_date,
                ("跑步", "运动"),
            )
            run_limit = run_deadline or overall_deadline
            tasks.append(
                self._movable_task(
                    task_id="run",
                    title="跑步",
                    target_date=target_date,
                    duration=self._duration_near(
                        query,
                        "跑步" if "跑步" in query else "运动",
                        default=30,
                    ),
                    location_raw="操场",
                    earliest=(
                        overall_start
                        or (time(18, 0) if "晚上" in query else time(8, 0))
                    ),
                    latest=(
                        run_limit.time()
                        if run_limit
                        else time(22, 0)
                    ),
                    deadline=(
                        run_limit.time()
                        if run_limit
                        else None
                    ),
                    preferred_period="evening" if "晚上" in query else None,
                    importance=3,
                )
            )
            tasks[-1] = tasks[-1].model_copy(
                update={"tags": ["outdoor", "exercise"]}
            )

        tasks = self._apply_explicit_order(query, tasks)
        tasks = self._link_movables_across_fixed_tasks(
            query,
            fixed_tasks,
            tasks,
        )
        return [*course_tasks, *fixed_tasks, *tasks], UserPreferences(
            buffer_min=0 if overall_deadline else 10,
            transport_mode=self.transport_mode_from_query(query),
            avoid_congestion=self.avoid_congestion_from_query(query),
        )

    @staticmethod
    def _link_movables_across_fixed_tasks(
        query: str,
        fixed_tasks: list[Task],
        movable_tasks: list[Task],
    ) -> list[Task]:
        """Keep an explicitly narrated order when a fixed event is in between."""
        if not fixed_tasks or not movable_tasks:
            return movable_tasks

        known_keywords = {
            "study": ("自习", "学习"),
            "parcel": ("取快递", "拿快递", "快递"),
            "dinner": ("吃晚饭", "晚饭", "吃饭"),
            "run": ("跑步", "运动"),
        }

        def position(task: Task) -> int:
            candidates = list(known_keywords.get(task.id, ()))
            compact_title = re.sub(
                r"^(?:参加|进行|前往|去)",
                "",
                task.title,
            )
            candidates.extend((task.title, compact_title))
            positions = [
                query.find(candidate)
                for candidate in candidates
                if candidate and query.find(candidate) >= 0
            ]
            return min(positions) if positions else len(query)

        sequence = sorted(
            [*fixed_tasks, *movable_tasks],
            key=position,
        )
        previous_id: str | None = None
        updates: dict[str, Task] = {}
        for index, task in enumerate(sequence):
            if task.flexibility == TaskFlexibility.MOVABLE:
                next_fixed = next(
                    (
                        candidate
                        for candidate in sequence[index + 1 :]
                        if (
                            candidate.flexibility
                            in {
                                TaskFlexibility.FIXED,
                                TaskFlexibility.LOCKED,
                            }
                            and candidate.fixed_start is not None
                        )
                    ),
                    None,
                )
                latest_end = task.latest_end
                if next_fixed is not None:
                    latest_end = min(
                        value
                        for value in (latest_end, next_fixed.fixed_start)
                        if value is not None
                    )
                updates[task.id] = task.model_copy(
                    update={
                        "depends_on": [previous_id] if previous_id else [],
                        "latest_end": latest_end,
                    }
                )
            previous_id = task.id
        return [updates.get(task.id, task) for task in movable_tasks]

    def _fixed_arrangement_tasks(
        self,
        query: str,
        target_date: date,
    ) -> list[Task]:
        """Extract explicit clock-time blocks as immutable user facts.

        Examples include “15:00到16:30开会” and “下午3点到4点做实验”。
        A concrete interval is stronger than a soft preference, so the
        scheduler must plan around it instead of moving it.
        """
        clock = (
            r"(?P<{period}>上午|中午|下午|晚上)?\s*"
            r"(?P<{hour}>\d{{1,2}})"
            r"(?:(?:\s*[:：]\s*(?P<{minute}>\d{{1,2}}))|"
            r"(?:\s*点(?:\s*(?P<{minute_point}>\d{{1,2}})\s*分)?))"
        )
        pattern = re.compile(
            clock.format(
                period="period1",
                hour="hour1",
                minute="minute1",
                minute_point="minute_point1",
            )
            + r"\s*(?:到|至|[-—~～])\s*"
            + clock.format(
                period="period2",
                hour="hour2",
                minute="minute2",
                minute_point="minute_point2",
            )
        )
        marker_words = (
            "有",
            "固定",
            "安排",
            "开会",
            "会议",
            "实验",
            "活动",
            "考试",
            "值班",
            "面试",
            "训练",
            "课程",
            "上课",
            "自习",
            "学习",
            "跑步",
            "运动",
            "吃饭",
            "取快递",
        )
        tasks: list[Task] = []
        for index, match in enumerate(pattern.finditer(query), start=1):
            clause_start = max(
                query.rfind(separator, 0, match.start())
                for separator in ("，", "。", "；", ",", ";")
            )
            following_boundaries = [
                position
                for separator in ("，", "。", "；", ",", ";")
                if (position := query.find(separator, match.end())) >= 0
            ]
            clause_end = min(following_boundaries, default=len(query))
            clause = query[clause_start + 1 : clause_end].strip()
            if not any(word in clause for word in marker_words):
                continue
            start_time = self._clock_from_groups(match, "1")
            end_time = self._clock_from_groups(
                match,
                "2",
                inherited_period=match.group("period1"),
            )
            if start_time is None or end_time is None:
                continue
            start_at = datetime.combine(target_date, start_time, self.timezone)
            end_at = datetime.combine(target_date, end_time, self.timezone)
            if end_at <= start_at:
                continue
            title = pattern.sub("", clause, count=1)
            title = re.sub(
                r"^(?:今天|明天|后天)?\s*(?:我)?\s*"
                r"(?:固定|已经安排|安排|有|要|需要|去|在)*\s*",
                "",
                title,
            ).strip(" ，。；、")
            title = title or "固定安排"
            location = next(
                (
                    name
                    for name in (
                        "第六教学楼",
                        "图书馆",
                        "菜鸟驿站",
                        "快递站",
                        "东操场",
                        "体育馆",
                        "实验室",
                        "食堂",
                    )
                    if name in clause
                ),
                None,
            )
            if location:
                title = re.sub(
                    rf"^(?:在|去)?{re.escape(location)}",
                    "",
                    title,
                ).strip()
            title = re.sub(r"^固定", "", title).strip() or "固定安排"
            tasks.append(
                Task(
                    id=(
                        f"fixed_{start_time:%H%M}_{end_time:%H%M}_{index}"
                    ),
                    title=title[:120],
                    date=target_date,
                    duration_min=int(
                        (end_at - start_at).total_seconds() // 60
                    ),
                    location_raw=location,
                    fixed_start=start_at,
                    fixed_end=end_at,
                    flexibility=TaskFlexibility.FIXED,
                    importance=5,
                    tags=["user_fixed", "hard_constraint"],
                    notes="用户明确给出的固定时间安排，不可被规划器移动",
                )
            )
        return tasks

    @staticmethod
    def _clock_from_groups(
        match: re.Match[str],
        suffix: str,
        inherited_period: str | None = None,
    ) -> time | None:
        period = match.group(f"period{suffix}") or inherited_period
        hour = int(match.group(f"hour{suffix}"))
        minute = int(
            match.group(f"minute{suffix}")
            or match.group(f"minute_point{suffix}")
            or 0
        )
        if period in {"下午", "晚上"} and 1 <= hour <= 11:
            hour += 12
        elif period == "中午" and 1 <= hour <= 10:
            hour += 12
        elif period == "上午" and hour == 12:
            hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return time(hour, minute)

    @staticmethod
    def _load_class_periods(
        path: Path | None,
    ) -> dict[int, tuple[time, time]]:
        if path is None or not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        result: dict[int, tuple[time, time]] = {}
        for item in payload.get("class_periods", []):
            try:
                result[int(item["period"])] = (
                    time.fromisoformat(item["start"]),
                    time.fromisoformat(item["end"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _period_number(raw: str) -> int | None:
        value = raw.strip()
        if value.isdigit():
            return int(value)
        return CHINESE_PERIOD_NUMBERS.get(value)

    def _course_tasks(
        self,
        query: str,
        target_date: date,
    ) -> list[Task]:
        """Convert stated class periods into deterministic fixed blocks."""
        if not self.class_periods or not re.search(
            r"第?\s*(?:1[0-3]|[1-9]|十三|十二|十一|十|"
            r"[一二三四五六七八九])(?:\s*(?:到|至|[-—~～、,，])"
            r"\s*第?\s*(?:1[0-3]|[1-9]|十三|十二|十一|十|"
            r"[一二三四五六七八九]))?\s*节",
            query,
        ):
            return []

        number = r"(?:1[0-3]|[1-9]|十三|十二|十一|十|[一二三四五六七八九])"
        periods: set[int] = set()
        covered_spans: list[tuple[int, int]] = []
        range_pattern = re.compile(
            rf"第?\s*({number})\s*(?:到|至|[-—~～])\s*"
            rf"第?\s*({number})\s*节"
        )
        for match in range_pattern.finditer(query):
            start = self._period_number(match.group(1))
            end = self._period_number(match.group(2))
            if start is None or end is None:
                continue
            lower, upper = sorted((start, end))
            periods.update(range(lower, upper + 1))
            covered_spans.append(match.span())

        list_pattern = re.compile(
            rf"第\s*({number}(?:\s*[、,，]\s*{number})+)\s*节"
        )
        for match in list_pattern.finditer(query):
            covered_spans.append(match.span())
            for raw in re.split(r"\s*[、,，]\s*", match.group(1)):
                value = self._period_number(raw)
                if value is not None:
                    periods.add(value)

        single_pattern = re.compile(rf"第\s*({number})\s*节")
        for match in single_pattern.finditer(query):
            if any(
                start <= match.start() and match.end() <= end
                for start, end in covered_spans
            ):
                continue
            value = self._period_number(match.group(1))
            if value is not None:
                periods.add(value)

        valid_periods = sorted(
            period for period in periods if period in self.class_periods
        )
        if not valid_periods:
            return []

        groups: list[list[int]] = []
        for period in valid_periods:
            if groups and period == groups[-1][-1] + 1:
                groups[-1].append(period)
            else:
                groups.append([period])

        tasks: list[Task] = []
        for group in groups:
            first, last = group[0], group[-1]
            start_at = datetime.combine(
                target_date,
                self.class_periods[first][0],
                self.timezone,
            )
            end_at = datetime.combine(
                target_date,
                self.class_periods[last][1],
                self.timezone,
            )
            title = (
                f"第{first}节课程"
                if first == last
                else f"第{first}—{last}节课程"
            )
            tasks.append(
                Task(
                    id=f"course_{first}_{last}",
                    title=title,
                    date=target_date,
                    duration_min=int(
                        (end_at - start_at).total_seconds() // 60
                    ),
                    fixed_start=start_at,
                    fixed_end=end_at,
                    flexibility=TaskFlexibility.FIXED,
                    importance=5,
                    tags=["course", "verified_timetable", "hard_constraint"],
                    notes="依据已核验校内上课时间表锁定，不可被规划器移动",
                )
            )
        return tasks

    def _tasks_from_old_plan(
        self,
        *,
        query: str,
        old_plan: Plan,
        intent: Intent,
    ) -> tuple[list[Task], UserPreferences]:
        tasks = []
        locked_ids = []
        old_task_items = [
            item
            for item in sorted(old_plan.items, key=lambda value: value.start_at)
            if item.item_type == "task" and item.task_id
        ]
        overall_deadline = self._overall_deadline(query, old_plan.date)
        study_extension = self._extension_minutes(query)
        for index, item in enumerate(old_task_items):
            if item.item_type != "task" or not item.task_id:
                continue
            duration = int(
                (item.end_at - item.start_at).total_seconds() // 60
            )
            title = item.title
            if (
                intent == Intent.REPLAN
                and ("自习" in title or "学习" in title)
                and study_extension
            ):
                start_at = item.start_at
                end_at = item.end_at + timedelta(
                    minutes=study_extension
                )
                duration += study_extension
                flexibility = TaskFlexibility.FIXED
            elif "实验课" in title and "延迟一小时" in query:
                start_at = item.start_at + timedelta(hours=1)
                end_at = item.end_at + timedelta(hours=1)
                flexibility = TaskFlexibility.FIXED
            elif (
                ("跑步" in title or item.task_id == "run")
                and "不要动" in query
            ):
                start_at = item.start_at
                end_at = item.end_at
                flexibility = TaskFlexibility.LOCKED
                locked_ids.append(item.task_id)
            else:
                tasks.append(
                    Task(
                        id=item.task_id,
                        title=title,
                        date=old_plan.date,
                        duration_min=duration,
                        location_id=item.location_id,
                        earliest_start=old_task_items[0].start_at,
                        latest_end=(
                            overall_deadline
                            or datetime.combine(
                                old_plan.date,
                                time(22, 0),
                                self.timezone,
                            )
                        ),
                        deadline=overall_deadline,
                        importance=max(1, 5 - index),
                        tags=(
                            ["outdoor", "exercise"]
                            if item.location_id == "track"
                            else []
                        ),
                    )
                )
                continue
            tasks.append(
                Task(
                    id=item.task_id,
                    title=title,
                    date=old_plan.date,
                    duration_min=duration,
                    location_id=item.location_id,
                    fixed_start=start_at,
                    fixed_end=end_at,
                    flexibility=flexibility,
                    deadline=overall_deadline,
                    importance=max(1, 5 - index),
                    tags=(
                        ["outdoor", "exercise"]
                        if item.location_id == "track"
                        else []
                    ),
                )
            )
        if intent == Intent.REPLAN:
            for index in range(1, len(tasks)):
                if tasks[index].flexibility == TaskFlexibility.MOVABLE:
                    tasks[index] = tasks[index].model_copy(
                        update={"depends_on": [tasks[index - 1].id]}
                    )
        return (
            tasks,
            UserPreferences(
                buffer_min=0,
                locked_task_ids=locked_ids,
                transport_mode=self.transport_mode_from_query(query),
                avoid_congestion=self.avoid_congestion_from_query(query),
            ),
        )

    @staticmethod
    def transport_mode_from_query(query: str) -> TransportMode:
        compact = re.sub(r"\s+", "", query)
        if any(
            keyword in compact
            for keyword in (
                "电瓶车",
                "电动车",
                "电动自行车",
                "小电驴",
                "骑电驴",
            )
        ):
            return TransportMode.ELECTROBIKE
        if any(
            keyword in compact
            for keyword in (
                "自行车",
                "共享单车",
                "单车",
                "骑车",
                "非机动车",
            )
        ):
            return TransportMode.BICYCLE
        return TransportMode.WALK

    @staticmethod
    def avoid_congestion_from_query(query: str) -> bool:
        return any(
            keyword in query
            for keyword in ("避开高峰", "避开拥堵", "错峰", "不要赶高峰")
        )

    def _movable_task(
        self,
        *,
        task_id: str,
        title: str,
        target_date: date,
        duration: int,
        location_raw: str,
        earliest: time,
        latest: time,
        importance: int,
        deadline: time | None = None,
        preferred_period: str | None = None,
    ) -> Task:
        return Task(
            id=task_id or f"task_{uuid4().hex}",
            title=title,
            date=target_date,
            duration_min=duration,
            location_raw=location_raw,
            earliest_start=datetime.combine(
                target_date,
                earliest,
                self.timezone,
            ),
            latest_end=datetime.combine(
                target_date,
                latest,
                self.timezone,
            ),
            deadline=(
                datetime.combine(target_date, deadline, self.timezone)
                if deadline
                else None
            ),
            preferred_period=preferred_period,
            importance=importance,
        )

    @staticmethod
    def _duration_near(query: str, keyword: str, default: int) -> int:
        number_words = "|".join(CHINESE_NUMBER_HOURS)
        minute_patterns = [
            rf"{keyword}[^，。；、]{{0,8}}?(\d+)\s*分钟",
            rf"(\d+)\s*分钟[^，。；、]{{0,8}}?{keyword}",
        ]
        for pattern in minute_patterns:
            match = re.search(pattern, query)
            if match:
                return max(5, int(match.group(1)))

        patterns = [
            rf"{keyword}[^，。；、]{{0,8}}?([0-9]+(?:\.[0-9]+)?)\s*个?小时",
            rf"([0-9]+(?:\.[0-9]+)?)\s*个?小时[^，。；、]{{0,8}}?{keyword}",
            rf"{keyword}[^，。；、]{{0,8}}?({number_words})小时",
            rf"({number_words})小时[^，。；、]{{0,8}}?{keyword}",
        ]
        for pattern in patterns:
            match = re.search(pattern, query)
            if not match:
                continue
            raw = match.group(1)
            hours = (
                float(raw)
                if re.fullmatch(r"[0-9.]+", raw)
                else CHINESE_NUMBER_HOURS[raw]
            )
            return max(5, round(hours * 60))
        return default

    @staticmethod
    def _closing_hour(query: str) -> int | None:
        match = re.search(r"(\d{1,2})\s*点(?:关门|关闭|前)", query)
        if not match:
            return None
        hour = int(match.group(1))
        return hour if 0 <= hour <= 23 else None

    @staticmethod
    def _courier_profile(
        query: str,
    ) -> tuple[str, str, time, time]:
        if "顺丰" in query:
            return (
                "取顺丰快递",
                "顺丰快递",
                time(8, 0),
                time(18, 0),
            )
        if "京东" in query:
            return (
                "取京东快递",
                "京东快递",
                time(8, 0),
                time(22, 0),
            )
        return (
            "取快递",
            "菜鸟驿站" if "菜鸟" in query else "快递站",
            time(8, 30),
            time(22, 30),
        )

    @staticmethod
    def _overall_start(query: str) -> time | None:
        match = re.search(
            r"(?<![\d年月日])(?:(上午|下午|晚上)\s*)?"
            r"(\d{1,2})(?!\d)(?:\s*[:：]\s*(\d{1,2}))?"
            r"(?!\s*(?:年|月|日|分钟|小时))"
            r"(?!\s*点?\s*前)\s*点?\s*"
            r"(?:后|以后|之后|开始|"
            r"(?=[^，。；、]{0,24}(?:"
            r"出发|前往|去|到(?!\s*\d))))",
            query,
        )
        if not match:
            return None
        period = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3) or 0)
        if period in {"下午", "晚上"} and 1 <= hour <= 11:
            hour += 12
        elif period == "上午" and hour == 12:
            hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return time(hour, minute)

    def journey_start_from_query(
        self,
        query: str,
        target_date: date,
    ) -> datetime | None:
        start = self._overall_start(query)
        if start is None:
            return None
        return datetime.combine(target_date, start, self.timezone)

    @staticmethod
    def journey_origin_from_query(query: str) -> str | None:
        match = re.search(
            r"从\s*([^，。；、]{1,40}?)\s*(?:出发|前往)",
            query,
        )
        if not match:
            return None
        raw = match.group(1).strip()
        raw = re.sub(
            r"^(?:今天|明天|后天)?"
            r"(?:(?:上午|下午|晚上)\s*)?"
            r"\d{1,2}(?::\d{1,2})?\s*点?\s*",
            "",
            raw,
        ).strip()
        return raw or None

    def _overall_deadline(
        self,
        query: str,
        target_date: date,
    ) -> datetime | None:
        match = re.search(
            r"(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?\s*点?\s*"
            r"前(?:(?:结束|完成|回来|搞定)(?:全部|所有|这些)?"
            r"(?:任务|事情|事项)?|(?=$|[，。；、]))",
            query,
        )
        return self._deadline_from_match(match, target_date)

    def _task_deadline(
        self,
        query: str,
        target_date: date,
        keywords: tuple[str, ...],
    ) -> datetime | None:
        """Return a deadline explicitly attached to one task clause.

        “18点前取快递” only constrains the parcel task, while
        “18点前结束” remains an overall deadline.  Clause boundaries keep a
        time expression from leaking into later tasks.
        """
        keyword_pattern = "|".join(re.escape(item) for item in keywords)
        time_pattern = (
            r"(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?\s*点?\s*前"
        )
        before_task = re.search(
            rf"{time_pattern}[^，。；、]{{0,16}}(?:{keyword_pattern})",
            query,
        )
        if before_task:
            return self._deadline_from_match(before_task, target_date)

        task_before = re.search(
            rf"(?:{keyword_pattern})[^，。；、]{{0,16}}?{time_pattern}",
            query,
        )
        if not task_before:
            return None
        hour = int(task_before.group(1))
        minute = int(task_before.group(2) or 0)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return datetime.combine(
            target_date,
            time(hour, minute),
            self.timezone,
        )

    def _deadline_from_match(
        self,
        match: re.Match[str] | None,
        target_date: date,
    ) -> datetime | None:
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None
        return datetime.combine(
            target_date,
            time(hour, minute),
            self.timezone,
        )

    @staticmethod
    def _extension_minutes(query: str) -> int:
        match = re.search(r"(?:延长|增加)\s*(\d+)\s*分钟", query)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _apply_explicit_order(
        query: str,
        tasks: list[Task],
    ) -> list[Task]:
        keywords = {
            "study": ("自习", "学习"),
            "parcel": ("取快递", "拿快递", "快递"),
            "dinner": ("吃晚饭", "晚饭", "吃饭"),
            "run": ("跑步", "运动"),
        }

        def position(task: Task) -> int:
            positions = [
                query.find(keyword)
                for keyword in keywords.get(task.id, ())
                if query.find(keyword) >= 0
            ]
            return min(positions) if positions else len(query)

        ordered = sorted(tasks, key=position)
        result = []
        for index, task in enumerate(ordered):
            result.append(
                task.model_copy(
                    update={
                        "depends_on": (
                            [ordered[index - 1].id] if index else []
                        ),
                        "importance": max(1, 5 - index),
                    }
                )
            )
        return result
