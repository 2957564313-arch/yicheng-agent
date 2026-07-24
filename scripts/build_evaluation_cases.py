from __future__ import annotations

import json
from pathlib import Path

from app.config import BASE_DIR


def chat_case(
    case_id: str,
    category: str,
    query: str,
    *,
    min_task_count: int,
    expected_status: str = "completed",
    warning_codes: list[str] | None = None,
) -> dict:
    return {
        "case_id": case_id,
        "category": category,
        "endpoint": "chat",
        "request": {
            "user_id": "evaluation_user",
            "thread_id": f"thread_{case_id}",
            "query": query,
            "mode": "offline",
            "client_context": {
                "now": "2026-07-23T08:00:00+08:00"
            }
        },
        "expected": {
            "http_status": 200,
            "status": expected_status,
            "plan_status": (
                "valid" if expected_status == "completed" else None
            ),
            "min_task_count": min_task_count,
            "warning_codes": (
                ["API_DEGRADED"]
                if warning_codes is None
                else warning_codes
            )
        }
    }

def build_cases() -> list[dict]:
    base_queries = [
        ("明天下午安排两个小时自习。", 1),
        ("明天去图书馆学习一个小时。", 1),
        ("明天下午取快递，快递站18点关门。", 1),
        ("明天安排吃晚饭。", 1),
        ("明天晚上去跑步。", 1),
        ("明天下午自习两个小时，然后取快递，18点前完成。", 2),
        ("明天取快递后吃晚饭，快递站18点关门。", 2),
        ("明天吃晚饭以后跑步。", 2),
        ("明天下午学习两个小时，晚上运动。", 2),
        ("明天下午自习两个小时、取快递、吃饭和跑步。", 4),
    ]
    cases = []
    for round_index in range(3):
        for index, (query, count) in enumerate(base_queries, start=1):
            cases.append(
                chat_case(
                    f"normal_{round_index + 1}_{index:02d}",
                    "normal",
                    query,
                    min_task_count=count,
                )
            )

    for index, hour in enumerate((16, 17, 18, 18, 17, 16, 18, 17, 18, 16), 1):
        cases.append(
            chat_case(
                f"deadline_{index:02d}",
                "deadline",
                f"明天下午取快递，快递站{hour}点关门。",
                min_task_count=1,
            )
        )

    degraded_queries = [
        "明天下午去图书馆自习两个小时，再去快递站，结合天气安排。",
        "明天下午学习一个小时并取快递。",
        "明天晚上吃饭后跑步，结合天气安排。",
        "明天下午自习两个小时，晚上跑步。",
        "明天取快递以后吃饭。",
    ]
    for index in range(10):
        query = degraded_queries[index % len(degraded_queries)]
        count = sum(
            [
                ("自习" in query or "学习" in query),
                ("快递" in query),
                ("吃饭" in query),
                ("跑步" in query),
            ]
        )
        cases.append(
            chat_case(
                f"degraded_{index + 1:02d}",
                "degraded",
                query,
                min_task_count=count,
                warning_codes=["API_DEGRADED"],
            )
        )

    for index in range(5):
        cases.append(
            chat_case(
                f"clarification_{index + 1:02d}",
                "clarification",
                "请帮我安排一下。",
                min_task_count=0,
                expected_status="needs_clarification",
                warning_codes=[],
            )
        )

    for index, demo_id in enumerate(
        [
            "demo_01_normal",
            "demo_02_emergency",
            "demo_03_degraded",
            "demo_01_normal",
            "demo_02_emergency",
        ],
        start=1,
    ):
        cases.append(
            {
                "case_id": f"demo_{index:02d}",
                "category": "demo",
                "endpoint": "demo",
                "demo_id": demo_id,
                "expected": {
                    "http_status": 200,
                    "status": "completed",
                    "plan_status": "valid",
                    "min_task_count": 2,
                    "warning_codes": ["API_DEGRADED"],
                },
            }
        )
    assert len(cases) == 60
    return cases


def main() -> None:
    output = BASE_DIR / "tests" / "fixtures" / "evaluation_cases.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_cases(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote 60 cases: {output}")


if __name__ == "__main__":
    main()
