from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import requests
from pydantic import ValidationError

from app.errors import AppError
from app.schemas.context import RetrievedFact
from app.schemas.plan import Plan
from app.schemas.plan_edit import PlanEdit
from app.schemas.understand import UnderstandResult
from app.schemas.weekly import WeeklyTextInterpretation


class OpenAICompatibleLLM:
    def __init__(
        self,
        *,
        enabled: bool,
        model: str,
        fallback_models: list[str] | None,
        base_url: str,
        api_key: str,
        enable_thinking: bool,
        timeout_seconds: float,
        prompt_dir: Path,
        campus_context_path: Path | None = None,
    ) -> None:
        self.enabled = enabled
        self.model = model
        self.models = tuple(
            dict.fromkeys(
                name.strip()
                for name in [model, *(fallback_models or [])]
                if name.strip()
            )
        )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.enable_thinking = enable_thinking
        self.timeout_seconds = timeout_seconds
        self.prompt_dir = prompt_dir
        self.campus_context_path = campus_context_path
        self._used_models: ContextVar[tuple[str, ...]] = ContextVar(
            f"used_llm_models_{id(self)}",
            default=(),
        )

    @property
    def configured(self) -> bool:
        return bool(
            self.enabled and self.base_url and self.api_key and self.models
        )

    @property
    def model_chain_label(self) -> str:
        return " → ".join(self.models)

    @property
    def used_model_label(self) -> str | None:
        used = self._used_models.get()
        return " → ".join(used) if used else None

    def reset_usage(self) -> None:
        """Start request-local model usage tracking."""
        self._used_models.set(())

    def _record_successful_model(self, model: str) -> None:
        used = self._used_models.get()
        if model not in used:
            self._used_models.set((*used, model))

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
        # Reference material first, the request last.  The schema alone
        # runs to thousands of tokens; with the request in front of it the
        # model reliably dropped stated constraints such as “白天”.
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "<json_schema>\n"
                    f"{json.dumps(schema, ensure_ascii=False)}\n"
                    "</json_schema>\n"
                    "<campus_time_context>\n"
                    f"{campus_context}\n"
                    "</campus_time_context>\n"
                    "<user_memory_context>\n"
                    f"{json.dumps(memory_context or [], ensure_ascii=False)}"
                    "\n</user_memory_context>\n"
                    f"<now>{now_iso}</now>\n"
                    "<request>\n"
                    f"{query}\n"
                    "</request>\n"
                    "先逐条对照 <request> 中出现的时段词、时长、次数和"
                    "顺序词，确认每一条都落到了对应字段上，再输出 JSON。"
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

    async def parse_plan_edit(
        self,
        *,
        query: str,
        now_iso: str,
        plan_summary: str,
        history: list[dict[str, str]] | None = None,
    ) -> PlanEdit:
        """Read a follow-up as a change to the plan the student already has.

        The model is given the day and the conversation so it can resolve
        “把这个挪到下午”, and it answers with the change rather than a new
        day — re-emitting the whole plan is how the arrangements nobody
        mentioned get lost.
        """

        if not self.configured:
            raise AppError(
                "LLM_NOT_CONFIGURED",
                "大模型尚未配置",
                status_code=503,
                retryable=False,
            )
        prompt = (self.prompt_dir / "plan_edit.md").read_text(
            encoding="utf-8"
        )
        schema = PlanEdit.model_json_schema()
        transcript = "".join(
            f"{turn.get('role', 'user')}: {turn.get('content', '')}" + chr(10)
            for turn in (history or [])
        )
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    "<json_schema>\n"
                    f"{json.dumps(schema, ensure_ascii=False)}\n"
                    "</json_schema>\n"
                    "<current_plan>\n"
                    f"{plan_summary}\n"
                    "</current_plan>\n"
                    "<conversation>\n"
                    f"{transcript}"
                    "</conversation>\n"
                    f"<now>{now_iso}</now>\n"
                    "<request>\n"
                    f"{query}\n"
                    "</request>\n"
                    "只输出被点名的改动。没被提到的安排不要出现在 operations 里。"
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
                return PlanEdit.model_validate_json(payload)
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

    async def parse_weekly_requirement(
        self,
        *,
        query: str,
        week_start: str,
        now_iso: str,
        memory_context: list[dict[str, Any]] | None = None,
    ) -> WeeklyTextInterpretation:
        if not self.configured:
            raise AppError(
                "LLM_NOT_CONFIGURED",
                "大模型尚未配置",
                status_code=503,
                retryable=False,
            )
        prompt = (self.prompt_dir / "weekly_understand.md").read_text(
            encoding="utf-8"
        )
        schema = WeeklyTextInterpretation.model_json_schema()
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"now={now_iso}\nweek_start={week_start}\n"
                    f"query={query}\n"
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
                return WeeklyTextInterpretation.model_validate_json(payload)
            except (ValidationError, json.JSONDecodeError, KeyError) as exc:
                last_error = exc
        raise AppError(
            "LLM_OUTPUT_INVALID",
            "模型连续两次未返回合法周目标结构",
            status_code=502,
            retryable=True,
            details=[{"reason": str(last_error)}],
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
                "source_title": fact.metadata.get("title"),
                "source_page": fact.metadata.get("page"),
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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        attempted_models: list[str] = []
        for index, model in enumerate(self.models):
            attempted_models.append(model)
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                # The planner needs deterministic JSON more than visible
                # reasoning, so hybrid thinking stays explicitly controlled.
                "enable_thinking": self.enable_thinking,
            }
            if response_format:
                body["response_format"] = response_format
            try:
                payload = await asyncio.to_thread(
                    self._post_sync,
                    url,
                    body,
                    headers,
                    (
                        min(self.timeout_seconds, 18)
                        if index == 0
                        else min(self.timeout_seconds, 6)
                    ),
                )
                content = payload["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("provider returned empty content")
                self._record_successful_model(model)
                return content
            except (
                requests.RequestException,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ) as exc:
                # Quota exhaustion, rate limiting, a temporarily unavailable
                # model, and malformed provider responses all move to the
                # next configured model. No provider detail reaches the user.
                last_error = exc
                continue
        raise AppError(
            "LLM_PROVIDER_ERROR",
            "模型服务暂时不可用，已切换为基础规划模式",
            status_code=502,
            retryable=True,
            details=[
                {
                    "attempted_model_count": len(attempted_models),
                    **self._safe_provider_error_details(last_error),
                }
            ],
        ) from last_error

    @staticmethod
    def _safe_provider_error_details(
        error: Exception | None,
    ) -> dict[str, Any]:
        """Expose actionable provider metadata without leaking response data."""
        if error is None:
            return {"provider_error_type": "UnknownError"}

        details: dict[str, Any] = {
            "provider_error_type": type(error).__name__,
            "provider_exception_type": type(error).__name__,
        }
        if not isinstance(error, requests.HTTPError):
            return details
        response = error.response
        if response is None:
            return details

        details["provider_status_code"] = response.status_code
        try:
            payload = response.json()
        except (requests.RequestException, TypeError, ValueError):
            return details
        if not isinstance(payload, dict):
            return details
        provider_error = payload.get("error")
        if not isinstance(provider_error, dict):
            return details
        provider_code = provider_error.get("code")
        provider_type = provider_error.get("type")
        if isinstance(provider_code, (str, int, float, bool)):
            details["provider_error_code"] = provider_code
        if isinstance(provider_type, (str, int, float, bool)):
            details["provider_error_type"] = provider_type
        return details

    def _post_sync(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        response = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=timeout_seconds or self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
