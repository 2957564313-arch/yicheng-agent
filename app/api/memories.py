from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response, status

from app.errors import AppError
from app.schemas.memory import (
    MemoryCreate,
    MemoryItem,
    MemoryListResponse,
    MemoryUpdate,
)


router = APIRouter(prefix="/api/v1/users", tags=["memories"])


@router.get("/{user_id}/memories", response_model=MemoryListResponse)
def list_memories(user_id: str, request: Request) -> MemoryListResponse:
    return MemoryListResponse(
        items=request.app.state.container.memories.list(user_id)
    )


@router.post(
    "/{user_id}/memories",
    response_model=MemoryItem,
    status_code=status.HTTP_201_CREATED,
)
def create_memory(
    user_id: str,
    payload: MemoryCreate,
    request: Request,
) -> MemoryItem:
    container = request.app.state.container
    return container.memories.upsert(
        user_id=user_id,
        payload=payload,
        now=datetime.now(ZoneInfo(container.settings.app_timezone)),
    )


@router.patch(
    "/{user_id}/memories/{memory_id}",
    response_model=MemoryItem,
)
def update_memory(
    user_id: str,
    memory_id: str,
    payload: MemoryUpdate,
    request: Request,
) -> MemoryItem:
    container = request.app.state.container
    memory = container.memories.update(
        user_id=user_id,
        memory_id=memory_id,
        payload=payload,
        now=datetime.now(ZoneInfo(container.settings.app_timezone)),
    )
    if memory is None:
        raise AppError("MEMORY_NOT_FOUND", "没有找到这条记忆", status_code=404)
    return memory


@router.delete(
    "/{user_id}/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_memory(
    user_id: str,
    memory_id: str,
    request: Request,
) -> Response:
    deleted = request.app.state.container.memories.delete(
        user_id=user_id,
        memory_id=memory_id,
    )
    if not deleted:
        raise AppError("MEMORY_NOT_FOUND", "没有找到这条记忆", status_code=404)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
