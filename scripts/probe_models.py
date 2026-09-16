"""Probe every candidate model: can it be called, and is its output usable?

The production adapter hides provider errors and falls through the chain, so a
model that is simply unavailable looks the same as one that is slow. This
probes each model on its own: a raw ping that surfaces the provider's real
error, then the actual requirement parse the product depends on.

    uv run python -m scripts.probe_models
    uv run python -m scripts.probe_models --models qwen3.8-max,glm-5.3
"""
from __future__ import annotations

import argparse
import asyncio
import json
from time import perf_counter

import requests

from app.config import BASE_DIR, Settings
from app.errors import AppError
from app.services.llm import OpenAICompatibleLLM

# Candidates worth ranking, strongest-looking first.
DEFAULT_MODELS = (
    "qwen3.8-2.4t-a95b",
    "deepseek-v4-pro-0813",
    "glm-5.3",
    "glm-5.2",
    "qwen3.8-max",
    "qwen3.8-27b",
)

# A request whose correct reading is unambiguous, so a model that returns JSON
# but misreads the constraints is still visibly wrong.
QUERY = (
    "今天14点后去图书馆自习2小时，再去菜鸟驿站取快递，"
    "最后去东操场跑步30分钟，18点前结束。"
)
NOW = "2026-07-24T13:00:00+08:00"


def ping(model: str, settings: Settings, timeout: float) -> tuple[bool, str]:
    """Smallest possible real call, returning the provider's own error text."""
    base = settings.llm_base_url.rstrip("/")
    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    try:
        r = requests.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "回复一个字：好"}],
                "temperature": 0,
                "max_tokens": 8,
            },
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, f"{type(exc).__name__}: {exc}"[:160]
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {})
            detail = err.get("message") or err.get("code") or r.text
        except ValueError:
            detail = r.text
        return False, f"HTTP {r.status_code}: {str(detail)[:150]}"
    try:
        return True, r.json()["choices"][0]["message"]["content"].strip()[:40]
    except (ValueError, KeyError, IndexError, TypeError):
        return False, f"unparseable response: {r.text[:120]}"


async def parse(model: str, settings: Settings, timeout: float) -> dict:
    llm = OpenAICompatibleLLM(
        enabled=True,
        model=model,
        fallback_models=[],          # isolate the model under test
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        enable_thinking=False,
        timeout_seconds=timeout,
        prompt_dir=BASE_DIR / "prompts",
        campus_context_path=settings.app_data_dir / "class_periods.json",
    )
    started = perf_counter()
    try:
        result = await llm.parse_requirement(query=QUERY, now_iso=NOW)
    except (AppError, requests.RequestException, ValueError, KeyError,
            IndexError, TypeError) as exc:
        return {
            "ok": False,
            "seconds": round(perf_counter() - started, 1),
            "detail": f"{type(exc).__name__}: {exc}"[:150],
        }
    seconds = round(perf_counter() - started, 1)
    durations = sorted(t.duration_min for t in result.tasks)
    return {
        "ok": True,
        "seconds": seconds,
        "tasks": len(result.tasks),
        # The correct reading is three tasks of 120 / 30 / short pickup.
        "correct": len(result.tasks) == 3 and 120 in durations and 30 in durations,
        "durations": durations,
        "clarifications": len(result.clarifications),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--timeout", type=float, default=90.0,
                    help="generous on purpose: measure true latency, then "
                         "decide what fits the 18s production budget")
    args = ap.parse_args()

    settings = Settings()
    if not (settings.llm_base_url and settings.llm_api_key):
        raise SystemExit(
            "缺少 LLM_BASE_URL / LLM_API_KEY。请在 .env 中填好后重试。"
        )

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    print(f"endpoint: {settings.llm_base_url}")
    print(f"probing {len(models)} models (timeout {args.timeout}s)\n")
    print(f"{'model':<26} {'ping':<6} {'parse':<7} {'sec':>6}  note")
    print("-" * 92)

    rows = []
    for model in models:
        ok, detail = await asyncio.to_thread(ping, model, settings, args.timeout)
        if not ok:
            print(f"{model:<26} {'FAIL':<6} {'-':<7} {'-':>6}  {detail}")
            rows.append({"model": model, "callable": False, "detail": detail})
            continue
        res = await parse(model, settings, args.timeout)
        if res["ok"]:
            flag = "OK" if res["correct"] else "WEAK"
            note = f"{res['tasks']} tasks {res['durations']}"
            if res["clarifications"]:
                note += f" +{res['clarifications']} clarify"
        else:
            flag, note = "FAIL", res["detail"]
        print(f"{model:<26} {'OK':<6} {flag:<7} {res['seconds']:>6}  {note}")
        rows.append({"model": model, "callable": True, **res})

    good = [r for r in rows if r.get("correct")]
    print("\n--- 结论 ---")
    if good:
        fastest = min(good, key=lambda r: r["seconds"])
        print("可用且解析正确：", ", ".join(f"{r['model']}({r['seconds']}s)" for r in good))
        print(f"首选候选（18s 预算内最强/最稳）：{good[0]['model']}")
        quick = ", ".join(r["model"] for r in good if r["seconds"] < 6)
        print("降级位候选（需 <6s）：", quick or
              f"无，最快的是 {fastest['model']} {fastest['seconds']}s")
    else:
        print("没有模型通过解析测试。")
    out = BASE_DIR / "reports" / "model_probe.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n明细已写入 {out}")


if __name__ == "__main__":
    asyncio.run(main())
