from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.llm import OpenAICompatibleLLM


def main() -> None:
    settings = Settings()
    llm = OpenAICompatibleLLM(
        enabled=settings.llm_enabled,
        model=settings.llm_model,
        fallback_models=settings.llm_models[1:],
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        enable_thinking=settings.llm_enable_thinking,
        timeout_seconds=settings.llm_timeout_seconds,
        prompt_dir=Path("prompts"),
        campus_context_path=settings.app_data_dir / "class_periods.json",
    )
    if not llm.configured:
        raise SystemExit("LLM is not configured")

    parsed = asyncio.run(
        llm.parse_requirement(
            query="明天第6节下课后去图书馆自习一个小时。",
            now_iso="2026-07-24T14:20:00+08:00",
        )
    )

    with TemporaryDirectory(prefix="yicheng-live-smoke-") as temporary:
        temp = Path(temporary)
        app_settings = Settings(
            app_database_path=temp / "app.db",
            app_checkpoint_database_path=temp / "checkpoints.db",
            live_route_enabled=False,
            live_weather_enabled=False,
        )
        with TestClient(create_app(app_settings)) as client:
            response = client.post(
                "/api/v1/chat",
                json={
                    "user_id": "live_smoke_user",
                    "thread_id": "live_smoke_thread",
                    "query": "学生考试作弊行为如何认定？",
                    "mode": "auto",
                    "client_context": {
                        "now": "2026-07-24T14:20:00+08:00"
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()

    first_task = parsed.tasks[0] if parsed.tasks else None
    print(
        json.dumps(
            {
                "model": settings.llm_model,
                "class_period_parse": {
                    "intent": parsed.intent,
                    "task_count": len(parsed.tasks),
                    "earliest_start": (
                        first_task.earliest_start.isoformat()
                        if first_task and first_task.earliest_start
                        else None
                    ),
                    "fixed_start": (
                        first_task.fixed_start.isoformat()
                        if first_task and first_task.fixed_start
                        else None
                    ),
                },
                "knowledge_query": {
                    "status": payload["status"],
                    "has_plan": payload["plan"] is not None,
                    "knowledge_source": payload["data_freshness"][
                        "knowledge"
                    ],
                    "answer_preview": payload["answer"][:300],
                },
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
