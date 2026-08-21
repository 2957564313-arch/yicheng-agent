from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.llm import OpenAICompatibleLLM
from app.services.scheduler import Scheduler


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="调用真实模型并输出需求解析的原始 JSON 与校验结果。",
    )
    parser.add_argument("query", nargs="?")
    parser.add_argument("--query-base64")
    parser.add_argument("--now", required=True)
    parser.add_argument("--history-json", default="[]")
    parser.add_argument("--memory-json", default="[]")
    parser.add_argument(
        "--full-app",
        action="store_true",
        help="同时通过临时数据库调用完整聊天与排程链路。",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="只输出模型原始响应和最终 API 结果。",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="只输出模型任务、合并任务与最终时间轴，便于线上验收。",
    )
    return parser


async def _run(args: argparse.Namespace) -> None:
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

    history = json.loads(args.history_json)
    memory = json.loads(args.memory_json)
    raw_calls: list[dict[str, Any]] = []
    original_chat = llm._chat

    async def traced_chat(messages, **kwargs):
        raw = await original_chat(messages, **kwargs)
        raw_calls.append(
            {
                "messages": messages,
                "response_format": kwargs.get("response_format"),
                "raw_response": raw,
            }
        )
        return raw

    llm._chat = traced_chat  # type: ignore[method-assign]
    query = args.query
    if args.query_base64:
        query = base64.b64decode(args.query_base64).decode("utf-8")
    if not query:
        raise SystemExit("query or --query-base64 is required")
    parse_kwargs = {
        "query": query,
        "now_iso": args.now,
        "memory_context": memory,
    }
    if history:
        parse_kwargs["history"] = history
    parsed = await llm.parse_requirement(**parse_kwargs)
    full_app_response = None
    scheduler_calls: list[dict[str, Any]] = []
    if args.full_app:
        original_schedule = Scheduler.schedule

        def traced_schedule(self, **kwargs):
            context = kwargs["context"]
            result = original_schedule(self, **kwargs)
            scheduler_calls.append(
                {
                    "tasks": [
                        task.model_dump(mode="json")
                        for task in kwargs["tasks"]
                    ],
                    "preferences": kwargs["preferences"].model_dump(
                        mode="json"
                    ),
                    "context": {
                        "target_date": context.target_date.isoformat(),
                        "now": context.now.isoformat(),
                        "day_start": context.day_start.isoformat(),
                        "day_end": context.day_end.isoformat(),
                        "opening_windows": {
                            key: [
                                [start.isoformat(), end.isoformat()]
                                for start, end in windows
                            ]
                            for key, windows in context.opening_windows.items()
                        },
                        "task_windows": {
                            key: [
                                [start.isoformat(), end.isoformat()]
                                for start, end in windows
                            ]
                            for key, windows in context.task_windows.items()
                        },
                        "soft_meal_windows": [
                            window.model_dump(mode="json")
                            for window in context.soft_meal_windows
                        ],
                    },
                    "result": {
                        "unscheduled_task_ids": result.unscheduled_task_ids,
                        "items": [
                            item.model_dump(mode="json")
                            for item in result.plan.items
                        ],
                    },
                }
            )
            return result

        Scheduler.schedule = traced_schedule
        with TemporaryDirectory(prefix="yicheng-live-trace-") as temporary:
            temp = Path(temporary)
            app_settings = Settings(
                app_database_path=temp / "app.db",
                app_checkpoint_database_path=temp / "checkpoints.db",
                app_access_enabled=False,
            )
            with TestClient(create_app(app_settings)) as client:
                response = client.post(
                    "/api/v1/chat",
                    json={
                        "user_id": "live_trace_user",
                        "thread_id": "live_trace_thread",
                        "query": query,
                        "mode": "auto",
                        "client_context": {"now": args.now},
                    },
                )
                full_app_response = response.json()
        Scheduler.schedule = original_schedule

    printed_calls = raw_calls
    if args.compact:
        printed_calls = [
            {
                "response_format": call["response_format"],
                "raw_response": call["raw_response"],
            }
            for call in raw_calls
        ]
    payload = {
                "model": llm.used_model_label,
                "raw_calls": printed_calls,
                "validated": parsed.model_dump(mode="json"),
                "scheduler_calls": scheduler_calls,
                "full_app_response": full_app_response,
            }
    if args.summary:
        last_schedule = scheduler_calls[-1] if scheduler_calls else None
        payload = {
            "model": llm.used_model_label,
            "model_json": (
                raw_calls[0]["raw_response"] if raw_calls else None
            ),
            "validated_tasks": [
                task.model_dump(mode="json") for task in parsed.tasks
            ],
            "merged_tasks": (
                last_schedule["tasks"] if last_schedule else None
            ),
            "unscheduled_task_ids": (
                last_schedule["result"]["unscheduled_task_ids"]
                if last_schedule
                else None
            ),
            "timeline": (
                [
                    {
                        "title": item["title"],
                        "start_at": item["start_at"],
                        "end_at": item["end_at"],
                        "item_type": item["item_type"],
                    }
                    for item in last_schedule["result"]["items"]
                ]
                if last_schedule
                else None
            ),
            "answer": (
                full_app_response.get("answer")
                if isinstance(full_app_response, dict)
                else None
            ),
        }
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    main()
