from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from app.schemas.common import (
    DataSource,
    IssueSeverity,
    PlanStatus,
    TaskFlexibility,
)
from app.schemas.context import (
    CongestionWindow,
    TravelEstimate,
    WeatherContext,
)
from app.schemas.plan import Plan, PlanItem, PlanMetrics
from app.schemas.task import Task, UserPreferences
from app.services.replanner import Replanner
from app.services.scheduler import PlanningContext, Scheduler
from app.services.validator import PlanValidator

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = (
    ROOT_DIR / "tests" / "fixtures" / "planning_benchmark_cases.json"
)
DEFAULT_JSON_REPORT = ROOT_DIR / "reports" / "planning_benchmark.json"
DEFAULT_MARKDOWN_REPORT = ROOT_DIR / "reports" / "planning_benchmark.md"

RANDOM_SEED = 20260729
# Updating the frozen fixture must be an explicit, reviewable action. Run the
# hash command documented in docs/TECHNICAL_BENCHMARK.md, review the diff, and
# then update this value in the same change.
EXPECTED_FIXTURE_SHA256 = (
    "ee8a013111212982d83080c94a43b69377b3e053eb7aeb0147414da748356e5f"
)

ALGORITHM_DEFINITIONS = {
    "greedy_first_fit": (
        "按输入顺序把任务放入最早的非重叠五分钟时隙；只处理固定时间、"
        "最早开始、最晚结束和截止时间，不读取路线、场馆、天气、依赖或旧计划。"
    ),
    "constraint_scheduler_no_history": (
        "使用当前确定性约束排程器，但在重排案例中移除旧计划历史；这是"
        "“关闭最小扰动目标”的消融组。"
    ),
    "constraint_scheduler_min_disruption": (
        "完整当前策略：约束排程与校验；重排案例额外使用旧计划位移成本，"
        "并保留锁定任务。"
    ),
}


@dataclass(slots=True)
class PreparedCase:
    raw: dict[str, Any]
    timezone: ZoneInfo
    target_date: date
    now: datetime
    tasks: list[Task]
    preferences: UserPreferences
    old_plan: Plan | None


def fixture_sha256(path: Path) -> str:
    # Keep the frozen hash stable across Windows checkouts (CRLF) and
    # Unix deployments (LF). The JSON fixture is text, so line-ending
    # normalization does not change its meaning or benchmark inputs.
    canonical = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(canonical).hexdigest()


