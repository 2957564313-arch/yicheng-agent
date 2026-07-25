from __future__ import annotations

import argparse
import asyncio
import json
from time import perf_counter

from app.config import BASE_DIR, Settings
from app.services.llm import OpenAICompatibleLLM


async def run(model: str, timeout_seconds: float) -> None:
    settings = Settings()
    llm = OpenAICompatibleLLM(
        enabled=True,
        model=model,
        fallback_models=[],
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        enable_thinking=False,
        timeout_seconds=timeout_seconds,
        prompt_dir=BASE_DIR / "prompts",
        campus_context_path=settings.app_data_dir / "class_periods.json",
    )
    if not llm.configured:
        raise RuntimeError("大模型连接信息不完整")

    started = perf_counter()
    try:
        result = await llm.parse_requirement(
            query=(
                "今天14点后去图书馆自习2小时，再去菜鸟驿站"
                "取快递，最后去东操场跑步30分钟，18点前结束。"
            ),
            now_iso="2026-07-24T13:00:00+08:00",
        )
        first_task = result.tasks[0] if result.tasks else None
        payload = {
            "model": model,
            "ok": True,
            "elapsed_seconds": round(perf_counter() - started, 2),
            "intent": result.intent.value,
            "task_count": len(result.tasks),
            "first_earliest_start": (
                first_task.earliest_start.isoformat()
                if first_task and first_task.earliest_start
                else None
            ),
            "clarification_count": len(result.clarifications),
            "clarifications": result.clarifications,
            "tasks": [
                {
                    "id": task.id,
                    "duration_min": task.duration_min,
                    "location_raw": task.location_raw,
                    "earliest_start": (
                        task.earliest_start.isoformat()
                        if task.earliest_start
                        else None
                    ),
                    "deadline": (
                        task.deadline.isoformat()
                        if task.deadline
                        else None
                    ),
                    "depends_on": task.depends_on,
                }
                for task in result.tasks
            ],
            "secrets_printed": False,
        }
    except Exception as exc:
        payload = {
            "model": model,
            "ok": False,
            "elapsed_seconds": round(perf_counter() - started, 2),
            "error_type": type(exc).__name__,
            "error_code": getattr(exc, "code", None),
            "secrets_printed": False,
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default="qwen3.6-flash",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45,
    )
    arguments = parser.parse_args()
    asyncio.run(run(arguments.model, arguments.timeout))


if __name__ == "__main__":
    main()
