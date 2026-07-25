from __future__ import annotations

import json
import warnings
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from starlette.exceptions import StarletteDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message=r"Using `httpx` with `starlette\.testclient` is deprecated.*",
    category=StarletteDeprecationWarning,
)

from fastapi.testclient import TestClient  # noqa: E402

from app.config import BASE_DIR, Settings
from app.main import create_app


def run_case(client: TestClient, case: dict) -> dict:
    if case["endpoint"] == "demo":
        response = client.post(
            f"/api/v1/demos/{case['demo_id']}/run"
        )
    else:
        response = client.post("/api/v1/chat", json=case["request"])

    expected = case["expected"]
    failures = []
    if response.status_code != expected["http_status"]:
        failures.append(
            f"http={response.status_code}, expected={expected['http_status']}"
        )
        return {
            "case_id": case["case_id"],
            "category": case["category"],
            "passed": False,
            "failures": failures,
            "response": response.text[:1000],
        }

    payload = response.json()
    if payload["status"] != expected["status"]:
        failures.append(
            f"status={payload['status']}, expected={expected['status']}"
        )
    expected_plan_status = expected.get("plan_status")
    if expected_plan_status:
        actual = payload.get("plan", {}).get("status")
        if actual != expected_plan_status:
            failures.append(
                f"plan_status={actual}, expected={expected_plan_status}"
            )
    plan_items = (payload.get("plan") or {}).get("items", [])
    task_items = [
        item
        for item in plan_items
        if item["item_type"] == "task"
    ]
    task_count = len(task_items)
    if task_count < expected["min_task_count"]:
        failures.append(
            f"task_count={task_count}, min={expected['min_task_count']}"
        )
    actual_codes = {item["code"] for item in payload.get("warnings", [])}
    for code in expected.get("warning_codes", []):
        if code not in actual_codes:
            failures.append(f"missing warning={code}")

    hard_violations = (
        (payload.get("plan") or {})
        .get("metrics", {})
        .get("hard_violation_count", 0)
    )
    if expected_plan_status == "valid" and hard_violations != 0:
        failures.append(f"hard_violation_count={hard_violations}")

    answer = payload.get("answer", "")
    for marker in expected.get("answer_contains", []):
        if marker not in answer:
            failures.append(f"answer missing={marker!r}")
    for marker in expected.get("answer_not_contains", []):
        if marker in answer:
            failures.append(f"answer unexpectedly contains={marker!r}")
    minimum_answer_length = expected.get("min_answer_length", 0)
    if len(answer) < minimum_answer_length:
        failures.append(
            f"answer_length={len(answer)}, min={minimum_answer_length}"
        )

    task_titles = [item.get("title", "") for item in task_items]
    for marker in expected.get("required_task_titles", []):
        if not any(marker in title for title in task_titles):
            failures.append(f"missing task title marker={marker!r}")
    for marker in expected.get("forbidden_task_titles", []):
        if any(marker in title for title in task_titles):
            failures.append(f"forbidden task title marker={marker!r}")

    required_travel_mode = expected.get("required_travel_mode")
    if required_travel_mode:
        travel_items = [
            item
            for item in plan_items
            if item["item_type"] == "travel"
        ]
        if not travel_items:
            failures.append("missing travel items")
        elif any(
            item.get("travel_mode") != required_travel_mode
            for item in travel_items
        ):
            actual_modes = sorted(
                {
                    str(item.get("travel_mode"))
                    for item in travel_items
                }
            )
            failures.append(
                f"travel_modes={actual_modes}, "
                f"expected={required_travel_mode}"
            )

    minimum_congestion_delay = expected.get(
        "min_congestion_delay_min",
        0,
    )
    if minimum_congestion_delay:
        actual_congestion_delay = max(
            (
                int(item.get("congestion_delay_min") or 0)
                for item in plan_items
                if item["item_type"] == "travel"
            ),
            default=0,
        )
        if actual_congestion_delay < minimum_congestion_delay:
            failures.append(
                f"congestion_delay_min={actual_congestion_delay}, "
                f"min={minimum_congestion_delay}"
            )

    expected_target_date = expected.get("target_date")
    if (
        expected_target_date
        and payload.get("time_context", {}).get("target_date")
        != expected_target_date
    ):
        failures.append(
            "target_date="
            f"{payload.get('time_context', {}).get('target_date')}, "
            f"expected={expected_target_date}"
        )

    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "passed": not failures,
        "failures": failures,
        "metrics": {
            "task_count": task_count,
            "hard_violation_count": hard_violations,
        },
    }


def main() -> None:
    cases_path = (
        BASE_DIR / "tests" / "fixtures" / "evaluation_cases.json"
    )
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="yicheng-eval-") as temporary:
        temp = Path(temporary)
        settings = Settings(
            app_database_path=temp / "app.db",
            app_checkpoint_database_path=temp / "checkpoints.db",
            app_data_dir=BASE_DIR / "data",
            app_demo_dir=BASE_DIR / "fixtures",
            llm_enabled=False,
            live_route_enabled=False,
            live_weather_enabled=False,
        )
        with TestClient(create_app(settings)) as client:
            results = [run_case(client, case) for case in cases]

    passed = sum(item["passed"] for item in results)
    category_totals = Counter(item["category"] for item in results)
    category_passed = Counter(
        item["category"] for item in results if item["passed"]
    )
    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "suite": "offline_mvp",
        "total": len(results),
        "passed": passed,
        "pass_rate": passed / len(results),
        "categories": {
            category: {
                "total": total,
                "passed": category_passed[category],
                "pass_rate": category_passed[category] / total,
            }
            for category, total in sorted(category_totals.items())
        },
    }
    report_dir = BASE_DIR / "reports"
    report_dir.mkdir(exist_ok=True)
    (report_dir / "evaluation.json").write_text(
        json.dumps(
            {"summary": summary, "results": results},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown = [
        "# 离线 MVP 评估报告",
        "",
        f"- 总案例：{summary['total']}",
        f"- 通过：{summary['passed']}",
        f"- 通过率：{summary['pass_rate']:.1%}",
        "",
        "## 分类",
        "",
        "| 分类 | 通过 | 总数 | 通过率 |",
        "|---|---:|---:|---:|",
    ]
    for category, values in summary["categories"].items():
        markdown.append(
            f"| {category} | {values['passed']} | "
            f"{values['total']} | {values['pass_rate']:.1%} |"
        )
    failures = [item for item in results if not item["passed"]]
    markdown.extend(["", "## 失败案例", ""])
    if not failures:
        markdown.append("无。")
    else:
        for failure in failures:
            markdown.append(
                f"- `{failure['case_id']}`："
                + "；".join(failure["failures"])
            )
    (report_dir / "evaluation.md").write_text(
        "\n".join(markdown) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
