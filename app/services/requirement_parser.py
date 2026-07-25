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
        if (
            intent != Intent.QUERY
            and old_plan is None
            and target_date < now.date()
        ):
            clarifications.append(
                f"你说的日期是{target_date:%Y年%m月%d日}，"
                "这一天已经过去；请确认是否要安排到下一次对应日期。"
            )
        if (
            not tasks
            and intent != Intent.QUERY
            and not (
                old_plan is not None
                and self._is_removal_request(query)
            )
        ):
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
        explicit_planning_markers = (
            "安排",
            "规划",
            "帮我安排",
            "请安排",
            "安排一下",
            "重新安排",
            "帮我规划",
            "请规划",
            "加入日程",
            "加入计划",
            "排进日程",
            "排进计划",
        )
        operational_domains = (
            "图书馆",
            "体育馆",
            "操场",
            "田径场",
            "阳光长跑",
            "快递",
            "驿站",
            "顺丰",
            "京东",
            "菜鸟",
            "校医院",
            "热水",
            "供水",
            "宿舍",
            "公寓",
            "门禁",
            "餐厅",
            "食堂",
        )
        operational_question_markers = (
            "几点",
            "什么时候",
            "何时",
            "哪个时间段",
            "哪些时间",
            "开放吗",
            "开吗",
            "营业吗",
            "到几点",
            "计入",
            "有什么规定",
            "有哪些规定",
            "怎么规定",
        )
        planning_keywords = (
            "安排",
            "规划",
            "自习",
            "学习",
            "取快递",
            "拿快递",
            "取顺丰",
            "拿顺丰",
            "顺丰快递",
            "取京东",
            "拿京东",
            "京东快递",
            "跑步",
            "长跑",
            "阳光长跑",
            "运动",
            "羽毛球",
            "乒乓球",
            "校医院",
            "看医生",
            "就诊",
            "洗澡",
            "洗漱",
            "热水",
            "吃饭",
        )
        if (
            not any(marker in query for marker in explicit_planning_markers)
            and any(domain in query for domain in operational_domains)
            and any(
                marker in query
                for marker in operational_question_markers
            )
        ):
            # 场馆、门禁、快递和校医院等“什么时候开放/能否计入”
            # 是校园事实查询。不能因为句子里同时出现“看病、长跑”等
            # 任务词，就误创建一项日程。
            return True
        if (
            any(keyword in query for keyword in ("热水", "供水"))
            and any(
                marker in query
                for marker in (
                    "几点",
                    "什么时候",
                    "开放时间",
                    "供应时间",
                    "有热水吗",
                    "有没有热水",
                    "到几点",
                )
            )
        ):
            return True
        if (
            any(marker in query for marker in ("几点", "什么时候", "何时"))
            and any(
                marker in query
                for marker in (
                    "开门",
                    "关门",
                    "关闭",
                    "开放",
                    "营业",
                    "就诊",
                    "计入",
                )
            )
        ):
            # “顺丰几点关闭”“校医院什么时候可以就诊”是在询问
            # 已核验规则，不是要求系统现在创建一项取件或就诊任务。
            return True
        if any(keyword in query for keyword in planning_keywords):
            # “根据我的课表帮我安排自习”等句子虽然包含“课表”，
            # 但核心动作是生成计划。课表应作为硬约束参与排程，而不是
            # 把整句话提前截断为知识问答。
            return False
        if any(
            re.search(pattern, query)
            for pattern in (
                r"课表",
                r"哪几节.*课",
                r"有哪些课",
                r"(?:有|没|没有)课吗",
                r"有没有课",
                r"是否有课",
                r"(?:要|需要|应该|是否要)上课吗",
                r"(?:放假|节假日|调休|补课)",
            )
        ):
            return True
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
                "旷课",
                "考勤",
                "迟到",
                "早退",
                "课程考核",
                "申诉",
                "违纪",
                "退学",
                "休学",
                "学籍",
                "转专业",
                "奖学金",
                "推免",
                "学分",
                "请假",
                "放假",
                "节假日",
                "调休",
                "补课",
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
        month_day = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日", query)
        if month_day:
            return date(
                now.year,
                int(month_day.group(1)),
                int(month_day.group(2)),
            )
        if "后天" in query:
            return now.date() + timedelta(days=2)
        if "明天" in query:
            return now.date() + timedelta(days=1)
        weekday_match = re.search(
            r"(下周|下星期|本周|这周|本星期|这星期|周|星期)\s*"
            r"([一二三四五六日天])",
            query,
        )
        if weekday_match:
            target_weekday = {
                "一": 0,
                "二": 1,
                "三": 2,
                "四": 3,
                "五": 4,
                "六": 5,
                "日": 6,
                "天": 6,
            }[weekday_match.group(2)]
            current_monday = now.date() - timedelta(days=now.weekday())
            prefix = weekday_match.group(1)
            target = current_monday + timedelta(days=target_weekday)
            if prefix in {"下周", "下星期"}:
                target += timedelta(days=7)
            elif prefix in {"周", "星期"}:
                if target < now.date():
                    target += timedelta(days=7)
            return target
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
                    location_raw=self._study_location(query),
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
                for keyword in (
                    "取快递",
                    "拿快递",
                    "去快递站",
                    "取件",
                    "取顺丰",
                    "拿顺丰",
                    "顺丰快递",
                    "取京东",
                    "拿京东",
                    "京东快递",
                )
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
                (
                    "取快递",
                    "拿快递",
                    "快递",
                    "取件",
                    "取顺丰",
                    "拿顺丰",
                    "顺丰快递",
                    "取京东",
                    "拿京东",
                    "京东快递",
                ),
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
            not any(
                word in fixed_text
                for word in ("校医院", "看医生", "就诊", "医务室")
            )
            and any(
                keyword in query
                for keyword in ("校医院", "看医生", "就诊", "医务室")
            )
        ):
            clinic_keyword = next(
                keyword
                for keyword in ("校医院", "看医生", "就诊", "医务室")
                if keyword in query
            )
            clinic_deadline = self._task_deadline(
                query,
                target_date,
                ("校医院", "看医生", "就诊", "医务室"),
            )
            clinic_limit = clinic_deadline or overall_deadline
            tasks.append(
                self._movable_task(
                    task_id="clinic",
                    title="前往校医院就诊",
                    target_date=target_date,
                    duration=self._duration_near(
                        query,
                        clinic_keyword,
                        default=30,
                    ),
                    location_raw="校医院",
                    earliest=(
                        overall_start
                        or (time(13, 30) if "下午" in query else time(8, 0))
                    ),
                    latest=(
                        clinic_limit.time()
                        if clinic_limit
                        else time(20, 0)
                    ),
                    deadline=(
                        clinic_limit.time()
                        if clinic_limit
                        else None
                    ),
                    importance=5,
                )
            )
            tasks[-1] = tasks[-1].model_copy(
                update={
                    "tags": [
                        "health",
                        "service_hours",
                        "hard_constraint",
                    ],
                    "notes": (
                        "校医院工作日8:00—20:00，双休日及节假日"
                        "8:00—11:30、13:30—16:00，就诊时间属于"
                        "已核验硬约束"
                    ),
                }
            )
        if (
            not any(
                word in fixed_text
                for word in ("洗澡", "洗漱", "热水")
            )
            and any(
                keyword in query
                for keyword in ("洗澡", "洗漱", "用热水", "打热水")
            )
        ):
            bath_keyword = next(
                keyword
                for keyword in ("洗澡", "洗漱", "用热水", "打热水")
                if keyword in query
            )
            bath_deadline = self._task_deadline(
                query,
                target_date,
                ("洗澡", "洗漱", "用热水", "打热水"),
            )
            bath_limit = bath_deadline or overall_deadline
            tasks.append(
                self._movable_task(
                    task_id="bath",
                    title="回宿舍洗澡" if "洗澡" in query else "宿舍洗漱",
                    target_date=target_date,
                    duration=self._duration_near(
                        query,
                        bath_keyword,
                        default=30,
                    ),
                    location_raw="学生公寓",
                    earliest=(
                        overall_start
                        or (
                            time(16, 30)
                            if any(
                                word in query
                                for word in ("下午", "晚上")
                            )
                            else time(6, 0)
                        )
                    ),
                    latest=(
                        bath_limit.time()
                        if bath_limit
                        else time(23, 59)
                    ),
                    deadline=(
                        bath_limit.time()
                        if bath_limit
                        else None
                    ),
                    preferred_period="evening" if "晚上" in query else None,
                    importance=3,
                )
            )
            tasks[-1] = tasks[-1].model_copy(
                update={
                    "tags": [
                        "dormitory",
                        "hot_water",
                        "activity_window",
                        "hard_constraint",
                    ],
                    "notes": (
                        "宿舍热水供应为6:00—8:00、16:30—24:00，"
                        "同时必须满足当天公寓门禁时间"
                    ),
                }
            )
        for (
            sport_keyword,
            sport_id,
            sport_title,
            sport_location,
        ) in (
            ("羽毛球", "badminton", "打羽毛球", "综合馆"),
            ("乒乓球", "table_tennis", "打乒乓球", "体育馆主馆"),
        ):
            if sport_keyword not in query or sport_keyword in fixed_text:
                continue
            sport_deadline = self._task_deadline(
                query,
                target_date,
                (sport_keyword,),
            )
            sport_limit = sport_deadline or overall_deadline
            tasks.append(
                self._movable_task(
                    task_id=sport_id,
                    title=sport_title,
                    target_date=target_date,
                    duration=self._duration_near(
                        query,
                        sport_keyword,
                        default=60,
                    ),
                    location_raw=sport_location,
                    earliest=(
                        overall_start
                        or (time(13, 0) if "下午" in query else time(11, 30))
                    ),
                    latest=(
                        sport_limit.time()
                        if sport_limit
                        else time(20, 30)
                    ),
                    deadline=(
                        sport_limit.time()
                        if sport_limit
                        else None
                    ),
                    preferred_period="evening" if "晚上" in query else None,
                    importance=3,
                )
            )
            tasks[-1] = tasks[-1].model_copy(
                update={
                    "tags": [
                        "indoor",
                        "exercise",
                        "reservation_required",
                        "hard_constraint",
                    ],
                    "notes": (
                        "暑期7月1日至9月4日仅工作日"
                        "11:30—20:30开放，周末不开放，并需按要求预约"
                    ),
                }
            )
        if (
            not any(
                word in fixed_text
                for word in ("跑步", "长跑", "阳光长跑", "运动")
            )
            and any(
                keyword in query
                for keyword in ("阳光长跑", "长跑", "跑步", "运动")
            )
        ):
            run_keyword = next(
                keyword
                for keyword in ("阳光长跑", "长跑", "跑步", "运动")
                if keyword in query
            )
            is_sunshine_run = "阳光长跑" in query
            run_deadline = self._task_deadline(
                query,
                target_date,
                ("阳光长跑", "长跑", "跑步", "运动"),
            )
            run_limit = run_deadline or overall_deadline
            tasks.append(
                self._movable_task(
                    task_id="run",
                    title="阳光长跑" if is_sunshine_run else "跑步",
                    target_date=target_date,
                    duration=self._duration_near(
                        query,
                        run_keyword,
                        default=30,
                    ),
                    location_raw=self._run_location(query),
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
                update={
                    "tags": [
                        "outdoor",
                        "exercise",
                        *(
                            ["sunshine_run", "activity_window"]
                            if is_sunshine_run
                            else []
                        ),
                    ]
                }
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
            "parcel": (
                "取顺丰",
                "拿顺丰",
                "顺丰快递",
                "取京东",
                "拿京东",
                "京东快递",
                "取快递",
                "拿快递",
                "快递",
                "取件",
            ),
            "dinner": ("吃晚饭", "晚饭", "吃饭"),
            "clinic": ("校医院", "看医生", "就诊", "医务室"),
            "bath": ("洗澡", "洗漱", "用热水", "打热水"),
            "badminton": ("羽毛球",),
            "table_tennis": ("乒乓球",),
            "run": ("阳光长跑", "长跑", "跑步", "运动"),
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
            "校医院",
            "看医生",
            "就诊",
            "洗澡",
            "洗漱",
            "羽毛球",
            "乒乓球",
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
                r"^(?:(?:另外|还有|再加|新增|补充|别忘了)\s*)?"
                r"(?:在\s*)?"
                r"(?:(?:\d{4}年)?\d{1,2}月\d{1,2}日|"
                r"今天|明天|后天)?\s*(?:我)?\s*(?:在\s*)?"
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
        """Convert each stated course into its own immutable time block."""
        if not self.class_periods:
            return []

        number = r"(?:1[0-3]|[1-9]|十三|十二|十一|十|[一二三四五六七八九])"
        covered_spans: list[tuple[int, int]] = []
        descriptors: list[tuple[re.Match[str], list[int]]] = []
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
            covered_spans.append(match.span())
            descriptors.append((match, list(range(lower, upper + 1))))

        list_pattern = re.compile(
            rf"第\s*({number}(?:\s*[、,，]\s*{number})+)\s*节"
        )
        for match in list_pattern.finditer(query):
            values = []
            for raw in re.split(r"\s*[、,，]\s*", match.group(1)):
                value = self._period_number(raw)
                if value is not None:
                    values.append(value)
            if not values:
                continue
            covered_spans.append(match.span())
            descriptors.append((match, sorted(set(values))))

        single_pattern = re.compile(rf"第?\s*({number})\s*节")
        for match in single_pattern.finditer(query):
            if any(
                start <= match.start() and match.end() <= end
                for start, end in covered_spans
            ):
                continue
            clause = self._course_clause(query, match)
            tail = query[match.end() : match.end() + 6]
            if (
                re.match(r"\s*(?:以后|之后|后)", tail)
                and not any(
                    marker in clause
                    for marker in ("有课", "上课", "下课", "课程")
                )
            ):
                # “第四节以后去自习” uses the period as a time anchor;
                # it does not assert that the user has a fourth-period class.
                continue
            value = self._period_number(match.group(1))
            if value is not None:
                descriptors.append((match, [value]))

        tasks: list[Task] = []
        used_ids: set[str] = set()
        for match, raw_periods in sorted(
            descriptors,
            key=lambda item: item[0].start(),
        ):
            valid_periods = [
                value for value in raw_periods if value in self.class_periods
            ]
            groups: list[list[int]] = []
            for period in valid_periods:
                if groups and period == groups[-1][-1] + 1:
                    groups[-1].append(period)
                else:
                    groups.append([period])
            clause = self._course_clause(query, match)
            course_title, location = self._course_title_and_location(
                clause=clause,
                matched_periods=match.group(0),
            )
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
                fallback_title = (
                    f"第{first}节课程"
                    if first == last
                    else f"第{first}—{last}节课程"
                )
                title = course_title or fallback_title
                base_id = f"course_{first}_{last}"
                task_id = base_id
                suffix = 2
                while task_id in used_ids:
                    task_id = f"{base_id}_{suffix}"
                    suffix += 1
                used_ids.add(task_id)
                tasks.append(
                    Task(
                        id=task_id,
                        title=title,
                        date=target_date,
                        duration_min=int(
                            (end_at - start_at).total_seconds() // 60
                        ),
                        location_raw=location,
                        fixed_start=start_at,
                        fixed_end=end_at,
                        flexibility=TaskFlexibility.FIXED,
                        importance=5,
                        tags=[
                            "course",
                            "verified_timetable",
                            "hard_constraint",
                            f"period:{first}-{last}",
                        ],
                        notes=(
                            "依据已核验校内上课时间表锁定，不可被规划器移动"
                        ),
                    )
                )
        return tasks

    @staticmethod
    def _course_clause(query: str, match: re.Match[str]) -> str:
        clause_start = max(
            query.rfind(separator, 0, match.start())
            for separator in ("，", "。", "；", ",", ";")
        )
        following = [
            position
            for separator in ("，", "。", "；", ",", ";")
            if (position := query.find(separator, match.end())) >= 0
        ]
        clause_end = min(following, default=len(query))
        return query[clause_start + 1 : clause_end].strip()

    @staticmethod
    def _course_title_and_location(
        *,
        clause: str,
        matched_periods: str,
    ) -> tuple[str | None, str | None]:
        location = next(
            (
                name
                for name in (
                    "第六教学楼",
                    "第七教学楼",
                    "六教",
                    "七教",
                    "图书馆",
                    "实验室",
                )
                if name in clause
            ),
            None,
        )
        title = clause.replace(matched_periods, "", 1)
        title = re.sub(
            r"^(?:今天|明天|后天)?\s*(?:我)?\s*"
            r"(?:有|要上|上|需要上)?\s*",
            "",
            title,
        )
        if location:
            title = re.sub(
                rf"(?:在|地点是|地点为)?\s*{re.escape(location)}",
                "",
                title,
            )
        title = title.strip(" ，。；、")
        if title in {"", "课", "课程", "有课", "上课"}:
            title = None
        return title[:120] if title else None, location

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
        removed_ids = self._removed_task_ids(query, old_task_items)
        rescheduled = self._rescheduled_intervals(
            query=query,
            target_date=old_plan.date,
            old_task_items=old_task_items,
        )
        duration_changes = self._duration_changes(
            query=query,
            old_task_items=old_task_items,
        )
        overall_deadline = self._overall_deadline(query, old_plan.date)
        for index, item in enumerate(old_task_items):
            if item.item_type != "task" or not item.task_id:
                continue
            if item.task_id in removed_ids:
                continue
            duration = int(
                (item.end_at - item.start_at).total_seconds() // 60
            )
            title = item.title
            if item.task_id in rescheduled:
                start_at, end_at = rescheduled[item.task_id]
                duration = int(
                    (end_at - start_at).total_seconds() // 60
                )
                flexibility = TaskFlexibility.FIXED
            elif item.task_id in duration_changes:
                start_at = item.start_at
                duration = duration_changes[item.task_id]
                end_at = start_at + timedelta(minutes=duration)
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
        if intent == Intent.REPLAN and self._is_addition_request(query):
            added_tasks, _ = self._extract_plan_tasks(
                query=query,
                target_date=old_plan.date,
            )
            existing_signatures = {
                self._task_signature(task) for task in tasks
            }
            existing_ids = {task.id for task in tasks}
            for added_task in added_tasks:
                signature = self._task_signature(added_task)
                if signature in existing_signatures:
                    continue
                unique_id = added_task.id
                if unique_id in existing_ids:
                    unique_id = f"{unique_id}_{uuid4().hex[:8]}"
                    added_task = added_task.model_copy(
                        update={"id": unique_id}
                    )
                tasks.append(added_task)
                existing_ids.add(unique_id)
                existing_signatures.add(signature)
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
    def _is_addition_request(query: str) -> bool:
        """Whether the user is appending to, rather than replacing, a plan."""
        return any(
            keyword in query
            for keyword in (
                "新增",
                "再加",
                "加一个",
                "加入",
                "补充",
                "另外",
                "还有",
                "别忘了",
            )
        )

    @staticmethod
    def _is_removal_request(query: str) -> bool:
        compact = re.sub(r"\s+", "", query)
        if any(
            negated in compact
            for negated in (
                "不要取消",
                "别取消",
                "不能取消",
                "不要删除",
                "不要去掉",
            )
        ):
            return False
        return any(
            marker in compact
            for marker in (
                "取消",
                "删除",
                "去掉",
                "移除",
                "不去了",
                "不去",
                "不用安排",
                "不安排",
                "别安排",
                "清空安排",
                "全部取消",
                "取消全部",
            )
        )

    def _removed_task_ids(
        self,
        query: str,
        old_task_items: list,
    ) -> set[str]:
        if not self._is_removal_request(query):
            return set()
        compact = re.sub(r"\s+", "", query)
        if any(
            marker in compact
            for marker in ("清空安排", "全部取消", "取消全部", "都取消")
        ):
            return {
                item.task_id
                for item in old_task_items
                if item.task_id
            }
        removed: set[str] = set()
        clauses = [
            clause
            for clause in re.split(r"[，。；,;]", query)
            if self._is_removal_request(clause)
        ]
        for item in old_task_items:
            if not item.task_id:
                continue
            aliases = self._task_removal_aliases(
                task_id=item.task_id,
                title=item.title,
            )
            if any(
                any(alias in clause for alias in aliases)
                for clause in clauses
            ):
                removed.add(item.task_id)
        return removed

    @staticmethod
    def _task_removal_aliases(*, task_id: str, title: str) -> set[str]:
        aliases = {title, task_id}
        known = {
            "study": {"自习", "学习", "图书馆"},
            "parcel": {"取快递", "拿快递", "快递", "取件", "驿站"},
            "run": {"跑步", "长跑", "运动"},
            "dinner": {"晚饭", "吃饭", "用餐"},
            "clinic": {"校医院", "看医生", "就诊"},
            "bath": {"洗澡", "洗漱"},
            "badminton": {"羽毛球"},
            "table_tennis": {"乒乓球"},
        }
        aliases.update(known.get(task_id, set()))
        if "会议" in title or "开会" in title:
            aliases.update({"会议", "开会"})
        if "课程" in title or "上课" in title:
            aliases.update({"课程", "上课"})
        return {alias for alias in aliases if alias}

    def _rescheduled_intervals(
        self,
        *,
        query: str,
        target_date: date,
        old_task_items: list,
    ) -> dict[str, tuple[datetime, datetime]]:
        """Resolve explicit or relative time changes for one existing task."""
        move_markers = (
            "改到",
            "改为",
            "挪到",
            "调整到",
            "移到",
            "提前到",
            "推迟到",
            "延后到",
            "提前",
            "推迟",
            "延后",
            "延迟",
            "顺延",
        )
        if not any(marker in query for marker in move_markers):
            return {}
        relative_minutes = self._relative_shift_minutes(query)
        if (
            relative_minutes is not None
            and any(
                marker in query
                for marker in (
                    "所有安排",
                    "全部安排",
                    "整个日程",
                    "全天安排",
                    "所有任务",
                    "全部任务",
                )
            )
        ):
            protected = self._protected_task_ids(
                query=query,
                old_task_items=old_task_items,
            )
            delta = timedelta(minutes=relative_minutes)
            return {
                item.task_id: (
                    item.start_at + delta,
                    item.end_at + delta,
                )
                for item in old_task_items
                if item.task_id
                and item.task_id not in protected
                and not self._is_course_plan_item(item)
            }

        move_clauses = [
            clause
            for clause in re.split(r"[，。；,;]", query)
            if any(marker in clause for marker in move_markers)
        ]
        targets = [
            item
            for item in old_task_items
            if item.task_id
            and any(
                any(alias in clause for clause in move_clauses)
                for alias in self._task_removal_aliases(
                    task_id=item.task_id,
                    title=item.title,
                )
            )
        ]
        if len(targets) != 1:
            return {}
        target = targets[0]

        fixed_candidates = self._fixed_arrangement_tasks(query, target_date)
        if len(fixed_candidates) == 1:
            candidate = fixed_candidates[0]
            if candidate.fixed_start and candidate.fixed_end:
                return {
                    target.task_id: (
                        candidate.fixed_start,
                        candidate.fixed_end,
                    )
                }

        single_clock = re.search(
            r"(?:改到|改为|挪到|调整到|移到|提前到|推迟到|延后到)"
            r"\s*(?P<period1>上午|中午|下午|晚上)?\s*"
            r"(?P<hour1>\d{1,2})"
            r"(?:(?:\s*[:：]\s*(?P<minute1>\d{1,2}))|"
            r"(?:\s*点(?:\s*(?P<minute_point1>\d{1,2})\s*分)?))",
            query,
        )
        if single_clock:
            start_time = self._clock_from_groups(single_clock, "1")
            if start_time:
                start_at = datetime.combine(
                    target_date,
                    start_time,
                    self.timezone,
                )
                duration = target.end_at - target.start_at
                return {
                    target.task_id: (
                        start_at,
                        start_at + duration,
                    )
                }

        if relative_minutes is not None:
            delta = timedelta(minutes=relative_minutes)
            return {
                target.task_id: (
                    target.start_at + delta,
                    target.end_at + delta,
                )
            }
        return {}

    @staticmethod
    def _relative_shift_minutes(query: str) -> int | None:
        relative = re.search(
            r"(?P<direction>提前|推迟|延后|延迟|顺延)\s*"
            r"(?P<amount>\d+(?:\.\d+)?|半|一|两|二)\s*"
            r"(?P<unit>小时|分钟)",
            query,
        )
        if not relative:
            return None
        raw_amount = relative.group("amount")
        amount = (
            CHINESE_NUMBER_HOURS.get(raw_amount)
            if not raw_amount.replace(".", "", 1).isdigit()
            else float(raw_amount)
        )
        if amount is None:
            return None
        minutes = (
            round(float(amount) * 60)
            if relative.group("unit") == "小时"
            else round(float(amount))
        )
        return -minutes if relative.group("direction") == "提前" else minutes

    def _duration_changes(
        self,
        *,
        query: str,
        old_task_items: list,
    ) -> dict[str, int]:
        """Resolve a duration edit for exactly one named existing task."""
        duration_clauses = [
            clause
            for clause in re.split(r"[，。；,;]", query)
            if re.search(
                r"(?:延长|增加|缩短|减少|时长.{0,4}(?:改成|改为|调整为))"
                r".{0,10}(?:小时|分钟)",
                clause,
            )
        ]
        targets = [
            item
            for item in old_task_items
            if item.task_id
            and any(
                any(alias in clause for clause in duration_clauses)
                for alias in self._task_removal_aliases(
                    task_id=item.task_id,
                    title=item.title,
                )
            )
        ]
        if len(targets) != 1:
            return {}
        target = targets[0]
        clause = next(
            clause
            for clause in duration_clauses
            if any(
                alias in clause
                for alias in self._task_removal_aliases(
                    task_id=target.task_id,
                    title=target.title,
                )
            )
        )
        amount_pattern = (
            r"(?P<amount>\d+(?:\.\d+)?|半|一|两|二)\s*"
            r"(?P<unit>小时|分钟)"
        )
        relative = re.search(
            rf"(?P<direction>延长|增加|缩短|减少)\s*{amount_pattern}",
            clause,
        )
        absolute = re.search(
            rf"(?:时长|持续时间).{{0,4}}"
            rf"(?:改成|改为|调整为)\s*{amount_pattern}",
            clause,
        )
        matched = relative or absolute
        if not matched:
            return {}
        raw_amount = matched.group("amount")
        amount = (
            CHINESE_NUMBER_HOURS.get(raw_amount)
            if not raw_amount.replace(".", "", 1).isdigit()
            else float(raw_amount)
        )
        if amount is None:
            return {}
        minutes = (
            round(float(amount) * 60)
            if matched.group("unit") == "小时"
            else round(float(amount))
        )
        current_minutes = max(
            1,
            round((target.end_at - target.start_at).total_seconds() / 60),
        )
        if relative:
            if relative.group("direction") in {"缩短", "减少"}:
                minutes = current_minutes - minutes
            else:
                minutes = current_minutes + minutes
        if minutes < 5:
            return {}
        return {target.task_id: minutes}

    def _protected_task_ids(
        self,
        *,
        query: str,
        old_task_items: list,
    ) -> set[str]:
        protect_markers = (
            "不要动",
            "别动",
            "保持原时间",
            "保持原来的时间",
            "保持不变",
            "不要调整",
            "别改",
        )
        clauses = [
            clause
            for clause in re.split(r"[，。；,;]", query)
            if any(marker in clause for marker in protect_markers)
        ]
        return {
            item.task_id
            for item in old_task_items
            if item.task_id
            and any(
                any(alias in clause for alias in self._task_removal_aliases(
                    task_id=item.task_id,
                    title=item.title,
                ))
                for clause in clauses
            )
        }

    @staticmethod
    def _is_course_plan_item(item) -> bool:
        return bool(
            (item.task_id and item.task_id.startswith("course_"))
            or any(
                marker in item.title
                for marker in ("上课", "课程", "实验课")
            )
        )

    @staticmethod
    def _task_signature(task: Task) -> tuple[object, ...]:
        """Stable semantic signature used to avoid duplicating old tasks."""
        return (
            task.title,
            task.date,
            task.fixed_start,
            task.fixed_end,
            task.location_id,
            task.location_raw,
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
    def _study_location(query: str) -> str:
        """Preserve a stated library floor so its exact closing rule applies."""
        if re.search(
            r"图书馆\s*(?:六|6|十二|12)\s*(?:层|楼)",
            query,
        ):
            if re.search(r"图书馆\s*(?:十二|12)\s*(?:层|楼)", query):
                return "图书馆十二层"
            return "图书馆六层"
        floor_match = re.search(
            r"图书馆\s*(七|八|九|十|十一|7|8|9|10|11)\s*(?:层|楼)",
            query,
        )
        if floor_match:
            floor = floor_match.group(1)
            chinese_floor = {
                "7": "七",
                "8": "八",
                "9": "九",
                "10": "十",
                "11": "十一",
            }.get(floor, floor)
            return f"图书馆{chinese_floor}层"
        return "图书馆"

    @staticmethod
    def _run_location(query: str) -> str:
        """Map natural campus names to verified HDU running venues."""
        if any(
            keyword in query
            for keyword in ("西北田径场", "西北操场", "北区操场", "北区")
        ):
            return "西北田径场"
        if any(
            keyword in query
            for keyword in (
                "体育馆副馆南侧塑胶跑道",
                "体育馆副馆南侧",
                "副馆南侧跑道",
                "体育馆跑道",
            )
        ):
            return "体育馆副馆南侧塑胶跑道"
        return "东操场"

    @staticmethod
    def _overall_start(query: str) -> time | None:
        # Remove calendar dates first so “7月24日21点后” keeps 21:00 as
        # the time anchor without mistaking month/day numbers for a clock.
        clock_query = re.sub(
            r"(?:20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}日?"
            r"|\d{1,2}月\d{1,2}日)",
            " ",
            query,
        )
        match = re.search(
            r"(?<![\d年月日])(?:(上午|下午|晚上)\s*)?"
            r"(\d{1,2})(?!\d)(?:"
            r"\s*[:：]\s*(\d{1,2})"
            r"|\s*点\s*(?:(\d{1,2})\s*分?)?"
            r")?"
            r"(?!\s*(?:年|月|日|分钟|小时))"
            r"(?!\s*点?\s*前)\s*"
            r"(?:后|以后|之后|开始|"
            r"(?=[^，。；、]{0,24}(?:"
            r"出发|前往|去|回(?:到)?|返回|到(?!\s*\d))))",
            clock_query,
        )
        if not match:
            return None
        period = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3) or match.group(4) or 0)
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
        time_pattern = (
            r"(\d{1,2})(?:\s*[:：]\s*(\d{1,2}))?\s*点?\s*前"
        )
        collective = re.search(
            time_pattern
            + (
                r"(?:(?:全部|所有|这些)(?:任务|事情|事项)?"
                r"(?:结束|完成|回来|搞定)|"
                r"(?:结束|完成|回来|搞定)(?:全部|所有|这些)"
                r"(?:任务|事情|事项)?)"
            ),
            query,
        )
        if collective:
            return self._deadline_from_match(collective, target_date)

        ending = re.search(
            time_pattern + r"(?:结束|完成|回来|搞定)?\s*[。！？!?]?\s*$",
            query,
        )
        return self._deadline_from_match(ending, target_date)

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

        task_then_deadline_clause = re.search(
            rf"(?:{keyword_pattern})[^。；、]{{0,24}}?[，,]\s*"
            rf"{time_pattern}(?:完成|结束|搞定)",
            query,
        )
        if task_then_deadline_clause:
            hour = int(task_then_deadline_clause.group(1))
            minute = int(task_then_deadline_clause.group(2) or 0)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return datetime.combine(
                    target_date,
                    time(hour, minute),
                    self.timezone,
                )

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
            "parcel": (
                "取顺丰",
                "拿顺丰",
                "顺丰快递",
                "取京东",
                "拿京东",
                "京东快递",
                "取快递",
                "拿快递",
                "快递",
                "取件",
            ),
            "dinner": ("吃晚饭", "晚饭", "吃饭"),
            "clinic": ("校医院", "看医生", "就诊", "医务室"),
            "bath": ("洗澡", "洗漱", "用热水", "打热水"),
            "badminton": ("羽毛球",),
            "table_tennis": ("乒乓球",),
            "run": ("阳光长跑", "长跑", "跑步", "运动"),
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
