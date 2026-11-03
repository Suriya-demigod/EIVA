"""Explicit, user-scoped long-term memory operations."""

from __future__ import annotations

from uuid import UUID

from backend.database.models import MemoryRecord
from backend.database.repositories import MemoryRepository
from backend.memory.retrieval import rank_memories


class MemoryManager:
    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    def create(
        self,
        *,
        user_id: str,
        content: str,
        tags: list[str] | None = None,
        importance: int = 3,
        source_conversation_id: UUID | None = None,
        source_task_id: UUID | None = None,
    ) -> MemoryRecord:
        normalized_tags = list(dict.fromkeys(tag.strip() for tag in (tags or []) if tag.strip()))
        record = MemoryRecord(
            user_id=user_id,
            content=content.strip(),
            tags=normalized_tags,
            importance=importance,
            source_conversation_id=source_conversation_id,
            source_task_id=source_task_id,
        )
        return self._repository.create(record)

    def list(self, user_id: str, limit: int = 100) -> list[MemoryRecord]:
        return self._repository.list_for_user(user_id, limit)

    def get(self, memory_id: UUID, user_id: str) -> MemoryRecord | None:
        return self._repository.get(memory_id, user_id)

    def search(self, query: str, user_id: str, limit: int = 10) -> list[MemoryRecord]:
        candidates = self._repository.list_for_user(user_id, limit=1000)
        return rank_memories(query, candidates, limit=limit)

    def delete(self, memory_id: UUID, user_id: str) -> bool:
        return self._repository.delete(memory_id, user_id)
