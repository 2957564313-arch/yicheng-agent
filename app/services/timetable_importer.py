from __future__ import annotations

import base64
import csv
import io
import json
import re
from typing import Any

from openpyxl import load_workbook

from app.schemas.timetable import CourseSessionCreate


HEADER_ALIASES = {
    "course_name": ("课程名称", "课程", "course_name", "course"),
    "weekday": ("星期", "周几", "weekday", "day"),
    "start_period": ("开始节次", "起始节次", "start_period", "start"),
    "end_period": ("结束节次", "终止节次", "end_period", "end"),
    "location": ("地点", "教室", "location", "room"),
    "weeks": ("周次", "教学周", "weeks", "week"),
}

WEEKDAY_VALUES = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "日": 7,
    "天": 7,
    "周一": 1,
    "周二": 2,
    "周三": 3,
    "周四": 4,
    "周五": 5,
    "周六": 6,
    "周日": 7,
    "星期一": 1,
    "星期二": 2,
    "星期三": 3,
    "星期四": 4,
    "星期五": 5,
    "星期六": 6,
    "星期日": 7,
    "星期天": 7,
}


def parse_timetable(
    *,
    content: str,
    format_name: str,
) -> tuple[list[CourseSessionCreate], int, list[str]]:
    rows = _load_rows(content=content, format_name=format_name)
    entries: list[CourseSessionCreate] = []
    skipped = 0
    messages: list[str] = []
    for index, raw in enumerate(rows, start=2):
        try:
            normalized = _normalize_row(raw)
            if not normalized["course_name"]:
                skipped += 1
                continue
            entries.append(CourseSessionCreate.model_validate(normalized))
        except Exception as exc:
            skipped += 1
            messages.append(f"第{index}行未导入：{exc}")
    if not entries:
        detail = messages[0] if messages else "文件中没有可识别的课程"
        raise ValueError(detail)
    return entries, skipped, messages[:10]


def _load_rows(*, content: str, format_name: str) -> list[dict[str, Any]]:
    if format_name == "json":
        payload = json.loads(content)
        rows = payload.get("entries", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("JSON需要是课程数组，或包含entries数组")
        return [row for row in rows if isinstance(row, dict)]
    if format_name == "csv":
        return list(csv.DictReader(io.StringIO(content.lstrip("\ufeff"))))
    if format_name == "xlsx_base64":
        binary = base64.b64decode(content, validate=True)
        workbook = load_workbook(io.BytesIO(binary), read_only=True, data_only=True)
        sheet = workbook.active
        values = list(sheet.iter_rows(values_only=True))
        if not values:
            return []
        headers = [str(value or "").strip() for value in values[0]]
        return [
            {
                headers[index]: value
                for index, value in enumerate(row)
                if index < len(headers) and headers[index]
            }
            for row in values[1:]
        ]
    raise ValueError("暂不支持这种课表格式")


def _normalize_row(raw: dict[str, Any]) -> dict[str, Any]:
    resolved = {
        key: _first_value(raw, aliases)
        for key, aliases in HEADER_ALIASES.items()
    }
    weekday_raw = str(resolved["weekday"] or "").strip()
    weekday = WEEKDAY_VALUES.get(weekday_raw)
    if weekday is None and weekday_raw.isdigit():
        weekday = int(weekday_raw)
    start_period = _period_value(resolved["start_period"])
    end_period = _period_value(resolved["end_period"]) or start_period
    return {
        "course_name": str(resolved["course_name"] or "").strip(),
        "weekday": weekday,
        "start_period": start_period,
        "end_period": end_period,
        "location": str(resolved["location"] or "").strip() or None,
        "weeks": _weeks_value(resolved["weeks"]),
    }


def _first_value(raw: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    compact = {str(key).strip().lower(): value for key, value in raw.items()}
    for alias in aliases:
        if alias.lower() in compact:
            return compact[alias.lower()]
    return None


def _period_value(value: Any) -> int | None:
    match = re.search(r"\d{1,2}", str(value or ""))
    return int(match.group()) if match else None


def _weeks_value(value: Any) -> list[int]:
    text = str(value or "").strip()
    if not text:
        return []
    odd_only = "单" in text
    even_only = "双" in text
    weeks: set[int] = set()
    for start_raw, end_raw in re.findall(
        r"(\d{1,2})(?:\s*[-—~至]\s*(\d{1,2}))?",
        text,
    ):
        start = int(start_raw)
        end = int(end_raw or start_raw)
        weeks.update(range(min(start, end), max(start, end) + 1))
    if odd_only:
        weeks = {week for week in weeks if week % 2 == 1}
    if even_only:
        weeks = {week for week in weeks if week % 2 == 0}
    return sorted(weeks)
