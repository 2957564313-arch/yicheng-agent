from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def main() -> None:
    base_settings = Settings()
    checks = {
        "llm": bool(
            base_settings.llm_enabled
            and base_settings.llm_api_key
            and base_settings.llm_base_url
        ),
        "route": bool(
            base_settings.live_route_enabled
            and base_settings.route_api_key
        ),
        "weather": bool(
            base_settings.live_weather_enabled
            and base_settings.weather_api_key
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"实时服务配置不完整：{checks}")

    with TemporaryDirectory(prefix="yicheng-live-e2e-") as temporary:
        temp = Path(temporary)
        settings = Settings(
            app_database_path=temp / "app.db",
            app_checkpoint_database_path=temp / "checkpoints.db",
        )
        with TestClient(create_app(settings)) as client:
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_id": "live_e2e_user",
                    "thread_id": "live_e2e_thread",
                    "query": (
                        "今天14点后去图书馆自习2小时，再去菜鸟驿站"
                        "取快递，最后去东操场跑步30分钟，18点前结束。"
                    ),
                    "mode": "live",
                    "client_context": {
                        "now": "2026-07-24T13:00:00+08:00"
                    },
                },
            )
            if response.status_code >= 400:
                print(
                    json.dumps(
                        {
                            "http_status": response.status_code,
                            "error": response.json().get("error", {}),
                            "secrets_printed": False,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                response.raise_for_status()
            payload = response.json()

    plan = payload.get("plan") or {}
    task_items = [
        {
            "title": item["title"],
            "start_at": item["start_at"],
            "end_at": item["end_at"],
            "location_id": item["location_id"],
        }
        for item in plan.get("items", [])
        if item.get("item_type") == "task"
    ]
    print(
        json.dumps(
            {
                "status": payload["status"],
                "plan_status": plan.get("status"),
                "task_count": len(task_items),
                "tasks": task_items,
                "data_freshness": payload["data_freshness"],
                "hard_violation_count": plan.get("metrics", {}).get(
                    "hard_violation_count"
                ),
                "warning_codes": [
                    warning["code"] for warning in payload["warnings"]
                ],
                "warnings": [
                    {
                        "code": warning["code"],
                        "message": warning["message"],
                        "details": warning.get("details", {}),
                    }
                    for warning in payload["warnings"]
                ],
                "execution_steps": payload["execution_steps"],
                "secrets_printed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
