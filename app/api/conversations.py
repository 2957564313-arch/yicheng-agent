from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request, Response, status

from app.api.chat import execute_chat
from app.errors import AppError
from app.schemas.chat import ChatRequest
from app.schemas.conversation import (
    ConversationDetail,
    ConversationForkRequest,
    ConversationForkResponse,
    ConversationThread,
    ConversationThreadUpdate,
)

router = APIRouter(prefix="/api/v1/users", tags=["conversations"])


@router.get("/{user_id}/threads", response_model=list[ConversationThread])
def list_threads(
    user_id: str,
    request: Request,
    limit: int = Query(default=40, ge=1, le=100),
) -> list[ConversationThread]:
    return request.app.state.container.conversations.list_threads(
        user_id=user_id,
        limit=limit,
    )


@router.get(
    "/{user_id}/threads/{thread_id}",
    response_model=ConversationDetail,
)
def get_thread(
    user_id: str,
    thread_id: str,
    request: Request,
) -> ConversationDetail:
    detail = request.app.state.container.conversations.get_detail(
        user_id=user_id,
        thread_id=thread_id,
    )
    if detail is None:
        raise AppError(
            "THREAD_NOT_FOUND",
            "未找到这条对话。",
            status_code=404,
        )
    return detail


@router.patch(
    "/{user_id}/threads/{thread_id}",
    response_model=ConversationThread,
)
def rename_thread(
    user_id: str,
    thread_id: str,
    payload: ConversationThreadUpdate,
    request: Request,
) -> ConversationThread:
    container = request.app.state.container
    thread = container.conversations.rename(
        user_id=user_id,
        thread_id=thread_id,
        title=payload.title.strip(),
        now=datetime.now(ZoneInfo(container.settings.app_timezone)),
    )
    if thread is None:
        raise AppError("THREAD_NOT_FOUND", "未找到这条对话。", status_code=404)
    return thread


@router.delete(
    "/{user_id}/threads/{thread_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_thread(
    user_id: str,
    thread_id: str,
    request: Request,
) -> Response:
    container = request.app.state.container
    deleted = container.conversations.delete(
        user_id=user_id,
        thread_id=thread_id,
        now=datetime.now(ZoneInfo(container.settings.app_timezone)),
    )
    if not deleted:
        raise AppError("THREAD_NOT_FOUND", "未找到这条对话。", status_code=404)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{user_id}/threads/{thread_id}/fork",
    response_model=ConversationForkResponse,
)
async def fork_thread(
    user_id: str,
    thread_id: str,
    payload: ConversationForkRequest,
    request: Request,
) -> ConversationForkResponse:
    container = request.app.state.container
    now = (
        payload.client_context.now.astimezone(
            ZoneInfo(container.settings.app_timezone)
        )
        if payload.client_context and payload.client_context.now
        else datetime.now(ZoneInfo(container.settings.app_timezone))
    )
    try:
        branch, baseline = container.conversations.fork(
            user_id=user_id,
            thread_id=thread_id,
            from_message_id=payload.from_message_id,
            now=now,
        )
    except LookupError as exc:
        raise AppError(
            "MESSAGE_NOT_FOUND",
            "未找到要修改的历史问题。",
            status_code=404,
        ) from exc
    except ValueError as exc:
        raise AppError(
            "MESSAGE_NOT_EDITABLE",
            "只能从自己的历史提问创建分支。",
            status_code=422,
        ) from exc

    client_context = payload.client_context
    if client_context is not None:
        client_context = client_context.model_copy(
            update={"previous_plan": baseline}
        )
    response = await execute_chat(
        ChatRequest(
            user_id=user_id,
            thread_id=branch.id,
            query=payload.query,
            old_plan_id=baseline.id if baseline else None,
            mode=payload.mode,
            publish_to_agenda=payload.publish_to_agenda,
            client_context=client_context,
        ),
        request,
    )
    refreshed = container.conversations.get_detail(
        user_id=user_id,
        thread_id=branch.id,
    )
    assert refreshed is not None
    return ConversationForkResponse(
        branch=refreshed.thread,
        response=response,
    )
