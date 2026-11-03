"""User-scoped explicit memory creation, retrieval, inspection, and deletion."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from backend.api.schemas import MemoryCreateRequest, MemoryListResponse, MemorySummary
from backend.config import get_settings
from backend.database.models import MemoryRecord
from backend.memory.manager import MemoryManager

router = APIRouter(prefix="/memories", tags=["memory"])


def _manager(request: Request) -> MemoryManager:
    return request.app.state.memory_manager


def _summary(record: MemoryRecord) -> MemorySummary:
    return MemorySummary(
        id=record.id,
        content=record.content,
        tags=record.tags,
        importance=record.importance,
        source_conversation_id=record.source_conversation_id,
        source_task_id=record.source_task_id,
        created_at=record.created_at,
    )


@router.post("", response_model=MemorySummary, status_code=status.HTTP_201_CREATED)
async def create_memory(payload: MemoryCreateRequest, request: Request) -> MemorySummary:
    record = _manager(request).create(
        user_id=get_settings().local_user_id,
        content=payload.content,
        tags=payload.tags,
        importance=payload.importance,
        source_conversation_id=payload.source_conversation_id,
        source_task_id=payload.source_task_id,
    )
    return _summary(record)


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    request: Request,
    query: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=200),
) -> MemoryListResponse:
    user_id = get_settings().local_user_id
    manager = _manager(request)
    items = manager.search(query, user_id, limit) if query else manager.list(user_id, limit)
    return MemoryListResponse(items=[_summary(item) for item in items])


@router.get("/{memory_id}", response_model=MemorySummary)
async def get_memory(memory_id: UUID, request: Request) -> MemorySummary:
    record = _manager(request).get(memory_id, get_settings().local_user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Memory was not found")
    return _summary(record)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: UUID, request: Request) -> Response:
    deleted = _manager(request).delete(memory_id, get_settings().local_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory was not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
