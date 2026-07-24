from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.config import BASE_DIR, Settings
from app.main import create_app


def main() -> None:
    summaries = []
    with TemporaryDirectory(prefix="yicheng-demo-smoke-") as temporary:
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
            for demo_id in (
                "demo_01_normal",
                "demo_02_emergency",
                "demo_03_degraded",
            ):
                response = client.post(f"/api/v1/demos/{demo_id}/run")
                response.raise_for_status()
                payload = response.json()
                task_items = [
                    {
                        "task_id": item["task_id"],
                        "start_at": item["start_at"],
                        "end_at": item["end_at"],
                    }
                    for item in payload["plan"]["items"]
                    if item["item_type"] == "task"
                ]
                summaries.append(
                    {
                        "demo_id": demo_id,
                        "status": payload["status"],
                        "plan_status": payload["plan"]["status"],
                        "hard_violation_count": payload["plan"]["metrics"][
                            "hard_violation_count"
                        ],
                        "tasks": task_items,
                        "plan_diff": payload["plan_diff"],
                    }
                )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