def load_suite(
    path: Path = DEFAULT_FIXTURE,
    *,
    verify_hash: bool = True,
) -> tuple[dict[str, Any], str]:
    digest = fixture_sha256(path)
    if (
        verify_hash
        and EXPECTED_FIXTURE_SHA256 != "TO_BE_FILLED"
        and digest != EXPECTED_FIXTURE_SHA256
    ):
        raise ValueError(
            "planning benchmark fixture hash mismatch: "
            f"expected {EXPECTED_FIXTURE_SHA256}, got {digest}"
        )
    suite = json.loads(path.read_text(encoding="utf-8"))
    if suite.get("random_seed") != RANDOM_SEED:
        raise ValueError(
            "fixture random_seed does not match the benchmark constant"
        )
    cases = suite.get("cases")
    if not isinstance(cases, list) or len(cases) < 24:
        raise ValueError("planning benchmark requires at least 24 cases")
    case_ids = [case.get("id") for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("planning benchmark case ids must be unique")
    return suite, digest


def _parse_datetime(raw: str, timezone: ZoneInfo) -> datetime:
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        raise ValueError(f"benchmark datetime is not timezone-aware: {raw}")
    return value.astimezone(timezone)


def _parse_time(raw: str) -> time:
    return time.fromisoformat(raw)


def _task_from_raw(
    raw: dict[str, Any],
    *,
    target_date: date,
    timezone: ZoneInfo,
) -> Task:
    values = dict(raw)
    values.setdefault("date", target_date)
    for key in (
        "earliest_start",
        "latest_end",
        "fixed_start",
        "fixed_end",
        "deadline",
    ):
        if values.get(key):
            values[key] = _parse_datetime(values[key], timezone)
    return Task.model_validate(values)


def _old_plan_from_raw(
    raw: list[dict[str, Any]] | None,
    *,
    case_id: str,
    target_date: date,
    now: datetime,
    timezone: ZoneInfo,
) -> Plan | None:
    if raw is None:
        return None
    items = [
        PlanItem(
            id=f"old_{case_id}_{item['task_id']}",
            task_id=item["task_id"],
            item_type="task",
            title=item["title"],
            start_at=_parse_datetime(item["start_at"], timezone),
            end_at=_parse_datetime(item["end_at"], timezone),
            location_id=item.get("location_id"),
            source=DataSource.DEMO_FIXTURE,
            reason="冻结基准中的重排前计划",
        )
        for item in raw
    ]
    return Plan(
        id=f"old_plan_{case_id}",
        user_id="benchmark_user",
        thread_id=f"benchmark_{case_id}",
        date=target_date,
        status=PlanStatus.VALID,
        version=1,
        items=items,
        metrics=PlanMetrics(
            scheduled_task_count=len(items),
            requested_task_count=len(items),
        ),
        created_at=now - timedelta(days=1),
    )


def prepare_case(
    raw: dict[str, Any],
    defaults: dict[str, Any],
) -> PreparedCase:
    merged = {**defaults, **raw}
    timezone = ZoneInfo(merged["timezone"])
    target_date = date.fromisoformat(merged["target_date"])
    now = _parse_datetime(merged["now"], timezone)
    tasks = [
        _task_from_raw(
            item,
            target_date=target_date,
            timezone=timezone,
        )
        for item in merged["tasks"]
    ]
    preferences = UserPreferences.model_validate(
        merged.get("preferences", {})
    )
    old_plan = _old_plan_from_raw(
        merged.get("old_plan"),
        case_id=merged["id"],
        target_date=target_date,
        now=now,
        timezone=timezone,
    )
    if merged["kind"] == "replan" and old_plan is None:
        raise ValueError(f"replan case {merged['id']} has no old_plan")
    return PreparedCase(
        raw=merged,
        timezone=timezone,
        target_date=target_date,
        now=now,
        tasks=tasks,
        preferences=preferences,
        old_plan=old_plan,
    )


def _parse_windows(
    raw: dict[str, list[list[str]]],
    timezone: ZoneInfo,
) -> dict[str, list[tuple[datetime, datetime]]]:
    return {
        key: [
            (
                _parse_datetime(start, timezone),
                _parse_datetime(end, timezone),
            )
            for start, end in windows
        ]
        for key, windows in raw.items()
    }


def build_context(
    case: PreparedCase,
    *,
    include_old_plan: bool,
) -> PlanningContext:
    raw = case.raw
    travel: dict[tuple[str, str], TravelEstimate] = {}
    for route in raw.get("routes", []):
        pairs = [(route["origin"], route["destination"])]
        if route.get("bidirectional", True):
            pairs.append((route["destination"], route["origin"]))
        for origin, destination in pairs:
            travel[(origin, destination)] = TravelEstimate(
                origin_id=origin,
                destination_id=destination,
                mode=route.get("mode", "walk"),
                duration_min=route["minutes"],
                base_duration_min=route["minutes"],
                source=DataSource.DEMO_FIXTURE,
                confidence=1,
            )

    congestion = [
        CongestionWindow(
            start_at=_parse_datetime(item["start_at"], case.timezone),
            end_at=_parse_datetime(item["end_at"], case.timezone),
            duration_multiplier=item.get("duration_multiplier", 1.25),
            minimum_extra_min=item.get("minimum_extra_min", 3),
            source=DataSource.DEMO_FIXTURE,
        )
        for item in raw.get("congestion_windows", [])
    ]
    weather = [
        WeatherContext(
            date=case.target_date,
            period=item.get("period", "day"),
            condition=item.get("condition"),
            rain_probability=item.get("rain_probability"),
            risk_start_at=(
                _parse_datetime(item["risk_start_at"], case.timezone)
                if item.get("risk_start_at")
                else None
            ),
            source=DataSource.DEMO_FIXTURE,
        )
        for item in raw.get("weather", [])
    ]
    return PlanningContext(
        target_date=case.target_date,
        timezone=case.timezone,
        now=case.now,
        travel=travel,
        congestion_windows=congestion,
        opening_windows=_parse_windows(
            raw.get("opening_windows", {}),
            case.timezone,
        ),
        task_windows=_parse_windows(
            raw.get("task_windows", {}),
            case.timezone,
        ),
        weather=weather,
        outdoor_location_ids=set(raw.get("outdoor_location_ids", [])),
        enforce_weather=raw.get("enforce_weather", False),
        day_start=_parse_time(raw["day_start"]),
        day_end=_parse_time(raw["day_end"]),
        old_plan=case.old_plan if include_old_plan else None,
        initial_location_id=raw.get("initial_location_id"),
        initial_departure_at=(
            _parse_datetime(
                raw["initial_departure_at"],
                case.timezone,
            )
            if raw.get("initial_departure_at")
            else None
        ),
    )


def _deterministic_id(case_id: str, value: str) -> str:
    return uuid5(
        NAMESPACE_URL,
        f"yicheng-benchmark:{case_id}:{value}",
    ).hex


def _ceil_five_minutes(value: datetime) -> datetime:
    value = value.replace(second=0, microsecond=0)
    remainder = value.minute % 5
    if remainder:
        value += timedelta(minutes=5 - remainder)
    return value


def _has_overlap(
    start_at: datetime,
    end_at: datetime,
    items: Iterable[PlanItem],
) -> bool:
    return any(
        start_at < item.end_at and end_at > item.start_at
        for item in items
        if item.item_type == "task"
    )


def greedy_first_fit(case: PreparedCase) -> Plan:
    """A transparent generic-calendar baseline, intentionally campus-blind."""

    raw = case.raw
    day_start = datetime.combine(
        case.target_date,
        _parse_time(raw["day_start"]),
        case.timezone,
    )
    day_end = datetime.combine(
        case.target_date,
        _parse_time(raw["day_end"]),
        case.timezone,
    )
    if day_end <= day_start:
        day_end += timedelta(days=1)
    if case.target_date == case.now.date():
        day_start = max(day_start, _ceil_five_minutes(case.now))

    items: list[PlanItem] = []
    for task in case.tasks:
        if task.flexibility not in {
            TaskFlexibility.FIXED,
            TaskFlexibility.LOCKED,
        }:
            continue
        if task.fixed_start is None or task.fixed_end is None:
            continue
        items.append(
            PlanItem(
                id=f"baseline_{_deterministic_id(raw['id'], task.id)}",
                task_id=task.id,
                item_type="task",
                title=task.title,
                start_at=task.fixed_start,
                end_at=task.fixed_end,
                location_id=task.location_id,
                source=DataSource.DEMO_FIXTURE,
                reason="贪心基线：保留固定任务",
            )
        )

    for task in case.tasks:
        if task.flexibility != TaskFlexibility.MOVABLE:
            continue
        search_start = max(day_start, task.earliest_start or day_start)
        search_end = min(
            day_end,
            task.latest_end or day_end,
            task.deadline or day_end,
        )
        cursor = _ceil_five_minutes(search_start)
        duration = timedelta(minutes=task.duration_min)
        while (
            cursor + duration <= search_end
            and _has_overlap(cursor, cursor + duration, items)
        ):
            cursor += timedelta(minutes=5)
        if cursor + duration > search_end:
            continue
        items.append(
            PlanItem(
                id=f"baseline_{_deterministic_id(raw['id'], task.id)}",
                task_id=task.id,
                item_type="task",
                title=task.title,
                start_at=cursor,
                end_at=cursor + duration,
                location_id=task.location_id,
                source=DataSource.DEMO_FIXTURE,
                reason="贪心基线：输入顺序的最早可用时隙",
            )
        )

    items.sort(key=lambda item: (item.start_at, item.task_id or ""))
    return Plan(
        id=f"baseline_plan_{_deterministic_id(raw['id'], 'plan')}",
        user_id="benchmark_user",
        thread_id=f"benchmark_{raw['id']}",
        date=case.target_date,
        status=PlanStatus.DRAFT,
        version=2 if case.old_plan else 1,
        items=items,
        metrics=PlanMetrics(
            scheduled_task_count=len(items),
            requested_task_count=len(case.tasks),
        ),
        created_at=case.now,
    )


def _run_constraint_strategy(
    case: PreparedCase,
    *,
    minimal_disruption: bool,
) -> tuple[Plan, PlanningContext]:
    if (
        minimal_disruption
        and case.raw["kind"] == "replan"
        and case.old_plan is not None
    ):
        context = build_context(case, include_old_plan=True)
        result = Replanner().replan(
            user_id="benchmark_user",
            thread_id=f"benchmark_{case.raw['id']}",
            tasks=case.tasks,
            preferences=case.preferences,
            context=context,
            old_plan=case.old_plan,
        )
        return result.plan, context

    context = build_context(case, include_old_plan=False)
    result = Scheduler().schedule(
        user_id="benchmark_user",
        thread_id=f"benchmark_{case.raw['id']}",
        tasks=case.tasks,
        preferences=case.preferences,
        context=context,
        version=2 if case.old_plan else 1,
    )
    # Validation still needs the old plan to calculate preservation metrics.
    context.old_plan = case.old_plan
    return result.plan, context


def _dependency_violations(
    plan: Plan,
    tasks: list[Task],
) -> list[dict[str, Any]]:
    by_task = {
        item.task_id: item
        for item in plan.items
        if item.item_type == "task" and item.task_id
    }
    issues: list[dict[str, Any]] = []
    for task in tasks:
        item = by_task.get(task.id)
        if item is None:
            continue
        for dependency_id in task.depends_on:
            dependency = by_task.get(dependency_id)
            if dependency is None or dependency.end_at > item.start_at:
                issues.append(
                    {
                        "code": "DEPENDENCY_ORDER_VIOLATION",
                        "task_ids": [dependency_id, task.id],
                    }
                )
    return issues


def _task_items(plan: Plan) -> dict[str, PlanItem]:
    return {
        item.task_id: item
        for item in plan.items
        if item.item_type == "task" and item.task_id
    }


def _evaluate_plan(
    case: PreparedCase,
    plan: Plan,
    context: PlanningContext,
) -> dict[str, Any]:
    validated, issues = PlanValidator().validate(
        plan=plan,
        tasks=case.tasks,
        context=context,
    )
    hard_issues = [
        {"code": issue.code, "task_ids": issue.task_ids}
        for issue in issues
        if issue.severity == IssueSeverity.ERROR
    ]
    hard_issues.extend(_dependency_violations(validated, case.tasks))
    task_items = _task_items(validated)

    deadline_tasks = [task for task in case.tasks if task.deadline]
    deadline_met_ids = [
        task.id
        for task in deadline_tasks
        if (
            task.id in task_items
            and task_items[task.id].end_at <= task.deadline
        )
    ]

    old_items = _task_items(case.old_plan) if case.old_plan else {}
    current_task_ids = {task.id for task in case.tasks}
    comparable_ids = sorted(set(old_items) & current_task_ids)
    preserved_ids = [
        task_id
        for task_id in comparable_ids
        if (
            task_id in task_items
            and task_items[task_id].start_at
            == old_items[task_id].start_at
        )
    ]
    total_displacement = sum(
        int(
            abs(
                (
                    task_items[task_id].start_at
                    - old_items[task_id].start_at
                ).total_seconds()
            )
            // 60
        )
        for task_id in comparable_ids
        if task_id in task_items
    )

    unaffected_ids = sorted(case.raw.get("unaffected_task_ids", []))
    false_moved_ids = [
        task_id
        for task_id in unaffected_ids
        if (
            task_id not in task_items
            or task_id not in old_items
            or task_items[task_id].start_at
            != old_items[task_id].start_at
        )
    ]
    scheduled_count = len(task_items)
    expected_count = len(case.tasks)
    feasible_complete = (
        not hard_issues and scheduled_count == expected_count
    )

    return {
        "case_id": case.raw["id"],
        "kind": case.raw["kind"],
        "category": case.raw["category"],
        "purpose": case.raw["purpose"],
        "expected_feasible": case.raw.get("expected_feasible", True),
        "feasible_complete": feasible_complete,
        "scheduled_task_count": scheduled_count,
        "requested_task_count": expected_count,
        "hard_constraint_violation_count": len(hard_issues),
        "hard_constraint_violation_codes": sorted(
            issue["code"] for issue in hard_issues
        ),
        "deadline_task_count": len(deadline_tasks),
        "deadline_met_count": len(deadline_met_ids),
        "deadline_met_ids": deadline_met_ids,
        "comparable_replan_task_count": len(comparable_ids),
        "preserved_task_count": len(preserved_ids),
        "preserved_task_ids": preserved_ids,
        "unaffected_task_count": len(unaffected_ids),
        "false_move_count": len(false_moved_ids),
        "false_moved_task_ids": false_moved_ids,
        "total_displacement_minutes": total_displacement,
        "task_intervals": {
            task_id: {
                "start_at": item.start_at.isoformat(),
                "end_at": item.end_at.isoformat(),
                "location_id": item.location_id,
            }
            for task_id, item in sorted(task_items.items())
        },
    }


def run_case(
    case: PreparedCase,
    algorithm: str,
) -> dict[str, Any]:
    if algorithm == "greedy_first_fit":
        plan = greedy_first_fit(case)
        context = build_context(case, include_old_plan=True)
    elif algorithm == "constraint_scheduler_no_history":
        plan, context = _run_constraint_strategy(
            case,
            minimal_disruption=False,
        )
    elif algorithm == "constraint_scheduler_min_disruption":
        plan, context = _run_constraint_strategy(
            case,
            minimal_disruption=True,
        )
    else:
        raise ValueError(f"unknown benchmark algorithm: {algorithm}")
    return _evaluate_plan(case, plan, context)


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    feasible = sum(item["feasible_complete"] for item in results)
    deadline_total = sum(item["deadline_task_count"] for item in results)
    deadline_met = sum(item["deadline_met_count"] for item in results)
    comparable = sum(
        item["comparable_replan_task_count"] for item in results
    )
    preserved = sum(item["preserved_task_count"] for item in results)
    unaffected = sum(item["unaffected_task_count"] for item in results)
    false_moves = sum(item["false_move_count"] for item in results)
    return {
        "case_count": len(results),
        "feasible_case_count": feasible,
        "feasible_completion_rate": _safe_rate(feasible, len(results)),
        "hard_constraint_violation_count": sum(
            item["hard_constraint_violation_count"]
            for item in results
        ),
        "deadline_task_count": deadline_total,
        "deadline_met_count": deadline_met,
        "deadline_satisfaction_rate": _safe_rate(
            deadline_met,
            deadline_total,
        ),
        "comparable_replan_task_count": comparable,
        "preserved_task_count": preserved,
        "preservation_rate": _safe_rate(preserved, comparable),
        "unaffected_task_count": unaffected,
        "false_move_count": false_moves,
        "false_move_rate": _safe_rate(false_moves, unaffected),
        "total_displacement_minutes": sum(
            item["total_displacement_minutes"] for item in results
        ),
    }


def run_benchmark(
    suite: dict[str, Any],
    fixture_digest: str,
) -> dict[str, Any]:
    random.seed(RANDOM_SEED)
    defaults = suite["defaults"]
    cases = [
        prepare_case(raw, defaults)
        for raw in suite["cases"]
    ]
    algorithms: dict[str, Any] = {}
    for algorithm, definition in ALGORITHM_DEFINITIONS.items():
        results = [run_case(case, algorithm) for case in cases]
        algorithms[algorithm] = {
            "definition": definition,
            "summary": summarize(results),
            "cases": results,
        }
    return {
        "suite": suite["suite"],
        "schema_version": suite["schema_version"],
        "fixture_version": suite["fixture_version"],
        "fixture_sha256": fixture_digest,
        "random_seed": RANDOM_SEED,
        "deterministic": True,
        "case_count": len(cases),
        "scope": suite["scope"],
        "limitations": suite["limitations"],
        "algorithms": algorithms,
    }


def _format_rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 易程智策确定性规划基线与消融报告",
        "",
        f"- 冻结数据版本：`{report['fixture_version']}`",
        f"- 场景数量：{report['case_count']}",
        f"- 固定随机种子：`{report['random_seed']}`",
        f"- 数据 SHA256：`{report['fixture_sha256']}`",
        "- 联网或大模型调用：无",
        "",
        "## 汇总",
        "",
        (
            "| 方法 | 可行完成率 | 硬约束违反 | 截止满足率 | "
            "保留率 | 误移动率 | 总位移（分钟） |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "greedy_first_fit": "贪心最早插入基线",
        "constraint_scheduler_no_history": "约束排程（关闭历史）",
        "constraint_scheduler_min_disruption": "完整策略（最小扰动）",
    }
    for name, payload in report["algorithms"].items():
        summary = payload["summary"]
        lines.append(
            f"| {labels[name]} "
            f"| {_format_rate(summary['feasible_completion_rate'])} "
            f"| {summary['hard_constraint_violation_count']} "
            f"| {_format_rate(summary['deadline_satisfaction_rate'])} "
            f"| {_format_rate(summary['preservation_rate'])} "
            f"| {_format_rate(summary['false_move_rate'])} "
            f"| {summary['total_displacement_minutes']} |"
        )

    lines.extend(
        [
            "",
            "## 方法边界",
            "",
            report["scope"],
            "",
            (
                "该报告不是用户研究，也不包含任何虚构的大模型结果。"
                "它只证明冻结输入下三个确定性算法的可复现行为。"
            ),
            "",
            "## 算法定义",
            "",
        ]
    )
    for name, definition in report["algorithms"].items():
        lines.append(f"- `{name}`：{definition['definition']}")

    lines.extend(["", "## 分场景结果", ""])
    for name, payload in report["algorithms"].items():
        lines.extend(
            [
                f"### {labels[name]}",
                "",
                "| 场景 | 类别 | 可行完成 | 硬约束违反 | 误移动 | 位移分钟 |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for item in payload["cases"]:
            lines.append(
                f"| `{item['case_id']}` | {item['category']} "
                f"| {'是' if item['feasible_complete'] else '否'} "
                f"| {item['hard_constraint_violation_count']} "
                f"| {item['false_move_count']} "
                f"| {item['total_displacement_minutes']} |"
            )
        lines.append("")

    lines.extend(["## 局限", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines).rstrip() + "\n"


def write_reports(
    report: dict[str, Any],
    *,
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_markdown(report),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the frozen deterministic planning benchmark."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON_REPORT,
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=DEFAULT_MARKDOWN_REPORT,
    )
    args = parser.parse_args()

    suite, digest = load_suite(args.fixture)
    report = run_benchmark(suite, digest)
    write_reports(
        report,
        json_path=args.json_out,
        markdown_path=args.markdown_out,
    )
    summaries = {
        name: payload["summary"]
        for name, payload in report["algorithms"].items()
    }
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
