from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from app.errors import AppError
from app.services.llm import OpenAICompatibleLLM


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "choices": [
                {"message": {"content": self.content}},
            ]
        }


class FakeClient:
    contents: list[str] = []
    calls: list[tuple[str, dict, dict]] = []

    @classmethod
    def post(
        cls,
        url: str,
        *,
        json: dict,
        headers: dict,
        timeout: float,
    ) -> FakeResponse:
        cls.calls.append((url, json, headers))
        return FakeResponse(cls.contents.pop(0))


def build_llm(prompt_dir: Path) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        enabled=True,
        model="qwen-test",
        fallback_models=[],
        base_url="https://model.example/v1",
        api_key="test-key",
        enable_thinking=False,
        timeout_seconds=5,
        prompt_dir=prompt_dir,
    )


@pytest.mark.asyncio
async def test_openai_compatible_parser_request(monkeypatch, tmp_path: Path):
    (tmp_path / "understand.md").write_text("parse", encoding="utf-8")
    valid = {
        "intent": "plan",
        "requested_date": "2026-07-24",
        "tasks": [
            {
                "id": "study",
                "title": "自习",
                "date": "2026-07-24",
                "duration_min": 60,
                "location_raw": "图书馆",
                "earliest_start": "2026-07-24T13:00:00+08:00",
                "latest_end": "2026-07-24T18:00:00+08:00",
                "flexibility": "movable",
            }
        ],
        "preferences": {},
        "clarifications": [],
        "confidence": 0.9,
    }
    fake = type("LLMClient", (FakeClient,), {})
    fake.contents = [json.dumps(valid, ensure_ascii=False)]
    fake.calls = []
    monkeypatch.setattr("app.services.llm.requests.post", fake.post)

    result = await build_llm(tmp_path).parse_requirement(
        query="明天下午学习一个小时",
        now_iso="2026-07-23T08:00:00+08:00",
    )

    assert result.tasks[0].duration_min == 60
    url, body, headers = fake.calls[0]
    assert url == "https://model.example/v1/chat/completions"
    assert body["model"] == "qwen-test"
    assert body["enable_thinking"] is False
    assert body["response_format"] == {"type": "json_object"}
    assert headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_invalid_model_output_is_retried_then_rejected(
    monkeypatch,
    tmp_path: Path,
):
    (tmp_path / "understand.md").write_text("parse", encoding="utf-8")
    fake = type("InvalidLLMClient", (FakeClient,), {})
    fake.contents = ["not-json", "{}"]
    fake.calls = []
    monkeypatch.setattr("app.services.llm.requests.post", fake.post)

    with pytest.raises(AppError) as error:
        await build_llm(tmp_path).parse_requirement(
            query="明天下午学习",
            now_iso="2026-07-23T08:00:00+08:00",
        )

    assert error.value.code == "LLM_OUTPUT_INVALID"
    assert len(fake.calls) == 2


@pytest.mark.asyncio
async def test_provider_failure_switches_to_fallback_model(
    monkeypatch,
    tmp_path: Path,
):
    (tmp_path / "respond.md").write_text("respond", encoding="utf-8")
    llm = OpenAICompatibleLLM(
        enabled=True,
        model="qwen-primary",
        fallback_models=["qwen-backup"],
        base_url="https://model.example/v1",
        api_key="test-key",
        enable_thinking=False,
        timeout_seconds=5,
        prompt_dir=tmp_path,
    )
    attempted: list[str] = []

    def fake_post(
        url: str,
        body: dict,
        headers: dict,
        timeout_seconds: float,
    ) -> dict:
        attempted.append(body["model"])
        if body["model"] == "qwen-primary":
            raise requests.HTTPError("quota exhausted")
        return {"choices": [{"message": {"content": "备用模型已接管"}}]}

    monkeypatch.setattr(llm, "_post_sync", fake_post)

    answer = await llm.polish_answer(draft="草稿", context={})

    assert answer == "备用模型已接管"
    assert attempted == ["qwen-primary", "qwen-backup"]
    assert llm.used_model_label == "qwen-backup"


@pytest.mark.asyncio
async def test_malformed_provider_response_switches_model(
    monkeypatch,
    tmp_path: Path,
):
    (tmp_path / "respond.md").write_text("respond", encoding="utf-8")
    llm = OpenAICompatibleLLM(
        enabled=True,
        model="qwen-primary",
        fallback_models=["qwen-backup"],
        base_url="https://model.example/v1",
        api_key="test-key",
        enable_thinking=False,
        timeout_seconds=5,
        prompt_dir=tmp_path,
    )
    responses = iter(
        [
            {"message": "temporarily unavailable"},
            {"choices": [{"message": {"content": "已恢复"}}]},
        ]
    )
    monkeypatch.setattr(
        llm,
        "_post_sync",
        lambda url, body, headers, timeout_seconds: next(responses),
    )

    assert await llm.polish_answer(draft="草稿", context={}) == "已恢复"
    assert llm.used_model_label == "qwen-backup"
