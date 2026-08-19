from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.chat import ChatResponse, ClientContext


class ConversationMessage(BaseModel):
    id: str
    thread_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class ConversationThread(BaseModel):
    id: str
    user_id: str
    title: str | None = None
    parent_thread_id: str | None = None
    forked_from_message_id: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message: str | None = None


class ConversationDetail(BaseModel):
    thread: ConversationThread
    messages: list[ConversationMessage] = Field(default_factory=list)


class ConversationThreadUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("对话名称不能为空")
        return normalized


class ConversationForkRequest(BaseModel):
    from_message_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["auto", "offline", "live"] = "auto"
    publish_to_agenda: bool = False
    client_context: ClientContext | None = None


class ConversationForkResponse(BaseModel):
    branch: ConversationThread
    response: ChatResponse
