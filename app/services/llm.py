from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import requests
from pydantic import ValidationError

from app.errors import AppError
from app.schemas.context import RetrievedFact
from app.schemas.plan import Plan
from app.schemas.understand import UnderstandResult


class OpenAICompatibleLLM:
    def __init__(
        self,
        *,
        enabled: bool,
        model: str,
        base_url: str,
        api_key: str,
        enable_thinking: bool,
        timeout_seconds: float,
        prompt_dir: Path,
        campus_context_path: Path | None = None,
    ) -> None:
        self.enabled = enabled
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.enable_thinking = enable_thinking
        self.timeout_seconds = timeout_seconds
        self.prompt_dir = prompt_dir
        self.campus_context_path = campus_context_path

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled and self.base_url and self.api_key and self.model
        )

    async def parse_requirement(
        self,
        *,
        query: str,
        now_iso: str,
        memory_context: list[dict[str, Any]] | None = None,
    ) -> UnderstandResult:
        if not self.configured:
            raise AppError(
                "LLM_NOT_CONFIGURED",
                "大模型尚未配置",
                status_code=503,
                retryable=False,
            )
        prompt = (self.prompt_dir / "understand.md").read_text(
            encoding="utf-8"
        )
        campus_context = ""
        if self.campus_context_path and self.campus_context_path.exists():
            campus_context = self.campus_context_path.read_text(
                encoding="utf-8"
            )
        schema = UnderstandResult.model_json_schema()
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"now={now_iso}\nquery={query}\n"
                    f"campus_time_context={campus_context}\n"
                    "user_memory_context="
                    f"{json.dumps(memory_context or [], ensure_ascii=False)}\n"
                    f"JSON Schema={json.dumps(schema, ensure_ascii=False)}"
                ),
            },
        ]
        last_error: Exception | None = None
        for attempt in range(2):
            if attempt and last_error:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "上一次输出未通过校验。只返回修正后的 JSON。"
                            f"错误：{last_error}"
                        ),
                    }
                )
            try:
                payload = await self._chat(
                    messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                return UnderstandResult.model_validate_json(payload)
            except (ValidationError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
        raise AppError(
            "LLM_OUTPUT_INVALID",
            "模型连续两次未返回合法结构",
            status_code=502,
            retryable=True,
            details=[{"reason": str(last_error)}],
        )

    async def render_plan(
        self,
        *,
        plan: Plan,
        warnings: list[dict[str, Any]],
    ) -> str:
        if not self.configured:
            raise AppError(
                "LLM_NOT_CONFIGURED",
                "大模型尚未配置",
                status_code=503,
            )
        prompt = (self.prompt_dir / "respond.md").read_text(encoding="utf-8")
        return await self._chat(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "plan": plan.model_dump(mode="json"),
                            "warnings": warnings,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.2,
        )

    async def polish_answer(
        self,
        *,
        draft: str,
        context: dict[str, Any],
    ) -> str:
        if not self.configured:
            raise AppError(
                "LLM_NOT_CONFIGURED",
                "大模型尚未配置",
                status_code=503,
            )
        prompt = (self.prompt_dir / "respond.md").read_text(encoding="utf-8")
        return await self._chat(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "verified_draft": draft,
                            "structured_context": context,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.25,
        )

    async def answer_question(
        self,
        *,
        query: str,
        facts: list[RetrievedFact],
    ) -> str:
        if not self.configured:
            raise AppError(
                "LLM_NOT_CONFIGURED",
                "大模型尚未配置",
                status_code=503,
            )
        prompt = (self.prompt_dir / "qa.md").read_text(encoding="utf-8")
        evidence = [
            {
                "content": fact.content,
                "source_ref": fact.source_ref,
                "priority": fact.priority,
                "verified_at": (
                    fact.verified_at.isoformat()
                    if fact.verified_at
                    else None
                ),
            }
            for fact in facts
        ]
        return await self._chat(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"query": query, "evidence": evidence},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
        )

    async def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        response_format: dict[str, str] | None = None,
        temperature: float,
    ) -> str:
        url = (
            self.base_url
            if self.base_url.endswith("/chat/completions")
            else f"{self.base_url}/chat/completions"
        )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            # Qwen3.7-Plus enables hybrid thinking by default. The planner
            # needs low-latency, deterministic JSON more than visible
            # reasoning, so thinking stays off unless explicitly enabled.
            "enable_thinking": self.enable_thinking,
        }
        if response_format:
            body["response_format"] = response_format
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            payload = await asyncio.to_thread(
                self._post_sync,
                url,
                body,
                headers,
            )
        except requests.RequestException as exc:
            raise AppError(
                "LLM_PROVIDER_ERROR",
                "模型服务调用失败",
                status_code=502,
                retryable=True,
                details=[
                    {
                        "reason": str(exc),
                        "provider_error_type": type(exc).__name__,
                    }
                ],
            ) from exc
        return payload["choices"][0]["message"]["content"]

    def _post_sync(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        response = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
