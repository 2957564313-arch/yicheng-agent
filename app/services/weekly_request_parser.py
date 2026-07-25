from __future__ import annotations

from datetime import date, datetime, time, timedelta
import re
from zoneinfo import ZoneInfo

from app.schemas.weekly import (
    EnergyLevel,
    GoalStageCreate,
    WeeklyGoalCreate,
    WeeklyTextInterpretation,
)


_WEEKDAYS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "日": 7,
    "天": 7,
}

_DEFAULT_DURATIONS = (
    (("取快递", "快递"), 30),
    (("吃饭", "用餐"), 45),
    (("跑步",), 30),
    (("运动", "锻炼"), 40),
    (("自习",), 120),
    (("复习", "备考"), 120),
    (("读论文", "阅读论文", "论文阅读"), 120),
    (("汇报准备", "准备汇报"), 120),
    (("实验报告", "课程报告", "写报告"), 120),
    (("作业",), 120),
)

_STAGE_KEYWORDS = (
    "资料整理",
    "论文阅读",
    "方案设计",
    "数据处理",
    "汇报准备",
    "编码",
    "测试",
    "报告",
    "复习",
    "阅读",
    "撰写",
)


class RuleBasedWeeklyRequestParser:
    """Conservative parser used when the language model is unavailable.

    It intentionally handles a documented, human-readable weekly-goal syntax
    instead of pretending every ambiguous sentence is fully understood.
    """

    def __init__(self, timezone_name: str = "Asia/Shanghai") -> None:
        self.timezone = ZoneInfo(timezone_name)

    def parse(
        self,
        *,
        query: str,
        week_start: date,
    ) -> WeeklyTextInterpretation:
        normalized = self._normalize(query)
        segments = [
            item.strip(" ，,")
            for item in re.split(r"[\n；;。]+", normalized)
            if item.strip(" ，,")
        ]
        goals: list[WeeklyGoalCreate] = []
        clarifications: list[str] = []
        for segment in segments:
            goal, question = self._parse_segment(
                segment=segment,
                week_start=week_start,
            )
            if goal is not None:
                goals.append(goal)
            elif question:
                clarifications.append(question)

        if not goals and not clarifications:
            clarifications.append(
                "请至少告诉我一个本周目标、预计投入时长和截止时间。"
            )
        return WeeklyTextInterpretation(
            goals=goals,
            clarifications=list(dict.fromkeys(clarifications))[:5],
            confidence=(
                0.86
                if goals and not clarifications
                else 0.62 if goals else 0.2
            ),
        )

    def _parse_segment(
        self,
        *,
        segment: str,
        week_start: date,
    ) -> tuple[WeeklyGoalCreate | None, str | None]:
        deadline = self._deadline(segment, week_start)
        stages = self._stages(segment)
        repeat = self._repeat(segment)
        duration = (
            sum(item.duration_min for item in stages)
            if stages
            else self._duration(segment, repeat=repeat)
        )
        title = self._title(segment)
        if not title:
            return None, "有一项目标名称没有识别清楚，请换一行重新描述。"
        if duration is None:
            return (
                None,
                f"“{title}”预计需要投入多长时间？"
                "可以写成“共3小时”或“2次，每次40分钟”。",
            )

        preferred_periods = []
        avoided_periods = []
        if re.search(r"晚上|晚间|夜间", segment):
            preferred_periods.append("evening")
        elif re.search(r"上午|早上|早晨", segment):
            preferred_periods.append("morning")
        elif re.search(r"下午", segment):
            preferred_periods.append("afternoon")
        if re.search(r"不要.*晚上|避免.*晚上|不想.*晚上", segment):
            avoided_periods.append("evening")
            preferred_periods = [
                item for item in preferred_periods if item != "evening"
            ]

        min_chunk = 30
        max_chunk = min(120, duration)
        max_chunks_per_day = 2
        if repeat is not None:
            count, each_min = repeat
            min_chunk = each_min
            max_chunk = each_min
            max_chunks_per_day = 1
            duration = count * each_min
        elif not re.search(r"可拆|分段|分多次|每天", segment):
            min_chunk = min(60, duration)

        location = self._preferred_location(segment, title)
        importance = (
            5
            if re.search(r"必须|务必|考试|答辩|提交|DDL|截止", segment, re.I)
            else 4 if deadline.date() < week_start + timedelta(days=6) else 3
        )
        soft_deadline = bool(
            re.search(
                r"(?:尽量|最好).{0,12}(?:完成|做完|截止)"
                r"|(?:完成|做完|截止).{0,12}(?:可以延期|不强求)",
                segment,
            )
        )
        hard_deadline = not soft_deadline
        energy_level = (
            EnergyLevel.HIGH
            if any(
                keyword in title
                for keyword in ("编码", "测试", "复习", "论文", "报告")
            )
            else EnergyLevel.MEDIUM
        )
        return (
            WeeklyGoalCreate(
                title=title,
                description=segment,
                deadline=deadline,
                total_duration_min=duration,
                splittable=(repeat is not None or duration > max_chunk),
                min_chunk_min=min_chunk,
                max_chunk_min=max_chunk,
                max_chunks_per_day=max_chunks_per_day,
                importance=importance,
                hard_deadline=hard_deadline,
                preferred_periods=preferred_periods,
                avoided_periods=avoided_periods,
                preferred_locations=[location] if location else [],
                energy_level=energy_level,
                stages=stages,
            ),
            None,
        )

    def _deadline(self, segment: str, week_start: date) -> datetime:
        weekday_match = re.search(
            r"(?:周|星期)([一二三四五六日天])",
            segment,
        )
        weekday = (
            _WEEKDAYS[weekday_match.group(1)] if weekday_match else 7
        )
        target_date = week_start + timedelta(days=weekday - 1)
        time_match = re.search(
            r"(?:周|星期)[一二三四五六日天]"
            r"(?:\s*上午|\s*下午|\s*晚上|\s*晚间)?"
            r"\s*(\d{1,2})(?:[:：](\d{1,2}))?\s*(?:点|时)?",
            segment,
        )
        hour = 22
        minute = 0
        if time_match:
            hour = min(23, int(time_match.group(1)))
            minute = min(59, int(time_match.group(2) or 0))
            prefix = segment[max(0, time_match.start() - 4):time_match.end()]
            if ("下午" in prefix or "晚上" in prefix or "晚间" in prefix) and hour < 12:
                hour += 12
        elif "中午" in segment:
            hour = 12
        elif "上午" in segment:
            hour = 12
        return datetime.combine(
            target_date,
            time(hour=hour, minute=minute),
            self.timezone,
        )

    def _repeat(self, segment: str) -> tuple[int, int] | None:
        patterns = (
            r"(\d+)\s*次.{0,12}?每次\s*(\d+(?:\.\d+)?)\s*(小时|分钟)",
            r"每次\s*(\d+(?:\.\d+)?)\s*(小时|分钟).{0,12}?(\d+)\s*次",
        )
        first = re.search(patterns[0], segment)
        if first:
            count = int(first.group(1))
            each = self._to_minutes(first.group(2), first.group(3))
            return (count, each) if 1 <= count <= 14 else None
        second = re.search(patterns[1], segment)
        if second:
            count = int(second.group(3))
            each = self._to_minutes(second.group(1), second.group(2))
            return (count, each) if 1 <= count <= 14 else None
        return None

    def _duration(
        self,
        segment: str,
        *,
        repeat: tuple[int, int] | None,
    ) -> int | None:
        if repeat:
            return repeat[0] * repeat[1]
        matched = re.search(
            r"(?:共|总共|预计(?:还)?要|需要|投入|安排|还要)"
            r"\s*(\d+(?:\.\d+)?)\s*(小时|分钟)",
            segment,
        )
        if matched:
            return self._to_minutes(matched.group(1), matched.group(2))
        for keywords, default in _DEFAULT_DURATIONS:
            if any(keyword in segment for keyword in keywords):
                return default
        return None

    def _stages(self, segment: str) -> list[GoalStageCreate]:
        matches: list[tuple[str, int]] = []
        for keyword in _STAGE_KEYWORDS:
            matched = re.search(
                rf"{re.escape(keyword)}\s*(\d+(?:\.\d+)?)\s*(小时|分钟)",
                segment,
            )
            if matched:
                matches.append(
                    (
                        keyword,
                        self._to_minutes(matched.group(1), matched.group(2)),
                    )
                )
        ordered = sorted(
            matches,
            key=lambda item: segment.index(item[0]),
        )
        stages = []
        previous_id = None
        for sequence, (title, duration) in enumerate(ordered, start=1):
            stage_id = f"stage_{sequence}"
            stages.append(
                GoalStageCreate(
                    id=stage_id,
                    title=title,
                    sequence=sequence,
                    duration_min=duration,
                    depends_on_stage_ids=(
                        [previous_id] if previous_id else []
                    ),
                    splittable=duration > 120,
                    min_chunk_min=min(60, duration),
                    preferred_location=self._preferred_location(
                        segment,
                        title,
                    ),
                )
            )
            previous_id = stage_id
        return stages if len(stages) >= 2 else []

    @staticmethod
    def _preferred_location(segment: str, title: str) -> str | None:
        location_match = re.search(
            r"(?:在|去)(图书馆|东操场|体育馆|宿舍|实验室|自习室|教室)",
            segment,
        )
        if location_match:
            return location_match.group(1)
        if "跑步" in title:
            return "东操场"
        if any(keyword in title for keyword in ("学习", "自习", "复习", "论文")):
            return "图书馆"
        return None

    @staticmethod
    def _title(segment: str) -> str:
        value = re.sub(r"^(?:请)?(?:帮我)?(?:安排)?(?:一下)?", "", segment)
        value = re.sub(
            r"^(?:本周|这周|未来七天|未来7天)\s*",
            "",
            value,
        )
        value = re.sub(
            r"^(?:周|星期)[一二三四五六日天]"
            r"(?:\s*上午|\s*下午|\s*晚上|\s*早上|\s*早晨|"
            r"\s*中午|\s*晚间)?"
            r"\s*\d{0,2}(?:[:：]\d{1,2})?\s*(?:点|时)?"
            r"\s*(?:前|之前|截止)?\s*",
            "",
            value,
        )
        value = re.split(
            r"[，,](?:预计|共|总共|需要|投入|其中|尽量|最好|必须)",
            value,
            maxsplit=1,
        )[0]
        value = re.sub(r"^(?:完成|做完|完成好|安排)", "", value)
        value = re.sub(
            r"\s*(?:共|总共|需要|预计(?:还)?要|投入|安排)"
            r"\s*\d+(?:\.\d+)?\s*(?:小时|分钟).*$",
            "",
            value,
        )
        value = re.sub(r"\d+\s*次.*$", "", value)
        return value.strip(" ，,。")[:160]

    @staticmethod
    def _normalize(query: str) -> str:
        return (
            query.replace("：", ":")
            .replace("～", "-")
            .replace("~", "-")
            .strip()
        )

    @staticmethod
    def _to_minutes(value: str, unit: str) -> int:
        amount = float(value)
        minutes = round(amount * 60) if unit == "小时" else round(amount)
        return max(5, min(20_160, minutes))
